"""
ComfyUI node registration helpers.

Pipedream nodes are written once using the legacy class pattern
(``INPUT_TYPES`` classmethod, ``RETURN_TYPES`` tuple, instance ``execute``
method, etc.) plus a ``DISPLAY_NAME`` class attribute, and are registered
through ``NODE_CLASS_MAPPINGS``.

Current ComfyUI loads legacy nodes alongside V3 (``comfy_api.latest``)
nodes, so no V3 wrapper is used.  ComfyUI only calls ``comfy_entrypoint``
when a module has no ``NODE_CLASS_MAPPINGS``, so a V3 registration path
cannot sit next to the legacy one anyway.  If the pack moves to V3, the
nodes should be ported to ``io.ComfyNode`` directly rather than shimmed.
"""


def get_node_class_mappings(node_classes: list) -> dict:
    """Build ``NODE_CLASS_MAPPINGS`` dict from a list of legacy node classes."""
    return {cls.__name__: cls for cls in node_classes}


def get_display_name_mappings(node_classes: list) -> dict:
    """Build ``NODE_DISPLAY_NAME_MAPPINGS`` dict from a list of legacy node classes."""
    return {
        cls.__name__: getattr(cls, "DISPLAY_NAME", cls.__name__)
        for cls in node_classes
    }
