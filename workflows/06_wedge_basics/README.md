# 06 — Wedge basics

One graph, one job per row. Runs as is (no model), using ComfyUI's `input/example.png`.

- **PD Wedge** has three rows for the token `size`: `256`, `512`, `1024`. Its `int` output feeds **Upscale Image**'s width and height, so each job renders at a different size.
- Its `wedge` output goes to **PD Output**, where `{size}` names the file: `pipedream_demo/wedge/example_256.png`, `example_512.png`, `example_1024.png`, each with a sidecar recording its wedge row.
- Press **preview wedge** on PD Output to list the three paths without running anything, then Run: 3 jobs are queued.

Try:
- `solo` = 2 renders only `512`.
- `{size_idx}` in the template numbers the files `000`, `001`, `002` instead.
- Chain a second PD Wedge into the first one's `wedge` input to get every combination (see 08).
- Load `example_512.png` with PD Load: its sidecar tells `sequence_mode` **auto** that it is a single image, even though `example_256.png` sits next to it.

07 and 08 use the same pattern with a checkpoint: a prompt wedge, and grouped and chained wedges.

**Nodes:** PD Load, PD Wedge, Upscale Image, PD Output
