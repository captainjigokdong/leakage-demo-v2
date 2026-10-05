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
        "퇴원 전 원내 사건: 크레아티닌 KDIGO 기준 AKI 또는 원내 사망. AKI는 tp에 아직 보고되지 않았고 tp+48시간까지 "
        "채취된 크레아티닌으로 판정한다 (사건 시각은 채취 시각). 보고가 창 뒤여도 채취가 창 안이면 센다. "
        "KDIGO: 각 값을 그보다 먼저 채취한 같은 입원의 값과만 비교한다 (48시간 안 최솟값보다 0.3 mg/dL 이상 높음, "
        "또는 7일 안 최솟값의 1.5배 이상). 측정법(method)이 다른 값끼리는 비교하지 않는다. "
        "결과는 원내에서 확인되는 사건으로 정의한다: 창 안에 퇴원하면 퇴원 뒤는 결과 창에 들어가지 않고, 창 안에 크레아티닌 "
        "측정이 없으면 음성이다. 창 안 퇴원 비율과 측정 빈도가 병동마다 다르므로 tp에 머문 병동별로 결과율·측정 빈도·창 안 "
        "퇴원 비율을 따로 보고한다.")
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


# --- 검수 1회차 반영 (승인 B, 2026-10-05). 번호는 docs/clean_review_v2.md의 분류표 -------------------

JAFFE_NOTE = ("2155-01-01 전에 채취한 크레아티닌은 jaffe로 재어 0.10 mg/dL 높다 (데이터 설명서 labs.value). 특징을 만들 때 "
              "jaffe 값에서 0.10을 빼 enzymatic 눈금으로 맞춘 뒤 집계한다 (cr_method_align 단계). 측정법 자체는 특징으로 "
              "넣지 않는다")
HISTORY_NOTE = ("이력은 등록 번호(patient_id)로 모은다. 같은 사람의 다른 등록 번호를 잇는 person_id는 자료 추출 때 연결되어 "
                "tp에는 알 수 없다")


def _is_creatinine(f: dict) -> bool:
    return f.get("source") == "labs" and (f.get("filter") or {}).get("test") == ["creatinine"]


def _append_desc(obj: dict, text: str, key: str = "description") -> None:
    obj[key] = (obj[key].rstrip(". ") + ". " + text) if obj.get(key) else text


