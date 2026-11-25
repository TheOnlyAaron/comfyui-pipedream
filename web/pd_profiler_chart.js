/**
 * PD Profiler memory chart, drawn on a canvas DOM widget.
 *
 * One horizontal bar per stage in run order (text encode, each sampler,
 * each VAE decode), split in proportion into models, working memory and
 * latents, running toward the VRAM budget (the dashed vertical line).
 * Above each bar: the stage, its time when measured, its total and how far
 * under or over budget it is.  What runs past the line is hatched: that is
 * what ComfyUI must offload, and what to cut (resolution, frames, batch,
 * precision) to get under.  The largest stage, the peak, is marked.
 *
 * A RAM bar follows, against the RAM budget: model weights and decoded
 * pixels.  After a run a solid vertical line marks the measured VRAM peak.
 * Hovering a bar shows its numbers.
 *
 * Colours are the first four categorical slots of the reference palette,
 * stepped for ComfyUI's dark or light theme (validated adjacent pairs;
 * values and names are always written beside the marks).
 *
 * ComfyUI loads every file in the web directory, so this module registers
 * nothing; pd_profiler.js imports it.
 */

const SERIES = {
    dark: { models: "#3987e5", working: "#d95926", latents: "#199e70", pixels: "#c98500" },
    light: { models: "#2a78d6", working: "#eb6834", latents: "#1baf7a", pixels: "#eda100" },
};
const LABELS = { models: "models", working: "working", latents: "latents", pixels: "pixels" };
const STACK = ["models", "working", "latents"];
const GIB = 1024 ** 3;
const MIB = 1024 ** 2;

const PAD = 8;
const LEGEND = 40;
const ROW = 34;
const BAR = 12;
const RAM_GAP = 10;
const EMPTY_HEIGHT = 30;

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
        series: SERIES[dark ? "dark" : "light"],
        text: pick("--input-text", "--fg-color") || (dark ? "#f0efec" : "#0b0b0b"),
        muted: pick("--descrip-text") || (dark ? "#c3c2b7" : "#52514e"),
        track: dark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.07)",
    };
}

function hatch(ctx, x, y, w, h, color) {
    if (w <= 0 || h <= 0) return;
    ctx.save();
    ctx.beginPath();
    ctx.rect(x, y, w, h);
    ctx.clip();
    ctx.strokeStyle = color;
    ctx.globalAlpha = 0.75;
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
    if (width <= 0) return "";
    if (ctx.measureText(text).width <= width) return text;
    let t = text;
    while (t.length > 1 && ctx.measureText(t + "…").width > width) t = t.slice(0, -1);
    return t.length > 1 ? t + "…" : "";
}

/** Canvas height (CSS px) for *chart*. */
export function chartHeight(chart) {
    if (!chart?.stages?.length) return EMPTY_HEIGHT;
    return LEGEND + chart.stages.length * ROW + RAM_GAP + ROW + 4;
}

/**
 * One budget-relative bar: *parts* ``[[key, bytes], ...]`` from x0, scaled
 * so *budget* lands at the budget line, overflow hatched.
 */
function bar(ctx, t, parts, x0, scale, y, budget) {
    const total = parts.reduce((a, [, v]) => a + (v > 0 ? v : 0), 0);
    let x = x0;
    const shown = parts.filter(([, v]) => v > 0);
    shown.forEach(([key, v], i) => {
        const w = v * scale - (i > 0 ? 2 : 0);
        if (i > 0) x += 2;
        if (w >= 0.5) {
            ctx.fillStyle = t.series[key];
            ctx.beginPath();
            const first = i === 0, last = i === shown.length - 1;
            ctx.roundRect(x, y, w, BAR, [first ? 4 : 0, last ? 4 : 0, last ? 4 : 0, first ? 4 : 0]);
            ctx.fill();
        }
        x += Math.max(0, w);
    });
    if (budget && total > budget) hatch(ctx, x0 + budget * scale, y, (total - budget) * scale, BAR, t.text);
    return total;
}

function budgetNote(total, budget) {
    if (!budget) return "";
    const diff = budget - total;
    return diff >= 0 ? `${fmtBytes(diff)} free` : `over by ${fmtBytes(-diff)}`;
}

