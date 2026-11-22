"""
Tests for core/settings.py and the settings-driven parts of core/tokens.py.

Standard library only; run from the pack root::

    python -m unittest discover -s tests
"""

import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import settings, tokens  # noqa: E402

EXAMPLE = os.path.join(ROOT, "pipedream.example.toml")


class SettingsCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.load, None, "")

    def write(self, name, text):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def load(self, user=None, facility=""):
        """Load quietly; returns the printed warnings."""
        err = StringIO()
        with redirect_stderr(err):
            settings.load(user_path=user, facility_path=facility)
        return err.getvalue()

    def assertWarned(self, *parts):
        self.assertTrue(any(all(p in w for p in parts) for w in settings.warnings),
                        f"no warning with {parts}: {settings.warnings}")


class TestLoading(SettingsCase):
    def test_builtin_defaults(self):
        self.assertEqual(self.load(), "")
        for key, spec in settings.SCHEMA.items():
            self.assertEqual(settings.get(key), spec.default, key)
        self.assertEqual(settings.sources, [])
        self.assertEqual(settings.summary(), "settings: facility (none), user (none)")

    def test_precedence_and_partial_files(self):
        user = self.write("user.toml", '[output]\nformat = "exr"\ncrf = 20\n'
                                       '[sequence]\nframe_separator = "_"\n')
        facility = self.write("fac.toml", '[output]\nformat = "mov"\n')
        self.assertEqual(self.load(user, facility), "")
        self.assertEqual(settings.get("output.format"), "mov")
        self.assertEqual(settings.get("output.crf"), 20)
        self.assertEqual(settings.get("sequence.frame_separator"), "_")
        self.assertEqual(settings.get("output.fps"), 24.0)
        self.assertEqual([s["scope"] for s in settings.sources], ["user", "facility"])
        self.assertEqual(settings.summary(), f"settings: facility {facility}, user {user}")

    def test_facility_from_env(self):
        facility = self.write("fac.toml", "[exr]\ncompression = 'none'\n")
        with mock.patch.dict(os.environ, {settings.ENV_VAR: facility}):
            self.load(None, None)
        self.assertEqual(settings.get("exr.compression"), "none")

    def test_int_accepted_for_float(self):
        self.load(None, self.write("f.toml", "[output]\nfps = 25\n"))
        self.assertIsInstance(settings.get("output.fps"), float)
        self.assertEqual(settings.get("output.fps"), 25.0)

    def test_invalid_type_falls_through(self):
        user = self.write("user.toml", "[output]\ncrf = 20\n")
        facility = self.write("fac.toml", '[output]\ncrf = "high"\noverwrite = 1\n')
        printed = self.load(user, facility)
        self.assertEqual(settings.get("output.crf"), 20)
        self.assertFalse(settings.get("output.overwrite"))
        self.assertWarned(facility, "output.crf", "expected an integer")
        self.assertWarned(facility, "output.overwrite", "true or false")
        self.assertEqual(printed.count("Settings warning"), 2)

    def test_out_of_range_and_bad_choice(self):
        path = self.write("f.toml", '[output]\ncrf = 99\nfps = 0.5\nformat = "tiff"\n'
                                    '[sequence]\nframe_separator = "/"\n'
                                    '[tokens]\ndate_format = ""\n')
        self.load(None, path)
        self.assertEqual(settings.get("output.crf"), 18)
        self.assertEqual(settings.get("output.fps"), 24.0)
        self.assertEqual(settings.get("output.format"), "png")
        self.assertEqual(settings.get("sequence.frame_separator"), ".")
        self.assertWarned("output.crf", "outside 0..51")
        self.assertWarned("output.fps", "outside")
        self.assertWarned("output.format", "'tiff' is not one of")
        self.assertWarned("sequence.frame_separator")
        self.assertWarned("tokens.date_format")

    def test_unknown_keys(self):
        path = self.write("f.toml", '[output]\nformatt = "exr"\n[outptu]\nformat = "exr"\n'
                                    'loose = 1\n')
        self.load(None, path)
        self.assertEqual(settings.get("output.format"), "png")
        self.assertWarned(path, "unknown key 'output.formatt'")
        self.assertWarned(path, "'outptu'")
        self.assertEqual(len(settings.warnings), 2)

    def test_top_level_key_is_unknown(self):
        path = self.write("f.toml", 'format = "exr"\n')
        self.load(None, path)
        self.assertWarned("unknown table or key 'format'")

    def test_bad_toml_syntax(self):
        user = self.write("user.toml", "[output]\ncrf = 20\n")
        facility = self.write("fac.toml", '[output\nformat = "exr"\n')
        self.load(user, facility)
        self.assertWarned(facility, "invalid TOML")
        self.assertEqual(settings.get("output.crf"), 20)
        self.assertEqual(settings.get("output.format"), "png")
        self.assertEqual([s["scope"] for s in settings.sources], ["user"])

    def test_missing_facility_file_warns_once(self):
        missing = os.path.join(self.tmp.name, "nope.toml")
        with mock.patch.dict(os.environ, {settings.ENV_VAR: missing}):
            printed = self.load(None, None)
        self.assertEqual(printed.count("Settings warning"), 1)
        self.assertIn(missing, printed)
        self.assertEqual(settings.sources, [])

    def test_missing_user_file_is_silent(self):
        self.assertEqual(self.load(os.path.join(self.tmp.name, "nope.toml"), ""), "")

    def test_without_toml_parser(self):
        path = self.write("f.toml", '[output]\nformat = "exr"\n')
        with mock.patch.object(settings, "_toml", None):
            self.load(None, path)
        self.assertWarned("Python 3.11+", "tomli")
        self.assertEqual(settings.get("output.format"), "png")
        self.assertEqual(settings.sources, [])

    def test_equal_delimiters_revert(self):
        self.load(None, self.write("f.toml", '[tokens]\nopen = "%"\nclose = "%"\n'))
        self.assertEqual(tokens.delimiters(), ("{", "}"))
        self.assertWarned("tokens.open and tokens.close")

    def test_delimiter_rules(self):
        self.load(None, self.write("f.toml", '[tokens]\nopen = ""\nclose = "x"\n'))
        self.assertEqual(tokens.delimiters(), ("{", "}"))
        self.assertWarned("tokens.open", "must not be empty")
        self.assertWarned("tokens.close", "letters")


