"""4단계 4a: 깨끗한 설계서 8개 (유형별 4개)를 만든다.

- 바탕: 2b 시험용 기본 설계서 `designs/prereview/` (오류 사례 48개의 패치가 이 설계서를 대상으로 쓰였다).
- 같은 유형 4개는 결과 정의·결과 창·tp·코호트 뼈대를 같게 두고, 바탕의 이름 있는 항목(특징·전처리·포함/제외 기준)을
  지우거나 이름을 바꾸지 않는다. 바꾸는 것은 ① 공통 수정(검수 지적 반영) ② 설계서마다 다른 부분뿐이다.
- 어떤 수정이 어떤 지적을 반영하는지는 `docs/clean_designs_v2.md`에 적는다.
- 출력: designs/clean_v2/<이름>.json. 실행: python -m tools.make_clean_v2
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = {"dynamic": ROOT / "designs" / "prereview" / "dynamic_aki.json",
       "fixed": ROOT / "designs" / "prereview" / "fixed_readmission.json"}
OUT = ROOT / "designs" / "clean_v2"
NAMES = {"dynamic": ["aki_a", "aki_b", "aki_c", "aki_d"], "fixed": ["readmit_a", "readmit_b", "readmit_c", "readmit_d"]}

CR = {"test": ["creatinine"]}
CR_METHOD_NOTE = ("2155-01-01 전은 jaffe(약 0.10 mg/dL 높음), 뒤는 enzymatic. 측정법이 다른 값이 섞인 채로 쓴다. "
                  "측정법 자체는 특징으로 넣지 않는다 (측정 날짜로 정해지는 값이고, 사용 시점에는 enzymatic 하나뿐이다)")
REFIT_NOTE = "조율 중에는 교차검증 학습 폴드마다 다시 맞추고, 최종 모형은 학습 부분 전체에 맞춘다"


def _feature(d: dict, name: str) -> dict:
    return next(f for f in d["features"] if f["name"] == name)


def _step(d: dict, name: str) -> dict:
    return next(s for s in d["preprocessing"] if s["name"] == name)


# --- 공통 수정 -------------------------------------------------------------

def common_dynamic(d: dict) -> dict:
    d = copy.deepcopy(d)
    # R2·B25: 질문과 결과(AKI 또는 원내 사망)를 맞춘다. R4: 결과는 퇴원 전 원내 사건으로 정의한다.
    d["question"] = ("성인 입원 중 매일(입원 24시간~7일), 앞으로 48시간 안에 퇴원 전 크레아티닌 KDIGO 기준 "
                     "급성 신손상(AKI)이 생기거나 원내에서 사망할지 예측한다.")
    o = d["outcome"]
    o["description"] = (
        "퇴원 전 원내 사건: 결과 창(tp, tp+48h]에 채취된 크레아티닌이 KDIGO 기준을 만족하거나 원내 사망. "
        "KDIGO: 결과 창의 각 값을 그보다 먼저 채취한 같은 입원의 값과만 비교한다 (48시간 안 최솟값보다 0.3 mg/dL 이상 높음, "
        "또는 7일 안 최솟값의 1.5배 이상). 측정법(method)이 다른 값끼리는 비교하지 않는다. "
        "결과는 원내에서 확인되는 사건으로 정의한다: 창 안에 퇴원하면 퇴원 뒤는 결과 창에 들어가지 않고, 창 안에 크레아티닌 "
        "측정이 없으면 음성이다. 창 안 퇴원 비율과 측정 빈도가 병동마다 다르므로 tp에 머문 병동별로 결과율·측정 빈도·창 안 "
        "퇴원 비율을 따로 보고한다. tp 전에 채취했지만 tp 뒤에 보고된 크레아티닌(보고 지연 최대 6시간)이 KDIGO 기준을 "
        "만족하면, tp에는 알 수 없고 예측 범위 안에서 알려지는 사건이므로 결과로 센다 (pending_at_tp).")
    o["ascertainment"]["min_followup"] = "tp (원내 사건으로 정의, outcome.description 참고)"
    o["censoring"]["end_of_data"] = "exclude_incomplete"          # R5 (O.end_of_data)
    o["pending_at_tp"] = "count_as_outcome"                      # 점검기 C.pending (B27)
    _feature(d, "cr_last")["assessment"]["method"] = CR_METHOD_NOTE  # R1·B22
    return d


def common_fixed(d: dict) -> dict:
    d = copy.deepcopy(d)
    o = d["outcome"]
    # R6: definition=next_admission은 "다음 입원 하나"가 아니라 창 안에 시작되는 같은 사람의 모든 입원을 본다.
    o["description"] = (
        "퇴원 뒤 30일 안에 같은 사람(person_id로 묶은 모든 등록 번호)의 예정되지 않은 입원이 시작되거나 사망. "
        "결과 계산(definition=next_admission)은 창 안에 시작되는 그 사람의 입원을 모두 본다 (창 안 첫 입원 하나만 보는 것이 "
        "아니다). 예정 입원(admission_info.admission_type == elective)은 사건으로 세지 않으므로, 창 안에 예정 입원이 먼저 "
        "있어도 그 뒤 응급 입원이 있으면 양성이다. 사망은 deaths.death_time이 창 안이면 양성. 같은 에피소드 안에서 바로 "
        "이어진 입원은 재입원으로 보지 않는다 (코호트가 에피소드의 마지막 입원만 쓴다).")
    for s in d["preprocessing"]:                                  # 점검기 F.fold_refit (예비 검수 B17과 같은 원리)
        s["fit_scope"] = "train_fold"
        s["description"] = REFIT_NOTE
    _feature(d, "cr_last")["assessment"]["method"] = CR_METHOD_NOTE  # R1·B22
    return d


# --- 설계서마다 다른 부분 ----------------------------------------------------

def temporal(d: dict, cutoff: str, gap: str, time_note: str) -> dict:
    """전향 사용 + 시간 순 분할 (예비 검수 B10, 점검기 S.temporal_deploy)."""
    s = d["split"]
    s.pop("test_fraction", None)
    s.update({"method": "temporal", "cutoff": cutoff, "gap": gap})
    d["split"] = s
    d["notes_split"] = (f"시간 순 분할: 기준 시각은 tp ({time_note}). 묶음(family_id, 없으면 person_id)째로 움직인다. "
                        f"묶음의 모든 행이 {cutoff[:10]} 이전이면 학습, 뒤의 행이 있는 묶음은 학습에서 빼고 "
                        f"{cutoff[:10]} + {gap} 뒤 행만 평가에 쓴다.")
    return d


def research_only(d: dict, setting: str) -> dict:
    """연구용 내부 검증 + 가족 단위 무작위 분할."""
    d["intended_use"] = {"purpose": "research_only",
                         "deployment_start": "해당 없음 (전향 사용 전의 내부 검증 연구)",
                         "setting": setting}
    d["notes_split"] = "가족 단위 무작위 분할 (family_id, 없으면 person_id), 평가 30%."
    return d


def boosting(d: dict) -> dict:
    d["model"]["family"] = "gradient_boosting (결정 나무)"
    d["model"]["selection"]["method"] = "나무 깊이·학습률·나무 수 격자 탐색"
    d["model"]["early_stopping"] = {"method": "사용하지 않음 (나무 수는 격자 탐색으로 정함)"}
    _step(d, "standardize")["description"] = REFIT_NOTE + ". 나무 모형에는 결과가 같지만 같은 입력 흐름을 유지한다"
    return d


def add_feature(d: dict, feat: dict, impute: bool = True, scale: bool = True, encode: bool = False) -> None:
    d["features"].append(feat)
    for step, flag in (("median_impute", impute), ("standardize", scale), ("one_hot", encode)):
        if flag:
            _step(d, step)["columns"].append(feat["name"])


def missing_indicator(d: dict) -> dict:
    d["analysis"]["missing_data"]["method"] = "indicator"
    d["preprocessing"].insert(0, {
        "name": "missing_flags", "kind": "transform", "method": "결측 여부 표시 열 추가 (값이 없으면 1)",
        "stateless": True, "applies_to": "train+test", "before_split": False, "uses_outcome": False,
        "columns": list(_step(d, "median_impute")["columns"]),
        "description": "데이터에서 추정하는 것이 없는 단계. 표시 열을 만든 뒤 median_impute로 값을 채운다"})
    return d


def make_dynamic(base: dict) -> dict[str, dict]:
    c = common_dynamic(base)
    out = {}
    a = temporal(copy.deepcopy(c), "2157-07-01 00:00:00", "48h", "입원 시각 + 24~168시간")
    out["aki_a"] = a

    b = research_only(copy.deepcopy(c), "A·B 병원의 성인 입원 환자 (ICU·병동), 후향 자료")
    b = boosting(b)
    add_feature(b, {"name": "sbp_slope_24h", "source": "vitals", "column": "value", "filter": {"item": ["sbp"]},
                    "scope": "index_admission", "time_column": "entered_time",
                    "window": {"start": "tp-24h", "end": "tp"}, "agg": "slope",
                    "description": "지난 24시간 수축기 혈압의 시간당 기울기"})
    # 수상해 보이지만 정당한 항목: tp 직전 6시간에 보고된 칼륨 (보고 시각 기준, tp 이후 값 없음)
    add_feature(b, {"name": "k_last_6h", "source": "labs", "column": "value", "filter": {"test": ["potassium"]},
                    "scope": "index_admission", "time_column": "report_time",
                    "window": {"start": "tp-6h", "end": "tp"}, "agg": "last"})
    out["aki_b"] = b

    cc = temporal(copy.deepcopy(c), "2157-01-01 00:00:00", "48h", "입원 시각 + 24~168시간")
    cc = boosting(cc)
    add_feature(cc, {"name": "abx_by_tp", "description": "tp까지 piperacillin-tazobactam 처방",
                     "source": "medications",
                     "filter": {"drug": ["piperacillin_tazobactam"], "med_type": ["inpatient"]},
                     "scope": "index_admission", "time_column": "order_time",
                     "window": {"start": "admit", "end": "tp"}, "agg": "any"}, impute=False, scale=False)
    add_feature(cc, {"name": "acei_by_tp", "description": "tp까지 ACE 억제제 처방", "source": "medications",
                     "filter": {"drug": ["ace_inhibitor"], "med_type": ["inpatient"]},
                     "scope": "index_admission", "time_column": "order_time",
                     "window": {"start": "admit", "end": "tp"}, "agg": "any"}, impute=False, scale=False)
    # 수상해 보이지만 정당한 항목: tp까지 시작된 입원 수 (이번 입원 포함, 입원 시각 ≤ tp)
    add_feature(cc, {"name": "n_admissions_to_tp", "source": "admissions", "scope": "patient_history",
                     "time_column": "admit_time", "window": {"end": "tp"}, "agg": "count",
                     "history_key": "patient_id",
                     "description": "같은 등록 번호에서 입원 시각이 tp 이전인 입원 수 (이번 입원 포함)"}, impute=False)
    out["aki_c"] = cc

    dd = research_only(copy.deepcopy(c), "A·B 병원의 성인 입원 환자 (ICU·병동), 후향 자료")
    dd["model"]["family"] = "logistic_regression (L1 규제)"
    dd = missing_indicator(dd)
    add_feature(dd, {"name": "hgb_last", "source": "labs", "column": "value", "filter": {"test": ["hemoglobin"]},
                     "scope": "index_admission", "time_column": "report_time",
                     "window": {"start": "admit", "end": "tp"}, "agg": "last"})
    out["aki_d"] = dd
    return out


def make_fixed(base: dict) -> dict[str, dict]:
    c = common_fixed(base)
    out = {}
    a = temporal(copy.deepcopy(c), "2157-01-01 00:00:00", "30d", "퇴원 시각")
    out["readmit_a"] = a

    b = research_only(copy.deepcopy(c), "A·B 병원의 성인 퇴원 환자 (ICU·병동), 후향 자료")
    b = boosting(b)
    add_feature(b, {"name": "n_clinic_365d", "description": "tp 전 365일 안 외래 방문 수 (방문 시각 기준)",
                    "source": "outpatient_visits", "scope": "patient_history", "time_column": "visit_time",
                    "window": {"start": "tp-365d", "end": "tp"}, "agg": "count", "history_key": "patient_id"},
                impute=False)
    # 수상해 보이지만 정당한 항목: 이전 입원의 주진단 코드 범주 (코딩 완료 시각 ≤ tp), 학습 폴드에서 맞춘 one-hot
    add_feature(b, {"name": "prior_dx_group", "source": "diagnoses", "column": "icd_code", "filter": {"seq": [1]},
                    "scope": "prior_admissions", "time_column": "coded_time",
                    "window": {"start": "-inf", "end": "tp"}, "agg": "last", "history_key": "patient_id",
                    "description": "가장 최근 이전 입원의 주진단 코드 (tp까지 코딩이 끝난 것). 범주형"},
                impute=False, scale=False, encode=True)
    out["readmit_b"] = b

    cc = temporal(copy.deepcopy(c), "2156-07-01 00:00:00", "30d", "퇴원 시각")
    cc = boosting(cc)
    add_feature(cc, {"name": "dc_diuretic", "description": "퇴원약에 루프 이뇨제가 있음",
                     "source": "medications", "filter": {"drug": ["loop_diuretic"], "med_type": ["discharge"]},
                     "scope": "index_admission", "time_column": "order_time",
                     "window": {"start": "admit", "end": "tp"}, "agg": "any", "episode": "index_episode"},
                impute=False, scale=False)
    # 수상해 보이지만 정당한 항목: 이전 입원의 마지막 크레아티닌 (보고 시각 ≤ tp)
    add_feature(cc, {"name": "prior_cr_last", "source": "labs", "column": "value", "filter": CR,
                     "scope": "prior_admissions", "time_column": "report_time", "window": {"end": "tp"},
                     "agg": "last", "history_key": "patient_id"})
    out["readmit_c"] = cc

    dd = research_only(copy.deepcopy(c), "A·B 병원의 성인 퇴원 환자 (ICU·병동), 후향 자료")
    dd["model"]["family"] = "logistic_regression (L1 규제)"
    dd = missing_indicator(dd)
    add_feature(dd, {"name": "k_last", "source": "labs", "column": "value", "filter": {"test": ["potassium"]},
                     "scope": "index_admission", "time_column": "report_time",
                     "window": {"start": "admit", "end": "tp"}, "agg": "last"})
    out["readmit_d"] = dd
    return out


EMPTY_NOTE = {
    "dynamic": "선택한 방법에 해당하지 않는 칸은 비워 두었다: cohort.sampling.by, cohort.sampling.fraction, "
               "cohort.sampling.ratio (전체 사용), split.n_folds, features의 date_compare (날짜만 있는 열을 쓰지 않음)",
    "fixed": "선택한 방법에 해당하지 않는 칸은 비워 두었다: outcome.filter, outcome.reference_window, outcome.reference "
             "(입원으로 정하는 결과라 기준값이 없음), cohort.sampling.by, cohort.sampling.fraction, cohort.sampling.ratio "
             "(전체 사용), split.n_folds, features의 date_compare (날짜만 있는 열을 쓰지 않음)",
}


def finish(name: str, t: str, d: dict) -> dict:
    split_note = d.pop("notes_split")
    if d["split"]["method"] != "temporal":
        extra = ", split.time_column, split.cutoff, split.gap (무작위 분할)"
    else:
        extra = ", split.time_column (기준 시각은 tp), split.test_fraction (경계 시각으로 나눔)"
    d["design_id"] = name
    d["notes"] = EMPTY_NOTE[t] + extra + ". " + split_note
    return d


def build() -> dict[str, dict]:
    bases = {t: json.loads(p.read_text(encoding="utf-8")) for t, p in SRC.items()}
    out = {}
    for t, maker in (("dynamic", make_dynamic), ("fixed", make_fixed)):
        made = maker(bases[t])
        assert sorted(made) == sorted(NAMES[t])
        for name in NAMES[t]:
            out[name] = finish(name, t, made[name])
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, d in build().items():
        (OUT / f"{name}.json").write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(OUT.relative_to(ROOT) / f"{name}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
