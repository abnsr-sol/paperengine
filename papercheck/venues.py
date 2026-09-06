"""Venue rules: dual-mode (international + national/Indian).

User picks --standard international or --standard national, then --venue.
"""
from __future__ import annotations
import json
from typing import Dict, List, Optional

# Freshness tracking (limitation fix): published limits change without notice,
# so every preset carries the date its numbers were last verified against the
# publisher's author guidelines. Reports surface this so users know what to
# re-check. Update this constant (and any preset that changed) after review.
RULES_LAST_VERIFIED = "2026-09"

INTERNATIONAL_PRESETS: Dict[str, Dict] = {
    "ieee_conference": {
        "standard": "international", "page_limit": 8, "word_limit": None,
        "abstract_word_limit": 250, "columns": 2, "page_size": "US Letter",
        "font_required": "Times New Roman", "font_size_required": 10,
        "required_sections": ["Abstract", "Introduction", "References"],
        "required_statements": ["Acknowledgment", "AI-use disclosure"],
        "citations_style": "ieee", "publisher": "IEEE", "min_references": 8,
        "heading_style": "roman", "caption_style": "Fig. N.", "table_caption_above": True,
        "plagiarism_threshold": None, "ai_policy": "disclosure_required", "double_blind": True,
    },
    "ieee_journal": {
        "standard": "international", "page_limit": 14, "word_limit": None,
        "abstract_word_limit": 250, "columns": 2, "page_size": "US Letter",
        "font_required": "Times New Roman", "font_size_required": 10,
        "required_sections": ["Abstract", "Introduction", "References"],
        "required_statements": ["Acknowledgment", "AI-use disclosure"],
        "citations_style": "ieee", "publisher": "IEEE", "min_references": 10,
        "heading_style": "roman", "caption_style": "Fig. N.", "table_caption_above": True,
        "plagiarism_threshold": None, "ai_policy": "disclosure_required", "double_blind": False,
    },
    "ieee_access": {
        "standard": "international", "page_limit": None, "word_limit": 10000,
        "abstract_word_limit": 250, "columns": 2, "page_size": "US Letter",
        "font_required": "Times New Roman", "font_size_required": 10,
        "required_sections": ["Abstract", "Introduction", "Conclusion", "References"],
        "required_statements": ["Data availability", "Acknowledgment", "AI-use disclosure"],
        "citations_style": "ieee", "publisher": "IEEE", "min_references": 20,
        "heading_style": "roman", "caption_style": "Fig. N.", "table_caption_above": True,
        "plagiarism_threshold": None, "ai_policy": "disclosure_required", "double_blind": False,
    },
    "acm": {
        "standard": "international", "page_limit": 10, "word_limit": None,
        "abstract_word_limit": 250, "columns": 2, "page_size": "US Letter",
        "font_required": None, "font_size_required": 10,
        "required_sections": ["Abstract", "Introduction", "References"],
        "required_statements": ["Acknowledgment", "AI-use disclosure"],
        "citations_style": "acm", "publisher": "ACM", "min_references": 10,
        "heading_style": "numeric", "caption_style": "Figure N.", "table_caption_above": True,
        "plagiarism_threshold": None, "ai_policy": "disclosure_required", "double_blind": True,
    },
    "elsevier": {
        "standard": "international", "word_limit": 8000, "page_limit": None,
        "abstract_word_limit": 300, "columns": 1, "page_size": "A4",
        "font_required": None, "font_size_required": None,
        "required_sections": ["Abstract", "Introduction", "Conclusion", "References"],
        "required_statements": ["Data availability", "Funding", "Conflicts of interest", "Author contributions", "Ethics approval"],
        "citations_style": "elsevier", "publisher": "Elsevier", "min_references": 15,
        "heading_style": "numeric", "caption_style": "Fig. N.", "table_caption_above": False,
        "plagiarism_threshold": None, "ai_policy": "disclosure_required", "double_blind": False,
    },
    "springer": {
        "standard": "international", "word_limit": 10000, "page_limit": None,
        "abstract_word_limit": 250, "columns": 1, "page_size": "A4",
        "font_required": None, "font_size_required": None,
        "required_sections": ["Abstract", "Introduction", "Conclusion", "References"],
        "required_statements": ["Data availability", "Funding", "Conflicts of interest", "Author contributions", "Ethics approval"],
        "citations_style": "springer", "publisher": "Springer Nature", "min_references": 15,
        "heading_style": "numeric", "caption_style": "Fig. N.", "table_caption_above": False,
        "plagiarism_threshold": None, "ai_policy": "disclosure_required", "double_blind": False,
    },
    "nature": {
        "standard": "international", "word_limit": 5000, "page_limit": None,
        "abstract_word_limit": 150, "columns": 1, "page_size": "A4",
        "font_required": None, "font_size_required": None,
        "required_sections": ["Abstract", "Introduction", "Methods", "Results", "Discussion", "References"],
        "required_statements": ["Data availability", "Code availability", "Funding", "Author contributions", "Competing interests"],
        "citations_style": "nature", "publisher": "Springer Nature", "min_references": 30,
        "max_figures": 5, "max_tables": 1,
        "heading_style": "numeric", "caption_style": "Fig. N.", "table_caption_above": False,
        "plagiarism_threshold": None, "ai_policy": "disclosure_required", "double_blind": False,
    },
    "mdpi": {
        "standard": "international", "word_limit": None, "page_limit": None,
        "abstract_word_limit": 200, "columns": 1, "page_size": "A4",
        "font_required": None, "font_size_required": None,
        "required_sections": ["Abstract", "Introduction", "Conclusion", "References"],
        "required_statements": ["Data availability", "Funding", "Conflicts of interest", "Author contributions"],
        "citations_style": "mdpi", "publisher": "MDPI", "min_references": 20,
        "heading_style": "numeric", "caption_style": "Fig. N.", "table_caption_above": False,
        "plagiarism_threshold": None, "ai_policy": "disclosure_required", "double_blind": False,
    },
    "wiley": {
        "standard": "international", "word_limit": 10000, "page_limit": None,
        "abstract_word_limit": 250, "columns": 1, "page_size": "A4",
        "font_required": None, "font_size_required": None,
        "required_sections": ["Abstract", "Introduction", "Conclusion", "References"],
        "required_statements": ["Data availability", "Funding", "Conflicts of interest", "Author contributions"],
        "citations_style": "wiley", "publisher": "Wiley", "min_references": 15,
        "heading_style": "numeric", "caption_style": "Fig. N.", "table_caption_above": False,
        "plagiarism_threshold": None, "ai_policy": "disclosure_required", "double_blind": False,
    },
    "tandfonline": {
        "standard": "international", "word_limit": 8000, "page_limit": None,
        "abstract_word_limit": 250, "columns": 1, "page_size": "A4",
        "font_required": None, "font_size_required": None,
        "required_sections": ["Abstract", "Introduction", "Conclusion", "References"],
        "required_statements": ["Funding", "Conflicts of interest", "Author contributions"],
        "citations_style": "tandfonline", "publisher": "Taylor & Francis", "min_references": 15,
        "heading_style": "numeric", "caption_style": "Fig. N.", "table_caption_above": False,
        "plagiarism_threshold": None, "ai_policy": "disclosure_required", "double_blind": False,
    },
    "plos": {
        "standard": "international", "word_limit": 10000, "page_limit": None,
        "abstract_word_limit": 300, "columns": 1, "page_size": "US Letter",
        "font_required": None, "font_size_required": None,
        "required_sections": ["Abstract", "Introduction", "Methods", "Results", "Discussion", "References"],
        "required_statements": ["Data availability", "Funding", "Competing interests", "Author contributions"],
        "citations_style": "plos", "publisher": "PLOS", "min_references": 30,
        "heading_style": "numeric", "caption_style": "Fig. N.", "table_caption_above": False,
        "plagiarism_threshold": None, "ai_policy": "disclosure_required", "double_blind": False,
    },
    "frontiers": {
        "standard": "international", "word_limit": 12000, "page_limit": None,
        "abstract_word_limit": 300, "columns": 1, "page_size": "A4",
        "font_required": None, "font_size_required": None,
        "required_sections": ["Abstract", "Introduction", "Materials and Methods", "Results", "Discussion", "Conclusion", "References"],
        "required_statements": ["Data availability", "Funding", "Author contributions", "Conflict of interest"],
        "citations_style": "frontiers", "publisher": "Frontiers", "min_references": 30,
        "heading_style": "numeric", "caption_style": "Figure N.", "table_caption_above": False,
        "plagiarism_threshold": None, "ai_policy": "disclosure_required", "double_blind": False,
    },
}

