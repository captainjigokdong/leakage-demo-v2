"""4단계 4a: 정당한 지적 목록 안(승인 C 전)의 칸 수·비중과 공개 18개 정답 칸과의 겹침을 센다.

전체 칸 = 설계서 JSON의 잎(값이 문자·수·참거짓이거나 그런 값의 목록인 자리) 수. 목록 칸이 그 잎이거나 그 위(부모)면
그 아래 잎을 모두 목록 칸으로 센다. 겹침은 경로가 같거나 한쪽이 다른 쪽의 위(부모)일 때다 (공개 패치의 op 경로 기준,
append로 새로 생기는 항목은 깨끗한 설계서에 없는 칸이라 겹치지 않는다).

실행: python -m tools.justified_v2
"""
from __future__ import annotations

import json
from pathlib import Path

from designs.inject import TYPE_KO
from designs.patches_v1_cases import V1_CASE_PATCHES
from tests.test_injectability_v2 import V1_ROWS

ROOT = Path(__file__).resolve().parent.parent
CLEAN = ROOT / "designs" / "clean_v2"
LIST = ROOT / "docs" / "justified_findings_v2.json"


def leaves(d, path: str = "") -> list[str]:
    if isinstance(d, dict):
        return [x for k, v in d.items() for x in leaves(v, f"{path}.{k}" if path else k)]
    if isinstance(d, list) and d and all(isinstance(x, dict) for x in d):
        return [x for i, e in enumerate(d)
                for x in leaves(e, f"{path}[name={e['name']}]" if "name" in e else f"{path}[{i}]")]
    return [path]


def related(a: str, b: str) -> bool:
    return a == b or a.startswith(b + ".") or a.startswith(b + "[") or b.startswith(a + ".") or b.startswith(a + "[")


def main() -> int:
    items = json.loads(LIST.read_text(encoding="utf-8"))["items"]
    answer = {cid: sorted({o["path"] for o in ops if o["op"] in ("set", "remove")}) for cid, ops in V1_CASE_PATCHES.items()}
    for p in sorted(CLEAN.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        cells = leaves(d)
        mine = [(it["id"], c) for it in items if p.stem in it["designs"]
                for c in (it["cells_by_design"][p.stem] if "cells_by_design" in it else it["cells"])]
        missing = [c for _, c in mine if not any(related(c, x) for x in cells)]
        covered = {x for x in cells if any(related(c, x) for _, c in mine)}
        over = sorted({f"{iid}~{cid}" for iid, c in mine for cid, paths in answer.items()
                       if d["design_type"] in TYPE_KO[V1_ROWS[cid]["design_types"]] for a in paths if related(c, a)})
        print(p.stem, f"목록 칸 {len(covered)} / 전체 {len(cells)} = {len(covered) / len(cells):.1%}",
              "| 목록 지정 칸", len(mine), "| 설계서에 없는 칸", missing, "| 정답 칸과 겹침", over)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
