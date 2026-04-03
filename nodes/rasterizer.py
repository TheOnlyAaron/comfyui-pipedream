"""
PD Rasterizer node.

Dry-run inspection node that connects to PD Wedge nodes and optionally a
PD Output Namer.  Computes the cartesian product of all connected wedges
and displays an iteration preview table.
"""

import itertools
import sys

from ..core.tokens import resolve_tokens


_MAX_PREVIEW_LINES = 50


class PDRasterizer:
    """Preview wedge iteration table without running a full render."""

    DISPLAY_NAME = "PD Rasterizer"
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    RETURN_TYPES = ("INT", "STRING")
    RETURN_NAMES = ("total_iterations", "preview_table")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "wedge_1": ("WEDGE",),
                "wedge_2": ("WEDGE",),
                "wedge_3": ("WEDGE",),
                "wedge_4": ("WEDGE",),
                "output_namer": ("STRING", {"forceInput": True}),
            },
        }

    def execute(self, wedge_1=None, wedge_2=None, wedge_3=None, wedge_4=None,
                output_namer=None):
        wedges = [w for w in (wedge_1, wedge_2, wedge_3, wedge_4) if w is not None]

        if not wedges:
            return (0, "No wedges connected.")

        # Header
        lines: list[str] = []
        for w in wedges:
            name = w.get("name", "?")
            count = len(w.get("values", []))
            lines.append(f"Wedge: {name:<16} \u2192 {count} values")

        lines.append("\u2500" * 40)

        # Cartesian product
        value_lists = [w.get("values", [""]) for w in wedges]
        product = list(itertools.product(*value_lists))
        total = len(product)
        lines.append(f"Total iterations:    {total}")

        # Filename preview
        if output_namer and product:
            lines.append("")
            wedge_names = [w.get("name", f"w{i}") for i, w in enumerate(wedges)]
            shown = min(total, _MAX_PREVIEW_LINES)

            for idx, combo in enumerate(product[:shown]):
                ctx: dict = {"wedge_idx": str(idx).zfill(3)}
                for wname, val in zip(wedge_names, combo):
                    ctx[f"wedge_{wname}"] = str(val)

                # Resolve the namer template with wedge context injected
                preview = resolve_tokens(output_namer, ctx)
                lines.append(f"  [{idx:03d}] {preview}")

            if total > shown:
                lines.append(f"  ... and {total - shown} more")

        preview_table = "\n".join(lines)
        return (total, preview_table)
