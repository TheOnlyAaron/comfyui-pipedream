/**
 * PD Profiler memory chart, drawn on a canvas DOM widget.
 *
 * One column per stage in run order (text encode, each sampler, each VAE
 * decode), stacked bottom-up: models, working memory, latents.  The dashed
 * line is the VRAM budget; the part of a column above it is hatched (that
 * is what ComfyUI must offload).  After a run, columns are as wide as the
 * stage took (each at least a tenth) and a solid line marks the measured
 * peak.  Below, one bar for RAM: model weights and decoded pixels against
 * the RAM budget.  Hovering a column or the RAM bar shows its numbers.
 *
 * Colours are the first four categorical slots of the reference palette,
 * stepped for ComfyUI's dark or light theme (validated adjacent pairs;
 * values and names are always written beside the marks).
 *
 * ComfyUI loads every file in the web directory, so this module registers
 * nothing; pd_profiler.js imports it.
 */

const HEIGHT = 224;
const SERIES = {
    dark: { models: "#3987e5", working: "#d95926", latents: "#199e70", pixels: "#c98500" },
    light: { models: "#2a78d6", working: "#eb6834", latents: "#1baf7a", pixels: "#eda100" },
};
const LABELS = { models: "models", working: "working", latents: "latents", pixels: "pixels" };
const STACK = ["models", "working", "latents"];
const GIB = 1024 ** 3;
const MIB = 1024 ** 2;

export function fmtBytes(n) {
    n = Number(n) || 0;
    if (n >= GIB) return `${(n / GIB).toFixed(1)} GB`;
    if (n >= MIB) return `${Math.round(n / MIB)} MB`;
    return `${Math.round(n / 1024)} KB`;
}

function fmtTime(s) {
    if (s == null) return "";
    if (s < 1) return `${Math.round(s * 1000)} ms`;
    if (s < 60) return `${s < 10 ? s.toFixed(1) : Math.round(s)} s`;
    const m = Math.floor(s / 60);
    return `${m} m ${String(Math.round(s - m * 60)).padStart(2, "0")} s`;
}

function luminance(color) {
    const probe = document.createElement("div");
    probe.style.color = color;
    document.body.appendChild(probe);
    const rgb = getComputedStyle(probe).color.match(/\d+(\.\d+)?/g)?.map(Number) ?? [53, 53, 53];
    probe.remove();
    return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255;
}

function theme() {
    const css = getComputedStyle(document.documentElement);
    const pick = (...names) => names.map(n => css.getPropertyValue(n).trim()).find(Boolean);
    const surface = pick("--comfy-menu-bg", "--bg-color") || "#353535";
    const dark = luminance(surface) < 0.5;
    return {
        dark,
        series: SERIES[dark ? "dark" : "light"],
        text: pick("--input-text", "--fg-color") || (dark ? "#f0efec" : "#0b0b0b"),
        muted: pick("--descrip-text") || (dark ? "#c3c2b7" : "#52514e"),
        grid: dark ? "rgba(255,255,255,0.12)" : "rgba(0,0,0,0.12)",
    };
}

function hatch(ctx, x, y, w, h, color) {
    if (w <= 0 || h <= 0) return;
    ctx.save();
    ctx.beginPath();
    ctx.rect(x, y, w, h);
    ctx.clip();
    ctx.strokeStyle = color;
    ctx.globalAlpha = 0.7;
    ctx.lineWidth = 1;
    for (let i = -h; i < w; i += 5) {
        ctx.beginPath();
        ctx.moveTo(x + i, y + h);
        ctx.lineTo(x + i + h, y);
        ctx.stroke();
    }
    ctx.restore();
}

function fitText(ctx, text, width) {
    if (ctx.measureText(text).width <= width) return text;
    let t = text;
    while (t.length > 1 && ctx.measureText(t + "…").width > width) t = t.slice(0, -1);
    return t.length > 1 ? t + "…" : "";
}

