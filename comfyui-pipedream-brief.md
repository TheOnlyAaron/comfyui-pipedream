# ComfyUI-Pipedream — Project Brief
**For:** Claude Code bootstrap session  
**Author:** Aaron Dabelow  
**Date:** 2026-04-02

---

## What This Is

A custom ComfyUI node pack for production pipeline use at a VFX/animation studio. The goal is non-glamorous, daily-driver utility: structured output naming, network path writing, shot metadata, iteration/wedging, and multi-input switching. It is not a visual effects node pack. It is plumbing.

The name is **Pipedream**. Repo will be `comfyui-pipedream`. Node class names use the `PD` prefix. All nodes appear under the `Pipedream` category in the ComfyUI node menu.

---

## Compatibility Requirements

- Must support **legacy ComfyUI node API** (current production installs)
- Must support **ComfyUI Nodes 2.0 API**
- A compatibility shim in `__init__.py` should detect which API is present and register accordingly — do not write things twice, abstract it cleanly
- Python 3.10+ target, no exotic dependencies, nothing that requires a separate model download

---

## Repository Structure

```
comfyui-pipedream/
│
├── __init__.py                  # Node registration, compat shim, version
├── pyproject.toml               # ComfyUI Registry / pip metadata
├── requirements.txt             # Minimal; likely empty or near-empty
├── README.md
├── CHANGELOG.md
├── LICENSE                      # MIT
│
├── nodes/
│   ├── __init__.py
│   ├── output_namer.py          # PD Output Namer
│   ├── network_output.py        # PD Network Output
│   ├── project_context.py       # PD Project Context
│   ├── shot_token.py            # PD Shot Token
│   ├── switch.py                # PD Switch (multi-input, multi-channel)
│   ├── wedge.py                 # PD Wedge (iteration list node)
│   └── rasterizer.py            # PD Rasterizer (wedge preview/inspector)
│
├── core/
│   ├── __init__.py
│   ├── compat.py                # Legacy vs Nodes 2.0 detection and shim
│   ├── tokens.py                # Token resolution engine ({shot}, {date}, etc.)
│   └── utils.py                 # Shared helpers (path normalization, etc.)
│
└── workflows/
    ├── README.md                # Explains workflow library, how to use
    ├── 01_basic_output_namer/
    │   ├── workflow.json
    │   └── README.md
    ├── 02_network_output/
    │   ├── workflow.json
    │   └── README.md
    ├── 03_project_context_tokens/
    │   ├── workflow.json
    │   └── README.md
    ├── 04_switch_node/
    │   ├── workflow.json
    │   └── README.md
    ├── 05_single_wedge/
    │   ├── workflow.json
    │   └── README.md
    ├── 06_multi_wedge_with_rasterizer/
    │   ├── workflow.json
    │   └── README.md
    └── 07_full_production_shot/
        ├── workflow.json
        └── README.md
```

---

## Node Specifications

### PD Project Context
**File:** `nodes/project_context.py`  
Top-level metadata node. Acts as the root token source for a workflow. Other PD nodes that accept tokens should accept a `PROJECT_CONTEXT` input.

Widgets:
- `project` (STRING) — e.g. `DITC_Ep01`
- `sequence` (STRING) — e.g. `sq010`
- `shot` (STRING) — e.g. `sh020`
- `version` (STRING) — e.g. `v001`
- `artist` (STRING) — optional, for metadata

Output: `PROJECT_CONTEXT` (custom type, passes dict internally)

---

### PD Shot Token
**File:** `nodes/shot_token.py`  
Lightweight alternative to Project Context when you only need shot-level tokens injected into a string. Accepts a raw string with `{tokens}` and resolves them.

Widgets:
- `template` (STRING, multiline) — e.g. `{project}_{shot}_{version}`
- `project`, `shot`, `version`, `date`, `time` (STRING widgets with defaults)

Output: `STRING` (resolved)

---

### PD Output Namer
**File:** `nodes/output_namer.py`  
Builds a structured output filename using tokens. Designed to feed into ComfyUI's built-in Save Image node or PD Network Output.

Inputs:
- `context` (PROJECT_CONTEXT, optional)
- `template` (STRING) — token pattern for filename

Widgets:
- `template` (STRING) — default: `{project}/{sequence}/{shot}/{shot}_{version}_{date}`
- `frame_padding` (INT, default 4)
- `extension` (COMBO: png, exr, jpg, mp4, webp)

