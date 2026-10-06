"""4단계 4a: 깨끗한 설계서 8개의 기술 통계 (판정이 아니다. 모델 성능은 계산하지 않는다).

점검기의 데이터 준비·분할·결과 계산 함수(leakcheck.checks.prepare_data, leakcheck.splitting.assign,
leakcheck.outcomes.label)를 그대로 써서, 설계서마다 아래를 센다. 점검기 판정 함수(run_checks)는 부르지 않는다.

1. 분할: 학습·평가·미사용 행 수와 평가 쪽 결과 사건 수
2. 동적 결과의 시각 기준: tp 전 채취·tp 뒤 보고(pending) 사건, 창 끝 직전 채취·창 뒤 보고 사건
3. 공통 수정으로 바뀐 칸(분할, 전처리 적합 범위)을 대상으로 하는 공개 패치(E05~E08)의 전제를 새 설계서 기준으로 다시 확인
5. (--d4) 결과 판정에도 jaffe −0.10 보정을 하면 KDIGO 사건 여부가 바뀌는 행 수
4. (--star) "수상해 보이지만 정당한 항목" 4개의 근거: 점검기 특징 계산의 확인 가능 시각, 그리고 원자료로 따로 센 값

실행: python -m tools.clean_v2_stats [--only 이름 ...]
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd

from designs.inject import apply_ops
from designs.patches_v1_cases import V1_CASE_PATCHES
from leakcheck import design as dz
from leakcheck import splitting
from leakcheck.checks import prepare_data
from leakcheck.data import load as load_tables
from leakcheck.features import make_feature
from leakcheck.outcomes import label
from leakcheck.kdigo import kdigo_event

ROOT = Path(__file__).resolve().parent.parent
CLEAN = ROOT / "designs" / "clean_v2"
DATA = ROOT / "data" / "synth"
EXTRACTION_END = pd.Timestamp("2160-01-01")
WINDOW_H = {"dynamic": 48.0, "fixed": 30 * 24.0}


def cohort(d: dict, tables: dict):
    """점검기 코호트 + end_of_data=exclude_incomplete(결과 창 끝이 추출 종료 뒤인 행 제외)."""
    ctx = prepare_data(d, tables)
    rows = ctx.cohort
    keep = rows["tp"] + pd.Timedelta(hours=WINDOW_H[d["design_type"]]) <= EXTRACTION_END
    return ctx, rows[keep].reset_index(drop=True)


def outcome(d: dict, ctx, rows) -> pd.Series:
    dd = copy.deepcopy(d)
    dd["outcome"].setdefault("filter", {})          # 고정 설계는 outcome.filter가 비어 있다 (해당 없음)
    return label(dd, ctx.tagged, rows).reindex(rows["index_id"]).to_numpy()


def split_table(d: dict, rows, y) -> dict:
    lab = splitting.assign(rows, d["split"]).to_numpy()
    out = {}
    for part in ("train", "test", splitting.UNUSED):
        m = lab == part
        out[part] = {"rows": int(m.sum()), "events": int(y[m].sum())}
    return out


def dynamic_timing(ctx, rows) -> dict:
    """크레아티닌 KDIGO 사건의 시각 기준. 결과 창은 채취 시각(collect_time) 기준이다."""
    labs = ctx.tagged["labs"]
    cr = labs[labs["test"] == "creatinine"][["_admission_id", "collect_time", "report_time", "value"]]
    m = rows[["index_id", "admission_id", "tp"]].merge(cr, left_on="admission_id", right_on="_admission_id")
    lo = m["tp"] - pd.Timedelta(hours=168)
    hi = m["tp"] + pd.Timedelta(hours=48)
    m = m[(m["collect_time"] > lo) & (m["collect_time"] <= hi)].sort_values(["index_id", "collect_time"])
    pending = late = only_late = 0
    for _, g in m.groupby("index_id", sort=False):
        h = (g["collect_time"] - g["collect_time"].iloc[0]).dt.total_seconds().to_numpy() / 3600
        v = g["value"].to_numpy(dtype=float)
        tp = g["tp"].iloc[0]
        ct, rt = g["collect_time"], g["report_time"]
        pend = ((ct <= tp) & (rt > tp)).to_numpy()
        inw = ((ct > tp) & (ct <= tp + pd.Timedelta(hours=48))).to_numpy()
        lt = inw & (rt > tp + pd.Timedelta(hours=48)).to_numpy()
        if pend.any() and kdigo_event(h, v, pend):
            pending += 1
        if lt.any() and kdigo_event(h, v, lt):
            late += 1
            if not kdigo_event(h, v, inw & ~lt):
                only_late += 1
    return {"pending_kdigo_rows": pending, "late_report_kdigo_rows": late, "only_late_report_rows": only_late}


def _imputed(d: dict, ctx, rows) -> dict[str, np.ndarray]:
    specs = {f["name"]: f for f in d["features"]}
    cols = next(s for s in d["preprocessing"] if s["name"] == "median_impute")["columns"]
    out = {}
    for c in cols:
        r = make_feature(ctx.tagged, specs[c], rows, specs)
        out[c] = pd.to_numeric(r.frame.set_index("index_id")["value"].reindex(rows["index_id"]),
                               errors="coerce").to_numpy(dtype=float)
    return out


def premises(d: dict, ctx, rows) -> dict:
    """공통 수정으로 바뀐 칸을 대상으로 하는 공개 패치의 전제·수치 차이 (2c 기준을 새 설계서로)."""
    t = d["design_type"]
    out = {}
    base_lab = splitting.assign(rows, d["split"])
    used = base_lab != splitting.UNUSED

    def both_sides(lab, col):
        return splitting.crossing(rows, lab, col)[0]

    for cid in ("E05", "E06", "E07"):
        ops = V1_CASE_PATCHES[cid]
        try:
            pd_ = apply_ops(d, ops)
        except (KeyError, ValueError):
            continue
        if cid == "E05" and t != "dynamic" or cid == "E06" and t != "fixed":
            continue
        lab = splitting.assign(rows, pd_["split"])
        if cid == "E05":
            prem = int((rows[used].groupby("admission_id").size() >= 2).sum())
            out[cid] = {"premise": prem, "difference": both_sides(lab, "admission")}
        elif cid == "E06":
            prem = int((rows[used].groupby("patient_id").size() >= 2).sum())
            out[cid] = {"premise": prem, "difference": both_sides(lab, "patient")}
        else:
            r = rows[used].dropna(subset=["family_id"])
            prem = int((r.groupby("family_id")["patient_id"].nunique() >= 2).sum())
            out[cid] = {"premise": prem, "difference": both_sides(lab, "family")}
    # E08: median_impute.fit_scope → all
    test = (base_lab == "test").to_numpy()
    train = (base_lab == "train").to_numpy()
    n_miss = n_test_miss = n_changed = 0
    for x in _imputed(d, ctx, rows).values():
        miss = np.isnan(x)
        n_miss += int((miss & (train | test)).sum())
        n_test_miss += int((miss & test).sum())
        if np.nanmedian(x[train | test]) != np.nanmedian(x[train]):
            n_changed += int((miss & (train | test)).sum())
    out["E08"] = {"premise": n_test_miss, "missing_cells": n_miss, "difference": n_changed}
    out.update(premises_round1(d, ctx, rows, base_lab))
    return out


def _feat_values(d: dict, ctx, rows, spec: dict) -> pd.Series:
    specs = {f["name"]: f for f in d["features"]}
    r = make_feature(ctx.tagged, spec, rows, specs)
    return r.frame.set_index("index_id")["value"].reindex(rows["index_id"])


def premises_round1(d: dict, ctx, rows, base_lab) -> dict:
    """(E14·E15 패치에는 scope가 없어 이번 입원으로 세운다. 계산용일 뿐 패치는 바꾸지 않는다.)
    검수 1회차 고침(D3·D4·F1·F2·F3)으로 바뀐 칸을 대상으로 하는 공개 패치: E02(cr_last), E09(특징·전처리),
    E14·E15(코호트, D3로 바뀜). E08(전처리 목록)은 위에서 센다."""
    from leakcheck.checks import _criterion_mask
    t = d["design_type"]
    out = {}
    labs = ctx.tagged["labs"]
    cr = labs[labs["test"] == "creatinine"]
    m = rows[["index_id", "admission_id", "tp"]].merge(cr[["_admission_id", "collect_time", "report_time"]],
                                                       left_on="admission_id", right_on="_admission_id")
    # E02: cr_last의 시각 열을 채취 시각으로
    pend = m[(m["collect_time"] <= m["tp"]) & (m["report_time"] > m["tp"])]["index_id"].nunique()
    base = _feat_values(d, ctx, rows, next(f for f in d["features"] if f["name"] == "cr_last"))
    pd_ = apply_ops(d, V1_CASE_PATCHES["E02"])
    pat = _feat_values(pd_, ctx, rows, next(f for f in pd_["features"] if f["name"] == "cr_last"))
    out["E02"] = {"premise": int(pend), "difference": int((base.fillna(-1) != pat.fillna(-1)).sum())}
    if t == "fixed":
        # E09: 이전 입원 주진단 범주에 전체 데이터로 결과율 인코딩
        pd_ = apply_ops(d, V1_CASE_PATCHES["E09"])
        code = _feat_values(pd_, ctx, rows, next(f for f in pd_["features"] if f["name"] == "prior_dx_main"))
        y = outcome(d, ctx, rows)
        lab = base_lab.to_numpy()
        df = pd.DataFrame({"code": code.to_numpy(), "y": y, "test": lab == "test", "used": lab != splitting.UNUSED})
        df = df[df["used"]].dropna(subset=["code"])
        enc_all = df.groupby("code")["y"].mean()
        enc_tr = df[~df["test"]].groupby("code")["y"].mean()
        changed = df["code"].map(enc_all) != df["code"].map(enc_tr)
        out["E09"] = {"premise": int(df["test"].sum()), "difference": int(changed.sum())}
    else:
        # E14: 재원 7일 이상 포함 기준 (재원 기간은 tp 뒤에 정해짐)
        pd_ = apply_ops(d, V1_CASE_PATCHES["E14"])
        spec = dict(next(c for c in pd_["cohort"]["inclusion"] if c["name"] == "los_7d"), scope="index_admission")
        keep = _criterion_mask(ctx.tagged, spec, rows)
        out["E14"] = {"premise": int((rows["discharge_time"] > rows["tp"]).sum()), "difference": int((~keep).sum())}
        # E15: 입원 전체에서 크레아티닌 3회 이상 (tp 뒤 보고 포함)
        pd_ = apply_ops(d, V1_CASE_PATCHES["E15"])
        spec = dict(next(c for c in pd_["cohort"]["inclusion"] if c["name"] == "cr_monitored"), scope="index_admission")
        to_tp = dict(spec, window={"start": "admit", "end": "tp"})
        a, b = _criterion_mask(ctx.tagged, spec, rows), _criterion_mask(ctx.tagged, to_tp, rows)
        late = m[m["report_time"] > m["tp"]]["index_id"].nunique()
        out["E15"] = {"premise": int(late), "difference": int((a != b).sum()), "excluded": int((~a).sum())}
    return out


STAR = {"aki_b": ("k_last_6h", "labs", "report_time"), "aki_c": ("n_admissions_to_tp", "admissions", "admit_time"),
        "readmit_b": ("prior_dx_group", "diagnoses", "coded_time"), "readmit_c": ("prior_cr_last", "labs", "report_time")}


def star_evidence(d: dict, ctx, rows, tables) -> dict:
    """★ 항목: (1) 점검기 특징 계산의 확인 가능 시각 > tp인 행 수 (2) 원자료로 따로: 특징이 읽는 행의 '알려지는 시각' 열."""
    name, table, tcol = STAR[d["design_id"]]
    specs = {f["name"]: f for f in d["features"]}
    spec = specs[name]
    r = make_feature(ctx.tagged, spec, rows, specs)
    late = int(r.leaks(rows).sum())
    has = int(r.frame["value"].notna().sum()) if spec["agg"] != "count" else int((r.frame["value"] > 0).sum())
    out = {"feature": name, "rows": int(len(rows)), "rows_with_value": has, "checker_available_after_tp": late}
    # 원자료: 같은 등록 번호의 행 중 특징이 읽는 행을 직접 고른다
    T = tables
    ir = rows[["index_id", "patient_id", "admission_id", "tp"]]
    if name == "k_last_6h":
        src = T["labs"][T["labs"]["test"] == "potassium"][["admission_id", "collect_time", "report_time"]]
        m = ir.merge(src, on="admission_id")
        used = m[(m["report_time"] > m["tp"] - pd.Timedelta(hours=6)) & (m["report_time"] <= m["tp"])]
        out["collected_before_tp_all"] = bool((used["collect_time"] <= used["tp"]).all())
    elif name == "n_admissions_to_tp":
        src = T["admissions"][["patient_id", "admission_id", "admit_time", "discharge_time"]]
        m = ir.merge(src, on="patient_id", suffixes=("", "_h"))
        used = m[m["admit_time"] <= m["tp"]]
        out["index_admission_counted_rows"] = int((used["admission_id_h"] == used["admission_id"]).groupby(used["index_id"]).any().sum())
        out["other_admission_ongoing_at_tp"] = int(((used["admission_id_h"] != used["admission_id"]) &
                                                   (used["discharge_time"] > used["tp"])).sum())
    elif name == "prior_dx_group":
        dx = T["diagnoses"][T["diagnoses"]["seq"] == 1].merge(T["admissions"][["admission_id", "patient_id"]],
                                                                on="admission_id")
        m = ir.merge(dx[["patient_id", "admission_id", "icd_code", "coded_time"]], on="patient_id", suffixes=("", "_h"))
        m = m[m["admission_id_h"] != m["admission_id"]]
        used = m[m["coded_time"] <= m["tp"]]
        out["prior_dx_coded_after_tp_not_used"] = int((m["coded_time"] > m["tp"]).sum())
        out["categories"] = int(used["icd_code"].nunique())
    else:
        src = T["labs"][T["labs"]["test"] == "creatinine"].merge(T["admissions"][["admission_id", "patient_id"]],
                                                                  on="admission_id")
        m = ir.merge(src[["patient_id", "admission_id", "report_time"]], on="patient_id", suffixes=("", "_h"))
        m = m[m["admission_id_h"] != m["admission_id"]]
        used = m[m["report_time"] <= m["tp"]]
        out["prior_reported_after_tp_not_used"] = int((m["report_time"] > m["tp"]).sum())
    used_t = used[tcol]
    out["source_rows_used"] = int(len(used))
    out["max_hours_known_minus_tp"] = float(((used_t - used["tp"]).dt.total_seconds() / 3600).max())
    return out


JAFFE_OFFSET = 0.10   # 설명서 labs.value: 크레아티닌은 jaffe 측정이면 0.10 mg/dL 높음 (생성기 고정값)


def _kdigo(h, v, events, same) -> bool:
    """events 중 하나가 그보다 먼저 채취한 값(same이 있으면 같은 측정법만)과 비교해 KDIGO를 만족하는가."""
    for j in np.flatnonzero(events):
        prior = np.arange(len(v)) < j
        if same is not None:
            prior &= same == same[j]
        rel = prior & (h >= h[j] - 168)
        if rel.any() and v[j] >= 1.5 * v[rel].min() - 1e-9:
            return True
        ab = prior & (h >= h[j] - 48)
        if ab.any() and v[j] - v[ab].min() >= 0.3 - 1e-9:
            return True
    return False


def d4_outcome_flips(ctx, rows) -> dict:
    """결과(크레아티닌 KDIGO)의 세 판정: A 지금 정의(같은 측정법끼리, 보정 없음), B jaffe −0.10 보정 뒤 측정법 무관 비교,
    C jaffe −0.10 보정 뒤 같은 측정법끼리. 사건 = tp에 보고되지 않았고 tp+48h까지 채취된 값. 사망은 넣지 않는다."""
    labs = ctx.tagged["labs"]
    cr = labs[labs["test"] == "creatinine"][["_admission_id", "collect_time", "report_time", "value", "method"]]
    m = rows[["index_id", "admission_id", "tp"]].merge(cr, left_on="admission_id", right_on="_admission_id")
    m = m[(m["collect_time"] > m["tp"] - pd.Timedelta(hours=168)) &
          (m["collect_time"] <= m["tp"] + pd.Timedelta(hours=48))].sort_values(["index_id", "collect_time"])
    res = {"A": set(), "B": set(), "C": set()}
    mixed = set()
    for iid, g in m.groupby("index_id", sort=False):
        h = (g["collect_time"] - g["collect_time"].iloc[0]).dt.total_seconds().to_numpy() / 3600
        v = g["value"].to_numpy(dtype=float)
        meth = g["method"].to_numpy()
        ev = (g["report_time"] > g["tp"]).to_numpy()
        adj = v - np.where(meth == "jaffe", JAFFE_OFFSET, 0.0)
        if len(set(meth)) > 1:
            mixed.add(iid)
        if _kdigo(h, v, ev, meth):
            res["A"].add(iid)
        if _kdigo(h, adj, ev, None):
            res["B"].add(iid)
        if _kdigo(h, adj, ev, meth):
            res["C"].add(iid)
    a = res["A"]
    out = {"rows": int(len(rows)), "rows_mixed_method_window": len(mixed), "positive_A_current": len(a)}
    for k in ("B", "C"):
        out[f"{k}_pos_to_neg"] = len(a - res[k])
        out[f"{k}_neg_to_pos"] = len(res[k] - a)
        out[f"{k}_flips_in_mixed"] = len((a ^ res[k]) & mixed)
    return out


DATA_START = pd.Timestamp("2150-01-01")


def left_truncation(d: dict, rows) -> dict:
    """왼쪽 절단 (2회차 새 지적): 학습 행 중 tp까지의 관찰 기간(연구 시작 2150-01-01부터)이 365일 미만인 비율."""
    lab = splitting.assign(rows, d["split"]).to_numpy()
    short = ((rows["tp"] - DATA_START) < pd.Timedelta(days=365)).to_numpy()
    tr = lab == "train"
    return {"train_rows": int(tr.sum()), "short_365d": int((tr & short).sum()),
            "fraction": round(float((tr & short).sum() / tr.sum()), 4)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--star", action="store_true", help="★ 항목 근거만")
    ap.add_argument("--lefttrunc", action="store_true", help="학습 행 중 이력 365일 미만 비율")
    ap.add_argument("--d4", action="store_true", help="결과 판정에 jaffe 보정을 할 때 바뀌는 행 수 (동적만)")
    args = ap.parse_args(argv)
    tables = load_tables(DATA)
    res = {}
    for p in sorted(CLEAN.glob("*.json")):
        if args.only and p.stem not in args.only:
            continue
        d = dz.normalize(json.loads(p.read_text(encoding="utf-8")))
        ctx, rows = cohort(d, tables)
        if args.d4:
            if d["design_type"] == "dynamic":
                print(p.stem, json.dumps(d4_outcome_flips(ctx, rows), ensure_ascii=False), flush=True)
            continue
        if args.lefttrunc:
            print(p.stem, json.dumps(left_truncation(d, rows), ensure_ascii=False), flush=True)
            continue
        if args.star:
            if d["design_id"] in STAR:
                print(p.stem, json.dumps(star_evidence(d, ctx, rows, tables), ensure_ascii=False), flush=True)
            continue
        y = outcome(d, ctx, rows)
        r = {"rows": int(len(rows)), "events": int(y.sum()), "split": split_table(d, rows, y)}
        if d["design_type"] == "dynamic":
            r["timing"] = dynamic_timing(ctx, rows)
        r["premises"] = premises(d, ctx, rows)
        res[p.stem] = r
        print(p.stem, json.dumps(r, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
