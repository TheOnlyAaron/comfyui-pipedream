"""
Validation helper, not part of the pack: caps PyTorch's allocator so a
large card fails like a small one.

``--reserve-vram`` makes ComfyUI *plan* for a smaller card (weights load
against less free memory), but sampling and decode can still allocate the
whole card, so a stage that would run out of memory on 8 GB succeeds on a
48 GB card.  With ``PD_VRAM_CAP_GB`` set, this module calls
``torch.cuda.set_per_process_memory_fraction`` when ComfyUI imports it, so
PyTorch raises out-of-memory past the cap.  Memory Dynamic VRAM (comfy-aimdo)
maps outside PyTorch's allocator isn't capped.

``run_validation.py`` links this folder into ComfyUI's ``custom_nodes`` as
``pd_vram_cap`` and sets the variable per server; without the variable it
does nothing.  Remove the link when done.
"""

import os
import sys

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

_cap = os.environ.get("PD_VRAM_CAP_GB", "").strip()
if _cap:
    try:
        import torch
        if torch.cuda.is_available():
            device = torch.cuda.current_device()
            total = torch.cuda.get_device_properties(device).total_memory
            fraction = min(1.0, float(_cap) * 1024 ** 3 / total)
            torch.cuda.set_per_process_memory_fraction(fraction, device)
            print(f"[pd_vram_cap] PyTorch allocator capped at {_cap} GB "
                  f"({fraction:.3f} of {total / 1024 ** 3:.1f} GB)", file=sys.stderr)
    except Exception as exc:
        print(f"[pd_vram_cap] could not cap VRAM: {exc}", file=sys.stderr)
