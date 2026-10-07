"""7단계 채점과 분석 (v2: docs/analysis_plan_v2.md. v1 계획은 docs/step7_analysis_plan.md).

잠긴 채점기(experiment/grader.py)의 함수를 그대로 불러 쓴다. 채점 규칙은 여기서 바꾸지 않는다.
세 분석 묶음을 같은 방식으로 채점·요약한다.
  main   주 분석: 채택된 보고서 (빈칸 행은 분모에서 빠짐)
  first  첫 시도 분석: 행마다 첫 시도 보고서 (폐기된 시도 포함)
  blank  빈칸 = 미탐지 분석: 채택된 보고서 + 빈칸 행을 "지적 0개" 제출(`[]`)로
기록 형식: {"report_id", "variant", "findings": findings.json 내용 또는 None(파일 없음)}.

  python -m experiment.analyze        (암호: 환경 변수 또는 터미널 입력, 정답표는 메모리에서만 복호화)

7단계에서 더한 것 (2026-10-07 사용자 결정 1~3, 채점 전에 커밋):
  - 수치 차이 0에 가까운 배치: 봉인 기록(sealed/stage4b_record.enc)을 메모리에서만 풀어 (변형, 사례 id)만 꺼내
    grader.summarize(near_zero=...)에 넘긴다. 목록은 파일로 쓰지 않는다.
  - grades_*는 평문을 쓰지 않고 sealed/grades_<묶음>.enc로 봉인, 평문 SHA-256은 results/grades_sha256.json.
  - 조건별 실행 시간·턴 수(meta), 목록 우선으로 판정이 바뀐 배치 수 (기록용, 판정에 쓰지 않음).
  - summary·overview에 변형별 정답 칸·변형 이름이 들어 있는지 검사 (있으면 멈춤).
"""
from __future__ import annotations

import hashlib
import json
import re
import statistics
from pathlib import Path

from experiment import grader

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "experiment" / "runs"
RESULTS = ROOT / "results"
SEALED = ROOT / "sealed"
RECORD_4B = SEALED / "stage4b_record.enc"
NEAR_ZERO_N = 2                      # docs/stage4b_v2.md: 배치된 30조합 중 "0에 가까움" 2
_NEAR_KEY = re.compile(r"near|zero|0에|가까", re.I)
_CASE_ID = re.compile(r"(?<![A-Za-z0-9])[CE]\d{2}(?![0-9])")
EMPTY_FINDINGS = "[]"
SETS = ("main", "first", "blank")


def _read(d: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))]


def blank_rows(conditions: dict[str, dict], reports: list[dict]) -> list[str]:
    have = {r["report_id"] for r in reports}
    return sorted(rid for rid in conditions if rid not in have)


def fill_blanks(conditions: dict[str, dict], reports: list[dict]) -> list[dict]:
    """빈칸 행을 지적 0개 보고서로 채운다 (모든 배치 미탐지, 오경보 0)."""
    return reports + [{"report_id": rid, "variant": conditions[rid]["variant"], "findings": EMPTY_FINDINGS}
                      for rid in blank_rows(conditions, reports)]


def report_sets(conditions: dict[str, dict], runs: Path = RUNS) -> dict[str, list[dict]]:
    reports = _read(runs / "reports")
    return {"main": reports, "first": _read(runs / "first_attempt_reports"),
            "blank": fill_blanks(conditions, reports)}


def invoked_flags(conditions: dict[str, dict], runs: Path = RUNS) -> dict[str, dict[str, bool]]:
    """행별 checker_invoked: 채택(마지막) 시도와 첫 시도. 빈칸 행은 채택 없음."""
    out = {}
    for rid in conditions:
        m = json.loads((runs / "meta" / f"{rid}.json").read_text(encoding="utf-8"))
        att = m["attempts"]
        out[rid] = {"first": bool(att[0]["audit"]["checker_invoked"]),
                    "adopted": bool(att[-1]["audit"]["checker_invoked"]) if m["status"] == "done" else None,
                    "no_checker_after_denial": bool(att[-1].get("no_checker_after_denial")) if m["status"] == "done" else None}
    return out


