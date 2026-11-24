# Changelog

## 0.2.0 (unreleased)

### PD Output and PD Load fixes
- PD Output: **Explore Output** button shows the last written file in
  Explorer/Finder; the path is saved with the workflow
- PD Output: the sidecar stores the workflow, and dropping a sidecar on
  ComfyUI reopens it (older sidecars open from their API prompt) instead of
  failing with "e is not iterable"
- PD Load: `sequence_from_file` leaves numbered files of different sizes
  (photos) as single images instead of failing on the size check

### Workflows, docs and cleanup
- Example workflows 01 (output basics), 02 (load and read back), 03 (video
  utilities) and 04 (colour with OCIO) run without a model, using ComfyUI's
  `input/example.png`; 05 and 06 (wedges) are unchanged
- README tightened; node names stay on one line in the table
- PD Load: a full path in `file` (e.g. PD Output's `path`) is used as is,
  whatever `path_mode` and `base_path` say. `sequence_from_file` is an
  optional input, so API prompts without it keep working
- PD Output previews ProRes and other video it cannot show directly as a
  playable mp4 (was an animated WebP), the same as PD Load
- Shared code: `core/paths.py` (frame mark, root folder and inside-folder
  checks for PD Output and PD Load), `core/comfy.py` (ComfyUI folders and
  server routes), preview helpers in `core/media.py`, and
  `trackPreviewMedia` in `web/pd_common.js`

### PD Load and PD OCIO Apply LUT
- PD Load: `template` is now `file` (settings `load.template` →
  `load.file`, empty by default). Paste a full file path into `file` or
  `base_path` (quotes from Windows' "Copy as path" are fine) and it is
  split into the two fields and loaded. A **load** button runs just this
  node (PD Load is now an output node). `fps_from_file` uses a video's
  frame rate, with `fps` as the override. Sequences and video preview as a
  playable clip. `sequence_from_file` (on by default): a file that is one
  frame of a sequence loads the whole sequence; off, just that frame
- New **PD Load**, the inverse of PD Output: a token template (with context
  and wedge tokens) resolved under ComfyUI's input folder or an
  absolute/UNC base path loads a single image, an image sequence
  (`{frame}`, `####`, `%04d`, or PD Output's `name.1001.png`) or a video.
  Outputs images, mask, fps, frame_count, first_frame, path, context (PD
  Output's sidecar tokens), video and audio. Frame range, every-nth, 16-bit
  and float precision, EXR un-premultiply and `linear to sRGB`. Files are
  re-read when they change on disk. New `[load]` settings
- New **PD OCIO Apply LUT**: applies a LUT file (.cube, .3dl, .spi3d,
  CLF/CTF, CDL...) forward or inverse, from a local or network path

### Renames and fixes
- Renamed nodes (class names too, so workflows saved with the old names
  need the nodes re-added): PD Shot Token → **PD Tokens To String**
  (`PDTokensToString`), PD Video Frame → **PD Video Get Frame**
  (`PDVideoGetFrame`), PD Image Frame → **PD Image From Batch**
  (`PDImageFromBatch`). The `[shot_token]` settings table is now
  `[tokens_to_string]`
- PD Project Context: `artist` is now `user`, and the token is `{user}`
- PD Output token panel: no resize handle of its own; it fills the node, so
  resizing the node resizes it (both renderers). Smaller on a new node
- Wedge preview: the panel could miss the result when the preview finished
  before the queue request returned

### Wedges (rework, #3)
- PD Wedge is rebuilt around rows: each row is an input of any type (image,
  prompt, model, video...) paired with a text value, the token's value for
  PD Output. Rows grow as they are used (up to 16); empty rows are skipped.
  An unlinked row's value is its text. Outputs: `value`, `text`, `int`,
  `float` and `wedge` (a chain for further wedges and PD Output). Inputs are
  lazy, so only the selected row's branch is computed. Optional `group`:
  wedges sharing a group step together instead of multiplying. Old PD Wedge
  workflows do not load into the new node
- One Queue click queues one job per combination of wedge rows. The prompt
  is built once, so every job has the same seed. The first wedge in a chain
  varies fastest; wedges in the same group step together and need the same
  number of rows. Above 20 jobs a confirmation shows the count. Only wedges
  that feed an output count. Wedge errors (no rows, mismatched group) mark
  the wedge like a validation error. The jobs come from
  `POST /pipedream/wedge/plan`
- PD Output has an optional `wedge` input (the last wedge of a chain). It
  adds `{<token>}` and `{<token>_idx}` for each wedge, plus `{wedge_idx}`
  and `{wedge_total}`, over the context tokens; the sidecar records the job
  and each wedge's row under `wedge`
- PD Wedge `solo`: run only that row number (0: every row), for a test
  render. In a group it pins the whole group
- PD Output "preview wedge" button: lists the path of every job in the
  token panel without running the graph or writing anything. Only what
  feeds the file name runs (context, wedges); wedges compute none of their
  row inputs. Shows the job count and warns about wedges not chained into
  the node, paths written by more than one job, and existing files when
  overwrite is off
- Example workflows 05 (prompt wedge) and 06 (product matrix: grouped and
  chained wedges) replace the old wedge READMEs. `docs/wedges-headless.md`
  notes how to expand wedges for prompts posted without the browser
- PD Rasterizer is removed; PD Output's wedge preview replaces it

### Alpha masks and premultiplication
- PD Video To Images and PD Video Frame have a new `mask` output (after
  `images`/`image`) with the video's alpha, 1.0 = opaque. Alpha planes
  (ProRes 4444, other `yuva*`, `rgba`, `gbrap*`) are decoded at full
  precision in the same pass and with the same frame selection as the
  images. Videos without alpha give a full-opacity mask of the same size and
  count. In-memory videos use their own alpha or RGBA channel 4. This shifts
  the later outputs by one, so links to `audio`/`fps`/`frame_count` (and
  `frame_index`/`frame_count`/`fps`) in workflows saved during 0.2.0
  development need reconnecting
- PD Image Frame: new optional `mask` input and `mask` output that picks the
  same frame (a single-frame mask is used for every frame); without a mask it
  outputs RGBA channel 4, else full opacity. Later outputs shift by one
- PD Output writes EXR alpha premultiplied, as the OpenEXR spec defines
  (RGB x alpha, after the sRGB to linear decode). PNG, WebP and ProRes 4444
  stay straight. The sidecar records `alpha.premultiplied`
- README section "Alpha and premultiplication": conventions per format,
  how to interpret ProRes 4444 (straight), and the inverted MASK of core
  Load Image / Join Image with Alpha (use Invert Mask)
- PD Video Frame and PD Image Frame show `index` only when mode is `index`
  (web/pd_video.js)
- PD Project Context "reset version" on an empty or non-numeric version
  resets to the configured `project.version` default (v001 when none is set)

### Facility / user defaults
- New TOML settings: built-in defaults, then `pipedream.toml` in the pack
  folder (user, git-ignored), then the file in `PIPEDREAM_COMFYUI_CONFIG` (facility).
  Keys override only when present and valid; invalid values, unknown keys,
  bad TOML and a missing facility file warn once in the console. Read with
  `tomllib` (or `tomli`), no new dependency. Restart ComfyUI after edits
- Tables `[output]`, `[exr]`, `[sequence]`, `[tokens]` (+ `[tokens.extra]`),
  `[shot_token]`, `[project]`, `[ocio]`, `[sound]`, defined once in the
  `core/settings.py` schema, which also generates `pipedream.example.toml`
- Node widget defaults come from the settings (saved workflows keep their
  values). Token delimiters, date/time formats, extra tokens and the
  sequence frame separator apply when resolving tokens
- The PD Output token reference ends with the loaded settings files, and
  the sidecar records them under `settings.sources`
- Added `tests/` (standard library unittest) for the settings and tokens

### PD Output: alpha, sequences, sRGB to linear
- Image sequences (breaking): image formats write one file per frame,
  numbered from the new `start_frame` (default 1001) at `{frame}` in the
  template, or as `name.1001.ext` without it (previously `name_0000.ext`).
  Single images get no number unless `{frame}` is used. Video formats drop
  `{frame}`. The sidecar is named without the frame number and records the
  frame range and `####` pattern. The token reference shows the range.
- Overwrite off now skips the whole sequence when any frame exists,
  instead of writing a mix of old and new frames
- New optional `alpha` input (IMAGE luminance, MASK, or VIDEO frames; one
  frame or one per frame, same size, otherwise a clear error). Written to
  png/webp (RGBA), exr (RGBA, alpha unconverted) and mov as ProRes 4444
  (`yuva444p10le`). The 4th channel of RGBA images is used when `alpha` is
  not connected. jpg/mp4/webm/ProRes 422 HQ drop it with a console warning
- New `prores_profile` (auto / 422 HQ / 4444). auto picks 4444 when there
  is an alpha
- New `exr_colorspace` (as is / sRGB to linear), using the piecewise sRGB
  EOTF extended above 1.0. Recorded in the sidecar
- The frontend hides the `alpha` input for formats without alpha and the
  `video` output for image formats (never while linked). Also hides
  `start_frame`/`frame_padding` for video, `prores_profile` unless mov and
  `exr_colorspace` unless exr. Slot hiding uses the new `showSlots()` in
  web/pd_common.js
- Widgets reordered/inserted (`format`, `start_frame`, `frame_padding`,
  `prores_profile` after `crf`, `exr_colorspace` after `exr_compression`).
  ComfyUI restores widget values by position, so PD Output nodes in
  workflows saved before this change may load with shifted values. Re-create
  those nodes

### Breaking cleanup
- Removed the legacy PD Output Relative / PD Output Absolute nodes and the
  PDOutputNamer / PDNetworkOutput aliases; use PD Output
- PD Shot Token now resolves its template against an optional context input
  instead of its own project/shot/version/date/time widgets
- PD Project Context is no longer an output node and has no hidden inputs
- Removed core/compat.py, core/utils.py (merged into core/media.py),
  core/display.py (now core/common.py, which also holds the shared
  wildcard type), requirements.txt, the original design brief and the
  placeholder workflow READMEs other than the wedge examples (05, 06)
- Frontend helpers shared through web/pd_common.js; all extensions use
  `isInputConnected` and target current (Nodes 2.0) frontends only

### Changes

- PD Project Context: added optional context input for override chaining
- PD Project Context: added auto_increment_version (persistent, like seed)
- New node: PD Custom Context (user-defined key/value token pairs)
- PD Custom Context: pairs auto-expand as names are filled, up to 10 (#7);
  all pairs are optional inputs and workflows saved with the old 5 fixed pairs
  load with their values intact
- PD Project Context: version auto-increment now happens in the frontend at
  queue time, so batch count > 1 gives each run its own version (#5)
- PD Project Context: version prefixes may now contain any characters before
  the trailing number (e.g. `take_0042`)
- PD Project Context: added "reset version" and "reset all versions in graph"
  buttons, plus a canvas menu entry for the global reset (#4)
- Moved the PD Project Context extension into web/pd_version.js
- Replaced PD Output Namer + PD Network Output with:
  - PD Output Relative (saves to ComfyUI output dir)
  - PD Output Absolute (saves to absolute/UNC path)
- Both output nodes show a token reference panel after execution
- PD Switch: simplified to single-channel with auto-growing inputs (2–8)
- Added 💭 emoji prefix to all node display names (with Windows fallback)
- Frontend extensions: shared code in web/pipedream.js, per-feature files in web/pd_*.js
- Nodes 2.0 fixes (#21): token reference and Rasterizer panels render in both
  renderers, PD Switch starts with 2 inputs and resizes as inputs change
- Removed the unused V3 wrapper (`wrap_as_v3`); nodes register via `NODE_CLASS_MAPPINGS` only (#17)
- New video nodes (Pipedream/Video, core `VIDEO` type, PyAV decode helpers in core/video.py):
  - PD Images To Video (in-memory video from images + optional audio)
  - PD Video To Images (range / every-Nth decode with matching audio)
  - PD Video Frame (first / last / index with keyframe seeking)
  - PD Image Frame (first / last / index for image batches)
- New node: PD Sound (#10) (browser sound cue with wildcard passthrough; plays when the node is reached or when the queue finishes; six synthesized sounds plus custom URL; optional error tone and play-when-cached; JS in web/pd_sound.js)
- New node: PD Output, combining Output Relative and Output Absolute with a
  `path_mode` switch (relative/absolute) and video formats (#11)
  - mp4 (H.264), mov (ProRes 422 HQ) and webm (VP9) encoded with PyAV, which
    ships with ComfyUI (no ffmpeg binary needed), with `fps` and `crf` widgets
  - Optional `video` (VIDEO) input: written with its own frame rate and audio
    (AAC for mp4/mov, Opus for webm), or as an image sequence for image
    formats; `images` is now optional and one of the two is required
  - Relative mode refuses templates that resolve outside the output directory
  - web/pd_output.js hides widgets that do not apply to the current
    mode/format (built for the Nodes 2.0 renderer, also works on the classic
    canvas)
- PD Output Relative / PD Output Absolute are now deprecated "(legacy)" nodes
  that share PD Output's implementation; existing workflows still load
- All PD Output nodes:
  - Write a sidecar JSON (template, resolved tokens/context, written paths,
    timestamp, ComfyUI prompt), toggled by `save_metadata` (#6)
  - Show a preview of what was written under the node (#8)
  - Outputs `path` (first file or the video), `path_sidecar`, `path_all`
    (every written file, newline-separated), `images` passthrough (#9) and
    `video` (a ComfyUI VIDEO of the written file); `path` stays in slot 0 so
    old `written_path` links keep working
  - EXR output now works (#16): linear float RGB/RGBA written with PyAV's EXR
    encoder, with `exr_precision` (half/float) and `exr_compression`
    (zip/zips/rle/none) options recorded in the sidecar; write failures
    raise an error instead of silently writing nothing

- New OCIO nodes under Pipedream/Color, using OpenColorIO (`opencolorio>=2.3`,
  Pipedream's first dependency, in requirements.txt; imported lazily so the
  other nodes still load without it):
  - PD OCIO Transform (colorspace to colorspace, optional look / inverse look)
  - PD OCIO Display (display/view transform, optional inverse)
  - Config choice: $OCIO environment (built-in ACES studio config when
    unset), built-in ACES studio / cg configs, or a custom config file
  - Float processing keeps values outside 0–1; alpha passes through
  - Dropdowns follow the selected config (web/pd_ocio.js, served by
    `GET /pipedream/ocio/options`); names are validated against the selected
    config at queue time

## 0.1.0

- Initial release
- PD Project Context node
- PD Shot Token node
- PD Output Namer node
- PD Network Output node
- PD Switch node (multi-channel, wildcard)
- PD Wedge node (iteration with optional auto-queue)
- PD Rasterizer node (wedge preview/inspector)
