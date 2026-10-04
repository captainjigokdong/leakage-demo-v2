"""48개 사례가 넓어진 설계서 형식에 조정 없이 주입되는가 (v2 2단계 2c).

- 대상 설계서: 시험용 기본 설계서 `designs/prereview/` (유형별 1개, 읽기 전용).
- v1 사례 18개: `designs/patches_v1_cases.py`. 암호 없이 돈다.
- 새 후보 30개: 패치는 `sealed/stage2c_record.enc`에만 있다. SEAL_PASSWORD가 있을 때만 돈다
  (건너뜀 표: 4단계 시작 시 반드시 통과). 화면에는 번호와 통과·실패만 나온다.
- 실질 확인(`designs/substance.py`): 전제가 데이터에 있어야 한다(0이면 실패). 수치 차이는 기록만 한다.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import os
import re
from collections import Counter
from pathlib import Path

import jsonschema
import pandas as pd
import pytest

from designs import substance
from designs.inject import TYPE_KO, apply_ops, targets_of
from designs.patches_v1_cases import V1_CASE_PATCHES, load_test_bases
from synth.tables_v2 import DERIVED_V2, TABLES_V2
from tools.draw_holdout import ALLOCATION, COLUMNS, catalog_hash

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "designs" / "schema.json").read_text(encoding="utf-8"))
CATALOG = ROOT / "designs" / "error_catalog_public.csv"
RECORD = ROOT / "sealed" / "stage2c_record.enc"
CANDIDATES = ROOT / "sealed" / "candidates.enc"
V1_CATALOG_HASH = "0cd3b12bbe164899bb13c9f18ae478e115fb44c3d7c94dd18ed60706cd11f357"   # v1 docs/holdout_log.md
NEW_ALLOCATION = {"Q1": 8, "Q2": 4, "Q3": 5, "Q4": 4, "Q5": 5, "Q7": 4}               # docs/seal_log_v2.md
CODE_COLUMNS = {"icd_code", "code"}                                                     # 앞부분 일치
BAD_NAME = re.compile(r"leak|next|future|after|post|outcome|target_leak|all_data|E\d\d|C\d\d", re.I)


def catalog_rows() -> list[dict]:
    with open(CATALOG, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


V1_ROWS = {r["id"]: r for r in catalog_rows()}
BASES = load_test_bases()


# --- 공통 점검 -------------------------------------------------------------

def _named(lst) -> bool:
    return isinstance(lst, list) and all(isinstance(x, dict) and "name" in x for x in lst) and lst


def changed_items(a, b, prefix: str = "") -> set[str]:
    """두 설계서가 다른 곳. 이름 있는 항목 목록은 'path:name', 그 밖은 점 경로."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = set()
        for k in set(a) | set(b):
            p = f"{prefix}.{k}" if prefix else k
            if k not in a or k not in b:
                out.add(p)
            elif a[k] != b[k]:
                out |= changed_items(a[k], b[k], p)
        return out
    if _named(a) or _named(b):
        na, nb = {x["name"]: x for x in a or []}, {x["name"]: x for x in b or []}
        return {f"{prefix}:{n}" for n in set(na) | set(nb) if na.get(n) != nb.get(n)}
    return {prefix} if a != b else set()


def _covered(item: str, targets: list[str]) -> bool:
    """이름 있는 항목('features:x', 'cohort.inclusion:x')은 그 항목만, 점 경로는 그 아래 전부."""
    for t in targets:
        if ":" in t:
            if item == t:
                return True
        elif item == t or item.startswith(t + ".") or item.startswith(t + ":"):
            return True
    return False


def _columns(source: str) -> set[str]:
    return set(TABLES_V2[source]) | {c.split(".")[1] for c in DERIVED_V2 if c.startswith(source + ".")}


ALL_COLUMNS = {c for t in TABLES_V2 for c in _columns(t)} | {"landmark_row_id"}


def _rowsets(ops: list[dict]):
    for op in ops:
        v = op.get("value")
        if isinstance(v, dict) and "source" in v:
            yield v
        if isinstance(v, dict) and isinstance(v.get("filter"), dict) and "source" not in v:
            yield v


