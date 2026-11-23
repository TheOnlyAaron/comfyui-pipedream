import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { chain, clearClassicVideoPreview, findWidget, showSlots, showWidgets } from "./pd_common.js";

/* ------------------------------------------------------------------ */
/*  Pipedream.Load                                                     */
/*    - Hide what does not apply: base_path in relative mode;          */
/*      sequence_from_file for video formats; fps_from_file for image  */
/*      formats; exr_colorspace unless exr or auto; the audio output   */
/*      for image formats.                                             */
/*    - Paste a full file path (quotes allowed) into file or           */
/*      base_path: if it is an existing file, it is split into the     */
/*      two fields (absolute mode) and loaded.                         */
/*    - "load" button: runs just this node to check what it loads.     */
/*    - Multi-frame loads preview as a playable video.                 */
/* ------------------------------------------------------------------ */

const VIDEO_FORMATS = ["mp4", "mov", "webm", "mkv"];
const VIDEO_EXTS = /\.(mp4|webm|mov|mkv)$/i;
const ABSOLUTE = /^([A-Za-z]:[\\/]|\\\\|\/\/|\/)/;

function sync(node) {
    if (node._pdSyncing) return;
    node._pdSyncing = true;
    try {
        const mode = findWidget(node, "path_mode")?.value;
        const format = findWidget(node, "format")?.value;
        const isImage = format !== "auto" && !VIDEO_FORMATS.includes(format);
        showWidgets(node, {
            base_path: mode === "absolute",
            sequence_from_file: !VIDEO_FORMATS.includes(format),
            fps_from_file: !isImage,
            exr_colorspace: format === "auto" || format === "exr",
        });
        showSlots(node, "output", { audio: !isImage });
    } finally {
        node._pdSyncing = false;
    }
}

/** Remove surrounding whitespace and quotes (Windows "Copy as path"). */
export function cleanPath(text) {
    let value = String(text ?? "").trim();
    while (value.length >= 2 && value[0] === value.at(-1) && `"'`.includes(value[0])) {
        value = value.slice(1, -1).trim();
    }
    return value;
}

function setValue(node, name, value) {
    const widget = findWidget(node, name);
    if (widget && widget.value !== value) widget.value = value;
}

/** Run just this node (PD Load is an output node), like the toolbar's run button. */
function runNode(node) {
    return app.queuePrompt(0, 1, [String(node.id)]);
}

/**
 * After file or base_path changes: strip quotes, and if the value is the
 * full path of an existing file, split it into base_path and file and load.
 */
async function onPathEdited(node, name) {
    const widget = findWidget(node, name);
    if (!widget) return;
    const value = cleanPath(widget.value);
    if (value !== widget.value) widget.value = value;
    if (!ABSOLUTE.test(value)) return;
    let found = null;
    try {
        const response = await api.fetchApi("/pipedream/load/check", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path: value }),
        });
        found = await response.json();
    } catch {
        return;
    }
    if (!found?.name) return;
    setValue(node, "path_mode", "absolute");
    setValue(node, "base_path", found.folder);
    setValue(node, "file", found.name);
    sync(node);
    node.setDirtyCanvas?.(true, true);
    runNode(node);
}

app.registerExtension({
    name: "Pipedream.Load",

    async nodeCreated(node) {
        if (node.comfyClass !== "PDLoad") return;

        for (const name of ["path_mode", "format"]) {
            const widget = findWidget(node, name);
            if (widget) chain(widget, "callback", () => sync(node));
        }
        for (const name of ["file", "base_path"]) {
            const widget = findWidget(node, name);
            if (widget) chain(widget, "callback", () => onPathEdited(node, name));
        }

        const button = node.addWidget("button", "load", null, () => runNode(node),
                                      { serialize: false });
        button.serialize = false;
        button.tooltip = "Run just this node to check what it loads (preview and info below).";

        // Images by default; a multi-frame load previews as a video (an mp4 in temp).
        node.previewMediaType = "image";
        chain(node, "onExecuted", function (output) {
            const isVideo = output?.animated?.some(Boolean) &&
                output?.images?.some(i => VIDEO_EXTS.test(i?.filename ?? ""));
            this.previewMediaType = isVideo ? "video" : "image";
            if (!isVideo && !globalThis.LiteGraph?.vueNodesMode) clearClassicVideoPreview(this);
        });

        chain(node, "onConfigure", () => sync(node));
        chain(node, "onConnectionsChange", () => queueMicrotask(() => sync(node)));
        sync(node);
    },
});
