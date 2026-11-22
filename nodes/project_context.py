"""
PD Project Context node.

Top-level metadata node that acts as the root token source for a workflow.
Other Pipedream nodes that accept tokens can receive a PROJECT_CONTEXT input
from this node.

Supports override chaining: an incoming PROJECT_CONTEXT provides base values,
and any non-empty widget on this node overrides those values.

Version auto-increment and the version reset buttons live entirely in the
frontend (``web/pd_version.js``).  The ``auto_increment_version`` widget is
read there at queue time, like seed's ``control_after_generate``, so each
queued prompt carries its own version.  This node only passes the value on.
"""

from ..core.common import display_name


class PDProjectContext:
    """Emit a PROJECT_CONTEXT dict from project-level metadata widgets."""

    DISPLAY_NAME = display_name("PD Project Context")
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    RETURN_TYPES = ("PROJECT_CONTEXT",)
    RETURN_NAMES = ("context",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "project": ("STRING", {"default": ""}),
                "sequence": ("STRING", {"default": ""}),
                "shot": ("STRING", {"default": ""}),
                "version": ("STRING", {"default": "v001"}),
            },
            "optional": {
                "context": ("PROJECT_CONTEXT",),
                "artist": ("STRING", {"default": ""}),
                "auto_increment_version": ("BOOLEAN", {"default": False}),
            },
        }

    def execute(self, project, sequence, shot, version, context=None,
                artist="", auto_increment_version=False):
        """Merge widget values over the incoming context and return it.

        ``auto_increment_version`` is only read by the frontend.
        """
        # Start from incoming context or empty dict
        ctx = dict(context) if context else {}

        # Widget values override incoming context only when non-empty
        for key, val in [("project", project), ("sequence", sequence),
                         ("shot", shot), ("version", version),
                         ("artist", artist)]:
            if val:
                ctx[key] = val
            elif key not in ctx:
                ctx[key] = val

        return (ctx,)