Output: `STRING` (resolved path string), `STRING` (filename only)

Token reference (resolved by `core/tokens.py`):
```
{project}       from context or widget
{sequence}
{shot}
{version}
{date}          YYYYMMDD
{time}          HHMMSS
{frame}         #### (padded)
{wedge_idx}     current wedge iteration index (zero-padded)
{wedge_<name>}  named wedge current value
```

---

### PD Network Output
**File:** `nodes/network_output.py`  
Writes image/video output to a UNC network path. Wraps file-writing logic with path normalization for Windows UNC paths (`\\server\share\...`).

Inputs:
- `images` (IMAGE)
- `path` (STRING) — resolved path from PD Output Namer, or raw

Widgets:
- `base_path` (STRING) — root UNC or local path, e.g. `\\RENDER01\Output`
- `create_dirs` (BOOL, default True)
- `overwrite` (BOOL, default False)

Output: `STRING` (final written path)

Notes:
- On path failures, log clearly to console — do not silently fail
- Normalize forward/backslash on Windows

---

### PD Switch
**File:** `nodes/switch.py`  
Routes one of N inputs to output. Supports any ComfyUI type (wildcard). Multiple independent channels per node.

Design decisions:
- `channels` widget (INT, 1–8) controls how many independent A/B/C... switch banks exist in the node
- Each channel has N inputs (controlled by `inputs_per_channel`, INT, 2–8) and 1 output
- `mode` widget: `manual` (widget-driven index) or `value` (INT input pin drives selection)
- In `value` mode, an INT input pin per channel selects the active input

This requires dynamic input/output registration — use the `INPUT_TYPES` classmethod pattern with dynamic counts. Reference how rgthree or KJNodes handle variable input counts for implementation guidance.

Output: one output per channel, same type as inputs

---

### PD Wedge
**File:** `nodes/wedge.py`  
Holds a list of values to iterate over. When the workflow executes, it spawns one queue entry per value (or per cartesian product if multiple wedges are connected).

Widgets:
- `name` (STRING) — identifier used in `{wedge_<name>}` token, e.g. `prompt`, `seed`, `cfg`
- `type` (COMBO: STRING, INT, FLOAT)
- `values` (STRING, multiline) — one value per line
- `mode` (COMBO: `sequential`, `random`, `cartesian` with other wedges)

Output:
- `WEDGE` (custom type — passes wedge state dict)
- `current_value` (STRING/INT/FLOAT depending on type widget) — the value for this run
- `wedge_index` (INT) — current iteration index

Implementation note: On first execution, read all values, queue N-1 additional prompt API calls with injected `wedge_index` parameter. The node emits the current index's value. See Option B wedge architecture discussed in design phase.

---

### PD Rasterizer
**File:** `nodes/rasterizer.py`  
Dry-run inspection node. Connects to one or more PD Wedge nodes and an optional PD Output Namer. On a lightweight "preview execute" (not a full render), computes the full cartesian product of all connected wedges and displays the iteration table.

Inputs:
- `wedge_1` through `wedge_4` (WEDGE, all optional)
- `output_namer` (STRING, optional — resolved template to preview filenames)

Widget:
- `execute_preview` (BUTTON or trigger) — runs the inspection without queuing renders

Output display (in node UI):
```
Wedge: prompt        → 3 values
Wedge: seed          → 4 values
────────────────────────────────
Total iterations:    12

[Preview filename list if output_namer connected]
  DITC_Ep01/sq010/sh020/sh020_v001_w000_20260402.png
  DITC_Ep01/sq010/sh020/sh020_v001_w001_20260402.png
  ...
```

Output: `INT` (total iteration count), `STRING` (serialized preview table)

Note: The UI display portion requires a small JS extension (`web/pipedream_rasterizer.js`) to render the preview panel in the node body. Scaffold this but it can be minimal for v1 — even a textarea-style display is acceptable.

---

## core/compat.py — Compatibility Shim

This is the most important architectural piece. Detect API version at import time and expose a unified registration interface.

```python
"""
Detects ComfyUI API version (legacy vs Nodes 2.0) and provides
a normalized node registration helper so individual node files
don't need to branch on API version themselves.
"""
```

