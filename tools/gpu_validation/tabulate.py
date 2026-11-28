"""
Tables from a ``run_validation.py`` results folder, as Markdown.

    python tools/gpu_validation/tabulate.py results/20261201_0900 [> tables.md]

Also writes ``tables.md`` into the folder.  Four tables:

1. **Stages**: per run and stage, the estimate (weights, working memory,
   total, verdict) beside the measurement: PyTorch's per-node allocator
   peak from the sidecar (``vram_per_node``) and ``nvidia-smi``'s peak over
   the node minus the idle reading before the run.  For a text-encode
   stage (whose node is the loader) the measurement is the largest of the
   nodes that read the loader.
2. **Runs**: per run, the largest estimated stage beside PyTorch's peak
   allocated and reserved, the device memory in use at node ends, Dynamic
   VRAM's usage, ``nvidia-smi``'s peak, the outcome and time.
3. **Verdicts on emulated cards**: per emulated run, the verdicts the
   profiler gave at that ``vram_gb`` (evaluated in the full-card session of
   the same mode) beside what happened: out of memory, ComfyUI's partial
   loads, a tiled-decode fallback, and the time against the full-card run.
4. **Calibration**: per family, stage kind and mode, the median ratio of
   measured working memory to ComfyUI's estimate.  Measured working memory
   is the per-node PyTorch peak minus the estimated weights, on the
   estimate path when the stage fits (weights fully resident); under
   Dynamic VRAM it is the PyTorch peak alone, since paged weights sit
   outside the allocator.

Standard library only.
"""

import json
import os
import statistics
import sys
from collections import defaultdict

GIB = 1024 ** 3
MIB = 1024 ** 2


def gib(n, digits=2):
    return "–" if n is None else f"{n / GIB:.{digits}f}"


