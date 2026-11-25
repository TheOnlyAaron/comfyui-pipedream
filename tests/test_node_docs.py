"""
Tests for tools/node_docs.py, the generator of the node pages' reference block.

Standard library only; run from the pack root::

    python -m unittest discover -s tests

The check runs on a temporary copy of ``web/docs`` (or, while that folder has
no pages, on a temporary folder with one hand-made page).
"""

import contextlib
import glob
import importlib
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "node_docs.py")
REAL_DOCS = os.path.join(ROOT, "web", "docs")

spec = importlib.util.spec_from_file_location("pd_node_docs_tool", TOOL)
node_docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(node_docs)

NODES = node_docs.load_nodes()
BY_NAME = {c.__name__: c for c in NODES}


def run(*args):
    """Run the generator in-process; returns (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = node_docs.main(list(args))
    return code, out.getvalue(), err.getvalue()


def page(name, body="Hand-written text.\n"):
    return (f"# {name}\n\n{body}\n## Inputs and outputs\n\n"
            f"{node_docs.START}\nold\n{node_docs.END}\n\nMore hand-written text.\n")


class TestCoverage(unittest.TestCase):
    def test_every_node_but_the_alias_is_covered(self):
        from_init = importlib.import_module("pipedream_docs.nodes").ALL_NODES
        expected = {c.__name__ for c in from_init} - {"PDOutput"}
        self.assertEqual(set(BY_NAME), expected)
        self.assertIn("PDSave", BY_NAME)
        self.assertEqual(len(NODES), len(BY_NAME))

    def test_every_block_renders(self):
        for name, cls in BY_NAME.items():
            block = node_docs.render_block(cls)
            self.assertIn("### Inputs", block, name)
            self.assertIn("### Outputs", block, name)
            self.assertNotIn("\U0001F4AD", node_docs.display_name(cls))


class TestRendering(unittest.TestCase):
    def test_collapsed_families(self):
        for cls, label in ((BY_NAME["PDSave"], "`exr_metadata, exr_metadata_2 … _8`"),
                           (BY_NAME["PDExrMetadataMerge"], "`exr_metadata, exr_metadata_2 … _8`"),
                           (BY_NAME["PDWedge"], "`input_1 … input_16`"),
                           (BY_NAME["PDWedge"], "`value_1 … value_16`"),
                           (BY_NAME["PDCustomContext"], "`custom_1_name … custom_10_name`"),
                           (BY_NAME["PDCustomContext"], "`custom_1_value … custom_10_value`"),
                           (BY_NAME["PDSwitch"], "`input_1 … input_8`")):
            self.assertIn(label, node_docs.render_inputs(cls), cls.__name__)
        self.assertNotIn("exr_metadata_3", node_docs.render_inputs(BY_NAME["PDSave"]))

    def test_hidden_inputs_skipped_and_combo_shortened(self):
        inputs = node_docs.render_inputs(BY_NAME["PDSave"])
        for hidden in ("extra_pnginfo", "unique_id"):
            self.assertNotIn(hidden, inputs)
        self.assertIn("(7 choices)", inputs)
        self.assertIn("relative, absolute", inputs)

    def test_output_node_line(self):
        self.assertIn("is an output node", node_docs.render_block(BY_NAME["PDSave"]))
        self.assertIn("is not an output node", node_docs.render_block(BY_NAME["PDSwitch"]))


class TestGenerator(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.docs = os.path.join(self.tmp.name, "docs")
        os.makedirs(self.docs)
        self.write("PDSave.md", page("PD Save"))

    def path(self, name):
        return os.path.join(self.docs, name)

    def write(self, name, text):
        with open(self.path(name), "w", encoding="utf-8", newline="") as fh:
            fh.write(text)

    def read(self, name):
        with open(self.path(name), encoding="utf-8", newline="") as fh:
            return fh.read()

    def test_real_pages_are_current_when_present(self):
        """Once web/docs has pages, a temporary copy must pass --check."""
        if not glob.glob(os.path.join(REAL_DOCS, "*.md")):
            self.skipTest("web/docs has no pages yet")
        copy = os.path.join(self.tmp.name, "real")
        shutil.copytree(REAL_DOCS, copy)
        code, _, err = run("--check", "--docs-dir", copy)
        self.assertEqual(code, 0, err)

    def test_fills_block_and_keeps_the_rest(self):
        self.write("PDSwitch.md", page("PD Switch"))
        run("--docs-dir", self.docs)
        text = self.read("PDSwitch.md")
        self.assertTrue(text.startswith("# PD Switch\n\nHand-written text.\n"))
        self.assertTrue(text.endswith("\nMore hand-written text.\n"))
        self.assertNotIn("\nold\n", text)
        self.assertIn("`input_1 … input_8`", text)
        before, block, after = node_docs._split(text)
        self.assertEqual(block, node_docs.render_block(BY_NAME["PDSwitch"]) + "\n")

    def test_idempotent(self):
        self.write("PDSwitch.md", page("PD Switch"))
        run("--docs-dir", self.docs)
        first = {n: self.read(n) for n in os.listdir(self.docs)}
        code, out, _ = run("--docs-dir", self.docs)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertEqual({n: self.read(n) for n in os.listdir(self.docs)}, first)

    def test_check_flags_stale_block(self):
        self.write("PDSwitch.md", page("PD Switch"))
        run("--docs-dir", self.docs)
        run("--docs-dir", self.docs)
        self.assertEqual(run("--check", "--docs-dir", self.docs)[0], 0)
        self.write("PDSwitch.md", self.read("PDSwitch.md").replace("`mode`", "`modus`"))
        code, _, err = run("--check", "--docs-dir", self.docs)
        self.assertEqual(code, 1)
        self.assertIn("PDSwitch.md", err)
        self.assertIn("out of date", err)

    def test_check_flags_missing_page(self):
        code, _, err = run("--check", "--docs-dir", self.docs)
        self.assertEqual(code, 1)
        self.assertIn("PDSwitch.md: page is missing", err)
        self.assertFalse(os.path.exists(self.path("PDSwitch.md")))

    def test_update_creates_skeletons_for_missing_pages(self):
        run("--docs-dir", self.docs)
        for name in BY_NAME:
            self.assertTrue(os.path.exists(self.path(f"{name}.md")), name)
        text = self.read("PDWedge.md")
        self.assertTrue(text.startswith("# PD Wedge\n\nTODO: describe this node.\n\n## Inputs and outputs\n"))
        self.assertIn(node_docs.START, text)
        self.assertEqual(run("--check", "--docs-dir", self.docs)[0], 0)

    def test_page_without_markers_is_reported_not_changed(self):
        text = "# PD Switch\n\nNo markers here.\n"
        self.write("PDSwitch.md", text)
        code, out, _ = run("--docs-dir", self.docs)
        self.assertEqual(code, 0)
        self.assertIn("PDSwitch.md", out)
        self.assertEqual(self.read("PDSwitch.md"), text)
        code, _, err = run("--check", "--docs-dir", self.docs)
        self.assertEqual(code, 1)
        self.assertIn("marker", err)

    def test_crlf_page_keeps_its_line_endings(self):
        self.write("PDSwitch.md", page("PD Switch").replace("\n", "\r\n"))
        run("--docs-dir", self.docs)
        text = self.read("PDSwitch.md")
        self.assertNotIn("\n", text.replace("\r\n", ""))
        self.assertEqual(run("--check", "--docs-dir", self.docs)[0], 0)

    def test_command_line_exit_status(self):
        proc = subprocess.run([sys.executable, "-I", TOOL, "--check", "--docs-dir", self.docs],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        proc = subprocess.run([sys.executable, "-I", TOOL, "--docs-dir", self.docs],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = subprocess.run([sys.executable, "-I", TOOL, "--check", "--docs-dir", self.docs],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
