"""
PD Save node.

One output node for every destination and format: resolves a token
template, then writes images (png/exr/jpg/webp) or video (mp4/mov/webm,
encoded with PyAV, which ships with ComfyUI) either into ComfyUI's output
directory (relative mode) or to an absolute/UNC path (absolute mode).

The source is an IMAGE batch or a ComfyUI VIDEO.  A VIDEO is written with
its own frame rate and audio, or as an image sequence when an image
format is chosen.  Image formats write one file per frame, numbered from
``start_frame`` at ``{frame}`` in the template (or ``name.1001.ext`` by
default, with the ``sequence.frame_separator`` setting before the number).  An optional alpha (IMAGE, MASK or VIDEO), or the fourth
channel of the images, is written to png/webp/exr and ProRes 4444
(straight, except EXR, which is premultiplied as its spec requires).

EXR header metadata comes from the ``exr_metadata`` inputs (merged in
order, frame N's table into frame N; see ``core/exr_meta.py``); nothing is
written unless one is connected.  The frontend shows them for exr only,
with one spare after the highest linked.

A connected PD Wedge chain adds its tokens (``{<token>}``,
``{<token>_idx}``, ``{wedge_idx}``, ``{wedge_total}``) over the context.

Each write can produce a sidecar JSON with the resolved tokens, template,
written paths, frame range, alpha convention, wedge job and the ComfyUI
prompt and workflow (drop the sidecar on ComfyUI to reopen the workflow,
see ``web/pd_save.js``).  The node shows a preview of what was written, returns the written paths,
passes the images through, returns a VIDEO for written video, and feeds
the token reference panel in ``web/pipedream.js``.

Widget defaults come from the facility/user settings (``core/settings.py``).
"""

import json
import os
import sys
from datetime import datetime

from ..core import settings
from ..core.comfy import output_directory, temp_directory
from ..core.common import display_name
from ..core.exr_meta import INPUT_NAMES as METADATA_INPUT_NAMES, ExrError, ExrMetadata, write_attributes
from ..core.media import (
    EXR_COLORSPACES,
    EXR_COMPRESSIONS,
    EXR_PRECISIONS,
    IMAGE_FORMATS,
    PATH_MODES,
    PRORES_CHOICES,
    VIDEO_FORMATS,
    alpha_matte,
    alpha_premultiplied,
    audio_codec,
    build_preview,
    ensure_directory,
    existing_files,
    match_alpha,
    normalize_path,
    save_image_sequence,
    save_video,
    supports_alpha,
    to_numpy,
    video_codec,
    write_sidecar,
)
from ..core.paths import FRAME_MARK, check_inside, resolve_root, strip_frame
from ..core.tokens import auto_tokens, format_token_reference, resolve_tokens, with_extra, wrap
from ..core.video import comfy_video_api
from ..core.wedge import PREVIEW_KEY, WedgeError, chain_jobs, wedge_metadata, wedge_tokens

ALPHA_TYPES = "IMAGE,MASK,VIDEO"


def resolve_pattern(template: str, tokens: dict, frame_padding: int, numbered: bool,
                    path_mode: str, base_path: str, file_format: str) -> tuple:
    """
    Resolve *template* into ``(resolved, root, pattern)``.

    *resolved* is the template with tokens filled in (relative to *root*,
    no extension), *pattern* the full path with extension.  Both hold
    ``FRAME_MARK`` where the frame number goes when *numbered*.  Raises
    ValueError for an empty file name, a missing base_path, or a relative
    path that escapes the output directory.
    """
    resolved = resolve_tokens(template, {**tokens, "frame": FRAME_MARK},
                              frame_padding=frame_padding)
    base = os.path.basename(resolved.replace("\\", "/"))
    frame_only = numbered and FRAME_MARK in base
    if not strip_frame(base).replace(FRAME_MARK, "").strip(" ._-") and not frame_only:
        raise ValueError(
            "[Pipedream] PD Save: no file name chosen. Enter one in 'file' (e.g. "
            f"{wrap('shot')}_{wrap('version')})" + (f"; '{template}' resolves to "
            f"'{resolved.replace(FRAME_MARK, '#')}'." if template.strip() else ".")
        )
    if not numbered:
        resolved = strip_frame(resolved)
    elif FRAME_MARK not in resolved:
        resolved = f"{resolved}{settings.get('sequence.frame_separator')}{FRAME_MARK}"

    root = resolve_root(path_mode, base_path, output_directory(), "PD Save")
    pattern = normalize_path(os.path.join(root, f"{resolved}.{file_format}"))
    if path_mode == "relative":
        check_inside(pattern, root, "PD Save", "output")
    return resolved, root, pattern


