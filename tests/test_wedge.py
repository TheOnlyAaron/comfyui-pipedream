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


def wedge_node(token, values, upstream=None, group="", links=()):
    inputs = {"token": token, "group": group}
    for n, text in enumerate(values, 1):
        inputs[f"value_{n}"] = text
    for n in links:
        inputs[f"input_{n}"] = ["90", 0]
    if upstream:
        inputs["wedge"] = [upstream, 4]
    return {"class_type": "PDWedge", "inputs": inputs}


class PlanCase(unittest.TestCase):
    def prompt(self):
        return {
            "90": {"class_type": "EmptyImage", "inputs": {}},
            "20": wedge_node("angle", ["front", "side", "top"], upstream="30"),
            "30": wedge_node("product", ["", "", ""], links=(1, 2, 3)),
            "40": {"class_type": "PDOutput", "inputs": {"images": ["20", 0], "wedge": ["20", 4]}},
        }

    def test_chain_order_first_fastest(self):
        prompt = self.prompt()
        plan = wedge.plan(prompt, ["40"])
        self.assertEqual([a["tokens"] for a in plan["axes"]], [["product"], ["angle"]])
        self.assertEqual(plan["total"], 9)
        rows = wedge.jobs(plan)
        self.assertEqual([(r["30"], r["20"]) for r in rows[:4]], [(0, 0), (1, 0), (2, 0), (0, 1)])
        self.assertEqual((rows[-1]["30"], rows[-1]["20"]), (2, 2))

    def test_unused_wedges_ignored(self):
        prompt = self.prompt()
        prompt["50"] = wedge_node("stray", ["a", "b"])
        self.assertEqual(wedge.plan(prompt, ["40"])["total"], 9)
        self.assertEqual(wedge.plan(prompt, [])["total"], 1)

    def test_group_steps_together(self):
        prompt = self.prompt()
        prompt["60"] = wedge_node("prompt", ["a", "b", "c"], group="look")
        prompt["30"]["inputs"]["group"] = "look"
        prompt["40"]["inputs"]["extra"] = ["60", 0]
        plan = wedge.plan(prompt, ["40"])
        self.assertEqual(plan["total"], 9)
        self.assertEqual([a["tokens"] for a in plan["axes"]], [["product", "prompt"], ["angle"]])
        for rows in wedge.jobs(plan):
            self.assertEqual(rows["30"], rows["60"])

    def test_group_mismatch(self):
        prompt = self.prompt()
        prompt["60"] = wedge_node("prompt", ["a", "b"], group="look")
        prompt["30"]["inputs"]["group"] = "look"
        prompt["40"]["inputs"]["extra"] = ["60", 0]
        with self.assertRaisesRegex(wedge.WedgeError, "same number of rows"):
            wedge.plan(prompt, ["40"])

    def test_no_rows(self):
        prompt = self.prompt()
        prompt["20"] = wedge_node("angle", ["", ""], upstream="30")
        with self.assertRaisesRegex(wedge.WedgeError, "no rows"):
            wedge.plan(prompt, ["40"])

    def test_too_many(self):
        prompt = {"9": {"class_type": "PDOutput", "inputs": {}}}
        upstream = None
        for i in range(4):
            prompt[str(i)] = wedge_node(f"w{i}", [str(n) for n in range(1, 13)], upstream=upstream)
            upstream = str(i)
        prompt["9"]["inputs"]["wedge"] = [upstream, 4]
        with self.assertRaisesRegex(wedge.WedgeError, "limit"):
            wedge.plan(prompt, ["9"])

    def test_apply_job(self):
        prompt = self.prompt()
        out = wedge.apply_job(prompt, {"20": 2, "30": 1}, 7, 9)
        self.assertEqual(wedge.job_state(out["20"]["inputs"]), (2, 7, 9))
        self.assertEqual(wedge.job_state(out["30"]["inputs"]), (1, 7, 9))
        self.assertNotIn(wedge.ROW_KEY, prompt["20"]["inputs"])

    def test_subgraph_ids_sort(self):
        self.assertLess(wedge._id_key("5:3"), wedge._id_key("12"))
        self.assertLess(wedge._id_key("2"), wedge._id_key("10"))


if __name__ == "__main__":
    unittest.main()
