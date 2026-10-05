"""점검기 시험 (v2 3단계).

깨끗한 설계서는 2b 시험용 기본 설계서(designs/prereview/), 공개 사례 18개는 2c 패치(designs/patches_v1_cases.py)를
그 위에 적용한다 (2026-10-04 사용자 승인 ②, D8). 점검 코드(leakcheck/)는 사례 ID를 모른다.
"""
import copy
import csv
import dataclasses
import json
import re
from pathlib import Path

import pytest

from designs.inject import apply_ops
from designs.patches_v1_cases import V1_CASE_PATCHES, load_test_bases
from leakcheck import rules
from leakcheck.checks import ASSUME, BLOCK, KIND, PASS, RECORD, UNABLE, WARN, run_checks
from leakcheck.design import DesignError
from tests.design_mutations import TRICKY_DYNAMIC

ROOT = Path(__file__).resolve().parent.parent
KINDS = {"동적": ["dynamic"], "고정": ["fixed"], "둘다": ["dynamic", "fixed"]}
TYPES = ["dynamic", "fixed"]

# 깨끗한 기본 설계서에서 나오는 판정은 조건 1 승인 표에 있는 것뿐이다 (2026-10-04 사용자 승인).
# 동적: D2(pending_at_tp) 차단, D5 경고, D3 경고, 결과 창이 추출 종료를 넘는데 not_applicable(검수 뒤 2026-10-05, O.end_of_data)
# 고정: D5 경고, D4 경고(전처리 단계마다)
CLEAN_PROBLEMS = {
    "dynamic": {("Q5", BLOCK, "outcome.pending_at_tp"), ("Q1", WARN, "split.method"),
                ("Q7", WARN, "data_source.death_source"), ("Q7", WARN, "outcome.censoring.end_of_data")},
    "fixed": {("Q1", WARN, "split.method"), ("Q3", WARN, "preprocessing.median_impute"),
              ("Q3", WARN, "preprocessing.one_hot"), ("Q3", WARN, "preprocessing.standardize")},
}
CLEAN_ASSUMPTIONS = {
    "dynamic": {("A.family_missing", "split.key"), ("A.family_missing", "model.tuning.cv_key")},
    "fixed": {("A.family_missing", "split.key"), ("A.family_missing", "model.tuning.cv_key"),
              ("A.episode_last", "cohort.rows_per_unit"), ("A.outside_sites", "outcome.ascertainment.scope.sites")},
}


def clean(t: str) -> dict:
    return copy.deepcopy(load_test_bases()[t])


def _problems(report):
    return {(f.question, f.verdict, f.target) for f in report.problems()}


def _added(d, t, tables=None):
    """기본 설계서에 없던 문제."""
    return _problems(run_checks(d, tables)) - CLEAN_PROBLEMS[t]


