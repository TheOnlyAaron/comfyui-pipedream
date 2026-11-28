"""
Run PD Profiler's GPU validation matrix against a real ComfyUI.

Usage, with ComfyUI's own Python (it needs aiohttp, which ComfyUI ships)::

    python tools/gpu_validation/run_validation.py config.json
    python tools/gpu_validation/run_validation.py config.json --only sdxl --dry-run
    python tools/gpu_validation/run_validation.py config.json --resume results/20261201_0900

For every server configuration, the script starts ComfyUI (``main.py``
from the config's ``comfy.dir``) on a private port, logs its output, and
for each case:

1. frees models (``POST /free``) and records the idle ``nvidia-smi`` reading;
2. presses **profile** (``POST /pipedream/profiler/evaluate``) at the full
   card and at each emulated ``vram_gb``, keeping the reports;
3. queues the graph with PD Profiler attached (``export_sidecar`` and
   ``vram_per_node`` on, the sidecar in a folder of its own) and follows
   ComfyUI's websocket for node start times;
4. records the outcome (success, out of memory, other error), ComfyUI's
   "loaded partially / completely" and tiled-decode fallback log lines, and
   ``nvidia-smi``'s peak over the run and over each node.

Server configurations, in order:

* ``dynamic``: ComfyUI's defaults (Dynamic VRAM on NVIDIA with PyTorch 2.8+);
* ``estimate``: ``--disable-dynamic-vram``, the estimate-based loading the
  profiler's verdicts model;
* for each ``emulate_gb`` X and each of ``emulate_modes``: ``--reserve-vram``
  set so ComfyUI plans for an X GB card (card total − X + ComfyUI's default
  OS margin), plus ``PD_VRAM_CAP_GB=X`` with ``vram_cap`` on, which caps
  PyTorch's allocator so stages over X really run out of memory (see
  ``vram_cap/__init__.py``).  Only ``emulate_cases`` run here; their
  verdicts come from step 2 of the full-card sessions, because the
  profiler in a ``--reserve-vram`` server would count the large reserve as
  its OS margin on top of the emulated card.

Each run is a line of ``results.jsonl`` in the results folder, next to the
server logs and the sidecars.  ``tabulate.py`` turns the folder into tables.
"""

import argparse
import asyncio
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import graphs  # noqa: E402

try:
    import aiohttp
except ImportError:
    aiohttp = None

GIB = 1024 ** 3
CAP_LINK = "pd_vram_cap"
OOM_MARKERS = ("outofmemory", "out of memory", "allocation on device")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
LOG_MARKERS = ("loaded partially", "loaded completely", "Unloaded partially",
               "retrying with tiled", "Requested to load", "out of memory")


# ---------------------------------------------------------------------------
# nvidia-smi
# ---------------------------------------------------------------------------

