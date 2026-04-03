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

All nodes appear under the **Pipedream** category in the ComfyUI node menu.

| Node | Description |
|------|-------------|
| **PD Project Context** | Top-level metadata node (project, sequence, shot, version, artist). Acts as the root token source for a workflow. |
| **PD Shot Token** | Lightweight token resolver — takes a template string and inline widget values, outputs a resolved string. |
| **PD Output Namer** | Builds a structured output filename from a token template. Feeds into Save Image or PD Network Output. |
| **PD Network Output** | Writes images to a local or UNC network path with directory creation and overwrite control. |
| **PD Switch** | Routes one of N inputs to output per channel. Supports any type (wildcard), up to 8 channels with 8 inputs each. |
| **PD Wedge** | Iteration node — holds a list of values and emits one per execution. Optional auto-queue for batch iteration. |
| **PD Rasterizer** | Dry-run inspector — connects to wedges and previews the full cartesian product iteration table. |

## Token Reference

Tokens are `{name}` placeholders resolved by PD Output Namer and PD Shot Token:

| Token | Source |
|-------|--------|
| `{project}` | Project Context or widget |
| `{sequence}` | Project Context or widget |
| `{shot}` | Project Context or widget |
| `{version}` | Project Context or widget |
| `{date}` | Auto: YYYYMMDD |
| `{time}` | Auto: HHMMSS |
| `{frame}` | Padded frame placeholder (e.g. `####`) |
| `{wedge_idx}` | Current wedge iteration index |
| `{wedge_<name>}` | Named wedge current value |

## Compatibility

Pipedream supports both the legacy ComfyUI node API and the Nodes 2.0 (V3) API. The compatibility layer detects which API is available at import time and registers nodes accordingly. No configuration needed.

## License

MIT — see [LICENSE](LICENSE).
