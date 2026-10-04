"""v2 합성 EHR의 기술 통계, 완료 기준(D23), 결과 확인 강도 차이.

모델 성능은 계산하지 않는다 (CLAUDE.md 절대 규칙 6). 결과율·표본 수·빈도 같은 기술 통계만 계산한다.
v1과 비교할 수 있게 v1 정의(synth/stats.py: KDIGO, 등록 번호 기준 30일 재입원)를 그대로 쓴다.
"""
from __future__ import annotations

from math import comb

import pandas as pd

from synth.stats import Check, kdigo_table, readmission_table

TARGET_RATE = (0.10, 0.20)
MIN_MULTI_ADMIT_FRAC = 0.20
MIN_POST_DISCHARGE_LAB_FRAC = 0.02
MIN_FAMILY_PAIRS = 30
MIN_LOCATION_RATIO = 2.0   # leakcheck.rules.Q7_RATIO_THRESHOLD와 같은 값 (규칙표는 고치지 않고 값만 맞춤)


def location_lab_rates(tables: dict[str, pd.DataFrame], test: str = "creatinine") -> dict[str, float]:
    """머문 병동(transfers) 기준 하루당 검사 횟수. {"ICU": x, "ward": y}."""
    tr, labs = tables["transfers"], tables["labs"]
    lab = labs.loc[labs["test"] == test, ["admission_id", "collect_time"]]
    m = lab.merge(tr[["admission_id", "unit", "in_time", "out_time"]], on="admission_id")
    m = m[(m["collect_time"] >= m["in_time"]) & (m["collect_time"] < m["out_time"])]
    days = (tr["out_time"] - tr["in_time"]).dt.total_seconds() / 86400
    out = {}
    for unit in ("ICU", "ward"):
        out[unit] = float((m["unit"] == unit).sum() / days[tr["unit"] == unit].sum())
    return out


def ascertainment(tables: dict[str, pd.DataFrame]) -> dict:
    """결과 확인 강도 차이 (데이터에 실제로 있는지)."""
    adm, info = tables["admissions"], tables["admission_info"]
    a = adm.merge(info, on="admission_id").sort_values(["patient_id", "admit_time"])
    a["next_admit"] = a.groupby("patient_id")["admit_time"].shift(-1)
    a["next_site"] = a.groupby("patient_id")["site"].shift(-1)
    alive = a[a["discharge_status"] != "died"]
    r30 = alive[(alive["next_admit"] - alive["discharge_time"]) <= pd.Timedelta(days=30)]
    b_share = r30.groupby("discharge_status")["next_site"].apply(lambda s: float((s == "B").mean())).to_dict()

    # 추적 외래: 생존 퇴원 뒤 5~28일 안 follow_up 방문
    v = tables["outpatient_visits"]
    fu = v[v["visit_type"] == "follow_up"].merge(adm[["patient_id"]].drop_duplicates(), on="patient_id")
    m = alive[["admission_id", "patient_id", "discharge_time", "discharge_status"]].merge(
        fu[["patient_id", "visit_time"]], on="patient_id", how="left")
    gap = m["visit_time"] - m["discharge_time"]
    m["fu"] = (gap >= pd.Timedelta(days=4)) & (gap <= pd.Timedelta(days=29))
    fu_rate = m.groupby(["admission_id", "discharge_status"])["fu"].any().groupby("discharge_status").mean().to_dict()

    # AKI 진단 코드 기록률 (KDIGO 양성 입원 중 N17 코드가 있는 비율), 병동·진료과별
    kd = kdigo_table(tables["labs"])
    pos = a.merge(kd[kd["aki"]], on="admission_id")
    dx = tables["diagnoses"]
    n17 = set(dx.loc[dx["icd_code"].isin(["N17.9", "584.9"]), "admission_id"])
    coded = set(dx["admission_id"])
    pos = pos[pos["admission_id"].isin(coded)]
    pos["n17"] = pos["admission_id"].isin(n17)
    code_rate = {f"{u}/{s}": float(g["n17"].mean()) for (u, s), g in pos.groupby(["unit", "service"])}

    loc = location_lab_rates(tables)
    return {"cr_per_day_location": loc, "cr_location_ratio": loc["ICU"] / loc["ward"],
            "readmit30_site_b_share": {k: float(v) for k, v in b_share.items()},
            "followup_rate": {k: float(v) for k, v in fu_rate.items()},
            "aki_code_rate": code_rate}


