"""
OpenColorIO helpers for the PD OCIO nodes.

``PyOpenColorIO`` (PyPI: ``opencolorio``) is imported lazily so the nodes
still register when it is missing; anything that needs it raises
:class:`OCIOUnavailable` with install instructions instead.

Configs are chosen with a ``config`` combo (:data:`CONFIG_CHOICES`) plus a
``config_path`` string used only for ``"custom file"``.  Loaded configs and
CPU processors are cached; file-based configs are keyed by path and
modification time, so an edited config file is picked up on the next run.

Default choices (config, colorspaces, display, view) can be set in the
``[ocio]`` settings table (``core/settings.py``).
"""

import os
import sys
import threading


CONFIG_ENV = "$OCIO environment"
CONFIG_STUDIO = "ACES studio (built-in)"
CONFIG_CG = "ACES cg (built-in)"
CONFIG_CUSTOM = "custom file"
CONFIG_CHOICES = [CONFIG_ENV, CONFIG_STUDIO, CONFIG_CG, CONFIG_CUSTOM]

BUILTIN_URIS = {
    CONFIG_STUDIO: "ocio://studio-config-latest",
    CONFIG_CG: "ocio://cg-config-latest",
}

NO_LOOK = "none"

# Shown in the dropdowns when PyOpenColorIO is missing, so the nodes still load.
FALLBACK_OPTIONS = {
    "colorspaces": ["ACEScg", "sRGB Encoded Rec.709 (sRGB)"],
    "families": {},
    "aliases": {},
    "displays": ["sRGB - Display"],
    "views": {"sRGB - Display": ["ACES 2.0 - SDR 100 nits (Rec.709)"]},
    "default_views": {"sRGB - Display": "ACES 2.0 - SDR 100 nits (Rec.709)"},
    "looks": [],
    "roles": {},
    "defaults": {
        "in_colorspace": "ACEScg",
        "out_colorspace": "sRGB Encoded Rec.709 (sRGB)",
        "display": "sRGB - Display",
        "view": "ACES 2.0 - SDR 100 nits (Rec.709)",
    },
}

_INSTALL_HINT = (
    "PD OCIO nodes need OpenColorIO. Install it into ComfyUI's Python, e.g. "
    "`python -m pip install opencolorio` (portable Windows builds: "
    "`python_embeded\\python.exe -m pip install opencolorio`), then restart ComfyUI."
)

_warned: set = set()
_lock = threading.Lock()
_configs: dict = {}
_processors: dict = {}
_MAX_PROCESSORS = 64


class OCIOUnavailable(RuntimeError):
    """Raised when PyOpenColorIO cannot be imported."""


def ocio():
    """Return the ``PyOpenColorIO`` module or raise :class:`OCIOUnavailable`."""
    try:
        import PyOpenColorIO
    except ImportError as exc:
        raise OCIOUnavailable(f"{_INSTALL_HINT} ({exc})") from exc
    return PyOpenColorIO


def available() -> bool:
    """True when PyOpenColorIO can be imported."""
    try:
        ocio()
    except OCIOUnavailable:
        return False
    return True


def _source(config: str, config_path: str = "") -> str:
    """Resolve a config choice to the file path or ``ocio://`` URI to load."""
    if config == CONFIG_ENV:
        env = os.environ.get("OCIO", "").strip()
        return env or BUILTIN_URIS[CONFIG_STUDIO]
    if config in BUILTIN_URIS:
        return BUILTIN_URIS[config]
    if config == CONFIG_CUSTOM:
        path = os.path.expanduser((config_path or "").strip().strip('"'))
        if not path:
            raise ValueError("config is 'custom file' but config_path is empty.")
        if not os.path.isfile(path):
            raise ValueError(f"OCIO config file not found: {path}")
        return path
    raise ValueError(f"Unknown OCIO config choice: {config!r}")


