"""
Tests for core/model_files.py and core/profiler.py (PD Profiler).

Standard library only; model files are written as header-only sparse
files.  ComfyUI's model detection is not available here, so diffusion
models use the file-name fallback; the ComfyUI path is exercised in a
running ComfyUI.  Run from the pack root::

    python -m unittest discover -s tests
"""

import json
import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import model_files as mf  # noqa: E402
from core import profiler as pf  # noqa: E402

GIB = 1024 ** 3


def write_safetensors(path, tensors):
    """*tensors*: name -> (dtype, shape).  The data is a sparse hole."""
    header, offset = {}, 0
    for name, (dtype, shape) in tensors.items():
        size = int(mf.SAFETENSORS_BYTES[dtype] * (eval("*".join(map(str, shape))) if shape else 1))
        header[name] = {"dtype": dtype, "shape": list(shape), "data_offsets": [offset, offset + size]}
        offset += size
    raw = json.dumps(header).encode()
    with open(path, "wb") as fh:
        fh.write(struct.pack("<Q", len(raw)) + raw)
        fh.truncate(8 + len(raw) + offset)
    return path


def write_gguf(path, tensors, kv=()):
    """*tensors*: name -> (ggml type, torch-order shape)."""
    def s(text):
        b = text.encode()
        return struct.pack("<Q", len(b)) + b
    body_kv = b""
    for key, shape in kv:
        body_kv += s(key) + struct.pack("<IIQ", 9, 5, len(shape)) + b"".join(struct.pack("<i", d) for d in shape)
    infos = b""
    for name, (kind, shape) in tensors.items():
        dims = list(reversed(shape))
        infos += s(name) + struct.pack("<I", len(dims)) + b"".join(struct.pack("<Q", d) for d in dims)
        infos += struct.pack("<IQ", kind, 0)
    with open(path, "wb") as fh:
        fh.write(b"GGUF" + struct.pack("<IQQ", 3, len(tensors), len(kv)) + body_kv + infos)
    return path


WAN21_VAE = {
    "decoder.middle.0.residual.0.gamma": ("BF16", (384,)),
    "decoder.head.0.gamma": ("BF16", (96,)),
    "decoder.head.2.weight": ("BF16", (3, 96, 3, 3, 3)),
    "encoder.conv1.weight": ("BF16", (96, 3, 3, 3, 3)),
    "decoder.conv.weight": ("BF16", (1000, 120000)),
}
WAN22_VAE = dict(WAN21_VAE, **{"decoder.upsamples.0.upsamples.0.residual.2.weight": ("BF16", (8, 8))})

NODES = {
    "UNETLoader": pf.NodeInfo(returns=("MODEL",), name="Load Diffusion Model"),
    "LoraLoaderModelOnly": pf.NodeInfo(returns=("MODEL",), name="LoraLoaderModelOnly"),
    "CLIPLoader": pf.NodeInfo(returns=("CLIP",), name="Load CLIP"),
    "VAELoader": pf.NodeInfo(returns=("VAE",), name="Load VAE"),
    "CLIPTextEncode": pf.NodeInfo(returns=("CONDITIONING",), name="CLIP Text Encode"),
    "EmptyHunyuanLatentVideo": pf.NodeInfo(returns=("LATENT",), name="Empty Video Latent"),
    "KSampler": pf.NodeInfo(returns=("LATENT",), name="KSampler"),
    "VAEDecode": pf.NodeInfo(returns=("IMAGE",), name="VAE Decode"),
    "VAEDecodeTiled": pf.NodeInfo(returns=("IMAGE",), name="VAE Decode (Tiled)"),
    "PDWedge": pf.NodeInfo(returns=("*", "STRING", "INT", "FLOAT", "WEDGE"), name="PD Wedge"),
    "PDProfiler": pf.NodeInfo(returns=(), name="PD Profiler"),
    "FakeApiImage": pf.NodeInfo(returns=("IMAGE",), api=True, name="Fake API Image"),
    "ImageScale": pf.NodeInfo(returns=("IMAGE",), name="Upscale Image"),
}


