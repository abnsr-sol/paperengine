"""Physical & computational plausibility engine.

Deterministic sanity checks on claimed performance vs physics and hardware:

1. **Speed-of-light latency floor**: distributed-systems claims of round-trip
   latencies below the physical minimum for the claimed distance. Light in
   fiber travels ~2e8 m/s, so a 6000 km US-EU link has a hard RTT floor of
   ~60 ms. Anything below it is physically impossible regardless of stack.
2. **GPU VRAM feasibility**: model parameter counts claimed trainable on
   declared hardware. AdamW static state = 2 bytes (fp16 weights) + 2
   (grads) + 8 (momentum+variance fp32) = 12 bytes/param; a 70B model needs
   ~840 GB — 4x24GB consumer GPUs cannot do it without offloading claims.

Both checks are arithmetic; findings say exactly which numbers conflict.
Conservative gates: only fires when the paper makes explicit claims.
"""
from __future__ import annotations

import re
from typing import List

from ..ingestion import Document
from ..risk import Finding, Severity

_C_FIBER = 2.0e8  # m/s, speed of light in glass fiber (~2/3 c)

# distance phrases -> kilometers
_DIST = [
    (r"(?:(?:us|united states|usa|america)[\s-]*(?:and|to)[- ]*(?:eu|europe|european)|(?:eu|europe)[\s-]*(?:and|to)[- ]*(?:us|united states|usa|america)|"
     r"(?:us|united states|usa|america)[ ]*[-–][ ]*(?:eu|europe|european)|(?:eu|europe|european)[ ]*[-–][ ]*(?:us|united states|usa|america)|"
     r"trans[\s-]*atlantic|inter[\s-]*continental|cross[\s-]*continental)",
     6000.0),
    (r"(?:us|usa|america)[\s-]*(?:and|to|[-–])[ ]*(?:asia|japan|singapore|india|china)", 11000.0),
    (r"((?:\d+(?:\.\d+)?)\s*(?:km|kilometers?|kilometres?))", None),  # captured
]

# latency phrases: "12 ms round-trip", "sub-millisecond RTT across regions"
_MS = r"(\d+(?:\.\d+)?)\s*(?:ms|milliseconds?)(?:\s*\([^)]*\))?"
_MS_CONTEXT = re.compile(
    r"(?:latency|round[\s-]*trip|rtt|response\s+time)", re.IGNORECASE)


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Physical", sev, title, detail, evidence, action, conf)


def _run_latency(body: str) -> List[Finding]:
    out: List[Finding] = []
    low = body.lower()
    # inter-continental context?
    for pat, km_default in _DIST:
        m = re.search(pat, low, re.IGNORECASE)
        if not m:
            continue
        if m.group(1) if m.groups() else km_default:
            km = float(m.group(1)) if m.groups() and m.group(1) else (km_default or 6000.0)
        else:
            continue
        floor_ms = 2.0 * km * 1000.0 / _C_FIBER * 1000.0  # RTT in ms
        # find claimed latencies near latency language
        for lm in _MS_CONTEXT.finditer(low):
            window = low[lm.start():lm.start() + 200]
            for mm in re.finditer(_MS, window):
                claimed = float(mm.group(1))
                # "sub-millisecond" style claims near inter-continent language
                if claimed < floor_ms * 0.5:
                    out.append(_f(
                        Severity.HIGH,
                        "Claimed latency below the speed-of-light floor",
                        f"The paper claims ~{claimed:g} ms latency for a link of "
                        f"roughly {km:,.0f} km, but the physical minimum round-trip "
                        f"for light in fiber is {floor_ms:.0f} ms. No protocol or "
                        "hardware can beat physics; either the distance, the "
                        "latency, or the deployment claim is misstated.",
                        f"claimed {claimed:g} ms vs floor {floor_ms:.0f} ms "
                        f"(~{km:,.0f} km)", 0.75,
                        "Re-verify the measurement: state the actual distance, "
                        "whether it is one-way, and what exactly was timed."))
                    break
            if out:
                break
        if out:
            break
    return out


def _run_vram(body: str) -> List[Finding]:
    out: List[Finding] = []
    low = body.lower()
    # model size: "70B parameters", "7 billion parameters"
    pm = re.search(r"(\d+(?:\.\d+)?)\s*(?:b\b|billion)\s+(?:parameters?|params)", low)
    if not pm:
        return out
    params_b = float(pm.group(1))
    # declared GPUs: "4 x A100 (40 GB)", "8 RTX 3090", "two V100s"
    gpu_m = re.search(
        r"(\d+|one|two|three|four|six|eight)\s*[x×\s]\s*"
        r"(a100|v100|h100|a6000|rtx\s*3090|rtx\s*4090|rtx\s*4080|rtx\s*3080|t4|"
        r"rtx\s*(?:20|30|40)\d{2}|gtx\s*1080(?:\s*ti)?)", low)
    if not gpu_m:
        return out
    n_words = {"one": 1, "two": 2, "three": 3, "four": 4, "six": 6, "eight": 8}
    n_raw = gpu_m.group(1)
    n = int(n_raw) if n_raw.isdigit() else n_words.get(n_raw, 0)
    if not n:
        return out
    gpu = gpu_m.group(2)
    vram_map = {"h100": 80, "a100": 80, "v100": 32, "a6000": 48, "t4": 16,
                "rtx 3090": 24, "rtx 4090": 24, "rtx 4080": 16, "rtx 3080": 10,
                "gtx 1080": 11, "gtx 1080 ti": 11}
    vram = None
    for k, v in vram_map.items():
        if k in gpu:
            vram = v
            break
    if vram is None:
        vram = 24  # conservative default for RTX consumer cards
    # any offloading / quantization escape hatch?
    escape = re.search(
        r"offload|zero[- ]?1|zero[- ]?2|zero[- ]?3|deepspeed|quantiz|int8|int4|"
        r"4[- ]?bit|8[- ]?bit|lora|qlora|gradient checkpoint|model parallel|"
        r"pipeline parallel|tensor parallel|cpu\s+offload|nvme", low)
    total_gb = n * vram
    needed_gb = params_b * 12.0  # 12 bytes per parameter, params already in billions -> GB
    if not escape and needed_gb > total_gb * 1.5:
        out.append(_f(
            Severity.HIGH,
            "Training claim exceeds declared GPU memory",
            f"The paper claims to train a ~{params_b:g}B-parameter model on "
            f"{n} x {gpu.upper()} ({total_gb} GB total), but AdamW static state "
            f"for fp16 training needs ~{needed_gb:.0f} GB (weights+grads+"
            "optimizer states, 12 bytes/param) — and no offloading, "
            "quantization, or parallelism strategy is mentioned. Reviewers "
            "who know the math will flag this immediately.",
            f"{params_b:g}B params on {n}x{gpu.upper()}: need ~{needed_gb:.0f} GB, "
            f"have {total_gb} GB", 0.7,
            "State the actual training strategy (ZeRO stage, LoRA/QLoRA, "
            "offloading, quantization) or correct the hardware/model-size "
            "claims."))
    return out


def run(doc: Document, ctx) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if doc.word_count < 200:
        return []
    out = _run_latency(body)
    out += _run_vram(body)
    return out
