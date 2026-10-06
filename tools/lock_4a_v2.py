"""4a 잠정 잠금: 정당한 지적 목록·깨끗한 설계서 8개(잠정, 4b 첫 순서의 봉인 확인 뒤 확정)와
4b에서 바꾸지 않는 추첨·배치 스크립트의 해시를 docs/lock_4a_v2.json에 적는다. 시험: tests/test_build_v2.py.

실행: python -m tools.lock_4a_v2
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from designs import build_v2 as B

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "docs" / "lock_4a_v2.json"
PROVISIONAL = ["docs/justified_findings_v2.json"] + [f"designs/clean_v2/{n}.json" for n in B.CLEAN_NAMES]
FIXED_FOR_4B = ["designs/build_v2.py", "designs/answer_key_v2.py"]


def sha(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def main() -> int:
    lock = {
        "status": "잠정 — 4b 첫 순서의 봉인 확인(docs/phases.md 4b 1)~3)) 뒤 확정. 그때 설계서를 고치거나 목록에 넣으면 다시 잠그고 이유를 적는다",
        "date": "2026-10-06",
        "provisional": {r: sha(r) for r in PROVISIONAL},
        "fixed_for_4b": {r: sha(r) for r in FIXED_FOR_4B},
        "seeds": {"DRAW_SEED": B.DRAW_SEED, "PLACE_SEED": B.PLACE_SEED},
    }
    LOCK.write_text(json.dumps(lock, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for g in ("provisional", "fixed_for_4b"):
        for r, h in lock[g].items():
            print(g, r, h)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
