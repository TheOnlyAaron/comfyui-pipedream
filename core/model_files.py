"""
Model files as PD Profiler sees them: tensor shapes and data types read
from the file header, without loading any weights.

``read_header(path)`` reads a ``.safetensors`` file (an 8-byte length and
a JSON table of every tensor) or a ``.gguf`` file (the GGUF tensor table;
dims are reversed to torch order, and ComfyUI-GGUF's
``comfy.gguf.orig_shape.*`` keys are honoured).  Results are cached by
path, size and modification time.  ``.ckpt``/``.pt`` pickles are not
read: only their size on disk is reported.

``diffusion_info``, ``vae_info`` and ``encoder_info`` turn a header into
what the profiler needs:

* the diffusion model is identified with ComfyUI's own detection
  (``comfy.model_detection.model_config_from_unet``) on shape-only
  stand-ins, which gives its latent format, ``memory_usage_factor`` and
  inference data types.  When ComfyUI is not importable, or detection
  needs real weight values, a small fallback table matched on the file
  name is used and the result says so (``detected = "fallback"``).
* the VAE family, latent channels, compression and ComfyUI's decode
  memory formula (``memory_used_decode`` in ``comfy/sd.py``) come from the
  same key checks ComfyUI makes.
* text encoders and CLIP vision only need their weight size.

Sizes are what ComfyUI keeps in memory: GGUF and fp8 weights stay as
stored; fp32 weights are cast to the inference type (2 bytes); a loader's
``weight_dtype`` fp8 choice stores the large weights in 1 byte.
"""

import json
import math
import os
import re
import struct

SAFETENSORS_BYTES = {
    "F64": 8, "I64": 8, "U64": 8, "F32": 4, "I32": 4, "U32": 4, "F16": 2, "BF16": 2,
    "I16": 2, "U16": 2, "F8_E4M3": 1, "F8_E5M2": 1, "F8_E8M0": 1, "I8": 1, "U8": 1,
    "BOOL": 1, "F4": 0.5, "F6_E2M3": 0.75, "F6_E3M2": 0.75,
}

# ggml type id: (name, elements per block, bytes per block)
GGML_TYPES = {
    0: ("F32", 1, 4), 1: ("F16", 1, 2), 2: ("Q4_0", 32, 18), 3: ("Q4_1", 32, 20),
    6: ("Q5_0", 32, 22), 7: ("Q5_1", 32, 24), 8: ("Q8_0", 32, 34), 9: ("Q8_1", 32, 36),
    10: ("Q2_K", 256, 84), 11: ("Q3_K", 256, 110), 12: ("Q4_K", 256, 144),
    13: ("Q5_K", 256, 176), 14: ("Q6_K", 256, 210), 15: ("Q8_K", 256, 292),
    16: ("IQ2_XXS", 256, 66), 17: ("IQ2_XS", 256, 74), 18: ("IQ3_XXS", 256, 98),
    19: ("IQ1_S", 256, 50), 20: ("IQ4_NL", 32, 18), 21: ("IQ3_S", 256, 110),
    22: ("IQ2_S", 256, 82), 23: ("IQ4_XS", 256, 136), 24: ("I8", 1, 1), 25: ("I16", 1, 2),
    26: ("I32", 1, 4), 27: ("I64", 1, 8), 28: ("F64", 1, 8), 29: ("IQ1_M", 256, 56),
    30: ("BF16", 1, 2),
}

FULL_PRECISION = ("F32", "F64")
CHECKPOINT_PREFIXES = {
    "diffusion": ("model.diffusion_model.",),
    "vae": ("first_stage_model.", "vae."),
    "text_encoder": ("cond_stage_model.", "conditioner.", "text_encoders.",
                     "text_embedding_projection."),
    "audio": ("audio_vae.", "vocoder."),
}


class HeaderError(Exception):
    """A model file whose header cannot be read."""


