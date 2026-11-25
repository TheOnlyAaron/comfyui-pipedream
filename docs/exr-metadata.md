# EXR metadata

EXR header metadata travels through the graph as an `EXR_METADATA` stream, frame by frame:

- **In:** [PD Load](../web/docs/PDLoad.md)'s `exr_metadata` output gives each loaded EXR frame's attributes (camera matrices, timecode, a renderer's or Nuke's own keys). A plate's per-frame values stay per frame.
- **Set:** [PD Project Context](../web/docs/PDProjectContext.md) and [PD Custom Context](../web/docs/PDCustomContext.md) have an `exr_metadata` output: every token becomes a string attribute named `pipedream/<token>` (`pipedream/shot`, `pipedream/version`, `pipedream/client`...). The prefix is the `exr.metadata_prefix` setting. Custom Context pairs are how you add your own keys; empty values are left out.
- **Profile:** [PD Profiler](../web/docs/PDProfiler.md)'s `exr_metadata` output stamps the run under `pipedream/profiler/`: budget, the peak estimate and its stage, each stage, the latent, model file paths, the measured time and VRAM peak. To feed PD Save, branch the profiler off before it (after it would be a loop). The profile changes every run, so a PD Save fed by it writes on every queue.
- **Merge:** [PD EXR Metadata Merge](../web/docs/PDExrMetadataMerge.md) combines up to 8 streams into one (a spare input appears as you connect one), frame by frame, with the same rule as PD Save: later inputs win on the same name, and per-frame tables stay per frame. Assemble a stream once and send it to several PD Saves, or inspect it with Get.
- **Out:** [PD Save](../web/docs/PDSave.md)'s `exr metadata` inputs (exr only; a spare appears as you connect one, up to 8) are merged frame by frame, later inputs winning on the same name. A source with one table per frame writes frame N's table into frame N; a single table goes into every frame. The sidecar lists the names written.
- **Nothing unless connected:** with no `exr metadata` input connected, PD Save writes no metadata: only FFmpeg's encoder defaults (`writer`, `gamma`). So loading an EXR and writing it back out without a connection strips its metadata.
- **Inspect:** [PD EXR Metadata Get](../web/docs/PDExrMetadataGet.md) lists every attribute with its type, marks those that vary by frame (`*`), and outputs one by `key` as `value`, `int` and `float`. `key` takes a full name or a unique last part (`shot`). `frame` picks the frame, `filter` narrows the list, and **preview** runs just the node and its inputs.

## Types and structural attributes

Attributes keep their EXR types (string, int, float, double, vectors, matrices, box, chromaticities, timecode, rational, keycode, string and float vectors); any other type is carried as raw bytes, so a load-and-write round trip loses nothing. Structural attributes (channels, compression, data and display windows, line order, pixel aspect) always come from the writer. Nuke shows the names as `exr/pipedream/...`.

## How the header is written

PD Save's EXRs come from FFmpeg's encoder, which can't write custom attributes, so the header is rewritten after each frame is encoded: attributes are inserted and the chunk offset table shifted to match. The pixel data isn't touched (checked against the OpenEXR library for every compression and precision PD Save writes). Standard library only; no extra dependency.

## Related

[Tokens](tokens.md) (context tokens become attributes), [alpha](alpha.md) (EXR is written premultiplied).
