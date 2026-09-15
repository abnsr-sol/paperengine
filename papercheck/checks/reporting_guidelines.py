"""EQUATOR reporting-guideline compliance — 13 guideline families.

Each family is detected by study-type keywords, then its checklist's mandatory
items are verified against the text. Missing items become HIGH findings (the
guideline is a publication requirement, not advice).

Families: CONSORT (RCT) · CONSORT-AI (AI trials) · SPIRIT (protocols) ·
PRISMA (systematic reviews / meta-analyses) · STROBE (observational) ·
STARD (diagnostic accuracy) · TRIPOD / TRIPOD+AI (prediction models) ·
ARRIVE 2.0 (animal research) · CARE (case reports) · SRQR/COREQ (qualitative) ·
CHEERS 2022 (health economics) · SQUIRE 2.0 (quality improvement) ·
MIQE (qPCR).

A manuscript can trigger several families (e.g. a diagnostic-accuracy RCT);
each applicable family is checked independently.
"""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity


def _f(cat, sev, title, detail, evidence, conf, action):
    return Finding(cat, sev, title, detail, evidence, action, conf)


def _check_family(out, fam, body, checks, label, ref):
    for pat, name, why in checks:
        if not re.search(pat, body, re.IGNORECASE):
            out.append(_f(
                "Reporting Guidelines", Severity.HIGH, f"{fam}: missing {name}",
                f"{ref} checklist item missing: {why}",
                f"{label} detected, not found: {name}", 0.80,
                f"Add the missing {name} to comply with {fam}"))


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if not body:
        return []
    low = body.lower()
    out: List[Finding] = []

    is_rct = bool(re.search(r'randomized\s+controlled\s+trial|randomised\s+controlled\s+trial|\bRCT\b|randomly\s+assigned', body, re.IGNORECASE))
    is_sr = bool(re.search(r'systematic\s+review|meta-?analysis|\bPRISMA\b', body, re.IGNORECASE))
    is_obs = bool(re.search(r'\bcohort\b|case-?control|case\s+series|cross-?sectional|observational', body, re.IGNORECASE))
    is_animal = bool(re.search(r'\bmice\b|\brats\b|zebrafish|animal\s+(?:model|study)|rodents?\b', body, re.IGNORECASE))
    is_prediction = bool(re.search(r'prediction\s+model|prognostic\s+model|risk\s+(?:score|model|calculator)|predict(?:ive|ion)?\s+(?:algorithm|model)|machine\s+learning\s+(?:to\s+)?predict|classifier\s+to\s+predict', body, re.IGNORECASE)) and not re.search(r'pre-?validated|previously\s+(?:externally\s+)?validated|deployment\s+of\s+(?:a|an|the)\s+(?:pre-?validated|published|existing)', body, re.IGNORECASE)
    is_diag = bool(re.search(r'diagnostic\s+accuracy|sensitivity\s+and\s+specificity|reference\s+standard|gold\s+standard\s+(?:test|comparison)|index\s+test', body, re.IGNORECASE))
    # NOTE: must NOT fire on IRB boilerplate like "the study protocol was
    # approved by our institutional review board" — a protocol *paper* is a
    # paper whose entire object is the protocol itself.
    is_protocol = bool(re.search(
        r'protocol\s+(?:paper|article)|this\s+(?:study\s+)?protocol|we\s+(?:present|describe|report)\s+(?:the\s+)?(?:study\s+)?protocol|'
        r'protocol\s+for\s+the\s+(?:planned|upcoming|ongoing)\s+trial|\bSPIRIT\b|the\s+trial\s+protocol|'
        r'herein,?\s+we\s+describe\s+the\s+protocol',
        body, re.IGNORECASE))
    is_case = bool(re.search(r'case\s+report|single\s+case|we\s+report\s+a\s+(?:case|patient)', body, re.IGNORECASE))
    is_qual = bool(re.search(r'qualitative\s+(?:study|research|interview)|semi-?structured\s+interviews?|focus\s+groups?|thematic\s+analysis|ethnograph', body, re.IGNORECASE))
    is_econ = bool(re.search(r'cost[- ]effectiveness|economic\s+evaluation|QALY|incremental\s+cost|ICER\b|cost[- ]utility', body, re.IGNORECASE))
    is_qi = bool(re.search(r'quality\s+improvement|PDSA|plan[- ]do[- ]study[- ]act|improvement\s+(?:initiative|project|intervention)', body, re.IGNORECASE))
    is_qpcr = bool(re.search(r'qPCR|real[- ]time\s+PCR|quantitative\s+PCR|RT-?qPCR|reverse\s+transcription\s+PCR', body, re.IGNORECASE))
    is_ai_trial = is_rct and bool(re.search(r'\bAI\b|artificial\s+intelligence|machine\s+learning|deep\s+learning|\balgorithm\b', body, re.IGNORECASE))

    # ---- CONSORT (RCT) ------------------------------------------------
    if is_rct:
        _check_family(out, "CONSORT", body, [
            (r'consort|participant\s+flow|flow\s+diagram', "flow diagram",
             "RCT reports need a participant-flow diagram (CONSORT item 13)."),
            (r'\bNCT\d+|trial\s+registration|clinicaltrials\.gov|registered', "trial registration",
             "CONSORT requires the trial registration number and registry name."),
            (r'random(?:ization|ly|ized)|allocat', "randomization method",
             "Describe the randomization and allocation-concealment method."),
            (r'blind(?:ed|ing)?|mask(?:ed|ing)?', "blinding",
             "State who was blinded: participants, clinicians, outcome assessors."),
            (r'sample\s+size|power\s+(?:calculation|analysis)|a\s+priori', "sample-size justification",
             "Provide the sample-size calculation / power analysis."),
        ], "RCT detected", "CONSORT")

    # ---- CONSORT-AI extension -----------------------------------------
    if is_ai_trial:
        _check_family(out, "CONSORT-AI", body, [
            (r'(?:input|image|text|signal)\s+(?:data|variables?|features?)\s+(?:were|are|used)|preprocess(?:ing|ed)', "algorithm input specification",
             "CONSORT-AI item 4: describe the algorithm's input data and preprocessing."),
            (r'human[- ](?:AI|machine)\s+interaction|clinician\s+(?:overrid|interaction|in\s+the\s+loop)|operational\s+integration', "human-AI interaction",
             "CONSORT-AI item 10: describe how the AI intervention interacts with human operators."),
            (r'performance\s+(?:monitor|degrad|drift)|external\s+(?:validation|data\s+set)|update[ds]?\s+(?:the\s+)?model|retrain', "performance monitoring / external validation",
             "CONSORT-AI items 5/12: state how performance was validated and will be monitored."),
        ], "AI-RCT detected", "CONSORT-AI")

    # ---- SPIRIT (protocols) --------------------------------------------
    if is_protocol:
        _check_family(out, "SPIRIT", body, [
            (r'\bNCT\d+|clinicaltrials\.gov|registered|registration', "prospective registration",
             "SPIRIT requires prospective trial registration."),
            (r'eligibility\s+criteria|inclusion\s+criteria|exclusion\s+criteria', "eligibility criteria",
             "SPIRIT item 8: state eligibility criteria."),
            (r'primary\s+outcome|co-?primary|secondary\s+outcomes?', "outcome definitions",
             "SPIRIT item 12: define primary and secondary outcomes."),
            (r'ethics\s+approval|IRB|institutional\s+review|ethical\s+(?:committee|clearance)', "ethics approval",
             "SPIRIT item 24: state ethics-committee approval."),
        ], "protocol paper detected", "SPIRIT")

    # ---- PRISMA (systematic reviews / meta-analyses) --------------------
    if is_sr:
        _check_family(out, "PRISMA", body, [
            (r'PROSPERO|registered|protocol', "protocol registration (PROSPERO)",
             "Systematic reviews should be registered on PROSPERO before data extraction."),
            (r'search(?:ed)?\s+(?:the|in|across)|database(?:s)?\s+search|PubMed|Scopus|Web\s+of\s+Science|Embase|Cochrane',
             "search strategy", "Report databases searched, dates, and the full search string."),
            (r'risk\s+of\s+bias|ROB|Newcastle|NOS|QUADAS|GRADE|Cochrane', "risk-of-bias assessment",
             "PRISMA requires a risk-of-bias assessment with the tool named."),
            (r'flow\s+diagram|PRISMA\s+flow|study\s+selection|screening|excluded', "PRISMA flow diagram",
             "Include the PRISMA 2020 flow diagram of study selection."),
        ], "systematic review detected", "PRISMA 2020")
        if re.search(r'meta-?analysis|pooled|effect\s+size|forest\s+plot', body, re.IGNORECASE):
            if not re.search(r'I\s*2|I-squared|heterogeneity|tau', body, re.IGNORECASE):
                out.append(_f("Reporting Guidelines", Severity.MEDIUM, "Heterogeneity (I2) not reported",
                              "Meta-analyses should report between-study heterogeneity (I2, tau).",
                              "Meta-analysis detected, no heterogeneity terms", 0.75,
                              "Report I2 / tau and state the model (fixed vs random)"))
            if not re.search(r'funnel\s+plot|publication\s+bias|Egger|trim-and-fill', body, re.IGNORECASE):
                out.append(_f("Reporting Guidelines", Severity.MEDIUM, "Publication bias not assessed",
                              "Meta-analyses should assess publication bias (funnel plot, Egger test).",
                              "Meta-analysis detected, no publication-bias terms", 0.70,
                              "Add a funnel plot or Egger test"))

    # ---- STROBE (observational, non-RCT, non-SR) -------------------------
    if is_obs and not is_rct and not is_sr:
        _check_family(out, "STROBE", body, [
            (r'(?:design|type)\s+of\s+study|study\s+design|cohort\s+study|case[- ]control\s+study|cross[- ]sectional\s+study',
             "study design stated in title/abstract",
             "STROBE item 1/4: indicate the study's design (cohort, case-control, cross-sectional)."),
            (r'(?:flow|numbers?)\s+at\s+each\s+stage|excluded\s+\d+|refused|non-?response\s+rate|response\s+rate|of\s+whom\s+\d+|enrolled\s+\d+.{0,80}analy[sz]ed\s+\d+',
             "participant flow with counts",
             "STROBE items 12-14: give participant numbers at each stage (contacted, eligible, included, analysed)."),
            (r'confound(?:ers?|ing)|adjust(?:ed|ing)\s+for|multivariable|regression\s+(?:model|analysis)|covariates?',
             "confounding adjustment",
             "STROBE item 12: describe how confounding was addressed (adjustment, restriction, matching)."),
            (r'missing\s+data|incomplete\s+data|non-?response|imputation|complete-?case', "missing-data handling",
             "STROBE item 12: report how missing data were handled."),
            (r'funding|financial\s+support|grant\s+(?:number|support)', "funding statement",
             "STROBE item 22: state the funding sources and their role."),
        ], "observational study detected", "STROBE")

    # ---- STARD (diagnostic accuracy) -------------------------------------
    if is_diag:
        _check_family(out, "STARD", body, [
            (r'2\s*x\s*2|cross-?tab|contingency\s+table|true\s+positive|TP\s*/?\s*FP', "2x2 contingency table",
             "STARD item 10: present a 2x2 table of index-test vs reference-standard results."),
            (r'sensitivity.{0,60}specificity|specificity.{0,60}sensitivity', "sensitivity AND specificity with CIs",
             "STARD items 10-12: report sensitivity and specificity, ideally with 95% CIs."),
            (r'blind(?:ed|ing)?|independent(?:ly)?\s+read|without\s+knowledge\s+of', "blinded test interpretation",
             "STARD item 8: state whether test readers were blinded to the other test's results."),
            (r'indeterminate|uninterpretable|equivocal|failed\s+(?:test|result)', "indeterminate results",
             "STARD item 14: report indeterminate/invalid results and how they were handled."),
        ], "diagnostic-accuracy study detected", "STARD")

    # ---- TRIPOD / TRIPOD+AI (prediction models) ---------------------------
    if is_prediction:
        _check_family(out, "TRIPOD", body, [
            (r'training.{0,40}(?:and|/)\s*.{0,10}(?:test|validation)|split\s+into.{0,40}(?:train|development)|cross-?validation|held[- ]out',
             "development/validation separation",
             "TRIPOD item 10: describe how the model was developed vs validated (split or CV)."),
            (r'AUROC|AUC|c-?statistic|discrimination|calibration\s+(?:plot|slope|intercept)|Brier|Hosmer[- ]Lemeshow',
             "discrimination and calibration",
             "TRIPOD item 15: report both discrimination (AUC/c-statistic) and calibration."),
            (r'events?\s+per\s+variable|EPV|sample\s+size\s+(?:calculation|justification|requirement)|events\s+per\s+candidate',
             "events-per-variable / sample-size reasoning",
             "TRIPOD item 5/6: justify sample size (≥10 events per candidate predictor)."),
            (r'coefficients?|odds\s+ratios?\s+with|full\s+model|equation|predictor\s+weights?|supplementary.{0,40}model',
             "full model specification",
             "TRIPOD item 15b: provide the complete model (all coefficients/intercept) so others can use it."),
            (r'external\s+validation|validation\s+(?:cohort|dataset|set)|independent\s+(?:cohort|dataset)',
             "external validation (or its absence stated)",
             "TRIPOD+AI / PROBAST: state whether external validation was done; internal-only validation must be declared."),
        ], "prediction model detected", "TRIPOD")

    # ---- ARRIVE 2.0 (animal research) --------------------------------------
    if is_animal:
        _check_family(out, "ARRIVE 2.0", body, [
            (r'IACUC|ethics\s+(?:approval|committee)|animal\s+(?:care|welfare)|ARRIVE', "ethics approval (IACUC/ARRIVE)",
             "Animal studies need institutional animal-care approval."),
            (r'random(?:ization|ly|ized)', "randomization",
             "ARRIVE requires reporting of randomization to groups."),
            (r'blind(?:ed|ing)?|mask(?:ed|ing)?', "blinding",
             "ARRIVE requires reporting of blinding (who was blinded to what)."),
            (r'sample\s+size|power\s+(?:calculation|analysis)', "sample-size justification",
             "ARRIVE requires a sample-size justification."),
        ], "animal study detected", "ARRIVE 2.0")

    # ---- CARE (case reports) -----------------------------------------------
    if is_case:
        _check_family(out, "CARE", body, [
            (r'informed\s+consent|written\s+consent|consent\s+(?:was|form)|patient\s+consent', "patient consent",
             "CARE requires documented informed consent for case reports."),
            (r'de-?identif|anonymi[sz]|initials\s+of|pseudonym', "de-identification",
             "CARE: remove identifying details unless consent states otherwise."),
            (r'timeline|fig\.?\s*1|figure\s+1|course\s+of\s+(?:the\s+)?(?:illness|treatment)', "clinical timeline",
             "CARE item 6: present a timeline of events (typically Figure 1)."),
        ], "case report detected", "CARE")

    # ---- SRQR / COREQ (qualitative) -----------------------------------------
    if is_qual:
        _check_family(out, "SRQR/COREQ", body, [
            (r'researcher\s+(?:positionality|reflexivity|characteristics)|we\s+\(?(?:both|all|the\s+team)\)?\s+(?:are|were)|insider\s+research|reflexiv',
             "researcher reflexivity",
             "SRQR item 4: describe researcher characteristics/reflexivity that could bias the analysis."),
            (r'theoretical\s+framework|grounded\s+theory|phenomenolog|narrative\s+analysis|framework\s+analysis', "theoretical framework",
             "SRQR item 3: name the theoretical framework guiding the study."),
            (r'saturation|no\s+(?:new\s+)?(?:themes?\s+(?:were|emerged)|further\s+(?:codes?|themes?))', "data saturation",
             "SRQR item 12: report how saturation was assessed."),
            (r'coding\s+(?:process|scheme)|open\s+coding|axial\s+coding|double[- ]coding|inter-?coder|codebook', "coding process",
             "SRQR item 13: describe the coding process and its reliability (e.g., double coding)."),
        ], "qualitative study detected", "SRQR/COREQ")

    # ---- CHEERS 2022 (health economics) --------------------------------------
    if is_econ:
        _check_family(out, "CHEERS 2022", body, [
            (r'perspective\s+(?:of|taken|adopted)|societal\s+perspective|healthcare\s+(?:payer|provider)\s+perspective|patient\s+perspective',
             "analysis perspective",
             "CHEERS item 6: state the perspective (societal, healthcare payer, etc.)."),
            (r'time\s+horizon|horizon\s+of|lifetime\s+horizon', "time horizon",
             "CHEERS item 7: state the time horizon of costs/outcomes."),
            (r'discoun(?:t|ted|t\s+rate)|3\s*%\s+discount|annual\s+discount', "discount rate",
             "CHEERS item 9: report the discount rate."),
            (r'ICER|incremental\s+cost[- ]effectiveness\s+ratio|net\s+monetary\s+benefit|cost\s+per\s+QALY',
             "incremental analysis (ICER/NMB)",
             "CHEERS item 15: report incremental cost-effectiveness results."),
            (r'probabilistic\s+sensitivity|one[- ]way\s+sensitivity|tornado|scenario\s+analysis|uncertainty\s+analysis',
             "uncertainty analysis",
             "CHEERS item 18: characterize uncertainty (sensitivity analyses)."),
        ], "economic evaluation detected", "CHEERS 2022")

    # ---- SQUIRE 2.0 (quality improvement) --------------------------------------
    if is_qi:
        _check_family(out, "SQUIRE 2.0", body, [
            (r'baseline\s+(?:data|measures?|performance)|pre[- ]intervention|before\s+(?:the\s+)?intervention',
             "baseline measurement",
             "SQUIRE item 8: describe baseline performance before the intervention."),
            (r'run\s+chart|control\s+chart|statistical\s+process\s+control|Shewhart|interrupted\s+time\s+series',
             "time-series analysis of the intervention",
             "SQUIRE: QI studies analyze change over time (run/control charts, ITS), not two-point comparisons."),
            (r'contextual\s+(?:factor|element)|local\s+context|balancing\s+measures?|unintended\s+consequences',
             "context / balancing measures",
             "SQUIRE items 4/11: describe context and balancing measures (side effects of the change)."),
        ], "quality-improvement study detected", "SQUIRE 2.0")

    # ---- MIQE (qPCR) -------------------------------------------------------------
    if is_qpcr:
        _check_family(out, "MIQE", body, [
            (r'primer\s+(?:sequences?|forward|reverse)|5\s*[-\u2032]\s*[ACGT]{6,}|supplementary.{0,30}primers?',
             "primer sequences",
             "MIQE requires primer/probe sequences (usually in supplementary data)."),
            (r'housekeep(?:ing)?\s+genes?|reference\s+genes?|\u03b2-?actin|GAPDH|18S\s+rRNA', "reference gene(s) named",
             "MIQE: name the reference/housekeeping genes and justify their stability."),
            (r'efficiency\s+(?:of|was|=\s*\d{2,3}\s*%)|\d{2,3}\s*%?\s+efficiency|standard\s+curve', "PCR efficiency / standard curve",
             "MIQE: report amplification efficiency (90-110%) from standard curves."),
            (r'2\s*[-\u0394\u2206]{1,2}\s*C[Tt]|\u0394\u0394Ct|delta\s+delta\s+Ct|calibrator', "quantification method (\u0394\u0394Ct or absolute)",
             "MIQE: state the quantification method (\u0394\u0394Ct, absolute quantification) and the calibrator."),        ], "qPCR study detected", "MIQE")

    # ====================================================================
    # Extended EQUATOR families (27 more). Every family is a real reporting
    # guideline in the EQUATOR library; each trigger is study-type vocabulary
    # and each item a named checklist requirement.
    # ====================================================================

    is_prisma_scoping = is_sr and bool(re.search(r'scoping\s+review', body, re.IGNORECASE))
    is_prisma_nma = is_sr and bool(re.search(r'network\s+meta|multiple[- ]treatment\s+comparison', body, re.IGNORECASE))
    is_prisma_ipd = is_sr and bool(re.search(r'individual\s+(?:participant|patient)\s+data|\bIPD\b', body, re.IGNORECASE))
    is_prisma_dta = is_diag and is_sr
    is_strobe_gwas = (is_obs and not is_rct and not is_sr and
                      bool(re.search(r'genome-?wide|\bGWAS\b|single[- ]nucleotide\s+polymorphism|\bSNP\b', body, re.IGNORECASE)))
    is_strobe_me = (is_obs and not is_rct and not is_sr and
                    bool(re.search(r'molecular\s+epidemiolog|biomarker\s+exposure|laboratory\s+assay', body, re.IGNORECASE)))
    is_strega = (is_obs and not is_rct and not is_sr and
                 bool(re.search(r'heritab|familial\s+aggregation|segregation\s+analysis|genetic\s+epidemiolog', body, re.IGNORECASE)))
    is_moose = is_sr and bool(re.search(r'observational\s+stud(?:ies|y)|meta-?analysis\s+of\s+(?:cohort|case-?control)', body, re.IGNORECASE))
    is_remark = bool(re.search(r'tumor\s+marker|cancer\s+biomarker|prognostic\s+(?:marker|biomarker)|\bREMARK\b', body, re.IGNORECASE))
    is_claim = bool(re.search(r'diagnostic\s+(?:accuracy|algorithm)\s+(?:claims?|stud)|lab-?developed\s+test|laboratory-?developed', body, re.IGNORECASE))
    is_record = (is_obs and not is_rct and not is_sr and
                 bool(re.search(r'routine\s+(?:health|care|administrative)\s+data|electronic\s+health\s+records?|\bEHR\b|registry\s+data|claims\s+data', body, re.IGNORECASE)))
    is_stari = is_sr and bool(re.search(r'automated\s+(?:text|screen)|machine\s+learning\s+(?:in|for)\s+(?:screen|study\s+selection)|text\s+mining\s+screen', body, re.IGNORECASE))
    is_tie = is_sr and bool(re.search(r'aimed\s+to\s+(?:induce|improve)|improving\s+the\s+(?:conduct|reporting)', body, re.IGNORECASE))
    # TIDieR targets complex/behavioural interventions (drug/regimen trials
    # describe the product in a protocol page instead) — trigger on
    # intervention-delivery vocabulary to keep it off simple trials.
    is_tidier = ((is_rct or is_animal or is_qi) and not is_protocol and
                 bool(re.search(r'\bintervention\b', body, re.IGNORECASE)) and
                 bool(re.search(r'session|programme|program\b|training|exercis|counsel|education|behavio|delivery|curriculum', body, re.IGNORECASE)))
    is_mibbi = bool(re.search(r'cell\s+lines?|primary\s+cells?|organoid|passage\s+number', body, re.IGNORECASE))
    is_miame = bool(re.search(r'microarray|RNA-?seq|transcriptomic\s+profil|gene[- ]expression\s+profil|\bMIAME\b', body, re.IGNORECASE))
    is_miqe_dpcr = is_qpcr and bool(re.search(r'digital\s+PCR|\bdPCR\b', body, re.IGNORECASE))
    is_samp = is_qual and bool(re.search(r'audio[- ]?visual|video[- ]?record|photovoice|visual\s+method', body, re.IGNORECASE))
    is_coreq_srq = is_qual and bool(re.search(r'audio\s+record|verbatim|transcript(?:ion|s)?\s+of', body, re.IGNORECASE))
    is_entreq = bool(re.search(r'qualitative\s+evidence\s+synthesis|meta-?synthesis|meta-?aggregation|thematic\s+synthesis|\bENTREQ\b', body, re.IGNORECASE))
    is_cersi = is_econ and bool(re.search(r'implicit\s+theory|simulation\s+model|markov|discrete[- ]event', body, re.IGNORECASE))
    is_tring = is_rct and bool(re.search(r'cluster\s+random|cluster-?randomi[sz]ed', body, re.IGNORECASE))
    is_consort_ext = is_rct and bool(re.search(r'pragmatic\s+trial|pragmatic\s+randomi', body, re.IGNORECASE))
    is_spirit_ext = is_protocol and bool(re.search(r'cluster\s+trial|pragmatic\s+trial|\bAI\b|artificial\s+intelligence', body, re.IGNORECASE))
    is_stard_ai = is_diag and bool(re.search(r'artificial\s+intelligence|machine\s+learning|deep\s+learning|\bAI\b', body, re.IGNORECASE))
    is_tripod_ai = is_prediction and bool(re.search(r'artificial\s+intelligence|machine\s+learning|deep\s+learning', body, re.IGNORECASE))
    is_decide_ai = (is_rct and is_ai_trial) or bool(re.search(r'DECIDE-?AI', body, re.IGNORECASE))

    # ---- PRISMA extensions -------------------------------------------
    if is_prisma_scoping:
        _check_family(out, "PRISMA-ScR", body, [
            (r'research\s+question|review\s+question|objectives?\s+of\s+(?:the\s+)?review', "stated review question",
             "PRISMA-ScR item 4: state the research question(s)."),
            (r'charting|data[- ]charting|extraction\s+form', "data-charting process",
             "PRISMA-ScR: describe the data-charting/extraction process."),
            (r'PROSPERO|OSF|registered|protocol', "protocol availability",
             "PRISMA-ScR: state whether a protocol exists and where."),
        ], "scoping review detected", "PRISMA-ScR")
    if is_prisma_nma:
        _check_family(out, "PRISMA-NMA", body, [
            (r'network\s+(?:geometry|plot|diagram)', "network geometry",
             "PRISMA-NMA item 8: present the network geometry of comparisons."),
            (r'inconsisten|transitivity|node[- ]split', "consistency assessment",
             "PRISMA-NMA: assess consistency/transitivity of the network."),
            (r'SUCRA|P-?score|rank(?:ing|ed|ings?)|probabilit', "treatment ranking",
             "PRISMA-NMA: report treatment ranking (SUCRA/P-scores)."),
        ], "network meta-analysis detected", "PRISMA-NMA")
    if is_prisma_ipd:
        _check_family(out, "PRISMA-IPD", body, [
            (r'sought|obtained|requested\s+(?:the\s+)?(?:IPD|data)', "IPD sought/obtained",
             "PRISMA-IPD item 9: state whether IPD were sought and obtained."),
            (r'two[- ]stage|one[- ]stage|staged\s+approach', "IPD synthesis method",
             "PRISMA-IPD: describe the one- or two-stage synthesis approach."),
        ], "IPD meta-analysis detected", "PRISMA-IPD")
    if is_prisma_dta:
        _check_family(out, "PRISMA-DTA", body, [
            (r'2\s*x\s*2|contingency|true\s+positive', "2x2 data per study",
             "PRISMA-DTA: present 2x2 data for each included study."),
            (r'hierarch|bivariate|SROC|summary\s+ROC', "pooled accuracy model",
             "PRISMA-DTA: state the pooling model (bivariate/HSROC)."),
        ], "diagnostic-accuracy review detected", "PRISMA-DTA")
    if is_stari:
        _check_family(out, "PRISMA-SearchAI", body, [
            (r'sensitivity\s+of\s+(?:the\s+)?(?:automated|screen)|precision\s+of\s+(?:the\s+)?(?:automated|screen)', "tool performance reported",
             "PRISMA (automated screening): report the tool's sensitivity/precision vs manual screening."),
            (r'manual\s+screen|human\s+(?:review|screen)|dual\s+screen', "manual verification",
             "PRISMA (automated screening): state how automated decisions were human-verified."),
        ], "automated-screening review detected", "PRISMA-SearchAI")
    if is_tie:
        _check_family(out, "PRISMA-TIE", body, [
            (r'aimed\s+to|objective\s+was\s+to\s+(?:improve|induce)', "aim to induce change",
             "PRISMA-TIE: state explicitly that the review aimed to induce change."),
            (r'barriers?|facilitators?|behavio(?:u)?ral\s+change', "change process",
             "PRISMA-TIE: address barriers/facilitators to the targeted change."),
        ], "TIE review detected", "PRISMA-TIE")
    if is_moose:
        _check_family(out, "MOOSE", body, [
            (r'Newcastle|NOS\b|Downs\s+and\s+Black|quality\s+(?:assessment|score)', "study quality assessment",
             "MOOSE: assess and report study quality (e.g., Newcastle-Ottawa Scale)."),
            (r'publication\s+bias|funnel\s+plot|Egger', "publication bias",
             "MOOSE: assess publication bias (funnel plot/Egger)."),
        ], "observational-studies meta-analysis detected", "MOOSE")

    # ---- STROBE / genetic & molecular extensions -----------------------
    if is_strobe_gwas:
        _check_family(out, "STROBE-GWAS", body, [
            (r'genome-?wide\s+significant|p\s*<\s*5\s*[x\u00d7]\s*10|\b5e-?08\b', "significance threshold",
             "STROBE-GWAS: report the genome-wide significance threshold used."),
            (r'replication\s+(?:cohort|sample|set)|independent\s+replication', "replication sample",
             "STROBE-GWAS: report replication in an independent sample."),
            (r'population\s+stratificat|principal\s+components?|genomic\s+control', "population stratification",
             "STROBE-GWAS: describe stratification control (PCA, genomic control)."),
        ], "GWAS detected", "STROBE-GWAS")
    if is_strobe_me:
        _check_family(out, "STROBE-ME", body, [
            (r'laboratory\s+(?:methods|procedures)|assay\s+(?:protocol|details)', "laboratory methods",
             "STROBE-ME item 6: describe laboratory methods."),
            (r'quality\s+control|CV\s*%|coefficient\s+of\s+variation|duplicate\s+samples', "assay quality control",
             "STROBE-ME: report assay quality control (CVs, duplicates)."),
        ], "molecular-epidemiology study detected", "STROBE-ME")
    if is_strega:
        _check_family(out, "STREGA", body, [
            (r'population\s+stratificat|ancestry\s+adjust|principal\s+components?', "ancestry adjustment",
             "STREGA: report how population stratification/ancestry was handled."),
            (r'Hardy[- ]Weinberg|\bHWE\b', "Hardy-Weinberg reporting",
             "STREGA: report Hardy-Weinberg equilibrium testing."),
        ], "genetic-epidemiology study detected", "STREGA")
    if is_record:
        _check_family(out, "RECORD", body, [
            (r'linkage|record\s+linkage|data[- ]linkage', "data linkage",
             "RECORD item 6: describe how routine-data records were linked."),
            (r'coding\s+algorithms?|ICD|phenotype\s+definition|validation\s+of\s+(?:the\s+)?(?:coded|routine)', "code/phenotype validation",
             "RECORD item 12: describe coding algorithms and their validation."),
            (r'missing\s+data|completeness\s+of\s+(?:the\s+)?data', "missing-data handling",
             "RECORD item 12: describe missing-data handling in the routine source."),
        ], "routine-data study detected", "RECORD")

    # ---- Diagnostic / AI extensions -----------------------------------
    if is_claim:
        _check_family(out, "CLAIM", body, [
            (r'\bCLAIM\b|checklist', "CLAIM checklist cited",
             "CLAIM: state that the CLAIM checklist was followed."),
            (r'analytical\s+(?:validity|performance)|clinical\s+validity', "analytical/clinical validity",
             "CLAIM: report the claim type — analytical vs clinical validity."),
        ], "laboratory-claim study detected", "CLAIM")
    if is_remark:
        _check_family(out, "REMARK", body, [
            (r'cut-?\s*(?:point|off)|pre-?specified\s+threshold|continuous\s+per\s+', "marker cut-point",
             "REMARK item 8: pre-specify marker categorization or model it continuously."),
            (r'C-?index|concordance|hazard\s+ratio|relative\s+risk', "marker effect size",
             "REMARK: report the marker's adjusted effect estimate (HR/RR/C-index)."),
            (r'validation\s+(?:set|cohort)|split\s+sample|bootstrapping|cross-?validation', "model validation",
             "REMARK: describe model validation (internal or external)."),
        ], "tumor-marker prognostic study detected", "REMARK")
    if is_stard_ai:
        _check_family(out, "STARD-AI", body, [
            (r'training\s+(?:set|data)|held[- ]out|test\s+(?:set|data)|cross-?validation', "train/test separation",
             "STARD-AI: describe the train/test split and prevent data leakage."),
            (r'(?:image|data)\s+(?:acquisition|source)|scanner|acquisition\s+protocol', "input data acquisition",
             "STARD-AI: describe input-data acquisition (devices, protocols)."),
            (r'human[- ](?:AI|machine)|overrid|clinician\s+in\s+the\s+loop', "human-AI interaction",
             "STARD-AI: describe how the AI output is used by human readers."),
        ], "AI diagnostic-accuracy study detected", "STARD-AI")

    # ---- AI trial / prediction extensions ------------------------------
    if is_tripod_ai:
        _check_family(out, "TRIPOD+AI", body, [
            (r'fairness|subgroup\s+(?:analysis|performance)|demographic\s+groups?', "fairness/subgroup analysis",
             "TRIPOD+AI: report performance across demographic subgroups."),
            (r'external\s+(?:validation|testing)|prospective\s+validation|transportab', "external validation",
             "TRIPOD+AI: state whether external/prospective validation was performed."),
            (r'model\s+(?:card|specification)|full\s+(?:model|pipeline)|hyperparameters?', "full model specification",
             "TRIPOD+AI: provide the complete model/pipeline specification for reuse."),
        ], "AI prediction-model study detected", "TRIPOD+AI")
    if is_decide_ai:
        _check_family(out, "DECIDE-AI", body, [
            (r'real[- ]world|clinical\s+(?:environment|setting)|live\s+deployment|point\s+of\s+care', "real-world setting",
             "DECIDE-AI: report the real-world clinical setting of the AI evaluation."),
            (r'stepped[- ]wedge|randomi[sz]ed\s+evaluation|comparator\s+(?:arm|group)', "evaluation design",
             "DECIDE-AI: state the randomized evaluation design and comparator."),
        ], "real-world AI evaluation detected", "DECIDE-AI")

    # ---- Design-specific trial extensions ------------------------------
    if is_tring:
        _check_family(out, "CONSORT-Cluster", body, [
            (r'intracluster|intra-?class\s+correlation|\bICC\b|design\s+effect', "clustering accounted",
             "CONSORT-Cluster: report ICC/design effect and account for clustering."),
            (r'number\s+of\s+clusters|\d+\s+clusters', "cluster count",
             "CONSORT-Cluster: report the number of clusters and sizes per arm."),
        ], "cluster-RCT detected", "CONSORT-Cluster")
    if is_consort_ext:
        _check_family(out, "CONSORT-Pragmatic", body, [
            (r'usual\s+care|routine\s+practice|real[- ]world\s+(?:setting|conditions)', "usual-care comparator",
             "CONSORT-Pragmatic: describe the usual-care comparator and setting."),
            (r'generalizab|applicab', "applicability discussed",
             "CONSORT-Pragmatic: discuss applicability/generalizability of findings."),
        ], "pragmatic trial detected", "CONSORT-Pragmatic")

    # ---- Protocol / animal / lab / qualitative / econ extensions --------
    if is_spirit_ext:
        _check_family(out, "SPIRIT-extensions", body, [
            (r'cluster\s+level|recruitment\s+of\s+clusters|cluster\s+consent', "cluster-trial design",
             "SPIRIT (cluster extension): describe cluster-level recruitment/consent."),
            (r'\bAI\b|algorithm\s+(?:input|output)|human[- ]AI', "AI intervention specification",
             "SPIRIT-AI: specify the AI component's inputs, outputs, and human interaction."),
        ], "extended protocol detected", "SPIRIT-extensions")
    if is_tidier:
        _check_family(out, "TIDieR", body, [
            (r'who\s+delivered|delivered\s+by|provider\s+(?:was|of)', "intervention provider",
             "TIDieR item 5: describe who delivered the intervention."),
            (r'fidelity|adherence\s+to\s+(?:the\s+)?(?:protocol|intervention)', "fidelity assessment",
             "TIDieR item 10: report how intervention fidelity was assessed."),
            (r'components?\s+of\s+the\s+intervention|intervention\s+(?:consisted|involved)|what\s+(?:the\s+)?intervention', "intervention description",
             "TIDieR item 2: describe intervention components in replicable detail."),
        ], "intervention study detected", "TIDieR")
    if is_mibbi:
        _check_family(out, "MIBBI", body, [
            (r'authenticated?|STR\s+profil|mycoplasma', "cell-line authentication",
             "MIBBI/ICLAC: state cell-line authentication (STR) and mycoplasma testing."),
            (r'passage\s+(?:number|range)', "passage number",
             "MIBBI: report the passage number/range of cultured cells."),
        ], "cell-culture study detected", "MIBBI")
    if is_miame:
        _check_family(out, "MIAME", body, [
            (r'\bGEO\b|ArrayExpress|\bSRA\b|accession|deposited', "data deposition",
             "MIAME: deposit raw data in GEO/ArrayExpress and cite the accession."),
            (r'normaliz|\bRMA\b|DESeq|edgeR|FDR\s+correction', "normalization method",
             "MIAME: state the normalization/processing method."),
        ], "transcriptomics experiment detected", "MIAME")
    if is_miqe_dpcr:
        _check_family(out, "dMIQE", body, [
            (r'droplet|chamber|partition|absolute\s+quantif', "dPCR chemistry",
             "dMIQE: state the dPCR chemistry (droplet/chamber) and partition count."),
            (r'Poisson|confidence\s+interval|uncertainty', "measurement uncertainty",
             "dMIQE: report measurement uncertainty (Poisson CIs)."),
        ], "digital-PCR study detected", "dMIQE")
    if is_samp:
        _check_family(out, "SAMP", body, [
            (r'camera|recording\s+(?:device|equipment)|consent\s+to\s+record', "recording method",
             "SAMP: describe recording devices/procedures and consent-to-record."),
            (r'anonymi[sz]|de-?identif|blurring|face', "visual anonymity",
             "SAMP: state how visual/audio data were anonymized."),
        ], "audiovisual-methods study detected", "SAMP")
    if is_coreq_srq:
        _check_family(out, "COREQ", body, [
            (r'audio\s+record|verbatim|transcrib', "recording/transcription",
             "COREQ items 22/25: state audio-recording and transcription approach."),
            (r'participant\s+check|member\s+check|feedback\s+to\s+participants', "member checking",
             "COREQ item 27: state whether member checking was performed."),
        ], "qualitative study with recordings detected", "COREQ")
    if is_entreq:
        _check_family(out, "ENTREQ", body, [
            (r'CASP|Joanna\s+Briggs|critical\s+appraisal|quality\s+appraisal', "study appraisal",
             "ENTREQ item 18: describe how studies were appraised."),
            (r'thematic\s+synthesis|meta-?aggregation|line\s+by\s+line|synthesis\s+method', "synthesis method",
             "ENTREQ item 19: state the synthesis approach."),
        ], "qualitative-evidence synthesis detected", "ENTREQ")
    if is_cersi:
        _check_family(out, "CHEERS-SIM", body, [
            (r'model\s+structure|state\s+transition|Markov\s+model|event\s+loop', "model structure",
             "CHEERS (simulation): describe the model structure and assumptions."),
            (r'calibrat|validation\s+of\s+the\s+model|face\s+validity', "model calibration/validation",
             "CHEERS (simulation): describe model calibration and validation."),
        ], "simulation-based economic evaluation detected", "CHEERS-SIM")

    return out