class TestTokens(SettingsCase):
    def test_custom_delimiters(self):
        for open_, close in (("<", ">"), ("[[", "]]")):
            path = self.write("f.toml", f'[tokens]\nopen = "{open_}"\nclose = "{close}"\n')
            self.assertEqual(self.load(None, path), "")
            tpl = f"{open_}project{close}/{{shot}}_{open_}frame{close}"
            self.assertEqual(tokens.resolve_tokens(tpl, {"project": "P", "shot": "S"}),
                             "P/{shot}_####")
            self.assertEqual(settings.get("shot_token.template"),
                             f"{open_}project{close}_{open_}shot{close}_{open_}version{close}")
            ref = tokens.format_token_reference({"project": "P"})
            self.assertIn(f"{open_}project{close}", ref)
            self.assertIn(f"{open_}frame{close}", ref)

    def test_explicit_template_not_rewritten(self):
        path = self.write("f.toml", '[tokens]\nopen = "<"\nclose = ">"\n'
                                    '[output]\ntemplate = "<shot>/{literal}"\n')
        self.load(None, path)
        self.assertEqual(settings.get("output.template"), "<shot>/{literal}")
        self.assertEqual(settings.get("output.template").count("<"), 1)

    def test_extra_tokens(self):
        user = self.write("user.toml", '[tokens.extra]\nfacility = "USER"\nsite = "LA"\n')
        facility = self.write(
            "fac.toml", '[tokens.extra]\nfacility = "MAKE"\nshow_root = "//nas/shows"\n'
                        'year = 2026\nframe = "x"\nbad = true\n')
        self.load(user, facility)
        extra = settings.get("tokens.extra")
        self.assertEqual(extra, {"facility": "MAKE", "site": "LA",
                                 "show_root": "//nas/shows", "year": "2026"})
        self.assertWarned("tokens.extra.frame", "reserved")
        self.assertWarned("tokens.extra.bad", "string or number")
        tpl = "{show_root}/{facility}_{site}_{year}_{shot}"
        self.assertEqual(tokens.resolve_tokens(tpl, {"shot": "sh010", "site": "NY"}),
                         "//nas/shows/MAKE_NY_2026_sh010")
        ref = tokens.format_token_reference({"site": "NY"})
        self.assertRegex(ref, r'\{facility\} += "MAKE" \(settings\)')
        self.assertNotIn('"LA"', ref)

    def test_date_time_formats(self):
        self.load(None, self.write("f.toml", '[tokens]\ndate_format = "%Y-%m-%d"\n'
                                             'time_format = "%Hh%M"\n'))
        self.assertRegex(tokens.resolve_tokens("{date}_{time}", {}),
                         r"^\d{4}-\d\d-\d\d_\d\dh\d\d$")

    def test_reference_names_sources(self):
        path = self.write("f.toml", "[sequence]\nframe_padding = 6\n")
        self.load(None, path)
        ref = tokens.format_token_reference({})
        self.assertTrue(ref.endswith(f"settings: facility {path}, user (none)"))
        self.assertIn("######", ref)
        self.assertEqual(tokens.resolve_tokens("{frame}", {}), "######")


class TestExampleFile(SettingsCase):
    def test_example_is_generated_from_schema(self):
        with open(EXAMPLE, encoding="utf-8") as fh:
            text = fh.read()
        self.assertEqual(text, settings.example_toml(),
                         "regenerate: python -m core.settings > pipedream.example.toml")

    def test_every_key_listed_under_its_table(self):
        with open(EXAMPLE, encoding="utf-8") as fh:
            text = fh.read()
        table = None
        found = set()
        for line in text.splitlines():
            if m := re.match(r"^#? ?\[([\w.]+)\]$", line):
                table = m.group(1)
                if table == settings.EXTRA_KEY:
                    found.add(table)
            elif (m := re.match(r"^# (\w+) = ", line)) and table != settings.EXTRA_KEY:
                found.add(f"{table}.{m.group(1)}")
        self.assertEqual(found, set(settings.SCHEMA))

    def test_uncommented_example_loads_cleanly_with_defaults(self):
        with open(EXAMPLE, encoding="utf-8") as fh:
            text = re.sub(r"^# (\[[\w.]+\]|\w+ = .*)$", r"\1", fh.read(), flags=re.M)
        self.assertEqual(self.load(None, self.write("all.toml", text)), "")
        for key, spec in settings.SCHEMA.items():
            if key != settings.EXTRA_KEY:
                self.assertEqual(settings.get(key), spec.default, key)
        self.assertEqual(settings.get("tokens.extra"),
                         {"facility": "MAKE", "show_root": "//nas/shows"})


if __name__ == "__main__":
    unittest.main()
