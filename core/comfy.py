"""
ComfyUI integration shared by the node modules: its input, output and temp
folders, the server routes, and showing a file in the OS file manager.

Everything degrades gracefully outside ComfyUI (tests, scripts): folders
fall back to the working directory and ``server_routes`` returns
``(None, None)``.
"""

import os
import subprocess
import sys

try:
    import folder_paths  # type: ignore[import-not-found]
except ImportError:
    folder_paths = None


def output_directory() -> str:
    """ComfyUI's output folder (``./output`` outside ComfyUI)."""
    if folder_paths is not None:
        return folder_paths.get_output_directory()
    return os.path.join(os.getcwd(), "output")


def input_directory() -> str:
    """ComfyUI's input folder (``./input`` outside ComfyUI)."""
    if folder_paths is not None:
        return folder_paths.get_input_directory()
    return os.path.join(os.getcwd(), "input")


def temp_directory() -> str | None:
    """ComfyUI's temp folder, or None outside ComfyUI (previews are skipped)."""
    if folder_paths is not None:
        return folder_paths.get_temp_directory()
    return None


def server_routes():
    """
    ``(routes, web)``: the ComfyUI server's aiohttp route table and the
    ``aiohttp.web`` module, or ``(None, None)`` when the server is not
    running (e.g. when a module is imported by tests).
    """
    try:
        from aiohttp import web
        from server import PromptServer
    except ImportError:
        return None, None
    instance = getattr(PromptServer, "instance", None)
    if instance is None:
        return None, None
    return instance.routes, web


_LOOPBACK = ("127.0.0.1", "::1", "localhost")


def reveal_in_file_manager(path: str, remote: str | None = None, select: bool = True) -> dict:
    """
    Show *path* in the file manager of the machine running ComfyUI.

    A file is selected in its folder (Explorer, Finder); on Linux, or
    without *select*, its folder opens.  When the file is gone, the nearest existing parent
    folder opens.  Requests from another machine (``--listen``) are
    refused: the window would open on the server, not for the viewer.
    Returns ``{"opened": path}`` or ``{"error": message}``.
    """
    if remote and remote not in _LOOPBACK:
        return {"error": "Explore only works in a browser on the ComfyUI machine."}
    target = os.path.normpath(path) if path else ""
    while target and not os.path.exists(target):
        parent = os.path.dirname(target)
        if parent == target:
            target = ""
            break
        target = parent
    if not target:
        return {"error": f"Neither '{path}' nor any parent folder exists."}
    if not select and os.path.isfile(target):
        target = os.path.dirname(target)
    is_file = os.path.isfile(target)
    if sys.platform == "win32":
        command = f'explorer /select,"{target}"' if is_file else f'explorer "{target}"'
        subprocess.Popen(command)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", target] if is_file else ["open", target])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(target) if is_file else target])
    return {"opened": target}
