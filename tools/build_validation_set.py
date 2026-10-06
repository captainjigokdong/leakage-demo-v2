"""채점기 검증 세트 (A)의 지적 목록을 v1 보고서에서 뽑는다 (5단계, 한 번만 실행).

- 입력: 공개된 v1 저장소(captainjigokdong/leakage-demo)의 `experiment/runs/reports/*.json` 119개와 `designs/variants/*.json` 20개.
  v1 코드는 실행하지 않는다. 보고서는 데이터로만 읽는다.
- 조건 파일(`experiment/runs/conditions.json`)과 v1 채점 결과(`results/`)는 읽지 않는다 (라벨을 조건을 가린 채 붙이기 위해).
- 출력: `tests/fixtures/validation_v1/entries.json` (지적 332개: id, 보고서 id, 변형, target, problem, 절반)
  과 `tests/fixtures/validation_v1/designs/` (v1 변형 20개 사본, 경로 해석에 씀).
- 개발/시험 절반은 보고서 단위로 나눈다 (같은 보고서의 지적이 양쪽에 섞이지 않게). 시드 20261006.

    python -m tools.build_validation_set /path/to/leakage-demo
"""
from __future__ import annotations

import json
import random
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "fixtures" / "validation_v1"
SEED = 20261006
_BLOCK = re.compile(r"```findings[^\n]*\n(.*?)```", re.S)


def entries_of(text: str) -> list[dict]:
    """보고서 본문의 마지막 findings 블록 (v1 지시문의 형식). 깨졌으면 빈 목록."""
    blocks = _BLOCK.findall(text)
    if not blocks:
        return []
    try:
        data = json.loads(blocks[-1])
    except json.JSONDecodeError:
        return []
    out = []
    for x in data if isinstance(data, list) else []:
        if not isinstance(x, dict) or not isinstance(x.get("problem"), str):
            continue
        tg = x.get("target")
        tgs = [tg] if isinstance(tg, str) else tg if isinstance(tg, list) else []
        out += [{"target": s, "problem": x["problem"]} for s in tgs if isinstance(s, str)]
    return out


def build(v1: Path) -> dict:
    reports = sorted((v1 / "experiment" / "runs" / "reports").glob("*.json"))
    rids = [p.stem for p in reports]
    rng = random.Random(SEED)
    test = set(rng.sample(rids, len(rids) // 2))
    rows = []
    for p in reports:
        r = json.loads(p.read_text(encoding="utf-8"))
        for e in entries_of(r["text"]):
            rows.append({"report_id": r["report_id"], "variant": r["variant"], **e,
                         "half": "test" if p.stem in test else "dev"})
    order = list(range(len(rows)))
    rng.shuffle(order)   # 라벨 순서를 보고서·변형 순서와 무관하게
    rows = [rows[i] for i in order]
    for i, row in enumerate(rows, 1):
        row["id"] = f"A{i:03d}"
    (OUT / "designs").mkdir(parents=True, exist_ok=True)
    for v in sorted({r["variant"] for r in rows}):
        shutil.copyfile(v1 / "designs" / "variants" / v, OUT / "designs" / v)
    return {"source": "captainjigokdong/leakage-demo experiment/runs/reports (v1, 119개)", "seed": SEED,
            "n_reports": len(reports), "n_test_reports": len(test),
            "entries": [{k: r[k] for k in ("id", "half", "report_id", "variant", "target", "problem")} for r in rows]}


def main(argv: list[str] | None = None) -> int:
    v1 = Path((argv or sys.argv[1:])[0])
    data = build(v1)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "entries.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"보고서 {data['n_reports']} (시험 절반 {data['n_test_reports']}), 지적 {len(data['entries'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
