"""7단계 분석 스크립트 시험. 진짜 정답표는 쓰지 않는다 (test_grader의 가짜 실행 재사용)."""
from __future__ import annotations

import json

import pytest

from experiment import analyze as an
from experiment import grader as gr
from tests.test_grader import _fake_run as _grader_fake_run


def _fake_run():
    """test_grader의 가짜 실행 + 실제 조건표처럼 variant 칸."""
    reports, conds, key, designs = _grader_fake_run()
    for r in reports:
        conds[r["report_id"]]["variant"] = r["variant"]
    return reports, conds, key, designs


def test_blank_row_counts_as_miss_without_false_alarms():
    reports, conds, key, designs = _fake_run()
    dropped = next(r for r in reports if conds[r["report_id"]]["condition"] == "가" and key[r["variant"]]["defects"])
    kept = [r for r in reports if r is not dropped]
    assert an.blank_rows(conds, kept) == [dropped["report_id"]]
    filled = an.fill_blanks(conds, kept)
    assert len(filled) == len(reports)
    g = next(x for x in gr.grade_all(filled, key, designs=dict(designs)) if x["report_id"] == dropped["report_id"])
    assert g["format_error"] is None and g["n_entries"] == 0 and g["false_alarms"] == []
    assert g["defects"] and not any(d["primary"] or d["secondary"] for d in g["defects"])


def test_blank_analysis_detection_not_higher_than_main():
    reports, conds, key, designs = _fake_run()
    kept = [r for r in reports if not (conds[r["report_id"]]["condition"] == "가" and r["variant"] == "vA.json")]
    assert kept != reports
    s_main = gr.summarize(gr.grade_all(kept, key, designs=dict(designs)), conds, key)
    s_blank = gr.summarize(gr.grade_all(an.fill_blanks(conds, kept), key, designs=dict(designs)), conds, key)
    a, b = s_main["conditions"]["가"]["detection"]["all"], s_blank["conditions"]["가"]["detection"]["all"]
    assert b["n"] > a["n"] and b["primary"] <= a["primary"]


def test_overview_row_and_invoked_split():
    reports, conds, key, designs = _fake_run()
    grades = gr.grade_all(reports, key, designs=dict(designs))
    s = gr.summarize(grades, conds, key)
    row = an.overview_row(s)
    for meas in ("primary", "secondary"):
        assert set(row[meas]["H2b"]) == {"가", "나"}
        assert all(isinstance(row[meas][k]["met"], bool) for k in ("H1a", "H1b", "H1c", "H2a"))
    assert row["unknown_kind"] == {"가": 4, "나": 8}   # 핵심어 없는 설명: (가) 2개·(나) 4개 × 반복 2
    ga = [rid for rid, c in conds.items() if c["condition"] == "가"]
    flags = {rid: {"adopted": rid != ga[0], "first": True, "no_checker_after_denial": rid == ga[0]} for rid in conds}
    sp = an.invoked_split(grades, conds, flags, "adopted")
    assert sp["not_invoked"]["reports"] == 1 and sp["invoked"]["reports"] == len(ga) - 1
    assert sp["not_invoked_with_denial"] == 1


@pytest.mark.skipif(not (an.RUNS / "conditions.json").exists(),
                    reason="실행 기록 없음 (v1 기록은 v1 저장소에만 보존)")
def test_real_run_files_without_key():
    """실제 실행 기록의 구조만 확인 (정답표 불필요): 첫 시도 = 조건표 행 수, 모든 행에 checker_invoked.
    빈칸 행 수는 실행 기록(meta)의 상태로 따로 센 값과 같아야 한다 (폐기·재실행 소진 = 빈칸, 6단계 사용자 승인)."""
    conds = json.loads((an.RUNS / "conditions.json").read_text(encoding="utf-8"))
    sets = an.report_sets(conds)
    assert len(sets["first"]) == len(conds) == len(sets["blank"])
    status = {rid: json.loads((an.RUNS / "meta" / f"{rid}.json").read_text(encoding="utf-8"))["status"] for rid in conds}
    assert len(an.blank_rows(conds, sets["main"])) == sum(s in ("discarded", "failed") for s in status.values())
    flags = an.invoked_flags(conds)
    assert set(flags) == set(conds)
    assert all(flags[r]["adopted"] is None for r in an.blank_rows(conds, sets["main"]))


