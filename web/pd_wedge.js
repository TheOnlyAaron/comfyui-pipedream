import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { chain, findWidget, isInputLinked, refit, setHidden, SAVE_CLASSES } from "./pd_common.js";

/* ------------------------------------------------------------------ */
/*  Pipedream.Wedge — auto-growing rows of input + text value          */
/* ------------------------------------------------------------------ */

export const MAX_ROWS = 16;
const INPUT = "input_";
const VALUE = "value_";
const LABEL_CHARS = 24;

/**
 * Number of rows that should be visible: every row up to the last one in
 * use, plus one spare.  Rows in the middle are kept (gaps are skipped at
 * run time) so nothing jumps around.
 *
 * @param {boolean[]} used  Whether each row is in use, in order.
 */
export function visibleRowCount(used, max = MAX_ROWS) {
    const last = used.lastIndexOf(true);
    return Math.min(max, last + 2);
}

function inputSlot(node, n) {
    return node.inputs?.findIndex(i => i.name === INPUT + n) ?? -1;
}

function rowUsed(node, n) {
    const slot = inputSlot(node, n);
    const value = findWidget(node, VALUE + n);
    return (slot >= 0 && node.isInputConnected(slot))
        || isInputLinked(node, VALUE + n)
        || !!String(value?.value ?? "").trim();
}

function rowLabel(node, n) {
    if (isInputLinked(node, VALUE + n)) return `${n}: (linked)`;
    const text = String(findWidget(node, VALUE + n)?.value ?? "").trim();
    if (!text) return `${n}`;
    return `${n}: ${text.length > LABEL_CHARS ? text.slice(0, LABEL_CHARS - 1) + "…" : text}`;
}

/** Show the rows in use plus a spare, hide the rest, label the sockets. */
export function syncRows(node) {
    const used = [];
    for (let n = 1; n <= MAX_ROWS; n++) used.push(rowUsed(node, n));
    const count = visibleRowCount(used);
    let changed = false;

    for (let n = MAX_ROWS; n > count; n--) {
        const slot = inputSlot(node, n);
        if (slot >= 0 && !node.isInputConnected(slot)) {
            node.removeInput(slot);
            changed = true;
        }
    }
    for (let n = 1; n <= count; n++) {
        if (inputSlot(node, n) < 0) {
            node.addInput(INPUT + n, "*");
            changed = true;
        }
    }
    for (let n = 1; n <= MAX_ROWS; n++) {
        const widget = findWidget(node, VALUE + n);
        if (widget && setHidden(widget, n > count && !isInputLinked(node, VALUE + n))) {
            changed = true;
        }
        const slot = inputSlot(node, n);
        if (slot >= 0) {
            const label = rowLabel(node, n);
            if (node.inputs[slot].label !== label) {
                node.inputs[slot].label = label;
                changed = true;
            }
        }
    }
    if (changed) refit(node);
    return count;
}

/* ------------------------------------------------------------------ */
/*  Queue expansion — one Queue click becomes one job per combination  */
/* ------------------------------------------------------------------ */

export const CONFIRM_ABOVE = 20;
const ROW_KEY = "pd_wedge_row";
const JOB_KEY = "pd_wedge_job";
const TOTAL_KEY = "pd_wedge_total";
const PREVIEW_KEY = "pd_wedge_preview";
const SOURCE_INPUTS = ["images", "video", "alpha"];

/** The unwrapped ``api.queuePrompt``, for prompts that must not be expanded. */
let queueOnce = null;

function hasWedge(output) {
    return Object.values(output ?? {}).some(n => n?.class_type === "PDWedge");
}

/**
 * Ask the server for the jobs of an API prompt (see nodes/wedge.py).
 * On failure the body is ``{error, node_id, input_name}``.
 */
