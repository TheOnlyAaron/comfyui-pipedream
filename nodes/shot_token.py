"""
PD Shot Token node.

Lightweight alternative to PD Project Context when you only need shot-level
tokens injected into a single string template.
"""

from ..core.tokens import resolve_tokens


class PDShotToken:
    """Resolve a token template using inline widget values."""

    DISPLAY_NAME = "PD Shot Token"
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("resolved",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "template": ("STRING", {
                    "default": "{project}_{shot}_{version}",
                    "multiline": True,
                }),
                "project": ("STRING", {"default": ""}),
                "shot": ("STRING", {"default": ""}),
                "version": ("STRING", {"default": "v001"}),
            },
            "optional": {
                "date": ("STRING", {"default": "auto"}),
                "time": ("STRING", {"default": "auto"}),
            },
        }

    def execute(self, template, project, shot, version, date="auto", time="auto"):
        ctx: dict = {
            "project": project,
            "shot": shot,
            "version": version,
        }
        # "auto" means let the token engine use live date/time
        if date != "auto":
            ctx["date"] = date
        if time != "auto":
            ctx["time"] = time

        resolved = resolve_tokens(template, ctx)
        return (resolved,)
