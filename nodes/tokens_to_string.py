"""
PD Tokens To String node.

Resolves a token template to a plain string, e.g. for prompts, filenames
or other nodes' path widgets.  Tokens come from an optional
PROJECT_CONTEXT (PD Project Context / PD Custom Context) plus the
automatic ``{date}``, ``{time}`` and ``{frame}`` tokens.  The default
template and frame padding come from the settings (``core/settings.py``).

It is an output node, so its "preview" button (``web/pipedream.js``) can
run just it and its inputs; the resolved text shows in the node's panel
after every run.
"""

from ..core import settings
from ..core.common import display_name
from ..core.tokens import resolve_tokens


class PDTokensToString:
    """Resolve a token template against a context."""

    DISPLAY_NAME = display_name("PD Tokens To String")
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("resolved",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "template": ("STRING", {
                    "default": settings.get("tokens_to_string.template"),
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
        resolved = resolve_tokens(template, dict(context or {}), frame_padding=frame_padding)
        return {"ui": {"resolved_text": [resolved]}, "result": (resolved,)}
