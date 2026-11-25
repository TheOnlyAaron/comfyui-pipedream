# Wedges

A wedge turns several near-identical graphs into one: each [PD Wedge](../web/docs/PDWedge.md) row is an input of any type paired with a text value, and one Run queues a job per row.

1. Set `token` (e.g. `product`), link inputs to `input_1`, `input_2`... and name each row in `value_n`. Rows appear as you fill them (up to 16). A row with only text outputs the text, so prompts and numbers can be typed in.
2. Use `value` where the input would go; the row's text is also on `text`, `int` and `float`.
3. Connect `wedge` to [PD Save](../web/docs/PDSave.md)'s `wedge` input and use `{product}` or `{product_idx}` in the template (see [tokens](tokens.md)).
4. Press **preview wedge** on PD Save to list every path, then Run.

Only the selected row's input is computed, the rest of the graph is cached between jobs, and every job has the same seed.

## Several wedges, solo and checks

- **Several wedges** chain through `wedge` and multiply (3 products × 2 looks = 6 jobs); the first in the chain varies fastest. Wedges with the same `group` step together instead (a product image and its prompt) and need the same row count.
- **solo** runs one row number (0 = all), for a test render.
- **Checks:** above 20 jobs Run asks first. A wedge without rows, an empty solo row or a mismatched group marks the wedge and queues nothing. The preview warns about wedges not chained into PD Save, paths written by several jobs, and existing files.

## Without the browser

Wedges are expanded by the frontend: a prompt posted to `/prompt` directly runs each wedge's first row. See [wedges-headless.md](wedges-headless.md).

## Related

[PD Load](../web/docs/PDLoad.md) takes the wedge tokens in `file`, so a wedge can load a different file per job. [PD Profiler](../web/docs/PDProfiler.md) follows only the selected row's branch; see [profiler.md](profiler.md). Examples: workflows 06 to 08 in [workflows/](../workflows/).
