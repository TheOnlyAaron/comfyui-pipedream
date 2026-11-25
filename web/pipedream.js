import { app } from "../../scripts/app.js";
import { addReadOnlyText, chain, refit, showOutputText } from "./pd_common.js";

/* ------------------------------------------------------------------ */
/*  Read-only text panels: PD Output token reference, PD Load info,    */
/*  PD Tokens To String result and PD EXR Metadata Get listing (each   */
/*  with a "preview" button that runs just that node and its inputs).  */
/* ------------------------------------------------------------------ */

const TEXT_PANELS = {
    PDOutput: ["token_display", "Token reference appears after execution...", "token_reference", 100],
    PDLoad: ["load_display", "What was loaded appears after execution...", "load_info", 70],
    PDTokensToString: ["resolved_display", "Press preview to see the resolved text...",
                       "resolved_text", 50],
    PDExrMetadataGet: ["metadata_display", "Press preview to list the metadata...",
                       "metadata_text", 160],
};
const PREVIEW = {
    PDTokensToString: "Run just this node and its inputs to see the resolved text below.",
    PDExrMetadataGet: "Run just this node and its inputs to list the metadata below.",
};

app.registerExtension({
    name: "Pipedream.TextPanels",

    async nodeCreated(node) {
        const panel = TEXT_PANELS[node.comfyClass];
        if (!panel) return;
        const [name, placeholder, key, minHeight] = panel;
        if (PREVIEW[node.comfyClass]) {
            const button = node.addWidget("button", "preview", null,
                () => app.queuePrompt(0, 1, [String(node.id)]), { serialize: false });
            button.serialize = false;
            button.tooltip = PREVIEW[node.comfyClass];
        }
        showOutputText(node, addReadOnlyText(node, name, placeholder, minHeight), key);
    },
});

/* ------------------------------------------------------------------ */
/*  Pipedream.Switch — auto-growing input slots                       */
/* ------------------------------------------------------------------ */

const SWITCH_MIN = 2;
const SWITCH_MAX = 8;
const SWITCH_PREFIX = "input_";

function switchSlots(node) {
    return (node.inputs || []).filter(inp => inp.name.startsWith(SWITCH_PREFIX));
}

function highestConnected(node) {
    let highest = -1;
    (node.inputs || []).forEach((inp, slot) => {
        if (inp.name.startsWith(SWITCH_PREFIX) && node.isInputConnected(slot)) {
            highest = Math.max(highest, parseInt(inp.name.slice(SWITCH_PREFIX.length), 10));
        }
    });
    return highest;
}

/** Keep one spare slot after the highest connected input, within [MIN, MAX]. */
function syncSwitchSlots(node) {
    const before = switchSlots(node).length;
    const target = Math.min(SWITCH_MAX, Math.max(SWITCH_MIN, highestConnected(node) + 1));

    while (switchSlots(node).length < target) {
        node.addInput(SWITCH_PREFIX + (switchSlots(node).length + 1), "*");
    }
    while (switchSlots(node).length > target) {
        const slots = switchSlots(node);
        const idx = node.inputs.indexOf(slots[slots.length - 1]);
        if (idx === -1 || node.isInputConnected(idx)) break;
        node.removeInput(idx);
    }

    if (switchSlots(node).length !== before) refit(node);
}

app.registerExtension({
    name: "Pipedream.Switch",

    async nodeCreated(node) {
        if (node.comfyClass !== "PDSwitch") return;
        // The Python node declares all 8 optional inputs; trim right away,
        // and re-sync once a saved workflow's links are restored.
        chain(node, "onConnectionsChange", () => syncSwitchSlots(node));
        chain(node, "onConfigure", () => syncSwitchSlots(node));
        syncSwitchSlots(node);
    },
});
