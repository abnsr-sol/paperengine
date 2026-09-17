"""Compression-ratio AI detection engine.

AI-generated text tends to be more predictable and uniform than human writing,
causing it to compress more efficiently. This engine LZMA-compresses paragraph
chunks and compares the ratio to known human academic prose baselines.

This is a supplementary signal, not proof of AI authorship. It works best on
multi-paragraph passages (>200 words) and is unreliable on short fragments,
technical formulas, or non-English text.

Source: thinkst/zippy (Apache-2.0) concept; academic prose baseline ~0.7-0.8.
"""
from __future__ import annotations

import lzma
import re
from typing import List

from ..ingestion import Document
from ..risk import Finding, Severity


def _compression_ratio(text: str) -> float:
    """Return compressed_size / raw_size. Lower = more compressible."""
    raw = len(text.encode("utf-8"))
    if raw < 100:
        return 1.0  # too short to measure
    try:
        compressed = len(lzma.compress(text.encode("utf-8")))
        return compressed / raw
    except Exception:
        return 1.0


def _split_paragraphs(text: str) -> List[str]:
    """Split body text into substantial paragraphs (>100 chars)."""
    paras = re.split(r"\n\s*\n", text)
    return [p.strip() for p in paras if len(p.strip()) > 100]


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if not body:
        return []

    paragraphs = _split_paragraphs(body)
    if len(paragraphs) < 3:
        return []  # need enough text for a meaningful signal

    # Human academic prose baseline: ~0.70-0.80 compression ratio
    # AI text typically: ~0.55-0.65 (more compressible)
    HUMAN_LOW = 0.65   # below this = suspiciously compressible
    HUMAN_HIGH = 0.85  # above this = normal/hard to compress

    ratios = []
    low_count = 0
    for para in paragraphs:
        r = _compression_ratio(para)
        ratios.append(r)
        if r < HUMAN_LOW:
            low_count += 1

    if not ratios:
        return []

    avg_ratio = sum(ratios) / len(ratios)
    total_paras = len(paragraphs)

    out = []

    # Strong signal: most paragraphs compress unusually well
    if low_count >= max(3, total_paras * 0.5) and avg_ratio < HUMAN_LOW:
        out.append(Finding(
            "LLM Artifacts",
            Severity.MEDIUM,
            "Unusually uniform text compression pattern",
            f"{low_count}/{total_paras} paragraphs compress below the human-academic baseline "
            f"(avg ratio: {avg_ratio:.3f}, human range: 0.65-0.85). AI-generated text tends to be "
            "more predictable and compresses more efficiently than human writing. This is a "
            "supplementary signal, not proof of AI authorship.",
            f"avg compression ratio: {avg_ratio:.3f} across {total_paras} paragraphs",
            0.55,
            "Review highlighted passages for accuracy and citations; "
            "if AI tools were used, disclose per venue policy",
        ))
    elif avg_ratio < HUMAN_LOW - 0.05:
        # Moderate signal: overall compression is low
        out.append(Finding(
            "LLM Artifacts",
            Severity.LOW,
            "Text compression ratio suggests high uniformity",
            f"Average compression ratio ({avg_ratio:.3f}) is below the typical human-academic "
            "range (0.65-0.85). This can indicate templated or highly uniform prose, which may "
            "reflect heavy editing, AI assistance, or simply disciplined technical writing.",
            f"avg ratio: {avg_ratio:.3f}, {low_count}/{total_paras} low-compression paragraphs",
            0.40,
            "No action required unless venue requires AI-disclosure; "
            "informational signal only",
        ))

    return out