UGC_THRESHOLD = {
    "level_0_max": 10, "level_1_max": 40, "level_2_max": 60, "level_3_min": 60,
    "single_source_max": 2, "bibliography_excluded": True, "quotes_excluded": True,
}

NATIONAL_PRESETS: Dict[str, Dict] = {
    "ugc_care": {
        "standard": "national", "page_limit": None, "word_limit": None,
        "abstract_word_limit": 250, "columns": 1, "page_size": "A4",
        "font_required": "Times New Roman", "font_size_required": 12,
        "required_sections": ["Abstract", "Introduction", "Conclusion", "References"],
        "required_statements": ["Data availability", "Funding", "Conflicts of interest", "Author contributions", "Ethics approval", "AI-use disclosure"],
        "citations_style": "apa", "publisher": "UGC-CARE listed", "min_references": 15,
        "heading_style": "numeric", "caption_style": "Fig. N.", "table_caption_above": True,
        "plagiarism_threshold": dict(UGC_THRESHOLD), "ai_policy": "ugc_2026", "double_blind": False,
        "require_orcid": True, "require_indexing": "Scopus or Web of Science", "min_novelty": "20%",
    },
    "aicte_conference": {
        "standard": "national", "page_limit": 6, "word_limit": None,
        "abstract_word_limit": 200, "columns": 1, "page_size": "A4",
        "font_required": "Times New Roman", "font_size_required": 12,
        "required_sections": ["Abstract", "Introduction", "References"],
        "required_statements": ["Acknowledgment"],
        "citations_style": "ieee", "publisher": "AICTE approved", "min_references": 8,
        "heading_style": "numeric", "caption_style": "Fig. N.", "table_caption_above": True,
        "plagiarism_threshold": dict(UGC_THRESHOLD), "ai_policy": "ugc_2026", "double_blind": False,
        "extra_pages_allowed": True, "extra_page_cost_inr": 1000,
    },
    "naac_journal": {
        "standard": "national", "page_limit": None, "word_limit": 6000,
        "abstract_word_limit": 250, "columns": 1, "page_size": "A4",
        "font_required": "Times New Roman", "font_size_required": 12,
        "required_sections": ["Abstract", "Introduction", "Conclusion", "References"],
        "required_statements": ["Data availability", "Funding", "Conflicts of interest", "Author contributions", "Ethics approval"],
        "citations_style": "apa", "publisher": "NAAC accredited journal", "min_references": 20,
        "heading_style": "numeric", "caption_style": "Fig. N.", "table_caption_above": True,
        "plagiarism_threshold": dict(UGC_THRESHOLD), "ai_policy": "ugc_2026", "double_blind": False,
        "require_orcid": True, "require_indexing": "Scopus or Web of Science",
    },
    "scopus_indian": {
        "standard": "national", "page_limit": None, "word_limit": 8000,
        "abstract_word_limit": 250, "columns": 1, "page_size": "A4",
        "font_required": "Times New Roman", "font_size_required": 10,
        "required_sections": ["Abstract", "Introduction", "Conclusion", "References"],
        "required_statements": ["Data availability", "Funding", "Conflicts of interest", "Author contributions"],
        "citations_style": "apa", "publisher": "Scopus-indexed Indian journal", "min_references": 25,
        "heading_style": "numeric", "caption_style": "Fig. N.", "table_caption_above": True,
        "plagiarism_threshold": dict(UGC_THRESHOLD), "ai_policy": "ugc_2026", "double_blind": False,
        "require_orcid": True, "require_indexing": "Scopus",
    },
    "indian_single_column": {
        "standard": "national", "page_limit": None, "word_limit": 6000,
        "abstract_word_limit": 200, "columns": 1, "page_size": "A4",
        "font_required": "Times New Roman", "font_size_required": 12,
        "required_sections": ["Abstract", "Introduction", "Conclusion", "References"],
        "required_statements": ["Funding", "Conflicts of interest"],
        "citations_style": "any", "publisher": "Indian journal (standard format)", "min_references": 10,
        "heading_style": "numeric", "caption_style": "Fig. N.", "table_caption_above": True,
        "plagiarism_threshold": dict(UGC_THRESHOLD), "ai_policy": "ugc_2026", "double_blind": False,
    },
    "ugc_phd_thesis": {
        "standard": "national", "page_limit": None, "word_limit": 80000,
        "abstract_word_limit": 300, "columns": 1, "page_size": "A4",
        "font_required": "Times New Roman", "font_size_required": 12,
        "required_sections": ["Abstract", "Introduction", "Literature Review", "Methodology", "Results", "Discussion", "Conclusion", "References", "Appendix"],
        "required_statements": ["Data availability", "Funding", "Conflicts of interest", "Ethics approval", "Plagiarism declaration", "AI-use disclosure"],
        "citations_style": "apa", "publisher": "UGC PhD thesis", "min_references": 50,
        "heading_style": "numeric", "caption_style": "Fig. N.", "table_caption_above": True,
        "plagiarism_threshold": dict(UGC_THRESHOLD), "ai_policy": "ugc_2026", "double_blind": False,
        "require_orcid": True, "require_indexing": "Shodhganga mandatory",
        "min_novelty": "20%", "require_plagiarism_report": True,
    },
}

