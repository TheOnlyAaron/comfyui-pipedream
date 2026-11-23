"""
Finding and decoding media for PD Load, the inverse of PD Output.

A resolved template (tokens already filled in) names one of:

- a **single image** (``shot_v001.png``),
- an **image sequence**: the frame number is marked by ``FRAME_MARK`` (from
  ``{frame}``), a run of ``#`` (``####``) or a printf ``%04d``; without a
  mark, a numbered file next to the name is found as well (PD Output's
  default ``name.1001.png``),
- a **video** (mp4/mov/webm/mkv/avi/m4v).

The extension can be part of the template, or chosen with ``format``
(``auto`` looks for every supported extension and refuses to guess when
more than one matches).  Directory listings use ``os.listdir``, so UNC
paths and mounted network shares work like local folders.

Decoding uses PyAV (shipped with ComfyUI) for every format, so 16-bit
PNG/TIFF and float EXR keep their precision; Pillow is the fallback for
files PyAV cannot open.  Alpha comes out as a MASK (1.0 = opaque,
straight).  EXR is premultiplied by its spec (PD Output writes it that
way), so EXR RGB is divided by alpha on load; ``linear to sRGB`` is the
inverse of PD Output's ``sRGB to linear``.

``torch``, ``numpy`` and ``av`` are imported lazily.
"""

import json
import os
import re
import sys

FRAME_MARK = "@@PDFRAME@@"

IMAGE_EXTS = ("exr", "png", "jpg", "jpeg", "webp", "tif", "tiff", "dpx", "bmp")
VIDEO_EXTS = ("mp4", "mov", "webm", "mkv", "avi", "m4v")
FORMATS = ("auto", "exr", "png", "jpg", "webp", "tif", "dpx", "mp4", "mov", "webm", "mkv")
EXR_COLORSPACES = ("as is", "linear to sRGB")

_ALIASES = {"jpg": ("jpg", "jpeg"), "tif": ("tif", "tiff")}
_HASHES = re.compile(r"#+")
_PRINTF = re.compile(r"%0?(\d*)d")


class MediaNotFound(FileNotFoundError):
    """No file matches the resolved template."""


def kind_of(ext: str) -> str:
    """``video`` or ``image`` for a file extension (without the dot)."""
    return "video" if ext.lower() in VIDEO_EXTS else "image"


def _split_ext(path: str):
    """``(stem, ext)`` when *path* ends in a supported extension, else ``(path, None)``."""
    base, dot_ext = os.path.splitext(path)
    ext = dot_ext[1:].lower()
    if ext in IMAGE_EXTS or ext in VIDEO_EXTS:
        return base, ext
    return path, None


def _candidates(file_format: str) -> tuple:
    """Extensions to look for: one format (and its aliases) or all of them for ``auto``."""
    if file_format in (None, "", "auto"):
        return IMAGE_EXTS + VIDEO_EXTS
    return _ALIASES.get(file_format, (file_format,))


def _frame_split(stem: str):
    """Split *stem* at its frame mark: ``(before, after)``, or None without one."""
    for pattern in (re.escape(FRAME_MARK), _HASHES.pattern, _PRINTF.pattern):
        match = re.search(pattern, stem)
        if match:
            return stem[:match.start()], stem[match.end():]
    return None


def _listdir(folder: str) -> list[str]:
    try:
        return os.listdir(folder or ".")
    except OSError:
        return []


