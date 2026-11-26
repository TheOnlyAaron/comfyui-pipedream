import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { chain, findWidget, showWidgets } from "./pd_common.js";

/* ------------------------------------------------------------------ */
/*  Pipedream.Sound — browser sound cues for the PDSound node         */
/*                                                                    */
/*  "node reached": the node returns a ui payload, so the server      */
/*  sends this tab an `executed` event for it and its sound plays     */
/*  right then.  Cached nodes do not execute; with when_cached on,    */
/*  they play from the `execution_cached` event instead.              */
/*                                                                    */
/*  "queue finished" (or a node with nothing connected): queueing a   */
/*  prompt that contains one arms it, and it plays when               */
/*  queue_remaining reaches 0 after work has run (error tone if a     */
/*  prompt failed, nothing if interrupted).                           */
/*                                                                    */
/*  Built-in sounds are WAV files in web/sounds/, played with an       */
/*  <audio> element (rendered from tools/sound_synths.js by            */
/*  tools/render_sounds.mjs).                                          */
/* ------------------------------------------------------------------ */

const NODE_CLASS = "PDSound";
const UI_KEY = "pd_sound";
const CACHED_STAGGER = 0.35;

const BUILT_IN = ["chime", "happy", "sad", "ding", "beeps", "alert", "error"];
const cache = new Map();

/** The <audio> element template for a built-in sound (web/sounds/<name>.wav). */
function builtIn(name) {
    const key = BUILT_IN.includes(name) ? name : "chime";
    if (!cache.has(key)) {
        const audio = new Audio(new URL(`sounds/${key}.wav`, import.meta.url).href);
        audio.preload = "auto";
        cache.set(key, audio);
    }
    return cache.get(key);
}

/** Load every built-in sound so the first cue plays without a fetch delay. */
function preload() {
    BUILT_IN.forEach(builtIn);
}

/**
 * Play a built-in sound after `delay` seconds; unknown names use the chime.
 * Each play uses its own copy, so cues can overlap.
 */
function playBuiltIn(name, volume, delay = 0) {
    const play = () => {
        const audio = builtIn(name).cloneNode();
        audio.volume = Math.max(0, Math.min(1, volume));
        audio.play().catch((err) => console.warn("[Pipedream] Could not play sound:", err));
    };
    if (delay > 0) setTimeout(play, delay * 1000);
    else play();
}

/**
 * Resolve a custom sound URL.  Absolute URLs and root-relative paths are
 * used as-is; anything else is resolved against this extension's web dir
 * (e.g. "sounds/done.wav").
 */
function resolveSoundUrl(url) {
    return new URL(url, import.meta.url).href;
}

/** Play the sound described by node settings (or the error tone) after `delay` seconds. */
export function playSound(settings, isError = false, delay = 0) {
    const raw = Number(settings.volume ?? 0.6);
    const volume = Number.isFinite(raw) ? raw : 0.6;
    if (isError) return playBuiltIn("error", volume, delay);

    const url = String(settings.custom_url || "").trim();
    if (settings.sound === "custom URL" && url) {
        const play = () => {
            const audio = new Audio(resolveSoundUrl(url));
            audio.volume = Math.max(0, Math.min(1, volume));
            audio.play().catch((err) => {
                console.warn("[Pipedream] Could not play custom sound, using the chime:", err);
                playBuiltIn("chime", volume);
            });
        };
        if (delay > 0) setTimeout(play, delay * 1000);
        else play();
        return;
    }
    playBuiltIn(settings.sound, volume, delay);
}

/**
 * Collect the enabled sound nodes of a queued prompt as id -> entry.
 *
 * A node plays on reach only in "node reached" mode with something linked
 * into `value`; otherwise it waits for the queue to finish.
 */
export function collectNodes(output) {
    const nodes = new Map();
    for (const [id, node] of Object.entries(output || {})) {
        if (node?.class_type !== NODE_CLASS || node.inputs?.enabled === false) continue;
        const settings = { ...node.inputs };
        const linked = Array.isArray(settings.value);
        delete settings.value;
        const reached = settings.play_when !== "queue finished" && linked;
        nodes.set(String(id), { settings, mode: reached ? "reached" : "finished" });
    }
    return nodes;
}

/** Make the per-prompt bookkeeping record. */
function newInfo(nodes = new Map()) {
    return { nodes, played: new Set(), cached: new Set(), errorPlayed: false };
}

