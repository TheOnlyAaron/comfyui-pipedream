"""
PD First Last Frame node.

Extracts the first and last frames from an image batch or video sequence.
Useful for first/last frame workflows when converting reference footage
to re-styled output.
"""

from ..core.display import display_name


class PDFirstLastFrame:
    """Extract first and last frames from an image batch or video."""

    DISPLAY_NAME = display_name("PD First Last Frame")
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "IMAGE", "INT")
    RETURN_NAMES = ("first_frame", "last_frame", "total_frames")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
            },
        }

    def execute(self, images):
        total = images.shape[0]
        first = images[0].unsqueeze(0)
        last = images[-1].unsqueeze(0)
        return (first, last, total)
