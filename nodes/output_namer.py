"""
PD Output Namer node.

Builds a structured output filename using tokens.  Designed to feed into
ComfyUI's built-in Save Image node or PD Network Output.
"""

import os

from ..core.tokens import resolve_tokens


class PDOutputNamer:
    """Build a resolved output path and filename from a token template."""

    DISPLAY_NAME = "PD Output Namer"
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("path", "filename")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "template": ("STRING", {
                    "default": "{project}/{sequence}/{shot}/{shot}_{version}_{date}",
                    "multiline": False,
                }),
                "frame_padding": ("INT", {
                    "default": 4,
                    "min": 1,
                    "max": 8,
                }),
                "extension": (["png", "exr", "jpg", "mp4", "webp"],),
            },
            "optional": {
                "context": ("PROJECT_CONTEXT",),
            },
        }

    def execute(self, template, frame_padding, extension, context=None):
        ctx: dict = {}
        if context is not None:
            ctx.update(context)

        resolved = resolve_tokens(template, ctx, frame_padding=frame_padding)
        full_path = f"{resolved}.{extension}"
        filename = os.path.basename(full_path)
        return (full_path, filename)
