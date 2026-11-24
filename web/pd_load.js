import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { chain, findWidget, showSlots, showWidgets, trackPreviewMedia } from "./pd_common.js";

/* ------------------------------------------------------------------ */
/*  Pipedream.Load                                                     */
/*    - Hide what does not apply: base_path in relative mode;          */
/*      sequence_mode for video formats; fps_from_file for image       */
/*      formats; exr_colorspace unless exr or auto; the audio output   */
/*      for image formats.                                             */
/*    - Paste a full file path (quotes allowed) into file or           */
/*      base_path: if it is an existing file, it is split into the     */
/*      two fields (absolute mode) and loaded.                         */
/*    - "load" button: runs just this node to check what it loads.     */
/*    - "Explore Input" button: opens the folder of the file in        */
/*      Explorer (Finder on macOS).                                    */
/*    - Drop zone (and the whole node on the classic canvas): files     */
/*      dragged from Explorer.  Browsers do not reveal a dropped file's */
/*      path, so the files are uploaded to ComfyUI's input/pipedream    */
/*      folder (all frames of a sequence, sidecar included) and loaded  */
/*      from there in relative mode.  Where the browser does expose    */
/*      the path (File.path, older Electron), it is loaded in place.   */
/*    - Multi-frame loads preview as a playable video.                 */
/* ------------------------------------------------------------------ */

const VIDEO_FORMATS = ["mp4", "mov", "webm", "mkv"];
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
            sequence_mode: !VIDEO_FORMATS.includes(format),
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

const UPLOAD_SUBFOLDER = "pipedream";

/**
 * Workflows saved before 0.2.1 hold the sequence_from_file boolean, which
 * lands in sequence_mode by position (or only in widgets_values_named):
 * true becomes auto, false single file.
 */
function migrateSequenceMode(node, info) {
    const widget = findWidget(node, "sequence_mode");
    if (!widget) return;
    const named = info?.widgets_values_named;
    let old = typeof widget.value === "boolean" ? widget.value : undefined;
    if (old === undefined && named && !("sequence_mode" in named) &&
        typeof named.sequence_from_file === "boolean") {
        old = named.sequence_from_file;
    }
    if (old !== undefined) widget.value = old ? "auto" : "single file";
}

function toast(severity, detail) {
    app.extensionManager?.toast?.add?.({ severity, summary: "PD Load", detail, life: 4000 });
}

/** Upload one file to input/pipedream; returns its path relative to the input folder. */
async function uploadFile(file) {
    const body = new FormData();
    body.append("image", file, file.name);
    body.append("subfolder", UPLOAD_SUBFOLDER);
    body.append("type", "input");
    body.append("overwrite", "true");
    const response = await api.fetchApi("/upload/image", { method: "POST", body });
    if (response.status !== 200) throw new Error(`${file.name}: ${response.status} ${response.statusText}`);
    const data = await response.json();
    return data.subfolder ? `${data.subfolder}/${data.name}` : data.name;
}

/**
 * Load dropped files: in place when the browser exposes their path,
 * otherwise uploaded.  The first media file by name is loaded, so with
 * sequence_mode auto a dropped sequence loads from its first frame.
 */
async function onFilesDropped(node, fileList) {
    const files = [...fileList].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
    const media = files.filter((f) => !/\.json$/i.test(f.name));
    if (!media.length) {
        toast("warn", "Drop an image, sequence or video file.");
        return;
    }
    if (media[0].path) {
        setValue(node, "file", media[0].path);
        await onPathEdited(node, "file");
        return;
    }
    toast("info", files.length > 1 ? `Uploading ${files.length} files to input/${UPLOAD_SUBFOLDER}...`
                                   : `Uploading ${files[0].name} to input/${UPLOAD_SUBFOLDER}...`);
    let picked = null;
    try {
        for (const file of files) {
            const uploaded = await uploadFile(file);
            if (file === media[0]) picked = uploaded;
        }
    } catch (error) {
        toast("error", `Upload failed: ${error.message ?? error}`);
        return;
    }
    setValue(node, "path_mode", "relative");
    setValue(node, "file", picked);
    sync(node);
    node.setDirtyCanvas?.(true, true);
    runNode(node);
}

const LAST_LOADED = "pd_last_loaded";

async function explore(node) {
    const value = (name) => findWidget(node, name)?.value ?? "";
    try {
        const response = await api.fetchApi("/pipedream/load/explore", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                path_mode: value("path_mode"),
                base_path: value("base_path"),
                file: value("file"),
                last: node.properties?.[LAST_LOADED] ?? "",
            }),
        });
        const result = await response.json();
        if (result.error) toast("error", result.error);
    } catch (error) {
        toast("error", String(error));
    }
}

const hasFiles = (event) => [...(event.dataTransfer?.types ?? [])].includes("Files");

/** A dashed drop target DOM widget; drops here never reach the canvas. */
function addDropZone(node) {
    const el = document.createElement("div");
    el.textContent = "Drop files here";
    el.title = `Files are copied to ComfyUI's input/${UPLOAD_SUBFOLDER} folder and loaded from there.`;
    Object.assign(el.style, {
        border: "2px dashed var(--border-color, #666)",
        borderRadius: "6px",
        color: "var(--descrip-text, #999)",
        fontSize: "12px",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        height: "100%",
        minHeight: "40px",
        boxSizing: "border-box",
        transition: "background 0.1s, border-color 0.1s",
    });
    const highlight = (on) => {
        el.style.background = on ? "rgba(80, 140, 255, 0.15)" : "";
        el.style.borderColor = on ? "rgb(80, 140, 255)" : "var(--border-color, #666)";
    };
    el.addEventListener("dragover", (event) => {
        if (!hasFiles(event)) return;
        event.preventDefault();
        event.stopPropagation();
        event.dataTransfer.dropEffect = "copy";
        highlight(true);
    });
    el.addEventListener("dragleave", () => highlight(false));
    el.addEventListener("drop", (event) => {
        if (!hasFiles(event)) return;
        event.preventDefault();
        event.stopPropagation();
        highlight(false);
        onFilesDropped(node, event.dataTransfer.files);
    });
    const widget = node.addDOMWidget("drop_zone", "pd_drop_zone", el, {
        getValue: () => "",
        setValue: () => {},
        getMinHeight: () => 44,
        serialize: false,
    });
    widget.serialize = false;
    return widget;
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

        const exploreButton = node.addWidget("button", "Explore Input", null, () => explore(node),
                                             { serialize: false });
        exploreButton.serialize = false;
        exploreButton.tooltip = "Open the folder of the file in Explorer (Finder on macOS).";
        chain(node, "onExecuted", (output) => {
            const path = output?.pd_loaded?.[0];
            if (path) {
                node.properties ??= {};
                node.properties[LAST_LOADED] = path;
            }
        });

        addDropZone(node);
        // Classic canvas: files dropped anywhere on the node load too.
        node.onDragOver = (event) => hasFiles(event);
        node.onDragDrop = (event) => {
            if (!event.dataTransfer?.files?.length) return false;
            onFilesDropped(node, event.dataTransfer.files);
            return true;
        };

        trackPreviewMedia(node);
        chain(node, "onConfigure", (info) => {
            migrateSequenceMode(node, info);
            sync(node);
        });
        chain(node, "onConnectionsChange", () => queueMicrotask(() => sync(node)));
        sync(node);
    },
});
