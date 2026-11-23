"""
ComfyUI integration shared by the node modules: its input, output and temp
folders, and the server routes.

Everything degrades gracefully outside ComfyUI (tests, scripts): folders
fall back to the working directory and ``server_routes`` returns
``(None, None)``.
"""

import os

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
