"""
API-format ComfyUI graphs for PD Profiler's GPU validation.

Two ways to get a graph, both returning an API prompt (``{id: {"class_type",
"inputs"}}``) with a PD Profiler attached as node ``"pd_profiler"``:

* ``build(case, models)``: built-in graphs from stock ComfyUI nodes for the
  families whose pipelines are a plain loader / encode / sample / decode
  chain: ``sdxl``, ``flux1``, ``wan21_t2v``, ``wan22_ti2v_5b``,
  ``wan22_a14b`` (two experts, KSamplerAdvanced split), ``hunyuan_video``
  and ``hunyuan15``.
* ``from_template(case)``: a workflow exported from ComfyUI with
  Workflow > Export (API), for pipelines with more moving parts (LTX-2.x
  and MiniMax H3 audio-video).  Every node with ``width``/``height``/
  ``length`` widgets gets the case's size, seeds are fixed, and ``steps``
  is overridden when the case gives it.

*case* is one entry of the run config (see ``example_config.json``);
*models* maps a role (``sdxl_ckpt``, ``wan14_t2v``, ...) to a file name as
ComfyUI lists it.  Standard library only.
"""

import copy
import json

PROFILER_ID = "pd_profiler"
NEGATIVE = "blurry, low quality"
PROMPT = "A lighthouse on a rocky coast at dusk, waves breaking, slow camera push in"


class GraphError(ValueError):
    """A case that can't be turned into a graph."""


def _need(models, *roles):
    missing = [r for r in roles if not models.get(r)]
    if missing:
        raise GraphError(f"config 'models' needs: {', '.join(missing)}")
    return [models[r] for r in roles]


def _ksampler(model, pos, neg, latent, steps, cfg, sampler="euler", scheduler="simple"):
    return {"class_type": "KSampler", "inputs": {
        "model": model, "positive": pos, "negative": neg, "latent_image": latent,
        "seed": 1, "steps": steps, "cfg": cfg, "sampler_name": sampler,
        "scheduler": scheduler, "denoise": 1.0}}


def _decode(case, samples, vae):
    if case.get("tiled"):
        return {"class_type": "VAEDecodeTiled", "inputs": {
            "samples": samples, "vae": vae, "tile_size": 512, "overlap": 64,
            "temporal_size": 64, "temporal_overlap": 8}}
    return {"class_type": "VAEDecode", "inputs": {"samples": samples, "vae": vae}}


def sdxl(case, models):
    (ckpt,) = _need(models, "sdxl_ckpt")
    w, h = case.get("width", 1024), case.get("height", 1024)
    return {
        "ckpt": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "pos": {"class_type": "CLIPTextEncode", "inputs": {"text": PROMPT, "clip": ["ckpt", 1]}},
        "neg": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE, "clip": ["ckpt", 1]}},
        "latent": {"class_type": "EmptyLatentImage",
                   "inputs": {"width": w, "height": h, "batch_size": case.get("batch", 1)}},
        "sample": _ksampler(["ckpt", 0], ["pos", 0], ["neg", 0], ["latent", 0],
                            case.get("steps", 4), case.get("cfg", 6.0), "euler", "normal"),
        "decode": _decode(case, ["sample", 0], ["ckpt", 2]),
    }


def flux1(case, models):
    unet, clip_l, t5, vae = _need(models, "flux1_unet", "clip_l", "t5xxl", "flux1_vae")
    w, h = case.get("width", 1024), case.get("height", 1024)
    return {
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": unet, "weight_dtype": case.get("weight_dtype", "default")}},
        "clip": {"class_type": "DualCLIPLoader", "inputs": {
            "clip_name1": clip_l, "clip_name2": t5, "type": "flux", "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "pos": {"class_type": "CLIPTextEncode", "inputs": {"text": PROMPT, "clip": ["clip", 0]}},
        "guide": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["pos", 0], "guidance": 3.5}},
        "neg": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["clip", 0]}},
        "latent": {"class_type": "EmptySD3LatentImage",
                   "inputs": {"width": w, "height": h, "batch_size": case.get("batch", 1)}},
        "sample": _ksampler(["unet", 0], ["guide", 0], ["neg", 0], ["latent", 0],
                            case.get("steps", 4), 1.0),
        "decode": _decode(case, ["sample", 0], ["vae", 0]),
    }


