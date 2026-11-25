"""
PD Load node: the inverse of PD Save.

Loads ``file`` from ComfyUI's input directory (relative mode) or from an
absolute/UNC ``base_path``: a single image, an image sequence or a video.
``file`` is a plain file name, or a token template (tokens from an
optional context and wedge, like PD Save).  Pasted paths may be quoted
(Windows "Copy as path"); the frontend (``web/pd_load.js``) splits a full
path pasted into either field into base_path and file, using
``POST /pipedream/load/check``.  Finding and decoding live in
``core/load.py``.

PD Load is an output node, so it can be run on its own (its "load"
button, or the selection toolbar's run button) to check what it loads.
Multi-frame loads preview as a playable mp4.

Outputs follow what was loaded: ``images`` and ``mask`` (alpha, 1.0 =
opaque), ``fps``, ``frame_count``, ``first_frame`` (the first frame
number of a sequence, or the start index of a video), ``path``,
``context`` (the tokens in PD Save's sidecar next to the media, with the
incoming context's non-empty values on top), a ``video`` (the file
itself, or the loaded frames as an in-memory VIDEO) and ``audio`` (video
files only).  ``fps_from_file`` uses a video's own frame rate; ``fps`` is
the rate of images, and an override for video when it is off.  The frontend
(``web/pd_load.js``) hides inputs and the audio output that do not apply
to the chosen format.

Files are re-read when they change on disk: ``IS_CHANGED`` looks the
media up again and fingerprints the files and their folder.  It resolves
``file`` itself when no context or wedge is linked; otherwise (it
only sees widget values) it re-checks the path the node resolved last,
and a changed context or wedge re-runs the node through ComfyUI's cache.
"""

import os
import sys

from ..core import settings
from ..core.comfy import input_directory, server_routes, temp_directory
from ..core.common import display_name
from ..core.exr_meta import ExrMetadata
from ..core.load import (
    EXR_COLORSPACES,
    SEQUENCE_MODES,
    clean_path,
    looks_absolute,
    split_file,
    FORMATS,
    find_media,
    fingerprint,
    normalize_sequence_mode,
    read_images,
    read_sidecar,
    select_frames,
)
from ..core.media import PATH_MODES, normalize_path, preview_clip, preview_name, preview_still
from ..core.paths import FRAME_MARK, check_inside, resolve_root
from ..core.tokens import auto_tokens, resolve_tokens, with_extra
from ..core.video import comfy_video_api, images_to_video, read_frames
from ..core.wedge import wedge_tokens

# Per node: the last resolved path, and whether context/wedge were linked
# (IS_CHANGED only sees widget values, so it re-checks the last path then).
_LAST_RESOLVED: dict = {}
_LINKED: dict = {}


def resolve_path(path_mode: str, base_path: str, file: str, tokens: dict) -> str:
    """
    Resolve *file* to a full path (frame mark kept).  A *file* that is
    already a full path (e.g. PD Save's ``path``) is used as is;
    otherwise it is joined to the root, and relative paths must stay inside
    ComfyUI's input folder.
    """
    file = clean_path(file)
    if not file:
        raise ValueError("[Pipedream] PD Load: file is empty. Type a file name, or paste "
                         "the full path of a file into file or base_path.")
    resolved = resolve_tokens(file, {**tokens, "frame": FRAME_MARK})
    if looks_absolute(resolved):
        return normalize_path(resolved)
    root = resolve_root(path_mode, clean_path(base_path), input_directory(), "PD Load")
    full = normalize_path(os.path.join(root, resolved))
    if path_mode == "relative":
        check_inside(full, root, "PD Load", "input")
    return full


def _preview(images, fps: float, audio=None) -> tuple[list[dict], bool]:
    """The node's preview: a PNG of a single frame, or a playable mp4 of several."""
    temp = temp_directory()
    if temp is None:
        return [], False
    try:
        name = preview_name("pd_load")
        if int(images.shape[0]) == 1:
            return [preview_still(images[0], temp, name)], False
        return [preview_clip(images, fps, temp, name, audio)], True
    except Exception as exc:
        print(f"[Pipedream] Warning: PD Load preview failed: {exc}", file=sys.stderr)
        return [], False


