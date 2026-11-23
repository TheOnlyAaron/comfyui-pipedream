"""
PD video utility nodes.

Pipedream-owned counterparts to core ComfyUI's Create Video / Get Video
Components, plus single-frame pickers.  All nodes use the core ``VIDEO``
type so they interoperate with Load Video, Save Video and other packs.
Decoding helpers live in ``core/video.py``.
"""

from ..core import settings
from ..core.common import display_name
from ..core.video import images_to_video, read_frame, read_frames, resolve_index

_CATEGORY = "Pipedream/Video"
_MODES = ["first", "last", "index"]
_INT_MAX = 0x7FFFFFFF

_MODE_TOOLTIP = "first / last frame, or the frame at 'index'."
_INDEX_TOOLTIP = "Frame index used when mode is 'index'. Negative values count from the end (-1 = last)."
_MASK_TOOLTIP = ("Alpha of the same frames (1.0 = opaque, straight alpha). Full opacity when "
                 "the video has no alpha.")


class PDImagesToVideo:
    """Wrap an IMAGE batch (plus optional audio) as an in-memory VIDEO."""

    DISPLAY_NAME = display_name("PD Images To Video")
    DESCRIPTION = (
        "Combine an image batch and optional audio into a VIDEO. "
        "Nothing is encoded or written to disk until a save node runs."
    )
    CATEGORY = _CATEGORY
    FUNCTION = "execute"
    RETURN_TYPES = ("VIDEO", "INT")
    RETURN_NAMES = ("video", "frame_count")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "fps": ("FLOAT", {
                    "default": settings.get("output.fps"), "min": 0.01, "max": 1000.0, "step": 0.001,
                    "tooltip": "Frame rate. NTSC rates like 23.976 snap to 24000/1001.",
                }),
            },
            "optional": {
                "audio": ("AUDIO",),
            },
        }

    def execute(self, images, fps, audio=None):
        video = images_to_video(images, fps, audio)
        return (video, int(images.shape[0]))


class PDVideoToImages:
    """Decode a frame range of a VIDEO to an IMAGE batch plus audio."""

    DISPLAY_NAME = display_name("PD Video To Images")
    DESCRIPTION = (
        "Decode a VIDEO to images, audio and fps. Optionally decode only a "
        "range (start_frame, frame_limit) and every Nth frame to save memory."
    )
    CATEGORY = _CATEGORY
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "MASK", "AUDIO", "FLOAT", "INT")
    RETURN_NAMES = ("images", "mask", "audio", "fps", "frame_count")
    OUTPUT_TOOLTIPS = (
        "Decoded frames, float32 RGB.",
        _MASK_TOOLTIP,
        "Audio cut to the decoded time span (None when the video has none).",
        "Source frame rate divided by step.",
        "Number of decoded frames.",
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("VIDEO",),
            },
            "optional": {
                "start_frame": ("INT", {
                    "default": 0, "min": 0, "max": _INT_MAX,
                    "tooltip": "First frame to decode (0-based).",
                }),
                "frame_limit": ("INT", {
                    "default": 0, "min": 0, "max": _INT_MAX,
                    "tooltip": "Maximum number of frames to output. 0 = all remaining frames.",
                }),
                "step": ("INT", {
                    "default": 1, "min": 1, "max": 10000,
                    "tooltip": "Keep every Nth frame. Output fps is divided by this value.",
                }),
            },
        }

    def execute(self, video, start_frame=0, frame_limit=0, step=1):
        images, mask, audio, fps, count = read_frames(video, start_frame, frame_limit, step)
        return (images, mask, audio, fps, count)


class PDVideoGetFrame:
    """Decode a single frame (first, last or by index) from a VIDEO."""

    DISPLAY_NAME = display_name("PD Video Get Frame")
    DESCRIPTION = (
        "Grab one frame from a VIDEO. Only the needed frame is decoded "
        "(seeks to the nearest keyframe). Negative index counts from the end."
    )
    CATEGORY = _CATEGORY
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "MASK", "INT", "INT", "FLOAT")
    RETURN_NAMES = ("image", "mask", "frame_index", "frame_count", "fps")
    OUTPUT_TOOLTIPS = (
        "The frame, float32 RGB.",
        _MASK_TOOLTIP,
        "Index of the frame that was used.",
        "Frame count (exact for last / negative indices).",
        "Source frame rate.",
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("VIDEO",),
                "mode": (_MODES, {"default": "first", "tooltip": _MODE_TOOLTIP}),
                "index": ("INT", {
                    "default": 0, "min": -_INT_MAX, "max": _INT_MAX,
                    "tooltip": _INDEX_TOOLTIP,
                }),
            },
        }

    def execute(self, video, mode, index):
        image, mask, frame_index, count, fps = read_frame(video, mode, index)
        return (image, mask, frame_index, count, fps)


class PDImageFromBatch:
    """Pick a single image (first, last or by index) from an IMAGE batch, with its mask."""

    DISPLAY_NAME = display_name("PD Image From Batch")
    DESCRIPTION = (
        "Pick one image from a batch: first, last or by index. "
        "Negative index counts from the end (-1 = last). The mask output "
        "picks the same frame."
    )
    CATEGORY = _CATEGORY
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "MASK", "INT", "INT")
    RETURN_NAMES = ("image", "mask", "frame_index", "frame_count")
    OUTPUT_TOOLTIPS = (
        "The picked image.",
        "The same frame of 'mask' (a single-frame mask is used for every frame). "
        "Without a mask: channel 4 of RGBA images, else full opacity. 1.0 = opaque.",
        "Index of the image that was used.",
        "Number of images in the batch.",
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "mode": (_MODES, {"default": "first", "tooltip": _MODE_TOOLTIP}),
                "index": ("INT", {
                    "default": 0, "min": -_INT_MAX, "max": _INT_MAX,
                    "tooltip": _INDEX_TOOLTIP,
                }),
            },
            "optional": {
                "mask": ("MASK", {
                    "tooltip": "Optional alpha to pick the same frame from (1.0 = opaque). "
                               "One frame, or as many frames as 'images'.",
                }),
            },
        }

    def execute(self, images, mode, index, mask=None):
        count = int(images.shape[0])
        idx = resolve_index(mode, index, count)
        return (images[idx:idx + 1], pick_mask(images, idx, mask), idx, count)


def pick_mask(images, idx: int, mask=None):
    """
    Return the ``1xHxW`` mask for image *idx* of *images*.

    A given *mask* (``NxHxW`` or ``HxW``) must have one frame (used for
    every image) or one per image.  Without one, channel 4 of RGBA images
    is used, else full opacity.
    """
    import torch

    if mask is None:
        if images.shape[-1] == 4:
            return images[idx:idx + 1, ..., 3]
        return torch.ones((1, *images.shape[1:3]), dtype=torch.float32, device=images.device)
    if mask.dim() == 2:
        mask = mask.unsqueeze(0)
    frames = int(mask.shape[0])
    if frames == 1:
        return mask
    if frames != int(images.shape[0]):
        raise ValueError(
            f"[Pipedream] PD Image From Batch: mask has {frames} frames but images has "
            f"{int(images.shape[0])}. Connect a mask with one frame or one per image."
        )
    return mask[idx:idx + 1]
