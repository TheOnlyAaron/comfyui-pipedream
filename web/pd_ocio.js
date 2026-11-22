import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { chain, findWidget, showWidgets } from "./pd_common.js";

/* ------------------------------------------------------------------ */
/*  Pipedream.OCIO — dynamic dropdowns for PD OCIO Transform/Display.  */
/*                                                                     */
/*  The backend lists the default config's names at load time.  When   */
/*  config or config_path changes, the selected config's colorspaces,  */
/*  displays, views and looks are fetched from                         */
/*  /pipedream/ocio/options and swapped into the combos; view follows  */
/*  display.  A value that is still valid is kept, otherwise the       */
/*  config's default is used.  config_path shows only for "custom      */
/*  file".                                                             */
/*                                                                     */
/*  Nodes 2.0 first: its dropdowns only notice new values when a new   */
/*  options object is assigned (widget.options = {...}); mutating      */
/*  widget.options.values in place updates the classic canvas only.    */
/* ------------------------------------------------------------------ */

const CUSTOM = "custom file";
const MIN_WIDTH = 400;  // room for long colorspace names
const NODES = {
    PDOCIOTransform: { colorspaces: ["in_colorspace", "out_colorspace"], look: true },
    PDOCIODisplay: { colorspaces: ["in_colorspace"], display: true },
};

async function fetchOptions(config, path) {
    const query = new URLSearchParams({ config, path: config === CUSTOM ? path : "" });
    const response = await api.fetchApi(`/pipedream/ocio/options?${query}`);
    const data = await response.json();
    if (!response.ok || data.error) throw new Error(data.error ?? response.statusText);
    return data;
}

/** Replace a combo's values; keep its value if still valid (aliases/roles map to their name), else use fallback. */
function setComboValues(node, name, values, fallback, lookup = {}) {
    const widget = findWidget(node, name);
    if (!widget || !values?.length) return;
    // Assign a new options object: Nodes 2.0 only sees the change through the options setter.
    widget.options = { ...widget.options, values: [...values] };
    let value = widget.value;
    if (!values.includes(value)) value = lookup[value];
    if (!values.includes(value)) value = values.includes(fallback) ? fallback : values[0];
    if (value !== widget.value) widget.value = value;
}

function updateViews(node) {
    const opts = node._pdOcio;
    const display = findWidget(node, "display")?.value;
    if (!opts || !(display in opts.views)) return;
    setComboValues(node, "view", opts.views[display], opts.default_views?.[display]);
    node.setDirtyCanvas?.(true, true);
}

function applyOptions(node, opts) {
    const spec = NODES[node.comfyClass];
    node._pdOcio = opts;
    const lookup = { ...opts.aliases };
    for (const [role, cs] of Object.entries(opts.roles ?? {})) lookup[role] ??= cs;
    for (const name of spec.colorspaces) {
        setComboValues(node, name, opts.colorspaces, opts.defaults[name], lookup);
    }
    if (spec.look) setComboValues(node, "look", ["none", ...opts.looks], "none");
    if (spec.display) {
        setComboValues(node, "display", opts.displays, opts.defaults.display);
        updateViews(node);
    }
    node.setDirtyCanvas?.(true, true);
}

/** Fetch the selected config's names and update the combos; stale responses are dropped. */
async function refresh(node) {
    const config = findWidget(node, "config")?.value;
    const path = findWidget(node, "config_path")?.value ?? "";
    if (!config || (config === CUSTOM && !path.trim())) return;
    const ticket = (node._pdOcioTicket ?? 0) + 1;
    node._pdOcioTicket = ticket;
    try {
        const opts = await fetchOptions(config, path);
        if (node._pdOcioTicket === ticket) applyOptions(node, opts);
    } catch (error) {
        if (node._pdOcioTicket === ticket) console.warn(`[Pipedream] OCIO config '${config === CUSTOM ? path : config}':`, error.message);
    }
}

function syncVisibility(node) {
    showWidgets(node, { config_path: findWidget(node, "config")?.value === CUSTOM });
}

app.registerExtension({
    name: "Pipedream.OCIO",

    async nodeCreated(node) {
        if (!NODES[node.comfyClass]) return;

        const config = findWidget(node, "config");
        if (config) {
            chain(config, "callback", () => {
                syncVisibility(node);
                refresh(node);
            });
        }
        const path = findWidget(node, "config_path");
        if (path) {
            let timer;
            chain(path, "callback", () => {
                clearTimeout(timer);
                timer = setTimeout(() => refresh(node), 400);
            });
        }
        const display = findWidget(node, "display");
        if (display) chain(display, "callback", () => updateViews(node));

        chain(node, "onConfigure", () => {
            syncVisibility(node);
            refresh(node);
        });

        if (node.size?.[0] < MIN_WIDTH) node.setSize?.([MIN_WIDTH, node.size[1]]);
        syncVisibility(node);
        // Runs after a loaded workflow's values are configured onto the widgets.
        setTimeout(() => refresh(node), 0);
    },
});
