/**
 * Render PD Sound's built-in sounds to WAV files in web/sounds/.
 *
 * PD Sound plays these files with an <audio> element.  The sounds are Web
 * Audio synths, kept in tools/sound_synths.js as the source.  They run in
 * headless Chromium through an OfflineAudioContext, so the files match the
 * original synthesis at the master level PD Sound used (half scale at
 * volume 1); the node's volume sets the element's volume.
 *
 * Re-render after editing a synth:
 *     node tools/render_sounds.mjs
 * Needs Node.js and Playwright with Chromium.  tools/ is left out of the
 * registry package (.comfyignore).
 */

import { createRequire } from "node:module";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = join(HERE, "..", "web", "sounds");
const SAMPLE_RATE = 22050;
const SECONDS = 1.6;
const SOURCE = readFileSync(join(HERE, "sound_synths.js"), "utf8");

/** 16-bit mono PCM WAV of *samples*, trailing silence trimmed (20 ms kept). */
function wav(samples, rate) {
    let end = samples.length;
    while (end > 1 && Math.abs(samples[end - 1]) < 1e-4) end--;
    end = Math.min(samples.length, end + Math.round(rate * 0.02));
    const data = Buffer.alloc(end * 2);
    for (let i = 0; i < end; i++) {
        data.writeInt16LE(Math.round(Math.max(-1, Math.min(1, samples[i])) * 32767), i * 2);
    }
    const head = Buffer.alloc(44);
    head.write("RIFF", 0);
    head.writeUInt32LE(36 + data.length, 4);
    head.write("WAVE", 8);
    head.write("fmt ", 12);
    head.writeUInt32LE(16, 16);
    head.writeUInt16LE(1, 20);
    head.writeUInt16LE(1, 22);
    head.writeUInt32LE(rate, 24);
    head.writeUInt32LE(rate * 2, 28);
    head.writeUInt16LE(2, 32);
    head.writeUInt16LE(16, 34);
    head.write("data", 36);
    head.writeUInt32LE(data.length, 40);
    return Buffer.concat([head, data]);
}

const browser = await chromium.launch();
const page = await browser.newPage();
const rendered = await page.evaluate(async ({ source, rate, seconds }) => {
    const SYNTHS = new Function(`${source}\nreturn SYNTHS;`)();
    const out = {};
    for (const name of Object.keys(SYNTHS)) {
        const ctx = new OfflineAudioContext(1, Math.round(rate * seconds), rate);
        const master = ctx.createGain();
        master.gain.value = 0.5;
        master.connect(ctx.destination);
        SYNTHS[name](ctx, master, 0.01);
        out[name] = Array.from((await ctx.startRendering()).getChannelData(0));
    }
    return out;
}, { source: SOURCE, rate: SAMPLE_RATE, seconds: SECONDS });
await browser.close();

mkdirSync(OUT_DIR, { recursive: true });
for (const [name, samples] of Object.entries(rendered)) {
    const bytes = wav(samples, SAMPLE_RATE);
    writeFileSync(join(OUT_DIR, `${name}.wav`), bytes);
    const peak = samples.reduce((m, v) => Math.max(m, Math.abs(v)), 0);
    console.log(`${name}.wav  ${(bytes.length / 1024).toFixed(0)} KB  peak ${peak.toFixed(3)}`);
}
