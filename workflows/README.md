# Pipedream workflows

Drag a JSON file from the **Download** column onto the ComfyUI canvas. 01–06 run as is, using ComfyUI's `input/example.png`, and write into `output/pipedream_demo/`. 05 needs `opencolorio`; 07–08 need a checkpoint (and images for 08).

| # | Workflow | Download | Shows |
|---|----------|----------|-------|
| 01 | [Tokens](01_tokens/) | [JSON](01_tokens/pipedream_01_tokens.json) | Project and custom context, PD Tokens To String with **preview**, automatic tokens |
| 02 | [Load and save](02_load_and_save/) | [JSON](02_load_and_save/pipedream_02_load_and_save.json) | PD Load (drop zone, paste a path), EXR sequence out with sidecar and header metadata, read back with `sequence_mode`, sidecar tokens, EXR metadata merged and read back |
| 03 | [Video frames](03_video_frames/) | [JSON](03_video_frames/pipedream_03_video_frames.json) | Images to video, mp4 out, get one frame, decode a range, pick from a batch, switch |
| 04 | [Sound](04_sound/) | [JSON](04_sound/pipedream_04_sound.json) | Inline and queue-finished sound cues, error buzzer |
| 05 | [Colour with OCIO](05_color_ocio/) | [JSON](05_color_ocio/pipedream_05_color_ocio.json) | OCIO transform and display, LUT, ACEScg EXR |
| 06 | [Wedge basics](06_wedge_basics/) | [JSON](06_wedge_basics/pipedream_06_wedge_basics.json) | One wedge, three sizes, three files; PD Profiler with a sidecar per job; no model |
| 07 | [Prompt wedge](07_prompt_wedge/) | [JSON](07_prompt_wedge/pipedream_07_prompt_wedge.json) | One wedge of three prompts; 3 jobs, same seed |
| 08 | [Product matrix](08_product_matrix/) | [JSON](08_product_matrix/pipedream_08_product_matrix.json) | Grouped and chained wedges: 3 products × 2 looks = 6 outputs |

Every Pipedream node appears in at least one workflow.
