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
        # ComfyUI: area (batch 2) * 2 bytes * 0.01 * memory_usage_factor MiB; Wan 14B's
        # factor is dim / 2222 = 2.30 (the file-name fallback uses ComfyUI's value).
        area = 2 * 21 * 90 * 160
        batched = area * 2 * 0.01 * 2.30 * 1024 ** 2
        self.assertAlmostEqual(sample["working_batched"], batched)
        self.assertAlmostEqual(sample["working_single"], batched / 2)
        # Weights + the batch-2 estimate don't fit 24 GB, so cond and uncond run one at a
        # time; the weights get 24 GB - max(reserve, batch-1 estimate + OS margin) - latent.
        self.assertAlmostEqual(sample["working"], batched / 2)
        self.assertIn("one at a time", sample["note"])
        room = 24 * GIB - (batched / 2 + pf.DEFAULT_OS_MARGIN) - sample["extra"]
        self.assertEqual(sample["verdict"], "offloads")
        self.assertAlmostEqual(sample["offload"], sample["weights"] - room)
        decode = report["stages"][2]
        self.assertEqual(decode["working"], 7000 * 90 * 160 * 64 * 2)
        self.assertEqual(report["peak"]["node"], max(report["stages"], key=lambda s: s["total"])["node"])
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


class VerdictTests(ProfilerCase):
    def verdict(self, vram_gb, **flow):
        report = self.profile(wan_flow(**flow), budget={"vram": vram_gb * GIB, "ram": 64 * GIB})
        return report["stages"][1]

    def test_fits_batched_on_big_card(self):
        sample = self.verdict(80, width=832, height=480)
        self.assertEqual(sample["verdict"], "fits")
        self.assertEqual(sample["working"], sample["working_batched"])
        self.assertNotIn("note", sample)

    def test_cfg_one_uses_single_estimate(self):
        prompt = wan_flow(width=832, height=480)
        prompt["7"]["inputs"]["cfg"] = 1.0
        sample = self.profile(prompt, budget={"vram": 80 * GIB})["stages"][1]
        self.assertEqual(sample["working"], sample["working_single"])
        self.assertIn("cfg 1", sample["note"])

    def test_does_not_fit_when_minimum_is_over_card(self):
        sample = self.verdict(8, width=1920, height=1088, length=121)
        self.assertGreater(sample["working_single"] + pf.DEFAULT_OS_MARGIN, 8 * GIB)
        self.assertEqual(sample["verdict"], "does not fit")

    def test_dynamic_vram_streams(self):
        self.env.dynamic_vram = True
        sample = self.verdict(24)
        self.assertEqual(sample["verdict"], "streams")
        report = self.profile(wan_flow(), budget={"vram": 24 * GIB, "ram": 64 * GIB})
        self.assertIn("Dynamic VRAM", " ".join(report["notes"]))
        self.assertIn("streams", pf.format_report(report))

    def test_decode_offloads_weights_before_tiling(self):
        report = self.profile(wan_flow(), budget={"vram": 12.6 * GIB, "ram": 64 * GIB})
        decode = report["stages"][2]
        # decode memory (12.02 GiB) fits next to the OS margin; the 0.24 GB of weights page out.
        self.assertEqual(decode["verdict"], "offloads")
        report = self.profile(wan_flow(), budget={"vram": 8 * GIB, "ram": 64 * GIB})
        self.assertEqual(report["stages"][2]["verdict"], "falls back to tiled decode")


