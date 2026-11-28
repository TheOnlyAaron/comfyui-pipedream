"""
Tests for the GPU validation harness in tools/gpu_validation: the graph
builders (checked against the profiler's own stage finder), template
patching, the run plan and the tables.  Standard library only::

    python -m unittest discover -s tests
"""

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "gpu_validation"))

from core import profiler as pf  # noqa: E402
import graphs  # noqa: E402
import run_validation as rv  # noqa: E402
import tabulate as tb  # noqa: E402

GIB = 1024 ** 3
N = pf.NodeInfo
NODES = {
    "CheckpointLoaderSimple": N(returns=("MODEL", "CLIP", "VAE")),
    "UNETLoader": N(returns=("MODEL",)),
    "CLIPLoader": N(returns=("CLIP",)),
    "DualCLIPLoader": N(returns=("CLIP",)),
    "VAELoader": N(returns=("VAE",)),
    "CLIPTextEncode": N(returns=("CONDITIONING",)),
    "FluxGuidance": N(returns=("CONDITIONING",)),
    "ModelSamplingSD3": N(returns=("MODEL",)),
    "EmptyLatentImage": N(returns=("LATENT",)),
    "EmptySD3LatentImage": N(returns=("LATENT",)),
    "EmptyHunyuanLatentVideo": N(returns=("LATENT",)),
    "Wan22ImageToVideoLatent": N(returns=("LATENT",)),
    "HunyuanVideo15ImageToVideo": N(returns=("CONDITIONING", "CONDITIONING", "LATENT")),
    "KSampler": N(returns=("LATENT",)),
    "KSamplerAdvanced": N(returns=("LATENT",)),
    "VAEDecode": N(returns=("IMAGE",)),
    "VAEDecodeTiled": N(returns=("IMAGE",)),
    "PDProfiler": N(returns=("EXR_METADATA",)),
}
MODELS = {role: f"{role}.safetensors" for role in (
    "sdxl_ckpt", "flux1_unet", "clip_l", "t5xxl", "flux1_vae", "umt5", "wan21_vae", "wan22_vae",
    "wan13_t2v", "wan14_t2v", "wan22_5b", "wan22_a14b_high", "wan22_a14b_low", "hunyuan_unet",
    "llava_llama3", "hunyuan_vae", "hunyuan15_unet", "qwen25vl", "byt5", "hunyuan15_vae")}
ENV = pf.ComfyEnv(node_info=NODES.get, resolve=lambda folders, name: None)


def stages(prompt):
    report = pf.build_profile(prompt, graphs.PROFILER_ID, ENV, {"vram": 48 * GIB})
    return [s["kind"] for s in report["stages"]], report


class BuilderTests(unittest.TestCase):
    def test_every_builder_gives_encode_sample_decode(self):
        samplers = {"wan22_a14b": 2}
        for name in graphs.BUILDERS:
            with self.subTest(builder=name):
                prompt, source = graphs.case_graph({"name": name, "builder": name}, MODELS)
                kinds, report = stages(graphs.attach_profiler(prompt, source))
                self.assertEqual(kinds.count("sample"), samplers.get(name, 1))
                self.assertEqual(kinds.count("decode"), 1)
                self.assertIn("encode", kinds)
                self.assertTrue(report["latents"], "latent size found")

    def test_sizes_reach_the_latent(self):
        prompt, source = graphs.case_graph(
            {"name": "w", "builder": "wan21_t2v", "unet_role": "wan13_t2v",
             "width": 1280, "height": 720, "length": 81}, MODELS)
        _, report = stages(graphs.attach_profiler(prompt, source))
        latent = report["latents"][0]
        self.assertEqual((latent["width"], latent["height"]), (1280, 720))
        self.assertEqual(latent["shape"][-2:], [90, 160])

    def test_a14b_splits_steps(self):
        prompt, _ = graphs.case_graph({"name": "a", "builder": "wan22_a14b", "steps": 6}, MODELS)
        self.assertEqual(prompt["sample_high"]["inputs"]["end_at_step"], 3)
        self.assertEqual(prompt["sample_low"]["inputs"]["start_at_step"], 3)
        self.assertEqual(prompt["sample_low"]["inputs"]["latent_image"], ["sample_high", 0])

    def test_tiled_and_missing_model(self):
        prompt, _ = graphs.case_graph({"name": "s", "builder": "sdxl", "tiled": True}, MODELS)
        self.assertEqual(prompt["decode"]["class_type"], "VAEDecodeTiled")
        with self.assertRaisesRegex(graphs.GraphError, "flux1_vae"):
            graphs.case_graph({"name": "f", "builder": "flux1"}, {"flux1_unet": "x"})
        with self.assertRaises(graphs.GraphError):
            graphs.case_graph({"name": "x", "builder": "nope"}, MODELS)

    def test_attach_profiler(self):
        out = graphs.attach_profiler({"1": {"class_type": "VAEDecode", "inputs": {}}}, "1", 12,
                                     "/tmp/side")
        inputs = out[graphs.PROFILER_ID]["inputs"]
        self.assertEqual(inputs["source"], ["1", 0])
        self.assertTrue(inputs["vram_per_node"] and inputs["export_sidecar"])
        self.assertEqual(inputs["path"], "/tmp/side/")
        self.assertEqual(inputs["vram_gb"], 12.0)


