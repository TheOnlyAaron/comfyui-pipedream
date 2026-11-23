"""
Tests for core/wedge.py.

Standard library only; run from the pack root::

    python -m unittest discover -s tests
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import wedge  # noqa: E402


class RowsCase(unittest.TestCase):
    def test_active_rows_skip_empty(self):
        inputs = {
            "token": "product",
            "input_1": ["4", 0], "value_1": "red",
            "value_2": "",
            "input_3": ["5", 0], "value_3": "",
            "value_4": "  blue ",
            "value_5": ["9", 0],
        }
        rows = wedge.active_rows(inputs)
        self.assertEqual([r["row"] for r in rows], [1, 3, 4, 5])
        self.assertEqual([r["linked"] for r in rows], [True, True, False, False])
        self.assertEqual([wedge.row_text(r) for r in rows], ["red", "3", "blue", "5"])

    def test_no_rows(self):
        self.assertEqual(wedge.active_rows({"token": "x", "value_1": ""}), [])

    def test_job_state(self):
        self.assertEqual(wedge.job_state({}), (0, 0, 1))
        inputs = {wedge.ROW_KEY: 2, wedge.JOB_KEY: 5, wedge.TOTAL_KEY: 12}
        self.assertEqual(wedge.job_state(inputs), (2, 5, 12))
        self.assertEqual(wedge.job_state({wedge.ROW_KEY: "bad"}), (0, 0, 1))


class ValuesCase(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(wedge.to_int("42"), 42)
        self.assertEqual(wedge.to_int("2.7"), 2)
        self.assertEqual(wedge.to_int("-3"), -3)
        self.assertEqual(wedge.to_int("red"), 0)
        self.assertEqual(wedge.to_float("0.25"), 0.25)
        self.assertEqual(wedge.to_float("7"), 7.0)
        self.assertEqual(wedge.to_float("red"), 0.0)

    def test_token_names(self):
        self.assertEqual(wedge.check_token(" product "), "product")
        for bad in ("", "two words", "a/b", "frame", "wedge_idx"):
            with self.assertRaises(wedge.WedgeError):
                wedge.check_token(bad)


class ChainCase(unittest.TestCase):
    def axis(self, token, rows, row=0, group=""):
        return {"token": token, "group": group, "rows": rows, "row": row}

    def test_chain_and_tokens(self):
        first = {"axes": wedge.chain_axes(None, self.axis("product", ["red", "blue"], 1)),
                 "job": 3, "total": 6}
        axes = wedge.chain_axes(first, self.axis("angle", ["front", "side", "top"], 1))
        self.assertEqual([a["token"] for a in axes], ["product", "angle"])
        self.assertEqual(wedge.wedge_tokens({"axes": axes, "job": 3, "total": 6}), {
            "product": "blue", "product_idx": "001",
            "angle": "side", "angle_idx": "001",
            "wedge_idx": "003", "wedge_total": "6",
        })

    def test_duplicate_token(self):
        first = {"axes": [self.axis("product", ["a"])]}
        with self.assertRaises(wedge.WedgeError):
            wedge.chain_axes(first, self.axis("product", ["b"]))

    def test_no_wedge(self):
        self.assertEqual(wedge.wedge_tokens(None), {})


if __name__ == "__main__":
    unittest.main()
