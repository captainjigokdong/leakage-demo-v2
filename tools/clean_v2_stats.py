"""4단계 4a: 깨끗한 설계서 8개의 기술 통계 (판정이 아니다. 모델 성능은 계산하지 않는다).

점검기의 데이터 준비·분할·결과 계산 함수(leakcheck.checks.prepare_data, leakcheck.splitting.assign,
leakcheck.outcomes.label)를 그대로 써서, 설계서마다 아래를 센다. 점검기 판정 함수(run_checks)는 부르지 않는다.

1. 분할: 학습·평가·미사용 행 수와 평가 쪽 결과 사건 수
2. 동적 결과의 시각 기준: tp 전 채취·tp 뒤 보고(pending) 사건, 창 끝 직전 채취·창 뒤 보고 사건
3. 공통 수정으로 바뀐 칸(분할, 전처리 적합 범위)을 대상으로 하는 공개 패치(E05~E08)의 전제를 새 설계서 기준으로 다시 확인

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
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args(argv)
    tables = load_tables(DATA)
    res = {}
    for p in sorted(CLEAN.glob("*.json")):
        if args.only and p.stem not in args.only:
            continue
        d = dz.normalize(json.loads(p.read_text(encoding="utf-8")))
        ctx, rows = cohort(d, tables)
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
