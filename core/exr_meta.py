"""
OpenEXR header metadata: read it, carry it per frame, write it.

``ExrMetadata`` is the value of the ``EXR_METADATA`` socket: a list of
per-frame attribute tables (name -> :class:`Attr`).  One table applies to
every frame; with several, frame *i* takes table *i* (the last repeats
when there are fewer tables than frames).  Sources:

* ``ExrMetadata.from_files(paths)``: the headers of loaded EXR files
  (PD Load), one table per file.
* ``ExrMetadata.from_tokens(tokens, prefix)``: context tokens as string
  attributes named ``<prefix><token>`` (the context nodes).
* ``ExrMetadata.merged(sources)``: several sources, frame by frame; later
  sources win on clashing names (PD Save's inputs, in order).

Attributes keep their EXR type.  The common types are decoded to plain
values (see ``decode``); any other type keeps its raw bytes, so loading
and writing an EXR loses nothing.  Attributes that describe the image
(``STRUCTURAL``: channels, compression, windows, line order...) are never
carried: the writer owns them.

``write_attributes(path, attrs)`` replaces the non-structural attributes
of a single-part scanline EXR in place: the header is rebuilt and the
chunk offset table shifted by the bytes added or removed.  PD Save's
EXRs come from FFmpeg's encoder, which cannot write custom attributes, so
they are added afterwards this way.  Standard library only.
"""

import math
import os
import struct

MAGIC = b"\x76\x2f\x31\x01"
TILED, LONG_NAMES, DEEP, MULTIPART = 0x200, 0x400, 0x800, 0x1000

STRUCTURAL = frozenset({
    "channels", "compression", "dataWindow", "displayWindow", "lineOrder",
    "pixelAspectRatio", "screenWindowCenter", "screenWindowWidth", "tiles",
    "chunkCount", "type", "name", "version", "maxSamplesPerPixel",
})

# compression id -> scanlines per chunk
LINES_PER_CHUNK = {0: 1, 1: 1, 2: 1, 3: 16, 4: 32, 5: 16, 6: 32, 7: 32, 8: 32, 9: 256}

_FIXED = {
    "int": "<i", "float": "<f", "double": "<d",
    "v2i": "<2i", "v2f": "<2f", "v2d": "<2d", "v3i": "<3i", "v3f": "<3f", "v3d": "<3d",
    "box2i": "<4i", "box2f": "<4f", "m33f": "<9f", "m33d": "<9d", "m44f": "<16f", "m44d": "<16d",
    "chromaticities": "<8f", "timecode": "<2I", "rational": "<iI", "keycode": "<7i",
    "compression": "<B", "lineOrder": "<B", "envmap": "<B", "deepImageState": "<B",
}
SCALAR = ("int", "float", "double", "compression", "lineOrder", "envmap", "deepImageState")


# PD Save's and PD EXR Metadata Merge's inputs, in merge order.
INPUT_NAMES = ["exr_metadata"] + [f"exr_metadata_{i}" for i in range(2, 9)]


class ExrError(Exception):
    """An EXR header that cannot be read or changed."""


class Attr:
    """One attribute: its EXR type name, decoded value, and raw bytes for unknown types."""

    __slots__ = ("type", "value", "raw")

    def __init__(self, type_name: str, value, raw: bytes | None = None):
        self.type = type_name
        self.value = value
        self.raw = raw

    def __eq__(self, other):
        return (isinstance(other, Attr) and self.type == other.type
                and self.value == other.value and self.raw == other.raw)

    def __repr__(self):
        return f"Attr({self.type!r}, {self.value!r})"

    def encode(self) -> bytes:
        return encode(self.type, self.value) if self.raw is None else self.raw

    def display(self) -> str:
        """The value as text: numbers plain, vectors in brackets, timecodes HH:MM:SS:FF."""
        if self.raw is not None:
            return f"<{len(self.raw)} bytes>"
        if self.type == "timecode":
            return timecode_text(self.value[0])
        if isinstance(self.value, list):
            return "[" + ", ".join(_num(v) for v in self.value) + "]"
        return _num(self.value) if isinstance(self.value, float) else str(self.value)

    def to_json(self) -> dict:
        out = {"type": self.type, "value": self.value}
        if self.raw is not None:
            out["raw"] = self.raw.hex()
        return out

    @classmethod
    def from_json(cls, data: dict) -> "Attr":
        raw = data.get("raw")
        return cls(data["type"], data.get("value"), bytes.fromhex(raw) if raw else None)