def _wan_common(case, models, unet_roles, vae_role):
    names = _need(models, *unet_roles, "umt5", vae_role)
    g = {}
    for i, unet in enumerate(names[:len(unet_roles)]):
        g[f"unet{i}"] = {"class_type": "UNETLoader", "inputs": {
            "unet_name": unet, "weight_dtype": case.get("weight_dtype", "default")}}
        g[f"shift{i}"] = {"class_type": "ModelSamplingSD3",
                          "inputs": {"model": [f"unet{i}", 0], "shift": case.get("shift", 8.0)}}
    g["clip"] = {"class_type": "CLIPLoader", "inputs": {
        "clip_name": names[-2], "type": "wan", "device": case.get("clip_device", "default")}}
    g["vae"] = {"class_type": "VAELoader", "inputs": {"vae_name": names[-1]}}
    g["pos"] = {"class_type": "CLIPTextEncode", "inputs": {"text": PROMPT, "clip": ["clip", 0]}}
    g["neg"] = {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE, "clip": ["clip", 0]}}
    return g


def _video_latent(case, cls="EmptyHunyuanLatentVideo", w=832, h=480, n=81):
    return {"class_type": cls, "inputs": {
        "width": case.get("width", w), "height": case.get("height", h),
        "length": case.get("length", n), "batch_size": case.get("batch", 1)}}


def wan21_t2v(case, models):
    role = case.get("unet_role", "wan14_t2v")
    g = _wan_common(case, models, [role], "wan21_vae")
    g["latent"] = _video_latent(case)
    g["sample"] = _ksampler(["shift0", 0], ["pos", 0], ["neg", 0], ["latent", 0],
                            case.get("steps", 4), case.get("cfg", 5.0), "uni_pc", "simple")
    g["decode"] = _decode(case, ["sample", 0], ["vae", 0])
    return g


def wan22_ti2v_5b(case, models):
    g = _wan_common(case, models, ["wan22_5b"], "wan22_vae")
    g["latent"] = {"class_type": "Wan22ImageToVideoLatent", "inputs": {
        "vae": ["vae", 0], "width": case.get("width", 1280), "height": case.get("height", 704),
        "length": case.get("length", 121), "batch_size": case.get("batch", 1)}}
    g["sample"] = _ksampler(["shift0", 0], ["pos", 0], ["neg", 0], ["latent", 0],
                            case.get("steps", 4), case.get("cfg", 5.0), "uni_pc", "simple")
    g["decode"] = _decode(case, ["sample", 0], ["vae", 0])
    return g


def wan22_a14b(case, models):
    """High-noise expert for the first half of the steps, low-noise for the rest."""
    g = _wan_common(case, models, ["wan22_a14b_high", "wan22_a14b_low"], "wan21_vae")
    steps = case.get("steps", 4)
    split = steps // 2
    g["latent"] = _video_latent(case, w=1280, h=720)
    common = {"positive": ["pos", 0], "negative": ["neg", 0], "noise_seed": 1, "steps": steps,
              "cfg": case.get("cfg", 3.5), "sampler_name": "euler", "scheduler": "simple"}
    g["sample_high"] = {"class_type": "KSamplerAdvanced", "inputs": dict(
        common, model=["shift0", 0], latent_image=["latent", 0], add_noise="enable",
        start_at_step=0, end_at_step=split, return_with_leftover_noise="enable")}
    g["sample_low"] = {"class_type": "KSamplerAdvanced", "inputs": dict(
        common, model=["shift1", 0], latent_image=["sample_high", 0], add_noise="disable",
        start_at_step=split, end_at_step=10000, return_with_leftover_noise="disable")}
    g["decode"] = _decode(case, ["sample_low", 0], ["vae", 0])
    return g


def hunyuan_video(case, models):
    unet, clip_l, llava, vae = _need(models, "hunyuan_unet", "clip_l", "llava_llama3", "hunyuan_vae")
    return {
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": unet, "weight_dtype": case.get("weight_dtype", "default")}},
        "clip": {"class_type": "DualCLIPLoader", "inputs": {
            "clip_name1": clip_l, "clip_name2": llava, "type": "hunyuan_video", "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "pos": {"class_type": "CLIPTextEncode", "inputs": {"text": PROMPT, "clip": ["clip", 0]}},
        "guide": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["pos", 0], "guidance": 6.0}},
        "latent": _video_latent(case, w=960, h=544, n=129),
        "sample": _ksampler(["unet", 0], ["guide", 0], ["guide", 0], ["latent", 0],
                            case.get("steps", 4), 1.0),
        "decode": _decode(case, ["sample", 0], ["vae", 0]),
    }


