"""
PD Profiler core: what a branch of a ComfyUI graph needs, read from the
graph itself, the model file headers and ComfyUI's own formulas.

``build_profile(prompt, node_id, env)`` walks upstream from *node_id* in
an API prompt (the graph as it will run: subgraphs flattened, bypassed
nodes removed) and returns a JSON-friendly report; ``format_report``
turns it into the text shown on the node and ``build_chart`` into the
data for the chart (``web/pd_profiler_chart.js``).  See docs/profiler.md.

The walk follows links; at a PD Wedge only the selected row's input is
followed (the solo row if set, else the queued row, else row 1), so one wedge
job is profiled.  Socket types come from the node classes, which is how
the walk finds, without a list of node names:

* samplers: a node returning LATENT that reads a MODEL or GUIDER and a LATENT;
* VAE decodes: a node reading a VAE and a LATENT and returning IMAGE;
* text encoders: a node reading CLIP and returning CONDITIONING;
* loaders: the end of a MODEL, VAE, CLIP or CLIP_VISION chain, read
  through their file inputs (``unet_name``, ``ckpt_name``, ``clip_name*``,
  ``vae_name``, ``lora_name``);
* latent sources: the end of a LATENT chain; its width, height, length and
  batch widgets give the latent shape with ComfyUI's floor rounding.

Memory is split into stages, because ComfyUI frees only as much as the
next model load needs (models stay resident while there is room): each
text encoder, each sampler (weights + ComfyUI's ``memory_required``, for a
batch of two when it fits next to the weights, else one + the latent) and
each VAE decode (weights + ComfyUI's ``memory_used_decode``).  The peak is
the largest stage; verdicts follow ``load_models_gpu`` (see ``_verdicts``).
API nodes count as zero and are flagged.  How each number was checked
against ComfyUI and published models: docs/profiler-accuracy.md.

``env`` is a :class:`ComfyEnv`; outside ComfyUI (tests) it is built from
plain callables.  Nothing here imports torch or ComfyUI directly.
"""

import math
import os
import re
import time
from dataclasses import dataclass, field

from . import model_files as mfiles
from . import settings
from .comfy import output_directory
from .media import IMAGE_FORMATS
from .wedge import (
    CLASS_TYPE as WEDGE_CLASS,
    INPUT_PREFIX as WEDGE_INPUT,
    WedgeError,
    active_rows,
    is_link,
    job_state,
    plan,
    row_text,
    solo_position,
    to_float,
    to_int,
)

PROFILE_DIR = "pipedream_profiles"
GIB = 1024 ** 3
MIB = 1024 ** 2
# ComfyUI's minimum_inference_memory: 0.8 GiB plus an OS margin (extra_reserved_memory:
# 400 MB, 600 MB on Windows; --reserve-vram replaces the margin).
DEFAULT_OS_MARGIN = (600 if os.name == "nt" else 400) * MIB
DEFAULT_RESERVE = 0.8 * GIB + DEFAULT_OS_MARGIN
FILE_INPUTS = {
    "unet_name": ("diffusion_models", "unet", "unet_gguf"),
    "ckpt_name": ("checkpoints",),
    "vae_name": ("vae",),
    "lora_name": ("loras",),
    "clip_name": ("text_encoders", "clip", "clip_gguf"),
    "clip_name1": ("text_encoders", "clip", "clip_gguf"),
    "clip_name2": ("text_encoders", "clip", "clip_gguf"),
    "clip_name3": ("text_encoders", "clip", "clip_gguf"),
    "clip_name4": ("text_encoders", "clip", "clip_gguf"),
}
LATENT_CHANNEL_SCALES = {48: (16, 4), 32: (16, 4), 128: (32, 8), 16: (8, 4), 12: (8, 6), 4: (8, 1)}


@dataclass
class NodeInfo:
    """What the profiler needs from a node class."""

    inputs: dict = field(default_factory=dict)
    returns: tuple = ()
    api: bool = False
    name: str = ""


@dataclass
class ComfyEnv:
    """
    The ComfyUI pieces the profiler uses, each optional.

    ``node_info(class_type) -> NodeInfo | None``; ``resolve(folders, name)
    -> path | None``; ``image_size(name) -> (w, h) | None``;
    ``model_detection``, ``model_management`` and ``torch`` are the
    ComfyUI/torch modules or None; ``attention_fast`` says whether
    ComfyUI uses its xformers/flash memory formula.  ``gpu`` is False on
    a machine without one: the profile then uses ComfyUI's GPU formulas
    and data types (fast attention, 16-bit weights and VAE), since the
    numbers are only useful for a machine that has a GPU.
    """

    node_info: object = None
    resolve: object = None
    image_size: object = None
    model_detection: object = None
    model_management: object = None
    torch: object = None
    attention_fast: bool = True
    reserve: float = DEFAULT_RESERVE
    os_margin: float = DEFAULT_OS_MARGIN
    gpu: bool = True
    dynamic_vram: bool = False
    vram_state: str = "NORMAL_VRAM"


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

