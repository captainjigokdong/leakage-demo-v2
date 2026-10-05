"""스킬 동결 해시 잠금 (v2 3단계). leakcheck/, skill_src/, designs/schema.json이 동결 목록과 같은지.

목록: docs/skill_freeze_v2.json (python -m tools.freeze_manifest로 만든다). `skill-frozen-v2` 태그 뒤에는
세 곳을 고치지 않는다. 파일을 더하거나, 빼거나, 바꾸면 이 시험이 실패한다. 버그는 docs/known_issues_v2.md에 적는다.
"""
import json
from pathlib import Path

from tools.freeze_manifest import OUT, frozen_files, sha256

ROOT = Path(__file__).resolve().parent.parent


def _locked() -> dict:
    return json.loads(OUT.read_text(encoding="utf-8"))


def test_frozen_file_set_unchanged():
    assert frozen_files() == sorted(_locked()["files"]), "동결 대상에 파일이 더해지거나 빠졌다"


def test_frozen_file_hashes_unchanged():
    changed = [rel for rel, h in _locked()["files"].items() if (ROOT / rel).exists() and sha256(rel) != h]
    assert not changed, f"동결 뒤 바뀐 파일: {changed}"


def test_manifest_covers_checker_skill_and_schema():
    m = _locked()
    assert m["tag"] == "skill-frozen-v2"
    files = set(m["files"])
    assert "designs/schema.json" in files
    assert {"skill_src/leakage-check/SKILL.md", "skill_src/leakage-check/rules.md",
            "skill_src/leakage-check/scripts/run_check.py"} <= files
    assert {f"leakcheck/{p.name}" for p in (ROOT / "leakcheck").glob("*.py")} <= files
