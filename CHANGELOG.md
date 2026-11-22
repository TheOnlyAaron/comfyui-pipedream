# Changelog

## 0.2.0 (unreleased)

- PD Project Context: added optional context input for override chaining
- PD Project Context: added auto_increment_version (persistent, like seed)
- New node: PD Custom Context (5 user-defined key/value token pairs)
- Replaced PD Output Namer + PD Network Output with:
  - PD Output Relative (saves to ComfyUI output dir)
  - PD Output Absolute (saves to absolute/UNC path)
- Both output nodes show a token reference panel after execution
- PD Switch: simplified to single-channel with auto-growing inputs (2–8)
- Added 💭 emoji prefix to all node display names (with Windows fallback)
- Consolidated JS extensions into single web/pipedream.js
- New node: PD Output, combining Output Relative and Output Absolute with a
  `path_mode` switch (relative/absolute) and video formats (#11)
  - mp4 (H.264), mov (ProRes 422 HQ) and webm (VP9) written by piping frames
    to the `ffmpeg` binary on PATH, with `fps` and `crf` widgets; clear error
    if ffmpeg is missing
  - Relative mode refuses templates that resolve outside the output directory
  - web/pd_output.js dims widgets that do not apply to the current mode/format
- PD Output Relative / PD Output Absolute are now deprecated "(legacy)" nodes
  that share PD Output's implementation; existing workflows still load
- All PD Output nodes:
  - Write a sidecar JSON (template, resolved tokens/context, written paths,
    timestamp, ComfyUI prompt), toggled by `save_metadata` (#6)
  - Show a preview of what was written under the node (#8)
  - New `images` passthrough output after `written_path` (#9)
  - EXR output now works (#16): linear float RGB/RGBA written via `ffmpeg`
    (fallbacks: OpenEXR, OpenCV), with `exr_precision` (half/float) and
    `exr_compression` (zip/zips/rle/none) options recorded in the sidecar;
    a missing writer raises an error instead of silently writing nothing

## 0.1.0

- Initial release
- PD Project Context node
- PD Shot Token node
- PD Output Namer node
- PD Network Output node
- PD Switch node (multi-channel, wildcard)
- PD Wedge node (iteration with optional auto-queue)
- PD Rasterizer node (wedge preview/inspector)
