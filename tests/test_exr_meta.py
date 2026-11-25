"""
Tests for core/exr_meta.py (EXR metadata).

Standard library only: EXRs are written here by hand (uncompressed or
ZIP-sized chunk tables, half RGB).  Run from the pack root::

    python -m unittest discover -s tests
"""

import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import exr_meta as em  # noqa: E402
from core.exr_meta import Attr, ExrMetadata  # noqa: E402


def attr(name, type_name, raw):
    return name.encode() + b"\0" + type_name.encode() + b"\0" + struct.pack("<i", len(raw)) + raw


def write_exr(path, width=4, height=3, compression=0, extra=b""):
    """A scanline half-RGB EXR; chunk data is fake but self-describing (y, size, bytes)."""
    chlist = b"".join(c + b"\0" + struct.pack("<iB3xii", 1, 0, 1, 1) for c in (b"B", b"G", b"R")) + b"\0"
    header = (attr("channels", "chlist", chlist)
              + attr("compression", "compression", bytes([compression]))
              + attr("dataWindow", "box2i", struct.pack("<4i", 0, 0, width - 1, height - 1))
              + attr("displayWindow", "box2i", struct.pack("<4i", 0, 0, width - 1, height - 1))
              + attr("lineOrder", "lineOrder", b"\0")
              + attr("pixelAspectRatio", "float", struct.pack("<f", 1.0))
              + attr("screenWindowCenter", "v2f", struct.pack("<2f", 0, 0))
              + attr("screenWindowWidth", "float", struct.pack("<f", 1.0))
              + extra + b"\0")
    lines = em.LINES_PER_CHUNK[compression]
    chunks = [(y, bytes([y % 251]) * (width * 6 * min(lines, height - y)))
              for y in range(0, height, lines)]
    start = 8 + len(header) + 8 * len(chunks)
    offsets, body = [], b""
    for y, pixels in chunks:
        offsets.append(start + len(body))
        body += struct.pack("<ii", y, len(pixels)) + pixels
    with open(path, "wb") as fh:
        fh.write(em.MAGIC + struct.pack("<I", 2) + header
                 + struct.pack(f"<{len(chunks)}Q", *offsets) + body)
    return [c[1] for c in chunks]


