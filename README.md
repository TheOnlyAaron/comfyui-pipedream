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
| **💭 PD Custom Context** | Adds user-defined key/value token pairs to a context. Starts with one empty pair; a new pair appears as each name is filled (up to 10). Chain after Project Context for custom tokens like `{task}`, `{department}`. |
| **💭 PD Project Context** | Top-level metadata node (project, sequence, shot, version, artist). Accepts an incoming context for override chaining. Supports auto-incrementing version and version reset buttons (see [Versioning](#versioning)). |
| **💭 PD Shot Token** | Resolves a token template to a string (for prompts, filenames or other nodes' paths), using an optional context from Project/Custom Context. |
| **💭 PD Output** | Resolves a token template and writes images (png/exr/jpg/webp) or video (mp4/mov/webm) to ComfyUI's output directory (`relative`) or an absolute/UNC path (`absolute`). Writes a sidecar JSON, previews what was written, passes the images through, and shows available tokens after execution. |
| **💭 PD Switch** | Routes one of N wildcard inputs to a single output. Inputs auto-grow when connected (2–8). |
| **💭 PD Wedge** | Iteration node — holds a list of values and emits one per execution. Optional auto-queue for batch iteration. |
| **💭 PD Rasterizer** | Dry-run inspector — connects to wedges and previews the full cartesian product iteration table. |
| **💭 PD Images To Video** | Wraps an image batch (plus optional audio) as an in-memory `VIDEO` at a given fps. Outputs the video and its frame count. |
| **💭 PD Video To Images** | Decodes a `VIDEO` to images, audio, fps and frame count. Optional start frame, frame limit and every-Nth step decode only what you ask for. |
| **💭 PD Video Frame** | Grabs one frame from a `VIDEO` (first, last or index; negative counts from the end). Seeks instead of decoding the whole clip. |
| **💭 PD Image Frame** | Picks one image from a batch (first, last or index; negative counts from the end). |
| **💭 PD Sound** | Plays a short browser sound when this point of the flow is reached, or when the whole queue finishes. Passes any value straight through, so it can sit inline or dangle at the end. See [PD Sound](#pd-sound). |

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
| `{project}` | Project Context |
| `{sequence}` | Project Context |
| `{shot}` | Project Context |
| `{version}` | Project Context |
| `{artist}` | Project Context |
| `{date}` | Auto: YYYYMMDD |
| `{time}` | Auto: HHMMSS |
| `{frame}` | Frame number in PD Output image sequences (`start_frame`, `frame_padding`); `####` in PD Shot Token |
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
| `images` / `video` (inputs) | Connect at least one. A connected `video` (ComfyUI VIDEO) is written instead of `images`, with its own frame rate and audio. With an image format, its frames are written as an image sequence. |
| `alpha` (input) | Optional. Takes an `IMAGE`, `MASK` or `VIDEO` (one socket typed `IMAGE,MASK,VIDEO`, so other types can't connect). A MASK is used as is. An IMAGE or a VIDEO's frames give their Rec.709 luminance, so a grey matte keeps its exact values. It needs one frame (used for every frame) or as many frames as the source, at the same size; anything else is an error. See [Alpha](#alpha). |
| `path_mode` | `relative` writes under ComfyUI's output directory. `absolute` writes under `base_path` (an absolute or UNC path). |
| `template` | The output path without an extension. `{frame}` sets where the frame number goes. See [Image sequences](#image-sequences). |
| `format` | Images, one file per frame: `png`, `exr`, `jpg`, `webp`. Video, one file per batch: `mp4` (H.264), `mov` (ProRes), `webm` (VP9). |
| `start_frame`, `frame_padding` | Image formats only. The first frame number (default `1001`, the usual VFX start, which leaves room for handles before frame 1000) and its digit count (default 4). |
| `fps`, `crf` | Video only. `fps` applies to `images` (a VIDEO keeps its own rate). `crf` sets the quality for mp4/webm (lower is better). ProRes ignores it. |
| `prores_profile` | mov only. `auto` (default) writes ProRes 4444 with alpha when there is an alpha, and ProRes 422 HQ otherwise. `422 HQ` never writes alpha. `4444` is 4:4:4 10-bit, with alpha when there is one. |
| `exr_precision`, `exr_compression` | EXR only. Precision is `half` (default) or `float`. Compression is `zip` (default), `zips`, `rle` or `none`. EXR keeps float values unclipped. |
| `exr_colorspace` | EXR only. `as is` (default) writes the values unchanged. `sRGB to linear` decodes sRGB-encoded images, which covers most generated and loaded images, to linear light with the piecewise sRGB curve: `v / 12.92` up to 0.04045, then `((v + 0.055) / 1.055) ^ 2.4`. The power segment carries on above 1.0 (2.0 becomes about 5.7), and negative values are mirrored. Alpha is never converted. This is plain math with no OCIO. |
| `overwrite` | When off, nothing is written if the file, or any frame of the sequence, already exists. The console says so. This prevents a sequence that mixes old and new frames. |
| `save_metadata` | Writes a sidecar `.json` next to the output, with the template, resolved tokens and context, written files, frame range and `#` pattern, alpha source, timestamp, the ComfyUI prompt and the EXR/video settings (`colorspace`, `prores_profile`). The workflow is not embedded in the image files. |
| `path` (output) | The first file written (the first frame of a sequence), or the video file. |
| `path_sidecar` (output) | The sidecar JSON path. Empty when `save_metadata` is off. |
| `path_all` (output) | Every written file, one per line (every frame of a sequence). |
| `images` (output) | The input images passed through (the VIDEO's frames when only a VIDEO is connected). |
| `video` (output) | The written video as a ComfyUI VIDEO, for Save Video, Preview Video and other video nodes. Only shown for video formats. |

### Image sequences

Image formats write one file per frame.

- **With `{frame}`** in the template, the frame number goes there: `{shot}/{shot}_{version}.{frame}` writes `sh010_v001.1001.exr`, `sh010_v001.1002.exr`, and so on. `{frame}` can also appear in folder names.
- **Without `{frame}`**, a batch of more than one frame gets the VFX-style `.1001` before the extension (`sh010_v001.1001.png`).
- **A single image** (batch of 1) gets no frame number unless the template uses `{frame}`, in which case it is numbered `start_frame`.
- **Video formats** ignore `{frame}`. It is removed along with one `.`, `_` or `-` just before it, so `clip.{frame}` writes `clip.mp4`.

The sidecar of a sequence is named after the file name without the frame number (`sh010_v001.json`). It records `sequence.first`, `last`, `count`, `padding` and `pattern` (e.g. `…/sh010_v001.####.exr`). After a run, the token reference shows the frame range that `{frame}` covered.

### Alpha

Alpha is written to `png` and `webp` (8-bit RGBA), `exr` (RGBA, with alpha written as is: linear, unclipped and never colour-converted) and `mov` as ProRes 4444 (`prores_ks` profile 4, `yuva444p10le`). When `alpha` is not connected, the fourth channel of 4-channel images is used as alpha.

`jpg`, `mp4`, `webm` and ProRes 422 HQ can't store alpha. If `alpha` is connected anyway, the file is written without it, a warning is printed to the console, and the sidecar records `"alpha": {"written": false}`. A warning was chosen over an error so that switching to a review format (e.g. mp4) doesn't break a graph that also writes alpha.

### Hidden widgets and sockets

Widgets that don't apply to the chosen mode and format are hidden. Sockets are hidden too: the `alpha` input for formats without alpha, and the `video` output for image formats. A linked widget or socket is never hidden. Frontend 1.59 has no per-slot hidden flag, so sockets are hidden by removing them and added back when they apply again. This is safe because inputs are matched by name, and `video` is the last output, so removing it shifts no other output's index. A saved workflow leaves out a hidden socket, and it comes back when the workflow is loaded with a format that uses it. The `images` output is always shown, since passing images through is useful for every format.

A preview of what was written appears under the node, with one entry per frame for sequences. Images and mp4/webm inside ComfyUI's output directory are shown directly. EXR, ProRes and files outside the output directory get a downscaled preview in ComfyUI's temp directory (an animated WebP for video).

Video and EXR are encoded with PyAV, which is part of ComfyUI's requirements, so you don't need to install `ffmpeg` or any extra package. Audio from a connected VIDEO is muxed as AAC (mp4/mov) or Opus (webm). Odd frame sizes are padded by one pixel to the even size the video codecs need. EXR uses the EXR encoder bundled in PyAV (scanline, RGB or RGBA, half or float; no PIZ/DWA compression). Note that ffmpeg's ProRes decoder reports 4444 files as `yuva444p12le` when reading them back. That is how the decoder works; the files are encoded from 10-bit `yuva444p10le`.


## Compatibility

Pipedream nodes are classic ComfyUI node classes registered through `NODE_CLASS_MAPPINGS`, which current ComfyUI loads alongside V3 (`comfy_api`) nodes. A future move to V3 would port the nodes directly.

All nodes are built and tested for the Nodes 2.0 (Vue) frontend first, and also work on the classic canvas.

**Note:** Node display names use a 💭 emoji prefix. On Windows systems with older console codepages (cp1252, cp932), the emoji is automatically omitted to prevent encoding errors.

## License

MIT — see [LICENSE](LICENSE).