def _num(v) -> str:
    return f"{v:.6g}" if isinstance(v, float) else str(v)


def decode(type_name: str, raw: bytes) -> Attr:
    """Decode an attribute's bytes; unknown or malformed types keep the raw bytes."""
    try:
        if type_name == "string":
            return Attr(type_name, raw.decode("utf-8", errors="replace"))
        if type_name in _FIXED:
            fmt = _FIXED[type_name]
            if struct.calcsize(fmt) != len(raw):
                raise struct.error("size mismatch")
            values = list(struct.unpack(fmt, raw))
            return Attr(type_name, values[0] if type_name in SCALAR else values)
        if type_name == "stringvector":
            items, pos = [], 0
            while pos < len(raw):
                (n,) = struct.unpack_from("<i", raw, pos)
                items.append(raw[pos + 4:pos + 4 + n].decode("utf-8", errors="replace"))
                pos += 4 + n
            return Attr(type_name, items)
        if type_name == "floatvector":
            return Attr(type_name, list(struct.unpack(f"<{len(raw) // 4}f", raw)))
    except (struct.error, ValueError):
        pass
    return Attr(type_name, None, bytes(raw))


def encode(type_name: str, value) -> bytes:
    """Encode a decoded value for *type_name*.  Raises ExrError for an impossible value."""
    try:
        if type_name == "string":
            return str(value).encode("utf-8")
        if type_name in _FIXED:
            values = [value] if type_name in SCALAR else list(value)
            return struct.pack(_FIXED[type_name], *values)
        if type_name == "stringvector":
            out = b""
            for item in value:
                b = str(item).encode("utf-8")
                out += struct.pack("<i", len(b)) + b
            return out
        if type_name == "floatvector":
            return struct.pack(f"<{len(value)}f", *value)
    except (struct.error, TypeError, ValueError) as exc:
        raise ExrError(f"cannot write {value!r} as an EXR {type_name}: {exc}") from exc
    raise ExrError(f"cannot write an EXR '{type_name}' attribute without its raw bytes")


def timecode_text(time_and_flags: int) -> str:
    """SMPTE ``HH:MM:SS:FF`` from a timecode attribute's packed BCD field."""
    t = int(time_and_flags)

    def bcd(shift, units_bits, tens_bits):
        units = (t >> shift) & ((1 << units_bits) - 1)
        tens = (t >> (shift + units_bits)) & ((1 << tens_bits) - 1)
        return tens * 10 + units

    sep = ";" if t & (1 << 6) else ":"
    return f"{bcd(24, 4, 2):02d}:{bcd(16, 4, 3):02d}:{bcd(8, 4, 3):02d}{sep}{bcd(0, 4, 2):02d}"


# ---------------------------------------------------------------------------
# Headers
# ---------------------------------------------------------------------------

class Header:
    """A single-part EXR header: version field, attributes in file order, where it ends."""

    def __init__(self, version: int, attrs: list, end: int):
        self.version = version
        self.attrs = attrs
        self.end = end

    def get(self, name):
        for n, t, raw in self.attrs:
            if n == name:
                return decode(t, raw)
        return None