def chunks_of(path):
    """Follow the offset table; returns each chunk's (y, pixels)."""
    header = em.read_header(path)
    window = header.get("dataWindow").value
    lines = em.LINES_PER_CHUNK[header.get("compression").value]
    count = -(-(window[3] - window[1] + 1) // lines)
    with open(path, "rb") as fh:
        data = fh.read()
    out = []
    for offset in struct.unpack_from(f"<{count}Q", data, header.end):
        y, size = struct.unpack_from("<ii", data, offset)
        out.append((y, data[offset + 8:offset + 8 + size]))
    return out


class ExrCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def path(self, name="a.exr"):
        return os.path.join(self.tmp.name, name)


class AttributeTests(ExrCase):
    def test_round_trip_types(self):
        values = {
            "string": "sh010", "int": -3, "float": 1.5, "double": 2.25,
            "v2i": [1, 2], "v3f": [0.5, 1.0, 2.0], "box2i": [0, 0, 9, 9],
            "m44f": [float(i) for i in range(16)], "chromaticities": [0.64, 0.33, 0.3, 0.6, 0.15, 0.06, 0.3127, 0.329],
            "timecode": [0x01020304, 0], "rational": [24000, 1001],
            "stringvector": ["a", "bc", ""], "floatvector": [1.0, 2.0],
        }
        for type_name, value in values.items():
            got = em.decode(type_name, em.encode(type_name, value))
            self.assertEqual(got.type, type_name)
            if isinstance(value, float) or (isinstance(value, list) and value and isinstance(value[0], float)):
                self.assertEqual(em.encode(type_name, got.value), em.encode(type_name, value))
            else:
                self.assertEqual(got.value, value)

    def test_unknown_type_keeps_bytes(self):
        a = em.decode("preview", b"\x01\x02\x03")
        self.assertIsNone(a.value)
        self.assertEqual(a.encode(), b"\x01\x02\x03")
        self.assertEqual(Attr.from_json(a.to_json()), a)

    def test_timecode_text(self):
        # 01:02:03:04 in BCD: hours 0x01, minutes 0x02, seconds 0x03, frames 0x04.
        self.assertEqual(em.timecode_text(0x01020304), "01:02:03:04")
        self.assertEqual(em.timecode_text(0x01020304 | (1 << 6)), "01:02:03;04")


class WriteTests(ExrCase):
    def test_inject_keeps_pixels_and_offsets(self):
        path = self.path()
        pixels = write_exr(path, height=5)
        attrs = {
            "pipedream/shot": Attr("string", "sh010"),
            "pipedream/profiler/peak_vram_estimate_gb": Attr("float", 13.0),
            "worldToCamera": Attr("m44f", [float(i) for i in range(16)]),
            "timeCode": Attr("timecode", [0x10000000, 0]),
            "channels": Attr("string", "ignored"),
        }
        em.write_attributes(path, attrs)
        header = em.read_header(path)
        self.assertTrue(header.version & em.LONG_NAMES)
        self.assertEqual(header.get("channels").type, "chlist")
        got = em.read_attributes(path)
        self.assertEqual(list(got), ["pipedream/shot", "pipedream/profiler/peak_vram_estimate_gb",
                                     "worldToCamera", "timeCode"])
        self.assertEqual(got["pipedream/shot"].value, "sh010")
        self.assertEqual(got["worldToCamera"].value, [float(i) for i in range(16)])
        self.assertEqual(chunks_of(path), list(zip(range(5), pixels)))

    def test_replace_and_clean(self):
        path = self.path()
        write_exr(path, extra=attr("owner", "string", b"someone"))
        em.write_attributes(path, {"pipedream/a": Attr("string", "1")})
        self.assertEqual(list(em.read_attributes(path)), ["pipedream/a"])
        em.write_attributes(path, {})
        self.assertEqual(em.read_attributes(path), {})
        self.assertFalse(em.read_header(path).version & em.LONG_NAMES)
        self.assertEqual([y for y, _ in chunks_of(path)], [0, 1, 2])

    def test_zip_chunk_table(self):
        path = self.path()
        pixels = write_exr(path, height=40, compression=3)
        em.write_attributes(path, {"pipedream/note": Attr("string", "x" * 5000)})
        self.assertEqual(chunks_of(path), list(zip([0, 16, 32], pixels)))

    def test_refuses_tiled_and_bad_offsets(self):
        path = self.path()
        write_exr(path)
        with open(path, "r+b") as fh:
            fh.seek(4)
            fh.write(struct.pack("<I", 2 | em.TILED))
        with self.assertRaises(em.ExrError):
            em.write_attributes(path, {})
        write_exr(path)
        with open(path, "r+b") as fh:
            header = em.read_header(path)
            fh.seek(header.end)
            fh.write(struct.pack("<Q", 12))
        with self.assertRaises(em.ExrError):
            em.write_attributes(path, {})


class MetadataTests(ExrCase):
    def test_from_files_per_frame(self):
        paths = []
        for i in range(3):
            p = self.path(f"f.{1001 + i}.exr")
            write_exr(p, extra=attr("frameNumber", "int", struct.pack("<i", 1001 + i))
                      + attr("owner", "string", b"make"))
            paths.append(p)
        meta = ExrMetadata.from_files(paths)
        self.assertEqual(len(meta), 3)
        self.assertEqual(meta.frame(2)["frameNumber"].value, 1003)
        self.assertEqual(meta.frame(9)["frameNumber"].value, 1003)
        self.assertEqual(meta.varying(), ["frameNumber"])
        self.assertIn("* frameNumber", meta.describe())

    def test_identical_frames_collapse(self):
        paths = []
        for i in range(2):
            p = self.path(f"g.{i}.exr")
            write_exr(p, extra=attr("owner", "string", b"make"))
            paths.append(p)
        self.assertEqual(len(ExrMetadata.from_files(paths)), 1)

    def test_tokens_and_merge(self):
        ctx = ExrMetadata.from_tokens({"shot": "sh010", "version": "v002", "empty": ""})
        self.assertEqual(list(ctx.frame(0)), ["pipedream/shot", "pipedream/version"])
        plate = ExrMetadata([{"frameNumber": Attr("int", 1)}, {"frameNumber": Attr("int", 2)}])
        later = ExrMetadata.from_tokens({"shot": "sh020"})
        merged = ExrMetadata.merged([plate, ctx, None, later])
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged.frame(1)["frameNumber"].value, 2)
        self.assertEqual(merged.frame(1)["pipedream/shot"].value, "sh020")
        self.assertEqual(ExrMetadata.from_json(merged.to_json()).frames, merged.frames)
        self.assertFalse(ExrMetadata.merged([None, ExrMetadata()]))


if __name__ == "__main__":
    unittest.main()
