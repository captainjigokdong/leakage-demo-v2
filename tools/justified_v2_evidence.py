"""4a: 정당한 지적 목록(docs/justified_findings_v2.json)의 근거 숫자를 깨끗한 설계서 기준으로 다시 센다.

판정이 아니다. 점검기 판정 함수(run_checks)와 모델 성능은 부르지 않는다. 점검기의 데이터 준비·특징·분할·결과
함수와 원자료로 센다. 에이전트가 센 숫자는 쓰지 않는다 (승인 C 결정 5).

- 코호트: 동적은 점검기 코호트 + end_of_data(결과 창 끝이 추출 종료 뒤인 행 제외) = 설계서 코호트.
  고정은 거기에 cohort.rows_per_unit(에피소드마다 마지막 입원 기록)을 더한다 — 점검기 코호트는 이 칸을 쓰지 않는다
  (known_issues_v2.md K5). 승인 C 넘길 메모: 고정 유형은 설계서대로 고른 코호트를 쓴다.

실행: python -m tools.justified_v2_evidence [--only L1 L2 ...]
"""
from __future__ import annotations

import argparse
import copy
import json

import numpy as np
import pandas as pd

from leakcheck import design as dz
from leakcheck import rules, splitting
from leakcheck.data import load as load_tables
from leakcheck.features import _apply_filter, _window_mask, make_feature, source_rows
from leakcheck.tagging import available_series
from leakcheck.outcomes import label
from tools.clean_v2_stats import (CLEAN, DATA, DATA_START, _kdigo, cohort, d4_outcome_flips, dynamic_timing,
                                  outcome)

NAMES = ["aki_a", "aki_b", "aki_c", "aki_d", "readmit_a", "readmit_b", "readmit_c", "readmit_d"]
HISTORY_SCOPES = {"prior_admissions", "patient_history"}
# last 집계에서 "확인 가능 시각"과 따로 "잰 시각"이 있는 테이블 (데이터 설명서)
MEASURED_TIME = {"labs": "collect_time", "vitals": "charted_time"}


def load(name: str) -> dict:
    return dz.normalize(json.loads((CLEAN / f"{name}.json").read_text(encoding="utf-8")))


def design_rows(d: dict, tables: dict):
    """설계서대로 고른 코호트. 고정은 에피소드의 마지막 입원 기록만 (rows_per_unit)."""
    ctx, rows = cohort(d, tables)
    rpu = d["cohort"].get("rows_per_unit")
    if rpu and rpu != {"unit": "admission", "choose": "all"}:
        assert rpu == {"unit": "episode", "choose": "last"}, rpu
        adm = tables["admissions"].merge(tables["admission_info"][["admission_id", "episode_id"]], on="admission_id")
        last = adm.sort_values("admit_time").groupby("episode_id")["admission_id"].last()
        rows = rows[rows["admission_id"].isin(set(last))].reset_index(drop=True)
    return ctx, rows


def episode_order(tables: dict) -> pd.DataFrame:
    adm = tables["admissions"].merge(tables["admission_info"][["admission_id", "episode_id"]], on="admission_id")
    adm = adm.sort_values(["episode_id", "admit_time"])
    adm["rec_no"] = adm.groupby("episode_id").cumcount()
    adm["n_rec"] = adm.groupby("episode_id")["admission_id"].transform("size")
    return adm


# --- 항목별 -------------------------------------------------------------------

def l1_death_source(d, ctx, rows, tables) -> dict:
    """사망 출처를 연계 자료로 바꾸면 결과가 바뀌는 행, 결과 창 끝이 사망 연계 반영일 뒤인 행."""
    y0 = outcome(d, ctx, rows)
    dd = copy.deepcopy(d)
    dd["data_source"]["death_source"] = "linked_registry"
    y1 = outcome(dd, ctx, rows)
    through = pd.Timestamp(tables["extract_info"]["death_linkage_through"].iloc[0])
    after = int((rows["tp"] + pd.Timedelta(hours=48) > through).sum())
    return {"rows": len(rows), "outcome_changes": int((y0 != y1).sum()), "neg_to_pos": int((~y0 & y1).sum()),
            "window_end_after_linkage": after, "linkage_through": str(through.date())}


