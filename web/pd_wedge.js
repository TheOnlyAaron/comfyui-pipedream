import { app } from "../../scripts/app.js";
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

app.registerExtension({
    name: "Pipedream.Wedge",

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
