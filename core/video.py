"""
Shared video helpers for the Pipedream video nodes.

Works with ComfyUI's core ``VIDEO`` type (``comfy_api.latest``) so the PD
video nodes interoperate with Load Video, Save Video, Create Video and
other packs.  File-backed videos are decoded with PyAV, which ships with
ComfyUI; only the requested frames are converted to tensors.  In-memory
videos (``VideoFromComponents``) are indexed directly.

Frame indexing for file-backed videos is derived from presentation
timestamps (constant frame rate is assumed when seeking).  If a stream
has no usable timestamps or frame rate, decoding falls back to a
sequential scan from the start.

All images are returned as float32 RGB in 0-1.  8-bit sources go through
``rgb24`` and higher bit depths (10/12-bit) through ``rgb48le``, so no
precision is lost.  Alpha channels are dropped.

``comfy_api``, ``torch``, ``numpy`` and ``av`` are imported lazily so this
module can be imported outside ComfyUI.
"""

import itertools
from fractions import Fraction

_NTSC_BASES = (24, 30, 48, 60, 120)


# ---------------------------------------------------------------------------
# ComfyUI API access
# ---------------------------------------------------------------------------

def comfy_video_api():
    """
    Return ``(VideoInput, VideoFromFile, VideoFromComponents, VideoComponents)``.

    Entries are ``None`` when ``comfy_api`` is unavailable (outside ComfyUI
    or on a ComfyUI build without the video API).
    """
    try:
        from comfy_api.latest import Input, InputImpl, Types  # type: ignore[import-not-found]

        return (
            Input.Video,
            InputImpl.VideoFromFile,
            InputImpl.VideoFromComponents,
            Types.VideoComponents,
        )
    except Exception:
        return (None, None, None, None)


def fps_to_fraction(fps: float) -> Fraction:
    """
    Convert a float frame rate to a ``Fraction``.

    NTSC rates (23.976, 29.97, 59.94, ...) snap to their exact
    ``N*1000/1001`` form; anything else is limited to a small denominator.
    """
    fps = float(fps)
    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps}")
    for base in _NTSC_BASES:
        ntsc = Fraction(base * 1000, 1001)
        if abs(fps - float(ntsc)) < 0.0015:
            return ntsc
    return Fraction(fps).limit_denominator(1001)


def resolve_index(mode: str, index: int, count: int) -> int:
    """
    Resolve a ``first`` / ``last`` / ``index`` selection to an absolute index.

    Negative indices count from the end (``-1`` is the last frame).  The
    result is clamped to ``[0, count - 1]``.
    """
    if count <= 0:
        raise ValueError("Cannot select a frame from an empty sequence.")
    if mode == "first":
        idx = 0
    elif mode == "last":
        idx = count - 1
    else:
        idx = index + count if index < 0 else index
    return max(0, min(int(idx), count - 1))


def is_file_backed(video) -> bool:
    """
    Return True when *video* can be streamed from an encoded source.

    ``VideoFromComponents`` (tensors in memory) returns False.  Other
    implementations count as file-backed when they override
    ``get_stream_source``, which avoids materializing every frame.
    """
    video_input, video_from_file, video_from_components, _ = comfy_video_api()
    if video_from_components is not None and isinstance(video, video_from_components):
        return False
    method = getattr(type(video), "get_stream_source", None)
    if method is None:
        return False
    if video_from_file is not None and isinstance(video, video_from_file):
        return True
    base = getattr(video_input, "get_stream_source", None) if video_input else None
    return method is not base


# ---------------------------------------------------------------------------
# Frame conversion
# ---------------------------------------------------------------------------