def load(run_dir) -> list:
    out = []
    with open(os.path.join(run_dir, "results.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            r["sidecar_data"] = None
            if r.get("sidecar"):
                try:
                    with open(os.path.join(run_dir, r["sidecar"]), encoding="utf-8") as sf:
                        r["sidecar_data"] = json.load(sf)
                except (OSError, ValueError):
                    pass
            out.append(r)
    return out


def family(run) -> str:
    return run["case"]["name"].split("-")[0]


def full_card_eval(runs, run, gb) -> dict | None:
    """The report at *gb* from the full-card session of *run*'s mode."""
    for other in runs:
        if other["session"] == run["mode"] and other["case"]["name"] == run["case"]["name"]:
            return other.get("evaluations", {}).get(str(float(gb)))
    return None


def full_card_run(runs, run):
    return next((o for o in runs if o["session"] == run["mode"]
                 and o["case"]["name"] == run["case"]["name"]), None)


def consumers(prompt, nid) -> list:
    return [k for k, node in prompt.items()
            if any(isinstance(v, list) and len(v) == 2 and str(v[0]) == str(nid)
                   for v in node.get("inputs", {}).values())]


def measured_stage(run, stage) -> tuple:
    """``(torch per-node peak, nvidia-smi node peak above idle)`` in bytes."""
    side = run.get("sidecar_data") or {}
    peaks = {str(n["node"]): n.get("vram_peak") for n in side.get("measured", {}).get("nodes", [])}
    nodes = [str(stage["node"])]
    if stage["kind"] in ("encode", "vision"):
        nodes = consumers(run["prompt"], stage["node"]) or nodes
    torch_vals = [peaks[n] for n in nodes if peaks.get(n)]
    smi = run.get("smi_node_peak_mib") or {}
    idle = run.get("smi_idle_mib") or 0
    smi_vals = [smi[n] for n in nodes if smi.get(n) is not None]
    return (max(torch_vals) if torch_vals else None,
            (max(smi_vals) - idle) * MIB if smi_vals else None)


def report_of(run) -> dict | None:
    """The estimate a full-card run is compared with."""
    if run.get("emulate_gb"):
        return None
    return run.get("evaluations", {}).get("0.0") or (run.get("sidecar_data") or {}).get("profile")


def stage_table(runs) -> list:
    lines = ["| Case | Mode | Stage | Weights | Working | Estimate | Verdict | PyTorch node peak "
             "| nvidia-smi node peak | PyTorch / estimate |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for run in runs:
        report = report_of(run)
        if not report or run.get("outcome") is None:
            continue
        for st in report.get("stages", []):
            torch_peak, smi_peak = measured_stage(run, st)
            ratio = f"{torch_peak / st['total']:.2f}" if torch_peak and st.get("total") else "–"
            lines.append(f"| {run['case']['name']} | {run['mode']} | {st['kind']} {st['label']} "
                         f"| {gib(st['weights'])} | {gib(st['working'])} | {gib(st.get('total'))} "
                         f"| {st.get('verdict', '')} | {gib(torch_peak)} | {gib(smi_peak)} | {ratio} |")
    return lines


def run_table(runs) -> list:
    lines = ["| Case | Session | Outcome | Time s | Estimate peak | PyTorch allocated | PyTorch reserved "
             "| Device in use | Dynamic VRAM | nvidia-smi peak (above idle) |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for run in runs:
        if run.get("outcome") is None:
            continue
        report = report_of(run) or full_card_eval(runs, run, run.get("emulate_gb") or 0) or {}
        peak = (report.get("peak") or {}).get("bytes")
        m = (run.get("sidecar_data") or {}).get("measured", {})
        smi, idle = run.get("smi_peak_mib"), run.get("smi_idle_mib") or 0
        smi_text = f"{smi / 1024:.2f} ({(smi - idle) / 1024:.2f})" if smi else "–"
        lines.append(f"| {run['case']['name']} | {run['session']} | {run['outcome']} "
                     f"| {run.get('seconds', 0):.0f} | {gib(peak)} | {gib(m.get('vram_peak'))} "
                     f"| {gib(m.get('vram_reserved'))} | {gib(m.get('device_peak'))} "
                     f"| {gib(m.get('dynamic_peak'))} | {smi_text} |")
    return lines


def observed(run) -> dict:
    log = run.get("log") or []
    partial = [l for l in log if "loaded partially" in l]
    offloaded = 0.0
    for line in partial:
        try:
            offloaded += float(line.split("MB offloaded")[0].rsplit(",", 1)[-1].strip().split()[-1])
        except (ValueError, IndexError):
            pass
    return {"oom": run.get("outcome") == "oom", "partial": len(partial),
            "offloaded_mb": offloaded, "tiled": any("retrying with tiled" in l for l in log)}


def agreement(verdicts, obs, mode, outcome) -> str:
    """'yes', 'no' or '?' (needs a person: e.g. streaming, judged by time)."""
    if outcome not in ("ok", "oom"):
        return "?"
    over = any(v == "does not fit" for v in verdicts)
    offload = any(v in ("offloads", "streams") for v in verdicts)
    fallback = any(v == "falls back to tiled decode" for v in verdicts)
    if obs["oom"]:
        return "yes" if over else "no"
    if over or fallback != obs["tiled"]:
        return "no"
    if mode == "estimate":
        if offload and obs["partial"]:
            return "yes"
        if not offload and not obs["partial"]:
            return "yes"
        return "no"
    return "yes" if not offload else "?"


def verdict_table(runs) -> list:
    lines = ["| Case | Card | Mode | Predicted (encode, sample, decode) | Outcome | Partial loads "
             "(MB offloaded) | Tiled fallback | Time vs 48 GB | Agrees |",
             "|---|---|---|---|---|---|---|---|---|"]
    for run in runs:
        gb = run.get("emulate_gb")
        if not gb or run.get("outcome") is None:
            continue
        report = full_card_eval(runs, run, gb) or {}
        verdicts = [s.get("verdict", "") for s in report.get("stages", [])]
        obs = observed(run)
        base = full_card_run(runs, run)
        slow = (f"×{run['seconds'] / base['seconds']:.2f}"
                if base and base.get("seconds") and run.get("outcome") == "ok" else "–")
        lines.append(f"| {run['case']['name']} | {gb:g} GB | {run['mode']} | {', '.join(verdicts) or '–'} "
                     f"| {run['outcome']} | {obs['partial']} ({obs['offloaded_mb']:.0f}) "
                     f"| {'yes' if obs['tiled'] else 'no'} | {slow} "
                     f"| {agreement(verdicts, obs, run['mode'], run['outcome'])} |")
    return lines


def calibration(runs) -> list:
    groups = defaultdict(list)
    for run in runs:
        report = report_of(run)
        if not report or run.get("outcome") != "ok":
            continue
        for st in report.get("stages", []):
            if st["kind"] not in ("sample", "decode") or not st.get("working"):
                continue
            torch_peak, _ = measured_stage(run, st)
            if not torch_peak:
                continue
            if run["mode"] == "estimate":
                if st.get("verdict") != "fits":
                    continue
                measured = torch_peak - st["weights"]
            else:
                measured = torch_peak
            groups[(family(run), st["kind"], run["mode"])].append(measured / st["working"])
    lines = ["| Family | Stage | Mode | Runs | Median measured / estimate | Range |",
             "|---|---|---|---|---|---|"]
    for (fam, kind, mode), ratios in sorted(groups.items()):
        lines.append(f"| {fam} | {kind} | {mode} | {len(ratios)} | {statistics.median(ratios):.2f} "
                     f"| {min(ratios):.2f}–{max(ratios):.2f} |")
    return lines


def machine_lines(run_dir) -> list:
    try:
        with open(os.path.join(run_dir, "machine.json"), encoding="utf-8") as fh:
            m = json.load(fh)
    except (OSError, ValueError):
        return []
    total = m.get("vram_total_mib")
    return [f"- GPU: {m.get('gpu')} ({float(total) / 1024:.1f} GiB), driver {m.get('driver')}"
            if total else f"- GPU: {m.get('gpu')}",
            f"- OS: {m.get('os')}", f"- ComfyUI: {m.get('comfyui')}", f"- PipeDream: {m.get('pack')}",
            f"- Started: {m.get('started')}"]


def tabulate(run_dir) -> str:
    runs = load(run_dir)
    parts = ["# PD Profiler GPU validation", "", *machine_lines(run_dir), "",
             "Sizes in GiB.", "",
             "## Stages (full card)", "", *stage_table(runs), "",
             "## Runs", "", *run_table(runs), "",
             "## Verdicts on emulated cards", "", *verdict_table(runs), "",
             "## Calibration", "", *calibration(runs), ""]
    return "\n".join(parts)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    text = tabulate(sys.argv[1])
    with open(os.path.join(sys.argv[1], "tables.md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)


if __name__ == "__main__":
    main()
