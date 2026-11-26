/**
 * Smoke test of the example workflows against a running ComfyUI.
 *
 *     node tools/smoke_workflows.mjs [http://127.0.0.1:8188] [--no-run]
 *
 * For each workflows/<NN_name>/workflow.json, in the Nodes 2.0 renderer and
 * the classic canvas:
 *   - loads it and fails on page errors or node types ComfyUI doesn't know;
 *   - queues it (once, classic canvas) unless --no-run or it needs files
 *     ComfyUI doesn't have (a model loader whose choice is missing), and
 *     fails if the queue reports an execution error.
 * Exits 1 when any workflow fails.  Needs Node.js and Playwright with
 * Chromium.  Restores the renderer setting when done.  tools/ is left out
 * of the registry package (.comfyignore).
 */

import { createRequire } from "node:module";
import { readdirSync, readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
const BASE = args.find(a => a.startsWith("http")) ?? "http://127.0.0.1:8188";
const RUN = !args.includes("--no-run");

const workflows = readdirSync(join(ROOT, "workflows"), { withFileTypes: true })
    .filter(d => d.isDirectory() && existsSync(join(ROOT, "workflows", d.name, "workflow.json")))
    .map(d => d.name).sort();

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
const pageErrors = [];
page.on("pageerror", e => pageErrors.push(String(e)));
await page.goto(BASE, { waitUntil: "networkidle" });
await page.waitForFunction(() => window.app && window.app.graph, null, { timeout: 60000 });
const originalVue = await page.evaluate(() => window.app.extensionManager.setting.get("Comfy.VueNodes.Enabled"));

let failures = 0;
for (const name of workflows) {
    const workflow = JSON.parse(readFileSync(join(ROOT, "workflows", name, "workflow.json"), "utf8"));
    const result = { name, load: {}, run: "skipped" };
    for (const vue of [true, false]) {
        pageErrors.length = 0;
        const load = await page.evaluate(async ({ workflow, vue }) => {
            await window.app.extensionManager.setting.set("Comfy.VueNodes.Enabled", vue);
            await window.app.loadGraphData(workflow);
            await new Promise(r => setTimeout(r, 800));
            const unknown = window.app.graph._nodes
                .filter(n => n.type !== "Note" && n.type !== "MarkdownNote" && !LiteGraph.registered_node_types[n.type])
                .map(n => n.type);
            return { nodes: window.app.graph._nodes.length, unknown };
        }, { workflow, vue });
        load.errors = [...pageErrors];
        result.load[vue ? "nodes2" : "classic"] = load;
        if (load.unknown.length || load.errors.length) failures++;
    }
    if (RUN) {
        const outcome = await page.evaluate(async () => {
            const { output } = await window.app.graphToPrompt();
            const info = await (await fetch("/object_info")).json();
            const missing = [];
            for (const node of Object.values(output)) {
                const spec = info[node.class_type]?.input?.required ?? {};
                for (const [input, value] of Object.entries(node.inputs)) {
                    const def = spec[input];
                    const choices = Array.isArray(def?.[0]) ? def[0] : (def?.[0] === "COMBO" ? def[1]?.options : null);
                    if (Array.isArray(choices) && /_name$/.test(input) && !choices.includes(value)) {
                        missing.push(`${node.class_type}.${input}=${value}`);
                    }
                }
            }
            if (missing.length) return { status: "skipped", reason: `needs ${missing.join(", ")}` };
            const errors = [], ids = [];
            const api = (await import("/scripts/api.js")).api;
            const queue = api.queuePrompt;
            api.queuePrompt = async function (...args) {
                try {
                    const res = await queue.apply(this, args);
                    if (res?.prompt_id) ids.push(res.prompt_id);
                    return res;
                } catch (e) {
                    errors.push(`rejected: ${e?.message ?? e}`);
                    throw e;
                }
            };
            try {
                await window.app.queuePrompt(0, 1);
            } catch (e) {
                errors.push(String(e?.message ?? e));
            }
            api.queuePrompt = queue;
            for (let i = 0; i < 180 && ids.length; i++) {
                await new Promise(r => setTimeout(r, 1000));
                const q = await (await fetch("/queue")).json();
                if (!q.queue_running.length && !q.queue_pending.length) break;
            }
            for (const id of ids) {
                const h = (await (await fetch(`/history/${id}`)).json())[id];
                const status = h?.status?.status_str;
                if (status !== "success") errors.push(`prompt ${id.slice(0, 8)}: ${status ?? "no result"}`);
            }
            if (!ids.length && !errors.length) errors.push("nothing was queued");
            return errors.length ? { status: "failed", reason: errors.join(" | ") } : { status: "ok", reason: `${ids.length} queue call(s)` };
        });
        result.run = outcome.status + (outcome.reason ? ` (${outcome.reason})` : "");
        if (outcome.status === "failed") failures++;
    }
    const l = result.load;
    console.log(`${name}: nodes2 ${l.nodes2.nodes} nodes${l.nodes2.unknown.length ? ", UNKNOWN " + l.nodes2.unknown : ""}${l.nodes2.errors.length ? ", ERRORS " + l.nodes2.errors : ""}; ` +
                `classic${l.classic.unknown.length ? " UNKNOWN " + l.classic.unknown : ""}${l.classic.errors.length ? " ERRORS " + l.classic.errors : " ok"}; run: ${result.run}`);
}

await page.evaluate(async (v) => { await window.app.extensionManager.setting.set("Comfy.VueNodes.Enabled", v); }, originalVue);
await browser.close();
console.log(failures ? `${failures} problem(s)` : "all workflows OK");
process.exit(failures ? 1 : 0);
