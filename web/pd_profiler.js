import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { addReadOnlyText, chain, findWidget, showOutputText, showWidgets } from "./pd_common.js";

/* ------------------------------------------------------------------ */
/*  Pipedream.Profiler                                                 */
/*                                                                     */
/*  "profile" evaluates what the node's input reads from without       */
/*  queuing anything (POST /pipedream/profiler/evaluate with the       */
/*  current prompt).  "use this machine" fills vram_gb / ram_gb with   */
/*  this machine's memory (GET /pipedream/profiler/machine).           */
/*                                                                     */
/*  Each run's measured node times are kept in node.properties, so     */
/*  they survive a save and later evaluations can estimate time.       */
/*  path is shown only while export_sidecar is on (or linked).         */
/* ------------------------------------------------------------------ */

const TIMINGS = "pd_profile_timings";
const GIB = 1024 ** 3;

/** Prompt id of a graph node (``outer:inner`` inside subgraphs). */
function promptId(output, node) {
    const id = String(node.id);
    if (output[id]?.class_type === node.comfyClass) return id;
    return Object.keys(output).find(k => k.endsWith(`:${id}`) && output[k].class_type === node.comfyClass);
}

async function evaluate(node) {
    const panel = findWidget(node, "profile_display");
    if (!panel) return;
    panel.value = "Profiling...";
    try {
        const { output } = await app.graphToPrompt();
        const id = promptId(output, node);
        if (!id) {
            panel.value = "This PD Profiler is bypassed or muted, or its input is not connected.";
            return;
        }
        const response = await api.fetchApi("/pipedream/profiler/evaluate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ prompt: output, node_id: id, timings: node.properties?.[TIMINGS] ?? {} }),
        });
        const result = await response.json();
        panel.value = result.text ?? result.error ?? "No result.";
    } catch (error) {
        panel.value = `Profile failed: ${error.message ?? error}`;
    }
    node.setDirtyCanvas?.(true, true);
}

async function useThisMachine(node) {
    try {
        const response = await api.fetchApi("/pipedream/profiler/machine");
        const machine = await response.json();
        for (const [name, bytes] of [["vram_gb", machine.vram], ["ram_gb", machine.ram]]) {
            const widget = findWidget(node, name);
            if (widget) {
                widget.value = Math.round((bytes / GIB) * 10) / 10;
                widget.callback?.(widget.value);
            }
        }
    } catch (error) {
        const panel = findWidget(node, "profile_display");
        if (panel) panel.value = `Could not read this machine: ${error.message ?? error}`;
    }
}

function syncPath(node) {
    showWidgets(node, { path: !!findWidget(node, "export_sidecar")?.value });
}

app.registerExtension({
    name: "Pipedream.Profiler",

    async nodeCreated(node) {
        if (node.comfyClass !== "PDProfiler") return;

        const profile = node.addWidget("button", "profile", null, () => evaluate(node), { serialize: false });
        profile.serialize = false;
        profile.tooltip = "Evaluate everything upstream of this node now, without running anything.";
        const machine = node.addWidget("button", "use this machine", null, () => useThisMachine(node),
                                       { serialize: false });
        machine.serialize = false;
        machine.tooltip = "Set vram_gb and ram_gb to this machine's memory (stops emulating another machine).";

        const panel = addReadOnlyText(node, "profile_display",
                                      "Press profile to evaluate upstream, or queue a run to measure it.", 220);
        showOutputText(node, panel, "profile_text");

        chain(node, "onExecuted", (output) => {
            const timings = output?.pd_profile_timings?.[0];
            if (timings && Object.keys(timings).length) {
                node.properties ??= {};
                node.properties[TIMINGS] = { ...(node.properties[TIMINGS] ?? {}), ...timings };
            }
        });

        let pending = null;
        const later = () => {
            clearTimeout(pending);
            pending = setTimeout(() => evaluate(node), 300);
        };
        for (const name of ["vram_gb", "ram_gb"]) {
            const widget = findWidget(node, name);
            if (widget) chain(widget, "callback", later);
        }
        const sidecar = findWidget(node, "export_sidecar");
        if (sidecar) chain(sidecar, "callback", () => syncPath(node));
        chain(node, "onConfigure", () => syncPath(node));
        syncPath(node);
    },
});
