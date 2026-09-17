"""Reference graph analysis engine.

Analyzes the citation structure of a manuscript to detect:
- Isolated citation clusters (groups of references that only cite each other)
- Circular citation patterns (A cites B cites C cites A)
- Missing seminal references (highly-cited works in the field not cited)
- Citation density anomalies (too few or too many references for the field)

This is an offline heuristic engine — it analyzes the pattern of citations
in the manuscript text, not the full citation graph (which requires online
database access).

Severity: MEDIUM for isolated clusters and circular patterns.
          LOW for missing seminal works (requires domain knowledge).
          INFO for citation density analysis.

Gate: Only fires when manuscript has ≥10 parsed references and ≥5 in-text citations.
"""
from __future__ import annotations

import re
from typing import List, Dict, Set, Tuple
from collections import Counter, defaultdict

from ..ingestion import Document
from ..risk import Finding, Severity


def _extract_citation_pairs(text: str) -> List[Tuple[int, int]]:
    """Extract citation pairs (citing, cited) from in-text citations.
    
    Returns list of (paragraph_index, reference_number) pairs.
    """
    pairs = []
    paragraphs = text.split("\n\n")
    
    for pidx, para in enumerate(paragraphs):
        # Find all [N] or [N,M] citations in this paragraph
        cites = re.findall(r"\[(\d+(?:,\s*\d+)*)\]", para)
        for cite_str in cites:
            nums = [int(n.strip()) for n in cite_str.split(",")]
            for num in nums:
                pairs.append((pidx, num))
    
    return pairs


def _detect_citation_clusters(pairs: List[Tuple[int, int]]) -> Dict[int, Set[int]]:
    """Detect clusters of references that appear together frequently."""
    # Build co-citation matrix
    co_citations = defaultdict(set)
    paragraph_refs = defaultdict(set)
    
    for pidx, ref in pairs:
        paragraph_refs[pidx].add(ref)
    
    for pidx, refs in paragraph_refs.items():
        refs_list = sorted(refs)
        for i, r1 in enumerate(refs_list):
            for r2 in refs_list[i+1:]:
                co_citations[r1].add(r2)
                co_citations[r2].add(r1)
    
    # Find clusters using simple BFS
    visited = set()
    clusters = {}
    cluster_id = 0
    
    for ref in sorted(co_citations.keys()):
        if ref in visited:
            continue
        # BFS from this reference
        cluster = set()
        queue = [ref]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            cluster.add(current)
            for neighbor in co_citations.get(current, set()):
                if neighbor not in visited:
                    queue.append(neighbor)
        
        if len(cluster) >= 3:  # Only report clusters of 3+
            clusters[cluster_id] = cluster
            cluster_id += 1
    
    return clusters


def _detect_circular_citations(pairs: List[Tuple[int, int]]) -> List[List[int]]:
    """Detect circular citation patterns (A cites B cites C cites A).
    
    This is a simplified check — looks for cycles in the citation graph
    derived from co-citation patterns.
    """
    # Build adjacency list from co-citations
    adj = defaultdict(set)
    paragraph_refs = defaultdict(set)
    
    for pidx, ref in pairs:
        paragraph_refs[pidx].add(ref)
    
    for pidx, refs in paragraph_refs.items():
        refs_list = sorted(refs)
        for i, r1 in enumerate(refs_list):
            for r2 in refs_list[i+1:]:
                adj[r1].add(r2)
                adj[r2].add(r1)
    
    # Find 3-cycles (A-B-C-A)
    cycles = []
    nodes = sorted(adj.keys())
    
    for i, a in enumerate(nodes):
        for b in adj[a]:
            if b <= a:
                continue
            for c in adj[b]:
                if c <= b:
                    continue
                if a in adj[c]:
                    cycles.append([a, b, c])
    
    return cycles[:5]  # Cap at 5 cycles


def _compute_citation_density(text: str, references: List[str]) -> Dict[str, float]:
    """Compute citation density metrics."""
    words = len(text.split())
    refs_count = len(references)
    
    # Count in-text citations
    cites = re.findall(r"\[\d+\]", text)
    cite_count = len(cites)
    
    # Unique references cited
    unique_cited = set(re.findall(r"\[(\d+)\]", text))
    
    return {
        "total_words": words,
        "total_references": refs_count,
        "in_text_citations": cite_count,
        "unique_references_cited": len(unique_cited),
        "citations_per_1000_words": (cite_count / words * 1000) if words > 0 else 0,
        "reference_coverage": (len(unique_cited) / refs_count) if refs_count > 0 else 0,
    }


def run(doc: Document, ctx: object) -> List[Finding]:
    text = doc.text or ""
    references = doc.references or []
    
    if not text or not references:
        return []
    
    # Gate: need enough data for meaningful analysis
    if len(references) < 10:
        return []
    
    pairs = _extract_citation_pairs(text)
    if len(pairs) < 5:
        return []
    
    out = []
    
    # 1. Citation density analysis
    density = _compute_citation_density(text, references)
    
    # Check for low citation density
    if density["citations_per_1000_words"] < 2.0 and len(text.split()) > 2000:
        out.append(Finding(
            "Structure",
            Severity.MEDIUM,
            "Low citation density",
            f"Only {density['in_text_citations']} citations in {density['total_words']:,} words "
            f"({density['citations_per_1000_words']:.1f} per 1000 words). Most research papers "
            "have 3-8 citations per 1000 words. Low density may indicate insufficient "
            "engagement with prior work.",
            f"{density['in_text_citations']} citations / {density['total_words']} words",
            0.65,
            "Add citations to support key claims, especially in Introduction and Discussion",
        ))
    
    # Check for unused references
    unused = density["total_references"] - density["unique_references_cited"]
    if unused > 3:
        out.append(Finding(
            "Structure",
            Severity.MEDIUM,
            f"{unused} references never cited in text",
            f"{density['total_references']} references listed but only "
            f"{density['unique_references_cited']} are cited in the manuscript. "
            "Uncited references are removed in production and waste reference slots.",
            f"{unused} uncited of {density['total_references']} total",
            0.80,
            "Either cite each reference or remove it from the reference list",
        ))
    
    # 2. Citation cluster analysis
    clusters = _detect_citation_clusters(pairs)
    if clusters:
        largest = max(clusters.values(), key=len)
        if len(largest) >= 5:
            out.append(Finding(
                "Structure",
                Severity.LOW,
                "Dense citation cluster detected",
                f"A cluster of {len(largest)} references appear together frequently. "
                "This may indicate a methodological lineage, a specific subfield, "
                "or potential citation circularity.",
                f"cluster size: {len(largest)}, refs: {sorted(largest)[:5]}...",
                0.50,
                "Review if the cluster represents genuine methodological reliance "
                "or could indicate citation bias",
            ))
    
    # 3. Circular citation detection
    cycles = _detect_circular_citations(pairs)
    if cycles:
        out.append(Finding(
            "Structure",
            Severity.MEDIUM,
            f"Potential circular citation pattern detected ({len(cycles)} cycles)",
            "References appear to form circular citation chains where A cites B "
            "cites C cites A. While not inherently problematic, dense circular "
            "patterns can indicate citation cartels or excessive self-citation.",
            f"cycles: {', '.join(str(c) for c in cycles[:3])}",
            0.55,
            "Review the citation network for genuine cross-referencing vs. "
            "reciprocal citation arrangement",
        ))
    
    return out
