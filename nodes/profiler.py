"""
PD Profiler node.

Connect ``source`` to anything (after PD Save, or off a branch): the
node profiles everything that input reads from, and nothing else, so
several flows in one graph each get their own numbers.  Its one output is
the profile as EXR metadata (``profile_metadata``) for PD Save, which
needs the profiler branched off before PD Save.

* **profile** (button, ``web/pd_profiler.js``): evaluates without
  queuing anything, through ``POST /pipedream/profiler/evaluate``.
* **queued runs**: the node also runs with the graph (``enabled``) and adds
  what was measured: node times, the run's VRAM peak (per node with
  ``vram_per_node``), the models ComfyUI holds and the input it received.
  ``export_sidecar`` writes the profile as JSON (``profile_path``).

``vram_gb`` and ``ram_gb`` emulate another machine's memory; 0 (or the
"use this machine" button, which fills in this machine's values through
``GET /pipedream/profiler/machine``) budgets against this machine.

The analysis is in ``core/profiler.py``, the model file reading in
``core/model_files.py`` and the run measurements in ``core/capture.py``.
"""

import asyncio
import os
import sys
import time

from ..core import capture, settings
from ..core.comfy import server_routes
from ..core.common import ANY, display_name
from ..core.exr_meta import ExrMetadata
from ..core.media import write_sidecar
from ..core.profiler import (
    GIB,
    ComfyEnv,
    Graph,
    NodeInfo,
    build_chart,
    build_profile,
    estimate_time,
    fmt_bytes,
    format_report,
    profile_metadata,
    profile_path,
    timings_from_run,
)
from ..core.wedge import CLASS_TYPE as WEDGE_CLASS, job_state

def comfy_env() -> ComfyEnv:
    """A ComfyEnv backed by the running ComfyUI (empty pieces outside it)."""
    env = ComfyEnv()
    try:
        import nodes as comfy_nodes  # type: ignore[import-not-found]
    except ImportError:
        comfy_nodes = None
    if comfy_nodes is not None:
        classes = comfy_nodes.NODE_CLASS_MAPPINGS
        names = getattr(comfy_nodes, "NODE_DISPLAY_NAME_MAPPINGS", {})
        cache = {}

        def node_info(class_type):
            if class_type in cache:
                return cache[class_type]
            klass = classes.get(class_type)
            info = None
            if klass is not None:
                try:
                    spec = klass.INPUT_TYPES() or {}
                except Exception:
                    spec = {}
                inputs = {**spec.get("required", {}), **spec.get("optional", {})}
                try:
                    returns = tuple(str(t) for t in (getattr(klass, "RETURN_TYPES", ()) or ()))
                except Exception:
                    returns = ()
                try:
                    api = bool(getattr(klass, "API_NODE", False))
                except Exception:
                    api = False
                module = getattr(klass, "RELATIVE_PYTHON_MODULE", "") or getattr(klass, "__module__", "")
                api = api or "comfy_api_nodes" in str(module)
                info = NodeInfo(inputs=inputs, returns=returns, api=api,
                                name=names.get(class_type, class_type))
            cache[class_type] = info
            return info

        env.node_info = node_info
    try:
        import folder_paths  # type: ignore[import-not-found]

        def resolve(folders, name):
            for folder in folders:
                try:
                    path = folder_paths.get_full_path(folder, name)
                except Exception:
                    path = None
                if path:
                    return path
            return None

        def image_size(name):
            try:
                from PIL import Image
                with Image.open(folder_paths.get_annotated_filepath(name)) as img:
                    return img.size
            except Exception:
                return None

        env.resolve, env.image_size = resolve, image_size
    except ImportError:
        pass
    try:
        import torch  # type: ignore[import-not-found]
        import comfy.model_detection as detection  # type: ignore[import-not-found]
        import comfy.model_management as mm  # type: ignore[import-not-found]
        env.torch, env.model_detection, env.model_management = torch, detection, mm
        env.gpu = getattr(mm.get_torch_device(), "type", "cpu") != "cpu"
        env.attention_fast = (not env.gpu
                              or bool(mm.xformers_enabled() or mm.pytorch_attention_flash_attention()))
        env.reserve = float(mm.minimum_inference_memory())
        env.os_margin = float(mm.extra_reserved_memory())
        env.vram_state = getattr(mm.vram_state, "name", str(mm.vram_state))
        try:
            import comfy.memory_management as memory  # type: ignore[import-not-found]
            env.dynamic_vram = bool(getattr(memory, "aimdo_enabled", False))
        except Exception:
            env.dynamic_vram = False
    except Exception:
        pass
    return env


