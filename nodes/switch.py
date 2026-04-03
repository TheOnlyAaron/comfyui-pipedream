"""
PD Switch node.

Routes one of N wildcard inputs to a single output.  Input slots are
managed dynamically by the JS extension (auto-grow on connect, auto-shrink
on disconnect, min 2, max 8).
"""

from ..core.display import display_name


class PDSwitch:
    """Single-channel input switch with wildcard type support."""

    DISPLAY_NAME = display_name("PD Switch")
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("output",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["manual", "value"],),
                "select": ("INT", {"default": 0, "min": 0, "max": 7}),
            },
            "optional": {
                "index": ("INT", {
                    "default": 0, "min": 0, "max": 7, "forceInput": True,
                }),
                **{f"input_{i}": ("*",) for i in range(1, 9)},
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    def execute(self, mode, select, index=None, **kwargs):
        if mode == "value":
            idx = index if index is not None else 0
        else:
            idx = select

        idx = max(0, min(idx, 7))
        value = kwargs.get(f"input_{idx + 1}")
        return (value,)
