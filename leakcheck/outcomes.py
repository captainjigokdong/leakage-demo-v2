"""결과 정의. 결정 카드의 결과율(기술 통계)에 쓴다. 모델 성능과는 무관하다.

- next_admission   결과 창 안에 같은 등록 번호(match_key=person_id면 같은 사람)의 입원이 시작됨.
                   planned=exclude면 planned_by 조건에 맞는 입원은 사건으로 세지 않는다
- kdigo_creatinine 결과 창 안에 채취된 크레아티닌이 KDIGO 기준을 만족 (각 값을 그보다 먼저 잰 값과 비교)
                   비교 대상 측정은 reference_window ∪ 결과 창 안의 것만 쓴다
- diagnosis_code   이번 입원의 진단 코드가 filter에 맞음
- censoring.death = composite_outcome이면 결과 창 안 사망도 양성 (death_source가 원내만이면 원내 사망만)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from leakcheck import timeline
from leakcheck.features import _apply_filter, make_feature
from leakcheck.kdigo import kdigo_event


def _deaths_in_window(o: dict, d: dict, tagged, index_rows) -> pd.Series:
    spec = {"name": "_death", "source": "deaths", "scope": "patient_history", "filter": {},
            "time_column": "death_time", "window": o["window"], "agg": "any",
            "history_key": o.get("match_key", "patient_id")}
    if d.get("data_source", {}).get("death_source") == "in_hospital_only":
        spec["filter"] = {"place": ["in_hospital"]}
    return make_feature(tagged, spec, index_rows).frame.set_index("index_id")["value"].astype(bool)


def label(design: dict, tagged: dict[str, pd.DataFrame], index_rows: pd.DataFrame) -> pd.Series:
    """예측 행마다 결과 (index_id → bool)."""
    o = design["outcome"]
    ids = index_rows["index_id"]
    if o["definition"] == "next_admission":
        spec = {"name": o["name"], "source": "admissions", "scope": "patient_history", "filter": o["filter"],
                "time_column": o.get("time_column", "admit_time"), "window": o["window"], "agg": "any",
                "history_key": o.get("match_key", "patient_id")}
        pb = o.get("planned_by")
        if o.get("planned") == "exclude" and pb and pb.get("source") == "admission_info" and "admission_info" in tagged:
            planned = set(_apply_filter(tagged["admission_info"], pb.get("filter", {}))["admission_id"])
            keep = tagged["admissions"][~tagged["admissions"]["admission_id"].isin(planned)]
            tagged = {**tagged, "admissions": keep}
        y = make_feature(tagged, spec, index_rows).frame.set_index("index_id")["value"].astype(bool)
    elif o["definition"] == "kdigo_creatinine":
        tc = o.get("time_column", "collect_time")
        labs = _apply_filter(tagged["labs"], o["filter"])
        m = index_rows[["index_id", "admission_id"]].merge(
            labs[["_admission_id", tc, "value"]], left_on="admission_id", right_on="_admission_id")
        ir = index_rows.set_index("index_id")
        ref = o.get("reference_window", {})
        lo = timeline.resolve(ref.get("start", o["window"].get("start", "-inf")), ir).reindex(m["index_id"])
        ws = timeline.resolve(o["window"].get("start", "-inf"), ir).reindex(m["index_id"])
        we = timeline.resolve(o["window"].get("end", "inf"), ir).reindex(m["index_id"])
        t = m[tc].to_numpy()
        m = m.assign(_in=(t > ws.to_numpy()) & (t <= we.to_numpy()))
        m = m[(t > lo.to_numpy()) & (t <= we.to_numpy())].sort_values(["index_id", tc])
        out = {}
        for iid, g in m.groupby("index_id", sort=False):
            if not g["_in"].any():
                continue
            h = (g[tc] - g[tc].iloc[0]).dt.total_seconds().to_numpy() / 3600
            out[iid] = kdigo_event(h, g["value"].to_numpy(dtype=float), g["_in"].to_numpy())
        y = pd.Series(out, dtype=bool).reindex(ids, fill_value=False).set_axis(ids)
    elif o["definition"] == "diagnosis_code":
        spec = {"name": o["name"], "source": "diagnoses", "scope": o.get("scope", "index_admission"),
                "filter": o["filter"], "agg": "any"}
        y = make_feature(tagged, spec, index_rows).frame.set_index("index_id")["value"].astype(bool)
    else:
        raise ValueError(f"알 수 없는 결과 정의: {o['definition']}")
    if o.get("censoring", {}).get("death") == "composite_outcome" and "deaths" in tagged:
        y = y.reindex(ids).to_numpy() | _deaths_in_window(o, design, tagged, index_rows).reindex(ids).to_numpy()
        y = pd.Series(np.asarray(y, dtype=bool), index=ids)
    return y.reindex(ids).astype(bool)
