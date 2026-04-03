"""
PD Project Context node.

Top-level metadata node that acts as the root token source for a workflow.
Other Pipedream nodes that accept tokens can receive a PROJECT_CONTEXT input
from this node.

Supports override chaining: an incoming PROJECT_CONTEXT provides base values,
and any non-empty widget on this node overrides those values.  Also supports
auto-incrementing the version string (persistent via widget state, like seed).
"""

import re

from ..core.display import display_name


class PDProjectContext:
    """Emit a PROJECT_CONTEXT dict from project-level metadata widgets."""

    DISPLAY_NAME = display_name("PD Project Context")
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    OUTPUT_NODE = True
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
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    def execute(self, project, sequence, shot, version, context=None,
                artist="", auto_increment_version=False, unique_id=None):
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

        # Auto-increment: use the current version, return next for the widget
        ui_update = {}
        if auto_increment_version:
            current = ctx.get("version", "v001")
            next_ver = self._increment_version(current)
            ui_update["version"] = [next_ver]

        if ui_update:
            return {"ui": ui_update, "result": (ctx,)}
        return (ctx,)

    @staticmethod
    def _increment_version(version: str) -> str:
        """Increment a version string like 'v001' → 'v002'."""
        match = re.match(r"^([a-zA-Z]*)(\d+)$", version)
        if match:
            prefix = match.group(1)
            num = int(match.group(2))
            width = len(match.group(2))
            return f"{prefix}{num + 1:0{width}d}"
        return version
