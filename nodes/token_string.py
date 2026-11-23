"""
PD Token String node.

Resolves a token template to a plain string, e.g. for prompts, filenames
or other nodes' path widgets.  Tokens come from an optional
PROJECT_CONTEXT (PD Project Context / PD Custom Context) plus the
automatic ``{date}``, ``{time}`` and ``{frame}`` tokens.  The default
template and frame padding come from the settings (``core/settings.py``).
"""

from ..core import settings
from ..core.common import display_name
from ..core.tokens import resolve_tokens


class PDTokenString:
    """Resolve a token template against a context."""

    DISPLAY_NAME = display_name("PD Token String")
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("resolved",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "template": ("STRING", {
                    "default": settings.get("token_string.template"),
                    "multiline": True,
                }),
                "frame_padding": ("INT", {"default": settings.get("sequence.frame_padding"),
                                           "min": 1, "max": 8}),
            },
            "optional": {
                "context": ("PROJECT_CONTEXT",),
            },
        }

    def execute(self, template, frame_padding, context=None):
        return (resolve_tokens(template, dict(context or {}), frame_padding=frame_padding),)