def hunyuan15(case, models):
    unet, qwen, byt5, vae = _need(models, "hunyuan15_unet", "qwen25vl", "byt5", "hunyuan15_vae")
    return {
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": unet, "weight_dtype": case.get("weight_dtype", "default")}},
        "shift": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["unet", 0], "shift": 7.0}},
        "clip": {"class_type": "DualCLIPLoader", "inputs": {
            "clip_name1": qwen, "clip_name2": byt5, "type": "hunyuan_video_15", "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "pos": {"class_type": "CLIPTextEncode", "inputs": {"text": PROMPT, "clip": ["clip", 0]}},
        "neg": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE, "clip": ["clip", 0]}},
        "cond": {"class_type": "HunyuanVideo15ImageToVideo", "inputs": {
            "positive": ["pos", 0], "negative": ["neg", 0], "vae": ["vae", 0],
            "width": case.get("width", 1280), "height": case.get("height", 720),
            "length": case.get("length", 121), "batch_size": case.get("batch", 1)}},
        "sample": _ksampler(["shift", 0], ["cond", 0], ["cond", 1], ["cond", 2],
                            case.get("steps", 4), case.get("cfg", 6.0)),
        "decode": _decode(case, ["sample", 0], ["vae", 0]),
    }


BUILDERS = {f.__name__: f for f in (sdxl, flux1, wan21_t2v, wan22_ti2v_5b, wan22_a14b,
                                    hunyuan_video, hunyuan15)}
SIZE_INPUTS = ("width", "height", "length")
SEED_INPUTS = ("seed", "noise_seed")


def upstream(prompt, root) -> set:
    """Ids *root* reads from, *root* included."""
    seen, todo = set(), [str(root)]
    while todo:
        nid = todo.pop()
        if nid in seen or nid not in prompt:
            continue
        seen.add(nid)
        for value in prompt[nid].get("inputs", {}).values():
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
                todo.append(value[0])
    return seen


def final_decode(prompt) -> str:
    """The video/image VAE decode with the most upstream nodes."""
    decodes = [nid for nid, node in prompt.items()
               if "decode" in node.get("class_type", "").lower()
               and "audio" not in node.get("class_type", "").lower()]
    if not decodes:
        raise GraphError("no VAE decode in the workflow: set 'profile_after' in the case")
    return max(decodes, key=lambda nid: len(upstream(prompt, nid)))


def from_template(case) -> dict:
    """An exported API workflow with the case's size, fixed seeds and optional steps."""
    with open(case["template"], encoding="utf-8") as fh:
        prompt = json.load(fh)
    if "nodes" in prompt and "links" in prompt:
        raise GraphError(f"{case['template']} is a UI workflow: export it with "
                         "Workflow > Export (API)")
    prompt = {str(k): v for k, v in prompt.items() if isinstance(v, dict) and "class_type" in v}
    for node in prompt.values():
        inputs = node.setdefault("inputs", {})
        for name in SIZE_INPUTS:
            if name in case and name in inputs and not isinstance(inputs[name], list):
                inputs[name] = case[name]
        for name in SEED_INPUTS:
            if name in inputs and not isinstance(inputs[name], list):
                inputs[name] = 1
        if "steps" in case and "steps" in inputs and not isinstance(inputs["steps"], list):
            inputs["steps"] = case["steps"]
    for nid, node in list(prompt.items()):
        if node["class_type"] == "PDProfiler":
            del prompt[nid]
    return prompt


def attach_profiler(prompt, source, vram_gb=0.0, sidecar_dir="", per_node=True) -> dict:
    """A copy of *prompt* with PD Profiler reading *source* (export and per-node peaks on)."""
    out = copy.deepcopy(prompt)
    out[PROFILER_ID] = {"class_type": "PDProfiler", "inputs": {
        "source": [str(source), 0], "enabled": True, "vram_gb": float(vram_gb), "ram_gb": 0.0,
        "vram_per_node": per_node, "export_sidecar": True,
        "path": sidecar_dir.rstrip("/\\") + "/" if sidecar_dir else ""}}
    return out


def case_graph(case, models) -> tuple:
    """``(prompt without profiler, node the profiler reads)`` for *case*."""
    if case.get("template"):
        prompt = from_template(case)
        return prompt, str(case.get("profile_after") or final_decode(prompt))
    builder = BUILDERS.get(case.get("builder", ""))
    if builder is None:
        raise GraphError(f"case {case.get('name')!r}: 'builder' must be one of "
                         f"{', '.join(BUILDERS)}, or give a 'template'")
    prompt = builder(case, models)
    return prompt, case.get("profile_after") or final_decode(prompt)