def make_budget(vram_gb, ram_gb) -> dict:
    """The memory to budget against: the widgets when set, else this machine.

    A linked widget (a ``[node, slot]`` pair in an API prompt) counts as unset.
    """
    vram_gb = vram_gb if isinstance(vram_gb, (int, float)) else 0
    ram_gb = ram_gb if isinstance(ram_gb, (int, float)) else 0
    machine = capture.machine()
    vram = float(vram_gb or 0) * GIB or machine["vram"]
    ram = float(ram_gb or 0) * GIB or machine["ram"]
    emulated = (bool(vram_gb) and abs(vram - machine["vram"]) > 0.05 * GIB
                or bool(ram_gb) and abs(ram - machine["ram"]) > 0.05 * GIB)
    return {"vram": vram, "ram": ram, "emulated": emulated, "machine": machine}


def describe_source(value) -> str:
    """One line about the value the profiler received."""
    try:
        if hasattr(value, "shape") and hasattr(value, "dtype"):
            nbytes = value.numel() * value.element_size()
            return f"tensor {list(value.shape)} {str(value.dtype).replace('torch.', '')} {fmt_bytes(nbytes)}"
        if isinstance(value, dict) and hasattr(value.get("samples"), "shape"):
            s = value["samples"]
            return f"LATENT {list(s.shape)} {str(s.dtype).replace('torch.', '')} {fmt_bytes(s.numel() * s.element_size())}"
        if hasattr(value, "get_dimensions"):
            w, h = value.get_dimensions()
            return f"VIDEO {w}×{h}"
        if isinstance(value, str):
            return f"text, {len(value)} characters"
        if isinstance(value, (list, tuple)):
            return f"{type(value).__name__} of {len(value)}"
    except Exception:
        pass
    return type(value).__name__


