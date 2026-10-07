"""7단계 사후 분석 2 (analysis_plan_v2.md에 없음, 결과를 본 뒤 더함 — 보고서에 "사후 분석"으로 표시).

채점 결과·analyze.py·posthoc_7.json은 고치지 않는다. grades는 메모리에서만 푼다 (posthoc_7.load_grades, SHA-256 대조).
숫자만 results/posthoc_7b.json에 쓰고, 정답 칸·변형 이름·사례 id가 있으면 멈춘다.
  1. 깨끗한 변형에서 목록에 흡수된 지적을 오경보로 함께 셌을 때의 보고서당 평균, 조건별
     (= (관대판 오경보 수 + 흡수된 지적 수) / 깨끗한 변형 보고서 수. 오경보는 항목 단위, 흡수는 지적 단위라 단순 합).
  2. 놓친 배치-실행 수와, 그중 결함 칸(관대판 정답 칸)을 "가정"·"점검 불가"로 적은 제출 수, 조건별.

  python -m experiment.posthoc_7b        (암호: 환경 변수 또는 터미널 입력)
"""
from __future__ import annotations

import json
from pathlib import Path

from experiment import analyze, grader
from experiment.posthoc_7 import load_grades

OUT = analyze.RESULTS / "posthoc_7b.json"


def absorbed_as_fa(grades: list[dict], conditions: dict, key_variants: dict) -> dict:
    out = {}
    for c in ("가", "나"):
        gs = [g for g in grades if g["source"] == "report" and conditions[g["report_id"]]["condition"] == c
              and not key_variants[g["variant"]]["defects"]]
        fa = sum(len(g["false_alarms"]) for g in gs)
        ab = sum(g["counts"]["n_justified"] for g in gs)
        out[c] = {"reports": len(gs), "false_alarms": fa, "absorbed": ab,
                  "mean_per_report_fa_only": fa / len(gs), "mean_per_report_with_absorbed": (fa + ab) / len(gs)}
    return out


def misses_with_defect_cell_non_problem(grades: list[dict], conditions: dict, key_variants: dict,
                                        reports: dict[str, dict]) -> dict:
    out = {c: {"missed": 0, "defect_cell_as_assumption_or_unable": 0} for c in ("가", "나")}
    designs: dict[str, dict] = {}
    for g in grades:
        if g["source"] != "report":
            continue
        c = conditions[g["report_id"]]["condition"]
        for d in g["defects"]:
            if d["primary"]:
                continue
            out[c]["missed"] += 1
            v = g["variant"]
            design = designs.setdefault(v, grader.load_design(v))
            kd = next(x for x in key_variants[v]["defects"] if x["id"] == d["id"])
            acc = grader._accept_keys(kd, design, False)
            raw, _, _ = grader.parse_findings(reports[g["report_id"]]["findings"])
            if any(x["kind"] in ("가정", "점검 불가") and (p := grader.resolve(x["target"], design)) is not None
                   and grader._any(p, acc, design) for x in raw):
                out[c]["defect_cell_as_assumption_or_unable"] += 1
    return out


def run(password: str, out: Path = OUT) -> dict:
    key = grader.load_answer_key(password)["variants"]
    grades = load_grades(password)
    conditions = json.loads((analyze.RUNS / "conditions.json").read_text(encoding="utf-8"))
    reports = {r["report_id"]: r for r in analyze._read(analyze.RUNS / "reports")}
    res = {"note": "사후 분석 2 (analysis_plan_v2.md에 없음, 결과를 본 뒤 더함). 판정에 쓰지 않음. 주 분석 grades.",
           "clean_absorbed_as_false_alarm": absorbed_as_fa(grades, conditions, key),
           "misses": misses_with_defect_cell_non_problem(grades, conditions, key, reports)}
    lc = analyze.leak_check([res], key)
    if lc["answer_cells"] or lc["variant_names"] or lc["case_ids"]:
        raise SystemExit(f"사후 분석 결과에 정답 칸·변형 이름·사례 id가 있음 {lc}. 멈춤.")
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return res


def main() -> int:
    from tools.seal import get_password
    print(json.dumps(run(get_password()), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
