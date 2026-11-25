"""
Media and file helpers for PD Save.

Path normalization, alpha and colour helpers, image sequence writing,
video and EXR encoding through PyAV (the ``av`` package that ships with
ComfyUI), preview image generation for the node UI, and sidecar metadata
writing.  No dependencies beyond what ComfyUI already installs.
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
PREVIEW_MAX_FRAMES = 1000

# format -> (label, PyAV encoder, pixel format, audio encoder)
_VIDEO_SPECS = {
    "mp4": ("h264", "libx264", "yuv420p", "aac"),
    "mov": ("prores_hq", "prores_ks", "yuv422p10le", "aac"),
    "webm": ("vp9", "libvpx-vp9", "yuv420p", "libopus"),
}

# ProRes profile -> (label, prores_ks profile, pixel format without / with alpha)
PRORES_PROFILES = ("422 HQ", "4444")
_PRORES_SPECS = {
    "422 HQ": ("prores_hq", "3", "yuv422p10le", None),
    "4444": ("prores_4444", "4", "yuv444p10le", "yuva444p10le"),
}
PRORES_CHOICES = ("auto",) + PRORES_PROFILES
ALPHA_FORMATS = ("png", "exr", "webp", "mov")
PATH_MODES = ("relative", "absolute")
EXR_COLORSPACES = ("as is", "sRGB to linear")

# Rec.709 luma weights, used to turn an RGB image or video into a matte.
_LUMA = (0.2126, 0.7152, 0.0722)

# BT.709 matrix/primaries, sRGB transfer, limited range (how ComfyUI tags SDR video).
_BT709 = 1
_SRGB_TRC = 13
_MPEG_RANGE = 1


def video_codec(fmt: str, prores_profile: str = "422 HQ") -> str:
    """Return a short codec label for a video *fmt* (used in metadata)."""
    if fmt == "mov":
        return _PRORES_SPECS[prores_profile][0]
    spec = _VIDEO_SPECS.get(fmt)
    return spec[0] if spec else ""


def supports_alpha(fmt: str, prores_profile: str = "4444") -> bool:
    """True when *fmt* can carry an alpha channel (mov only as ProRes 4444)."""
    if fmt == "mov":
        return prores_profile == "4444"
    return fmt in ALPHA_FORMATS


def alpha_premultiplied(fmt: str) -> bool:
    """
    True when alpha written to *fmt* is premultiplied (associated).

    Only EXR: the OpenEXR spec defines RGBA as premultiplied.  png/webp
    store straight alpha by spec, and ProRes 4444 is written straight (its
    bitstream has no reliable flag, so straight is Pipedream's convention).
    """
    return fmt == "exr"


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


def srgb_to_linear(rgb):
    """
    Decode sRGB-encoded values to linear light with the piecewise sRGB EOTF.

    ``v <= 0.04045`` maps to ``v / 12.92``; above that
    ``((v + 0.055) / 1.055) ** 2.4``.  The power segment is simply
    continued above 1.0 (2.0 becomes about 5.7), so overbright values stay
    monotonic and finite, and negative values are mirrored
    (``-f(-v)``).  NaN/inf are made finite first.  Returns float32.
    """
    import numpy as np

    v = np.nan_to_num(np.asarray(rgb, dtype=np.float32), nan=0.0, posinf=1.0, neginf=0.0)
    a = np.abs(v)
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    return (np.sign(v) * lin).astype(np.float32)


def linear_to_srgb(rgb):
    """
    Encode linear light to sRGB, the inverse of ``srgb_to_linear``.

    ``v <= 0.0031308`` maps to ``12.92 * v``; above that
    ``1.055 * v ** (1 / 2.4) - 0.055``, continued above 1.0 and mirrored
    for negative values.  NaN/inf are made finite first.  Returns float32.
    """
    import numpy as np

    v = np.nan_to_num(np.asarray(rgb, dtype=np.float32), nan=0.0, posinf=1.0, neginf=0.0)
    a = np.abs(v)
    enc = np.where(a <= 0.0031308, a * 12.92, 1.055 * a ** (1.0 / 2.4) - 0.055)
    return (np.sign(v) * enc).astype(np.float32)


def rgb_frame(image):
    """
    Return one IMAGE item ``(H, W, C)`` as a float32 RGB array ``(H, W, 3)``.

    One channel is expanded to grey RGB, two channels (luminance + alpha)
    use the first, and channels beyond three are dropped; alpha is handled
    separately (see ``alpha_matte``).  Values are not clipped.
    """
    import numpy as np

    arr = np.asarray(to_numpy(image), dtype=np.float32)
    if arr.ndim == 2:
        arr = arr[..., None]
    if arr.shape[-1] < 3:
        arr = np.repeat(arr[..., :1], 3, axis=-1)
    return np.ascontiguousarray(arr[..., :3])


def alpha_matte(source):
    """
    Turn an alpha source into a float32 matte of shape ``(N, H, W)``.

    *source* is a ComfyUI MASK (``(N, H, W)`` or ``(H, W)``) used as is,
    or an IMAGE batch ``(N, H, W, C)``: one channel is used directly and
    three or more channels are reduced to Rec.709 luminance
    (``0.2126 R + 0.7152 G + 0.0722 B``), so a grey matte keeps its exact
    values.  A VIDEO is unpacked by the caller into its IMAGE frames.
    Values are returned unclipped.
    """
    import numpy as np

    arr = np.asarray(to_numpy(source), dtype=np.float32)
    if arr.ndim == 2:
        return arr[None]
    if arr.ndim == 3:
        return arr
    if arr.ndim != 4:
        raise ValueError(f"[Pipedream] Unsupported alpha shape {tuple(arr.shape)}.")
    if arr.shape[-1] < 3:
        return np.ascontiguousarray(arr[..., 0])
    return np.ascontiguousarray(arr[..., 0] * _LUMA[0] + arr[..., 1] * _LUMA[1] + arr[..., 2] * _LUMA[2])


def match_alpha(alpha, count: int, height: int, width: int):
    """
    Check that matte *alpha* ``(N, H, W)`` fits a source of *count* frames
    of ``height x width``.  N must equal *count* or be 1 (one matte for
    every frame).  Raises ``ValueError`` with both shapes otherwise.
    """
    n, h, w = alpha.shape
    if n not in (1, count):
        raise ValueError(
            f"[Pipedream] Alpha has {n} frames but the source has {count}. "
            "Connect an alpha with the same frame count, or a single frame "
            "to use for every frame."
        )
    if (h, w) != (height, width):
        raise ValueError(
            f"[Pipedream] Alpha is {w}x{h} but the source is {width}x{height}. "
            "Resize the alpha to match (e.g. with an Upscale/Resize node)."
        )
    return alpha


def _alpha_at(alpha, index: int):
    """Return frame *index* of matte *alpha*, broadcasting a single frame."""
    return alpha[index if alpha.shape[0] > 1 else 0]


def _frames_for_encoder(images, high_bit_depth: bool, alpha=None):
    """
    Return ``(frames, av_format)`` for PyAV: RGB (or RGBA with matte
    *alpha*) padded to even dimensions (4:2:0 and 4:2:2 chroma need them),
    16-bit when *high_bit_depth* (ProRes is 10-bit), 8-bit otherwise.
    Alpha is only supported at high bit depth.
    """
    import numpy as np

    if high_bit_depth:
        arr = np.stack([rgb_frame(f) for f in images])
        if alpha is not None:
            mattes = np.stack([_alpha_at(alpha, i) for i in range(arr.shape[0])])
            arr = np.concatenate([arr, mattes[..., None]], axis=-1)
        arr = np.nan_to_num(arr, nan=0.0, posinf=1.0, neginf=0.0) * 65535.0
        av_format = "rgba64le" if alpha is not None else "rgb48le"
        frames = arr.clip(0, 65535).astype(np.uint16)
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
               crf: int = 18, overwrite: bool = False, audio=None,
               alpha=None, prores_profile: str = "422 HQ") -> list[str]:
    """
    Encode an IMAGE batch as a single video file with PyAV.

    ``mp4`` uses H.264 (yuv420p), ``mov`` uses ProRes (10-bit) and
    ``webm`` uses VP9 (yuv420p), tagged BT.709.  *prores_profile* is
    ``422 HQ`` (yuv422p10le) or ``4444`` (yuv444p10le, or yuva444p10le
    with an alpha channel when matte *alpha* ``(1|N, H, W)`` is given;
    straight alpha, RGB is not premultiplied).
    *alpha* is ignored by every other format/profile.  *crf* applies to
    H.264 and VP9; ProRes ignores it.  Odd frame sizes are padded to even
    by repeating the last row/column.  *audio* is an optional ComfyUI
    AUDIO dict (``{"waveform": (B, C, S), "sample_rate": int}``), muxed as
    AAC for mp4/mov and Opus for webm.

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
    profile = "3"
    if fmt == "mov":
        if prores_profile not in _PRORES_SPECS:
            raise ValueError(f"[Pipedream] Unknown ProRes profile: '{prores_profile}'")
        _, profile, pix_fmt, alpha_pix_fmt = _PRORES_SPECS[prores_profile]
        if alpha is not None and alpha_pix_fmt:
            pix_fmt = alpha_pix_fmt
        else:
            alpha = None
    else:
        alpha = None
    frames, av_format = _frames_for_encoder(images, high_bit_depth=(fmt == "mov"), alpha=alpha)
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
                stream.options = {"profile": profile, "vendor": "apl0"}
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


def preview_still(image, temp_dir: str, name: str) -> dict:
    """Save one frame (``HxWxC`` tensor or array) as a downscaled PNG in *temp_dir*."""
    from PIL import Image

    os.makedirs(temp_dir, exist_ok=True)
    _downscale(Image.fromarray(frames_to_uint8(image[None])[0])).save(
        os.path.join(temp_dir, name + ".png"), compress_level=1)
    return {"filename": name + ".png", "subfolder": "", "type": "temp"}


def preview_clip(images, fps: float, temp_dir: str, name: str, audio=None) -> dict:
    """
    Save frames as a playable H.264 mp4 in *temp_dir*: downscaled to
    ``PREVIEW_MAX_SIZE``, at most ``PREVIEW_MAX_FRAMES`` frames, with the
    audio if given.  The frontend shows it with video controls.
    """
    import torch.nn.functional as F

    frames = images[:PREVIEW_MAX_FRAMES, ..., :3]
    h, w = int(frames.shape[1]), int(frames.shape[2])
    scale = min(1.0, PREVIEW_MAX_SIZE / max(h, w))
    if scale < 1.0:
        size = (max(2, int(h * scale)), max(2, int(w * scale)))
        frames = F.interpolate(frames.permute(0, 3, 1, 2), size=size, mode="area")
        frames = frames.permute(0, 2, 3, 1)
    os.makedirs(temp_dir, exist_ok=True)
    save_video(frames.clamp(0, 1), os.path.join(temp_dir, name + ".mp4"), "mp4",
               fps=fps, crf=23, overwrite=True, audio=audio)
    return {"filename": name + ".mp4", "subfolder": "", "type": "temp"}


def preview_name(prefix: str = "pd_preview") -> str:
    """A unique file name stem for a temp preview."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def build_preview(images, written: list[str], is_video: bool, fps: float,
                  output_dir: str | None, temp_dir: str | None,
                  audio=None) -> tuple[list[dict], bool]:
    """
    Build the ``ui["images"]`` list showing what an output node wrote.

    *written* holds one path per frame of *images* for image formats.
    Browser-viewable images, and mp4/webm video, inside ComfyUI's output
    directory are referenced directly.  Anything else (EXR, ProRes, files
    outside the output dir) gets a downscaled PNG, or a playable mp4 for
    video (``preview_clip``), in the temp directory.

    Returns ``(entries, animated)``.  Preview failures never raise.
    """
    if not written:
        return [], False
    name = preview_name()
    try:
        if is_video:
            ext = os.path.splitext(written[0])[1].lower().lstrip(".")
            if ext in BROWSER_VIDEO_FORMATS:
                entry = _ui_entry_for(written[0], output_dir, "output")
                if entry is not None:
                    return [entry], True
            if not temp_dir:
                return [], False
            return [preview_clip(images, fps, temp_dir, name, audio)], True

        entries: list[dict] = []
        for i, path in enumerate(written):
            entry = None
            if os.path.splitext(path)[1].lower() in BROWSER_IMAGE_EXTS:
                entry = _ui_entry_for(path, output_dir, "output")
            if entry is None and temp_dir:
                entry = preview_still(images[min(i, len(images) - 1)], temp_dir, f"{name}_{i:04d}")
            if entry is not None:
                entries.append(entry)
        return entries, False
    except Exception as exc:
        print(f"[Pipedream] Warning: failed to build preview: {exc}", file=sys.stderr)
        return [], False


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


def existing_files(paths: list[str]) -> list[str]:
    """Return the entries of *paths* that already exist on disk."""
    return [p for p in paths if os.path.exists(p)]


def save_image_sequence(images, paths: list[str], alpha=None,
                        exr_precision: str = "half", exr_compression: str = "zip",
                        exr_linearize: bool = False, exr_metadata=None) -> list[str]:
    """
    Write IMAGE batch *images* ``(B, H, W, C)`` as one file per frame.

    *paths* gives the output path of each frame (``len(paths) == B``);
    the extension picks the format.  *alpha* is an optional matte
    ``(1|B, H, W)`` written as the alpha channel of png/webp (8-bit RGBA)
    and exr; jpg has no alpha and ignores it.

    png/jpg/webp are written 8-bit with Pillow, clipped to 0-1.  ``.exr``
    keeps the float data unclipped and is written by ``save_exr`` with
    *exr_precision* and *exr_compression*; with *exr_linearize* the RGB
    channels are decoded from sRGB to linear first (``srgb_to_linear``),
    alpha is always written as is.

    Alpha conventions: *images* and *alpha* are straight (unpremultiplied),
    as everywhere in ComfyUI.  png/webp store straight alpha (their spec),
    so they are written as is.  OpenEXR defines RGBA as premultiplied, so
    EXR RGB is multiplied by the alpha, after the sRGB to linear decode
    (which must see straight values).  See ``alpha_premultiplied``.
    *exr_metadata*, when given, is called as ``exr_metadata(index, path)``
    after each EXR frame is written (PD Save adds header metadata).
    EXR failures raise ``RuntimeError``;
    other per-file failures are printed and skipped.  Callers handle the
    overwrite policy (see ``existing_files``).

    Returns the paths that were written.
    """
    import numpy as np
    from PIL import Image

    written: list[str] = []
    for i, out_path in enumerate(paths):
        ext = os.path.splitext(out_path)[1].lower()
        rgb = rgb_frame(images[i])
        matte = _alpha_at(alpha, i) if alpha is not None else None

        if ext == ".exr":
            if exr_linearize:
                rgb = srgb_to_linear(rgb)
            if matte is not None:
                matte = np.asarray(matte, np.float32)[..., None]
                rgb = np.concatenate([rgb * matte, matte], axis=-1)
            save_exr(np.ascontiguousarray(rgb), out_path, exr_precision, exr_compression)
            if exr_metadata is not None:
                exr_metadata(i, out_path)
            written.append(out_path)
            continue

        if matte is not None and ext in (".png", ".webp"):
            rgb = np.concatenate([rgb, np.asarray(matte, np.float32)[..., None]], axis=-1)
        pixels = (np.nan_to_num(rgb, nan=0.0, posinf=1.0, neginf=0.0) * 255.0 + 0.5)
        img = Image.fromarray(pixels.clip(0, 255).astype(np.uint8))
        save_kwargs = {"quality": 95} if ext in (".jpg", ".jpeg", ".webp") else {}
        try:
            img.save(out_path, **save_kwargs)
            written.append(out_path)
        except Exception as exc:
            print(f"[Pipedream] Error: failed to write '{out_path}': {exc}", file=sys.stderr)

    return written
