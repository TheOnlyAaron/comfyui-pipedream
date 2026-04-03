"""
Token resolution engine for Pipedream nodes.

Resolves template strings like '{project}/{shot}_{version}' against a context
dictionary. Standalone module with no ComfyUI dependency.
"""

import re
import sys
from datetime import datetime


def context_from_project(
    project: str = "",
    sequence: str = "",
    shot: str = "",
    version: str = "",
    artist: str = "",
) -> dict:
    """Build a context dict from project-level metadata fields."""
    ctx = {
        "project": project,
        "sequence": sequence,
        "shot": shot,
        "version": version,
    }
    if artist:
        ctx["artist"] = artist
    return ctx


def resolve_tokens(template: str, context: dict, frame_padding: int = 4) -> str:
    """
    Replace ``{token}`` placeholders in *template* with values from *context*.

    Special tokens resolved automatically when absent from context:
        {date}          YYYYMMDD (current date)
        {time}          HHMMSS (current time)
        {frame}         '#' repeated *frame_padding* times (e.g. ``####``)
        {wedge_idx}     current wedge iteration index (from context)
        {wedge_<name>}  named wedge value (looked up as ``wedge_<name>`` key)

    Unknown tokens are left as-is and a warning is printed to stderr.
    """
    now = datetime.now()

    def _replace(match: re.Match) -> str:
        name = match.group(1)

        # Explicit context value takes priority
        if name in context:
            return str(context[name])

        # Built-in auto-resolved tokens
        if name == "date":
            return now.strftime("%Y%m%d")
        if name == "time":
            return now.strftime("%H%M%S")
        if name == "frame":
            return "#" * frame_padding

        # Wedge tokens — look for 'wedge_<name>' key in context
        if name.startswith("wedge_"):
            wedge_key = name  # already prefixed
            if wedge_key in context:
                return str(context[wedge_key])

        # Unknown token — warn and leave in place
        print(
            f"[Pipedream] Warning: unknown token '{{{name}}}' in template",
            file=sys.stderr,
        )
        return match.group(0)

    return re.sub(r"\{(\w+)\}", _replace, template)


def format_token_reference(context: dict, frame_padding: int = 4) -> str:
    """Build a human-readable summary of available tokens and their current values."""
    now = datetime.now()
    lines = ["Available tokens:"]

    for key, val in sorted(context.items()):
        token = "{" + key + "}"
        lines.append(f"  {token:<18} = \"{val}\"")

    # Auto-resolved tokens (show current value)
    if "date" not in context:
        lines.append(f"  {{date}}            = {now.strftime('%Y%m%d')} (auto)")
    if "time" not in context:
        lines.append(f"  {{time}}            = {now.strftime('%H%M%S')} (auto)")
    lines.append(f"  {{frame}}           = {'#' * frame_padding} (auto)")

    return "\n".join(lines)