# ---------------------------------------------------------------- 7단계에서 더한 것 (가짜 자료로 끝까지)

def _fake_runs_dir(tmp_path, reports, conds, checker=()):
    runs = tmp_path / "runs"
    for d in ("reports", "first_attempt_reports", "checker", "meta"):
        (runs / d).mkdir(parents=True)
    (runs / "conditions.json").write_text(json.dumps(conds, ensure_ascii=False), encoding="utf-8")
    for i, r in enumerate(reports):
        for d in ("reports", "first_attempt_reports"):
            (runs / d / f"{r['report_id']}.json").write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
        (runs / "meta" / f"{r['report_id']}.json").write_text(json.dumps(
            {"status": "done", "attempts": [{"audit": {"checker_invoked": conds[r["report_id"]]["condition"] == "가"},
                                             "seconds": 10.0 + i, "num_turns": 5 + i}]}), encoding="utf-8")
    for c in checker:
        (runs / "checker" / f"{c['report_id']}.json").write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    return runs


def _patch_key(monkeypatch, key, designs):
    monkeypatch.setattr(gr, "load_answer_key", lambda pw: {"variants": key})
    monkeypatch.setattr(gr, "verify_variants", lambda kv: [])
    monkeypatch.setattr(gr, "load_design", lambda fname: designs[fname])


def _record(tmp_path, rec, pw="시험암호"):
    from tools.seal import encrypt_bytes
    p = tmp_path / "rec.enc"
    p.write_bytes(encrypt_bytes(json.dumps(rec, ensure_ascii=False).encode("utf-8"), pw))
    return p


@pytest.mark.parametrize("rec", [
    {"recount": {"near_zero": [["E02", "aki_a"], ["E06", "readmit_c"]], "threshold": 10}},
    {"rows": [{"case": "E02", "base": "aki_a", "diff": 3, "near_zero": True},
              {"case": "E06", "base": "readmit_c", "diff": 1, "near_zero": True},
              {"case": "E13", "base": "aki_b", "diff": 900, "near_zero": False}]},
    {"0에 가까움": ["E02×aki_a", "E06×readmit_c"]},
])
def test_near_zero_from_record_shapes(rec):
    _, _, key, _ = _fake_run()
    an.NEAR_ZERO_N = 2
    assert an.near_zero_from_record(rec, key) == [["vA.json", "E02"], ["vB.json", "E06"]]


def test_near_zero_from_record_stops_unless_exact():
    _, _, key, _ = _fake_run()
    with pytest.raises(SystemExit):
        an.near_zero_from_record({"near_zero": [["E02", "aki_a"]]}, key)
    with pytest.raises(SystemExit):
        an.near_zero_from_record({"exclusions": [["E02", "aki_a"], ["E06", "readmit_c"]]}, key)


