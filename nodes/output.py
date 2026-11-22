"""
PD Output node.

One output node for every destination and format: resolves a token
template, then writes images (png/exr/jpg/webp) or video (mp4/mov/webm,
encoded with PyAV, which ships with ComfyUI) either into ComfyUI's output
directory (relative mode) or to an absolute/UNC path (absolute mode).

The source is an IMAGE batch or a ComfyUI VIDEO.  A VIDEO is written with
its own frame rate and audio, or as an image sequence when an image
format is chosen.

Each write can produce a sidecar JSON with the resolved tokens, template,
written paths and the ComfyUI prompt.  The node shows a preview of what was
written, returns the written paths, passes the images through, returns a
VIDEO for written video, and keeps the token reference panel driven by
``web/pipedream.js``.

``PDOutputBase.write_outputs`` holds the shared implementation used by
``PDOutput`` and the legacy ``PDOutputRelative`` / ``PDOutputAbsolute``
nodes.
"""

import os
import sys
from datetime import datetime

from ..core.display import display_name
from ..core.media import (
    IMAGE_FORMATS,
    VIDEO_FORMATS,
    audio_codec,
    build_preview,
    save_video,
    video_codec,
    write_sidecar,
)
from ..core.tokens import resolve_tokens, format_token_reference
from ..core.utils import normalize_path, ensure_directory, save_image_batch

# ComfyUI's folder_paths is available at runtime inside custom nodes.
try:
    import folder_paths  # type: ignore[import-not-found]
except ImportError:
    folder_paths = None

DEFAULT_TEMPLATE = "{project}/{sequence}/{shot}/{shot}_{version}_{date}"
PATH_MODES = ("relative", "absolute")


def get_output_directory() -> str:
    """Return ComfyUI's output directory, with a cwd fallback outside ComfyUI."""
    if folder_paths is not None:
        return folder_paths.get_output_directory()
    fallback = os.path.join(os.getcwd(), "output")
    print(
        "[Pipedream] Warning: folder_paths not available, "
        f"using fallback output dir: {fallback}",
        file=sys.stderr,
    )
    return fallback


def get_temp_directory() -> str | None:
    """Return ComfyUI's temp directory, or None outside ComfyUI."""
    if folder_paths is not None:
        return folder_paths.get_temp_directory()
    return None


def video_from_file(path: str):
    """
    Return a ComfyUI VIDEO (``VideoFromFile``) for *path*, or None when
    ``comfy_api`` is not importable (outside ComfyUI).
    """
    try:
        from comfy_api.latest import InputImpl  # type: ignore[import-not-found]
    except Exception:
        return None
    return InputImpl.VideoFromFile(path)


def video_source(video) -> tuple:
    """
    Unpack a ComfyUI VIDEO into ``(images, audio, fps)``.

    Uses ``get_components()``, so it works for any VIDEO implementation
    (file, tensors, list).
    """
    components = video.get_components()
    fps = float(components.frame_rate) if components.frame_rate else 24.0
    return components.images, getattr(components, "audio", None), fps


