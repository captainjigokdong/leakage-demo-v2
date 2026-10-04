"""v1 사례 18개(E01~E18)의 v2 형식용 패치 (v2 2단계 2c).

- 대상 설계서: v2 형식을 모두 채운 시험용 기본 설계서 `designs/prereview/` (유형별 1개, 읽기 전용).
- 사례 문장은 `designs/error_catalog_public.csv` 18행 그대로다 (v1에서 조정한 E11·E16·E18도 조정 전 원래 문장).
- E02, E03, E06~E08, E12~E15 (9개): v1 패치(`designs/inject.PUBLIC_PATCHES`)를 그대로 쓴다.
- E01, E10, E17 (3개): v1 패치로는 문장의 일부가 넓어진 형식에 드러나지 않아 다시 썼다 (2c 사용자 승인,
  바꾼 내용과 이유는 `docs/injection_log_v2.md`).
- E04, E05, E09, E11, E16, E18 (6개, v1 보류): 이 파일에서 처음 평문으로 쓴다.
- 심은 항목 이름은 기본 설계의 다른 항목과 같은 방식으로 붙인다 (결함을 암시하지 않게).

`designs/inject.py`의 v1 변형 생성 경로(v1 기본 설계, 변형 20개)는 4단계에서 v2로 다시 짤 때까지 그대로 둔다.
"""
from __future__ import annotations

import json
from pathlib import Path

from designs.inject import CR, PUBLIC_PATCHES

ROOT = Path(__file__).resolve().parent.parent
TEST_BASE_DIR = ROOT / "designs" / "prereview"
TEST_BASE_FILES = {"dynamic": "dynamic_aki.json", "fixed": "fixed_readmission.json"}

V1_REWRITTEN_PATCHES: dict[str, list[dict]] = {
    # "이번 입원": v2 형식에는 scope 기본값이 없어 명시한다.
    "E01": [{"op": "append", "path": "features",
             "value": {"name": "n_dx", "source": "diagnoses", "scope": "index_admission", "agg": "count"}}],
    # "결과와의 단변량 연관": v2 형식의 방법·결과 사용 칸으로 나타낸다.
    "E10": [{"op": "append", "path": "preprocessing",
             "value": {"name": "select_k", "kind": "select", "method": "univariate_top_k", "k": 5,
                       "fit_scope": "all", "uses_outcome": True}}],
    # "결과 확인 방식을 단위별로 구분하지 않음": 확인 방식과, 확인 강도를 따로 볼 하위 집단을 함께 비운다.
    "E17": [{"op": "remove", "path": "outcome.ascertainment"},
            {"op": "set", "path": "cohort.subgroups", "value": []}],
}

V1_HOLDOUT_PATCHES: dict[str, list[dict]] = {
    # 날짜만 있는 시술(chart_date)을 날짜끼리 비교(date <= date(tp))해 같은 날 tp에 쓴다.
    "E04": [{"op": "append", "path": "features",
             "value": {"name": "n_proc", "source": "procedures", "scope": "index_admission",
                       "time_column": "chart_date", "window": {"start": "admit", "end": "tp"},
                       "date_compare": "same_date_ok", "agg": "count"}}],
    "E05": [{"op": "set", "path": "split.key", "value": "landmark_row_id"}],
    # 진단 코드별 결과율 인코딩을 전체 데이터로 계산한다. 인코딩할 진단 코드 범주형 특징(이전 입원의 주진단,
    # 코딩 완료 시각이 tp 이전)을 함께 더한다. 그 특징 자체는 결함이 아니다 (2c 사용자 결정).
    "E09": [{"op": "append", "path": "features",
             "value": {"name": "prior_dx_main", "source": "diagnoses", "column": "icd_code",
                       "filter": {"seq": [1]}, "scope": "prior_admissions", "time_column": "coded_time",
                       "window": {"start": "-inf", "end": "tp"}, "agg": "last", "history_key": "patient_id"}},
            {"op": "append", "path": "preprocessing",
             "value": {"name": "dx_encode", "kind": "encode", "method": "target", "stateless": False,
                       "fit_scope": "all", "applies_to": "train+test", "before_split": True,
                       "uses_outcome": True, "columns": ["prior_dx_main"]}}],
    # 결과 창과 같은 창(같은 시각 열 collect_time, (tp, tp+48h])의 크레아티닌 변화량.
    "E11": [{"op": "append", "path": "features",
             "value": {"name": "cr_change_48h", "source": "labs", "column": "value", "filter": CR,
                       "scope": "index_admission", "time_column": "collect_time",
                       "window": {"start": "tp", "end": "tp+48h"}, "agg": "delta"}}],
    "E16": [{"op": "append", "path": "cohort.inclusion",
             "value": {"name": "clinic_visit", "source": "outpatient_visits", "scope": "patient_history",
                       "time_column": "visit_time", "window": {"start": "tp", "end": "inf"}, "agg": "any",
                       "history_key": "patient_id", "op": "==", "value": True}}],
    # 본원(A) 기록으로만 재입원을 찾고, 퇴원처별 확인 차이를 확인 방식·하위 집단에 적지 않는다.
    "E18": [{"op": "set", "path": "outcome.ascertainment.scope.sites", "value": ["A"]},
            {"op": "set", "path": "outcome.ascertainment.by_stratum", "value": []},
            {"op": "set", "path": "outcome.ascertainment.method",
             "value": "A 병원의 입원 기록과 사망 연계 자료에서 결과를 찾는다."},
            {"op": "set", "path": "cohort.subgroups", "value": ["unit", "site"]}],
}

V1_CASE_PATCHES: dict[str, list[dict]] = dict(sorted({**PUBLIC_PATCHES, **V1_REWRITTEN_PATCHES, **V1_HOLDOUT_PATCHES}.items()))


def load_test_bases() -> dict[str, dict]:
    return {t: json.loads((TEST_BASE_DIR / f).read_text(encoding="utf-8")) for t, f in TEST_BASE_FILES.items()}
