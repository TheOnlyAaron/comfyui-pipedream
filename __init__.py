"""
ComfyUI-Pipedream — Production pipeline utility nodes.

Provides structured output naming, network path writing, shot metadata,
wedge iteration, and multi-input switching for VFX/animation workflows.
"""

__version__ = "0.2.0"

from .nodes import ALL_NODES, PDOutputNamer, PDNetworkOutput
from .core.compat import get_node_class_mappings, get_display_name_mappings, V3_AVAILABLE

# Legacy API registration (always available)
NODE_CLASS_MAPPINGS = get_node_class_mappings(ALL_NODES)
NODE_DISPLAY_NAME_MAPPINGS = get_display_name_mappings(ALL_NODES)

# Backward compatibility for saved workflows referencing old node names
NODE_CLASS_MAPPINGS["PDOutputNamer"] = PDOutputNamer
NODE_CLASS_MAPPINGS["PDNetworkOutput"] = PDNetworkOutput

# V3 API registration (when Nodes 2.0 is present)
if V3_AVAILABLE:
    from .core.compat import get_v3_nodes
    NODES = get_v3_nodes(ALL_NODES)

# JS extensions directory
WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
