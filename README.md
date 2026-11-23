# ComfyUI-Pipedream

Production pipeline utility nodes for ComfyUI — output naming, network paths, token strings, wedge iteration, and multi-input switching.

Pipedream is not a visual effects node pack. It is plumbing.

## Installation

Every command below uses full paths, so it works from any folder. Restart ComfyUI afterwards; the nodes appear under the **Pipedream** category.

The only extra dependency is [OpenColorIO](https://opencolorio.org) (`opencolorio`, BSD-3) for the OCIO nodes. Without it every other node works, and the OCIO nodes explain how to install it. Video and EXR use PyAV, which ComfyUI already installs.

### ComfyUI Desktop (Windows)

Desktop keeps each instance (environment) in `%LOCALAPPDATA%\Comfy-Desktop\ComfyUI-Installs\<instance name>`. Open the instance in Desktop, go to its **Terminal** tab (PowerShell, with that instance's Python already active), and paste:

```powershell
$instance = "ComfyUI"   # the instance name shown in Desktop's instance list
$nodes = "$env:LOCALAPPDATA\Comfy-Desktop\ComfyUI-Installs\$instance\ComfyUI\custom_nodes"
git clone https://github.com/theonlyaaron/comfyui-pipedream.git "$nodes\comfyui-pipedream"
python -m pip install -r "$nodes\comfyui-pipedream\requirements.txt"
```

Change `$instance` if your instance has another name (e.g. `"PipeDream"`). If `git clone` says the path does not exist, the instance folder is named differently: check `dir "$env:LOCALAPPDATA\Comfy-Desktop\ComfyUI-Installs"`.

> Older Desktop versions (before instances) keep custom nodes in `Documents\ComfyUI\custom_nodes` instead; use `$nodes = "$env:USERPROFILE\Documents\ComfyUI\custom_nodes"` with the same last two lines.

### ComfyUI portable (Windows)

Set `$portable` to your `ComfyUI_windows_portable` folder, then paste into PowerShell:

```powershell
$portable = "C:\ComfyUI_windows_portable"   # the folder holding run_nvidia_gpu.bat
git clone https://github.com/theonlyaaron/comfyui-pipedream.git "$portable\ComfyUI\custom_nodes\comfyui-pipedream"
& "$portable\python_embeded\python.exe" -m pip install -r "$portable\ComfyUI\custom_nodes\comfyui-pipedream\requirements.txt"
```

### Manual install (Linux, macOS, Windows git clone)

Set `COMFY` to the folder that holds ComfyUI's `main.py`, activate the Python environment you run ComfyUI with, then paste:

```bash
COMFY=~/ComfyUI   # the folder holding main.py
git clone https://github.com/theonlyaaron/comfyui-pipedream.git "$COMFY/custom_nodes/comfyui-pipedream"
python -m pip install -r "$COMFY/custom_nodes/comfyui-pipedream/requirements.txt"
```

### Updating, or trying a branch

Restart ComfyUI and refresh the browser after any of these.

ComfyUI Desktop (PowerShell, set `$instance` as above):

```powershell
$instance = "ComfyUI"
$pack = "$env:LOCALAPPDATA\Comfy-Desktop\ComfyUI-Installs\$instance\ComfyUI\custom_nodes\comfyui-pipedream"
git -C $pack pull
```

Portable (PowerShell):

```powershell
$pack = "C:\ComfyUI_windows_portable\ComfyUI\custom_nodes\comfyui-pipedream"
git -C $pack pull
```

Manual install (bash):

```bash
pack=~/ComfyUI/custom_nodes/comfyui-pipedream
git -C "$pack" pull
```

To test a development branch (e.g. `wedges`), set `$pack` / `pack` as above, then:

```bash
git -C "$pack" fetch origin
git -C "$pack" checkout wedges
git -C "$pack" pull
```

and `git -C "$pack" checkout main` to go back. These lines work in both PowerShell and bash.

### Checking it loaded

ComfyUI's console lists `comfyui-pipedream` under "Import times for custom nodes" at startup. If it says `IMPORT FAILED`, the lines above it give the reason. Make sure only one copy of the pack is installed per ComfyUI: an old copy in another `custom_nodes` folder (or a second Desktop instance) is a common reason for "my changes don't show up".

## Nodes

All nodes appear under the **Pipedream** category with a 💭 prefix.

| Node | Description |
|------|-------------|
| **💭 PD Custom Context** | Adds user-defined key/value token pairs to a context. Starts with one empty pair; a new pair appears as each name is filled (up to 10). Chain after Project Context for custom tokens like `{task}`, `{department}`. |
| **💭 PD Project Context** | Top-level metadata node (project, sequence, shot, version, user). Accepts an incoming context for override chaining. Supports auto-incrementing version and version reset buttons (see [Versioning](#versioning)). |
| **💭 PD Token String** | Resolves a token template to a string (for prompts, filenames or other nodes' paths), using an optional context from Project/Custom Context. |
| **💭 PD Output** | Resolves a token template and writes images (png/exr/jpg/webp) or video (mp4/mov/webm) to ComfyUI's output directory (`relative`) or an absolute/UNC path (`absolute`). Writes a sidecar JSON, previews what was written, passes the images through, and shows available tokens after execution. **preview wedge** lists every wedge job's path without running the graph. |
| **💭 PD Load** | Loads an image, image sequence or video from ComfyUI's input folder or any local/network folder. Paste a full file path into it and it fills in the rest. Outputs images, mask (alpha), fps, frame count, first frame, path, a context with PD Output's sidecar tokens, a `VIDEO` and audio; previews video as a playable clip. `file` can use tokens to read back what PD Output wrote. See [PD Load](#pd-load). |
| **💭 PD Switch** | Routes one of N wildcard inputs to a single output. Inputs auto-grow when connected (2–8). |
| **💭 PD Wedge** | Rows of input (any type) + text value; each job runs one row. Only the selected input is computed. Outputs the row's input (or its text), the text as STRING/INT/FLOAT, and a `WEDGE` chain for further wedges and PD Output. `group` steps wedges together; `solo` runs one row. See [Wedges](#wedges). |
| **💭 PD Images To Video** | Wraps an image batch (plus optional audio) as an in-memory `VIDEO` at a given fps. Outputs the video and its frame count. |
| **💭 PD Video To Images** | Decodes a `VIDEO` to images, mask (alpha), audio, fps and frame count. Optional start frame, frame limit and every-Nth step decode only what you ask for. |
| **💭 PD Video Get Frame** | Grabs one frame and its mask (alpha) from a `VIDEO` (first, last or index; negative counts from the end). Seeks instead of decoding the whole clip. |
| **💭 PD Image From Batch** | Picks one image from a batch (first, last or index; negative counts from the end), and the same frame of an optional mask. |
| **💭 PD OCIO Transform** | Converts images between two OpenColorIO colorspaces, optionally through a look. See [OCIO](#ocio). |
| **💭 PD OCIO Display** | Applies an OpenColorIO display/view transform (e.g. the ACES output transform for sRGB), or its inverse. See [OCIO](#ocio). |
| **💭 PD OCIO Apply LUT** | Applies a LUT file (.cube, .3dl, .csp, .spi1d/.spi3d, CLF/CTF, CDL...) from a local or network path, forward or inverse. |
| **💭 PD Sound** | Plays a short browser sound when this point of the flow is reached, or when the whole queue finishes. Passes any value straight through, so it can sit inline or dangle at the end. See [PD Sound](#pd-sound). |

## Video

The video nodes live under **Pipedream/Video** and use ComfyUI's core `VIDEO` type, so they plug straight into Load Video, Save Video, Create Video and other packs. They overlap with core **Create Video** / **Get Video Components** on purpose: these are Pipedream-owned versions we can extend, with a few practical differences:

- **Range decoding.** PD Video To Images decodes only `start_frame` … `start_frame + frame_limit × step`, keeping every `step`-th frame, instead of loading the whole clip. That matters at 1080p, where each float32 frame is about 25 MB. Output fps is divided by `step`, and the audio is cut to the same time span, so the two stay in sync.
- **Single frames without a full decode.** PD Video Get Frame seeks to the nearest keyframe before the target and decodes forward from there. `last` and negative indices find the real end of the stream, even when the container's frame count is wrong. Videos that are already in memory (e.g. from Create Video or PD Images To Video) are indexed directly.
- **Last / negative indices.** PD Image From Batch does the same for image batches; core Image From Batch has no "last" option and no negative indices.
- **Nothing written to disk.** PD Images To Video returns an in-memory video. Encoding only happens when a save node runs.

Notes:

- Images come out as float32 RGB in 0–1. 8-bit sources are converted through `rgb24`, and 10/12-bit sources through `rgb48le`, so they keep their precision.
- **Alpha comes out as a MASK.** PD Video To Images and PD Video Get Frame have a `mask` output (1.0 = opaque). Streams with an alpha plane (ProRes 4444, which ffmpeg decodes as `yuva444p12le`, and other `yuva*`, `rgba` or `gbrap*` formats) are decoded through `rgba64le` (or `rgba` for 8-bit, `gbrapf32le` for float), so alpha keeps its full precision. It is decoded in the same pass as the images, with the same start frame, limit and step. Without alpha, the mask is full opacity at the same size and count, so a graph wired for alpha keeps working with any clip. See [Alpha and premultiplication](#alpha-and-premultiplication).
- In-memory videos (from PD Images To Video, Create Video, ...) use the alpha they carry: the video's own alpha (recent ComfyUI) or the fourth channel of RGBA images. PD Images To Video has no alpha input, so its videos give full opacity. To write images with alpha, connect the images and the mask to PD Output directly.
- PD Image From Batch's optional `mask` input takes one frame (used for every image) or one per image, and the `mask` output is the same frame as `image`. Without a mask, it outputs the fourth channel of RGBA images, else full opacity.
- PD Video Get Frame and PD Image From Batch show the `index` widget only when `mode` is `index` (or when it is linked).
- Out-of-range indices are clamped to the first or last frame. `frame_index` reports the frame that was actually used.
- PD Video Get Frame's `frame_count` is exact for `last` and negative indices. For `first` and positive indices it comes from container metadata.
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

## OCIO

The OCIO nodes live under **Pipedream/Color** and use [OpenColorIO](https://opencolorio.org) 2.3 or newer.

- **config** picks the OCIO config: `$OCIO environment` (the config in the `OCIO` environment variable, or the built-in ACES studio config when it is unset), `ACES studio (built-in)` (`ocio://studio-config-latest`), `ACES cg (built-in)` (`ocio://cg-config-latest`) or `custom file`, which reads `config_path` (shown only for that choice).
- **PD OCIO Transform** converts `in_colorspace` to `out_colorspace`. Pick a `look` to apply one of the config's looks on the way (`inverse_look` applies its inverse). Defaults: `ACEScg` (or the config's `scene_linear` role) to `sRGB - Texture` (or its `color_picking` role).
- **PD OCIO Display** applies the `display`/`view` transform to an image in `in_colorspace`; `inverse` goes from the display back to the scene colorspace. Defaults are the config's default display and view.
- **PD OCIO Apply LUT** applies a LUT file from `lut_path` (local or network): .cube, .3dl, .csp, .spi1d/.spi3d, CLF/CTF, CDL and the other formats OpenColorIO reads. The LUT sees the values as they are, so convert to the colorspace it was built for first (e.g. PD OCIO Transform to a log space, LUT, then back). `interpolation` is best (tetrahedral), tetrahedral, linear or nearest; `inverse` inverts it (exact for 1D LUTs, approximate for 3D). An edited LUT file is re-read.
- **Looks** are named grades defined inside an OCIO config (often built from LUT files). The built-in ACES configs have one (ACES 1.3 gamut compression); studio configs usually add show looks. For a LUT that is not part of a config, use PD OCIO Apply LUT.
- **Linear spaces:** the built-in configs include `Linear Rec.709 (sRGB)`, `Linear P3-D65`, `Linear Rec.2020`, `ACEScg`, `ACES2065-1` and camera linear spaces. If the lists only show two colourspaces, OpenColorIO is not installed (see [Installation](#installation)).
- Images are processed as float32: values outside 0–1 survive linear-to-linear conversions, and alpha (a 4th channel) passes through untouched.
- The dropdowns follow the selected config: changing `config` or `config_path` reloads the colorspace, display, view and look lists, and `view` follows `display`. Values that still exist are kept, others reset to the config's defaults. Colorspace aliases and role names (e.g. `srgb_tx`, `scene_linear`) are accepted too.
- Names are validated against the selected config when you queue, so a workflow saved with a custom config loads and runs even though its names are not in the default lists.
- Loaded configs and processors are cached. A custom config file is reloaded when it changes on disk.

## Token Reference

Tokens are `{name}` placeholders resolved by output nodes and PD Token String. The delimiters, the date/time formats and extra fixed tokens can be configured (see [Facility / user defaults](#facility--user-defaults)):

| Token | Source |
|-------|--------|
| `{project}` | Project Context |
| `{sequence}` | Project Context |
| `{shot}` | Project Context |
| `{version}` | Project Context |
| `{user}` | Project Context |
| `{date}` | Auto: YYYYMMDD |
| `{time}` | Auto: HHMMSS |
| `{frame}` | Frame number in PD Output image sequences (`start_frame`, `frame_padding`); `####` in PD Token String |
| `{<token>}`, `{<token>_idx}` | PD Wedge (via PD Output's `wedge` input): the selected row's text and its position (`000`, `001`...) |
| `{wedge_idx}`, `{wedge_total}` | PD Wedge: the job number and the number of jobs |
| `{<custom>}` | Any key added via PD Custom Context |
| `{<extra>}` | Any `[tokens.extra]` setting (context values override it) |

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

- **reset version** — resets that node's version to its first version, keeping its prefix and padding (`v017` → `v001`, `take_0042` → `take_0001`). An empty or non-numeric version becomes the configured default (`project.version` in the [facility/user settings](#facility--user-defaults), e.g. `take_0001`), or `v001` when none is set.
- **reset all versions in graph** — after a confirmation, resets every PD Project Context in the workflow, including inside subgraphs.

The global reset is also available from the canvas right-click menu as **Pipedream: reset all versions** (recent ComfyUI frontends only).

## PD Output

| Input / Output | Notes |
|----------------|-------|
| `images` / `video` (inputs) | Connect at least one. A connected `video` (ComfyUI VIDEO) is written instead of `images`, with its own frame rate and audio. With an image format, its frames are written as an image sequence. |
| `alpha` (input) | Optional. Takes an `IMAGE`, `MASK` or `VIDEO` (one socket typed `IMAGE,MASK,VIDEO`, so other types can't connect). A MASK is used as is (1.0 = opaque; put an Invert Mask after core Load Image's mask). An IMAGE or a VIDEO's frames give their Rec.709 luminance, so a grey matte keeps its exact values. It needs one frame (used for every frame) or as many frames as the source, at the same size; anything else is an error. See [Alpha](#alpha). |
| `path_mode` | `relative` writes under ComfyUI's output directory. `absolute` writes under `base_path` (an absolute or UNC path). |
| `template` | The output path without an extension. `{frame}` sets where the frame number goes. See [Image sequences](#image-sequences). |
| `format` | Images, one file per frame: `png`, `exr`, `jpg`, `webp`. Video, one file per batch: `mp4` (H.264), `mov` (ProRes), `webm` (VP9). |
| `start_frame`, `frame_padding` | Image formats only. The first frame number (default `1001`, the usual VFX start, which leaves room for handles before frame 1000) and its digit count (default 4). |
| `fps`, `crf` | Video only. `fps` applies to `images` (a VIDEO keeps its own rate). `crf` sets the quality for mp4/webm (lower is better). ProRes ignores it. |
| `prores_profile` | mov only. `auto` (default) writes ProRes 4444 with alpha when there is an alpha, and ProRes 422 HQ otherwise. `422 HQ` never writes alpha. `4444` is 4:4:4 10-bit, with alpha when there is one. |
| `exr_precision`, `exr_compression` | EXR only. Precision is `half` (default) or `float`. Compression is `zip` (default), `zips`, `rle` or `none`. EXR keeps float values unclipped. |
| `exr_colorspace` | EXR only. `as is` (default) writes the values unchanged. `sRGB to linear` decodes sRGB-encoded images, which covers most generated and loaded images, to linear light with the piecewise sRGB curve: `v / 12.92` up to 0.04045, then `((v + 0.055) / 1.055) ^ 2.4`. The power segment carries on above 1.0 (2.0 becomes about 5.7), and negative values are mirrored. Alpha is never converted. This is plain math with no OCIO; for other colorspaces, put [PD OCIO Transform](#ocio) before PD Output and leave this on `as is`. |
| `overwrite` | When off, nothing is written if the file, or any frame of the sequence, already exists. The console says so. This prevents a sequence that mixes old and new frames. |
| `save_metadata` | Writes a sidecar `.json` next to the output, with the template, resolved tokens and context, written files, frame range and `#` pattern, alpha (`written`, `source`, `premultiplied`), timestamp, the ComfyUI prompt and the EXR/video settings (`colorspace`, `prores_profile`). The workflow is not embedded in the image files. |
| `path` (output) | The first file written (the first frame of a sequence), or the video file. |
| `path_sidecar` (output) | The sidecar JSON path. Empty when `save_metadata` is off. |
| `path_all` (output) | Every written file, one per line (every frame of a sequence). |
| `images` (output) | The input images passed through (the VIDEO's frames when only a VIDEO is connected). |
| `video` (output) | The written video as a ComfyUI VIDEO, for Save Video, Preview Video and other video nodes. Only shown for video formats. |

### Image sequences

Image formats write one file per frame.

- **With `{frame}`** in the template, the frame number goes there: `{shot}/{shot}_{version}.{frame}` writes `sh010_v001.1001.exr`, `sh010_v001.1002.exr`, and so on. `{frame}` can also appear in folder names.
- **Without `{frame}`**, a batch of more than one frame gets the VFX-style `.1001` before the extension (`sh010_v001.1001.png`). The separator can be set to `_` or `-` with `sequence.frame_separator`.
- **A single image** (batch of 1) gets no frame number unless the template uses `{frame}`, in which case it is numbered `start_frame`.
- **Video formats** ignore `{frame}`. It is removed along with one `.`, `_` or `-` just before it, so `clip.{frame}` writes `clip.mp4`.

The sidecar of a sequence is named after the file name without the frame number (`sh010_v001.json`). It records `sequence.first`, `last`, `count`, `padding` and `pattern` (e.g. `…/sh010_v001.####.exr`). After a run, the token reference shows the frame range that `{frame}` covered.

### Alpha

Alpha is written to `png` and `webp` (8-bit RGBA, straight), `exr` (RGBA, premultiplied; alpha itself is written as is: linear, unclipped and never colour-converted) and `mov` as ProRes 4444 (`prores_ks` profile 4, `yuva444p10le`, straight). When `alpha` is not connected, the fourth channel of 4-channel images is used as alpha. See [Alpha and premultiplication](#alpha-and-premultiplication) for why EXR differs.

`jpg`, `mp4`, `webm` and ProRes 422 HQ can't store alpha. If `alpha` is connected anyway, the file is written without it, a warning is printed to the console, and the sidecar records `"alpha": {"written": false}`. A warning was chosen over an error so that switching to a review format (e.g. mp4) doesn't break a graph that also writes alpha.

### Hidden widgets and sockets

Widgets that don't apply to the chosen mode and format are hidden. Sockets are hidden too: the `alpha` input for formats without alpha, and the `video` output for image formats. A linked widget or socket is never hidden. Frontend 1.59 has no per-slot hidden flag, so sockets are hidden by removing them and added back when they apply again. This is safe because inputs are matched by name, and `video` is the last output, so removing it shifts no other output's index. A saved workflow leaves out a hidden socket, and it comes back when the workflow is loaded with a format that uses it. The `images` output is always shown, since passing images through is useful for every format.

A preview of what was written appears under the node, with one entry per frame for sequences. Images and mp4/webm inside ComfyUI's output directory are shown directly. EXR, ProRes and files outside the output directory get a downscaled preview in ComfyUI's temp directory (an animated WebP for video).

Video and EXR are encoded with PyAV, which is part of ComfyUI's requirements, so you don't need to install `ffmpeg` or any extra package. Audio from a connected VIDEO is muxed as AAC (mp4/mov) or Opus (webm). Odd frame sizes are padded by one pixel to the even size the video codecs need. EXR uses the EXR encoder bundled in PyAV (scanline, RGB or RGBA, half or float; no PIZ/DWA compression). Note that ffmpeg's ProRes decoder reports 4444 files as `yuva444p12le` when reading them back. That is how the decoder works; the files are encoded from 10-bit `yuva444p10le`.


## PD Load

PD Load reads an image, image sequence or video from a local or network folder, or reads back what PD Output wrote.

- **Quick start:** copy a file's path (in Windows Explorer, shift+right click → *Copy as path*) and paste it into `file` or `base_path`. The quotes are removed, the path is split into `base_path` (the folder) and `file` (the name), `path_mode` switches to `absolute`, and the file loads. **load** (or the run button in the selection toolbar) runs just this node to check what it loads.
- **Where:** `path_mode` `relative` reads from ComfyUI's `input` folder; `absolute` reads from `base_path` (`C:\Shots`, `/mnt/shows`, `\\server\shows` or `//server/shows`).
- **What:** `file` can include the extension (`plate.exr`) or leave it to `format`. `auto` looks for every supported type and stops with an error if more than one matches. Images: exr, png, jpg, webp, tif, dpx, bmp. Video: mp4, mov, webm, mkv, avi, m4v.
- **Sequences:** mark the frame number with `####`, `%04d` or `{frame}` (`shot.####.exr`). Without a mark, a numbered file next to the name is found too, which is how PD Output names sequences (`name.1001.png`). `start_frame` (frame number, 0 = first on disk), `frame_count` (0 = all) and `every_nth` pick the frames; missing frames in the range are skipped and listed in the info panel.
- **Video:** `start_frame` is a frame index. `fps_from_file` (on by default) uses the video's frame rate; turn it off to use `fps` as an override. Images and sequences use `fps`. With the defaults, `video` is the file itself (no re-encode downstream); with a range or an fps override it is the loaded frames as an in-memory `VIDEO`, with the matching audio.
- **Preview:** a single image shows as an image; a sequence or video shows as a playable clip (downscaled, with audio) so you can scrub through what was loaded. The info panel lists the pattern, frame range, size, alpha, fps and sidecar.
- **Precision and alpha:** everything decodes with PyAV, so 16-bit PNG/TIFF and float EXR keep their precision. Alpha comes out as `mask` (1.0 = opaque). EXR is premultiplied by its spec, so its RGB is divided by alpha on load (PD Output multiplies on write); `exr_colorspace` `linear to sRGB` reverses PD Output's `sRGB to linear`.
- **Tokens (optional):** `file` takes the same tokens as PD Output's template, from a connected `context` and `wedge`. `{shot}_{version}` with `base_path` set to the shot folder finds the file PD Output wrote for that shot, and a wedge can load a different file per job. When PD Output's sidecar JSON sits next to the media, its tokens come out of `context`, with the incoming context's non-empty values on top.
- **Changes on disk** (new frames, overwritten files) are picked up on the next queue; unchanged files stay cached, so the rest of the graph does not re-run. With a context or wedge linked, the first queue after loading a workflow re-reads once.
- `fps_from_file` (image formats), `exr_colorspace` (formats other than exr/auto) and the `audio` output (image formats) are hidden when they do not apply.

## Wedges

A wedge turns several near-identical graphs into one. Each **PD Wedge** row is an input of any type (image, prompt, model, video, LoRA...) paired with a text value; one Queue click runs the graph once per row, and the row's text becomes a file name token on PD Output.

1. Set `token` (e.g. `product`). Link inputs to `input_1`, `input_2`... and name each row in `value_n`. Rows appear as you use them (up to 16); a row with only text uses the text as its value, so prompts and numbers can be typed in.
2. Use the wedge's `value` where the input would go. The row's text is also on `text`, `int` and `float` (for seeds, strengths, steps...).
3. Connect the wedge's `wedge` output to PD Output's `wedge` input and use `{product}` (row text) or `{product_idx}` (`000`, `001`...) in the template. `{wedge_idx}` is the job number, `{wedge_total}` the job count.
4. Press **preview wedge** on PD Output to list every job's path without running the graph, then Run.

Only the selected row's input is computed, and ComfyUI's cache keeps everything else (base image, model, encoded prompts) between jobs. The prompt is built once per click, so the seed is the same in every job.

**Several wedges.** Chain wedges through their `wedge` input; the last one goes to PD Output. They multiply: 3 products × 2 looks = 6 jobs. The first wedge in the chain varies fastest. Wedges with the same `group` step together instead (row 1 with row 1...), e.g. a product image and its prompt, and need the same number of rows.

**Solo.** `solo` on a wedge runs only that row number (0: all rows), for a test render.

**Checks.** Above 20 jobs, Run asks before queueing. A wedge without rows, an empty solo row or a group with different row counts stops the queue and marks the wedge. The preview warns when a wedge that changes the image is not chained into PD Output (its jobs would overwrite each other), when jobs share a path, and when files exist with overwrite off.

Wedges are expanded by the frontend; a prompt posted straight to `/prompt` runs each wedge's first row once. See [docs/wedges-headless.md](docs/wedges-headless.md). Example workflows are in [workflows/](workflows/).

## Alpha and premultiplication

Pipedream has no premultiplication setting. It uses fixed conventions, recorded in the PD Output sidecar (`"alpha": {"written": true, "source": "mask", "premultiplied": false}`).

**Inside ComfyUI, IMAGE + MASK are straight (unpremultiplied).** RGB is the colour of the surface and the MASK says how opaque it is, with 1.0 = opaque and 0.0 = transparent. This is how ComfyUI images work (Load Image gives straight RGB from a PNG), so Pipedream never premultiplies or unpremultiplies inside the graph. Every Pipedream `mask` output and PD Output's `alpha` input use 1.0 = opaque.

| Format | Written as | Why |
|--------|-----------|-----|
| PNG, WebP | Straight | The PNG and WebP specs define straight alpha. Written as is. |
| ProRes 4444 (`mov`) | Straight | The ProRes bitstream has no reliable premultiplied/straight flag, and tools differ (After Effects asks on import, some exporters default to premultiplied). Pipedream picks straight: interpret Pipedream ProRes 4444 files as **straight** in After Effects, Nuke, Resolve and Final Cut Pro. |
| EXR | Premultiplied | The OpenEXR spec defines RGBA as premultiplied (associated alpha), and Nuke and other compositors expect that. PD Output multiplies RGB by alpha. With `exr_colorspace` = `sRGB to linear`, the decode happens first, on the straight values, then RGB is multiplied. EXR without alpha is unchanged. |

Reading: PD Video To Images and PD Video Get Frame assume ProRes 4444 (and any other video with alpha) is straight and pass RGB through unchanged, so a ProRes 4444 written by PD Output reads back with the same RGB and alpha. If a file was exported premultiplied, divide RGB by the mask yourself.

PD Images To Video has no alpha input and makes RGB-only videos. Connect images and a mask to PD Output to write alpha.

**Core ComfyUI uses the opposite mask polarity.** Core Load Image outputs its MASK as `1 - alpha` (1 = transparent), and core Split Image with Alpha does the same. Core Join Image with Alpha inverts its mask input (it stores `1 - mask` as alpha). Pipedream uses 1 = opaque, so:

- Core Load Image's mask → Pipedream (PD Output `alpha`, PD Image From Batch `mask`): put an **Invert Mask** in between.
- A Pipedream `mask` → core Join Image with Alpha: also put an **Invert Mask** in between.
- Core Load Image's image → Join Image with Alpha (with Load Image's own mask) → PD Output `images` is already correct: the fourth channel is the real alpha.
- For an image without alpha, core Load Image outputs a 64×64 mask of zeros, not one the size of the image. PD Output rejects it for its size, so leave `alpha` unconnected in that case (or Invert Mask and resize it).

## Facility / user defaults

A studio can deploy Pipedream with its own defaults (output template, network root, formats, frame numbering, token delimiters, OCIO config, ...) from a TOML file, without touching the code. Settings are layered, lowest to highest:

1. **Built-in** defaults (what you get with no files).
2. **User** file: `pipedream.toml` in the pack folder (`ComfyUI/custom_nodes/comfyui-pipedream/pipedream.toml`; ignored by git).
3. **Facility** file: the path in the `PIPEDREAM_COMFYUI_CONFIG` environment variable.

A key only overrides when it is present and valid (right type, allowed value or range); missing keys fall through to the layer below. An invalid value, an unknown key (to catch typos), a TOML syntax error, or a `PIPEDREAM_COMFYUI_CONFIG` that points at a missing file prints one `[Pipedream] Settings warning:` line in the ComfyUI console naming the file, key and problem, and that key (or file) is ignored.

[`pipedream.example.toml`](pipedream.example.toml) lists every key with its built-in default commented out and a description: copy it, then uncomment and edit only the lines you want. For example:

```toml
[output]
path_mode = "absolute"
base_path = '\\server\shows'          # single quotes keep backslashes
template = "{project}/{shot}/comp/{shot}_{version}"
format = "exr"

[sequence]
start_frame = 1001
frame_separator = "_"                 # name_1001.exr

[tokens.extra]
facility = "FaciltyName"
show_root = "//nas/shows"

[ocio]
config = "custom file"
config_path = '\\server\pipeline\ocio\config.ocio'
```

| Table | Keys |
|-------|------|
| `[output]` | `template`, `path_mode`, `base_path`, `format`, `fps` (also PD Images To Video), `crf`, `create_dirs`, `overwrite`, `save_metadata`, `prores_profile` |
| `[load]` | `file`, `path_mode`, `base_path` (PD Load) |
| `[exr]` | `precision`, `compression`, `colorspace` |
| `[sequence]` | `frame_padding` (also PD Token String), `start_frame`, `frame_separator` (`.`, `_` or `-`: the separator in `name.1001.exr` when the template has no `{frame}`) |
| `[tokens]` | `open`, `close` (token delimiters, default `{` `}`; non-empty, different, no letters/digits/`_`/spaces), `date_format`, `time_format` (strftime) |
| `[tokens.extra]` | Any fixed tokens, available to every template. Context values (Project/Custom Context) override them. `frame` is reserved. |
| `[token_string]` | `template` (PD Token String) |
| `[project]` | `version`, `auto_increment_version` (PD Project Context) |
| `[ocio]` | `config`, `config_path`, `in_colorspace`, `out_colorspace`, `display`, `view`. Names the default config does not have warn once and fall back to the config's defaults. |
| `[sound]` | `sound`, `volume`, `play_when` (PD Sound) |

How the settings apply:

- **Widget defaults.** New nodes start with the configured values. Nodes in saved workflows keep their saved values. Inputs left out of an API prompt also use the settings.
- **Server-side behaviour.** Token delimiters, date/time formats, extra tokens and the frame separator apply wherever tokens are resolved (PD Output, PD Token String). With custom delimiters, the built-in templates switch to them (unless you set the template too), and `{...}` becomes plain text.
- **Traceability.** The PD Output token reference ends with the loaded files (`settings: facility \\server\pipeline\comfyui\pipedream.toml, user (none)`), and the sidecar JSON records them under `settings.sources`.
- **Restart needed.** Files are read once, when ComfyUI starts. Restart ComfyUI after editing a file or changing `PIPEDREAM_COMFYUI_CONFIG`.

**Facility deployment (Windows).** Keep one file on the pipeline share and set the variable machine-wide on every workstation and render node, e.g. with a Group Policy Preference (Computer Configuration > Preferences > Windows Settings > Environment, a System variable) or from a deployment script:

```bat
setx PIPEDREAM_COMFYUI_CONFIG "\\server\pipeline\comfyui\pipedream.toml" /M
```

ComfyUI started after that (a new session or service restart) picks it up. On Linux/macOS, export it in the environment that launches ComfyUI (`export PIPEDREAM_COMFYUI_CONFIG=/mnt/pipeline/comfyui/pipedream.toml`). Artists can still keep personal tweaks in the user file; the facility file wins for every key it sets.

TOML is read with Python's built-in `tomllib` (3.11+, which current ComfyUI uses), or the `tomli` package if installed on older Python; with neither, a warning is printed and the built-ins are used. No extra dependency.

For maintainers: the schema in `core/settings.py` is the single source for validation, the docs above and the example file. After changing it, regenerate the example with `python -m core.settings > pipedream.example.toml` (from the pack folder) and run `python -m unittest discover -s tests`, which also checks the example is in sync.

## Compatibility

Pipedream nodes are classic ComfyUI node classes registered through `NODE_CLASS_MAPPINGS`, which current ComfyUI loads alongside V3 (`comfy_api`) nodes. A future move to V3 would port the nodes directly.

All nodes are built and tested for the Nodes 2.0 (Vue) frontend first, and also work on the classic canvas.

**Note:** Node display names use a 💭 emoji prefix. On Windows systems with older console codepages (cp1252, cp932), the emoji is automatically omitted to prevent encoding errors.

## License

MIT — see [LICENSE](LICENSE).
