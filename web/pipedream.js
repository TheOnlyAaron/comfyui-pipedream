import { app } from "../../scripts/app.js";

/* ------------------------------------------------------------------ */
/*  Pipedream.Rasterizer — read-only preview textarea                 */
/* ------------------------------------------------------------------ */

app.registerExtension({
    name: "Pipedream.Rasterizer",

    async nodeCreated(node) {
        if (node.comfyClass !== "PDRasterizer") return;

        const widget = node.addWidget("customtext", "preview_display", "", () => {}, {
            multiline: true,
            dynamicPrompts: false,
        });
        widget.inputEl.readOnly = true;
        widget.inputEl.style.fontFamily = "monospace";
        widget.inputEl.style.fontSize = "11px";
        widget.inputEl.style.opacity = "0.85";

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
/*  Shared by PDOutputRelative and PDOutputAbsolute                   */
/* ------------------------------------------------------------------ */

app.registerExtension({
    name: "Pipedream.OutputTokenRef",

    async nodeCreated(node) {
        if (node.comfyClass !== "PDOutputRelative" &&
            node.comfyClass !== "PDOutputAbsolute") return;

        const widget = node.addWidget("customtext", "token_display", "", () => {}, {
            multiline: true,
            dynamicPrompts: false,
        });
        widget.inputEl.readOnly = true;
        widget.inputEl.style.fontFamily = "monospace";
        widget.inputEl.style.fontSize = "11px";
        widget.inputEl.style.opacity = "0.85";
        widget.inputEl.placeholder = "Token reference appears after execution...";

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
                if (slots[i].name.startsWith(PREFIX) && slots[i].link != null) {
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
                if (last.link != null) break;  // don't remove connected
                const idx = node.inputs.indexOf(last);
                if (idx !== -1) node.removeInput(idx);
            }
        }

        // Initial setup: show 3 inputs
        const existing = getInputSlots().length;
        for (let i = existing + 1; i <= 3; i++) {
            if (!node.inputs?.find(inp => inp.name === PREFIX + i)) {
                node.addInput(PREFIX + i, "*");
            }
        }

        const origOnConnectionsChange = node.onConnectionsChange;
        node.onConnectionsChange = function (type, index, connected, linkInfo) {
            if (origOnConnectionsChange) {
                origOnConnectionsChange.call(this, type, index, connected, linkInfo);
            }
            syncSlots();
        };
    },
});

/* ------------------------------------------------------------------ */
/*  Pipedream.ProjectContext — version auto-increment widget update    */
/* ------------------------------------------------------------------ */

app.registerExtension({
    name: "Pipedream.ProjectContext",

    async nodeCreated(node) {
        if (node.comfyClass !== "PDProjectContext") return;

        const origOnExecuted = node.onExecuted;
        node.onExecuted = function (output) {
            if (origOnExecuted) origOnExecuted.call(this, output);
            if (output?.version?.length > 0) {
                const versionWidget = this.widgets?.find(w => w.name === "version");
                if (versionWidget) {
                    versionWidget.value = output.version[0];
                }
            }
        };
    },
});
