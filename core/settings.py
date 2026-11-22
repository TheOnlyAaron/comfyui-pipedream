"""
Facility and user defaults for Pipedream, read from TOML files.

Precedence, lowest to highest:

1. built-in defaults (:data:`SCHEMA`)
2. user file: ``pipedream.toml`` in the pack root (:data:`USER_PATH`)
3. facility file: the path in the ``PIPEDREAM_COMFYUI_CONFIG`` environment variable

A key overrides only when it is present and valid; missing keys fall
through.  Invalid values, unknown keys, unreadable files and TOML syntax
errors print one console warning each and are ignored.  Files are read once
when ComfyUI imports the pack, so changes need a restart.

API::

    from ..core import settings
    settings.get("output.format")      # "png" unless overridden
    settings.sources                    # [{"scope": "facility", "path": ...}, ...]
    settings.summary()                  # "settings: facility //nas/pd.toml, user (none)"

The schema also generates ``pipedream.example.toml``::

    python -m core.settings > pipedream.example.toml
"""

import math
import os
import re
import sys
import textwrap
from dataclasses import dataclass
from datetime import datetime

from .common import PLAY_WHEN, SOUNDS
from .media import (
    EXR_COLORSPACES,
    EXR_COMPRESSIONS,
    EXR_PRECISIONS,
    IMAGE_FORMATS,
    PATH_MODES,
    PRORES_CHOICES,
    VIDEO_FORMATS,
)
from .ocio import CONFIG_CHOICES, CONFIG_ENV

try:
    import tomllib as _toml
except ImportError:
    try:
        import tomli as _toml  # type: ignore[import-not-found, no-redef]
    except ImportError:
        _toml = None

ENV_VAR = "PIPEDREAM_COMFYUI_CONFIG"
USER_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipedream.toml")
EXTRA_KEY = "tokens.extra"
RESERVED_TOKENS = ("frame",)
# Built-in templates written with {}, rewritten to the configured delimiters when not set.
TEMPLATE_KEYS = ("output.template", "shot_token.template")

_TOKEN_NAME = re.compile(r"^\w+$")


@dataclass(frozen=True)
class Setting:
    """One setting: its type, built-in default, allowed values and description."""

    type: type
    default: object
    description: str
    choices: tuple = ()
    min: float | None = None
    max: float | None = None
    check: object = None


def _strftime(value):
    try:
        out = datetime(2001, 2, 3, 4, 5, 6).strftime(value)
    except (ValueError, TypeError) as exc:
        return f"not a valid strftime format ({exc})"
    return None if out else "format produces an empty string"


def _delimiter(value):
    if not value:
        return "must not be empty"
    if re.search(r"[\w\s]", value):
        return "must not contain letters, digits, '_' or whitespace"
    return None


def _not_empty(value):
    return None if value.strip() else "must not be empty"


