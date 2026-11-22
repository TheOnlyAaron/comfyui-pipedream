"""
Media and file helpers for PD Output.

Path normalization, image batch writing, video and EXR encoding through
PyAV (the ``av`` package that ships with ComfyUI), preview image
generation for the node UI, and sidecar metadata writing.  No dependencies beyond what ComfyUI already installs.
"""

import json
import math
import os
import sys
import uuid
from fractions import Fraction

IMAGE_FORMATS = ("png", "exr", "jpg", "webp")
VIDEO_FORMATS = ("mp4", "mov", "webm")
BROWSER_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")
BROWSER_VIDEO_FORMATS = ("mp4", "webm")

PREVIEW_MAX_SIZE = 512

# format -> (label, PyAV encoder, pixel format, audio encoder)
_VIDEO_SPECS = {
    "mp4": ("h264", "libx264", "yuv420p", "aac"),
    "mov": ("prores_hq", "prores_ks", "yuv422p10le", "aac"),
    "webm": ("vp9", "libvpx-vp9", "yuv420p", "libopus"),
}

# BT.709 matrix/primaries, sRGB transfer, limited range (how ComfyUI tags SDR video).
_BT709 = 1
_SRGB_TRC = 13
_MPEG_RANGE = 1


def video_codec(fmt: str) -> str:
    """Return a short codec label for a video *fmt* (used in metadata)."""
    spec = _VIDEO_SPECS.get(fmt)
    return spec[0] if spec else ""


def audio_codec(fmt: str) -> str:
    """Return the audio encoder used for a video *fmt* (``aac`` or ``libopus``)."""
    spec = _VIDEO_SPECS.get(fmt)
    return spec[3] if spec else ""


def import_av():
    """
    Import and return PyAV.

    PyAV is part of ComfyUI's own requirements, so this only fails in a
    broken install; the error says how to fix it.
    """
    try:
        import av  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "[Pipedream] PyAV (the 'av' Python package) is not installed. It is "
            "part of ComfyUI's requirements: run 'pip install -r requirements.txt' "
            "in your ComfyUI folder (or 'pip install av') with ComfyUI's Python."
        ) from exc
    return av


def to_numpy(value):
    """Return a numpy array for a torch tensor or array-like *value*."""
    import numpy as np

    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        return value.numpy()
    return np.asarray(value)


def frames_to_uint8(images):
    """
    Convert an IMAGE tensor ``(B, H, W, C)`` to a uint8 RGB array.

    Values are clipped to ``[0, 1]`` (NaN/inf made finite) and alpha is
    dropped.
    """
    import numpy as np

    arr = to_numpy(images)
    arr = (np.nan_to_num(arr, nan=0.0, posinf=1.0, neginf=0.0) * 255.0).clip(0, 255).astype(np.uint8)
    if arr.ndim == 3:
        arr = arr[..., None]
    channels = arr.shape[-1]
    if channels == 1:
        arr = np.repeat(arr, 3, axis=-1)
    elif channels > 3:
        arr = arr[..., :3]
    return np.ascontiguousarray(arr)


def _frames_for_encoder(images, high_bit_depth: bool):
    """
    Return ``(frames, av_format)`` for PyAV: RGB padded to even dimensions
    (4:2:0 and 4:2:2 chroma need them), 16-bit when *high_bit_depth*
    (ProRes is 10-bit), 8-bit otherwise.
    """
    import numpy as np

    if high_bit_depth:
        arr = to_numpy(images).astype(np.float32)
        if arr.ndim == 3:
            arr = arr[..., None]
        if arr.shape[-1] == 1:
            arr = np.repeat(arr, 3, axis=-1)
        arr = np.nan_to_num(arr[..., :3], nan=0.0, posinf=1.0, neginf=0.0) * 65535.0
        frames, av_format = arr.clip(0, 65535).astype(np.uint16), "rgb48le"
    else:
        frames, av_format = frames_to_uint8(images), "rgb24"
    _, height, width, _ = frames.shape
    pad_h, pad_w = height % 2, width % 2
    if pad_h or pad_w:
        frames = np.pad(frames, ((0, 0), (0, pad_h), (0, pad_w), (0, 0)), mode="edge")
    return np.ascontiguousarray(frames), av_format


