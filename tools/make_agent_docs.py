"""에이전트용 문서 사본 (5단계). 두 조건이 같은 파일을 받는다 (docs/agent/, 해시 잠금은 experiment/prompt.py).

- 형식 설명: `docs/design_format_v2.md`에서 "근거" 열과 "근거 표기" 절, 저장소 안내 머리말을 뺀다.
- 데이터 설명서: `docs/data_dictionary_v2.md`에서 "근거" 열, 저장소 안내 머리말, 보조 데이터 절(본 실험에 주지 않는 데이터)을 뺀다.
  (2b 예비 검수 사본과 같은 방식에 근거 열을 더 뺀다.)
- 분류 이름·근거 꼬리표·정당한 지적 목록·점검기 문제(K)·검수 기록의 내용이 없는지는 `tests/test_grader.py`가 확인한다.

    python -m tools.make_agent_docs
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "agent"

FORMAT_HEAD = """# 설계서 형식 설명

설계서(JSON)의 모든 칸을 설명한다.

경로 표기: `a.b`는 객체 안의 칸, `a[]`는 목록의 각 항목이다. 여러 곳에서 같이 쓰는 정의(행 명세 `rowset`, 전처리 단계 `step` 등)는 마지막 절에 한 번만 적는다.

시각 표기: `기준점+간격` (`tp`, `tp-48h`, `admit+24h`, `discharge+30d`, `-inf`, `inf`). 구간은 (start, end] 반열린 구간.
"""

DICT_HEAD = """# 데이터 설명서

합성 데이터의 **모든 테이블의 모든 열**에 대해, 값이 언제 생기고 언제 알려지는지를 같은 형식으로 적는다.
모든 환자·수치는 가상 값이다. 날짜는 실제 날짜와 섞이지 않게 2150년대로 옮겨 두었다.

- 결측·값의 범위 칸은 저장된 데이터에서 잰 값이다. 형식은 `실측 <값> (설계 <원래 설계값>)`.
- 시각은 분 단위 (`YYYY-MM-DD HH:MM:SS`), 날짜는 일 단위 (`YYYY-MM-DD`).
"""


def _drop_column(lines: list[str], name: str = "근거") -> list[str]:
    """표마다 머리 칸에 name이 있으면 그 열을 지운다."""
    out, idx, in_table = [], None, False
    for ln in lines:
        if ln.startswith("|"):
            cells = ln.strip().strip("|").split("|")
            if not in_table:   # 표의 머리 줄에서만 찾는다
                in_table = True
                idx = [c.strip() for c in cells].index(name) if any(c.strip() == name for c in cells) else None
            if idx is not None and len(cells) > idx:
                cells = cells[:idx] + cells[idx + 1:]
                ln = "|" + "|".join(cells) + "|"
                if all(re.fullmatch(r"\s*:?-+:?\s*", c) for c in cells):
                    ln = "|" + "|".join("---" for _ in cells) + "|"
        else:
            idx, in_table = None, False
        out.append(ln)
    return out


def _sections(text: str) -> list[tuple[str, str]]:
    parts = re.split(r"(?m)^(?=## )", text)
    return [(p.splitlines()[0] if p.startswith("## ") else "", p) for p in parts]


# 형식 설명의 설명 칸에서 바꾸는 것: 출처 표시 "(예비 검수 B..)"는 지우고, 분류 이름과 같은 낱말은 뜻이 같은 말로 바꾼다.
FORMAT_REPLACE = [(re.compile(r" \(예비 검수 [^)]*\)"), ""), (re.compile(r"독립 단위:"), "서로 독립으로 보는 묶음의 단위:")]


def build_format(src: Path = ROOT / "docs" / "design_format_v2.md") -> str:
    secs = [p for h, p in _sections(src.read_text(encoding="utf-8")) if h and h != "## 근거 표기"]
    text = "\n".join(_drop_column("".join(secs).splitlines()))
    for pat, rep in FORMAT_REPLACE:
        text = pat.sub(rep, text)
    return FORMAT_HEAD + "\n" + text.rstrip() + "\n"


def build_dictionary(src: Path = ROOT / "docs" / "data_dictionary_v2.md") -> str:
    keep = []
    for h, p in _sections(src.read_text(encoding="utf-8")):
        if not h or h.startswith("## 보조 데이터"):
            continue
        keep.append(p)
    lines = _drop_column("".join(keep).splitlines())
    lines = [ln for ln in lines if not ln.startswith("| 근거 |")]   # 칸 설명 표의 "근거" 줄
    return DICT_HEAD + "\n" + "\n".join(lines).rstrip() + "\n"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "design_format.md").write_text(build_format(), encoding="utf-8")
    (OUT / "data_dictionary.md").write_text(build_dictionary(), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
