import { app } from "../../scripts/app.js";
import { chain, isInputLinked, refit, setHidden } from "./pd_common.js";

/* ------------------------------------------------------------------ */
/*  Pipedream.CustomContext — auto-expanding key/value pairs          */
/* ------------------------------------------------------------------ */

export const MAX_PAIRS = 10;

/**
 * Number of name/value pairs that should be visible.
 *
 * Every pair up to the last one in use stays visible (gaps are kept so
 * nothing jumps around), plus one empty pair after it once that pair has
 * a name. Pairs past that collapse. Always at least 1, at most `max`.
 *
 * @param {{name?: string, value?: string, nameLinked?: boolean,
 *          valueLinked?: boolean}[]} pairs  State of each pair, in order.
 * @param {number} [max]
 * @returns {number}
 */
export function visiblePairCount(pairs, max = MAX_PAIRS) {
    let last = -1;
    let lastNamed = false;
    pairs.slice(0, max).forEach((p, i) => {
        const named = !!p.name || !!p.nameLinked;
        if (named || !!p.value || !!p.valueLinked) {
            last = i;
            lastNamed = named;
        }
    });
    if (last < 0) return 1;
    return Math.min(max, last + 1 + (lastNamed ? 1 : 0));
}

/**
 * Collect the name/value widgets of a PD Custom Context node, by pair.
 *
 * @returns {{name: object, value: object}[]} Only pairs with both widgets.
 */
export function getPairWidgets(node) {
    const pairs = [];
    for (let i = 1; i <= MAX_PAIRS; i++) {
        const name = node.widgets?.find(w => w.name === `custom_${i}_name`);
        const value = node.widgets?.find(w => w.name === `custom_${i}_value`);
        if (!name || !value) break;
        pairs.push({ name, value });
    }
    return pairs;
}

/**
 * Show the pairs that should be visible, hide the rest and refit the
 * node height. Widgets are never removed, so serialization and
 * `widgets_values` order are unaffected.
 *
 * @returns {number} The number of visible pairs.
 */
export function syncPairs(node) {
    const pairs = getPairWidgets(node);
    const count = visiblePairCount(pairs.map(p => ({
        name: p.name.value,
        value: p.value.value,
        nameLinked: isInputLinked(node, p.name.name),
        valueLinked: isInputLinked(node, p.value.name),
    })));

    let changed = false;
    pairs.forEach((p, i) => {
        const hide = i >= count;
        for (const w of [p.name, p.value]) {
            if (setHidden(w, hide)) changed = true;
        }
    });

    if (changed) refit(node);
    return count;
}

app.registerExtension({
    name: "Pipedream.CustomContext",

    async nodeCreated(node) {
        if (node.comfyClass !== "PDCustomContext") return;
        for (const { name, value } of getPairWidgets(node)) {
            for (const w of [name, value]) chain(w, "callback", () => syncPairs(node));
        }
        chain(node, "onConfigure", () => syncPairs(node));
        chain(node, "onConnectionsChange", () => syncPairs(node));
        syncPairs(node);
    },
});
