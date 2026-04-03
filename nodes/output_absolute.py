"""
PD Output Absolute node.

Resolves a token template and saves images to an absolute or UNC network
path.  Identical to PD Output Relative except the base path is user-supplied
rather than ComfyUI's output directory.
"""

import os

from ..core.display import display_name
from ..core.tokens import resolve_tokens, format_token_reference
from ..core.utils import normalize_path, ensure_directory, save_image_batch


class PDOutputAbsolute:
    """Save images to an absolute or network path using a token template."""

    DISPLAY_NAME = display_name("PD Output Absolute")
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
                "base_path": ("STRING", {"default": ""}),
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

    def execute(self, images, base_path, template, frame_padding, extension,
                context=None, create_dirs=True, overwrite=False):
        ctx = dict(context) if context else {}

        resolved = resolve_tokens(template, ctx, frame_padding=frame_padding)
        relative_path = f"{resolved}.{extension}"

        full_path = normalize_path(os.path.join(base_path, relative_path))

        if create_dirs:
            ensure_directory(full_path, create=True)

        written = save_image_batch(images, full_path, overwrite=overwrite)
        final = written[0] if written else full_path

        # Token reference for JS display
        token_ref = format_token_reference(ctx, frame_padding=frame_padding)

        return {"ui": {"token_reference": [token_ref]}, "result": (final,)}
