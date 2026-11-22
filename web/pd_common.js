/**
 * Shared helpers for the Pipedream frontend extensions.
 *
 * Written for the Nodes 2.0 (Vue) renderer first: ``widget.hidden`` is
 * reactive there and nodes lay themselves out.  The classic canvas skips
 * hidden widgets too; it only needs the node refitted afterwards.
 *
 * ComfyUI loads every file in the web directory, so this module registers
 * nothing; the extensions import it.
 */

export function findWidget(node, name) {
    return node?.widgets?.find(w => w.name === name);
}

/** True when the input called ``name`` (or the input backing widget ``name``) is linked. */
export function isInputLinked(node, name) {
    const slot = node?.inputs?.findIndex(i => i.name === name || i.widget?.name === name) ?? -1;
    return slot >= 0 && node.isInputConnected(slot);
}

/** Wrap ``object[method]`` so ``after`` runs (with the same this/args) after the original. */
export function chain(object, method, after) {
    const original = object[method];
    object[method] = function (...args) {
        const result = original?.apply(this, args);
        after.apply(this, args);
        return result;
    };
}

/** Refit the node height to its visible widgets (classic canvas only) and redraw. */
export function refit(node) {
    if (!globalThis.LiteGraph?.vueNodesMode && node.computeSize && node.setSize) {
        node.setSize([node.size[0], node.computeSize()[1]]);
    }
    node.setDirtyCanvas?.(true, true);
}

/**
 * Show or hide widgets by name, then refit if anything changed.
 *
 * ``rules`` maps widget name to "should be shown".  A widget whose input
 * socket is linked is never hidden.
 *
 * @returns {boolean} true if any widget changed.
 */
export function showWidgets(node, rules) {
    let changed = false;
    for (const [name, shown] of Object.entries(rules)) {
        const widget = findWidget(node, name);
        if (!widget) continue;
        const hidden = !shown && !isInputLinked(node, name);
        if (!!widget.hidden === hidden) continue;
        widget.hidden = hidden;
        changed = true;
    }
    if (changed) refit(node);
    return changed;
}

/**
 * Add a read-only, non-serialized multiline text display.
 *
 * A plain <textarea> DOM widget, which both renderers mount.  Nodes 2.0
 * lays DOM widgets out with CSS and ignores getMinHeight, so the minimum
 * height is also set in CSS.
 */
export function addReadOnlyText(node, name, placeholder, minHeight = 100) {
    const el = document.createElement("textarea");
    el.className = "comfy-multiline-input";
    el.readOnly = true;
    el.placeholder = placeholder ?? "";
    el.spellcheck = false;
    el.wrap = "off";
    Object.assign(el.style, {
        fontFamily: "monospace",
        fontSize: "11px",
        opacity: "0.85",
        width: "100%",
        boxSizing: "border-box",
        resize: "vertical",
        minHeight: `${minHeight}px`,
    });
    const widget = node.addDOMWidget(name, "pd_readonly_text", el, {
        getValue: () => el.value,
        setValue: (v) => { el.value = v ?? ""; },
        getMinHeight: () => minHeight,
        serialize: false,
    });
    widget.serialize = false;
    return widget;
}

/** Fill a read-only text widget from ``output[key][0]`` whenever the node executes. */
export function showOutputText(node, widget, key) {
    chain(node, "onExecuted", (output) => {
        if (output?.[key]?.length > 0) widget.value = output[key][0];
    });
}
