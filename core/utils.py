"""
Shared utility helpers for Pipedream nodes.

Path normalization, directory creation, and other small helpers that
multiple node modules rely on.
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
