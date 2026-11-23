"""
Path building shared by PD Output and PD Load.

``FRAME_MARK`` stands in for ``{frame}`` while a template is resolved; the
writer replaces it per frame and the loader turns it into a frame-number
pattern.  ``resolve_root`` picks the folder a template is resolved under
and ``check_inside`` keeps relative paths inside ComfyUI's folders.
"""

import os
import re

FRAME_MARK = "@@PDFRAME@@"
_FRAME_WITH_SEP = re.compile(r"[._-]?" + re.escape(FRAME_MARK))


def strip_frame(text: str) -> str:
    """Remove the frame mark from *text*, with one separator before it."""
    return _FRAME_WITH_SEP.sub("", text)


def resolve_root(path_mode: str, base_path: str, relative_root: str, node: str) -> str:
    """
    The folder to resolve under: *relative_root* (a ComfyUI folder) in
    ``relative`` mode, else *base_path*.  Raises ValueError naming *node*
    when absolute mode has no base_path.
    """
    if path_mode == "relative":
        return relative_root
    base_path = (base_path or "").strip()
    if not base_path:
        raise ValueError(f"[Pipedream] {node} absolute mode needs a base_path "
                         "(e.g. /mnt/projects or \\\\server\\share).")
    return base_path


def check_inside(path: str, root: str, node: str, folder: str) -> None:
    """Raise ValueError if *path* is outside *root* (ComfyUI's *folder* folder)."""
    inside = os.path.abspath(root)
    try:
        ok = os.path.commonpath([os.path.abspath(path), inside]) == inside
    except ValueError:  # different drives on Windows
        ok = False
    if not ok:
        raise ValueError(f"[Pipedream] {node}: '{strip_frame(path)}' is outside ComfyUI's "
                         f"{folder} folder. Use absolute path mode for other locations.")
