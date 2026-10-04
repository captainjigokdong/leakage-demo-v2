"""데이터 설명서(docs/data_dictionary_v2.md)가 모든 테이블의 모든 열을 같은 형식으로 다루는지 (v2 2단계).

데이터 파일의 열이 목록(synth/tables_v2.py)과 같은지는 데이터를 다시 생성한 뒤(2b) 따로 확인한다.
"""
from __future__ import annotations

import re
from pathlib import Path

from synth.tables_v2 import DERIVED_V2, EVENT_TIME_COLUMNS, RECORD_TIME_COLUMNS, TABLES_V2
from tests.test_design_format_doc import TAG

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "data_dictionary_v2.md"
N_CELLS = 9  # 열 + 8칸
ROW = re.compile(r"^\| `([a-z_]+\.[a-z_]+)` \|(.*)\|$")


def dictionary_rows() -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in DOC.read_text(encoding="utf-8").splitlines():
        m = ROW.match(line)
        if m:
            assert m.group(1) not in rows, f"설명서에 같은 열이 두 번: {m.group(1)}"
            rows[m.group(1)] = [c.strip() for c in m.group(2).split(" | ")]
    return rows


def expected_columns() -> set[str]:
    return {f"{t}.{c}" for t, cols in TABLES_V2.items() for c in cols} | set(DERIVED_V2)


def test_every_column_documented():
    missing = expected_columns() - set(dictionary_rows())
    assert not missing, f"설명서에 없는 열: {sorted(missing)}"


def test_no_documented_column_outside_table_list():
    extra = set(dictionary_rows()) - expected_columns()
    assert not extra, f"테이블 목록에 없는 열: {sorted(extra)}"


def test_every_row_fills_all_cells():
    for col, cells in dictionary_rows().items():
        assert len(cells) == N_CELLS - 1, f"{col}: 칸 수 {len(cells)}"
        assert all(cells), f"{col}: 빈 칸"


def test_every_row_has_valid_basis():
    for col, cells in dictionary_rows().items():
        tags = [t.strip() for t in cells[-1].split(";")]
        bad = [t for t in tags if not TAG.match(t)]
        assert not bad, f"{col}: 근거 꼬리표 형식이 아님 {bad}"


def test_every_table_has_a_section():
    text = DOC.read_text(encoding="utf-8")
    for t in TABLES_V2:
        assert re.search(rf"^## {t}\b", text, re.M), f"테이블 절 없음: {t}"


def test_time_column_lists_refer_to_real_columns():
    cols = expected_columns()
    for t, cs in EVENT_TIME_COLUMNS.items():
        for c in cs:
            assert f"{t}.{c}" in cols, f"{t}.{c}"
    for t, m in RECORD_TIME_COLUMNS.items():
        for c, ref in m.items():
            assert f"{t}.{c}" in cols, f"{t}.{c}"
            assert (ref if "." in ref else f"{t}.{ref}") in cols, ref
