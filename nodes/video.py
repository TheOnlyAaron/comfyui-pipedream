"""
PD video utility nodes.

Pipedream-owned counterparts to core ComfyUI's Create Video / Get Video
Components, plus single-frame pickers.  All nodes use the core ``VIDEO``
type so they interoperate with Load Video, Save Video and other packs.
Decoding helpers live in ``core/video.py``.
"""

from ..core.common import display_name
from ..core.video import images_to_video, read_frame, read_frames, resolve_index

_CATEGORY = "Pipedream/Video"
_MODES = ["first", "last", "index"]
_INT_MAX = 0x7FFFFFFF

_MODE_TOOLTIP = "first / last frame, or the frame at 'index'."
_INDEX_TOOLTIP = "Frame index used when mode is 'index'. Negative values count from the end (-1 = last)."


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
                    "default": 24.0, "min": 0.01, "max": 1000.0, "step": 0.001,
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
    RETURN_TYPES = ("IMAGE", "AUDIO", "FLOAT", "INT")
    RETURN_NAMES = ("images", "audio", "fps", "frame_count")

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
        images, audio, fps, count = read_frames(video, start_frame, frame_limit, step)
        return (images, audio, fps, count)


class PDVideoFrame:
    """Decode a single frame (first, last or by index) from a VIDEO."""

    DISPLAY_NAME = display_name("PD Video Frame")
    DESCRIPTION = (
        "Grab one frame from a VIDEO. Only the needed frame is decoded "
        "(seeks to the nearest keyframe). Negative index counts from the end."
    )
    CATEGORY = _CATEGORY
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "INT", "INT", "FLOAT")
    RETURN_NAMES = ("image", "frame_index", "frame_count", "fps")

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
        image, frame_index, count, fps = read_frame(video, mode, index)
        return (image, frame_index, count, fps)


class PDImageFrame:
    """Pick a single image (first, last or by index) from an IMAGE batch."""

    DISPLAY_NAME = display_name("PD Image Frame")
    DESCRIPTION = (
        "Pick one image from a batch: first, last or by index. "
        "Negative index counts from the end (-1 = last)."
    )
    CATEGORY = _CATEGORY
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "INT", "INT")
    RETURN_NAMES = ("image", "frame_index", "frame_count")

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
        }

    def execute(self, images, mode, index):
        count = int(images.shape[0])
        idx = resolve_index(mode, index, count)
        return (images[idx:idx + 1], idx, count)
