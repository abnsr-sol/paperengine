"""PaperCheck — academic manuscript pre-submission rejection-risk engine.

Modular analysis of a submitted manuscript across every dimension that can
cause rejection (formatting, language, integrity, AI-risk, novelty,
consistency), producing an evidence-linked risk report:

    Risk | Finding | Evidence | Confidence | Action

Everything here is a risk *signal*, not a verdict. Similarity is not
plagiarism, and an AI-risk score is not proof of AI authorship. See README.md
for the full research-angle map and the honest-limitations section.
"""

__version__ = "0.1.0"