"""원리 시험 (v2 3단계): 새로 만든 판정 경로마다 공개 사례 18개에 없는 예시로 확인한다.

각 경로마다 두 설계를 만든다.
- bad:  그 원리를 어기는 설계 → 기대한 판정(또는 가정)이 나온다
- good: 같은 설계를 지금 형식(161칸) 안의 올바른 표현으로 고친 것 → 그 판정이 사라진다 (조건 1: 피할 수 있어야 한다)
기본 설계서는 2b 시험용 기본 설계서(designs/prereview/)이고, 그 설계서에 원래 있던 판정은 빼고 본다.
"""
from __future__ import annotations

import copy

import pytest

from designs.patches_v1_cases import load_test_bases
from leakcheck.checks import ASSUME, BLOCK, UNABLE, WARN, run_checks


def base(t):
    return copy.deepcopy(load_test_bases()[t])


def add_feature(spec):
    return lambda d: d["features"].append(copy.deepcopy(spec))


def add_criterion(part, spec):
    return lambda d: d["cohort"][part].append(copy.deepcopy(spec))


def setp(path, value):
    def f(d):
        *head, last = path.split(".")
        x = d
        for k in head:
            x = x.setdefault(k, {})
        x[last] = value
    return f


def chain(*fs):
    def f(d):
        for g in fs:
            g(d)
    return f


def step(name, **kw):
    return lambda d: d["preprocessing"].append({"name": name, **kw})


def _found(d):
    r = run_checks(d)
    return ({(f.question, f.verdict, f.target) for f in r.findings if f.verdict in (BLOCK, WARN, UNABLE)}
            | {("가정", a.rule, a.target) for a in r.assumptions})


CR = {"test": ["creatinine"]}
OLAB = {"name": "outpatient_k", "source": "outpatient_labs", "column": "value", "filter": {"test": ["potassium"]},
        "scope": "patient_history", "time_column": "report_time", "window": {"end": "tp"}, "agg": "last"}

