"""7단계 사후 분석 (analysis_plan_v2.md에 없는 계산, 결과를 본 뒤 더함 — 보고서에 "사후 분석"으로 표시).

채점 결과(sealed/grades_main.enc)와 analyze.py는 고치지 않는다. grades는 메모리에서만 풀고 평문 SHA-256을
results/grades_sha256.json과 대조한다. 숫자만 results/posthoc_7.json에 쓰고, 정답 칸·변형 이름이 있으면 멈춘다.
  1. 목록에 흡수된 지적 수(관대판·엄격판)를 깨끗한 변형 / 결함 변형으로 나눈 값, 조건별.
  2. 참고값 중 summary에 조건별 값이 없는 것(가정 칸 겹침 제외, 수치 차이 0 배치 제외, 서술 수정 사례 제외)의
     조건별 탐지 수/분모 (전체·공개·보류).

  python -m experiment.posthoc_7        (암호: 환경 변수 또는 터미널 입력)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiment import analyze, grader

OUT = analyze.RESULTS / "posthoc_7.json"


def load_grades(password: str, name: str = "main", sealed: Path = analyze.SEALED, results: Path = analyze.RESULTS) -> list[dict]:
    from tools.seal import decrypt_bytes
    blob = decrypt_bytes((sealed / f"grades_{name}.enc").read_bytes(), password)
    want = json.loads((results / "grades_sha256.json").read_text(encoding="utf-8"))["sha256"][f"grades_{name}.json"]
    if hashlib.sha256(blob).hexdigest() != want:
        raise SystemExit(f"grades_{name} 평문 SHA-256 불일치. 멈춤.")
    return json.loads(blob)


def absorbed_split(grades: list[dict], conditions: dict, key_variants: dict) -> dict:
    out = {}
    for c in ("가", "나"):
        gs = [g for g in grades if g["source"] == "report" and conditions[g["report_id"]]["condition"] == c]
        out[c] = {}
        for label, clean in (("clean", True), ("defect", False)):
            sel = [g for g in gs if (not key_variants[g["variant"]]["defects"]) == clean]
            out[c][label] = {"reports": len(sel),
                             "n_justified": sum(g["counts"]["n_justified"] for g in sel),
                             "n_justified_strict": sum(g["counts"]["n_justified_strict"] for g in sel)}
    return out


def _count(gs: list[dict], keep) -> dict:
    p = [(g, d) for g in gs for d in g["defects"] if keep(g, d)]
    tally = lambda f: {"detected": sum(d["primary"] for g, d in p if f(d)), "n": sum(1 for g, d in p if f(d))}
    return {"all": tally(lambda d: True), "public": tally(lambda d: not d["holdout"]),
            "holdout": tally(lambda d: d["holdout"])}


def reference_counts(grades: list[dict], conditions: dict, near_zero: list[list[str]]) -> dict:
    nz = {tuple(x) for x in near_zero}
    keeps = {"without_assumption_overlap_cases": lambda g, d: d["id"] not in grader.ASSUMPTION_OVERLAP_CASES,
             "without_near_zero": lambda g, d: (g["variant"], d["id"]) not in nz,
             "without_narrative_fixed": lambda g, d: d["id"] not in grader.NARRATIVE_FIXED_CASES}
    out = {}
    for name, keep in keeps.items():
        out[name] = {c: _count([g for g in grades if g["source"] == "report"
                                and conditions[g["report_id"]]["condition"] == c], keep) for c in ("가", "나")}
    return out


def run(password: str, out: Path = OUT) -> dict:
    from tools.seal import decrypt_bytes
    key = grader.load_answer_key(password)["variants"]
    grades = load_grades(password)
    conditions = json.loads((analyze.RUNS / "conditions.json").read_text(encoding="utf-8"))
    near_zero = analyze.near_zero_from_record(json.loads(decrypt_bytes(analyze.RECORD_4B.read_bytes(), password)), key)
    res = {"note": "사후 분석 (analysis_plan_v2.md에 없음, 결과를 본 뒤 더함). 판정에 쓰지 않음. 주 분석 grades.",
           "absorbed_by_variant_type": absorbed_split(grades, conditions, key),
           "reference_counts_primary": reference_counts(grades, conditions, near_zero)}
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
