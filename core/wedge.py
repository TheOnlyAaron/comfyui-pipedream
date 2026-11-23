"""
Wedge rows, values and queue expansion, shared by the PD Wedge node and
its server route.  No ComfyUI dependency.

A PD Wedge node has up to ``MAX_ROWS`` rows.  Row *n* is an optional
input socket ``input_n`` (any type) paired with a text widget
``value_n``.  A row is *active* when its socket is linked or its text is
not empty; empty rows are skipped, so the active rows are numbered by
position (0, 1, 2, ...) and that position is what a queued job selects.

The row's text is the wedge token's value.  With nothing linked, the text
is also the row's value; a linked row with empty text gets its row number
as text, so file names stay unique.

One queued prompt becomes one job per combination of rows (``plan``,
``jobs``, ``apply_job``).  The job a node runs is set in the prompt as plain
inputs on the node (``ROW_KEY``, ``JOB_KEY``, ``TOTAL_KEY``).  ComfyUI
drops prompt inputs a node does not declare, so the node reads them from
the hidden ``PROMPT``; they still change the node's cache signature, so a
new row re-executes the wedge and everything downstream of it.

The ``WEDGE`` value passed down a chain of wedges (and on to PD Output)
is a dict::

    {"axes": [{"token": "product", "group": "", "rows": ["red", "blue"],
               "row": 1, "solo": False}, ...],
     "job": 3, "total": 6}

``axes`` lists the chained wedges, upstream first; ``solo`` marks a wedge
pinned to one row.

A preview run sets ``PREVIEW_KEY`` on the wedges: they then compute none of
their row inputs (``value`` is None) and PD Output lists the paths of every
job from the chain (``chain_jobs``) instead of writing.
"""

import re

CLASS_TYPE = "PDWedge"
MAX_ROWS = 16
INPUT_PREFIX = "input_"
VALUE_PREFIX = "value_"

PREVIEW_KEY = "pd_wedge_preview"
ROW_KEY = "pd_wedge_row"
JOB_KEY = "pd_wedge_job"
TOTAL_KEY = "pd_wedge_total"

INDEX_DIGITS = 3
RESERVED_TOKENS = frozenset({"frame", "wedge_idx", "wedge_total"})
_TOKEN_NAME = re.compile(r"^\w+$")


class WedgeError(ValueError):
    """A wedge setup that cannot run (no rows, bad token, mismatched group...).

    ``node_id`` and ``input_name`` name the wedge and widget at fault when
    known, so the frontend can mark them.
    """

    def __init__(self, message: str, node_id: str | None = None, input_name: str = "token"):
        super().__init__(message)
        self.node_id = node_id
        self.input_name = input_name


def is_link(value) -> bool:
    """True for a prompt link (``[node_id, output_index]``)."""
    return (isinstance(value, (list, tuple)) and len(value) == 2
            and isinstance(value[1], int) and not isinstance(value[1], bool))


def active_rows(inputs: dict) -> list[dict]:
    """
    Return the active rows of a PD Wedge node's prompt *inputs*, in order.

    Each row is ``{"row": n, "linked": bool, "text": str}`` where *n* is the
    1-based row number shown on the node.  A linked value widget (text fed
    from another node) counts as active; its text is only known at run
    time, so it is reported as empty here.
    """
    rows = []
    for n in range(1, MAX_ROWS + 1):
        linked = is_link(inputs.get(f"{INPUT_PREFIX}{n}"))
        value = inputs.get(f"{VALUE_PREFIX}{n}")
        value_linked = is_link(value)
        text = "" if value_linked or value is None else str(value).strip()
        if linked or value_linked or text:
            rows.append({"row": n, "linked": linked, "text": text})
    return rows


def row_text(row: dict) -> str:
    """The token value of an active row (its text, or its row number)."""
    return row["text"] or str(row["row"])


def check_token(token: str) -> str:
    """Return *token* stripped, or raise WedgeError if it is not a usable name."""
    token = (token or "").strip()
    if not _TOKEN_NAME.match(token):
        raise WedgeError(
            f"PD Wedge token '{token}' must be letters, digits and underscores "
            "(it is used as a file name token)."
        )
    if token in RESERVED_TOKENS:
        raise WedgeError(f"PD Wedge token '{token}' is reserved; pick another name.")
    return token


def to_int(text: str) -> int:
    """Parse *text* as an int ('2.7' gives 2); 0 when it is not a number."""
    try:
        return int(text)
    except ValueError:
        try:
            return int(float(text))
        except ValueError:
            return 0


def to_float(text: str) -> float:
    """Parse *text* as a float; 0.0 when it is not a number."""
    try:
        return float(text)
    except ValueError:
        return 0.0


