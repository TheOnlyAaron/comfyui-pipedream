# ComfyUI-PipeDream

Production pipeline nodes for ComfyUI: token-based output and loading on local and network paths, EXR metadata through the pipeline, wedges, a memory and time profiler, video utilities, OCIO colour and sound cues.

Pipedream is not a visual effects node pack. It is plumbing.

**Comfy Registry:** [registry.comfy.org/publishers/theonlyaaron/nodes/PipeDream](https://registry.comfy.org/publishers/theonlyaaron/nodes/PipeDream) · install id `PipeDream`

## Installation

Open **Manager → Custom Nodes Manager**, search for **PipeDream** and click **Install**, then restart ComfyUI; the nodes appear under **Pipedream**. Install it one way only: a registry install and a git clone in `custom_nodes` at the same time register every node twice.

The only extra dependency is [OpenColorIO](https://opencolorio.org) (`opencolorio`), for the OCIO nodes. comfy-cli, git clone variants for Desktop, portable and manual installs, and updating or trying a branch are in [docs/install.md](docs/install.md).

## Nodes

Display names carry a 💭 prefix (left out on consoles that can't print emoji). Each name links to the node's page, which ComfyUI also shows in the node's help panel.

### Context and tokens

| Node | What it does |
|------|--------------|
| [**PD&nbsp;Project&nbsp;Context**](web/docs/PDProjectContext.md) | Shot details as tokens: project, sequence, shot, version, user. Chains for overrides; version auto-increment and reset buttons. Also outputs the tokens as EXR metadata. |
| [**PD&nbsp;Custom&nbsp;Context**](web/docs/PDCustomContext.md) | Your own key/value tokens (`{task}`, `{department}`...); a new pair appears as you fill one (up to 10). Also outputs the tokens as EXR metadata. |
| [**PD&nbsp;Tokens&nbsp;To&nbsp;String**](web/docs/PDTokensToString.md) | Resolves a token template to text, for prompts, titles or other nodes' paths. **preview** shows the result on the node. |

### Load and save

| Node | What it does |
|------|--------------|
| [**PD&nbsp;Save**](web/docs/PDSave.md) | Writes images (png/exr/jpg/webp) or video (mp4/mov/webm) to a token-built path, with alpha and a sidecar JSON. |
| [**PD&nbsp;Load**](web/docs/PDLoad.md) | Loads an image, sequence or video from any local or network path; paste a path to fill it in. |

### EXR metadata

| Node | What it does |
|------|--------------|
| [**PD&nbsp;EXR&nbsp;Metadata&nbsp;Merge**](web/docs/PDExrMetadataMerge.md) | Combines EXR metadata streams (up to 8) into one, frame by frame; later inputs win. |
| [**PD&nbsp;EXR&nbsp;Metadata&nbsp;Get**](web/docs/PDExrMetadataGet.md) | Lists an EXR metadata stream on the node and outputs one attribute's value. |

### Wedges and switching

| Node | What it does |
|------|--------------|
| [**PD&nbsp;Wedge**](web/docs/PDWedge.md) | Runs the graph once per row of inputs (any type), for comparison matrices. |
| [**PD&nbsp;Switch**](web/docs/PDSwitch.md) | Routes one of up to 8 inputs (any type) to its output. |

### Video

| Node | What it does |
|------|--------------|
| [**PD&nbsp;Images&nbsp;To&nbsp;Video**](web/docs/PDImagesToVideo.md) | Wraps images (and audio) as an in-memory `VIDEO`. |
| [**PD&nbsp;Video&nbsp;To&nbsp;Images**](web/docs/PDVideoToImages.md) | Decodes a `VIDEO` to images, mask, audio and fps; only the frame range you ask for. |
| [**PD&nbsp;Video&nbsp;Get&nbsp;Frame**](web/docs/PDVideoGetFrame.md) | One frame (first, last, index; negative counts from the end) without decoding the whole clip. |
| [**PD&nbsp;Image&nbsp;From&nbsp;Batch**](web/docs/PDImageFromBatch.md) | One image from a batch (first, last, index), with its mask. |

### Colour

| Node | What it does |
|------|--------------|
| [**PD&nbsp;OCIO&nbsp;Transform**](web/docs/PDOCIOTransform.md) | Converts between OpenColorIO colourspaces, optionally through a look. |
| [**PD&nbsp;OCIO&nbsp;Display**](web/docs/PDOCIODisplay.md) | Applies an OCIO display/view transform (e.g. ACES for sRGB), or its inverse. |
| [**PD&nbsp;OCIO&nbsp;Apply&nbsp;LUT**](web/docs/PDOCIOApplyLUT.md) | Applies a LUT file (.cube, .3dl, .spi3d, CLF...), forward or inverse. |

### Utility

| Node | What it does |
|------|--------------|
| [**PD&nbsp;Sound**](web/docs/PDSound.md) | Plays a browser sound when its point in the graph runs, or when the queue finishes. |
| [**PD&nbsp;Profiler**](web/docs/PDProfiler.md) | Profiles everything upstream of its input: models, latent sizes, VRAM and RAM per stage, time, API nodes. Evaluates without running; measures real runs. |

## Example workflows

Drag a `workflow.json` from [workflows/](workflows/) onto the canvas. 01–06 run as is (they use ComfyUI's `input/example.png`); 05 needs `opencolorio`, 07–08 need a checkpoint. Files go to `output/pipedream_demo/<workflow folder>/`. Every node appears in at least one.

| # | Workflow | Shows |
|---|----------|-------|
| 01 | [Tokens](workflows/01_tokens/) | Project and custom context, PD Tokens To String with **preview**, automatic tokens |
| 02 | [Load and save](workflows/02_load_and_save/) | PD Load (drop zone, paste a path), EXR sequence with sidecar and header metadata, read back with `sequence_mode`; EXR metadata merged and read back |
| 03 | [Video frames](workflows/03_video_frames/) | Images to video, mp4 out, get one frame, decode a range, pick from a batch, switch |
| 04 | [Sound](workflows/04_sound/) | Inline and queue-finished sound cues, error buzzer |
| 05 | [Colour with OCIO](workflows/05_color_ocio/) | OCIO transform and display, LUT, ACEScg EXR |
| 06 | [Wedge basics](workflows/06_wedge_basics/) | One wedge, three sizes, three files, profiled; no model |
| 07 | [Prompt wedge](workflows/07_prompt_wedge/) | One wedge of three prompts: 3 jobs, same seed |
| 08 | [Product matrix](workflows/08_product_matrix/) | Grouped and chained wedges: 3 products × 2 looks |

## Topics

- [Tokens](docs/tokens.md): built-in tokens, context nodes, chaining and versioning.
- [Wedges](docs/wedges.md): one job per row, chained and grouped wedges; [without the browser](docs/wedges-headless.md).
- [EXR metadata](docs/exr-metadata.md): reading, setting, merging and writing header attributes.
- [Alpha and premultiplication](docs/alpha.md): conventions per format, and mask polarity against core ComfyUI.
- [Profiler](docs/profiler.md): how each number is worked out, the sidecar, use without the browser.
- [Profiler accuracy](docs/profiler-accuracy.md): how each number was checked against ComfyUI's source, 73 published model files and published requirements.
- [Settings](docs/settings.md): facility and user defaults in TOML.
- [Pipeline integration](docs/pipeline.md): settings, sidecars and ComfyUI's API for ftrack, Flow, Deadline and publish tools, without running scripts from ComfyUI.
- [Installation](docs/install.md): Manager, comfy-cli, git clone, updating.

## Settings

Studios can set defaults (templates, network roots, formats, token delimiters, OCIO config...) in `pipedream.toml` in the pack folder, or in a shared facility file, which wins, named by a `pipedream_facility.txt` pointer file in ComfyUI's user folder. [`pipedream.example.toml`](pipedream.example.toml) lists every key. Details and deployment: [docs/settings.md](docs/settings.md).

## Compatibility

Classic ComfyUI node classes (`NODE_CLASS_MAPPINGS`), which current ComfyUI loads alongside V3 nodes. Built for the Nodes 2.0 frontend first, and tested on the classic canvas. PD Profiler's run measurements use ComfyUI's per-prompt progress registry (`comfy_execution.progress`); on versions without it the profiler still evaluates, without measurements.

## License

MIT — see [LICENSE](LICENSE).