def _mode(sequence_mode, legacy: dict) -> str:
    """
    The sequence mode to use: *sequence_mode*, or the old
    ``sequence_from_file`` boolean from an API prompt written before 0.2.1.
    """
    if "sequence_from_file" in legacy and sequence_mode in (None, "auto"):
        return normalize_sequence_mode(legacy["sequence_from_file"])
    return normalize_sequence_mode(sequence_mode)


def _ranges(numbers: list[int]) -> str:
    """'1004, 1007-1009' for a sorted list of frame numbers."""
    parts, start, prev = [], None, None
    for n in numbers + [None]:
        if start is None:
            start = prev = n
        elif n is not None and n == prev + 1:
            prev = n
        else:
            parts.append(f"{start}" if start == prev else f"{start}-{prev}")
            start = prev = n
    return ", ".join(parts)


class PDLoad:
    """Load an image, image sequence or video from a local or network path."""

    DISPLAY_NAME = display_name("PD Load")
    DESCRIPTION = (
        "Load an image, image sequence or video from a folder (ComfyUI's input folder, or "
        "an absolute/UNC base_path), with its alpha, frame rate, audio and PD Save "
        "sidecar tokens. Paste a full file path into file or base_path to fill both. "
        "file can use tokens, so it can read back what PD Save wrote."
    )
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    # exr_metadata must stay last: the frontend hides trailing outputs only.
    RETURN_TYPES = ("IMAGE", "MASK", "FLOAT", "INT", "INT", "STRING", "PROJECT_CONTEXT",
                    "VIDEO", "AUDIO", "EXR_METADATA")
    RETURN_NAMES = ("images", "mask", "fps", "frame_count", "first_frame", "path", "context",
                    "video", "audio", "exr_metadata")
    OUTPUT_TOOLTIPS = (
        "The loaded frames (RGB).",
        "Alpha of each frame, 1.0 = opaque (full opacity when the files have none).",
        "Frame rate: the video's (fps_from_file), else the fps input; divided by every_nth.",
        "Number of frames loaded.",
        "First frame number of a sequence, or the start index of a video (0 for one image).",
        "The first file loaded (the video file for video).",
        "The tokens of PD Save's sidecar next to the media, with the incoming "
        "context's non-empty values on top.",
        "The video file, or the loaded frames as an in-memory VIDEO.",
        "The video's audio (video files only).",
        "The EXR header metadata of each loaded frame (empty for other formats), for PD "
        "Output's exr_metadata or PD EXR Metadata Get. Structural attributes (channels, "
        "windows, compression) are left out.",
    )

    @classmethod
    def INPUT_TYPES(cls):
        s = settings.get
        return {
            "required": {
                "path_mode": (list(PATH_MODES), {
                    "default": s("load.path_mode"),
                    "tooltip": "relative: ComfyUI input directory. "
                               "absolute: base_path (absolute or UNC path).",
                }),
                "base_path": ("STRING", {
                    "default": s("load.base_path"),
                    "tooltip": "Folder for absolute mode. Paste a full file path here or "
                               "into file and it is split into folder and file.",
                }),
                "file": ("STRING", {
                    "default": s("load.file"),
                    "tooltip": "File to load, e.g. plate.exr, or shot.####.exr for a sequence "
                               "(also {frame} or %04d). The extension is optional (see format). "
                               "Tokens such as {shot}_{version} come from context and wedge. "
                               "A full path (e.g. PD Save's path) ignores base_path.",
                }),
                "format": (list(FORMATS), {
                    "default": "auto",
                    "tooltip": "File type to look for when file has no extension. "
                               "auto: any supported type (an error if several match).",
                }),
                "start_frame": ("INT", {
                    "default": 0, "min": 0, "max": 9999999,
                    "tooltip": "Sequences: first frame number to load (0: the first on disk). "
                               "Video: first frame index (0: the start).",
                }),
                "frame_count": ("INT", {
                    "default": 0, "min": 0, "max": 9999999,
                    "tooltip": "Number of frames to load (0: all).",
                }),
                "every_nth": ("INT", {
                    "default": 1, "min": 1, "max": 1000,
                    "tooltip": "Load every nth frame (fps is divided to match).",
                }),
            },
            "optional": {
                "sequence_mode": (list(SEQUENCE_MODES), {
                    "default": "auto",
                    "tooltip": "When file is one numbered image (shot.1001.exr): "
                               "auto: load the whole sequence it belongs to, unless PD "
                               "Output's sidecar, different frame sizes or unpadded numbers "
                               "(wedge outputs) say it is a single image; the panel says "
                               "why. single file: just this file. sequence: every file "
                               "named like it. A frame mark (####) always loads a sequence.",
                }),
                "context": ("PROJECT_CONTEXT", {
                    "tooltip": "Tokens for file, from PD Project/Custom Context.",
                }),
                "wedge": ("WEDGE", {
                    "tooltip": "Last PD Wedge of a chain: its tokens fill file, so "
                               "each wedge job can load a different file.",
                }),
                "fps_from_file": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Use a video file's own frame rate. Off: use fps instead. "
                               "Images and sequences always use fps.",
                }),
                "fps": ("FLOAT", {
                    "default": settings.get("output.fps"), "min": 1.0, "max": 240.0,
                    "step": 0.001,
                    "tooltip": "Frame rate of images and sequences, and of video when "
                               "fps_from_file is off.",
                }),
                "exr_colorspace": (list(EXR_COLORSPACES), {
                    "default": "as is",
                    "tooltip": "EXR only. as is: values unchanged (usually linear). linear to "
                               "sRGB: encode to sRGB, the inverse of PD Save's sRGB to linear.",
                }),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    @classmethod
    def VALIDATE_INPUTS(cls, sequence_mode="auto"):
        """Accept the old sequence_from_file booleans in sequence_mode (converted on execute)."""
        return True

    @classmethod
    def IS_CHANGED(cls, path_mode="relative", base_path="", file="", format="auto",
                   unique_id=None, context=None, wedge=None, sequence_mode="auto",
                   **kwargs):
        sequence_mode = _mode(sequence_mode, kwargs)
        widgets = (path_mode, base_path, file, format, sequence_mode,
                   tuple(sorted((k, str(v)) for k, v in kwargs.items())))
        resolved = None
        if context is None and wedge is None and not _LINKED.get(str(unique_id)):
            try:
                resolved = resolve_path(path_mode, base_path, file,
                                        {**auto_tokens(), **with_extra({})})
            except Exception:
                resolved = None
        if resolved is None:
            resolved = _LAST_RESOLVED.get(str(unique_id))
        try:
            paths = (find_media(resolved, format, sequence_mode)["paths"]
                     if resolved else [])
        except Exception:
            paths = []
        return repr((widgets, resolved, fingerprint(paths)))

    def execute(self, path_mode, base_path, file, format, start_frame=0, frame_count=0,
                every_nth=1, sequence_mode="auto", context=None, wedge=None,
                fps_from_file=True,
                fps=settings.get("output.fps"), exr_colorspace="as is", unique_id=None,
                **legacy):
        sequence_mode = _mode(sequence_mode, legacy)
        incoming = dict(context) if context else {}
        tokens = auto_tokens()
        tokens.update(with_extra({**incoming, **wedge_tokens(wedge)}))
        full = resolve_path(path_mode, base_path, file, tokens)
        _LAST_RESOLVED[str(unique_id)] = full
        _LINKED[str(unique_id)] = context is not None or wedge is not None
        media = find_media(full, format, sequence_mode)

        missing, audio = [], None
        if media["kind"] == "video":
            video_from_file = comfy_video_api()[1]
            if video_from_file is None:
                raise RuntimeError("[Pipedream] PD Load needs ComfyUI's comfy_api video support.")
            source = video_from_file(media["paths"][0])
            images, mask, audio, rate, count = read_frames(source, start_frame, frame_count,
                                                           every_nth)
            file_rate = rate
            if not fps_from_file:
                rate = float(fps) / max(1, int(every_nth))
            whole = (start_frame == 0 and frame_count == 0 and every_nth == 1
                     and abs(rate - file_rate) < 1e-6)
            video = source if whole else images_to_video(images, rate, audio)
            first, loaded = int(start_frame), media["paths"][:1]
            has_alpha = bool((mask < 1.0).any())
        else:
            if media["kind"] == "sequence":
                loaded, frames, missing = select_frames(media, start_frame, frame_count,
                                                        every_nth)
                first = frames[0]
            else:
                loaded, first = media["paths"], 0
            try:
                images, mask, has_alpha = read_images(loaded, exr_colorspace)
            except ValueError as exc:
                if media["kind"] == "sequence" and "first frame is" in str(exc):
                    raise ValueError(f"{exc} If these are separate images, set sequence_mode "
                                     "to single file.") from exc
                raise
            rate = float(fps) / max(1, int(every_nth))
            count = int(images.shape[0])
            video = images_to_video(images, rate)

        exr_metadata = ExrMetadata()
        if media["kind"] != "video" and media["ext"] == "exr":
            exr_metadata = ExrMetadata.from_files(loaded)

        sidecar = read_sidecar(media["pattern"], media["kind"])
        out_context = {**incoming, **sidecar,
                       **{k: v for k, v in incoming.items() if v not in ("", None)}}

        height, width = int(images.shape[1]), int(images.shape[2])
        kind = {"image": "image", "sequence": "image sequence", "video": "video"}[media["kind"]]
        lines = [f"Loaded: {media['pattern']}"]
        if media["kind"] == "sequence":
            lines.append(f"{kind}: frames {first}-{frames[-1]} ({count} loaded, "
                         f"{len(media['frames'])} on disk {media['frames'][0]}-"
                         f"{media['frames'][-1]})")
        else:
            lines.append(f"{kind}: {count} frame{'s' if count != 1 else ''}"
                         + (f" from index {first}" if media["kind"] == "video" else ""))
        if exr_metadata:
            names = exr_metadata.names()
            varying = exr_metadata.varying()
            lines.append(f"exr metadata: {len(names)} attribute{'s' if len(names) != 1 else ''}"
                         + (f", {len(varying)} varying by frame" if varying else ""))
        alpha_note = "yes" if has_alpha else "no"
        if has_alpha and media["ext"] == "exr":
            alpha_note += " (EXR, un-premultiplied)"
        fps_note = f"fps {rate:g}"
        if media["kind"] == "video" and not fps_from_file and abs(rate - file_rate) > 1e-6:
            fps_note += f" (override; file {file_rate:g})"
        lines.append(f"{width}x{height}, alpha: {alpha_note}, {fps_note}"
                     + (", audio" if audio else ""))
        if sidecar:
            lines.append(f"sidecar: {len(sidecar)} token(s) ({', '.join(sorted(sidecar))})")
        if media.get("note"):
            lines.append(media["note"])
        if missing:
            lines.append(f"! missing frames (skipped): {_ranges(missing)}")

        ui = {"load_info": ["\n".join(lines)], "pd_loaded": [loaded[0]]}
        preview, animated = _preview(images, rate, audio)
        if preview:
            ui["images"] = preview
            if animated:
                ui["animated"] = (True,)
        return {
            "ui": ui,
            "result": (images, mask, rate, count, first, loaded[0], out_context, video, audio,
                       exr_metadata),
        }


routes, web = server_routes()
if routes is not None:
    @routes.post("/pipedream/load/check")
    async def load_check_route(request):
        """``{"path"}`` -> ``{"folder", "name"}`` when it is an existing file, else ``{}``."""
        try:
            body = await request.json()
            return web.json_response(split_file(str(body.get("path", ""))) or {})
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=400)

    @routes.post("/pipedream/load/path")
    async def path_route(request):
        """
        ``{"path_mode", "base_path", "file", "last"}`` -> ``{"path"}``: the full
        path of the file the widgets point at, for the Copy Path button.  Falls
        back to the last loaded file, then the folder.  Nothing is opened.
        """
        try:
            body = await request.json()
            mode = str(body.get("path_mode", "relative"))
            path = ""
            try:
                full = resolve_path(mode, str(body.get("base_path", "")), str(body.get("file", "")),
                                    {**auto_tokens(), **with_extra({})})
                if "{" not in full:
                    path = full
            except Exception:
                path = ""
            path = path or str(body.get("last") or "")
            if not path:
                path = input_directory() if mode == "relative" else str(body.get("base_path") or "").strip()
            if not path:
                return web.json_response({"error": "Set base_path or file first."})
            return web.json_response({"path": os.path.normpath(path)})
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=400)
