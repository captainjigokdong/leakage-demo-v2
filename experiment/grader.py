"""채점기 v2 (5단계에 고정, `experiment/scoring_rules.md`를 코드로 옮긴 것).

제출 파일 `findings.json` → (지목 칸, kind, 문제 종류) 목록 → 정답표와 대조 → 탐지 · 중립 · 오경보.
판정은 모두 규칙 기반이다. LLM은 쓰지 않는다 (CLAUDE.md 절대 규칙 7).
v1 채점기(보고서 끝 ```findings 블록, 문장으로 점검 불가 판정)는 v1 저장소에 기록으로 남아 있다.

맹검: 채점 단계(`grade_*`)는 보고서 id · 변형 파일 · 제출 파일 내용만 받는다. 조건(가/나) 표시는
채점이 끝난 뒤 `summarize`에서만 붙인다. 조건 칸이 섞인 기록은 채점하지 않고 멈춘다.

사용 (7단계):
    python -m experiment.grader grade runs/findings --checker runs/checker --out results/grades.json
    python -m experiment.grader summarize results/grades.json runs/conditions.json --out results/summary.json
암호는 tools.seal과 같은 방식(환경 변수 SEAL_PASSWORD 또는 터미널 입력)으로만 받는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
VARIANT_DIR = ROOT / "designs" / "variants"
ANSWER_KEY = ROOT / "sealed" / "answer_key.enc"
VARIANT_LOG = ROOT / "docs" / "variants_v2.md"

FINDING_KINDS = ("문제", "가정", "점검 불가")   # 제출 파일의 kind 칸 (지시문과 같음)
QS = ["Q1", "Q2", "Q3", "Q4", "Q5", "Q7"]       # 보조 분석의 문제 종류 (Q6는 기록만)
BOOTSTRAP_N = 10_000
BOOTSTRAP_SEED = 20261006
CONDITION_FIELDS = {"condition", "arm", "조건", "skill"}

# 실행 규칙 (docs/success_criteria_v2.md에 잠금. 6단계 실행기가 이 값을 쓴다)
MAX_TURNS = 60          # 실행당 턴 수 상한, 두 조건 같음
MAX_TURNS_RETRY = 5     # 형식 재제출 요청 1회의 턴 수 상한
FORMAT_RETRIES = 1      # 형식 검사 실패(파일 없음 포함) 때 재제출 요청 횟수

# 채점하지 않는 최상위 칸: 지목해도 탐지 가능하지만 오경보로 세지 않는다 (scoring_rules.md 2절)
NOT_GRADED_HEADS = {"attempts", "design_id", "design_type", "notes"}

# 참고값용 칸 (판정에는 쓰지 않음). docs/known_issues_v2.md K1·K5, 4a 검수 지적·점검기 출력으로 확정.
K_CELLS = {
    "K1": {"bases": ["readmit_b"], "cells": ["features.n_clinic_365d"]},
    "K5": {"bases": ["readmit_a", "readmit_b", "readmit_c", "readmit_d"], "cells": ["cohort.rows_per_unit"]},
}
# 깨끗한 설계서에서 점검기가 "가정"을 내는 칸 (tests/test_grader.py가 점검기 출력과 같은지 확인한다)
_ALL_ASSUMPTION = ["split.key", "model.tuning.cv_key"]
_FIXED_ASSUMPTION = _ALL_ASSUMPTION + ["cohort.rows_per_unit", "outcome.ascertainment.scope.sites"]
ASSUMPTION_CELLS = {**{b: _ALL_ASSUMPTION for b in ("aki_a", "aki_b", "aki_c", "aki_d")},
                    **{b: _FIXED_ASSUMPTION for b in ("readmit_a", "readmit_b", "readmit_c", "readmit_d")}}
# 정답 칸이 깨끗한 설계서의 가정 칸·정당한 지적 목록 칸과 같은 공개 사례 (H1a 참고값에서 뺀다)
ASSUMPTION_OVERLAP_CASES = ("E05", "E06", "E07", "E18")
# 4b에서 서술을 고친 후보 (뽑혔으면 H2a·H2b를 뺀 값과 함께 보고)
NARRATIVE_FIXED_CASES = ("C18", "C27", "C30")

# ---------------------------------------------------------------- 문제 종류 핵심어 사전 (보조 분석 전용)
# 문제 설명(problem)을 소문자로 바꾼 뒤 부분 문자열로 찾는다. 한 설명이 여러 종류에 걸릴 수 있다.
# 보조 분석(항목 + 종류)에만 쓰며 판정에는 쓰지 않는다. 검증 세트 (A) 개발 절반으로만 보강한다.

KEYWORDS: dict[str, list[str]] = {
    "Q1": [  # 가용 시점
        "가용 시점", "확인 가능 시각", "확인 가능한 시각", "알려진 시각", "알려지는 시각",
        "예측 시점 이후", "예측 시점 뒤", "예측 시점보다 늦", "예측 시점에는 알", "예측 시점에 알",
        "예측 시점에 아직", "예측 시점에서 알", "예측 시각 이후", "예측 시각 뒤",
        "tp 이후", "tp 뒤", "tp보다 늦", "tp 시점에는 알", "tp에는 알", "tp에 아직", "tp에 알",
        "기준 시점(", "뒤일 수 있다", "데이터에서 늦게 알려진",
        "미래 정보", "미래의 정보", "미래 데이터", "미래 시점", "아직 알려지지", "아직 알 수 없",
        "아직 나오지", "아직 보고되지", "보고 시각", "보고되기 전", "보고 지연",
        "채취 시각", "채취 시점", "퇴원 시점에야", "퇴원 후에야", "퇴원 때 확정", "퇴원 시 확정",
        "입원 전체 기간", "입원 전체의", "입원 기간 전체", "시간적 누수", "시점 누수", "시간 누수",
        "look-ahead", "lookahead", "look ahead", "future information", "future data", "future value",
        "information from the future", "leakage from the future", "not available at prediction",
        "not yet available", "unavailable at prediction", "not available at the time",
        "available only after", "only known after", "known only at", "after the prediction time",
        "after prediction time", "after the prediction point", "after the landmark",
        "temporal leakage", "time leakage", "report time", "reported after", "result time",
        "collection time", "collect_time", "whole admission", "entire admission", "entire stay",
        "퇴원 후에 코딩", "퇴원 후 코딩", "퇴원 뒤에 코딩", "코딩 지연", "코딩되어",
        "예측 시점에 사용할 수 없", "예측 시점에는 사용할 수 없", "예측 시점에 쓸 수 없", "예측 시점에는 쓸 수 없",
        "예측 시점에 이용할 수 없", "예측 시점에 존재하지", "예측 시점에는 존재하지",
        "coded after discharge", "coding delay", "not usable at prediction", "cannot be used at prediction",
    ],
    "Q2": [  # 독립 단위
        "독립 단위", "분할 단위", "분할 키", "분할 묶음", "그룹 분할", "묶음 분할",
        "같은 환자", "동일 환자", "같은 가족", "동일 가족", "가족 단위", "환자 단위",
        "학습과 평가에 함께", "학습·평가에", "학습/평가에", "학습과 평가 양쪽", "학습과 평가에 나뉘",
        "학습과 테스트", "학습 세트와 테스트", "서로 독립이 아", "독립적이지 않", "독립이 아니",
        "행 단위 분할", "행 단위로 분할", "입원 단위 분할", "입원 단위로 분할", "무작위 행 분할",
        "교차검증 키", "교차 검증 키", "교차검증 묶음",
        "same patient", "same family", "patient-level split", "patient level split", "family-level",
        "group split", "grouped split", "group k-fold", "groupkfold", "group-aware",
        "independent unit", "unit of independence", "not independent", "non-independent",
        "split key", "split unit", "split by row", "row-level split", "admission-level split",
        "both train and test", "both training and test", "train and test sets", "across splits",
        "cv key", "cross-validation key", "patient overlap", "subject overlap",
        "독립성이 깨", "독립성을 깨", "독립성 위반", "독립성을 위반", "독립성을 해", "독립성이 없",
        "학습과 검증에", "학습과 검증 세트", "학습·검증", "학습/검증", "가족 구성원이",
        "행 단위로 나누", "행 단위로 분할", "한 사람의 데이터", "같은 사람", "동일 인물", "양쪽에 섞", "양쪽에 들어",
        "independence", "same person", "same individual", "both sides of the split",
    ],
    "Q3": [  # 적합 범위
        "적합 범위", "fit_scope", "fit scope", "범위에서 적합",
        "전체 데이터로 적합", "전체 데이터에서 적합", "전체 데이터로 추정", "전체 데이터에서 추정",
        "전체 데이터를 사용해 추정", "전체 데이터로 계산", "전체 데이터에서 계산", "전체 데이터로 학습",
        "전체 데이터에서 선택", "전체 데이터로 선택", "분할 전에", "분할 이전에", "분할하기 전",
        "평가 부분의 정보", "평가 데이터의 정보", "테스트 데이터의 정보", "평가 데이터 정보",
        "학습 부분에서만", "학습 데이터에서만", "전처리 누수", "특징 선택 누수", "변수 선택 누수",
        "fit on the full", "fit on all", "fitted on all", "fit on the entire", "fitted on the entire",
        "fit on the whole", "fitted on the whole", "entire dataset", "whole dataset", "full dataset",
        "before splitting", "before the split", "prior to splitting", "test set information",
        "information from the test", "training data only", "training set only", "train only",
        "train_fold", "preprocessing leakage", "feature selection leakage", "data snooping",
        "전체 표본에서", "전체 표본으로", "전체 표본을", "전체 자료에서", "전체 자료로",
        "시험 세트 정보", "시험 세트의 정보", "검증 세트 정보", "검증 세트의 정보", "테스트 세트 정보",
        "테스트 세트의 정보", "평가 세트 정보", "평가 세트의 정보", "미리 본", "엿보",
        "peek", "test data leak into", "whole sample", "full sample", "entire sample",
    ],
    "Q4": [  # 결과 출처
        "결과 출처", "결과 정의", "결과를 정한", "결과를 정의", "결과를 정하는", "결과와 같은 행",
        "결과 창", "결과 기간", "결과와 겹", "대리 변수", "대리변수", "결과의 대리", "결과를 반영",
        "결과 정보", "결과가 섞", "결과 누수", "레이블 누수", "라벨 누수", "타깃 누수", "타겟 누수",
        "결과 자체", "결과를 직접", "결과를 암시", "결과를 그대로",
        "target leakage", "label leakage", "outcome leakage", "proxy", "outcome definition",
        "defines the outcome", "define the outcome", "outcome window", "encodes the outcome",
        "reflects the outcome", "same row as the outcome", "derived from the outcome",
        "consequence of the outcome", "downstream of the outcome",
        "예측하려는 결과", "예측할 결과", "예측하는 결과", "예측 대상인 결과", "예측 대상 자체", "결과 그 자체",
        "outcome we are predicting", "outcome being predicted", "is the outcome itself", "is itself the outcome",
    ],
    "Q5": [  # 선택 시점
        "선택 시점", "선택 편향", "불멸 시간", "생존 편향", "코호트 선택 시점", "대상자 선택 시점",
        "기준 시점 이후", "기준 시점 뒤", "immortal time", "selection bias", "survivor bias",
        "survivorship", "selection time", "conditioning on the future",
        "conditioned on the future",
    ],
    "Q7": [  # 결과 확인 균질성
        "확인 균질성", "확인 강도", "측정 강도", "측정 빈도", "측정 횟수가 다", "검사 빈도",
        "검사 횟수가 다", "감시 편향", "탐지 편향", "확인 편향", "결과 확인", "층별로 다루",
        "ascertainment", "surveillance bias", "detection bias", "verification bias",
        "measurement frequency", "testing frequency", "monitoring intensity", "measured more often",
        "tested more often", "differential measurement", "differential testing", "informative observation",
    ],
    "Q6": [  # 다중 시도 (기록만)
        "다중 시도", "다중 비교", "다중 검정", "시도 횟수", "multiple testing", "multiple comparison",
        "number of attempts", "p-hacking", "forking paths",
    ],
}

_LABEL = re.compile(r"(?<![a-z0-9])q([1-7])(?![0-9])")
_RANGE = re.compile(r"(?<![a-z0-9])q([1-7])\s*[~\-–]\s*q([1-7])(?![0-9])")


def classify(problem: str, path: str | None = None) -> frozenset:
    """문제 설명 → 문제 종류 집합 (보조 분석 전용). 빈 집합이면 종류 불명.
    칸이 포함·제외 기준이면 시점 문제(Q1)를 선택 시점(Q5)으로도 본다. Q6는 기록만 하므로 결과에서 뺀다."""
    t = problem.lower().replace("tₚ", "tp").replace("t_p", "tp")
    qs = {f"Q{m}" for m in _LABEL.findall(t)}
    for a, b in _RANGE.findall(t):
        qs |= {f"Q{i}" for i in range(int(a), int(b) + 1)}
    qs |= {q for q, words in KEYWORDS.items() if any(w in t for w in words)}
    if path and path.startswith("cohort.") and "Q1" in qs:
        qs.add("Q5")
    qs.discard("Q6")
    return frozenset(qs)


# ---------------------------------------------------------------- 설계서 경로

LIST_SECTIONS = {"features": "features", "inclusion": "cohort.inclusion",
                 "exclusion": "cohort.exclusion", "preprocessing": "preprocessing"}


def _names(design: dict) -> dict[str, list[str]]:
    c = design.get("cohort", {})
    return {"features": [f["name"] for f in design.get("features", [])],
            "inclusion": [x["name"] for x in c.get("inclusion", [])],
            "exclusion": [x["name"] for x in c.get("exclusion", [])],
            "preprocessing": [p["name"] for p in design.get("preprocessing", [])]}


def _parts(s: str) -> list[str]:
    s = s.strip().strip("`'\" ")
    s = re.sub(r"\[\s*(?:name\s*=\s*)?['\"]?([^\]'\"]+?)['\"]?\s*\]", r".\1", s)
    s = s.replace(":", ".").replace("/", ".")
    return [p.strip() for p in s.split(".") if p.strip()]


def _walk(obj, parts: list[str]) -> list[str]:
    """obj 안에서 실제로 있는 가장 깊은 앞부분 (이름이 있는 목록은 name으로 찾는다)."""
    done = []
    for p in parts:
        if isinstance(obj, dict) and p in obj:
            obj = obj[p]
        elif isinstance(obj, list) and (hit := [x for x in obj if isinstance(x, dict) and x.get("name") == p]):
            obj = hit[0]
        else:
            break
        done.append(p)
    return done


def _list_item(section: str, rest: list[str], design: dict) -> str | None:
    """목록 칸(features 등): 이름이 없으면 묶음, 없는 이름이면 None, 있으면 그 항목 + 있는 하위 칸."""
    names = _names(design)[section]
    base = LIST_SECTIONS[section]
    if not rest:
        return base
    if rest[0] not in names:
        return None
    items = design.get(section, []) if section in ("features", "preprocessing") else design["cohort"][section]
    item = next(x for x in items if x.get("name") == rest[0])
    return ".".join([base, rest[0]] + _walk(item, rest[1:]))


def canon(parts: list[str], design: dict) -> str | None:
    """점 경로 조각 → 설계서의 정규 경로. 설계서에 없는 경로면 None (scoring_rules.md 2절)."""
    if not parts:
        return None
    head, rest = parts[0], parts[1:]
    if head == "cohort":
        if not rest:
            return "cohort"
        if rest[0] in ("inclusion", "exclusion"):
            return _list_item(rest[0], rest[1:], design)
        if rest[0] not in design.get("cohort", {}):
            return None
        return ".".join(["cohort"] + _walk(design["cohort"], rest))
    if head in LIST_SECTIONS:
        return _list_item(head, rest, design)
    if head == "ascertainment":
        head, rest = "outcome", ["ascertainment"] + rest
    if head == "cv_key":
        head, rest = "model", ["tuning", "cv_key"] + rest
    if head == "outcome" and rest and rest[0] == design.get("outcome", {}).get("name"):
        rest = rest[1:]
    if head in design:
        return ".".join([head] + _walk(design[head], rest))
    hits = [s for s, ns in _names(design).items() if head in ns]
    if len(hits) == 1:
        return _list_item(hits[0], [head] + rest, design)
    return None


_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:(?:\.|:)[A-Za-z0-9_]+|\[[^\]]*\])*")


def resolve(target: str, design: dict) -> str | None:
    """제출의 target 문자열 → 설계서 정규 경로. 하나로 정할 수 없으면 None(대상 불명)."""
    whole = canon(_parts(target), design)
    if whole is not None:
        return whole
    toks = _TOKEN.findall(target)
    qualified = [t for t in toks if re.search(r"[.:\[]", t)]
    for group in (qualified, toks):   # 점 경로로 적은 것을 먼저 본다
        found = {c for tok in group if (c := canon(_parts(tok), design)) is not None}
        if found:
            return found.pop() if len(found) == 1 else None
    return None


def key_path(t: str, design: dict) -> str:
    """정답표·목록의 칸(inject.targets_of 표기, [name=] 표기) → 정규 경로. 'cohort'·'model'은 묶음 그대로."""
    p = _parts(t)
    if p in (["cohort"], ["model"]):
        return p[0]
    return canon(p, design) or ".".join(p)


def is_bundle(path: str, design: dict) -> bool:
    """최상위 묶음 전체 (features, cohort, outcome, model, split, tp 등 dict·list인 최상위 칸, cohort.inclusion·exclusion).
    split_unit처럼 값 하나인 최상위 칸은 묶음이 아니다."""
    p = path.split(".")
    if len(p) == 1:
        return isinstance(design.get(p[0]), (dict, list)) or p[0] == "cohort"
    return p[0] == "cohort" and len(p) == 2 and p[1] in ("inclusion", "exclusion")


def item_of(path: str) -> str:
    """오경보 중복 제거 단위: 목록 항목(features.이름 등) 또는 최상위 칸 아래 첫 칸(outcome.window 등)."""
    p = path.split(".")
    if p[0] == "cohort" and len(p) >= 3 and p[1] in ("inclusion", "exclusion"):
        return ".".join(p[:3])
    return ".".join(p[:2])


def graded(path: str) -> bool:
    return path.split(".")[0] not in NOT_GRADED_HEADS


def _within(a: str, b: str) -> bool:
    return a == b or a.startswith(b + ".")


def _split_member(f: str) -> bool:
    return _within(f, "split") or f == "split_unit" or _within(f, "model.tuning.cv_key")


def matches(f: str, t: str, design: dict, strict: bool = False) -> bool:
    """지적 경로 f가 정답·목록 칸 t를 가리키는가 (scoring_rules.md 2절).
    - 같거나 더 좁으면(f가 t 안) 일치.
    - 더 넓으면(t가 f 안) 관대판만 일치, 단 f가 최상위 묶음 전체이면 불인정. 엄격판은 불인정.
    - 분할 묶음: 칸이 `split` 전체이면 split.*, split_unit, model.tuning.cv_key 지적이 일치.
    - 하위 집단 예외: 칸이 outcome.ascertainment(또는 그 하위)이면 cohort.subgroups 지적도 일치."""
    if _within(f, t):
        return True
    if t == "split" and _split_member(f):
        return True
    if _within(t, "outcome.ascertainment") and _within(f, "cohort.subgroups"):
        return True
    return (not strict) and _within(t, f) and not is_bundle(f, design)


# ---------------------------------------------------------------- 제출 파일

def validate_findings(text: str | None) -> list[str]:
    """형식 검사. 빈 목록이면 통과. 실패면 재제출 요청 1회 대상 (파일 없음도 실패)."""
    if text is None:
        return ["파일 없음"]
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return ["JSON 오류"]
    if not isinstance(data, list):
        return ["목록 아님"]
    bad = []
    for i, x in enumerate(data):
        if not isinstance(x, dict):
            bad.append(f"{i}: 객체 아님")
            continue
        tg = x.get("target")
        if not (isinstance(tg, str) and tg.strip()) and not (isinstance(tg, list) and tg and all(isinstance(s, str) and s.strip() for s in tg)):
            bad.append(f"{i}: target")
        if x.get("kind") not in FINDING_KINDS:
            bad.append(f"{i}: kind")
        if not isinstance(x.get("problem"), str):
            bad.append(f"{i}: problem")
    return bad


def parse_findings(text: str | None) -> tuple[list[dict], str | None, int]:
    """제출 파일 내용 → (지적 목록, 형식 오류, 버린 항목 수).
    파일 없음·JSON 오류·목록 아님이면 지적 0개. 칸이 틀린 항목은 버리고 수만 센다. target이 목록이면 따로 지적."""
    if text is None:
        return [], "파일 없음", 0
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return [], "JSON 오류", 0
    if not isinstance(data, list):
        return [], "목록 아님", 0
    out, bad = [], 0
    for i, x in enumerate(data):
        if validate_findings(json.dumps([x], ensure_ascii=False)):
            bad += 1
            continue
        tgs = [x["target"]] if isinstance(x["target"], str) else x["target"]
        out += [{"target": s, "kind": x["kind"], "problem": x["problem"]} for s in tgs]
    return out, None, bad


# ---------------------------------------------------------------- 채점

@dataclass
class Entry:
    target: str
    kind: str                     # 문제 | 가정 | 점검 불가
    problem: str
    path: str | None = None
    qs: frozenset = frozenset()


COUNT_KEYS = ("n_problem", "n_assumption", "n_unable", "n_unresolved", "n_too_broad", "n_not_graded",
              "n_support", "n_justified", "n_justified_strict", "n_unknown_kind",
              "n_assumption_cell_problem", "n_defect_cell_assumption", "n_defect_cell_unable")


@dataclass
class Grade:
    report_id: str
    variant: str
    source: str                                  # "report" | "checker"
    format_error: str | None = None
    n_entries: int = 0
    n_malformed: int = 0
    counts: dict = field(default_factory=lambda: dict.fromkeys(COUNT_KEYS, 0))
    defects: list[dict] = field(default_factory=list)
    false_alarms: list[str] = field(default_factory=list)          # 관대판, 항목 단위 중복 없음
    false_alarms_strict: list[str] = field(default_factory=list)   # 엄격판 (넓게 적은 지적은 목록·정답 불인정)
    false_alarms_no_k: list[str] = field(default_factory=list)     # K1·K5 칸 오경보를 뺀 참고값
    legit_flagged: list[str] = field(default_factory=list)         # 오경보 중 legit_changes 칸

    def to_dict(self) -> dict:
        return asdict(self)


def _check_blind(rec: dict) -> None:
    bad = CONDITION_FIELDS & set(rec)
    if bad:
        raise ValueError(f"채점 입력에 조건 칸 {sorted(bad)}이 있다. 조건은 채점 뒤에만 붙인다.")


def _accept_keys(d: dict, design: dict, strict: bool) -> list[str]:
    ks = [key_path(t, design) for t in d["accept_targets"]]
    if strict and len(ks) > 1:   # 엄격판: 다른 칸이 있으면 묶음 전체(cohort·model) 칸은 뺀다
        ks = [k for k in ks if k not in ("cohort", "model")] or ks
    return ks


def _any(f: str, keys: list[str], design: dict, strict: bool = False) -> bool:
    return any(matches(f, k, design, strict) for k in keys)


def _score(g: Grade, entries: list[Entry], design: dict, key_entry: dict) -> Grade:
    base = key_entry.get("base")
    defects = key_entry["defects"]
    acc = [_accept_keys(d, design, False) for d in defects]
    acc_s = [_accept_keys(d, design, True) for d in defects]
    sup = [key_path(t, design) for d in defects for t in d.get("support_targets", [])]
    just = [key_path(c, design) for j in key_entry.get("justified", []) for c in j["cells"]]
    legit = [key_path(t, design) for lc in key_entry.get("legit_changes", []) for t in lc["targets"]]
    kcells = [c for k in K_CELLS.values() if base in k["bases"] for c in k["cells"]]
    assume = ASSUMPTION_CELLS.get(base, [])
    c = g.counts
    hit = [dict(pri=[], sec=[], pri_s=[], sec_s=[], pri_j=[]) for _ in defects]
    fa, fa_s, fa_k, lg = [], [], [], []

    def add(lst, f):
        if item_of(f) not in lst:
            lst.append(item_of(f))

    for e in entries:
        f = e.path
        if e.kind == "가정":
            c["n_assumption"] += 1
        elif e.kind == "점검 불가":
            c["n_unable"] += 1
        else:
            c["n_problem"] += 1
        if f is None:
            c["n_unresolved"] += 1
            continue
        on_defect = [i for i in range(len(defects)) if _any(f, acc[i], design)]
        if e.kind != "문제":
            if on_defect:
                c["n_defect_cell_assumption" if e.kind == "가정" else "n_defect_cell_unable"] += 1
            continue
        if not e.qs:
            c["n_unknown_kind"] += 1
        if _any(f, assume, design):
            c["n_assumption_cell_problem"] += 1
        in_just, in_just_s = _any(f, just, design), _any(f, just, design, True)
        for i, d in enumerate(defects):
            sec_ok = bool(e.qs & set(d["accept_questions"]))
            if i in on_defect:
                hit[i]["pri"].append(True)
                hit[i]["sec"].append(sec_ok)
                if not in_just:
                    hit[i]["pri_j"].append(True)
            if _any(f, acc_s[i], design, True):
                hit[i]["pri_s"].append(True)
                hit[i]["sec_s"].append(sec_ok)
        # 관대판 분류 (우선순위: 결함 > support > 목록 > 묶음 > 채점 안 함 > legit·그 밖 = 오경보)
        if on_defect:
            pass
        elif _any(f, sup, design):
            c["n_support"] += 1
        elif in_just:
            c["n_justified"] += 1
        elif is_bundle(f, design):
            c["n_too_broad"] += 1
        elif not graded(f):
            c["n_not_graded"] += 1
        else:
            add(fa, f)
            if _any(f, legit, design):
                add(lg, f)
            if not _any(f, kcells, design):
                add(fa_k, f)
        # 엄격판 분류 (넓게 적은 지적은 정답·목록·support에 맞지 않음)
        if any(_any(f, a, design, True) for a in acc_s) or _any(f, sup, design, True):
            pass
        elif in_just_s:
            c["n_justified_strict"] += 1
        elif is_bundle(f, design) or not graded(f):
            pass
        else:
            add(fa_s, f)
    for i, d in enumerate(defects):
        h = hit[i]
        g.defects.append({"id": d["id"], "question": d["question"], "holdout": d["holdout"],
                          "primary": bool(h["pri"]), "secondary": any(h["sec"]),
                          "primary_strict": bool(h["pri_s"]), "secondary_strict": any(h["sec_s"]),
                          "primary_justified_first": bool(h["pri_j"])})
    g.false_alarms, g.false_alarms_strict, g.false_alarms_no_k, g.legit_flagged = fa, fa_s, fa_k, lg
    return g


def grade_report(rec: dict, design: dict, key_entry: dict) -> Grade:
    """에이전트 제출 1개. rec = {"report_id", "variant", "findings": 파일 내용 문자열 또는 None(파일 없음)}."""
    _check_blind(rec)
    raw, err, bad = parse_findings(rec.get("findings"))
    g = Grade(rec["report_id"], rec["variant"], "report", err, len(raw), bad)
    entries = []
    for x in raw:
        p = resolve(x["target"], design)
        entries.append(Entry(x["target"], x["kind"], x["problem"], p, classify(x["problem"], p)))
    return _score(g, entries, design, key_entry)


def grade_checker(rec: dict, design: dict, key_entry: dict) -> Grade:
    """(가) 조건의 점검기 출력(JSON) 1개 → 점검기만으로 본 탐지율(2차 지표).
    rec = {"report_id", "variant", "exit_code", "checker": 점검기 --json 출력 또는 None}.
    차단·경고 → 문제(종류는 question 칸), 가정 → 가정, 점검 불가·출처 불명·확인 불가 → 점검 불가."""
    _check_blind(rec)
    g = Grade(rec["report_id"], rec["variant"], "checker")
    out = rec.get("checker")
    if rec.get("exit_code") == 2 or out is None:
        g.format_error = "점검 불가(종료 코드 2)"
        return _score(g, [], design, key_entry)
    entries = []
    for f in list(out.get("findings", [])) + list(out.get("assumptions", [])):
        v, q, reason = f["verdict"], f.get("question", ""), f.get("reason", "")
        if v == "가정":
            kind = "가정"
        elif v == "점검 불가" or q not in QS + ["Q6"] or reason.startswith("출처 불명") or "확인 불가" in reason:
            kind = "점검 불가" if v in ("차단", "경고", "점검 불가") else None
        elif v in ("차단", "경고"):
            kind = "문제"
        else:
            kind = None
        if kind is None:
            continue
        entries.append(Entry(f["target"], kind, reason, resolve(f["target"], design),
                             frozenset({q}) if q in QS else frozenset()))
    g.n_entries = len(entries)
    return _score(g, entries, design, key_entry)


# ---------------------------------------------------------------- 정답표 · 변형 파일

def load_answer_key(password: str, path: Path = ANSWER_KEY) -> dict:
    """7단계 전용. 정답표를 메모리에서만 복호화한다 (평문을 파일로 쓰지 않는다)."""
    from tools.seal import decrypt_bytes
    return json.loads(decrypt_bytes(path.read_bytes(), password))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def injection_log_hashes(path: Path = VARIANT_LOG) -> dict[str, str]:
    rows = re.findall(r"^\| (?:designs/variants/)?`?(design_\w+\.json)`? \| `([0-9a-f]{64})` \|", path.read_text(encoding="utf-8"), re.M)
    return dict(rows)


def verify_variants(key_variants: dict, variant_dir: Path = VARIANT_DIR, log: dict[str, str] | None = None) -> list[str]:
    """변형 파일 SHA-256을 정답표·변형 목록(docs/variants_v2.md)과 대조. 어긋난 항목 목록(빈 목록이면 일치)."""
    log = injection_log_hashes() if log is None else log
    bad = []
    files = {p.name for p in variant_dir.glob("design_*.json")}
    if files != set(key_variants):
        bad.append(f"파일 목록 불일치: {sorted(files ^ set(key_variants))}")
    for fname, entry in key_variants.items():
        if fname not in files:
            continue
        h = sha256_file(variant_dir / fname)
        if h != entry["sha256"]:
            bad.append(f"{fname}: 정답표 해시와 다름")
        if log.get(fname) != h:
            bad.append(f"{fname}: 변형 목록 해시와 다름")
    return bad


def load_design(fname: str, variant_dir: Path = VARIANT_DIR) -> dict:
    return json.loads((variant_dir / fname).read_text(encoding="utf-8"))


def grade_all(reports: list[dict], key_variants: dict, checker: list[dict] = (),
              designs: dict[str, dict] | None = None) -> list[dict]:
    """맹검 채점. 제출·점검기 기록 → Grade 사전 목록 (조건 없음)."""
    designs = designs if designs is not None else {}
    out = []
    for rec, fn in [(r, grade_report) for r in reports] + [(c, grade_checker) for c in checker]:
        v = rec["variant"]
        if v not in designs:
            designs[v] = load_design(v)
        out.append(fn(rec, designs[v], key_variants[v]).to_dict())
    return out


# ---------------------------------------------------------------- 요약 · 가설

def _rate(xs: list[bool]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _placements(grades: list[dict], keep=lambda d: True) -> list[dict]:
    return [{**d, "variant": g["variant"], "report_id": g["report_id"]}
            for g in grades for d in g["defects"] if keep(d)]


MEASURES = ("primary", "secondary", "primary_strict", "secondary_strict", "primary_justified_first")


def detection(grades: list[dict], keep=lambda d: True) -> dict:
    """배치-실행 단위 탐지율 (배치 × 실행을 모두 합쳐 셈)."""
    p = _placements(grades, keep)
    out = {"n": len(p)} | {m: _rate([d[m] for d in p]) for m in MEASURES}
    out["by_question"] = {q: {"n": len(x), "primary": _rate([d["primary"] for d in x]),
                              "secondary": _rate([d["secondary"] for d in x])}
                          for q in QS if (x := [d for d in p if d["question"] == q])}
    return out


FA_FIELDS = ("false_alarms", "false_alarms_strict", "false_alarms_no_k")


def false_alarms(grades: list[dict], key_variants: dict) -> dict:
    out = {}
    for label, clean in (("clean", True), ("defect", False)):
        gs = [g for g in grades if (not key_variants[g["variant"]]["defects"]) == clean]
        out[label] = {"reports": len(gs)}
        for f in FA_FIELDS:
            n = [len(g[f]) for g in gs]
            out[label][f] = {"total": sum(n), "mean_per_report": (sum(n) / len(n)) if n else None}
        out[label]["legit_total"] = sum(len(g["legit_flagged"]) for g in gs)
    return out


def _boot(units: list, fa, fb, n: int = BOOTSTRAP_N, seed: int = BOOTSTRAP_SEED) -> dict:
    """묶음(변형) 단위 짝지은 부트스트랩. fa·fb(unit) → (분자, 분모). 통계량 = Σ분자/Σ분모 (가) − (나)."""
    if not units:
        return {"diff": None, "ci95": None, "n_units": 0}
    na, da = map(np.array, zip(*[fa(u) for u in units]))
    nb, db = map(np.array, zip(*[fb(u) for u in units]))
    na, da, nb, db = (x.astype(float) for x in (na, da, nb, db))
    if da.sum() == 0 or db.sum() == 0:
        return {"diff": None, "ci95": None, "n_units": len(units)}
    est = na.sum() / da.sum() - nb.sum() / db.sum()
    idx = np.random.default_rng(seed).integers(0, len(units), size=(n, len(units)))
    sa, sda, sb, sdb = na[idx].sum(1), da[idx].sum(1), nb[idx].sum(1), db[idx].sum(1)
    ok = (sda > 0) & (sdb > 0)
    diffs = sa[ok] / sda[ok] - sb[ok] / sdb[ok]
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return {"diff": float(est), "ci95": [float(lo), float(hi)], "n_units": len(units),
            "n_boot": int(ok.sum()), "seed": seed}


def boot_detection_diff(ga: list[dict], gb: list[dict], measure: str = "primary", keep=lambda d: True) -> dict:
    """탐지율 차이 (가 − 나). 단위 = keep에 맞는 배치가 있는 결함 변형. 변형 안 배치·반복은 합쳐 센다."""
    units = sorted({g["variant"] for g in ga + gb if any(keep(d) for d in g["defects"])})

    def f(gs):
        return lambda v: (sum(d[measure] for g in gs if g["variant"] == v for d in g["defects"] if keep(d)),
                          sum(1 for g in gs if g["variant"] == v for d in g["defects"] if keep(d)))
    return _boot(units, f(ga), f(gb))


def boot_fa_diff(ga: list[dict], gb: list[dict], key_variants: dict, fa_field: str = "false_alarms") -> dict:
    """깨끗한 변형에서 보고서당 오경보 차이 (가 − 나). 단위 = 깨끗한 변형, 분모 = 보고서 수."""
    units = sorted({g["variant"] for g in ga + gb if not key_variants[g["variant"]]["defects"]})

    def f(gs):
        return lambda v: (sum(len(g[fa_field]) for g in gs if g["variant"] == v),
                          sum(1 for g in gs if g["variant"] == v))
    return _boot(units, f(ga), f(gb))


def boot_public_minus_holdout(gs: list[dict], measure: str = "primary", keep=lambda d: True) -> dict:
    """한 조건 안의 공개 − 보류 탐지율 (H2b). 단위 = 결함 변형 (공개·보류가 섞인 변형은 함께 뽑힌다)."""
    units = sorted({g["variant"] for g in gs if any(keep(d) for d in g["defects"])})
    pub = lambda v: (sum(d[measure] for g in gs if g["variant"] == v for d in g["defects"] if keep(d) and not d["holdout"]),
                     sum(1 for g in gs if g["variant"] == v for d in g["defects"] if keep(d) and not d["holdout"]))
    hol = lambda v: (sum(d[measure] for g in gs if g["variant"] == v for d in g["defects"] if keep(d) and d["holdout"]),
                     sum(1 for g in gs if g["variant"] == v for d in g["defects"] if keep(d) and d["holdout"]))
    return _boot(units, pub, hol)


def stability(grades: list[dict], measure: str = "primary") -> float | None:
    """같은 (변형, 결함)에 대한 반복 실행들이 모두 같은 판정인 비율."""
    groups: dict[tuple, list[bool]] = {}
    for d in _placements(grades):
        groups.setdefault((d["variant"], d["id"]), []).append(d[measure])
    multi = [v for v in groups.values() if len(v) > 1]
    return _rate([len(set(v)) == 1 for v in multi])


def _counts(gs: list[dict], meta: dict[str, dict]) -> dict:
    out = {k: sum(g["counts"][k] for g in gs) for k in COUNT_KEYS}
    out["n_malformed"] = sum(g["n_malformed"] for g in gs)
    out["format_errors"] = {e: sum(g["format_error"] == e for g in gs) for e in ("파일 없음", "JSON 오류", "목록 아님")}
    out["empty_list"] = sum(g["format_error"] is None and g["n_entries"] == 0 and g["n_malformed"] == 0 for g in gs)
    out["format_retries"] = sum(meta.get(g["report_id"], {}).get("format_retries", 0) for g in gs)
    out["turn_capped"] = sum(bool(meta.get(g["report_id"], {}).get("turn_capped")) for g in gs)
    return out


def _hyp(ga: list[dict], gb: list[dict], key_variants: dict, keep=lambda d: True, measure: str = "primary") -> dict:
    """H1a·H1b·H1c·H2a 판정과 H2b 기술 (docs/success_criteria_v2.md). keep으로 배치를 거른 참고값에도 같은 함수를 쓴다."""
    h1a = boot_detection_diff(ga, gb, measure, keep)
    clean_a = [g for g in ga if not key_variants[g["variant"]]["defects"]]
    fa_mean = (sum(len(g["false_alarms"]) for g in clean_a) / len(clean_a)) if clean_a else None
    h1c = boot_fa_diff(ga, gb, key_variants)
    hold = lambda d: keep(d) and d["holdout"]
    h2a = boot_detection_diff(ga, gb, measure, hold)
    return {
        "H1a": {**h1a, "met": h1a["ci95"] is not None and h1a["ci95"][0] > 0},
        "H1b": {"fa_clean_mean_ga": fa_mean, "reports": len(clean_a), "met": fa_mean is not None and fa_mean <= 1},
        "H1c": {**h1c, "met": h1c["ci95"] is not None and h1c["ci95"][1] < 0},
        "H2a": {**h2a, "met": h2a["ci95"] is not None and h2a["ci95"][0] > 0},
        "H2b": {"가": boot_public_minus_holdout(ga, measure, keep), "나": boot_public_minus_holdout(gb, measure, keep),
                "note": "기술만 (기준 없음)"},
    }


def summarize(grades: list[dict], conditions: dict[str, dict], key_variants: dict,
              near_zero: tuple = ()) -> dict:
    """채점 결과에 조건을 붙여 지표·가설을 계산한다 (docs/success_criteria_v2.md, docs/analysis_plan_v2.md).
    conditions[report_id] = {"condition": 가|나, "rep", "turn_capped", "format_retries"} (조건 파일).
    near_zero = 수치 차이가 0에 가까운 배치 [(변형, 사례 id)] (7단계에 봉인 기록에서 확인해 넣는다)."""
    reps = [g for g in grades if g["source"] == "report"]
    chk = [g for g in grades if g["source"] == "checker"]
    by = {c: [g for g in reps if conditions[g["report_id"]]["condition"] == c] for c in ("가", "나")}
    out: dict = {"conditions": {}, "n_reps": sorted({conditions[g["report_id"]].get("rep") for g in reps}, key=str)}
    for c, gs in by.items():
        out["conditions"][c] = {
            "reports": len(gs),
            "detection": {"all": detection(gs), "public": detection(gs, lambda d: not d["holdout"]),
                          "holdout": detection(gs, lambda d: d["holdout"])},
            "false_alarms": false_alarms(gs, key_variants),
            "counts": _counts(gs, conditions),
            "stability": {"primary": stability(gs, "primary"), "secondary": stability(gs, "secondary")},
        }
    ck = [g for g in chk if conditions[g["report_id"]]["condition"] == "가"]
    out["checker_only"] = {"runs": len(ck), "detection": detection(ck),
                           "holdout": detection(ck, lambda d: d["holdout"]),
                           "false_alarms": false_alarms(ck, key_variants), "counts": _counts(ck, {})}
    ga, gb = by["가"], by["나"]
    out["hypotheses"] = _hyp(ga, gb, key_variants)                       # 판정 (주 분석)
    out["secondary"] = _hyp(ga, gb, key_variants, measure="secondary")  # 판정에 쓰지 않음
    nz = {tuple(x) for x in near_zero}
    drawn_fixed = sorted({d["id"] for g in reps for d in g["defects"] if d["id"] in NARRATIVE_FIXED_CASES})
    capped = {rid for rid, m in conditions.items() if m.get("turn_capped")}
    nocap = lambda gs: [g for g in gs if g["report_id"] not in capped]
    ref = {
        "strict_breadth": _hyp(ga, gb, key_variants, measure="primary_strict"),
        "justified_first": _hyp(ga, gb, key_variants, measure="primary_justified_first"),
        "without_assumption_overlap_cases": _hyp(ga, gb, key_variants, lambda d: d["id"] not in ASSUMPTION_OVERLAP_CASES),
        "without_near_zero": None,
        "without_narrative_fixed": (_hyp(ga, gb, key_variants, lambda d: d["id"] not in NARRATIVE_FIXED_CASES)
                                    if drawn_fixed else None),
        "narrative_fixed_drawn": drawn_fixed,
        "without_turn_capped": _hyp(nocap(ga), nocap(gb), key_variants) if capped else None,
        "fa_strict": {"H1b": _fa_mean(ga, key_variants, "false_alarms_strict"),
                      "H1c": boot_fa_diff(ga, gb, key_variants, "false_alarms_strict")},
        "fa_without_k1_k5": {"H1b": _fa_mean(ga, key_variants, "false_alarms_no_k"),
                             "H1c": boot_fa_diff(ga, gb, key_variants, "false_alarms_no_k")},
    }
    if nz:
        keep_nz = {(g["variant"], d["id"]) for g in reps for d in g["defects"]} - nz
        ref["without_near_zero"] = _hyp(*[[{**g, "defects": [d for d in g["defects"] if (g["variant"], d["id"]) in keep_nz]}
                                            for g in x] for x in (ga, gb)], key_variants)
    out["reference"] = ref
    return out


def _fa_mean(gs: list[dict], key_variants: dict, fa_field: str) -> float | None:
    clean = [g for g in gs if not key_variants[g["variant"]]["defects"]]
    return (sum(len(g[fa_field]) for g in clean) / len(clean)) if clean else None


# ---------------------------------------------------------------- 명령행

def _read_dir(d: Path | None) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))] if d else []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grade", help="맹검 채점 (조건 파일을 읽지 않는다)")
    g.add_argument("reports", type=Path)
    g.add_argument("--checker", type=Path)
    g.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("summarize", help="채점 결과 + 조건 → 지표·가설")
    s.add_argument("grades", type=Path)
    s.add_argument("conditions", type=Path)
    s.add_argument("--near-zero", type=Path, help="수치 차이 0에 가까운 배치 [[변형, 사례 id], ...] (7단계)")
    s.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)

    from tools.seal import get_password
    key = load_answer_key(get_password())
    bad = verify_variants(key["variants"])
    if bad:
        raise SystemExit("변형 파일 해시 불일치:\n" + "\n".join(bad))
    if a.cmd == "grade":
        grades = grade_all(_read_dir(a.reports), key["variants"], _read_dir(a.checker))
        a.out.write_text(json.dumps(grades, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        grades = json.loads(a.grades.read_text(encoding="utf-8"))
        conds = json.loads(a.conditions.read_text(encoding="utf-8"))
        nz = json.loads(a.near_zero.read_text(encoding="utf-8")) if a.near_zero else ()
        summary = summarize(grades, conds, key["variants"], near_zero=nz)
        a.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
