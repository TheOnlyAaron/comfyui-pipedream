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
| **💭 PD Project Context** | Top-level metadata node (project, sequence, shot, version, artist). Accepts an incoming context for override chaining. Supports auto-incrementing version. |
| **💭 PD Custom Context** | Adds up to 5 user-defined key/value token pairs to a context. Chain after Project Context for custom tokens like `{task}`, `{department}`. |
| **💭 PD Shot Token** | Lightweight token resolver — takes a template string and inline widget values, outputs a resolved string. |
| **💭 PD Output Relative** | Resolves a token template and saves images to ComfyUI's output directory. Shows available tokens after execution. |
| **💭 PD Output Absolute** | Same as Output Relative but saves to an absolute or UNC network path. |
| **💭 PD Switch** | Routes one of N wildcard inputs to a single output. Inputs auto-grow when connected (2–8). |
| **💭 PD Wedge** | Iteration node — holds a list of values and emits one per execution. Optional auto-queue for batch iteration. |
| **💭 PD Rasterizer** | Dry-run inspector — connects to wedges and previews the full cartesian product iteration table. |
| **💭 PD Images To Video** | Wraps an image batch (plus optional audio) as an in-memory `VIDEO` at a given fps. Outputs the video and its frame count. |
| **💭 PD Video To Images** | Decodes a `VIDEO` to images, audio, fps and frame count. Optional start frame, frame limit and every-Nth step decode only what you ask for. |
| **💭 PD Video Frame** | Grabs one frame from a `VIDEO` (first, last or index; negative counts from the end). Seeks instead of decoding the whole clip. |
| **💭 PD Image Frame** | Picks one image from a batch (first, last or index; negative counts from the end). |

## Video

The video nodes live under **Pipedream/Video** and use ComfyUI's core `VIDEO` type, so they plug straight into Load Video, Save Video, Create Video and other packs. They overlap with core **Create Video** / **Get Video Components** on purpose: these are Pipedream-owned versions we can extend, with a few practical differences:

- **Range decoding.** PD Video To Images decodes only `start_frame` … `start_frame + frame_limit × step`, keeping every `step`-th frame, instead of loading the whole clip. That matters at 1080p, where each float32 frame is about 25 MB. Output fps is divided by `step`, and the audio is cut to the same time span, so the two stay in sync.
- **Single frames without a full decode.** PD Video Frame seeks to the nearest keyframe before the target and decodes forward from there. `last` and negative indices find the real end of the stream, even when the container's frame count is wrong. Videos that are already in memory (e.g. from Create Video or PD Images To Video) are indexed directly.
- **Last / negative indices.** PD Image Frame does the same for image batches; core Image From Batch has no "last" option and no negative indices.
- **Nothing written to disk.** PD Images To Video returns an in-memory video. Encoding only happens when a save node runs.

Notes:

- Images come out as float32 RGB in 0–1. 8-bit sources are converted through `rgb24`, and 10/12-bit sources through `rgb48le`, so they keep their precision.
- Alpha channels are dropped. Use core Get Video Components if you need a video's alpha.
- Out-of-range indices are clamped to the first or last frame. `frame_index` reports the frame that was actually used.
- PD Video Frame's `frame_count` is exact for `last` and negative indices. For `first` and positive indices it comes from container metadata.
- Seeking assumes a constant frame rate. On variable-frame-rate footage, frame indices are approximate.
- Decoding uses PyAV, which ships with ComfyUI. No ffmpeg binary or extra packages are needed.

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

## Compatibility

Pipedream supports both the legacy ComfyUI node API and the Nodes 2.0 (V3) API. The compatibility layer detects which API is available at import time and registers nodes accordingly.

**Note:** Node display names use a 💭 emoji prefix. On Windows systems with legacy console codepages (cp1252, cp932), the emoji is automatically omitted to prevent encoding errors.

## License

MIT — see [LICENSE](LICENSE).