class FamilyTests(ProfilerCase):
    def test_minimax_vae_and_frames(self):
        vae = {"decoder.transformer_blocks.0.scale1": ("BF16", (1024,)),
               "encoder.conv_in.weight": ("BF16", (128, 3, 3, 3, 3)),
               "decoder.big": ("BF16", (1000, 100000))}
        self.files["h3_vae.safetensors"] = write_safetensors(os.path.join(self.tmp.name, "h3vae.safetensors"), vae)
        self.files["minimax_h3_fp8.safetensors"] = write_safetensors(
            os.path.join(self.tmp.name, "h3.safetensors"), {"blocks.0.w": ("F8_E4M3", (5120, 1_000_000))})
        tensors = {k: mf.Tensor(t, sh, 0) for k, (t, sh) in vae.items()}
        self.assertEqual(mf.vae_family(tensors), ("MiniMax H3", 24))
        prompt = wan_flow(unet="minimax_h3_fp8.safetensors", width=1344, height=768, length=120)
        prompt["3"]["inputs"]["vae_name"] = "h3_vae.safetensors"
        report = self.profile(prompt)
        latent = report["latents"][0]
        # 120 frames snap up to 124 (17k+5); latents are 5k+2: (124 - 5) // 17 * 5 + 2 = 37.
        self.assertEqual(latent["shape"], [1, 24, 37, 48, 84])
        self.assertEqual(latent["frames"], 124)
        self.assertIn("becomes 124 frames", " ".join(report["warnings"]))
        decode = report["stages"][-1]
        # Decode memory is capped at one streamed chunk (30 frames) at fp16.
        self.assertAlmostEqual(decode["working"], (9.5 * 30 * 768 * 1344 + 270_000_000) * 2 * 1.03)

    def test_checkpoint_without_vae_is_not_a_vae(self):
        self.files["flux_unet_only.safetensors"] = write_safetensors(
            os.path.join(self.tmp.name, "flux.safetensors"), {"double_blocks.0.w": ("BF16", (3072, 1_000_000))})
        self.env.node_info = dict(NODES, CheckpointLoaderSimple=pf.NodeInfo(
            returns=("MODEL", "CLIP", "VAE"), name="Load Checkpoint")).get
        models = pf.Models(pf.Graph({"1": {"class_type": "CheckpointLoaderSimple",
                                           "inputs": {"ckpt_name": "flux_unet_only.safetensors"}}}, self.env),
                           self.env, [])
        self.assertIsNone(models.vae("1"))
        self.assertEqual(models.encoders("1"), [])
        self.assertEqual(models.diffusion("1")["params"], 3072 * 1_000_000)

    def test_ltx2_audio_parts_counted(self):
        self.files["ltx2.safetensors"] = write_safetensors(os.path.join(self.tmp.name, "ltx2.safetensors"), {
            "model.diffusion_model.blocks.0.w": ("BF16", (4096, 100_000)),
            "vae.decoder.up_blocks.0.res_blocks.0.conv1.conv.weight": ("BF16", (512, 512, 3, 3, 3)),
            "audio_vae.decoder.w": ("BF16", (1000, 100_000)),
            "vocoder.w": ("BF16", (1000, 50_000)),
            "text_embedding_projection.w": ("BF16", (4096, 3840)),
        })
        self.env.node_info = dict(NODES, CheckpointLoaderSimple=pf.NodeInfo(
            returns=("MODEL", "CLIP", "VAE"), name="Load Checkpoint")).get
        models = pf.Models(pf.Graph({"1": {"class_type": "CheckpointLoaderSimple",
                                           "inputs": {"ckpt_name": "ltx2.safetensors"}}}, self.env), self.env, [])
        self.assertEqual(models.audio("1")["params"], 1000 * 100_000 + 1000 * 50_000)
        self.assertEqual(models.vae("1")["family"], "LTX-Video")
        self.assertEqual(models.encoders("1")[0]["params"], 4096 * 3840)


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


class ChartTests(ProfilerCase):
    def test_chart_stacks_and_seconds(self):
        timings = {"7": {"seconds": 90.0, "class": "KSampler"}}
        report = self.profile(wan_flow(), budget={"vram": 24 * GIB, "ram": 64 * GIB}, timings=timings)
        chart = pf.build_chart(report, timings, {"nodes": [{"node": "8", "seconds": 4.0}],
                                                 "vram_peak": 20 * GIB})
        self.assertEqual([s["kind"] for s in chart["stages"]], ["encode", "sample", "decode"])
        sample = chart["stages"][1]
        self.assertEqual(sample["latents"], 1 * 16 * 21 * 90 * 160 * 4)
        self.assertEqual(sample["total"], sample["models"] + sample["working"] + sample["latents"])
        self.assertEqual((sample["seconds"], chart["stages"][2]["seconds"]), (90.0, 4.0))
        self.assertIsNone(chart["stages"][0]["seconds"])
        self.assertEqual(chart["vram"], 24 * GIB)
        self.assertEqual(chart["ram_use"]["pixels"], 1280 * 720 * 3 * 4 * 81)
        self.assertEqual(chart["measured_peak"], 20 * GIB)
        json.dumps(chart)


