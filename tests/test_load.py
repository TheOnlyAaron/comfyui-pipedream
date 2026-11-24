"""
Tests for core/load.py: finding single images, sequences and videos, and
picking frames.  Decoding is covered by the ComfyUI integration run.

Standard library only; run from the pack root::

    python -m unittest discover -s tests
"""

import json
import os
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

    def test_sequence_from_file(self):
        self.touch("sh010.1001.exr", "sh010.1002.exr", "sh010.1003.exr", "lone_0007.png",
                   "v2.png", "v3.png")
        one = load.find_media(self.path("sh010.1002.exr"))
        self.assertEqual((one["kind"], one["frames"]), ("image", [0]))
        seq = load.find_media(self.path("sh010.1002.exr"), sequence_from_file=True)
        self.assertEqual((seq["kind"], seq["frames"]), ("sequence", [1001, 1002, 1003]))
        self.assertEqual(seq["pattern"], self.path("sh010.####.exr"))
        self.assertEqual(load.find_media(self.path("lone_0007.png"),
                                         sequence_from_file=True)["kind"], "image")
        self.assertEqual(load.find_media(self.path("v2.png"),
                                         sequence_from_file=True)["kind"], "sequence")
        self.touch("0001.jpg", "0002.jpg")
        bare = load.find_media(self.path("0002.jpg"), sequence_from_file=True)
        self.assertEqual((bare["frames"], bare["pattern"]), ([1, 2], self.path("####.jpg")))

    def test_sequence_from_file_sizes_differ(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not installed")
        for name, size in (("photo_01.jpg", (632, 468)), ("photo_02.jpg", (620, 467)),
                           ("photo_03.jpg", (632, 468)), ("plate_1.jpg", (64, 32)),
                           ("plate_2.jpg", (64, 32))):
            Image.new("RGB", size).save(self.path(name))
        photo = load.find_media(self.path("photo_02.jpg"), sequence_from_file=True)
        self.assertEqual((photo["kind"], photo["paths"]), ("image", [self.path("photo_02.jpg")]))
        self.assertIn("632x468", photo["note"])
        plate = load.find_media(self.path("plate_2.jpg"), sequence_from_file=True)
        self.assertEqual((plate["kind"], plate["note"]), ("sequence", ""))

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