def invoked_split(grades: list[dict], conditions: dict[str, dict], flags: dict[str, dict], which: str) -> dict:
    """(가)를 점검기를 부른 실행 / 부르지 않은 실행으로 나눈 탐지율 (참고 분석)."""
    ga = [g for g in grades if g["source"] == "report" and conditions[g["report_id"]]["condition"] == "가"]
    out = {}
    for label, want in (("invoked", True), ("not_invoked", False)):
        gs = [g for g in ga if flags[g["report_id"]][which] is want]
        out[label] = {"reports": len(gs), "detection": grader.detection(gs),
                      "holdout": grader.detection(gs, lambda d: d["holdout"])}
    out["not_invoked_with_denial"] = sum(1 for g in ga if flags[g["report_id"]][which] is False
                                         and flags[g["report_id"]]["no_checker_after_denial"])
    return out


def near_zero_from_record(rec, key_variants: dict) -> list[list[str]]:
    """봉인 기록에서 수치 차이 0에 가까운 배치를 [[변형, 사례 id], ...]로 꺼낸다 (내용은 출력하지 않음).
    이름에 near·zero·0에·가까가 든 키 아래의 목록 원소, 또는 그런 키가 참인 사전을 조각으로 보고,
    조각마다 사례 id 하나와 바탕(또는 변형 이름) 하나가 있으면 정답표의 배치와 맞춘다. 정확히 NEAR_ZERO_N개가 아니면 멈춘다."""
    placed = {(d["id"], v["base"]): fname for fname, v in key_variants.items() for d in v["defects"]}
    by_id = {d["id"]: fname for fname, v in key_variants.items() for d in v["defects"]}
    bases = sorted({v["base"] for v in key_variants.values()}, key=len, reverse=True)
    frags: list[str] = []

    def walk(o):
        if isinstance(o, dict):
            for k, val in o.items():
                if _NEAR_KEY.search(str(k)):
                    if val is True:
                        frags.append(json.dumps(o, ensure_ascii=False))
                    elif isinstance(val, list):
                        frags.extend(json.dumps(x, ensure_ascii=False) for x in val)
                    elif isinstance(val, dict):
                        frags.extend(json.dumps({kk: vv}, ensure_ascii=False) for kk, vv in val.items())
                walk(val)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(rec)
    out, bad = set(), 0
    for f in frags:
        ids = set(_CASE_ID.findall(f))
        vs = {v for v in key_variants if v in f}
        bs = {b for b in bases if re.search(rf"(?<![a-z_]){b}(?![a-z_])", f)}
        if len(ids) == 1 and len(vs) == 1 and by_id.get(next(iter(ids))) == next(iter(vs)):
            out.add((next(iter(vs)), next(iter(ids))))
        elif len(ids) == 1 and len(bs) == 1 and (next(iter(ids)), next(iter(bs))) in placed:
            i = next(iter(ids))
            out.add((placed[(i, next(iter(bs)))], i))
        elif len(ids) == 1 and not vs and not bs:
            # 대체 규칙 (7단계 채점 전 수정, 사용자 승인): 변형·바탕 이름이 없으면 정답표 결함 변형에
            # 정확히 한 번 배치된 사례 id일 때만 그 배치로 맞춘다. 0번이거나 2번 이상이면 멈춘다.
            i = next(iter(ids))
            hits = [fname for fname, v in key_variants.items() if v.get("kind", "defect") == "defect"
                    and any(d["id"] == i for d in v["defects"])]
            if len(hits) != 1:
                raise SystemExit(f"봉인 기록 조각의 사례 id가 정답표 결함 변형에 {len(hits)}번 배치됨 (기대 1). 멈춤.")
            out.add((hits[0], i))
        else:
            bad += 1
    if len(out) != NEAR_ZERO_N or bad:
        raise SystemExit(f"봉인 기록에서 0에 가까운 배치를 {len(out)}개 찾음 (기대 {NEAR_ZERO_N}, 맞추지 못한 조각 {bad}). 멈춤.")
    nz = [list(x) for x in sorted(out)]
    check_near_zero_placed(nz, key_variants)
    return nz


