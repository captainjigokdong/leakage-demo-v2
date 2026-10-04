"""2b 예비 검수용 깨끗한 기본 설계서 (designs/prereview/). 4단계의 깨끗한 설계서와 별개다.

넓어진 형식을 모두 채웠는지 확인한다. 선택한 방법에 해당하지 않아 비운 칸은 NOT_APPLICABLE에 적고,
같은 내용을 설계서의 notes에도 적었다.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from synth.tables_v2 import DERIVED_V2, TABLES_V2

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "designs" / "schema.json").read_text(encoding="utf-8"))
DESIGNS = {"fixed": ROOT / "designs" / "prereview" / "fixed_readmission.json",
           "dynamic": ROOT / "designs" / "prereview" / "dynamic_aki.json"}
NOT_APPLICABLE = {
    "fixed": {"outcome.filter", "outcome.reference_window", "outcome.reference", "cohort.sampling.by",
              "cohort.sampling.fraction", "cohort.sampling.ratio", "split.n_folds", "split.time_column",
              "split.cutoff", "split.gap"},
    "dynamic": {"cohort.sampling.by", "cohort.sampling.fraction", "cohort.sampling.ratio", "split.n_folds",
                "split.time_column", "split.cutoff", "split.gap"},
}
# 설계서 목록 항목(rowset)의 칸 중 설계서 전체에서 한 번 이상 쓰여야 하는 것 (date_compare는 날짜 열을 안 써서 제외)
ROWSET_FIELDS = {"name", "description", "source", "column", "filter", "scope", "time_column", "window", "agg",
                 "made_by", "derive", "assessment", "as_of"}


def _object_paths(schema: dict, prefix: str = "") -> list[str]:
    """schema의 객체 칸 경로 ($ref 목록 항목·data_use 안쪽은 따로 본다)."""
    out = []
    for k, v in schema.get("properties", {}).items():
        path = f"{prefix}{k}"
        out.append(path)
        if v.get("type") == "object" and "properties" in v:
            out += _object_paths(v, path + ".")
    return out


def _get(d: dict, path: str):
    for k in path.split("."):
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


@pytest.mark.parametrize("kind", sorted(DESIGNS))
def test_valid_against_schema(kind):
    jsonschema.validate(json.loads(DESIGNS[kind].read_text(encoding="utf-8")), SCHEMA)


@pytest.mark.parametrize("kind", sorted(DESIGNS))
def test_every_field_filled_or_listed_not_applicable(kind):
    d = json.loads(DESIGNS[kind].read_text(encoding="utf-8"))
    na = NOT_APPLICABLE[kind]
    missing = [p for p in _object_paths(SCHEMA)
               if _get(d, p) is None and not any(p == x or p.startswith(x + ".") for x in na)]
    assert not missing, missing
    for p in NOT_APPLICABLE[kind]:
        assert _get(d, p) is None, f"해당 없음으로 적었는데 채워져 있음: {p}"
        assert p in d["notes"], f"notes에 적히지 않음: {p}"


@pytest.mark.parametrize("kind", sorted(DESIGNS))
def test_rowset_fields_used_somewhere(kind):
    d = json.loads(DESIGNS[kind].read_text(encoding="utf-8"))
    used = {k for f in d["features"] for k in f}
    assert ROWSET_FIELDS <= used, ROWSET_FIELDS - used


@pytest.mark.parametrize("kind", sorted(DESIGNS))
def test_known_weaknesses_handled(kind):
    """2b 사용자 조건: 진단 코드는 코딩 완료 시각, 추적 부족 제외, 사망 처리 명시, 가족·없으면 사람(person_id)으로 분할 (승인 ② 뒤 환자 → 사람)."""
    d = json.loads(DESIGNS[kind].read_text(encoding="utf-8"))
    for f in d["features"]:
        if f.get("source") == "diagnoses":
            assert f["time_column"] == "coded_time" and f["window"]["end"] == "tp", f["name"]
    assert d["outcome"]["censoring"]["death"] not in (None, "not_applicable")
    assert (d["split"]["key"], d["split"]["fallback_key"], d["split_unit"]) == ("family_id", "person_id", "family")
    assert d["model"]["tuning"]["fallback_key"] == "person_id"
    if kind == "fixed":
        assert d["outcome"]["censoring"]["end_of_data"] == "exclude_incomplete"
        assert any(c["name"] == "followup_incomplete" for c in d["cohort"]["exclusion"])


@pytest.mark.parametrize("kind", sorted(DESIGNS))
def test_sources_and_columns_exist(kind):
    d = json.loads(DESIGNS[kind].read_text(encoding="utf-8"))
    rows = d["features"] + d["cohort"]["inclusion"] + d["cohort"]["exclusion"]
    for f in rows:
        if "source" not in f:
            continue
        cols = set(TABLES_V2[f["source"]]) | {c.split(".")[1] for c in DERIVED_V2 if c.startswith(f["source"] + ".")}
        for c in [f.get("column"), f.get("time_column"), *(f.get("filter") or {})]:
            assert c is None or c in cols, (f["name"], c)
