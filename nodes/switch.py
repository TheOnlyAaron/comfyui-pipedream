"""
PD Switch node.

Routes one of N inputs to output per channel.  Supports any ComfyUI type
(wildcard) and multiple independent channels per node instance.
"""


class PDSwitch:
    """Multi-channel input switch with wildcard type support."""

    DISPLAY_NAME = "PD Switch"
    CATEGORY = "Pipedream"
    FUNCTION = "execute"

    # Max 8 channels, each producing one output.  Unused slots pass None.
    RETURN_TYPES = ("*",) * 8
    RETURN_NAMES = tuple(f"ch{c}_out" for c in range(1, 9))

    @classmethod
    def INPUT_TYPES(cls):
        required = {
            "channels": ("INT", {"default": 1, "min": 1, "max": 8}),
            "inputs_per_channel": ("INT", {"default": 2, "min": 2, "max": 8}),
            "mode": (["manual", "value"],),
        }

        optional = {}

        # Per-channel manual selector widget
        for c in range(1, 9):
            optional[f"ch{c}_select"] = ("INT", {
                "default": 0,
                "min": 0,
                "max": 7,
            })

        # Per-channel value-mode index input (driven by upstream INT)
        for c in range(1, 9):
            optional[f"ch{c}_index"] = ("INT", {
                "default": 0,
                "min": 0,
                "max": 7,
                "forceInput": True,
            })

        # Data inputs — wildcard type, 8 channels × 8 inputs each
        for c in range(1, 9):
            for i in range(1, 9):
                optional[f"ch{c}_in{i}"] = ("*",)

        return {"required": required, "optional": optional}

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    def execute(self, channels, inputs_per_channel, mode, **kwargs):
        outputs: list = []

        for c in range(1, channels + 1):
            # Determine selected index
            if mode == "value":
                idx = kwargs.get(f"ch{c}_index", 0) or 0
            else:
                idx = kwargs.get(f"ch{c}_select", 0) or 0

            idx = max(0, min(idx, inputs_per_channel - 1))

            # Retrieve the selected input (1-based input numbering)
            value = kwargs.get(f"ch{c}_in{idx + 1}")
            outputs.append(value)

        # Pad to 8 outputs
        while len(outputs) < 8:
            outputs.append(None)

        return tuple(outputs)