def _frame_to_array(frame, crop=None):
    """
    Convert an ``av.VideoFrame`` to an ``HxWx3`` numpy array.

    Returns ``uint8`` for 8-bit sources, ``uint16`` for higher bit depths
    and ``float32`` for float pixel formats.  Rotation metadata and the
    optional ``(x, y, w, h)`` crop are applied like core ComfyUI does.
    """
    import numpy as np

    name = frame.format.name
    if "f16" in name or "f32" in name:
        arr = frame.to_ndarray(format="gbrpf32le")
    elif any(c.bits > 8 for c in frame.format.components):
        arr = frame.to_ndarray(format="rgb48le")
    else:
        arr = frame.to_ndarray(format="rgb24")

    rotation = getattr(frame, "rotation", 0) or 0
    quadrant = int(round(rotation // 90)) % 4
    if quadrant:
        arr = np.rot90(arr, k=quadrant, axes=(0, 1))
    if crop is not None:
        x, y, w, h = crop
        arr = arr[y:y + h, x:x + w]
    return np.ascontiguousarray(arr)


def _array_to_float(arr):
    """Return a float32 torch tensor in 0-1 from a ``_frame_to_array`` result."""
    import numpy as np
    import torch

    if arr.dtype == np.uint8:
        return torch.from_numpy(arr).float().div_(255.0)
    if arr.dtype == np.uint16:
        return torch.from_numpy(arr.astype(np.float32)).div_(65535.0)
    return torch.from_numpy(arr.astype(np.float32, copy=False))


def _stack_arrays(arrays):
    """
    Stack frame arrays into one ``NxHxWx3`` float32 tensor.

    The output is preallocated and filled frame by frame, so peak memory
    is the integer frames plus one float copy rather than two float copies.
    """
    import torch

    h, w, c = arrays[0].shape
    out = torch.empty((len(arrays), h, w, c), dtype=torch.float32)
    for i in range(len(arrays)):
        out[i] = _array_to_float(arrays[i])
        arrays[i] = None
    return out


# ---------------------------------------------------------------------------
# PyAV reader
# ---------------------------------------------------------------------------

class _Reader:
    """
    Seekable view of the first video stream of a file-backed VIDEO.

    Honours the trim window and crop rectangle that core nodes (Trim Video,
    Crop Video) attach to ``VideoFromFile``.
    """

    def __init__(self, video):
        from .media import import_av

        self._av = import_av()
        self.source = video.get_stream_source()
        trim = getattr(video, "get_active_trim_window", None)
        self.start_time, self.duration = trim() if trim else (0.0, 0.0)
        crop = getattr(video, "get_active_crop_rect", None)
        self.crop = crop() if crop else None

        self.container = None
        self._reopen()

        tb = self.stream.time_base
        rate = self.stream.average_rate or self.stream.guessed_rate
        self.time_base = Fraction(tb) if tb else None
        self.rate = Fraction(rate) if rate else None
        self.start_pts = int(self.start_time / tb) if tb else 0
        self.end_pts = (
            int((self.start_time + self.duration) / tb) if (tb and self.duration) else None
        )
        self.pts_per_frame = (
            1 / (self.rate * self.time_base) if (self.rate and self.time_base) else None
        )
        self._first_pts = None

    def _open(self):
        if hasattr(self.source, "seek"):
            self.source.seek(0)
        return self._av.open(self.source, mode="r")

    def _reopen(self):
        """(Re)open the container, e.g. for sources that cannot seek."""
        if self.container is not None:
            self.container.close()
        self.container = self._open()
        if not self.container.streams.video:
            self.container.close()
            raise ValueError("Video has no video stream.")
        self.stream = self.container.streams.video[0]
        self.stream.thread_type = "AUTO"

    def close(self):
        self.container.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @property
    def fps(self) -> float:
        return float(self.rate) if self.rate else 0.0

    def _decode(self, seek_pts=None):
        """Yield frames in presentation order inside the trim window."""
        target = self.start_pts if seek_pts is None else max(int(seek_pts), self.start_pts)
        # Always seek: it also flushes the decoder after a previous pass hit EOF.
        try:
            self.container.seek(target, stream=self.stream, backward=True)
        except self._av.error.FFmpegError:
            self._reopen()
        for packet in self.container.demux(self.stream):
            try:
                frames = packet.decode()
            except self._av.error.InvalidDataError:
                continue
            for frame in frames:
                if frame.pts is not None:
                    if frame.pts < self.start_pts:
                        continue
                    if self.end_pts is not None and frame.pts >= self.end_pts:
                        return
                yield frame

    def _timed(self) -> bool:
        """Return True when timestamp-based seeking can be used."""
        if self.pts_per_frame is None:
            return False
        if self._first_pts is None:
            gen = self._decode()
            first = next(gen, None)
            gen.close()
            if first is None or first.pts is None:
                self.pts_per_frame = None
                return False
            self._first_pts = first.pts
        return True

    def _index_of(self, pts) -> int:
        return int(round(Fraction(pts - self._first_pts) / self.pts_per_frame))

    def _pts_of(self, index):
        return self._first_pts + index * self.pts_per_frame

    def reported_count(self):
        """Frame count from container metadata, or None if unavailable."""
        stream = self.stream
        if stream.frames and stream.frames > 0 and not self.start_time and not self.duration:
            return int(stream.frames)
        if not self.rate:
            return None
        if stream.duration is not None and self.time_base:
            total = float(stream.duration * self.time_base)
        elif self.container.duration is not None:
            total = self.container.duration / self._av.time_base
        else:
            return None
        available = total - self.start_time
        if self.duration:
            available = min(available, self.duration)
        count = int(round(available * float(self.rate)))
        return count if count > 0 else None

    def indexed(self, start_index: int = 0):
        """
        Yield ``(index, frame)`` for frames at or after *start_index*.

        Seeks to the nearest keyframe before the target when timestamps
        allow; otherwise (or if the seek lands past the target) decodes
        sequentially from the start.
        """
        if start_index > 0 and self._timed():
            gen = self._decode(seek_pts=self._pts_of(start_index))
            head = next(gen, None)
            if head is not None and head.pts is not None and self._index_of(head.pts) <= start_index:
                for frame in itertools.chain((head,), gen):
                    if frame.pts is None:
                        continue
                    idx = self._index_of(frame.pts)
                    if idx >= start_index:
                        yield idx, frame
                return
            gen.close()

        for idx, frame in enumerate(self._decode()):
            if idx >= start_index:
                yield idx, frame

    def frame_at(self, index: int):
        """Return ``(index, frame)`` for the first frame at or after *index*, or None."""
        gen = self.indexed(index)
        found = next(gen, None)
        gen.close()
        return found

    def last(self):
        """
        Return ``(index, frame)`` for the final frame.

        Seeks to the latest position any metadata suggests and decodes to
        the end, so an under- or over-reported frame count still yields the
        true last frame.  Falls back to a full sequential decode.
        """
        if self._timed():
            hints = []
            count = self.reported_count()
            if count:
                hints.append(self._pts_of(count - 1))
            if self.end_pts is not None:
                hints.append(self.end_pts - self.pts_per_frame)
            elif self.stream.duration is not None:
                hints.append((self.stream.start_time or 0) + self.stream.duration - self.pts_per_frame)
            target = max(hints) if hints else None
            if target is not None and target > self._first_pts:
                last = None
                for frame in self._decode(seek_pts=target):
                    if frame.pts is not None:
                        last = frame
                if last is not None:
                    return self._index_of(last.pts), last

        last, idx = None, -1
        for idx, frame in enumerate(self._decode()):
            last = frame
        if last is None:
            raise ValueError("Video contains no decodable frames.")
        return idx, last


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------

def _decode_audio(reader: _Reader, t0: float, t1):
    """
    Decode the first audio stream between *t0* and *t1* seconds.

    *t1* of None means "to the end".  Returns a ComfyUI AUDIO dict
    (``waveform`` ``1xCxS`` float32, ``sample_rate``) or None when the
    source has no audio.
    """
    import numpy as np
    import torch

    av = reader._av
    container = reader._open()
    try:
        if not container.streams.audio:
            return None
        stream = container.streams.audio[0]
        sr = int(stream.sample_rate or stream.codec_context.sample_rate or 0)
        if sr <= 0:
            return None
        tb = stream.time_base
        if t0 > 1.0 and tb:
            container.seek(int((t0 - 1.0) / tb), stream=stream, backward=True)

        first = int(round(t0 * sr))
        stop = int(round(t1 * sr)) if t1 is not None else None
        resampler = av.AudioResampler(format="fltp")
        chunks, pos = [], None

        def take(frames):
            nonlocal pos
            for out in frames:
                data = out.to_ndarray()
                start = pos
                pos += data.shape[1]
                lo = max(first - start, 0)
                hi = data.shape[1] if stop is None else min(stop - start, data.shape[1])
                if hi > lo:
                    chunks.append(data[:, lo:hi])

        for packet in container.demux(stream):
            try:
                decoded = packet.decode()
            except av.error.InvalidDataError:
                continue
            for frame in decoded:
                if pos is None:
                    pos = int(round(float(frame.pts * tb) * sr)) if frame.pts is not None else 0
                take(resampler.resample(frame))
            if stop is not None and pos is not None and pos >= stop:
                break
        if pos is not None:
            take(resampler.resample(None))

        if not chunks:
            channels = stream.channels or 1
            data = np.zeros((channels, 0), dtype=np.float32)
        else:
            data = np.concatenate(chunks, axis=1).astype(np.float32, copy=False)
        return {"waveform": torch.from_numpy(np.ascontiguousarray(data)).unsqueeze(0), "sample_rate": sr}
    finally:
        container.close()


def _slice_audio(audio, t0: float, t1):
    """Slice a ComfyUI AUDIO dict to ``[t0, t1)`` seconds (t1 None = to end)."""
    if audio is None:
        return None
    sr = int(audio["sample_rate"])
    lo = int(round(t0 * sr))
    hi = int(round(t1 * sr)) if t1 is not None else None
    return {"waveform": audio["waveform"][..., lo:hi], "sample_rate": sr}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def read_frame(video, mode: str = "first", index: int = 0):
    """
    Decode a single frame from a VIDEO.

    Returns ``(image, frame_index, frame_count, fps)`` where *image* is a
    ``1xHxWx3`` float32 tensor and *frame_index* is the resolved absolute
    index.  Only the needed frame is decoded for file-backed videos.

    *frame_count* is exact when the end of the video had to be located
    (``last`` or negative indices); otherwise it comes from container
    metadata and is corrected upward if a later frame is found.
    """
    if not is_file_backed(video):
        comps = video.get_components()
        images = comps.images
        count = int(images.shape[0])
        idx = resolve_index(mode, index, count)
        return images[idx:idx + 1, ..., :3], idx, count, float(comps.frame_rate)

    with _Reader(video) as reader:
        needs_end = mode == "last" or (mode == "index" and index < 0)
        found, count = None, None
        if needs_end:
            last_idx, last_frame = reader.last()
            count = last_idx + 1
            if mode == "last" or index == -1:
                found = (last_idx, last_frame)
            else:
                found = reader.frame_at(max(count + index, 0)) or (last_idx, last_frame)
        else:
            target = 0 if mode == "first" else index
            found = reader.frame_at(target)
            if found is None:
                last_idx, last_frame = reader.last()
                found, count = (last_idx, last_frame), last_idx + 1

        if found is None:
            raise ValueError("Video contains no decodable frames.")
        idx, frame = found
        if count is None:
            count = max(reader.reported_count() or 0, idx + 1)
        image = _array_to_float(_frame_to_array(frame, reader.crop)).unsqueeze(0)
        return image, int(idx), int(count), reader.fps


def read_frames(video, start_frame: int = 0, frame_limit: int = 0, step: int = 1):
    """
    Decode a range of frames (and matching audio) from a VIDEO.

    Selects every *step*-th frame starting at *start_frame*, up to
    *frame_limit* frames (0 = until the end).  Returns
    ``(images, audio, fps, frame_count)``; *fps* is the source rate divided
    by *step* so images and audio stay in sync.  Audio covers the full
    time span of the selection, or is None if the video has none.
    """
    start_frame = max(int(start_frame), 0)
    frame_limit = max(int(frame_limit), 0)
    step = max(int(step), 1)

    if not is_file_backed(video):
        comps = video.get_components()
        total = int(comps.images.shape[0])
        if start_frame >= total:
            raise ValueError(f"start_frame {start_frame} is past the end of the video ({total} frames).")
        end = total if not frame_limit else min(total, start_frame + frame_limit * step)
        images = comps.images[start_frame:end:step, ..., :3]
        rate = Fraction(comps.frame_rate)
        span_end = min(total, start_frame + images.shape[0] * step)
        audio = _slice_audio(comps.audio, float(start_frame / rate), float(span_end / rate))
        return images, audio, float(rate) / step, int(images.shape[0])

    with _Reader(video) as reader:
        arrays, last_seen = [], None
        stop = start_frame + frame_limit * step if frame_limit else None
        for idx, frame in reader.indexed(start_frame):
            if stop is not None and idx >= stop:
                break
            last_seen = idx
            if (idx - start_frame) % step == 0:
                arrays.append(_frame_to_array(frame, reader.crop))
        if not arrays:
            raise ValueError(f"start_frame {start_frame} is past the end of the video.")

        rate = reader.rate or Fraction(1)
        t0 = reader.start_time + float(start_frame / rate)
        if stop is None and last_seen is not None and reader.duration == 0:
            t1 = None
        else:
            span = min(len(arrays) * step, last_seen + 1 - start_frame)
            t1 = t0 + float(span / rate)
        audio = _decode_audio(reader, t0, t1)
        images = _stack_arrays(arrays)
        return images, audio, float(rate) / step, int(images.shape[0])


def images_to_video(images, fps: float, audio=None):
    """
    Wrap an IMAGE batch (and optional AUDIO) as an in-memory core VIDEO.

    Returns a ``VideoFromComponents``; nothing is encoded or written.
    Alpha channels are dropped.
    """
    _, _, video_from_components, video_components = comfy_video_api()
    if video_from_components is None:
        raise RuntimeError("PD Images To Video requires ComfyUI's comfy_api video support.")
    if images.shape[0] == 0:
        raise ValueError("No images to convert to video.")
    components = video_components(
        images=images[..., :3],
        audio=audio,
        frame_rate=fps_to_fraction(fps),
    )
    return video_from_components(components)
