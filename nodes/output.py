"""
PD Output node.

One output node for every destination and format: resolves a token
template, then writes images (png/exr/jpg/webp) or video (mp4/mov/webm via
the ``ffmpeg`` binary) either into ComfyUI's output directory (relative
mode) or to an absolute/UNC path (absolute mode).

Each write can produce a sidecar JSON with the resolved tokens, template,
written paths and the ComfyUI prompt.  The node shows a preview of what was
written, passes the images through for downstream nodes, and keeps the
token reference panel driven by ``web/pipedream.js``.

``PDOutputBase.write_outputs`` holds the shared implementation used by
``PDOutput`` and the legacy ``PDOutputRelative`` / ``PDOutputAbsolute``
nodes.
"""

import os
import sys
from datetime import datetime

from ..core.display import display_name
from ..core.media import (
    EXR_COMPRESSIONS,
    EXR_PRECISIONS,
    IMAGE_FORMATS,
    VIDEO_FORMATS,
    build_preview,
    save_video,
    exr_writer,
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

# Optional EXR widgets shared by PD Output and the legacy nodes (appended
# last so saved widget values keep their positions).
EXR_INPUTS = {
    "exr_precision": (list(EXR_PRECISIONS), {
        "default": "half",
        "tooltip": "EXR only: half (16-bit float) or float (32-bit float).",
    }),
    "exr_compression": (list(EXR_COMPRESSIONS), {
        "default": "zip",
        "tooltip": "EXR only: zip (16 scanlines), zips (1 scanline), rle or none.",
    }),
}


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


class PDOutputBase:
    """Shared write/metadata/preview logic for the PD Output nodes."""

    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING", "IMAGE")
    RETURN_NAMES = ("written_path", "images")

    def write_outputs(self, images, path_mode, base_path, template,
                      frame_padding, file_format, context=None, fps=24.0,
                      crf=18, create_dirs=True, overwrite=False,
                      save_metadata=True, prompt=None, exr_precision="half",
                      exr_compression="zip"):
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
            written = save_video(images, full_path, file_format, fps=fps,
                                 crf=crf, overwrite=overwrite)
        else:
            written = save_image_batch(images, full_path, overwrite=overwrite,
                                       exr_precision=exr_precision,
                                       exr_compression=exr_compression)
        final = written[0] if written else full_path

        if save_metadata and written:
            metadata = {
                "node": type(self).__name__,
                "timestamp": now.isoformat(timespec="seconds"),
                "template": template,
                "resolved": resolved,
                "path_mode": path_mode,
                "base_path": root,
                "format": file_format,
                "frame_padding": frame_padding,
                "context": ctx,
                "tokens": tokens,
                "files": written,
                "image": {
                    "count": int(images.shape[0]),
                    "height": int(images.shape[1]),
                    "width": int(images.shape[2]),
                    "channels": int(images.shape[3]) if len(images.shape) > 3 else 1,
                },
                "prompt": prompt,
            }
            if is_video:
                metadata["video"] = {
                    "fps": fps,
                    "codec": video_codec(file_format),
                    "crf": None if file_format == "mov" else crf,
                }
            elif file_format == "exr":
                metadata["exr"] = {
                    "precision": exr_precision,
                    "compression": exr_compression,
                    "writer": exr_writer()[0],
                }
            write_sidecar(os.path.splitext(full_path)[0] + ".json", metadata)

        previews, animated = build_preview(
            images, written, is_video, fps, output_dir, get_temp_directory()
        )

        ui = {"token_reference": [format_token_reference(ctx, frame_padding=frame_padding)]}
        if previews:
            ui["images"] = previews
            if animated:
                ui["animated"] = (True,)

        return {"ui": ui, "result": (final, images)}


class PDOutput(PDOutputBase):
    """Write images or video to ComfyUI's output dir or an absolute path using a token template."""

    DISPLAY_NAME = display_name("PD Output")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
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
                    "tooltip": "Images: png/exr/jpg/webp. Video (needs ffmpeg on PATH): "
                               "mp4 = H.264, mov = ProRes 422 HQ, webm = VP9.",
                }),
            },
            "optional": {
                "context": ("PROJECT_CONTEXT",),
                "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.001,
                                  "tooltip": "Video frame rate."}),
                "crf": ("INT", {"default": 18, "min": 0, "max": 51,
                                "tooltip": "Video quality for mp4/webm (lower = better). "
                                           "Ignored for ProRes."}),
                "create_dirs": ("BOOLEAN", {"default": True}),
                "overwrite": ("BOOLEAN", {"default": False}),
                "save_metadata": ("BOOLEAN", {"default": True,
                                              "tooltip": "Write a sidecar .json next to the output."}),
                **EXR_INPUTS,
            },
            "hidden": {"prompt": "PROMPT"},
        }

    def execute(self, images, path_mode, base_path, template, frame_padding,
                format, context=None, fps=24.0, crf=18, create_dirs=True,
                overwrite=False, save_metadata=True, prompt=None,
                exr_precision="half", exr_compression="zip"):
        return self.write_outputs(
            images, path_mode, base_path, template, frame_padding, format,
            context=context, fps=fps, crf=crf, create_dirs=create_dirs,
            overwrite=overwrite, save_metadata=save_metadata, prompt=prompt,
            exr_precision=exr_precision, exr_compression=exr_compression,
        )
