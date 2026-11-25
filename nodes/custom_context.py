"""
PD Custom Context node.

Adds user-defined key/value pairs to a PROJECT_CONTEXT dict, enabling
arbitrary tokens like {task}, {department}, {element}, etc.  The context
also comes out as EXR metadata (one string attribute per token) for PD
Output, so these pairs are also how metadata is set.

Every pair is an optional input so any subset validates.  The JS extension
(``web/pd_custom_context.js``) starts with one empty pair and reveals the
next one as each name is filled, up to ``MAX_PAIRS``.
"""

from ..core import settings
from ..core.common import display_name
from ..core.exr_meta import ExrMetadata

MAX_PAIRS = 10


class PDCustomContext:
    """Add up to ``MAX_PAIRS`` custom named tokens to a context dict."""

    DISPLAY_NAME = display_name("PD Custom Context")
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    RETURN_TYPES = ("PROJECT_CONTEXT", "EXR_METADATA")
    RETURN_NAMES = ("context", "exr_metadata")
    OUTPUT_TOOLTIPS = (
        "The tokens, for PD Save, PD Load and the other context inputs.",
        "Every token of the context as an EXR string attribute named after the "
        "exr.metadata_prefix setting (pipedream/shot...), for PD Save's exr_metadata. "
        "Empty values are left out.",
    )

    @classmethod
    def INPUT_TYPES(cls):
        optional = {"context": ("PROJECT_CONTEXT",)}
        for i in range(1, MAX_PAIRS + 1):
            optional[f"custom_{i}_name"] = ("STRING", {"default": ""})
            optional[f"custom_{i}_value"] = ("STRING", {"default": ""})

        return {"required": {}, "optional": optional}

    def execute(self, context=None, **kwargs):
        """
        Return a copy of *context* with the custom pairs merged in.

        Pairs whose name is empty or missing are skipped; a missing value
        becomes an empty string.
        """
        ctx = dict(context) if context else {}

        for i in range(1, MAX_PAIRS + 1):
            name = kwargs.get(f"custom_{i}_name") or ""
            value = kwargs.get(f"custom_{i}_value")
            if name:
                ctx[name] = "" if value is None else value

        return (ctx, ExrMetadata.from_tokens(ctx, settings.get("exr.metadata_prefix")))