class Tensor:
    """One tensor of a header: dtype name, torch-order shape and stored bytes."""

    __slots__ = ("dtype", "shape", "nbytes")

    def __init__(self, dtype: str, shape, nbytes: float):
        self.dtype = dtype
        self.shape = tuple(int(d) for d in shape)
        self.nbytes = nbytes

    @property
    def numel(self) -> int:
        return math.prod(self.shape)


class ModelFile:
    """A model file's header: format, size on disk, tensors and metadata."""

    def __init__(self, path: str, fmt: str, size: int, tensors: dict, metadata: dict):
        self.path = path
        self.name = os.path.basename(path)
        self.format = fmt
        self.size = size
        self.tensors = tensors
        self.metadata = metadata

    def subset(self, prefixes, strip=False) -> dict:
        """The tensors whose names start with one of *prefixes* (removed with *strip*)."""
        out = {}
        for k, t in self.tensors.items():
            for prefix in prefixes:
                if k.startswith(prefix):
                    out[k[len(prefix):] if strip else k] = t
                    break
        return out


_cache: dict = {}


def read_header(path: str) -> ModelFile:
    """Read *path*'s tensor table (cached).  Raises HeaderError."""
    try:
        stat = os.stat(path)
    except OSError as exc:
        raise HeaderError(f"cannot read '{path}': {exc.strerror or exc}") from exc
    key = (os.path.normcase(os.path.abspath(path)), stat.st_size, stat.st_mtime_ns)
    if key in _cache:
        return _cache[key]
    ext = os.path.splitext(path)[1].lower()
    try:
        with open(path, "rb") as fh:
            if ext == ".gguf":
                tensors, metadata = _read_gguf(fh)
                fmt = "gguf"
            elif ext in (".safetensors", ".sft"):
                tensors, metadata = _read_safetensors(fh)
                fmt = "safetensors"
            else:
                tensors, metadata, fmt = {}, {}, ext.lstrip(".") or "unknown"
    except (OSError, ValueError, struct.error, UnicodeDecodeError) as exc:
        raise HeaderError(f"cannot read the header of '{path}': {exc}") from exc
    result = ModelFile(path, fmt, stat.st_size, tensors, metadata)
    _cache[key] = result
    return result


def _read_safetensors(fh):
    (length,) = struct.unpack("<Q", fh.read(8))
    if length <= 0 or length > 256 * 1024 * 1024:
        raise ValueError(f"implausible header length {length}")
    header = json.loads(fh.read(length))
    metadata = header.pop("__metadata__", None) or {}
    tensors = {}
    for name, entry in header.items():
        dtype = entry.get("dtype", "F32")
        start, end = entry.get("data_offsets", (0, 0))
        tensors[name] = Tensor(dtype, entry.get("shape", ()), end - start)
    return tensors, metadata


def _gguf_reader(fh, version):
    count_fmt = "<I" if version == 1 else "<Q"
    count_size = 4 if version == 1 else 8

    def count():
        return struct.unpack(count_fmt, fh.read(count_size))[0]

    def string():
        return fh.read(count()).decode("utf-8", errors="replace")

    scalars = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?",
               10: "<Q", 11: "<q", 12: "<d"}

    def value(kind):
        if kind == 8:
            return string()
        if kind == 9:
            item_kind = struct.unpack("<I", fh.read(4))[0]
            n = count()
            if item_kind in scalars and item_kind not in (8, 9):
                fmt = scalars[item_kind]
                size = struct.calcsize(fmt)
                raw = fh.read(size * n)
                return list(struct.unpack("<" + fmt[1:] * n, raw)) if n <= 64 else n
            return [value(item_kind) for _ in range(n)]
        fmt = scalars.get(kind)
        if fmt is None:
            raise ValueError(f"unknown GGUF value type {kind}")
        return struct.unpack(fmt, fh.read(struct.calcsize(fmt)))[0]

    return count, string, value


