# 03 — Video utilities

Make, write, trim and read back video. Runs as is (no model).

- **PD Images To Video** wraps 48 frames as an in-memory VIDEO at 24 fps; **PD Output** writes `pipedream_demo/clip_review.mp4`.
- **PD Video Get Frame** seeks to one frame (`last`); **PD Video To Images** decodes a range (from frame 12, 12 frames, every 2nd); **PD Image From Batch** picks one image (`-1` = last).
- **PD Switch** chooses which single frame to preview (`select` 0 or 1).
- **PD Load** reads the mp4 back (its `file` comes from PD Output's `path`) and previews it as a playable clip.
- **PD Sound** chimes when the queue finishes.

**Nodes:** PD Load (×2), Repeat Image Batch, PD Images To Video, PD Output, PD Video Get Frame, PD Video To Images, PD Image From Batch, PD Switch, PD Sound, Preview Image
