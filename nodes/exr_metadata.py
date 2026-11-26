"""
PD EXR Metadata Get and PD EXR Metadata Merge nodes.

**Merge** combines up to 8 ``EXR_METADATA`` streams into one, frame by
frame, later inputs winning on the same name (the same rule as PD
Save's inputs), so a stream can be assembled once and sent to several
PD Saves or inspected.  A spare input appears as one is connected
(``web/pipedream.js``).

**Get**:

Shows an ``EXR_METADATA`` stream (from PD Load, a context node or PD
Profiler) on the node, one attribute per line with its type, marking the
names that vary by frame, and outputs one attribute's value by name as
text, int and float.  ``key`` matches a full name, or a unique last part
(``shot`` finds ``pipedream/shot``).  It is an output node, so its
**preview** button (``web/pipedream.js``) runs just it and its inputs.
"""

from ..core.common import display_name
from ..core.exr_meta import INPUT_NAMES, ExrMetadata
from ..core.wedge import to_float, to_int


def find_key(table: dict, key: str):
    """The attribute name for *key*: exact, else a unique ``.../key`` suffix; None otherwise."""
    key = (key or "").strip()
    if not key:
        return None
    if key in table:
        return key
    matches = [n for n in table if n.endswith("/" + key) or n.lower() == key.lower()]
    return matches[0] if len(matches) == 1 else None


class PDExrMetadataGet:
    """Show EXR metadata and output one attribute's value."""

    DISPLAY_NAME = display_name("PD EXR Metadata Get")
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING", "INT", "FLOAT", "STRING")
    RETURN_NAMES = ("value", "int", "float", "names")
    OUTPUT_TOOLTIPS = (
        "The value of 'key' as text (vectors in brackets, timecodes as HH:MM:SS:FF).",
        "The value as an integer (0 if not a number).",
        "The value as a float (0.0 if not a number).",
        "Every attribute name of the frame, one per line.",
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "exr_metadata": ("EXR_METADATA", {
                    "tooltip": "From PD Load, a context node's exr_metadata or PD Profiler.",
                }),
            },
            "optional": {
                "key": ("STRING", {
                    "default": "",
                    "tooltip": "Attribute to output: a full name (pipedream/shot, "
                               "worldToCamera) or a unique last part (shot).",
                }),
                "frame": ("INT", {
                    "default": 1, "min": 1, "max": 100000,
                    "tooltip": "Which frame's metadata (1 = the first loaded frame). Sources "
                               "with one table give it for every frame.",
                }),
                "filter": ("STRING", {
                    "default": "",
                    "tooltip": "Show only names containing this text (e.g. camera, "
                               "pipedream/profiler). The outputs are not filtered.",
                }),
            },
        }

    def execute(self, exr_metadata, key="", frame=1, filter=""):
        meta = exr_metadata if isinstance(exr_metadata, ExrMetadata) else ExrMetadata()
        index = max(0, int(frame or 1) - 1)
        table = meta.frame(index)
        name = find_key(table, key)
        value_text, as_int, as_float = "", 0, 0.0
        if name is not None:
            attr = table[name]
            value_text = attr.display()
            if isinstance(attr.value, (int, float)) and not isinstance(attr.value, bool):
                as_int, as_float = int(attr.value), float(attr.value)
            else:
                as_int, as_float = to_int(value_text), to_float(value_text)

        shown = meta
        if filter.strip():
            needle = filter.strip().lower()
            shown = ExrMetadata([{n: a for n, a in f.items() if needle in n.lower()}
                                 for f in meta.frames])
        lines = [shown.describe(index)]
        if filter.strip():
            lines[0] += f"\n(names containing '{filter.strip()}'; {len(table)} in all)"
        if (key or "").strip():
            lines.append("")
            lines.append(f"{key.strip()} -> {name} = {value_text}" if name
                         else f"'{key.strip()}' not found (or matches more than one name).")
        return {"ui": {"metadata_text": ["\n".join(lines)]},
                "result": (value_text, as_int, as_float, "\n".join(table))}


class PDExrMetadataMerge:
    """Combine EXR metadata streams frame by frame; later inputs win."""

    DISPLAY_NAME = display_name("PD EXR Metadata Merge")
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    RETURN_TYPES = ("EXR_METADATA",)
    RETURN_NAMES = ("exr_metadata",)
    OUTPUT_TOOLTIPS = (
        "The inputs merged frame by frame: a source with one table per frame keeps them "
        "per frame, a single table applies to every frame, and later inputs win on the "
        "same name.",
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {name: ("EXR_METADATA", {
                "tooltip": "A metadata stream (PD Load, a context node, PD Profiler or "
                           "another merge). Later inputs win on the same name.",
            }) for name in INPUT_NAMES},
        }

    def execute(self, **inputs):
        return (ExrMetadata.merged(inputs.get(name) for name in INPUT_NAMES),)
