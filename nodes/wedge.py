"""
PD Wedge node.

Turns several near-identical runs of a graph into one graph: each row is
an input (any type) paired with a text value, and each queued job selects
one row.  The selected input comes out of ``value``; the row's text is
the wedge token's value for PD Output, and also comes out as ``text``,
``int`` and ``float``.  An unlinked row's value is its text, so prompts,
seeds or numbers can be wedged by typing them in.

Inputs are lazy: only the selected row's branch is computed, and ComfyUI's
cache keeps the rest of the graph between jobs.

Wedges chain through ``wedge``: the upstream wedge is the first axis and
varies fastest.  Wedges sharing a ``group`` step together instead of
multiplying.  Row and job selection, and the WEDGE value, are described in
``core/wedge.py``; the rows are shown and hidden by ``web/pd_wedge.js``.
"""

from ..core.common import ANY, display_name
from ..core.wedge import (
    INPUT_PREFIX,
    MAX_ROWS,
    VALUE_PREFIX,
    WedgeError,
    active_rows,
    chain_axes,
    check_token,
    job_state,
    row_text,
    to_float,
    to_int,
)


class PDWedge:
    """Emit one row (input and text value) per queued job."""

    DISPLAY_NAME = display_name("PD Wedge")
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    RETURN_TYPES = (ANY, "STRING", "INT", "FLOAT", "WEDGE")
    RETURN_NAMES = ("value", "text", "int", "float", "wedge")
    OUTPUT_TOOLTIPS = (
        "The selected row's input, or its text when nothing is linked.",
        "The selected row's text (the token value).",
        "The selected row's text as an integer (2.7 gives 2; 0 if not a number).",
        "The selected row's text as a float (0.0 if not a number).",
        "This wedge and the wedges chained before it, for the next wedge or PD Output.",
    )

    @classmethod
    def INPUT_TYPES(cls):
        rows = {}
        for n in range(1, MAX_ROWS + 1):
            rows[f"{INPUT_PREFIX}{n}"] = (ANY, {
                "lazy": True,
                "tooltip": "Anything: image, prompt, model, video... Only the "
                           "selected row is computed.",
            })
        for n in range(1, MAX_ROWS + 1):
            rows[f"{VALUE_PREFIX}{n}"] = ("STRING", {
                "default": "",
                "tooltip": f"Token value for row {n}. With nothing linked to "
                           f"{INPUT_PREFIX}{n}, also the row's value.",
            })
        return {
            "required": {
                "token": ("STRING", {
                    "default": "wedge",
                    "tooltip": "Token name for PD Output, e.g. product gives "
                               "{product} and {product_idx}.",
                }),
            },
            "optional": {
                "group": ("STRING", {
                    "default": "",
                    "tooltip": "Wedges with the same group step together (row 1 with "
                               "row 1...) instead of multiplying. Empty: multiply.",
                }),
                "wedge": ("WEDGE", {
                    "tooltip": "Previous wedge in the chain. It varies faster than this one.",
                }),
                **rows,
            },
            "hidden": {"prompt": "PROMPT", "unique_id": "UNIQUE_ID"},
        }

    @classmethod
    def VALIDATE_INPUTS(cls, input_types):
        """Accept any connected type; taking ``input_types`` skips type checks."""
        return True

    @staticmethod
    def _selection(prompt, unique_id):
        inputs = (prompt or {}).get(str(unique_id), {}).get("inputs", {})
        rows = active_rows(inputs)
        position, job, total = job_state(inputs)
        if not rows:
            raise WedgeError("PD Wedge has no rows: link an input or type a value.")
        if position >= len(rows):
            raise WedgeError(
                f"PD Wedge row {position} was queued but the node has {len(rows)} rows."
            )
        return rows, position, job, total

    def check_lazy_status(self, token, prompt=None, unique_id=None, **kwargs):
        rows, position, _, _ = self._selection(prompt, unique_id)
        row = rows[position]
        name = f"{INPUT_PREFIX}{row['row']}"
        if row["linked"] and kwargs.get(name) is None:
            return [name]
        return []

    def execute(self, token, group="", wedge=None, prompt=None, unique_id=None, **kwargs):
        token = check_token(token)
        rows, position, job, total = self._selection(prompt, unique_id)

        texts = []
        for row in rows:
            runtime = kwargs.get(f"{VALUE_PREFIX}{row['row']}")
            if isinstance(runtime, str) and runtime.strip():
                texts.append(runtime.strip())
            else:
                texts.append(row_text(row))

        row = rows[position]
        text = texts[position]
        value = kwargs.get(f"{INPUT_PREFIX}{row['row']}") if row["linked"] else text

        axis = {"token": token, "group": (group or "").strip(), "rows": texts, "row": position}
        out = {"axes": chain_axes(wedge, axis), "job": job, "total": total}
        return (value, text, to_int(text), to_float(text), out)