ALL_PRESETS = {}
ALL_PRESETS.update(INTERNATIONAL_PRESETS)
ALL_PRESETS.update(NATIONAL_PRESETS)
for _p in ALL_PRESETS.values():
    _p["rules_last_verified"] = RULES_LAST_VERIFIED
ALL_PRESETS["generic"] = {
    "standard": "international", "word_limit": None, "page_limit": None,
    "abstract_word_limit": 250, "required_sections": ["Abstract", "Introduction", "Conclusion", "References"],
    "required_statements": ["Data availability", "Conflicts of interest", "Funding", "Author contributions"],
    "font_required": None, "font_size_required": None, "columns": None, "page_size": None,
    "citations_style": "any", "publisher": "unknown", "min_references": 8,
    "heading_style": None, "caption_style": None, "table_caption_above": None,
    "plagiarism_threshold": None, "ai_policy": "unknown", "double_blind": False,
}
PRESETS = ALL_PRESETS
DEFAULTS = PRESETS["generic"]


def list_venues(standard: Optional[str] = None) -> Dict[str, List[str]]:
    intl = sorted(k for k, v in PRESETS.items() if v.get("standard") == "international" and k != "generic")
    national = sorted(k for k, v in PRESETS.items() if v.get("standard") == "national")
    if standard == "international":
        return {"international": intl}
    elif standard == "national":
        return {"national": national}
    return {"international": intl, "national": national}


def get_rules(venue: str, venue_json: Optional[str] = None) -> Dict:
    rules = dict(DEFAULTS)
    key = venue.lower().replace("-", "_").replace(" ", "_") if venue else "generic"
    if key in PRESETS:
        rules.update(PRESETS[key])
    if venue_json:
        with open(venue_json, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            for candidate in (data.get("venue"), data.get(key), data):
                if isinstance(candidate, dict):
                    rules.update(candidate)
                    break
    rules["_name"] = venue if venue else "generic"
    return rules


def describe(venue: str) -> str:
    key = venue.lower().replace("-", "_").replace(" ", "_") if venue else "generic"
    p = PRESETS.get(key, {})
    std = p.get("standard", "international")
    pub = p.get("publisher", "unknown")
    label = "National (Indian)" if std == "national" else "International"
    return f"{venue} ({label} -- {pub})"
