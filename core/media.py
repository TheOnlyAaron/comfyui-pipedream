"""
Media helpers for Pipedream output nodes.

Video and EXR encoding (frames piped to the ``ffmpeg`` binary on PATH),
preview image generation for the ComfyUI node UI, and sidecar metadata
writing.  Only numpy and PIL are required; OpenEXR or OpenCV are used as
EXR fallbacks when they happen to be installed.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid

IMAGE_FORMATS = ("png", "exr", "jpg", "webp")
VIDEO_FORMATS = ("mp4", "mov", "webm")
BROWSER_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")

PREVIEW_MAX_SIZE = 512

EXR_PRECISIONS = ("half", "float")
EXR_COMPRESSIONS = ("zip", "zips", "rle", "none")

_VIDEO_CODECS = {
    "mp4": "h264",
    "mov": "prores_hq",
    "webm": "vp9",
}


def video_codec(fmt: str) -> str:
    """Return a short codec label for a video *fmt* (used in metadata)."""
    return _VIDEO_CODECS.get(fmt, "")


def frames_to_uint8(images):
    """
    Convert an IMAGE tensor ``(B, H, W, C)`` to a uint8 RGB array.

    Values are clipped to ``[0, 1]`` (NaN/inf made finite) and alpha is
    dropped, so HDR data is only clipped for previews and 8-bit outputs.
    """
    import numpy as np

    arr = images.cpu().numpy() if hasattr(images, "cpu") else np.asarray(images)
    arr = (np.nan_to_num(arr, nan=0.0, posinf=1.0, neginf=0.0) * 255.0).clip(0, 255).astype(np.uint8)
    if arr.ndim == 3:
        arr = arr[..., None]
    channels = arr.shape[-1]
    if channels == 1:
        arr = np.repeat(arr, 3, axis=-1)
    elif channels > 3:
        arr = arr[..., :3]
    return np.ascontiguousarray(arr)


def find_ffmpeg(purpose: str) -> str:
    """
    Return the path of the ``ffmpeg`` binary on PATH.

    Raises ``RuntimeError`` naming *purpose* (e.g. "'mp4' video") when
    ffmpeg is not installed.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            f"[Pipedream] ffmpeg was not found on PATH. Install ffmpeg to write "
            f"{purpose}, or choose another format."
        )
    return ffmpeg


def _run_ffmpeg(cmd: list[str], chunks, full_path: str) -> None:
    """Run *cmd*, write each bytes chunk to its stdin, and raise on failure."""
    with tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=err)
        try:
            for chunk in chunks:
                proc.stdin.write(chunk)
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass
        code = proc.wait()
        if code != 0:
            err.seek(0)
            detail = err.read().decode("utf-8", "replace").strip()
            raise RuntimeError(
                f"[Pipedream] ffmpeg failed writing '{full_path}' "
                f"(exit {code}): {detail}"
            )


def _ffmpeg_codec_args(fmt: str, crf: int) -> list[str]:
    even = ["-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2"]
    if fmt == "mp4":
        return even + ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
                       "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    if fmt == "mov":
        return even + ["-c:v", "prores_ks", "-profile:v", "3",
                       "-pix_fmt", "yuv422p10le", "-vendor", "apl0"]
    if fmt == "webm":
        return even + ["-c:v", "libvpx-vp9", "-crf", str(min(crf, 63)), "-b:v", "0",
                       "-pix_fmt", "yuv420p", "-row-mt", "1"]
    raise ValueError(f"[Pipedream] Unsupported video format: '{fmt}'")


def save_video(images, full_path: str, fmt: str, fps: float = 24.0,
               crf: int = 18, overwrite: bool = False) -> list[str]:
    """
    Encode an IMAGE batch as a single video file by piping raw RGB frames
    to ``ffmpeg``.

    ``mp4`` uses H.264, ``mov`` uses ProRes 422 HQ and ``webm`` uses VP9.
    *crf* applies to H.264 and VP9; ProRes ignores it.  Raises
    ``RuntimeError`` when ffmpeg is not on PATH or the encode fails.
    Returns ``[full_path]`` on success, or ``[]`` when the file exists and
    *overwrite* is disabled.
    """
    ffmpeg = find_ffmpeg(f"'{fmt}' video")

    if not overwrite and os.path.exists(full_path):
        print(
            f"[Pipedream] Error: file already exists and overwrite is "
            f"disabled: '{full_path}'",
            file=sys.stderr,
        )
        return []

    frames = frames_to_uint8(images)
    _, height, width, _ = frames.shape
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{width}x{height}", "-r", f"{float(fps):g}",
        "-i", "-",
        *_ffmpeg_codec_args(fmt, int(crf)),
        "-r", f"{float(fps):g}",
        full_path,
    ]

    _run_ffmpeg(cmd, (frame.tobytes() for frame in frames), full_path)
    return [full_path]


# --------------------------------------------------------------------------
# EXR
# --------------------------------------------------------------------------

_FFMPEG_EXR_COMPRESSION = {"zip": "zip16", "zips": "zip1", "rle": "rle", "none": "none"}
_CV2_EXR_COMPRESSION = {"none": 0, "rle": 1, "zips": 2, "zip": 3}
_OPENEXR_COMPRESSION = {"zip": "ZIP_COMPRESSION", "zips": "ZIPS_COMPRESSION",
                        "rle": "RLE_COMPRESSION", "none": "NO_COMPRESSION"}


def exr_frame(image):
    """
    Return one IMAGE item ``(H, W, C)`` as a float32 RGB or RGBA array.

    Values stay linear and unclipped.  One channel is expanded to RGB, two
    channels are read as luminance + alpha, and extra channels beyond four
    are dropped.
    """
    import numpy as np

    arr = image.cpu().numpy() if hasattr(image, "cpu") else np.asarray(image)
    arr = np.asarray(arr, dtype=np.float32)
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