def _value_present(source: str, col: str, val) -> bool:
    s = substance.tables()[source][col].dropna()
    if col in CODE_COLUMNS:
        return s.astype(str).str.startswith(str(val)).any()
    if pd.api.types.is_numeric_dtype(s):
        return (s == val).any()
    return (s.astype(str) == str(val)).any()


def check_case(ops: list[dict], types: list[str]) -> list[str]:
    """한 사례의 패치를 해당 유형의 시험용 기본 설계서마다 점검한다. 문제 목록(비면 통과)."""
    problems = []
    targets = targets_of(ops)
    for t in types:
        base = BASES[t]
        try:
            d = apply_ops(base, ops)                                  # ① 적용 (같은 값이면 실패)
        except (KeyError, ValueError) as e:
            problems.append(f"{t}: 적용 실패 {type(e).__name__}")
            continue
        try:
            jsonschema.validate(d, SCHEMA)                           # ② schema
        except jsonschema.ValidationError:
            problems.append(f"{t}: schema 불일치")
        extra = [c for c in changed_items(base, d) if not _covered(c, targets)]
        if extra:                                                    # ③ 지목한 항목만 바뀜
            problems.append(f"{t}: 지목하지 않은 곳이 바뀜 {len(extra)}곳")
    for v in _rowsets(ops):                                          # ④ 테이블·열, ⑤ 값이 데이터에 있음
        src = v.get("source")
        if src is None:
            continue
        if src not in TABLES_V2:
            problems.append("테이블 없음")
            continue
        cols = _columns(src)
        for c in [v.get("column"), v.get("time_column"), *(v.get("filter") or {})]:
            if c is not None and c not in cols:
                problems.append("열 없음")
        for c, vals in (v.get("filter") or {}).items():
            if c in TABLES_V2[src] and not all(_value_present(src, c, x) for x in vals):
                problems.append("값 없음")
    for op in ops:
        if op["path"] in ("split.key", "split.fallback_key", "model.tuning.cv_key") and op.get("value") not in ALL_COLUMNS:
            problems.append("분할 열 없음")
        v = op.get("value")
        if isinstance(v, dict) and "name" in v and BAD_NAME.search(v["name"]):  # ⑥ 이름
            problems.append("결함을 암시하는 이름")
    return problems


# --- 공개 목록 18행 -----------------------------------------------------------

def test_public_catalog_is_v1_eighteen_unchanged():
    rows = catalog_rows()
    with open(CATALOG, newline="", encoding="utf-8") as f:
        assert csv.DictReader(f).fieldnames == COLUMNS
    assert [r["id"] for r in rows] == [f"E{i:02d}" for i in range(1, 19)]
    assert catalog_hash(rows) == V1_CATALOG_HASH          # 조정 전 원래 문장 (v1 기록값)
    assert dict(Counter(r["question"] for r in rows)) == ALLOCATION


def test_v1_patches_cover_catalog():
    assert sorted(V1_CASE_PATCHES) == sorted(V1_ROWS)


def test_test_bases_are_prereview_and_valid():
    for t, d in BASES.items():
        assert d["design_type"] == t
        jsonschema.validate(d, SCHEMA)


# --- v1 18개 주입 -----------------------------------------------------------

V1_PARAMS = [pytest.param(cid, id=cid) for cid in sorted(V1_CASE_PATCHES)]


@pytest.mark.parametrize("cid", V1_PARAMS)
def test_v1_case_injects_without_adjustment(cid):
    assert check_case(V1_CASE_PATCHES[cid], TYPE_KO[V1_ROWS[cid]["design_types"]]) == []


@pytest.mark.parametrize("cid", V1_PARAMS)
def test_v1_case_premise_in_locked_data(cid):
    """실질 확인 (1) 전제: 결함이 기대는 사실이 잠긴 데이터에 있다. (2) 수치 차이는 기록만 한다."""
    for t in TYPE_KO[V1_ROWS[cid]["design_types"]]:
        r = substance.V1_SUBSTANCE[cid](t)
        assert r["premise_ok"], f"{cid} {t}: 전제 없음"
        assert r["difference"] >= 0