def _parse(data: bytes):
    """Parse ``data`` (the file from byte 0); returns a Header or None if more bytes are needed."""
    if data[:4] != MAGIC:
        raise ExrError("not an OpenEXR file")
    if len(data) < 8:
        return None
    (version,) = struct.unpack_from("<I", data, 4)
    pos, attrs = 8, []
    while True:
        if pos >= len(data):
            return None
        if data[pos] == 0:
            return Header(version, attrs, pos + 1)
        name_end = data.find(b"\0", pos)
        type_end = data.find(b"\0", name_end + 1) if name_end >= 0 else -1
        if type_end < 0 or type_end + 5 > len(data):
            return None
        (size,) = struct.unpack_from("<i", data, type_end + 1)
        if size < 0:
            raise ExrError("corrupt attribute size")
        start = type_end + 5
        if start + size > len(data):
            return None
        attrs.append((data[pos:name_end].decode("latin-1"),
                      data[name_end + 1:type_end].decode("latin-1"), data[start:start + size]))
        pos = start + size


def read_header(path: str) -> Header:
    """Read the (first part's) header of *path*.  Raises ExrError."""
    try:
        with open(path, "rb") as fh:
            data = b""
            chunk = 65536
            while True:
                more = fh.read(chunk)
                data += more
                header = _parse(data)
                if header is not None:
                    return header
                if not more:
                    raise ExrError("header is truncated")
                chunk = min(chunk * 4, 64 * 1024 * 1024)
    except OSError as exc:
        raise ExrError(f"cannot read '{path}': {exc.strerror or exc}") from exc


def read_attributes(path: str) -> dict:
    """The non-structural attributes of *path* (name -> Attr), in file order."""
    return {n: decode(t, raw) for n, t, raw in read_header(path).attrs if n not in STRUCTURAL}


def write_attributes(path: str, attrs: dict) -> None:
    """
    Replace the non-structural attributes of the single-part scanline EXR
    at *path* with *attrs* (name -> Attr), in place.

    The structural attributes stay as they are; the chunk offset table is
    shifted by the change in header size.  Raises ExrError for tiled,
    deep or multi-part files, or a file whose offsets do not check out.
    """
    with open(path, "rb") as fh:
        data = fh.read()
    header = _parse(data)
    if header is None:
        raise ExrError("header is truncated")
    if header.version & (TILED | DEEP | MULTIPART):
        raise ExrError("only single-part scanline EXRs can take metadata")
    window = header.get("dataWindow")
    compression = header.get("compression")
    if window is None or compression is None or compression.value not in LINES_PER_CHUNK:
        raise ExrError("header has no usable dataWindow or compression")
    ymin, ymax = window.value[1], window.value[3]
    chunks = math.ceil((ymax - ymin + 1) / LINES_PER_CHUNK[compression.value])
    table_end = header.end + 8 * chunks
    if table_end > len(data):
        raise ExrError("offset table is truncated")
    offsets = struct.unpack_from(f"<{chunks}Q", data, header.end)
    if offsets and (offsets[0] < table_end or offsets[0] + 4 > len(data)
                    or struct.unpack_from("<i", data, offsets[0])[0] != ymin):
        raise ExrError("first chunk is not where the offset table says")

    kept = [(n, t, raw) for n, t, raw in header.attrs if n in STRUCTURAL]
    added = [(name, attr.type, attr.encode()) for name, attr in attrs.items() if name not in STRUCTURAL]
    body = b""
    long_names = False
    for name, type_name, raw in kept + added:
        n, t = name.encode("utf-8"), type_name.encode("utf-8")
        if not n or len(n) > 255 or len(t) > 255 or b"\0" in n:
            raise ExrError(f"attribute name '{name}' must be 1 to 255 bytes")
        long_names |= len(n) > 31 or len(t) > 31
        body += n + b"\0" + t + b"\0" + struct.pack("<i", len(raw)) + raw
    body += b"\0"
    version = header.version | LONG_NAMES if long_names else header.version & ~LONG_NAMES
    delta = (8 + len(body)) - header.end
    table = struct.pack(f"<{chunks}Q", *(o + delta for o in offsets))
    out = MAGIC + struct.pack("<I", version) + body + table + data[table_end:]

    tmp = f"{path}.pdtmp"
    try:
        with open(tmp, "wb") as fh:
            fh.write(out)
        os.replace(tmp, path)
    except OSError as exc:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise ExrError(f"cannot write '{path}': {exc.strerror or exc}") from exc