def test_run_end_to_end_with_fake_key(tmp_path, monkeypatch):
    """참고값 8종·조건별 보고 항목이 모두 계산되고, grades는 봉인만, 커밋할 평문에 정답 칸·변형 이름이 없다."""
    import copy
    from tools.seal import decrypt_bytes
    reports, conds, key, designs = _fake_run()
    key = copy.deepcopy(key)
    key["vH.json"]["defects"][0]["id"] = "C18"
    _patch_key(monkeypatch, key, designs)
    ga = [r for r in reports if conds[r["report_id"]]["condition"] == "가"]
    checker = [{"report_id": r["report_id"], "variant": r["variant"], "exit_code": 0, "checker": None} for r in ga]
    runs = _fake_runs_dir(tmp_path, reports, conds, checker)
    out, sealed = tmp_path / "results", tmp_path / "sealed"
    sealed.mkdir()
    rec = _record(tmp_path, {"near_zero": [["E02", "aki_a"], ["E06", "readmit_c"]]})
    ov = an.run("시험암호", out=out, runs=runs, sealed=sealed, record=rec)

    assert ov["graded_rows"] == {"main": 20, "first": 20, "blank": 20}
    assert ov["sets_identical"] == {"first": True, "blank": True}
    assert ov["near_zero_n"] == 2 and ov["narrative_fixed_drawn"] == ["C18"]
    assert ov["leak_check"]["answer_cells"] == 0 and ov["leak_check"]["variant_names"] == 0
    assert sorted(p.name for p in out.glob("*.json")) == ["grades_sha256.json", "overview.json", "summary_blank.json",
                                                          "summary_first.json", "summary_main.json"]   # grades 평문 없음
    hashes = json.loads((out / "grades_sha256.json").read_text(encoding="utf-8"))["sha256"]
    import hashlib
    for n in an.SETS:
        blob = decrypt_bytes((sealed / f"grades_{n}.enc").read_bytes(), "시험암호")
        assert hashlib.sha256(blob).hexdigest() == hashes[f"grades_{n}.json"]

    s = json.loads((out / "summary_main.json").read_text(encoding="utf-8"))
    ref = s["reference"]
    # 참고값 8종 (턴 상한 제외는 걸린 실행이 없으면 None)
    for k in ("strict_breadth", "justified_first", "without_assumption_overlap_cases", "without_near_zero",
              "without_narrative_fixed", "fa_without_k1_k5", "fa_with_too_broad", "fa_strict"):
        assert ref[k] is not None, k
    assert "without_turn_capped" in ref and ref["without_turn_capped"] is None
    assert ref["without_near_zero"]["H1a"]["n_units"] == 1     # vA·vB 배치가 빠짐
    # 조건별 보고 항목
    for c in ("가", "나"):
        cs = s["conditions"][c]
        assert {"all", "public", "holdout"} <= set(cs["detection"]) and "by_question" in cs["detection"]["all"]
        for m in ("primary", "secondary", "primary_strict", "primary_justified_first"):
            assert m in cs["detection"]["all"]
        for side in ("clean", "defect"):
            assert {"false_alarms", "false_alarms_strict", "false_alarms_no_k", "false_alarms_with_broad",
                    "legit_total"} <= set(cs["false_alarms"][side])
        for k in ("n_justified", "n_justified_strict", "detections_via_bundle_or_exception_only", "n_too_broad",
                  "n_problem", "n_assumption", "n_unable", "n_defect_cell_assumption", "n_defect_cell_unable",
                  "n_assumption_cell_problem", "n_unresolved", "n_not_graded", "n_support", "n_unknown_kind",
                  "n_sibling_of_defect", "n_malformed", "format_errors", "empty_list", "format_retries", "turn_capped"):
            assert k in cs["counts"], k
        assert cs["stability"]["primary"] is not None
        rt = s["extra"]["runtime"][c]
        assert rt["seconds"]["n"] == 10 and rt["num_turns"]["n"] == 10
    assert set(s["extra"]["justified_first_changed"]) == {"가", "나"}
    assert s["checker_only"]["runs"] == 10 and "holdout" in s["checker_only"]
    assert set(s["hypotheses"]) == {"H1a", "H1b", "H1c", "H2a", "H2b"}