class PDOutputBase:
    """Shared write/metadata/preview logic for the PD Output nodes."""

    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING", "STRING", "STRING", "IMAGE", "VIDEO")
    RETURN_NAMES = ("path", "path_sidecar", "path_all", "images", "video")
    OUTPUT_TOOLTIPS = (
        "First file written, or the video file.",
        "Sidecar JSON path (empty when save_metadata is off).",
        "Every written file, one per line.",
        "The input images (or the VIDEO's frames when only a VIDEO is connected).",
        "The written video as a ComfyUI VIDEO (empty for image formats).",
    )

    def write_outputs(self, images, path_mode, base_path, template,
                      frame_padding, file_format, context=None, fps=24.0,
                      crf=18, create_dirs=True, overwrite=False,
                      save_metadata=True, prompt=None, video=None):
        audio = None
        if video is not None:
            frames, audio, fps = video_source(video)
        elif images is not None:
            frames = images
        else:
            raise ValueError(
                "[Pipedream] PD Output needs an input: connect 'images' or 'video'."
            )
        if frames is None or len(frames.shape) < 3 or int(frames.shape[0]) == 0:
            raise ValueError("[Pipedream] PD Output got no frames to write.")

        ctx = dict(context) if context else {}
        now = datetime.now()

        tokens = {
            "date": now.strftime("%Y%m%d"),
            "time": now.strftime("%H%M%S"),
            "frame": "#" * frame_padding,
        }
        tokens.update(ctx)

        resolved = resolve_tokens(template, tokens, frame_padding=frame_padding)
        output_dir = get_output_directory()

        if path_mode == "relative":
            root = output_dir
        else:
            if not base_path or not base_path.strip():
                raise ValueError(
                    "[Pipedream] Absolute path mode needs a base_path "
                    "(e.g. /mnt/projects or \\\\server\\share)."
                )
            root = base_path.strip()

        full_path = normalize_path(os.path.join(root, f"{resolved}.{file_format}"))

        if path_mode == "relative":
            out_abs = os.path.abspath(output_dir)
            if os.path.commonpath([os.path.abspath(full_path), out_abs]) != out_abs:
                raise ValueError(
                    f"[Pipedream] Resolved path escapes the output directory: "
                    f"'{full_path}'. Use absolute path mode for other locations."
                )

        if create_dirs:
            ensure_directory(full_path, create=True)

        is_video = file_format in VIDEO_FORMATS
        if is_video:
            written = save_video(frames, full_path, file_format, fps=fps,
                                 crf=crf, overwrite=overwrite, audio=audio)
        else:
            written = save_image_batch(frames, full_path, overwrite=overwrite)
        final = written[0] if written else full_path

        sidecar = ""
        if save_metadata and written:
            shape = frames.shape
            metadata = {
                "node": type(self).__name__,
                "timestamp": now.isoformat(timespec="seconds"),
                "template": template,
                "resolved": resolved,
                "path_mode": path_mode,
                "base_path": root,
                "format": file_format,
                "frame_padding": frame_padding,
                "source": "video" if video is not None else "images",
                "context": ctx,
                "tokens": tokens,
                "files": written,
                "image": {
                    "count": int(shape[0]),
                    "height": int(shape[1]),
                    "width": int(shape[2]),
                    "channels": int(shape[3]) if len(shape) > 3 else 1,
                },
                "prompt": prompt,
            }
            if is_video:
                has_audio = bool(audio) and audio.get("waveform") is not None
                metadata["video"] = {
                    "fps": fps,
                    "codec": video_codec(file_format),
                    "crf": None if file_format == "mov" else crf,
                    "audio": audio_codec(file_format) if has_audio else None,
                    "sample_rate": int(audio.get("sample_rate", 0)) if has_audio else None,
                }
            sidecar = write_sidecar(os.path.splitext(full_path)[0] + ".json", metadata) or ""

        previews, animated = build_preview(
            frames, written, is_video, fps, output_dir, get_temp_directory()
        )

        ui = {"token_reference": [format_token_reference(ctx, frame_padding=frame_padding)]}
        if previews:
            ui["images"] = previews
            if animated:
                ui["animated"] = (True,)

        video_out = video_from_file(final) if is_video and os.path.isfile(final) else None
        passthrough = images if images is not None else frames
        return {
            "ui": ui,
            "result": (final, sidecar, "\n".join(written), passthrough, video_out),
        }


class PDOutput(PDOutputBase):
    """Write images or video to ComfyUI's output dir or an absolute path using a token template."""

    DISPLAY_NAME = display_name("PD Output")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "path_mode": (list(PATH_MODES), {
                    "default": "relative",
                    "tooltip": "relative: ComfyUI output directory. "
                               "absolute: base_path (absolute or UNC path).",
                }),
                "base_path": ("STRING", {
                    "default": "",
                    "tooltip": "Root folder for absolute mode. Ignored in relative mode.",
                }),
                "template": ("STRING", {"default": DEFAULT_TEMPLATE, "multiline": False}),
                "frame_padding": ("INT", {"default": 4, "min": 1, "max": 8}),
                "format": (list(IMAGE_FORMATS + VIDEO_FORMATS), {
                    "default": "png",
                    "tooltip": "Images: png/exr/jpg/webp. Video: mp4 = H.264, "
                               "mov = ProRes 422 HQ, webm = VP9 (audio from a "
                               "connected VIDEO is kept).",
                }),
            },
            "optional": {
                "images": ("IMAGE", {"tooltip": "Frames to write. Connect this or 'video'."}),
                "context": ("PROJECT_CONTEXT",),
                "video": ("VIDEO", {
                    "tooltip": "Optional VIDEO to write instead of 'images', with its "
                               "own frame rate and audio. With an image format its "
                               "frames are written as an image sequence.",
                }),
                "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.001,
                                  "tooltip": "Video frame rate for 'images'. A connected "
                                             "VIDEO keeps its own frame rate."}),
                "crf": ("INT", {"default": 18, "min": 0, "max": 51,
                                "tooltip": "Video quality for mp4/webm (lower = better). "
                                           "Ignored for ProRes."}),
                "create_dirs": ("BOOLEAN", {"default": True}),
                "overwrite": ("BOOLEAN", {"default": False}),
                "save_metadata": ("BOOLEAN", {"default": True,
                                              "tooltip": "Write a sidecar .json next to the output."}),
            },
            "hidden": {"prompt": "PROMPT"},
        }

    def execute(self, path_mode, base_path, template, frame_padding, format,
                images=None, context=None, video=None, fps=24.0, crf=18,
                create_dirs=True, overwrite=False, save_metadata=True,
                prompt=None):
        return self.write_outputs(
            images, path_mode, base_path, template, frame_padding, format,
            context=context, fps=fps, crf=crf, create_dirs=create_dirs,
            overwrite=overwrite, save_metadata=save_metadata, prompt=prompt,
            video=video,
        )
