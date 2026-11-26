# PD Profiler accuracy: model file validation

Appendix to [Profiler accuracy](profiler-accuracy.md). Every row is a real file published on Hugging Face. Only its header was read (HTTP range requests); the file was rebuilt locally as a sparse file of its true size and run through PipeDream's `core/model_files.py` with ComfyUI's own model detection (ComfyUI `62879ac`, November 2026). Loaded sizes assume an NVIDIA GPU with fp16/bf16 support and show plain fp8 files as stored; on a GPU without fp8 compute, ComfyUI upcasts a plain fp8 file to 16-bit when it fits, and the profiler reports that on such a machine.

Checked on every row: the bytes in the tensor table plus the header equal the true file size exactly (safetensors); GGUF differs only by its header and alignment padding.

Columns: size in bytes (GB); format; what PipeDream identified (`comfy` = ComfyUI's detection, `fallback` = the file-name table); parameters (billions); true size minus tensor bytes (the header); dominant data type; bytes once loaded (GB); latent channels / dims / ComfyUI memory_usage_factor / patch size; VAE family / channels / spatial / temporal compression; text encoder bytes once loaded (GB).

Not covered: the official `Lightricks/LTX-2.5` repository is gated (HTTP 401); public LTX-2 and LTX-2.3 files and community LTX-2.5 conversions stand in. The two rows marked unrecognised are an audio VAE and a latent upsampler, which are not video VAEs.

| # | repo / path | size B (GB) | fmt | PipeDream detection | params B | size - stored (header) | dominant dtype | loaded GB (gpusim) | latent ch / dims / mem factor / patch | VAE family / ch / sp / t | encoder loaded GB |
|--|--|--|--|--|--|--|--|--|--|--|--|
| 1 | Comfy-Org/Wan_2.1_ComfyUI_repackaged/split_files/diffusion_models/wan2.1_t2v_14B_fp8_e4m3fn.safetensors | 14289605920 (14.29) | safetensors | WAN21_T2V (comfy) | 14.288 | 115936 | F8_E4M3 | 14.29 | 16 / 3 / 2.3 / [1, 2, 2] | - | - |
| 2 | Comfy-Org/Wan_2.1_ComfyUI_repackaged/split_files/diffusion_models/wan2.1_t2v_14B_fp8_scaled.safetensors | 14293896178 (14.29) | safetensors | WAN21_T2V (comfy) | 14.288 | 144664 | F8_E4M3 | 14.29 | 16 / 3 / 2.3 / [1, 2, 2] | - | - |
| 3 | Comfy-Org/Wan_2.1_ComfyUI_repackaged/split_files/diffusion_models/wan2.1_t2v_14B_fp16.safetensors | 28577761176 (28.58) | safetensors | WAN21_T2V (comfy) | 14.288 | 112408 | F16 | 28.58 | 16 / 3 / 2.3 / [1, 2, 2] | - | - |
| 4 | Comfy-Org/Wan_2.1_ComfyUI_repackaged/split_files/diffusion_models/wan2.1_t2v_14B_bf16.safetensors | 28577096680 (28.58) | safetensors | WAN21_T2V (comfy) | 14.288 | 113512 | BF16 | 28.58 | 16 / 3 / 2.3 / [1, 2, 2] | - | - |
| 5 | Comfy-Org/Wan_2.1_ComfyUI_repackaged/split_files/diffusion_models/wan2.1_t2v_1.3B_bf16.safetensors | 2838104528 (2.84) | safetensors | WAN21_T2V (comfy) | 1.419 | 110928 | BF16 | 2.84 | 16 / 3 / 0.691 / [1, 2, 2] | - | - |
| 6 | Comfy-Org/Wan_2.1_ComfyUI_repackaged/split_files/diffusion_models/wan2.1_i2v_720p_14B_fp8_scaled.safetensors | 16401356938 (16.40) | safetensors | WAN21_I2V (comfy) | 16.395 | 174696 | F8_E4M3 | 16.40 | 16 / 3 / 2.3 / [1, 2, 2] | - | - |
| 7 | Comfy-Org/Wan_2.2_ComfyUI_Repackaged/split_files/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors | 14293923632 (14.29) | safetensors | WAN21_T2V (comfy) | 14.288 | 180736 | F8_E4M3 | 14.29 | 16 / 3 / 2.3 / [1, 2, 2] | - | - |
| 8 | Comfy-Org/Wan_2.2_ComfyUI_Repackaged/split_files/diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors | 14293923632 (14.29) | safetensors | WAN21_T2V (comfy) | 14.288 | 180736 | F8_E4M3 | 14.29 | 16 / 3 / 2.3 / [1, 2, 2] | - | - |
| 9 | Comfy-Org/Wan_2.2_ComfyUI_Repackaged/split_files/diffusion_models/wan2.2_t2v_high_noise_14B_fp16.safetensors | 28577095592 (28.58) | safetensors | WAN21_T2V (comfy) | 14.288 | 112424 | F16 | 28.58 | 16 / 3 / 2.3 / [1, 2, 2] | - | - |
| 10 | Comfy-Org/Wan_2.2_ComfyUI_Repackaged/split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors | 9999658848 (10.00) | safetensors | WAN22_T2V (comfy) | 5.000 | 83424 | F16 | 10.00 | 48 / 3 / 1.38 / [1, 2, 2] | - | - |
| 11 | Comfy-Org/Wan_2.1_ComfyUI_repackaged/split_files/vae/wan_2.1_vae.safetensors | 253815318 (0.25) | safetensors | - | 0.127 | 30256 | BF16 | 0.25 | - | Wan 2.1 / 16 / 8 / 4 | - |
| 12 | Comfy-Org/Wan_2.2_ComfyUI_Repackaged/split_files/vae/wan2.2_vae.safetensors | 1409400960 (1.41) | safetensors | - | 0.705 | 23624 | F16 | 1.41 | - | Wan 2.2 / 48 / 16 / 4 | - |
| 13 | Comfy-Org/Wan_2.1_ComfyUI_repackaged/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors | 6735906897 (6.74) | safetensors | - | 5.685 | 48856 | F8_E4M3 | 6.74 | - | - | 6.74 |
| 14 | Comfy-Org/Wan_2.1_ComfyUI_repackaged/split_files/text_encoders/umt5_xxl_fp16.safetensors | 11366399385 (11.37) | safetensors | - | 5.685 | 30400 | F16 | 11.37 | - | - | 11.37 |
| 15 | Comfy-Org/flux1-dev/flux1-dev-fp8.safetensors [ckpt] | 17246524772 (17.25) | safetensors | Flux (comfy) | 11.901 | 226448 | F8_E4M3 | d 11.90 + v 0.17 + e 5.01 | 16 / 2 / 3.1 / 2 | KL / 16 / 8 / 1 | 5.01 |
| 16 | Comfy-Org/flux1-schnell/flux1-schnell-fp8.safetensors [ckpt] | 17236328572 (17.24) | safetensors | FluxSchnell (comfy) | 11.891 | 260008 | F8_E4M3 | d 11.89 + v 0.17 + e 5.01 | 16 / 2 / 3.1 / 2 | KL / 16 / 8 / 1 | 5.01 |
| 17 | Comfy-Org/flux1-dev/flux1-dev.safetensors | 23802932552 (23.80) | safetensors | Flux (comfy) | 11.901 | 115912 | BF16 | 23.80 | 16 / 2 / 3.1 / 2 | - | - |
| 18 | Comfy-Org/Lumina_Image_2.0_Repackaged/split_files/vae/ae.safetensors | 335304388 (0.34) | safetensors | - | 0.084 | 25656 | F32 | 0.17 | - | KL / 16 / 8 / 1 | - |
| 19 | Comfy-Org/flux2-dev/split_files/vae/flux2-vae.safetensors | 336213556 (0.34) | safetensors | - | 0.084 | 28064 | F32 | 0.17 | - | Flux 2 / 128 / 16 / 1 | - |
| 22 | comfyanonymous/flux_text_encoders/t5xxl_fp16.safetensors | 9787841024 (9.79) | safetensors | - | 4.894 | 27136 | F16 | 9.79 | - | - | 9.79 |
| 23 | comfyanonymous/flux_text_encoders/t5xxl_fp8_e4m3fn.safetensors | 4893934904 (4.89) | safetensors | - | 4.894 | 27960 | F8_E4M3 | 4.89 | - | - | 4.89 |
| 24 | comfyanonymous/flux_text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors | 5157348688 (5.16) | safetensors | - | 4.894 | 45744 | F8_E4M3 | 5.16 | - | - | 5.16 |
| 25 | comfyanonymous/flux_text_encoders/clip_l.safetensors | 246144152 (0.25) | safetensors | - | 0.123 | 23192 | F16 | 0.25 | - | - | 0.25 |
| 26 | stabilityai/stable-diffusion-xl-base-1.0/sd_xl_base_1.0.safetensors [ckpt] | 6938078334 (6.94) | safetensors | SDXL (comfy) | 2.567 | 402444 | F16 | d 5.13 + v 0.17 + e 1.64 | 4 / 2 / 0.8 / - | KL / 4 / 8 / 1 | 1.64 |
| 27 | stabilityai/stable-diffusion-xl-base-1.0/unet/diffusion_pytorch_model.fp16.safetensors | 5135149760 (5.14) | safetensors | SDXL (comfy) | 2.567 | 222392 | F16 | 5.13 | 4 / 2 / 0.8 / - | - | - |
| 28 | stabilityai/sdxl-vae/sdxl_vae.safetensors | 334641164 (0.33) | safetensors | - | 0.084 | 25704 | F32 | 0.17 | - | KL / 4 / 8 / 1 | - |
| 29 | Comfy-Org/stable-diffusion-v1-5-archive/v1-5-pruned-emaonly-fp16.safetensors [ckpt] | 2132696762 (2.13) | safetensors | SD15 (comfy) | 0.860 | 201990 | F16 | d 1.72 + v 0.17 + e 0.25 | 4 / 2 / 1 / - | KL / 4 / 8 / 1 | 0.25 |
| 30 | Lightricks/LTX-Video/ltx-video-2b-v0.9.1.safetensors [ckpt] | 5716863844 (5.72) | safetensors | LTXV (comfy) | 1.923 | 138752 | BF16 | d 3.85 + v 1.87 | 128 / 3 / 5.5 / - | LTX-Video / 128 / 32 / 8 | - |
| 31 | Lightricks/LTX-Video/ltxv-13b-0.9.8-dev-fp8.safetensors [ckpt] | 15694279916 (15.69) | safetensors | LTXV (comfy) | 13.043 | 214792 | F8_E4M3 | d 13.20 + v 2.49 | 128 / 3 / 11 / - | LTX-Video / 128 / 32 / 8 | - |
| 32 | Lightricks/LTX-Video/ltxv-13b-0.9.8-dev.safetensors [ckpt] | 28579183340 (28.58) | safetensors | LTXV (comfy) | 13.043 | 216328 | BF16 | d 26.09 + v 2.49 | 128 / 3 / 11 / - | LTX-Video / 128 / 32 / 8 | - |
| 33 | Comfy-Org/HunyuanVideo_repackaged/split_files/diffusion_models/hunyuan_video_t2v_720p_bf16.safetensors | 25642131432 (25.64) | safetensors | HunyuanVideo (comfy) | 12.821 | 106344 | BF16 | 25.64 | 16 / 3 / 1.8 / [1, 2, 2] | - | - |
| 34 | Comfy-Org/HunyuanVideo_repackaged/split_files/vae/hunyuan_video_vae_bf16.safetensors | 492984198 (0.49) | safetensors | - | 0.246 | 26592 | BF16 | 0.49 | - | HunyuanVideo / 16 / 8 / 4 | - |
| 35 | Comfy-Org/HunyuanVideo_repackaged/split_files/text_encoders/llava_llama3_fp8_scaled.safetensors | 9091392483 (9.09) | safetensors | - | 8.040 | 56536 | F8_E4M3 | 9.09 | - | - | 9.09 |
| 36 | Comfy-Org/Qwen-Image_ComfyUI/split_files/diffusion_models/qwen_image_bf16.safetensors | 40861031488 (40.86) | safetensors | QwenImage (comfy) | 20.430 | 229312 | BF16 | 40.86 | 16 / 3 / 1.8 / - | - | - |
| 37 | Comfy-Org/Qwen-Image_ComfyUI/split_files/diffusion_models/qwen_image_fp8_e4m3fn.safetensors | 20430635136 (20.43) | safetensors | QwenImage (comfy) | 20.430 | 234048 | F8_E4M3 | 20.43 | 16 / 3 / 1.8 / - | - | - |
| 38 | Comfy-Org/Qwen-Image_ComfyUI/split_files/vae/qwen_image_vae.safetensors | 253806246 (0.25) | safetensors | - | 0.127 | 21184 | BF16 | 0.25 | - | Wan 2.1 / 16 / 8 / 4 | - |
| 39 | Comfy-Org/Qwen-Image_ComfyUI/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors | 9384670680 (9.38) | safetensors | - | 8.292 | 152232 | F8_E4M3 | 9.38 | - | - | 9.38 |
| 48 | Lightricks/LTX-2.3/ltx-2.3-22b-dev.safetensors [ckpt] | 46149344974 (46.15) | safetensors | LTXAV (comfy) | 21.005 | 872440 | BF16 | d 42.01 + v 1.45 + e 2.31 | 128 / 3 / 0.077 / - | LTX-Video / 128 / 32 / 8 | 2.31 |
| 49 | Lightricks/LTX-2/ltx-2-19b-dev-fp8.safetensors [ckpt] | 27078716018 (27.08) | safetensors | LTXAV (comfy) | 19.585 | 1042152 | F8_E4M3 | d 22.96 + v 2.44 + e 1.45 | 128 / 3 / 0.077 / - | LTX-Video / 128 / 32 / 8 | 1.45 |
| 50 | Lightricks/LTX-2/ltx-2-19b-dev-fp4.safetensors [ckpt] | 19988416674 (19.99) | safetensors | LTXAV (comfy) | 12.495 | 1213720 | U8 | d 15.87 + v 2.44 + e 1.45 | 128 / 3 / 0.077 / - | LTX-Video / 128 / 32 / 8 | 1.45 |
| 51 | Lightricks/LTX-2/vae/diffusion_pytorch_model.safetensors | 2444982370 (2.44) | safetensors | - | 1.222 | 22656 | BF16 | 2.44 | - | HunyuanVideo / 128 / 8 / 4 | - |
| 52 | PrunaAI/P-LTX-2.3-VAED/vae/diffusion_pytorch_model.safetensors | 1327909418 (1.33) | safetensors | - | 0.664 | 22600 | BF16 | 1.33 | - | HunyuanVideo / 128 / 8 / 4 | - |
| 53 | rzgar/LTX-2.3-Cinematic-VAE/LTX23_video_vae_bf16_cinematic.safetensors | 1452258578 (1.45) | safetensors | - | 0.726 | 46128 | BF16 | 1.45 | - | LTX-Video / 128 / 32 / 8 | - |
| 54 | neuregex/LTX-2.5-w4a8-comfy/diffusion_models/ltx-2.5-22b-distilled-transformer-w4a8.safetensors | 12520363000 (12.52) | safetensors | LTXAV (comfy) | 12.025 | 1521912 | I8 | 12.50 | 128 / 3 / 0.077 / - | - | - |
| 55 | neuregex/LTX-2.5-w4a8-comfy/text_encoders/gemma4-12b-with-proj-ltx-2.5-w4a8.safetensors | 10604341102 (10.60) | safetensors | - | 8.382 | 234712 | I8 | 10.60 | - | - | 10.60 |
| 56 | Comfy-Org/MiniMax-H3/diffusion_models/minimax_h3_fl2va_bf16.safetensors | 66280487368 (66.28) | safetensors | MiniMaxH3 (comfy) | 33.123 | 57224 | BF16 | 66.25 | 24 / 3 / 0.114 / [1, 2, 2] | - | - |
| 57 | Comfy-Org/MiniMax-H3/diffusion_models/minimax_h3_fl2va_pruned_fp8_scaled.safetensors | 20958205608 (20.96) | safetensors | MiniMaxH3 (comfy) | 20.111 | 112816 | F8_E4M3 | 20.96 | 24 / 3 / 0.114 / - | - | - |
| 58 | Comfy-Org/MiniMax-H3/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors | 20970379616 (20.97) | safetensors | MiniMaxH3 (comfy) | 20.114 | 95424 | I8 | 20.96 | 24 / 3 / 0.114 / - | - | - |
| 59 | Comfy-Org/MiniMax-H3/diffusion_models/minimax_h3_fl2va_pruned_w6a8.safetensors | 15983746636 (15.98) | safetensors | MiniMaxH3 (comfy) | 15.900 | 120120 | I8 | 15.98 | 24 / 3 / 0.114 / - | - | - |
| 60 | Comfy-Org/MiniMax-H3/vae/minimax_h3_video_vae_fp16.safetensors | 5207808496 (5.21) | safetensors | - | 2.604 | 66336 | F16 | 5.21 | - | MiniMax H3 / 24 / 16 / 4 | - |
| 61 | Comfy-Org/MiniMax-H3/vae/minimax_h3_sol_vae_fp16.safetensors | 3596335728 (3.60) | safetensors | - | 1.798 | 45984 | F16 | 3.60 | - | MiniMax H3 / 24 / 16 / 4 | - |
| 62 | Comfy-Org/MiniMax-H3/vae/minimax_h3_audio_vae_fp32.safetensors | 605254808 (0.61) | safetensors | - | 0.151 | 105528 | F32 | 0.30 | - | UNRECOGNISED / 0 / 8 / 1 | - |
| 63 | Comfy-Org/MiniMax-H3/text_encoders/qwen3vl_32b_minimax_h3_bf16.safetensors | 51506295256 (51.51) | safetensors | - | 25.753 | 103416 | BF16 | 51.51 | - | - | 51.51 |
| 64 | Comfy-Org/MiniMax-H3/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors | 15687142551 (15.69) | safetensors | - | 15.089 | 231408 | U8 | 15.69 | - | - | 15.69 |
| 65 | Comfy-Org/Wan_2.2_ComfyUI_Repackaged/split_files/diffusion_models/wan2.2_t2v_low_noise_14B_fp16.safetensors | 28577095592 (28.58) | safetensors | WAN21_T2V (comfy) | 14.288 | 112424 | F16 | 28.58 | 16 / 3 / 2.3 / [1, 2, 2] | - | - |
| 66 | Comfy-Org/Wan_2.2_ComfyUI_Repackaged/split_files/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors | 14294742832 (14.29) | safetensors | WAN21_T2V (comfy) | 14.289 | 180736 | F8_E4M3 | 14.29 | 16 / 3 / 2.3 / [1, 2, 2] | - | - |
| 67 | Comfy-Org/Wan_2.2_ComfyUI_Repackaged/split_files/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors | 14294742832 (14.29) | safetensors | WAN21_T2V (comfy) | 14.289 | 180736 | F8_E4M3 | 14.29 | 16 / 3 / 2.3 / [1, 2, 2] | - | - |
| 68 | Comfy-Org/Wan_2.2_ComfyUI_Repackaged/split_files/diffusion_models/wan2.2_i2v_high_noise_14B_fp16.safetensors | 28577914792 (28.58) | safetensors | WAN21_T2V (comfy) | 14.289 | 112424 | F16 | 28.58 | 16 / 3 / 2.3 / [1, 2, 2] | - | - |
| 69 | Comfy-Org/Wan_2.2_ComfyUI_Repackaged/split_files/diffusion_models/wan2.2_i2v_low_noise_14B_fp16.safetensors | 28577914792 (28.58) | safetensors | WAN21_T2V (comfy) | 14.289 | 112424 | F16 | 28.58 | 16 / 3 / 2.3 / [1, 2, 2] | - | - |
| 70 | Comfy-Org/Wan_2.2_ComfyUI_Repackaged/split_files/diffusion_models/wan2.2_fun_control_5B_bf16.safetensors | 10003303280 (10.00) | safetensors | WAN22_T2V (comfy) | 5.002 | 84464 | BF16 | 10.00 | 48 / 3 / 1.38 / [1, 2, 2] | - | - |
| 71 | Comfy-Org/Wan_2.2_ComfyUI_Repackaged/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors | 6735906897 (6.74) | safetensors | - | 5.685 | 48856 | F8_E4M3 | 6.74 | - | - | 6.74 |
| 72 | Comfy-Org/Hunyuan-Video-1.5/split_files/diffusion_models/hunyuanvideo1.5_720p_t2v_fp16.safetensors | 16653368128 (16.65) | safetensors | HunyuanVideo15 (comfy) | 8.327 | 151808 | F16 | 16.65 | 32 / 3 / 4 / [1, 1, 1] | - | - |
| 73 | Comfy-Org/Hunyuan-Video-1.5/split_files/diffusion_models/hunyuanvideo1.5_480p_i2v_fp16.safetensors | 16653368128 (16.65) | safetensors | HunyuanVideo15 (comfy) | 8.327 | 151808 | F16 | 16.65 | 32 / 3 / 4 / [1, 1, 1] | - | - |
| 74 | Comfy-Org/Hunyuan-Video-1.5/split_files/diffusion_models/hunyuanvideo1.5_480p_t2v_cfg_distilled_fp8_scaled.safetensors | 8330399746 (8.33) | safetensors | HunyuanVideo15 (comfy) | 8.327 | 204016 | F8_E4M3 | 8.33 | 32 / 3 / 4 / [1, 1, 1] | - | - |
| 75 | Comfy-Org/Hunyuan-Video-1.5/split_files/diffusion_models/hunyuanvideo1.5_720p_sr_distilled_fp16.safetensors | 16662949072 (16.66) | safetensors | HunyuanVideo15_SR_Distilled (comfy) | 8.331 | 152208 | F16 | 16.66 | 32 / 3 / 4 / [1, 1, 1] | - | - |
| 76 | Comfy-Org/Hunyuan-Video-1.5/split_files/vae/hunyuanvideo15_vae_fp16.safetensors | 2521292758 (2.52) | safetensors | - | 1.261 | 24528 | F16 | 2.52 | - | HunyuanVideo 1.5 / 32 / 16 / 4 | - |
| 77 | Comfy-Org/Hunyuan-Video-1.5/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors | 9384670680 (9.38) | safetensors | - | 8.292 | 152232 | F8_E4M3 | 9.38 | - | - | 9.38 |
| 78 | Comfy-Org/Hunyuan-Video-1.5/split_files/text_encoders/byt5_small_glyphxl_fp16.safetensors | 438643184 (0.44) | safetensors | - | 0.219 | 13296 | F16 | 0.44 | - | - | 0.44 |
| 79 | Comfy-Org/Hunyuan-Video-1.5/split_files/latent_upscale_models/hunyuanvideo15_latent_upsampler_720p.safetensors | 85854616 (0.09) | safetensors | - | 0.021 | 10008 | F32 | 0.04 | - | UNRECOGNISED / 0 / 8 / 1 | - |
| 80 | city96/Wan2.1-T2V-14B-gguf/wan2.1-t2v-14b-Q4_K_M.gguf | 10124581504 (10.12) | gguf | WAN21_T2V (comfy) | 14.288 | 67968.0 | Q4_K | 10.12 | 16 / 3 / 2.3 / [1, 2, 2] | - | - |
| 81 | city96/Wan2.1-T2V-14B-gguf/wan2.1-t2v-14b-Q8_0.gguf | 15879461504 (15.88) | gguf | WAN21_T2V (comfy) | 14.288 | 67968.0 | Q8_0 | 15.88 | 16 / 3 / 2.3 / [1, 2, 2] | - | - |
| 82 | city96/FLUX.1-dev-gguf/flux1-dev-Q4_K_S.gguf | 6805988640 (6.81) | gguf | Flux (comfy) | 11.901 | 54304.0 | Q4_K | 6.81 | 16 / 2 / 3.1 / 2 | - | - |
| 83 | city96/FLUX.1-dev-gguf/flux1-dev-Q8_0.gguf | 12708281504 (12.71) | gguf | Flux (comfy) | 11.901 | 54304.0 | Q8_0 | 12.71 | 16 / 2 / 3.1 / 2 | - | - |