PREVIEW_LINES = 200
METADATA_INPUTS = METADATA_INPUT_NAMES


def preview_request(prompt, unique_id) -> dict | None:
    """
    The wedge preview request set on this node by the frontend, or None.

    It is a JSON string ``{"total": jobs in the queue, "axes": [{"tokens",
    "length"}]}`` for the wedges that feed this node, from the planner.
    """
    raw = (prompt or {}).get(str(unique_id), {}).get("inputs", {}).get(PREVIEW_KEY)
    if not raw:
        return None
    try:
        request = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (TypeError, ValueError):
        request = {}
    return request if isinstance(request, dict) else {}


def wedge_preview(request: dict, path_mode, base_path, template, file_format,
                  frame_padding, context, wedge, overwrite) -> dict:
    """
    List the path every job of the connected wedge chain would write.

    Nothing is written.  Flags paths written by more than one job (from
    wedges not chained into this node, or a template without the wedge
    tokens) and, with overwrite off, files that already exist.
    """
    numbered = file_format not in VIDEO_FORMATS and wrap("frame") in template
    hashes = "#" * frame_padding
    try:
        jobs = chain_jobs(wedge)
    except WedgeError as exc:
        raise ValueError(f"[Pipedream] {exc}") from exc
    base = dict(context) if context else {}
    tokens = auto_tokens()

    rows, root = [], ""
    for job_tokens in jobs:
        ctx = with_extra({**base, **job_tokens})
        resolved, root, pattern = resolve_pattern(template, {**tokens, **ctx}, frame_padding,
                                                  numbered, path_mode, base_path, file_format)
        rows.append((job_tokens.get("wedge_idx", "000"), resolved.replace(FRAME_MARK, hashes),
                     pattern.replace(FRAME_MARK, f"{settings.get('sequence.start_frame'):0{frame_padding}d}")))

    chained = {a["token"] for a in (wedge or {}).get("axes", [])}
    other = [a for a in request.get("axes", []) if not set(a.get("tokens", [])) & chained]
    repeat = 1
    for axis in other:
        repeat *= max(1, int(axis.get("length", 1)))
    queued = int(request.get("total", len(rows) * repeat) or 1)

    groups = {}
    for a in (wedge or {}).get("axes", []):
        key = a.get("group") or id(a)
        entry = groups.setdefault(key, {"tokens": [], "rows": len(a["rows"]), "solo": False})
        entry["tokens"].append(a["token"])
        entry["solo"] = entry["solo"] or bool(a.get("solo"))
    axes = " x ".join(
        f"{'+'.join(g['tokens'])} " + ("1 (solo)" if g["solo"] else str(g["rows"]))
        for g in groups.values()
    )
    lines = [f"Wedge preview: {len(rows)} output{'s' if len(rows) != 1 else ''}"
             + (f" ({axes})" if axes else "") + ", nothing written.",
             f"Root: {root}", ""]
    for idx, resolved, _ in rows[:PREVIEW_LINES]:
        lines.append(f"  [{idx}] {resolved}.{file_format}")
    if len(rows) > PREVIEW_LINES:
        lines.append(f"  ... and {len(rows) - PREVIEW_LINES} more")

    warnings = []
    if other:
        names = ", ".join("+".join(a.get("tokens", [])) for a in other)
        warnings.append(f"Not chained into this PD Save: {names}. Each path above is "
                        f"written {repeat} times ({len(rows) * repeat} jobs), each over the last.")
    seen = {}
    for idx, resolved, _ in rows:
        seen.setdefault(resolved, []).append(idx)
    clashes = {p: i for p, i in seen.items() if len(i) > 1}
    if clashes:
        path, idxs = next(iter(clashes.items()))
        warnings.append(f"{len(clashes)} path(s) are written by more than one job, e.g. "
                        f"{path}.{file_format} by jobs {', '.join(idxs)}. Add the wedge "
                        "tokens to the template.")
    if not overwrite:
        existing = [r for r in rows if os.path.exists(r[2])]
        if existing:
            warnings.append(f"{len(existing)} file(s) already exist and overwrite is off, "
                            f"so those jobs write nothing, e.g. {existing[0][1]}.{file_format}.")
    if queued != len(rows) * repeat:
        warnings.append(f"The queue makes {queued} jobs in all (other outputs' wedges).")
    if warnings:
        lines += ["", "Warnings:"] + [f"  ! {w}" for w in warnings]
    else:
        lines += ["", f"Queue makes {queued} job{'s' if queued != 1 else ''}."]

    paths = [r[2] for r in rows]
    return {
        "ui": {"token_reference": ["\n".join(lines)]},
        "result": (paths[0] if paths else "", "", "\n".join(paths), None, None),
    }