def wan_flow(prefix="", unet="wan2.1_t2v_14B_bf16.safetensors", width=1280, height=720,
             length=81, steps=20):
    p = prefix
    return {
        f"{p}1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": "default"}},
        f"{p}2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5.safetensors", "type": "wan"}},
        f"{p}3": {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}},
        f"{p}4": {"class_type": "CLIPTextEncode", "inputs": {"text": "x", "clip": [f"{p}2", 0]}},
        f"{p}6": {"class_type": "EmptyHunyuanLatentVideo",
                  "inputs": {"width": width, "height": height, "length": length, "batch_size": 1}},
        f"{p}7": {"class_type": "KSampler", "inputs": {
            "model": [f"{p}1", 0], "positive": [f"{p}4", 0], "negative": [f"{p}4", 0],
            "latent_image": [f"{p}6", 0], "seed": 1, "steps": steps, "cfg": 5.0}},
        f"{p}8": {"class_type": "VAEDecode", "inputs": {"samples": [f"{p}7", 0], "vae": [f"{p}3", 0]}},
        f"{p}9": {"class_type": "PDProfiler", "inputs": {"source": [f"{p}8", 0]}},
    }


class ProfilerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = self.tmp.name
        self.files = {
            "wan2.1_t2v_14B_bf16.safetensors": write_safetensors(
                os.path.join(d, "wan14.safetensors"),
                {"blocks.0.w": ("BF16", (5120, 2_000_000)), "norm": ("F32", (5120,))}),
            "wan2.1_t2v_1.3B_bf16.safetensors": write_safetensors(
                os.path.join(d, "wan13.safetensors"), {"blocks.0.w": ("BF16", (1536, 800_000))}),
            "umt5.safetensors": write_safetensors(
                os.path.join(d, "umt5.safetensors"), {"enc.w": ("F8_E4M3", (4096, 1_000_000))}),
            "wan_2.1_vae.safetensors": write_safetensors(os.path.join(d, "vae.safetensors"), WAN21_VAE),
        }
        self.env = pf.ComfyEnv(node_info=NODES.get,
                               resolve=lambda folders, name: self.files.get(name))

    def profile(self, prompt, node="9", budget=None, timings=None):
        return pf.build_profile(prompt, node, self.env, budget, timings)


class HeaderTests(ProfilerCase):
    def test_safetensors(self):
        header = mf.read_header(self.files["umt5.safetensors"])
        self.assertEqual(header.format, "safetensors")
        self.assertEqual(header.tensors["enc.w"].shape, (4096, 1_000_000))
        self.assertEqual(header.tensors["enc.w"].nbytes, 4096 * 1_000_000)
        self.assertEqual(mf.dominant_dtype(header.tensors), "F8_E4M3")

    def test_gguf_shapes_reversed_and_orig_shape(self):
        path = write_gguf(os.path.join(self.tmp.name, "m.gguf"),
                          {"blocks.0.w": (8, (5120, 5120)), "patch.weight": (0, (5120, 64))},
                          kv=[("comfy.gguf.orig_shape.patch.weight", (5120, 16, 1, 2, 2))])
        header = mf.read_header(path)
        self.assertEqual(header.format, "gguf")
        self.assertEqual(header.tensors["blocks.0.w"].dtype, "Q8_0")
        self.assertEqual(header.tensors["blocks.0.w"].nbytes, 5120 * 5120 / 32 * 34)
        self.assertEqual(header.tensors["patch.weight"].shape, (5120, 16, 1, 2, 2))

    def test_loaded_bytes(self):
        tensors = {"w": mf.Tensor("F32", (100, 10), 4000), "b": mf.Tensor("F32", (10,), 40)}
        self.assertEqual(mf.loaded_bytes(tensors, 2), 2020)
        self.assertEqual(mf.loaded_bytes(tensors, 2, "fp8_e4m3fn"), 1000 + 20)

    def test_vae_families(self):
        tensors = lambda d: {k: mf.Tensor(t, s, 0) for k, (t, s) in d.items()}
        self.assertEqual(mf.vae_family(tensors(WAN21_VAE)), ("Wan 2.1", 16))
        self.assertEqual(mf.vae_family(tensors(WAN22_VAE)), ("Wan 2.2", 48))
        self.assertEqual(mf.vae_family(tensors({"decoder.up_blocks.0.res_blocks.0.conv1.conv.weight":
                                                ("BF16", (1, 1))}))[0], "LTX-Video")
        self.assertEqual(mf.vae_family(tensors({"decoder.conv_in.weight": ("F32", (512, 16, 3, 3))})),
                         ("KL", 16))
        self.assertEqual(mf.vae_family(tensors({"decoder.conv_in.weight": ("F32", (512, 32, 3, 3)),
                                                "bn.running_mean": ("F32", (128,))})), ("Flux 2", 128))
        self.assertEqual(mf.vae_family(tensors({"decoder.conv_in.conv.weight": ("F32", (512, 16, 3, 3, 3))})),
                         ("HunyuanVideo", 16))


