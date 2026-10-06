"""검증 세트 (A) 채점: 라벨과 v2 채점기의 해석·분류가 얼마나 같은가 (5단계).

(A)가 검증하는 것: target → 항목 해석(`grader.resolve`, 경로 읽기)과 문제 종류 핵심어 분류(`grader.classify`, 보조 분석 전용).
칸 넓이·우선순위·kind는 (B) 시험(`tests/test_grader.py`)이 검증한다.

- 항목 일치: 라벨 항목 == item_of(resolve(target)). 라벨 "묶음"은 resolve가 최상위 묶음, "대상 불명"은 None이어야 일치.
- Q 일치(기준): 라벨 Q가 모두 채점기 Q 안에 있음 (라벨 Q가 없는 지적은 분모에서 뺌).
- 함께 보고(기준 아님): 엄격 일치(집합이 같음), 라벨에 없는 Q를 더 붙인 비율, 지적당 평균 Q 개수.

    python -m tools.validation_report dev|test|all
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from experiment import grader as gr

ROOT = Path(__file__).resolve().parent.parent
VSET = ROOT / "tests" / "fixtures" / "validation_v1"
ITEM_MIN, Q_MIN = 0.95, 0.85   # 시험 절반 통과 기준 (5단계 계획, 사용자 승인)


def load() -> tuple[list[dict], dict, dict]:
    entries = json.loads((VSET / "entries.json").read_text(encoding="utf-8"))["entries"]
    labels = json.loads((VSET / "labels.json").read_text(encoding="utf-8"))["labels"]
    designs = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in (VSET / "designs").glob("*.json")}
    return entries, labels, designs


def got_item(e: dict, designs: dict) -> str:
    d = designs[e["variant"]]
    p = gr.resolve(e["target"], d)
    if p is None:
        return "대상 불명"
    return "묶음" if gr.is_bundle(p, d) else gr.item_of(p)


def rows(half: str = "all") -> list[dict]:
    entries, labels, designs = load()
    out = []
    for e in entries:
        if half != "all" and e["half"] != half:
            continue
        d = designs[e["variant"]]
        p = gr.resolve(e["target"], d)
        lab = labels[e["id"]]
        out.append({"id": e["id"], "half": e["half"], "label_item": lab["item"], "item": got_item(e, designs),
                    "label_qs": set(lab["qs"]), "qs": set(gr.classify(e["problem"], p))})
    return out


def metrics(rs: list[dict]) -> dict:
    n = len(rs)
    item_ok = sum(r["item"] == r["label_item"] for r in rs)
    withq = [r for r in rs if r["label_qs"]]
    q_ok = sum(r["label_qs"] <= r["qs"] for r in withq)
    exact = sum(r["label_qs"] == r["qs"] for r in rs)
    extra = sum(bool(r["qs"] - r["label_qs"]) for r in rs)
    return {"n": n, "item_agree": item_ok / n, "item_ok": item_ok,
            "q_n": len(withq), "q_agree": q_ok / len(withq), "q_ok": q_ok,
            "q_exact": exact / n, "q_extra_rate": extra / n,
            "mean_q_label": sum(len(r["label_qs"]) for r in rs) / n,
            "mean_q_grader": sum(len(r["qs"]) for r in rs) / n,
            "passed": item_ok / n >= ITEM_MIN and q_ok / len(withq) >= Q_MIN}


def main(argv: list[str] | None = None) -> int:
    half = (argv or sys.argv[1:] or ["all"])[0]
    rs = rows(half)
    print(json.dumps(metrics(rs), ensure_ascii=False, indent=1))
    for r in rs:
        if r["item"] != r["label_item"] or not r["label_qs"] <= r["qs"]:
            print(r["id"], "항목", r["label_item"], "→", r["item"], "| Q", sorted(r["label_qs"]), "→", sorted(r["qs"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