def load_config(config: str, config_path: str = ""):
    """Load (or fetch from cache) the OCIO config for a config choice.

    Returns ``(config_object, cache_key)``.  Raises :class:`ValueError` for a
    bad choice or path, or with OCIO's message when the config fails to load.
    """
    OCIO = ocio()
    source = _source(config, config_path)
    try:
        mtime = os.path.getmtime(source) if not source.startswith("ocio://") else 0
    except OSError:
        mtime = 0
    key = (source, mtime)
    with _lock:
        cfg = _configs.get(key)
        if cfg is None:
            try:
                cfg = OCIO.Config.CreateFromFile(source)
            except Exception as exc:
                raise ValueError(f"Could not load OCIO config '{source}': {exc}") from exc
            for stale in [k for k in _configs if k[0] == source]:
                del _configs[stale]
            _configs[key] = cfg
    return cfg, key


def _first(cfg, candidates, names):
    """First candidate (colorspace or role name) that resolves in ``cfg``, as its canonical name."""
    for name in candidates:
        if not name:
            continue
        cs = cfg.getColorSpace(name)
        if cs is not None and cs.getName() in names:
            return cs.getName()
    return names[0] if names else ""


def options(config: str, config_path: str = "") -> dict:
    """Describe a config for the dropdowns.

    Returns colorspace names (config order), the same grouped by family,
    alias → name, displays, views and default view per display, look names,
    roles and sensible defaults.
    """
    OCIO = ocio()
    cfg, _ = load_config(config, config_path)
    colorspaces, families, aliases = [], {}, {}
    for cs in cfg.getColorSpaces():
        name = cs.getName()
        colorspaces.append(name)
        families.setdefault(cs.getFamily() or "Other", []).append(name)
        aliases.update((alias, name) for alias in cs.getAliases())
    displays = list(cfg.getDisplays())
    views = {d: list(cfg.getViews(d)) for d in displays}
    pref = _preferred()
    default_display = cfg.getDefaultDisplay() or (displays[0] if displays else "")
    if pref["display"] in displays:
        default_display = pref["display"]
    default_view = cfg.getDefaultView(default_display) if default_display else ""
    if pref["view"] in views.get(default_display, ()):
        default_view = pref["view"]
    return {
        "colorspaces": colorspaces,
        "families": families,
        "aliases": aliases,
        "displays": displays,
        "views": views,
        "default_views": {d: cfg.getDefaultView(d) for d in displays},
        "looks": [look.getName() for look in cfg.getLooks()],
        "roles": dict(cfg.getRoles()),
        "defaults": {
            "in_colorspace": _first(
                cfg, [pref["in_colorspace"], "ACEScg", OCIO.ROLE_SCENE_LINEAR], colorspaces),
            "out_colorspace": _first(
                cfg,
                [pref["out_colorspace"], "sRGB - Texture", OCIO.ROLE_COLOR_PICKING,
                 OCIO.ROLE_TEXTURE_PAINT, OCIO.ROLE_MATTE_PAINT],
                colorspaces,
            ),
            "display": default_display,
            "view": default_view,
        },
    }


def _preferred() -> dict:
    """The ``[ocio]`` default names from the settings (empty string = config default)."""
    from . import settings
    return {k: settings.get(f"ocio.{k}")
            for k in ("in_colorspace", "out_colorspace", "display", "view")}


def _warn_once(message: str) -> None:
    if message not in _warned:
        _warned.add(message)
        print(f"[Pipedream] Settings warning: {message}", file=sys.stderr)


def default_options() -> dict:
    """Options of the default config: the ``ocio.config`` setting, else $OCIO.

    $OCIO falls back to the built-in studio config.  Configured default
    names that the config lacks warn once and use the config's defaults.
    Falls back to :data:`FALLBACK_OPTIONS` when OCIO is missing or the
    config cannot be loaded, so ``INPUT_TYPES`` never fails.
    """
    from . import settings
    config, path = settings.get("ocio.config"), settings.get("ocio.config_path")
    opts = None
    if config != CONFIG_ENV:
        try:
            opts = options(config, path)
        except OCIOUnavailable:
            return FALLBACK_OPTIONS
        except Exception as exc:
            _warn_once(f"ocio.config {config!r}: {exc}; listing the $OCIO config instead.")
    if opts is None:
        try:
            opts = options(CONFIG_ENV)
        except Exception:
            return FALLBACK_OPTIONS
    known = {*opts["colorspaces"], *opts["aliases"], *opts["roles"]}
    for key, value in _preferred().items():
        listed = known if key.endswith("colorspace") else (
            opts["displays"] if key == "display" else {v for vs in opts["views"].values() for v in vs})
        if value and value not in listed:
            _warn_once(f"ocio.{key} {value!r} is not in the default OCIO config; "
                       f"using {opts['defaults'][key]!r}.")
    return opts


