import { app } from "../../scripts/app.js";

/* ------------------------------------------------------------------ */
/*  Pipedream.Output — hide widgets that do not apply to the current   */
/*  path_mode / format: base_path in relative mode, fps/crf for image  */
/*  formats, crf for ProRes, fps when a VIDEO input is connected (the  */
/*  video keeps its own frame rate), exr_* for non-EXR formats.  The   */
/*  legacy Output Relative/Absolute nodes only get the exr_* handling, */
/*  driven by their "extension" widget.                                */
/*                                                                     */
/*  Written for the Nodes 2.0 (Vue) renderer first: widget.hidden is   */
/*  reactive there and the node re-lays itself out.  The classic       */
/*  canvas honours it too; we only resize the node there.  A widget    */
/*  whose input socket is linked is never hidden.                      */
/* ------------------------------------------------------------------ */

const NODE_CLASSES = ["PDOutput", "PDOutputRelative", "PDOutputAbsolute"];
const VIDEO_FORMATS = ["mp4", "mov", "webm"];
const VIDEO_EXTS = /\.(mp4|webm|mov|mkv)$/i;

function findWidget(node, name) {
    return node.widgets?.find(w => w.name === name);
}

function inputLinked(node, name) {
    return node.inputs?.some(i => (i.name === name || i.widget?.name === name) && i.link != null);
}

function setShown(node, name, shown) {
    const widget = findWidget(node, name);
    if (!widget) return false;
    const hidden = !shown && !inputLinked(node, name);
    if (!!widget.hidden === hidden) return false;
    widget.hidden = hidden;
    return true;
}

function syncWidgets(node) {
    const mode = findWidget(node, "path_mode")?.value;
    const format = (findWidget(node, "format") ?? findWidget(node, "extension"))?.value;
    const isVideo = VIDEO_FORMATS.includes(format);
    const hasVideoInput = inputLinked(node, "video");

    let changed = false;
    if (mode !== undefined) {
        changed = setShown(node, "base_path", mode === "absolute") || changed;
    }
    changed = setShown(node, "fps", isVideo && !hasVideoInput) || changed;
    changed = setShown(node, "crf", isVideo && format !== "mov") || changed;
    changed = setShown(node, "exr_precision", format === "exr") || changed;
    changed = setShown(node, "exr_compression", format === "exr") || changed;
    if (!changed) return;

    if (!globalThis.LiteGraph?.vueNodesMode && node.computeSize && node.setSize) {
        node.setSize([node.size[0], node.computeSize()[1]]);
    }
    node.setDirtyCanvas?.(true, true);
}

function chain(object, method, after) {
    const original = object[method];
    object[method] = function (...args) {
        const result = original?.apply(this, args);
        after.apply(this, args);
        return result;
    };
}

app.registerExtension({
    name: "Pipedream.Output",

    async nodeCreated(node) {
        if (!NODE_CLASSES.includes(node.comfyClass)) return;

        for (const name of ["path_mode", "format", "extension"]) {
            const widget = findWidget(node, name);
            if (widget) chain(widget, "callback", () => syncWidgets(node));
        }
        chain(node, "onConfigure", () => syncWidgets(node));
        chain(node, "onConnectionsChange", () => syncWidgets(node));

        // The frontend previews nodes with a VIDEO input as video unless
        // previewMediaType says otherwise; our previews are usually images.
        node.previewMediaType = "image";
        chain(node, "onExecuted", function (output) {
            const isVideo = output?.animated?.some(Boolean) &&
                output?.images?.some(i => VIDEO_EXTS.test(i?.filename ?? ""));
            this.previewMediaType = isVideo ? "video" : "image";
        });

        syncWidgets(node);
    },
});