def check_near_zero_placed(near_zero: list[list[str]], key_variants: dict) -> None:
    """찾은 배치가 정답표의 결함 변형(kind = defect)에 실제로 배치된 사례인지 대조. 아니면 내용 없이 멈춘다."""
    ok = sum(v in key_variants and key_variants[v].get("kind", "defect") == "defect"
             and any(d["id"] == i for d in key_variants[v]["defects"]) for v, i in near_zero)
    if ok != len(near_zero) or len({tuple(x) for x in near_zero}) != len(near_zero):
        raise SystemExit(f"0에 가까운 배치 대조 실패: 정답표 결함 변형 배치와 맞는 것 {ok}/{len(near_zero)}. 멈춤.")


def narrative_fixed_drawn(key_variants: dict) -> list[str]:
    return sorted({d["id"] for v in key_variants.values() for d in v["defects"] if d["id"] in grader.NARRATIVE_FIXED_CASES})


def runtime_stats(conditions: dict[str, dict], runs: Path, which: str) -> dict:
    """조건별 실행 시간(초)·턴 수. which = adopted(채택 시도) | first(첫 시도). 기록용, 판정에 쓰지 않음."""
    vals: dict[str, dict[str, list]] = {c: {"seconds": [], "num_turns": []} for c in ("가", "나")}
    for rid, c in conditions.items():
        m = json.loads((runs / "meta" / f"{rid}.json").read_text(encoding="utf-8"))
        if which == "adopted" and m["status"] != "done":
            continue
        a = m["attempts"][-1 if which == "adopted" else 0]
        for f in ("seconds", "num_turns"):
            if a.get(f) is not None:
                vals[c["condition"]][f].append(a[f])
    st = lambda xs: ({"n": len(xs), "total": sum(xs), "mean": statistics.fmean(xs), "median": statistics.median(xs),
                      "min": min(xs), "max": max(xs)} if xs else {"n": 0})
    return {c: {f: st(xs) for f, xs in v.items()} for c, v in vals.items()}


def justified_first_changed(grades: list[dict], conditions: dict[str, dict]) -> dict:
    """목록 우선(참고값)으로 판정이 바뀐 배치-실행 수, 조건별."""
    return {c: sum(d["primary"] != d["primary_justified_first"] for g in grades if g["source"] == "report"
                   and conditions[g["report_id"]]["condition"] == c for d in g["defects"]) for c in ("가", "나")}


def _strings(o) -> set[str]:
    if isinstance(o, dict):
        return set(map(str, o)) | set().union(*map(_strings, o.values())) if o else set()
    if isinstance(o, list):
        return set().union(*map(_strings, o)) if o else set()
    return {o} if isinstance(o, str) else set()


def leak_check(objs: list, key_variants: dict) -> dict:
    """커밋할 평문(JSON)의 키·문자열 값 중 변형별 정답 칸(accept·support, 그 아래 칸 포함)·변형 이름과 같은 것을 센다.
    사례 id 수는 따로 센다 (기록)."""
    cells = {t for v in key_variants.values() for d in v["defects"]
             for t in d.get("accept_targets", []) + d.get("support_targets", [])}
    forms = cells | {t.replace(":", ".") for t in cells}
    strs = set().union(*map(_strings, objs)) if objs else set()
    hit = lambda x: any(x == f or x.startswith(f + ".") or x.startswith(f + ":") for f in forms)
    return {"answer_cells": sum(map(hit, strs)),
            "variant_names": sum(any(v in x for v in key_variants) for x in strs),
            "case_ids": len({i for x in strs for i in _CASE_ID.findall(x)})}