def job_state(inputs: dict) -> tuple[int, int, int]:
    """Return ``(row, job, total)`` set on a node by the queue expansion.

    Without an expansion (a single run) this is row 0, job 0 of 1.
    """
    def _int(key, default):
        try:
            return int(inputs.get(key, default))
        except (TypeError, ValueError):
            return default

    return _int(ROW_KEY, 0), _int(JOB_KEY, 0), max(1, _int(TOTAL_KEY, 1))


def index_label(index: int) -> str:
    """Zero-padded index used by the ``{<token>_idx}`` and ``{wedge_idx}`` tokens."""
    return f"{index:0{INDEX_DIGITS}d}"


def chain_axes(upstream: dict | None, axis: dict) -> list[dict]:
    """Append *axis* to the axes of an upstream WEDGE, refusing duplicate tokens."""
    axes = list((upstream or {}).get("axes", []))
    if any(a["token"] == axis["token"] for a in axes):
        raise WedgeError(
            f"PD Wedge token '{axis['token']}' is used twice in the same chain; "
            "give each wedge its own token."
        )
    axes.append(axis)
    return axes


def wedge_tokens(wedge: dict | None) -> dict:
    """
    Return the file name tokens of a WEDGE value.

    Each axis gives ``{<token>}`` (its row's text) and ``{<token>_idx}``
    (the row position); ``{wedge_idx}`` is the job number and
    ``{wedge_total}`` the number of jobs.
    """
    if not wedge:
        return {}
    tokens = {}
    for axis in wedge.get("axes", []):
        tokens[axis["token"]] = axis["rows"][axis["row"]]
        tokens[f"{axis['token']}_idx"] = index_label(axis["row"])
    tokens["wedge_idx"] = index_label(wedge.get("job", 0))
    tokens["wedge_total"] = str(wedge.get("total", 1))
    return tokens


def wedge_metadata(wedge: dict | None) -> dict | None:
    """Sidecar summary of a WEDGE value: job, total and each axis's row."""
    if not wedge:
        return None
    return {
        "job": wedge.get("job", 0),
        "total": wedge.get("total", 1),
        "axes": [
            {"token": a["token"], "group": a["group"], "row": a["row"],
             "value": a["rows"][a["row"]], "rows": len(a["rows"])}
            for a in wedge.get("axes", [])
        ],
    }

# ---------------------------------------------------------------------------
# Queue expansion: one prompt in, one job per combination of wedge rows out.
# ---------------------------------------------------------------------------

MAX_JOBS = 10000


def _id_key(node_id: str) -> tuple:
    """Sort key for prompt node ids ('7', '12', '5:3' inside subgraphs)."""
    return tuple((0, int(p)) if p.isdigit() else (1, p) for p in str(node_id).split(":"))


def ancestors(prompt: dict, roots) -> set:
    """Return *roots* and every node they read from, following prompt links."""
    seen, stack = set(), [str(r) for r in roots]
    while stack:
        node_id = stack.pop()
        if node_id in seen or node_id not in prompt:
            continue
        seen.add(node_id)
        for value in prompt[node_id].get("inputs", {}).values():
            if is_link(value):
                stack.append(str(value[0]))
    return seen


def _chain_depth(prompt: dict, node_id: str) -> int:
    """Number of wedges before *node_id* in its chain (via the ``wedge`` input)."""
    depth, seen = 0, {node_id}
    link = prompt[node_id]["inputs"].get("wedge")
    while is_link(link) and str(link[0]) not in seen:
        upstream = prompt.get(str(link[0]))
        if not upstream or upstream.get("class_type") != CLASS_TYPE:
            break
        depth += 1
        seen.add(str(link[0]))
        link = upstream["inputs"].get("wedge")
    return depth


def solo_position(rows: list[dict], solo) -> int | None:
    """Position of row number *solo* among the active *rows*; None when solo is off (0)."""
    try:
        solo = int(solo or 0)
    except (TypeError, ValueError):
        solo = 0
    if solo <= 0:
        return None
    for position, row in enumerate(rows):
        if row["row"] == solo:
            return position
    raise WedgeError(f"PD Wedge solo row {solo} is empty; pick a row in use or 0 for all rows.",
                     input_name="solo")