class Graph:
    """An API prompt with socket types and wedge-aware links."""

    def __init__(self, prompt: dict, env: ComfyEnv):
        self.prompt = prompt
        self.env = env
        self._info = {}

    def node(self, nid) -> dict:
        return self.prompt.get(str(nid), {})

    def cls(self, nid) -> str:
        return self.node(nid).get("class_type", "")

    def info(self, nid) -> NodeInfo:
        cls = self.cls(nid)
        if cls not in self._info:
            found = self.env.node_info(cls) if self.env.node_info else None
            self._info[cls] = found or NodeInfo(name=cls)
        return self._info[cls]

    def label(self, nid) -> str:
        name = (self.info(nid).name or self.cls(nid)).lstrip("\U0001F4AD ").strip()
        return f"#{nid} {name}"

    def selected_row(self, nid) -> int | None:
        """Row number a PD Wedge computes in this prompt (None without rows)."""
        inputs = self.node(nid).get("inputs", {})
        rows = active_rows(inputs)
        if not rows:
            return None
        position, _, _ = job_state(inputs)
        try:
            pinned = solo_position(rows, inputs.get("solo"))
        except WedgeError:
            pinned = None
        if pinned is not None:
            position = pinned
        return rows[min(position, len(rows) - 1)]["row"]

    def links(self, nid) -> list:
        """``(input_name, source_id, slot)`` for the links this node reads."""
        inputs = self.node(nid).get("inputs", {})
        out = []
        row = self.selected_row(nid) if self.cls(nid) == WEDGE_CLASS else None
        for name, value in inputs.items():
            if not is_link(value):
                continue
            if row is not None and name.startswith(WEDGE_INPUT) and name != f"{WEDGE_INPUT}{row}":
                continue
            out.append((name, str(value[0]), value[1]))
        return out

    def out_type(self, src, slot, depth=0) -> str:
        """
        The type of output *slot* of *src*.  A wildcard output (PD Wedge,
        PD Switch) takes the type of the input it passes on.
        """
        returns = self.info(src).returns
        typ = str(returns[slot]) if 0 <= slot < len(returns) else ""
        if typ != "*" or depth > 8:
            return typ
        for name, upstream, upslot in self.links(src):
            if name.startswith("input_"):
                found = self.out_type(upstream, upslot, depth + 1)
                if found and found != "*":
                    return found
        return typ

    def upstream(self, root) -> list:
        """Every node *root* reads from (not *root*), nearest first."""
        seen, order, queue = {str(root)}, [], [str(root)]
        while queue:
            nid = queue.pop(0)
            for _, src, _ in self.links(nid):
                if src not in seen and src in self.prompt:
                    seen.add(src)
                    order.append(src)
                    queue.append(src)
        return order

    def chain(self, nid, input_name, wanted) -> list:
        """
        Follow *input_name* of *nid*, then each node's first *wanted*-typed
        input, to the node that makes it.  Returns the nodes passed
        through, nearest first (the source last); a wildcard output (PD
        Switch, PD Wedge) is followed through.
        """
        wanted = (wanted,) if isinstance(wanted, str) else tuple(wanted)
        value = self.node(nid).get("inputs", {}).get(input_name)
        if not is_link(value):
            return []
        out, current, slot = [], str(value[0]), value[1]
        while current in self.prompt and current not in out:
            out.append(current)
            nxt = None
            for name, src, s in self.links(current):
                typ = self.out_type(src, s)
                if typ in wanted:
                    nxt = (src, s)
                    break
            if nxt is None:
                break
            current, slot = nxt
        return out

    def input_types(self, nid) -> dict:
        """Input name to declared type for the node's linked inputs."""
        return {name: self.out_type(src, slot) for name, src, slot in self.links(nid)}

    def value(self, nid, name, default=None):
        """
        A literal input, or the value of a constant node or PD Wedge feeding it.

        Returns *default* when the input is computed at run time.
        """
        raw = self.node(nid).get("inputs", {}).get(name, default)
        if not is_link(raw):
            return raw
        src, slot = str(raw[0]), raw[1]
        node = self.node(src)
        inputs = node.get("inputs", {})
        if node.get("class_type") == WEDGE_CLASS:
            row = self.selected_row(src)
            text = next((row_text(r) for r in active_rows(inputs) if r["row"] == row), "")
            return {1: text, 2: to_int(text), 3: to_float(text)}.get(slot, default)
        literals = [v for v in inputs.values() if not is_link(v)]
        if len(inputs) >= 1 and len(literals) == len(inputs) and "value" in inputs:
            return inputs["value"]
        if len(inputs) == 1 and literals:
            return literals[0]
        return default


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Models:
    """Loader nodes resolved to files and read once per profile."""

    def __init__(self, graph: Graph, env: ComfyEnv, notes: list):
        self.graph = graph
        self.env = env
        self.notes = notes
        self._files = {}

    def files(self, nid) -> list:
        """``(input_name, ModelFile | None, filename)`` for a loader's file inputs."""
        if nid in self._files:
            return self._files[nid]
        out = []
        inputs = self.graph.node(nid).get("inputs", {})
        vision = "vision" in self.graph.cls(nid).lower()
        for name, folders in FILE_INPUTS.items():
            filename = inputs.get(name)
            if not isinstance(filename, str) or not filename:
                continue
            if vision and name.startswith("clip_name"):
                folders = ("clip_vision",)
            path = self.env.resolve(folders, filename) if self.env.resolve else None
            mf = None
            if path:
                try:
                    mf = mfiles.read_header(path)
                except mfiles.HeaderError as exc:
                    self.notes.append(f"{self.graph.label(nid)}: {exc}")
            else:
                self.notes.append(f"{self.graph.label(nid)}: '{filename}' not found in "
                                  f"{', '.join(folders)}.")
            out.append((name, mf, filename))
        self._files[nid] = out
        return out

    def _part(self, nid, role, names):
        for name, mf, filename in self.files(nid):
            if name not in names or mf is None:
                continue
            if name == "ckpt_name":
                part = mf.subset(mfiles.CHECKPOINT_PREFIXES[role], strip=role in ("vae", "audio"))
                if not part and mf.tensors:
                    # No such section: ComfyUI loads a prefix-less file as the diffusion
                    # model, and the checkpoint has no VAE / text encoder / audio part.
                    return (mf, None, filename) if role == "diffusion" else (None, None, None)
                return mf, part, filename
            return mf, None, filename
        return None, None, None

    def audio(self, nid) -> dict | None:
        """A checkpoint's bundled audio VAE and vocoder (LTX-2), as weights only."""
        mf, tensors, filename = self._part(nid, "audio", ("ckpt_name",))
        if mf is None or not tensors:
            return None
        return {"node": nid, "file": filename, "path": mf.path, "format": mf.format,
                **mfiles.encoder_info(mf, tensors, self.env)}

    def diffusion(self, nid) -> dict | None:
        mf, tensors, filename = self._part(nid, "diffusion", ("unet_name", "ckpt_name"))
        if mf is None:
            return None
        weight_dtype = self.graph.value(nid, "weight_dtype", "default")
        info = mfiles.diffusion_info(mf, tensors, str(weight_dtype), self.env, filename)
        return {"node": nid, "file": filename, "path": mf.path, "format": mf.format, **info}

    def vae(self, nid) -> dict | None:
        mf, tensors, filename = self._part(nid, "vae", ("vae_name", "ckpt_name"))
        if mf is None:
            return None
        info = mfiles.vae_info(mf, tensors, self.env)
        return {"node": nid, "file": filename, "path": mf.path, "format": mf.format, "_info": info,
                **{k: v for k, v in info.items() if k != "amd"}}

    def encoders(self, nid, vision=False) -> list:
        names = ("clip_name", "clip_name1", "clip_name2", "clip_name3", "clip_name4")
        out = []
        for name, mf, filename in self.files(nid):
            if mf is None:
                continue
            if name in names:
                out.append({"node": nid, "file": filename, "path": mf.path, "format": mf.format,
                            **mfiles.encoder_info(mf, None, self.env)})
            elif name == "ckpt_name" and not vision:
                tensors = mf.subset(mfiles.CHECKPOINT_PREFIXES["text_encoder"])
                if tensors:
                    out.append({"node": nid, "file": filename, "path": mf.path, "format": mf.format,
                                **mfiles.encoder_info(mf, tensors, self.env)})
        return out

    def lora(self, nid) -> dict | None:
        for name, mf, filename in self.files(nid):
            if name == "lora_name" and mf is not None:
                return {"node": nid, "file": filename, "path": mf.path, "stored_bytes": mf.size}
        return None


# ---------------------------------------------------------------------------
# Memory formulas
# ---------------------------------------------------------------------------

def sampling_bytes(latent_shape, model: dict, env: ComfyEnv, batch: int = 2) -> float:
    """
    ComfyUI's ``BaseModel.memory_required`` for the latent batch times
    *batch*.  ``sampler_helpers.estimate_memory`` computes it for 2 (cond
    and uncond together; it decides which other models to evict) and 1
    (the minimum; the model's weights are loaded against this one).
    """
    if not latent_shape:
        return 0.0
    shape = [latent_shape[0] * batch] + list(latent_shape[1:])
    area = shape[0] * math.prod(shape[2:])
    factor = model.get("memory_usage_factor", 1.0)
    if env.attention_fast:
        return area * model.get("inference_bytes", 2) * 0.01 * factor * MIB
    return area * 0.15 * factor * MIB


