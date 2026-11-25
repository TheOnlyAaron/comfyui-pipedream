import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { chain, findWidget, isInputLinked, showSlots, showWidgets, trackPreviewMedia } from "./pd_common.js";

/* ------------------------------------------------------------------ */
/*  Pipedream.Output — hide widgets and sockets that do not apply to   */
/*  the current path_mode / format:                                    */
/*    base_path in relative mode; fps/crf for image formats (crf for   */
/*    ProRes, fps while a VIDEO is connected); prores_profile unless   */
/*    mov; exr_* unless exr; start_frame/frame_padding for video;      */
/*    the alpha input for formats without alpha (jpg/mp4/webm, ProRes  */
/*    422 HQ); the video output for image formats.  exr_metadata       */
/*    inputs show for exr only, one spare after the highest linked.    */
/*  Linked widgets and sockets are never hidden.                       */
/*                                                                     */
/*  "Explore Output" shows the last written file in Explorer/Finder.   */
/*  The path is kept in node.properties, so it survives a save.        */
/*                                                                     */
/*  Dropping or opening a PD Output sidecar .json reopens the workflow */
/*  stored in it (or its API prompt, for sidecars written before the   */
/*  workflow was stored) instead of failing as a broken workflow.      */
/* ------------------------------------------------------------------ */

const VIDEO_FORMATS = ["mp4", "mov", "webm"];
const METADATA_INPUTS = ["exr_metadata", ...[2, 3, 4, 5, 6, 7, 8].map(n => `exr_metadata_${n}`)];

/** exr_metadata inputs to show: for exr, every one up to a spare after the highest linked. */
function metadataRules(node, isExr) {
    let highest = -1;
    METADATA_INPUTS.forEach((name, i) => { if (isInputLinked(node, name)) highest = i; });
    const count = isExr ? Math.min(METADATA_INPUTS.length, highest + 2) : 0;
    return Object.fromEntries(METADATA_INPUTS.map((name, i) => [name, i < count]));
}

function labelMetadata(node) {
    for (const input of node.inputs ?? []) {
        const i = METADATA_INPUTS.indexOf(input.name);
        if (i >= 0) input.label = i === 0 ? "exr metadata" : `exr metadata ${i + 1}`;
    }
}
const ALPHA_IMAGE_FORMATS = ["png", "exr", "webp"];

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
        showSlots(node, "input", { alpha: alphaOk, ...metadataRules(node, isExr) });
        labelMetadata(node);
        showSlots(node, "output", { video: isVideo });
    } finally {
        node._pdSyncing = false;
    }
}

const LAST_OUTPUT = "pd_last_output";

function toast(severity, detail) {
    if (app.extensionManager?.toast?.add) {
        app.extensionManager.toast.add({ severity, summary: "PD Output", detail, life: 4000 });
    } else {
        alert(detail);
    }
}

async function explore(node) {
    const path = node.properties?.[LAST_OUTPUT];
    if (!path) {
        toast("warn", "Nothing written yet: run the node first.");
        return;
    }
    try {
        const response = await api.fetchApi("/pipedream/output/reveal", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path }),
        });
        const result = await response.json();
        if (result.error) toast("error", result.error);
    } catch (error) {
        toast("error", String(error));
    }
}

function isSidecar(data) {
    return data && typeof data === "object" && data.node === "PDOutput" && "context" in data;
}

/** Wrap app.loadGraphData so a PD Output sidecar loads the workflow it stores. */
function acceptSidecars() {
    const original = app.loadGraphData;
    if (typeof original !== "function" || original._pdSidecar) return;
    const wrapped = async function (graphData, ...rest) {
        if (!isSidecar(graphData)) return original.call(this, graphData, ...rest);
        if (Array.isArray(graphData.workflow?.nodes)) {
            return original.call(this, graphData.workflow, ...rest);
        }
        if (graphData.prompt && typeof app.loadApiJson === "function") {
            const name = typeof rest[2] === "string" ? rest[2] : "sidecar";
            return app.loadApiJson(graphData.prompt, name);
        }
        toast("error", "This sidecar holds no workflow.");
    };
    wrapped._pdSidecar = true;
    app.loadGraphData = wrapped;
}

app.registerExtension({
    name: "Pipedream.Output",

    setup() {
        acceptSidecars();
    },

    async nodeCreated(node) {
        if (node.comfyClass !== "PDOutput") return;

        for (const name of ["path_mode", "format", "prores_profile"]) {
            const widget = findWidget(node, name);
            if (widget) chain(widget, "callback", () => sync(node));
        }
        chain(node, "onConfigure", () => sync(node));
        // Deferred so a slot is never removed inside the link operation that unlinked it.
        chain(node, "onConnectionsChange", () => queueMicrotask(() => sync(node)));

        trackPreviewMedia(node);

        // Shown as "file" like PD Load; the input stays "template" so saved workflows
        // and API prompts keep working.
        const templateWidget = findWidget(node, "template");
        if (templateWidget) templateWidget.label = "file";

        const button = node.addWidget("button", "Explore Output", null, () => explore(node),
                                      { serialize: false });
        button.serialize = false;
        button.tooltip = "Show the last written file in Explorer (Finder on macOS).";
        chain(node, "onExecuted", (output) => {
            const path = output?.pd_written?.[0];
            if (path) {
                node.properties ??= {};
                node.properties[LAST_OUTPUT] = path;
            }
        });

        // Deferred: a graph loaded from an API prompt links inputs after creating the
        // node, and an exr_metadata input trimmed now could not be linked.
        setTimeout(() => sync(node), 0);
    },
});
