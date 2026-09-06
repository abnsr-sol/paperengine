"""Figure quality engine: western blot specifics, microscopy scale bars, box plots, colorblind accessibility."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Figure Quality", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx: object) -> List[Finding]:
    text = doc.text or ""
    if not text:
        return []
    low = text.lower()
    out = []
    # western blots
    if re.search(r"western\s+blot|immunoblot", low):
        if not re.search(r"molecular\s+(?:weight|mass)\s+marker|protein\s+ladder|kda\s+marker|loading\s+control|actin|gapdh|tubulin", low):
            out.append(_f(Severity.HIGH, "Western blots without markers/controls", "Journals require molecular-weight markers and loading controls (actin/GAPDH) on every blot.",
                          "Western-blot keywords, no marker/loading-control terms", 0.80, "Add marker lanes and loading controls; state the antibody and exposure"))
        if not re.search(r"cropped|uncropped|full-?length\s+blot|original\s+blot", low):
            out.append(_f(Severity.MEDIUM, "Cropped blots without uncropped originals", "Editors increasingly require uncropped blot images as supplementary material.",
                          "Blot mentioned, no uncropped-original wording", 0.65, "Provide uncropped blots in supplementary information"))
    # microscopy
    if re.search(r"microscop|histolog|immunofluoresc|confocal|staining|stained", low):
        if not re.search(r"scale\s+bar|magnification|objective\s+(?:lens|\d+x)|nan?ometer|micron|micrometer|µm|um\b", low):
            out.append(_f(Severity.MEDIUM, "Microscopy images without scale bar/magnification", "Microscopy figures must state scale bars and magnification.",
                          "Microscopy keywords, no scale/magnification info", 0.75, "Add scale bars to images and state the objective/magnification in captions"))
    # box plots
    if re.search(r"box[- ]?plot|box-?whisker", low):
        if not re.search(r"individual\s+(?:data\s+)?points|scatter|raw\s+data|all\s+points|overlay(?:ed)?\s+points|notches?\b", low):
            out.append(_f(Severity.MEDIUM, "Box plots without individual data points", "Journals recommend showing raw data points overlaid on box plots.",
                          "Box-plot keywords, no individual-points wording", 0.65, "Overlay all data points on box plots and define whiskers (min-max or 1.5 IQR)"))
    # colorblind accessibility
    if re.search(r"red[- ]green|green[- ]red", low) and re.search(r"figure|plot|graph|color", low):
        out.append(_f(Severity.LOW, "Possible red-green color coding in figures", "Red-green palettes are inaccessible to ~8% of men; use colorblind-safe palettes (viridis) or add patterns.",
                      "red/green color terms near figure wording", 0.55, "Switch to a colorblind-safe palette and add distinct line styles/markers"))
    # error bar definition in captions
    if re.search(r"error\s+bars?", low) and not re.search(r"(?:represent|show|indicate|denote)s?\s+(?:the\s+)?(?:standard\s+)?(?:deviation|error)|\b(?:SD|SEM|SE)\b|95%\s*CI", low):
        out.append(_f(Severity.LOW, "Error bars not defined in captions", "Captions must state whether error bars show SD, SEM, or 95% CI and whether they are one- or two-sided.",
                      "Error bars mentioned, no SD/SEM/CI definition nearby", 0.60, "Define error bars explicitly in each caption"))
    return out