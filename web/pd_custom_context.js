import { app } from "../../scripts/app.js";

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

function isLinked(node, widget) {
    return !!node.inputs?.some(inp => inp.widget?.name === widget.name && inp.link != null);
}

function setWidgetHidden(widget, hidden) {
    if (hidden) {
        if (!widget.hidden) widget._pdComputeSize = widget.computeSize;
        widget.hidden = true;
        widget.computeSize = () => [0, -4];
    } else if (widget.hidden) {
        widget.hidden = false;
        if (widget._pdComputeSize) widget.computeSize = widget._pdComputeSize;
        else delete widget.computeSize;
        delete widget._pdComputeSize;
    }
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
        nameLinked: isLinked(node, p.name),
        valueLinked: isLinked(node, p.value),
    })));

    let changed = false;
    pairs.forEach((p, i) => {
        const hide = i >= count;
        for (const w of [p.name, p.value]) {
            if (!!w.hidden !== hide) {
                setWidgetHidden(w, hide);
                changed = true;
            }
        }
    });

    if (changed && node.computeSize && node.setSize) {
        node.setSize([node.size[0], node.computeSize()[1]]);
        node.setDirtyCanvas?.(true, true);
    }
    return count;
}

app.registerExtension({
    name: "Pipedream.CustomContext",

    async nodeCreated(node) {
        if (node.comfyClass !== "PDCustomContext") return;

        for (const { name, value } of getPairWidgets(node)) {
            for (const w of [name, value]) {
                const origCallback = w.callback;
                w.callback = function (...args) {
                    const r = origCallback?.apply(this, args);
                    syncPairs(node);
                    return r;
                };
            }
        }

        const origOnConfigure = node.onConfigure;
        node.onConfigure = function (info) {
            const r = origOnConfigure?.call(this, info);
            syncPairs(this);
            return r;
        };

        const origOnConnectionsChange = node.onConnectionsChange;
        node.onConnectionsChange = function (...args) {
            const r = origOnConnectionsChange?.apply(this, args);
            syncPairs(this);
            return r;
        };

        syncPairs(node);
    },
});
