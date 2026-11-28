# Pipeline integration

How to connect Pipedream to a studio pipeline (ftrack, Flow Production Tracking, Deadline, a publish tool) while staying inside the rules ComfyUI and the Comfy Registry set for custom nodes.

## The ground rules

Pipedream doesn't start other programs, run scripts, or read environment variables. That's deliberate:

- The [Comfy Registry standards](https://docs.comfy.org/registry/standards) ban `eval`/`exec` and runtime installs, and the registry's security scan flags code that starts processes, makes network requests or reads the environment ([January 2025 security update](https://blog.comfy.org/p/comfyui-2025-jan-security-update)).
- A workflow is shared as a file, and loading it must be safe. A node that runs a script named in the workflow turns every shared workflow into a way to run code on someone else's machine.

So Pipedream's side of an integration is **data**: predictable paths, sidecar JSON, EXR metadata and ComfyUI's own API. Your pipeline's side, the code that talks to ftrack or Flow, runs outside ComfyUI, under your control.

## 1. Configure: settings and the pointer file

Facility defaults (output templates, network roots, formats, OCIO config, extra tokens such as `{facility}`) live in one shared TOML file. Each machine finds it through a pointer file, `pipedream_facility.txt` in ComfyUI's user folder, which a deployment script or Group Policy copies there. See [Settings](settings.md#finding-the-facility-file).

Per-shot values come into the graph as tokens: [PD Project Context](../web/docs/PDProjectContext.md) (project, shot, version) and [PD Custom Context](../web/docs/PDCustomContext.md) (any key/value pairs). A pipeline tool that builds or edits workflows sets those widgets; see [Tokens](tokens.md).

## 2. Record: what each render leaves behind

| Output | Where | What it holds |
|---|---|---|
| The files | the resolved template, e.g. `//nas/shows/ABC/sh010/comp/sh010_v003.####.exr` | images, sequences or video |
| PD Save sidecar | `<name>.json` next to the files (`save_metadata` on) | the template and resolved path, every token value, context, wedge row, the list of files written, image size, alpha, the settings files used, and the workflow |
| EXR header metadata | inside each EXR (`pipedream/...` attributes) | context tokens and anything merged in, readable by Nuke and other tools ([EXR metadata](exr-metadata.md)) |
| Profile sidecar | `<name>.profile.json` (PD Profiler, `export_sidecar` on) | node times, memory estimate and measured peak, models used ([Profiler](profiler.md#sidecar)) |

PD Save's `path`, `path_sidecar` and `path_all` outputs carry the same paths through the graph.

## 3. React: hooking in from outside ComfyUI

Pick whichever fits how your pipeline already works.

### Watch for sidecars

A small service (or an ftrack/Flow event plugin) watches the output roots for new `*.json` sidecars written by PD Save (`"node": "PDSave"`; older files say `"PDOutput"`). The sidecar is written after the files, so its arrival means the render is complete. It has everything a publish needs: the files, the shot tokens and the version.

```python
import json, pathlib

def on_new_sidecar(path):
    data = json.loads(pathlib.Path(path).read_text())
    if data.get("node") not in ("PDSave", "PDOutput"):
        return
    tokens = data["tokens"]
    publish(project=tokens.get("project"), shot=tokens.get("shot"),
            version=tokens.get("version"), files=data["files"])  # your ftrack / Flow code
```

### Listen to ComfyUI

ComfyUI reports progress over its websocket (`/ws?clientId=...`). When a node returns UI data it sends an `executed` message with the node id, the prompt id and the node's `output` ([messages](https://docs.comfy.org/development/comfyui-server/comms_messages)). PD Save's output includes `pd_written`, the first file written:

```python
import json, websocket  # websocket-client

ws = websocket.create_connection("ws://127.0.0.1:8188/ws?clientId=pipeline")
while True:
    msg = ws.recv()
    if isinstance(msg, str):
        event = json.loads(msg)
        if event["type"] == "executed" and "pd_written" in event["data"]["output"]:
            on_render(event["data"]["prompt_id"], event["data"]["output"]["pd_written"][0])
```

`GET /history/<prompt_id>` returns the same outputs after the fact ([routes](https://docs.comfy.org/development/comfyui-server/comms_routes)).

### Drive ComfyUI

A pipeline tool or a render manager submits work with `POST /prompt` (the API-format workflow), then follows it as above. With PD Save's `path` linked into a PD Profiler with `export_sidecar` on, each render leaves its own record of time and memory. Wedges posted this way run one row; see [Wedges without the browser](wedges-headless.md).

On Deadline, the job's own post-task script (which runs in Deadline, not in ComfyUI) can read the sidecar and publish.

## Why there's no "run a script" node

A node that runs a `.py` or `.bat` after a render would be the shortest route, and other packs offer one. It isn't in Pipedream because it would put a code-execution path in every workflow and in the registry package. If a studio needs one, keep it in a separate, privately installed node pack that only runs scripts from a folder named in the facility settings, chosen by name rather than by path, so a shared workflow can't point it anywhere else.
