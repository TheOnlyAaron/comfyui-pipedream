"""
PD Load node: the inverse of PD Output.

Loads ``file`` from ComfyUI's input directory (relative mode) or from an
absolute/UNC ``base_path``: a single image, an image sequence or a video.
``file`` is a plain file name, or a token template (tokens from an
optional context and wedge, like PD Output).  Pasted paths may be quoted
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
``context`` (the tokens in PD Output's sidecar next to the media, with the
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
import uuid

from ..core import settings
from ..core.common import display_name
from ..core.load import (
    EXR_COLORSPACES,
    clean_path,
    split_file,
    FORMATS,
    FRAME_MARK,
    find_media,
    fingerprint,
    read_images,
    read_sidecar,
    select_frames,
)
from ..core.media import PATH_MODES, frames_to_uint8, normalize_path, save_video
from ..core.tokens import auto_tokens, resolve_tokens, with_extra
from ..core.video import comfy_video_api, images_to_video, read_frames
from ..core.wedge import wedge_tokens

try:
    import folder_paths  # type: ignore[import-not-found]
except ImportError:
    folder_paths = None

# Per node: the last resolved path, and whether context/wedge were linked
# (IS_CHANGED only sees widget values, so it re-checks the last path then).
_LAST_RESOLVED: dict = {}
_LINKED: dict = {}
_PREVIEW_SIZE = 512
_PREVIEW_FRAMES = 1000


def input_directory() -> str:
    """ComfyUI's input directory, with a cwd fallback outside ComfyUI."""
    if folder_paths is not None:
        return folder_paths.get_input_directory()
    return os.path.join(os.getcwd(), "input")


def resolve_path(path_mode: str, base_path: str, file: str, tokens: dict) -> str:
    """Resolve *file* to a full path (frame mark kept), checking relative paths stay inside input."""
    file, base_path = clean_path(file), clean_path(base_path)
    if not file:
        raise ValueError("[Pipedream] PD Load: file is empty. Type a file name, or paste "
                         "the full path of a file into file or base_path.")
    resolved = resolve_tokens(file, {**tokens, "frame": FRAME_MARK})
    if path_mode == "relative":
        root = input_directory()
    else:
        if not base_path:
            raise ValueError("[Pipedream] PD Load absolute mode needs a base_path "
                             "(e.g. /mnt/projects or \\\\server\\share).")
        root = base_path
    full = normalize_path(os.path.join(root, resolved))
    if path_mode == "relative":
        inside = os.path.abspath(root)
        if os.path.commonpath([os.path.abspath(full), inside]) != inside:
            raise ValueError(f"[Pipedream] PD Load: '{resolved}' is outside the input "
                             "directory. Use absolute path mode for other locations.")
    return full


