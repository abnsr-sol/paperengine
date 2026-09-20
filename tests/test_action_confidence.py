"""Regression tests for the Finding action/confidence transposition repair.

Several engines historically passed the numeric confidence into the `action`
slot and the advice text into `confidence`. Finding.__post_init__ now repairs
that at construction; these tests lock the behaviour in so it cannot regress.
"""
import unittest
import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from papercheck.risk import Finding, Severity  # noqa: E402


class TestFindingArgOrder(unittest.TestCase):
    def test_transposed_pair_is_repaired(self):
        # confidence passed in the action slot, advice text in confidence slot
        f = Finding("Cat", Severity.HIGH, "t", "d", "e",
                    0.9, "Do the thing")
        self.assertEqual(f.action, "Do the thing")
        self.assertAlmostEqual(f.confidence, 0.9, places=6)

    def test_correct_order_is_untouched(self):
        f = Finding("Cat", Severity.HIGH, "t", "d", "e",
                    "Do the thing", 0.9)
        self.assertEqual(f.action, "Do the thing")
        self.assertAlmostEqual(f.confidence, 0.9, places=6)

    def test_numeric_string_action_is_also_repaired(self):
        f = Finding("Cat", Severity.LOW, "t", "d", "e", "0.55", "Advice")
        self.assertEqual(f.action, "Advice")
        self.assertAlmostEqual(f.confidence, 0.55, places=6)

    def test_action_is_never_numeric_across_all_engines(self):
        from papercheck.checks import ALL_ENGINES, CheckContext
        from papercheck.ingestion import Document
        from papercheck.venues import get_rules

        text = ("We used 42 epochs with batch size 128. " * 40
                + "The mean was 3.48 with SD 0.5. r = 5.0. p = 0.000. "
                + "Ethics approval was obtained. Data are available on Zenodo. "
                + "[1] Smith J. Title. Journal. 2020. " * 12)
        doc = Document(path="x.txt", name="x.txt", file_type="txt",
                       text=text, paragraphs=[text],
                       references=["[1] Smith J. Title. Journal. 2020."])
        ctx = CheckContext(venue="generic", rules=get_rules("generic"))
        numeric = re.compile(r"^[0-9]*\.?[0-9]+$")
        offenders = []
        for engine in ALL_ENGINES:
            name = engine.__module__.rsplit(".", 1)[-1]
            try:
                findings = engine(doc, ctx) or []
            except Exception:
                continue
            for f in findings:
                if numeric.match(str(f.action).strip()):
                    offenders.append((name, f.title))
        self.assertEqual(offenders, [],
                         f"engines still emitting numeric action: {offenders}")


if __name__ == "__main__":
    unittest.main()