def l2_record_scope(d, ctx, rows, tables) -> dict:
    """결과·기준값·제외 기준이 입원 기록 단위인 것의 영향."""
    ep = episode_order(tables).set_index("admission_id")
    r = rows.join(ep[["episode_id", "rec_no", "n_rec"]], on="admission_id", rsuffix="_e")
    multi = r[r["n_rec"] > 1]
    first = r[r["rec_no"] < r["n_rec"] - 1]                       # 뒤 기록이 있는 기록의 랜드마크
    cross = first[(first["discharge_time"] > first["tp"]) &
                  (first["discharge_time"] <= first["tp"] + pd.Timedelta(hours=48))]
    later = r[r["rec_no"] > 0]
    # 뒤 기록 랜드마크 중, 같은 에피소드 앞 기록의 크레아티닌(tp까지 보고)으로 이미 KDIGO AKI인 행
    labs = ctx.tagged["labs"]
    cr = labs[labs["test"] == "creatinine"][["_admission_id", "collect_time", "report_time", "value", "method"]]
    epi = ep.reset_index()[["admission_id", "episode_id", "rec_no"]]
    cr = cr.merge(epi, left_on="_admission_id", right_on="admission_id")
    known = 0
    for _, row in later.iterrows():
        prev = cr[(cr["episode_id"] == row["episode_id"]) & (cr["rec_no"] < row["rec_no"]) &
                  (cr["report_time"] <= row["tp"])]
        found = False
        for _, g in prev.groupby("admission_id"):               # 결과 정의처럼 같은 입원 기록 값끼리만 비교
            g = g.sort_values("collect_time")
            h = (g["collect_time"] - g["collect_time"].iloc[0]).dt.total_seconds().to_numpy() / 3600
            if _kdigo(h, g["value"].to_numpy(dtype=float), np.ones(len(g), bool), g["method"].to_numpy()):
                found = True
                break
        known += found
    # 제외 기준 aki_known_by_tp에 episode: index_episode를 다시 넣으면 바뀌는 행
    specs = {f["name"]: f for f in d["features"]}
    ex = next(e for e in d["cohort"]["exclusion"] if e["name"] == "aki_known_by_tp")
    with_ep = dict(ex, episode="index_episode")
    a = make_feature(ctx.tagged, ex, rows, specs).frame["value"].to_numpy()
    b = make_feature(ctx.tagged, with_ep, rows, specs).frame["value"].to_numpy()
    return {"rows": len(rows), "episodes_multi_record": int(multi["episode_id"].nunique()),
            "landmarks_in_nonlast_record": len(first), "window_crosses_record_end": len(cross),
            "landmarks_in_later_record": len(later), "later_record_aki_already_in_earlier_record": int(known),
            "exclusion_episode_changes": int((a != b).sum())}


def l3_pending(d, ctx, rows, tables) -> dict:
    return {"rows": len(rows), "pending_kdigo_rows": dynamic_timing(ctx, rows)["pending_kdigo_rows"]}


def l4_method(d, ctx, rows, tables) -> dict:
    r = d4_outcome_flips(ctx, rows)
    return {"rows": len(rows), "neg_to_pos": r["C_neg_to_pos"], "pos_to_neg": r["C_pos_to_neg"],
            "B_neg_to_pos": r["B_neg_to_pos"], "B_pos_to_neg": r["B_pos_to_neg"]}


def l5_split(d, ctx, rows, tables) -> dict:
    lab = splitting.assign(rows, d["split"]).to_numpy()
    return {"rows": len(rows), "method": d["split"]["method"], "unused": int((lab == splitting.UNUSED).sum())}


def l6_history_key(d, ctx, rows, tables) -> dict:
    pl = tables["person_links"]
    n_ids = pl.groupby("person_id")["patient_id"].nunique()
    multi = set(n_ids[n_ids > 1].index)
    return {"persons_multi_id": len(multi), "persons": int(len(n_ids)),
            "cohort_rows_of_those": int(rows["person_id"].isin(multi).sum()), "rows": len(rows)}


