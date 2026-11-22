"""
PD OCIO nodes: OpenColorIO colorspace and display/view transforms.

The dropdowns list the default config ($OCIO, else the built-in ACES studio
config) when ComfyUI loads; the frontend (web/pd_ocio.js) swaps in the
selected config's names through ``GET /pipedream/ocio/options``.  Because
the names depend on the selected config, ``VALIDATE_INPUTS`` takes over
validation of those inputs from ComfyUI's fixed combo-list check.
"""

from functools import partial

import torch

from ..core import ocio, settings
from ..core.common import display_name

_CATEGORY = "Pipedream/Color"

_CONFIG_TOOLTIP = (
    "OCIO config. '$OCIO environment' uses the config in the OCIO environment "
    "variable, or the built-in ACES studio config when it is unset."
)
_PATH_TOOLTIP = "Path to a config.ocio file. Used only when config is 'custom file'."


def _config_inputs():
    return {
        "config": (ocio.CONFIG_CHOICES, {"default": settings.get("ocio.config"),
                                         "tooltip": _CONFIG_TOOLTIP}),
        "config_path": ("STRING", {"default": settings.get("ocio.config_path"),
                                   "tooltip": _PATH_TOOLTIP}),
    }


def _combo(values, default, tooltip):
    values = list(values) or [default]
    return (values, {"default": default if default in values else values[0], "tooltip": tooltip})


def _apply(cpu, image: torch.Tensor) -> torch.Tensor:
    """Run a CPU processor over an IMAGE tensor's RGB channels."""
    pixels = image.detach().cpu().numpy()
    out = ocio.apply_rgb(cpu, pixels)
    return torch.from_numpy(out).to(device=image.device, dtype=image.dtype)


def _run(build, image):
    """Build a processor and apply it, turning config/name errors into readable ones."""
    try:
        cpu = build()
    except ocio.OCIOUnavailable:
        raise
    except Exception as exc:
        raise ValueError(f"OCIO: {exc}") from exc
    return _apply(cpu, image)


class PDOCIOTransform:
    """Convert images between two colorspaces of an OCIO config, optionally through a look."""

    DISPLAY_NAME = display_name("PD OCIO Transform")
    DESCRIPTION = (
        "Convert an image from one OpenColorIO colorspace to another, optionally "
        "applying a look. Values outside 0-1 are kept and alpha passes through."
    )
    CATEGORY = _CATEGORY
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def INPUT_TYPES(cls):
        opts = ocio.default_options()
        defaults = opts["defaults"]
        return {
            "required": {
                "image": ("IMAGE",),
                **_config_inputs(),
                "in_colorspace": _combo(opts["colorspaces"], defaults["in_colorspace"],
                                        "Colorspace of the incoming image."),
                "out_colorspace": _combo(opts["colorspaces"], defaults["out_colorspace"],
                                         "Colorspace to convert to."),
            },
            "optional": {
                "look": _combo([ocio.NO_LOOK, *opts["looks"]], ocio.NO_LOOK,
                               "Optional look from the config, applied between the colorspaces."),
                "inverse_look": ("BOOLEAN", {"default": False,
                                             "tooltip": "Apply the inverse of the look."}),
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, config=None, config_path="", in_colorspace=None,
                        out_colorspace=None, look=None):
        if config is None:
            return True
        return ocio.check_names(config, config_path or "",
                                colorspaces=(in_colorspace, out_colorspace), look=look)

    def execute(self, image, config, config_path, in_colorspace, out_colorspace,
                look=ocio.NO_LOOK, inverse_look=False):
        build = partial(ocio.colorspace_processor, config, config_path,
                        in_colorspace, out_colorspace, look, inverse_look)
        return (_run(build, image),)


class PDOCIODisplay:
    """Apply an OCIO display/view transform (e.g. ACES output transform) to images."""

    DISPLAY_NAME = display_name("PD OCIO Display")
    DESCRIPTION = (
        "Apply an OpenColorIO display/view transform, e.g. scene-linear ACEScg to "
        "sRGB with the ACES output transform. 'inverse' converts display images "
        "back to the scene colorspace. Alpha passes through."
    )
    CATEGORY = _CATEGORY
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def INPUT_TYPES(cls):
        opts = ocio.default_options()
        defaults = opts["defaults"]
        all_views = list(dict.fromkeys(v for views in opts["views"].values() for v in views))
        return {
            "required": {
                "image": ("IMAGE",),
                **_config_inputs(),
                "in_colorspace": _combo(opts["colorspaces"], defaults["in_colorspace"],
                                        "Scene colorspace of the incoming image."),
                "display": _combo(opts["displays"], defaults["display"], "Display device."),
                "view": _combo(all_views, defaults["view"],
                               "View (rendering) for the display. The list follows the display."),
                "inverse": ("BOOLEAN", {"default": False,
                                        "tooltip": "Convert from the display/view back to in_colorspace."}),
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, config=None, config_path="", in_colorspace=None,
                        display=None, view=None):
        if config is None:
            return True
        return ocio.check_names(config, config_path or "", colorspaces=(in_colorspace,),
                                display=display, view=view)

    def execute(self, image, config, config_path, in_colorspace, display, view, inverse=False):
        build = partial(ocio.display_processor, config, config_path,
                        in_colorspace, display, view, inverse)
        return (_run(build, image),)


def _register_routes():
    """Add ``GET /pipedream/ocio/options`` (the frontend's dropdown source) when the server is up."""
    try:
        from aiohttp import web
        from server import PromptServer
        routes = PromptServer.instance.routes
    except Exception:
        return

    @routes.get("/pipedream/ocio/options")
    async def ocio_options(request):
        config = request.query.get("config", ocio.CONFIG_ENV)
        path = request.query.get("path", "")
        try:
            return web.json_response(ocio.options(config, path))
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=400)


_register_routes()
