# ComfyUI-Pipedream

Production pipeline utility nodes for ComfyUI — output naming, network paths, shot tokens, wedge iteration, and multi-input switching.

Pipedream is not a visual effects node pack. It is plumbing.

## Installation

Clone into your ComfyUI `custom_nodes` directory:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/theonlyaaron/comfyui-pipedream.git
```

No additional dependencies are required.

## Nodes

All nodes appear under the **Pipedream** category with a 💭 prefix.

| Node | Description |
|------|-------------|
| **💭 PD Project Context** | Top-level metadata node (project, sequence, shot, version, artist). Accepts an incoming context for override chaining. Supports auto-incrementing version and version reset buttons (see [Versioning](#versioning)). |
| **💭 PD Custom Context** | Adds up to 5 user-defined key/value token pairs to a context. Chain after Project Context for custom tokens like `{task}`, `{department}`. |
| **💭 PD Shot Token** | Lightweight token resolver — takes a template string and inline widget values, outputs a resolved string. |
| **💭 PD Output Relative** | Resolves a token template and saves images to ComfyUI's output directory. Shows available tokens after execution. |
| **💭 PD Output Absolute** | Same as Output Relative but saves to an absolute or UNC network path. |
| **💭 PD Switch** | Routes one of N wildcard inputs to a single output. Inputs auto-grow when connected (2–8). |
| **💭 PD Wedge** | Iteration node — holds a list of values and emits one per execution. Optional auto-queue for batch iteration. |
| **💭 PD Rasterizer** | Dry-run inspector — connects to wedges and previews the full cartesian product iteration table. |

## Token Reference

Tokens are `{name}` placeholders resolved by output nodes and PD Shot Token:

| Token | Source |
|-------|--------|
| `{project}` | Project Context or widget |
| `{sequence}` | Project Context or widget |
| `{shot}` | Project Context or widget |
| `{version}` | Project Context or widget |
| `{artist}` | Project Context |
| `{date}` | Auto: YYYYMMDD |
| `{time}` | Auto: HHMMSS |
| `{frame}` | Padded frame placeholder (e.g. `####`) |
| `{wedge_idx}` | Current wedge iteration index |
| `{wedge_<name>}` | Named wedge current value |
| `{<custom>}` | Any key added via PD Custom Context |

## Context Chaining

PD Project Context accepts an optional incoming context. Non-empty widget values override the incoming values, empty widgets pass through. This lets you set up a base context and override per-shot:

```
PD Project Context (base: project=DITC, sequence=sq010)
    → PD Project Context (override: shot=sh010)
        → PD Custom Context (task=comp, element=BG)
            → PD Output Relative
```

## Versioning

PD Project Context's `version` widget is a prefix followed by a number, e.g. `v001`, `take_0042`. The number's zero-padding width is preserved (`v009` → `v010`, `v999` → `v1000`).

**Auto-increment.** With `auto_increment_version` on, the version is bumped in the frontend at queue time, like seed's `control_after_generate`: each queued prompt uses the current version, then the widget advances by one. Queuing with batch count 5 from `v001` runs `v001`–`v005` and leaves the widget on `v006`. Versions without a trailing number are left as-is, and nothing is bumped while the `version` input is driven by a link.

**Reset buttons.** Each PD Project Context node has two buttons:

- **reset version** — resets that node's version to its first version, keeping its prefix and padding (`v017` → `v001`, `take_0042` → `take_0001`). An empty or non-numeric version becomes `v001`.
- **reset all versions in graph** — after a confirmation, resets every PD Project Context in the workflow, including inside subgraphs.

The global reset is also available from the canvas right-click menu as **Pipedream: reset all versions** (recent ComfyUI frontends only).

## Compatibility

Pipedream supports both the legacy ComfyUI node API and the Nodes 2.0 (V3) API. The compatibility layer detects which API is available at import time and registers nodes accordingly.

**Note:** Node display names use a 💭 emoji prefix. On Windows systems with legacy console codepages (cp1252, cp932), the emoji is automatically omitted to prevent encoding errors.

## License

MIT — see [LICENSE](LICENSE).
