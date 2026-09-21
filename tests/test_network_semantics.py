"""Network semantics: "we could not ask" must never become "it does not exist".

This is the highest-consequence bug class in an integrity screener. A 429, a
blocked request, a 5xx or a dropped connection all mean the same thing — we
learned nothing — yet an earlier revision of the online engines folded them
into "reference not found in Crossref (possible hallucination)". On a throttled
batch run that brands every real citation in the manuscript as fabricated.

The shared HTTP layer returns an explicit status so callers can tell the three
cases apart, and these tests pin the behaviour down:

    (None, None)  -> never reached the server   -> disclose, never accuse
    (429,  None)  -> throttled / blocked / 5xx  -> disclose, never accuse
    (404,  None)  -> the server said absent     -> a real finding
    (200, {...})  -> a real answer              -> normal analysis
"""
from __future__ import annotations
import unittest
from unittest import mock

from papercheck import net
from papercheck.checks import CheckContext
from papercheck.checks import crossref_verify as cr
from papercheck.ingestion import Document
from tests._fixtures import http_error, json_response


def _doc():
    return Document(
        path="x.txt", name="x.txt", file_type="txt",
        text="Body text about the study.",
        paragraphs=["Body text about the study."],
        references=[
            "Smith J. A real published paper. Journal of Things. 2020;12(3):45-67. doi:10.1234/real.2020",
            "Doe A. Another real paper. Journal of Stuff. 2019;3(1):1-9.",
        ],
    )


def _ctx():
    return CheckContext(online=True, max_online_checks=5)


class TestStatusClassification(unittest.TestCase):
    def test_transport_failure_is_indeterminate(self):
        self.assertFalse(net.is_definitive(None))

    def test_throttle_block_and_server_faults_are_indeterminate(self):
        for status in (401, 403, 407, 408, 425, 429, 451, 500, 502, 503, 504):
            self.assertFalse(net.is_definitive(status), status)

    def test_absent_and_success_are_definitive(self):
        for status in (200, 201, 404, 410):
            self.assertTrue(net.is_definitive(status), status)

    def test_get_distinguishes_404_from_a_dead_network(self):
        with mock.patch("urllib.request.urlopen", side_effect=http_error(404)):
            self.assertEqual(net.get("http://x", sleep=lambda s: None), (404, None))

        with mock.patch("urllib.request.urlopen",
                        side_effect=net.urllib.error.URLError("down")):
            self.assertEqual(net.get("http://x", sleep=lambda s: None), (None, None))


class TestCrossrefNeverAccusesOnTransportFailure(unittest.TestCase):
    def _titles(self, side_effect):
        with mock.patch("urllib.request.urlopen", side_effect=side_effect):
            return [f.title for f in cr.run(_doc(), _ctx())]

    def test_network_down_does_not_flag_references(self):
        titles = self._titles(net.urllib.error.URLError("network down"))
        self.assertFalse([t for t in titles if "not found" in t.lower()], titles)
        self.assertTrue([t for t in titles if "unreachable" in t.lower()], titles)

    def test_throttling_does_not_flag_references(self):
        titles = self._titles(http_error(429))
        self.assertFalse([t for t in titles if "not found" in t.lower()], titles)
        self.assertTrue([t for t in titles if "unreachable" in t.lower()], titles)

    def test_blocked_request_does_not_flag_references(self):
        titles = self._titles(http_error(403))
        self.assertFalse([t for t in titles if "not found" in t.lower()], titles)

    def test_server_error_does_not_flag_references(self):
        titles = self._titles(http_error(503))
        self.assertFalse([t for t in titles if "not found" in t.lower()], titles)

    def test_real_404_does_flag_the_doi(self):
        with mock.patch("urllib.request.urlopen", side_effect=http_error(404)):
            findings = cr.run(_doc(), _ctx())
        self.assertTrue(
            any("does not resolve" in f.title.lower() for f in findings),
            [f.title for f in findings])
        self.assertTrue(any(f.severity.value == "High" for f in findings))

    def test_empty_search_results_do_flag(self):
        with mock.patch("urllib.request.urlopen",
                        side_effect=lambda req, timeout=None:
                        json_response({"message": {"items": []}})):
            findings = cr.run(_doc(), _ctx())
        self.assertTrue(any("not found" in f.title.lower() for f in findings),
                        [f.title for f in findings])

    def test_successful_lookup_is_quiet(self):
        def fake(req, timeout=None):
            if "/works/10.1234/real.2020" in req.full_url:
                return json_response({"message": {
                    "title": ["A real paper"],
                    "published-print": {"date-parts": [[2020]]}}})
            return json_response({"message": {"items": [
                {"title": ["A real paper"], "issued": {"date-parts": [[2020]]}}]}})

        with mock.patch("urllib.request.urlopen", side_effect=fake):
            findings = cr.run(_doc(), _ctx())
        self.assertEqual([f.title for f in findings], [])

    def test_year_mismatch_still_reported(self):
        def fake(req, timeout=None):
            if "/works/10.1234/real.2020" in req.full_url:
                return json_response({"message": {
                    "title": ["A real paper"],
                    "published-print": {"date-parts": [[2019]]}}})
            return json_response({"message": {"items": [
                {"title": ["A real paper"], "issued": {"date-parts": [[2019]]}}]}})

        with mock.patch("urllib.request.urlopen", side_effect=fake):
            findings = cr.run(_doc(), _ctx())
        self.assertTrue(any("year mismatch" in f.title.lower() for f in findings),
                        [f.title for f in findings])


if __name__ == "__main__":
    unittest.main()
