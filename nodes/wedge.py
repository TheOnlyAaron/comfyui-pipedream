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
multiplying.  ``solo`` runs one row only (for a test render).  Row and
job selection, the preview and the WEDGE value are described in
``core/wedge.py``; the rows are shown and hidden by ``web/pd_wedge.js``.

The route ``POST /pipedream/wedge/plan`` takes ``{"prompt": {...}}`` (an
API prompt) and returns ``{"total", "axes", "jobs"}``, or ``{"error",
"node_id", "input_name"}`` with status 400.  The frontend calls it when queuing and queues one prompt
per job; it is also the starting point for headless submission.
"""

import sys

from ..core.comfy import server_routes
from ..core.common import ANY, display_name
from ..core.wedge import (
    INPUT_PREFIX,
    MAX_ROWS,
    PREVIEW_KEY,
    VALUE_PREFIX,
    WedgeError,
    active_rows,
    jobs,
    plan,
    chain_axes,
    check_token,
    job_state,
    row_text,
    solo_position,
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
                "solo": ("INT", {
                    "default": 0, "min": 0, "max": MAX_ROWS,
                    "tooltip": "Run only this row number, e.g. for a test render. "
                               "0: every row.",
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
        """Return ``(rows, position, job, total, solo, preview)`` for this run."""
        inputs = (prompt or {}).get(str(unique_id), {}).get("inputs", {})
        rows = active_rows(inputs)
        position, job, total = job_state(inputs)
        if not rows:
            raise WedgeError("PD Wedge has no rows: link an input or type a value.")
        pinned = solo_position(rows, inputs.get("solo"))
        if pinned is not None:
            position = pinned
        if position >= len(rows):
            raise WedgeError(
                f"PD Wedge row {position} was queued but the node has {len(rows)} rows."
            )
        return rows, position, job, total, pinned is not None, bool(inputs.get(PREVIEW_KEY))

    def check_lazy_status(self, token, prompt=None, unique_id=None, **kwargs):
        rows, position, _, _, _, preview = self._selection(prompt, unique_id)
        if preview:
            return []
        row = rows[position]
        name = f"{INPUT_PREFIX}{row['row']}"
        if row["linked"] and kwargs.get(name) is None:
            return [name]
        return []

    def execute(self, token, group="", solo=0, wedge=None, prompt=None, unique_id=None, **kwargs):
        token = check_token(token)
        rows, position, job, total, soloed, _ = self._selection(prompt, unique_id)

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

        axis = {"token": token, "group": (group or "").strip(), "rows": texts,
                "row": position, "solo": soloed}
        out = {"axes": chain_axes(wedge, axis), "job": job, "total": total}
        return (value, text, to_int(text), to_float(text), out)


def plan_prompt(prompt: dict, output_ids=None) -> dict:
    """
    Plan the jobs of an API *prompt*: ``{"total", "axes", "jobs"}``.

    Output nodes default to every node whose class sets ``OUTPUT_NODE``.
    Raises WedgeError when the wedges cannot run.
    """
    if output_ids is None:
        import nodes as comfy_nodes  # ComfyUI's node registry
        mappings = comfy_nodes.NODE_CLASS_MAPPINGS
        output_ids = [
            node_id for node_id, node in prompt.items()
            if getattr(mappings.get(node.get("class_type")), "OUTPUT_NODE", False) is True
        ]
    wedge_plan = plan(prompt, output_ids)
    return {**wedge_plan, "jobs": jobs(wedge_plan)}


routes, web = server_routes()
if routes is not None:
    @routes.post("/pipedream/wedge/plan")
    async def wedge_plan_route(request):
        try:
            body = await request.json()
            prompt = body.get("prompt") or {}
            result = plan_prompt(prompt, body.get("outputs") or None)
        except WedgeError as exc:
            return web.json_response({"error": str(exc), "node_id": exc.node_id,
                                      "input_name": exc.input_name}, status=400)
        except Exception as exc:  # malformed request
            print(f"[Pipedream] Error: wedge plan failed: {exc}", file=sys.stderr)
            return web.json_response({"error": f"Wedge plan failed: {exc}"}, status=400)
        return web.json_response(result)
