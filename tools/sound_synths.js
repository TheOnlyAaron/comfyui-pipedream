/*
 * PD Sound's built-in sounds as Web Audio synths: the source of the WAV files
 * in web/sounds/.  Not loaded by ComfyUI; tools/render_sounds.mjs runs this
 * file in a browser (it must define SYNTHS, each (ctx, out, startTime)).
 */

/**
 * Schedule one enveloped note.
 *
 * `partials` is a list of [frequency ratio, amplitude, duration scale];
 * `glide` bends the pitch by that factor over the note.  With `hold`, the
 * note sustains at full level and releases over its last `hold` seconds
 * (a buzzer) instead of decaying from the attack (a bell).
 */
function voice(ctx, out, {
    freq, start, dur, type = "sine", gain = 1, attack = 0.006, glide = 0,
    partials = [[1, 1, 1]], hold = 0,
}) {
    for (const [ratio, amp, scale = 1] of partials) {
        const end = start + dur * scale;
        const osc = ctx.createOscillator();
        const env = ctx.createGain();
        osc.type = type;
        osc.frequency.setValueAtTime(freq * ratio, start);
        if (glide) osc.frequency.exponentialRampToValueAtTime(freq * ratio * glide, end);
        env.gain.setValueAtTime(0.0001, start);
        const level = Math.max(0.0002, gain * amp);
        env.gain.exponentialRampToValueAtTime(level, start + attack);
        if (hold) env.gain.setValueAtTime(level, Math.max(start + attack, end - hold));
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
const SYNTHS = {
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
    /** Game-show buzzer used for errors: a sustained, rasping low blat. */
    error(ctx, out, t) {
        const f = lowpass(ctx, out, 2400);
        const buzz = { start: t, dur: 0.65, gain: 0.32, attack: 0.008, hold: 0.06 };
        voice(ctx, f, { ...buzz, freq: 110, type: "sawtooth" });
        voice(ctx, f, { ...buzz, freq: 116.5, type: "sawtooth" });
        voice(ctx, f, { ...buzz, freq: 55, type: "square", gain: 0.22 });
    },
};
