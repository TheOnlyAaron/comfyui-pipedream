"""
ComfyUI API compatibility shim.

Detects whether the V3 (Nodes 2.0) API is available and provides helpers
so that individual node files can be written once using the legacy class
pattern and automatically registered for whichever API is present.

Node authors write standard legacy-style classes (INPUT_TYPES classmethod,
RETURN_TYPES tuple, instance ``execute`` method, etc.) and add a
``DISPLAY_NAME`` class attribute.  The helpers here take care of the rest.
"""

import inspect

# ---------------------------------------------------------------------------
# V3 API detection
# ---------------------------------------------------------------------------

try:
    from comfy_api.latest import io  # type: ignore[import-not-found]

    V3_AVAILABLE = True
except Exception:
    V3_AVAILABLE = False
    io = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Type mapping  (legacy type string -> V3 io type)
# ---------------------------------------------------------------------------

_LEGACY_TO_V3: dict[str, object] = {}

if V3_AVAILABLE:
    _LEGACY_TO_V3 = {
        "IMAGE": io.Image,
        "LATENT": io.Latent,
        "STRING": io.String,
        "INT": io.Int,
        "FLOAT": io.Float,
        "BOOLEAN": io.Boolean,
    }


def _v3_type_for(legacy_type: str):
    """Return the V3 ``io`` type object for a legacy type string."""
    if legacy_type == "*":
        return io.AnyType if hasattr(io, "AnyType") else io.Custom("*")
    if legacy_type in _LEGACY_TO_V3:
        return _LEGACY_TO_V3[legacy_type]
    return io.Custom(legacy_type)


# ---------------------------------------------------------------------------
# V3 wrapper factory
# ---------------------------------------------------------------------------

def _build_v3_input(name: str, type_str: str, config: dict | None = None):
    """Create a V3 input descriptor from legacy INPUT_TYPES info."""
    v3_type = _v3_type_for(type_str)

    kwargs: dict = {}
    if config:
        for key in ("default", "min", "max", "step"):
            if key in config:
                kwargs[key] = config[key]
        if config.get("multiline"):
            kwargs["multiline"] = True

    return v3_type.Input(name, **kwargs)


def _build_v3_output(type_str: str, display_name: str | None = None):
    """Create a V3 output descriptor from a legacy RETURN_TYPES entry."""
    v3_type = _v3_type_for(type_str)
    kwargs = {}
    if display_name:
        kwargs["display_name"] = display_name
    return v3_type.Output(**kwargs)


def wrap_as_v3(legacy_cls):
    """
    Wrap a legacy-style node class as a V3 ``io.ComfyNode`` subclass.

    Returns a new class that delegates execution to an instance of
    *legacy_cls* while exposing the V3 schema interface.
    """
    if not V3_AVAILABLE:
        return legacy_cls

    input_spec = legacy_cls.INPUT_TYPES()
    func_name = getattr(legacy_cls, "FUNCTION", "execute")
    exec_method = getattr(legacy_cls, func_name)
    param_names = [
        p
        for p in inspect.signature(exec_method).parameters
        if p != "self"
    ]

    # Build V3 inputs
    v3_inputs = []
    for section in ("required", "optional"):
        for name, spec in input_spec.get(section, {}).items():
            if isinstance(spec, tuple) and len(spec) >= 1:
                type_str = spec[0]
                config = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else None
                # COMBO type — spec[0] is a list of strings
                if isinstance(type_str, (list, tuple)):
                    inp = io.Combo.Input(name, options=list(type_str))
                else:
                    inp = _build_v3_input(name, type_str, config)
                if section == "optional":
                    inp = inp.make_optional()
                v3_inputs.append(inp)

    # Build V3 outputs
    return_types = getattr(legacy_cls, "RETURN_TYPES", ())
    return_names = getattr(legacy_cls, "RETURN_NAMES", (None,) * len(return_types))
    v3_outputs = [
        _build_v3_output(rt, rn) for rt, rn in zip(return_types, return_names)
    ]

    # Capture in closure
    _legacy_cls = legacy_cls
    _param_names = param_names
    _func_name = func_name

    class V3Wrapper(io.ComfyNode):
        @classmethod
        def define_schema(cls):
            return io.Schema(
                node_id=_legacy_cls.__name__,
                display_name=getattr(_legacy_cls, "DISPLAY_NAME", _legacy_cls.__name__),
                category=getattr(_legacy_cls, "CATEGORY", "Pipedream"),
                description=getattr(_legacy_cls, "DESCRIPTION", ""),
                inputs=v3_inputs,
                outputs=v3_outputs,
                is_output_node=getattr(_legacy_cls, "OUTPUT_NODE", False),
            )

        @classmethod
        def execute(cls, **kwargs):
            instance = _legacy_cls()
            ordered = [kwargs.get(p) for p in _param_names]
            result = getattr(instance, _func_name)(*ordered)
            if isinstance(result, tuple):
                return io.NodeOutput(*result)
            return io.NodeOutput(result)

    V3Wrapper.__name__ = _legacy_cls.__name__ + "_V3"
    V3Wrapper.__qualname__ = V3Wrapper.__name__
    return V3Wrapper


# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------

def get_node_class_mappings(node_classes: list) -> dict:
    """Build ``NODE_CLASS_MAPPINGS`` dict from a list of legacy node classes."""
    return {cls.__name__: cls for cls in node_classes}


def get_display_name_mappings(node_classes: list) -> dict:
    """Build ``NODE_DISPLAY_NAME_MAPPINGS`` dict from a list of legacy node classes."""
    return {
        cls.__name__: getattr(cls, "DISPLAY_NAME", cls.__name__)
        for cls in node_classes
    }


def get_v3_nodes(node_classes: list) -> list:
    """
    Return a list of V3-wrapped node classes.

    Returns an empty list when the V3 API is not available.
    """
    if not V3_AVAILABLE:
        return []
    wrapped = []
    for cls in node_classes:
        try:
            wrapped.append(wrap_as_v3(cls))
        except Exception as exc:
            print(f"[Pipedream] Warning: failed to wrap {cls.__name__} for V3: {exc}")
    return wrapped