Key things to abstract:
- `INPUT_TYPES` classmethod signature differences
- `RETURN_TYPES` / `RETURN_NAMES` handling
- Execution method name (`__call__` vs `execute`)
- Any category/display name registration differences

Each node file imports from `core.compat` rather than importing ComfyUI internals directly.

---

## core/tokens.py — Token Engine

Standalone, no ComfyUI dependency. Resolves a token template string given a context dict.

```python
resolve_tokens(template: str, context: dict) -> str
```

- `context` is built from Project Context node values + wedge state + runtime values (date, time)
- Unknown tokens are left as-is with a console warning, not silently dropped
- Frame token `{frame}` resolves to `####` by default (for use in path patterns, not literal frames)
- Should be unit-testable independently

---

## Workflow Library

Each workflow lives in `workflows/NN_name/` with a `workflow.json` and a `README.md`.

The `workflows/README.md` at the root explains:
- How to load workflows (drag into ComfyUI, or File > Load)
- That all workflows require Pipedream nodes installed
- Progression order (01 → 07 is intentional learning path)

### Workflow Progression

| # | Name | Teaches |
|---|------|---------|
| 01 | `basic_output_namer` | How to wire PD Output Namer with default tokens, feed into Save Image |
| 02 | `network_output` | Replacing Save Image with PD Network Output, UNC path setup |
| 03 | `project_context_tokens` | Using PD Project Context as the token root; how context flows downstream |
| 04 | `switch_node` | Single-channel and multi-channel switch; manual vs value-driven mode |
| 05 | `single_wedge` | One PD Wedge iterating over a prompt list; how queue injection works |
| 06 | `multi_wedge_with_rasterizer` | Two wedges (prompt + seed), Rasterizer preview, cartesian product |
| 07 | `full_production_shot` | All nodes together: Project Context → Shot Token → Wedge × 2 → Rasterizer → Output Namer → Network Output |

Workflows 01–04 should use only core ComfyUI nodes (KSampler, CLIP Text Encode, etc.) as the generative backbone — keep them model-agnostic. Workflows 05–07 can use a simple SD1.5 or SDXL backbone as placeholder.

All workflow JSONs must be valid ComfyUI workflow files. Scaffold them with placeholder node IDs that match the actual registered node class names.

---

## pyproject.toml Requirements

Must be valid for ComfyUI Registry (CNR) submission. Include:
- `name = "comfyui-pipedream"`
- `version = "0.1.0"`
- Author: Aaron Dabelow
- Description: "Production pipeline utility nodes for ComfyUI — output naming, network paths, shot tokens, wedge iteration, and multi-input switching."
- `license = "MIT"`
- No heavy dependencies in `[project.dependencies]`

---

## Code Style Notes

- Python 3.10+, no type hint requirement but use them where they aid readability
- Minimal inline comments; robust module/class-level docstrings
- Console prints for debug/error output — no logging framework
- Do not use `print()` for normal operation, only for warnings and errors
- Errors should be descriptive: tell the user what token failed, what path was invalid, etc.
- No third-party dependencies unless absolutely unavoidable

---

## What Claude Code Should Do First

1. Scaffold the full directory structure above (empty files with docstrings/stubs)
2. Implement `core/compat.py` — this is the foundation everything else builds on
3. Implement `core/tokens.py` — standalone, testable
4. Implement `nodes/project_context.py` and `nodes/output_namer.py` — these are the most fundamental and test the token engine
5. Implement `nodes/switch.py` — self-contained, no token dependency
6. Implement `nodes/wedge.py` — requires queue injection logic
7. Implement `nodes/rasterizer.py` — depends on wedge
8. Scaffold `workflows/` directory with README and stub workflow JSONs
9. Write `README.md` and `pyproject.toml`

Do not proceed to workflow JSON generation until the node class names are finalized — the JSONs must reference actual registered names.

---

## Open Questions / Deferred Decisions

- **Rasterizer UI**: JS extension for in-node display is v1 scope but can be a simple textarea. Full rich panel is v2.
- **Wedge cartesian mode**: For v1, multiple wedges operate independently (each spawns its own queue). True cartesian product (all combinations) is the v1.1 target once the basic queue injection is stable.
- **PD Network Output + video**: Image output is v1. Video file writing (mp4 passthrough) is v2.
- **Registry publication**: Not immediate. Get it working locally first, then submit to CNR.