class CrawlTests(ProfilerCase):
    def test_only_this_flow(self):
        prompt = {**wan_flow("a"), **wan_flow("b", unet="wan2.1_t2v_1.3B_bf16.safetensors")}
        report = self.profile(prompt, "a9")
        files = [m["file"] for m in report["models"]]
        self.assertIn("wan2.1_t2v_14B_bf16.safetensors", files)
        self.assertNotIn("wan2.1_t2v_1.3B_bf16.safetensors", files)
        self.assertEqual([s["kind"] for s in report["stages"]], ["encode", "sample", "decode"])

    def test_latent_shape_and_floor_warnings(self):
        report = self.profile(wan_flow(width=1280, height=1078, length=80))
        latent = report["latents"][0]
        self.assertEqual(latent["shape"], [1, 16, 20, 134, 160])
        self.assertEqual((latent["width"], latent["height"], latent["frames"]), (1280, 1072, 77))
        text = " ".join(report["warnings"])
        self.assertIn("height 1078 decodes to 1072", text)
        self.assertIn("length 80 gives 77 frames", text)

    def test_stage_memory_and_peak(self):
        report = self.profile(wan_flow(), budget={"vram": 24 * GIB, "ram": 64 * GIB})
        sample = report["stages"][1]
        self.assertEqual(sample["weights"], 5120 * 2_000_000 * 2 + 5120 * 2)
        # ComfyUI: area (batch 2) * 2 bytes * 0.01 * memory_usage_factor MiB.
        area = 2 * 21 * 90 * 160
        self.assertAlmostEqual(sample["working"], area * 2 * 0.01 * 0.9 * 1024 ** 2)
        decode = report["stages"][2]
        self.assertEqual(decode["working"], 7000 * 90 * 160 * 64 * 2)
        self.assertEqual(report["peak"]["node"], max(report["stages"], key=lambda s: s["total"])["node"])
        self.assertIn(sample["verdict"], ("fits", "offloads", "does not fit"))
        self.assertEqual(report["ram"]["frames_out"], 1280 * 720 * 3 * 4 * 81)

    def test_tiled_decode_is_per_tile(self):
        prompt = wan_flow()
        prompt["8"] = {"class_type": "VAEDecodeTiled", "inputs": {
            "samples": ["7", 0], "vae": ["3", 0], "tile_size": 512, "temporal_size": 32}}
        decode = self.profile(prompt)["stages"][2]
        self.assertTrue(decode["tiled"])
        self.assertEqual(decode["working"], 7000 * 64 * 64 * 64 * 2)

    def test_api_node_flagged_not_counted(self):
        prompt = wan_flow()
        prompt["30"] = {"class_type": "FakeApiImage", "inputs": {"prompt": "x"}}
        prompt["31"] = {"class_type": "ImageScale", "inputs": {"image": ["30", 0], "width": 64, "height": 64}}
        prompt["9"]["inputs"]["source"] = ["31", 0]
        report = self.profile(prompt)
        self.assertEqual([a["node"] for a in report["api_nodes"]], ["30"])
        self.assertEqual(report["stages"], [])

    def test_wedge_follows_selected_row_only(self):
        prompt = wan_flow()
        prompt["20"] = {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.1_t2v_1.3B_bf16.safetensors"}}
        prompt["21"] = {"class_type": "PDWedge", "inputs": {
            "token": "model", "solo": 0, "input_1": ["1", 0], "value_1": "big",
            "input_2": ["20", 0], "value_2": "small"}}
        prompt["7"]["inputs"]["model"] = ["21", 0]
        report = self.profile(prompt)
        self.assertEqual([m["file"] for m in report["models"] if m["role"] == "diffusion"],
                         ["wan2.1_t2v_14B_bf16.safetensors"])
        self.assertEqual(report["wedge"]["total"], 2)
        self.assertEqual(report["wedge"]["branches"], ["21"])
        prompt["21"]["inputs"]["solo"] = 2
        report = self.profile(prompt)
        self.assertEqual([m["file"] for m in report["models"] if m["role"] == "diffusion"],
                         ["wan2.1_t2v_1.3B_bf16.safetensors"])
        self.assertEqual(report["wedge"]["total"], 1)

    def test_wedge_int_feeds_widget(self):
        prompt = wan_flow()
        prompt["21"] = {"class_type": "PDWedge", "inputs": {
            "token": "w", "solo": 2, "value_1": "832", "value_2": "1024"}}
        prompt["6"]["inputs"]["width"] = ["21", 2]
        latent = self.profile(prompt)["latents"][0]
        self.assertEqual(latent["width"], 1024)


class CheckpointTests(ProfilerCase):
    def test_checkpoint_parts(self):
        self.files["sdxl.safetensors"] = write_safetensors(os.path.join(self.tmp.name, "ckpt.safetensors"), {
            "model.diffusion_model.input_blocks.0.0.weight": ("F16", (320, 4, 3, 3)),
            "model.diffusion_model.big": ("F16", (2560, 1_000_000)),
            "first_stage_model.decoder.conv_in.weight": ("F32", (512, 4, 3, 3)),
            "first_stage_model.decoder.big": ("F32", (1000, 20_000)),
            "conditioner.embedders.0.big": ("F16", (768, 500_000)),
        })
        self.env.node_info = dict(NODES, CheckpointLoaderSimple=pf.NodeInfo(
            returns=("MODEL", "CLIP", "VAE"), name="Load Checkpoint"),
            EmptyLatentImage=pf.NodeInfo(returns=("LATENT",))).get
        prompt = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sdxl.safetensors"}},
            "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "x", "clip": ["1", 1]}},
            "6": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 2}},
            "7": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["4", 0],
                                                       "negative": ["4", 0], "latent_image": ["6", 0]}},
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["1", 2]}},
            "9": {"class_type": "PDProfiler", "inputs": {"source": ["8", 0]}},
        }
        report = self.profile(prompt)
        roles = {m["role"]: m for m in report["models"]}
        self.assertEqual(roles["vae"]["family"], "KL")
        self.assertEqual(roles["diffusion"]["params"], 320 * 4 * 9 + 2560 * 1_000_000)
        self.assertEqual(roles["text encoder"]["params"], 768 * 500_000)
        self.assertEqual(report["latents"][0]["shape"], [2, 4, 128, 128])
        decode = report["stages"][-1]
        self.assertEqual(decode["working"], 2178 * 128 * 128 * 64 * 2)