def round1_fixes(t: str, d: dict) -> None:
    feats = d["features"]
    # D4: jaffe 값 보정 (데이터에서 추정하지 않는 고정값)
    cr = [f["name"] for f in feats if _is_creatinine(f)]
    for f in feats:
        if f["name"] in cr:
            _append_desc(f, "jaffe 값은 0.10 mg/dL을 빼서 맞춘 값으로 집계한다")
    _feature(d, "cr_last")["assessment"]["method"] = JAFFE_NOTE
    d["preprocessing"].insert(0, {
        "name": "cr_method_align", "kind": "transform", "method": "jaffe 측정 크레아티닌 값에서 0.10 mg/dL을 뺀다",
        "stateless": True, "applies_to": "train+test", "before_split": False, "uses_outcome": False, "columns": cr,
        "description": "집계 전 값 단위로 적용한다. 0.10은 데이터 설명서(labs.value)의 고정 차이이고 데이터에서 추정하지 않는다. "
                       "결과 판정(KDIGO)은 같은 측정법끼리만 비교하므로 이 보정을 쓰지 않는다"})
    # D6: 이력 특징의 근거 한 문장
    for f in feats:
        if f.get("history_key") == "patient_id":
            _append_desc(f, HISTORY_NOTE)
    # 작은 명시: 조율 폴드 수
    d["model"]["tuning"]["method"] = "group_kfold 5폴드 (family_id, 없으면 person_id)"
    o = d["outcome"]
    if t == "dynamic":
        # D1a: 창이 있는 이번 입원 특징은 같은 에피소드 전체를 본다
        for f in feats:
            if f.get("scope") == "index_admission" and "time_column" in f and "episode" not in f:
                f["episode"] = "index_episode"
        # D2: 결과 서술에 칸 대응
        _append_desc(o, "설계서 칸으로는 outcome.window (tp, tp+48h]가 채취 시각 창이고, tp 이전에 채취되어 tp에 아직 "
                        "보고되지 않은 값은 outcome.pending_at_tp=count_as_outcome으로 같은 규칙에 들어간다")
        # D3: 자료 추출 종료 무렵 입원 제외
        d["cohort"]["exclusion"].append({
            "name": "admit_near_extraction_end",
            "description": "자료 추출 종료(2160-01-01) 30일(재원 기간 상한) 전 뒤에 시작한 입원. 종료 때 아직 입원 중인 입원은 "
                           "데이터에 없어 이 기간의 입원은 짧게 끝난 것만 남는다. 입원 시각은 tp에 알려져 있다",
            "source": "admissions", "column": "admit_time", "scope": "index_admission", "agg": "value",
            "op": ">", "value": "2159-12-02 00:00:00"})
        # D7·D8: 확인 방식 서술
        _append_desc(o["ascertainment"], "병동 채혈 빈도는 연구 기간 동안 늘어나므로(데이터 설명서), 측정 빈도와 결과율을 "
                                         "병동 × 연도별로도 보고한다", "method")
        _append_desc(o["ascertainment"], "결과 판정은 규칙 코드(KDIGO)로 하고 예측값을 보지 않는다. KDIGO의 기준값은 정의상 "
                                         "이전 크레아티닌이다", "method")
        # 작은 명시: 제외 기준 kdigo_aki의 비교 규칙
        ex = next(x for x in d["cohort"]["exclusion"] if x["name"] == "aki_known_by_tp")
        _append_desc(ex, "판정 규칙은 결과와 같다 (각 값을 먼저 채취한 같은 측정법의 값과 비교, 48시간 +0.3 mg/dL 또는 "
                         "7일 1.5배). tp까지 보고된 값만 쓴다")
    else:
        # F1: 퇴원약은 이번 퇴원(인덱스 입원)의 것만
        for name in ("n_discharge_meds", "dc_diuretic"):
            f = next((x for x in feats if x["name"] == name), None)
            if f:
                f.pop("episode", None)
                _append_desc(f, "이번 퇴원(인덱스 입원)의 퇴원약만 센다. 같은 에피소드 앞 입원(전원 퇴원)의 퇴원약은 넣지 않는다")
        # F2: 검사·활력 특징은 에피소드 전체, 열 값 특징은 마지막 입원 기록 기준임을 적음
        for f in feats:
            if f.get("scope") == "index_admission" and "time_column" in f and "episode" not in f \
                    and f["name"] not in ("n_discharge_meds", "dc_diuretic"):
                f["episode"] = "index_episode"
        for name in ("los_h", "unit"):
            _append_desc(_feature(d, name), "두 입원 기록으로 나뉜 에피소드에서는 마지막 입원 기록(인덱스 입원) 기준이다")
        # F3: ★ 진단 범주의 ICD-9 → ICD-10
        f = next((x for x in feats if x["name"] == "prior_dx_group"), None)
        if f:
            _append_desc(f, "ICD-9 코드는 dx_code_map 단계에서 ICD-10 코드로 바꾼 뒤 범주로 쓴다")
            idx = next(i for i, x in enumerate(d["preprocessing"]) if x["name"] == "one_hot")
            d["preprocessing"].insert(idx, {
                "name": "dx_code_map", "kind": "transform",
                "method": "ICD-9 주진단 코드를 같은 병의 ICD-10 코드로 바꾼다 (데이터 설명서 diagnoses.code_system의 코드별 대응)",
                "stateless": True, "applies_to": "train+test", "before_split": False, "uses_outcome": False,
                "columns": ["prior_dx_group"],
                "description": "고정 대응표를 쓰고 데이터에서 추정하지 않는다. 코드 체계는 2155-10-01에 ICD-9에서 ICD-10으로 바뀌었다"})
    # 가정·점검 불가 분류에서 고칠 수 있는 사실 (서술로 명시, 승인 B 확인 3)
    for f in feats:
        if f.get("source") == "diagnoses" and f.get("scope") == "prior_admissions":
            _append_desc(f, "같은 에피소드의 앞 입원 진단도 tp 전에 코딩이 끝났으면 넣는다 (n_prior_adm은 입원 수라 같은 에피소드를 뺀다)")
    _append_desc(_feature(d, "age"), "데이터의 나이는 95에서 잘려 있다 (데이터 설명서 patients.age)")
    adult = next(c for c in d["cohort"]["inclusion"] if c["name"] == "adult")
    _append_desc(adult, "patients.age는 그 등록 번호의 첫 입원 때 나이라 인덱스 입원 때 나이는 그 이상이다")
    _append_desc(d["model"]["threshold"], "보정(calibration)한 확률에서 정한다", "method")
    if t == "dynamic":
        _append_desc(o, "결과 창 끝(tp+48h)이 자료 추출 종료 뒤인 행은 뺀다 (end_of_data=exclude_incomplete)")
    # D9: 결측 표시 단계는 대치하는 열 전부
    mf = next((x for x in d["preprocessing"] if x["name"] == "missing_flags"), None)
    if mf:
        mf["columns"] = list(_step(d, "median_impute")["columns"])
        _append_desc(mf, "결측이 없는 열의 표시 열은 모두 0이라 모형에 영향이 없다")


EPISODE_NOTE = {
    "dynamic": "두 입원 기록으로 이어진 에피소드에서 창이 있는 이번 입원 특징은 에피소드 전체를 본다. 결과·tp는 입원 기록 단위다",
    "fixed": "두 입원 기록으로 이어진 에피소드에서 검사·활력·ICU·투석 특징은 에피소드 전체를, 퇴원약은 이번 퇴원을, "
             "열 값 특징(los_h, unit 등)은 마지막 입원 기록을 본다",
}


def finish(name: str, t: str, d: dict) -> dict:
    round1_fixes(t, d)
    split_note = d.pop("notes_split") + " " + EPISODE_NOTE[t] + "."
    if d["split"]["method"] != "temporal":
        extra = ", split.time_column, split.cutoff, split.gap (무작위 분할)"
    else:
        extra = ", split.time_column (기준 시각은 tp), split.test_fraction (경계 시각으로 나눔)"
    d["design_id"] = name
    more = ["agg가 last·first인 특징의 순서는 각 특징의 time_column 기준이다",
            "평가 지표의 신뢰구간은 가족(없으면 사람) 단위 부트스트랩으로 구하고, 하위 집단(특히 표본이 적은 B 병원)은 "
            "신뢰구간과 함께 보고한다"]
    if d["split"]["method"] != "temporal":
        more.append("split.test_fraction은 묶음 수의 비율이다")
    if t == "dynamic":
        more.append("outcome.planned·planned_by·match_key는 이 결과(입원 중 AKI·원내 사망)에는 쓰이지 않는다")
    else:
        more.append("코호트는 에피소드의 마지막 입원을 먼저 고른 뒤 제외 기준을 적용한다")
    d["notes"] = EMPTY_NOTE[t] + extra + ". " + split_note + " " + ". ".join(more) + "."
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
