# 01 — Output basics

Name and write files from shot tokens. Runs as is (no model): it uses ComfyUI's `input/example.png`.

- **PD Project Context** (`demo` / `sq010` / `sh010` / `v001` / `jsmith`) and **PD Custom Context** (`task` = `comp`) hold the shot details.
- **PD Output** writes `pipedream_demo/demo/sq010/sh010/comp/sh010_comp_v001.png` in ComfyUI's output folder, with a sidecar `.json`. Its panel lists every token after the run.
- **PD Tokens To String** resolves `{shot} {task} {version} by {user}` to text, for prompts or other nodes' paths.

Try: bump `version` (or turn on `auto_increment_version`), switch `format` to `exr`, or set `path_mode` to `absolute` with a network `base_path`.

**Nodes:** PD Load, PD Project Context, PD Custom Context, PD Output, PD Tokens To String, Preview as Text
