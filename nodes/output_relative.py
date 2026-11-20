"""
PD Output Relative node (legacy).

Deprecated in favour of PD Output with ``path_mode = relative``.  Kept
registered so saved workflows still load; it shares PD Output's
implementation, so it also writes sidecar metadata, shows a preview and
passes the images through.
"""

from ..core.display import display_name
from .output import PDOutputBase, DEFAULT_TEMPLATE


class PDOutputRelative(PDOutputBase):
    """Save images to ComfyUI's output directory using a token template (legacy)."""

    DISPLAY_NAME = display_name("PD Output Relative (legacy)")
    DEPRECATED = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "template": ("STRING", {"default": DEFAULT_TEMPLATE, "multiline": False}),
                "frame_padding": ("INT", {"default": 4, "min": 1, "max": 8}),
                "extension": (["png", "exr", "jpg", "webp"],),
            },
            "optional": {
                "context": ("PROJECT_CONTEXT",),
                "create_dirs": ("BOOLEAN", {"default": True}),
                "overwrite": ("BOOLEAN", {"default": False}),
                "save_metadata": ("BOOLEAN", {"default": True}),
            },
            "hidden": {"prompt": "PROMPT"},
        }

    def execute(self, images, template, frame_padding, extension,
                context=None, create_dirs=True, overwrite=False,
                save_metadata=True, prompt=None):
        return self.write_outputs(
            images, "relative", "", template, frame_padding, extension,
            context=context, create_dirs=create_dirs, overwrite=overwrite,
            save_metadata=save_metadata, prompt=prompt,
        )