def _write_exr_ffmpeg(ffmpeg: str, rgb, path: str, precision: str, compression: str):
    import numpy as np

    height, width, channels = rgb.shape
    pix_fmt = "gbrapf32le" if channels == 4 else "gbrpf32le"
    order = [1, 2, 0, 3] if channels == 4 else [1, 2, 0]
    planar = np.ascontiguousarray(rgb.transpose(2, 0, 1)[order].astype("<f4"))
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", pix_fmt, "-s", f"{width}x{height}",
        "-i", "-",
        "-frames:v", "1", "-c:v", "exr", "-pix_fmt", pix_fmt,
        "-format", precision, "-compression", _FFMPEG_EXR_COMPRESSION[compression],
        "-f", "image2", "-update", "1",
        path,
    ]
    _run_ffmpeg(cmd, [planar.tobytes()], path)


def _write_exr_openexr(openexr, rgb, path: str, precision: str, compression: str):
    import numpy as np

    names = "RGBA"[: rgb.shape[-1]]
    dtype = np.float16 if precision == "half" else np.float32
    channels = {n: np.ascontiguousarray(rgb[..., i].astype(dtype)) for i, n in enumerate(names)}
    if hasattr(openexr, "File"):
        header = {"compression": getattr(openexr, _OPENEXR_COMPRESSION[compression]),
                  "type": openexr.scanlineimage}
        with openexr.File(header, channels) as exr:
            exr.write(path)
        return

    import Imath  # type: ignore[import-not-found]

    pixel = Imath.PixelType(Imath.PixelType.HALF if precision == "half" else Imath.PixelType.FLOAT)
    header = openexr.Header(rgb.shape[1], rgb.shape[0])
    header["channels"] = {n: Imath.Channel(pixel) for n in names}
    header["compression"] = Imath.Compression(getattr(Imath.Compression, _OPENEXR_COMPRESSION[compression]))
    out = openexr.OutputFile(path, header)
    try:
        out.writePixels({n: c.tobytes() for n, c in channels.items()})
    finally:
        out.close()


def _write_exr_cv2(cv2, rgb, path: str, precision: str, compression: str):
    bgr = rgb[..., [2, 1, 0, 3]] if rgb.shape[-1] == 4 else rgb[..., ::-1]
    params = [cv2.IMWRITE_EXR_TYPE, 1 if precision == "half" else 2]
    if hasattr(cv2, "IMWRITE_EXR_COMPRESSION"):
        params += [cv2.IMWRITE_EXR_COMPRESSION, _CV2_EXR_COMPRESSION[compression]]
    if not cv2.imwrite(path, bgr.copy(), params):
        raise RuntimeError(f"OpenCV could not write '{path}'")


def exr_writer():
    """
    Pick an EXR writer.  Returns ``(name, write)`` where ``write`` takes
    ``(rgb, path, precision, compression)``.

    Order: the ``ffmpeg`` binary first, since PD Output already relies on
    it for video and its behaviour does not depend on the Python
    environment; then the OpenEXR bindings (the reference implementation);
    then OpenCV, last because EXR support must be enabled through
    ``OPENCV_IO_ENABLE_OPENEXR`` before cv2 is first imported, which another
    node may already have done.  Raises ``RuntimeError`` if none is usable.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return "ffmpeg", lambda *a: _write_exr_ffmpeg(ffmpeg, *a)
    try:
        import OpenEXR  # type: ignore[import-not-found]
        return "OpenEXR", lambda *a: _write_exr_openexr(OpenEXR, *a)
    except ImportError:
        pass
    os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
    try:
        import cv2  # type: ignore[import-not-found]
        if not hasattr(cv2, "haveImageWriter") or cv2.haveImageWriter(".exr"):
            return "opencv", lambda *a: _write_exr_cv2(cv2, *a)
    except ImportError:
        pass
    raise RuntimeError(
        "[Pipedream] No EXR writer available. Install ffmpeg on PATH (recommended) "
        "or the 'OpenEXR' Python package (OpenCV with EXR support also works), "
        "or choose another format."
    )


def save_exr(rgb, path: str, precision: str = "half", compression: str = "zip") -> str:
    """
    Write one float RGB/RGBA array ``(H, W, 3|4)`` to *path* as OpenEXR.

    *precision* is ``half`` or ``float``; *compression* is one of
    ``EXR_COMPRESSIONS``.  Data is written as-is (linear, no clipping).
    Returns the writer name.  Raises ``RuntimeError`` on failure.
    """
    if precision not in EXR_PRECISIONS:
        raise ValueError(f"[Pipedream] Unknown EXR precision: '{precision}'")
    if compression not in EXR_COMPRESSIONS:
        raise ValueError(f"[Pipedream] Unknown EXR compression: '{compression}'")
    name, write = exr_writer()
    try:
        write(rgb, path, precision, compression)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"[Pipedream] {name} failed writing '{path}': {exc}") from exc
    return name


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

    Browser-viewable images inside ComfyUI's output directory are
    referenced directly.  Anything else (EXR, absolute paths outside the
    output dir) gets a downscaled PNG in the temp directory.  Video gets a
    downscaled animated WebP in the temp directory.

    Returns ``(entries, animated)``.  Preview failures never raise.
    """
    from PIL import Image

    if not written:
        return [], False

    entries: list[dict] = []
    prefix = f"pd_preview_{uuid.uuid4().hex[:8]}"

    try:
        if is_video:
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
