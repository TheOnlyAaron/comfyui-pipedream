import { app } from "../../scripts/app.js";

/* ------------------------------------------------------------------ */
/*  Pipedream.ProjectContext — version auto-increment and reset       */
/* ------------------------------------------------------------------ */

const NODE_CLASS = "PDProjectContext";
const DEFAULT_VERSION = "v001";
const VERSION_RE = /^(.*?)(\d+)$/;

/**
 * Split a version string into a prefix and a trailing number.
 *
 * "v001" -> { prefix: "v", number: 1, width: 3 }
 * "take_0042" -> { prefix: "take_", number: 42, width: 4 }
 *
 * @param {string} version
 * @returns {{prefix: string, number: number, width: number} | null}
 *          null when the string has no trailing digits.
 */
export function parseVersion(version) {
    const match = VERSION_RE.exec(String(version ?? "").trim());
    if (!match) return null;
    return {
        prefix: match[1],
        number: parseInt(match[2], 10),
        width: match[2].length,
    };
}

/**
 * Format a prefix and number, zero-padding the number to ``width``.
 * Numbers wider than ``width`` are kept intact ("v999" + 1 -> "v1000").
 */
export function formatVersion(prefix, number, width) {
    return prefix + String(number).padStart(width, "0");
}

/**
 * Return the next version, preserving prefix and padding width.
 * Strings without trailing digits are returned unchanged.
 *
 * @param {string} version
 * @returns {string}
 */
export function incrementVersion(version) {
    const parsed = parseVersion(version);
    if (!parsed) return version;
    return formatVersion(parsed.prefix, parsed.number + 1, parsed.width);
}

/**
 * Return the first version in the same style as ``version``.
 *
 * "v017" -> "v001", "take_0042" -> "take_0001".  Empty or unparseable
 * strings fall back to "v001".
 *
 * @param {string} version
 * @returns {string}
 */
export function resetVersion(version) {
    const parsed = parseVersion(version);
    if (!parsed) return DEFAULT_VERSION;
    return formatVersion(parsed.prefix, 1, parsed.width);
}

/** True when ``node`` is a PD Project Context node. */
export function isProjectContext(node) {
    return (node?.comfyClass ?? node?.type) === NODE_CLASS;
}

function findWidget(node, name) {
    return node?.widgets?.find(w => w.name === name);
}

/** True when the widget's input socket is connected to an upstream node. */
function isWidgetLinked(node, name) {
    return (node?.inputs ?? []).some((inp, slot) => {
        if (inp.widget?.name !== name && inp.name !== name) return false;
        // isInputConnected() is the current API; reading input.link logs a
        // deprecation warning on recent (Nodes 2.0) frontends.
        if (typeof node.isInputConnected === "function") return node.isInputConnected(slot);
        return inp.link != null;
    });
}

function setVersion(node, value) {
    const widget = findWidget(node, "version");
    if (!widget || widget.value === value) return false;
    widget.value = value;
    widget.callback?.(value);
    node.setDirtyCanvas?.(true, true);
    return true;
}

/**
 * Advance a node's version widget if ``auto_increment_version`` is on.
 *
 * Called once per queued prompt, after that prompt has been built, so
 * batch count N yields N consecutive versions.  Skipped when the version
 * comes in through a link, since the widget value is not what runs.
 *
 * @returns {boolean} true if the version changed.
 */
export function bumpNodeVersion(node) {
    if (!findWidget(node, "auto_increment_version")?.value) return false;
    if (isWidgetLinked(node, "version")) return false;
    const widget = findWidget(node, "version");
    if (!widget) return false;
    return setVersion(node, incrementVersion(widget.value));
}

/**
 * Reset a node's version widget to its first version.
 *
 * @returns {boolean} true if the version changed.
 */
export function resetNodeVersion(node) {
    const widget = findWidget(node, "version");
    if (!widget) return false;
    return setVersion(node, resetVersion(widget.value));
}

/**
 * Collect every PD Project Context node in ``graph`` and its subgraphs.
 *
 * Handles both the legacy LiteGraph ``_nodes`` array and the newer
 * ``nodes`` / ``subgraphs`` API.  Each subgraph definition is visited
 * once, even when several subgraph nodes share it.
 *
 * @param {object} graph root graph
 * @returns {object[]}
 */
export function collectProjectContexts(graph) {
    const found = [];
    const visited = new Set();

    function walk(g) {
        if (!g || visited.has(g)) return;
        visited.add(g);
        for (const node of g.nodes ?? g._nodes ?? []) {
            if (isProjectContext(node)) found.push(node);
            if (node.subgraph) walk(node.subgraph);
        }
        for (const sub of g.subgraphs?.values?.() ?? []) walk(sub);
    }

    walk(graph);
    return found;
}

/** Reset every PD Project Context in the workflow, after a confirm(). */
function resetAllVersions() {
    const nodes = collectProjectContexts(app.rootGraph ?? app.graph);
    if (nodes.length === 0) return;
    const label = nodes.length === 1 ? "node" : "nodes";
    const ok = window.confirm(
        `Reset the version on ${nodes.length} PD Project Context ${label} ` +
        `in this workflow (including subgraphs) back to their first version?`,
    );
    if (!ok) return;
    for (const node of nodes) resetNodeVersion(node);
    app.canvas?.setDirty?.(true, true);
}

app.registerExtension({
    name: "Pipedream.ProjectContext",

    async nodeCreated(node) {
        if (!isProjectContext(node)) return;

        const versionWidget = findWidget(node, "version");
        if (versionWidget) {
            const origAfterQueued = versionWidget.afterQueued;
            versionWidget.afterQueued = function (...args) {
                origAfterQueued?.apply(this, args);
                bumpNodeVersion(node);
            };
        }

        const buttons = [
            ["reset version", () => resetNodeVersion(node)],
            ["reset all versions in graph", resetAllVersions],
        ];
        for (const [label, callback] of buttons) {
            const button = node.addWidget("button", label, null, callback, {
                serialize: false,
            });
            button.serialize = false;
        }
    },

    getCanvasMenuItems() {
        return [
            null,
            { content: "Pipedream: reset all versions", callback: resetAllVersions },
        ];
    },
});