def build_axes(items: list[dict]) -> dict:
    """
    Group wedge *items* into axes and count the jobs.

    Each item is ``{"key", "token", "group", "rows", "pinned"}``: ``rows``
    is its row count and ``pinned`` the solo row position or None.  Items
    are already in axis order.  Ungrouped items are an axis each; items with
    the same group share one axis and must have the same row count.  An
    axis with a pinned member runs only that row (length 1).

    Returns ``{"axes": [{"group", "nodes", "tokens", "rows", "length",
    "pinned"}], "total"}``; ``nodes`` holds the item keys.
    """
    axes, by_group = [], {}
    for item in items:
        if item["rows"] == 0:
            raise WedgeError(
                f"PD Wedge '{item['token']}' has no rows: link an input or type a value.",
                item["key"], f"{VALUE_PREFIX}1")
        group = item["group"]
        axis = by_group.get(group) if group else None
        if axis is None:
            axis = {"group": group, "nodes": [], "tokens": [], "rows": item["rows"], "pinned": None}
            axes.append(axis)
            if group:
                by_group[group] = axis
        elif axis["rows"] != item["rows"]:
            raise WedgeError(
                f"PD Wedges in group '{group}' need the same number of rows: "
                f"{', '.join(axis['tokens'])} {axis['rows']}, '{item['token']}' {item['rows']}.",
                item["key"], "group")
        if item["pinned"] is not None and axis["pinned"] is None:
            axis["pinned"] = item["pinned"]
        axis["nodes"].append(item["key"])
        axis["tokens"].append(item["token"])

    total = 1
    for axis in axes:
        axis["length"] = 1 if axis["pinned"] is not None else axis["rows"]
        total *= axis["length"]
    if total > MAX_JOBS:
        raise WedgeError(f"The wedges make {total} jobs; the limit is {MAX_JOBS}.")
    return {"axes": axes, "total": total}


def plan(prompt: dict, output_ids) -> dict:
    """
    Work out the jobs for *prompt*.

    Only wedges that an output node in *output_ids* reads from count.  Axes
    are ordered by chain position (upstream first), then node id; the first
    axis varies fastest.  Grouping and solo are as in ``build_axes``, whose
    result this returns (``total`` is 1 and ``axes`` empty without wedges).
    Raises WedgeError for a wedge without rows, an empty solo row, a
    mismatched group or too many jobs.
    """
    used = ancestors(prompt, output_ids)
    wedges = sorted(
        (n for n in used if prompt[n].get("class_type") == CLASS_TYPE),
        key=lambda n: (_chain_depth(prompt, n), _id_key(n)),
    )
    items = []
    for node_id in wedges:
        inputs = prompt[node_id]["inputs"]
        rows = active_rows(inputs)
        group = inputs.get("group")
        try:
            pinned = solo_position(rows, inputs.get("solo"))
        except WedgeError as exc:
            exc.node_id = node_id
            raise
        items.append({
            "key": node_id,
            "token": str(inputs.get("token", "")).strip() or f"#{node_id}",
            "group": group.strip() if isinstance(group, str) else "",
            "rows": len(rows),
            "pinned": pinned,
        })
    return build_axes(items)


def jobs(wedge_plan: dict) -> list[dict]:
    """Return one ``{node_id: row}`` per job, the first axis varying fastest."""
    result = []
    for job in range(wedge_plan["total"]):
        rows, rest = {}, job
        for axis in wedge_plan["axes"]:
            if axis["pinned"] is not None:
                row = axis["pinned"]
            else:
                row = rest % axis["length"]
                rest //= axis["length"]
            for node_id in axis["nodes"]:
                rows[node_id] = row
        result.append(rows)
    return result


def chain_jobs(wedge: dict | None) -> list[dict]:
    """
    Return the file name tokens of every job of a WEDGE chain, in job order.

    Used by the preview: the chain's axes carry every row's text, so the
    tokens of all jobs can be listed from one run.  Without a wedge there
    is one job with no tokens.
    """
    if not wedge:
        return [{}]
    chain = wedge.get("axes", [])
    built = build_axes([
        {"key": i, "token": a["token"], "group": a.get("group", ""),
         "rows": len(a["rows"]), "pinned": a["row"] if a.get("solo") else None}
        for i, a in enumerate(chain)
    ])
    result = []
    for job, rows in enumerate(jobs(built)):
        axes = [{**a, "row": rows[i]} for i, a in enumerate(chain)]
        result.append(wedge_tokens({"axes": axes, "job": job, "total": built["total"]}))
    return result


def apply_job(prompt: dict, rows: dict, job: int, total: int) -> dict:
    """Return a copy of *prompt* with each wedge set to its row for *job*."""
    out = dict(prompt)
    for node_id, row in rows.items():
        node = dict(out[node_id])
        node["inputs"] = {**node["inputs"], ROW_KEY: row, JOB_KEY: job, TOTAL_KEY: total}
        out[node_id] = node
    return out
