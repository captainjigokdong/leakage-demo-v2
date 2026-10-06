"""4a 잠금: 정당한 지적 목록·깨끗한 설계서 8개와 4b에서 바꾸지 않는 추첨·배치 스크립트의 해시를
docs/lock_4a_v2.json에 적는다. 시험: tests/test_build_v2.py.

4a에서 잠정으로 잠그고(`provisional_4a`), 4b 첫 순서의 봉인 확인 뒤 확정했다(`locked`, 2026-10-06).
4b 봉인 확인의 배치 제외 목록은 봉인 기록(sealed/stage4b_record.enc) 안에만 있고, 여기에는 그 해시만 적는다.

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


PROVISIONAL_4A = {
    "docs/justified_findings_v2.json": "3bdfbbbbb0cc2bae0818ad91f77c16e11deb88d79fa47a3dddf872624e8be940",
    "designs/clean_v2/aki_a.json": "71758667594071e9a24e4729dbf7cf98b5a32ca7052ea35033a2dc9eb4967687",
    "designs/clean_v2/aki_b.json": "9132e7fd0060f3ebbf2bc7850d50eb3ef6c6615780af359b1465c616550ccfa9",
    "designs/clean_v2/aki_c.json": "4d8e7fb66cab2e0fb350e39f11c86986051a023b274c1c765b860e8f36e1cf13",
    "designs/clean_v2/aki_d.json": "e2ed1b47dccb17da908e171216c59719cb8ee6c92a27e07a73d50c96193e7661",
    "designs/clean_v2/readmit_a.json": "022c6d7e604e37ab2a46dceefd733fd389a09780e5ee829b4d13c8cd6bd2b2e1",
    "designs/clean_v2/readmit_b.json": "23dadcc77ce98082f15bbeef09efd9e4247a25bb3b2f03951d9e500695e98961",
    "designs/clean_v2/readmit_c.json": "a7d5ad66670f660723779aa44e654b554e9e207e61e3016b2188059bdc809d6a",
    "designs/clean_v2/readmit_d.json": "1e829c867106b69e86089b5eb6481fde4ca032031e7c1d2ac10c583d62f75248",
}
EXCLUSIONS_4B_SHA256 = "7eadd825e396a1c94b5d4988c61b3fe2ee9db307922377c933edecdd2cef9f08"


def main() -> int:
    lock = {
        "status": "확정 — 4b 봉인 확인 뒤 다시 잠금 (4b 봉인 확인 조건에 따라 수정, 칸 20·설계서 4)",
        "date": "2026-10-06",
        "locked": {r: sha(r) for r in PROVISIONAL},
        "provisional_4a": PROVISIONAL_4A,
        "exclusions_4b_sha256": EXCLUSIONS_4B_SHA256,
        "fixed_for_4b": {r: sha(r) for r in FIXED_FOR_4B},
        "seeds": {"DRAW_SEED": B.DRAW_SEED, "PLACE_SEED": B.PLACE_SEED},
    }
    LOCK.write_text(json.dumps(lock, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for g in ("locked", "fixed_for_4b"):
        for r, h in lock[g].items():
            print(g, r, h)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