def _read_gguf(fh):
    if fh.read(4) != b"GGUF":
        raise ValueError("not a GGUF file")
    (version,) = struct.unpack("<I", fh.read(4))
    count, string, value = _gguf_reader(fh, version)
    n_tensors, n_kv = count(), count()
    metadata = {}
    for _ in range(n_kv):
        key = string()
        kind = struct.unpack("<I", fh.read(4))[0]
        val = value(kind)
        if key.startswith(("general.", "comfy.")) or not isinstance(val, list):
            metadata[key] = val
    tensors = {}
    for _ in range(n_tensors):
        name = string()
        (n_dims,) = struct.unpack("<I", fh.read(4))
        dims = [count() for _ in range(n_dims)]
        (kind,) = struct.unpack("<I", fh.read(4))
        fh.read(8)
        type_name, block, block_bytes = GGML_TYPES.get(kind, (f"type{kind}", 1, 2))
        numel = math.prod(dims)
        shape = tuple(reversed(dims))
        orig = metadata.get(f"comfy.gguf.orig_shape.{name}")
        if isinstance(orig, list) and orig:
            shape = tuple(int(d) for d in orig)
        tensors[name] = Tensor(type_name, shape, numel / block * block_bytes)
    return tensors, metadata


# ---------------------------------------------------------------------------
# Sizes
# ---------------------------------------------------------------------------

def dominant_dtype(tensors: dict) -> str:
    """The data type holding most of the bytes, e.g. ``"BF16"`` or ``"Q4_K"``."""
    totals = {}
    for t in tensors.values():
        totals[t.dtype] = totals.get(t.dtype, 0) + t.nbytes
    return max(totals, key=totals.get) if totals else ""


FLOATS = ("F64", "F32", "F16", "BF16", "F8_E4M3", "F8_E5M2")


def loaded_bytes(tensors: dict, inference_bytes: int = 2, weight_dtype: str = "default",
                 fp8_bytes: int = 1, cast_all: bool = False) -> float:
    """
    Bytes the *tensors* take once ComfyUI has loaded them.

    fp32 tensors are cast to the inference type; a loader ``weight_dtype``
    of fp8 stores every weight with two or more dims in 1 byte; fp8 tensors
    take *fp8_bytes* (2 when ComfyUI upcasts a plain fp8 file on a GPU
    without fp8 compute); quantized tensors stay as stored.  *cast_all*
    casts every float tensor to *inference_bytes* (a VAE is cast as a whole).
    """
    fp8 = str(weight_dtype).startswith("fp8")
    total = 0.0
    for t in tensors.values():
        if cast_all and t.dtype in FLOATS:
            total += t.numel * inference_bytes
        elif fp8 and len(t.shape) >= 2 and t.dtype in ("F32", "F16", "BF16"):
            total += t.numel
        elif t.dtype in ("F8_E4M3", "F8_E5M2"):
            total += t.numel * fp8_bytes
        elif t.dtype in FULL_PRECISION:
            total += t.numel * inference_bytes
        else:
            total += t.nbytes
    return total


def param_count(tensors: dict) -> int:
    return sum(t.numel for t in tensors.values())


# ---------------------------------------------------------------------------
# Diffusion model detection
# ---------------------------------------------------------------------------

class _Stub:
    """Shape-only stand-in for a tensor, for ComfyUI's model detection."""

    def __init__(self, tensor: Tensor, torch_mod):
        self.shape = torch_mod.Size(tensor.shape) if torch_mod else tensor.shape
        self.ndim = len(tensor.shape)
        self.dtype = _torch_dtype(tensor.dtype, torch_mod)

    def size(self, dim=None):
        return self.shape if dim is None else self.shape[dim]

    def dim(self):
        return self.ndim


def _torch_dtype(name, torch_mod):
    if torch_mod is None:
        return name
    table = {"F32": "float32", "F16": "float16", "BF16": "bfloat16", "F64": "float64",
             "F8_E4M3": "float8_e4m3fn", "F8_E5M2": "float8_e5m2", "I64": "int64",
             "I32": "int32", "I16": "int16", "I8": "int8", "U8": "uint8", "BOOL": "bool"}
    return getattr(torch_mod, table.get(name, "uint8"), None)


