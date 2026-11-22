"""
Token resolution engine for Pipedream nodes.

Resolves template strings like '{project}/{shot}_{version}' against a context
dictionary.  The delimiters, the date/time formats and the fixed
``[tokens.extra]`` tokens come from :mod:`core.settings`.  No ComfyUI
dependency.
"""

import re
import sys
from datetime import datetime

from . import settings


def delimiters() -> tuple[str, str]:
    """Return the configured ``(open, close)`` token delimiters."""
    return settings.get("tokens.open"), settings.get("tokens.close")


def wrap(name: str, delims: tuple[str, str] | None = None) -> str:
    """Return token *name* with delimiters, e.g. ``{frame}``."""
    open_, close = delims or delimiters()
    return f"{open_}{name}{close}"


def auto_tokens(now: datetime | None = None) -> dict:
    """Return the automatic ``date`` and ``time`` tokens in the configured formats."""
    now = now or datetime.now()
    return {
        "date": now.strftime(settings.get("tokens.date_format")),
        "time": now.strftime(settings.get("tokens.time_format")),
    }


def with_extra(context: dict) -> dict:
    """Return *context* over the configured ``[tokens.extra]`` tokens."""
    return {**settings.get("tokens.extra"), **context}


def resolve_tokens(template: str, context: dict, frame_padding: int | None = None,
                   delims: tuple[str, str] | None = None) -> str:
    """
    Replace token placeholders (``{token}`` by default) in *template*.

    Values come from *context*, then the ``[tokens.extra]`` settings, then
    these automatic tokens:
        date    current date (``tokens.date_format``, default YYYYMMDD)
        time    current time (``tokens.time_format``, default HHMMSS)
        frame   '#' repeated *frame_padding* times (e.g. ``####``)

    *frame_padding* defaults to ``sequence.frame_padding``; *delims* to
    the ``tokens.open`` / ``tokens.close`` settings.  Wedge tokens
    (``wedge_idx``, ``wedge_<name>``) are ordinary context keys.  Unknown
    tokens are left as-is and a warning is printed to stderr.
    """
    open_, close = delims or delimiters()
    if frame_padding is None:
        frame_padding = settings.get("sequence.frame_padding")
    values = with_extra(context)
    auto = None

    def _replace(match: re.Match) -> str:
        nonlocal auto
        name = match.group(1)
        if name in values:
            return str(values[name])
        if name == "frame":
            return "#" * frame_padding
        if name in ("date", "time"):
            auto = auto or auto_tokens()
            return auto[name]
        print(f"[Pipedream] Warning: unknown token '{match.group(0)}' in template",
              file=sys.stderr)
        return match.group(0)

    pattern = re.escape(open_) + r"(\w+)" + re.escape(close)
    return re.sub(pattern, _replace, template)


def format_token_reference(context: dict, frame_padding: int | None = None,
                           frame_info: str | None = None) -> str:
    """
    Build a human-readable summary of available tokens and their current values.

    Lists *context*, then the ``[tokens.extra]`` settings it does not
    override, then the automatic tokens.  *frame_info* describes what the
    frame token resolved to (e.g. the written frame range); by default it
    shows the ``#`` placeholder.  The last line names the loaded settings
    files.
    """
    if frame_padding is None:
        frame_padding = settings.get("sequence.frame_padding")
    lines = ["Available tokens:"]

    for key, val in sorted(context.items()):
        lines.append(f"  {wrap(key):<18} = \"{val}\"")
    for key, val in sorted(settings.get("tokens.extra").items()):
        if key not in context:
            lines.append(f"  {wrap(key):<18} = \"{val}\" (settings)")

    auto = auto_tokens()
    for key in ("date", "time"):
        if key not in context and key not in settings.get("tokens.extra"):
            lines.append(f"  {wrap(key):<18} = {auto[key]} (auto)")
    lines.append(f"  {wrap('frame'):<18} = {frame_info or '#' * frame_padding + ' (auto)'}")
    lines.append(settings.summary())

    return "\n".join(lines)
