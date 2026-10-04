"""v2 합성 데이터의 테이블·열 목록 (2단계에서 확정).

v2에서 데이터 구조를 확정하며 전체 재생성한다 (생성은 2단계 2b). 이 목록이 기준이다.
- 본 데이터: data/synth/, 보조 데이터(환자 적고 변수 많은): data/synth_aux/. 두 데이터는 같은 테이블·열을 쓴다.
- 열마다 값이 언제 생기고 언제 알려지는지는 docs/data_dictionary_v2.md에 적는다.
- 이후 단계에서 테이블·열을 더하지 않는다.
"""
from __future__ import annotations

TABLES_V2: dict[str, list[str]] = {
    "extract_info": ["extraction_end_time", "sites_covered", "death_linkage_through"],
    "patients": ["patient_id", "family_id", "age", "sex"],
    "person_links": ["patient_id", "person_id"],
    "admissions": ["admission_id", "patient_id", "admit_time", "discharge_time", "discharge_status", "unit"],
    "admission_info": ["admission_id", "site", "admission_type", "service", "episode_id"],
    "transfers": ["transfer_id", "admission_id", "unit", "in_time", "out_time"],
    "labs": ["lab_id", "admission_id", "test", "value", "unit", "method", "collect_time", "report_time"],
    "vitals": ["vital_id", "admission_id", "item", "value", "charted_time", "entered_time"],
    "medications": ["med_id", "admission_id", "drug", "med_type", "order_time"],
    "orders": ["order_id", "admission_id", "order_type", "order_time"],
    "diagnoses": ["admission_id", "seq", "icd_code", "code_system", "present_on_admission", "coded_time"],
    "procedures": ["admission_id", "code", "chart_date", "coded_time"],
    "problem_list": ["entry_id", "patient_id", "admission_id", "version", "icd_code", "status", "recorded_time"],
    "outpatient_visits": ["visit_id", "patient_id", "visit_time", "site", "visit_type"],
    "outpatient_labs": ["lab_id", "patient_id", "visit_id", "test", "value", "unit", "method",
                        "collect_time", "report_time"],
    "admission_bookings": ["booking_id", "patient_id", "source_admission_id", "booked_time", "planned_date",
                           "admission_id"],
    "deaths": ["patient_id", "death_time", "place", "death_recorded_time", "source"],
}

# 데이터 파일에는 없지만 설계서가 열 이름으로 쓸 수 있는 값 (계산식은 데이터 설명서)
DERIVED_V2: dict[str, str] = {
    "admissions.length_of_stay_h": "(discharge_time - admit_time) 시간",
    "index_row.landmark_row_id": "예측 행 식별자. 동적 설계: (admission_id, 랜드마크 간격) 한 쌍 / 고정 설계: admission_id",
}

# 사건 시각 열: 사망 시각·자료 추출 종료 시각 뒤에 있으면 안 된다
EVENT_TIME_COLUMNS: dict[str, list[str]] = {
    "admissions": ["admit_time", "discharge_time"],
    "transfers": ["in_time", "out_time"],
    "labs": ["collect_time"],
    "vitals": ["charted_time"],
    "medications": ["order_time"],
    "orders": ["order_time"],
    "procedures": ["chart_date"],
    "outpatient_visits": ["visit_time"],
    "outpatient_labs": ["collect_time"],
    "admission_bookings": ["booked_time"],
    "deaths": ["death_time"],
}

# 기록 시각 열: 사망 뒤여도 되지만 자기 사건 시각보다 뒤, 자료 추출 종료 시각 이전
RECORD_TIME_COLUMNS: dict[str, dict[str, str]] = {
    "labs": {"report_time": "collect_time"},
    "vitals": {"entered_time": "charted_time"},
    "diagnoses": {"coded_time": "admissions.discharge_time"},
    "procedures": {"coded_time": "chart_date"},
    "problem_list": {"recorded_time": "admissions.admit_time"},
    "outpatient_labs": {"report_time": "collect_time"},
    "deaths": {"death_recorded_time": "death_time"},
}