# Used when ComfyUI's detection is unavailable.  latent: channels,
# spatial and temporal compression; memory_usage_factor as ComfyUI sets it.
FALLBACK_MODELS = [
    # pattern, family, latent channels, latent dims, memory_usage_factor (as ComfyUI sets it)
    (r"minimax.*h3|h3.*minimax", "MiniMax H3", 24, 3, 0.114),
    (r"hunyuan.?video.?1\.?5|hunyuanvideo1\.?5|hunyuan.*1\.5", "HunyuanVideo 1.5", 32, 3, 4.0),
    (r"wan2\.?2.*(ti2v|5b)", "Wan 2.2 5B", 48, 3, 1.38),
    (r"wan2\.?[12].*1\.3b", "Wan 2.1 1.3B", 16, 3, 0.69),
    (r"wan2\.?[12]", "Wan 2.x 14B", 16, 3, 2.30),
    (r"ltx", "LTX-Video / LTX-2", 128, 3, 5.5),
    (r"hunyuan.*video|hunyuanvideo", "HunyuanVideo", 16, 3, 1.8),
    (r"qwen.*image", "Qwen-Image", 16, 3, 1.8),
    (r"chroma", "Chroma", 16, 2, 3.2),
    (r"flux", "Flux.1", 16, 2, 3.1),
    (r"sd3", "SD3", 16, 2, 1.6),
    (r"sdxl|xl", "SDXL", 4, 2, 0.8),
    (r"", "SD 1.5 (assumed)", 4, 2, 1.0),
]


class DiffusionInfo(dict):
    """
    What the profiler knows about a diffusion model.

    Keys: ``family``, ``detected`` ("comfy" or "fallback"), ``params``,
    ``stored_bytes``, ``dtype``, ``latent_channels``, ``latent_dims``,
    ``memory_usage_factor``, ``inference_bytes``, ``loaded_bytes``.
    """


def diffusion_info(mf: ModelFile, tensors: dict | None = None, weight_dtype: str = "default",
                   comfy_env=None, name: str = "") -> DiffusionInfo:
    """
    Identify the diffusion model in *tensors* (default: the whole file).
    *name* is the file as picked in the loader (with subfolders), used by
    the fallback; default the file's own name.
    """
    tensors = mf.tensors if tensors is None else tensors
    info = DiffusionInfo(params=param_count(tensors),
                         stored_bytes=sum(t.nbytes for t in tensors.values()) or mf.size,
                         dtype=dominant_dtype(tensors) or mf.format)
    config = _comfy_config(tensors, mf.metadata, comfy_env) if tensors else None
    if config is not None:
        latent = config.latent_format
        info.update(
            family=type(config).__name__,
            detected="comfy",
            latent_channels=int(getattr(latent, "latent_channels", 4)),
            latent_dims=int(getattr(latent, "latent_dimensions", 2)),
            memory_usage_factor=float(getattr(config, "memory_usage_factor", 2.0)),
        )
        if type(config).__name__.startswith("MiniMaxH3"):
            # ComfyUI's MiniMaxH3AV format reports max(video 24, audio 32); the video latent is 24.
            info["latent_channels"] = 24
        patch = (getattr(config, "unet_config", None) or {}).get("patch_size")
        if isinstance(patch, (int, list, tuple)):
            info["patch_size"] = list(patch) if isinstance(patch, (list, tuple)) else patch
        inference = _inference_bytes(config, info, comfy_env)
    else:
        name = (name or mf.name).lower()
        for pattern, family, channels, dims, factor in FALLBACK_MODELS:
            if re.search(pattern, name):
                break
        info.update(family=family, detected="fallback", latent_channels=channels,
                    latent_dims=dims, memory_usage_factor=factor)
        inference = 2
    info["inference_bytes"] = inference
    fp8_bytes = _fp8_bytes(config, info, tensors, weight_dtype, comfy_env)
    if fp8_bytes > 1:
        info["fp8_upcast"] = True
    if mf.format == "gguf":
        info["loaded_bytes"] = info["stored_bytes"]
    else:
        info["loaded_bytes"] = (loaded_bytes(tensors, inference, weight_dtype, fp8_bytes)
                                if tensors else mf.size)
    return info