SCHEMA: dict[str, Setting] = {
    "output.template": Setting(
        str, "{project}/{sequence}/{shot}/{shot}_{version}_{date}",
        "PD Output path template, without extension.", check=_not_empty),
    "output.path_mode": Setting(
        str, "relative", "PD Output: relative (ComfyUI output dir) or absolute (base_path).",
        choices=PATH_MODES),
    "output.base_path": Setting(
        str, "", "PD Output root folder for absolute mode, e.g. a facility network root. "
        "UNC works: '\\\\server\\shows' (single quotes keep backslashes) or '//server/shows'."),
    "output.format": Setting(
        str, "png", "PD Output file format.", choices=IMAGE_FORMATS + VIDEO_FORMATS),
    "output.fps": Setting(
        float, 24.0, "Video frame rate (PD Output, PD Images To Video).", min=1.0, max=240.0),
    "output.crf": Setting(int, 18, "mp4/webm quality, lower is better.", min=0, max=51),
    "output.create_dirs": Setting(bool, True, "Create missing output folders."),
    "output.overwrite": Setting(bool, False, "Replace existing files."),
    "output.save_metadata": Setting(bool, True, "Write a sidecar .json next to the output."),
    "output.prores_profile": Setting(
        str, "auto", "mov only: auto (4444 with alpha, else 422 HQ), 422 HQ or 4444.",
        choices=PRORES_CHOICES),
    "exr.precision": Setting(str, "half", "EXR float precision.", choices=EXR_PRECISIONS),
    "exr.compression": Setting(str, "zip", "EXR compression.", choices=EXR_COMPRESSIONS),
    "exr.colorspace": Setting(
        str, "as is", "EXR: write values as is, or decode sRGB to linear.",
        choices=EXR_COLORSPACES),
    "sequence.frame_padding": Setting(
        int, 4, "Digits in frame numbers (PD Output, PD Shot Token, PD Rasterizer).",
        min=1, max=8),
    "sequence.start_frame": Setting(int, 1001, "First frame number of an image sequence.",
                                    min=0, max=9999999),
    "sequence.frame_separator": Setting(
        str, ".", "Separator before the frame number when the template has no frame "
        "token (name.1001.exr).", choices=(".", "_", "-")),
    "tokens.open": Setting(str, "{", "Token opening delimiter. The built-in templates "
                           "follow the delimiters unless set.", check=_delimiter),
    "tokens.close": Setting(str, "}", "Token closing delimiter (must differ from open).",
                            check=_delimiter),
    "tokens.date_format": Setting(str, "%Y%m%d", "strftime format of the date token.",
                                  check=_strftime),
    "tokens.time_format": Setting(str, "%H%M%S", "strftime format of the time token.",
                                  check=_strftime),
    EXTRA_KEY: Setting(
        dict, {}, "Fixed tokens available to every template; context values override "
        "them. Values are strings or numbers. 'frame' is reserved."),
    "shot_token.template": Setting(str, "{project}_{shot}_{version}",
                                   "PD Shot Token default template."),
    "project.version": Setting(str, "v001", "PD Project Context default version.",
                               check=_not_empty),
    "project.auto_increment_version": Setting(
        bool, False, "PD Project Context: bump the version after each queue."),
    "ocio.config": Setting(str, CONFIG_ENV, "OCIO config choice.", choices=tuple(CONFIG_CHOICES)),
    "ocio.config_path": Setting(str, "", "config.ocio path, used when config is 'custom file'."),
    "ocio.in_colorspace": Setting(
        str, "", "Default input colorspace. Empty: the config's default (ACEScg or "
        "scene_linear). Names not in the config fall back to that default."),
    "ocio.out_colorspace": Setting(
        str, "", "PD OCIO Transform default output colorspace. Empty: sRGB - Texture or "
        "the color_picking role."),
    "ocio.display": Setting(str, "", "PD OCIO Display default display. Empty: the "
                            "config's default display."),
    "ocio.view": Setting(str, "", "PD OCIO Display default view. Empty: the display's "
                         "default view."),
    "sound.sound": Setting(str, "chime", "PD Sound default sound.", choices=tuple(SOUNDS)),
    "sound.volume": Setting(float, 0.6, "PD Sound default volume.", min=0.0, max=1.0),
    "sound.play_when": Setting(str, "node reached", "PD Sound default trigger.",
                               choices=tuple(PLAY_WHEN)),
}

_TABLES = tuple(dict.fromkeys(k.split(".")[0] for k in SCHEMA))

_values: dict = {}
sources: list[dict] = []
warnings: list[str] = []


def _warn(message: str) -> None:
    warnings.append(message)
    print(f"[Pipedream] Settings warning: {message}", file=sys.stderr)


def _type_name(t) -> str:
    return {str: "a string", int: "an integer", float: "a number", bool: "true or false",
            dict: "a table"}[t]


def validate(key: str, value):
    """
    Check *value* for setting *key*.

    Returns ``(value, None)`` with the value coerced to the setting's type
    (an integer for a float setting becomes a float), or ``(None, problem)``.
    """
    spec = SCHEMA[key]
    if key == EXTRA_KEY:
        return value, None
    if spec.type is float and isinstance(value, int) and not isinstance(value, bool):
        value = float(value)
    if not isinstance(value, spec.type) or (spec.type is int and isinstance(value, bool)):
        return None, f"expected {_type_name(spec.type)}, got {value!r}"
    if isinstance(value, float) and math.isnan(value):
        return None, "expected a number, got nan"
    if spec.choices and value not in spec.choices:
        allowed = ", ".join(repr(c) for c in spec.choices)
        return None, f"{value!r} is not one of {allowed}"
    if spec.min is not None and value < spec.min or spec.max is not None and value > spec.max:
        return None, f"{value!r} is outside {spec.min}..{spec.max}"
    if spec.check:
        problem = spec.check(value)
        if problem:
            return None, f"{value!r}: {problem}"
    return value, None


def _extra_tokens(path: str, table) -> dict:
    """Validate a ``[tokens.extra]`` table; returns the valid tokens as strings."""
    out = {}
    for name, value in table.items():
        where = f"{path}: {EXTRA_KEY}.{name}"
        if not _TOKEN_NAME.match(name):
            _warn(f"{where}: token names may only use letters, digits and '_'; ignored.")
        elif name in RESERVED_TOKENS:
            _warn(f"{where}: '{name}' is reserved; ignored.")
        elif isinstance(value, bool) or not isinstance(value, (str, int, float)):
            _warn(f"{where}: expected a string or number, got {value!r}; ignored.")
        else:
            out[name] = str(value)
    return out


def _read(path: str):
    """Parse a TOML file; returns a dict, or None after a warning."""
    if _toml is None:
        _warn(f"{path}: cannot read TOML (needs Python 3.11+ or the 'tomli' package); "
              "using built-in defaults.")
        return None
    try:
        with open(path, "rb") as fh:
            return _toml.load(fh)
    except OSError as exc:
        _warn(f"{path}: cannot read file ({exc.strerror or exc}); ignored.")
    except Exception as exc:
        _warn(f"{path}: invalid TOML ({exc}); file ignored.")
    return None