app.registerExtension({
    name: "Pipedream.Sound",

    async setup() {
        let armed = null;
        let ran = false;
        let hadError = false;
        let interrupted = false;

        const prompts = new Map();
        let pending = null;

        /** Bookkeeping for a prompt id; an unknown id claims the in-flight queue request. */
        const infoFor = (promptId) => {
            const key = String(promptId ?? "");
            let info = prompts.get(key);
            if (!info) {
                info = pending || newInfo();
                pending = null;
                prompts.set(key, info);
            }
            return info;
        };
        const forget = (promptId) => {
            prompts.delete(String(promptId ?? ""));
        };

        const unlock = () => preload();
        window.addEventListener("pointerdown", unlock, { once: true, capture: true });
        window.addEventListener("keydown", unlock, { once: true, capture: true });

        const origQueuePrompt = api.queuePrompt;
        api.queuePrompt = async function (...args) {
            // Arm before the request: a fully cached prompt can finish
            // before the HTTP response arrives.
            const previous = armed;
            let info = null;
            try {
                info = newInfo(collectNodes(args[1]?.output));
                pending = info;
                const finisher = [...info.nodes.values()].find((e) => e.mode === "finished");
                if (finisher) armed = finisher.settings;
                if (info.nodes.size) preload();
            } catch (err) {
                console.warn("[Pipedream] Sound arm failed:", err);
            }
            try {
                const res = await origQueuePrompt.apply(this, args);
                if (info && res?.prompt_id != null && !prompts.has(String(res.prompt_id))) {
                    prompts.set(String(res.prompt_id), info);
                }
                if (pending === info) pending = null;
                return res;
            } catch (err) {
                armed = previous;
                if (pending === info) pending = null;
                throw err;
            }
        };

        api.addEventListener("execution_start", ({ detail }) => {
            infoFor(detail?.prompt_id);
            if (!armed) return;
            ran = true;
            interrupted = false;
        });

        api.addEventListener("execution_cached", ({ detail }) => {
            const info = infoFor(detail?.prompt_id);
            let n = 0;
            for (const raw of detail?.nodes || []) {
                const id = String(raw);
                info.cached.add(id);
                const entry = info.nodes.get(id);
                if (entry?.mode !== "reached" || !entry.settings.when_cached) continue;
                if (info.played.has(id)) continue;
                info.played.add(id);
                playSound(entry.settings, false, CACHED_STAGGER * n++);
            }
        });

        api.addEventListener("executed", ({ detail }) => {
            const payload = detail?.output?.[UI_KEY]?.[0];
            if (!payload) return;
            const info = infoFor(detail.prompt_id);
            const id = String(detail.node);
            const entry = info.nodes.get(id);
            if (entry && entry.mode !== "reached") return;
            // Newer ComfyUI re-sends `executed` for cached nodes.
            if (info.cached.has(id) && !payload.when_cached) return;
            if (info.played.has(id)) return;
            info.played.add(id);
            playSound(payload);
        });

        api.addEventListener("execution_error", ({ detail }) => {
            if (armed) hadError = true;
            const info = infoFor(detail?.prompt_id);
            const toner = [...info.nodes.values()].find(
                (e) => e.mode === "reached" && e.settings.error_tone !== false,
            );
            if (toner && !info.errorPlayed) {
                info.errorPlayed = true;
                playSound(toner.settings, true);
            }
            forget(detail?.prompt_id);
        });
        api.addEventListener("execution_interrupted", ({ detail }) => {
            if (armed) interrupted = true;
            forget(detail?.prompt_id);
        });
        api.addEventListener("execution_success", ({ detail }) => {
            forget(detail?.prompt_id);
        });

        api.addEventListener("status", ({ detail }) => {
            if (detail?.exec_info?.queue_remaining !== 0) return;
            if (!armed || !ran) return;
            const settings = armed;
            const error = hadError && settings.error_tone !== false;
            const skip = interrupted;
            armed = null;
            ran = hadError = interrupted = false;
            if (!skip) playSound(settings, error);
        });
    },

    async nodeCreated(node) {
        if (node.comfyClass !== NODE_CLASS) return;

        const settingsFromWidgets = () => Object.fromEntries(
            (node.widgets || []).map((w) => [w.name, w.value]),
        );

        const button = node.addWidget("button", "▶ test sound", null, () => {
            playSound(settingsFromWidgets());
        });
        button.serialize = false;

        // custom_url only for "custom URL"; when_cached only in "node reached" mode.
        const syncVisibility = () => showWidgets(node, {
            custom_url: findWidget(node, "sound")?.value === "custom URL",
            when_cached: findWidget(node, "play_when")?.value !== "queue finished",
        });
        for (const name of ["sound", "play_when"]) {
            const widget = findWidget(node, name);
            if (widget) chain(widget, "callback", syncVisibility);
        }
        chain(node, "onConfigure", syncVisibility);
        chain(node, "onConnectionsChange", syncVisibility);
        syncVisibility();
    },
});
