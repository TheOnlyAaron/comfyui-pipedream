import { app } from "../../scripts/app.js";
/**
 * Add a read-only, non-serialized multiline text display.
 *
 * Uses ``node.addDOMWidget`` with a plain <textarea>, which both the
 * classic canvas and the Nodes 2.0 (Vue) renderer mount.  The old
 * ``addWidget("customtext")`` call no longer creates a DOM element
 * (``inputEl`` is undefined), so setting ``inputEl.readOnly`` threw in
 * nodeCreated before onExecuted was hooked up and the display never
 * filled.  ComfyWidgets from scripts/widgets.js is avoided because the
 * frontend flags it as an internal module.
 */
function addReadOnlyText(node, name, placeholder, minHeight = 100) {
    const el = document.createElement("textarea");
    el.className = "comfy-multiline-input";
    el.readOnly = true;
    el.placeholder = placeholder ?? "";
    el.spellcheck = false;
    el.wrap = "off";   // keep the token / iteration tables aligned
    Object.assign(el.style, {
        fontFamily: "monospace",
        fontSize: "11px",
        opacity: "0.85",
        width: "100%",
        boxSizing: "border-box",
        resize: "vertical",
        // Nodes 2.0 lays DOM widgets out with CSS and ignores getMinHeight.
        minHeight: `${minHeight}px`,
    });
    const widget = node.addDOMWidget(name, "pd_readonly_text", el, {
        getValue: () => el.value,
        setValue: (v) => { el.value = v ?? ""; },
        getMinHeight: () => minHeight,
        serialize: false,
    });
    widget.serialize = false;
    return widget;
}

/** True when input ``slot`` is linked, without the deprecated input.link. */
function isSlotConnected(node, slot) {
    if (typeof node.isInputConnected === "function") return node.isInputConnected(slot);
    return node.inputs?.[slot]?.link != null;
}

/* ------------------------------------------------------------------ */
/*  Pipedream.Rasterizer — read-only preview textarea                 */
/* ------------------------------------------------------------------ */

app.registerExtension({
    name: "Pipedream.Rasterizer",

    async nodeCreated(node) {
        if (node.comfyClass !== "PDRasterizer") return;

        const widget = addReadOnlyText(node, "preview_display",
            "Iteration table appears after execution...");

        const origOnExecuted = node.onExecuted;
        node.onExecuted = function (output) {
            if (origOnExecuted) origOnExecuted.call(this, output);
            if (output?.preview_table?.length > 0) {
                widget.value = output.preview_table[0];
            }
        };
    },
});

/* ------------------------------------------------------------------ */
/*  Pipedream.OutputTokenRef — read-only token reference display      */
/*  Shared by PDOutput and the legacy Relative/Absolute nodes         */
/* ------------------------------------------------------------------ */

app.registerExtension({
    name: "Pipedream.OutputTokenRef",

    async nodeCreated(node) {
        if (!["PDOutput", "PDOutputRelative", "PDOutputAbsolute"]
            .includes(node.comfyClass)) return;

        const widget = addReadOnlyText(node, "token_display",
            "Token reference appears after execution...", 140);

        const origOnExecuted = node.onExecuted;
        node.onExecuted = function (output) {
            if (origOnExecuted) origOnExecuted.call(this, output);
            if (output?.token_reference?.length > 0) {
                widget.value = output.token_reference[0];
            }
        };
    },
});

/* ------------------------------------------------------------------ */
/*  Pipedream.Switch — auto-growing input slots                       */
/* ------------------------------------------------------------------ */

app.registerExtension({
    name: "Pipedream.Switch",

    async nodeCreated(node) {
        if (node.comfyClass !== "PDSwitch") return;

        const MIN_INPUTS = 2;
        const MAX_INPUTS = 8;
        const PREFIX = "input_";

        function getInputSlots() {
            return (node.inputs || []).filter(inp => inp.name.startsWith(PREFIX));
        }

        function getHighestConnected() {
            const slots = node.inputs || [];
            let highest = -1;
            for (let i = slots.length - 1; i >= 0; i--) {
                if (slots[i].name.startsWith(PREFIX) && isSlotConnected(node, i)) {
                    const num = parseInt(slots[i].name.replace(PREFIX, ""), 10);
                    if (num > highest) highest = num;
                }
            }
            return highest;
        }

        function syncSlots() {
            const current = getInputSlots().length;
            const highestConnected = getHighestConnected();
            // Target: one more than highest connected, clamped to [MIN, MAX]
            let target = Math.max(MIN_INPUTS, highestConnected + 1);
            target = Math.min(target, MAX_INPUTS);

            // Add slots if needed
            while (getInputSlots().length < target) {
                const next = getInputSlots().length + 1;
                node.addInput(PREFIX + next, "*");
            }

            // Remove trailing empty slots if needed
            while (getInputSlots().length > target) {
                const slots = getInputSlots();
                const last = slots[slots.length - 1];
                const idx = node.inputs.indexOf(last);
                if (idx === -1 || isSlotConnected(node, idx)) break;  // don't remove connected
                node.removeInput(idx);
            }

            if (getInputSlots().length !== current) fitHeight();
        }

        // Fit the node to its contents after slots change, so no empty
        // band is left where removed inputs were (both renderers).
        function fitHeight() {
            if (!node.computeSize || !node.setSize) return;
            node.setSize([node.size[0], node.computeSize()[1]]);
            node.setDirtyCanvas?.(true, true);
        }

        // The Python node declares all 8 optional inputs, so a new node
        // starts with every slot; trim to the minimum (plus a spare after
        // the highest connected one) right away.  onConfigure re-syncs once
        // a saved workflow's links are restored.

        const origOnConnectionsChange = node.onConnectionsChange;
        node.onConnectionsChange = function (type, index, connected, linkInfo) {
            if (origOnConnectionsChange) {
                origOnConnectionsChange.call(this, type, index, connected, linkInfo);
            }
            syncSlots();
        };

        const origOnConfigure = node.onConfigure;
        node.onConfigure = function (...args) {
            const r = origOnConfigure?.apply(this, args);
            syncSlots();
            return r;
        };

        syncSlots();
    },
});
