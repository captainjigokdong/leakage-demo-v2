"""저장된 v2 데이터 시험 (2단계 2b): data/synth/ (본 데이터), data/synth_aux/ (보조 데이터).

- 테이블마다 해시 잠금 시험 하나 (압축 전 CSV의 sha256이 MANIFEST와 같은지)
- 데이터 폴더의 파일 목록 = MANIFEST의 파일 목록 + MANIFEST.json
- 파일의 열 = synth/tables_v2.py (생성기 안의 정답 값이 저장되지 않았는지도 이것으로 확인)
- 일관성: 사망 뒤 사건 0건, 자료 추출 종료 뒤 기록 0건, 기록 시각 >= 사건 시각
- 완료 기준(D23)과 결과 확인 강도 차이
"""
from __future__ import annotations

import gzip
import hashlib
import json
from functools import lru_cache
from pathlib import Path

import pytest

from synth import consistency_v2 as cv
from synth.generate_v2 import PROFILES, load
from synth.stats import kdigo_table
from synth.stats_v2 import check_criteria, summarize
from synth.tables_v2 import TABLES_V2

ROOT = Path(__file__).resolve().parent.parent
DIRS = {name: ROOT / p.out for name, p in PROFILES.items()}
MANIFEST_KEYS = {"generator", "generator_version", "profile", "seed", "n_persons", "packages", "tables"}


@lru_cache(maxsize=None)
def manifest(ds: str) -> dict:
    return json.loads((DIRS[ds] / "MANIFEST.json").read_text())


@lru_cache(maxsize=None)
def tables(ds: str) -> dict:
    return load(DIRS[ds])


@pytest.mark.parametrize("ds,table", [(d, t) for d in sorted(DIRS) for t in TABLES_V2])
def test_table_hash_matches_manifest(ds, table):
    info = manifest(ds)["tables"][table]
    raw = gzip.decompress((DIRS[ds] / info["file"]).read_bytes())
    assert hashlib.sha256(raw).hexdigest() == info["sha256_csv"]
    assert raw.count(b"\n") - 1 == info["rows"]


@pytest.mark.parametrize("ds", sorted(DIRS))
def test_folder_files_equal_manifest(ds):
    m = manifest(ds)
    assert set(m) == MANIFEST_KEYS
    assert set(m["tables"]) == set(TABLES_V2)
    assert (m["profile"], m["seed"]) == (ds, PROFILES[ds].seed)
    assert tables(ds)["person_links"]["person_id"].nunique() == m["n_persons"] == PROFILES[ds].n_persons
    files = sorted(p.name for p in DIRS[ds].iterdir())
    assert files == sorted([i["file"] for i in m["tables"].values()] + ["MANIFEST.json"])


@pytest.mark.parametrize("ds", sorted(DIRS))
def test_columns_exactly_table_list(ds):
    assert cv.column_mismatches(tables(ds)) == {}


@pytest.mark.parametrize("ds", sorted(DIRS))
def test_no_events_after_death(ds):
    bad = {k: v for k, v in cv.events_after_death(tables(ds)).items() if v}
    assert not bad


@pytest.mark.parametrize("ds", sorted(DIRS))
def test_nothing_after_extraction_end(ds):
    bad = {k: v for k, v in cv.after_extraction_end(tables(ds)).items() if v}
    assert not bad
    assert cv.unlinked_out_of_hospital(tables(ds)) == 0


@pytest.mark.parametrize("ds", sorted(DIRS))
def test_record_not_before_event(ds):
    bad = {k: v for k, v in cv.record_before_event(tables(ds)).items() if v}
    assert not bad


def test_main_criteria_and_ascertainment_differences():
    """D23: v1 기준 7개 + 결과 확인 강도 차이 4개 (ICU/병동 측정 빈도, 재입원 B 병원, 추적 외래, AKI 코드 기록률)."""
    checks = check_criteria(summarize(tables("main")))
    assert all(c.passed for c in checks), [c for c in checks if not c.passed]


def test_aux_shape():
    t = tables("aux")
    assert t["person_links"]["person_id"].nunique() == len(t["admissions"]) == 200
    assert t["labs"]["test"].nunique() == 501
    rate = kdigo_table(t["labs"][t["labs"]["test"] == "creatinine"])["aki"].mean()
    assert 0.20 <= rate <= 0.40
