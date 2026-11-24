"""
Tests for core/load.py: finding single images, sequences and videos, and
picking frames.  Decoding is covered by the ComfyUI integration run.

Standard library only; run from the pack root::

    python -m unittest discover -s tests
"""

import json
import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import load  # noqa: E402


class FindCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name

    def touch(self, *names):
        for name in names:
            open(os.path.join(self.dir, name), "w").close()

    def path(self, name):
        return os.path.join(self.dir, name)

    def test_single_with_and_without_extension(self):
        self.touch("plate.png")
        for template, fmt in (("plate.png", "auto"), ("plate", "auto"), ("plate", "png")):
            media = load.find_media(self.path(template), fmt)
            self.assertEqual((media["kind"], media["ext"]), ("image", "png"))
            self.assertEqual(media["paths"], [self.path("plate.png")])

    def test_sequence_marks(self):
        self.touch("sh010.1001.exr", "sh010.1002.exr", "sh010.1004.exr", "other.1001.exr")
        for template in ("sh010.####.exr", "sh010.%04d", f"sh010.{load.FRAME_MARK}", "sh010"):
            media = load.find_media(self.path(template), "auto")
            self.assertEqual(media["kind"], "sequence", template)
            self.assertEqual(media["frames"], [1001, 1002, 1004])
            self.assertEqual(media["pattern"], self.path("sh010.####.exr"))

    def test_mark_in_folder_name_part(self):
        self.touch("sh010_v001_0001.png", "sh010_v001_0002.png")
        media = load.find_media(self.path("sh010_v001_####"), "png")
        self.assertEqual(media["frames"], [1, 2])
        self.assertEqual(media["pattern"], self.path("sh010_v001_####.png"))

    def test_video(self):
        self.touch("edit_v002.mov")
        media = load.find_media(self.path("edit_v002"), "auto")
        self.assertEqual((media["kind"], media["ext"]), ("video", "mov"))

    def test_auto_refuses_to_guess(self):
        self.touch("plate.png", "plate.exr")
        with self.assertRaisesRegex(ValueError, "set format"):
            load.find_media(self.path("plate"), "auto")
        self.assertEqual(load.find_media(self.path("plate"), "exr")["ext"], "exr")

    def test_jpeg_alias(self):
        self.touch("ref.jpeg")
        self.assertEqual(load.find_media(self.path("ref"), "jpg")["ext"], "jpeg")

    def test_not_found(self):
        self.touch("plate.png")
        with self.assertRaisesRegex(load.MediaNotFound, "plate_v002"):
            load.find_media(self.path("plate_v002"), "auto")
        with self.assertRaisesRegex(load.MediaNotFound, "does not exist"):
            load.find_media(self.path("nope/plate"), "png")

    def test_sequence_auto(self):
        self.touch("sh010.1001.exr", "sh010.1002.exr", "sh010.1003.exr", "lone_0007.png",
                   "v2.png", "v3.png")
        one = load.find_media(self.path("sh010.1002.exr"))
        self.assertEqual((one["kind"], one["frames"]), ("image", [0]))
        seq = load.find_media(self.path("sh010.1002.exr"), sequence_mode="auto")
        self.assertEqual((seq["kind"], seq["frames"]), ("sequence", [1001, 1002, 1003]))
        self.assertEqual(seq["pattern"], self.path("sh010.####.exr"))
        self.assertEqual(load.find_media(self.path("lone_0007.png"),
                                         sequence_mode="auto")["kind"], "image")
        self.assertEqual(load.find_media(self.path("v2.png"),
                                         sequence_mode="auto")["kind"], "sequence")
        self.touch("0001.jpg", "0002.jpg")
        bare = load.find_media(self.path("0002.jpg"), sequence_mode="auto")
        self.assertEqual((bare["frames"], bare["pattern"]), ([1, 2], self.path("####.jpg")))

    def test_sequence_auto_sizes_differ(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not installed")
        for name, size in (("photo_01.jpg", (632, 468)), ("photo_02.jpg", (620, 467)),
                           ("photo_03.jpg", (632, 468)), ("plate_1.jpg", (64, 32)),
                           ("plate_2.jpg", (64, 32))):
            Image.new("RGB", size).save(self.path(name))
        photo = load.find_media(self.path("photo_02.jpg"), sequence_mode="auto")
        self.assertEqual((photo["kind"], photo["paths"]), ("image", [self.path("photo_02.jpg")]))
        self.assertIn("632x468", photo["note"])
        plate = load.find_media(self.path("plate_2.jpg"), sequence_mode="auto")
        self.assertEqual(plate["kind"], "sequence")
        self.assertIn("guessed", plate["note"])

    def write_exr_header(self, name, width, height):
        """A minimal EXR header (magic, version, compression and dataWindow)."""
        def attr(key, kind, value):
            return key + b"\0" + kind + b"\0" + struct.pack("<i", len(value)) + value
        data = (b"\x76\x2f\x31\x01" + struct.pack("<i", 2)
                + attr(b"compression", b"compression", b"\x03")
                + attr(b"dataWindow", b"box2i", struct.pack("<4i", 0, 0, width - 1, height - 1))
                + b"\0")
        with open(self.path(name), "wb") as fh:
            fh.write(data)

    def test_exr_size_from_header(self):
        self.write_exr_header("a.exr", 512, 256)
        self.assertEqual(load._image_size(self.path("a.exr")), (512, 256))

    def test_sequence_auto_exr_sizes_differ(self):
        for name, size in (("Sr388_256.exr", 256), ("Sr388_512.exr", 512),
                           ("sh_1001.exr", 64), ("sh_1002.exr", 64)):
            self.write_exr_header(name, size, size)
        wedge = load.find_media(self.path("Sr388_512.exr"), sequence_mode="auto")
        self.assertEqual(wedge["kind"], "image")
        self.assertIn("256x256", wedge["note"])
        seq = load.find_media(self.path("sh_1002.exr"), sequence_mode="auto")
        self.assertEqual(seq["frames"], [1001, 1002])

    def write_sidecar(self, name, sequence_pattern=None):
        data = {"node": "PDOutput", "context": {}}
        if sequence_pattern:
            data["sequence"] = {"first": 1001, "last": 1002, "pattern": sequence_pattern}
        with open(self.path(name), "w") as fh:
            json.dump(data, fh)

    def test_sequence_modes(self):
        self.touch("sh010.1001.exr", "sh010.1002.exr", "lone_0007.png")
        one = load.find_media(self.path("sh010.1002.exr"), sequence_mode="single file")
        self.assertEqual((one["kind"], one["note"]), ("image", ""))
        forced = load.find_media(self.path("sh010.1002.exr"), sequence_mode="sequence")
        self.assertEqual(forced["frames"], [1001, 1002])
        alone = load.find_media(self.path("lone_0007.png"), sequence_mode="sequence")
        self.assertEqual(alone["kind"], "image")
        self.assertIn("no other numbered files", alone["note"])
        marked = load.find_media(self.path("sh010.####.exr"), sequence_mode="single file")
        self.assertEqual(marked["kind"], "sequence")

    def test_auto_sidecar_single(self):
        self.touch("seed_101.png", "seed_102.png")
        self.write_sidecar("seed_101.json")
        media = load.find_media(self.path("seed_101.png"), sequence_mode="auto")
        self.assertEqual(media["kind"], "image")
        self.assertIn("seed_101.json has no sequence", media["note"])
        self.assertIn("set sequence_mode to sequence", media["note"])
        forced = load.find_media(self.path("seed_101.png"), sequence_mode="sequence")
        self.assertEqual(forced["kind"], "sequence")

    def test_auto_sidecar_sequence(self):
        self.touch("sh010.1001.exr", "sh010.1002.exr")
        self.write_sidecar("sh010.json", "D:\\shots\\sh010.####.exr")
        media = load.find_media(self.path("sh010.1002.exr"), sequence_mode="auto")
        self.assertEqual(media["kind"], "sequence")
        self.assertIn("from sidecar sh010.json", media["note"])

    def test_auto_sidecar_other_pattern_ignored(self):
        self.touch("sh010.1001.exr", "sh010.1002.exr")
        self.write_sidecar("sh010.json", "/shots/sh010_####.exr")
        media = load.find_media(self.path("sh010.1002.exr"), sequence_mode="auto")
        self.assertEqual(media["kind"], "sequence")
        self.assertIn("guessed", media["note"])

    def test_auto_unpadded_numbers(self):
        self.touch("seed_1.png", "seed_2.png", "seed_10.png", "take_01.png", "take_02.png",
                   "take_10.png")
        seed = load.find_media(self.path("seed_2.png"), sequence_mode="auto")
        self.assertEqual(seed["kind"], "image")
        self.assertIn("unpadded numbers (seed_1.png ... seed_10.png)", seed["note"])
        take = load.find_media(self.path("take_02.png"), sequence_mode="auto")
        self.assertEqual(take["kind"], "sequence")

    def test_auto_same_size_photos_stay_a_sequence(self):
        self.touch("IMG_0001.jpg", "IMG_0002.jpg")
        media = load.find_media(self.path("IMG_0002.jpg"), sequence_mode="auto")
        self.assertEqual(media["kind"], "sequence")
        self.assertIn("set sequence_mode to single file", media["note"])

    def test_normalize_sequence_mode(self):
        for value, mode in ((True, "auto"), (False, "single file"), ("false", "single file"),
                            ("Sequence", "sequence"), ("single file", "single file"),
                            ("bogus", "auto"), (None, "auto")):
            self.assertEqual(load.normalize_sequence_mode(value), mode, value)

    def test_select_frames(self):
        self.touch(*[f"s.{n}.png" for n in (1001, 1002, 1003, 1005, 1006, 1007)])
        media = load.find_media(self.path("s.####.png"))
        paths, frames, missing = load.select_frames(media)
        self.assertEqual((frames, missing), ([1001, 1002, 1003, 1005, 1006, 1007], [1004]))
        _, frames, missing = load.select_frames(media, start_frame=1002, frame_count=3)
        self.assertEqual((frames, missing), ([1002, 1003], [1004]))
        _, frames, _ = load.select_frames(media, every_nth=2)
        self.assertEqual(frames, [1001, 1003, 1005, 1007])
        with self.assertRaisesRegex(ValueError, "after the last frame"):
            load.select_frames(media, start_frame=2000)

    def test_sidecar(self):
        self.touch("sh010_v001.1001.png")
        with open(self.path("sh010_v001.json"), "w") as fh:
            json.dump({"context": {"shot": "sh010", "version": "v001"}}, fh)
        media = load.find_media(self.path("sh010_v001"))
        self.assertEqual(load.sidecar_path(media["pattern"], media["kind"]),
                         self.path("sh010_v001.json"))
        self.assertEqual(load.read_sidecar(media["pattern"], media["kind"]),
                         {"shot": "sh010", "version": "v001"})
        self.assertEqual(load.read_sidecar(self.path("x.png"), "image"), {})

    def test_clean_and_split(self):
        self.touch("my plate.JPG")
        full = self.path("my plate.JPG")
        self.assertEqual(load.clean_path(f'  "{full}" '), full)
        self.assertEqual(load.clean_path(f"'{full}'"), full)
        self.assertTrue(load.looks_absolute("C:\\Users\\x.png"))
        self.assertTrue(load.looks_absolute("\\\\server\\share\\x.exr"))
        self.assertFalse(load.looks_absolute("plate.exr"))
        self.assertEqual(load.split_file(f'"{full}"'), {"folder": self.dir, "name": "my plate.JPG"})
        self.assertIsNone(load.split_file(self.path("missing.png")))
        self.assertIsNone(load.split_file(self.dir))
        self.assertIsNone(load.split_file("my plate.JPG"))

    def test_fingerprint_sees_new_frames(self):
        self.touch("s.1001.png")
        before = load.fingerprint([self.path("s.1001.png")])
        os.utime(self.dir, ns=(1, 1))
        self.assertNotEqual(before, load.fingerprint([self.path("s.1001.png")]))


if __name__ == "__main__":
    unittest.main()
