"""
PD Network Output node.

Writes image output to a local or UNC network path.  Wraps file-writing
logic with path normalization for Windows UNC paths.
"""

import os
import sys

import numpy as np
from PIL import Image

from ..core.utils import normalize_path, ensure_directory


class PDNetworkOutput:
    """Save images to a network or local path with directory creation."""

    DISPLAY_NAME = "PD Network Output"
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("written_path",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "path": ("STRING", {"default": "", "forceInput": True}),
            },
            "optional": {
                "base_path": ("STRING", {"default": ""}),
                "create_dirs": ("BOOLEAN", {"default": True}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
        }

    def execute(self, images, path, base_path="", create_dirs=True, overwrite=False):
        if base_path:
            full_path = os.path.join(base_path, path)
        else:
            full_path = path

        full_path = normalize_path(full_path)

        if create_dirs:
            ensure_directory(full_path, create=True)

        ext = os.path.splitext(full_path)[1].lower()

        # images is a batch tensor of shape (B, H, W, C) float32 0-1
        batch_size = images.shape[0]
        written_paths: list[str] = []

        for i in range(batch_size):
            if batch_size > 1:
                base, extension = os.path.splitext(full_path)
                out_path = f"{base}_{i:04d}{extension}"
            else:
                out_path = full_path

            if not overwrite and os.path.exists(out_path):
                print(
                    f"[Pipedream] Error: file already exists and overwrite is disabled: "
                    f"'{out_path}'",
                    file=sys.stderr,
                )
                continue

            img_array = (images[i].cpu().numpy() * 255).clip(0, 255).astype(np.uint8)
            img = Image.fromarray(img_array)

            save_kwargs: dict = {}
            if ext in (".jpg", ".jpeg"):
                save_kwargs["quality"] = 95
            elif ext == ".webp":
                save_kwargs["quality"] = 95

            try:
                img.save(out_path, **save_kwargs)
                written_paths.append(out_path)
            except Exception as exc:
                print(
                    f"[Pipedream] Error: failed to write '{out_path}': {exc}",
                    file=sys.stderr,
                )

        final = written_paths[0] if written_paths else full_path
        return (final,)