def _minimax(model, vae) -> bool:
    family = str((model or {}).get("family", "")) + " " + str((vae or {}).get("family", ""))
    return "MiniMax" in family


def latent_scales(model: dict | None, vae: dict | None) -> tuple:
    """
    ``(spatial, temporal, channels, dims)`` for latents of this flow: from
    the model when ComfyUI identified it, else from the VAE, else guessed.
    """
    trusted = model if (model or {}).get("detected") == "comfy" else None
    known_vae = vae if (vae or {}).get("family") else None
    if trusted:
        channels, dims = trusted["latent_channels"], trusted["latent_dims"]
    elif known_vae:
        channels = known_vae["latent_channels"]
        dims = 3 if known_vae["temporal"] > 1 else 2
    else:
        channels = (model or {}).get("latent_channels") or 4
        dims = (model or {}).get("latent_dims") or 2
    if vae and vae.get("family"):
        return vae["spatial"], vae["temporal"], channels, dims
    spatial, temporal = LATENT_CHANNEL_SCALES.get(channels, (8, 4))
    if channels == 128 and dims == 2:
        spatial, temporal = 16, 1
    return spatial, (temporal if dims == 3 else 1), channels, dims


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

def _is_sampler(graph, nid) -> bool:
    if "LATENT" not in graph.info(nid).returns:
        return False
    types = set(graph.input_types(nid).values())
    return "LATENT" in types and bool(types & {"MODEL", "GUIDER"})


def _is_decoder(graph, nid) -> bool:
    types = set(graph.input_types(nid).values())
    return {"VAE", "LATENT"} <= types and "IMAGE" in graph.info(nid).returns


def _is_encoder(graph, nid) -> bool:
    types = set(graph.input_types(nid).values())
    return "CLIP" in types and "CONDITIONING" in graph.info(nid).returns


def _input_named(graph, nid, wanted) -> str | None:
    for name, typ in graph.input_types(nid).items():
        if typ == wanted:
            return name
    return None


def _image_size(graph, nid, depth=0):
    """``(width, height, frames)`` of an IMAGE made by *nid*, or None."""
    if depth > 12:
        return None
    w, h = graph.value(nid, "width"), graph.value(nid, "height")
    if isinstance(w, (int, float)) and isinstance(h, (int, float)) and w > 0 and h > 0:
        frames = graph.value(nid, "batch_size", graph.value(nid, "length", 1))
        return int(w), int(h), int(frames) if isinstance(frames, (int, float)) else 1
    image = graph.value(nid, "image")
    if isinstance(image, str) and graph.env.image_size:
        size = graph.env.image_size(image)
        if size:
            return size[0], size[1], 1
    upstream = _input_named(graph, nid, "IMAGE")
    if upstream:
        src = graph.chain(nid, upstream, "IMAGE")
        if src:
            size = _image_size(graph, src[0], depth + 1)
            scale = graph.value(nid, "scale_by")
            if size and isinstance(scale, (int, float)):
                size = (round(size[0] * scale), round(size[1] * scale), size[2])
            return size
    return None


