"""
ComfyUI-Pipedream — production pipeline utility nodes.

Structured output naming and writing, shot metadata, video utilities,
sound cues, wedge iteration and input switching for VFX/animation
workflows.  Nodes are classic ComfyUI node classes with a ``DISPLAY_NAME``
attribute, registered through ``NODE_CLASS_MAPPINGS``.
"""

__version__ = "0.2.0"

from .nodes import ALL_NODES

NODE_CLASS_MAPPINGS = {cls.__name__: cls for cls in ALL_NODES}
NODE_DISPLAY_NAME_MAPPINGS = {cls.__name__: cls.DISPLAY_NAME for cls in ALL_NODES}

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
