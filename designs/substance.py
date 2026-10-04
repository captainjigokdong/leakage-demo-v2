"""실질 확인 (v2 2단계 2c): 패치를 적용한 설계가 잠긴 데이터에서 깨끗한 설계와 어떻게 다른가.

두 단계로 센다 (2c 진행 중 사용자 결정으로 다듬음, docs/injection_log_v2.md).
- (1) 전제(premise): 결함이 기대는 사실이 잠긴 데이터에 있는가. 0이면 멈추고 보고한다.
- (2) 수치 차이(difference): 그 결함이 값이나 대상 행을 실제로 얼마나 바꾸는가. 0이어도 기록만 한다.
- 점검기 판정과 모델 성능은 계산하지 않는다 (CLAUDE.md 절대 규칙 6).
- 예측 행은 시험용 기본 설계서(`designs/prereview/`)의 코호트를 근사한다:
  동적 = 성인 + tp에 입원 중 + tp까지 투석 오더 없음, 고정 = 성인 + 생존 퇴원 + 2158-12-01 이전 퇴원 + 에피소드의 마지막 입원.
  tp까지 이미 AKI인 행은 빼지 않는다 (근사).
- 여기의 계산은 사례 확인용이다. 모형 특징은 이 모듈로 만들지 않는다 (절대 규칙 5).
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

SEED = 20261040          # 시험용 기본 설계서의 split.seed
TEST_FRACTION = 0.3
OFFSETS_H = [24, 48, 72, 96, 120, 144, 168]
FOLLOWUP_CUTOFF = pd.Timestamp("2158-12-01")


@lru_cache(maxsize=1)
def tables() -> dict[str, pd.DataFrame]:
    from synth.generate_v2 import load
    return load()


# --- 예측 행 ---------------------------------------------------------------

@lru_cache(maxsize=1)
def dynamic_rows() -> pd.DataFrame:
    T = tables()
    a = T["admissions"].merge(T["patients"][["patient_id", "family_id", "age"]], on="patient_id")
    a = a[a["age"] >= 18]
    rows = pd.concat([a.assign(offset_h=h, tp=a["admit_time"] + pd.Timedelta(hours=h)) for h in OFFSETS_H])
    rows = rows[rows["discharge_time"] > rows["tp"]]
    dial = T["orders"][T["orders"]["order_type"] == "dialysis_order"]
    first_dial = dial.groupby("admission_id")["order_time"].min()
    rows = rows[~(rows["admission_id"].map(first_dial) <= rows["tp"])]
    rows = rows.assign(landmark_row_id=rows["admission_id"] + "_" + rows["offset_h"].astype(str))
    return rows.sort_values(["admission_id", "offset_h"]).reset_index(drop=True)


@lru_cache(maxsize=1)
def fixed_rows() -> pd.DataFrame:
    T = tables()
    a = T["admissions"].merge(T["patients"][["patient_id", "family_id", "age"]], on="patient_id")
    a = a.merge(T["admission_info"][["admission_id", "site", "episode_id"]], on="admission_id")
    a = a[(a["age"] >= 18) & (a["discharge_status"] != "died") & (a["discharge_time"] <= FOLLOWUP_CUTOFF)]
    a = a.sort_values("discharge_time").groupby("episode_id", as_index=False).tail(1)
    rows = a.assign(tp=a["discharge_time"], landmark_row_id=a["admission_id"])
    return rows.sort_values("admission_id").reset_index(drop=True)


def rows_of(kind: str) -> pd.DataFrame:
    return dynamic_rows() if kind == "dynamic" else fixed_rows()


def person_of() -> pd.Series:
    pl = tables()["person_links"]
    return pl.set_index("patient_id")["person_id"]


# --- 공통 계산 --------------------------------------------------------------

def creatinine() -> pd.DataFrame:
    labs = tables()["labs"]
    return labs[labs["test"] == "creatinine"]


def asof(rows: pd.DataFrame, events: pd.DataFrame, time_col: str, value_cols: list[str]) -> pd.DataFrame:
    """행마다 같은 입원에서 time_col <= tp인 마지막 사건의 value_cols (없으면 NaN)."""
    ev = events.dropna(subset=[time_col]).sort_values(time_col)[["admission_id", time_col, *value_cols]]
    r = rows[["landmark_row_id", "admission_id", "tp"]].sort_values("tp")
    m = pd.merge_asof(r, ev, left_on="tp", right_on=time_col, by="admission_id", direction="backward")
    return m.set_index("landmark_row_id").reindex(rows["landmark_row_id"])[value_cols]


def cumulative(events: pd.DataFrame, time_col: str) -> pd.DataFrame:
    """입원 안에서 time_col 순서로 누적 최댓값(cum_max)과 누적 개수(cum_n)."""
    ev = events.dropna(subset=[time_col]).sort_values(["admission_id", time_col]).copy()
    g = ev.groupby("admission_id")["value"]
    ev["cum_max"] = g.cummax()
    ev["cum_n"] = g.cumcount() + 1
    return ev


def in_window(rows: pd.DataFrame, events: pd.DataFrame, time_col: str, hours: float) -> pd.Series:
    """행마다 같은 입원에서 tp < time_col <= tp+hours인 사건 수."""
    m = rows[["landmark_row_id", "admission_id", "tp"]].merge(events[["admission_id", time_col]], on="admission_id")
    hit = (m[time_col] > m["tp"]) & (m[time_col] <= m["tp"] + pd.Timedelta(hours=hours))
    n = m[hit].groupby("landmark_row_id").size()
    return rows["landmark_row_id"].map(n).fillna(0).astype(int)


def holdout_test(keys: pd.Series, seed: int = SEED, frac: float = TEST_FRACTION) -> pd.Series:
    """묶음 열 값마다 평가 부분(True)/학습 부분(False)을 무작위로 정한다."""
    uniq = np.sort(keys.dropna().unique())
    rng = np.random.default_rng(seed)
    test = dict(zip(uniq, rng.random(len(uniq)) < frac))
    return keys.map(test)


def split_frame(rows: pd.DataFrame, key: str) -> pd.Series:
    """key 열로 분할하되 결측이면 사람(person_id)으로 (기본 설계서의 fallback_key)."""
    k = rows[key] if key in rows else rows["landmark_row_id"]
    fb = rows["patient_id"].map(person_of())
    return holdout_test(k.astype(object).where(k.notna(), "P:" + fb.astype(str)))


def groups_on_both_sides(rows: pd.DataFrame, is_test: pd.Series, group: pd.Series) -> int:
    df = pd.DataFrame({"g": group.values, "t": is_test.values}).dropna(subset=["g"])
    return int((df.groupby("g")["t"].nunique() == 2).sum())


def fixed_outcome(rows: pd.DataFrame, sites: tuple[str, ...] = ("A", "B")) -> pd.Series:
    """고정 설계 결과 근사: 같은 사람의 (tp, tp+30d] 예정되지 않은 입원(sites에서) 또는 사망."""
    T = tables()
    pid = person_of()
    adm = T["admissions"].merge(T["admission_info"][["admission_id", "site", "admission_type"]], on="admission_id")
    adm = adm[(adm["admission_type"] != "elective") & adm["site"].isin(sites)]
    adm = adm.assign(person_id=adm["patient_id"].map(pid))
    r = rows[["landmark_row_id", "patient_id", "tp"]].assign(person_id=rows["patient_id"].map(pid))
    m = r.merge(adm[["person_id", "admit_time"]], on="person_id")
    hit = (m["admit_time"] > m["tp"]) & (m["admit_time"] <= m["tp"] + pd.Timedelta(days=30))
    readmit = set(m.loc[hit, "landmark_row_id"])
    d = T["deaths"].assign(person_id=T["deaths"]["patient_id"].map(pid))
    md = r.merge(d[["person_id", "death_time"]], on="person_id")
    dhit = (md["death_time"] > md["tp"]) & (md["death_time"] <= md["tp"] + pd.Timedelta(days=30))
    died = set(md.loc[dhit, "landmark_row_id"])
    return rows["landmark_row_id"].isin(readmit | died).astype(int)


def result(premise: float, premise_detail: str, diff: float, diff_detail: str) -> dict:
    return {"premise": float(premise), "premise_ok": bool(premise > 0), "premise_detail": premise_detail,
            "difference": float(diff), "difference_detail": diff_detail}


# --- 특징 근사 (실질 확인용) ---------------------------------------------------

def lab(test: str) -> pd.DataFrame:
    labs = tables()["labs"]
    return labs[labs["test"] == test]


def vital(item: str) -> pd.DataFrame:
    v = tables()["vitals"]
    return v[v["item"] == item]


def to_tp(rows, events, time_col, agg):
    """같은 입원에서 time_col <= tp인 값의 last / min / max."""
    ev = events.dropna(subset=[time_col]).sort_values(["admission_id", time_col]).copy()
    if agg == "last":
        return asof(rows, ev, time_col, ["value"])["value"].values
    ev["c"] = ev.groupby("admission_id")["value"].cummin() if agg == "min" else ev.groupby("admission_id")["value"].cummax()
    return asof(rows, ev, time_col, ["c"])["c"].values


def window(rows, events, time_col, hours, agg):
    """같은 입원에서 tp-hours < time_col <= tp인 값의 집계."""
    m = rows[["landmark_row_id", "admission_id", "tp"]].merge(events[["admission_id", time_col, "value"]],
                                                            on="admission_id")
    m = m[(m[time_col] > m["tp"] - pd.Timedelta(hours=hours)) & (m[time_col] <= m["tp"])]
    return rows["landmark_row_id"].map(m.groupby("landmark_row_id")["value"].agg(agg)).values


def imputed_columns(kind: str) -> dict[str, np.ndarray]:
    """시험용 기본 설계서의 median_impute 대상 열 (파생 열 제외)."""
    rows = rows_of(kind)
    cr = creatinine()
    if kind == "dynamic":
        return {"cr_last": to_tp(rows, cr, "report_time", "last"), "cr_min_adm": to_tp(rows, cr, "report_time", "min"),
                "cr_max_48h": window(rows, cr, "report_time", 48, "max"),
                "bun_last": to_tp(rows, lab("bun"), "report_time", "last"),
                "k_last": to_tp(rows, lab("potassium"), "report_time", "last"),
                "hgb_min": to_tp(rows, lab("hemoglobin"), "report_time", "min"),
                "sbp_min_24h": window(rows, vital("sbp"), "entered_time", 24, "min"),
                "hr_max_24h": window(rows, vital("heart_rate"), "entered_time", 24, "max"),
                "temp_max_24h": window(rows, vital("temperature"), "entered_time", 24, "max")}
    return {"cr_last": to_tp(rows, cr, "report_time", "last"),
            "hgb_min": to_tp(rows, lab("hemoglobin"), "report_time", "min"),
            "sbp_last": window(rows, vital("sbp"), "entered_time", 24, "last")}


def split_groups(rows: pd.DataFrame) -> np.ndarray:
    k = rows["family_id"]
    return k.astype(object).where(k.notna(), "P:" + rows["patient_id"].map(person_of()).astype(str)).values


# --- v1 사례 18개 -----------------------------------------------------------

def e01(kind):
    rows = rows_of(kind)
    dx = tables()["diagnoses"]
    late = rows.merge(dx[["admission_id", "coded_time"]], on="admission_id")
    n = late[late["coded_time"] > late["tp"]]["landmark_row_id"].nunique()
    return result(n, f"이번 입원 진단 코드가 tp 뒤에 코딩된 행 {n:,}/{len(rows):,}",
                  n, f"tp까지 알려진 코드만 셀 때와 특징 값이 다른 행 {n:,}")


def e02(kind):
    rows = rows_of(kind)
    cr = creatinine()
    m = rows[["landmark_row_id", "admission_id", "tp"]].merge(cr[["admission_id", "collect_time", "report_time"]],
                                                            on="admission_id")
    pend = m[(m["collect_time"] <= m["tp"]) & (m["report_time"] > m["tp"])]["landmark_row_id"].nunique()
    a, b = to_tp(rows, cr, "collect_time", "last"), to_tp(rows, cr, "report_time", "last")
    n = int((~((a == b) | (np.isnan(a) & np.isnan(b)))).sum())
    return result(pend, f"tp 전에 채취했지만 tp 뒤에 보고된 크레아티닌이 있는 행 {pend:,}/{len(rows):,}",
                  n, f"마지막 크레아티닌 값이 달라지는 행 {n:,}")


def e03(kind):
    rows = rows_of(kind)
    cr = creatinine()
    after = in_window(rows, cr, "report_time", 24 * 3650)
    p = int((after > 0).sum())
    whole = rows["admission_id"].map(cr.groupby("admission_id")["value"].max()).values
    n = int((whole > np.nan_to_num(to_tp(rows, cr, "report_time", "max"), nan=-np.inf)).sum())
    return result(p, f"tp 뒤에 보고된 크레아티닌이 있는 행 {p:,}/{len(rows):,}",
                  n, f"입원 전체 최댓값이 tp까지 최댓값보다 커서 값이 달라지는 행 {n:,}")


def e04(kind):
    rows = rows_of(kind)
    pr = tables()["procedures"].assign(day=lambda d: pd.to_datetime(d["chart_date"]).dt.normalize())
    m = rows[["landmark_row_id", "admission_id", "tp"]].merge(pr[["admission_id", "day"]], on="admission_id")
    n = m[m["day"] == m["tp"].dt.normalize()]["landmark_row_id"].nunique()
    return result(n, f"tp와 같은 날짜의 시술(날짜만 있음)이 있는 행 {n:,}/{len(rows):,}",
                  n, f"날짜끼리 비교에서만 시술이 들어가 특징 값이 달라지는 행 {n:,}")


def e05(kind):
    rows = rows_of(kind)
    p = int((rows.groupby("admission_id").size() >= 2).sum())
    t = holdout_test(rows["landmark_row_id"])
    n, m = groups_on_both_sides(rows, t, rows["admission_id"]), groups_on_both_sides(rows, t, rows["patient_id"])
    return result(p, f"예측 행이 2개 이상인 입원 {p:,}",
                  n, f"행 단위 분할에서 학습·평가 양쪽에 행이 있는 입원 {n:,} (등록 번호 {m:,})")


def e06(kind):
    rows = rows_of(kind)
    p = int((rows.groupby("patient_id").size() >= 2).sum())
    n = groups_on_both_sides(rows, holdout_test(rows["admission_id"]), rows["patient_id"])
    return result(p, f"예측 행이 2개 이상인 등록 번호 {p:,}",
                  n, f"입원 단위 분할에서 학습·평가 양쪽에 입원이 있는 등록 번호 {n:,}")


def e07(kind):
    rows = rows_of(kind)
    p = int((rows.dropna(subset=["family_id"]).groupby("family_id")["patient_id"].nunique() >= 2).sum())
    n = groups_on_both_sides(rows, split_frame(rows, "patient_id"), rows["family_id"])
    return result(p, f"예측 행에 등록 번호가 2개 이상인 가족 {p:,}",
                  n, f"환자 단위 분할에서 학습·평가 양쪽에 구성원이 있는 가족 {n:,}")


def e08(kind):
    from sklearn.model_selection import GroupKFold
    rows = rows_of(kind)
    test = split_frame(rows, "family_id").astype(bool).values
    groups = split_groups(rows)
    tr = np.where(~test)[0]
    folds = list(GroupKFold(5).split(tr, groups=groups[tr]))
    n_missing = n_test_missing = n_changed = n_fold_diff = 0
    for x in imputed_columns(kind).values():
        miss = np.isnan(x)
        n_missing += int(miss.sum())
        n_test_missing += int((miss & test).sum())
        if np.nanmedian(x) != np.nanmedian(x[~test]):
            n_changed += int(miss.sum())
        n_fold_diff += sum(np.nanmedian(x[tr][a]) != np.nanmedian(x) for a, _ in folds)
    return result(n_missing, f"대치 대상 열의 결측 {n_missing:,}칸 (평가 부분 {n_test_missing:,}칸, 평가 부분이 적합에 들어감)",
                  n_changed, f"최종 분할 기준 채워지는 값이 달라지는 칸 {n_changed:,}"
                             f" (조율 5폴드: 학습 폴드 중앙값이 전체 중앙값과 다른 열×폴드 {n_fold_diff})")


def _prior_dx_main(rows):
    T = tables()
    dx = T["diagnoses"][T["diagnoses"]["seq"] == 1]
    dx = dx.merge(T["admissions"][["admission_id", "patient_id"]], on="admission_id")
    m = rows[["landmark_row_id", "patient_id", "admission_id", "tp"]].merge(
        dx[["patient_id", "admission_id", "icd_code", "coded_time"]], on="patient_id", suffixes=("", "_dx"))
    m = m[(m["admission_id_dx"] != m["admission_id"]) & (m["coded_time"] <= m["tp"])]
    return rows["landmark_row_id"].map(m.sort_values("coded_time").groupby("landmark_row_id")["icd_code"].last())


def e09(kind):
    rows = rows_of(kind)
    code, y = _prior_dx_main(rows), fixed_outcome(rows)
    test = split_frame(rows, "family_id").astype(bool).values
    df = pd.DataFrame({"code": code.values, "y": y.values, "test": test}).dropna(subset=["code"])
    enc_all = df.groupby("code")["y"].mean()
    enc_tr = df[~df["test"]].groupby("code")["y"].mean()
    changed = df["code"].map(enc_all) != df["code"].map(enc_tr)
    p = int(df["test"].sum())
    return result(p, f"주진단 코드가 있는 행 {len(df):,} 중 평가 부분 {p:,} (결과가 인코딩에 들어감)",
                  int(changed.sum()), f"인코딩 값이 전체·학습 부분에서 다른 행 {int(changed.sum()):,}"
                                      f" (코드 {int((enc_all != enc_tr.reindex(enc_all.index)).sum())}/{len(enc_all)}종)")


def e10(kind):
    from sklearn.feature_selection import f_classif
    rows = rows_of(kind)
    y = (fixed_outcome(rows) if kind == "fixed" else in_window(rows, creatinine(), "collect_time", 48) > 0).astype(int)
    X = pd.DataFrame({k: v for k, v in imputed_columns(kind).items()}).assign(age=rows["age"].values)
    X = X.fillna(X.median())
    test = split_frame(rows, "family_id").astype(bool).values
    f_all, _ = f_classif(X, y)
    f_tr, _ = f_classif(X[~test], y[~test])
    k = min(5, X.shape[1])
    top_all, top_tr = set(np.argsort(-f_all)[:k]), set(np.argsort(-f_tr)[:k])
    n = int((~np.isclose(f_all, f_tr)).sum())
    return result(int(test.sum()), f"평가 부분 {int(test.sum()):,}행의 결과가 선택 점수에 들어감",
                  n, f"단변량 F 점수가 다른 특징 {n}/{X.shape[1]}, 상위 {k}개 중 바뀐 특징 {len(top_all - top_tr)}")


def e11(kind):
    rows = rows_of(kind)
    n_in = in_window(rows, creatinine(), "collect_time", 48)
    p, n = int((n_in >= 1).sum()), int((n_in >= 2).sum())
    return result(p, f"결과 창 (tp, tp+48h]에 크레아티닌이 있는 행 {p:,}/{len(rows):,}",
                  n, f"그 창의 값으로 변화량이 계산되는 행 {n:,}")


def e12(kind):
    rows = rows_of(kind)
    adm = tables()["admissions"]
    nxt = rows[["landmark_row_id", "patient_id", "tp"]].merge(adm[["patient_id", "admit_time"]], on="patient_id")
    has_next = rows["landmark_row_id"].isin(set(nxt[nxt["admit_time"] > nxt["tp"]]["landmark_row_id"]))
    y = fixed_outcome(rows)
    n = int(has_next.sum())
    return result(n, f"다음 입원이 있는 행 {n:,}/{len(rows):,}",
                  n, f"특징 값이 생기는 행 {n:,} (결과 양성 {int(y.sum()):,}행 중 {int((has_next & (y == 1)).sum()):,})")


def e13(kind):
    rows = rows_of(kind)
    o = tables()["orders"]
    o = o[o["order_type"].isin(["dialysis_order", "nephrology_consult"])]
    m = rows[["landmark_row_id", "admission_id", "tp"]].merge(o[["admission_id", "order_time"]], on="admission_id")
    n = m[m["order_time"] <= m["tp"]]["landmark_row_id"].nunique()
    return result(n, f"tp까지 투석·신장내과 협진 오더가 있는 행 {n:,}/{len(rows):,}",
                  n, f"특징 값이 참인 행 {n:,}")


def e14(kind):
    rows = rows_of(kind)
    los = (rows["discharge_time"] - rows["admit_time"]) / pd.Timedelta(hours=1)
    p = int((rows["discharge_time"] > rows["tp"]).sum())
    n = int((los < 168).sum())
    return result(p, f"재원 기간이 tp 뒤에 정해지는 행 {p:,}/{len(rows):,}",
                  n, f"재원 7일 미만이라 포함 기준으로 빠지는 행 {n:,}")


def e15(kind):
    rows = rows_of(kind)
    cr = creatinine()
    p = int((in_window(rows, cr, "report_time", 24 * 3650) > 0).sum())
    ev = cumulative(cr, "report_time")
    by_tp = asof(rows, ev, "report_time", ["cum_n"])["cum_n"].fillna(0).values
    whole = rows["admission_id"].map(cr.groupby("admission_id").size()).fillna(0).values
    n = int(((whole >= 3) & (by_tp < 3)).sum())
    return result(p, f"tp 뒤에 보고된 크레아티닌이 있는 행 {p:,}/{len(rows):,}",
                  n, f"tp 뒤 측정까지 세어야 3회 이상이 되어 포함되는 행 {n:,} (포함 기준으로 빠지는 행 {int((whole < 3).sum()):,})")


def e16(kind):
    rows = rows_of(kind)
    v = tables()["outpatient_visits"]
    m = rows[["landmark_row_id", "patient_id", "tp"]].merge(v[["patient_id", "visit_time"]], on="patient_id")
    has = rows["landmark_row_id"].isin(set(m[m["visit_time"] > m["tp"]]["landmark_row_id"]))
    y = fixed_outcome(rows)
    n = int((~has).sum())
    return result(n, f"퇴원 뒤 외래 방문이 없는 행 {n:,}/{len(rows):,}"
                     f" (결과율: 방문 있음 {y[has].mean():.3f}, 없음 {y[~has].mean():.3f})",
                  n, f"포함 기준으로 빠지는 행 {n:,}")


def e17(kind):
    rows = rows_of(kind)
    unit = asof(rows, tables()["transfers"], "in_time", ["unit"])["unit"].values
    n_in = in_window(rows, creatinine(), "collect_time", 48).values
    icu, ward = n_in[unit == "ICU"].mean(), n_in[unit == "ward"].mean()
    p = int(min((unit == "ICU").sum(), (unit == "ward").sum()))
    return result(p, f"tp에 ICU {int((unit == 'ICU').sum()):,}행, 병동 {int((unit == 'ward').sum()):,}행이 함께 있음",
                  icu - ward, f"결과 창 크레아티닌 측정 수 평균: ICU {icu:.2f}, 병동 {ward:.2f}")


def e18(kind):
    rows = rows_of(kind)
    y_all, y_a = fixed_outcome(rows), fixed_outcome(rows, sites=("A",))
    missed = (y_all == 1) & (y_a == 0)
    n = int(missed.sum())
    by = rows.assign(missed=missed.values).groupby("discharge_status")["missed"].mean()
    rates = ", ".join(f"{k} {v:.3f}" for k, v in by.items())
    return result(n, f"B 병원에서만 확인되는 결과 양성 행 {n:,}/{int(y_all.sum()):,}",
                  n, f"A 병원만 볼 때 놓치는 행 {n:,} (퇴원처별 놓치는 비율: {rates})")


V1_SUBSTANCE = {"E01": e01, "E02": e02, "E03": e03, "E04": e04, "E05": e05, "E06": e06, "E07": e07,
                "E08": e08, "E09": e09, "E10": e10, "E11": e11, "E12": e12, "E13": e13, "E14": e14,
                "E15": e15, "E16": e16, "E17": e17, "E18": e18}