def summarize(tables: dict[str, pd.DataFrame]) -> dict:
    pts, adm, labs, orders = tables["patients"], tables["admissions"], tables["labs"], tables["orders"]
    links = tables["person_links"]
    kd = kdigo_table(labs)
    adm_aki = adm.merge(kd, on="admission_id", how="left")
    adm_aki["aki"] = adm_aki["aki"].fillna(False).astype(bool)
    rd = readmission_table(adm)

    n_adm_per_pt = adm.groupby("patient_id").size().reindex(pts["patient_id"], fill_value=0)
    per_person = adm.merge(links, on="patient_id").groupby("person_id").size()

    lab_dis = labs.merge(adm[["admission_id", "discharge_time"]], on="admission_id")
    post_dis = (lab_dis["collect_time"] <= lab_dis["discharge_time"]) & (
        lab_dis["report_time"] > lab_dis["discharge_time"])
    fam_sizes = pts.drop_duplicates("family_id")["family_id"].dropna()
    fam_sizes = links.merge(pts, on="patient_id").drop_duplicates("person_id")["family_id"].dropna().value_counts()
    renal = orders[orders["order_type"].isin(["dialysis_order", "nephrology_consult"])]
    aki_adm = adm_aki[adm_aki["aki"]]
    aki_renal_pts = aki_adm[aki_adm["admission_id"].isin(renal["admission_id"])]["patient_id"].nunique()

    per_adm = labs[labs["test"] == "creatinine"].groupby("admission_id").size().rename("n_cr")
    los_days = (adm["discharge_time"] - adm["admit_time"]).dt.total_seconds() / 86400
    freq = adm.assign(los_days=los_days).merge(per_adm, on="admission_id", how="left").fillna({"n_cr": 0})
    freq["cr_per_day"] = freq["n_cr"] / freq["los_days"]
    deaths = tables["deaths"]
    info = tables["admission_info"]

    s = {
        "n_persons": int(links["person_id"].nunique()),
        "n_patient_ids": len(pts),
        "n_admissions": len(adm),
        "rows": {k: len(v) for k, v in tables.items()},
        "admissions_per_patient_mean": float(n_adm_per_pt.mean()),
        "admissions_per_patient_dist": {int(k): int(v) for k, v in n_adm_per_pt.value_counts().sort_index().items()},
        "aki_rate": float(adm_aki["aki"].mean()),
        "aki_rate_icu": float(adm_aki.loc[adm_aki["unit"] == "ICU", "aki"].mean()),
        "aki_rate_ward": float(adm_aki.loc[adm_aki["unit"] == "ward", "aki"].mean()),
        "readmit30_rate": float(rd["readmit30"].mean()),
        "death_rate": float((adm["discharge_status"] == "died").mean()),
        "deaths_in_hospital": int((deaths["place"] == "in_hospital").sum()),
        "deaths_out_of_hospital": int((deaths["place"] == "out_of_hospital").sum()),
        "multi_admit_frac": float((n_adm_per_pt >= 2).mean()),
        "multi_admit_frac_person": float((per_person >= 2).mean()),
        "post_discharge_lab_frac": float(post_dis.mean()),
        "post_discharge_lab_n": int(post_dis.sum()),
        "family_pairs": int(sum(comb(int(x), 2) for x in fam_sizes)),
        "n_families": int(len(fam_sizes)),
        "family_id_missing": float(pts["family_id"].isna().mean()),
        "id_switch_persons": int((links.groupby("person_id").size() >= 2).sum()),
        "icu_patients": int(adm.loc[adm["unit"] == "ICU", "patient_id"].nunique()),
        "ward_patients": int(adm.loc[adm["unit"] == "ward", "patient_id"].nunique()),
        "aki_patients_with_renal_order": int(aki_renal_pts),
        "cr_per_day_icu": float(freq.loc[freq["unit"] == "ICU", "cr_per_day"].mean()),
        "cr_per_day_ward": float(freq.loc[freq["unit"] == "ward", "cr_per_day"].mean()),
        "site_b_admission_frac": float((info["site"] == "B").mean()),
        "elective_frac": float((info["admission_type"] == "elective").mean()),
        "split_episode_frac": float(info["episode_id"].duplicated(keep=False).mean()),
    }
    s.update(ascertainment(tables))
    return s