class PDProfiler:
    """Profile everything upstream of one input: memory, models, latents and time."""

    DISPLAY_NAME = display_name("PD Profiler")
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    RETURN_TYPES = ("EXR_METADATA",)
    RETURN_NAMES = ("exr_metadata",)
    OUTPUT_TOOLTIPS = (
        "This run's profile as EXR metadata under pipedream/profiler/ (budget, peak, each "
        "stage, latent, model paths, measured time and VRAM), for PD Save's exr_metadata. "
        "To use it, branch the profiler off before PD Save (after it would be a loop).",
    )

    @classmethod
    def INPUT_TYPES(cls):
        s = settings.get
        return {
            "required": {
                "source": (ANY, {
                    "lazy": True,
                    "tooltip": "Anything. Everything this input reads from is profiled; "
                               "other flows in the graph are ignored. Put it after PD "
                               "Save or branch it off a flow.",
                }),
            },
            "optional": {
                "enabled": ("BOOLEAN", {
                    "default": s("profiler.enabled"),
                    "tooltip": "Run with queued runs and report what was measured. Off: "
                               "the node does nothing on runs (the profile button still works).",
                }),
                "vram_gb": ("FLOAT", {
                    "default": s("profiler.vram_gb"), "min": 0.0, "max": 1024.0, "step": 0.5, "round": 0.1,
                    "tooltip": "GPU memory to budget against, in GB, e.g. a farm node's card. "
                               "0: this machine. 'use this machine' fills in this machine's.",
                }),
                "ram_gb": ("FLOAT", {
                    "default": s("profiler.ram_gb"), "min": 0.0, "max": 8192.0, "step": 0.5, "round": 0.1,
                    "tooltip": "System memory to budget against, in GB. 0: this machine.",
                }),
                "vram_per_node": ("BOOLEAN", {
                    "default": s("profiler.vram_per_node"),
                    "tooltip": "Also measure the VRAM peak of each node during runs. ComfyUI "
                               "has no 'node started' signal for custom nodes, so this listens "
                               "to the progress messages it already sends and resets torch's "
                               "peak counter at each node. It changes nothing in the run; off "
                               "by default because it touches a ComfyUI internal. Without it "
                               "you still get node times and the run's overall VRAM peak.",
                }),
                "export_sidecar": ("BOOLEAN", {
                    "default": s("profiler.export_sidecar"),
                    "tooltip": "Write the profile as JSON after each run: next to 'path' "
                               "(<name>.profile.json), or in output/pipedream_profiles.",
                }),
                "path": ("STRING", {
                    "default": "",
                    "tooltip": "Where the sidecar goes: link PD Save's path to write it "
                               "next to the output, or type a folder. Empty: "
                               "output/pipedream_profiles.",
                }),
            },
            "hidden": {"prompt": "PROMPT", "unique_id": "UNIQUE_ID"},
        }

    @classmethod
    def VALIDATE_INPUTS(cls, input_types):
        return True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def check_lazy_status(self, source=None, enabled=True, **kwargs):
        return ["source"] if enabled and source is None else []

    def execute(self, source=None, enabled=True, vram_gb=0.0, ram_gb=0.0, vram_per_node=False,
                export_sidecar=False, path="", prompt=None, unique_id=None):
        if not enabled:
            return {"ui": {"profile_text": ["PD Profiler is off for runs: turn 'enabled' on to "
                                            "measure, or press profile to evaluate."]},
                    "result": (ExrMetadata(),)}
        env = comfy_env()
        node_id = str(unique_id)
        report = build_profile(prompt or {}, node_id, env, make_budget(vram_gb, ram_gb))
        prompt_id = capture.current_prompt_id()
        run = capture.snapshot(prompt_id) if prompt_id else None
        graph = Graph(prompt or {}, env)
        actual = {"source": describe_source(source), "loaded_models": capture.loaded_models(),
                  "nodes": []}
        timings = {}
        if run is not None:
            for nid in graph.upstream(node_id):
                entry = run["nodes"].get(nid)
                if entry is not None:
                    actual["nodes"].append({"node": nid, "label": graph.label(nid), **entry})
            actual["vram_peak"] = run.get("vram_peak")
            actual["vram_reserved"] = run.get("vram_reserved")
            actual["device_peak"] = run.get("device_peak")
            actual["dynamic_peak"] = run.get("dynamic_peak")
            actual["vram_total"] = capture.machine()["vram"]
            timings = timings_from_run(prompt or {}, node_id, env, run, report)
            report["time"] = estimate_time(report, graph, graph.upstream(node_id), timings)
        else:
            report["notes"].append("This ComfyUI does not report node progress: no measurements.")
        for nid in graph.upstream(node_id):
            if graph.cls(nid) == WEDGE_CLASS:
                _, job, total = job_state(graph.node(nid).get("inputs", {}))
                if total > 1:
                    actual["job"] = f"{job + 1} of {total}"
                break

        if export_sidecar:
            now = time.strftime("%Y%m%d_%H%M%S")
            target = profile_path(path, now)
            try:
                os.makedirs(os.path.dirname(target), exist_ok=True)
            except OSError as exc:
                print(f"[Pipedream] PD Profiler: cannot create '{os.path.dirname(target)}': {exc}",
                      file=sys.stderr)
            written = write_sidecar(target, {
                "node": "PDProfiler", "prompt_id": prompt_id,
                "written": time.strftime("%Y-%m-%d %H:%M:%S"),
                "settings": settings.summary(), "profile": report, "measured": actual,
                "timings": timings,
            })
            actual["sidecar"] = written or f"failed: {target}"

        metadata = profile_metadata(report, actual, settings.get("exr.metadata_prefix"), prompt_id)
        return {"result": (metadata,),
                "ui": {"profile_text": [format_report(report, actual)],
                       "pd_profile_timings": [timings],
                       "pd_profile_chart": [build_chart(report, timings, actual)]}}


capture.install()

routes, web = server_routes()
if routes is not None:
    @routes.post("/pipedream/profiler/evaluate")
    async def profiler_evaluate_route(request):
        try:
            data = await request.json()
            prompt = data.get("prompt") or {}
            node_id = str(data.get("node_id", ""))
            if node_id not in prompt:
                return web.json_response({"error": "This PD Profiler is not in the prompt "
                                                   "(bypassed or muted?)."}, status=400)
            inputs = prompt[node_id].get("inputs", {})

            def work():
                env = comfy_env()
                budget = make_budget(inputs.get("vram_gb", 0), inputs.get("ram_gb", 0))
                report = build_profile(prompt, node_id, env, budget, data.get("timings") or {})
                return {"text": format_report(report), "report": report,
                        "chart": build_chart(report, data.get("timings") or {})}

            result = await asyncio.get_running_loop().run_in_executor(None, work)
            return web.json_response(result, dumps=_dumps)
        except Exception as exc:
            return web.json_response({"error": f"PD Profiler: {exc}"}, status=500)

    @routes.get("/pipedream/profiler/machine")
    async def profiler_machine_route(request):
        return web.json_response(capture.machine())


def _dumps(value):
    import json
    return json.dumps(value, default=str)
