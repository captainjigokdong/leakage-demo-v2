"""출처를 기록하는 특징 생성 (CLAUDE.md 절대 규칙 5).

특징은 make_feature()로만 만든다. 결과 특징은 재료 행의 꼬리표를 물려받는다.
- available_time = 재료 행들의 확인 가능 시각 최댓값 (창의 끝이 유한하면 그것도 포함:
  "창 안에 아무 일도 없었다"는 사실은 창이 닫혀야 알 수 있다)
- provenance     = 재료 행 ID 목록 + 계산 방식
- 파생 특징(derive)은 재료 특징의 확인 가능 시각 최댓값과 출처를 물려받는다

FeatureRegistry에 등록되지 않은 열은 "출처 불명"이다 (Q1~Q3 확인 불가).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from leakcheck import rules, timeline
from leakcheck.kdigo import kdigo_first
from leakcheck.tagging import available_series, person_map

from leakcheck.design import UNKNOWN  # noqa: E402
INDEX_COLUMNS = ["index_id", "admission_id", "patient_id", "person_id", "family_id", "episode_id", "site",
                 "unit", "discharge_status", "admit_time", "discharge_time", "tp", "landmark_h"]
AGGS = ("value", "last", "first", "max", "min", "mean", "count", "any", "kdigo_aki", "delta", "range", "slope")


def build_index(design: dict, tagged: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """예측 행. 고정: 입원당 하나 / 동적: 입원 × 랜드마크 (tₚ < 퇴원인 것만)."""
    adm = tagged["admissions"]
    fam = tagged["patients"].set_index("patient_id")["family_id"]
    per = person_map(tagged)
    info = tagged.get("admission_info")
    ep = info.set_index("admission_id")["episode_id"] if info is not None else None
    site = info.set_index("admission_id")["site"] if info is not None else None
    anchor = design["tp"]["anchor"]
    parts = []
    for o in design["tp"]["offsets_h"]:
        base = adm["admit_time"] if anchor == "admit" else adm["discharge_time"]
        tp = base + pd.Timedelta(hours=o)
        keep = tp < adm["discharge_time"] if anchor == "admit" else pd.Series(True, index=adm.index)
        a = adm[keep]
        parts.append(pd.DataFrame({
            "index_id": a["admission_id"] + f"@{o:g}h",
            "admission_id": a["admission_id"],
            "patient_id": a["patient_id"],
            "person_id": a["patient_id"].map(per),
            "family_id": a["patient_id"].map(fam),
            "episode_id": a["admission_id"].map(ep) if ep is not None else a["admission_id"],
            "site": a["admission_id"].map(site) if site is not None else pd.NA,
            "unit": a["unit"],
            "discharge_status": a["discharge_status"],
            "admit_time": a["admit_time"],
            "discharge_time": a["discharge_time"],
            "tp": tp[keep],
            "landmark_h": float(o),
        }))
    idx = pd.concat(parts, ignore_index=True)
    return idx.sort_values(["admission_id", "landmark_h"], kind="stable").reset_index(drop=True)


@dataclass
class FeatureResult:
    name: str
    frame: pd.DataFrame   # index_id, value, available_time, provenance
    method: str
    spec: dict

    def leaks(self, index_rows: pd.DataFrame, ref: str = "tp") -> pd.Series:
        """확인 가능 시각이 기준 시점(기본 tₚ)보다 늦은 예측 행."""
        ref_t = timeline.resolve(ref, index_rows).set_axis(index_rows["index_id"])
        at = self.frame.set_index("index_id")["available_time"].reindex(ref_t.index)
        return (at > ref_t).fillna(False)


@dataclass
class FeatureRegistry:
    """make_feature로 만든 특징의 출처 기록. 여기 없는 열은 출처 불명."""
    entries: dict[str, FeatureResult] = field(default_factory=dict)

    def add(self, r: FeatureResult) -> None:
        self.entries[r.name] = r

    def provenance_of(self, column: str) -> str:
        r = self.entries.get(column)
        return r.method if r else UNKNOWN

    def unknown_columns(self, columns) -> list[str]:
        return [c for c in columns if c not in self.entries]


def describe(spec: dict) -> str:
    """계산 방식 문자열 (provenance의 일부)."""
    if spec.get("derive"):
        dv = spec["derive"]
        return f"{dv.get('op')}({', '.join(dv.get('of', []))})"
    col = spec.get("column") or rules.table_rule(spec["source"]).value_column or "*"
    flt = ", ".join(f"{k}∈{{{','.join(map(str, v))}}}" for k, v in spec.get("filter", {}).items())
    w = spec.get("window")
    win = ""
    if w:
        tc = spec.get("time_column") or rules.default_time_column(spec["source"])
        win = f", {tc}∈({w.get('start', '-inf')}, {w.get('end', 'inf')}]"
    return f"{spec['agg']}({spec['source']}.{col}{' | ' + flt if flt else ''}{win}, scope={spec['scope']})"


# ---------------------------------------------------------------- 재료 행 고르기

def _admissions_ext(tagged: dict) -> pd.DataFrame:
    adm = tagged["admissions"][["patient_id", "admission_id", "admit_time", "discharge_time"]].copy()
    adm["person_id"] = adm["patient_id"].map(person_map(tagged))
    info = tagged.get("admission_info")
    adm["episode_id"] = (adm["admission_id"].map(info.set_index("admission_id")["episode_id"])
                         if info is not None else adm["admission_id"])
    return adm


def _admission_pairs(index_rows: pd.DataFrame, tagged: dict, scope: str, history_key: str,
                     episode: str | None) -> pd.DataFrame:
    """예측 행 → 재료 입원 (index_id, src_admission_id)."""
    key = history_key or "patient_id"
    if scope == "index_admission":
        pairs = pd.DataFrame({"index_id": index_rows["index_id"], "src_admission_id": index_rows["admission_id"]})
        if episode == "index_episode":
            adm = _admissions_ext(tagged)
            m = index_rows[["index_id", "patient_id", "episode_id", "admit_time"]].merge(
                adm.rename(columns={"admission_id": "src_admission_id", "admit_time": "src_admit"})[
                    ["patient_id", "episode_id", "src_admission_id", "src_admit"]], on=["patient_id", "episode_id"])
            m = m[m["src_admit"] < m["admit_time"]]
            pairs = pd.concat([pairs, m[["index_id", "src_admission_id"]]], ignore_index=True)
        return pairs
    adm = _admissions_ext(tagged).rename(columns={"admission_id": "src_admission_id", "admit_time": "src_admit",
                                                  "discharge_time": "src_discharge", "episode_id": "src_episode"})
    left = index_rows[["index_id", key, "admission_id", "admit_time", "episode_id"]]
    m = left.merge(adm[[key, "src_admission_id", "src_admit", "src_discharge", "src_episode"]], on=key)
    if scope == "prior_admissions":
        m = m[m["src_discharge"] <= m["admit_time"]]
        if episode == "exclude_index_episode":
            m = m[m["src_episode"] != m["episode_id"]]
    elif scope == "next_admission":
        m = m[m["src_admit"] > m["admit_time"]].sort_values(["index_id", "src_admit"])
        m = m.groupby("index_id", sort=False).head(1)
    elif scope not in ("patient_history", "patient"):
        raise ValueError(f"알 수 없는 범위: {scope}")
    return m[["index_id", "src_admission_id"]]


def _patient_pairs(index_rows: pd.DataFrame, tagged: dict, history_key: str) -> pd.DataFrame:
    """예측 행 → 재료 등록 번호 (같은 등록 번호, 또는 같은 사람의 모든 등록 번호)."""
    if (history_key or "patient_id") == "person_id":
        per = person_map(tagged)
        ids = pd.DataFrame({"src_patient_id": per.index, "person_id": per.to_numpy()})
        return index_rows[["index_id", "person_id"]].merge(ids, on="person_id")[["index_id", "src_patient_id"]]
    return pd.DataFrame({"index_id": index_rows["index_id"], "src_patient_id": index_rows["patient_id"]})


def source_rows(tagged: dict, spec: dict, index_rows: pd.DataFrame) -> pd.DataFrame:
    """명세가 고르는 (예측 행, 재료 행) 쌍. 창·필터 적용 전."""
    table = spec["source"]
    rule = rules.table_rule(table)
    src = tagged[table]
    scope = spec["scope"]
    hk = spec.get("history_key", "patient_id")
    if rule.entity_via is None:
        return index_rows[["index_id"]].merge(src, how="cross")
    if table in ("patients", "person_links"):
        return index_rows[["index_id", "patient_id"]].merge(src, on="patient_id")
    if rule.admission_column and scope in ("index_admission", "prior_admissions", "next_admission") or \
            rule.entity_via == "admission_id":
        if rule.admission_column is None:
            raise rules.RuleMissing(f"'{table}'에는 입원 범위({scope})가 없다")
        pairs = _admission_pairs(index_rows, tagged, scope, hk, spec.get("episode"))
        return pairs.merge(src, left_on="src_admission_id", right_on="_admission_id")
    if scope not in ("patient", "patient_history"):
        raise rules.RuleMissing(f"'{table}'에는 입원 범위({scope})가 없다")
    pairs = _patient_pairs(index_rows, tagged, hk)
    return pairs.merge(src, left_on="src_patient_id", right_on="_patient_id")


def _apply_filter(df: pd.DataFrame, flt: dict) -> pd.DataFrame:
    for col, vals in flt.items():
        if col not in df:
            raise rules.RuleMissing(f"필터 열 '{col}'이 테이블에 없다")
        if col in rules.CODE_COLUMNS:
            df = df[df[col].astype("string").str.startswith(tuple(str(v) for v in vals)).fillna(False)]
        else:
            df = df[df[col].isin(vals)]
    return df


def date_times(df: pd.DataFrame, col: str, how: str) -> pd.Series:
    """날짜만 있는 열 → 시각. day_end: 23:59 / day_start: 00:00."""
    day = pd.to_datetime(df[col], format="%Y-%m-%d", errors="coerce")
    return day + pd.Timedelta(hours=24) - pd.Timedelta(minutes=1) if how == "day_end" else day


def _time_values(df: pd.DataFrame, table: str, col: str, how: str | None = None) -> pd.Series:
    kind = rules.table_rule(table).time_columns.get(col)
    if kind is None:
        raise rules.RuleMissing(f"'{table}.{col}'은 규칙표의 시각 열이 아니다")
    if kind == "date":
        return date_times(df, col, how or rules.DATE_ONLY_DEFAULT)
    return df[col]


def _window_mask(m: pd.DataFrame, spec: dict, table: str, tc: str, ir: pd.DataFrame) -> np.ndarray:
    w = spec["window"]
    start = timeline.resolve(w.get("start", "-inf"), ir).reindex(m["index_id"]).to_numpy()
    end = timeline.resolve(w.get("end", "inf"), ir).reindex(m["index_id"]).to_numpy()
    if rules.table_rule(table).time_columns.get(tc) == "date":
        how = spec.get("date_compare", rules.DATE_ONLY_DEFAULT)
        if how == "same_date_ok":   # 날짜끼리 비교: 창 끝은 date ≤ date(end), 창 시작은 그날 끝 > start
            day = _time_values(m, table, tc, "day_start").to_numpy()
            end_day = pd.DatetimeIndex(end).normalize().to_numpy()
            return (_time_values(m, table, tc, "day_end").to_numpy() > start) & (day <= end_day)
        t = _time_values(m, table, tc, how).to_numpy()
    else:
        t = _time_values(m, table, tc).to_numpy()
    return (t > start) & (t <= end)


def _select_versions(m: pd.DataFrame, rule: rules.TableRule, spec: dict, ir: pd.DataFrame) -> pd.DataFrame:
    """수정 이력이 있는 테이블: as_of 시점의 버전만 남긴다."""
    entry, ver = rule.versions
    as_of = spec.get("as_of")
    if as_of == "tp":
        tp = timeline.resolve("tp", ir).reindex(m["index_id"]).to_numpy()
        m = m[m["_available_time"].to_numpy() <= tp]
    elif as_of != "latest":
        return m
    m = m.sort_values(["index_id", entry, ver], kind="stable")
    return m.groupby(["index_id", entry], sort=False).tail(1)


# ---------------------------------------------------------------- 집계

def _groups(ids: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """정렬된 id 배열 → (각 묶음의 id, 경계 위치)."""
    if len(ids) == 0:
        return ids, np.array([0])
    cut = np.flatnonzero(ids[1:] != ids[:-1]) + 1
    return ids[np.r_[0, cut]], np.r_[0, cut, len(ids)]


def _kdigo_by_group(m: pd.DataFrame, tc: str) -> pd.Series:
    m = m.sort_values(["index_id", "_order"], kind="stable")
    keys, b = _groups(m["index_id"].to_numpy())
    h = m["_order"].to_numpy().astype("datetime64[m]").astype(np.int64) / 60
    v = m["val"].to_numpy(dtype=float)
    out = [kdigo_first(h[b[i]:b[i + 1]], v[b[i]:b[i + 1]]) is not None for i in range(len(keys))]
    return pd.Series(out, index=keys, dtype=bool)


def _slope_by_group(m: pd.DataFrame) -> pd.Series:
    m = m.dropna(subset=["val_num"])
    keys, b = _groups(m["index_id"].to_numpy())
    h = m["_order"].to_numpy().astype("datetime64[m]").astype(np.int64) / 60
    v = m["val_num"].to_numpy(dtype=float)
    out = []
    for i in range(len(keys)):
        hh, vv = h[b[i]:b[i + 1]], v[b[i]:b[i + 1]]
        out.append(np.polyfit(hh - hh[0], vv, 1)[0] if len(vv) >= 2 and np.ptp(hh) > 0 else np.nan)
    return pd.Series(out, index=keys, dtype=float)


def _provenance_by_group(m: pd.DataFrame) -> pd.Series:
    keys, b = _groups(m["index_id"].to_numpy())
    p = m["_provenance"].to_numpy()
    return pd.Series([tuple(p[b[i]:b[i + 1]]) for i in range(len(keys))], index=keys, dtype=object)


def _derived(tagged, spec, index_rows, others) -> FeatureResult:
    dv = spec["derive"]
    names = dv.get("of", [])
    if not names or any(n not in (others or {}) for n in names):
        raise rules.RuleMissing(f"파생 특징 '{spec.get('name')}'의 재료 특징이 설계서에 없다 ({UNKNOWN})")
    parts = [make_feature(tagged, others[n], index_rows, others).frame.set_index("index_id") for n in names]
    ids = index_rows["index_id"]
    vals = [pd.to_numeric(p["value"].reindex(ids), errors="coerce").to_numpy(dtype=float) for p in parts]
    op = dv.get("op")
    with np.errstate(divide="ignore", invalid="ignore"):
        if op == "ratio":
            v = vals[0] / vals[1]
        elif op == "difference":
            v = vals[0] - vals[1]
        elif op == "sum":
            v = np.sum(vals, axis=0)
        elif op == "product":
            v = np.prod(vals, axis=0)
        else:
            raise ValueError(f"알 수 없는 파생 방식: {op}")
    avail = pd.concat([p["available_time"].reindex(ids) for p in parts], axis=1).max(axis=1)
    provs = [p["provenance"].reindex(ids).tolist() for p in parts]
    prov = [tuple(x for pr in row for x in (pr if isinstance(pr, tuple) else ())) for row in zip(*provs)]
    out = pd.DataFrame({"index_id": ids, "value": v, "available_time": avail.to_numpy(), "provenance": prov})
    return FeatureResult(spec["name"], out, describe(spec), spec)


def make_feature(tagged: dict[str, pd.DataFrame], spec: dict, index_rows: pd.DataFrame,
                 others: dict[str, dict] | None = None) -> FeatureResult:
    """설계서의 특징(또는 포함·제외 기준) 명세 하나를 예측 행마다 계산한다.

    others: 이름 → 명세 (파생 특징의 재료를 찾을 때)
    """
    if spec.get("derive"):
        return _derived(tagged, spec, index_rows, others)
    if "source" not in spec:
        raise rules.RuleMissing(f"특징 '{spec.get('name')}'에 source가 없다 ({UNKNOWN})")
    table = spec["source"]
    rule = rules.table_rule(table)
    col = spec.get("column") or rule.value_column
    agg = spec["agg"]
    if col is not None and col not in tagged[table]:
        raise rules.RuleMissing(f"'{table}'에 열 '{col}'이 없다")
    if col is not None:
        rules.availability(table, col)
    ir = index_rows.set_index("index_id")

    m = source_rows(tagged, spec, index_rows)
    m = m.assign(_available_time=available_series(m, table, spec.get("column")).to_numpy())
    if rule.versions and spec.get("as_of") and spec.get("version_order", "version_then_filter") == "version_then_filter":
        m = _select_versions(m, rule, spec, ir)
        m = _apply_filter(m, spec.get("filter", {}))
    else:
        m = _apply_filter(m, spec.get("filter", {}))
        if rule.versions and spec.get("as_of"):
            m = _select_versions(m, rule, spec, ir)

    tc = spec.get("time_column") or rules.default_time_column(table)
    w = spec.get("window")
    if w:
        if tc is None:
            raise rules.RuleMissing(f"'{table}'에는 창을 적용할 시각 열이 없다")
        m = m[_window_mask(m, spec, table, tc, ir)]
    order = _time_values(m, table, tc, spec.get("date_compare")) if tc else m["_available_time"]
    val = m[col].to_numpy() if col else np.full(len(m), np.nan)
    m = m.assign(_order=order.to_numpy(), val=val)
    if table == "patients" and col == "age" and spec.get("age_reference") == "index_admission":
        adm_t = ir["admit_time"].reindex(m["index_id"]).to_numpy()
        years = (adm_t - m["_first_admit"].to_numpy()) / np.timedelta64(1, "D") / 365.25
        m["val"] = np.minimum(pd.to_numeric(m["val"]).to_numpy() + np.floor(years), 95)
    m["val_num"] = pd.to_numeric(m["val"], errors="coerce")

    m = m.sort_values(["index_id", "_order"], kind="stable")
    g = m.groupby("index_id", sort=False)
    if agg == "count":
        val = g.size()
    elif agg == "any":
        val = g.size() > 0
    elif agg in ("value", "last"):
        val = g["val"].last()
    elif agg == "first":
        val = g["val"].first()
    elif agg in ("max", "min", "mean"):
        val = getattr(g["val_num"], agg)()
    elif agg == "delta":
        val = g["val_num"].last() - g["val_num"].first()
    elif agg == "range":
        val = g["val_num"].max() - g["val_num"].min()
    elif agg == "slope":
        val = _slope_by_group(m)
    elif agg == "kdigo_aki":
        val = _kdigo_by_group(m, tc)
    else:
        raise ValueError(f"알 수 없는 집계: {agg}")

    ids = index_rows["index_id"]
    out = pd.DataFrame({"index_id": ids})
    v = val.reindex(ids)
    if agg == "count":
        v = v.fillna(0).astype(int)
    elif agg in ("any", "kdigo_aki"):
        v = v.astype("boolean").fillna(False).astype(bool)
    out["value"] = v.to_numpy()
    avail = g["_available_time"].max().reindex(ids)
    if w and timeline.parse(w.get("end", "inf")).anchor != "inf":
        wend = timeline.resolve(w["end"], index_rows).set_axis(ids)
        avail = pd.concat([avail, wend], axis=1).max(axis=1)
    out["available_time"] = avail.to_numpy()
    prov = _provenance_by_group(m).reindex(ids)
    out["provenance"] = [p if isinstance(p, tuple) else () for p in prov]
    return FeatureResult(spec["name"], out, describe(spec), spec)


def feature_matrix(results: list[FeatureResult], index_rows: pd.DataFrame) -> tuple[pd.DataFrame, FeatureRegistry]:
    reg = FeatureRegistry()
    X = index_rows[["index_id"]].copy()
    for r in results:
        reg.add(r)
        X[r.name] = r.frame.set_index("index_id")["value"].reindex(X["index_id"]).to_numpy()
    return X, reg
