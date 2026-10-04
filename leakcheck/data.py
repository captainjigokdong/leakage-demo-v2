"""데이터 폴더 읽기 (점검기 자체 로더, 2026-10-04 사용자 결정 D7).

규칙표(leakcheck/rules.py)에 있는 테이블을 <이름>.csv.gz에서 읽는다. 데이터 생성기를 쓰지 않는다.
- 시각 열(datetime)은 시각으로, 날짜 열(date)과 식별·코드 열은 문자열로 읽는다
- 규칙표에 없는 파일은 읽지 않는다 (MANIFEST.json 등)
"""
from __future__ import annotations

from pathlib import Path

from leakcheck import rules

# 숫자처럼 보여도 문자로 읽어야 하는 열 (식별자, 코드, 날짜)
STRING_COLUMNS = {"family_id", "source_admission_id", "admission_id", "patient_id", "visit_id", "icd_code",
                  "code", "sites_covered"}


class DataError(FileNotFoundError):
    pass


def load(folder: str | Path) -> dict:
    import pandas as pd
    folder = Path(folder)
    if not folder.is_dir():
        raise DataError(f"데이터 폴더가 없다: {folder}")
    missing = [n for n in rules.TABLES if not (folder / f"{n}.csv.gz").exists()]
    if missing:
        raise DataError(f"데이터 폴더 {folder}에 테이블 파일이 없다: {', '.join(f'{m}.csv.gz' for m in missing)}")
    tables = {}
    for name, rule in rules.TABLES.items():
        strings = STRING_COLUMNS | {c for c, k in rule.time_columns.items() if k == "date"}
        head = pd.read_csv(folder / f"{name}.csv.gz", nrows=0).columns
        df = pd.read_csv(folder / f"{name}.csv.gz", dtype={c: "string" for c in head if c in strings})
        for c, k in rule.time_columns.items():
            if k == "datetime" and c in df:
                df[c] = pd.to_datetime(df[c])
        tables[name] = df
    return tables
