"""
PD Project Context node.

Top-level metadata node that acts as the root token source for a workflow.
Other Pipedream nodes that accept tokens can receive a PROJECT_CONTEXT input
from this node.
"""

from ..core.tokens import context_from_project


class PDProjectContext:
    """Emit a PROJECT_CONTEXT dict from project-level metadata widgets."""

    DISPLAY_NAME = "PD Project Context"
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
                "artist": ("STRING", {"default": ""}),
            },
        }

    def execute(self, project, sequence, shot, version, artist=""):
        ctx = context_from_project(
            project=project,
            sequence=sequence,
            shot=shot,
            version=version,
            artist=artist,
        )
        return (ctx,)
