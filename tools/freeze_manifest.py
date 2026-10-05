"""스킬 동결 해시 목록 (v2 3단계). leakcheck/, skill_src/, designs/schema.json의 파일별 sha256.

결과: docs/skill_freeze_v2.json. 시험(tests/test_skill_freeze.py)이 현재 파일과 목록이 같은지 확인한다.
목록을 커밋한 뒤 사용자가 main에 `skill-frozen-v2` 태그를 만든다. 그 뒤에는 세 곳을 고치지 않는다 (CLAUDE.md 절대 규칙 3).

실행: python -m tools.freeze_manifest
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "skill_freeze_v2.json"
DIRS = ("leakcheck", "skill_src")
FILES = ("designs/schema.json",)


def frozen_files() -> list[str]:
    out = [str(p.relative_to(ROOT)) for d in DIRS for p in (ROOT / d).rglob("*")
           if p.is_file() and "__pycache__" not in p.parts]
    return sorted(out + list(FILES))


def sha256(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def manifest() -> dict:
    return {"tag": "skill-frozen-v2", "covers": [*(f"{d}/" for d in DIRS), *FILES],
            "files": {rel: sha256(rel) for rel in frozen_files()}}


def main() -> int:
    m = manifest()
    OUT.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"썼다: {OUT.relative_to(ROOT)} ({len(m['files'])}개 파일)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
