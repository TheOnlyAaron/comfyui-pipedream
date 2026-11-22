import { app } from "../../scripts/app.js";

/* ------------------------------------------------------------------ */
/*  Pipedream.Output — dim widgets that do not apply to the current    */
/*  path_mode / format (base_path in relative mode, fps/crf for        */
/*  image formats, crf for ProRes, exr_* for non-EXR formats).         */
/*  The legacy Output Relative/Absolute nodes only get the exr_*       */
/*  dimming, driven by their "extension" widget.                       */
/* ------------------------------------------------------------------ */

const NODE_CLASSES = ["PDOutput", "PDOutputRelative", "PDOutputAbsolute"];
const VIDEO_FORMATS = ["mp4", "mov", "webm"];

function findWidget(node, name) {
    return node.widgets?.find(w => w.name === name);
}

function setActive(widget, active) {
    if (!widget) return;
    widget.disabled = !active;
}

function syncWidgets(node) {
    const modeWidget = findWidget(node, "path_mode");
    const format = (findWidget(node, "format") ?? findWidget(node, "extension"))?.value;
    const isVideo = VIDEO_FORMATS.includes(format);

    if (modeWidget) {
        setActive(findWidget(node, "base_path"), modeWidget.value === "absolute");
    }
    setActive(findWidget(node, "fps"), isVideo);
    setActive(findWidget(node, "crf"), isVideo && format !== "mov");
    setActive(findWidget(node, "exr_precision"), format === "exr");
    setActive(findWidget(node, "exr_compression"), format === "exr");
    node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
    name: "Pipedream.Output",

    async nodeCreated(node) {
        if (!NODE_CLASSES.includes(node.comfyClass)) return;

        for (const name of ["path_mode", "format", "extension"]) {
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