def check_names(config: str, config_path: str = "", colorspaces=(), display=None,
                view=None, look=None):
    """Check names against the selected config.

    Returns ``True`` or an error message suitable for ``VALIDATE_INPUTS``.
    Colorspace names may be canonical names, aliases or roles.
    """
    if config not in CONFIG_CHOICES:
        return f"Unknown config {config!r}; expected one of {CONFIG_CHOICES}."
    try:
        cfg, _ = load_config(config, config_path)
    except OCIOUnavailable as exc:
        return str(exc)
    except ValueError as exc:
        return str(exc)
    label = config if config != CONFIG_CUSTOM else config_path
    for name in colorspaces:
        if name is not None and cfg.getColorSpace(name) is None:
            return f"Colorspace '{name}' is not in OCIO config '{label}'."
    if display is not None:
        if display not in cfg.getDisplays():
            return f"Display '{display}' is not in OCIO config '{label}'."
        if view is not None and view not in cfg.getViews(display):
            return f"View '{view}' is not available for display '{display}' in OCIO config '{label}'."
    if look not in (None, "", NO_LOOK) and cfg.getLook(look) is None:
        return f"Look '{look}' is not in OCIO config '{label}'."
    return True


def _cpu_processor(cfg_key, cfg, params: tuple, build):
    """Cached default CPU processor for ``build()``'s transform, keyed by config and params."""
    key = (cfg_key, params)
    with _lock:
        cpu = _processors.get(key)
    if cpu is None:
        cpu = cfg.getProcessor(build()).getDefaultCPUProcessor()
        with _lock:
            if len(_processors) >= _MAX_PROCESSORS:
                _processors.pop(next(iter(_processors)))
            _processors[key] = cpu
    return cpu


def colorspace_processor(config, config_path, in_colorspace, out_colorspace,
                         look=NO_LOOK, inverse_look=False):
    """CPU processor converting ``in_colorspace`` to ``out_colorspace``.

    With a look (anything but ``"none"``) a LookTransform applies it on the
    way; ``inverse_look`` applies the look's inverse instead.
    """
    OCIO = ocio()
    cfg, cfg_key = load_config(config, config_path)
    use_look = look not in (None, "", NO_LOOK)

    def build():
        if use_look:
            return OCIO.LookTransform(
                src=in_colorspace, dst=out_colorspace,
                looks=("-" if inverse_look else "") + look,
            )
        return OCIO.ColorSpaceTransform(src=in_colorspace, dst=out_colorspace)

    params = ("cs", in_colorspace, out_colorspace, look if use_look else None,
              bool(inverse_look and use_look))
    return _cpu_processor(cfg_key, cfg, params, build)


def display_processor(config, config_path, in_colorspace, display, view, inverse=False):
    """CPU processor for a display/view transform (scene → display, or back with ``inverse``)."""
    OCIO = ocio()
    cfg, cfg_key = load_config(config, config_path)

    def build():
        direction = OCIO.TRANSFORM_DIR_INVERSE if inverse else OCIO.TRANSFORM_DIR_FORWARD
        return OCIO.DisplayViewTransform(
            src=in_colorspace, display=display, view=view, direction=direction,
        )

    return _cpu_processor(cfg_key, cfg, ("dv", in_colorspace, display, view, bool(inverse)), build)


def apply_rgb(cpu, pixels):
    """Apply a CPU processor to the RGB channels of an ``(..., C)`` float array.

    Works on a contiguous float32 copy, so values outside 0–1 are kept.
    Channels beyond the first three (alpha) are passed through untouched.
    """
    import numpy as np

    if pixels.shape[-1] < 3:
        raise ValueError(f"OCIO needs RGB images; got {pixels.shape[-1]} channel(s).")
    rgb = np.array(pixels[..., :3], dtype=np.float32, order="C", copy=True)
    cpu.applyRGB(rgb)
    if pixels.shape[-1] == 3:
        return rgb
    out = np.array(pixels, dtype=np.float32, copy=True)
    out[..., :3] = rgb
    return out
