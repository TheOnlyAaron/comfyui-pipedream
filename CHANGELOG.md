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

## 0.1.0

- Initial release
- PD Project Context node
- PD Shot Token node
- PD Output Namer node
- PD Network Output node
- PD Switch node (multi-channel, wildcard)
- PD Wedge node (iteration with optional auto-queue)
- PD Rasterizer node (wedge preview/inspector)