def _seal_json(obj, path: Path, password: str) -> str:
    """평문을 파일로 쓰지 않고 봉인한다. 평문 SHA-256을 돌려준다."""
    from tools.seal import encrypt_bytes
    blob = (json.dumps(obj, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    path.write_bytes(encrypt_bytes(blob, password))
    return hashlib.sha256(blob).hexdigest()


def _comparable(summary: dict) -> dict:
    return {k: v for k, v in summary.items() if k not in ("invoked_split", "extra")}


def overview_row(summary: dict) -> dict:
    """보고서 맨 앞 표의 한 줄: H1a·H1b·H1c·H2a 판정(주 분석)과 H2b 기술, 보조 분석(판정에 쓰지 않음)."""
    row = {}
    for label, h in (("primary", summary["hypotheses"]), ("secondary", summary["secondary"])):
        row[label] = {k: {x: h[k].get(x) for x in ("diff", "ci95", "met", "n_units")} for k in ("H1a", "H1c", "H2a")}
        row[label]["H1b"] = dict(h["H1b"])
        row[label]["H2b"] = {c: {x: h["H2b"][c].get(x) for x in ("diff", "ci95")} for c in ("가", "나")}
        row[label]["detection"] = {c: summary["conditions"][c]["detection"]["all"][label] for c in ("가", "나")}
    row["checker_only_holdout"] = summary["checker_only"]["holdout"]["primary"]
    row["unknown_kind"] = {c: summary["conditions"][c]["counts"]["n_unknown_kind"] for c in ("가", "나")}
    row["reports"] = {c: summary["conditions"][c]["reports"] for c in ("가", "나")}
    return row


def run(password: str, out: Path = RESULTS, runs: Path = RUNS, sealed: Path = SEALED,
        record: Path = RECORD_4B) -> dict:
    from tools.seal import decrypt_bytes
    key = grader.load_answer_key(password)
    bad = grader.verify_variants(key["variants"])
    if bad:
        raise SystemExit(f"변형 파일 해시 불일치 {len(bad)}건. 멈춤.")
    # 봉인 기록 탐색·정답표 대조는 채점(grade_all)보다 먼저 한다. 실패하면 아무 결과도 쓰지 않고 멈춘다.
    near_zero = near_zero_from_record(json.loads(decrypt_bytes(record.read_bytes(), password)), key["variants"])
    conditions = json.loads((runs / "conditions.json").read_text(encoding="utf-8"))
    checker = _read(runs / "checker")
    flags = invoked_flags(conditions, runs)
    out.mkdir(parents=True, exist_ok=True)
    overview = {"variants_verified": len(key["variants"]), "near_zero_n": len(near_zero),
                "narrative_fixed_drawn": narrative_fixed_drawn(key["variants"]),
                "blank_rows": {rid: conditions[rid]["condition"] for rid in blank_rows(conditions, _read(runs / "reports"))},
                "graded_rows": {}, "sets": {}}
    hashes, comp = {}, {}
    for name, reports in report_sets(conditions, runs).items():
        grades = grader.grade_all(reports, key["variants"], checker)
        summary = grader.summarize(grades, conditions, key["variants"], near_zero=near_zero)
        if name in ("main", "first"):
            summary["invoked_split"] = invoked_split(grades, conditions, flags, "adopted" if name == "main" else "first")
        summary["extra"] = {"runtime": runtime_stats(conditions, runs, "first" if name == "first" else "adopted"),
                            "justified_first_changed": justified_first_changed(grades, conditions),
                            "note": "기록용, 판정에 쓰지 않음 (7단계 사용자 결정 3)"}
        hashes[f"grades_{name}.json"] = _seal_json(grades, sealed / f"grades_{name}.enc", password)
        overview["graded_rows"][name] = sum(g["source"] == "report" for g in grades)
        (out / f"summary_{name}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        overview["sets"][name] = overview_row(summary)
        comp[name] = (sorted((json.dumps({k: v for k, v in g.items() if k != "report_id"}, sort_keys=True, ensure_ascii=False)
                              for g in grades)), _comparable(summary))
    overview["sets_identical"] = {n: comp[n] == comp["main"] for n in ("first", "blank")}
    overview["variant_hashes_verified"] = True
    (out / "overview.json").write_text(json.dumps(overview, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out / "grades_sha256.json").write_text(json.dumps(
        {"note": "평문 grades_*.json의 SHA-256. 평문은 커밋하지 않고 sealed/grades_<묶음>.enc로 봉인 (7단계 사용자 결정 2)",
         "sha256": hashes}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    objs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(out.glob("*.json"))]
    overview["leak_check"] = leak_check(objs, key["variants"])
    if overview["leak_check"]["answer_cells"] or overview["leak_check"]["variant_names"]:
        raise SystemExit(f"커밋할 평문에 정답 칸·변형 이름이 있음 {overview['leak_check']}. 멈춤.")
    return overview


def main() -> int:
    from tools.seal import get_password
    print(json.dumps(run(get_password()), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