def test_checker_rejects_bad_patch():
    """점검 함수가 실제로 문제를 잡는지 (가짜 패치)."""
    bad = [{"op": "append", "path": "features",
            "value": {"name": "x1", "source": "labs", "filter": {"test": ["no_such_test"]}, "agg": "last"}}]
    assert "값 없음" in check_case(bad, ["dynamic"])
    assert check_case([{"op": "set", "path": "split.key", "value": "family_id"}], ["dynamic"])  # 같은 값
    assert check_case([{"op": "set", "path": "split.key", "value": "nope_id"}], ["dynamic"]) == ["분할 열 없음"]


def test_changed_items_flags_untargeted_change():
    base = BASES["dynamic"]
    d = copy.deepcopy(base)
    d["split"]["seed"] = 1
    d["features"][0]["agg"] = "last"
    assert not any(_covered(c, ["outcome.window"]) for c in changed_items(base, d))
    assert all(_covered(c, ["split", f"features:{base['features'][0]['name']}"]) for c in changed_items(base, d))


# --- 새 후보 30개 (봉인, 암호 필요) ---------------------------------------------

needs_password = pytest.mark.skipif(
    not (os.environ.get("SEAL_PASSWORD") and RECORD.exists()),
    reason="암호 필요 (sealed/stage2c_record.enc). 4단계 시작 시(암호를 받을 때) 반드시 통과")


@pytest.fixture(scope="module")
def sealed():
    from tools.seal import decrypt_bytes
    pw = os.environ["SEAL_PASSWORD"]
    record = json.loads(decrypt_bytes(RECORD.read_bytes(), pw))
    cands = list(csv.DictReader(io.StringIO(decrypt_bytes(CANDIDATES.read_bytes(), pw).decode("utf-8"))))
    return record, {r["id"]: r for r in cands}


def row_sha256(row: dict) -> str:
    return hashlib.sha256(json.dumps({c: row[c] for c in COLUMNS}, ensure_ascii=False,
                                     sort_keys=True).encode("utf-8")).hexdigest()


@needs_password
def test_new_cases_complete_and_sentences_unchanged(sealed):
    record, cands = sealed
    cases = record["cases"]
    assert sorted(c["id"] for c in cases) == sorted(cands) == [f"C{i:02d}" for i in range(1, 31)]
    assert dict(Counter(cands[i]["question"] for i in cands)) == NEW_ALLOCATION
    assert not set(cands) & set(V1_ROWS)                              # 48개 id가 겹치지 않음
    bad = [c["id"] for c in cases if c["row_sha256"] != row_sha256(cands[c["id"]])]
    assert not bad, f"문장 해시 불일치: {bad}"
    assert all(c.get("mapping") for c in cases), "대응표가 빠진 사례가 있음"


@needs_password
def test_new_cases_inject_without_adjustment(sealed):
    record, cands = sealed
    failed = [c["id"] for c in record["cases"]
              if check_case(c["ops"], TYPE_KO[cands[c["id"]]["design_types"]])]
    assert not failed, f"주입 점검 실패: {failed}"


@needs_password
def test_new_cases_premise_in_locked_data(sealed):
    record, cands = sealed
    ns = {"substance": substance, "pd": pd, "np": substance.np, **{k: getattr(substance, k) for k in dir(substance)
                                                                   if not k.startswith("_")}}
    exec(record["substance_code"], ns)                                # 봉인 안의 확인 함수 (메모리에서만)
    no_premise = []
    for c in record["cases"]:
        for t in TYPE_KO[cands[c["id"]]["design_types"]]:
            r = ns["NEW_SUBSTANCE"][c["id"]](t)
            if not r["premise_ok"]:
                no_premise.append(c["id"])
    assert not no_premise, f"전제 없음: {sorted(set(no_premise))}"