def _apply(path: str, data: dict, values: dict, given: set) -> None:
    """Merge the valid keys of parsed file *data* into *values*, warning about the rest."""
    for table, entries in data.items():
        if table not in _TABLES:
            _warn(f"{path}: unknown table or key '{table}'; ignored.")
            continue
        if not isinstance(entries, dict):
            _warn(f"{path}: '{table}' must be a table ([{table}]); ignored.")
            continue
        for name, value in entries.items():
            key = f"{table}.{name}"
            if key not in SCHEMA:
                _warn(f"{path}: unknown key '{key}'; ignored.")
            elif key == EXTRA_KEY:
                if isinstance(value, dict):
                    values[EXTRA_KEY] = {**values[EXTRA_KEY], **_extra_tokens(path, value)}
                else:
                    _warn(f"{path}: '{key}' must be a table ([{key}]); ignored.")
            else:
                checked, problem = validate(key, value)
                if problem:
                    _warn(f"{path}: {key}: {problem}; using {values[key]!r}.")
                else:
                    values[key] = checked
                    given.add(key)


def load(user_path: str | None = USER_PATH, facility_path: str | None = None) -> None:
    """
    (Re)load the settings: built-ins, then *user_path*, then *facility_path*.

    *facility_path* defaults to ``$PIPEDREAM_COMFYUI_CONFIG``.  A missing user file
    is silently skipped; a missing facility file warns.  Updates the
    module-level values, :data:`sources` and :data:`warnings` in place.
    """
    if facility_path is None:
        facility_path = os.environ.get(ENV_VAR, "").strip().strip('"')
    values = {k: (dict(s.default) if isinstance(s.default, dict) else s.default)
              for k, s in SCHEMA.items()}
    warnings.clear()
    loaded, given = [], set()
    for scope, path in (("user", user_path), ("facility", facility_path)):
        if not path:
            continue
        path = os.path.expanduser(path)
        if scope == "user" and not os.path.exists(path):
            continue
        data = _read(path)
        if data is not None:
            _apply(path, data, values, given)
            loaded.append({"scope": scope, "path": path})
    if values["tokens.open"] == values["tokens.close"]:
        _warn(f"tokens.open and tokens.close are both {values['tokens.open']!r}; "
              "using the built-in '{' and '}'.")
        values["tokens.open"] = SCHEMA["tokens.open"].default
        values["tokens.close"] = SCHEMA["tokens.close"].default
    open_, close = values["tokens.open"], values["tokens.close"]
    for key in TEMPLATE_KEYS:
        if key not in given:
            values[key] = re.sub(r"\{(\w+)\}", lambda m: f"{open_}{m.group(1)}{close}",
                                 SCHEMA[key].default)
    _values.clear()
    _values.update(values)
    sources[:] = loaded


def get(key: str):
    """Return the effective value of setting *key* (e.g. ``"output.format"``)."""
    value = _values[key]
    return dict(value) if isinstance(value, dict) else value


def summary() -> str:
    """One line naming the loaded files, e.g. ``settings: facility /p/pd.toml, user (none)``."""
    paths = {s["scope"]: s["path"] for s in sources}
    parts = [f"{scope} {paths.get(scope, '(none)')}" for scope in ("facility", "user")]
    return "settings: " + ", ".join(parts)


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return repr(value)


def example_toml() -> str:
    """Return the fully commented example file, with every key at its built-in default."""
    lines = [
        "# Pipedream facility / user defaults.",
        "#",
        "# Copy to pipedream.toml in the pack folder (user), or point the",
        f"# {ENV_VAR} environment variable at a copy (facility; wins over user).",
        "# Every key is optional: uncomment and edit only what you want to change.",
        "# New nodes get these defaults; saved workflows keep their values.",
        "# Restart ComfyUI after editing.",
        "#",
        "# Generated from core/settings.py: python -m core.settings > pipedream.example.toml",
    ]
    table = None
    for key, spec in SCHEMA.items():
        if key == EXTRA_KEY:
            lines += ["", *textwrap.wrap(spec.description, 78, initial_indent="# ",
                                         subsequent_indent="# "), f"# [{EXTRA_KEY}]",
                      '# facility = "MAKE"', '# show_root = "//nas/shows"']
            continue
        section, name = key.split(".", 1)
        if section != table:
            table = section
            lines += ["", f"[{section}]"]
        else:
            lines.append("")
        note = spec.description
        if spec.choices:
            note += " One of: " + ", ".join(_toml_value(c) for c in spec.choices) + "."
        elif spec.min is not None:
            note += f" Range {spec.min}..{spec.max}."
        lines += textwrap.wrap(note, 78, initial_indent="# ", subsequent_indent="# ",
                               break_on_hyphens=False, break_long_words=False)
        lines.append(f"# {name} = {_toml_value(spec.default)}")
    return "\n".join(lines) + "\n"


load()

if __name__ == "__main__":
    sys.stdout.write(example_toml())
