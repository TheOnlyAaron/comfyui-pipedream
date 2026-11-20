# ComfyUI-Pipedream

Production pipeline utility nodes for ComfyUI — output naming, network paths, shot tokens, wedge iteration, and multi-input switching.

Pipedream is not a visual effects node pack. It is plumbing.

## Installation

Clone into your ComfyUI `custom_nodes` directory:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/theonlyaaron/comfyui-pipedream.git
```

No additional Python dependencies are required. Writing video from PD Output needs the `ffmpeg` binary on your `PATH`.

## Nodes

All nodes appear under the **Pipedream** category with a 💭 prefix.

| Node | Description |
|------|-------------|
| **💭 PD Project Context** | Top-level metadata node (project, sequence, shot, version, artist). Accepts an incoming context for override chaining. Supports auto-incrementing version. |
| **💭 PD Custom Context** | Adds up to 5 user-defined key/value token pairs to a context. Chain after Project Context for custom tokens like `{task}`, `{department}`. |
| **💭 PD Shot Token** | Lightweight token resolver — takes a template string and inline widget values, outputs a resolved string. |
| **💭 PD Output** | Resolves a token template and writes images (png/exr/jpg/webp) or video (mp4/mov/webm) to ComfyUI's output directory (`relative`) or an absolute/UNC path (`absolute`). Writes a sidecar JSON, previews what was written, passes the images through, and shows available tokens after execution. |
| **💭 PD Output Relative (legacy)** | Deprecated: use PD Output in `relative` mode. Kept so older workflows still load. |
| **💭 PD Output Absolute (legacy)** | Deprecated: use PD Output in `absolute` mode. Kept so older workflows still load. |
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
            → PD Output
```

## PD Output

| Input / Output | Notes |
|----------------|-------|
| `path_mode` | `relative` writes under ComfyUI's output directory; `absolute` writes under `base_path` (absolute or UNC path). |
| `format` | Images: `png`, `exr`, `jpg`, `webp` (batches get a `_0000` index). Video: `mp4` (H.264), `mov` (ProRes 422 HQ), `webm` (VP9), one file per batch. |
| `fps`, `crf` | Video only. `crf` is the quality for mp4/webm (lower is better); ProRes ignores it. |
| `save_metadata` | Writes `<name>.json` next to the output: template, resolved tokens and context, written file paths, timestamp and the ComfyUI prompt. The workflow is not embedded in the image files. |
| `written_path` (output) | Path of the first file written. |
| `images` (output) | The input images, passed through for downstream nodes. |

A preview of what was written appears under the node. Files inside ComfyUI's output directory are shown directly; EXR, video and absolute paths outside it get a downscaled preview in ComfyUI's temp directory (an animated WebP for video).

Video is encoded by piping frames to the `ffmpeg` binary, which must be on your `PATH` (no Python package is needed). If it is missing, the node raises an error telling you so.

## Compatibility

Pipedream supports both the legacy ComfyUI node API and the Nodes 2.0 (V3) API. The compatibility layer detects which API is available at import time and registers nodes accordingly.

**Note:** Node display names use a 💭 emoji prefix. On Windows systems with legacy console codepages (cp1252, cp932), the emoji is automatically omitted to prevent encoding errors.

## License

MIT — see [LICENSE](LICENSE).
