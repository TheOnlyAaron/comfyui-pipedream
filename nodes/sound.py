"""
PD Sound node.

Plays a short sound in the browser, either when this point of the flow is
reached or when the whole queue finishes (like the After Effects
render-complete chime).  Server side the node only passes its ``value``
input through unchanged and, in "node reached" mode, returns a ``ui``
payload so the frontend receives an ``executed`` event for this node.
All audio is handled by ``web/pd_sound.js``.
"""

from ..core import settings
from ..core.common import ANY, PLAY_WHEN, SOUNDS, display_name


class PDSound:
    """Inline or standalone browser sound cue.

    Inline, wire anything through ``value``; the output is the same object,
    untouched.  In "node reached" mode the sound plays when this node
    executes, so several nodes can mark progress through one graph, each
    with its own sound.  In "queue finished" mode it plays once the queue
    drains.  A node with nothing connected has no place in the flow, so the
    frontend treats it as "queue finished" either way.

    The node is an ``OUTPUT_NODE`` so it still runs when left dangling.  It
    never forces re-execution: when its inputs are cached it does not run,
    and only plays if ``when_cached`` is on (handled by the frontend from
    the ``execution_cached`` event).
    """

    DISPLAY_NAME = display_name("PD Sound")
    DESCRIPTION = (
        "Plays a sound in the browser when this node is reached or when the "
        "queue finishes. Passes its input through unchanged, so it can sit "
        "inline or dangle at the end."
    )
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    RETURN_TYPES = (ANY,)
    RETURN_NAMES = ("value",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "enabled": ("BOOLEAN", {"default": True}),
                "play_when": (PLAY_WHEN, {"default": settings.get("sound.play_when")}),
                "sound": (SOUNDS, {"default": settings.get("sound.sound")}),
                "volume": ("FLOAT", {
                    "default": settings.get("sound.volume"), "min": 0.0, "max": 1.0, "step": 0.05,
                }),
                "custom_url": ("STRING", {"default": ""}),
                "when_cached": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "node reached: also play when this node is "
                               "skipped because its result is cached.",
                }),
                "error_tone": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "value": (ANY,),
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, input_types):
        """Accept any connected type; taking ``input_types`` skips type checks."""
        return True

    def execute(self, enabled, play_when, sound, volume, custom_url,
                when_cached, error_tone, value=None):
        """Pass ``value`` through; in "node reached" mode, also send a ui cue.

        Returns:
            ``{"result": (value,)}`` plus, when enabled in "node reached"
            mode, ``"ui": {"pd_sound": [settings]}``, which ComfyUI sends to
            the queuing tab as an ``executed`` event for this node.
        """
        out = {"result": (value,)}
        if enabled and play_when == "node reached":
            out["ui"] = {"pd_sound": [{
                "sound": sound,
                "volume": float(volume),
                "custom_url": custom_url,
                "when_cached": bool(when_cached),
                "error_tone": bool(error_tone),
            }]}
        return out
