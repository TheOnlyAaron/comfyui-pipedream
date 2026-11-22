"""
PD Output Absolute node (legacy).

Deprecated in favour of PD Output with ``path_mode = absolute``.  Kept
registered so saved workflows still load; it shares PD Output's
implementation, so it also writes sidecar metadata, shows a preview and
has the same outputs (path, path_sidecar, path_all, images, video).
"""

from ..core.display import display_name
from .output import PDOutputBase, DEFAULT_TEMPLATE, EXR_INPUTS


class PDOutputAbsolute(PDOutputBase):
    """Save images to an absolute or network path using a token template (legacy)."""

    DISPLAY_NAME = display_name("PD Output Absolute (legacy)")
    DEPRECATED = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "base_path": ("STRING", {"default": ""}),
                "template": ("STRING", {"default": DEFAULT_TEMPLATE, "multiline": False}),
                "frame_padding": ("INT", {"default": 4, "min": 1, "max": 8}),
                "extension": (["png", "exr", "jpg", "webp"],),
            },
            "optional": {
                "context": ("PROJECT_CONTEXT",),
                "create_dirs": ("BOOLEAN", {"default": True}),
                "overwrite": ("BOOLEAN", {"default": False}),
                "save_metadata": ("BOOLEAN", {"default": True}),
                **EXR_INPUTS,
            },
            "hidden": {"prompt": "PROMPT"},
        }

    def execute(self, images, base_path, template, frame_padding, extension,
                context=None, create_dirs=True, overwrite=False,
                save_metadata=True, prompt=None, exr_precision="half",
                exr_compression="zip"):
        return self.write_outputs(
            images, "absolute", base_path, template, frame_padding, extension,
            context=context, create_dirs=create_dirs, overwrite=overwrite,
            save_metadata=save_metadata, prompt=prompt,
            exr_precision=exr_precision, exr_compression=exr_compression,
        )
