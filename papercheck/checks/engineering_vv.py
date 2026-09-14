"""Engineering V&V engine — simulation/FEA/CFD credibility per ASME V&V,
NAFEMS, and NASA-STD-7009.

Engineering reviews (IEEE Trans., ASME Journals, Elsevier Mech. Eng.) desk-reject
or reject simulation papers on Verification & Validation grounds: no mesh/grid
independence, no validation against experiment, uncertainty never quantified.
This engine detects an engineering-simulation study and audits the seven
mandatory V&V story beats:

  V1  Mesh/grid/time-step independence study
  V2  Validation against experimental/analytical data
  V3  Solver + discretization scheme identification
  V4  Boundary conditions fully specified
  V5  Uncertainty quantification (sensitivity or error bars)
  V6  Material properties / constitutive model sourced
  V7  Hardware + solver version for reproducibility

Only fires on simulation vocabulary, so purely experimental or ML papers are
never touched. Each miss is a MEDIUM finding (reviewer friction, not fraud).
"""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_SIM = (
    r"finite\s+element|\bFEA\b|\bCFD\b|computational\s+fluid|finite\s+volume|"
    r"finite\s+difference|mesh(?:ing)?\s+(?:was|generation|refinement)|\bFEM\b|"
    r"multiphysics|discretiz|Navier[- ]Stokes|LES\b|\bDNS\b|\bRANS\b|k[- ]epsilon|"
    r"grid\s+generation|solver|Monte\s+Carlo|polynomial\s+chaos"
)


