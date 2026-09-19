"""Realism regression tests.

Locks in the false-positive and crash fixes found by scripts/realism_probe.py:
- statcheck rounding-interval (p=.05 with recomputed .049948 is NOT an error)
- trial_ethics real-world IRB / data-availability phrasing
- submission: 'participants' alone must not demand trial registration
- CheckContext tolerates None fields (library API boundary)
- tiny fragments (<100 words) produce no structural/submission verdicts
- rrid_validate offline loop works with a zero online budget
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from papercheck.ingestion import Document, load_document  # noqa: E402
from papercheck.checks import ALL_ENGINES, CheckContext  # noqa: E402
from papercheck.statscalc import extract_results  # noqa: E402
from papercheck.risk import Severity  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make_doc(text: str, name: str = "t") -> Document:
    return Document(path=f"{name}.txt", name=name, file_type="txt", text=text)


def run_engine(mod_name: str, doc: Document, ctx=None):
    ctx = ctx or CheckContext(venue=None, rules=None, online=False,
                              max_online_checks=0)
    for eng in ALL_ENGINES:
        if getattr(eng, "__module__", "").endswith(mod_name):
            return eng(doc, ctx) or []
    raise AssertionError(f"engine module not found: {mod_name}")


class TestStatcheckRounding(unittest.TestCase):
    ROUNDING = ("The effect was significant, F(2, 57) = 3.16, p = .05, "
                "and also t(30) = 2.04, p = 0.05.")
    CONTRADICTION = ("However, the follow-up was null: F(2, 57) = 0.10, "
                     "p = .01, and t(20) = 0.5, p = .001.")

    def _decision_errors(self, text: str) -> int:
        return sum(1 for r in extract_results(text) if r.decision_error)

    def test_rounding_boundary_is_not_decision_error(self):
        # F recomputes to 0.049948 and t to 0.05024 — both inside the
        # 2-decimal rounding interval of .05. Zero CRITICALs allowed.
        doc = make_doc(self.ROUNDING * 4 + " Padding sentence for the gate. " * 60)
        self.assertGreaterEqual(doc.word_count, 200)
        self.assertEqual(self._decision_errors(doc.text), 0)
        from papercheck.risk import Severity as _Sev
        serious = [f for f in run_engine("statcheck", doc)
                   if f.severity in (_Sev.CRITICAL, _Sev.HIGH)]
        self.assertEqual(serious, [])

    def test_true_contradiction_still_fires(self):
        doc = make_doc(self.CONTRADICTION * 4 + " Padding sentence for the gate. " * 60)
        self.assertGreaterEqual(doc.word_count, 200)
        self.assertEqual(self._decision_errors(doc.text), 8)  # 2 x 4 repeats
        titles = [f.title for f in run_engine("statcheck", doc)]
        self.assertTrue(any("decision error" in t for t in titles))


class TestTrialEthicsPhrasing(unittest.TestCase):
    PSYCH = open(os.path.join(ROOT, "scripts", "realism_fixtures",
                              "apa_psych.txt"), encoding="utf-8").read()

    def test_university_irb_phrase_recognized(self):
        doc = make_doc(self.PSYCH, "psych")
        findings = run_engine("trial_ethics", doc)
        titles = " | ".join(f.title for f in findings)
        self.assertNotIn("without ethics approval", titles)

    def test_data_available_on_request_recognized(self):
        doc = make_doc(self.PSYCH, "psych")
        findings = run_engine("trial_ethics", doc)
        titles = " | ".join(f.title for f in findings)
        self.assertNotIn("data/code availability", titles)


class TestSubmissionParticipant(unittest.TestCase):
    def test_participants_alone_do_not_demand_registration(self):
        text = ("Participants completed a survey about study habits. "
                "Participants were undergraduates. ") * 8
        doc = make_doc(text)
        findings = run_engine("submission", doc)
        titles = " | ".join(f.title for f in findings)
        self.assertNotIn("trial registration", titles)


class TestCheckContextNone(unittest.TestCase):
    def test_none_fields_normalized(self):
        ctx = CheckContext(venue=None, rules=None, corpus=None,
                           online_cache=None)
        self.assertEqual(ctx.venue, "generic")
        self.assertEqual(ctx.rules, {})
        self.assertEqual(ctx.corpus, [])
        self.assertEqual(ctx.online_cache, {})

    def test_all_engines_survive_none_context(self):
        for text in ("", "hello", "   \n\t ", "abstract only text",
                     "\x00\x01 junk \ufffd"):
            doc = make_doc(text)
            for eng in ALL_ENGINES:
                try:
                    eng(doc, CheckContext(venue=None, rules=None))
                except Exception as exc:  # noqa: BLE001
                    self.fail(
                        f"{eng.__module__} crashed on {text!r}: {exc}")


class TestTinyFragmentGate(unittest.TestCase):
    FRAGMENTS = ("", "hello", "   \n\t  ", "## Abstract\n\nShort bit.\n")

    def test_no_serious_findings_on_fragments(self):
        for text in self.FRAGMENTS:
            doc = make_doc(text)
            for mod in ("structure", "submission", "reproducibility"):
                for f in run_engine(mod, doc):
                    self.assertNotIn(
                        f.severity, (Severity.CRITICAL, Severity.HIGH),
                        f"{mod} fired {f.title!r} on fragment {text!r}")


class TestRridOfflineZeroBudget(unittest.TestCase):
    def test_offline_rrid_format_check_with_zero_budget(self):
        text = ("Antibody details: RRID:AB_3076434. " +
                "Filler text for the gate. " * 20)
        doc = make_doc(text)
        ctx = CheckContext(venue=None, rules=None, online=False,
                           max_online_checks=0)
        findings = run_engine("rrid_validate", doc, ctx)
        self.assertTrue(any("RRID" in f.title for f in findings))


if __name__ == "__main__":
    unittest.main()
