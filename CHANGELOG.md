# Changelog

## 0.2.0 (unreleased)

- PD Project Context: added optional context input for override chaining
- PD Project Context: added auto_increment_version (persistent, like seed)
- PD Project Context: version auto-increment now happens in the frontend at
  queue time, so batch count > 1 gives each run its own version (#5)
- PD Project Context: version prefixes may now contain any characters before
  the trailing number (e.g. `take_0042`)
- PD Project Context: added "reset version" and "reset all versions in graph"
  buttons, plus a canvas menu entry for the global reset (#4)
- Moved the PD Project Context extension into web/pd_version.js
- New node: PD Custom Context (5 user-defined key/value token pairs)
- Replaced PD Output Namer + PD Network Output with:
  - PD Output Relative (saves to ComfyUI output dir)
  - PD Output Absolute (saves to absolute/UNC path)
- Both output nodes show a token reference panel after execution
- PD Switch: simplified to single-channel with auto-growing inputs (2–8)
- Added 💭 emoji prefix to all node display names (with Windows fallback)
- Consolidated JS extensions into single web/pipedream.js

## 0.1.0

- Initial release
- PD Project Context node
- PD Shot Token node
- PD Output Namer node
- PD Network Output node
- PD Switch node (multi-channel, wildcard)
- PD Wedge node (iteration with optional auto-queue)
- PD Rasterizer node (wedge preview/inspector)
