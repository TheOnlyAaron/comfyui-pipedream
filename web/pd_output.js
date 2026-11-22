import { app } from "../../scripts/app.js";
import { chain, findWidget, isInputLinked, showWidgets } from "./pd_common.js";

/* ------------------------------------------------------------------ */
/*  Pipedream.Output — hide widgets that do not apply to the current   */
/*  path_mode / format: base_path in relative mode, fps/crf for image  */
/*  formats, crf for ProRes, exr_* unless the format is exr, fps when  */
/*  a VIDEO input is connected (the video keeps its own frame rate).   */
/* ------------------------------------------------------------------ */

const VIDEO_FORMATS = ["mp4", "mov", "webm"];
const VIDEO_EXTS = /\.(mp4|webm|mov|mkv)$/i;

function syncWidgets(node) {
    const mode = findWidget(node, "path_mode")?.value;
    const format = findWidget(node, "format")?.value;
    const isVideo = VIDEO_FORMATS.includes(format);
    showWidgets(node, {
        base_path: mode === "absolute",
        fps: isVideo && !isInputLinked(node, "video"),
        crf: isVideo && format !== "mov",
        exr_precision: format === "exr",
        exr_compression: format === "exr",
    });
}

/** The classic canvas keeps its video-preview DOM widget after switching to an image format. */
function clearClassicVideoPreview(node) {
    const widget = findWidget(node, "video-preview");
    if (widget) {
        node.removeWidget(widget);
        widget.onRemove?.();
    }
    node.videoContainer = undefined;
}

app.registerExtension({
    name: "Pipedream.Output",

    async nodeCreated(node) {
        if (node.comfyClass !== "PDOutput") return;

        for (const name of ["path_mode", "format"]) {
            const widget = findWidget(node, name);
            if (widget) chain(widget, "callback", () => syncWidgets(node));
        }
        chain(node, "onConfigure", () => syncWidgets(node));
        chain(node, "onConnectionsChange", () => syncWidgets(node));

        // The frontend previews any node with a VIDEO input as video unless
        // previewMediaType says otherwise; our previews are usually images.
        node.previewMediaType = "image";
        chain(node, "onExecuted", function (output) {
            const isVideo = output?.animated?.some(Boolean) &&
                output?.images?.some(i => VIDEO_EXTS.test(i?.filename ?? ""));
            this.previewMediaType = isVideo ? "video" : "image";
            if (!isVideo && !globalThis.LiteGraph?.vueNodesMode) clearClassicVideoPreview(this);
        });

        syncWidgets(node);
    },
});