def latent_of(graph, nid, model, vae, notes, warnings, depth=0) -> dict | None:
    """
    Shape of the LATENT made by *nid*: a latent source, or a sampler or
    latent op, read through to its source.
    """
    if depth > 24:
        return None
    if _is_sampler(graph, nid) or _input_named(graph, nid, "LATENT") and not _input_named(graph, nid, "VAE"):
        name = _input_named(graph, nid, "LATENT")
        chain = graph.chain(nid, name, "LATENT") if name else []
        if not chain:
            return None
        latent = latent_of(graph, chain[0], model, vae, notes, warnings, depth + 1)
        if latent is None:
            return None
        return _apply_latent_op(graph, nid, latent)
    spatial, temporal, channels, dims = latent_scales(model, vae)
    w, h = graph.value(nid, "width"), graph.value(nid, "height")
    length = graph.value(nid, "length", graph.value(nid, "video_frames", graph.value(nid, "num_frames")))
    batch = graph.value(nid, "batch_size", 1)
    if graph.cls(nid) == "Wan22ImageToVideoLatent" and not any(n == "start_image" for n, _, _ in graph.links(nid)):
        batch = 1  # without start_image the node ignores batch_size (nodes_wan.py)
    source = "widgets"
    if not (isinstance(w, (int, float)) and isinstance(h, (int, float))):
        pixels = _input_named(graph, nid, "IMAGE")
        size = None
        if pixels:
            chain = graph.chain(nid, pixels, "IMAGE")
            size = _image_size(graph, chain[0]) if chain else None
        if size is None:
            notes.append(f"{graph.label(nid)}: latent size is only known at run time.")
            return None
        w, h, frames = size
        source = "image"
        if dims == 3:
            length, batch = frames, 1
        else:
            batch = frames
    w, h = int(w), int(h)
    batch = int(batch) if isinstance(batch, (int, float)) and batch > 0 else 1
    shape = [batch, channels]
    frames_out = 1
    if dims == 3:
        length = int(length) if isinstance(length, (int, float)) and length > 0 else 1
        if _minimax(model, vae):
            # MiniMax H3: frames snap up to 17k+5; latents are 5k+2 (nodes_minimax_h3.py).
            frames_out = length if length <= 5 else length + (-(length - 5)) % 17
            frames_out = max(5, frames_out)
            lt = 2 if frames_out <= 5 else (frames_out - 5) // 17 * 5 + 2
            shape.append(lt)
            if frames_out != length:
                warnings.append(f"{graph.label(nid)}: length {length} becomes {frames_out} frames "
                                "(MiniMax H3 snaps frame counts up to 17k+5).")
            shape += [h // spatial, w // spatial]
            return _latent_result(nid, source, shape, spatial, temporal, batch, frames_out, w, h,
                                  graph, warnings)
        lt = (length - 1) // temporal + 1
        shape.append(lt)
        frames_out = (lt - 1) * temporal + 1
        if frames_out != length:
            warnings.append(f"{graph.label(nid)}: length {length} gives {frames_out} frames "
                            f"(frame counts are {temporal}k+1); use {frames_out} or "
                            f"{frames_out + temporal}.")
    shape += [h // spatial, w // spatial]
    return _latent_result(nid, source, shape, spatial, temporal if dims == 3 else 1, batch,
                          frames_out if dims == 3 else batch, w, h, graph, warnings)


def _latent_result(nid, source, shape, spatial, temporal, batch, frames, w, h, graph, warnings):
    """The latent entry of a report, warning when the size loses pixels."""
    out_w, out_h = shape[-1] * spatial, shape[-2] * spatial
    for side, asked, got in (("width", w, out_w), ("height", h, out_h)):
        if asked != got:
            warnings.append(f"{graph.label(nid)}: {side} {asked} decodes to {got}: ComfyUI drops "
                            f"the last {asked - got} px. Use {got + spatial} (crop after) or {got}.")
    return {"node": nid, "source": source, "shape": shape, "width": out_w, "height": out_h,
            "frames": frames, "batch": batch, "spatial": spatial, "temporal": temporal}


def _apply_latent_op(graph, nid, latent):
    latent = dict(latent, shape=list(latent["shape"]))
    s = latent["spatial"]
    w, h = graph.value(nid, "width"), graph.value(nid, "height")
    scale = graph.value(nid, "scale_by")
    amount = graph.value(nid, "amount")
    if _is_sampler(graph, nid):
        return latent
    if isinstance(w, (int, float)) and isinstance(h, (int, float)) and w > 0 and h > 0:
        latent["shape"][-2:] = [int(h) // s, int(w) // s]
    elif isinstance(scale, (int, float)) and scale > 0:
        latent["shape"][-2:] = [round(latent["shape"][-2] * scale), round(latent["shape"][-1] * scale)]
    if isinstance(amount, int) and amount > 1 and "Repeat" in graph.cls(nid):
        latent["shape"][0] *= amount
        latent["batch"] *= amount
    latent["width"], latent["height"] = latent["shape"][-1] * s, latent["shape"][-2] * s
    return latent


def _tile_shape(graph, nid, shape, vae) -> list:
    """The latent shape of one tile of a tiled decode (ComfyUI's memory is per tile)."""
    shape = list(shape)
    tile = graph.value(nid, "tile_size")
    if isinstance(tile, int) and tile > 0:
        side = max(1, tile // vae["spatial"])
        shape[-2], shape[-1] = min(shape[-2], side), min(shape[-1], side)
    temporal = graph.value(nid, "temporal_size")
    if len(shape) == 5 and isinstance(temporal, int) and temporal > 0 and vae["temporal"] > 1:
        shape[2] = min(shape[2], max(2, temporal // vae["temporal"]))
    return shape


def _tokens(shape, model) -> int | None:
    patch = (model or {}).get("patch_size")
    if not patch or not shape:
        return None
    patch = tuple(patch) if isinstance(patch, (list, tuple)) else (patch,)
    spatial = shape[2:]
    if len(patch) < len(spatial):
        patch = (1,) * (len(spatial) - len(patch)) + patch
    return math.prod(math.ceil(d / p) for d, p in zip(spatial, patch[-len(spatial):]))


def _steps(graph, nid) -> int | None:
    steps = graph.value(nid, "steps")
    if isinstance(steps, int):
        end, start = graph.value(nid, "end_at_step"), graph.value(nid, "start_at_step")
        if isinstance(end, int) and isinstance(start, int):
            return max(0, min(end, steps) - start)
        return steps
    for name in ("sigmas",):
        chain = graph.chain(nid, name, "SIGMAS")
        for src in chain:
            value = graph.value(src, "steps")
            if isinstance(value, int):
                return value
    return None


def _cfg(graph, nid):
    cfg = graph.value(nid, "cfg")
    if cfg is None and "guider" in graph.node(nid).get("inputs", {}):
        chain = graph.chain(nid, "guider", "GUIDER")
        if chain:
            cfg = graph.value(chain[0], "cfg", 1.0 if "Basic" in graph.cls(chain[0]) else None)
    return cfg


def _model_loader(graph, nid):
    """``(loader, lora nodes)`` behind a sampler's MODEL (through a GUIDER)."""
    start, name = nid, _input_named(graph, nid, "MODEL")
    if name is None:
        guider = _input_named(graph, nid, "GUIDER")
        chain = graph.chain(nid, guider, "GUIDER") if guider else []
        if not chain:
            return None, []
        start, name = chain[-1], _input_named(graph, chain[-1], "MODEL")
        if name is None:
            return None, []
    chain = graph.chain(start, name, "MODEL")
    if not chain:
        return None, []
    loras = [n for n in chain if "lora_name" in graph.node(n).get("inputs", {})]
    return chain[-1], loras


def build_profile(prompt: dict, node_id, env: ComfyEnv, budget: dict | None = None,
                  timings: dict | None = None) -> dict:
    """
    Profile what *node_id* reads from in *prompt*.

    *budget* is ``{"vram", "ram", "emulated", "machine"}`` (bytes); *timings*
    maps node id to a measured ``{"seconds", "steps", "tokens", "class"}``.
    """
    node_id = str(node_id)
    graph = Graph(prompt, env)
    notes, warnings = [], []
    models = Models(graph, env, notes)
    up = graph.upstream(node_id)
    report = {"node": node_id, "evaluated": time.strftime("%Y-%m-%d %H:%M:%S"),
              "budget": budget or {}, "upstream": len(up), "notes": notes,
              "warnings": warnings, "api_nodes": [], "models": [], "latents": [],
              "stages": [], "loras": []}

    if env.dynamic_vram:
        notes.append("Dynamic VRAM is on: weights page in from RAM as needed, so an offload "
                     "verdict means streaming (slower), not a failure.")
    if env.vram_state in ("HIGH_VRAM", "SHARED"):
        notes.append("--highvram / --gpu-only: models stay on the GPU and are not partly "
                     "loaded, so a stage that doesn't fit runs out of memory instead of offloading.")
    elif env.vram_state == "NO_VRAM":
        notes.append("--novram: nearly all weights stream from RAM.")
    if not env.gpu:
        notes.append("No GPU on this machine: memory uses ComfyUI's GPU formulas and 16-bit "
                     "weights. Set vram_gb to budget against a card.")
    for nid in up:
        if graph.info(nid).api:
            report["api_nodes"].append({"node": nid, "class": graph.cls(nid),
                                        "name": graph.info(nid).name})

    vae_by_loader, diffusion_by_loader = {}, {}
    for nid in up:
        if not _is_decoder(graph, nid):
            continue
        vname = _input_named(graph, nid, "VAE")
        chain = graph.chain(nid, vname, "VAE") if vname else []
        if chain and chain[-1] not in vae_by_loader:
            vae_by_loader[chain[-1]] = models.vae(chain[-1])
    flow_vae = next((v for v in vae_by_loader.values() if v), None)

    sampler_latents = {}
    for nid in reversed(up):
        if not _is_sampler(graph, nid):
            continue
        loader, loras = _model_loader(graph, nid)
        model = None
        if loader is not None:
            if loader not in diffusion_by_loader:
                diffusion_by_loader[loader] = models.diffusion(loader)
            model = diffusion_by_loader[loader]
        for lora_node in loras:
            lora = models.lora(lora_node)
            if lora and lora not in report["loras"]:
                report["loras"].append(lora)
        latent = latent_of(graph, nid, model, flow_vae, notes, warnings)
        sampler_latents[nid] = latent
        if latent and latent not in report["latents"]:
            report["latents"].append(latent)
        weights = (model or {}).get("loaded_bytes", 0)
        shape = latent["shape"] if latent else None
        working = sampling_bytes(shape, model, env) if model and shape else 0
        single = sampling_bytes(shape, model, env, batch=1) if model and shape else 0
        latent_bytes = math.prod(shape) * 4 if shape else 0
        stage = {"kind": "sample", "node": nid, "label": graph.label(nid),
                 "weights": weights, "working": working, "extra": latent_bytes,
                 "working_batched": working, "working_single": single,
                 "steps": _steps(graph, nid), "cfg": _cfg(graph, nid),
                 "tokens": _tokens(shape, model), "model": loader}
        if model is None:
            stage["unknown"] = "model" if loader is None else "model file"
        if not shape:
            stage["unknown"] = stage.get("unknown", "latent size")
        report["stages"].append(stage)

    for nid in reversed(up):
        if not _is_decoder(graph, nid):
            continue
        vname = _input_named(graph, nid, "VAE")
        chain = graph.chain(nid, vname, "VAE") if vname else []
        vae = vae_by_loader.get(chain[-1]) if chain else None
        lname = _input_named(graph, nid, "LATENT")
        lchain = graph.chain(nid, lname, "LATENT") if lname else []
        latent = None
        if lchain:
            latent = sampler_latents.get(lchain[0]) or latent_of(
                graph, lchain[0], next(iter(diffusion_by_loader.values()), None), vae, notes, warnings)
        shape = latent["shape"] if latent else None
        decode = None
        tiled = "tile" in graph.cls(nid).lower()
        if vae and shape:
            one = [1] + list(shape[1:])
            if tiled:
                one = _tile_shape(graph, nid, one, vae)
            decode = vae["_info"].decode_bytes(one)
        frames = latent["frames"] * (latent["batch"] if len(shape or []) == 5 else 1) if latent else 0
        channels = 4 if (vae or {}).get("family") == "Qwen-Image 2.1" else 3
        out_bytes = latent["width"] * latent["height"] * channels * 4 * frames if latent else 0
        stage = {"kind": "decode", "node": nid, "label": graph.label(nid),
                 "weights": (vae or {}).get("loaded_bytes", 0), "working": decode or 0,
                 "extra": 0, "frames_out": out_bytes, "tiled": tiled,
                 "vae_family": (vae or {}).get("family", ""),
                 "pixels": [latent["width"], latent["height"], frames] if latent else None}
        if vae is None:
            stage["unknown"] = "VAE file"
        elif decode is None:
            stage["unknown"] = "VAE type" if not vae.get("family") else "latent size"
        report["stages"].append(stage)

    encoders_seen = set()
    for nid in up:
        if not _is_encoder(graph, nid):
            continue
        cname = _input_named(graph, nid, "CLIP")
        chain = graph.chain(nid, cname, "CLIP") if cname else []
        if not chain or chain[-1] in encoders_seen:
            continue
        loader = chain[-1]
        encoders_seen.add(loader)
        files = models.encoders(loader)
        report["models"] += [dict(f, role="text encoder") for f in files]
        report["stages"].insert(0, {"kind": "encode", "node": loader, "label": graph.label(loader),
                                    "weights": sum(f["loaded_bytes"] for f in files),
                                    "working": 0, "extra": 0,
                                    **({} if files else {"unknown": "encoder file"})})
    for nid in up:
        if "CLIP_VISION" in graph.info(nid).returns and not graph.links(nid):
            files = models.encoders(nid, vision=True)
            if files:
                report["models"] += [dict(f, role="clip vision") for f in files]
                report["stages"].insert(0, {"kind": "vision", "node": nid, "label": graph.label(nid),
                                            "weights": sum(f["loaded_bytes"] for f in files),
                                            "working": 0, "extra": 0})

    for loader in diffusion_by_loader:
        audio = models.audio(loader)
        if audio:
            report["models"].append(dict(audio, role="audio vae"))
    report["models"] = (
        [dict(m, role="diffusion") for m in diffusion_by_loader.values() if m]
        + [{k: v for k, v in dict(m, role="vae").items() if k != "_info"}
           for m in vae_by_loader.values() if m]
        + report["models"])
    _verdicts(report, env)
    report["ram"] = _ram(report, env)
    report["wedge"] = _wedge(prompt, node_id, graph, up)
    report["time"] = estimate_time(report, graph, up, timings or {})
    return report


def _verdicts(report, env):
    """
    Each stage's verdict against the VRAM budget, following ComfyUI's
    ``load_models_gpu``: a model's weights get the budget minus
    max(minimum_inference_memory, batch-1 estimate + OS margin); when the
    batch-2 estimate doesn't fit next to them, cond and uncond run one at a
    time (samplers.py).  VAE weights are offloaded or paged before a decode
    falls back to tiling; only an actual out-of-memory error tiles.
    """
    budget = report["budget"].get("vram") or 0
    margin = env.os_margin
    stream = "streams" if env.dynamic_vram else "offloads"
    peak = None
    for stage in report["stages"]:
        if stage["kind"] == "sample" and stage.get("working_single"):
            single, batched = stage["working_single"], stage["working_batched"]
            cfg = stage.get("cfg")
            if isinstance(cfg, (int, float)) and cfg == 1.0:
                stage["working"] = single
                stage["note"] = "cfg 1: one pass per step"
            elif budget and stage["weights"] + batched + stage["extra"] + margin > budget:
                stage["working"] = single
                stage["note"] = "cond and uncond run one at a time (both don't fit)"
        stage["total"] = stage["weights"] + stage["working"] + stage["extra"]
        if budget:
            if stage["kind"] == "decode":
                _decode_verdict(stage, budget, env, stream)
            else:
                reserve = max(env.reserve, stage["working"] + margin)
                room = budget - reserve - stage["extra"]
                if stage["working"] + stage["extra"] + margin > budget:
                    stage["verdict"] = "does not fit"
                elif stage["weights"] > room:
                    stage["offload"] = stage["weights"] - max(0.0, room)
                    stage["verdict"] = stream
                else:
                    stage["verdict"] = "fits"
        if peak is None or stage["total"] > peak["total"]:
            peak = stage
    report["peak"] = {"bytes": peak["total"], "node": peak["node"], "label": peak["label"],
                      "kind": peak["kind"]} if peak else None


def _decode_verdict(stage, budget, env, stream):
    """VAE decode: weights may be offloaded (not LTX 2.4's); the decode itself must fit."""
    decode = stage["working"]
    fixed = stage.get("vae_family") == "LTX 2.4"
    room = budget - env.os_margin - decode
    if not decode:
        stage["verdict"] = "fits" if stage["weights"] <= budget - env.reserve else stream
    elif decode + env.os_margin > budget or (fixed and stage["total"] + env.os_margin > budget):
        stage["verdict"] = "tiled" if stage.get("tiled") else "falls back to tiled decode"
    elif stage["weights"] > room:
        stage["offload"] = stage["weights"] - max(0.0, room)
        stage["verdict"] = stream
    else:
        stage["verdict"] = "fits"


def _ram(report, env=None) -> dict:
    """
    System RAM: model weights plus decoded frames (float32).  With Dynamic
    VRAM the weights are the memory-mapped files (stored size, reclaimable
    page cache); otherwise ComfyUI holds the loaded weights in RAM when a
    model is offloaded or between runs.
    """
    key = "stored_bytes" if env is not None and env.dynamic_vram else "loaded_bytes"
    weights = sum(m.get(key, m.get("loaded_bytes", 0)) for m in report["models"])
    frames = sum(s.get("frames_out", 0) for s in report["stages"])
    offload = max((s.get("offload", 0) for s in report["stages"]), default=0)
    total = weights + frames
    return {"weights": weights, "frames_out": frames, "offload": offload, "total": total}


def _wedge(prompt, node_id, graph, up) -> dict | None:
    try:
        wedge_plan = plan(prompt, [node_id])
    except WedgeError as exc:
        return {"error": str(exc)}
    if wedge_plan.get("total", 1) <= 1 and not wedge_plan.get("axes"):
        return None
    wedges = [n for n in up if graph.cls(n) == WEDGE_CLASS]
    rows = {n: graph.selected_row(n) for n in wedges}
    differ = []
    for n in wedges:
        sources = [src for name, src, _ in _all_links(graph, n) if name.startswith(WEDGE_INPUT)]
        if len(set(sources)) > 1:
            differ.append(n)
    return {"total": wedge_plan.get("total", 1),
            "axes": [{"tokens": a.get("tokens", []), "length": a.get("length", 1),
                      "rows": a.get("rows", 1), "solo": a.get("pinned") is not None}
                     for a in wedge_plan.get("axes", [])],
            "rows": rows, "branches": differ}


def _all_links(graph, nid):
    inputs = graph.node(nid).get("inputs", {})
    return [(k, str(v[0]), v[1]) for k, v in inputs.items() if is_link(v)]


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------

def estimate_time(report, graph, up, timings) -> dict | None:
    """
    Time for one queue of this flow, from measured node times.

    Samplers scale with steps and with latent tokens (linear: rough when
    the size changed).  With wedges, nodes downstream of a wedge or on a
    wedge row's branch run every job; the rest run once.
    """
    if not timings:
        return None
    stages = {s["node"]: s for s in report["stages"] if s["kind"] == "sample"}
    wedges = [n for n in up if graph.cls(n) == WEDGE_CLASS]
    per_job = set()
    for nid in up:
        if nid in wedges:
            per_job.add(nid)
            continue
        if any(w in graph.upstream(nid) for w in wedges):
            per_job.add(nid)
    for w in wedges:
        for name, src, _ in graph.links(w):
            if name.startswith(WEDGE_INPUT):
                per_job.add(src)
                per_job.update(n for n in graph.upstream(src) if n not in _shared(graph, w, src))
    once = per = 0.0
    scaled, unmeasured, rows = False, [], []
    for nid in up:
        t = timings.get(nid)
        if not t or t.get("class") not in (None, graph.cls(nid)):
            if not graph.info(nid).api:
                unmeasured.append(nid)
            continue
        seconds = float(t.get("seconds", 0))
        stage = stages.get(nid)
        if stage:
            if stage.get("steps") and t.get("steps"):
                factor = stage["steps"] / t["steps"]
                scaled |= abs(factor - 1) > 1e-6
                seconds *= factor
            if stage.get("tokens") and t.get("tokens"):
                factor = stage["tokens"] / t["tokens"]
                scaled |= abs(factor - 1) > 1e-6
                seconds *= factor
        if nid in per_job:
            per += seconds
        else:
            once += seconds
        rows.append((nid, seconds, nid in per_job))
    wedge = report.get("wedge") or {}
    jobs = int(wedge.get("total", 1) or 1)
    rows.sort(key=lambda r: -r[1])
    return {"once": once, "per_job": per, "jobs": jobs, "total": once + per * jobs,
            "scaled": scaled, "unmeasured": len(unmeasured),
            "measured": max((t.get("at", "") for t in timings.values()), default=""),
            "slowest": [{"node": n, "label": graph.label(n), "seconds": s, "per_job": p}
                        for n, s, p in rows[:4]]}


def _shared(graph, wedge, src) -> set:
    """Nodes on a row branch that the wedge's other inputs also read (cached across jobs)."""
    shared = set()
    for name, other, _ in graph.links(wedge):
        if other != src:
            shared.update(graph.upstream(other) + [other])
    return shared


def timings_from_run(prompt, node_id, env, run: dict, report: dict) -> dict:
    """Measured node times of this flow from a capture *run*, for later estimates."""
    graph = Graph(prompt, env)
    stages = {s["node"]: s for s in report.get("stages", []) if s["kind"] == "sample"}
    out = {}
    at = time.strftime("%Y-%m-%d %H:%M")
    for nid in graph.upstream(node_id):
        entry = run.get("nodes", {}).get(nid)
        if not entry or entry.get("cached"):
            continue
        item = {"seconds": round(entry["seconds"], 3), "class": graph.cls(nid), "at": at}
        stage = stages.get(nid)
        if stage:
            if stage.get("steps"):
                item["steps"] = stage["steps"]
            if stage.get("tokens"):
                item["tokens"] = stage["tokens"]
        out[nid] = item
    return out


def measured_peak(actual: dict | None):
    """
    The run's VRAM peak for the chart: the larger of torch's allocator peak
    and the device memory in use at node ends (which also counts memory
    Dynamic VRAM holds outside PyTorch's allocator, and other processes).
    """
    actual = actual or {}
    values = [v for v in (actual.get("vram_peak"), actual.get("device_peak")) if v]
    return max(values) if values else None


def build_chart(report: dict, timings: dict | None = None, actual: dict | None = None) -> dict:
    """
    The memory chart drawn on the node (``web/pd_profiler.js``).

    One column per stage, stacked models / working memory / latents, against
    the VRAM budget; a RAM bar of model weights and decoded pixels.  Each
    stage carries its measured seconds when known (from this run, else from
    *timings*), so the frontend can draw stage widths by time.
    """
    budget = report.get("budget") or {}
    measured = {n["node"]: n["seconds"] for n in (actual or {}).get("nodes", [])
                if not n.get("cached")}
    timings = timings or {}
    stages = []
    for s in report.get("stages", []):
        seconds = measured.get(s["node"])
        if seconds is None and s["node"] in timings:
            seconds = timings[s["node"]].get("seconds")
        latents = s["extra"] if s["kind"] == "sample" else 0
        stages.append({
            "kind": s["kind"], "name": STAGE_NAMES.get(s["kind"], s["kind"]), "node": s["node"],
            "label": s["label"], "models": s["weights"], "working": s["working"],
            "latents": latents, "total": s.get("total", s["weights"] + s["working"] + latents),
            "seconds": seconds, "verdict": s.get("verdict", ""), "offload": s.get("offload", 0),
            "note": s.get("note", ""),
            "unknown": s.get("unknown", ""),
        })
    ram = report.get("ram") or {}
    return {"vram": budget.get("vram") or 0, "ram": budget.get("ram") or 0,
            "emulated": bool(budget.get("emulated")), "stages": stages,
            "ram_use": {"models": ram.get("weights", 0), "pixels": ram.get("frames_out", 0)},
            "measured_peak": measured_peak(actual)}


def profile_metadata(report: dict, actual: dict | None = None, prefix: str = "pipedream/",
                     prompt_id: str | None = None):
    """
    The profile as EXR metadata (``ExrMetadata``), names under
    ``<prefix>profiler/``: budget, peak estimate and stage, each stage,
    the latent, model files (full paths), API nodes, and what a run
    measured (time, VRAM peak).  Sizes in GB, times in seconds.
    """
    from .exr_meta import Attr, ExrMetadata

    base = f"{prefix}profiler/"
    table = {}

    def put(name, value):
        if value is None or value == "":
            return
        if isinstance(value, bool):
            table[base + name] = Attr("int", int(value))
        elif isinstance(value, int):
            table[base + name] = Attr("int", value)
        elif isinstance(value, float):
            table[base + name] = Attr("float", round(value, 4))
        else:
            table[base + name] = Attr("string", str(value))

    gb = lambda n: float(n or 0) / GIB
    budget = report.get("budget") or {}
    put("profiled_at", report.get("evaluated"))
    put("prompt_id", prompt_id)
    put("gpu", (budget.get("machine") or {}).get("gpu"))
    if budget.get("vram"):
        put("vram_budget_gb", gb(budget["vram"]))
    if budget.get("ram"):
        put("ram_budget_gb", gb(budget["ram"]))
    put("emulated", bool(budget.get("emulated")))
    peak = report.get("peak")
    if peak:
        put("peak_vram_estimate_gb", gb(peak["bytes"]))
        put("peak_stage", peak["label"])
    for i, st in enumerate(report.get("stages", []), 1):
        name = STAGE_NAMES.get(st["kind"], st["kind"])
        if st.get("unknown"):
            put(f"stage_{i}", f"{name} {st['label']}: {st['unknown']} unknown")
            continue
        parts = f"models {gb(st['weights']):.2f} GB, working {gb(st['working']):.2f} GB"
        if st.get("extra"):
            parts += f", latents {gb(st['extra']):.3f} GB"
        verdict = f", {st['verdict']}" if st.get("verdict") else ""
        put(f"stage_{i}", f"{name} {st['label']}: {gb(st['total']):.2f} GB ({parts}){verdict}")
    for i, latent in enumerate(report.get("latents", []), 1):
        key = "latent" if i == 1 else f"latent_{i}"
        put(key, "[" + ", ".join(str(d) for d in latent["shape"]) + "]")
        put(f"{key}_size", f"{latent['width']}x{latent['height']}")
        put(f"{key}_frames", int(latent["frames"]))
    for i, m in enumerate(report.get("models", []), 1):
        put(f"model_{i}", f"{m['role']}: {m.get('path') or m['file']}")
    for i, lora in enumerate(report.get("loras", []), 1):
        put(f"lora_{i}", lora.get("path") or lora["file"])
    if report.get("api_nodes"):
        put("api_nodes", ", ".join(f"{a['name'] or a['class']} #{a['node']}" for a in report["api_nodes"]))
    t = report.get("time")
    if t:
        put("time_estimate_s", float(t["total"]))
        put("jobs", int(t["jobs"]))
    if actual:
        ran = [n for n in actual.get("nodes", []) if not n.get("cached")]
        if ran:
            put("time_upstream_s", float(sum(n["seconds"] for n in ran)))
        if actual.get("vram_peak"):
            put("measured_peak_vram_gb", gb(actual["vram_peak"]))
        if actual.get("device_peak"):
            put("measured_device_vram_gb", gb(actual["device_peak"]))
        put("wedge_job", actual.get("job"))
    return ExrMetadata([table])


def profile_path(path: str, now: str) -> str:
    """
    Where the profile sidecar goes.

    Next to a written file as ``<name>.profile.json`` (the frame number of
    an image sequence dropped), inside a given folder, or in
    ``output/pipedream_profiles`` when no path is given.
    """
    path = (path or "").strip().splitlines()[0].strip() if (path or "").strip() else ""
    name = f"profile_{now}.json"
    if not path:
        return os.path.join(output_directory(), PROFILE_DIR, name)
    if path.endswith(("/", "\\")) or os.path.isdir(path):
        return os.path.join(path, name)
    folder, base = os.path.split(path)
    stem, ext = os.path.splitext(base)
    if ext.lstrip(".").lower() in IMAGE_FORMATS:
        sep = re.escape(settings.get("sequence.frame_separator"))
        stem = re.sub(rf"(?:{sep}|\.)\d+$", "", stem)
    return os.path.join(folder, f"{stem}.profile.json")


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

def fmt_bytes(n) -> str:
    n = float(n or 0)
    if n >= GIB:
        return f"{n / GIB:.1f} GB"
    if n >= MIB:
        return f"{n / MIB:.0f} MB"
    return f"{n / 1024:.0f} KB"


def fmt_time(seconds) -> str:
    seconds = max(0.0, float(seconds))
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.1f} s" if seconds < 10 else f"{seconds:.0f} s"
    minutes, sec = divmod(round(seconds), 60)
    if minutes < 60:
        return f"{minutes} m {sec:02d} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} m"


def _params(n) -> str:
    return f"{n / 1e9:.2f} B" if n >= 1e9 else f"{n / 1e6:.0f} M"


STAGE_NAMES = {"encode": "text encode", "vision": "clip vision", "sample": "sample",
               "decode": "VAE decode"}


def format_report(report: dict, actual: dict | None = None) -> str:
    """The report as the text shown on the node."""
    lines = []
    head = "measured run" if actual else "evaluated, nothing run"
    lines.append(f"PD Profiler · {head} · {report.get('evaluated', '')}")
    budget = report.get("budget") or {}
    if budget:
        machine = budget.get("machine") or {}
        gpu = machine.get("gpu") or ("GPU" if machine.get("vram") else "no GPU")
        vram = fmt_bytes(budget["vram"]) if budget.get("vram") else "none (no GPU)"
        line = f"Budget   VRAM {vram} · RAM {fmt_bytes(budget.get('ram'))}"
        if budget.get("emulated"):
            here = fmt_bytes(machine["vram"]) if machine.get("vram") else "no"
            line += f"  (emulated; this machine: {here} VRAM, {fmt_bytes(machine.get('ram'))} RAM)"
        elif budget.get("vram"):
            line += f"  ({gpu})"
        lines.append(line)
    for api in report.get("api_nodes", []):
        lines.append(f"! API node upstream: {api['name'] or api['class']} #{api['node']}. "
                     "Runs off-site and is not counted; its inputs leave this machine.")
    wedge = report.get("wedge")
    if wedge and wedge.get("error"):
        lines.append(f"! Wedge: {wedge['error']}")
    elif wedge:
        axes = " × ".join(f"{'+'.join(a['tokens'])} " + ("1 (solo)" if a["solo"] else str(a["length"]))
                          for a in wedge["axes"])
        rows = ", ".join(f"#{n} row {r}" for n, r in wedge["rows"].items())
        lines.append(f"Wedge    {axes} = {wedge['total']} jobs; profiling one job ({rows})")
        for n in wedge.get("branches", []):
            lines.append(f"  ! #{n}: rows read from different branches; other jobs may differ "
                         "in models or sizes.")
    for w in report.get("warnings", []):
        lines.append(f"! {w}")

    if report.get("models"):
        lines.append("")
        lines.append("Models")
        for m in report["models"]:
            lines.append(f"  {m['role']:<13}{m['file']}  (#{m['node']})")
            detail = []
            if m.get("family"):
                how = "ComfyUI detection" if m.get("detected") == "comfy" else (
                    "guessed from file name" if m.get("detected") == "fallback" else "")
                detail.append(f"{m['family']}" + (f" ({how})" if how else ""))
            if m.get("params"):
                detail.append(f"{_params(m['params'])} params")
            if m.get("dtype"):
                detail.append(str(m["dtype"]) + (" (upcast to 16-bit: this GPU has no fp8 compute)"
                                                 if m.get("fp8_upcast") else ""))
            detail.append(f"{fmt_bytes(m.get('loaded_bytes'))} loaded")
            lines.append(f"  {'':<13}" + " · ".join(detail))
        for lora in report.get("loras", []):
            lines.append(f"  {'lora':<13}{lora['file']}  {fmt_bytes(lora['stored_bytes'])} "
                         "(merged into the model's weights)")

    for latent in report.get("latents", []):
        lines.append("")
        shape = latent["shape"]
        frames = f"{latent['frames']} frames, " if len(shape) == 5 else ""
        lines.append(f"Latent   #{latent['node']}  {latent['width']}×{latent['height']}, {frames}"
                     f"batch {latent['batch']}")
        lines.append(f"         [{', '.join(str(d) for d in shape)}] · "
                     f"{math.prod(shape):,} values · {fmt_bytes(math.prod(shape) * 4)}")

    if report.get("stages"):
        lines.append("")
        lines.append("Stages   VRAM; ComfyUI frees what the next model needs, so the peak is the largest")
        for i, s in enumerate(report["stages"], 1):
            name = STAGE_NAMES.get(s["kind"], s["kind"])
            if s.get("unknown"):
                lines.append(f"  {i} {name:<12}{s['label']}: {s['unknown']} unknown"
                             + (f", weights {fmt_bytes(s['weights'])}" if s["weights"] else ""))
                continue
            parts = f"{fmt_bytes(s['weights'])} weights"
            if s["working"]:
                parts += f" + {fmt_bytes(s['working'])} " + (
                    "decode" if s["kind"] == "decode" else "sampling")
            extra = []
            if s["kind"] == "sample":
                if s.get("steps"):
                    extra.append(f"{s['steps']} steps")
                if s.get("tokens"):
                    extra.append(f"{s['tokens']:,} tokens")
            verdict = s.get("verdict", "")
            if s.get("offload") and verdict == "streams":
                verdict = f"streams {fmt_bytes(s['offload'])} of the weights from RAM (slower)"
            elif s.get("offload"):
                verdict = f"offloads {fmt_bytes(s['offload'])} of the weights to RAM (slower)"
            elif verdict == "does not fit":
                verdict = ("over budget: even with every weight offloaded, ComfyUI's minimum "
                           "estimate is over the card; likely out of memory")
            lines.append(f"  {i} {name:<12}{s['label']}  {parts} = {fmt_bytes(s['total'])}"
                         + (f"  {verdict}" if verdict else ""))
            if s.get("note"):
                extra.append(s["note"])
            if extra:
                lines.append(f"    {'':<12}" + " · ".join(extra))
        peak = report.get("peak")
        if peak:
            of = f", {fmt_bytes(budget['vram'])} available" if budget.get("vram") else ""
            lines.append(f"Peak     {fmt_bytes(peak['bytes'])} VRAM needed at {peak['label']}{of}")
        ram = report.get("ram") or {}
        if ram.get("total"):
            of = f" of {fmt_bytes(budget['ram'])}" if budget.get("ram") else ""
            warn = "  ! more than the machine has" if budget.get("ram") and ram["total"] > budget["ram"] else ""
            lines.append(f"RAM      ~{fmt_bytes(ram['total'])}{of}: models {fmt_bytes(ram['weights'])}, "
                         f"frames out {fmt_bytes(ram['frames_out'])} (float32 IMAGE){warn}")
    else:
        lines.append("")
        lines.append("No sampler, VAE decode or text encoder upstream.")

    t = report.get("time")
    lines.append("")
    if t:
        note = "scaled to current steps and size, rough" if t["scaled"] else "as measured"
        lines.append(f"Time     from the run at {t['measured']} ({note})")
        if t["jobs"] > 1:
            lines.append(f"  once per queue  {fmt_time(t['once'])}  (models, encoders, nodes before the wedge)")
            lines.append(f"  per job         {fmt_time(t['per_job'])}")
            lines.append(f"  {t['jobs']} jobs: {fmt_time(t['once'])} + {t['jobs']} × "
                         f"{fmt_time(t['per_job'])} ≈ {fmt_time(t['total'])}")
        else:
            lines.append(f"  total ≈ {fmt_time(t['total'])}")
        if t["slowest"]:
            lines.append("  slowest: " + ", ".join(f"{r['label']} {fmt_time(r['seconds'])}"
                                                   for r in t["slowest"]))
        if t["unmeasured"]:
            lines.append(f"  {t['unmeasured']} node(s) not measured yet (cached or new): not counted")
    else:
        lines.append("Time     run once to measure; later estimates scale from that run.")

    if actual:
        lines += _format_actual(actual)
    if report.get("notes"):
        lines.append("")
        lines += [f"note: {n}" for n in report["notes"]]
    return "\n".join(lines)


def _format_actual(actual: dict) -> list:
    lines = ["", "Measured this run"]
    nodes = actual.get("nodes", [])
    ran = [n for n in nodes if not n.get("cached")]
    cached = len(nodes) - len(ran)
    total = sum(n["seconds"] for n in ran)
    lines.append(f"  upstream time {fmt_time(total)}: {len(ran)} node(s) ran, {cached} cached")
    for n in sorted(ran, key=lambda n: -n["seconds"])[:6]:
        peak = f"  peak {fmt_bytes(n['vram_peak'])}" if n.get("vram_peak") is not None else ""
        lines.append(f"    {n['label']:<34} {fmt_time(n['seconds'])}{peak}")
    if actual.get("vram_peak") is not None:
        reserved = f", reserved {fmt_bytes(actual['vram_reserved'])}" if actual.get("vram_reserved") else ""
        lines.append(f"  peak VRAM {fmt_bytes(actual['vram_peak'])} allocated{reserved} "
                     f"(this machine: {fmt_bytes(actual.get('vram_total'))})")
    if actual.get("device_peak"):
        lines.append(f"  device memory in use, highest at a node end: {fmt_bytes(actual['device_peak'])} "
                     "(includes memory outside PyTorch)")
    if actual.get("dynamic_peak") is not None:
        lines.append(f"  Dynamic VRAM held, highest at a node end: {fmt_bytes(actual['dynamic_peak'])} "
                     "(weights paged in outside PyTorch's count)")
    if actual.get("job"):
        lines.append(f"  wedge job {actual['job']}")
    for m in actual.get("loaded_models", []):
        where = f", {fmt_bytes(m['on_gpu'])} on the GPU" if actual.get("vram_total") else ""
        lines.append(f"  loaded now: {m['name']} {fmt_bytes(m['size'])}{where}")
    source = actual.get("source")
    if source:
        lines.append(f"  input: {source}")
    if actual.get("sidecar"):
        lines.append(f"  profile written: {actual['sidecar']}")
    return lines