class MetadataTests(ProfilerCase):
    def test_profile_metadata(self):
        report = self.profile(wan_flow(), budget={"vram": 24 * GIB, "ram": 64 * GIB,
                                                  "machine": {"gpu": "RTX 4060"}})
        meta = pf.profile_metadata(report, {"nodes": [{"node": "7", "seconds": 40.0}],
                                            "vram_peak": 2 * GIB}, "pipedream/", "abc")
        table = meta.frame(0)
        get = lambda k: table[f"pipedream/profiler/{k}"].value
        self.assertEqual(get("gpu"), "RTX 4060")
        self.assertEqual(get("vram_budget_gb"), 24.0)
        self.assertEqual(get("prompt_id"), "abc")
        self.assertEqual(get("latent"), "[1, 16, 21, 90, 160]")
        self.assertEqual(get("latent_frames"), 81)
        self.assertEqual(table["pipedream/profiler/latent_frames"].type, "int")
        self.assertTrue(get("model_1").startswith("diffusion: "))
        self.assertTrue(get("model_1").endswith("wan14.safetensors"))
        self.assertIn("sample #7", get("stage_2"))
        self.assertEqual(get("time_upstream_s"), 40.0)
        self.assertEqual(get("measured_peak_vram_gb"), 2.0)


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


class RobustnessTests(ProfilerCase):
    def test_capture_only_with_enabled_profiler(self):
        from core import capture

        class Prompt:
            def __init__(self, nodes):
                self.original_prompt = nodes
        self.assertEqual(capture._profilers(Prompt({"1": {"class_type": "KSampler", "inputs": {}}})), [])
        off = {"1": {"class_type": "PDProfiler", "inputs": {"enabled": False}}}
        self.assertEqual(capture._profilers(Prompt(off)), [])
        on = {"1": {"class_type": "PDProfiler", "inputs": {"vram_per_node": True}}}
        self.assertEqual(capture._profilers(Prompt(on)), [{"vram_per_node": True}])

    def test_malformed_safetensors_header(self):
        path = os.path.join(self.tmp.name, "bad.safetensors")
        body = json.dumps({"a": "not a tensor"}).encode()
        with open(path, "wb") as fh:
            fh.write(struct.pack("<Q", len(body)) + body)
        with self.assertRaises(mf.HeaderError):
            mf.read_header(path)

    def test_wan22_latent_batch_needs_start_image(self):
        NODES["Wan22ImageToVideoLatent"] = pf.NodeInfo(
            inputs={"vae": "VAE", "start_image": "IMAGE"}, returns=("LATENT",), name="Wan22 Latent")
        NODES["LoadImage"] = pf.NodeInfo(returns=("IMAGE", "MASK"), name="Load Image")
        self.addCleanup(NODES.pop, "Wan22ImageToVideoLatent")
        self.addCleanup(NODES.pop, "LoadImage")
        prompt = wan_flow()
        prompt["6"] = {"class_type": "Wan22ImageToVideoLatent", "inputs": {
            "vae": ["3", 0], "width": 1280, "height": 704, "length": 121, "batch_size": 3}}
        self.assertEqual(self.profile(prompt)["latents"][0]["shape"][0], 1)
        prompt["5"] = {"class_type": "LoadImage", "inputs": {"image": "a.png"}}
        prompt["6"]["inputs"]["start_image"] = ["5", 0]
        self.assertEqual(self.profile(prompt)["latents"][0]["shape"][0], 3)
