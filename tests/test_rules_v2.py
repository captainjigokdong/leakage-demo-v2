"""규칙표가 모든 테이블·열을 다루고, 데이터 설명서(docs/data_dictionary_v2.md)와 맞는지 (v2 3단계).

테이블 목록의 기준은 synth/tables_v2.py. 규칙은 설명서의 "값이 알려지는 때" 칸만 보고 썼다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from leakcheck import rules
from synth.generate_v2 import DATE_COLUMNS, DATETIME_COLUMNS
from synth.tables_v2 import DERIVED_V2, TABLES_V2
from tests.test_data_dictionary import dictionary_rows

ROOT = Path(__file__).resolve().parent.parent

# 설명서 "값이 알려지는 때" 칸의 문구 → (규칙 종류, 확인 시각 열). 괄호 안 보충 설명은 떼고 읽는다.
# 새 문구가 나오면 이 표에 없어서 시험이 실패한다 (추측하지 않음).
PHRASES = {
    "자료 추출 시": ("extraction", None),
    "첫 입원 시": ("first_admit", None),
    "입원 시": ("row_anchor", "admit"),
    "퇴원 시": ("row_anchor", "discharge"),
    "병동 입실 시": ("column", "in_time"),
    "병동 퇴실 시": ("column", "out_time"),
    "보고 시": ("column", "report_time"),
    "report_time": ("column", "report_time"),
    "입력 시": ("column", "entered_time"),
    "전산 입력 시": ("column", "entered_time"),
    "entered_time": ("column", "entered_time"),
    "처방 시": ("column", "order_time"),
    "오더 시": ("column", "order_time"),
    "coded_time": ("column", "coded_time"),
    "코딩 완료 시": ("column", "coded_time"),
    "코드 입력 시": ("column", "coded_time"),
    # 항목을 처음 기록한 시각 ≤ 그 버전의 기록 시각. 규칙은 버전마다 recorded_time (같거나 늦은 쪽, 보수적)
    "처음 기록 시": ("column", "recorded_time"),
    "recorded_time": ("column", "recorded_time"),
    "이 버전 기록 시": ("column", "recorded_time"),
    "방문 시": ("column", "visit_time"),
    "예약 시": ("column", "booked_time"),
    "예약 입원 시": ("linked_admit", "admission_id"),
    "death_recorded_time": ("column", "death_recorded_time"),
    "사망 기록 시": ("column", "death_recorded_time"),
}


def _expected(cell: str):
    key = cell.split(" (")[0].strip()
    assert key in PHRASES, f"설명서 문구가 대응표에 없다: {cell!r}"
    return PHRASES[key]


def test_every_table_has_a_rule():
    assert set(rules.TABLES) == set(TABLES_V2)
    for name, rule in rules.TABLES.items():
        assert rule.name == name


def test_every_column_has_an_explicit_rule():
    for t, cols in TABLES_V2.items():
        missing = [c for c in cols if c not in rules.TABLES[t].column_available]
        assert not missing, f"{t}: 열 규칙 없음 {missing}"
        extra = [c for c in rules.TABLES[t].column_available if c not in cols and f"{t}.{c}" not in DERIVED_V2]
        assert not extra, f"{t}: 목록에 없는 열의 규칙 {extra}"
    for d in DERIVED_V2:
        t, c = d.split(".")
        if t == "index_row":
            assert c in rules.INDEX_ROW_COLUMNS and rules.split_level(c) == "index_row"
        else:
            assert c in rules.TABLES[t].column_available and c in rules.TABLES[t].derived


def test_rules_match_data_dictionary():
    rows = dictionary_rows()
    for t, cols in TABLES_V2.items():
        for c in cols:
            kind, col = _expected(rows[f"{t}.{c}"][2])
            a = rules.availability(t, c)
            assert a.kind == kind, (t, c, a.kind, kind)
            if col is not None:
                assert a.column == col, (t, c, a.column, col)
    a = rules.availability("admissions", "length_of_stay_h")
    assert (a.kind, a.column) == _expected(rows["admissions.length_of_stay_h"][2])


def test_time_column_kinds_match_data():
    for t, rule in rules.TABLES.items():
        dt = {c for c, k in rule.time_columns.items() if k == "datetime"}
        d = {c for c, k in rule.time_columns.items() if k == "date"}
        assert dt == set(DATETIME_COLUMNS.get(t, [])), t
        assert d == set(DATE_COLUMNS.get(t, [])), t


def test_every_rule_has_layer_and_basis():
    for t, rule in rules.TABLES.items():
        for a in [rule.row_available, *rule.column_available.values()]:
            assert a.layer in (1, 2, 3) and a.basis.startswith("설명서"), t
            if a.kind == "column":
                assert a.column in rule.time_columns, (t, a.column)
                assert all(c in rule.time_columns for c in a.lag_from), t
    for aid, (text, param) in rules.ASSUMPTIONS.items():
        assert aid.startswith("A.") and text
        if param is not None:
            assert hasattr(rules, param), (aid, param)


@pytest.mark.parametrize("folder", ["data/synth", "data/synth_aux"])
def test_committed_data_tags_without_error(folder):
    """본·보조 데이터의 17개 테이블 모든 행에 꼬리표가 붙는다 (규칙 없는 테이블·연결 안 되는 행 없음)."""
    from leakcheck.data import load
    from leakcheck.tagging import tag_tables
    tables = load(ROOT / folder)
    tagged = tag_tables(tables, "family")
    assert set(tagged) == set(TABLES_V2)
    for name, df in tagged.items():
        assert len(df) == len(tables[name]) and df["_available_time"].notna().all(), name