def find_media(resolved: str, file_format: str = "auto") -> dict:
    """
    Find the file(s) a resolved template names.

    Returns ``{"kind": "image"|"sequence"|"video", "paths": [...],
    "frames": [...], "pattern": str, "ext": str}``; ``frames`` holds the
    frame numbers of a sequence (``[0]`` otherwise) and ``pattern`` is a
    readable name (``shot.####.exr`` for a sequence).  Raises MediaNotFound
    (with what was searched) or ValueError when ``auto`` finds more than
    one format.
    """
    stem, ext = _split_ext(resolved)
    exts = (ext,) if ext else _candidates(file_format)
    folder, name = os.path.split(stem)
    entries = _listdir(folder)
    split = _frame_split(name)

    found = {}
    for candidate in exts:
        if split is None:
            single = f"{name}.{candidate}"
            if single in entries or os.path.isfile(os.path.join(folder, single)):
                found[candidate] = ("single", [os.path.join(folder, single)], [0])
                continue
            before, after = name, ""
            regex = re.compile(re.escape(before) + r"[._-]?(\d+)" + re.escape(after)
                               + r"\." + re.escape(candidate) + "$", re.IGNORECASE)
        else:
            before, after = split
            regex = re.compile(re.escape(before) + r"(\d+)" + re.escape(after)
                               + r"\." + re.escape(candidate) + "$", re.IGNORECASE)
        frames = sorted((int(m.group(1)), entry) for entry in entries
                        if (m := regex.match(entry)))
        if frames:
            found[candidate] = ("sequence", [os.path.join(folder, e) for _, e in frames],
                                [n for n, _ in frames])

    if not found:
        shown = os.path.join(folder, name) + (f".{ext}" if ext else
                                              f".{{{','.join(exts)}}}" if len(exts) > 1
                                              else f".{exts[0]}")
        hint = "" if entries or not folder else " (the folder does not exist or cannot be read)"
        raise MediaNotFound(f"[Pipedream] PD Load found nothing matching {shown}{hint}.")
    if len(found) > 1:
        raise ValueError(
            f"[Pipedream] PD Load found {', '.join(sorted(found))} files for "
            f"'{os.path.join(folder, name)}'; set format to pick one."
        )

    ext, (how, paths, frames) = next(iter(found.items()))
    kind = kind_of(ext)
    if how == "sequence" and kind == "video":
        kind, paths, frames = "video", paths[:1], [0]
    elif how == "sequence":
        kind = "sequence"
    first = os.path.basename(paths[0])
    if kind == "sequence":
        digits = re.search(r"(\d+)\.[^.]+$", first)
        width = len(digits.group(1)) if digits else 4
        pattern = os.path.join(folder, first[:digits.start(1)] + "#" * width
                               + first[digits.end(1):]) if digits else paths[0]
    else:
        pattern = paths[0]
    return {"kind": kind, "paths": paths, "frames": frames, "pattern": pattern, "ext": ext}


def select_frames(media: dict, start_frame: int = 0, frame_count: int = 0,
                  every_nth: int = 1) -> tuple[list[str], list[int], list[int]]:
    """
    Pick the frames of a sequence to load.

    *start_frame* is a frame number (0: the first on disk), *frame_count*
    the number of frames (0: all) and *every_nth* the step.  Returns
    ``(paths, frames, missing)``, where *missing* lists frame numbers in the
    selected range that are not on disk (they are skipped).
    """
    step = max(1, int(every_nth))
    pairs = list(zip(media["frames"], media["paths"]))
    first = media["frames"][0] if start_frame <= 0 else int(start_frame)
    last = media["frames"][-1]
    if first > last:
        raise ValueError(f"[Pipedream] PD Load: start_frame {first} is after the last frame "
                         f"on disk ({last}).")
    wanted = list(range(first, last + 1, step))
    if frame_count > 0:
        wanted = wanted[:int(frame_count)]
    on_disk = dict(pairs)
    paths = [on_disk[n] for n in wanted if n in on_disk]
    frames = [n for n in wanted if n in on_disk]
    missing = [n for n in wanted if n not in on_disk]
    if not paths:
        raise ValueError(f"[Pipedream] PD Load: no frames on disk between {first} and "
                         f"{wanted[-1] if wanted else first}.")
    return paths, frames, missing


