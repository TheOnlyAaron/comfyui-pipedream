"""
What PD Profiler measures while a prompt runs, and the machine it runs on.

ComfyUI reports node starts and finishes to the progress handlers of its
``comfy_execution.progress`` registry, which it creates afresh for every
prompt.  ``install()`` wraps the registry's constructor so each new
registry of a prompt with an enabled PD Profiler gets :class:`RunCapture`, a read-only handler that records:

* per node: wall-clock seconds, or "cached" when ComfyUI reused the result;
* the peak VRAM of the whole prompt (torch's allocator peak, reset when
  the prompt starts), plus the device memory in use (total minus free,
  which includes memory outside PyTorch's allocator) and Dynamic VRAM's
  own usage, both sampled as each node finishes;
* per node VRAM peaks, only when a PD Profiler in the prompt has
  ``vram_per_node`` on (the peak is reset as each node starts).

Nothing is changed in what ComfyUI does or sends.  On ComfyUI versions
without the progress registry, ``install()`` returns False and runs carry
no measurements.  The last few runs are kept by prompt id (``run``).

``machine()`` describes this machine: GPU name, VRAM and RAM in bytes.
"""

import sys
import time
from collections import OrderedDict

KEEP_RUNS = 8
PROFILER_CLASS = "PDProfiler"

_runs: OrderedDict = OrderedDict()
_installed = None


def _torch():
    try:
        import torch  # type: ignore[import-not-found]
    except ImportError:
        return None
    return torch if torch.cuda.is_available() else None


def _profilers(dynprompt) -> list:
    """Inputs of the enabled PD Profilers in the prompt."""
    prompt = getattr(dynprompt, "original_prompt", None) or {}
    return [node.get("inputs", {}) for node in prompt.values()
            if isinstance(node, dict) and node.get("class_type") == PROFILER_CLASS
            and node.get("inputs", {}).get("enabled", True) is not False]


def _dynamic_usage():
    """VRAM held by Dynamic VRAM (comfy-aimdo), or None when it is off."""
    try:
        import comfy.memory_management as memory  # type: ignore[import-not-found]
        if not getattr(memory, "aimdo_enabled", False):
            return None
        import comfy_aimdo.control as control  # type: ignore[import-not-found]
        return int(control.get_total_vram_usage())
    except Exception:
        return None


def run(prompt_id) -> dict | None:
    """The capture of *prompt_id* (``{"started", "nodes", "vram_peak", ...}``), or None."""
    return _runs.get(prompt_id)


def current_prompt_id():
    """The prompt being executed, from ComfyUI's progress registry, or None."""
    try:
        from comfy_execution.progress import get_progress_state  # type: ignore[import-not-found]
        return get_progress_state().prompt_id
    except Exception:
        return None


def snapshot(prompt_id) -> dict | None:
    """*prompt_id*'s capture with the prompt's VRAM peak so far filled in."""
    entry = _runs.get(prompt_id)
    if entry is None:
        return None
    torch = _torch()
    if torch is not None:
        try:
            current = torch.cuda.max_memory_allocated()
            entry["vram_peak"] = max(entry.get("vram_peak") or 0, current)
            entry["vram_reserved"] = max(entry.get("vram_reserved") or 0,
                                         torch.cuda.max_memory_reserved())
        except Exception:
            pass
    return entry


