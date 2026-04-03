# Pipedream Workflow Library

Example workflows demonstrating how to use Pipedream nodes. Each subdirectory contains a `workflow.json` (when available) and a README explaining the setup.

## Loading Workflows

1. Drag the `workflow.json` file into ComfyUI, or use **File > Load**
2. All workflows require the Pipedream node pack to be installed

## Progression

The workflows are numbered as an intentional learning path:

| # | Workflow | What It Teaches |
|---|---------|-----------------|
| 01 | Basic Output Namer | Wire PD Output Namer with default tokens, feed into Save Image |
| 02 | Network Output | Replace Save Image with PD Network Output, UNC path setup |
| 03 | Project Context + Tokens | Use PD Project Context as the token root; context flows downstream |
| 04 | Switch Node | Single-channel and multi-channel switch; manual vs value-driven mode |
| 05 | Single Wedge | One PD Wedge iterating over a prompt list; queue injection basics |
| 06 | Multi-Wedge + Rasterizer | Two wedges (prompt + seed), Rasterizer preview, cartesian product |
| 07 | Full Production Shot | All nodes together in a complete production pipeline |

Workflows 01–04 use only core ComfyUI nodes as the generative backbone. Workflows 05–07 use a simple SD1.5/SDXL backbone as placeholder.
