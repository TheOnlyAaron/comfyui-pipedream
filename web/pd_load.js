import { app } from "../../scripts/app.js";
import { chain, findWidget, showSlots, showWidgets } from "./pd_common.js";

/* ------------------------------------------------------------------ */
/*  Pipedream.Load — hide what does not apply to the chosen format:    */
/*    base_path in relative mode; fps for video formats (video keeps   */
/*    its own rate); exr_colorspace unless exr or auto; the audio      */
/*    output for image formats.  Linked widgets are never hidden.      */
/* ------------------------------------------------------------------ */

const VIDEO_FORMATS = ["mp4", "mov", "webm", "mkv"];

function sync(node) {
    if (node._pdSyncing) return;
    node._pdSyncing = true;
    try {
        const mode = findWidget(node, "path_mode")?.value;
        const format = findWidget(node, "format")?.value;
        const isVideo = VIDEO_FORMATS.includes(format);
        const isImage = format !== "auto" && !isVideo;
        showWidgets(node, {
            base_path: mode === "absolute",
            fps: !isVideo,
            exr_colorspace: format === "auto" || format === "exr",
        });
        showSlots(node, "output", { audio: !isImage });
    } finally {
        node._pdSyncing = false;
    }
}

app.registerExtension({
    name: "Pipedream.Load",

    async nodeCreated(node) {
        if (node.comfyClass !== "PDLoad") return;
        for (const name of ["path_mode", "format"]) {
            const widget = findWidget(node, name);
            if (widget) chain(widget, "callback", () => sync(node));
        }
        chain(node, "onConfigure", () => sync(node));
        chain(node, "onConnectionsChange", () => queueMicrotask(() => sync(node)));
        sync(node);
    },
});
