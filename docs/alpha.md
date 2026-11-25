# Alpha and premultiplication

Inside ComfyUI, IMAGE + MASK are **straight** and every Pipedream mask uses **1.0 = opaque**. Pipedream never premultiplies inside the graph; files follow their format's convention, recorded in the sidecar:

| Format | Written as | Why |
|--------|-----------|-----|
| PNG, WebP | Straight | Their specs define straight alpha. |
| ProRes 4444 | Straight | No reliable flag in the bitstream; interpret Pipedream ProRes as straight in AE, Nuke, Resolve. |
| EXR | Premultiplied | The OpenEXR spec defines RGBA as premultiplied; RGB is multiplied after any sRGB-to-linear decode. [PD Load](../web/docs/PDLoad.md) divides it back. |

jpg, mp4 and webm can't store alpha; [PD Save](../web/docs/PDSave.md) skips it with a console warning.

## Core ComfyUI masks

Core ComfyUI uses the opposite mask polarity: Load Image's mask is `1 - alpha`, and Join Image with Alpha inverts its mask. Put an **Invert Mask** between core masks and Pipedream (either direction). For images without alpha, core Load Image gives a 64×64 empty mask; leave PD Save's `alpha` unconnected then.

## Where alpha comes from

PD Save takes alpha from its `alpha` input (a MASK, or an IMAGE/VIDEO's luminance; one frame or one per frame) or the images' fourth channel. PD Load returns alpha as `mask`. The video nodes ([PD Video To Images](../web/docs/PDVideoToImages.md), [PD Video Get Frame](../web/docs/PDVideoGetFrame.md)) return a ProRes 4444, `yuva*` or `rgba` source's alpha as `mask` (1.0 = opaque), and full opacity when there is none.
