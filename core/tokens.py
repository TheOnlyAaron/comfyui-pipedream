"""
Token resolution engine for Pipedream nodes.

Resolves template strings like '{project}/{shot}_{version}' against a context
dictionary. Standalone module with no ComfyUI dependency.
"""

import re
import sys
from datetime import datetime


def resolve_tokens(template: str, context: dict, frame_padding: int = 4) -> str:
    """
    Replace ``{token}`` placeholders in *template* with values from *context*.

    Special tokens resolved automatically when absent from context:
        {date}          YYYYMMDD (current date)
        {time}          HHMMSS (current time)
        {frame}         '#' repeated *frame_padding* times (e.g. ``####``)

    Wedge tokens (``{wedge_idx}``, ``{wedge_<name>}``) are ordinary context
    keys.  Unknown tokens are left as-is and a warning is printed to stderr.
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

        # Unknown token — warn and leave in place
        print(
            f"[Pipedream] Warning: unknown token '{{{name}}}' in template",
            file=sys.stderr,
        )
        return match.group(0)

    return re.sub(r"\{(\w+)\}", _replace, template)


def format_token_reference(context: dict, frame_padding: int = 4,
                           frame_info: str | None = None) -> str:
    """
    Build a human-readable summary of available tokens and their current values.

    *frame_info* describes what ``{frame}`` resolved to (e.g. the written
    frame range); by default it shows the ``#`` placeholder.
    """
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
    lines.append(f"  {{frame}}           = {frame_info or '#' * frame_padding + ' (auto)'}")

    return "\n".join(lines)