class TemplateTests(unittest.TestCase):
    def write(self, data):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh)
        self.addCleanup(os.remove, path)
        return path

    def test_patches_sizes_seeds_steps(self):
        path = self.write({
            "1": {"class_type": "EmptyLTXVLatentVideo",
                  "inputs": {"width": 768, "height": 512, "length": 97, "batch_size": 1}},
            "2": {"class_type": "KSampler", "inputs": {"seed": 99, "steps": 30, "latent_image": ["1", 0]}},
            "3": {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["2", 0]}},
            "4": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0]}},
            "5": {"class_type": "LTXVAudioVAEDecode", "inputs": {"samples": ["3", 1]}},
            "6": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["9", 0]}},
            "7": {"class_type": "PDProfiler", "inputs": {"source": ["4", 0]}},
            "8": {"class_type": "PrimitiveInt", "inputs": {"width": ["1", 0]}},
        })
        prompt, source = graphs.case_graph({"name": "t", "template": path, "width": 1280,
                                            "height": 704, "length": 121, "steps": 8}, {})
        self.assertEqual(prompt["1"]["inputs"]["width"], 1280)
        self.assertEqual(prompt["1"]["inputs"]["length"], 121)
        self.assertEqual(prompt["2"]["inputs"]["seed"], 1)
        self.assertEqual(prompt["2"]["inputs"]["steps"], 8)
        self.assertEqual(prompt["8"]["inputs"]["width"], ["1", 0], "links are left alone")
        self.assertNotIn("7", prompt)
        self.assertEqual(source, "4", "deepest video decode, not the audio one")

    def test_ui_workflow_rejected(self):
        path = self.write({"nodes": [], "links": []})
        with self.assertRaisesRegex(graphs.GraphError, "Export \\(API\\)"):
            graphs.case_graph({"name": "t", "template": path}, {})


class PlanTests(unittest.TestCase):
    def test_sessions(self):
        cfg = {"cases": [{"name": "a"}, {"name": "b"}], "emulate_gb": [8, 24],
               "emulate_cases": ["b"], "emulate_modes": ["estimate"]}
        plan = rv.sessions(cfg, 48.0)
        self.assertEqual([p[0] for p in plan], ["dynamic", "estimate", "estimate_emu8gb",
                                                "estimate_emu24gb"])
        name, args, env, cases, evaluate, gb = plan[2]
        margin = rv.default_os_margin_gb(48.0)
        self.assertEqual(args, ["--disable-dynamic-vram", "--reserve-vram", str(round(40 + margin, 2))])
        self.assertEqual(env, {"PD_VRAM_CAP_GB": "8"})
        self.assertEqual([c["name"] for c in cases], ["b"])
        self.assertFalse(evaluate)
        self.assertEqual(plan[1][1], ["--disable-dynamic-vram"])
        self.assertTrue(plan[0][4])

    def test_windows_and_outcome(self):
        events = {"starts": [("1", 10.0), ("2", 11.0), ("1", 13.0)], "t_end": 15.0}
        self.assertEqual(rv.node_windows(events), {"1": (10.0, 15.0), "2": (11.0, 13.0)})
        self.assertEqual(rv.outcome({}), "ok")
        self.assertEqual(rv.outcome({"error": {"type": "OutOfMemoryError", "message": ""}}), "oom")
        self.assertEqual(rv.outcome({"error": {"type": "RuntimeError",
                                               "message": "CUDA out of memory. Tried"}}), "oom")
        self.assertEqual(rv.outcome({"error": {"type": "ValueError", "message": "x"}}), "ValueError")


