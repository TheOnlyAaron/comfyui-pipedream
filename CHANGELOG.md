# Changelog

## 0.2.0 (unreleased)

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
