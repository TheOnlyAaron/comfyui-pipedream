"""
Display name helper for Pipedream nodes.

Provides an emoji prefix for node display names with a safe fallback
for terminals that cannot encode emoji (e.g. Windows cp1252/cp932).
"""

import sys

_EMOJI_PREFIX = "\U0001F4AD "  # 💭

try:
    _EMOJI_PREFIX.encode(sys.stdout.encoding or "utf-8")
except (UnicodeEncodeError, LookupError):
    _EMOJI_PREFIX = ""


def display_name(base: str) -> str:
    """Return *base* with the Pipedream emoji prefix (when supported)."""
    return f"{_EMOJI_PREFIX}{base}" if _EMOJI_PREFIX else base
