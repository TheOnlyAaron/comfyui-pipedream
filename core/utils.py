"""
Shared utility helpers for Pipedream nodes.

Path normalization, directory creation, image saving, and other small
helpers that multiple node modules rely on.
"""

import os
import sys


def normalize_path(path: str) -> str:
    """
    Normalize slashes for the current platform.

    On Windows, forward slashes become backslashes and UNC prefixes
    (``\\\\server\\share``) are preserved.  On POSIX, backslashes become
    forward slashes.  Trailing separators are stripped.
    """
    if sys.platform == "win32":
        path = path.replace("/", "\\")
    else:
        path = path.replace("\\", "/")
    return path.rstrip(os.sep)


def ensure_directory(path: str, create: bool = True) -> str:
    """
    Return the directory portion of *path*, optionally creating it.

    Raises ``OSError`` with a descriptive message on failure.
    """
    directory = os.path.dirname(path)
    if not directory:
        return directory
    if create and not os.path.isdir(directory):
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as exc:
            raise OSError(
                f"[Pipedream] Failed to create directory '{directory}': {exc}"
            ) from exc
    return directory


def save_image_batch(images, full_path: str, overwrite: bool = False) -> list[str]:
    """
    Save a batch of ComfyUI IMAGE tensors to disk.

    *images* is a tensor of shape ``(B, H, W, C)`` with float32 values in
    ``[0, 1]``.  When the batch size is greater than one, a zero-padded
    index is appended before the extension (e.g. ``name_0001.png``).

    Returns a list of successfully written file paths.
    """
    import numpy as np
    from PIL import Image

    ext = os.path.splitext(full_path)[1].lower()
    batch_size = images.shape[0]
    written: list[str] = []

    for i in range(batch_size):
        if batch_size > 1:
            base, extension = os.path.splitext(full_path)
            out_path = f"{base}_{i:04d}{extension}"
        else:
            out_path = full_path

        if not overwrite and os.path.exists(out_path):
            print(
                f"[Pipedream] Error: file already exists and overwrite is "
                f"disabled: '{out_path}'",
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
            written.append(out_path)
        except Exception as exc:
            print(
                f"[Pipedream] Error: failed to write '{out_path}': {exc}",
                file=sys.stderr,
            )

    return written
