import { app } from "../../scripts/app.js";

/* ------------------------------------------------------------------ */
/*  Pipedream.Output — dim widgets that do not apply to the current    */
/*  path_mode / format (base_path in relative mode, fps/crf for        */
/*  image formats, crf for ProRes).                                    */
/* ------------------------------------------------------------------ */

const VIDEO_FORMATS = ["mp4", "mov", "webm"];

function findWidget(node, name) {
    return node.widgets?.find(w => w.name === name);
}

function setActive(widget, active) {
    if (!widget) return;
    widget.disabled = !active;
}

function syncWidgets(node) {
    const mode = findWidget(node, "path_mode")?.value;
    const format = findWidget(node, "format")?.value;
    const isVideo = VIDEO_FORMATS.includes(format);

    setActive(findWidget(node, "base_path"), mode === "absolute");
    setActive(findWidget(node, "fps"), isVideo);
    setActive(findWidget(node, "crf"), isVideo && format !== "mov");
    node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
    name: "Pipedream.Output",

    async nodeCreated(node) {
        if (node.comfyClass !== "PDOutput") return;

        for (const name of ["path_mode", "format"]) {
            const widget = findWidget(node, name);
            if (!widget) continue;
            const origCallback = widget.callback;
            widget.callback = function (...args) {
                const result = origCallback?.apply(this, args);
                syncWidgets(node);
                return result;
            };
        }

        const origOnConfigure = node.onConfigure;
        node.onConfigure = function (...args) {
            const result = origOnConfigure?.apply(this, args);
            syncWidgets(node);
            return result;
        };

        syncWidgets(node);
    },
});