# (번호, 유형, 원리, bad, 기대, good)
CASES = [
    # ---- Q1 가용 시점
    ("q1_history_person", "fixed", "history_key=person_id는 자료 추출 때 연결",
     add_feature(dict(OLAB, history_key="person_id")), ("Q1", BLOCK, "features.outpatient_k"),
     add_feature(dict(OLAB, history_key="patient_id"))),
    ("q1_as_of_latest", "fixed", "버전 기록의 최종본은 tₚ 뒤 수정일 수 있음",
     add_feature({"name": "pl_htn", "source": "problem_list", "filter": {"icd_code": ["I10"]}, "scope": "patient_history",
                  "time_column": "recorded_time", "window": {"end": "tp"}, "as_of": "latest", "agg": "any"}),
     ("Q1", BLOCK, "features.pl_htn"),
     add_feature({"name": "pl_htn", "source": "problem_list", "filter": {"icd_code": ["I10"]}, "scope": "patient_history",
                  "time_column": "recorded_time", "window": {"end": "tp"}, "as_of": "tp", "agg": "any"})),
    ("q1_date_only_same_day", "fixed", "날짜만 있는 예정일을 같은 날까지 비교 + 예약 테이블 확인 시각과의 지연 상한 없음",
     add_feature({"name": "planned_soon", "source": "admission_bookings", "scope": "patient_history",
                  "time_column": "planned_date", "window": {"end": "tp"}, "date_compare": "same_date_ok", "agg": "any"}),
     ("Q1", BLOCK, "features.planned_soon"),
     add_feature({"name": "planned_soon", "source": "admission_bookings", "scope": "patient_history",
                  "time_column": "booked_time", "window": {"end": "tp"}, "agg": "any"})),
    ("q1_linked_admission", "fixed", "예약의 admission_id는 예약 입원 때 채워짐",
     add_feature({"name": "booking_realized", "source": "admission_bookings", "column": "admission_id",
                  "scope": "index_admission", "time_column": "booked_time", "window": {"end": "tp"}, "agg": "count"}),
     ("Q1", BLOCK, "features.booking_realized"),
     add_feature({"name": "booking_realized", "source": "admission_bookings", "column": "booking_id",
                  "scope": "index_admission", "time_column": "booked_time", "window": {"end": "tp"}, "agg": "count"})),
    ("q1_extraction_value", "dynamic", "자료 추출 정보는 모든 tₚ 뒤",
     add_feature({"name": "linkage_date", "source": "extract_info", "column": "death_linkage_through", "agg": "value",
                  "scope": "patient"}), ("Q1", BLOCK, "features.linkage_date"),
     lambda d: None),
    ("q1_future_fill", "dynamic", "뒤 행의 값으로 결측 대치",
     step("bfill_vitals", kind="impute", method="interpolate", stateless=True), ("Q1", BLOCK, "preprocessing.bfill_vitals"),
     step("bfill_vitals", kind="impute", method="forward_fill", stateless=True)),
    ("q1_temporal_deploy", "fixed", "전향 사용인데 시간 순 분할 아님 (D5)",
     lambda d: None, ("Q1", WARN, "split.method"),
     chain(setp("split.method", "temporal"), setp("split.time_column", "tp"), setp("split.cutoff", "2158-01-01"),
           setp("split.gap", "30d"))),
    ("q1_derived_inherits", "dynamic", "파생 특징은 재료의 확인 시각을 물려받음",
     chain(add_feature({"name": "k_collected", "source": "labs", "filter": {"test": ["potassium"]},
                        "time_column": "collect_time", "window": {"end": "tp"}, "agg": "last"}),
           add_feature({"name": "k_over_cr", "derive": {"op": "ratio", "of": ["k_collected", "cr_last"]}})),
     ("Q1", BLOCK, "features.k_over_cr"),
     chain(add_feature({"name": "k_collected", "source": "labs", "filter": {"test": ["potassium"]},
                        "time_column": "report_time", "window": {"end": "tp"}, "agg": "last"}),
           add_feature({"name": "k_over_cr", "derive": {"op": "ratio", "of": ["k_collected", "cr_last"]}}))),
    ("q1_derived_missing_part", "dynamic", "파생 특징의 재료가 설계서에 없으면 점검 불가",
     add_feature({"name": "x_ratio", "derive": {"op": "ratio", "of": ["nonexistent", "cr_last"]}}),
     ("Q1~Q3", UNABLE, "features.x_ratio"),
     add_feature({"name": "x_ratio", "derive": {"op": "ratio", "of": ["k_last", "cr_last"]}})),
    # ---- Q2 독립 단위
    ("q2_fallback_patient", "fixed", "대체 키가 개체 단위(사람)보다 작음",
     setp("split.fallback_key", "patient_id"), ("Q2", BLOCK, "split.fallback_key"),
     setp("split.fallback_key", "person_id")),
    ("q2_no_fallback", "dynamic", "결측이 있는 키에 대체 키 없음 → 등록 번호로 묶인다고 가정 + 차단",
     lambda d: d["split"].pop("fallback_key"), ("Q2", BLOCK, "split.key"),
     setp("split.fallback_key", "person_id")),
    ("q2_cv_key_rows", "dynamic", "조율 교차검증 키가 예측 행",
     setp("model.tuning.cv_key", "landmark_row_id"), ("Q2", BLOCK, "model.tuning.cv_key"),
     setp("model.tuning.cv_key", "family_id")),
    ("q2_dedup_within", "fixed", "중복 제거를 분할 안에서",
     setp("cohort.deduplication.when", "within_split"), ("Q2", WARN, "cohort.deduplication.when"),
     setp("cohort.deduplication.when", "before_split")),
    ("q2_temporal_gap", "dynamic", "시간 순 분할의 간격이 결과 창보다 짧음",
     chain(setp("split.method", "temporal"), setp("split.cutoff", "2158-01-01"), setp("split.gap", "24h")),
     ("Q2", WARN, "split.gap"),
     chain(setp("split.method", "temporal"), setp("split.cutoff", "2158-01-01"), setp("split.gap", "48h"))),
    # ---- Q3 적합 범위
    ("q3_fold_refit", "dynamic", "교차검증 조율인데 학습 부분 전체에서 한 번 적합 (D4)",
     setp("preprocessing", [{"name": "scale_all", "kind": "scale", "method": "z_score", "fit_scope": "train"}]),
     ("Q3", WARN, "preprocessing.scale_all"),
     setp("preprocessing", [{"name": "scale_all", "kind": "scale", "method": "z_score", "fit_scope": "train_fold"}])),
    ("q3_eval_on_train", "fixed", "학습 부분으로 성능 평가",
     setp("evaluation.data", "train"), ("Q3", BLOCK, "evaluation.data"), setp("evaluation.data", "test")),
    ("q3_validation_reuse", "fixed", "검증 부분으로 임계값을 정하고 같은 부분으로 평가",
     chain(setp("model.threshold.fit_scope", "validation"), setp("evaluation.data", "validation")),
     ("Q3", BLOCK, "evaluation.data"),
     chain(setp("model.threshold.fit_scope", "validation"), setp("evaluation.data", "test"))),
    ("q3_test_reuse", "fixed", "평가 부분을 여러 번 봄",
     setp("evaluation.test_set_uses", 4), ("Q3", WARN, "evaluation.test_set_uses"), setp("evaluation.test_set_uses", 1)),
    ("q3_resample_test", "fixed", "재표본 추출을 평가 부분에도 적용",
     step("smote", kind="resample", method="smote", fit_scope="train_fold", applies_to="train+test"),
     ("Q3", BLOCK, "preprocessing.smote"),
     step("smote", kind="resample", method="smote", fit_scope="train_fold", applies_to="train_fold")),
    ("q3_before_split", "fixed", "추정 단계를 분할 전에",
     step("winsor", kind="clip", fit_scope="train_fold", before_split=True), ("Q3", BLOCK, "preprocessing.winsor"),
     step("winsor", kind="clip", fit_scope="train_fold", before_split=False)),
    # ---- Q4 결과 출처
    ("q4_rule_proxy_problem", "dynamic", "규칙표 대리 기록(AKI 문제 목록 항목), 설계서 목록 없이도 경고",
     chain(setp("outcome.proxies", []),
           add_feature({"name": "aki_problem_by_tp", "source": "problem_list", "filter": {"icd_code": ["N17"]},
                        "time_column": "recorded_time", "window": {"start": "admit", "end": "tp"}, "agg": "any"})),
     ("Q4", WARN, "features.aki_problem_by_tp"),
     chain(setp("outcome.proxies", []),
           add_feature({"name": "aki_problem_by_tp", "source": "problem_list", "filter": {"icd_code": ["I50"]},
                        "time_column": "recorded_time", "window": {"start": "admit", "end": "tp"}, "agg": "any"}))),
    ("q4_design_proxy_diuretic", "dynamic", "설계서가 대리 기록으로 적은 이뇨제 (규칙표 목록에는 없음, A안)",
     add_feature({"name": "diuretic_by_tp", "source": "medications", "filter": {"drug": ["loop_diuretic"]},
                  "time_column": "order_time", "window": {"start": "admit", "end": "tp"}, "agg": "any"}),
     ("Q4", WARN, "features.diuretic_by_tp"),
     chain(lambda d: d["outcome"].update(proxies=[x for x in d["outcome"]["proxies"] if x["source"] != "medications"]),
           add_feature({"name": "diuretic_by_tp", "source": "medications", "filter": {"drug": ["loop_diuretic"]},
                        "time_column": "order_time", "window": {"start": "admit", "end": "tp"}, "agg": "any"}))),
    ("q4_vitals_window_reuse", "dynamic", "다른 테이블 특징의 창이 결과 창과 겹침",
     add_feature({"name": "hr_next", "source": "vitals", "filter": {"item": ["heart_rate"]},
                  "time_column": "entered_time", "window": {"start": "tp+12h", "end": "tp+36h"}, "agg": "max"}),
     ("Q4", BLOCK, "features.hr_next"),
     add_feature({"name": "hr_next", "source": "vitals", "filter": {"item": ["heart_rate"]},
                  "time_column": "entered_time", "window": {"start": "tp-24h", "end": "tp"}, "agg": "max"})),
    ("q4_not_blind", "fixed", "결과를 예측변수를 알고 정함",
     setp("outcome.ascertainment.blind_to_predictors", False),
     ("Q4", WARN, "outcome.ascertainment.blind_to_predictors"),
     setp("outcome.ascertainment.blind_to_predictors", True)),
    # ---- Q5 선택 시점
    ("q5_last_per_person", "fixed", "사람마다 마지막 행 (D1)",
     setp("cohort.rows_per_unit", {"unit": "person", "choose": "last"}), ("Q5", BLOCK, "cohort.rows_per_unit"),
     setp("cohort.rows_per_unit", {"unit": "person", "choose": "first"})),
    ("q5_last_landmark", "dynamic", "입원마다 마지막 랜드마크 (퇴원 시각을 알아야 함)",
     setp("cohort.rows_per_unit", {"unit": "admission", "choose": "last"}), ("Q5", BLOCK, "cohort.rows_per_unit"),
     setp("cohort.rows_per_unit", {"unit": "admission", "choose": "all"})),
    ("q5_death_exclude", "fixed", "결과 창 안 사망으로 행을 뺌",
     setp("outcome.censoring.death", "exclude"), ("Q5", BLOCK, "outcome.censoring.death"),
     setp("outcome.censoring.death", "competing_risk")),
    ("q5_sampling_eval", "fixed", "결과 기준 표본 추출을 평가에도 적용",
     setp("cohort.sampling", {"method": "case_control", "ratio": 2, "uses_outcome": True, "applies_to": "both"}),
     ("Q5", BLOCK, "cohort.sampling"),
     setp("cohort.sampling", {"method": "case_control", "ratio": 2, "uses_outcome": True, "applies_to": "development"})),
    ("q5_time_compare_lag", "dynamic", "채취 시각을 tₚ와 비교: 보고까지 지연 6h",
     add_criterion("exclusion", {"name": "cr_drawn_after_tp", "source": "labs", "column": "collect_time",
                                 "filter": {"test": ["creatinine"]}, "scope": "index_admission", "agg": "max",
                                 "op": ">", "value": "tp"}),
     ("Q5", BLOCK, "cohort.exclusion.cr_drawn_after_tp"),
     add_criterion("exclusion", {"name": "cr_drawn_after_tp", "source": "transfers", "column": "out_time",
                                 "scope": "index_admission", "agg": "max", "op": ">", "value": "tp"})),
    ("q5_patient_table_future", "fixed", "환자 단위 테이블의 tₚ 뒤 기록으로 포함",
     add_criterion("inclusion", dict(OLAB, name="has_outpatient_k", window={"start": "tp", "end": "inf"}, agg="any",
                                     op="==", value=True)),
     ("Q5", BLOCK, "cohort.inclusion.has_outpatient_k"),
     add_criterion("inclusion", dict(OLAB, name="has_outpatient_k", window={"end": "tp"}, agg="any",
                                     op="==", value=True))),
    ("q5_lost_exclude", "fixed", "추적 소실로 행을 뺌 → 형식에 대안이 없어 가정",
     setp("outcome.censoring.lost_to_followup", "exclude"),
     ("가정", "A.post_tp_exclusion", "outcome.censoring.lost_to_followup"),
     setp("outcome.censoring.lost_to_followup", "count_as_negative")),
    ("q5_outcome_missing_exclude", "fixed", "결과 결측 행을 뺌 → 가정",
     setp("analysis.missing_data.outcome_missing", "exclude"),
     ("가정", "A.post_tp_exclusion", "analysis.missing_data.outcome_missing"),
     setp("analysis.missing_data.outcome_missing", "not_applicable")),
    # ---- Q7 결과 확인 균질성
    ("q7_match_key", "fixed", "결과를 같은 등록 번호에서만 찾음",
     setp("outcome.match_key", "patient_id"), ("Q7", WARN, "outcome.match_key"), setp("outcome.match_key", "person_id")),
    ("q7_history", "dynamic", "결과 측정법이 바뀌었는데 이력 없음",
     setp("outcome.history", []), ("Q7", WARN, "outcome.history"), lambda d: None),
    ("q7_end_of_data", "fixed", "결과 창이 추출 종료를 넘는 행을 음성으로",
     setp("outcome.censoring.end_of_data", "count_as_negative"), ("Q7", WARN, "outcome.censoring.end_of_data"),
     setp("outcome.censoring.end_of_data", "survival_model")),
    ("q7_death_source", "dynamic", "원내 사망만으로 사망 포함 결과 (D3)",
     lambda d: None, ("Q7", WARN, "data_source.death_source"), setp("data_source.death_source", "linked_registry")),
    ("q7_site_scope_handled", "fixed", "확인 범위가 B만 — 퇴원처 층을 다루면 경고 없음",
     chain(setp("outcome.ascertainment.scope.sites", ["B"]), setp("outcome.ascertainment.by_stratum", ["site"])),
     ("Q7", WARN, "outcome.ascertainment.scope.sites"),
     chain(setp("outcome.ascertainment.scope.sites", ["B"]),
           setp("outcome.ascertainment.by_stratum", ["site", "discharge_status"]))),
    ("q7_unit_stratum", "dynamic", "측정 결과의 확인 강도 층(병동)을 다루지 않음 → 기본 설계서는 특징 이름(unit_at_tp)으로 다룸",
     lambda d: (d["outcome"]["ascertainment"].update(by_stratum=[]), d["cohort"].update(subgroups=[])),
     ("Q7", WARN, "outcome.ascertainment.by_stratum"), lambda d: None),
    # ---- 가정 (3층)
    ("a_date_only", "dynamic", "날짜만 있는 열을 date_compare 없이",
     add_feature({"name": "proc_coded", "source": "procedures", "time_column": "chart_date",
                  "window": {"end": "tp-48h"}, "agg": "count"}),
     ("가정", "A.date_only", "features.proc_coded"),
     add_feature({"name": "proc_coded", "source": "procedures", "time_column": "coded_time",
                  "window": {"end": "tp"}, "agg": "count"})),
]