def l8_family(d, ctx, rows, tables) -> dict:
    p = tables["patients"]
    return {"family_missing": int(p["family_id"].isna().sum()), "patients": int(len(p)),
            "cohort_rows_family_missing": int(rows["family_id"].isna().sum()), "rows": len(rows)}


def l9_sites(d, ctx, rows, tables) -> dict:
    return {"rows": len(rows), "discharge_status": rows["discharge_status"].value_counts().to_dict(),
            "sites_covered": str(tables["extract_info"]["sites_covered"].iloc[0])}


def l10_left_trunc(d, ctx, rows, tables) -> dict:
    lab = splitting.assign(rows, d["split"]).to_numpy()
    short = ((rows["tp"] - DATA_START) < pd.Timedelta(days=365)).to_numpy()
    tr = lab == "train"
    return {"train_rows": int(tr.sum()), "short_365d": int((tr & short).sum()),
            "fraction": round(float((tr & short).sum() / tr.sum()), 4)}


def _last_by(ctx, spec, rows, measured: str) -> tuple[pd.Series, pd.Series]:
    """make_feature와 같은 행 선택(출처·필터·창)에서 last를 두 순서로: time_column 순 / 잰 시각 순."""
    table = spec["source"]
    ir = rows.set_index("index_id")
    m = source_rows(ctx.tagged, spec, rows)
    m = m.assign(_available_time=available_series(m, table, spec.get("column")).to_numpy())
    m = _apply_filter(m, spec.get("filter", {}))
    tc = spec["time_column"]
    m = m[_window_mask(m, spec, table, tc, ir)]
    col = spec.get("column") or rules.table_rule(table).value_column
    a = m.sort_values(["index_id", tc], kind="stable").groupby("index_id")[col].last()
    b = m.sort_values(["index_id", measured], kind="stable").groupby("index_id")[col].last()
    return a, b


def l11_last_order(d, ctx, rows, tables) -> dict:
    """last 집계 특징: time_column(보고·입력 시각) 순 마지막 값과 잰 시각 순 마지막 값이 다른 행."""
    specs = {f["name"]: f for f in d["features"]}
    out = {}
    for f in d["features"]:
        if f.get("agg") != "last" or f["source"] not in MEASURED_TIME or f.get("time_column") == MEASURED_TIME[f["source"]]:
            continue
        a, b = _last_by(ctx, f, rows, MEASURED_TIME[f["source"]])
        ref = make_feature(ctx.tagged, f, rows, specs).frame.set_index("index_id")["value"]
        same_as_checker = bool((pd.to_numeric(ref.reindex(a.index)) - pd.to_numeric(a)).abs().fillna(0).max() < 1e-9)
        out[f["name"]] = {"time_column": f["time_column"], "rows_with_value": int(len(a)),
                          "differ": int((a != b.reindex(a.index)).sum()), "same_as_checker": same_as_checker}
    return {"rows": len(rows), "features": out}


ITEMS = {"L1": (l1_death_source, "dynamic"), "L2": (l2_record_scope, "dynamic"), "L3": (l3_pending, "dynamic"),
         "L4": (l4_method, "dynamic"), "L5": (l5_split, "temporal"), "L6": (l6_history_key, "all"),
         "L8": (l8_family, "all"), "L9": (l9_sites, "fixed"), "L10": (l10_left_trunc, "all"),
         "L11": (l11_last_order, "all")}


def applies(kind: str, d: dict) -> bool:
    return (kind == "all" or kind == d["design_type"] or (kind == "temporal" and d["split"]["method"] == "temporal"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--designs", nargs="*")
    args = ap.parse_args(argv)
    tables = load_tables(DATA)
    for name in args.designs or NAMES:
        d = load(name)
        ctx, rows = design_rows(d, tables)
        for lid, (fn, kind) in ITEMS.items():
            if (args.only and lid not in args.only) or not applies(kind, d):
                continue
            print(name, lid, json.dumps(fn(d, ctx, rows, tables), ensure_ascii=False, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
