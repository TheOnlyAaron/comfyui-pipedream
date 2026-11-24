# Pipedream workflows

Drag a `workflow.json` onto the ComfyUI canvas. 01–04 run as is, using ComfyUI's `input/example.png`, and write into `output/pipedream_demo/`. 05–06 need a checkpoint (and images for 06).

| # | Workflow | Shows |
|---|----------|-------|
| 01 | [Output basics](01_output_basics/) | Project/custom context tokens, PD Output, sidecar, PD Tokens To String |
| 02 | [Load and read back](02_load_and_read_back/) | PD Load, EXR sequence out, read back with `sequence_mode` and sidecar tokens |
| 03 | [Video utilities](03_video_utilities/) | Images to video, mp4 out, get frame, decode a range, pick from batch, switch, sound |
| 04 | [Colour with OCIO](04_color_ocio/) | OCIO transform and display, LUT, ACEScg EXR |
| 05 | [Prompt wedge](05_prompt_wedge/) | One wedge of three prompts; 3 jobs, same seed |
| 06 | [Product matrix](06_product_matrix/) | Grouped and chained wedges: 3 products × 2 looks = 6 outputs |
