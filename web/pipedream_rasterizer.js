import { app } from "../../scripts/app.js";

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

        // Update preview text when the node executes
        const origOnExecuted = node.onExecuted;
        node.onExecuted = function (output) {
            if (origOnExecuted) origOnExecuted.call(this, output);
            if (output && output.preview_table && output.preview_table.length > 0) {
                widget.value = output.preview_table[0];
            }
        };
    },
});
