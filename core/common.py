"""
Small helpers shared by every Pipedream node module.

``display_name`` adds the 💭 prefix to node display names, falling back to
no prefix on consoles that cannot encode emoji (e.g. Windows cp1252/cp932).
``ANY`` is the wildcard socket type used by PD Switch and PD Sound.
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


class AnyType(str):
    """Wildcard type string that matches every socket type.

    ``__ne__`` always returning False makes ComfyUI's type check
    (``received_type != input_type``) accept any connection.
    """

    def __ne__(self, other):
        return False

    __hash__ = str.__hash__


ANY = AnyType("*")