/** Draw *chart* (from build_chart in core/profiler.py) into *canvas*; returns hover regions. */
function draw(canvas, chart) {
    const dpr = window.devicePixelRatio || 1;
    const W = Math.max(160, canvas.clientWidth);
    const H = chartHeight(chart);
    canvas.style.height = `${H}px`;
    canvas.style.minHeight = canvas.style.maxHeight = `${H}px`;
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    ctx.font = "10px monospace";
    ctx.textBaseline = "alphabetic";
    const t = theme();
    const regions = [];

    if (!chart?.stages?.length) {
        ctx.fillStyle = t.muted;
        ctx.fillText(chart ? "No sampler, VAE decode or text encoder upstream."
                           : "Press profile to chart memory by stage.", PAD, 18);
        return regions;
    }

    const stages = chart.stages;
    const x0 = PAD, x1 = W - PAD, span = x1 - x0;
    const peak = stages.reduce((a, s) => (s.total > a.total ? s : a), stages[0]);

    // Legend
    let lx = PAD;
    const present = STACK.filter(k => stages.some(s => s[k] > 0));
    if (chart.ram_use?.pixels > 0) present.push("pixels");
    for (const key of present) {
        ctx.fillStyle = t.series[key];
        ctx.beginPath();
        ctx.roundRect(lx, 4, 9, 9, 2);
        ctx.fill();
        ctx.fillStyle = t.text;
        ctx.fillText(LABELS[key], lx + 13, 12);
        lx += 13 + ctx.measureText(LABELS[key]).width + 12;
    }
    if (stages.some(s => chart.vram && s.total > chart.vram)) {
        hatch(ctx, lx, 4, 10, 10, t.text);
        ctx.strokeStyle = t.text;
        ctx.strokeRect(lx + 0.5, 4.5, 9, 9);
        ctx.fillStyle = t.text;
        ctx.fillText("over budget", lx + 13, 12);
    }
    lx = PAD;
    const lineKey = (label, dashed, color) => {
        ctx.strokeStyle = color;
        ctx.setLineDash(dashed ? [4, 3] : []);
        ctx.beginPath();
        ctx.moveTo(lx + 4.5, 19);
        ctx.lineTo(lx + 4.5, 31);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = t.text;
        ctx.fillText(label, lx + 13, 29);
        lx += 13 + ctx.measureText(label).width + 14;
    };
    if (chart.vram) lineKey(`VRAM budget ${fmtBytes(chart.vram)}${chart.emulated ? " (emulated)" : ""}`, true, t.text);
    else {
        ctx.fillStyle = t.muted;
        ctx.fillText("no VRAM budget: set vram_gb", PAD, 29);
    }
    if (chart.measured_peak) lineKey(`measured peak ${fmtBytes(chart.measured_peak)}`, false, t.muted);

    // VRAM rows, one scale: the budget line sits where it falls; overflow runs past it.
    const vmax = Math.max(chart.vram || 0, peak.total, chart.measured_peak || 0) * 1.04 || 1;
    const vscale = span / vmax;
    const top = LEGEND;
    stages.forEach((s, i) => {
        const y = top + i * ROW;
        const by = y + 15;
        const isPeak = s === peak && stages.length > 1;
        ctx.fillStyle = t.track;
        ctx.beginPath();
        ctx.roundRect(x0, by, span, BAR, 4);
        ctx.fill();
        const parts = STACK.map(k => [k, s[k]]);
        bar(ctx, t, parts, x0, vscale, by, chart.vram);
        if (s.unknown) {
            ctx.setLineDash([3, 3]);
            ctx.strokeStyle = t.muted;
            ctx.strokeRect(x0 + 0.5, by + 0.5, span - 1, BAR - 1);
            ctx.setLineDash([]);
        }

        const left = `${s.name} #${s.node}${s.seconds != null ? " · " + fmtTime(s.seconds) : ""}${isPeak ? "  ▲ peak" : ""}`;
        const right = s.unknown ? `${s.unknown} unknown`
            : `${fmtBytes(s.total)}${chart.vram ? " · " + budgetNote(s.total, chart.vram) : ""}`;
        ctx.font = "10px monospace";
        const rw = ctx.measureText(right).width;
        ctx.fillStyle = t.text;
        ctx.textAlign = "right";
        ctx.fillText(right, x1, y + 10);
        ctx.textAlign = "left";
        ctx.font = isPeak ? "bold 10px monospace" : "10px monospace";
        ctx.fillText(fitText(ctx, left, span - rw - 10), x0, y + 10);
        ctx.font = "10px monospace";

        const lines = [`${s.name}  ${s.label}`];
        if (s.unknown) lines.push(`${s.unknown} unknown`);
        for (const key of STACK) {
            if (s[key] > 0) lines.push(`${LABELS[key]}: ${fmtBytes(s[key])} (${Math.round((s[key] / s.total) * 100)}%)`);
        }
        lines.push(`total: ${fmtBytes(s.total)}`);
        if (chart.vram) lines.push(budgetNote(s.total, chart.vram));
        if (s.offload) lines.push(`ComfyUI offloads ${fmtBytes(s.offload)} to RAM`);
        else if (s.verdict && s.verdict !== "fits") lines.push(s.verdict);
        if (s.seconds != null) lines.push(`time: ${fmtTime(s.seconds)}`);
        regions.push({ x0, x1, y0: y, y1: y + ROW, text: lines.join("\n") });
    });
    const mark = (value, dashed, color) => {
        const mx = Math.round(x0 + value * vscale) + 0.5;
        ctx.strokeStyle = color;
        ctx.setLineDash(dashed ? [4, 3] : []);
        stages.forEach((_, i) => {
            const by = top + i * ROW + 15;
            ctx.beginPath();
            ctx.moveTo(mx, by - 1);
            ctx.lineTo(mx, by + BAR + 1);
            ctx.stroke();
        });
        ctx.setLineDash([]);
    };
    if (chart.measured_peak) mark(chart.measured_peak, false, t.muted);
    if (chart.vram) mark(chart.vram, true, t.text);

    // RAM row, its own scale and budget.
    const ram = chart.ram_use || {};
    const ramUse = (ram.models || 0) + (ram.pixels || 0);
    const y = top + stages.length * ROW + RAM_GAP;
    const by = y + 15;
    const rmax = Math.max(chart.ram || 0, ramUse) * 1.04 || 1;
    const rscale = span / rmax;
    ctx.fillStyle = t.track;
    ctx.beginPath();
    ctx.roundRect(x0, by, span, BAR, 4);
    ctx.fill();
    bar(ctx, t, [["models", ram.models], ["pixels", ram.pixels]], x0, rscale, by, chart.ram);
    ctx.fillStyle = t.text;
    ctx.fillText("RAM", x0, y + 10);
    ctx.textAlign = "right";
    ctx.fillText(`~${fmtBytes(ramUse)}${chart.ram ? " · " + budgetNote(ramUse, chart.ram) : ""}`, x1, y + 10);
    ctx.textAlign = "left";
    if (chart.ram) {
        const rx = Math.round(x0 + chart.ram * rscale) + 0.5;
        ctx.strokeStyle = t.text;
        ctx.setLineDash([4, 3]);
        ctx.beginPath();
        ctx.moveTo(rx, by - 1);
        ctx.lineTo(rx, by + BAR + 1);
        ctx.stroke();
        ctx.setLineDash([]);
    }
    regions.push({
        x0, x1, y0: y, y1: y + ROW,
        text: [`RAM ~${fmtBytes(ramUse)}`, `models: ${fmtBytes(ram.models)}`,
               `pixels (float32 IMAGE): ${fmtBytes(ram.pixels)}`,
               chart.ram ? `budget ${fmtBytes(chart.ram)}: ${budgetNote(ramUse, chart.ram)}` : ""]
            .filter(Boolean).join("\n"),
    });
    return regions;
}