/** Draw *chart* (from build_chart in core/profiler.py) into *canvas*; returns hover regions. */
function draw(canvas, chart) {
    const dpr = window.devicePixelRatio || 1;
    const W = Math.max(120, canvas.clientWidth);
    const H = HEIGHT;
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    const t = theme();
    const regions = [];
    ctx.font = "10px monospace";
    ctx.textBaseline = "alphabetic";

    if (!chart || !chart.stages?.length) {
        ctx.fillStyle = t.muted;
        ctx.fillText(chart ? "No sampler, VAE decode or text encoder upstream."
                           : "Press profile to chart memory by stage.", 8, 20);
        return regions;
    }

    const L = 8, R = 8, plotTop = 56, plotBottom = 152;
    const stages = chart.stages;
    const maxTotal = Math.max(...stages.map(s => s.total), chart.measured_peak || 0);
    const yMax = Math.max(chart.vram || 0, maxTotal) * 1.08 || 1;
    const y = v => plotBottom - (v / yMax) * (plotBottom - plotTop);

    // Legend
    const present = STACK.filter(k => stages.some(s => s[k] > 0));
    if (chart.ram_use?.pixels > 0) present.push("pixels");
    let lx = L;
    for (const key of present) {
        ctx.fillStyle = t.series[key];
        ctx.beginPath();
        ctx.roundRect(lx, 6, 9, 9, 2);
        ctx.fill();
        ctx.fillStyle = t.text;
        ctx.fillText(LABELS[key], lx + 13, 14);
        lx += 13 + ctx.measureText(LABELS[key]).width + 12;
    }
    const over = chart.vram && stages.some(s => s.total > chart.vram);
    if (over) {
        ctx.strokeStyle = t.text;
        ctx.strokeRect(lx + 0.5, 6.5, 9, 9);
        hatch(ctx, lx, 6, 10, 10, t.text);
        ctx.fillStyle = t.text;
        ctx.fillText("over budget", lx + 13, 14);
    }

    // Second legend row: the budget and measured peak lines.
    lx = L;
    const lineKey = (label, dashed, color) => {
        ctx.strokeStyle = color;
        ctx.setLineDash(dashed ? [4, 3] : []);
        ctx.beginPath();
        ctx.moveTo(lx, 26.5);
        ctx.lineTo(lx + 16, 26.5);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = t.text;
        ctx.fillText(label, lx + 21, 30);
        lx += 21 + ctx.measureText(label).width + 14;
    };
    if (chart.vram) lineKey(`VRAM ${fmtBytes(chart.vram)}${chart.emulated ? " (emulated)" : ""}`, true, t.text);
    else {
        ctx.fillStyle = t.muted;
        ctx.fillText("no VRAM budget: set vram_gb", lx, 30);
    }
    if (chart.measured_peak) lineKey(`measured peak ${fmtBytes(chart.measured_peak)}`, false, t.muted);

    // Baseline
    ctx.strokeStyle = t.grid;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(L, plotBottom + 0.5);
    ctx.lineTo(W - R, plotBottom + 0.5);
    ctx.stroke();

    // Column widths: by measured seconds when every stage has them.
    const gap = 8;
    const area = W - L - R - gap * (stages.length - 1);
    const timed = stages.every(s => s.seconds > 0);
    let shares = stages.map(() => 1 / stages.length);
    if (timed) {
        const sum = stages.reduce((a, s) => a + s.seconds, 0);
        shares = stages.map(s => Math.max(0.1, s.seconds / sum));
        const norm = shares.reduce((a, b) => a + b, 0);
        shares = shares.map(v => v / norm);
    }
    let widths = shares.map(v => v * area);
    const cap = 150;
    if (!timed && widths[0] > cap) widths = widths.map(() => cap);
    const used = widths.reduce((a, b) => a + b, 0) + gap * (stages.length - 1);
    let x = L + Math.max(0, (W - L - R - used) / 2);

    stages.forEach((s, i) => {
        const w = widths[i];
        if (s.unknown) {
            ctx.setLineDash([3, 3]);
            ctx.strokeStyle = t.muted;
            ctx.strokeRect(x + 0.5, y(Math.max(s.total, yMax * 0.15)) + 0.5, w - 1, plotBottom - y(Math.max(s.total, yMax * 0.15)) - 1);
            ctx.setLineDash([]);
        }
        let cum = 0;
        const parts = STACK.filter(k => s[k] > 0);
        parts.forEach((key, j) => {
            const top = y(cum + s[key]);
            const bottom = y(cum);
            cum += s[key];
            const h = bottom - top - (j > 0 ? 2 : 0);
            if (h < 0.5) return;
            ctx.fillStyle = t.series[key];
            ctx.beginPath();
            const last = j === parts.length - 1;
            ctx.roundRect(x, top, w, h, last ? [4, 4, 0, 0] : 0);
            ctx.fill();
        });
        if (chart.vram && s.total > chart.vram) {
            hatch(ctx, x, y(s.total), w, y(chart.vram) - y(s.total), t.text);
        }
        ctx.fillStyle = t.text;
        if (w >= 34) {
            const value = s.unknown ? "?" : fmtBytes(s.total);
            ctx.textAlign = "center";
            ctx.fillText(fitText(ctx, value, w), x + w / 2, y(Math.max(s.total, s.unknown ? yMax * 0.15 : 0)) - 4);
        }
        ctx.textAlign = "left";
        ctx.fillStyle = t.text;
        ctx.fillText(fitText(ctx, s.name, w), x, plotBottom + 13);
        ctx.fillStyle = t.muted;
        const sub = `#${s.node}${s.seconds != null ? " · " + fmtTime(s.seconds) : ""}`;
        ctx.fillText(fitText(ctx, sub, w), x, plotBottom + 25);

        const lines = [`${s.name}  ${s.label}`];
        if (s.unknown) lines.push(`${s.unknown} unknown`);
        for (const key of STACK) if (s[key] > 0) lines.push(`${LABELS[key]}: ${fmtBytes(s[key])}`);
        lines.push(`total: ${fmtBytes(s.total)}`);
        if (s.offload) lines.push(`offloads ${fmtBytes(s.offload)} to RAM`);
        else if (s.verdict) lines.push(s.verdict);
        if (s.seconds != null) lines.push(`time: ${fmtTime(s.seconds)}`);
        regions.push({ x0: x, x1: x + w, y0: plotTop - 12, y1: plotBottom + 28, text: lines.join("\n") });
        x += w + gap;
    });

    // Budget and measured peak
    if (chart.vram) {
        const by = Math.round(y(chart.vram)) + 0.5;
        ctx.strokeStyle = t.text;
        ctx.setLineDash([4, 3]);
        ctx.beginPath();
        ctx.moveTo(L, by);
        ctx.lineTo(W - R, by);
        ctx.stroke();
        ctx.setLineDash([]);
    }
    if (chart.measured_peak) {
        const py = Math.round(y(chart.measured_peak)) + 0.5;
        ctx.strokeStyle = t.muted;
        ctx.beginPath();
        ctx.moveTo(L, py);
        ctx.lineTo(W - R, py);
        ctx.stroke();
    }

    // RAM bar
    const ram = chart.ram_use || {};
    const ramUse = (ram.models || 0) + (ram.pixels || 0);
    const ry = 204, rh = 10;
    const scale = Math.max(chart.ram || 0, ramUse) * 1.05 || 1;
    const bx = L, bw = W - L - R;
    const rx = v => bx + (v / scale) * bw;
    ctx.fillStyle = t.text;
    const ramText = `RAM ~${fmtBytes(ramUse)}${chart.ram ? ` of ${fmtBytes(chart.ram)}` : ""}`;
    ctx.fillText(ramText, L, ry - 5);
    let cx = bx;
    [["models", ram.models], ["pixels", ram.pixels]].forEach(([key, v], j) => {
        if (!(v > 0)) return;
        const w = rx(v) - bx - (j > 0 ? 2 : 0);
        if (j > 0) cx += 2;
        if (w < 0.5) return;
        ctx.fillStyle = t.series[key];
        ctx.beginPath();
        ctx.roundRect(cx, ry, w, rh, 3);
        ctx.fill();
        cx += w;
    });
    ctx.strokeStyle = t.grid;
    ctx.strokeRect(bx + 0.5, ry + 0.5, bw - 1, rh - 1);
    if (chart.ram) {
        const tx = Math.round(rx(chart.ram)) + 0.5;
        if (ramUse > chart.ram) hatch(ctx, tx, ry, rx(ramUse) - tx, rh, t.text);
        ctx.strokeStyle = t.text;
        ctx.setLineDash([3, 2]);
        ctx.beginPath();
        ctx.moveTo(tx, ry - 3);
        ctx.lineTo(tx, ry + rh + 3);
        ctx.stroke();
        ctx.setLineDash([]);
    }
    regions.push({
        x0: bx, x1: bx + bw, y0: ry - 14, y1: ry + rh + 4,
        text: [`RAM ~${fmtBytes(ramUse)}`, `models: ${fmtBytes(ram.models)}`,
               `pixels (float32 IMAGE): ${fmtBytes(ram.pixels)}`,
               chart.ram ? `budget: ${fmtBytes(chart.ram)}` : ""].filter(Boolean).join("\n"),
    });
    return regions;
}

