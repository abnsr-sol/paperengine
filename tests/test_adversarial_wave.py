"""Tests for the four wave engines: physical plausibility, ML fairness,
statistical-correction awareness, and proof gaps."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from papercheck.ingestion import load_document  # noqa: E402
from papercheck.checks import (  # noqa: E402
    physical_plausibility, ml_fairness, corrections, proof_gaps)


def _doc(body: str):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(body)
        path = f.name
    try:
        return load_document(path)
    finally:
        os.unlink(path)


_PAD_SYS = ("We study distributed consensus protocols across datacenters with "
            "fault tolerance and replication guarantees under crash and network "
            "partitions. " * 16)
_PAD_ML = ("We evaluate our approach on standard vision benchmarks with "
           "convolutional networks and large-scale pretraining. " * 14)
_PAD_ANOVA = ("We analyzed the response times across conditions using "
              "repeated-measures ANOVA with the standard statistical software "
              "and reported effect sizes for each experimental condition. " * 14)
_PAD_THM = ("We present Theorem 1 and prove the convergence bound for the "
            "optimization algorithm under mild assumptions formally. " * 14)


class TestPhysicalPlausibility(unittest.TestCase):
    def test_speed_of_light_floor(self):
        doc = _doc(_PAD_SYS + "Deployment spans US and EU datacenters. Results: "
                   "round-trip latency is 1.2 ms at p99.")
        finds = physical_plausibility.run(doc, None)
        self.assertTrue(any("speed-of-light" in f.title.lower() for f in finds),
                        [f.title for f in finds])

    def test_reasonable_latency_not_flagged(self):
        doc = _doc(_PAD_SYS + "Deployment spans US and EU datacenters. Results: "
                   "round-trip latency is 85 ms at p99.")
        self.assertEqual(physical_plausibility.run(doc, None), [])

    def test_vram_impossible(self):
        doc = _doc(_PAD_ML + "We train a 70B parameter model with AdamW on "
                   "4 RTX 3090 GPUs for two weeks.")
        finds = physical_plausibility.run(doc, None)
        self.assertTrue(any("GPU memory" in f.title for f in finds),
                        [f.title for f in finds])

    def test_vram_with_offloading_not_flagged(self):
        doc = _doc(_PAD_ML + "We train a 70B parameter model with AdamW using "
                   "ZeRO-3 CPU offloading on 4 RTX 3090 GPUs.")
        self.assertEqual(physical_plausibility.run(doc, None), [])


class TestMLFairness(unittest.TestCase):
    def test_strawman_baseline(self):
        doc = _doc(_PAD_ML + "We performed hyperparameter tuning with grid "
                   "search over learning rates. Baselines use default "
                   "settings throughout the experiments.")
        finds = ml_fairness.run(doc, None)
        self.assertTrue(any("untuned" in f.title.lower() for f in finds),
                        [f.title for f in finds])

    def test_fair_comparison_info(self):
        doc = _doc(_PAD_ML + "We performed grid search hyperparameter tuning; "
                   "identical tuning budget was applied to all baselines for "
                   "a fair comparison.")
        finds = ml_fairness.run(doc, None)
        self.assertTrue(any(f.severity.value == "Info" for f in finds),
                        [f.title for f in finds])

    def test_metric_masking(self):
        doc = _doc(_PAD_ML + "The dataset exhibits severe class imbalance "
                   "(98:2 ratio). Our method achieves 97.2% accuracy on the "
                   "test set under this distribution shift.")
        finds = ml_fairness.run(doc, None)
        self.assertTrue(any("metric masking" in f.title.lower()
                            or "imbalanced" in f.title.lower() for f in finds),
                        [f.title for f in finds])

    def test_balanced_metrics_not_flagged(self):
        doc = _doc(_PAD_ML + "The dataset exhibits severe class imbalance "
                   "(98:2 ratio). Our method achieves 97.2% accuracy, macro "
                   "F1 of 0.88, and MCC of 0.81 on the test set.")
        self.assertEqual(ml_fairness.run(doc, None), [])


class TestCorrections(unittest.TestCase):
    def test_correction_downgrades_to_info(self):
        doc = _doc(_PAD_ANOVA + "A t(28) = 2.45, p = .90 was observed. "
                   "We applied a Greenhouse-Geisser correction and "
                   "Bonferroni correction for multiple comparisons.")
        finds = corrections.run(doc, None)
        self.assertTrue(any(f.severity.value == "Info" and "correction" in f.title.lower()
                            for f in finds), [f.title for f in finds])
        # must NOT be flagged critical/high by this engine
        self.assertFalse(any(f.severity.value in ("High", "Critical") for f in finds))

    def test_marginal_cluster_nudge(self):
        doc = _doc(_PAD_ANOVA + "t(28) = 2.10, p = .045. F(2, 46) = 3.35, "
                   "p = .043. chi2(1) = 4.20, p = .041. t(55) = 2.02, "
                   "p = .048. Another test was F(3, 90) = 2.85, p = .041.")
        finds = corrections.run(doc, None)
        self.assertTrue(any("marginal" in f.title.lower() for f in finds),
                        [f.title for f in finds])


class TestProofGaps(unittest.TestCase):
    def test_dismissal_phrases_flagged(self):
        doc = _doc(_PAD_THM + "Proof of Theorem 1. It is trivial to see that "
                   "the bound holds. By simple algebra, the terms cancel. "
                   "Obviously the remainder converges; details are omitted.")
        finds = proof_gaps.run(doc, None)
        self.assertTrue(any("dismissal" in f.title.lower() for f in finds),
                        [f.title for f in finds])

    def test_no_math_no_findings(self):
        doc = _doc(_PAD_ML + "The system was trained and evaluated; the "
                   "results are reported in the next section with tables.")
        self.assertEqual(proof_gaps.run(doc, None), [])


if __name__ == "__main__":
    unittest.main()