def install() -> bool:
    """Attach RunCapture to every new progress registry.  Safe to call twice."""
    global _installed
    if _installed is not None:
        return _installed
    try:
        from comfy_execution import progress  # type: ignore[import-not-found]
    except ImportError:
        _installed = False
        return False
    base = getattr(progress, "ProgressHandler", None)
    registry = getattr(progress, "ProgressRegistry", None)
    if base is None or registry is None:
        _installed = False
        return False

    class RunCapture(base):
        """Read-only progress handler recording node times and VRAM peaks."""

        def __init__(self, prompt_id, per_node):
            super().__init__("pipedream_profiler")
            self.entry = {"started": time.time(), "nodes": {}, "vram_peak": None,
                          "vram_reserved": None, "device_peak": None, "dynamic_peak": None,
                          "per_node": per_node}
            self._t0 = {}
            self.torch = _torch()
            if self.torch is not None:
                try:
                    self.torch.cuda.reset_peak_memory_stats()
                except Exception:
                    self.torch = None
            _runs[prompt_id] = self.entry
            while len(_runs) > KEEP_RUNS:
                _runs.popitem(last=False)

        def start_handler(self, node_id, state, prompt_id):
            self._t0[node_id] = time.perf_counter()
            if self.entry["per_node"] and self.torch is not None:
                try:
                    self._fold_peak()
                    self.torch.cuda.reset_peak_memory_stats()
                except Exception:
                    pass

        def update_handler(self, node_id, value, max_value, state, prompt_id, image=None):
            pass

        def finish_handler(self, node_id, state, prompt_id):
            nodes = self.entry["nodes"]
            started = self._t0.pop(node_id, None)
            if started is None:
                nodes.setdefault(node_id, {"seconds": 0.0, "cached": True})
                return
            item = nodes.get(node_id)
            if item is None or item.get("cached"):
                item = nodes[node_id] = {"seconds": 0.0, "cached": False}
            item["seconds"] += time.perf_counter() - started
            self._sample_device()
            if self.entry["per_node"] and self.torch is not None:
                try:
                    peak = self.torch.cuda.max_memory_allocated()
                    item["vram_peak"] = max(item.get("vram_peak") or 0, peak)
                    self._fold_peak(peak)
                except Exception:
                    pass

        def _sample_device(self):
            """Device memory in use and Dynamic VRAM usage, sampled at node ends."""
            if self.torch is None:
                return
            try:
                free, total = self.torch.cuda.mem_get_info()
                self.entry["device_peak"] = max(self.entry["device_peak"] or 0, total - free)
            except Exception:
                pass
            usage = _dynamic_usage()
            if usage is not None:
                self.entry["dynamic_peak"] = max(self.entry["dynamic_peak"] or 0, usage)

        def _fold_peak(self, peak=None):
            if peak is None:
                peak = self.torch.cuda.max_memory_allocated()
            self.entry["vram_peak"] = max(self.entry["vram_peak"] or 0, peak)
            self.entry["vram_reserved"] = max(self.entry["vram_reserved"] or 0,
                                              self.torch.cuda.max_memory_reserved())

        def reset(self):
            pass

    original = registry.__init__

    def __init__(self, prompt_id, dynprompt, *args, **kwargs):
        original(self, prompt_id, dynprompt, *args, **kwargs)
        try:
            profilers = _profilers(dynprompt)
            if profilers:
                per_node = any(p.get("vram_per_node") is True for p in profilers)
                self.register_handler(RunCapture(prompt_id, per_node))
        except Exception as exc:
            print(f"[Pipedream] PD Profiler could not watch this run: {exc}", file=sys.stderr)

    registry.__init__ = __init__
    _installed = True
    return True


def machine() -> dict:
    """``{"gpu", "vram", "ram"}`` for this machine (bytes; 0 when unknown)."""
    out = {"gpu": "", "vram": 0, "ram": 0}
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        device = mm.get_torch_device()
        if getattr(device, "type", "") != "cpu":
            out["vram"] = int(mm.get_total_memory(device))
            out["gpu"] = str(mm.get_torch_device_name(device)).split(" : ")[0]
        out["ram"] = int(mm.get_total_memory(mm.torch.device("cpu")))
    except Exception:
        pass
    if not out["ram"]:
        try:
            import psutil  # type: ignore[import-not-found]
            out["ram"] = int(psutil.virtual_memory().total)
        except Exception:
            pass
    return out


def loaded_models() -> list:
    """Models ComfyUI holds right now: name, size and bytes on the GPU."""
    out = []
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        for loaded in list(mm.current_loaded_models):
            patcher = loaded.model
            if patcher is None:
                continue
            inner = getattr(patcher, "model", None)
            out.append({"name": type(inner).__name__ if inner is not None else type(patcher).__name__,
                        "size": int(patcher.model_size()), "on_gpu": int(patcher.loaded_size())})
    except Exception:
        pass
    return out