def check_criteria(s: dict) -> list[Check]:
    """D23: v1 기준 7개 (가족 쌍은 기록된 것 기준) + 결과 확인 강도 차이."""
    lo, hi = TARGET_RATE
    pct = lambda x: f"{x:.1%}"  # noqa: E731
    b, fu, cr = s["readmit30_site_b_share"], s["followup_rate"], s["aki_code_rate"]
    return [
        Check("AKI 비율 (입원 기준)", pct(s["aki_rate"]), "10~20%", lo <= s["aki_rate"] <= hi),
        Check("30일 재입원 비율 (생존 퇴원, 등록 번호 기준)", pct(s["readmit30_rate"]), "10~20%",
              lo <= s["readmit30_rate"] <= hi),
        Check("입원 2회 이상 (등록 번호 기준)", pct(s["multi_admit_frac"]), ">= 20%",
              s["multi_admit_frac"] >= MIN_MULTI_ADMIT_FRAC),
        Check("퇴원 직전 채취·퇴원 후 보고 검사", f"{pct(s['post_discharge_lab_frac'])} ({s['post_discharge_lab_n']}건)",
              ">= 2%", s["post_discharge_lab_frac"] >= MIN_POST_DISCHARGE_LAB_FRAC),
        Check("기록된 가족 관계 쌍", f"{s['family_pairs']}쌍 ({s['n_families']}가족)", ">= 30쌍",
              s["family_pairs"] >= MIN_FAMILY_PAIRS),
        Check("ICU 환자 / 병동 환자", f"{s['icu_patients']}명 / {s['ward_patients']}명", "둘 다 > 0",
              s["icu_patients"] > 0 and s["ward_patients"] > 0),
        Check("투석 오더·신장내과 협진이 있는 AKI 환자", f"{s['aki_patients_with_renal_order']}명", ">= 1",
              s["aki_patients_with_renal_order"] >= 1),
        Check("크레아티닌 측정 빈도 ICU/병동 (머문 병동)", f"{s['cr_location_ratio']:.2f}배", ">= 2.0",
              s["cr_location_ratio"] >= MIN_LOCATION_RATIO),
        Check("30일 재입원 중 B 병원: 전원 > 자택", f"{pct(b.get('transfer', 0))} / {pct(b.get('home', 0))}",
              "전원 > 자택", b.get("transfer", 0) > b.get("home", 0)),
        Check("추적 외래: 자택 > 전원", f"{pct(fu.get('home', 0))} / {pct(fu.get('transfer', 0))}", "자택 > 전원",
              fu.get("home", 0) > fu.get("transfer", 0)),
        Check("AKI 코드 기록률: ICU·내과 > 병동·외과",
              f"{pct(cr.get('ICU/medicine', 0))} / {pct(cr.get('ward/surgery', 0))}", "ICU·내과 > 병동·외과",
              cr.get("ICU/medicine", 0) > cr.get("ward/surgery", 0)),
    ]


def format_report(s: dict, checks: list[Check]) -> str:
    lines = [f"사람 {s['n_persons']}명 (등록 번호 {s['n_patient_ids']}개), 입원 {s['n_admissions']}건",
             f"AKI {s['aki_rate']:.1%} (ICU {s['aki_rate_icu']:.1%}, 병동 {s['aki_rate_ward']:.1%}), "
             f"30일 재입원 {s['readmit30_rate']:.1%}, 입원 2회 이상 {s['multi_admit_frac']:.1%} "
             f"(사람 기준 {s['multi_admit_frac_person']:.1%})",
             f"원내 사망 {s['death_rate']:.1%}, 사망 기록 원내 {s['deaths_in_hospital']} / 원외 {s['deaths_out_of_hospital']}",
             f"크레아티닌/일: 입원 병동 기준 ICU {s['cr_per_day_icu']:.2f}, 병동 {s['cr_per_day_ward']:.2f}; "
             f"머문 병동 기준 ICU {s['cr_per_day_location']['ICU']:.2f}, 병동 {s['cr_per_day_location']['ward']:.2f}",
             f"B 병원 입원 {s['site_b_admission_frac']:.1%}, 예약 입원 {s['elective_frac']:.1%}, "
             f"이어진 입원 에피소드에 속한 입원 기록 {s['split_episode_frac']:.1%}, family_id 결측 {s['family_id_missing']:.1%}, "
             f"등록 번호 둘 {s['id_switch_persons']}명", ""]
    for c in checks:
        lines.append(f"[{'✔' if c.passed else '✘'}] {c.name}: {c.value}  (기준 {c.criterion})")
    return "\n".join(lines)