/**
 * Add the chart widget to *node*.  Returns ``{set(chart)}``; the widget
 * is not serialized.
 */
export function addProfileChart(node) {
    const canvas = document.createElement("canvas");
    Object.assign(canvas.style, { width: "100%", height: `${HEIGHT}px`, display: "block" });
    let chart = null;
    let regions = [];
    const redraw = () => { regions = draw(canvas, chart); };
    const widget = node.addDOMWidget("profile_chart", "pd_profile_chart", canvas, {
        getValue: () => "",
        setValue: () => {},
        getMinHeight: () => HEIGHT,
        getMaxHeight: () => HEIGHT,
        serialize: false,
    });
    widget.serialize = false;
    canvas.addEventListener("mousemove", (event) => {
        const rect = canvas.getBoundingClientRect();
        const px = (event.clientX - rect.left) * (canvas.clientWidth / rect.width);
        const py = (event.clientY - rect.top) * (HEIGHT / rect.height);
        const hit = regions.find(r => px >= r.x0 && px <= r.x1 && py >= r.y0 && py <= r.y1);
        canvas.title = hit ? hit.text : "";
    });
    new ResizeObserver(redraw).observe(canvas);
    requestAnimationFrame(redraw);
    return {
        set(value) {
            chart = value ?? null;
            redraw();
        },
    };
}
