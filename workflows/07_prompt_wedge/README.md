# 07 — Prompt wedge

One PD Wedge with three rows. Each row pairs a prompt (a String (Multiline) node linked to `input_n`) with a short name (`value_n`): `studio`, `kitchen`, `night`. The wedge's `value` goes to the positive CLIP Text Encode; its `wedge` output goes to PD Save, where the name is `{look}`.

Run queues 3 jobs. The prompt is built once per click, so the seed (fixed at 1234 here, but randomize works too) is the same in every job; only the prompt changes. The checkpoint, negative prompt and latent are computed once and cached.

PD Save template: `wedges/05_prompt/{look}_{date}`, giving `studio_20261122.png`, `kitchen_...`, `night_...`.

Try:
- **preview wedge** on PD Save lists the three paths without running anything.
- `solo` = 2 on the wedge renders only `kitchen`.
- A row with no input linked uses its text as the value: type a whole prompt into `value_4` (it then becomes the file name too, so prefer `{look_idx}` in the template for long text).

**Nodes used:** PD Wedge, String (Multiline), CheckpointLoaderSimple, CLIP Text Encode, Empty Latent Image, KSampler, VAE Decode, PD Save
