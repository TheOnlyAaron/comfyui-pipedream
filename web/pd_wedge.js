import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { chain, findWidget, isInputLinked, refit, setHidden } from "./pd_common.js";

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

app.registerExtension({
    name: "Pipedream.Wedge",

    setup() {
        wrapQueuePrompt();
    },

    async nodeCreated(node) {
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
