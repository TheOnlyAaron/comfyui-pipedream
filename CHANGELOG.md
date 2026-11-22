# Changelog

## 0.2.0 (unreleased)

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
