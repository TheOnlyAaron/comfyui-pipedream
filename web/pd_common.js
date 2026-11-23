/**
 * Shared helpers for the Pipedream frontend extensions.
 *
 * Written for the Nodes 2.0 (Vue) renderer first: ``widget.hidden`` is
 * reactive there.  Both renderers size the node from ``node.size``, so
 * after hiding widgets the node is refitted to ``computeSize()``, with
 * hidden widgets collapsed to no height.
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

/** Refit the node height to its visible widgets and redraw. */
export function refit(node) {
    if (node.computeSize && node.setSize) {
        node.setSize([node.size[0], node.computeSize()[1]]);
    }
    node.setDirtyCanvas?.(true, true);
}

/** Hide or show a widget, collapsing its height while hidden. */
export function setHidden(widget, hidden) {
    if (hidden === !!widget.hidden) return false;
    if (hidden) {
        widget._pdComputeSize = widget.computeSize;
        widget.computeSize = () => [0, -4];
    } else if (widget._pdComputeSize) {
        widget.computeSize = widget._pdComputeSize;
    } else {
        delete widget.computeSize;
    }
    if (!hidden) delete widget._pdComputeSize;
    widget.hidden = hidden;
    return true;
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
        if (setHidden(widget, !shown && !isInputLinked(node, name))) changed = true;
    }
    if (changed) refit(node);
    return changed;
}

/** Type and tooltip of input or output ``name`` from the node's Python definition. */
function slotSpec(node, kind, name) {
    const def = node.constructor?.nodeData;
    if (!def) return null;
    if (kind === "input") {
        const spec = def.input?.required?.[name] ?? def.input?.optional?.[name];
        return spec ? { type: spec[0], extra: { tooltip: spec[1]?.tooltip } } : null;
    }
    const index = def.output_name?.indexOf(name) ?? -1;
    if (index < 0) return null;
    return { type: def.output[index], extra: { tooltip: def.output_tooltips?.[index] } };
}

/**
 * Show or hide input or output sockets by removing and re-adding them.
 *
 * Frontend 1.59 has no per-slot "hidden" flag: the Vue renderer draws every
 * output and every input without a widget, and the classic canvas draws
 * every slot.  Removing a slot is the only way to hide it.
 *
 * Inputs are sent to the backend by name, and ``removeInput`` shifts the
 * links of later inputs, so any socket input (one without a widget) can be
 * listed; a shown input is appended, which keeps it after the other socket
 * inputs in both renderers.  Outputs are addressed by index, so only the
 * outputs declared last in the Python definition may be listed (in
 * declared order): removing them shifts nothing and re-adding restores
 * their index.  A linked slot is never removed.  Saved workflows omit a
 * hidden slot; the extension shows it again after loading if it applies.
 *
 * @param {"input"|"output"} kind
 * @param {Record<string, boolean>} rules slot name to "should be shown".
 * @returns {boolean} true if any slot changed.
 */
export function showSlots(node, kind, rules) {
    const isInput = kind === "input";
    const slots = () => (isInput ? node.inputs : node.outputs) ?? [];
    let changed = false;
    if (isInput) {
        for (let i = slots().length - 1; i >= 0; i--) {
            const name = slots()[i].name;
            if (name in rules && !rules[name] && !node.isInputConnected(i)) {
                node.removeInput(i);
                changed = true;
            }
        }
    } else {
        for (let i = slots().length - 1; i >= 0; i--) {
            const name = slots()[i].name;
            if (!(name in rules) || rules[name] || node.isOutputConnected(i)) break;
            node.removeOutput(i);
            changed = true;
        }
    }
    for (const [name, shown] of Object.entries(rules)) {
        if (!shown || slots().some(s => s.name === name)) continue;
        const spec = slotSpec(node, kind, name);
        if (!spec) continue;
        if (isInput) node.addInput(name, spec.type, spec.extra);
        else node.addOutput(name, spec.type, spec.extra);
        changed = true;
    }
    if (changed) refit(node);
    return changed;
}

/**
 * Add a read-only, non-serialized multiline text display.
 *
 * A plain <textarea> DOM widget, which both renderers mount.  It has no
 * resize handle of its own: it fills the space the node gives it, so
 * resizing the node resizes the panel (in width and height).  Nodes 2.0
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
        resize: "none",
        height: "100%",
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

const VIDEO_FILE = /\.(mp4|webm|mov|mkv)$/i;

/** Remove the classic canvas' video-preview DOM widget (kept after a switch back to images). */
function clearClassicVideoPreview(node) {
    const widget = findWidget(node, "video-preview");
    if (widget) {
        node.removeWidget(widget);
        widget.onRemove?.();
    }
    node.videoContainer = undefined;
}

/**
 * Show a node's preview as video when it executes with a video file in
 * ``ui.images`` and ``ui.animated``, and as images otherwise.
 *
 * The frontend previews any node with a VIDEO input or output as video
 * unless ``previewMediaType`` says otherwise.  The classic canvas keeps
 * its video player after a switch back to images, so it is removed then.
 */
export function trackPreviewMedia(node) {
    node.previewMediaType = "image";
    chain(node, "onExecuted", function (output) {
        const isVideo = output?.animated?.some(Boolean) &&
            output?.images?.some(i => VIDEO_FILE.test(i?.filename ?? ""));
        this.previewMediaType = isVideo ? "video" : "image";
        if (!isVideo && !globalThis.LiteGraph?.vueNodesMode) clearClassicVideoPreview(this);
    });
}
