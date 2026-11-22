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
/* ------------------------------------------------------------------ */

const NODE_CLASS = "PDSound";
const UI_KEY = "pd_sound";
const CACHED_STAGGER = 0.35;

let audioCtx = null;

/** Return a shared AudioContext, creating and resuming it as needed. */
function getAudioContext() {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    if (!audioCtx) audioCtx = new Ctx();
    if (audioCtx.state === "suspended") audioCtx.resume().catch(() => {});
    return audioCtx;
}

/**
 * Schedule one enveloped note.
 *
 * `partials` is a list of [frequency ratio, amplitude, duration scale];
 * `glide` bends the pitch by that factor over the note.
 */
function voice(ctx, out, {
    freq, start, dur, type = "sine", gain = 1, attack = 0.006, glide = 0,
    partials = [[1, 1, 1]],
}) {
    for (const [ratio, amp, scale = 1] of partials) {
        const end = start + dur * scale;
        const osc = ctx.createOscillator();
        const env = ctx.createGain();
        osc.type = type;
        osc.frequency.setValueAtTime(freq * ratio, start);
        if (glide) osc.frequency.exponentialRampToValueAtTime(freq * ratio * glide, end);
        env.gain.setValueAtTime(0.0001, start);
        env.gain.exponentialRampToValueAtTime(Math.max(0.0002, gain * amp), start + attack);
        env.gain.exponentialRampToValueAtTime(0.0001, end);
        osc.connect(env).connect(out);
        osc.start(start);
        osc.stop(end + 0.05);
    }
}

/** Return a lowpass filter feeding `out`, to soften square/saw waves. */
function lowpass(ctx, out, hz) {
    const f = ctx.createBiquadFilter();
    f.type = "lowpass";
    f.frequency.value = hz;
    f.connect(out);
    return f;
}

const BELL = [[1, 1, 1], [2, 0.25, 0.6], [3.01, 0.08, 0.4]];
const BRIGHT_BELL = [[1, 1, 1], [2.76, 0.3, 0.5], [5.4, 0.1, 0.3]];

/** Built-in sounds, each `(ctx, out, t0)`; all finish within ~1.4s. */
export const SYNTHS = {
    /** Two-note bell, E5 then B5: the classic render-complete chime. */
    chime(ctx, out, t) {
        voice(ctx, out, { freq: 659.25, start: t, dur: 1.2, gain: 0.8, partials: BELL });
        voice(ctx, out, { freq: 987.77, start: t + 0.16, dur: 1.2, gain: 0.8, partials: BELL });
    },
    /** Bright rising C major arpeggio. */
    happy(ctx, out, t) {
        [523.25, 659.25, 783.99, 1046.5].forEach((freq, i) => {
            voice(ctx, out, {
                freq, start: t + i * 0.09, dur: i === 3 ? 0.7 : 0.32,
                type: "triangle", gain: 0.7, partials: [[1, 1], [2, 0.15, 0.5]],
            });
        });
    },
    /** Falling C minor line whose last note sags flat. */
    sad(ctx, out, t) {
        const f = lowpass(ctx, out, 1800);
        voice(ctx, f, { freq: 392.0, start: t, dur: 0.4, type: "triangle", gain: 0.8 });
        voice(ctx, f, { freq: 311.13, start: t + 0.3, dur: 0.45, type: "triangle", gain: 0.8 });
        voice(ctx, f, {
            freq: 261.63, start: t + 0.6, dur: 0.75, type: "triangle", gain: 0.8,
            glide: 0.94, attack: 0.02,
        });
    },
    /** Single bright bell strike. */
    ding(ctx, out, t) {
        voice(ctx, out, { freq: 880, start: t, dur: 1.3, gain: 0.8, partials: BRIGHT_BELL });
    },
    /** Three short, even beeps. */
    beeps(ctx, out, t) {
        const f = lowpass(ctx, out, 2500);
        for (let i = 0; i < 3; i++) {
            voice(ctx, f, { freq: 1000, start: t + i * 0.15, dur: 0.09, type: "square", gain: 0.35, attack: 0.004 });
        }
    },
    /** Buzzy two-tone alternation, high-low twice. */
    alert(ctx, out, t) {
        const f = lowpass(ctx, out, 2000);
        [880, 659.25, 880, 659.25].forEach((freq, i) => {
            voice(ctx, f, { freq, start: t + i * 0.16, dur: 0.14, type: "sawtooth", gain: 0.35, attack: 0.005 });
        });
    },
    /** Low two-pulse buzzer used for errors. */
    error(ctx, out, t) {
        const f = lowpass(ctx, out, 900);
        voice(ctx, f, { freq: 196, start: t, dur: 0.2, type: "square", gain: 0.6, attack: 0.005 });
        voice(ctx, f, { freq: 185, start: t + 0.24, dur: 0.32, type: "square", gain: 0.6, attack: 0.005 });
    },
};

/** Synthesize a built-in sound after `delay` seconds; unknown names use the chime. */
function playSynth(name, volume, delay = 0) {
    const ctx = getAudioContext();
    if (!ctx) return;
    const master = ctx.createGain();
    master.gain.value = Math.max(0, Math.min(1, volume)) * 0.5;
    master.connect(ctx.destination);
    (SYNTHS[name] || SYNTHS.chime)(ctx, master, ctx.currentTime + 0.02 + delay);
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
    if (isError) return playSynth("error", volume, delay);

    const url = String(settings.custom_url || "").trim();
    if (settings.sound === "custom URL" && url) {
        const play = () => {
            const audio = new Audio(resolveSoundUrl(url));
            audio.volume = Math.max(0, Math.min(1, volume));
            audio.play().catch((err) => {
                console.warn("[Pipedream] Could not play custom sound, using synth chime:", err);
                playSynth("chime", volume);
            });
        };
        if (delay > 0) setTimeout(play, delay * 1000);
        else play();
        return;
    }
    playSynth(settings.sound, volume, delay);
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

        const unlock = () => getAudioContext();
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
                if (info.nodes.size) getAudioContext();
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

        const errButton = node.addWidget("button", "▶ test error tone", null, () => {
            playSound(settingsFromWidgets(), true);
        });
        errButton.serialize = false;

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
