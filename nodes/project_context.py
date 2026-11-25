"""
PD Project Context node.

Top-level metadata node that acts as the root token source for a workflow.
Other Pipedream nodes that accept tokens can receive a PROJECT_CONTEXT input
from this node.

Supports override chaining: an incoming PROJECT_CONTEXT provides base values,
and any non-empty widget on this node overrides those values.  The context
also comes out as EXR metadata (one string attribute per token, see
``core/exr_meta.py``) for PD Output.

Version auto-increment and the version reset buttons live entirely in the
frontend (``web/pd_version.js``).  The ``auto_increment_version`` widget is
read there at queue time, like seed's ``control_after_generate``, so each
queued prompt carries its own version.  This node only passes the value on.
"""

from ..core import settings
from ..core.common import display_name
from ..core.exr_meta import ExrMetadata


class PDProjectContext:
    """Emit a PROJECT_CONTEXT dict from project-level metadata widgets."""

    DISPLAY_NAME = display_name("PD Project Context")
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    RETURN_TYPES = ("PROJECT_CONTEXT", "EXR_METADATA")
    RETURN_NAMES = ("context", "exr_metadata")
    OUTPUT_TOOLTIPS = (
        "The tokens, for PD Output, PD Load and the other context inputs.",
        "Every token of the context as an EXR string attribute named after the "
        "exr.metadata_prefix setting (pipedream/shot...), for PD Output's exr_metadata. "
        "Empty values are left out.",
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "project": ("STRING", {"default": ""}),
                "sequence": ("STRING", {"default": ""}),
                "shot": ("STRING", {"default": ""}),
                "version": ("STRING", {"default": settings.get("project.version")}),
            },
            "optional": {
                "context": ("PROJECT_CONTEXT",),
                "user": ("STRING", {"default": ""}),
                "auto_increment_version": ("BOOLEAN", {
                    "default": settings.get("project.auto_increment_version"),
                }),
            },
        }

    def execute(self, project, sequence, shot, version, context=None,
                user="", auto_increment_version=False):
        """Merge widget values over the incoming context and return it.

        ``auto_increment_version`` is only read by the frontend.
        """
        # Start from incoming context or empty dict
        ctx = dict(context) if context else {}

        # Widget values override incoming context only when non-empty
        for key, val in [("project", project), ("sequence", sequence),
                         ("shot", shot), ("version", version),
                         ("user", user)]:
            if val:
                ctx[key] = val
            elif key not in ctx:
                ctx[key] = val

        return (ctx, ExrMetadata.from_tokens(ctx, settings.get("exr.metadata_prefix")))
