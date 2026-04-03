"""
PD Wedge node.

Holds a list of values to iterate over.  On execution, emits the current
iteration's value.  When ``auto_queue`` is enabled, the node queues
additional ComfyUI prompt executions for the remaining values.
"""

import copy
import json
import os
import random
import sys
import urllib.request
import urllib.error


_SERVER_URL = os.environ.get("COMFYUI_SERVER_URL", "http://127.0.0.1:8188")


from ..core.display import display_name


class PDWedge:
    """Iteration/wedging node that emits one value per execution."""

    DISPLAY_NAME = display_name("PD Wedge")
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    RETURN_TYPES = ("WEDGE", "STRING", "INT")
    RETURN_NAMES = ("wedge", "current_value", "wedge_index")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "name": ("STRING", {"default": "wedge"}),
                "type": (["STRING", "INT", "FLOAT"],),
                "values": ("STRING", {
                    "default": "",
                    "multiline": True,
                }),
                "mode": (["sequential", "random"],),
                "auto_queue": ("BOOLEAN", {"default": False}),
            },
            "hidden": {
                "prompt": "PROMPT",
                "unique_id": "UNIQUE_ID",
            },
        }

    def execute(self, name, type, values, mode, auto_queue, prompt=None, unique_id=None):
        # Parse values list
        value_list = [v.strip() for v in values.split("\n") if v.strip()]
        if not value_list:
            print("[Pipedream] Warning: PD Wedge has no values to iterate", file=sys.stderr)
            return ({"name": name, "values": [], "current_index": 0}, "", 0)

        # Determine current index from injected override or default to 0
        current_index = 0
        if prompt and unique_id:
            node_inputs = prompt.get(str(unique_id), {}).get("inputs", {})
            override = node_inputs.get("_wedge_override_index")
            if override is not None:
                current_index = int(override)

        # Apply mode
        if mode == "random":
            rng = random.Random(current_index)
            order = list(range(len(value_list)))
            rng.shuffle(order)
            effective_idx = order[current_index % len(order)]
        else:
            effective_idx = current_index % len(value_list)

        raw_value = value_list[effective_idx]

        # Cast value according to type widget
        current_value = self._cast(raw_value, type)

        # Build wedge state dict
        wedge_state = {
            "name": name,
            "type": type,
            "values": value_list,
            "current_index": current_index,
            "current_value": current_value,
        }

        # Queue additional iterations if auto_queue is enabled and this is
        # the first (non-injected) execution
        if auto_queue and current_index == 0 and len(value_list) > 1:
            self._queue_remaining(prompt, unique_id, value_list)

        return (wedge_state, str(current_value), current_index)

    @staticmethod
    def _cast(value: str, type_name: str):
        try:
            if type_name == "INT":
                return int(value)
            if type_name == "FLOAT":
                return float(value)
        except ValueError:
            print(
                f"[Pipedream] Warning: could not cast '{value}' to {type_name}, "
                f"returning as string",
                file=sys.stderr,
            )
        return value

    @staticmethod
    def _queue_remaining(prompt, unique_id, value_list):
        """POST modified prompts to the ComfyUI server for remaining values."""
        if not prompt or not unique_id:
            print(
                "[Pipedream] Warning: cannot auto-queue — prompt or unique_id unavailable",
                file=sys.stderr,
            )
            return

        uid = str(unique_id)
        for idx in range(1, len(value_list)):
            modified = copy.deepcopy(prompt)
            if uid in modified and "inputs" in modified[uid]:
                modified[uid]["inputs"]["_wedge_override_index"] = idx
            else:
                print(
                    f"[Pipedream] Warning: node {uid} not found in prompt, "
                    f"skipping queue injection for index {idx}",
                    file=sys.stderr,
                )
                return

            payload = json.dumps({"prompt": modified}).encode("utf-8")
            req = urllib.request.Request(
                f"{_SERVER_URL}/prompt",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=10):
                    pass
            except (urllib.error.URLError, OSError) as exc:
                print(
                    f"[Pipedream] Error: failed to queue wedge iteration {idx}: {exc}",
                    file=sys.stderr,
                )
                return
