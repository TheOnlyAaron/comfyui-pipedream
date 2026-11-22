# Pipedream Workflows

Example workflows for PD Wedge. Drag a `workflow.json` onto the ComfyUI canvas to load it, pick a checkpoint (and images for 06), then press **preview wedge** on PD Output before you Run.

| # | Workflow | What it shows |
|---|----------|---------------|
| 05 | [Prompt wedge](05_prompt_wedge/) | One wedge: three prompts (String nodes) with short names; 3 jobs, same seed |
| 06 | [Product matrix](06_product_matrix/) | One base image, three products composited in, two looks: 3 × 2 = 6 outputs. Grouped wedges, chained wedges, per-product folders |

Both use a plain SD1.5/SDXL checkpoint pipeline as a stand-in; the wedge part works the same with any model (Wan, Flux, an API node...).
