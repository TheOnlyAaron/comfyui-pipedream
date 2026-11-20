import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

/* ------------------------------------------------------------------ */
/*  Pipedream.RenderSound — browser chime when the queue drains       */
/*                                                                    */
/*  A prompt queued from this tab that contains an enabled            */
/*  PDRenderCompleteSound node arms the chime with that node's        */
/*  settings.  When the server reports queue_remaining == 0 after     */
/*  work has run, the chime plays (or the error tone, if any prompt   */
/*  failed) and the arm is cleared.                                   */
/* ------------------------------------------------------------------ */

const NODE_CLASS = "PDRenderCompleteSound";

/** Synth presets: notes are [frequency Hz, start offset s]. */
const PRESETS = {
    chime: { notes: [[659.25, 0], [987.77, 0.16]], decay: 1.4, partials: [1, 2, 3.01], gains: [1, 0.25, 0.08] },
    bell:  { notes: [[523.25, 0], [783.99, 0.22]], decay: 2.2, partials: [1, 2.76, 5.4], gains: [1, 0.35, 0.12] },
    ding:  { notes: [[1046.5, 0]], decay: 1.0, partials: [1, 2, 4.2], gains: [1, 0.2, 0.05] },
    error: { notes: [[440, 0], [349.23, 0.2]], decay: 0.9, partials: [1, 2, 3], gains: [1, 0.3, 0.1] },
};

let audioCtx = null;

/** Return a shared AudioContext, creating and resuming it as needed. */
function getAudioContext() {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    if (!audioCtx) audioCtx = new Ctx();
    if (audioCtx.state === "suspended") audioCtx.resume().catch(() => {});
    return audioCtx;
}

/** Synthesize a bell-like preset with WebAudio. */
function playSynth(name, volume) {
    const ctx = getAudioContext();
    if (!ctx) return;
    const preset = PRESETS[name] || PRESETS.chime;
    const master = ctx.createGain();
    master.gain.value = Math.max(0, Math.min(1, volume)) * 0.5;
    master.connect(ctx.destination);

    const t0 = ctx.currentTime + 0.02;
    for (const [freq, offset] of preset.notes) {
        preset.partials.forEach((ratio, i) => {
            const start = t0 + offset;
            const end = start + preset.decay / (1 + i * 0.6);
            const osc = ctx.createOscillator();
            const env = ctx.createGain();
            osc.type = "sine";
            osc.frequency.value = freq * ratio;
            env.gain.setValueAtTime(0.0001, start);
            env.gain.exponentialRampToValueAtTime(preset.gains[i], start + 0.008);
            env.gain.exponentialRampToValueAtTime(0.0001, end);
            osc.connect(env).connect(master);
            osc.start(start);
            osc.stop(end + 0.05);
        });
    }
}

/**
 * Resolve a custom sound URL.  Absolute URLs and root-relative paths are
 * used as-is; anything else is resolved against this extension's web dir
 * (e.g. "sounds/done.wav").
 */
function resolveSoundUrl(url) {
    return new URL(url, import.meta.url).href;
}

/** Play a sound described by node settings; falls back to the synth chime. */
function playSound(settings, isError = false) {
    const volume = Number(settings.volume ?? 0.6);
    if (isError) return playSynth("error", volume);

    const url = String(settings.custom_url || "").trim();
    if (settings.sound === "custom URL" && url) {
        const audio = new Audio(resolveSoundUrl(url));
        audio.volume = Math.max(0, Math.min(1, volume));
        audio.play().catch((err) => {
            console.warn("[Pipedream] Could not play custom sound, using synth chime:", err);
            playSynth("chime", volume);
        });
        return;
    }
    playSynth(settings.sound, volume);
}

/** Find the settings of the first enabled sound node in a prompt's output. */
function findArmSettings(output) {
    for (const node of Object.values(output || {})) {
        if (node?.class_type === NODE_CLASS && node.inputs?.enabled !== false) {
            return { ...node.inputs };
        }
    }
    return null;
}

app.registerExtension({
    name: "Pipedream.RenderSound",

    async setup() {
        let armed = null;
        let ran = false;
        let hadError = false;
        let interrupted = false;

        const unlock = () => getAudioContext();
        window.addEventListener("pointerdown", unlock, { once: true, capture: true });
        window.addEventListener("keydown", unlock, { once: true, capture: true });

        const origQueuePrompt = api.queuePrompt;
        api.queuePrompt = async function (...args) {
            // Arm before the request: a fully cached prompt can finish
            // before the HTTP response arrives.
            const previous = armed;
            try {
                const settings = findArmSettings(args[1]?.output);
                if (settings) {
                    armed = settings;
                    getAudioContext();
                }
            } catch (err) {
                console.warn("[Pipedream] Render sound arm failed:", err);
            }
            try {
                return await origQueuePrompt.apply(this, args);
            } catch (err) {
                armed = previous;
                throw err;
            }
        };

        api.addEventListener("execution_start", () => {
            if (!armed) return;
            ran = true;
            interrupted = false;
        });
        api.addEventListener("execution_error", () => {
            if (armed) hadError = true;
        });
        api.addEventListener("execution_interrupted", () => {
            if (armed) interrupted = true;
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
    },
});
