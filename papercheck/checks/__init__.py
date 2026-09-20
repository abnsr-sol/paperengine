"""Check engines. Each exposes run(doc, ctx) -> List[Finding].
To add a rejection angle: create a module with run(), register in ALL_ENGINES.
"""
from __future__ import annotations
import importlib
import pkgutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from ..ingestion import Document

CheckFn = Callable[[Document, "CheckContext"], List["Finding"]]

@dataclass
class CheckContext:
    venue: str = "generic"
    rules: Dict = field(default_factory=dict)
    corpus: List[Document] = field(default_factory=list)
    online: bool = False
    mailto: str = ""
    max_online_checks: int = 10
    online_cache: Dict[str, object] = field(default_factory=dict)
    pubpeer_threshold: int = 2

    def __post_init__(self) -> None:
        if self.venue is None:
            self.venue = "generic"
        if self.rules is None:
            self.rules = {}
        if self.corpus is None:
            self.corpus = []
        if self.online_cache is None:
            self.online_cache = {}


def _registry_self_check(engines: List[CheckFn]) -> None:
    """Raise at import time if the registry drifts from the files on disk."""
    base = Path(__file__).resolve().parent
    engine_files = {
        p.stem
        for p in base.glob("*.py")
        if p.stem != "__init__" and not p.stem.startswith("_")
    }
    registered = {
        fn.__module__.rsplit(".", 1)[-1] for fn in engines
    }
    if engine_files != registered:
        extra = engine_files - registered
        missing = registered - engine_files
        parts = []
        if extra:
            parts.append("engine files not registered: " + ", ".join(sorted(extra)))
        if missing:
            parts.append("registered engines not on disk: " + ", ".join(sorted(missing)))
        raise RuntimeError("engine registry drift: " + "; ".join(parts))
    if len(engines) != len(engine_files):
        raise RuntimeError(
            "engine count mismatch: registry=%d files=%d"
            % (len(engines), len(engine_files))
        )


def _import_engines() -> List[CheckFn]:
    from importlib import import_module
    pkg = __package__ or "papercheck.checks"
    mods = [name for _, name, _ in pkgutil.iter_modules([__path__[0]])]
    out: List[CheckFn] = []
    for mod in sorted(mods):
        if mod.startswith("_"):
            continue
        m = import_module(f".{mod}", pkg)
        run = getattr(m, "run", None)
        if callable(run):
            out.append(run)
    return out


def run_all_engines(doc: Document, ctx: CheckContext) -> Tuple[List["Finding"], List[str]]:
    """Run every registered engine with fault isolation.

    Returns (findings, engine_errors): an engine that raises is skipped and
    its name + error appended to engine_errors instead of aborting the whole
    check — one bad engine must never blank a report (the GUI crash of
    v1.8.0 was exactly this failure class).

    A failed engine additionally contributes one LOW-severity finding, so the
    report tells the reader that coverage was reduced instead of silently
    looking clean. Reports must never be *quieter* than reality.
    """
    findings: List["Finding"] = []
    errors: List[str] = []
    for engine in ALL_ENGINES:
        name, eff, err = _run_engine(engine, doc, ctx)
        if err is not None:
            errors.append(err)
            findings.append(_engine_error_finding(name, err))
        findings.extend(eff)
    return findings, errors


def _engine_error_finding(name: str, err: str):
    """LOW-severity note that one engine could not complete."""
    from ..risk import Finding, Severity
    return Finding(
        "Engine", Severity.LOW,
        f"Check engine '{name}' did not complete",
        "One engine failed on this manuscript, so that specific check did not "
        "run. Every other engine completed normally — the report is still "
        "valid, but this angle is uncovered.",
        err[:300],
        confidence=1.0,
        action="Re-run to confirm; if it repeats, this manuscript triggered a "
               "bug in that engine — please report it with the error above.")


def _run_engine(engine: CheckFn, doc: Document, ctx: CheckContext):
    name = getattr(engine, "__module__", "engine").rsplit(".", 1)[-1]
    try:
        engine_findings = engine(doc, ctx) or []
    except Exception as exc:  # noqa: BLE001
        return name, [], f"{name}: {type(exc).__name__}: {exc}"
    for f in engine_findings:
        if not f.source:
            f.source = name
    return name, engine_findings, None


# import-time guard: keeps engine registry honest forever
def _build_registry() -> List[CheckFn]:
    engines = _import_engines()
    _registry_self_check(engines)
    return engines


ALL_ENGINES: List[CheckFn] = _build_registry()
