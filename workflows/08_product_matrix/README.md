# 08 — Product matrix

One base image, three products, two looks: 6 outputs from one graph.

- **product** (PD Wedge): three Load Image nodes, named `cola`, `lime`, `berry`. Its `value` (the product image) is composited onto the base image.
- **product_prompt** (PD Wedge, chained after product): a text row per product (`a red cola can`, ...). It shares the group `product` with the product wedge, so the two step together: the cola image always gets the cola prompt.
- **look** (PD Wedge, chained after product_prompt): two text rows that multiply the products. String Concatenate joins `product_prompt` and `look` into the positive prompt.
- The base image, negative prompt, checkpoint and seed are the same in every job.

The product wedge is first in the chain, so it varies fastest:

| job | product | look |
|-----|---------|------|
| 000 | cola | picnic table |
| 001 | lime | picnic table |
| 002 | berry | picnic table |
| 003 | cola | bar counter |
| 004 | lime | bar counter |
| 005 | berry | bar counter |

PD Save template: `wedges/06_products/{product}/{product}_{look_idx}`, one folder per product (`cola/cola_000.png`, `cola/cola_001.png`, ...). The sidecar JSON records each job's wedge rows.

Setup: load a base image and the three product images (the composite places the product at x/y 256; adjust to taste), pick a checkpoint, then press **preview wedge** on PD Save:

```
Wedge preview: 6 outputs (product+product_prompt 3 x look 2), nothing written.
  [000] wedges/06_products/cola/cola_000.png
  ...
```

Things to try:
- Add a fourth product: link another Load Image to `input_4`, name it, and add a fourth prompt to product_prompt. With only one of the two, Run stops with "need the same number of rows" on the wedge.
- Remove `{product}` from the template: the preview warns that paths are written by more than one job.
- Disconnect look's `wedge` output from PD Save (connect product_prompt's instead): the preview warns that `look` is not chained into PD Save.

**Nodes used:** PD Wedge (×3), Load Image (×4), Image Composite Masked, String Concatenate, CheckpointLoaderSimple, VAE Encode, CLIP Text Encode, KSampler, VAE Decode, PD Save