def _add_audio_stream(av, container, audio, fmt: str, frame_count: int, rate: Fraction):
    """
    Add an audio stream for a ComfyUI AUDIO dict and return
    ``(stream, frames)`` ready to encode, or ``(None, [])`` without audio.

    The waveform (first batch item) is trimmed to the video length.
    mp4/mov get AAC at the source sample rate; webm gets Opus, resampled
    to 48 kHz.  More than two channels (other than 5.1) are cut to stereo.
    """
    import numpy as np

    if not audio or audio.get("waveform") is None:
        return None, []
    waveform = to_numpy(audio["waveform"]).astype(np.float32)
    if waveform.ndim == 3:
        waveform = waveform[0]
    if waveform.ndim == 1:
        waveform = waveform[None, :]
    sample_rate = int(audio.get("sample_rate", 44100))
    waveform = waveform[:, : math.ceil(sample_rate / rate * frame_count)]
    if waveform.shape[-1] == 0:
        return None, []
    if waveform.shape[0] not in (1, 2, 6):
        waveform = waveform[:2]
    layout = {1: "mono", 2: "stereo", 6: "5.1"}[waveform.shape[0]]

    out_rate = 48000 if fmt == "webm" else sample_rate
    stream = container.add_stream(audio_codec(fmt), rate=out_rate, layout=layout)
    frame = av.AudioFrame.from_ndarray(np.ascontiguousarray(waveform), format="fltp", layout=layout)
    frame.sample_rate = sample_rate
    frame.pts = 0
    if out_rate == sample_rate:
        return stream, [frame]
    resampler = av.audio.resampler.AudioResampler(format="fltp", layout=layout, rate=out_rate)
    return stream, list(resampler.resample(frame)) + list(resampler.resample(None))


def save_video(images, full_path: str, fmt: str, fps: float = 24.0,
               crf: int = 18, overwrite: bool = False, audio=None) -> list[str]:
    """
    Encode an IMAGE batch as a single video file with PyAV.

    ``mp4`` uses H.264 (yuv420p), ``mov`` uses ProRes 422 HQ (10-bit) and
    ``webm`` uses VP9 (yuv420p), tagged BT.709.  *crf* applies to H.264
    and VP9; ProRes ignores it.  Odd frame sizes are padded to even by
    repeating the last row/column.  *audio* is an optional ComfyUI AUDIO
    dict (``{"waveform": (B, C, S), "sample_rate": int}``), muxed as AAC
    for mp4/mov and Opus for webm.

    Returns ``[full_path]`` on success, or ``[]`` when the file exists and
    *overwrite* is disabled.  Raises ``RuntimeError`` when PyAV is missing
    or the encode fails.
    """
    if fmt not in _VIDEO_SPECS:
        raise ValueError(f"[Pipedream] Unsupported video format: '{fmt}'")
    av = import_av()

    if not overwrite and os.path.exists(full_path):
        print(
            f"[Pipedream] Error: file already exists and overwrite is "
            f"disabled: '{full_path}'",
            file=sys.stderr,
        )
        return []

    _, encoder, pix_fmt, _ = _VIDEO_SPECS[fmt]
    frames, av_format = _frames_for_encoder(images, high_bit_depth=(fmt == "mov"))
    count, height, width, _ = frames.shape
    rate = Fraction(round(float(fps) * 1000), 1000)
    options = {"movflags": "+faststart"} if fmt in ("mp4", "mov") else {}

    try:
        with av.open(full_path, mode="w", options=options) as container:
            stream = container.add_stream(encoder, rate=rate)
            stream.width, stream.height, stream.pix_fmt = width, height, pix_fmt
            if fmt == "mp4":
                stream.options = {"crf": str(int(crf)), "preset": "medium"}
            elif fmt == "mov":
                stream.options = {"profile": "3", "vendor": "apl0"}
            else:
                stream.bit_rate = 0
                stream.options = {"crf": str(min(int(crf), 63)), "row-mt": "1"}
            cc = stream.codec_context
            cc.colorspace, cc.color_primaries = _BT709, _BT709
            cc.color_trc, cc.color_range = _SRGB_TRC, _MPEG_RANGE

            audio_stream, audio_frames = _add_audio_stream(av, container, audio, fmt, count, rate)

            for arr in frames:
                frame = av.VideoFrame.from_ndarray(arr, format=av_format)
                frame = frame.reformat(format=pix_fmt, dst_colorspace=_BT709)
                container.mux(stream.encode(frame))
            container.mux(stream.encode(None))

            if audio_stream is not None:
                for frame in audio_frames:
                    container.mux(audio_stream.encode(frame))
                container.mux(audio_stream.encode(None))
    except Exception as exc:
        raise RuntimeError(
            f"[Pipedream] Failed to write '{fmt}' video '{full_path}': {exc}"
        ) from exc

    return [full_path]


EXR_PRECISIONS = ("half", "float")
EXR_COMPRESSIONS = ("zip", "zips", "rle", "none")
_EXR_COMPRESSION = {"zip": "zip16", "zips": "zip1", "rle": "rle", "none": "none"}