class TimeTests(ProfilerCase):
    def test_scales_steps(self):
        timings = {"7": {"seconds": 100.0, "steps": 10, "class": "KSampler", "at": "t"},
                   "1": {"seconds": 20.0, "class": "UNETLoader", "at": "t"}}
        t = self.profile(wan_flow(steps=20), timings=timings)["time"]
        self.assertAlmostEqual(t["total"], 220.0)
        self.assertTrue(t["scaled"])

    def test_wedge_jobs(self):
        prompt = wan_flow()
        prompt["21"] = {"class_type": "PDWedge", "inputs": {
            "token": "seed", "value_1": "1", "value_2": "2", "value_3": "3"}}
        prompt["7"]["inputs"]["seed"] = ["21", 2]
        timings = {"7": {"seconds": 60.0, "class": "KSampler"}, "8": {"seconds": 5.0, "class": "VAEDecode"},
                   "1": {"seconds": 20.0, "class": "UNETLoader"}, "4": {"seconds": 2.0, "class": "CLIPTextEncode"}}
        t = self.profile(prompt, timings=timings)["time"]
        self.assertEqual(t["jobs"], 3)
        self.assertAlmostEqual(t["per_job"], 65.0)
        self.assertAlmostEqual(t["once"], 22.0)
        self.assertAlmostEqual(t["total"], 22.0 + 3 * 65.0)


class OutputTests(ProfilerCase):
    def test_profile_path(self):
        self.assertEqual(pf.profile_path("/o/shot_v001.1001.exr", "T"),
                         os.path.join("/o", "shot_v001.profile.json"))
        self.assertEqual(pf.profile_path("/o/shot_010.mp4", "T"),
                         os.path.join("/o", "shot_010.profile.json"))
        self.assertEqual(pf.profile_path(self.tmp.name, "T"),
                         os.path.join(self.tmp.name, "profile_T.json"))
        self.assertTrue(pf.profile_path("", "T").endswith(os.path.join(pf.PROFILE_DIR, "profile_T.json")))

    def test_format_report(self):
        prompt = wan_flow()
        prompt["30"] = {"class_type": "FakeApiImage", "inputs": {}}
        prompt["6"]["inputs"]["width"] = 1270
        report = self.profile(prompt, budget={"vram": 16 * GIB, "ram": 32 * GIB, "emulated": True,
                                              "machine": {"vram": 24 * GIB, "ram": 64 * GIB}})
        text = pf.format_report(report)
        for part in ("Budget   VRAM 16.0 GB", "emulated", "Models", "Latent", "Stages",
                     "Peak", "width 1270 decodes to 1264", "run once to measure"):
            self.assertIn(part, text)
        self.assertEqual(pf.fmt_time(0.25), "250 ms")
        self.assertEqual(pf.fmt_time(125), "2 m 05 s")


if __name__ == "__main__":
    unittest.main()