@pytest.mark.parametrize("cid,t,why,bad,expected,good", CASES, ids=[c[0] for c in CASES])
def test_principle_fires_and_correct_form_avoids_it(cid, t, why, bad, expected, good):
    clean = _found(base(t))
    d_bad, d_good = base(t), base(t)
    bad(d_bad)
    good(d_good)
    found_bad = _found(d_bad)
    if expected in clean:   # 기본 설계서에 이미 있는 판정(D3, D5): bad는 기본 설계서 그대로
        assert expected in found_bad
    else:
        assert expected in found_bad - clean, (cid, sorted(found_bad - clean))
    assert expected not in _found(d_good), (cid, why)


def test_temporal_split_keeps_groups_together_in_data(small_tables):
    """D5 해석: temporal + 묶음 키는 묶음째로 움직여 데이터에서 나뉘는 묶음이 없다."""
    d = base("fixed")
    d["split"].update(method="temporal", time_column="tp", cutoff="2155-06-01", gap="30d")
    r = run_checks(d, small_tables)
    assert not any(f.question == "Q2" and f.verdict == BLOCK for f in r.findings), r.to_text()
    assert ("Q1", WARN, "split.method") not in {(f.question, f.verdict, f.target) for f in r.findings}
    from leakcheck import splitting
    from leakcheck.checks import prepare_data
    from leakcheck.design import normalize
    nd = normalize(d)
    ctx = prepare_data(nd, small_tables)
    lab = splitting.assign(ctx.cohort, nd["split"])
    assert set(lab) == {"train", "test", splitting.UNUSED}
    tr, te = ctx.cohort[lab == "train"], ctx.cohort[lab == "test"]
    assert (tr["tp"] <= "2155-06-01").all() and (te["tp"] > "2155-07-01").all()