def exr_frame(image):
    """
    Return one IMAGE item ``(H, W, C)`` as a float32 RGB or RGBA array.

    Values stay linear and unclipped.  One channel is expanded to RGB, two
    channels are read as luminance + alpha, and extra channels beyond four
    are dropped.
    """
    import numpy as np

    arr = np.asarray(to_numpy(image), dtype=np.float32)
    if arr.ndim == 2:
        arr = arr[..., None]
    channels = arr.shape[-1]
    if channels == 1:
        arr = np.repeat(arr, 3, axis=-1)
    elif channels == 2:
        arr = np.concatenate([np.repeat(arr[..., :1], 3, axis=-1), arr[..., 1:]], axis=-1)
    elif channels > 4:
        arr = arr[..., :4]
    return np.ascontiguousarray(arr)


def save_exr(rgb, path: str, precision: str = "half", compression: str = "zip") -> str:
    """
    Write one float RGB/RGBA array ``(H, W, 3|4)`` to *path* as OpenEXR.

    Uses PyAV's ``exr`` encoder (gbrpf32le / gbrapf32le input) directly,
    without a muxer: an EXR frame is the whole file.  *precision* is
    ``half`` or ``float`` (the encoder's ``format`` option); *compression*
    is ``zip`` (16 scanlines), ``zips`` (1 scanline), ``rle`` or ``none``.
    Data is written as-is (linear, no clipping); 4 channels write alpha.

    Returns *path*.  Raises ``RuntimeError`` when PyAV is missing or the
    encode fails.
    """
    if precision not in EXR_PRECISIONS:
        raise ValueError(f"[Pipedream] Unknown EXR precision: '{precision}'")
    if compression not in EXR_COMPRESSIONS:
        raise ValueError(f"[Pipedream] Unknown EXR compression: '{compression}'")
    av = import_av()

    height, width, channels = rgb.shape
    pix_fmt = "gbrapf32le" if channels == 4 else "gbrpf32le"
    try:
        ctx = av.CodecContext.create("exr", "w")
        ctx.width, ctx.height, ctx.pix_fmt = width, height, pix_fmt
        ctx.time_base = Fraction(1, 24)
        ctx.options = {"format": precision, "compression": _EXR_COMPRESSION[compression]}
        frame = av.VideoFrame.from_ndarray(rgb, format=pix_fmt)
        packets = list(ctx.encode(frame)) + list(ctx.encode(None))
        with open(path, "wb") as fh:
            for packet in packets:
                fh.write(bytes(packet))
    except Exception as exc:
        raise RuntimeError(f"[Pipedream] Failed to write EXR '{path}': {exc}") from exc
    return path


def _downscale(img, max_size: int = PREVIEW_MAX_SIZE):
    from PIL import Image

    if max(img.size) > max_size:
        img = img.copy()
        img.thumbnail((max_size, max_size), Image.LANCZOS)
    return img


def _ui_entry_for(path: str, base_dir: str, kind: str) -> dict | None:
    """Return a ComfyUI preview dict if *path* lives inside *base_dir*."""
    if not base_dir:
        return None
    path = os.path.abspath(path)
    base_dir = os.path.abspath(base_dir)
    try:
        if os.path.commonpath([path, base_dir]) != base_dir:
            return None
    except ValueError:
        return None
    subfolder = os.path.relpath(os.path.dirname(path), base_dir)
    subfolder = "" if subfolder == "." else subfolder.replace("\\", "/")
    return {"filename": os.path.basename(path), "subfolder": subfolder, "type": kind}


def build_preview(images, written: list[str], is_video: bool, fps: float,
                  output_dir: str | None, temp_dir: str | None) -> tuple[list[dict], bool]:
    """
    Build the ``ui["images"]`` list showing what an output node wrote.

    Browser-viewable images, and mp4/webm video, inside ComfyUI's output
    directory are referenced directly.  Anything else (EXR, ProRes, files
    outside the output dir) gets a downscaled PNG, or an animated WebP for
    video, in the temp directory.

    Returns ``(entries, animated)``.  Preview failures never raise.
    """
    from PIL import Image

    if not written:
        return [], False

    entries: list[dict] = []
    prefix = f"pd_preview_{uuid.uuid4().hex[:8]}"

    try:
        if is_video:
            ext = os.path.splitext(written[0])[1].lower().lstrip(".")
            if ext in BROWSER_VIDEO_FORMATS:
                entry = _ui_entry_for(written[0], output_dir, "output")
                if entry is not None:
                    return [entry], True
            if not temp_dir:
                return [], False
            os.makedirs(temp_dir, exist_ok=True)
            frames = [_downscale(Image.fromarray(f)) for f in frames_to_uint8(images)]
            name = f"{prefix}.webp"
            frames[0].save(
                os.path.join(temp_dir, name),
                save_all=True,
                append_images=frames[1:],
                duration=max(1, int(round(1000.0 / max(float(fps), 0.01)))),
                loop=0,
                quality=80,
            )
            return [{"filename": name, "subfolder": "", "type": "temp"}], len(frames) > 1

        frames = None
        for i, path in enumerate(written):
            entry = None
            if os.path.splitext(path)[1].lower() in BROWSER_IMAGE_EXTS:
                entry = _ui_entry_for(path, output_dir, "output")
            if entry is None and temp_dir:
                if frames is None:
                    frames = frames_to_uint8(images)
                idx = min(_batch_index(path, len(written), i), len(frames) - 1)
                os.makedirs(temp_dir, exist_ok=True)
                name = f"{prefix}_{i:04d}.png"
                _downscale(Image.fromarray(frames[idx])).save(
                    os.path.join(temp_dir, name), compress_level=1
                )
                entry = {"filename": name, "subfolder": "", "type": "temp"}
            if entry is not None:
                entries.append(entry)
    except Exception as exc:
        print(f"[Pipedream] Warning: failed to build preview: {exc}", file=sys.stderr)

    return entries, False