def stage(kind, node, weights, working, verdict="fits"):
    return {"kind": kind, "node": node, "label": f"#{node} X", "weights": weights * GIB,
            "working": working * GIB, "extra": 0, "total": (weights + working) * GIB,
            "verdict": verdict}


class TableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = self.tmp.name
        prompt = {"clip": {"class_type": "CLIPLoader", "inputs": {}},
                  "pos": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0]}},
                  "sample": {"class_type": "KSampler", "inputs": {"positive": ["pos", 0]}},
                  "decode": {"class_type": "VAEDecode", "inputs": {"samples": ["sample", 0]}}}
        full = {"stages": [stage("encode", "clip", 10, 0), stage("sample", "sample", 2.6, 3.5),
                           stage("decode", "decode", 0.2, 5.0)],
                "peak": {"bytes": 10 * GIB}}
        small = {"stages": [stage("encode", "clip", 10, 0, "offloads"),
                            stage("sample", "sample", 2.6, 3.5, "offloads"),
                            stage("decode", "decode", 0.2, 5.0, "does not fit")]}
        os.makedirs(os.path.join(d, "sidecars"))
        with open(os.path.join(d, "sidecars", "full.json"), "w") as fh:
            json.dump({"measured": {"vram_peak": 9 * GIB, "nodes": [
                {"node": "pos", "vram_peak": 9.5 * GIB},
                {"node": "sample", "vram_peak": 2.6 * GIB + 1.75 * GIB},
                {"node": "decode", "vram_peak": 4 * GIB}]}}, fh)
        runs = [
            {"run_id": "estimate__wan-a", "session": "estimate", "mode": "estimate", "emulate_gb": None,
             "case": {"name": "wan-a"}, "prompt": prompt, "outcome": "ok", "seconds": 100.0,
             "evaluations": {"0.0": full, "8.0": small}, "sidecar": "sidecars/full.json",
             "smi_idle_mib": 500, "smi_peak_mib": 11000, "smi_node_peak_mib": {"sample": 5000}},
            {"run_id": "estimate_emu8gb__wan-a", "session": "estimate_emu8gb", "mode": "estimate",
             "emulate_gb": 8, "case": {"name": "wan-a"}, "prompt": prompt, "outcome": "oom",
             "seconds": 50.0, "evaluations": {},
             "log": ["loaded partially; 7000.00 MB usable, 1000.00 MB loaded, 1600.00 MB offloaded, "
                     "0.00 MB buffer reserved, lowvram patches: 0"]},
        ]
        with open(os.path.join(d, "results.jsonl"), "w") as fh:
            for r in runs:
                fh.write(json.dumps(r) + "\n")

    def test_tables(self):
        text = tb.tabulate(self.tmp.name)
        self.assertIn("| wan-a | estimate | encode #clip X | 10.00 | 0.00 | 10.00 | fits | 9.50 |", text)
        self.assertIn("| wan-a | estimate | sample #sample X | 2.60 | 3.50 | 6.10 | fits | 4.35 | 4.39 | 0.71 |", text)
        self.assertIn("| wan-a | 8 GB | estimate | offloads, offloads, does not fit | oom | 1 (1600) | no | – | yes |",
                      text)
        self.assertIn("| wan | sample | estimate | 1 | 0.50 | 0.50–0.50 |", text)
        self.assertIn("| wan | decode | estimate | 1 | 0.76 |", text)

    def test_agreement(self):
        obs = {"oom": False, "partial": 0, "tiled": False}
        self.assertEqual(tb.agreement(["fits", "fits"], obs, "estimate", "ok"), "yes")
        self.assertEqual(tb.agreement(["fits", "offloads"], obs, "estimate", "ok"), "no")
        self.assertEqual(tb.agreement(["fits", "streams"], obs, "dynamic", "ok"), "?")
        self.assertEqual(tb.agreement(["fits", "falls back to tiled decode"], dict(obs, tiled=True),
                                      "dynamic", "ok"), "yes")
        self.assertEqual(tb.agreement(["fits"], dict(obs, oom=True), "estimate", "oom"), "no")


if __name__ == "__main__":
    unittest.main()
