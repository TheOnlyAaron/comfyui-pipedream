import { app } from "../../scripts/app.js";
import { chain, findWidget, showWidgets } from "./pd_common.js";

/* ------------------------------------------------------------------ */
/*  Pipedream.Video — PD Video Frame / PD Image Frame show the index   */
/*  widget only when mode is "index" (never hidden while linked).      */
/* ------------------------------------------------------------------ */

const NODE_CLASSES = ["PDVideoFrame", "PDImageFrame"];

function sync(node) {
    showWidgets(node, { index: findWidget(node, "mode")?.value === "index" });
}

app.registerExtension({
    name: "Pipedream.Video",

    async nodeCreated(node) {
        if (!NODE_CLASSES.includes(node.comfyClass)) return;
        const mode = findWidget(node, "mode");
        if (mode) chain(mode, "callback", () => sync(node));
        chain(node, "onConfigure", () => sync(node));
        chain(node, "onConnectionsChange", () => sync(node));
        sync(node);
    },
});