def _comfy_config(tensors: dict, metadata: dict, comfy_env):
    if comfy_env is None or comfy_env.model_detection is None:
        return None
    detection = comfy_env.model_detection
    stubs = {k: _Stub(t, comfy_env.torch) for k, t in tensors.items()}
    try:
        prefix = detection.unet_prefix_from_state_dict(stubs)
        stripped = {k[len(prefix):]: v for k, v in stubs.items() if prefix and k.startswith(prefix)}
        if stripped:
            stubs = stripped
        config = detection.model_config_from_unet(stubs, "", metadata=metadata or None)
    except Exception:
        config = None
    if config is None:
        # Diffusers-layout files, as comfy.sd.load_diffusion_model_state_dict tries them.
        for attempt in ("model_config_from_diffusers_unet", "convert_diffusers_mmdit"):
            try:
                if attempt == "model_config_from_diffusers_unet":
                    config = detection.model_config_from_diffusers_unet(stubs)
                else:
                    converted = detection.convert_diffusers_mmdit(stubs, "")
                    config = detection.model_config_from_unet(converted, "") if converted else None
            except Exception:
                config = None
            if config is not None:
                break
    return config


def _fp8_bytes(config, info, tensors, weight_dtype, comfy_env) -> int:
    """
    Bytes per weight of a plain (unscaled) fp8 file once loaded: ComfyUI's
    ``unet_dtype`` upcasts it to 16-bit on a GPU without fp8 compute when
    it fits (load_diffusion_model_state_dict).  Scaled fp8 stays 1 byte.
    """
    mm = comfy_env.model_management if comfy_env else None
    torch_mod = comfy_env.torch if comfy_env else None
    if (config is None or mm is None or torch_mod is None or not getattr(comfy_env, "gpu", True)
            or not str(info.get("dtype", "")).startswith("F8") or str(weight_dtype).startswith("fp8")):
        return 1
    if any(k.endswith(("scale_weight", "weight_scale", "scaled_fp8", ".comfy_quant")) for k in tensors):
        return 1
    stored = torch_mod.float8_e5m2 if info["dtype"] == "F8_E5M2" else torch_mod.float8_e4m3fn
    try:
        dtype = mm.unet_dtype(model_params=info["params"],
                              supported_dtypes=list(config.supported_inference_dtypes) + [stored],
                              weight_dtype=stored)
        return int(mm.dtype_size(dtype))
    except Exception:
        return 1


def _inference_bytes(config, info, comfy_env) -> int:
    mm = comfy_env.model_management if comfy_env else None
    if mm is None or not getattr(comfy_env, "gpu", True):
        return 2
    try:
        dtype = mm.unet_dtype(model_params=info["params"],
                              supported_dtypes=list(config.supported_inference_dtypes))
        return int(mm.dtype_size(dtype))
    except Exception:
        return 2


# ---------------------------------------------------------------------------
# VAE families (the key checks and formulas of comfy/sd.py VAE.__init__)
# ---------------------------------------------------------------------------

def _kl(shape, b):
    return 2178 * shape[2] * shape[3] * 64 * b


