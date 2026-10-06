"""Regression tests for the venue-integrity engine (venue_hijack).

Two long-standing defects are locked in here, both caused by matching against
`ctx.venue` — which is a *rendered label* ("elsevier (International -- Elsevier)"),
not a journal name:

  1. the CRITICAL "known hijacked journal" alert could never fire, because the
     label can never equal a journal title in the bundled list;
  2. the same label injected the word "international", which the generic-title
     predatory indicator counted as an invented-journal tell — so 19 of 24
     presets were reported as predatory on a completely clean paper.

The tests below assert both directions: real hijacks must fire, and legitimate
venues must stay quiet.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from papercheck.checks import CheckContext, venue_hijack as V  # noqa: E402
from papercheck.ingestion import Document  # noqa: E402
from papercheck.venues import PRESETS, describe, get_rules  # noqa: E402

_INTEL = os.path.join(os.path.dirname(__file__), "..", "papercheck", "data", "venue_intel.json")
with open(_INTEL, encoding="utf-8") as _fh:
    HIJACKED_TITLE = json.load(_fh)["hijacked_journals"][0]["title_norm"]

CLEAN_BODY = (
    "We used 42 epochs. The mean was 3.48 with SD 0.5. "
    "Ethics approval was obtained. Data are available on Zenodo."
)
SERIOUS = {"Critical", "High", "Medium"}


def _doc(text):
    return Document(path="x.txt", name="x.txt", file_type="txt",
                    text=text, paragraphs=[text], references=[])


def _critical(findings):
    return [f for f in findings if f.severity.value.lower() == "critical"]


class TestVenueHijackReachability(unittest.TestCase):
    def setUp(self):
        self.text = f"This manuscript is submitted to {HIJACKED_TITLE}. We used 42 epochs."

    def test_explicit_venue_flags_known_hijack(self):
        ctx = CheckContext(venue=describe(HIJACKED_TITLE),
                           rules=get_rules(HIJACKED_TITLE))
        self.assertTrue(_critical(V.run(_doc(self.text), ctx)),
                        "CRITICAL must fire when the venue is named via --venue")

    def test_text_extracted_venue_flags_known_hijack(self):
        ctx = CheckContext(venue="generic", rules=get_rules("generic"))
        self.assertTrue(_critical(V.run(_doc(self.text), ctx)),
                        "CRITICAL must fire when the venue is read from the text")

    def test_extraction_does_not_swallow_the_sentence(self):
        doc = _doc(self.text)
        self.assertEqual(
            V._normalize_title(V._extract_venue_name(doc, self.text)),
            V._normalize_title(HIJACKED_TITLE))


class TestVenueLabelHandling(unittest.TestCase):
    def test_label_suffix_is_stripped(self):
        self.assertEqual(V._clean_venue_label("elsevier (International -- Elsevier)"),
                         "elsevier")
        # national presets nest parentheses
        self.assertEqual(V._clean_venue_label("ugc_care (National (Indian) -- UGC-CARE listed)"),
                         "ugc_care")

    def test_sentence_tail_is_trimmed(self):
        self.assertEqual(
            V._trim_sentence_tail(
                "American Journal of Industrial and Business Management. We us"),
            "American Journal of Industrial and Business Management")

    def test_resolve_prefers_the_raw_name_over_the_label(self):
        ctx = CheckContext(venue=describe("elsevier"), rules=get_rules("elsevier"))
        self.assertEqual(V._resolve_venue_name(ctx, _doc(""), ""), "elsevier")


class TestNoFalsePredatoryAccusations(unittest.TestCase):
    def test_no_preset_accuses_a_clean_paper(self):
        doc = _doc(CLEAN_BODY)
        offenders = {}
        for key in PRESETS:
            if key == "generic":
                continue
            ctx = CheckContext(venue=describe(key), rules=get_rules(key))
            serious = [f for f in V.run(doc, ctx) if f.severity.value in SERIOUS]
            if serious:
                offenders[key] = [f.severity.value for f in serious]
        self.assertEqual(
            offenders, {},
            f"legitimate presets reported as predatory on a clean paper: {offenders}")


if __name__ == "__main__":
    unittest.main()
