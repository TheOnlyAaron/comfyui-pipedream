# PD Profiler GPU validation

Measures PD Profiler's estimates against real runs on a large NVIDIA card. The method and results are in [docs/profiler-accuracy.md](../../docs/profiler-accuracy.md#gpu-validation).

| File | What it does |
|---|---|
| `run_validation.py` | Starts ComfyUI once per configuration, presses **profile** and queues each graph, samples `nvidia-smi`, writes `results.jsonl` |
| `tabulate.py` | Turns a results folder into Markdown tables (`tables.md`) |
| `graphs.py` | Built-in graphs (SDXL, Flux.1, Wan 2.1, Wan 2.2 5B and A14B, HunyuanVideo, HunyuanVideo 1.5) and patching of exported API workflows |
| `example_config.json` | The full matrix; copy it and edit the paths and model names |
| `vram_cap/` | Optional ComfyUI module that caps PyTorch's allocator for emulated cards; linked into `custom_nodes` while emulated runs need it |

## Before you start

1. A current ComfyUI with PipeDream installed, on the GPU machine. Note the ComfyUI commit: `machine.json` records it.
2. The model files from the config's `models` list. The defaults are the Comfy-Org repackaged names; change them to match your files.
3. LTX-2.x and MiniMax H3 run from your own workflows. Open ComfyUI's text-to-video template for each, check that it runs, then use **Workflow > Export (API)** and save it under `workflows/` with the name the config uses (`ltx2_t2v_api.json`, `minimax_h3_t2v_api.json`). The runner sets each node's `width`, `height` and `length` to the case's size, fixes seeds, sets `steps` and attaches PD Profiler to the video decode with the most nodes upstream. To pick a different node, set `profile_after` to its id.
4. Nothing else should be using the GPU: `nvidia-smi` sees the whole card. The runner subtracts the idle reading taken before each run.

## Run

From the pack folder, with ComfyUI's Python:

```bash
python tools/gpu_validation/run_validation.py my_config.json --dry-run
```

```bash
python tools/gpu_validation/run_validation.py my_config.json
```

`--only sdxl,flux1` runs only cases whose names start with those. If a run stops partway, `--resume <results folder>` skips the runs already recorded.

Then make the tables:

```bash
python tools/gpu_validation/tabulate.py tools/gpu_validation/results/<folder>
```

Send back the whole results folder (`results.jsonl`, `machine.json`, `tables.md`, the server logs and `sidecars/`). The calibration work needs the raw data, not only the tables.

## What runs

| Session | ComfyUI flags | Cases | Purpose |
|---|---|---|---|
| `dynamic` | defaults | all | Dynamic VRAM, ComfyUI's default on NVIDIA |
| `estimate` | `--disable-dynamic-vram` | all | The estimate-based loading the verdicts model |
| `<mode>_emu<X>gb` | `--reserve-vram` (card − X + ComfyUI's OS margin), `PD_VRAM_CAP_GB=X` | `emulate_cases` | Emulated X GB card: are fits / offloads / over budget right? |

In each full-card session, every case is evaluated at the full card and at each `emulate_gb` before it runs. The emulated sessions are judged against those evaluations. A profiler running inside a `--reserve-vram` server would take the large reserve as its OS margin and count it on top of the emulated card.

`--reserve-vram` only changes how ComfyUI plans weight loading. Sampling and decode could still use the whole 48 GB, so a stage that would run out of memory on 8 GB would succeed. The `vram_cap` module caps PyTorch's allocator at X GB, so those stages really fail. Memory that Dynamic VRAM maps outside PyTorch isn't capped, so treat out-of-memory results in emulated `dynamic` sessions as approximate. Set `"vram_cap": false` to emulate with `--reserve-vram` alone.

Each case runs 2 to 8 steps. Peak memory is reached in the first step, so more steps would only add time.

## Time and disk

The example matrix is about 100 runs. It hasn't been timed on an A6000 yet. Expect several hours, mostly spent on the 14B video models at 720p. Wan 2.2 A14B's two fp16 experts are about 57 GB together, plus the text encoder, so the offloading runs need well over 64 GB of system RAM to avoid swapping.
