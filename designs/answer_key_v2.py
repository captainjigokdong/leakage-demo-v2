"""v2 정답표 형식 (4a에서 확정, 내용은 4b). 형식 설명: docs/answer_key_format_v2.md.

이 파일에는 새 후보의 내용이 없다. 점검기(leakcheck)를 불러오지 않는다.
"""
from __future__ import annotations

import json
from pathlib import Path

from designs.inject import targets_of

ROOT = Path(__file__).resolve().parent.parent
JUSTIFIED = ROOT / "docs" / "justified_findings_v2.json"
VERSION = "v2"
QUESTIONS = {"Q1", "Q2", "Q3", "Q4", "Q5", "Q7"}
VERDICTS = {"차단", "경고"}
TYPES = {"dynamic", "fixed"}

# 지적 하나를 판정하는 우선순위 (앞이 먼저). 칸이 여러 줄에 맞으면 가장 앞 줄로 판정한다.
PRIORITY = [
    ("accept", "탐지", "결함의 accept_targets를 지목 (보조 분석은 accept_questions의 종류여야 함)"),
    ("support", "중립", "결함의 support_targets만 지목 — 탐지도 오경보도 아님"),
    ("justified", "중립", "바탕의 정당한 지적 목록 칸 (docs/justified_findings_v2.json) — 두 조건 같게"),
    ("legit", "오경보", "바탕의 수상해 보이지만 정당한 항목 (legit_changes)"),
    ("other", "오경보", "그 밖의 칸"),
]

# 바탕의 "수상해 보이지만 정당한 항목" (docs/clean_designs_v2.md 4절). 지적하면 오경보.
LEGIT_ITEMS = {
    "aki_b": ["features:k_last_6h"],
    "aki_c": ["features:n_admissions_to_tp"],
    "readmit_b": ["features:prior_dx_group"],
    "readmit_c": ["features:prior_cr_last"],
}

# 공개 사례 중 기본값(accept = 패치의 모든 지목 항목, support 없음, accept_questions = [질문])과 다른 것.
# 2c 기록에 근거가 있는 것만 (docs/injection_log_v2.md). 보류 사례를 기본값과 다르게 정하면 4b에서 사용자 승인.
PUBLIC_EXCEPTIONS = {
    "E04": {"accept_questions": ["Q1", "Q4"],
            "basis": "2c: 시술 개수가 투석 처치(대리 기록)도 세므로 Q1과 Q4가 모두 정당한 종류"},
    "E09": {"support_targets": ["features:prior_dx_main"],
            "basis": "2c 사용자 결정: 더한 진단 코드 범주형 특징 자체는 결함이 아니다 (결함은 결과율 인코딩)"},
}


def defect_entry(case_id: str, question: str, holdout: bool, expected_verdict: str, ops: list[dict],
                 support_targets: list[str] | None = None, accept_questions: list[str] | None = None) -> dict:
    """사례 하나의 정답 칸. 기본값: accept = 패치의 지목 항목 중 support가 아닌 것 전부."""
    targets = targets_of(ops)
    support = list(support_targets or [])
    return {"id": case_id, "question": question, "holdout": holdout, "expected_verdict": expected_verdict,
            "accept_targets": [t for t in targets if t not in support], "support_targets": support,
            "accept_questions": list(accept_questions or [question])}


def justified_cells(base: str, path: Path = JUSTIFIED) -> list[dict]:
    """바탕 하나의 정당한 지적 목록 칸: [{"id", "cells"}]."""
    out = []
    for it in json.loads(path.read_text(encoding="utf-8"))["items"]:
        if base not in it["designs"]:
            continue
        cells = it["cells_by_design"][base] if "cells_by_design" in it else it["cells"]
        out.append({"id": it["id"], "cells": list(cells)})
    return out


def variant_entry(fname_sha256: str, base: str, design_type: str, defects: list[dict]) -> dict:
    return {"sha256": fname_sha256, "base": base, "design_type": design_type,
            "kind": "defect" if defects else "clean", "defects": defects,
            "legit_changes": [{"targets": [t], "note": "결함 아님. 지적하면 오경보"} for t in LEGIT_ITEMS.get(base, [])],
            "justified": justified_cells(base)}


def validate_key(key: dict) -> list[str]:
    """정답표 형식 검사. 문제 목록(비면 통과)."""
    p = []
    if key.get("version") != VERSION:
        p.append("version")
    if [r[0] for r in key.get("priority", [])] != [r[0] for r in PRIORITY]:
        p.append("priority")
    variants = key.get("variants", {})
    seen: list[str] = []
    for fname, v in variants.items():
        where = fname
        for k in ("sha256", "base", "design_type", "kind", "defects", "legit_changes", "justified"):
            if k not in v:
                p.append(f"{where}: {k} 없음")
        if p and p[-1].startswith(where):
            continue
        if v["design_type"] not in TYPES:
            p.append(f"{where}: design_type")
        if len(v["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in v["sha256"]):
            p.append(f"{where}: sha256")
        if v["kind"] != ("defect" if v["defects"] else "clean"):
            p.append(f"{where}: kind")
        if len(v["defects"]) > 2:
            p.append(f"{where}: 결함 3개 이상")
        acc_all: list[str] = []
        for d in v["defects"]:
            for k in ("id", "question", "holdout", "expected_verdict", "accept_targets", "support_targets",
                      "accept_questions"):
                if k not in d:
                    p.append(f"{where}: {d.get('id')} {k} 없음")
            if any(k not in d for k in ("accept_targets", "support_targets", "accept_questions", "question")):
                continue
            seen.append(d["id"])
            if not d["accept_targets"]:
                p.append(f"{where}: {d['id']} accept_targets 비어 있음")
            if set(d["accept_targets"]) & set(d["support_targets"]):
                p.append(f"{where}: {d['id']} accept·support 겹침")
            if d["question"] not in d["accept_questions"] or not set(d["accept_questions"]) <= QUESTIONS:
                p.append(f"{where}: {d['id']} accept_questions")
            if d.get("expected_verdict") not in VERDICTS:
                p.append(f"{where}: {d['id']} expected_verdict")
            acc_all += d["accept_targets"]
        if len(acc_all) != len(set(acc_all)):
            p.append(f"{where}: 한 변형 안 결함의 지목 항목 겹침")
    if len(seen) != len(set(seen)):
        p.append("사례가 두 번 이상 배치됨")
    return p
