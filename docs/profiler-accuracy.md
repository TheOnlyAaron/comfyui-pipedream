# PD Profiler accuracy

How far to trust each number [PD Profiler](../web/docs/PDProfiler.md) shows, and how each was checked. For how the profiler works, see the [profiler reference](profiler.md).

Checked in November 2026 against ComfyUI [`62879ac`](https://github.com/comfyanonymous/ComfyUI/tree/62879ac7f585be68f9423af242cbedbf95858b70) (24 November 2026) in four ways:

1. **ComfyUI's source.** Every formula and decision the profiler copies was traced to the code ComfyUI runs. Links below go to that commit.
2. **Real model files.** 73 files published on Hugging Face were read header-only and run through the profiler's model reader with ComfyUI's own detection. The per-file table is in the [appendix](profiler-accuracy-models.md).
3. **Published requirements.** The profiler was run on the real files at the settings model authors published VRAM figures for.
4. **Measurement.** Real ComfyUI graphs on a CPU machine, plus one field run on an 8 GB RTX 4060.

No GPU large enough for the big video models was available. Measured GPU peaks for those are planned (see [GPU validation](#gpu-validation-planned)).

## Summary

| Number | Accuracy | How it was checked |
|---|---|---|
| Latent shape, frame and pixel rounding | **Exact** | ComfyUI's latent nodes; 24 real tensors in ComfyUI ([CPU](#cpu-this-review)) |
| Decoded pixels (float32 IMAGE) and latent bytes | **Exact** | ComfyUI's tensor layout; real tensors |
| Model parameters, stored bytes, data type | **Exact** | 73 published files: tensor bytes plus header equal the file size |
| Model family, latent channels, VAE compression | **Exact** for every ComfyUI-format file checked | ComfyUI's own detection on the real headers |
| Bytes a model takes once loaded | **Exact** when the dtype rule is known (see [Loaded sizes](#loaded-sizes)) | ComfyUI's dtype selection; measured within 0.05% ([CPU](#cpu-this-review)) |
| Sampling memory | **ComfyUI's own estimate**, the number it loads models by, not a measurement | `memory_required`; compared with published peaks |
| VAE decode memory | **ComfyUI's own estimate** for that VAE family | `memory_used_decode` |
| Fits, offloads or over budget | **Follows ComfyUI's loading rule** on the estimate path; under Dynamic VRAM, weights page instead | `load_models_gpu`, `samplers.py` |
| RAM | **Upper bound** | ComfyUI's offload and cache behaviour |
| Time | **Measured** per node (within 0.1% of ComfyUI's timestamps); estimates scale linearly, so they're rough when the size changes | ComfyUI's progress registry ([CPU](#cpu-this-review)) |

## Formulas at a glance

Roughly what the profiler computes for each number, and what that rests on. Shapes use ComfyUI's order: `b` batch, `c` channels, `T` latent frames, `h × w` latent height and width, `L` video frames, `H × W` pixels, `s` and `t` the VAE's spatial and temporal compression. "B" is bytes; "dtype B" is bytes per value of the data type in use (2 for fp16 and bf16).

| Number | Formula (roughly) | Basis | Checked by |
|---|---|---|---|
| Latent shape | `[b, c, (L − 1) // t + 1, H // s, W // s]` | **Exact**: ComfyUI's latent nodes | **Tested**: 24 cases in ComfyUI, all matched ([CPU](#cpu-this-review)) |
| Latent bytes | `b × c × T × h × w × 4 B` (float32) | **Exact**: ComfyUI's tensor layout | **Tested** |
| Decoded frames | `frames × H × W × 3 × 4 B` (float32 IMAGE; 4 channels for RGBA VAEs) | **Exact**: ComfyUI's IMAGE type | **Tested**: 15 decodes matched to the byte |
| File size | `Σ parameters × bytes per value + header` | **Exact**: safetensors and GGUF headers | **Tested**: 73 published files ([appendix](profiler-accuracy-models.md)) |
| Loaded weights | `parameters × inference dtype B`: fp32 and 16-bit files load at 2 B; scaled fp8, int8, nvfp4 and GGUF stay as stored; plain fp8 stays 1 B only with fp8 compute or when 2 B wouldn't fit | **Exact**: ComfyUI's `unet_dtype` / `vae_dtype` rules | **Tested**: within 0.05% of ComfyUI's `model_size()` with 16-bit forced; the fp8 branch by changing ComfyUI's weight budget |
| Sampling, batch 1 (`est1`) | `b × T × h × w × dtype B × 0.01 × factor` MiB with flash attention or xformers; `× 0.15 × factor` without. `factor` is per model (Wan 14B 2.30, Flux 3.1, SDXL 0.8, ...) | **Theoretical**: ComfyUI's own `memory_required`, which it loads models by | **Partly tested**: grows linearly with tokens on CPU; the GPU magnitude is untested. Published peaks run 20–35% higher ([comparison](#compared-with-published-requirements)) |
| Sampling, cond + uncond (`est2`) | `2 × est1`, used when `weights + est2 + margin` fits; otherwise `est1` (one pass at a time). cfg 1 always uses `est1` | **Theoretical**: ComfyUI's `estimate_memory` and `samplers.py` | **Tested** (shape only): cfg above 1 doubled the CPU peak |
| OS margin | 400 MB on Linux, 600 MB on Windows (+100 MB on cards over 15 GB); `--reserve-vram` replaces it | **Exact**: ComfyUI's constants | Read from ComfyUI when running in it |
| Room for weights | `VRAM − max(0.8 GiB + margin, est1 + margin) − latent bytes` | **Theoretical**: ComfyUI's `load_models_gpu` rule | **Field run**: an 8 GB card ran SDXL at 4096² partly offloaded, as predicted ([field run](#field-run-sdxl-at-40964096-on-an-8-gb-rtx-4060)) |
| Sampler verdict | **fits** when `weights ≤ room`; **offloads / streams** `weights − room`; **over budget** when `est1 + latent bytes + margin > VRAM` | **Theoretical**: follows the rule above | Field run; GPU validation planned |
| VAE decode | Per family, × dtype B. KL (SD, SDXL, Flux.1): `2178 × h × w × 64`. Wan 2.1: `(2200 if T ≤ 4 else 7000) × h × w × 64`. Wan 2.2: `8000 × h × w × 256`. LTX-Video: `1200 × T × h × w × 512`. Others in [VAE decode memory](#vae-decode-memory) | **Theoretical**: ComfyUI's `memory_used_decode` per family | **Partly tested**: on CPU the ratio to the formula stays constant across resolutions (KL 2.72, Wan 2.2 0.59, Wan 2.1 2.36); magnitude and frame scaling need a GPU |
| Decode verdict | **falls back to tiled decode** when `decode + margin > VRAM`; else VAE weights offload first (LTX 2.4's can't) | **Theoretical**: ComfyUI's `VAE.decode` | GPU validation planned |
| Stage total and peak | stage `= weights + working + latent bytes`; peak `= max(stages)` | **Theoretical**: ComfyUI frees only what the next load needs | Field run |
| RAM | `Σ model weights + decoded frames`; stored bytes (memory-mapped) under Dynamic VRAM | **Upper bound**: ComfyUI's offload and cache behaviour | Not measured |
| Time | `measured seconds × (new steps ÷ steps) × (new tokens ÷ tokens)` | **Measured** per node; the scaling is **theoretical** | **Tested**: per-node sum within 0.1% of ComfyUI's own timestamps; scaling rough when the size changes |
| Measured VRAM peak | `max(PyTorch allocator peak, device memory in use)` | **Measured** | Device memory includes what Dynamic VRAM holds outside PyTorch |

Basis key:
- **Exact:** arithmetic on known sizes, or the same rule ComfyUI's code applies.
- **Theoretical:** ComfyUI's own estimate or loading rule, copied faithfully but not a measurement of memory use.
- **Tested / partly tested:** checked against real runs in this review; "partly" means the shape of the curve was confirmed but not the GPU magnitude.
- **Upper bound:** can only be lower in practice.

## Exact numbers

### Latent shapes

ComfyUI's latent nodes floor-divide: `[batch, channels, (length − 1) // t + 1, height // s, width // s]`. For example [`EmptyHunyuanLatentVideo`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy_extras/nodes_hunyuan.py#L63-L64), [`EmptyLTXVLatentVideo`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy_extras/nodes_lt.py#L83-L84), [`EmptySD3LatentImage`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy_extras/nodes_sd3.py#L58-L59) and [`EmptyLatentImage`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/nodes.py#L1273-L1275). Sampling then sets the channel count to the model's ([`fix_empty_latent_channels`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/sample.py#L45-L70)).

So a size that isn't a multiple of the compression loses pixels, and the profiler says so. For example, 1080 high on a 16× VAE decodes to 1072.

| Family | Latent channels | Spatial | Temporal | Frame rule |
|---|---|---|---|---|
| SD 1.5, SDXL | 4 | 8 | none | none |
| SD3, Flux.1 | 16 | 8 | none | none |
| Flux 2 | 128 | 16 | none | none |
| Wan 2.1, Wan 2.2 A14B, HunyuanVideo | 16 | 8 | 4 | 4k+1 |
| Wan 2.2 TI2V 5B | 48 | 16 | 4 | 4k+1 |
| HunyuanVideo 1.5 | 32 | 16 | 4 | 4k+1 |
| LTX-Video, LTX-2, LTX-2.3 | 128 | 32 | 8 | 8k+1 |
| MiniMax H3 (video stream) | 24 | 16 | 4* | 17k+5 frames → 5k+2 latents |

\* MiniMax H3 snaps frame counts up to 17k+5, and its latent length is `(frames − 5) // 17 × 5 + 2` ([`nodes_minimax_h3.py`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy_extras/nodes_minimax_h3.py)). ComfyUI's combined audio-video latent format reports 32 channels, the audio stream's. The profiler counts the 24-channel video latent.

Sources: ComfyUI's [`latent_formats.py`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/latent_formats.py) and VAE definitions in [`sd.py`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/sd.py), cross-checked against the model READMEs ([Wan 2.1](https://github.com/Wan-Video/Wan2.1), [Wan 2.2](https://github.com/Wan-Video/Wan2.2), [HunyuanVideo](https://github.com/Tencent-Hunyuan/HunyuanVideo), [HunyuanVideo 1.5](https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5), [LTX-Video](https://github.com/Lightricks/LTX-Video), [LTX-2](https://github.com/Lightricks/LTX-2)).

### Pixels and latents in memory

- **IMAGE** is a float32 tensor `[batch, height, width, channels]` with values 0–1 (see ComfyUI's [datatypes](https://docs.comfy.org/custom-nodes/backend/datatypes) and [`LoadImage`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/nodes.py)). That's `width × height × 3 × 4` bytes per frame: 24.9 MB for 1920×1080 and 99.5 MB for 4K UHD.
- **Decoded frames** go to the intermediate device: system RAM, float32, unless `--gpu-only` or `--fp16-intermediates` ([`intermediate_device`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/model_management.py#L1263-L1273)). The VAE copies each batch's output into one tensor as it goes ([`VAE.decode`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/sd.py#L1388-L1407)). RGBA VAEs (Qwen-Image 2.1) output 4 channels, and the profiler counts 4 for them.
- **LATENT** is `{"samples": [batch, channels, (time,) height, width]}`, float32 on the intermediate device: `4` bytes per value.

### Model files

The [appendix](profiler-accuracy-models.md) lists every file. In short:
- For every safetensors file, the tensor bytes plus the header equal the true file size exactly. For GGUF the difference is only the header and alignment padding.
- ComfyUI's detection identified every ComfyUI-format diffusion model, including fp8, scaled fp8, int8, nvfp4 and GGUF files: Wan 2.1, Wan 2.2 (all variants), Flux.1, SDXL, SD 1.5, LTX-Video, LTX-2, LTX-2.3, HunyuanVideo, HunyuanVideo 1.5, Qwen-Image and MiniMax H3.
- Parameter counts match the published figures (billions): Wan 14B 14.29 and 1.3B 1.42, Wan 2.2 5B 5.00, Flux.1 11.90, SDXL UNet 2.57, LTX 1.92 and 13.04, HunyuanVideo 12.82, HunyuanVideo 1.5 8.33, Qwen-Image 20.43, MiniMax H3 33.12, umt5-xxl 5.69.
- Bytes per value: fp32 4, fp16 and bf16 2, fp8 1; GGUF Q8_0 1.0625, Q6_K 0.8203, Q5_K 0.6875, Q4_K 0.5625, Q3_K 0.4297, Q2_K 0.3281 (from [gguf-py's quant sizes](https://github.com/ggml-org/llama.cpp/blob/master/gguf-py/gguf/constants.py)).

### Loaded sizes

ComfyUI picks the dtype a model runs in, and the profiler asks ComfyUI the same question:
- fp32 weights are cast to the inference dtype ([`unet_dtype`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/model_management.py#L1132-L1183), [`load_diffusion_model_state_dict`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/sd.py#L2504-L2573)).
- Scaled fp8, int8 and nvfp4 stay as stored, and so does GGUF (dequantized per layer).
- A **plain fp8 file is upcast to 16-bit** on a GPU without fp8 compute (RTX 30-series and older) when it fits, which doubles its size. The profiler asks ComfyUI's `unet_dtype` and shows "upcast to 16-bit" when this happens.
- A VAE is cast as a whole to its working dtype ([`vae_dtype`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/model_management.py)). Text encoders follow `text_encoder_dtype`.

The profiler applies these rules for the machine ComfyUI runs on. With `vram_gb` emulating another card, the dtype choice is still this machine's.

## ComfyUI's own estimates

### Sampling memory

ComfyUI estimates a model's working memory with [`BaseModel.memory_required`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/model_base.py#L432-L454):
- `batch × (product of the latent's spatial and time dims) × dtype bytes × 0.01 × memory_usage_factor` MiB, with xformers or flash attention;
- `× 0.15 × memory_usage_factor` MiB otherwise.

[`estimate_memory`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/sampler_helpers.py#L165-L179) computes it for twice the batch (cond and uncond together) and for the batch alone. The factor is set per model family in [`supported_models.py`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/supported_models.py). Wan's scales with model width: `dim / 2222`, so 2.30 for 14B and 0.69 for 1.3B. The profiler reads the factor from ComfyUI's detection of the file.

ComfyUI's own comment calls this formula a TODO to be tweaked. It's the estimate ComfyUI loads models by, not a measurement. In the comparisons below it comes out **below** the model authors' published peaks. In the 8 GB field run it was far **above** the measured PyTorch peak, though that peak may leave out weights held by Dynamic VRAM.

Not counted: reference-image conditioning, which edit models (Flux Kontext and Flux 2, Qwen-Image-Edit, Omnigen2, Lumina2, Wan S2V and others) add to the estimate ([`memory_usage_factor_conds`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/model_base.py#L432-L454)). With one same-size reference image, the profiler shows about half of ComfyUI's estimate.

### VAE decode memory

Each VAE family has its own estimate in [`comfy/sd.py`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/sd.py) (`memory_used_decode`). It's computed per batch item, and the profiler copies it for every family:

| Family | Profiler status |
|---|---|
| KL (SD, SDXL, Flux.1, SD3) | checked |
| Flux 2 | checked, with ComfyUI's ×4 unless fused normalisation is available |
| Wan 2.1, Wan 2.2 | checked |
| Qwen-Image 2.1 | checked |
| LTX-Video | checked |
| LTX 2.4 | copied; not validated on a real file (no public VAE has its key) |
| HunyuanVideo, HunyuanVideo 1.5 | checked |
| CogVideoX | checked |
| Hunyuan Image 2.1 and refiner | checked |
| MiniMax H3 | streamed; at most one 17-frame chunk (28 frames plus 2) resident |

For tiled decode, the estimate is for one tile ([`decode_tiled`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/sd.py#L1426-L1453)).

ComfyUI pages VAE weights out first and tiles only after an actual out-of-memory error ([`VAE.decode`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/sd.py#L1365-L1456)). So the profiler says "falls back to tiled decode" only when the decode itself can't fit. LTX 2.4's VAE can't be offloaded, so its weights count against that.

## How ComfyUI uses VRAM and RAM

### Which models stay in VRAM

- [`free_memory`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/model_management.py#L889-L933) unloads only as much as the next load needs. Models stay resident while there's room, unless `--disable-smart-memory` is set or after an out-of-memory error.
- That's why the profiler reports memory **per stage** (text encode, each sampler, each decode) and takes the largest as the peak, rather than adding everything up.
- An unloaded model moves to system RAM, not out of memory entirely. It's freed only when its loader's cached output is dropped.

| What | Runs on | Moves to when not in use | Source |
|---|---|---|---|
| Diffusion model | GPU | RAM | [`sd.py`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/sd.py#L2521), [`unet_offload_device`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/model_management.py#L1102-L1106) |
| Text encoder | GPU when fp16 works (CPU in low VRAM modes) | RAM | [`text_encoder_device`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/model_management.py#L1209-L1226) |
| VAE | GPU (CPU with `--cpu-vae`) | RAM | [`vae_device`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/model_management.py#L1275-L1284) |
| IMAGE and LATENT outputs | RAM | (stay) | [`intermediate_device`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/model_management.py#L1263-L1273) |

`--gpu-only` keeps all of these on the GPU.

### How much of a model loads (the estimate path)

[`load_models_gpu`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/model_management.py#L935-L1035) gives a model's weights the free VRAM minus whichever is larger:
- `minimum_inference_memory`: 0.8 GiB plus an OS margin of 400 MB on Linux and 600 MB on Windows (700 MB on cards over 15 GB). `--reserve-vram` replaces the margin. See [the constants](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/model_management.py#L873-L887).
- The **batch-1** sampling estimate plus the OS margin.

The doubled estimate only decides which other models get evicted. If cond and uncond don't fit together, ComfyUI runs them one at a time ([`samplers.py`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/samplers.py#L273-L284)). Weights over the budget stay in RAM and are cast to the GPU layer by layer.

The profiler's verdicts follow this:

| Verdict | When |
|---|---|
| **fits** | Weights plus the doubled estimate fit. The stage notes when only the batch-1 estimate fits, because cond and uncond then run one at a time. |
| **offloads N** | N of the weights stay in RAM. Slower, not a failure. |
| **over budget** | The batch-1 estimate, the latents and the OS margin alone, with no weights at all, are over the card. Likely out of memory. |

On AMD and Intel GPUs, ComfyUI also gives at least 40% of free VRAM to weights, which the profiler doesn't model.

### Dynamic VRAM

On NVIDIA with PyTorch 2.8 or later, ComfyUI's default loader is now [Dynamic VRAM](https://docs.comfy.org/development/comfyui-server/startup-flags) (comfy-aimdo):
- It's on unless `--disable-dynamic-vram`, `--highvram`, `--gpu-only`, `--novram` or `--cpu` is given ([`enables_dynamic_vram`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/cli_args.py#L336-L339), [`main.py`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/main.py#L285-L326)).
- Weights live in a virtual address range, page in when used and page out under pressure ([`ModelPatcherDynamic`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/model_patcher.py#L1950-L1985)).
- ComfyUI's code says the estimate is then ignored for loading ([comment](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/model_patcher.py#L1932-L1936)), and `--lowvram` has no effect.

What changes in the profiler:
- **Verdicts:** it detects Dynamic VRAM and reads "streams N" instead of "offloads N". The estimate still decides whether cond and uncond batch together, and how many VAE batch items run at once.
- **RAM:** RAM holds the memory-mapped model files at their stored size, as reclaimable page cache ([`load_safetensors`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/utils.py#L150-L196)). The RAM line counts stored bytes then.
- **Measurement:** weights paged in by Dynamic VRAM are allocated outside PyTorch's allocator. So `torch.cuda.max_memory_allocated` (PyTorch [allocator notes](https://github.com/pytorch/pytorch/blob/main/docs/source/notes/cuda.md)) can leave them out. The run measurement now also records the device memory in use (total minus free, at each node's end) and Dynamic VRAM's own usage. The chart's measured-peak line uses the larger reading.

### RAM

The RAM line is an **upper bound**: every model's weights in the branch, plus the decoded frames as float32. On the estimate path, every unloaded model's copy stays in RAM while its loader's output is cached. ComfyUI's default output cache keeps entries until RAM gets tight ([`main.py`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/main.py#L342-L360)).

Not counted:
- a 2-D tiled decode's brief 3× output buffer ([`decode_tiled_`](https://github.com/comfyanonymous/ComfyUI/blob/62879ac7f585be68f9423af242cbedbf95858b70/comfy/sd.py#L1278-L1289));
- outputs of earlier runs still in the cache;
- Dynamic VRAM's pinned buffers.

### Budget

The profiler budgets against the card's **total** VRAM, or `vram_gb`. ComfyUI decides against **free** VRAM at the moment of loading, which is lower when a display, another program or a second ComfyUI uses the same GPU. On a desktop card that also drives monitors, expect a few hundred MB less than the profiler assumes.

## Compared with published requirements

The profiler, run on the real model files at the settings their authors published VRAM figures for:

| Configuration | Published peak | Profiler (largest stage) | Profiler stages |
|---|---|---|---|
| Wan 2.1 T2V 1.3B, 832×480×81, 24 GB card | 8.19 GB¹ | 6.2 GB sampling stage (text encode 10.6 GB, fp16 umt5 on the GPU) | 2.6 GB weights + 3.5 GB sampling; decode 5.2 GB |
| Wan 2.1 T2V 14B bf16, 1280×720×81, 80 GB card | 69.1 GB² | 53.9 GB | 26.6 weights + 27.2 sampling; decode 12.0 GB |
| Wan 2.2 TI2V 5B, 1280×704×121, 24 GB card | 22.9 GB³ | 15.2 GB | 9.3 weights + 5.9 sampling; decode 13.4 GB + 1.3 GB weights |
| HunyuanVideo 13B, 1280×720×129, 80 GB card | 60 GB⁴ | 40.6 GB | 23.9 weights + 16.7 sampling (cfg 1); decode 38.5 GB |
| HunyuanVideo 13B, 960×544×129, 80 GB card | 45 GB⁴ | 33.4 GB | 23.9 weights + 9.5 sampling (cfg 1); decode 21.8 GB |
| HunyuanVideo 1.5 fp16, 1280×720×121, 24 GB card | ≥ 14 GB with offloading⁵ | 27.1 GB needed; offloads 0.6 GB on 24 GB | 15.5 weights + 8.7 sampling (cond and uncond one at a time); decode 24.7 GB, tiles |

1. [Wan 2.1 README](https://github.com/Wan-Video/Wan2.1): RTX 4090, `--offload_model True --t5_cpu`. The text encoder runs on the CPU there, so compare the sampling stage.
2. Wan 2.1 README efficiency table: a single H20, A100 or H100 with `--offload_model True`. Frame count not stated.
3. [Wan 2.2 README](https://github.com/Wan-Video/Wan2.2): RTX 4090, `--offload_model True --convert_model_dtype --t5_cpu`.
4. [HunyuanVideo README](https://github.com/Tencent-Hunyuan/HunyuanVideo): batch 1 on an 80 GB GPU.
5. [HunyuanVideo 1.5 README](https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5): minimum with offloading. ComfyUI's [HunyuanVideo 1.5 page](https://docs.comfy.org/tutorials/video/hunyuan/hunyuan-video-1-5) recommends a 24 GB GPU.

How to read this:
- The published figures come from the authors' own scripts, not ComfyUI. They use different attention code and offloading, and don't say whether they're allocator or `nvidia-smi` figures.
- The profiler's largest stage is 20–35% below them for the large models.
- That's consistent with ComfyUI's estimate being a planning figure rather than a measurement. It isn't evidence the profiler is wrong about ComfyUI; only the GPU validation below can settle that.
- Published peak figures weren't found for Flux.1, SDXL, LTX-Video, LTX-2.5 or MiniMax H3.

## Measured

### CPU (this review)

Run on a machine without a GPU (ComfyUI 0.46.0, PyTorch 2.15, `--cpu`), with random-weight model files built from ComfyUI's own classes so their key layouts and sizes match the published files. On `--cpu` ComfyUI keeps everything in float32, so loaded sizes were also checked with `--bf16-unet` / `--bf16-vae`, the 16-bit types a GPU picks. Memory on a CPU says little about CUDA, so only shapes, sizes and times are machine-independent results; the decode and sampling runs check scaling only.

| Check | Result |
|---|---|
| Latent shapes and decoded IMAGE bytes, 24 cases: `EmptyLatentImage`, `EmptySD3LatentImage`, `EmptyHunyuanLatentVideo`, `EmptyLTXVLatentVideo`, `Wan22ImageToVideoLatent`, odd sizes (1078 → 1072), lengths (80 → 77 frames), batch 2 | **Exact**, after one fix: `Wan22ImageToVideoLatent` ignores `batch_size` without a `start_image`, so the profiler now applies the batch only when a start image is connected |
| Loaded size, Wan 2.1 1.3B DiT stored as bf16, fp16 with fp32 norms, fp32; loader `weight_dtype` fp8 | **Within 0.05%** of ComfyUI's `model_size()` |
| Loaded size, Wan 2.1, Wan 2.2, SD and 16-channel KL VAEs | **Exact** |
| A file already in fp8, `weight_dtype` default | ComfyUI keeps it at 1 byte only with fp8 compute or when the 16-bit copy wouldn't fit; otherwise it upcasts. Confirmed by changing ComfyUI's weight budget (1 GiB keeps fp8, 24 GiB upcasts). On a GPU the profiler asks the same `unet_dtype` function; see [Limitations](#limitations) |
| VAE decode peak against `memory_used_decode`, by resolution | The ratio is constant across sizes for each VAE (KL 2.72, Wan 2.2 0.59, Wan 2.1 at one latent frame 2.36), so the formulas scale correctly with resolution. KL's 2.72 is ComfyUI's own AMD factor (2.73). Over frame count the CPU doesn't follow the Wan 2.1 formula (CPU 3D convolutions); magnitude needs a GPU |
| Sampling peak, Wan 1.3B, one step, 256 to 5,120 tokens | Grows linearly with tokens; cfg above 1 doubles it, as the batch-2 estimate assumes. Absolute values fall between ComfyUI's flash and non-flash formulas, which differ 7.5× by construction; a GPU is needed to check which applies |
| Node times | The per-node sum was within 0.1% of ComfyUI's own start and finish timestamps (16.854 s against 16.866 s) |
| Cached nodes | Were counted as "not measured" because ComfyUI sends no progress events for them. Fixed: an upstream node with no events is reported as cached |

Fixes from this run, with tests: the `Wan22ImageToVideoLatent` batch rule, cached-node reporting, and no "on the GPU" detail on a machine without one.

### Field run: SDXL at 4096×4096 on an 8 GB RTX 4060

SDXL base (checkpoint), 4096×4096, batch 1, 2 steps, tiled VAE decode, ComfyUI on an RTX 4060 with 8 GB of VRAM and 128 GB of RAM. Profiled before the fixes from this review.

| | Value |
|---|---|
| Latent | `[1, 4, 512, 512]` (exact) |
| Profiler, sampling stage | 4.8 GB weights + 8.2 GB doubled estimate = 13.0 GB, then "over budget" |
| Profiler now (this review's rule) | Cond and uncond can't run together. The batch-1 estimate (4.1 GB) plus the margin leaves about 3.5 GB for weights, so it offloads about 1.3 GB. |
| Measured | KSampler 47 s, tiled VAE decode 42 s. PyTorch peak 2.5 GB allocated, 3.5 GB reserved. After the run ComfyUI held SDXL with 1.6 GB of 4.8 GB on the GPU. |

What it shows:
- The old "over budget" verdict was wrong: ComfyUI ran the stage with part of the model offloaded. The fixed rule predicts that.
- The measured 2.5 GB PyTorch peak is well below even the batch-1 estimate plus the resident weights. Two likely reasons: ComfyUI's estimate is conservative, and on a recent ComfyUI Dynamic VRAM holds weights outside PyTorch's count. The device-memory reading added in this review will separate the two on the next run.

## Limitations

- **Reference-image conditioning** (edit models) isn't added to the sampling estimate.
- **Diffusers-layout VAE files** (LTX-2's diffusers VAEs) are misidentified. Diffusers-layout diffusion models (an SDXL diffusers UNet) are detected through ComfyUI's diffusers path, as its loader does.
- **Packed 4- and 6-bit weights** (nvfp4, w6a8) show fewer parameters than the model has, because two values share a byte. Loaded bytes are still right.
- **LTX-2.5:** the official repository is gated, so it was validated on public LTX-2 and LTX-2.3 files and community LTX-2.5 conversions. The LTX 2.4 VAE formula is copied from ComfyUI but untested on a real file.
- **MiniMax H3's Sol decoder** (non-causal) has a different decode estimate in ComfyUI, and the profiler uses the stock decoder's.
- **AMD and Intel GPUs:** ComfyUI's 40% minimum weight share isn't modelled.
- **Timing:** async nodes and nodes that expand into subgraphs include the time of whatever ran in between or inside them. With `vram_per_node`, their per-node peaks overlap.
- **fp8 files on GPUs without fp8 compute** (Ampere and older, A6000 included): whether ComfyUI upcasts them depends on the card's VRAM. The profiler asks ComfyUI on the machine it runs on, so an emulated `vram_gb` doesn't change that decision, and on a machine without a GPU the stored 1 byte is used.
- **`--fp8_e4m3fn-unet`** and similar flags aren't read; the loader's `weight_dtype` is.
- **ComfyUI moves fast.** This review is against `62879ac`. Re-check after large memory-management changes.

## GPU validation (planned)

Measured GPU peaks for the large models are planned for an NVIDIA RTX A6000 (48 GB), in a separate session. The plan:

1. **Runs:** the configurations in [Compared with published requirements](#compared-with-published-requirements) that fit 48 GB, plus an image model (SDXL, Flux.1) and the newer video models (Wan 2.2 A14B, HunyuanVideo 1.5, LTX-2.x, MiniMax H3), at two or three sizes each.
2. **Record for each:** the profiler's evaluation before the run; then from the run, PD Profiler's measured PyTorch peak (allocated and reserved), device memory in use, Dynamic VRAM usage, per-node peaks (`vram_per_node` on) and node times; and `nvidia-smi`'s peak.
   Also: VAE decode peaks for Wan 2.1 at one, two and five latent frames (the CPU couldn't check the formula over time), and a plain fp8 diffusion model (the A6000 has no fp8 compute, so ComfyUI should upcast it to 16-bit).
3. **Run each twice:** once with Dynamic VRAM (the default) and once with `--disable-dynamic-vram`. The second exercises the estimate path the verdicts model.
4. **Emulate smaller cards:** `vram_gb` 8, 12, 16 and 24, checked against `--reserve-vram` runs that limit what ComfyUI sees.
5. **Collect** the profile sidecars (`export_sidecar`), which hold the estimate and the measurement side by side. Add a results table to this page, and adjust the profiler where the estimate and the measurement disagree consistently.

## Sources

- ComfyUI source at [`62879ac`](https://github.com/comfyanonymous/ComfyUI/tree/62879ac7f585be68f9423af242cbedbf95858b70); individual files and lines are linked where used above.
- ComfyUI docs: [startup flags](https://docs.comfy.org/development/comfyui-server/startup-flags), [datatypes](https://docs.comfy.org/custom-nodes/backend/datatypes), [Wan 2.2](https://docs.comfy.org/tutorials/video/wan/wan2_2), [HunyuanVideo 1.5](https://docs.comfy.org/tutorials/video/hunyuan/hunyuan-video-1-5), [LTX-2.5](https://docs.comfy.org/tutorials/video/ltx/ltx-2-5), [Qwen-Image](https://docs.comfy.org/tutorials/image/qwen/qwen-image), [system requirements](https://docs.comfy.org/installation/system_requirements).
- Model repositories: [Wan 2.1](https://github.com/Wan-Video/Wan2.1), [Wan 2.2](https://github.com/Wan-Video/Wan2.2), [HunyuanVideo](https://github.com/Tencent-Hunyuan/HunyuanVideo), [HunyuanVideo 1.5](https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5), [LTX-Video](https://github.com/Lightricks/LTX-Video), [LTX-2](https://github.com/Lightricks/LTX-2).
- Model files and sizes: the Hugging Face repositories listed in the [appendix](profiler-accuracy-models.md) (Comfy-Org repackages, Lightricks, city96 GGUF, stabilityai, and others).
- PyTorch CUDA memory: [`docs/source/notes/cuda.md`](https://github.com/pytorch/pytorch/blob/main/docs/source/notes/cuda.md).
- GGUF block sizes: [gguf-py constants](https://github.com/ggml-org/llama.cpp/blob/master/gguf-py/gguf/constants.py).
