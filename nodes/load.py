"""
PD Load node: the inverse of PD Output.

Resolves a token template (from an optional context and wedge, like PD
Output) to a path in ComfyUI's input directory (relative mode) or under
an absolute/UNC ``base_path``, and loads what it finds there: a single
image, an image sequence or a video.  Finding and decoding live in
``core/load.py``.

Outputs follow what was loaded: ``images`` and ``mask`` (alpha, 1.0 =
opaque), ``fps``, ``frame_count``, ``first_frame`` (the first frame
number of a sequence, or the start index of a video), ``path``,
``context`` (the tokens in PD Output's sidecar next to the media, with the
incoming context's non-empty values on top), a ``video`` (the file itself, or the loaded frames as
an in-memory VIDEO) and ``audio`` (video files only).  The frontend
(``web/pd_load.js``) hides inputs and the audio output that do not apply
to the chosen format.

Files are re-read when they change on disk: ``IS_CHANGED`` looks the
media up again and fingerprints the files and their folder.  It resolves
the template itself when no context or wedge is linked; otherwise (it
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
    FORMATS,
    FRAME_MARK,
    find_media,
    fingerprint,
    read_images,
    read_sidecar,
    select_frames,
)
from ..core.media import PATH_MODES, frames_to_uint8, normalize_path
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


def input_directory() -> str:
    """ComfyUI's input directory, with a cwd fallback outside ComfyUI."""
    if folder_paths is not None:
        return folder_paths.get_input_directory()
    return os.path.join(os.getcwd(), "input")


def resolve_path(path_mode: str, base_path: str, template: str, tokens: dict) -> str:
    """Resolve *template* to a full path (frame mark kept), checking relative paths stay inside input."""
    resolved = resolve_tokens(template, {**tokens, "frame": FRAME_MARK})
    if path_mode == "relative":
        root = input_directory()
    else:
        if not base_path or not base_path.strip():
            raise ValueError("[Pipedream] PD Load absolute mode needs a base_path "
                             "(e.g. /mnt/projects or \\\\server\\share).")
        root = base_path.strip()
    full = normalize_path(os.path.join(root, resolved))
    if path_mode == "relative":
        inside = os.path.abspath(root)
        if os.path.commonpath([os.path.abspath(full), inside]) != inside:
            raise ValueError(f"[Pipedream] PD Load: '{resolved}' is outside the input "
                             "directory. Use absolute path mode for other locations.")
    return full


def _preview(images) -> list[dict]:
    """A downscaled PNG of the first frame in the temp directory, for the node's preview."""
    if folder_paths is None:
        return []
    try:
        from PIL import Image

        temp = folder_paths.get_temp_directory()
        os.makedirs(temp, exist_ok=True)
        img = Image.fromarray(frames_to_uint8(images[:1])[0])
        img.thumbnail((_PREVIEW_SIZE, _PREVIEW_SIZE))
        name = f"pd_load_{uuid.uuid4().hex[:8]}.png"
        img.save(os.path.join(temp, name), compress_level=1)
        return [{"filename": name, "subfolder": "", "type": "temp"}]
    except Exception as exc:
        print(f"[Pipedream] Warning: PD Load preview failed: {exc}", file=sys.stderr)
        return []


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
    """Load an image, image sequence or video from a token template (local or network path)."""

    DISPLAY_NAME = display_name("PD Load")
    DESCRIPTION = (
        "The inverse of PD Output: resolves a token template to a path (ComfyUI's input "
        "folder, or an absolute/UNC base_path) and loads the image, image sequence or "
        "video found there, with its alpha, frame rate, audio and PD Output sidecar tokens."
    )
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "MASK", "FLOAT", "INT", "INT", "STRING", "PROJECT_CONTEXT",
                    "VIDEO", "AUDIO")
    RETURN_NAMES = ("images", "mask", "fps", "frame_count", "first_frame", "path", "context",
                    "video", "audio")
    OUTPUT_TOOLTIPS = (
        "The loaded frames (RGB).",
        "Alpha of each frame, 1.0 = opaque (full opacity when the files have none).",
        "Frame rate: the video's, or the fps input for images, divided by every_nth.",
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
                    "tooltip": "Root folder for absolute mode. Ignored in relative mode.",
                }),
                "template": ("STRING", {
                    "default": s("load.template"),
                    "tooltip": "Path to load, with tokens. The extension is optional (see "
                               "format). Mark sequence frames with {frame}, #### or %04d; "
                               "PD Output's name.1001.png is found without a mark too.",
                }),
                "format": (list(FORMATS), {
                    "default": "auto",
                    "tooltip": "File type to look for when the template has no extension. "
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
                    "tooltip": "Tokens for the template, from PD Project/Custom Context.",
                }),
                "wedge": ("WEDGE", {
                    "tooltip": "Last PD Wedge of a chain: its tokens fill the template, so "
                               "each wedge job can load a different file.",
                }),
                "fps": ("FLOAT", {
                    "default": settings.get("output.fps"), "min": 1.0, "max": 240.0,
                    "step": 0.001,
                    "tooltip": "Frame rate of images and sequences. Video files keep their own.",
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
    def IS_CHANGED(cls, path_mode="relative", base_path="", template="", format="auto",
                   unique_id=None, context=None, wedge=None, **kwargs):
        widgets = (path_mode, base_path, template, format,
                   tuple(sorted((k, str(v)) for k, v in kwargs.items())))
        resolved = None
        if context is None and wedge is None and not _LINKED.get(str(unique_id)):
            try:
                resolved = resolve_path(path_mode, base_path, template,
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

    def execute(self, path_mode, base_path, template, format, start_frame=0, frame_count=0,
                every_nth=1, context=None, wedge=None, fps=settings.get("output.fps"),
                exr_colorspace="as is", unique_id=None):
        incoming = dict(context) if context else {}
        tokens = auto_tokens()
        tokens.update(with_extra({**incoming, **wedge_tokens(wedge)}))
        full = resolve_path(path_mode, base_path, template, tokens)
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
            whole = start_frame == 0 and frame_count == 0 and every_nth == 1
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
        lines.append(f"{width}x{height}, alpha: {alpha_note}, fps {rate:g}"
                     + (", audio" if audio else ""))
        if sidecar:
            lines.append(f"sidecar: {len(sidecar)} token(s) ({', '.join(sorted(sidecar))})")
        if missing:
            lines.append(f"! missing frames (skipped): {_ranges(missing)}")

        ui = {"load_info": ["\n".join(lines)]}
        preview = _preview(images)
        if preview:
            ui["images"] = preview
        return {
            "ui": ui,
            "result": (images, mask, rate, count, first, loaded[0], out_context, video, audio),
        }
