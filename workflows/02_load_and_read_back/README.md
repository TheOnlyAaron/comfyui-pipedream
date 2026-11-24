# 02 — Load and read back

Load a file, write an EXR sequence, and read it back with its tokens. Runs as is (no model).

- **PD Load** reads `example.png` from ComfyUI's input folder. For your own file, paste its full path (Explorer: shift+right click → *Copy as path*) into `file` or `base_path`; it is split into the two fields and loaded.
- **Repeat Image Batch** makes 5 frames and **PD Output** writes them as `pipedream_demo/demo/sh020/sh020_v001.1001.exr` … `.1005.exr` (`sRGB to linear`) with a sidecar.
- A second **PD Load** takes PD Output's `path` (the first frame) in `file`. `sequence_mode` **auto** loads all 5 frames (PD Output's sidecar marks them as a sequence), `linear to sRGB` undoes the conversion, and its `context` output carries the sidecar's tokens into **PD Tokens To String** (`demo / sh020 / v001`).

**load** on a PD Load runs just that node.

**Nodes:** PD Load (×2), Repeat Image Batch, PD Project Context, PD Output, PD Tokens To String, Preview Image, Preview as Text
