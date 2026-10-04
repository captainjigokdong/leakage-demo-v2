"""데이터 설명서의 결측·값의 범위 칸을 저장된 데이터의 실측값으로 바꾼다 (2단계 2b).

칸 형식: `실측 <값> (설계 <원래 설계값>)`. 이미 실측값이 있으면 실측 부분만 다시 계산한다 (설계 부분은 그대로).
보조 데이터의 실측값은 설명서 끝 "보조 데이터" 절의 표에 따로 적는다.
시험(tests/test_data_dictionary.py)이 설명서의 실측 부분이 저장된 데이터에서 다시 계산한 값과 같은지 확인한다.

실행: python -m synth.profile_v2 [--check]
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

from synth.generate_v2 import DATE_COLUMNS, DATETIME_COLUMNS, PROFILES, load
from synth.tables_v2 import TABLES_V2

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "data_dictionary_v2.md"
ROW = re.compile(r"^\| `([a-z_]+)\.([a-z_]+)` \|(.*)\|$")
MEASURED = re.compile(r"^실측 (.*?) \(설계 (.*)\)$")
AUX_START = "### 보조 데이터 실측값"
MAX_CATEGORIES = 12


def _is_time(t: str, c: str) -> bool:
    return c in DATETIME_COLUMNS.get(t, []) or c in DATE_COLUMNS.get(t, [])


def missing_text(s: pd.Series) -> str:
    n = len(s)
    if n == 0:
        return "행 없음"
    return f"{s.isna().mean() * 100:.1f}%"


def range_text(t: str, c: str, s: pd.Series) -> str:
    v = s.dropna()
    if len(v) == 0:
        return "값 없음"
    if _is_time(t, c):
        fmt = "%Y-%m-%d" if c in DATE_COLUMNS.get(t, []) else "%Y-%m-%d %H:%M"
        x = pd.to_datetime(v)
        return f"{x.min().strftime(fmt)} ~ {x.max().strftime(fmt)}"
    if pd.api.types.is_numeric_dtype(v):
        lo, hi = v.min(), v.max()
        f = (lambda x: f"{int(x)}") if pd.api.types.is_integer_dtype(v) else (lambda x: f"{x:g}")
        return f"{f(lo)} ~ {f(hi)}"
    u = sorted(v.astype(str).unique())
    if len(u) <= MAX_CATEGORIES:
        return ", ".join(u)
    return f"{u[0]} ~ {u[-1]} (고유값 {len(u)}개)"


def profile(tables: dict[str, pd.DataFrame]) -> dict[str, tuple[str, str]]:
    return {f"{t}.{c}": (missing_text(tables[t][c]), range_text(t, c, tables[t][c]))
            for t, cols in TABLES_V2.items() for c in cols}


def _merge(cell: str, measured: str) -> str:
    m = MEASURED.match(cell)
    design = m.group(2) if m else cell
    return f"실측 {measured} (설계 {design})"


def apply(text: str, main: dict, aux: dict) -> str:
    out = []
    for line in text.split(AUX_START)[0].rstrip().splitlines():   # 보조 실측표는 아래에서 새로 쓴다
        m = ROW.match(line)
        key = f"{m.group(1)}.{m.group(2)}" if m else None
        if key in main:
            cells = [x.strip() for x in m.group(3).split(" | ")]
            cells[4] = _merge(cells[4], main[key][0])     # 결측
            cells[5] = _merge(cells[5], main[key][1])     # 값의 범위
            line = f"| `{key}` | " + " | ".join(cells) + " |"
        out.append(line)
    head = "\n".join(out) + "\n"
    rows = ["", AUX_START, "", "`data/synth_aux/`에서 계산. 열마다 결측과 값의 범위.", "",
            "| 열 | 결측 | 값의 범위 |", "|---|---|---|"]
    rows += [f"| `{k}` | {v[0]} | {v[1]} |" for k, v in aux.items()]
    return head + "\n".join(rows) + "\n"


def measured_from_doc(text: str) -> tuple[dict, dict]:
    """설명서에서 실측 부분만 읽는다 (시험용)."""
    main, aux = {}, {}
    body, _, aux_part = text.partition(AUX_START)
    for line in body.splitlines():
        m = ROW.match(line)
        if m:
            cells = [x.strip() for x in m.group(3).split(" | ")]
            a, b = MEASURED.match(cells[4]), MEASURED.match(cells[5])
            main[f"{m.group(1)}.{m.group(2)}"] = (a.group(1) if a else None, b.group(1) if b else None)
    for line in aux_part.splitlines():
        m = re.match(r"^\| `([a-z_]+\.[a-z_]+)` \| (.*) \| (.*) \|$", line)
        if m:
            aux[m.group(1)] = (m.group(2), m.group(3))
    return main, aux


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="설명서 실측값 반영")
    ap.add_argument("--check", action="store_true", help="쓰지 않고 다른 곳만 출력")
    args = ap.parse_args(argv)
    main_p = profile(load(ROOT / PROFILES["main"].out))
    aux_p = profile(load(ROOT / PROFILES["aux"].out))
    text = DOC.read_text(encoding="utf-8")
    new = apply(text, main_p, aux_p)
    if args.check:
        print("같음" if new == text else "다름")
        return 0 if new == text else 1
    DOC.write_text(new, encoding="utf-8")
    print(f"반영: {DOC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
