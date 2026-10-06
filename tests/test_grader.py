"""5단계 채점기 v2 시험 = 검증 세트 (B). 진짜 정답표는 쓰지 않는다 (가짜 정답표 + 가짜 제출).

가짜 변형은 깨끗한 설계서(designs/clean_v2/)에 공개 사례 패치(designs/patches_v1_cases.py)를 적용해 만든다.
정답표 항목은 designs/answer_key_v2.py의 함수로 만든다 (진짜 정답표와 같은 형식, 정당한 지적 목록은 잠긴 목록 그대로).
변형 파일(designs/variants/)끼리, 또는 변형과 깨끗한 설계서를 비교하지 않는다.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

import pytest

from designs import answer_key_v2 as ak
from designs import inject as inj
from designs.patches_v1_cases import V1_CASE_PATCHES
from experiment import grader as gr
from experiment import prompt

ROOT = Path(__file__).resolve().parent.parent
CLEAN = ROOT / "designs" / "clean_v2"
QUESTION = {"E01": "Q1", "E02": "Q1", "E03": "Q1", "E04": "Q1", "E05": "Q2", "E06": "Q2", "E07": "Q2",
            "E08": "Q3", "E09": "Q3", "E10": "Q3", "E11": "Q1", "E12": "Q4", "E13": "Q4", "E14": "Q5",
            "E15": "Q5", "E16": "Q5", "E17": "Q7", "E18": "Q7"}


def base(name: str) -> dict:
    return json.loads((CLEAN / f"{name}.json").read_text(encoding="utf-8"))


def variant(b: str, cases: tuple = (), holdout: bool = False) -> tuple[dict, dict]:
    """(가짜 변형 설계서, 정답표 항목) — answer_key_v2 형식."""
    d = base(b)
    defects = []
    for cid in cases:
        ops = V1_CASE_PATCHES[cid]
        d = inj.apply_ops(d, ops)
        exc = ak.PUBLIC_EXCEPTIONS.get(cid, {})
        defects.append(ak.defect_entry(cid, QUESTION[cid], holdout, "차단", ops,
                                       exc.get("support_targets"), exc.get("accept_questions")))
    return d, ak.variant_entry("-", b, d["design_type"], defects)


def sub(items: list[dict] | None) -> str | None:
    return None if items is None else json.dumps(items, ensure_ascii=False)


def P(target, problem="문제가 있다", kind="문제"):
    return {"target": target, "kind": kind, "problem": problem}


def grade(design, entry, items, rid="r1"):
    return gr.grade_report({"report_id": rid, "variant": "v.json", "findings": sub(items)}, design, entry)


# ---------------------------------------------------------------- 형식 검사 (구조와 kind만)

def test_validate_scope_structure_and_kind_only():
    assert gr.validate_findings(None) == ["파일 없음"]
    assert gr.validate_findings("[") == ["JSON 오류"]
    assert gr.validate_findings('{"a": 1}') == ["목록 아님"]
    assert gr.validate_findings("[]") == []
    assert gr.validate_findings(sub([P("features.no_such_feature"), P(["split.key", "설계 전체"])])) == []  # 경로는 보지 않음
    assert gr.validate_findings(sub([P("split.key", kind="경고")])) == ["0: kind"]
    assert gr.validate_findings(sub([{"target": "", "kind": "문제", "problem": "x"}])) == ["0: target"]
    assert gr.validate_findings(sub([{"target": "a", "kind": "가정"}])) == ["0: problem"]


def test_empty_list_vs_missing_file():
    d, e = variant("aki_a", ("E02",))
    g0 = grade(d, e, [])
    gn = grade(d, e, None)
    assert g0.format_error is None and g0.n_entries == 0
    assert gn.format_error == "파일 없음" and gn.n_entries == 0
    assert not g0.defects[0]["primary"] and not gn.defects[0]["primary"]
    assert g0.false_alarms == gn.false_alarms == []


def test_list_target_and_malformed_entry():
    d, e = variant("aki_a", ("E02",))
    g = grade(d, e, [P(["features.cr_last", "features.age"]), {"target": "features.sex", "kind": "?", "problem": "x"}])
    assert g.n_entries == 2 and g.n_malformed == 1
    assert g.defects[0]["primary"] and g.false_alarms == ["features.age"]


# ---------------------------------------------------------------- kind

def test_kind_assumption_and_unable_on_defect_cell():
    d, e = variant("aki_a", ("E02",))
    g = grade(d, e, [P("features.cr_last", kind="가정"), P("features.cr_last", kind="점검 불가"), P("features.age", kind="가정")])
    assert not g.defects[0]["primary"] and g.false_alarms == []
    c = g.counts
    assert (c["n_assumption"], c["n_unable"], c["n_defect_cell_assumption"], c["n_defect_cell_unable"]) == (2, 1, 1, 1)


def test_assumption_written_as_problem():
    """가정 칸을 kind=문제로 적음: 깨끗한 변형에서 목록 칸(L8 split.key)이면 중립, 수는 따로 셈."""
    d, e = variant("readmit_c")
    g = grade(d, e, [P("split.key", "family_id 결측 행은 대체 키로 묶여 가족이 나뉠 수 있다")])
    assert g.false_alarms == [] and g.counts["n_justified"] == 1 and g.counts["n_assumption_cell_problem"] == 1


def test_assumption_cell_as_problem_on_defect_cell_is_detection():
    d, e = variant("readmit_c", ("E06",))
    g = grade(d, e, [P("split.key", "family_id 결측")])
    assert g.defects[0]["primary"] and g.counts["n_assumption_cell_problem"] == 1


# ---------------------------------------------------------------- 우선순위

def test_defect_cell_that_is_also_justified_is_detection_and_sensitivity():
    """E02 정답 features.cr_last, 목록 L11 칸 features.cr_last.time_column: 탐지가 우선. 민감도(목록 먼저)는 미탐지."""
    d, e = variant("aki_a", ("E02",))
    g = grade(d, e, [P("features[name=cr_last].time_column", "채취 시각이라 tp 뒤 보고 값이 들어간다")])
    x = g.defects[0]
    assert x["primary"] and x["secondary"] and not x["primary_justified_first"]
    assert g.false_alarms == [] and g.counts["n_justified"] == 0


def test_justified_first_includes_exception_routes():
    """민감도 ⑤는 예외(분할 묶음)로 맞은 지적도 포함: E06 정답 split, 지적 model.tuning.cv_key(L8 목록 칸)."""
    d, e = variant("readmit_c", ("E06",))
    g = grade(d, e, [P("model.tuning.cv_key", "같은 가족이 fold에 나뉜다")])
    x = g.defects[0]
    assert x["primary"] and x["via_bundle_or_exception_only"] and not x["primary_justified_first"]


def test_support_is_neutral():
    d, e = variant("readmit_a", ("E09",))
    g = grade(d, e, [P("features.prior_dx_main", "범주형 진단 코드")])
    assert not g.defects[0]["primary"] and g.false_alarms == [] and g.counts["n_support"] == 1


def test_legit_change_is_false_alarm():
    d, e = variant("aki_b")
    g = grade(d, e, [P("features.k_last_6h", "의심")])
    assert g.false_alarms == ["features.k_last_6h"] and g.legit_flagged == ["features.k_last_6h"]


@pytest.mark.parametrize("b,item", [("aki_c", "n_admissions_to_tp"), ("readmit_b", "prior_dx_group"), ("readmit_c", "prior_cr_last")])
def test_legit_item_not_absorbed_by_broad_route(b, item):
    """S3 뒤 결정: 좁게 맞음이 넓게 맞음보다 먼저. legit 항목을 항목 단위로 지적 → 오경보,
    그 항목의 목록 칸(history_key, 목록 L6)을 지적 → 중립."""
    d, e = variant(b)
    g = grade(d, e, [P(f"features.{item}", "의심")])
    assert g.false_alarms == [f"features.{item}"] and g.legit_flagged == [f"features.{item}"] and g.counts["n_justified"] == 0
    g2 = grade(d, e, [P(f"features.{item}.history_key", "등록 번호로만 묶는다")])
    assert g2.false_alarms == [] and g2.counts["n_justified"] == 1


def test_non_legit_item_still_absorbed_by_broad_route():
    d, e = variant("readmit_a")
    g = grade(d, e, [P("features.prior_dx_ckd", "x")])
    assert g.false_alarms == [] and g.counts["n_justified"] == 1 and g.counts["n_justified_strict"] == 0


def test_justified_k2_is_neutral_k1_is_false_alarm():
    da, ea = variant("aki_c")
    ga = grade(da, ea, [P("data_source.death_source", "원내 사망만 쓴다")])
    assert ga.false_alarms == [] and ga.counts["n_justified"] == 1
    db, eb = variant("readmit_b")
    gb = grade(db, eb, [P("features.n_clinic_365d", "추적 외래가 결과 대리 기록과 겹친다")])
    assert gb.false_alarms == ["features.n_clinic_365d"] and gb.false_alarms_no_k == []


def test_k5_cell_reference():
    d, e = variant("readmit_a")
    g = grade(d, e, [P("cohort.rows_per_unit", "점검기 코호트는 마지막 입원만 고르지 않는다")])
    assert g.false_alarms == ["cohort.rows_per_unit"] and g.false_alarms_no_k == []
    d2, e2 = variant("aki_a")   # 동적 바탕은 K5가 아니다
    g2 = grade(d2, e2, [P("cohort.rows_per_unit", "x")])
    assert g2.false_alarms_no_k == ["cohort.rows_per_unit"]


# ---------------------------------------------------------------- 칸 넓이

def test_breadth_item_level_broader_matches_justified_but_not_strict():
    d, e = variant("aki_a")
    g = grade(d, e, [P("features.cr_last", "마지막 값을 입력 시각 순으로 고른다")])
    assert g.false_alarms == [] and g.counts["n_justified"] == 1
    assert g.false_alarms_strict == ["features.cr_last"] and g.counts["n_justified_strict"] == 0


def test_breadth_broader_on_accept_and_strict():
    """E18 정답에 outcome.ascertainment.scope.sites 등. outcome.ascertainment(최상위 아래 칸) 지적은 관대판 탐지, 엄격판 미탐지."""
    d, e = variant("readmit_a", ("E18",))
    x = grade(d, e, [P("outcome.ascertainment", "A·B 밖 병원 재입원을 놓친다")]).defects[0]
    assert x["primary"] and not x["primary_strict"] and not x["via_bundle_or_exception_only"]


def test_top_bundle_finding_is_too_broad():
    d, e = variant("readmit_a", ("E18",))
    g = grade(d, e, [P("outcome", "결과 확인이 고르지 않다"), P("features", "x"), P("outcome.readmit_30d", "x")])
    assert not g.defects[0]["primary"] and g.false_alarms == []
    assert g.counts["n_too_broad"] == 3 and set(g.false_alarms_with_broad) == {"outcome", "features"}


def test_bundle_key_and_strict_drops_it():
    """E18 정답 칸에 cohort(묶음)가 있다: 관대판은 어떤 cohort.* 지적도 탐지(묶음 경로로만), 엄격판은 묶음 칸을 뺀다."""
    d, e = variant("readmit_a", ("E18",))
    x = grade(d, e, [P("cohort.exclusion.died_in_hospital", "x")]).defects[0]
    assert x["primary"] and x["via_bundle_or_exception_only"] and not x["primary_strict"]


@pytest.mark.parametrize("target,route,strict", [
    ("split.key", "bundle", True), ("split", "bundle", True), ("split.method", "bundle", True),
    ("split_unit", "exception", False), ("model.tuning.cv_key", "exception", False)])
def test_split_group(target, route, strict):
    d, e = variant("readmit_c", ("E06",))
    x = grade(d, e, [P(target, "같은 가족이 학습과 평가에 나뉜다")]).defects[0]
    assert x["primary"] and x["via_bundle_or_exception_only"] and x["primary_strict"] is strict
    assert gr.match_route(gr.resolve(target, d), "split", d) == route


def test_subgroups_exception_only_for_ascertainment():
    d, e = variant("aki_a", ("E17",))
    x = grade(d, e, [P("cohort.subgroups", "ICU·병동 측정 빈도가 다르다")]).defects[0]
    assert x["primary"]   # E17은 정답에 cohort 묶음도 있다
    assert gr.match_route("cohort.subgroups", "outcome.ascertainment", d) == "exception"
    assert gr.match_route("cohort.subgroups", "outcome.window", d) is None


def test_sibling_cell_is_not_detection():
    """형제 칸: 정답 outcome.ascertainment(E17)인데 outcome.window 지적 → 탐지 아님, 그 칸의 판정(여기서는 오경보), 수는 기록."""
    d, e = variant("aki_a", ("E17",))
    g = grade(d, e, [P("outcome.window", "결과 창이 잘린다")])
    assert not g.defects[0]["primary"] and g.false_alarms == ["outcome.window"]
    assert g.counts["n_sibling_of_defect"] == 1


def test_nonexistent_paths():
    d, e = variant("aki_a")
    g = grade(d, e, [P("features.no_such"), P("no_such_section.x"), P("설계 전체"),
                     P("features (age, sex, unit)"), P("features.age.no_such_cell")])
    assert g.counts["n_unresolved"] == 4 and g.false_alarms == ["features.age"]


def test_duplicates_counted_once_per_item():
    d, e = variant("aki_a")
    g = grade(d, e, [P("features.age"), P("features.age"), P("features.age.source"), P("features.sex")])
    assert g.false_alarms == ["features.age", "features.sex"]


def test_not_graded_heads():
    d, e = variant("aki_a")
    g = grade(d, e, [P("attempts.n_models_tried", "다중 시도"), P("notes")])
    assert g.false_alarms == [] and g.counts["n_not_graded"] == 2


def test_natural_target_strings():
    d, e = variant("aki_a", ("E02",))
    for t in ("features[name=cr_last].time_column", "features:cr_last", "cr_last", "`features.cr_last`",
              "features.cr_last (time_column=collect_time)"):
        assert grade(d, e, [P(t)]).defects[0]["primary"], t


def test_secondary_uses_accept_questions():
    d, e = variant("aki_a", ("E02",))
    assert grade(d, e, [P("features.cr_last", "보고 시각 전 값이다")]).defects[0]["secondary"]
    x = grade(d, e, [P("features.cr_last", "이상할 수도 있다")])
    assert x.defects[0]["primary"] and not x.defects[0]["secondary"] and x.counts["n_unknown_kind"] == 1
    d4, e4 = variant("aki_a", ("E04",))   # E04 accept_questions = Q1, Q4
    assert grade(d4, e4, [P("features.n_proc", "투석은 결과의 대리 변수")]).defects[0]["secondary"]


def test_two_defects_one_variant():
    d, e = variant("aki_a", ("E02", "E13"))
    g = grade(d, e, [P("features.renal_ordered", "결과의 대리 변수")])
    assert [x["primary"] for x in g.defects] == [False, True]


# ---------------------------------------------------------------- 점검기 출력

def test_grade_checker_output():
    d, e = variant("aki_a", ("E02",))
    out = {"findings": [
        {"question": "Q1", "verdict": "차단", "target": "features.cr_last", "reason": "확인 가능 시각이 tp 뒤"},
        {"question": "Q2", "verdict": "통과", "target": "split.key", "reason": "-"},
        {"question": "Q1~Q3", "verdict": "경고", "target": "features.age", "reason": "출처 불명: 확인 불가."}],
        "assumptions": [{"question": "Q2", "verdict": "가정", "target": "split.key", "reason": "family 결측"}]}
    g = gr.grade_checker({"report_id": "c1", "variant": "v.json", "exit_code": 1, "checker": out}, d, e)
    assert g.defects[0]["secondary"] and g.false_alarms == []
    assert (g.counts["n_unable"], g.counts["n_assumption"]) == (1, 1)
    g2 = gr.grade_checker({"report_id": "c2", "variant": "v.json", "exit_code": 2, "checker": None}, d, e)
    assert not g2.defects[0]["primary"]


def test_checker_on_clean_base_has_no_false_alarm():
    """깨끗한 설계서 8개의 점검기 판정(설계서 단계)이 기대 집합과 같다. v2 채점기로 채점하면 오경보는 K1 하나뿐이고,
    점검기의 가정 칸은 grader.ASSUMPTION_CELLS와 같다. 점검기는 고치지 않고 변형에는 돌리지 않는다."""
    from leakcheck.checks import run_checks
    from tests.test_inject import EXPECTED_CLEAN_PROBLEMS
    for name in sorted(EXPECTED_CLEAN_PROBLEMS):
        d, e = variant(name)
        r = run_checks(d)
        assert sorted((f.verdict, f.rule, f.target) for f in r.problems()) == EXPECTED_CLEAN_PROBLEMS[name]
        out = r.to_dict()
        assert sorted({a["target"] for a in out["assumptions"]}) == sorted(gr.ASSUMPTION_CELLS[name]), name
        g = gr.grade_checker({"report_id": name, "variant": "v.json", "exit_code": 0, "checker": out}, d, e)
        want = ["features.n_clinic_365d"] if name == "readmit_b" else []
        assert g.false_alarms == want and g.false_alarms_no_k == [] and g.counts["n_unresolved"] == 0, name


# ---------------------------------------------------------------- 맹검

def test_blind_guard():
    d, e = variant("aki_a", ("E02",))
    for k in ("condition", "arm", "조건", "skill"):
        with pytest.raises(ValueError):
            gr.grade_report({"report_id": "r", "variant": "v.json", "findings": "[]", k: "가"}, d, e)
    with pytest.raises(ValueError):
        gr.grade_checker({"report_id": "r", "variant": "v.json", "exit_code": 0, "checker": None, "condition": "가"}, d, e)


def test_grade_all_has_no_condition_input():
    import inspect
    for fn in (gr.grade_report, gr.grade_checker, gr.grade_all):
        assert not {"condition", "conditions"} & set(inspect.signature(fn).parameters)


# ---------------------------------------------------------------- 요약 · 가설

def _fake_run(reps: int = 2):
    """가짜 변형 5개 (공개 결함 2, 보류 결함 1, 깨끗한 2) × 조건 2 × 반복."""
    specs = {"vA.json": variant("aki_a", ("E02",)), "vB.json": variant("readmit_c", ("E06",)),
             "vH.json": variant("aki_b", ("E13",), holdout=True),
             "vC.json": variant("aki_c"), "vD.json": variant("readmit_b")}
    designs = {k: v[0] for k, v in specs.items()}
    key = {k: v[1] for k, v in specs.items()}
    good = {"vA.json": [P("features.cr_last", "채취 시각이라 tp 뒤 보고 값")],
            "vB.json": [P("split.key", "같은 환자의 입원이 학습과 평가에 나뉜다")],
            "vH.json": [P("features.renal_ordered", "결과의 대리 변수")],
            "vC.json": [P("data_source.death_source", "원내 사망만")],
            "vD.json": [P("features.n_clinic_365d", "대리 기록과 겹친다")]}
    weak = {"vA.json": [P("features.cr_last", "좀 의심스럽다")], "vB.json": [P("features.age", "확인 필요")],
            "vH.json": [], "vC.json": [P("features.age", "확인 필요"), P("outcome", "x")], "vD.json": []}
    reports, conds, i = [], {}, 0
    for cond, items in (("가", good), ("나", weak)):
        for rep in range(1, reps + 1):
            for v in specs:
                i += 1
                rid = f"r{i:03d}"
                reports.append({"report_id": rid, "variant": v, "findings": sub(items[v])})
                conds[rid] = {"condition": cond, "rep": rep, "turn_capped": False, "format_retries": 0}
    return reports, conds, key, designs


def test_summary_end_to_end():
    reports, conds, key, designs = _fake_run()
    s = gr.summarize(gr.grade_all(reports, key, designs=dict(designs)), conds, key)
    ga, gb = s["conditions"]["가"], s["conditions"]["나"]
    assert ga["detection"]["all"]["primary"] == 1.0 and gb["detection"]["all"]["primary"] == pytest.approx(1 / 3)
    assert ga["detection"]["holdout"]["n"] == 2 and ga["detection"]["public"]["n"] == 4
    assert ga["false_alarms"]["clean"]["false_alarms"] == {"total": 2, "mean_per_report": 0.5}
    assert ga["false_alarms"]["clean"]["false_alarms_no_k"]["total"] == 0
    assert gb["counts"]["n_too_broad"] == 2 and gb["false_alarms"]["clean"]["false_alarms_with_broad"]["total"] == 4
    assert ga["counts"]["n_justified"] == 2
    assert ga["counts"]["detections_via_bundle_or_exception_only"] == 2   # vB split.key → split 묶음 정답
    h = s["hypotheses"]
    assert h["H1a"]["diff"] == pytest.approx(2 / 3) and h["H1a"]["n_units"] == 3
    assert h["H1b"] == {"fa_clean_mean_ga": 0.5, "reports": 4, "met": True}
    # (가): vD의 K1 1건 × 2회 / 4 = 0.5, (나): vC의 features.age 1건 × 2회 / 4 = 0.5 ("outcome"은 넓음이라 세지 않음)
    assert h["H1c"]["n_units"] == 2 and h["H1c"]["diff"] == pytest.approx(0.0)
    assert h["H2a"]["n_units"] == 1 and h["H2a"]["diff"] == 1.0
    assert h["H2b"]["note"] == "기술만 (기준 없음)" and "met" not in h["H2b"]
    assert set(s["reference"]) >= {"strict_breadth", "justified_first", "without_assumption_overlap_cases",
                                   "fa_without_k1_k5", "fa_with_too_broad", "fa_strict"}
    assert s["reference"]["without_turn_capped"] is None and s["reference"]["narrative_fixed_drawn"] == []
    assert s["reference"]["fa_without_k1_k5"]["H1b"] == 0.0
    assert s["n_reps"] == [1, 2]


def test_strict_reported_for_h1a_and_h2a():
    reports, conds, key, designs = _fake_run()
    s = gr.summarize(gr.grade_all(reports, key, designs=dict(designs)), conds, key)
    st = s["reference"]["strict_breadth"]
    assert {"H1a", "H2a"} <= set(st) and st["H2a"]["n_units"] == 1


def test_one_rep_only_and_turn_capped_reference():
    reports, conds, key, designs = _fake_run(reps=1)
    rid = next(r for r in conds if conds[r]["condition"] == "가")
    conds[rid]["turn_capped"] = True
    s = gr.summarize(gr.grade_all(reports, key, designs=dict(designs)), conds, key)
    assert s["n_reps"] == [1] and s["conditions"]["가"]["reports"] == 5
    assert s["conditions"]["가"]["counts"]["turn_capped"] == 1 and s["reference"]["without_turn_capped"] is not None


def test_near_zero_and_narrative_fixed_reference():
    reports, conds, key, designs = _fake_run()
    key = copy.deepcopy(key)
    key["vH.json"]["defects"][0]["id"] = "C18"
    s = gr.summarize(gr.grade_all(reports, key, designs=dict(designs)), conds, key, near_zero=[["vA.json", "E02"]])
    assert s["reference"]["narrative_fixed_drawn"] == ["C18"]
    assert s["reference"]["without_narrative_fixed"]["H2a"]["n_units"] == 0
    assert s["reference"]["without_near_zero"]["H1a"]["n_units"] == 2   # vA의 배치가 빠져 vA는 단위에서 빠짐
    assert s["reference"]["without_near_zero"]["H1a"]["diff"] != s["hypotheses"]["H1a"]["diff"]


def test_secondary_not_used_for_judgment():
    reports, conds, key, designs = _fake_run()
    s = gr.summarize(gr.grade_all(reports, key, designs=dict(designs)), conds, key)
    assert "secondary" in s and set(s["hypotheses"]) == {"H1a", "H1b", "H1c", "H2a", "H2b"}


def test_checker_only_metric():
    reports, conds, key, designs = _fake_run()
    chk = [{"report_id": r["report_id"], "variant": r["variant"], "exit_code": 1,
            "checker": {"findings": [{"question": "Q1", "verdict": "차단", "target": "features.cr_last", "reason": "-"}]}}
           for r in reports if conds[r["report_id"]]["condition"] == "가"]
    s = gr.summarize(gr.grade_all(reports, key, chk, designs=dict(designs)), conds, key)
    c = s["checker_only"]
    assert c["runs"] == 10 and c["detection"]["primary"] == pytest.approx(1 / 3)
    # vC·vD의 cr_last 지적은 목록 L11 칸(cr_last.time_column)보다 넓은 항목 단위 → 관대판 중립, 엄격판 오경보
    assert c["false_alarms"]["clean"]["false_alarms"]["total"] == 0
    assert c["false_alarms"]["clean"]["false_alarms_strict"]["total"] == 4


def test_stability():
    reports, conds, key, designs = _fake_run()
    s = gr.summarize(gr.grade_all(reports, key, designs=dict(designs)), conds, key)
    assert s["conditions"]["가"]["stability"]["primary"] == 1.0


# ---------------------------------------------------------------- 변형 해시 대조

def test_verify_variants(tmp_path):
    """잠금 기준: v2 변형 목록 docs/variants_v2.md (4b 사용자 결정 ㉢)."""
    log = gr.injection_log_hashes()
    assert len(log) == 30
    fake_key = {f: {"sha256": h} for f, h in log.items()}
    assert gr.verify_variants(fake_key, log=log) == []
    for f in log:
        (tmp_path / f).write_text((gr.VARIANT_DIR / f).read_text(encoding="utf-8"), encoding="utf-8")
    first = sorted(log)[0]
    (tmp_path / first).write_text("{}\n", encoding="utf-8")
    bad = gr.verify_variants(fake_key, tmp_path, log=log)
    assert len(bad) == 2 and all(first in b for b in bad)


def test_resolve_on_real_variants():
    """실제 맹검 변형 30개의 모든 목록 항목을 해석할 수 있다 (정답표는 쓰지 않는다, 변형끼리 비교하지 않는다)."""
    for p in sorted(gr.VARIANT_DIR.glob("design_*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        for s, ns in gr._names(d).items():
            for n in ns:
                assert gr.resolve(f"{gr.LIST_SECTIONS[s]}.{n}", d) == f"{gr.LIST_SECTIONS[s]}.{n}"


# ---------------------------------------------------------------- 검증 세트 (A)

def test_validation_set_a_test_half_passes():
    """(A) 시험 절반: 항목 일치 ≥ 0.95, Q 일치(라벨 Q ⊆ 채점기 Q) ≥ 0.85 (5단계 기준)."""
    from tools import validation_report as vr
    m = vr.metrics(vr.rows("test"))
    assert m["n"] == 168 and m["item_agree"] >= vr.ITEM_MIN and m["q_agree"] >= vr.Q_MIN


def test_validation_set_labels_fixed():
    lab = json.loads((ROOT / "tests" / "fixtures" / "validation_v1" / "labels.json").read_text(encoding="utf-8"))
    assert len(lab["labels"]) == 332 and len(lab["revisions"][0]["changed"]) == 48


# ---------------------------------------------------------------- 실행 규칙 상수

def test_run_limits_match_criteria():
    doc = (ROOT / "docs" / "success_criteria_v2.md").read_text(encoding="utf-8")
    assert (gr.MAX_TURNS, gr.MAX_TURNS_RETRY, gr.FORMAT_RETRIES) == (60, 5, 1)
    assert "턴 수 상한 **60**" in doc and "재제출 턴 상한 **5**" in doc


# ---------------------------------------------------------------- 지시문 · 형식 설명 · 설명서 사본

BANNED = ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "가용 시점", "독립 단위", "적합 범위", "결과 출처",
          "선택 시점", "확인 균질성", "누수", "leak", "스킬", "skill", "점검기", "run_check"]


def test_prompt_fixed_and_neutral():
    t = prompt.text()
    assert prompt.PROMPT_SHA256 in (ROOT / "docs" / "success_criteria_v2.md").read_text(encoding="utf-8")
    assert "한국어" in t and "findings.json" in t and all(k in t for k in gr.FINDING_KINDS)
    assert not [w for w in BANNED if w.lower() in t.lower()]
    r = prompt.render("design.json", "data", "design_format.md", "data_dictionary.md")
    assert "{{" not in r and "design.json" in r and "design_format.md" in r and "data_dictionary.md" in r


def test_prompt_example_parses():
    m = re.search(r"```json\n(.*?)```", prompt.text(), re.S)
    assert m and gr.validate_findings(m.group(1)) == []


@pytest.mark.parametrize("path", [prompt.FORMAT_FILE, prompt.DICTIONARY_FILE])
def test_agent_docs_neutral_and_locked(path):
    """두 조건이 같은 파일을 받는다. 분류 이름·근거 표기·정당한 지적 목록·K 항목·검수 기록 내용이 없다."""
    t = path.read_text(encoding="utf-8")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == prompt.AGENT_DOC_SHA256[path.name]
    banned = BANNED + ["K L", "P+AI", "PROBAST", "Kapoor", "검수", "정당한 지적", "justified", "known_issues",
                       "sealed", "봉인", "v1", "v2", "꼬리표"]
    hits = [w for w in banned if w.lower() in t.lower()]
    # 점검기 문제(K1~K7)·목록 번호(L1~L11)·사례 번호(E01~E18, C01~C30)가 낱말로 없다 (ICD 코드 K21.9·E11.9 등은 제외)
    hits += re.findall(r"(?<![\w.])(?:K[1-7]|L(?:1[01]|[1-9])|E(?:0[1-9]|1[0-8])|C(?:[0-2][0-9]|30))(?![\w.])", t)
    assert not hits, hits


def test_locked_files_match_success_criteria():
    """5단계에 고정한 지시문·채점기·채점 규칙·에이전트용 문서가 바뀌지 않았다 (run.py는 6단계에서 고치므로 잠그지 않음)."""
    doc = (ROOT / "docs" / "success_criteria_v2.md").read_text(encoding="utf-8")
    locked = dict(re.findall(r"^\| `?((?:experiment|docs)/\S+?)`? \| `([0-9a-f]{64})` \|", doc, re.M))
    assert set(locked) == {"experiment/agent_prompt.md", "experiment/grader.py", "experiment/scoring_rules.md",
                           "experiment/prompt.py", "docs/agent/design_format.md", "docs/agent/data_dictionary.md",
                           "docs/analysis_plan_v2.md"}
    assert "experiment/run.py" not in locked
    for f, h in locked.items():
        assert hashlib.sha256((ROOT / f).read_bytes()).hexdigest() == h, f
