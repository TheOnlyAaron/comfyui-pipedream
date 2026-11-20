"""
PD Render Complete Sound node.

Plays a chime in the browser when the ComfyUI queue finishes, like the
After Effects render-complete chime.  The node does nothing server-side;
its presence in a queued prompt arms the chime in the tab that queued it,
and ``web/pd_sound.js`` plays the sound once the queue drains.
"""

from ..core.display import display_name


SOUNDS = ["chime", "bell", "ding", "custom URL"]


class PDRenderCompleteSound:
    """Browser-side render-complete chime, armed by being in the graph.

    Works standalone with no connections.  The optional ``trigger`` input
    accepts anything, so the node can be tied to a branch if desired.
    """

    DISPLAY_NAME = display_name("PD Render Complete Sound")
    DESCRIPTION = (
        "Plays a chime in the browser when the queue finishes. "
        "No connections required."
    )
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    RETURN_TYPES = ()

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "enabled": ("BOOLEAN", {"default": True}),
                "volume": ("FLOAT", {
                    "default": 0.6, "min": 0.0, "max": 1.0, "step": 0.05,
                }),
                "sound": (SOUNDS,),
                "custom_url": ("STRING", {"default": ""}),
                "error_tone": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "trigger": ("*",),
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    def execute(self, enabled, volume, sound, custom_url, error_tone, trigger=None):
        """No-op; the sound is played by the frontend extension."""
        return ()
