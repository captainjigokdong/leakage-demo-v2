"""v2 데이터 일관성 검사 (2단계 2b). 위반 행 수를 센다. 저장된 데이터와 생성 직후 데이터 모두에 쓴다.

- 사건 시각 열(EVENT_TIME_COLUMNS)은 그 사람의 사망 시각 뒤 0건 (등록 번호가 둘이면 person_id로 묶어 본다)
- 모든 시각·날짜 열은 자료 추출 종료 시각 뒤 0건. admission_bookings.planned_date만 예외 (예정일, D9)
- 기록 시각 열(RECORD_TIME_COLUMNS)은 자기 사건 시각 이상 (원내 사망은 기록 = 사망 시각, D3)
- 원외 사망의 기록 날짜는 death_linkage_through 이하
"""
from __future__ import annotations

import pandas as pd

from synth.tables_v2 import EVENT_TIME_COLUMNS, RECORD_TIME_COLUMNS, TABLES_V2

EXEMPT_FROM_EXTRACTION_END = {("admission_bookings", "planned_date")}
ADMISSION_LINKED = ("transfers", "labs", "vitals", "medications", "orders", "procedures", "diagnoses")
DATE_ONLY = {("procedures", "chart_date"), ("admission_bookings", "planned_date"),
             ("extract_info", "death_linkage_through")}


def _as_time(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s)


def column_mismatches(tables: dict[str, pd.DataFrame]) -> dict[str, list[str]]:
    """{테이블: 실제 열} 중 TABLES_V2와 이름·순서가 다른 것. 테이블 집합이 다르면 그것도."""
    out = {t: list(df.columns) for t, df in tables.items() if list(df.columns) != TABLES_V2.get(t)}
    for t in set(TABLES_V2) - set(tables):
        out[t] = ["(테이블 없음)"]
    return out


def _person_of(tables) -> tuple[pd.Series, pd.Series]:
    links = tables["person_links"].set_index("patient_id")["person_id"]
    adm_person = tables["admissions"].set_index("admission_id")["patient_id"].map(links)
    return links, adm_person


def death_times(tables) -> pd.Series:
    links, _ = _person_of(tables)
    d = tables["deaths"]
    return _as_time(d["death_time"]).groupby(d["patient_id"].map(links)).min()


def events_after_death(tables, deaths: pd.Series | None = None) -> dict[str, int]:
    """사건 시각이 사망 시각보다 뒤인 행 수. deaths를 주면 그 사망 시각(person_id → 시각)으로 본다."""
    links, adm_person = _person_of(tables)
    death = death_times(tables) if deaths is None else deaths
    out = {}
    for t, cols in EVENT_TIME_COLUMNS.items():
        if t == "deaths":
            continue
        df = tables[t]
        person = (df["admission_id"].map(adm_person) if t in ADMISSION_LINKED and t != "admissions"
                  else df["patient_id"].map(links))
        dt = person.map(death)
        for c in cols:
            v = _as_time(df[c])
            if (t, c) in DATE_ONLY:   # 날짜만: 사망한 날보다 뒤 날짜면 위반
                bad = v > dt.dt.normalize()
            else:
                bad = v > dt
            out[f"{t}.{c}"] = int(bad.fillna(False).sum())
    return out


def after_extraction_end(tables) -> dict[str, int]:
    end = _as_time(tables["extract_info"]["extraction_end_time"]).iloc[0]
    out = {}
    for t, cols in TABLES_V2.items():
        for c in cols:
            if (t, c) in EXEMPT_FROM_EXTRACTION_END:
                continue
            if not (c.endswith("_time") or c.endswith("_date") or c == "death_linkage_through"):
                continue
            v = _as_time(tables[t][c])
            out[f"{t}.{c}"] = int((v > end).sum())
    return out


def record_before_event(tables) -> dict[str, int]:
    adm = tables["admissions"].set_index("admission_id")
    out = {}
    for t, m in RECORD_TIME_COLUMNS.items():
        df = tables[t]
        for col, ref in m.items():
            rec = _as_time(df[col])
            if ref.startswith("admissions."):
                ev = _as_time(df["admission_id"].map(adm[ref.split(".")[1]]))
            else:
                ev = _as_time(df[ref])
            out[f"{t}.{col}"] = int((rec < ev).sum())
    return out


def unlinked_out_of_hospital(tables) -> int:
    """원외 사망 중 기록 날짜가 death_linkage_through 뒤인 행 수 (연계 반영 사망만 있어야 한다)."""
    through = pd.Timestamp(tables["extract_info"]["death_linkage_through"].iloc[0])
    d = tables["deaths"]
    ooh = d[d["place"] == "out_of_hospital"]
    return int((_as_time(ooh["death_recorded_time"]).dt.normalize() > through).sum())


def report(tables) -> dict:
    return {"columns": column_mismatches(tables), "after_death": events_after_death(tables),
            "after_extraction_end": after_extraction_end(tables), "record_before_event": record_before_event(tables),
            "unlinked_out_of_hospital": unlinked_out_of_hospital(tables)}


def violations(rep: dict) -> int:
    n = len(rep["columns"]) + rep["unlinked_out_of_hospital"]
    for k in ("after_death", "after_extraction_end", "record_before_event"):
        n += sum(rep[k].values())
    return n