def alpha_source(alpha) -> tuple:
    """
    Return ``(matte_input, kind)`` for an ``alpha`` input value.

    *kind* is ``video`` (its frames are used), ``mask`` or ``image``.
    """
    if hasattr(alpha, "get_components"):
        return alpha.get_components().images, "video"
    return alpha, ("mask" if len(alpha.shape) <= 3 else "image")


def video_source(video) -> tuple:
    """
    Unpack a ComfyUI VIDEO into ``(images, audio, fps)``.

    Uses ``get_components()``, so it works for any VIDEO implementation
    (file, tensors, list).
    """
    components = video.get_components()
    fps = float(components.frame_rate) if components.frame_rate else 24.0
    return components.images, getattr(components, "audio", None), fps


def metadata_for(inputs: dict, file_format: str, count: int):
    """
    ``(merged ExrMetadata or None, writer or None)`` from PD Save's
    exr_metadata inputs, in input order.  The writer replaces a written
    EXR frame's header metadata; None when nothing is connected (nothing
    is written) or the format is not exr.
    """
    sources = [inputs[name] for name in METADATA_INPUTS if inputs.get(name) is not None]
    if not sources:
        return None, None
    merged = ExrMetadata.merged(sources)
    if file_format != "exr":
        print("[Pipedream] Warning: PD Save: exr_metadata is only written to exr files; "
              f"ignored for {file_format}.", file=sys.stderr)
        return merged, None
    if len(merged) > 1 and len(merged) != count:
        print(f"[Pipedream] Warning: PD Save: exr_metadata has {len(merged)} frame tables "
              f"for {count} frames; " + ("the last table repeats." if len(merged) < count
                                          else "the extra tables are ignored."),
              file=sys.stderr)

    def write(index: int, path: str):
        try:
            write_attributes(path, merged.frame(index))
        except ExrError as exc:
            raise RuntimeError(f"[Pipedream] PD Save: cannot write EXR metadata to "
                               f"'{path}': {exc}") from exc

    return merged, write


