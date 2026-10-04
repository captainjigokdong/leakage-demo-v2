"""봉인된 후보 목록의 핵심어가 커밋 내용·커밋 설명에 얼마나 나오는지 센다 (v2 2단계).

후보 목록은 sealed/candidates.enc를 메모리에서만 연다. 평문 파일을 만들지 않는다.
화면에는 개수만 출력한다. 일치한 핵심어 목록이 필요하면 --hits-json으로 저장소 밖 경로에 쓰고,
그 목록은 봉인 파일 안에만 기록한다.

핵심어 (후보의 name, how_to_inject 칸에서 기계적으로 뽑음)
- 영문 식별자: 글자·숫자·밑줄·점으로 된 4자 이상 낱말 (대소문자 무시, 낱말 경계로 셈)
- 한글 구: 한글이 든 이웃한 두 어절

사용 예:
    SEAL_PASSWORD=... python -m tools.keyword_check 126f0b6..f7e349c [--hits-json /저장소밖/hits.json]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import subprocess
import sys
from pathlib import Path

from tools.seal import decrypt_bytes, get_password

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = ROOT / "sealed" / "candidates.enc"
_ASCII = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{3,}")
_SPLIT = re.compile(r'[\s,()"·/→=<>]+')
_HANGUL = re.compile(r"[가-힣]")


def keywords(rows: list[dict]) -> dict[str, set[str]]:
    """핵심어 → 그 핵심어가 나온 후보 id 집합."""
    kw: dict[str, set[str]] = {}
    for r in rows:
        for field in ("name", "how_to_inject"):
            s = r[field]
            for tok in _ASCII.findall(s):
                kw.setdefault(tok.lower(), set()).add(r["id"])
            words = [w for w in _SPLIT.split(s) if _HANGUL.search(w)]
            for a, b in zip(words, words[1:]):
                kw.setdefault(f"{a} {b}", set()).add(r["id"])
    return kw


def count_hits(kw: dict[str, set[str]], text: str) -> dict[str, int]:
    low = text.lower()
    out = {}
    for k in kw:
        if _HANGUL.search(k):
            c = text.count(k)
        else:
            c = len(re.findall(r"(?<![a-z0-9_])" + re.escape(k) + r"(?![a-z0-9_])", low))
        if c:
            out[k] = c
    return out


def added_lines(rev_range: str) -> str:
    """범위 안 커밋들이 더한 줄 (봉인 폴더 제외)."""
    diff = subprocess.run(["git", "diff", "--text", "-U0", rev_range, "--", ".", ":!sealed"],
                          cwd=ROOT, capture_output=True, check=True).stdout.decode("utf-8", "replace")
    return "\n".join(l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))


def commit_messages(rev_range: str) -> str:
    return subprocess.run(["git", "log", "--format=%B", rev_range], cwd=ROOT, capture_output=True,
                          check=True).stdout.decode("utf-8", "replace")


def load_candidates(password: str) -> list[dict]:
    text = decrypt_bytes(CANDIDATES.read_bytes(), password).decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("rev_range", help="git 범위 (예: 126f0b6..HEAD)")
    ap.add_argument("--hits-json", type=Path, help="일치 목록을 쓸 경로 (저장소 밖)")
    a = ap.parse_args(argv)
    if a.hits_json and ROOT in a.hits_json.resolve().parents:
        print("일치 목록은 저장소 밖에만 쓴다", file=sys.stderr)
        return 2
    kw = keywords(load_candidates(get_password()))
    diff_hits = count_hits(kw, added_lines(a.rev_range))
    msg_hits = count_hits(kw, commit_messages(a.rev_range))
    print(f"핵심어 {len(kw)}개 | 커밋 내용: 일치 핵심어 {len(diff_hits)}개, {sum(diff_hits.values())}회"
          f" | 커밋 설명: 일치 핵심어 {len(msg_hits)}개, {sum(msg_hits.values())}회")
    if a.hits_json:
        a.hits_json.write_text(json.dumps(
            {"range": a.rev_range,
             "diff": {k: [c, sorted(kw[k])] for k, c in sorted(diff_hits.items())},
             "messages": {k: [c, sorted(kw[k])] for k, c in sorted(msg_hits.items())}},
            ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
