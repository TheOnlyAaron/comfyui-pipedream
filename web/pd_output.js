import { app } from "../../scripts/app.js";
import { chain, findWidget, isInputLinked, showSlots, showWidgets } from "./pd_common.js";

/* ------------------------------------------------------------------ */
/*  Pipedream.Output — hide widgets and sockets that do not apply to   */
/*  the current path_mode / format:                                    */
/*    base_path in relative mode; fps/crf for image formats (crf for   */
/*    ProRes, fps while a VIDEO is connected); prores_profile unless   */
/*    mov; exr_* unless exr; start_frame/frame_padding for video;      */
/*    the alpha input for formats without alpha (jpg/mp4/webm, ProRes  */
/*    422 HQ); the video output for image formats.                     */
/*  Linked widgets and sockets are never hidden.                       */
/* ------------------------------------------------------------------ */

const VIDEO_FORMATS = ["mp4", "mov", "webm"];
const ALPHA_IMAGE_FORMATS = ["png", "exr", "webp"];
const VIDEO_EXTS = /\.(mp4|webm|mov|mkv)$/i;

function sync(node) {
    if (node._pdSyncing) return;
    node._pdSyncing = true;
    try {
        const mode = findWidget(node, "path_mode")?.value;
        const format = findWidget(node, "format")?.value;
        const prores = findWidget(node, "prores_profile")?.value;
        const isVideo = VIDEO_FORMATS.includes(format);
        const isExr = format === "exr";
        showWidgets(node, {
            base_path: mode === "absolute",
            start_frame: !isVideo,
            frame_padding: !isVideo,
            fps: isVideo && !isInputLinked(node, "video"),
            crf: isVideo && format !== "mov",
            prores_profile: format === "mov",
            exr_precision: isExr,
            exr_compression: isExr,
            exr_colorspace: isExr,
        });
        const alphaOk = ALPHA_IMAGE_FORMATS.includes(format) || (format === "mov" && prores !== "422 HQ");
        showSlots(node, "input", { alpha: alphaOk });
        showSlots(node, "output", { video: isVideo });
    } finally {
        node._pdSyncing = false;
    }
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

        for (const name of ["path_mode", "format", "prores_profile"]) {
            const widget = findWidget(node, name);
            if (widget) chain(widget, "callback", () => sync(node));
        }
        chain(node, "onConfigure", () => sync(node));
        // Deferred so a slot is never removed inside the link operation that unlinked it.
        chain(node, "onConnectionsChange", () => queueMicrotask(() => sync(node)));

        // The frontend previews any node with a VIDEO input as video unless
        // previewMediaType says otherwise; our previews are usually images.
        node.previewMediaType = "image";
        chain(node, "onExecuted", function (output) {
            const isVideo = output?.animated?.some(Boolean) &&
                output?.images?.some(i => VIDEO_EXTS.test(i?.filename ?? ""));
            this.previewMediaType = isVideo ? "video" : "image";
            if (!isVideo && !globalThis.LiteGraph?.vueNodesMode) clearClassicVideoPreview(this);
        });

        sync(node);
    },
});