def _f(sev, title, detail, evidence, conf, action):
    f = Finding("Engineering V&V", sev, title, detail, evidence, action, conf)
    f.source = "engineering_vv"
    return f


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if not body or len(body.split()) < 200:
        return []
    if not re.search(_SIM, body, re.IGNORECASE):
        return []
    low = body.lower()
    out: List[Finding] = []

    # V1: mesh / grid / time-step independence
    if not re.search(
        r"mesh\s+(?:independence|convergence|refinement\s+study)|grid\s+(?:independence|convergence)|"
        r"time[- ]step\s+(?:independence|convergence)|convergence\s+(?:study|test|analysis)|"
        r"grid\s+convergence\s+index|\bGCI\b|Richardson\s+extrapolat|h-?refinement\s+study|"
        r"element\s+(?:count|size)\s+(?:was|is)\s+(?:varied|increased|refined)|coarser|finer\s+mesh",
        low):
        out.append(_f(
            Severity.MEDIUM,
            "No mesh/grid/time-step independence study (ASME V&V)",
            "Simulation credibility starts with proof the discrete solution has "
            "converged: report at least three mesh resolutions, the monitored "
            "quantity at each, and (ideally) a Grid Convergence Index. Reviewers "
            "at ASME/IEEE venues treat an unconverged mesh as grounds for "
            "rejection regardless of how good the results look.",
            "Simulation study detected; no independence/convergence-study language found",
            0.85,
            "Add a mesh-independence section: 3+ resolutions, monitored quantity, GCI or Richardson extrapolation"))

    # V2: validation against experiment / analytical solution
    if not re.search(
        r"validat(?:ed?|ing|ion)\s+against|compared\s+(?:with|to|against)\s+(?:the\s+)?(?:experimental|measured|analytical|literature)\s+(?:results?|data|values?)|"
        r"experimental\s+(?:validation|data\s+for\s+(?:comparison|verification))|benchmark\s+(?:problem|case|solution)|"
        r"analytical\s+solution|agreement\s+(?:within|of)\s+\d+(?:\.\d+)?\s*%|deviat(?:es?|ion)\s+.{0,30}\d+(?:\.\d+)?\s*%|"
        r"code[- ]to[- ]code\s+(?:comparison|verification)|method\s+of\s+manufactured\s+solutions",
        low):
        out.append(_f(
            Severity.MEDIUM,
            "No validation against experimental or analytical data (ASME V&V)",
            "Verification (solving the equations right) needs validation (solving "
            "the right equations): the results must be compared against an "
            "experiment, an analytical solution, a benchmark problem, or an "
            "established code. State the deviation quantitatively.",
            "No validation-comparison language found",
            0.85,
            "Add a validation section with quantitative deviation vs experiment/analytical/benchmark data"))

    # V3: solver + scheme identification
    if not re.search(
        r"(?:commercial|open[- ]source)\s+solver|ansys|comsol|abaqus|openfoam|fluent|star[- ]ccm|ls[- ]dyna|fenics|code_saturne|\bsu2\b|mfix|"
        r"solver\s+(?:version|used|was)|second[- ]order\s+(?:upwind|accurate)|first[- ]order|upwind|central\s+differenc|"
        r"simple\s+algorithm|\bpiso\b|\bpimple\b|galerkin|discretization\s+scheme|turbulence\s+model",
        low):
        out.append(_f(
            Severity.LOW,
            "Solver, version, and discretization schemes not identified",
            "Reproducibility requires naming the solver and version, the "
            "discretization schemes (time and space), and for CFD the turbulence "
            "model. 'A commercial solver was used' is not sufficient.",
            "No solver/scheme names detected",
            0.75,
            "Name the solver + version, spatial/temporal schemes, and turbulence/constitutive models"))

    # V4: boundary conditions
    if not re.search(
        r"boundary\s+conditions?\s+(?:were|are|applied|set|imposed|prescribed)|no[- ]slip|free[- ]slip|dirichlet|neumann|"
        r"inlet\s+velocity|outlet\s+(?:pressure|boundary)|fixed\s+(?:support|constraint)|clamped|symmetry\s+boundary|"
        r"prescribed\s+(?:displacement|temperature|pressure)|initial\s+conditions?",
        low):
        out.append(_f(
            Severity.MEDIUM,
            "Boundary conditions not specified",
            "A simulation without fully specified boundary and initial conditions "
            "cannot be reproduced \u2014 a standard reviewer demand on the first "
            "revision round. List every BC on every domain boundary with values.",
            "Simulation detected; no boundary-condition specification found",
            0.80,
            "Add a table of boundary/initial conditions with values for each domain face"))

    # V5: uncertainty quantification
    if not re.search(
        r"uncertainty\s+(?:quantification|analysis|of|estimate|\bUQ\b)|\bUQ\b|error\s+(?:estimate|bar)|confidence\s+(?:interval|band)|"
        r"sensitivity\s+(?:of|analysis|study)|sensitivit(?:y|ies)\s+to\s+(?:mesh|parameters?|input)|Monte\s+Carlo|polynomial\s+chaos|"
        r"sobol|aleator|epistemic",
        low):
        out.append(_f(
            Severity.MEDIUM,
            "No uncertainty quantification (NASA-STD-7009 / ASME V&V)",
            "NASA-STD-7009 and ASME V&V 20 both require an estimate of the "
            "uncertainty in reported simulation outputs \u2014 at minimum "
            "input-sensitivity analysis, at best propagation (Monte Carlo, "
            "polynomial chaos). Point-value predictions with no error bars are "
            "a known rejection trigger.",
            "No UQ / sensitivity-analysis language found",
            0.80,
            "Add uncertainty quantification: sensitivity to key inputs and mesh, error bars on predicted quantities"))

    # V6: material / constitutive properties sourced
    if re.search(r"material\s+(?:properties|model|behavi)|constitutive|young'?s\s+modulus|density\s+of|thermal\s+conductivity|viscosity", low):
        if not re.search(
            r"properties\s+(?:were\s+)?(?:taken|obtained|sourced|measured|tabulated)\s+from|from\s+the\s+literature|\[\d+\]\s*.{0,30}(?:properties|data)|"
            r"measured\s+(?:using|via|by)|supplier|datasheet|handbook|standard\s+(?:ASTM|ISO)\s*\d+|tabulated\s+in\s+table",
            low):
            out.append(_f(
                Severity.LOW,
                "Material/constitutive properties without a source",
                "Material or model parameters appear in the study but no source "
                "is given (measurement, datasheet, handbook, or cited dataset). "
                "Reviewers ask where every number came from.",
                "Material-property vocabulary present; no sourcing language found",
                0.65,
                "Cite or measure every material/constitutive parameter; tabulate them with sources"))

    # V7: hardware + solver version (reproducibility)
    if not re.search(
        r"(?:intel|amd|xeon|epyc|core\s+i[579]|ryzen|threadripper)\b|gpu\s*(?:model)?\s*[:=]|\brtx\b|\bgtx\b|\ba100\b|\bh100\b|\bv100\b|"
        r"\d+\s*gb\s+(?:ram|memory)|compute\s+node|hpc\s+cluster|parallel(?:ized)?\s+on\s+\d+\s+cores",
        low):
        out.append(_f(
            Severity.LOW,
            "Compute environment not reported",
            "Simulation reproducibility includes the hardware (CPU/GPU model, "
            "cores, memory) and parallelization setup, since iteration counts "
            "and round-off can differ across environments.",
            "No hardware specification detected",
            0.55,
            "Report CPU/GPU model, core count, memory, and runtime"))

    return out