def _preview(images, fps: float, audio=None) -> tuple[list[dict], bool]:
    """
    The node's preview in the temp directory: a PNG of a single frame, or a
    playable H.264 mp4 (with the audio) of several, downscaled to
    ``_PREVIEW_SIZE``.  Returns ``(entries, animated)``.
    """
    if folder_paths is None:
        return [], False
    try:
        import torch.nn.functional as F
        from PIL import Image

        temp = folder_paths.get_temp_directory()
        os.makedirs(temp, exist_ok=True)
        name = f"pd_load_{uuid.uuid4().hex[:8]}"
        if int(images.shape[0]) == 1:
            img = Image.fromarray(frames_to_uint8(images[:1])[0])
            img.thumbnail((_PREVIEW_SIZE, _PREVIEW_SIZE))
            img.save(os.path.join(temp, name + ".png"), compress_level=1)
            return [{"filename": name + ".png", "subfolder": "", "type": "temp"}], False
        frames = images[:_PREVIEW_FRAMES]
        h, w = int(frames.shape[1]), int(frames.shape[2])
        scale = min(1.0, _PREVIEW_SIZE / max(h, w))
        if scale < 1.0:
            size = (max(2, int(h * scale)), max(2, int(w * scale)))
            frames = F.interpolate(frames.permute(0, 3, 1, 2), size=size, mode="area")
            frames = frames.permute(0, 2, 3, 1)
        path = os.path.join(temp, name + ".mp4")
        save_video(frames.clamp(0, 1), path, "mp4", fps=fps, crf=23, overwrite=True,
                   audio=audio)
        return [{"filename": name + ".mp4", "subfolder": "", "type": "temp"}], True
    except Exception as exc:
        print(f"[Pipedream] Warning: PD Load preview failed: {exc}", file=sys.stderr)
        return [], False


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
        "an absolute/UNC base_path), with its alpha, frame rate, audio and PD Output "
        "sidecar tokens. Paste a full file path into file or base_path to fill both. "
        "file can use tokens, so it can read back what PD Output wrote."
    )
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    RETURN_TYPES = ("IMAGE", "MASK", "FLOAT", "INT", "INT", "STRING", "PROJECT_CONTEXT",
                    "VIDEO", "AUDIO")
    RETURN_NAMES = ("images", "mask", "fps", "frame_count", "first_frame", "path", "context",
                    "video", "audio")
    OUTPUT_TOOLTIPS = (
        "The loaded frames (RGB).",
        "Alpha of each frame, 1.0 = opaque (full opacity when the files have none).",
        "Frame rate: the video's (fps_from_file), else the fps input; divided by every_nth.",
        "Number of frames loaded.",
        "First frame number of a sequence, or the start index of a video (0 for one image).",
        "The first file loaded (the video file for video).",
        "The tokens of PD Output's sidecar next to the media, with the incoming "
        "context's non-empty values on top.",
        "The video file, or the loaded frames as an in-memory VIDEO.",
        "The video's audio (video files only).",
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
                               "Tokens such as {shot}_{version} come from context and wedge.",
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
                               "sRGB: encode to sRGB, the inverse of PD Output's sRGB to linear.",
                }),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    @classmethod
    def IS_CHANGED(cls, path_mode="relative", base_path="", file="", format="auto",
                   unique_id=None, context=None, wedge=None, **kwargs):
        widgets = (path_mode, base_path, file, format,
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
            paths = find_media(resolved, format)["paths"] if resolved else []
        except Exception:
            paths = []
        return repr((widgets, resolved, fingerprint(paths)))

    def execute(self, path_mode, base_path, file, format, start_frame=0, frame_count=0,
                every_nth=1, context=None, wedge=None, fps_from_file=True,
                fps=settings.get("output.fps"), exr_colorspace="as is", unique_id=None):
        incoming = dict(context) if context else {}
        tokens = auto_tokens()
        tokens.update(with_extra({**incoming, **wedge_tokens(wedge)}))
        full = resolve_path(path_mode, base_path, file, tokens)
        _LAST_RESOLVED[str(unique_id)] = full
        _LINKED[str(unique_id)] = context is not None or wedge is not None
        media = find_media(full, format)

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
            images, mask, has_alpha = read_images(loaded, exr_colorspace)
            rate = float(fps) / max(1, int(every_nth))
            count = int(images.shape[0])
            video = images_to_video(images, rate)

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
        if missing:
            lines.append(f"! missing frames (skipped): {_ranges(missing)}")

        ui = {"load_info": ["\n".join(lines)]}
        preview, animated = _preview(images, rate, audio)
        if preview:
            ui["images"] = preview
            if animated:
                ui["animated"] = (True,)
        return {
            "ui": ui,
            "result": (images, mask, rate, count, first, loaded[0], out_context, video, audio),
        }


def _register_routes():
    try:
        from aiohttp import web
        from server import PromptServer
    except ImportError:
        return
    if getattr(PromptServer, "instance", None) is None:
        return

    @PromptServer.instance.routes.post("/pipedream/load/check")
    async def load_check_route(request):
        """``{"path"}`` -> ``{"folder", "name"}`` when it is an existing file, else ``{}``."""
        try:
            body = await request.json()
            return web.json_response(split_file(str(body.get("path", ""))) or {})
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=400)


_register_routes()