class PDSave:
    """Write images or video to ComfyUI's output dir or an absolute path using a token template."""

    DISPLAY_NAME = display_name("PD Save")
    CATEGORY = "Pipedream"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING", "STRING", "STRING", "IMAGE", "VIDEO")
    RETURN_NAMES = ("path", "path_sidecar", "path_all", "images", "video")
    OUTPUT_TOOLTIPS = (
        "First file written (the first frame of a sequence), or the video file.",
        "Sidecar JSON path (empty when save_metadata is off).",
        "Every written file, one per line.",
        "The input images (or the VIDEO's frames when only a VIDEO is connected).",
        "The written video as a ComfyUI VIDEO (video formats only).",
    )

    @classmethod
    def INPUT_TYPES(cls):
        # 'video' must stay the last output: the frontend removes it for
        # image formats, which is only index-safe for a trailing output.
        s = settings.get
        frame = wrap("frame")
        return {
            "required": {
                "path_mode": (list(PATH_MODES), {
                    "default": s("output.path_mode"),
                    "tooltip": "relative: ComfyUI output directory. "
                               "absolute: base_path (absolute or UNC path).",
                }),
                "base_path": ("STRING", {
                    "default": s("output.base_path"),
                    "tooltip": "Root folder for absolute mode. Ignored in relative mode.",
                }),
                "template": ("STRING", {
                    "default": s("output.template"), "multiline": False,
                    "display_name": "file",
                    "tooltip": f"Output path without extension. Put {frame} where the frame "
                               f"number goes (e.g. {wrap('shot')}.{frame}); without it, "
                               f"sequences get '{s('sequence.frame_separator')}"
                               f"{s('sequence.start_frame'):0{s('sequence.frame_padding')}d}' "
                               "(the start frame) before the extension.",
                }),
                "format": (list(IMAGE_FORMATS + VIDEO_FORMATS), {
                    "default": s("output.format"),
                    "tooltip": "Images (one file per frame): png/exr/jpg/webp. Video: "
                               "mp4 = H.264, mov = ProRes, webm = VP9 (audio from a "
                               "connected VIDEO is kept).",
                }),
                "start_frame": ("INT", {
                    "default": s("sequence.start_frame"), "min": 0, "max": 9999999,
                    "tooltip": "Number of the first frame of an image sequence "
                               "(1001 is the usual VFX start, leaving room for handles).",
                }),
                "frame_padding": ("INT", {
                    "default": s("sequence.frame_padding"), "min": 1, "max": 8,
                    "tooltip": "Digits in image sequence frame numbers (4: 1001, 0042).",
                }),
            },
            "optional": {
                "images": ("IMAGE", {"tooltip": "Frames to write. Connect this or 'video'. "
                                                "A fourth channel is written as alpha."}),
                "context": ("PROJECT_CONTEXT",),
                "wedge": ("WEDGE", {
                    "tooltip": "Last PD Wedge of a chain: adds {<token>} and {<token>_idx} "
                               "for each wedge, plus {wedge_idx} and {wedge_total}. "
                               "Wedge tokens override context tokens of the same name.",
                }),
                "video": ("VIDEO", {
                    "tooltip": "Optional VIDEO to write instead of 'images', with its "
                               "own frame rate and audio. With an image format its "
                               "frames are written as an image sequence.",
                }),
                "fps": ("FLOAT", {"default": s("output.fps"), "min": 1.0, "max": 240.0, "step": 0.001,
                                  "tooltip": "Video frame rate for 'images'. A connected "
                                             "VIDEO keeps its own frame rate."}),
                "crf": ("INT", {"default": s("output.crf"), "min": 0, "max": 51,
                                "tooltip": "Video quality for mp4/webm (lower = better). "
                                           "Ignored for ProRes."}),
                "prores_profile": (list(PRORES_CHOICES), {
                    "default": s("output.prores_profile"),
                    "tooltip": "mov only. auto: 4444 with alpha when there is an alpha, "
                               "otherwise 422 HQ. 4444 without alpha is 4:4:4 10-bit.",
                }),
                "create_dirs": ("BOOLEAN", {"default": s("output.create_dirs")}),
                "overwrite": ("BOOLEAN", {
                    "default": s("output.overwrite"),
                    "tooltip": "Replace existing files. When off, nothing is written if "
                               "the file (or any frame of the sequence) already exists.",
                }),
                "save_metadata": ("BOOLEAN", {"default": s("output.save_metadata"),
                                              "tooltip": "Write a sidecar .json next to the output."}),
                "exr_precision": (list(EXR_PRECISIONS), {
                    "default": s("exr.precision"),
                    "tooltip": "EXR only: half (16-bit float) or float (32-bit float).",
                }),
                "exr_compression": (list(EXR_COMPRESSIONS), {
                    "default": s("exr.compression"),
                    "tooltip": "EXR only: zip (16 scanlines), zips (1 scanline), rle or none.",
                }),
                "exr_colorspace": (list(EXR_COLORSPACES), {
                    "default": s("exr.colorspace"),
                    "tooltip": "EXR only. as is: write the values unchanged. sRGB to "
                               "linear: decode sRGB-encoded images (most generated "
                               "images) to linear light. Alpha is never converted.",
                }),
                "alpha": (ALPHA_TYPES, {
                    "tooltip": "Optional alpha for png/webp/exr and mov (ProRes 4444): a "
                               "MASK, an IMAGE (its luminance) or a VIDEO (its frames' "
                               "luminance). One frame, or as many frames as the source. "
                               "1.0 = opaque, straight; EXR is written premultiplied. Core "
                               "Load Image's mask is inverted: put Invert Mask in between.",
                }),
                **{name: ("EXR_METADATA", {
                    "tooltip": "EXR header metadata to write (exr only), from PD Load, a "
                               "context node's exr_metadata or PD Profiler. Inputs are merged "
                               "frame by frame; later inputs win on the same name. With "
                               "nothing connected no metadata is written. A source with one "
                               "table per frame writes frame N's into frame N.",
                }) for name in METADATA_INPUTS},
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO",
                       "unique_id": "UNIQUE_ID"},
        }

    def execute(self, path_mode, base_path, template, format,
                start_frame=settings.get("sequence.start_frame"),
                frame_padding=settings.get("sequence.frame_padding"),
                images=None, context=None, wedge=None, video=None, fps=settings.get("output.fps"),
                crf=settings.get("output.crf"),
                prores_profile=settings.get("output.prores_profile"),
                create_dirs=settings.get("output.create_dirs"),
                overwrite=settings.get("output.overwrite"),
                save_metadata=settings.get("output.save_metadata"),
                exr_precision=settings.get("exr.precision"),
                exr_compression=settings.get("exr.compression"),
                exr_colorspace=settings.get("exr.colorspace"), alpha=None, prompt=None,
                extra_pnginfo=None, unique_id=None, **metadata_inputs):
        """Write the source and return the ui payload plus outputs.

        Omitted optional inputs (e.g. from an API prompt) use the settings
        loaded at startup.  A wedge preview run lists paths instead.
        """
        request = preview_request(prompt, unique_id)
        if request is not None:
            return wedge_preview(request, path_mode, base_path, template, format,
                                 frame_padding, context, wedge, overwrite)

        file_format = format
        is_video = file_format in VIDEO_FORMATS
        audio = None
        if video is not None:
            frames, audio, fps = video_source(video)
        elif images is not None:
            frames = images
        else:
            raise ValueError(
                "[Pipedream] PD Save needs an input: connect 'images' or 'video'."
            )
        if frames is None or len(frames.shape) < 3 or int(frames.shape[0]) == 0:
            raise ValueError("[Pipedream] PD Save got no frames to write.")
        count, height, width = (int(x) for x in frames.shape[:3])

        matte, matte_kind = None, None
        if alpha is not None:
            source, matte_kind = alpha_source(alpha)
            matte = match_alpha(alpha_matte(source), count, height, width)
        elif len(frames.shape) == 4 and int(frames.shape[-1]) == 4:
            matte, matte_kind = to_numpy(frames[..., 3]), "images channel 4"

        profile = None
        if file_format == "mov":
            profile = prores_profile
            if profile == "auto":
                profile = "4444" if matte is not None else "422 HQ"
        if matte is not None and not supports_alpha(file_format, profile or ""):
            if alpha is not None:
                target = f"ProRes {profile}" if file_format == "mov" else file_format
                print(
                    f"[Pipedream] Warning: PD Save: {target} cannot store alpha, so the "
                    "connected alpha is ignored. Use png, webp, exr, or mov with "
                    "prores_profile auto/4444 to keep it.",
                    file=sys.stderr,
                )
            matte = None

        exr_metadata, exr_writer = metadata_for(metadata_inputs, file_format, count)

        ctx = dict(context) if context else {}
        ctx.update(wedge_tokens(wedge))
        now = datetime.now()
        numbered = not is_video and (count > 1 or wrap("frame") in template)
        first, last = start_frame, start_frame + count - 1
        frame_label = f"{first:0{frame_padding}d}"
        if count > 1:
            frame_label += f"-{last:0{frame_padding}d}"

        tokens = auto_tokens(now)
        tokens.update(with_extra(ctx))
        resolved, root, pattern = resolve_pattern(template, tokens, frame_padding, numbered,
                                                  path_mode, base_path, file_format)
        tokens["frame"] = frame_label if numbered else ""
        output_dir = output_directory()

        if numbered:
            paths = [pattern.replace(FRAME_MARK, f"{start_frame + i:0{frame_padding}d}")
                     for i in range(count)]
        else:
            paths = [pattern]
        if create_dirs:
            for path in {os.path.dirname(p): p for p in paths}.values():
                ensure_directory(path, create=True)

        if is_video:
            written = save_video(frames, paths[0], file_format, fps=fps, crf=crf,
                                 overwrite=overwrite, audio=audio, alpha=matte,
                                 prores_profile=profile or "422 HQ")
        else:
            clash = [] if overwrite else existing_files(paths)
            if clash:
                print(
                    f"[Pipedream] Error: {len(clash)} of {len(paths)} file(s) already "
                    f"exist and overwrite is disabled, nothing written: '{clash[0]}'",
                    file=sys.stderr,
                )
                written = []
            else:
                written = save_image_sequence(
                    frames, paths, alpha=matte, exr_precision=exr_precision,
                    exr_compression=exr_compression,
                    exr_linearize=exr_colorspace == "sRGB to linear",
                    exr_metadata=exr_writer,
                )
        final = written[0] if written else paths[0]
        hashes = "#" * frame_padding

        sidecar = ""
        if save_metadata and written:
            stem = strip_frame(os.path.splitext(os.path.basename(pattern))[0]) or "sequence"
            metadata = {
                "node": "PDSave",
                "timestamp": now.isoformat(timespec="seconds"),
                "template": template,
                "resolved": resolved.replace(FRAME_MARK, hashes),
                "path_mode": path_mode,
                "base_path": root,
                "format": file_format,
                "source": "video" if video is not None else "images",
                "context": ctx,
                "tokens": tokens,
                "wedge": wedge_metadata(wedge),
                "files": written,
                "image": {
                    "count": count,
                    "height": height,
                    "width": width,
                    "channels": int(frames.shape[3]) if len(frames.shape) > 3 else 1,
                },
                "alpha": {
                    "written": matte is not None,
                    "source": matte_kind,
                    "premultiplied": alpha_premultiplied(file_format) if matte is not None else None,
                },
                "settings": {"sources": list(settings.sources)},
                "prompt": prompt,
                "workflow": (extra_pnginfo or {}).get("workflow"),
            }
            if numbered:
                metadata["sequence"] = {
                    "first": first,
                    "last": last,
                    "count": count,
                    "padding": frame_padding,
                    "pattern": pattern.replace(FRAME_MARK, hashes),
                }
            if is_video:
                has_audio = bool(audio) and audio.get("waveform") is not None
                metadata["video"] = {
                    "fps": fps,
                    "codec": video_codec(file_format, profile or "422 HQ"),
                    "crf": None if file_format == "mov" else crf,
                    "prores_profile": profile,
                    "audio": audio_codec(file_format) if has_audio else None,
                    "sample_rate": int(audio.get("sample_rate", 0)) if has_audio else None,
                }
            elif file_format == "exr":
                metadata["exr"] = {
                    "precision": exr_precision,
                    "compression": exr_compression,
                    "colorspace": exr_colorspace,
                    "metadata": ({"tables": len(exr_metadata), "names": exr_metadata.names(),
                                  "varying": exr_metadata.varying()}
                                 if exr_metadata is not None else None),
                }
            sidecar_path = os.path.join(os.path.dirname(paths[0]), stem + ".json")
            sidecar = write_sidecar(sidecar_path, metadata) or ""

        previews, animated = build_preview(
            frames, written, is_video, fps, output_dir, temp_directory(), audio
        )

        if numbered:
            frame_info = f"{frame_label} ({count} frame{'s' if count > 1 else ''})"
        elif is_video:
            frame_info = "not used for video"
        else:
            frame_info = (f"not used (single image; add {wrap('frame')} to number it "
                          f"{first:0{frame_padding}d})")
        ui = {"token_reference": [format_token_reference(
            ctx, frame_padding=frame_padding, frame_info=frame_info)]}
        if written:
            ui["pd_written"] = [final]
        if previews:
            ui["images"] = previews
            if animated:
                ui["animated"] = (True,)

        video_out = None
        if is_video and os.path.isfile(final):
            video_from_file = comfy_video_api()[1]
            video_out = video_from_file(final) if video_from_file else None
        passthrough = images if images is not None else frames
        return {
            "ui": ui,
            "result": (final, sidecar, "\n".join(written), passthrough, video_out),
        }


class PDOutput(PDSave):
    """
    PD Save's former name, kept so workflows, API prompts and scripts that
    use ``PDOutput`` still load and run.  Hidden from search; new nodes are
    PD Save.  To be removed in a later minor release.
    """

    DISPLAY_NAME = display_name("PD Output (renamed PD Save)")
    DEPRECATED = True