class SmiSampler:
    """``nvidia-smi`` memory.used samples (MiB) with their timestamps, in a thread."""

    def __init__(self, gpu=0, interval_ms=200):
        self.samples = []
        self.gpu, self.interval = gpu, interval_ms
        self.proc = None
        self.thread = None

    def start(self):
        if not shutil.which("nvidia-smi"):
            print("nvidia-smi not found: runs carry no nvidia-smi readings", file=sys.stderr)
            return self
        self.proc = subprocess.Popen(
            ["nvidia-smi", "-i", str(self.gpu), "--query-gpu=timestamp,memory.used",
             "--format=csv,noheader,nounits", f"-lms={self.interval}"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()
        return self

    def _read(self):
        for line in self.proc.stdout:
            try:
                stamp, used = [p.strip() for p in line.split(",")]
                t = datetime.strptime(stamp, "%Y/%m/%d %H:%M:%S.%f").timestamp()
                self.samples.append((t, float(used)))
            except ValueError:
                continue

    def stop(self):
        if self.proc:
            self.proc.terminate()

    def window(self, t0, t1) -> list:
        return [mb for t, mb in self.samples if t0 <= t <= t1]

    def peak(self, t0, t1):
        values = self.window(t0, t1)
        return max(values) if values else None

    def idle(self, seconds=1.5):
        now = time.time()
        values = self.window(now - seconds, now)
        return statistics.median(values) if values else None


def smi_query(field, gpu=0):
    try:
        out = subprocess.run(["nvidia-smi", "-i", str(gpu), f"--query-gpu={field}",
                              "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=20).stdout.strip()
        return out or None
    except (OSError, subprocess.SubprocessError):
        return None


def default_os_margin_gb(total_gb) -> float:
    """ComfyUI's EXTRA_RESERVED_VRAM: 0.4 GB, 0.6 on Windows (0.7 on cards over 15 GB)."""
    if os.name == "nt":
        return 0.7 if total_gb * 1024 > 15 * 1024 else 0.6
    return 0.4


# ---------------------------------------------------------------------------
# ComfyUI server
# ---------------------------------------------------------------------------

def git_head(path):
    try:
        return subprocess.run(["git", "-C", path, "log", "-1", "--format=%h %cs"],
                              capture_output=True, text=True, timeout=20).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


class Server:
    """One ComfyUI process with given arguments, its output in a log file."""

    def __init__(self, cfg, name, extra_args, env_extra, log_dir):
        comfy = cfg["comfy"]
        self.dir = comfy["dir"]
        self.python = comfy.get("python") or sys.executable
        self.port = int(comfy.get("port", 8199))
        self.url = f"http://127.0.0.1:{self.port}"
        self.args = list(comfy.get("args", [])) + list(extra_args)
        self.env = dict(os.environ, **env_extra)
        self.log_path = os.path.join(log_dir, f"server_{name}.log")
        self.proc = None
        self.log = None

    def start(self, timeout=900):
        cmd = [self.python, "main.py", "--listen", "127.0.0.1", "--port", str(self.port),
               "--disable-auto-launch", *self.args]
        self.log = open(self.log_path, "ab")
        self.log.write(f"\n==== {datetime.now():%Y-%m-%d %H:%M:%S} {' '.join(cmd)}\n".encode())
        self.log.flush()
        self.proc = subprocess.Popen(cmd, cwd=self.dir, env=self.env,
                                     stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.time() + timeout
        import urllib.request
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"ComfyUI exited at start; see {self.log_path}")
            try:
                with urllib.request.urlopen(self.url + "/system_stats", timeout=5) as r:
                    return json.loads(r.read())
            except OSError:
                time.sleep(2)
        raise RuntimeError(f"ComfyUI did not start in {timeout} s; see {self.log_path}")

    def log_offset(self):
        self.log.flush()
        return os.path.getsize(self.log_path)

    def log_since(self, offset) -> list:
        self.log.flush()
        with open(self.log_path, "rb") as fh:
            fh.seek(offset)
            text = fh.read().decode("utf-8", "replace")
        return [ANSI.sub("", line).strip() for line in text.splitlines()
                if any(m.lower() in line.lower() for m in LOG_MARKERS)]

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(60)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.log:
            self.log.close()


# ---------------------------------------------------------------------------
# One case
# ---------------------------------------------------------------------------

async def free_models(session, url):
    async with session.post(url + "/free", json={"unload_models": True, "free_memory": True}):
        pass
    await asyncio.sleep(4)


async def evaluate(session, url, prompt) -> dict:
    body = {"prompt": prompt, "node_id": graphs.PROFILER_ID}
    async with session.post(url + "/pipedream/profiler/evaluate", json=body) as r:
        data = await r.json()
    if "error" in data:
        return {"error": data["error"]}
    return data["report"]


async def queue_and_follow(session, url, prompt, timeout) -> dict:
    """Queue *prompt*; node start times, cached nodes and the outcome from the websocket."""
    client = uuid.uuid4().hex
    events = {"starts": [], "cached": [], "error": None, "t_queued": time.time()}
    async with session.ws_connect(f"{url}/ws?clientId={client}", max_msg_size=0) as ws:
        async with session.post(url + "/prompt", json={"prompt": prompt, "client_id": client}) as r:
            data = await r.json()
        if "prompt_id" not in data:
            events["error"] = {"type": "rejected", "message": json.dumps(data)[:2000]}
            events["t_end"] = time.time()
            return events
        pid = events["prompt_id"] = data["prompt_id"]
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                msg = await ws.receive(timeout=max(1.0, deadline - time.time()))
            except asyncio.TimeoutError:
                break
            if msg.type != aiohttp.WSMsgType.TEXT:
                if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
                continue
            item = json.loads(msg.data)
            kind, d = item.get("type"), item.get("data") or {}
            if d.get("prompt_id") not in (None, pid):
                continue
            now = time.time()
            if kind == "execution_start":
                events["t_start"] = now
            elif kind == "execution_cached":
                events["cached"] += [str(n) for n in d.get("nodes", [])]
            elif kind == "executing":
                if d.get("node") is None:
                    events["t_end"] = now
                    break
                events["starts"].append((str(d["node"]), now))
            elif kind == "execution_error":
                events["error"] = {"type": d.get("exception_type", ""),
                                   "message": str(d.get("exception_message", ""))[:2000],
                                   "node": d.get("node_id"), "class": d.get("node_type")}
            elif kind == "execution_interrupted":
                events["error"] = {"type": "interrupted", "message": ""}
        else:
            events["error"] = events["error"] or {"type": "timeout", "message": f"{timeout} s"}
            async with session.post(url + "/interrupt", json={}):
                pass
        events.setdefault("t_end", time.time())
    return events


def node_windows(events) -> dict:
    """
    node id -> (start, end) from consecutive websocket start times.  PD
    Profiler is left out: its lazy input makes it start first and resume
    last, so its window would be the whole run.
    """
    starts = [s for s in events.get("starts", []) if s[0] != graphs.PROFILER_ID]
    out = {}
    for i, (nid, t0) in enumerate(starts):
        t1 = starts[i + 1][1] if i + 1 < len(starts) else events.get("t_end", t0)
        a, b = out.get(nid, (t0, t1))
        out[nid] = (min(a, t0), max(b, t1))
    return out


def outcome(events) -> str:
    err = events.get("error")
    if not err:
        return "ok"
    text = f"{err.get('type', '')} {err.get('message', '')}".lower()
    if any(m in text for m in OOM_MARKERS):
        return "oom"
    return err.get("type") or "error"


async def run_case(session, server, smi, case, models, run_dir, session_name,
                   evaluate_gb, do_run=True, run_vram_gb=0.0, timeout=3600) -> dict:
    prompt, source = graphs.case_graph(case, models)
    run_id = f"{session_name}__{case['name']}"
    sidecar_dir = os.path.join(run_dir, "sidecars", run_id)
    os.makedirs(sidecar_dir, exist_ok=True)
    full = graphs.attach_profiler(prompt, source, run_vram_gb, sidecar_dir)
    result = {"run_id": run_id, "session": session_name, "case": case, "source": source,
              "prompt": full, "evaluations": {}}

    await free_models(session, server.url)
    result["smi_idle_mib"] = smi.idle()
    for gb in evaluate_gb:
        probe = graphs.attach_profiler(prompt, source, gb, "")
        result["evaluations"][str(gb)] = await evaluate(session, server.url, probe)
    if not do_run:
        return result

    offset = server.log_offset()
    events = await queue_and_follow(session, server.url, full, timeout)
    await asyncio.sleep(1.0)
    t0, t1 = events.get("t_start", events["t_queued"]), events.get("t_end", time.time())
    result.update({
        "outcome": outcome(events), "error": events.get("error"),
        "prompt_id": events.get("prompt_id"), "seconds": round(t1 - t0, 3),
        "cached": events.get("cached", []),
        "smi_peak_mib": smi.peak(t0, t1),
        "smi_node_peak_mib": {nid: smi.peak(a, b) for nid, (a, b) in node_windows(events).items()},
        "node_seconds_ws": {nid: round(b - a, 3) for nid, (a, b) in node_windows(events).items()},
        "log": server.log_since(offset),
    })
    sidecars = sorted(f for f in os.listdir(sidecar_dir) if f.endswith(".json"))
    if sidecars:
        result["sidecar"] = os.path.relpath(os.path.join(sidecar_dir, sidecars[-1]), run_dir)
    return result


# ---------------------------------------------------------------------------
# Matrix
# ---------------------------------------------------------------------------

def sessions(cfg, total_gb) -> list:
    """``(name, extra args, extra env, cases, evaluate?, emulated GB)`` in run order."""
    modes = cfg.get("modes", ["dynamic", "estimate"])
    flags = {"dynamic": [], "estimate": ["--disable-dynamic-vram"]}
    cases = cfg["cases"]
    out = [(mode, flags[mode], {}, cases, True, None) for mode in modes]
    names = set(cfg.get("emulate_cases") or [c["name"] for c in cases])
    emu_cases = [c for c in cases if c["name"] in names]
    margin = default_os_margin_gb(total_gb)
    for gb in cfg.get("emulate_gb", []):
        reserve = round(total_gb - gb + margin, 2)
        env = {"PD_VRAM_CAP_GB": str(gb)} if cfg.get("vram_cap", True) else {}
        for mode in cfg.get("emulate_modes", modes):
            out.append((f"{mode}_emu{gb:g}gb", flags[mode] + ["--reserve-vram", str(reserve)],
                        env, emu_cases, False, gb))
    return out


def link_cap(comfy_dir) -> str | None:
    target = os.path.join(comfy_dir, "custom_nodes", CAP_LINK)
    if os.path.exists(target):
        return None
    source = os.path.join(HERE, "vram_cap")
    try:
        os.symlink(source, target, target_is_directory=True)
    except OSError:
        shutil.copytree(source, target)
    return target


def load_done(path) -> set:
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as fh:
        return {json.loads(line)["run_id"] for line in fh if line.strip()}


async def main_async(args):
    with open(args.config, encoding="utf-8") as fh:
        cfg = json.load(fh)
    base = os.path.dirname(os.path.abspath(args.config))
    for case in cfg["cases"]:
        if case.get("template") and not os.path.isabs(case["template"]):
            case["template"] = os.path.join(base, case["template"])
    if args.only:
        wanted = set(args.only.split(","))
        cfg["cases"] = [c for c in cfg["cases"] if c["name"] in wanted
                        or any(c["name"].startswith(w) for w in wanted)]
    for case in cfg["cases"]:
        graphs.case_graph(case, cfg.get("models", {}))  # fail early on a bad case
    gpu = int(cfg.get("gpu_index", 0))
    total_mib = smi_query("memory.total", gpu)
    total_gb = float(total_mib) / 1024 if total_mib else float(cfg.get("card_gb", 48))
    plan = sessions(cfg, total_gb)

    if args.dry_run:
        for name, extra, env, cases, ev, gb in plan:
            print(f"{name}: {' '.join(extra) or '(defaults)'} {env or ''}")
            for c in cases:
                prompt, source = graphs.case_graph(c, cfg.get("models", {}))
                print(f"    {c['name']}: {len(prompt)} nodes, profiler after {source}")
        return

    run_dir = args.resume or os.path.join(cfg.get("results_dir", os.path.join(HERE, "results")),
                                          datetime.now().strftime("%Y%m%d_%H%M"))
    os.makedirs(run_dir, exist_ok=True)
    results_path = os.path.join(run_dir, "results.jsonl")
    done = load_done(results_path)
    machine = {"started": datetime.now().isoformat(timespec="seconds"),
               "gpu": smi_query("name", gpu), "driver": smi_query("driver_version", gpu),
               "vram_total_mib": total_mib, "os": platform.platform(),
               "comfyui": git_head(cfg["comfy"]["dir"]), "pack": git_head(PACK),
               "config": cfg}
    with open(os.path.join(run_dir, "machine.json"), "w", encoding="utf-8") as fh:
        json.dump(machine, fh, indent=2)

    linked = link_cap(cfg["comfy"]["dir"]) if cfg.get("emulate_gb") and cfg.get("vram_cap", True) else None
    smi = SmiSampler(gpu, int(cfg.get("smi_interval_ms", 200))).start()
    eval_gb = [0.0] + [float(g) for g in cfg.get("emulate_gb", [])]
    try:
        for name, extra, env, cases, do_eval, gb in plan:
            todo = [c for c in cases if f"{name}__{c['name']}" not in done]
            if not todo:
                continue
            server = Server(cfg, name, extra, env, run_dir)
            print(f"== {name}: starting ComfyUI {' '.join(extra)}", flush=True)
            stats = server.start()
            try:
                async with aiohttp.ClientSession() as session:
                    for case in todo:
                        print(f"   {case['name']} ...", end="", flush=True)
                        result = await run_case(
                            session, server, smi, case, cfg.get("models", {}), run_dir, name,
                            eval_gb if do_eval else [], run_vram_gb=gb or 0.0,
                            timeout=case.get("timeout", cfg.get("timeout", 3600)))
                        result.update({"mode": name.split("_")[0], "emulate_gb": gb,
                                       "server_args": extra, "server_env": env,
                                       "system_stats": stats})
                        with open(results_path, "a", encoding="utf-8") as fh:
                            fh.write(json.dumps(result, default=str) + "\n")
                        peak = result.get("smi_peak_mib")
                        print(f" {result.get('outcome')} {result.get('seconds', 0):.0f} s"
                              f"{f', nvidia-smi peak {peak / 1024:.1f} GiB' if peak else ''}",
                              flush=True)
            finally:
                server.stop()
                await asyncio.sleep(5)
    finally:
        smi.stop()
        if linked:
            print(f"Remove {linked} when the validation is done.")
    print(f"Results in {run_dir}. Tables: python {os.path.join(HERE, 'tabulate.py')} {run_dir}")


def main():
    if aiohttp is None:
        sys.exit("run_validation.py needs aiohttp: run it with ComfyUI's Python.")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("config", help="run config (see example_config.json)")
    parser.add_argument("--only", help="comma-separated case names or prefixes")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and graphs, run nothing")
    parser.add_argument("--resume", help="an earlier results folder: skip runs already in it")
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
