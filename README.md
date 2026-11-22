# ComfyUI-Pipedream

Production pipeline utility nodes for ComfyUI — output naming, network paths, shot tokens, wedge iteration, and multi-input switching.

Pipedream is not a visual effects node pack. It is plumbing.

## Installation

Clone into your ComfyUI `custom_nodes` directory:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/theonlyaaron/comfyui-pipedream.git
```

No additional dependencies are required.

## Nodes

All nodes appear under the **Pipedream** category with a 💭 prefix.

| Node | Description |
|------|-------------|
| **💭 PD Project Context** | Top-level metadata node (project, sequence, shot, version, artist). Accepts an incoming context for override chaining. Supports auto-incrementing version. |
| **💭 PD Custom Context** | Adds up to 5 user-defined key/value token pairs to a context. Chain after Project Context for custom tokens like `{task}`, `{department}`. |
| **💭 PD Shot Token** | Lightweight token resolver — takes a template string and inline widget values, outputs a resolved string. |
| **💭 PD Output Relative** | Resolves a token template and saves images to ComfyUI's output directory. Shows available tokens after execution. |
| **💭 PD Output Absolute** | Same as Output Relative but saves to an absolute or UNC network path. |
| **💭 PD Switch** | Routes one of N wildcard inputs to a single output. Inputs auto-grow when connected (2–8). |
| **💭 PD Wedge** | Iteration node — holds a list of values and emits one per execution. Optional auto-queue for batch iteration. |
| **💭 PD Rasterizer** | Dry-run inspector — connects to wedges and previews the full cartesian product iteration table. |
| **💭 PD Sound** | Plays a short browser sound when this point of the flow is reached, or when the whole queue finishes. Passes any value straight through, so it can sit inline or dangle at the end. See [PD Sound](#pd-sound). |

## PD Sound

Wire anything through the `value` input; the `value` output is the same object, untouched. The node is an output node, so it also runs when left dangling.

- **play_when = node reached** (default): plays when this node executes, so several PD Sound nodes along a graph each announce their own stage with their own sound. A node with nothing connected has no place in the flow, so it waits for the queue to finish instead.
- **play_when = queue finished**: plays once the queue drains, like a render-complete chime. If any prompt failed it plays the error tone instead (`error_tone`); nothing plays after an interrupt.
- **Caching**: a cached node does not execute, and PD Sound never forces it to (that would re-run everything downstream). Turn on `when_cached` to also play when the node is skipped as cached; those sounds play as the prompt starts, because cached work is already done.
- **Errors**: in node reached mode, an execution error plays the error tone straight away (unless `error_tone` is off).
- **Sounds**: `chime`, `happy`, `sad`, `ding`, `beeps`, `alert` are synthesized in the browser (no audio files). `custom URL` plays a file: absolute URL, root-relative path, or a path relative to this pack's `web/` folder. Each node picks its own sound and volume; the test buttons preview them.
- Sounds play in the browser tab that queued the prompt. Changing a PD Sound widget changes its inputs, so nodes downstream of an inline PD Sound re-run on the next queue, as with any other widget edit.

## Token Reference

Tokens are `{name}` placeholders resolved by output nodes and PD Shot Token:

| Token | Source |
|-------|--------|
| `{project}` | Project Context or widget |
| `{sequence}` | Project Context or widget |
| `{shot}` | Project Context or widget |
| `{version}` | Project Context or widget |
| `{artist}` | Project Context |
| `{date}` | Auto: YYYYMMDD |
| `{time}` | Auto: HHMMSS |
| `{frame}` | Padded frame placeholder (e.g. `####`) |
| `{wedge_idx}` | Current wedge iteration index |
| `{wedge_<name>}` | Named wedge current value |
| `{<custom>}` | Any key added via PD Custom Context |

## Context Chaining

PD Project Context accepts an optional incoming context. Non-empty widget values override the incoming values, empty widgets pass through. This lets you set up a base context and override per-shot:

```
PD Project Context (base: project=DITC, sequence=sq010)
    → PD Project Context (override: shot=sh010)
        → PD Custom Context (task=comp, element=BG)
            → PD Output Relative
```

## Compatibility

Pipedream supports both the legacy ComfyUI node API and the Nodes 2.0 (V3) API. The compatibility layer detects which API is available at import time and registers nodes accordingly.

**Note:** Node display names use a 💭 emoji prefix. On Windows systems with legacy console codepages (cp1252, cp932), the emoji is automatically omitted to prevent encoding errors.

## License

MIT — see [LICENSE](LICENSE).