def test_bootstrap_paired_10000_seed():
    assert gr.BOOTSTRAP_N == 10_000 and gr.BOOTSTRAP_SEED == 20261006
    import inspect
    src = inspect.getsource(gr._boot)
    # 짝지은 추출: 같은 idx로 두 조건을 같이 뽑는다
    assert "na[idx]" in src and "nb[idx]" in src and src.count("integers(") == 1
    r = gr._boot(["a", "b", "c"], lambda u: (1, 2), lambda u: (0, 2))
    assert r["seed"] == 20261006 and r["n_boot"] == 10_000 and r["diff"] == 0.5


def test_leak_check_catches_cells_and_variant_names():
    _, _, key, _ = _fake_run()
    assert an.leak_check([{"invoked_split": 1, "x": "split은 단어"}], key) == {"answer_cells": 0, "variant_names": 0, "case_ids": 0}
    lc = an.leak_check([{"a": ["features.cr_last", "split.key"], "vA.json": 1, "b": "E02"}], key)
    assert lc == {"answer_cells": 2, "variant_names": 1, "case_ids": 1}


def test_near_zero_from_record_id_only_fallback():
    """대체 규칙 (7단계 채점 전 수정, 사용자 승인): 변형·바탕 이름이 없는 조각은 사례 id가 결함 변형에 정확히 한 번 배치될 때만 맞춘다."""
    _, _, key, _ = _fake_run()
    an.NEAR_ZERO_N = 2
    assert an.near_zero_from_record({"near_zero": ["E02 차이 작음", "E06 차이 작음"]}, key) == [["vA.json", "E02"], ["vB.json", "E06"]]
    # 0번 배치
    with pytest.raises(SystemExit):
        an.near_zero_from_record({"near_zero": ["E02 차이 작음", "E09 차이 작음"]}, key)
    # 2번 이상 배치
    key2 = dict(key)
    key2["vE.json"] = json.loads(json.dumps(key["vA.json"]))
    with pytest.raises(SystemExit):
        an.near_zero_from_record({"near_zero": ["E02 차이 작음", "E06 차이 작음"]}, key2)
    # 깨끗한 변형의 배치는 세지 않는다 (kind != defect)
    key3 = dict(key)
    key3["vF.json"] = dict(json.loads(json.dumps(key["vA.json"])), kind="clean")
    assert an.near_zero_from_record({"near_zero": ["E02 차이 작음", "E06 차이 작음"]}, key3) == [["vA.json", "E02"], ["vB.json", "E06"]]


def test_near_zero_must_be_placed_defect():
    _, _, key, _ = _fake_run()
    an.check_near_zero_placed([["vA.json", "E02"], ["vB.json", "E06"]], key)
    for bad in ([["vA.json", "E06"], ["vB.json", "E06"]],      # 그 변형에 없는 사례
                [["vC.json", "E02"], ["vB.json", "E06"]],      # 깨끗한 변형
                [["vZ.json", "E02"], ["vB.json", "E06"]],      # 정답표에 없는 변형
                [["vA.json", "E02"], ["vA.json", "E02"]]):     # 중복
        with pytest.raises(SystemExit):
            an.check_near_zero_placed(bad, key)
    # 기록에 배치되지 않은 조합 조각이 섞여 있으면 멈춘다
    with pytest.raises(SystemExit):
        an.near_zero_from_record({"near_zero": [["E02", "aki_a"], ["E06", "readmit_c"], ["E02", "aki_c"]]}, key)


def test_near_zero_checked_before_grading(tmp_path, monkeypatch):
    reports, conds, key, designs = _fake_run()
    _patch_key(monkeypatch, key, designs)
    called = []
    monkeypatch.setattr(gr, "grade_all", lambda *a, **k: called.append(1) or [])
    runs = _fake_runs_dir(tmp_path, reports, conds)
    out = tmp_path / "results"
    rec = _record(tmp_path, {"near_zero": [["E02", "aki_a"], ["E13", "readmit_c"]]})
    with pytest.raises(SystemExit):
        an.run("시험암호", out=out, runs=runs, sealed=tmp_path, record=rec)
    assert called == [] and not out.exists()