def _minimax_decode(shape, b):
    """
    ComfyUI's MiniMax H3 ``estimate_decode_memory``: the decoder streams
    17-frame clips, so at most one chunk (28 frames, +2) is resident.
    Frames follow its 5k+2 latents <-> 17k+5 frames mapping.
    """
    frames = max(1, (shape[2] - 2) // 5 * 17 + 5)
    height, width = shape[3] * 16, shape[4] * 16
    fixed = 110_000_000 if frames <= 22 else 270_000_000
    frames = min(frames, 30)
    return (9.5 * frames * height * width + fixed) * b * 1.03


VAE_FAMILIES = {
    # name: (channels, spatial, temporal, decode(shape, dtype bytes), working dtypes)
    "Wan 2.1": (16, 8, 4, lambda s, b: (2200 if s[2] <= 4 else 7000) * s[3] * s[4] * 64 * b,
                ("bf16", "fp16", "fp32")),
    "Wan 2.2": (48, 16, 4, lambda s, b: 8000 * s[3] * s[4] * 256 * b, ("bf16", "fp16", "fp32")),
    "Qwen-Image 2.1": (64, 16, 1, lambda s, b: 900 * s[2] * s[3] * 256 * b,
                       ("bf16", "fp16", "fp32")),
    "LTX-Video": (128, 32, 8, lambda s, b: 1200 * s[2] * s[3] * s[4] * 512 * b, ("bf16", "fp32")),
    "LTX 2.4": (128, 32, 8, lambda s, b: 1700 * s[2] * s[3] * s[4] * 512 * b, ("bf16", "fp32")),
    "HunyuanVideo 1.5": (32, 16, 4, lambda s, b: 3600 * 4 * s[-2] * s[-1] * 256 * b,
                         ("fp16", "bf16", "fp32")),
    "CogVideoX": (16, 8, 4, lambda s, b: 2800 * max(2, (s[2] - 1) * 4 + 1) * s[3] * s[4] * 64 * b,
                  ("bf16", "fp16", "fp32")),
    "HunyuanVideo": (16, 8, 4, lambda s, b: 2800 * min(8, (s[2] - 1) * 4 + 1) * s[3] * s[4] * 64 * b,
                     ("bf16", "fp16", "fp32")),
    "Hunyuan Image 2.1": (64, 32, 1, lambda s, b: 700 * s[2] * s[3] * 1024 * b,
                          ("fp16", "bf16", "fp32")),
    "Hunyuan refiner": (32, 16, 4, lambda s, b: 2800 * s[-3] * s[-2] * s[-1] * 256 * b,
                        ("fp16", "bf16", "fp32")),
    "MiniMax H3": (24, 16, 4, lambda s, b: _minimax_decode(s, b), ("fp16", "fp32")),
    "KL": (4, 8, 1, _kl, ("bf16", "fp32")),
    "Flux 2": (128, 16, 1, _kl, ("fp16", "bf16", "fp32")),
}


def vae_family(tensors: dict) -> tuple[str, int]:
    """``(family, latent channels)`` from a VAE's keys, or ``("", 0)`` when not recognised."""
    keys = tensors.keys()

    def shape(name):
        t = tensors.get(name)
        return t.shape if t else ()

    if ("decoder.transformer_blocks.0.scale1" in keys or "decoder.blocks.0.scale1" in keys
            or "encoder.down.5.block.0.nin_shortcut.weight" in keys
            or ("blocks.0.scale1" in keys and "x_embedder.weight" in keys)):
        return "MiniMax H3", 24

    if "decoder.middle.0.residual.0.gamma" in keys:
        if "decoder.upsamples.0.upsamples.0.residual.2.weight" in keys:
            head = shape("decoder.head.2.weight")
            if len(head) == 5 and head[2] == 1:
                return "Qwen-Image 2.1", 64
            return "Wan 2.2", 48
        return "Wan 2.1", 16
    if "decoder.conv_in_x_t.weight" in keys:
        conv = shape("decoder.conv_in.weight")
        return "LTX 2.4", conv[1] if len(conv) > 1 else 128
    if "decoder.up_blocks.0.res_blocks.0.conv1.conv.weight" in keys:
        return "LTX-Video", 128
    conv3d = shape("decoder.conv_in.conv.weight")
    if conv3d:
        if conv3d[1] == 32:
            return "HunyuanVideo 1.5", 32
        if "decoder.mid_block.resnets.0.norm1.norm_layer.weight" in keys:
            out = shape("encoder.conv_out.conv.weight")
            return "CogVideoX", (out[0] // 2) if out else 16
        return "HunyuanVideo", conv3d[1]
    conv = shape("decoder.conv_in.weight")
    if conv:
        if conv[1] == 64:
            return "Hunyuan Image 2.1", 64
        if conv[1] == 32 and len(conv) == 5:
            return "Hunyuan refiner", 32
        if "bn.running_mean" in keys:
            return "Flux 2", conv[1] * 4
        return "KL", conv[1]
    return "", 0


class VaeInfo(dict):
    """
    Keys: ``family`` ("" when unknown), ``latent_channels``, ``spatial``,
    ``temporal``, ``dtype_bytes``, ``stored_bytes``, ``loaded_bytes``.
    Call ``decode_bytes(latent_shape)`` for ComfyUI's decode memory.
    """

    def decode_bytes(self, latent_shape) -> float | None:
        entry = VAE_FAMILIES.get(self.get("family", ""))
        if entry is None or not latent_shape:
            return None
        shape = list(latent_shape)
        if len(shape) == 4 and self["temporal"] > 1:
            shape.insert(2, 1)
        try:
            value = entry[3](shape, self["dtype_bytes"])
        except (IndexError, TypeError):
            return None
        if self.get("family") == "KL" and self.get("amd"):
            value *= 2.73
        value *= self.get("decode_factor", 1.0)
        return float(value)


def vae_info(mf: ModelFile, tensors: dict | None = None, comfy_env=None) -> VaeInfo:
    tensors = mf.tensors if tensors is None else tensors
    family, channels = vae_family(tensors)
    entry = VAE_FAMILIES.get(family)
    dtype_bytes = _vae_dtype_bytes(entry[4] if entry else ("bf16", "fp32"), comfy_env)
    info = VaeInfo(family=family, latent_channels=channels or (entry[0] if entry else 0),
                   spatial=entry[1] if entry else 8, temporal=entry[2] if entry else 1,
                   dtype_bytes=dtype_bytes,
                   stored_bytes=sum(t.nbytes for t in tensors.values()) or mf.size)
    if family == "Flux 2":
        info["spatial"] = 16
    info["loaded_bytes"] = loaded_bytes(tensors, dtype_bytes, cast_all=True) if tensors else mf.size
    if family == "Flux 2":
        info["decode_factor"] = _flux2_factor(dtype_bytes, comfy_env)
    mm = comfy_env.model_management if comfy_env else None
    try:
        info["amd"] = bool(mm and mm.is_amd())
    except Exception:
        info["amd"] = False
    return info


def _flux2_factor(dtype_bytes, comfy_env) -> float:
    """ComfyUI multiplies Flux 2's decode estimate by 4 unless comfy-kitchen's fused norm serves it."""
    torch_mod = comfy_env.torch if comfy_env else None
    mm = comfy_env.model_management if comfy_env else None
    try:
        from comfy.ldm.modules.diffusionmodules.model import fused_norm_served  # type: ignore
        dtype = {2: torch_mod.bfloat16, 4: torch_mod.float32}.get(dtype_bytes, torch_mod.bfloat16)
        return 1.0 if fused_norm_served(mm.vae_device(), dtype) else 4.0
    except Exception:
        return 4.0


def _vae_dtype_bytes(working, comfy_env) -> int:
    mm = comfy_env.model_management if comfy_env else None
    torch_mod = comfy_env.torch if comfy_env else None
    if mm is None or torch_mod is None or not getattr(comfy_env, "gpu", True):
        return 2
    names = {"bf16": "bfloat16", "fp16": "float16", "fp32": "float32"}
    try:
        dtype = mm.vae_dtype(mm.vae_device(), [getattr(torch_mod, names[w]) for w in working])
        return int(mm.dtype_size(dtype))
    except Exception:
        return 2


def encoder_info(mf: ModelFile, tensors: dict | None = None, comfy_env=None) -> dict:
    """Text encoder or CLIP vision: stored and loaded weight bytes."""
    tensors = mf.tensors if tensors is None else tensors
    inference = 2
    mm = comfy_env.model_management if comfy_env else None
    if mm is not None and getattr(comfy_env, "gpu", True):
        try:
            inference = int(mm.dtype_size(mm.text_encoder_dtype()))
        except Exception:
            pass
    stored = sum(t.nbytes for t in tensors.values()) or mf.size
    loaded = stored if mf.format == "gguf" or not tensors else loaded_bytes(tensors, inference)
    return {"params": param_count(tensors), "dtype": dominant_dtype(tensors) or mf.format,
            "stored_bytes": stored, "loaded_bytes": loaded}