# ---------------------------------------------------------------------------
# The socket value
# ---------------------------------------------------------------------------

class ExrMetadata:
    """Per-frame EXR attributes (the ``EXR_METADATA`` socket)."""

    def __init__(self, frames: list | None = None):
        self.frames = [dict(f) for f in (frames or [])]

    def __len__(self):
        return len(self.frames)

    def __bool__(self):
        return any(self.frames)

    def frame(self, index: int) -> dict:
        """The attributes for frame *index* (0-based); the last table repeats."""
        if not self.frames:
            return {}
        return self.frames[min(max(0, index), len(self.frames) - 1)]

    def names(self) -> list:
        """Every attribute name, in first-seen order."""
        seen = {}
        for f in self.frames:
            for n in f:
                seen.setdefault(n, None)
        return list(seen)

    def varying(self) -> list:
        """Names whose value differs between frames (or that some frames lack)."""
        if len(self.frames) < 2:
            return []
        first = self.frames[0]
        return [n for n in self.names() if any(f.get(n) != first.get(n) for f in self.frames[1:])]

    @classmethod
    def from_files(cls, paths) -> "ExrMetadata":
        """One table per EXR file; files that cannot be read give an empty table."""
        frames = []
        for path in paths:
            try:
                frames.append(read_attributes(path))
            except ExrError:
                frames.append({})
        if frames and all(f == frames[0] for f in frames[1:]):
            frames = frames[:1]
        return cls(frames)

    @classmethod
    def from_tokens(cls, tokens: dict, prefix: str = "pipedream/") -> "ExrMetadata":
        """Context tokens as string attributes ``<prefix><name>``; empty values are left out."""
        table = {}
        for name, value in (tokens or {}).items():
            text = "" if value is None else str(value)
            if text.strip():
                table[f"{prefix}{name}"] = Attr("string", text)
        return cls([table] if table else [])

    @classmethod
    def merged(cls, sources) -> "ExrMetadata":
        """Combine *sources* frame by frame; later sources win on clashing names."""
        sources = [s for s in sources if s is not None and len(s)]
        if not sources:
            return cls()
        count = max(len(s) for s in sources)
        frames = []
        for i in range(count):
            table = {}
            for s in sources:
                table.update(s.frame(i))
            frames.append(table)
        return cls(frames)

    def to_json(self) -> list:
        return [{n: a.to_json() for n, a in f.items()} for f in self.frames]

    @classmethod
    def from_json(cls, data) -> "ExrMetadata":
        return cls([{n: Attr.from_json(a) for n, a in f.items()} for f in (data or [])])

    def describe(self, index: int = 0, limit: int = 400) -> str:
        """A readable listing of frame *index*'s attributes, noting which vary by frame."""
        if not self:
            return "No EXR metadata."
        varying = set(self.varying())
        table = self.frame(index)
        frames = len(self.frames)
        lines = [f"{len(table)} attribute{'s' if len(table) != 1 else ''}"
                 + (f", frame {min(index, frames - 1) + 1} of {frames} tables" if frames > 1 else "")
                 + (f"; {len(varying)} vary by frame (*)" if varying else "")]
        width = min(40, max((len(n) for n in table), default=0))
        for n, a in list(table.items())[:limit]:
            mark = "*" if n in varying else " "
            lines.append(f"{mark} {n:<{width}}  {a.display()}  ({a.type})")
        if len(table) > limit:
            lines.append(f"  ... and {len(table) - limit} more")
        return "\n".join(lines)