export async function fetchPlan(output, outputs) {
    const response = await api.fetchApi("/pipedream/wedge/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: output, outputs: outputs?.length ? outputs : null }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) return { error: body.error || `Wedge plan failed (${response.status})`, node_id: body.node_id, input_name: body.input_name };
    return body;
}

/**
 * A queue response that rejects the prompt the way ComfyUI's validation
 * does, so the app marks the wedge and shows the error on it.
 */
function rejection(output, plan) {
    const id = plan.node_id ?? Object.keys(output).find(k => output[k].class_type === "PDWedge");
    toast("error", plan.error);
    return {
        node_errors: {
            [id]: {
                errors: [{ type: "custom_validation_failed", message: plan.error, details: plan.error,
                          extra_info: { input_name: plan.input_name ?? "token" } }],
                dependent_outputs: [],
                class_type: "PDWedge",
            },
        },
    };
}

/** Copy of ``output`` with each wedge set to its row for this job. */
export function applyJob(output, rows, job, total) {
    const copy = { ...output };
    for (const [id, row] of Object.entries(rows)) {
        copy[id] = {
            ...copy[id],
            inputs: { ...copy[id].inputs, [ROW_KEY]: row, [JOB_KEY]: job, [TOTAL_KEY]: total },
        };
    }
    return copy;
}

function describe(plan) {
    return plan.axes
        .map(a => `${a.tokens.join(" + ")} (${a.length})`)
        .join(" × ");
}

async function confirmJobs(plan) {
    const message = `The wedges make ${plan.total} jobs: ${describe(plan)}. Queue them all?`;
    const dialog = app.extensionManager?.dialog;
    if (dialog?.confirm) return !!(await dialog.confirm({ title: "PD Wedge", message }));
    return window.confirm(message);
}

function toast(severity, detail) {
    app.extensionManager?.toast?.add({ severity, summary: "PD Wedge", detail, life: 4000 });
}

/**
 * Wrap ``api.queuePrompt``: a prompt with wedges is queued once per job.
 *
 * The prompt is built once by the app (so every job has the same seed)
 * and copied per job.  ``number`` -1 queues at the front, so the jobs are
 * sent in reverse to keep the first wedge varying fastest in the queue.
 * Returns the last job's response; declining the confirmation queues
 * nothing, and a wedge error queues nothing and marks the wedge.
 */
function wrapQueuePrompt() {
    const original = api.queuePrompt;
    queueOnce = (number, data, options) => original.call(api, number, data, options);
    api.queuePrompt = async function (number, data, options) {
        if (!hasWedge(data?.output)) return original.call(this, number, data, options);
        const plan = await fetchPlan(data.output, options?.partialExecutionTargets);
        if (plan.error) return rejection(data.output, plan);
        if (!plan.axes.length) return original.call(this, number, data, options);
        if (plan.total > CONFIRM_ABOVE && !(await confirmJobs(plan))) {
            return { node_errors: {} };
        }
        const order = [...plan.jobs.keys()];
        if (number === -1) order.reverse();
        let response;
        for (const job of order) {
            const output = applyJob(data.output, plan.jobs[job], job, plan.total);
            response = await original.call(this, number, { ...data, output }, options);
        }
        toast("info", `Queued ${plan.total} jobs: ${describe(plan)}`);
        return response;
    };
}

/* ------------------------------------------------------------------ */
/*  Preview — list every job's path on PD Save without running       */
/* ------------------------------------------------------------------ */

function isLink(value) {
    return Array.isArray(value) && value.length === 2 && Number.isInteger(value[1]);
}

/** ``roots`` and every node they read from. */
export function ancestors(output, roots) {
    const seen = new Set();
    const stack = [...roots];
    while (stack.length) {
        const id = String(stack.pop());
        if (seen.has(id) || !output[id]) continue;
        seen.add(id);
        for (const value of Object.values(output[id].inputs ?? {})) {
            if (isLink(value)) stack.push(value[0]);
        }
    }
    return seen;
}

/**
 * The preview prompt for PD Save ``id``: its images/video/alpha are
 * unlinked and only what it still reads from is kept (context, wedges,
 * whatever feeds their text).  Wedges are flagged so they compute none of
 * their row inputs, and PD Save gets the request it lists paths for.
 */
export function previewPrompt(output, id, request) {
    const target = { ...output[id], inputs: { ...output[id].inputs } };
    for (const name of SOURCE_INPUTS) delete target.inputs[name];
    target.inputs[PREVIEW_KEY] = JSON.stringify(request);
    const source = { ...output, [id]: target };
    const pruned = {};
    for (const key of ancestors(source, [id])) {
        pruned[key] = source[key].class_type === "PDWedge"
            ? { ...source[key], inputs: { ...source[key].inputs, [PREVIEW_KEY]: true } }
            : source[key];
    }
    return pruned;
}

/** Prompt id of a graph node (``outer:inner`` inside subgraphs). */
function promptId(output, node) {
    const id = String(node.id);
    if (output[id]?.class_type === node.comfyClass) return id;
    return Object.keys(output).find(k => k.endsWith(`:${id}`) && output[k].class_type === node.comfyClass);
}

/**
 * Put the preview text in PD Save's panel when the preview prompt runs.
 *
 * The app only routes results of prompts it queued itself, so this
 * listens for the preview's own ``executed`` event.  The listener starts
 * before the prompt is sent (a small preview can finish before the queue
 * request returns); events are kept until ``watch(promptId)`` names the
 * prompt.  Returns ``{watch, stop}``.
 */
function listenForPreview(node, id) {
    const seen = [];
    let target = null;
    const show = (detail) => {
        if (String(detail.node) !== id && String(detail.display_node) !== id) return false;
        const text = detail.output?.token_reference?.[0];
        const panel = findWidget(node, "token_display");
        if (text && panel) panel.value = text;
        node.setDirtyCanvas?.(true, true);
        return true;
    };
    const onExecuted = ({ detail }) => {
        if (!detail) return;
        if (target === null) seen.push(detail);
        else if (detail.prompt_id === target && show(detail)) stop();
    };
    const onError = ({ detail }) => {
        if (target !== null && detail?.prompt_id === target) stop();
    };
    const stop = () => {
        api.removeEventListener("executed", onExecuted);
        api.removeEventListener("execution_error", onError);
        clearTimeout(timer);
    };
    const timer = setTimeout(stop, 120000);
    api.addEventListener("executed", onExecuted);
    api.addEventListener("execution_error", onError);
    return {
        watch(promptIdValue) {
            target = promptIdValue;
            if (seen.some(d => d.prompt_id === target && show(d))) stop();
        },
        stop,
    };
}

async function previewWedge(node) {
    try {
        const { output, workflow } = await app.graphToPrompt();
        const id = promptId(output, node);
        if (!id) {
            toast("warn", "This PD Save is bypassed or not part of the prompt.");
            return;
        }
        const [all, own] = await Promise.all([fetchPlan(output), fetchPlan(output, [id])]);
        const failed = all.error ? all : own.error ? own : null;
        if (failed) {
            toast("error", failed.error);
            return;
        }
        const request = { total: all.total, axes: own.axes.map(a => ({ tokens: a.tokens, length: a.length })) };
        const send = queueOnce ?? ((n, d) => api.queuePrompt(n, d));
        const listener = listenForPreview(node, id);
        try {
            const response = await send(0, { output: previewPrompt(output, id, request), workflow });
            if (response?.prompt_id) listener.watch(response.prompt_id);
            else listener.stop();
        } catch (error) {
            listener.stop();
            throw error;
        }
    } catch (error) {
        toast("error", `Preview failed: ${error.message ?? error}`);
    }
}

app.registerExtension({
    name: "Pipedream.Wedge",

    setup() {
        wrapQueuePrompt();
    },

    async nodeCreated(node) {
        if (SAVE_CLASSES.includes(node.comfyClass)) {
            const button = node.addWidget("button", "preview wedge", null, () => previewWedge(node),
                                          { serialize: false });
            button.serialize = false;
            button.tooltip = "List the path of every job (wedge rows) in the panel below "
                + "without running the graph. Shows the job count and clashing paths.";
            return;
        }
        if (node.comfyClass !== "PDWedge") return;
        for (let n = 1; n <= MAX_ROWS; n++) {
            const widget = findWidget(node, VALUE + n);
            if (widget) chain(widget, "callback", () => syncRows(node));
        }
        chain(node, "onConnectionsChange", () => syncRows(node));
        chain(node, "onConfigure", () => syncRows(node));
        syncRows(node);
    },
});