def _batch_index(path: str, count: int, fallback: int) -> int:
    """Recover the batch index from a ``name_0003.ext`` path written by save_image_batch."""
    if count <= 1:
        return 0
    stem = os.path.splitext(os.path.basename(path))[0]
    tail = stem.rsplit("_", 1)[-1]
    return int(tail) if tail.isdigit() else fallback


def write_sidecar(path: str, data: dict) -> str | None:
    """Write *data* as pretty JSON to *path*.  Returns the path, or None on failure."""
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str, ensure_ascii=False)
        return path
    except Exception as exc:
        print(f"[Pipedream] Error: failed to write metadata '{path}': {exc}",
              file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Paths and image batches
# ---------------------------------------------------------------------------

def normalize_path(path: str) -> str:
    """
    Normalize slashes for the current platform.

    On Windows, forward slashes become backslashes and UNC prefixes
    (``\\\\server\\share``) are preserved.  On POSIX, backslashes become
    forward slashes.  Trailing separators are stripped.
    """
    if sys.platform == "win32":
        path = path.replace("/", "\\")
    else:
        path = path.replace("\\", "/")
    return path.rstrip(os.sep)


def ensure_directory(path: str, create: bool = True) -> str:
    """
    Return the directory portion of *path*, optionally creating it.

    Raises ``OSError`` with a descriptive message on failure.
    """
    directory = os.path.dirname(path)
    if not directory:
        return directory
    if create and not os.path.isdir(directory):
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as exc:
            raise OSError(
                f"[Pipedream] Failed to create directory '{directory}': {exc}"
            ) from exc
    return directory


def save_image_batch(images, full_path: str, overwrite: bool = False,
                     exr_precision: str = "half",
                     exr_compression: str = "zip") -> list[str]:
    """
    Save a batch of ComfyUI IMAGE tensors to disk.

    *images* is a tensor of shape ``(B, H, W, C)`` with float32 values in
    ``[0, 1]``.  When the batch size is greater than one, a zero-padded
    index is appended before the extension (e.g. ``name_0001.png``).

    png/jpg/webp are written 8-bit with Pillow.  ``.exr`` keeps the float
    data linear and unclipped, including alpha, and is written by
    ``save_exr`` with *exr_precision* (``half``/``float``) and
    *exr_compression*; EXR write failures (including no available writer)
    raise ``RuntimeError`` instead of being skipped.

    Returns a list of successfully written file paths.
    """
    import numpy as np
    from PIL import Image

    ext = os.path.splitext(full_path)[1].lower()
    batch_size = images.shape[0]
    written: list[str] = []

    for i in range(batch_size):
        if batch_size > 1:
            base, extension = os.path.splitext(full_path)
            out_path = f"{base}_{i:04d}{extension}"
        else:
            out_path = full_path

        if not overwrite and os.path.exists(out_path):
            print(
                f"[Pipedream] Error: file already exists and overwrite is "
                f"disabled: '{out_path}'",
                file=sys.stderr,
            )
            continue

        if ext == ".exr":
            save_exr(exr_frame(images[i]), out_path, exr_precision, exr_compression)
            written.append(out_path)
            continue

        img_array = (to_numpy(images[i]) * 255).clip(0, 255).astype(np.uint8)
        img = Image.fromarray(img_array)

        save_kwargs: dict = {}
        if ext in (".jpg", ".jpeg"):
            save_kwargs["quality"] = 95
        elif ext == ".webp":
            save_kwargs["quality"] = 95

        try:
            img.save(out_path, **save_kwargs)
            written.append(out_path)
        except Exception as exc:
            print(
                f"[Pipedream] Error: failed to write '{out_path}': {exc}",
                file=sys.stderr,
            )

    return written
