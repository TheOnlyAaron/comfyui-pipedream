"""
PD Custom Context node.

Adds user-defined key/value pairs to a PROJECT_CONTEXT dict, enabling
arbitrary tokens like {task}, {department}, {element}, etc.
"""

from ..core.display import display_name


class PDCustomContext:
    """Add up to 5 custom named tokens to a context dict."""

    DISPLAY_NAME = display_name("PD Custom Context")
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    RETURN_TYPES = ("PROJECT_CONTEXT",)
    RETURN_NAMES = ("context",)

    @classmethod
    def INPUT_TYPES(cls):
        required = {}
        for i in range(1, 6):
            required[f"custom_{i}_name"] = ("STRING", {"default": ""})
            required[f"custom_{i}_value"] = ("STRING", {"default": ""})

        return {
            "required": required,
            "optional": {
                "context": ("PROJECT_CONTEXT",),
            },
        }

    def execute(self, context=None, **kwargs):
        ctx = dict(context) if context else {}

        for i in range(1, 6):
            name = kwargs.get(f"custom_{i}_name", "")
            value = kwargs.get(f"custom_{i}_value", "")
            if name:
                ctx[name] = value

        return (ctx,)