/**
 * Add the chart widget to *node*.  Returns ``{set(chart)}``; the widget
 * is not serialized, grows the node when the chart needs more rows and
 * never stretches the drawing when the node is resized.
 */
export function addProfileChart(node) {
    // The renderer sizes the widget element to the space the node gives it;
    // the canvas sits in a container so only the container stretches and
    // the drawing keeps its own pixel height.
    const container = document.createElement("div");
    Object.assign(container.style, { width: "100%", overflow: "hidden" });
    const canvas = document.createElement("canvas");
    Object.assign(canvas.style, { width: "100%", height: `${EMPTY_HEIGHT}px`, display: "block",
                                  flex: "none" });
    container.appendChild(canvas);
    let chart = null;
    let regions = [];
    const redraw = () => { regions = draw(canvas, chart); };
    const widget = node.addDOMWidget("profile_chart", "pd_profile_chart", container, {
        getValue: () => "",
        setValue: () => {},
        getMinHeight: () => chartHeight(chart),
        getMaxHeight: () => chartHeight(chart),
        serialize: false,
    });
    widget.serialize = false;
    canvas.addEventListener("mousemove", (event) => {
        const rect = canvas.getBoundingClientRect();
        const px = (event.clientX - rect.left) * (canvas.clientWidth / rect.width);
        const py = (event.clientY - rect.top) * (canvas.clientHeight / rect.height);
        const hit = regions.find(r => px >= r.x0 && px <= r.x1 && py >= r.y0 && py <= r.y1);
        canvas.title = hit ? hit.text : "";
    });
    new ResizeObserver(redraw).observe(canvas);
    requestAnimationFrame(redraw);
    return {
        set(value) {
            chart = value ?? null;
            redraw();
            const need = node.computeSize?.();
            if (need && node.size[1] < need[1]) node.setSize([node.size[0], need[1]]);
            node.setDirtyCanvas?.(true, true);
        },
    };
}