def _public_cases():
    with open(ROOT / "designs" / "error_catalog_public.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [pytest.param(r, t, id=f"{r['id']}-{t}") for r in rows for t in KINDS[r["design_types"]]]


def _inject(case_id: str, t: str) -> dict:
    d = apply_ops(clean(t), V1_CASE_PATCHES[case_id])
    d["design_id"] = f"{d['design_id']}+{case_id}"
    return d


# --- 깨끗한 설계 ---

@pytest.mark.parametrize("t", TYPES)
def test_clean_design_findings_are_the_approved_ones(t):
    r = run_checks(clean(t))
    assert _problems(r) == CLEAN_PROBLEMS[t], r.to_text()
    assert r.unable() == []
    assert {(a.rule, a.target) for a in r.assumptions} == CLEAN_ASSUMPTIONS[t]
    assert [f.question for f in r.findings if f.verdict == RECORD] == ["Q6"]


@pytest.mark.parametrize("t", TYPES)
def test_clean_design_with_data_adds_nothing(t, small_tables):
    r = run_checks(clean(t), small_tables)
    assert _problems(r) == CLEAN_PROBLEMS[t], r.to_text()
    assert r.unable() == []


def test_larger_group_crossing_is_data_warning(small_tables):
    """선언 단위(사람)보다 큰 묶음(가족)이 학습·평가에 나뉘면 데이터 단계에서 경고한다."""
    d = clean("fixed")
    d["split_unit"], d["split"]["key"] = "person", "person_id"
    d["split"].pop("fallback_key")
    d["model"]["tuning"].update(cv_key="person_id")
    d["model"]["tuning"].pop("fallback_key")
    assert not any(f.target == "split_unit" for f in run_checks(d).problems())
    w = [f for f in run_checks(d, small_tables).problems() if f.target == "split_unit"]
    assert len(w) == 1 and w[0].verdict == WARN and "family" in w[0].reason and re.search(r"\d+/\d+", w[0].reason)


# --- 공개 18개 사례 ---

@pytest.mark.parametrize("case,t", _public_cases())
def test_public_case_gets_expected_verdict(case, t):
    r = run_checks(_inject(case["id"], t))
    assert (case["question"], case["expected_verdict"]) in {(q, v) for q, v, _ in _problems(r)}, r.to_text()


@pytest.mark.parametrize("case,t", _public_cases())
def test_public_case_with_data(case, t, small_tables):
    r = run_checks(_inject(case["id"], t), small_tables)
    assert (case["question"], case["expected_verdict"]) in {(q, v) for q, v, _ in _problems(r)}, r.to_text()


# --- 수상해 보이지만 정당한 설계 ---

def _tricky(name):
    d = clean("dynamic")
    d["features"].append(copy.deepcopy(TRICKY_DYNAMIC[name]))
    return d


@pytest.mark.parametrize("name", list(TRICKY_DYNAMIC))
def test_suspicious_but_legitimate_feature_passes(name):
    assert _added(_tricky(name), "dynamic") == set()


def test_suspicious_but_legitimate_design_passes_with_data(small_tables):
    d = clean("dynamic")
    d["features"] += copy.deepcopy(list(TRICKY_DYNAMIC.values()))
    r = run_checks(d, small_tables)
    assert _problems(r) == CLEAN_PROBLEMS["dynamic"]
    assert "데이터" not in " ".join(f.reason for f in r.findings if f.question == "Q1" and f.verdict != PASS)


# --- 핵심 시연: 같은 규칙, 다른 tₚ ---

DISCHARGE_FEATURE = {"name": "discharge_status_this_admission", "source": "admissions", "column": "discharge_status",
                     "scope": "index_admission", "agg": "value"}
DX_FEATURE = {"name": "dx_ckd_this_admission", "source": "diagnoses", "scope": "index_admission",
              "filter": {"icd_code": ["N18"]}, "agg": "any"}


def _with(t, spec):
    d = clean(t)
    d["features"].append(copy.deepcopy(spec))
    return d


def test_core_demo_same_rule_blocks_dynamic_passes_fixed(small_tables):
    """퇴원 때 알려지는 값: 동적(tₚ = 입원 중)은 차단, 고정(tₚ = 퇴원)은 통과. 데이터에서도 같은 결론."""
    target = ("Q1", BLOCK, "features.discharge_status_this_admission")
    assert target in _added(_with("dynamic", DISCHARGE_FEATURE), "dynamic")
    assert _added(_with("fixed", DISCHARGE_FEATURE), "fixed") == set()
    assert target in _added(_with("dynamic", DISCHARGE_FEATURE), "dynamic", small_tables)
    assert _added(_with("fixed", DISCHARGE_FEATURE), "fixed", small_tables) == set()


def test_this_admission_dx_is_coded_after_discharge():
    """v2: 진단 코드는 코딩 완료 시각(퇴원 뒤)에 알려진다는 것이 데이터의 사실이다 → 두 유형 모두 차단."""
    for t in TYPES:
        assert ("Q1", BLOCK, "features.dx_ckd_this_admission") in _added(_with(t, DX_FEATURE), t)


def test_rule_table_lag_flips_verdict(monkeypatch):
    """규칙표 한 줄(채취→보고 지연 상한)을 바꾸면 판정이 바뀐다."""
    spec = {"name": "cr_collected_6h_before", "source": "labs", "filter": {"test": ["creatinine"]},
            "time_column": "collect_time", "window": {"start": "admit", "end": "tp-6h"}, "agg": "last"}
    assert _added(_with("dynamic", spec), "dynamic") == set()
    labs = rules.TABLES["labs"]
    slow = dataclasses.replace(labs.row_available, lag_from={"collect_time": 8.0})
    monkeypatch.setitem(rules.TABLES, "labs", dataclasses.replace(
        labs, row_available=slow, column_available={c: slow for c in labs.column_available}))
    assert ("Q1", BLOCK, "features.cr_collected_6h_before") in _added(_with("dynamic", spec), "dynamic")


# --- 개별 원리 ---

def test_q4_same_table_alone_is_not_blocked():
    """동적 AKI: 특징도 결과도 크레아티닌(labs)이지만 행·시간 구간이 겹치지 않으면 통과."""
    d = clean("dynamic")
    assert d["outcome"]["source"] == "labs"
    assert any(f.get("source") == "labs" and f.get("filter", {}).get("test") == ["creatinine"] for f in d["features"])
    assert [f for f in run_checks(d).findings if f.question == "Q4"][0].verdict == PASS


def test_q4_window_overlapping_outcome_window_blocks():
    d = _with("dynamic", {"name": "cr_next_24h", "source": "labs", "filter": {"test": ["creatinine"]},
                          "time_column": "report_time", "window": {"start": "tp", "end": "tp+24h"}, "agg": "max"})
    found = {(q, v) for q, v, tg in _added(d, "dynamic") if "cr_next_24h" in tg}
    assert ("Q4", BLOCK) in found and ("Q1", BLOCK) in found


def test_q4_outcome_window_reuse_from_other_table_blocks():
    d = _with("dynamic", {"name": "orders_in_outcome_window", "source": "orders",
                          "filter": {"order_type": ["chest_xray"]}, "time_column": "order_time",
                          "window": {"start": "tp", "end": "tp+48h"}, "agg": "count"})
    assert ("Q4", BLOCK, "features.orders_in_outcome_window") in _added(d, "dynamic")


def test_unknown_provenance_feature_is_unable():
    d = clean("dynamic")
    d["features"].append({"name": "risk_score", "description": "노트북에서 계산"})
    d["features"].append({"name": "cr_slope", "source": "labs", "made_by": "pandas 직접 계산"})
    r = run_checks(d)
    unk = [f for f in r.findings if f.question == "Q1~Q3"]
    assert {f.target for f in unk} == {"features.risk_score", "features.cr_slope"}
    assert all(f.verdict == UNABLE and "Q1~Q3 확인 불가" in f.reason for f in unk)
    assert all(f.to_dict()["kind"] == "점검 불가" for f in unk)


def test_q7_threshold_is_fixed_at_two():
    assert rules.Q7_RATIO_THRESHOLD == 2.0


def test_q7_restricted_cohort_passes():
    d = clean("dynamic")
    d["outcome"].pop("ascertainment")
    d["cohort"]["subgroups"] = []
    assert ("Q7", WARN, "outcome.ascertainment.by_stratum") in _problems(run_checks(d))
    d["cohort"]["inclusion"].append({"name": "icu_only", "source": "admissions", "column": "unit",
                                     "agg": "value", "op": "==", "value": "ICU"})
    assert ("Q7", WARN, "outcome.ascertainment.by_stratum") not in _problems(run_checks(d))


def test_q3_missing_fit_scope_blocks_and_stateless_passes():
    d = clean("fixed")
    d["preprocessing"].append({"name": "log_cr", "kind": "transform", "stateless": True})
    assert _added(d, "fixed") == set()
    d["preprocessing"].append({"name": "pca", "kind": "reduce"})
    assert ("Q3", BLOCK, "preprocessing.pca") in _added(d, "fixed")


def test_q3_fit_scope_anywhere_in_design_is_checked():
    d = clean("fixed")
    d["model"]["tuning"]["fit_scope"] = "train+test"
    assert ("Q3", BLOCK) in {(q, v) for q, v, _ in _added(d, "fixed")}


def test_row_level_split_method_blocks_even_with_group_key():
    d = clean("dynamic")
    d["split"]["method"] = "random_rows"
    assert ("Q2", BLOCK, "split.key") in _added(d, "dynamic")


def test_unit_finer_than_entity_blocks():
    d = clean("fixed")
    d["split_unit"], d["split"]["key"] = "admission", "admission_id"
    assert ("Q2", BLOCK, "split_unit") in _added(d, "fixed")


def test_unknown_source_is_reported_not_guessed():
    d = _with("dynamic", {"name": "note_count", "source": "icu_notes", "agg": "count"})
    f = [f for f in run_checks(d).findings if f.target == "features.note_count"]
    assert f and f[0].verdict == UNABLE and "규칙표에 없어 확인 불가" in f[0].reason


def test_unknown_source_or_column_with_data_is_reported(small_tables):
    d = _with("dynamic", {"name": "cr_flag", "source": "labs", "column": "flag", "agg": "last"})
    d["cohort"]["exclusion"].append({"name": "on_pressors", "source": "icu_notes", "agg": "any",
                                     "op": "==", "value": True})
    r = run_checks(d, small_tables)
    got = {f.target: (f.question, f.verdict) for f in r.findings if "확인 불가" in f.reason}
    assert got == {"features.cr_flag": ("Q1~Q3", UNABLE), "cohort.exclusion.on_pressors": ("Q5", UNABLE)}


def test_invalid_design_raises():
    d = clean("dynamic")
    d["features"][0]["window"] = {"end": "tomorrow"}
    with pytest.raises(DesignError):
        run_checks(d)
    d = clean("fixed")
    del d["split"]
    with pytest.raises(DesignError):
        run_checks(d)


def test_output_is_structured_json():
    r = run_checks(_inject("E02", "fixed"))
    out = json.loads(r.to_json())
    assert out["blocked"] is True
    base = {"question", "verdict", "target", "reason", "rule", "basis"}
    for f in out["findings"]:
        assert set(f) == (base | {"kind"} if f["verdict"] in KIND else base), f
        if f["verdict"] in KIND:
            assert f["kind"] == KIND[f["verdict"]]
    assert out["assumptions"] and all(a["verdict"] == ASSUME and a["kind"] == "가정" for a in out["assumptions"])
    assert set(KIND.values()) == {"문제", "가정", "점검 불가"}
    assert all(f["basis"].startswith("규칙 ") for f in out["findings"] if f["verdict"] in (BLOCK, WARN))


def test_check_code_knows_no_case_ids():
    """점검은 사례 목록이 아니라 원리로 구현한다: 점검·스킬 코드에 사례 ID가 없어야 한다."""
    pat = re.compile(r"\bE\d{2}\b")
    for p in list((ROOT / "leakcheck").rglob("*.py")) + list((ROOT / "skill_src").rglob("*")):
        if p.is_file():
            assert not pat.search(p.read_text(encoding="utf-8")), p
