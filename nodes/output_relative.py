"""
PD Output Relative node.

Resolves a token template and saves images to ComfyUI's output directory.
Combines template resolution with image writing in a single output node.
Includes a token reference display (updated via JS extension).
"""

import os
import sys

from ..core.display import display_name
from ..core.tokens import resolve_tokens, format_token_reference
from ..core.utils import normalize_path, ensure_directory, save_image_batch

# ComfyUI's folder_paths is available at runtime inside custom nodes.
try:
    import folder_paths  # type: ignore[import-not-found]
except ImportError:
    folder_paths = None


class PDOutputRelative:
    """Save images to ComfyUI's output directory using a token template."""

    DISPLAY_NAME = display_name("PD Output Relative")
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("written_path",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "template": ("STRING", {
                    "default": "{project}/{sequence}/{shot}/{shot}_{version}_{date}",
                    "multiline": False,
                }),
                "frame_padding": ("INT", {"default": 4, "min": 1, "max": 8}),
                "extension": (["png", "exr", "jpg", "webp"],),
            },
            "optional": {
                "context": ("PROJECT_CONTEXT",),
                "create_dirs": ("BOOLEAN", {"default": True}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
        }

    def execute(self, images, template, frame_padding, extension,
                context=None, create_dirs=True, overwrite=False):
        ctx = dict(context) if context else {}

        resolved = resolve_tokens(template, ctx, frame_padding=frame_padding)
        relative_path = f"{resolved}.{extension}"

        # Join with ComfyUI's output directory
        if folder_paths is not None:
            output_dir = folder_paths.get_output_directory()
        else:
            output_dir = os.path.join(os.getcwd(), "output")
            print(
                "[Pipedream] Warning: folder_paths not available, "
                f"using fallback output dir: {output_dir}",
                file=sys.stderr,
            )

        full_path = normalize_path(os.path.join(output_dir, relative_path))

        if create_dirs:
            ensure_directory(full_path, create=True)

        written = save_image_batch(images, full_path, overwrite=overwrite)
        final = written[0] if written else full_path

        # Token reference for JS display
        token_ref = format_token_reference(ctx, frame_padding=frame_padding)

        return {"ui": {"token_reference": [token_ref]}, "result": (final,)}