def read_image(path: str):
    """
    Decode one image file to an ``HxWx3`` or ``HxWx4`` numpy array.

    uint8 for 8-bit files, uint16 for 16-bit, float32 for float (EXR), the
    same as the video decoder (``core.video._frame_to_array``).
    """
    from .video import _frame_to_array, has_alpha

    try:
        import av

        with av.open(path) as container:
            frame = next(container.decode(video=0))
            return _frame_to_array(frame, None, has_alpha(frame))
    except Exception as av_error:
        try:
            import numpy as np
            from PIL import Image, ImageOps

            with Image.open(path) as img:
                img = ImageOps.exif_transpose(img)
                mode = "RGBA" if "A" in img.getbands() or img.mode == "P" else "RGB"
                return np.array(img.convert(mode))
        except Exception as pil_error:
            raise ValueError(f"[Pipedream] PD Load could not read '{path}': {av_error}; "
                             f"{pil_error}") from pil_error


def read_images(paths: list[str], exr_colorspace: str = "as is"):
    """
    Decode image files into ``(images, mask)``: ``NxHxWx3`` IMAGE and
    ``NxHxW`` MASK, float32.

    All frames must have the same size.  Files without alpha get a
    full-opacity mask.  EXR RGB is un-premultiplied by its alpha, then
    optionally encoded from linear to sRGB.
    """
    import numpy as np

    from .media import linear_to_srgb
    from .video import _stack_arrays

    arrays = []
    for path in paths:
        arr = read_image(path)
        if arrays and arr.shape[:2] != arrays[0].shape[:2]:
            raise ValueError(
                f"[Pipedream] PD Load: '{os.path.basename(path)}' is "
                f"{arr.shape[1]}x{arr.shape[0]} but the first frame is "
                f"{arrays[0].shape[1]}x{arrays[0].shape[0]}."
            )
        arrays.append(arr)

    if any(a.shape[2] == 4 for a in arrays):
        for i, arr in enumerate(arrays):
            if arr.shape[2] == 3:
                full = np.iinfo(arr.dtype).max if arr.dtype.kind == "u" else 1.0
                arrays[i] = np.concatenate(
                    [arr, np.full(arr.shape[:2] + (1,), full, arr.dtype)], axis=-1)
    has_alpha = arrays[0].shape[2] == 4
    is_exr = all(p.lower().endswith(".exr") for p in paths)
    images, mask = _stack_arrays(arrays)

    if is_exr and has_alpha:
        alpha = mask.unsqueeze(-1)
        covered = alpha > 0
        images = images.where(~covered, images / alpha.clamp(min=1e-8))
    if is_exr and exr_colorspace == "linear to sRGB":
        import torch
        images = torch.from_numpy(linear_to_srgb(images.numpy()))
    return images, mask, has_alpha


def sidecar_path(pattern: str, kind: str) -> str:
    """Where PD Output writes the sidecar for this media: the name without frame and extension, .json."""
    folder, name = os.path.split(pattern)
    stem = os.path.splitext(name)[0]
    if kind == "sequence":
        stem = re.sub(r"[._-]?#+", "", stem)
    return os.path.join(folder, (stem or "sequence") + ".json")


def read_sidecar(pattern: str, kind: str) -> dict:
    """The ``context`` of PD Output's sidecar next to the media, or {} when there is none."""
    path = sidecar_path(pattern, kind)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"[Pipedream] Warning: PD Load could not read sidecar '{path}': {exc}",
              file=sys.stderr)
        return {}
    context = data.get("context") if isinstance(data, dict) else None
    return {str(k): v for k, v in context.items()} if isinstance(context, dict) else {}


def fingerprint(paths: list[str]) -> tuple:
    """Modification times and sizes of *paths* and their folders, to spot changes on disk."""
    stamp = []
    for path in list(dict.fromkeys(paths + [os.path.dirname(p) for p in paths])):
        try:
            info = os.stat(path)
            stamp.append((path, info.st_mtime_ns, info.st_size))
        except OSError:
            stamp.append((path, None, None))
    return tuple(stamp)
