# ComfyUI-PipeDream

Production pipeline nodes for ComfyUI: token-based output and loading on local and network paths, EXR metadata through the pipeline, wedges, a memory and time profiler, video utilities, OCIO colour and sound cues.

Pipedream is not a visual effects node pack. It is plumbing.

**Comfy Registry:** [registry.comfy.org/publishers/theonlyaaron/nodes/PipeDream](https://registry.comfy.org/publishers/theonlyaaron/nodes/PipeDream) · install id `PipeDream`

## Installation

Restart ComfyUI after installing; the nodes appear under **Pipedream**. Install it one way only: a registry install and a git clone in `custom_nodes` at the same time register every node twice.

The only extra dependency is [OpenColorIO](https://opencolorio.org) (`opencolorio`, BSD-3), for the OCIO nodes. Everything else works without it. Video and EXR use PyAV, which ComfyUI already ships.

### ComfyUI Manager (recommended)

Open the **Nodes Manager** (Manager → Custom Nodes Manager), search for **PipeDream** and click **Install**. Manager installs the dependencies and handles updates.

- **Versions:** numbered versions (`0.2.0`, ...) are the stable releases published to the [Comfy Registry](https://registry.comfy.org/publishers/theonlyaaron/nodes/PipeDream). **nightly** is the newest commit on `main`. Minor versions (`0.3.0`, ...) also get a [GitHub release](https://github.com/theonlyaaron/comfyui-pipedream/releases) with their changelog notes.
- A version published in the last few hours may not be in Manager's cached list yet ("Cannot resolve install target 'PipeDream@latest'"): pick **nightly** from the version list, or restart ComfyUI later.

### comfy-cli

With [comfy-cli](https://docs.comfy.org/comfy-cli/getting-started) installed (`pip install comfy-cli`), in the Python environment ComfyUI runs with:

```bash
comfy node install PipeDream
```

`comfy node update PipeDream` updates it. When comfy-cli doesn't know which install to use, name it: `comfy --workspace "<path to ComfyUI>" node install PipeDream`.

### Git clone

For development, or to follow `main` without Manager. The commands use full paths, so they work from any folder.

#### ComfyUI Desktop (Windows)

Desktop keeps each instance in `%LOCALAPPDATA%\Comfy-Desktop\ComfyUI-Installs\<instance name>`. Open the instance's **Terminal** tab (its Python is already active) and paste:

```powershell
$instance = "ComfyUI"   # the instance name shown in Desktop's instance list
$nodes = "$env:LOCALAPPDATA\Comfy-Desktop\ComfyUI-Installs\$instance\ComfyUI\custom_nodes"
git clone https://github.com/theonlyaaron/comfyui-pipedream.git "$nodes\comfyui-pipedream"
python -m pip install -r "$nodes\comfyui-pipedream\requirements.txt"
```

If `git clone` says the path does not exist, check the instance folder name with `dir "$env:LOCALAPPDATA\Comfy-Desktop\ComfyUI-Installs"`.

> Older Desktop versions (before instances) use `$nodes = "$env:USERPROFILE\Documents\ComfyUI\custom_nodes"` with the same last two lines.

#### ComfyUI portable (Windows)

```powershell
$portable = "C:\ComfyUI_windows_portable"   # the folder holding run_nvidia_gpu.bat
git clone https://github.com/theonlyaaron/comfyui-pipedream.git "$portable\ComfyUI\custom_nodes\comfyui-pipedream"
& "$portable\python_embeded\python.exe" -m pip install -r "$portable\ComfyUI\custom_nodes\comfyui-pipedream\requirements.txt"
```

#### Manual install (Linux, macOS, Windows)

Activate the Python environment ComfyUI runs with, then:

```bash
COMFY=~/ComfyUI   # the folder holding main.py
git clone https://github.com/theonlyaaron/comfyui-pipedream.git "$COMFY/custom_nodes/comfyui-pipedream"
python -m pip install -r "$COMFY/custom_nodes/comfyui-pipedream/requirements.txt"
```

### Updating, or trying a branch

Point `$pack` (PowerShell) or `pack` (bash) at the installed folder, e.g.:

```powershell
$pack = "$env:LOCALAPPDATA\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\custom_nodes\comfyui-pipedream"
```

```bash
pack=~/ComfyUI/custom_nodes/comfyui-pipedream
```

Then update (or switch to a branch such as `wedges`, and back with `checkout main`). These lines work in both shells:

```bash
git -C "$pack" pull
```

```bash
git -C "$pack" fetch origin
git -C "$pack" checkout wedges
```

Restart ComfyUI and refresh the browser afterwards. At startup the console lists `comfyui-pipedream` under "Import times for custom nodes" (or `IMPORT FAILED` with the reason). Keep one copy of the pack per ComfyUI: a stale copy in another `custom_nodes` folder or Desktop instance is the usual reason changes don't show up.

## Nodes

Display names carry a 💭 prefix (left out on consoles that can't print emoji).

| Node | What it does |
|------|--------------|
| **PD&nbsp;Project&nbsp;Context** | Shot details as tokens: project, sequence, shot, version, user. Chains for overrides; version auto-increment and reset buttons. Also outputs the tokens as EXR metadata. |
| **PD&nbsp;Custom&nbsp;Context** | Your own key/value tokens (`{task}`, `{department}`...); a new pair appears as you fill one (up to 10). Also outputs the tokens as EXR metadata. |
| **PD&nbsp;Tokens&nbsp;To&nbsp;String** | Resolves a token template to text, for prompts, titles or other nodes' paths. **preview** shows the result on the node. |
| **PD&nbsp;Output** | Writes images (png/exr/jpg/webp) or video (mp4/mov/webm) to a token-built path, with alpha and a sidecar JSON. [More](#pd-output) |
| **PD&nbsp;Load** | Loads an image, sequence or video from any local or network path; paste a path to fill it in. [More](#pd-load) |
| **PD&nbsp;Wedge** | Runs the graph once per row of inputs (any type), for comparison matrices. [More](#wedges) |
| **PD&nbsp;Switch** | Routes one of up to 8 inputs (any type) to its output. |
| **PD&nbsp;Images&nbsp;To&nbsp;Video** | Wraps images (and audio) as an in-memory `VIDEO`. |
| **PD&nbsp;Video&nbsp;To&nbsp;Images** | Decodes a `VIDEO` to images, mask, audio and fps; only the frame range you ask for. |
| **PD&nbsp;Video&nbsp;Get&nbsp;Frame** | One frame (first, last, index; negative counts from the end) without decoding the whole clip. |
| **PD&nbsp;Image&nbsp;From&nbsp;Batch** | One image from a batch (first, last, index), with its mask. |
| **PD&nbsp;OCIO&nbsp;Transform** | Converts between OpenColorIO colourspaces, optionally through a look. [More](#ocio) |
| **PD&nbsp;OCIO&nbsp;Display** | Applies an OCIO display/view transform (e.g. ACES for sRGB), or its inverse. |
| **PD&nbsp;OCIO&nbsp;Apply&nbsp;LUT** | Applies a LUT file (.cube, .3dl, .spi3d, CLF...), forward or inverse. |
| **PD&nbsp;Sound** | Plays a browser sound when its point in the graph runs, or when the queue finishes. [More](#pd-sound) |
| **PD&nbsp;EXR&nbsp;Metadata&nbsp;Merge** | Combines EXR metadata streams (up to 8) into one, frame by frame; later inputs win. [More](#exr-metadata) |
| **PD&nbsp;EXR&nbsp;Metadata&nbsp;Get** | Lists an EXR metadata stream on the node and outputs one attribute's value. [More](#exr-metadata) |
| **PD&nbsp;Profiler** | Profiles everything upstream of its input: models, latent sizes, VRAM and RAM per stage, time, API nodes. Evaluates without running; measures real runs. [More](#pd-profiler) |

## Example workflows

Drag a `workflow.json` from [workflows/](workflows/) onto the canvas. 01–06 run as is (they use ComfyUI's `input/example.png` and write to `output/pipedream_demo/`); 05 needs `opencolorio`, 07–08 need a checkpoint. Every node appears in at least one.

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

## Tokens

Templates use `{name}` placeholders. Delimiters, date/time formats and fixed extra tokens are configurable ([defaults](#facility--user-defaults)).

| Token | From |
|-------|------|
| `{project}` `{sequence}` `{shot}` `{version}` `{user}` | PD Project Context |
| `{<custom>}` | PD Custom Context |
| `{date}` `{time}` | Automatic (`YYYYMMDD`, `HHMMSS`) |
| `{frame}` | Frame number in PD Output sequences; `####` in PD Tokens To String; sequence frames in PD Load |
| `{<token>}` `{<token>_idx}` | PD Wedge row text and position (`000`, `001`...) |
| `{wedge_idx}` `{wedge_total}` | PD Wedge job number and job count |
| `{<extra>}` | `[tokens.extra]` settings (context values win) |

**Chaining.** Contexts accept an incoming context: non-empty widgets override it, empty ones pass it through. Set up a base and override per shot:

```
PD Project Context (project=DITC, sequence=sq010)
  → PD Project Context (shot=sh010)
    → PD Custom Context (task=comp)
      → PD Output
```

**Versioning.** `version` is a prefix plus a number (`v001`, `take_0042`); padding is kept (`v009` → `v010`). With `auto_increment_version`, each queued prompt uses the current version and the widget then advances, like a seed's `control_after_generate` (batch count 5 from `v001` runs `v001`–`v005`). **reset version** returns the node to its first version (`v017` → `v001`); **reset all versions in graph** (also in the canvas menu as *Pipedream: reset all versions*) resets every PD Project Context, subgraphs included.

## PD Output

Resolves `file` (the `template` input in API prompts and settings) under ComfyUI's output folder (`relative`) or `base_path` (`absolute`, UNC works) and writes `images` or a connected `video`.

- **Formats:** png, exr, jpg, webp (one file per frame), mp4 (H.264), mov (ProRes), webm (VP9). A `video` input keeps its frame rate and audio; with an image format its frames become a sequence.
- **Sequences:** `{frame}` places the frame number (`{shot}_{version}.{frame}` → `sh010_v001.1001.exr`), starting at `start_frame` with `frame_padding` digits. Without `{frame}`, batches of more than one frame get `.1001` before the extension (`sequence.frame_separator` can make it `_` or `-`); a single image gets no number. Video formats drop `{frame}`.
- **Alpha:** from `alpha` (a MASK, or an IMAGE/VIDEO's luminance; one frame or one per frame) or the images' fourth channel. Written to png/webp (straight), exr (premultiplied) and mov as ProRes 4444 (`prores_profile` `auto` picks 4444 when there is alpha, else 422 HQ). jpg/mp4/webm can't store alpha: it is skipped with a console warning. See [Alpha and premultiplication](#alpha-and-premultiplication).
- **EXR:** `half` or `float`, `zip`/`zips`/`rle`/`none`, values unclipped. `exr_colorspace` `sRGB to linear` decodes sRGB images to linear with the sRGB curve (no OCIO); for other spaces put PD OCIO Transform first.
- **Safety:** with `overwrite` off nothing is written if the file, or any frame of the sequence, exists. Relative paths can't leave the output folder.
- **Sidecar** (`save_metadata`): `<name>.json` next to the output (frame number dropped) with the template, tokens, context, files, frame range and pattern, alpha, wedge job, settings files, the ComfyUI prompt and the workflow. PD Load reads it back; drop it on ComfyUI to reopen the workflow that wrote it.
- **EXR metadata** (exr only): `exr metadata` inputs write header attributes from PD Load, a context node or PD Profiler; a spare input appears as you connect one. See [EXR metadata](#exr-metadata).
- **Outputs:** `path` (first file), `path_sidecar`, `path_all` (one per line), the images passed through, and `video` (video formats).
- **Panel and preview:** after a run the panel lists every token and its value; the preview shows what was written (EXR, ProRes and files outside the output folder get a downscaled preview, video as a playable clip). **preview wedge** lists every wedge job's path without running the graph. **Copy Path** copies the last written file's full path (the first frame of a sequence), to paste into Explorer, Finder, Nuke or any other application; it works from any browser.
- Widgets and sockets that don't apply to the format are hidden (never while linked). Encoding uses PyAV: no ffmpeg install, audio as AAC/Opus, odd sizes padded to even for video codecs.

## PD Load

Loads an image, image sequence or video, and reads back what PD Output wrote.

- **Paste a path:** copy a file's path (Explorer: shift+right click → *Copy as path*) into `file` or `base_path`. Quotes are removed, the path is split into folder and name, `path_mode` switches to `absolute`, and the file loads. **load** (or the selection toolbar's run button) runs just this node.
- **Copy Path** copies the full path of the file the widgets point at (resolved from `path_mode`, `base_path` and `file`), to paste into Explorer, Finder, Nuke or any other application.
- **Drop files:** drag files from Explorer onto the drop zone (or anywhere on the node in the classic canvas). Browsers don't reveal a dropped file's path, so the files are copied to ComfyUI's `input/pipedream` folder (overwriting same-named files) and loaded from there in `relative` mode. Drop every frame of a sequence, plus its sidecar for the tokens. For files on a share, pasting the path loads them in place without copying.
- **Where:** `relative` reads from ComfyUI's input folder, `absolute` from `base_path` (`C:\Shots`, `/mnt/shows`, `\\server\shows`). A full path in `file` (e.g. PD Output's `path`) is used as is.
- **What:** `file` may include the extension or leave it to `format`; `auto` tries every type and stops if more than one matches. Images: exr, png, jpg, webp, tif, dpx, bmp. Video: mp4, mov, webm, mkv, avi, m4v.
- **Sequences:** mark the frame with `####`, `%04d` or `{frame}`; PD Output's `name.1001.png` is found without a mark. `start_frame` (frame number, 0 = first), `frame_count` (0 = all) and `every_nth` pick frames; gaps are skipped and listed. `sequence_mode` decides what a single numbered file loads (`shot.1002.exr` with `shot.1001.exr` next to it):
  - **auto** (default) loads the whole sequence unless one of these says it's a single image: PD Output's sidecar (a single image's own `name.json` has no `sequence`; a sequence's `name.json` names its pattern), frames of different sizes, or unpadded numbers of different lengths (`seed_1` … `seed_10`, typical of wedges). Otherwise it guesses a sequence. The info panel says what it decided and why.
  - **single file** loads just that file; **sequence** loads every file named like it.
  - A frame mark (`####`) always loads a sequence. Workflows saved with the old `sequence_from_file` switch convert on load (on → auto, off → single file).
- **Video:** `start_frame` is a frame index. `fps_from_file` (on) uses the video's rate; off, `fps` overrides it (images always use `fps`). With defaults, `video` is the file itself; otherwise the loaded frames as an in-memory VIDEO with matching audio.
- **Quality:** 16-bit PNG/TIFF and float EXR keep their precision. Alpha comes out as `mask`; EXR is un-premultiplied, and `exr_colorspace` `linear to sRGB` reverses PD Output's `sRGB to linear`.
- **Preview:** one frame shows as an image, several as a playable clip; the panel lists the pattern, frames, size, alpha, fps and sidecar.
- **EXR metadata:** for EXR, `exr_metadata` carries each frame's header attributes (everything but the structural ones), for PD Output or PD EXR Metadata Get. See [EXR metadata](#exr-metadata).
- **Tokens (optional):** `file` takes PD Output's tokens from `context` and `wedge` (e.g. `{shot}_{version}`), so a wedge can load a different file per job. A sidecar next to the media fills `context` (incoming non-empty values win).
- **Changes on disk** are picked up on the next queue; unchanged files stay cached. With context or wedge linked, the first queue after opening a workflow re-reads once.

## Wedges

A wedge turns several near-identical graphs into one: each **PD Wedge** row is an input of any type paired with a text value, and one Run queues a job per row.

1. Set `token` (e.g. `product`), link inputs to `input_1`, `input_2`... and name each row in `value_n`. Rows appear as you fill them (up to 16). A row with only text outputs the text, so prompts and numbers can be typed in.
2. Use `value` where the input would go; the row's text is also on `text`, `int` and `float`.
3. Connect `wedge` to PD Output's `wedge` input and use `{product}` or `{product_idx}` in the template.
4. Press **preview wedge** on PD Output to list every path, then Run.

Only the selected row's input is computed, the rest of the graph is cached between jobs, and every job has the same seed.

- **Several wedges** chain through `wedge` and multiply (3 products × 2 looks = 6 jobs); the first in the chain varies fastest. Wedges with the same `group` step together instead (a product image and its prompt) and need the same row count.
- **solo** runs one row number (0 = all), for a test render.
- **Checks:** above 20 jobs Run asks first. A wedge without rows, an empty solo row or a mismatched group marks the wedge and queues nothing. The preview warns about wedges not chained into PD Output, paths written by several jobs, and existing files.

Wedges are expanded by the frontend: a prompt posted to `/prompt` directly runs each wedge's first row. See [docs/wedges-headless.md](docs/wedges-headless.md).

## Video

The video nodes (**Pipedream/Video**) use ComfyUI's core `VIDEO` type, so they work with Load Video, Save Video, Create Video and other packs.

- **Only what you ask for.** PD Video To Images decodes `start_frame` … `start_frame + frame_limit × step` (fps divided by `step`, audio trimmed to match); PD Video Get Frame seeks to the nearest keyframe. `last` and negative indices find the real end even when the container's count is wrong.
- **Precision and alpha:** float32 RGB 0–1; 10/12-bit sources keep their precision. Alpha (ProRes 4444, `yuva*`, `rgba`...) comes out as `mask` (1.0 = opaque), full opacity when there is none. In-memory videos use their own alpha or the fourth channel.
- PD Images To Video encodes nothing (and has no alpha); writing happens in a save node. Out-of-range indices clamp, and `frame_index` reports the frame used. Seeking assumes a constant frame rate.

## OCIO

The OCIO nodes (**Pipedream/Color**) need OpenColorIO 2.3+.

- **config:** `$OCIO environment` (else the built-in ACES studio config), `ACES studio (built-in)`, `ACES cg (built-in)`, or `custom file` (`config_path`). The dropdowns follow the selected config; aliases and roles (`scene_linear`, `srgb_tx`) work, and names are checked when you queue.
- **PD OCIO Transform:** `in_colorspace` → `out_colorspace`, optionally through a config **look** (a named grade defined in the config; the built-in configs have one, studio configs add show looks).
- **PD OCIO Display:** `display`/`view` transform, or `inverse` back to the scene space.
- **PD OCIO Apply LUT:** any LUT file OCIO reads, from a local or network path; `inverse` is exact for 1D LUTs, approximate for 3D. The LUT sees the values as they are, so convert to its expected space first.
- **Linear spaces** such as `Linear Rec.709 (sRGB)`, `Linear Rec.2020`, `ACEScg` are in the built-in configs. If the lists show only two colourspaces, OpenColorIO is not installed.
- Float32 throughout (values outside 0–1 survive), alpha untouched; configs, processors and LUTs are cached and re-read when the file changes.

## PD Sound

Wire anything through `value` (passed on untouched), or leave it dangling.

- `play_when` **node reached** plays when the node runs, so several nodes can announce stages; **queue finished** plays once the queue drains (the error tone if a prompt failed).
- Cached nodes don't run and aren't forced to; `when_cached` also plays for them. Errors play `error_tone`, a buzzer.
- Sounds: `chime`, `happy`, `sad`, `ding`, `beeps`, `alert` (synthesized) or a `custom URL`; each node has its own sound, volume and **test sound** button. Sounds play in the tab that queued the prompt.

## EXR metadata

EXR header metadata travels through the graph as an `EXR_METADATA` stream, frame by frame:

- **In:** PD Load's `exr_metadata` output gives each loaded EXR frame's attributes (camera matrices, timecode, a renderer's or Nuke's own keys). A plate's per-frame values stay per frame.
- **Set:** PD Project Context and PD Custom Context have an `exr_metadata` output: every token becomes a string attribute named `pipedream/<token>` (`pipedream/shot`, `pipedream/version`, `pipedream/client`...). The prefix is the `exr.metadata_prefix` setting. Custom Context pairs are how you add your own keys; empty values are left out.
- **Profile:** PD Profiler's `exr_metadata` output stamps the run under `pipedream/profiler/`: budget, the peak estimate and its stage, each stage, the latent, model file paths, the measured time and VRAM peak. To feed PD Output, branch the profiler off before it (after it would be a loop). The profile changes every run, so a PD Output fed by it writes on every queue.
- **Merge:** **PD EXR Metadata Merge** combines up to 8 streams into one (a spare input appears as you connect one), frame by frame, with the same rule as PD Output: later inputs win on the same name, and per-frame tables stay per frame. Assemble a stream once and send it to several PD Outputs, or inspect it with Get.
- **Out:** PD Output's `exr metadata` inputs (exr only; a spare appears as you connect one, up to 8) are merged frame by frame, later inputs winning on the same name. A source with one table per frame writes frame N's table into frame N; a single table goes into every frame. The sidecar lists the names written.
- **Nothing unless connected:** with no `exr metadata` input connected, PD Output writes no metadata: only FFmpeg's encoder defaults (`writer`, `gamma`). So loading an EXR and writing it back out without a connection strips its metadata.
- **Inspect:** **PD EXR Metadata Get** lists every attribute with its type, marks those that vary by frame (`*`), and outputs one by `key` as `value`, `int` and `float`. `key` takes a full name or a unique last part (`shot`). `frame` picks the frame, `filter` narrows the list, and **preview** runs just the node and its inputs.

Attributes keep their EXR types (string, int, float, double, vectors, matrices, box, chromaticities, timecode, rational, keycode, string and float vectors); any other type is carried as raw bytes, so a load-and-write round trip loses nothing. Structural attributes (channels, compression, data and display windows, line order, pixel aspect) always come from the writer. Nuke shows the names as `exr/pipedream/...`.

PD Output's EXRs come from FFmpeg's encoder, which can't write custom attributes, so the header is rewritten after each frame is encoded: attributes are inserted and the chunk offset table shifted to match. The pixel data isn't touched (checked against the OpenEXR library for every compression and precision PD Output writes). Standard library only; no extra dependency.

## PD Profiler

Like a profile node in Nuke: connect `source` to anything and it reports on everything that input reads from, and nothing else, so several flows in one graph each get their own numbers. It has no outputs: put it after PD Output (on its `images`) or branch it off a flow. Core Save nodes have no outputs; branch off what feeds them.

- **profile** evaluates without queuing anything. **Queued runs** (`enabled`) add what was measured. Nothing needs typing in: the numbers come from the graph, the model files, ComfyUI's own formulas and this machine.
- **Models:** each loader's file is identified from its header (safetensors and GGUF tensor tables; no weights are loaded) with ComfyUI's own model detection, so renamed files still match. It reports parameters, data type and the bytes ComfyUI keeps in memory. LoRAs are listed. If detection fails, the name is matched instead and the report says so.
- **Latent:** the exact shape from the latent node's widgets, with ComfyUI's rounding down. A size that loses pixels (1080 high on a 16-px model decodes to 1072) or a frame count that isn't 4k+1 / 8k+1 is flagged with the values to use.
- **Memory by stage**, because ComfyUI frees each model before the next: text encode, each sampler (weights + ComfyUI's `memory_required` + latent; Wan 2.2's two experts are two stages), each VAE decode (weights + ComfyUI's decode estimate, per tile for tiled decode). Each stage reads fits / offloads (with how much) / over budget against the VRAM budget. The peak is the largest stage. RAM: model weights plus decoded frames (float32).
- **Chart:** one horizontal bar per stage, split in proportion into models, working memory and latents, running toward a dashed VRAM-budget line. Each bar is labelled with its total and how much is free or how far over. The part past the line is hatched: that's what to cut (resolution, frames, batch, weight precision) until every bar is under. The peak stage is marked, and measured times appear after a run, with a solid line for the measured peak. A RAM bar shows model weights and decoded pixels against the RAM budget. Hover a bar for its numbers.
- **Budget:** `vram_gb` / `ram_gb` emulate another machine, such as a farm node's card; 0 means this machine. **use this machine** fills in this machine's values.
- **Time:** after a run, each node's time is kept on the node (saved with the workflow). Later evaluations scale sampler times by steps and latent size. With wedges: a once-per-queue part (loaders, encoders, nodes before the wedge) plus the per-job part times the job count.
- **Wedges:** only the selected row's branch is followed (the queued row, else `solo`, else row 1). The report shows the job count and says when rows read from different branches.
- **API nodes** count as zero (they run off-site) and are flagged at the top, since their inputs leave the machine.
- **Measured runs** add the time of each upstream node (or cached), the run's VRAM peak, the models ComfyUI holds and the input received. `vram_per_node` also measures each node's VRAM peak; it resets torch's peak counter as each node starts, so it is off by default (see its tooltip).
- **EXR metadata output:** the run's profile as `pipedream/profiler/...` attributes for PD Output (see [EXR metadata](#exr-metadata)); branch the profiler off before PD Output to use it.
- **Sidecar** (`export_sidecar`): the profile as JSON after each run. Link PD Output's `path` to `path` and it is written next to the output as `<name>.profile.json` (frame number dropped). Otherwise it goes into a typed folder, or `output/pipedream_profiles/`.

Memory figures are ComfyUI's own estimates (the ones it loads and offloads by), not a guarantee. Text encoder activations and custom samplers with their own memory handling aren't modelled. Without a GPU, the profile uses ComfyUI's GPU formulas and 16-bit data types.

How each number is worked out, the sidecar format and use without the browser: [docs/profiler.md](docs/profiler.md).

## Alpha and premultiplication

Inside ComfyUI, IMAGE + MASK are **straight** and every Pipedream mask uses **1.0 = opaque**. Pipedream never premultiplies inside the graph; files follow their format's convention, recorded in the sidecar:

| Format | Written as | Why |
|--------|-----------|-----|
| PNG, WebP | Straight | Their specs define straight alpha. |
| ProRes 4444 | Straight | No reliable flag in the bitstream; interpret Pipedream ProRes as straight in AE, Nuke, Resolve. |
| EXR | Premultiplied | The OpenEXR spec defines RGBA as premultiplied; RGB is multiplied after any sRGB-to-linear decode. PD Load divides it back. |

Core ComfyUI uses the opposite mask polarity: Load Image's mask is `1 - alpha`, and Join Image with Alpha inverts its mask. Put an **Invert Mask** between core masks and Pipedream (either direction). For images without alpha, core Load Image gives a 64×64 empty mask; leave PD Output's `alpha` unconnected then.

## Facility / user defaults

Studios can set defaults (templates, network roots, formats, frame numbering, token delimiters, OCIO config...) in TOML, layered lowest to highest:

1. Built-in defaults.
2. **User:** `pipedream.toml` in the pack folder (ignored by git).
3. **Facility:** the file in the `PIPEDREAM_COMFYUI_CONFIG` environment variable.

A key applies when present and valid; invalid values, unknown keys and syntax errors print one `[Pipedream] Settings warning:` and are ignored. Files are read at startup. [`pipedream.example.toml`](pipedream.example.toml) lists every key with its default and description; copy it and uncomment what you need:

```toml
[output]
path_mode = "absolute"
base_path = '\\server\shows'          # single quotes keep backslashes
template = "{project}/{shot}/comp/{shot}_{version}"
format = "exr"

[tokens.extra]
facility = "FacilityName"

[ocio]
config = "custom file"
config_path = '\\server\pipeline\ocio\config.ocio'
```

| Table | Keys |
|-------|------|
| `[output]` | `template`, `path_mode`, `base_path`, `format`, `fps`, `crf`, `create_dirs`, `overwrite`, `save_metadata`, `prores_profile` |
| `[load]` | `file`, `path_mode`, `base_path` |
| `[exr]` | `precision`, `compression`, `colorspace`, `metadata_prefix` |
| `[sequence]` | `frame_padding`, `start_frame`, `frame_separator` |
| `[tokens]` | `open`, `close`, `date_format`, `time_format` |
| `[tokens.extra]` | Any fixed tokens (`frame` is reserved) |
| `[tokens_to_string]` | `template` |
| `[project]` | `version`, `auto_increment_version` |
| `[ocio]` | `config`, `config_path`, `in_colorspace`, `out_colorspace`, `display`, `view` |
| `[sound]` | `sound`, `volume`, `play_when` |
| `[profiler]` | `enabled`, `vram_gb`, `ram_gb`, `vram_per_node`, `export_sidecar` |

New nodes start with these values (saved workflows keep theirs), and inputs missing from an API prompt use them. Delimiters, date/time formats, extra tokens and the frame separator apply wherever tokens resolve. The token panel and sidecar name the settings files in use.

To deploy on Windows, set the variable machine-wide (Group Policy Preferences or a script), then restart ComfyUI:

```bat
setx PIPEDREAM_COMFYUI_CONFIG "\\server\pipeline\comfyui\pipedream.toml" /M
```

For maintainers: `core/settings.py` is the single source for validation and the example file. After changing it, run `python -m core.settings > pipedream.example.toml` and `python -m unittest discover -s tests`.

## Compatibility

Classic ComfyUI node classes (`NODE_CLASS_MAPPINGS`), which current ComfyUI loads alongside V3 nodes. Built for the Nodes 2.0 frontend first, and tested on the classic canvas. PD Profiler's run measurements use ComfyUI's per-prompt progress registry (`comfy_execution.progress`); on versions without it the profiler still evaluates, without measurements.

## License

MIT — see [LICENSE](LICENSE).
