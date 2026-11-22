# ComfyUI-Pipedream

Production pipeline utility nodes for ComfyUI — output naming, network paths, shot tokens, wedge iteration, and multi-input switching.

Pipedream is not a visual effects node pack. It is plumbing.

## Installation

Clone into your ComfyUI `custom_nodes` directory:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/theonlyaaron/comfyui-pipedream.git
```

No additional dependencies are required. Video and EXR are written with PyAV (`av`), which ComfyUI already installs.

## Nodes

All nodes appear under the **Pipedream** category with a 💭 prefix.

| Node | Description |
|------|-------------|
| **💭 PD Project Context** | Top-level metadata node (project, sequence, shot, version, artist). Accepts an incoming context for override chaining. Supports auto-incrementing version. |
| **💭 PD Custom Context** | Adds user-defined key/value token pairs to a context. Starts with one empty pair; a new pair appears as each name is filled (up to 10). Chain after Project Context for custom tokens like `{task}`, `{department}`. |
| **💭 PD Project Context** | Top-level metadata node (project, sequence, shot, version, artist). Accepts an incoming context for override chaining. Supports auto-incrementing version and version reset buttons (see [Versioning](#versioning)). |
| **💭 PD Shot Token** | Lightweight token resolver — takes a template string and inline widget values, outputs a resolved string. |
| **💭 PD Output** | Resolves a token template and writes images (png/exr/jpg/webp) or video (mp4/mov/webm) to ComfyUI's output directory (`relative`) or an absolute/UNC path (`absolute`). Writes a sidecar JSON, previews what was written, passes the images through, and shows available tokens after execution. |
| **💭 PD Output Relative (legacy)** | Deprecated: use PD Output in `relative` mode. Kept so older workflows still load. |
| **💭 PD Output Absolute (legacy)** | Deprecated: use PD Output in `absolute` mode. Kept so older workflows still load. |
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
| **💭 PD Sound** | Plays a short browser sound when this point of the flow is reached, or when the whole queue finishes. Passes any value straight through, so it can sit inline or dangle at the end. See [PD Sound](#pd-sound). |

## PD Sound

Wire anything through the `value` input; the `value` output is the same object, untouched. The node is an output node, so it also runs when left dangling.

- **play_when = node reached** (default): plays when this node executes, so several PD Sound nodes along a graph each announce their own stage with their own sound. A node with nothing connected has no place in the flow, so it waits for the queue to finish instead.
- **play_when = queue finished**: plays once the queue drains, like a render-complete chime. If any prompt failed it plays the error tone instead (`error_tone`); nothing plays after an interrupt.
- **Caching**: a cached node does not execute, and PD Sound never forces it to (that would re-run everything downstream). Turn on `when_cached` to also play when the node is skipped as cached; those sounds play as the prompt starts, because cached work is already done.
- **Errors**: in node reached mode, an execution error plays the error tone straight away (unless `error_tone` is off).
- **Sounds**: `chime`, `happy`, `sad`, `ding`, `beeps`, `alert` are synthesized in the browser (no audio files). `custom URL` plays a file: absolute URL, root-relative path, or a path relative to this pack's `web/` folder. Each node picks its own sound and volume; the test buttons preview them.
- Sounds play in the browser tab that queued the prompt. Changing a PD Sound widget changes its inputs, so nodes downstream of an inline PD Sound re-run on the next queue, as with any other widget edit.

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

## Versioning

PD Project Context's `version` widget is a prefix followed by a number, e.g. `v001`, `take_0042`. The number's zero-padding width is preserved (`v009` → `v010`, `v999` → `v1000`).

**Auto-increment.** With `auto_increment_version` on, the version is bumped in the frontend at queue time, like seed's `control_after_generate`: each queued prompt uses the current version, then the widget advances by one. Queuing with batch count 5 from `v001` runs `v001`–`v005` and leaves the widget on `v006`. Versions without a trailing number are left as-is, and nothing is bumped while the `version` input is driven by a link.

**Reset buttons.** Each PD Project Context node has two buttons:

- **reset version** — resets that node's version to its first version, keeping its prefix and padding (`v017` → `v001`, `take_0042` → `take_0001`). An empty or non-numeric version becomes `v001`.
- **reset all versions in graph** — after a confirmation, resets every PD Project Context in the workflow, including inside subgraphs.

The global reset is also available from the canvas right-click menu as **Pipedream: reset all versions** (recent ComfyUI frontends only).

## PD Output

| Input / Output | Notes |
|----------------|-------|
| `images` / `video` (inputs) | Connect at least one. A connected `video` (ComfyUI VIDEO) is written instead of `images`, with its own frame rate and audio; with an image format its frames are written as an image sequence. |
| `path_mode` | `relative` writes under ComfyUI's output directory; `absolute` writes under `base_path` (absolute or UNC path). |
| `format` | Images: `png`, `exr`, `jpg`, `webp` (batches get a `_0000` index). Video: `mp4` (H.264), `mov` (ProRes 422 HQ), `webm` (VP9), one file per batch. |
| `fps`, `crf` | Video only. `fps` applies to `images` (a VIDEO keeps its own rate). `crf` is the quality for mp4/webm (lower is better); ProRes ignores it. |
| `exr_precision`, `exr_compression` | EXR only. `half` (default) or `float`; compression `zip` (default), `zips`, `rle` or `none`. EXR keeps the linear float values (no clipping to 0–1) and writes alpha when the image has 4 channels. |
| `save_metadata` | Writes `<name>.json` next to the output: template, resolved tokens and context, written file paths, timestamp, the ComfyUI prompt and the EXR/video settings. The workflow is not embedded in the image files. |
| `path` (output) | First file written, or the video file. |
| `path_sidecar` (output) | The sidecar JSON path, empty when `save_metadata` is off. |
| `path_all` (output) | Every written file, one per line. |
| `images` (output) | The input images passed through (the VIDEO's frames when only a VIDEO is connected). |
| `video` (output) | The written video as a ComfyUI VIDEO, for Save Video, Preview Video and other video nodes. Empty for image formats. |

A preview of what was written appears under the node. Images and mp4/webm inside ComfyUI's output directory are shown directly; EXR, ProRes and files outside it get a downscaled preview in ComfyUI's temp directory (an animated WebP for video). Widgets that do not apply to the chosen mode and format are hidden.

Video and EXR are encoded with PyAV, which is part of ComfyUI's requirements, so no `ffmpeg` install or extra package is needed. Audio from a connected VIDEO is muxed as AAC (mp4/mov) or Opus (webm). Odd frame sizes are padded by one pixel to the even size the video codecs need. EXR uses the EXR encoder bundled in PyAV (scanline, RGB or RGBA, half or float; no PIZ/DWA compression).

The legacy Relative/Absolute nodes share this implementation, have the same five outputs and also have the `exr_precision` and `exr_compression` options; `path` is the first output, so links from their old `written_path` output keep working.

## Compatibility

Pipedream supports both the legacy ComfyUI node API and the Nodes 2.0 (V3) API. The compatibility layer detects which API is available at import time and registers nodes accordingly.

**Note:** Node display names use a 💭 emoji prefix. On Windows systems with legacy console codepages (cp1252, cp932), the emoji is automatically omitted to prevent encoding errors.

## License

MIT — see [LICENSE](LICENSE).
