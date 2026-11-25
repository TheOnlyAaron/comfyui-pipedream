# 02 — Load and save

Load a file, write an EXR sequence with a sidecar and header metadata, and read it back with its tokens and metadata. Runs as is (no model), using ComfyUI's `input/example.png`.

- **PD Load** reads `example.png` from ComfyUI's input folder. For your own file:
  - drop it on the node's drop zone (it is copied to `input/pipedream`), or
  - paste its full path (Explorer: shift+right click → *Copy as path*) into `file`; network files load in place.

  **Explore Input** opens the file's folder.
- **Repeat Image Batch** makes 5 frames and **PD Output** writes them as `pipedream_demo/demo/sh020/sh020_v001.1001.exr` … `.1005.exr` (`sRGB to linear`) with a sidecar `sh020_v001.json`. **Explore Output** shows them in Explorer.
- A second **PD Load** takes PD Output's `path` (the first frame) in `file`. `sequence_mode` **auto** loads all 5 frames, and its panel says why (`sequence: from sidecar sh020_v001.json`). `linear to sRGB` undoes the conversion, and its `context` output carries the sidecar's tokens into **PD Tokens To String** (`demo / sh020 / v001`).

- **EXR metadata:** PD Project Context's `exr_metadata` output goes into PD Output's `exr metadata` input, so every frame's header carries `pipedream/project`, `pipedream/shot` and `pipedream/version` (Nuke shows them as `exr/pipedream/...`). The read-back PD Load's `exr_metadata` goes to **PD EXR Metadata Get**: press **preview** to list every attribute; `key` `shot` outputs `sh020`.

Try `sequence_mode` **single file** on the second PD Load to load just the first frame. Drop the sidecar `.json` on the canvas to reopen the workflow that wrote it.

**load** on a PD Load runs just that node.

**Nodes:** PD Load (×2), Repeat Image Batch, PD Project Context, PD Output, PD Tokens To String, PD EXR Metadata Get, Preview Image
