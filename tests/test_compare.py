"""Tests for the before/after comparison engine and web-UI comparison flow."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from papercheck.compare import compare, render_console, render_html  # noqa: E402
from papercheck.webui import _parse_multipart  # noqa: E402

_ORIGINAL = """# A Study of Cloud Scheduling

## Abstract
We study scheduling. Results show 30% improvement in throughput.

## Introduction
Cloud scheduling matters for cost and latency. This paper contributes a new
scheduler with details in the Methods section that follows.

## Methods
We used a randomized design with n=120 nodes and a power analysis.
Statistics: t(58) = 2.5, p = 0.01, d = 0.6, 95% CI [0.1, 1.1].

## Results
Throughput improved 30% versus baseline (n=120).

## Conclusion
We showed scheduling gains. Limitations: single cluster, one workload.

## References
[1] Smith, J. (2020). Cloud systems. Journal of Systems, 12(3), 1-20.
    https://doi.org/10.1000/sys.001
[2] Rao, A. (2021). Scheduling theory. Computing, 8(2), 5-30.
    https://doi.org/10.1000/comp.002
[3] Lee, K. (2019). Datacenters. Systems, 3(1), 7-15.
    https://doi.org/10.1000/sys.003
[4] Park, M. (2022). Queues. Networks, 6(4), 2-18.
    https://doi.org/10.1000/net.004
[5] Chen, L. (2018). Storage. Storage, 2(2), 9-25.
    https://doi.org/10.1000/sto.005
[6] Gupta, R. (2023). Energy. Energy, 4(1), 3-12.
    https://doi.org/10.1000/ene.006
"""

_REVISED = """# A Study of Cloud Scheduling

## Abstract
We study scheduling. Results show 30% improvement in throughput.

## Introduction
Cloud scheduling matters for cost and latency. This paper contributes a new
scheduler with details in the Methods section that follows.

## Methods
We used a randomized design with n=120 nodes and a power analysis.
Statistics: t(58) = 2.5, p = 0.01, d = 0.6, 95% CI [0.1, 1.1].

## Results
Throughput improved 30% versus baseline (n=120).

## Conclusion
We showed scheduling gains. Limitations: single cluster, one workload.

## Conflict of Interest
The authors declare no conflict of interest.

## Funding
This work was funded by grant EXAMPLE-2026.

## Data Availability
All data and code are available at https://github.com/example/repo.

## References
[1] Smith, J. (2020). Cloud systems. Journal of Systems, 12(3), 1-20.
    https://doi.org/10.1000/sys.001
[2] Rao, A. (2021). Scheduling theory. Computing, 8(2), 5-30.
    https://doi.org/10.1000/comp.002
[3] Lee, K. (2019). Datacenters. Systems, 3(1), 7-15.
    https://doi.org/10.1000/sys.003
[4] Park, M. (2022). Queues. Networks, 6(4), 2-18.
    https://doi.org/10.1000/net.004
[5] Chen, L. (2018). Storage. Storage, 2(2), 9-25.
    https://doi.org/10.1000/sto.005
[6] Gupta, R. (2023). Energy. Energy, 4(1), 3-12.
    https://doi.org/10.1000/ene.006
"""


def _write_tmp(text: str, suffix: str = ".txt") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


class TestCompare(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orig = _write_tmp(_ORIGINAL)
        cls.rev = _write_tmp(_REVISED)

    @classmethod
    def tearDownClass(cls):
        for p in (cls.orig, cls.rev):
            os.unlink(p)

    def test_compare_runs_and_classifies(self):
        cmp = compare(self.orig, self.rev, venue="elsevier", standard="international")
        s = cmp.summary()
        for key in ("before", "after", "delta", "fixed", "still_open", "new"):
            self.assertIn(key, s)
        # every original finding must be exactly one of fixed/still-open
        self.assertEqual(len(cmp.fixed) + len(cmp.still_open),
                         len({(f.category, f.title) for f in cmp.before.findings}))

    def test_added_statements_become_fixed(self):
        cmp = compare(self.orig, self.rev, venue="elsevier", standard="international")
        fixed_titles = " ".join(f.title.lower() for f in cmp.fixed)
        self.assertIn("statement", fixed_titles)

    def test_identical_docs_yield_zero_diff(self):
        cmp = compare(self.orig, self.orig, venue="elsevier", standard="international")
        self.assertEqual(len(cmp.fixed), 0)
        self.assertEqual(len(cmp.new), 0)
        self.assertEqual(cmp.before.readiness_score, cmp.after.readiness_score)

    def test_renderers_contain_sections(self):
        cmp = compare(self.orig, self.rev, venue="elsevier", standard="international")
        console = render_console(cmp)
        for needle in ("BEFORE / AFTER", "FIXED since last version",
                       "STILL OPEN", "NEW in this revision"):
            self.assertIn(needle, console)
        page = render_html(cmp)
        for needle in ("revision comparison", "Still open", "Fixed since",
                       "New in this revision"):
            self.assertIn(needle, page)


class TestMultipartTwoFiles(unittest.TestCase):
    def test_two_files_and_fields(self):
        boundary = "----X"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="a.txt"\r\n'
            "Content-Type: text/plain\r\n\r\nFIRST\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="revised"; filename="b.txt"\r\n'
            "Content-Type: text/plain\r\n\r\nSECOND\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="venue"\r\n\r\ngeneric\r\n'
            f"--{boundary}--\r\n"
        ).encode()
        files, fields = _parse_multipart(body, f"multipart/form-data; boundary={boundary}")
        self.assertIn("file", files)
        self.assertIn("revised", files)
        self.assertEqual(files["file"][0], "a.txt")
        self.assertEqual(files["revised"][1], b"SECOND")
        self.assertEqual(fields.get("venue"), "generic")


if __name__ == "__main__":
    unittest.main()
