# Pipedream workflows

Drag a `workflow.json` onto the ComfyUI canvas. 01–06 run as is, using ComfyUI's `input/example.png`, and write into `output/pipedream_demo/`. 05 needs `opencolorio`; 07–08 need a checkpoint (and images for 08).

| # | Workflow | Shows |
|---|----------|-------|
| 01 | [Tokens](01_tokens/) | Project and custom context, PD Tokens To String with **preview**, automatic tokens |
| 02 | [Load and save](02_load_and_save/) | PD Load (drop zone, paste a path), EXR sequence out with sidecar, read back with `sequence_mode` and sidecar tokens |
| 03 | [Video frames](03_video_frames/) | Images to video, mp4 out, get one frame, decode a range, pick from a batch, switch |
| 04 | [Sound](04_sound/) | Inline and queue-finished sound cues, error buzzer |
| 05 | [Colour with OCIO](05_color_ocio/) | OCIO transform and display, LUT, ACEScg EXR |
| 06 | [Wedge basics](06_wedge_basics/) | One wedge, three sizes, three files; PD Profiler with a sidecar per job; no model |
| 07 | [Prompt wedge](07_prompt_wedge/) | One wedge of three prompts; 3 jobs, same seed |
| 08 | [Product matrix](08_product_matrix/) | Grouped and chained wedges: 3 products × 2 looks = 6 outputs |

Every Pipedream node appears in at least one workflow.
