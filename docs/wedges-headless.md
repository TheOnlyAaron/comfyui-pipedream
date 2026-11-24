# Wedges without the browser (future work)

Status: **not built.** Today one Queue click is expanded into one job per wedge combination by the frontend (`web/pd_wedge.js` wraps `api.queuePrompt`). A prompt posted straight to ComfyUI's `/prompt` (a script, Deadline, another service) is *not* expanded: every wedge runs its first row (or its `solo` row) once. This note records how to close that gap.

## What already exists

The expansion logic is Python and has no ComfyUI or browser dependency, so a headless path only needs a new entry point:

- `core/wedge.py`
  - `plan(prompt, output_ids)`: the axes and total for an API prompt (groups, solo, chain order, the 10,000-job limit). It raises `WedgeError` with `node_id` / `input_name`.
  - `jobs(plan)`: one `{node_id: row}` per job, the first axis varying fastest.
  - `apply_job(prompt, rows, job, total)`: a copy of the prompt with `pd_wedge_row` / `pd_wedge_job` / `pd_wedge_total` set on each wedge.
- `nodes/wedge.py`
  - `plan_prompt(prompt, output_ids=None)`: `plan` + `jobs`. It defaults the outputs to every `OUTPUT_NODE` class.
  - `POST /pipedream/wedge/plan`: `{"prompt"}` → `{"total", "axes", "jobs"}`, or `{"error", "node_id", "input_name"}` with status 400.

The frontend only applies `jobs` and posts each prompt. A headless client can do the same today:

```python
plan = post("/pipedream/wedge/plan", {"prompt": prompt})
for job, rows in enumerate(plan["jobs"]):
    post("/prompt", {"prompt": apply_job(prompt, rows, job, plan["total"]),
                     "client_id": client_id,
                     "extra_data": {"extra_pnginfo": {"workflow": workflow}}})
```

## Options

1. **Submit route (recommended first step).** `POST /pipedream/wedge/queue` takes the same body as `/prompt` (prompt, client_id, extra_data, front, number). It plans, then queues each job through ComfyUI's own path: `PromptServer.instance` validation plus `prompt_queue.put`, the same as `server.py`'s `post_prompt`. It returns `{"prompt_ids": [...], "total"}`. Clients opt in by changing the URL. The plain `/prompt` keeps its meaning, so the frontend wrapper and this route can never both expand the same prompt.
2. **Transparent expansion.** `PromptServer.instance.add_on_prompt_handler` sees every `/prompt` body before it's queued. It could queue jobs 1..N-1 itself and return job 0. The prompt would need a marker (e.g. the `pd_wedge_row` keys already present) so prompts the frontend already expanded aren't expanded again. This is more invisible, and so more surprising. It's also tied to an internal hook whose behavior has changed between ComfyUI versions.
3. **Client-side helper.** A small `pipedream_submit.py` (stdlib only) wraps the snippet above for Deadline or other farm scripts. It works against any ComfyUI with the pack installed and needs no server changes.

## Things to decide when we build it

- **Seed:** the frontend copies one prompt, so every job has the same seed. Headless clients should do the same and set the seed once, before expanding.
- **Validation:** validate the first job before queueing the rest, so a bad graph fails once instead of N times.
- **Cancel:** return all prompt ids so a client (or a Deadline job) can cancel the batch.
- **Farm split:** for Deadline, one task per job (or per chunk of jobs) maps naturally to `jobs[i]`, with `{wedge_idx}` keeping output names unique across machines.
- **Confirmation:** the 20-job confirmation is UI-only. A headless route should take an explicit `max_jobs` instead.
