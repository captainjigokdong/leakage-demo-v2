"""규칙표 (어댑터). docs/research_plan.md 4절, v2 3단계.

사람이 정하고 잠근 규칙을 모든 행에 기계적으로 적용한다. 의미를 해석하지 않는다.
테이블 규칙은 docs/data_dictionary_v2.md의 "값이 알려지는 때" 칸만 보고 썼다.

- 1층 구조: 데이터의 열이 곧 확인 가능 시각이다 (labs.report_time, diagnoses.coded_time)
- 2층 맥락: 데이터 밖의 지식(설명서에 적힌 지연 상한, 확인 강도를 좌우하는 층). 근거와 함께 적는다
- 3층 불확실: 아무도 확실히 모른다. 보수적 기본값을 쓰고 "가정"으로 따로 출력한다

규칙은 "언제 알려지는가"만 말한다. 쓸 수 있는지는 설계의 tₚ가 정한다.
규칙이 없는 테이블·열은 추측하지 않고 RuleMissing으로 멈춘다 ("점검 불가").
이 파일은 순수 파이썬이다 (pandas 없이 설계서 점검이 돌아야 한다).
"""
from __future__ import annotations

from dataclasses import dataclass, field

RULES_VERSION = "2"

H = 1.0
D = 24.0

# ---------------------------------------------------------------- 조정할 수 있는 값 (2층: 설명서의 지연 상한)
# 바꾸면 설계서만 점검할 때의 상한이 바뀐다. 데이터를 주면 실제 시각 열로 다시 확인한다.
LAB_REPORT_LAG_MAX_H = 6 * H            # labs.report_time: collect_time 뒤 30분~6시간
VITAL_ENTRY_LAG_MAX_H = 6 * H           # vitals.entered_time: charted_time 뒤 0~6시간
OUTPATIENT_LAB_LAG_MAX_H = 24 * H       # outpatient_labs.report_time: collect_time 뒤 수 시간~1일
DX_CODING_MAX_AFTER_DISCHARGE_H = 90 * D    # diagnoses.coded_time: 퇴원 뒤 90%는 1~14일, 10%는 15~90일
PROC_CODING_MAX_AFTER_DISCHARGE_H = 90 * D  # procedures.coded_time: 80%는 그 입원의 진단 coded_time과 같음
PROBLEM_MAX_AFTER_DISCHARGE_H = 30 * D  # problem_list.recorded_time: 수정 버전은 퇴원 30일 뒤까지
DEATH_RECORD_LAG_MAX_H = 180 * D        # deaths.death_recorded_time: 원외 사망은 14~180일 뒤
EPISODE_GAP_MAX_H = 1 * H               # admission_info.episode_id: 이어진 입원은 앞 입원 퇴원 0~60분 뒤

# Q7 판정 기준: 층 사이 비(최대/최소)가 이 값 이상이면 경고.
# 2026-10-02 사용자 확정 (v1). 실험 전 고정값이며 이후 바꾸지 않는다.
Q7_RATIO_THRESHOLD = 2.0

# ---------------------------------------------------------------- 3층 기본값 (가정으로 출력)
# 날짜만 있는 값(procedures.chart_date 등)의 그날 시각. 설계서의 date_compare가 없을 때 쓴다.
# day_end: 그날 23:59로 본다 (창 끝과 비교할 때 가장 이른 쪽이 아니라 보수적으로 늦은 쪽)
DATE_ONLY_DEFAULT = "day_end"


class RuleMissing(KeyError):
    """규칙표에 해당 테이블·열의 규칙이 없다. 추측하지 않고 멈춘다 (점검 불가)."""


@dataclass(frozen=True)
class Avail:
    """값이 알려지는 가장 이른 시각을 정하는 규칙.

    kind
    - "column":       같은 행의 시각 열 `column`이 곧 확인 가능 시각 (+ offset_h)
    - "row_anchor":   그 행이 속한 입원의 기준점(`column` = "admit" | "discharge") + offset_h
    - "first_admit":  그 등록 번호의 첫 입원 시각 (인덱스 입원 시각 이전)
    - "linked_admit": 같은 행의 `column`(입원 번호)이 가리키는 입원의 입원 시각. 비어 있으면 자료 추출 시
    - "extraction":   자료 추출 시 (모든 tₚ 뒤)

    lag_from: 같은 행의 다른 시각 열 → 확인 가능 시각까지의 지연 상한(시간). None = 상한 없음.
    """
    kind: str
    column: str | None
    layer: int
    basis: str
    offset_h: float = 0.0
    lag_from: dict[str, float | None] = field(default_factory=dict)


@dataclass(frozen=True)
class TableRule:
    name: str
    entity_via: str | None           # "admission_id"를 거쳐 / "patient_id" 직접 / None(전역 1행)
    id_columns: tuple[str, ...]      # provenance에 쓰는 행 식별 열
    time_columns: dict[str, str]     # 열 → "datetime" | "date"
    value_column: str | None         # 집계할 때 기본 값 열
    row_available: Avail             # 행이 존재한다는 사실(개수 집계 등)이 알려지는 시각
    column_available: dict[str, Avail] = field(default_factory=dict)   # 모든 열을 빠짐없이 적는다
    # 입원 범위(index_admission 등)로 고를 때 쓰는 입원 번호 열. None이면 입원 범위가 없다
    admission_column: str | None = None
    admission_nullable: bool = False
    # 이 테이블의 행이 소속 입원의 퇴원 뒤 얼마까지 늦게 알려질 수 있는가(시간). None = 상한 없음
    max_after_discharge_h: float | None = 0.0
    # 결과를 이 테이블로 정하면 확인 강도가 층마다 다를 수 있다 (Q7)
    measurement: bool = False
    # 수정 이력: (항목 열, 버전 열). as_of로 버전을 고른다
    versions: tuple[str, str] | None = None
    # 값에서 계산하는 열 (데이터 단계)
    derived: dict[str, str] = field(default_factory=dict)


def _same(cols, a: Avail) -> dict[str, Avail]:
    return {c: a for c in cols}


_DICT = "설명서"
_ADMIT = Avail("row_anchor", "admit", 1, f"{_DICT}: 입원 시 알려진다")
_DISCHARGE = Avail("row_anchor", "discharge", 1, f"{_DICT}: 퇴원 시 알려진다 (discharge_time)")
_FIRST = Avail("first_admit", None, 1, f"{_DICT}: 그 등록 번호의 첫 입원 시 알려진다")
_EXTRACT = Avail("extraction", None, 1, f"{_DICT}: 자료 추출 시 알려진다 (모든 tₚ 뒤)")
_LABS = Avail("column", "report_time", 1, f"{_DICT}: 검사 값은 보고 시각(report_time)에 알려진다. "
              f"채취→보고 지연 상한 {LAB_REPORT_LAG_MAX_H:g}h",
              lag_from={"collect_time": LAB_REPORT_LAG_MAX_H})
_VITALS = Avail("column", "entered_time", 1, f"{_DICT}: 활력징후는 전산 입력 시각(entered_time)에 알려진다. "
                f"관찰→입력 지연 상한 {VITAL_ENTRY_LAG_MAX_H:g}h",
                lag_from={"charted_time": VITAL_ENTRY_LAG_MAX_H})
_OLABS = Avail("column", "report_time", 1, f"{_DICT}: 외래 검사 값은 보고 시각(report_time)에 알려진다. "
               f"채취→보고 지연 상한 {OUTPATIENT_LAB_LAG_MAX_H:g}h",
               lag_from={"collect_time": OUTPATIENT_LAB_LAG_MAX_H})
_DX = Avail("column", "coded_time", 1, f"{_DICT}: 진단 코드는 코딩 완료 시각(coded_time)에 알려진다. "
            f"퇴원 뒤 최대 {DX_CODING_MAX_AFTER_DISCHARGE_H / D:g}일")
_PROC = Avail("column", "coded_time", 1, f"{_DICT}: 시술 코드는 코드 입력 시각(coded_time)에 알려진다. "
              f"시술 날짜(chart_date)에서 입력까지 지연 상한 없음, 퇴원 뒤 최대 "
              f"{PROC_CODING_MAX_AFTER_DISCHARGE_H / D:g}일", lag_from={"chart_date": None})
_PROBLEM = Avail("column", "recorded_time", 1, f"{_DICT}: 문제 목록은 버전마다 기록 시각(recorded_time)에 알려진다")
_ORDER_MED = Avail("column", "order_time", 1, f"{_DICT}: 처방 시각(order_time)에 알려진다")
_ORDER = Avail("column", "order_time", 1, f"{_DICT}: 오더 시각(order_time)에 알려진다")
_VISIT = Avail("column", "visit_time", 1, f"{_DICT}: 방문 시각(visit_time)에 알려진다")
_BOOKED = Avail("column", "booked_time", 1, f"{_DICT}: 예약 시각(booked_time)에 알려진다")
_DEATH = Avail("column", "death_recorded_time", 1, f"{_DICT}: 사망은 사망 기록 시각(death_recorded_time)에 알려진다. "
               f"원외 사망은 사망 뒤 최대 {DEATH_RECORD_LAG_MAX_H / D:g}일",
               lag_from={"death_time": DEATH_RECORD_LAG_MAX_H})

TABLES: dict[str, TableRule] = {
    "extract_info": TableRule(
        name="extract_info", entity_via=None, id_columns=("extraction_end_time",),
        time_columns={"extraction_end_time": "datetime", "death_linkage_through": "date"},
        value_column=None, row_available=_EXTRACT,
        column_available=_same(("extraction_end_time", "sites_covered", "death_linkage_through"), _EXTRACT),
        max_after_discharge_h=None,
    ),
    "patients": TableRule(
        name="patients", entity_via="patient_id", id_columns=("patient_id",), time_columns={},
        value_column=None, row_available=_FIRST,
        column_available=_same(("patient_id", "family_id", "age", "sex"), _FIRST),
    ),
    "person_links": TableRule(
        name="person_links", entity_via="patient_id", id_columns=("patient_id",), time_columns={},
        value_column="person_id", row_available=_FIRST,
        column_available={"patient_id": _FIRST,
                          "person_id": Avail("extraction", None, 1,
                                             f"{_DICT}: 등록 번호 연결은 자료 추출 때 한 번에 한다 (모든 tₚ 뒤)")},
    ),
    "admissions": TableRule(
        name="admissions", entity_via="patient_id", id_columns=("admission_id",),
        time_columns={"admit_time": "datetime", "discharge_time": "datetime"},
        value_column=None, row_available=_ADMIT,
        column_available={**_same(("admission_id", "patient_id", "admit_time", "unit"), _ADMIT),
                          **_same(("discharge_time", "discharge_status", "length_of_stay_h"), _DISCHARGE)},
        admission_column="admission_id",
        derived={"length_of_stay_h": "(discharge_time - admit_time) 시간"},
    ),
    "admission_info": TableRule(
        name="admission_info", entity_via="admission_id", id_columns=("admission_id",), time_columns={},
        value_column=None, row_available=_ADMIT,
        column_available=_same(("admission_id", "site", "admission_type", "service", "episode_id"), _ADMIT),
        admission_column="admission_id",
    ),
    "transfers": TableRule(
        name="transfers", entity_via="admission_id", id_columns=("transfer_id",),
        time_columns={"in_time": "datetime", "out_time": "datetime"},
        value_column="unit", row_available=Avail("column", "in_time", 1, f"{_DICT}: 병동 입실 시각(in_time)에 알려진다"),
        column_available={**_same(("transfer_id", "admission_id", "unit", "in_time"),
                                  Avail("column", "in_time", 1, f"{_DICT}: 병동 입실 시각(in_time)에 알려진다")),
                          "out_time": Avail("column", "out_time", 1, f"{_DICT}: 병동 퇴실 시각(out_time)에 알려진다",
                                            lag_from={"in_time": None})},
        admission_column="admission_id",
    ),
    "labs": TableRule(
        name="labs", entity_via="admission_id", id_columns=("lab_id",),
        time_columns={"collect_time": "datetime", "report_time": "datetime"},
        value_column="value", row_available=_LABS,
        column_available=_same(("lab_id", "admission_id", "test", "value", "unit", "method", "collect_time",
                                "report_time"), _LABS),
        admission_column="admission_id", max_after_discharge_h=LAB_REPORT_LAG_MAX_H, measurement=True,
    ),
    "vitals": TableRule(
        name="vitals", entity_via="admission_id", id_columns=("vital_id",),
        time_columns={"charted_time": "datetime", "entered_time": "datetime"},
        value_column="value", row_available=_VITALS,
        column_available=_same(("vital_id", "admission_id", "item", "value", "charted_time", "entered_time"),
                               _VITALS),
        admission_column="admission_id", max_after_discharge_h=VITAL_ENTRY_LAG_MAX_H, measurement=True,
    ),
    "medications": TableRule(
        name="medications", entity_via="admission_id", id_columns=("med_id",),
        time_columns={"order_time": "datetime"}, value_column="drug", row_available=_ORDER_MED,
        column_available=_same(("med_id", "admission_id", "drug", "med_type", "order_time"), _ORDER_MED),
        admission_column="admission_id",
    ),
    "orders": TableRule(
        name="orders", entity_via="admission_id", id_columns=("order_id",),
        time_columns={"order_time": "datetime"}, value_column="order_type", row_available=_ORDER,
        column_available=_same(("order_id", "admission_id", "order_type", "order_time"), _ORDER),
        admission_column="admission_id",
    ),
    "diagnoses": TableRule(
        name="diagnoses", entity_via="admission_id", id_columns=("admission_id", "seq"),
        time_columns={"coded_time": "datetime"}, value_column="icd_code", row_available=_DX,
        column_available=_same(("admission_id", "seq", "icd_code", "code_system", "present_on_admission",
                                "coded_time"), _DX),
        admission_column="admission_id", max_after_discharge_h=DX_CODING_MAX_AFTER_DISCHARGE_H, measurement=True,
    ),
    "procedures": TableRule(
        name="procedures", entity_via="admission_id", id_columns=("admission_id", "code", "chart_date"),
        time_columns={"chart_date": "date", "coded_time": "datetime"}, value_column="code", row_available=_PROC,
        column_available=_same(("admission_id", "code", "chart_date", "coded_time"), _PROC),
        admission_column="admission_id", max_after_discharge_h=PROC_CODING_MAX_AFTER_DISCHARGE_H,
    ),
    "problem_list": TableRule(
        name="problem_list", entity_via="patient_id", id_columns=("entry_id", "version"),
        time_columns={"recorded_time": "datetime"}, value_column="icd_code", row_available=_PROBLEM,
        column_available=_same(("entry_id", "patient_id", "admission_id", "version", "icd_code", "status",
                                "recorded_time"), _PROBLEM),
        admission_column="admission_id", max_after_discharge_h=PROBLEM_MAX_AFTER_DISCHARGE_H,
        versions=("entry_id", "version"),
    ),
    "outpatient_visits": TableRule(
        name="outpatient_visits", entity_via="patient_id", id_columns=("visit_id",),
        time_columns={"visit_time": "datetime"}, value_column="visit_type", row_available=_VISIT,
        column_available=_same(("visit_id", "patient_id", "visit_time", "site", "visit_type"), _VISIT),
        max_after_discharge_h=None,
    ),
    "outpatient_labs": TableRule(
        name="outpatient_labs", entity_via="patient_id", id_columns=("lab_id",),
        time_columns={"collect_time": "datetime", "report_time": "datetime"}, value_column="value",
        row_available=_OLABS,
        column_available=_same(("lab_id", "patient_id", "visit_id", "test", "value", "unit", "method",
                                "collect_time", "report_time"), _OLABS),
        max_after_discharge_h=None, measurement=True,
    ),
    "admission_bookings": TableRule(
        name="admission_bookings", entity_via="patient_id", id_columns=("booking_id",),
        time_columns={"booked_time": "datetime", "planned_date": "date"}, value_column="planned_date",
        row_available=_BOOKED,
        column_available={**_same(("booking_id", "patient_id", "source_admission_id", "booked_time",
                                   "planned_date"), _BOOKED),
                          "admission_id": Avail("linked_admit", "admission_id", 1,
                                                f"{_DICT}: 예약 입원이 이루어질 때(그 입원의 입원 시각) 채워진다")},
        admission_column="source_admission_id", admission_nullable=True,
    ),
    "deaths": TableRule(
        name="deaths", entity_via="patient_id", id_columns=("patient_id",),
        time_columns={"death_time": "datetime", "death_recorded_time": "datetime"}, value_column="death_time",
        row_available=_DEATH,
        column_available=_same(("patient_id", "death_time", "place", "death_recorded_time", "source"), _DEATH),
        max_after_discharge_h=None,
    ),
}

# 데이터 파일에는 없지만 설계서가 쓰는 예측 행 식별자 (설명서 파생 열 index_row.landmark_row_id)
INDEX_ROW_COLUMNS = {"landmark_row_id": "index_id"}

# ---------------------------------------------------------------- 분할 (Q2)
# 독립 단위의 위계 (작은 것 → 큰 것). 형식(designs/schema.json split_unit)과 같다.
SPLIT_LEVELS = {"index_row": 0, "admission": 1, "episode": 2, "patient": 3, "person": 4, "family": 5}
SPLIT_ALIASES = {
    "index_row": "index_row", "index_id": "index_row", "row": "index_row", "row_id": "index_row",
    "landmark_row_id": "index_row",
    "admission": "admission", "admission_id": "admission",
    "episode": "episode", "episode_id": "episode",
    "patient": "patient", "patient_id": "patient",
    "person": "person", "person_id": "person",
    "family": "family", "family_id": "family",
}
SPLIT_KEY_COLUMN = {"index_row": "index_id", "admission": "admission_id", "episode": "episode_id",
                    "patient": "patient_id", "person": "person_id", "family": "family_id"}
# 같은 개체의 행은 반드시 함께 움직여야 한다. 독립 단위는 이보다 작을 수 없다.
# 2층: 설명서 person_links — 같은 사람이 등록 번호 둘을 가질 수 있다 (2026-10-04 사용자 결정 D6)
ENTITY_LEVEL = "person"
ENTITY_BASIS = f"{_DICT} person_links: 일부 사람은 등록 번호(patient_id)가 둘이다. 같은 사람은 person_id로 묶인다"
# 형식의 기본값 (designs/schema.json split_unit default)
DEFAULT_SPLIT_UNIT = "patient"
# 결측이 있는 묶음 열 (설명서 patients.family_id 결측 약 80%)
NULLABLE_SPLIT_LEVELS = {"family"}
ROW_LEVEL_METHODS = {"random_rows"}

# 시간 순 분할(temporal)의 해석 (2026-10-04 사용자 결정 D5).
# 형식 설명서: key = 분할 묶음 열, fallback_key = key가 결측인 행에 쓸 열, cutoff = 경계 시각,
# gap = 학습 끝과 평가 시작 사이 간격. 설명서가 정하지 않은 부분은 가장 보수적으로 정했다.
TEMPORAL_RULE = (
    "묶음(key, 결측이면 fallback_key)째로 움직인다. 묶음의 모든 행이 cutoff 이전(≤)이면 학습. "
    "cutoff 뒤의 행이 하나라도 있는 묶음은 학습에 넣지 않고, 그 묶음의 cutoff + gap 뒤 행만 평가에 넣는다. "
    "나머지 행(학습에 못 들어간 묶음의 cutoff + gap 이전 행)은 어느 쪽에도 쓰지 않는다. "
    "기준 시각 열(time_column)이 없으면 tp. cutoff가 없으면 test_fraction 분위수"
)

# 데이터에서 무엇을 추정하는 단계가 허용되는 적합 범위 (validation = 학습 부분에서 떼어 둔 검증 부분)
FIT_SCOPES_OK = {"train", "train_fold", "validation"}
# 재표본 추출은 학습 데이터에만 적용해야 한다
RESAMPLE_APPLY_OK = {"train", "train_fold"}
# 뒤(나중) 행의 값을 쓰는 결측 대치 방법
FUTURE_FILL_METHODS = {"backward_fill", "bfill", "interpolate"}

# ---------------------------------------------------------------- 결과 (Q4, Q7)

@dataclass(frozen=True)
class Stratum:
    id: str
    name: str
    members: tuple[tuple[str, str], ...]    # 이 층을 나타내는 (테이블, 열)
    basis: str


UNIT_STRATUM = Stratum("O.strata.unit", "머문 병동", (("admissions", "unit"), ("transfers", "unit")),
                       f"{_DICT} labs.collect_time: ICU는 하루 1~2회, 병동은 30~72시간 간격으로 채혈 "
                       f"(vitals도 ICU 1~2시간, 병동 4~8시간)")
SERVICE_STRATUM = Stratum("O.strata.service", "진료과", (("admission_info", "service"),),
                          f"{_DICT} 데이터 전체의 성질: 진단 코드의 누락 정도는 병동·진료과에 따라 다르다")
DISCHARGE_STRATUM = Stratum("O.strata.discharge_status", "퇴원처", (("admissions", "discharge_status"),),
                            f"{_DICT} 데이터 전체의 성질: 퇴원처에 따라 퇴원 뒤 다른 병원(B)으로 재입원하는 비율이 "
                            f"다르다 (전원 > 자택)")

# 결과 정의(또는 결과 테이블)별로 확인 강도를 좌우하는 층 (2층)
ASCERTAINMENT_STRATA: dict[str, tuple[Stratum, ...]] = {
    "labs": (UNIT_STRATUM,),
    "vitals": (UNIT_STRATUM,),
    "diagnoses": (UNIT_STRATUM, SERVICE_STRATUM),
}
# 결과 확인 범위(병원)가 데이터보다 좁을 때 놓치는 정도를 좌우하는 층 (2층)
SITE_SCOPE_STRATA: tuple[Stratum, ...] = (DISCHARGE_STRATUM,)
ALL_SITES = ("A", "B")      # 설명서 extract_info.sites_covered
# 데이터 단계 Q7에서 측정 빈도를 비교하는 후보 층 (v1부터)
ASCERTAINMENT_CANDIDATES = [("admissions", "unit"), ("patients", "sex")]

# 연구 기간 중 결과 측정법·코드 체계가 바뀐 것 (2층, 설명서)
OUTCOME_CHANGES = [
    {"id": "O.change.creatinine_method", "source": "labs", "filter": {"test": ["creatinine"]},
     "date": "2155-01-01", "what": "크레아티닌 측정법 jaffe → enzymatic (labs.method)"},
    {"id": "O.change.icd", "source": "diagnoses", "filter": {}, "date": "2155-10-01",
     "what": "진단 코드 체계 ICD-9 → ICD-10 (diagnoses.code_system)"},
]

# 결과 정의별 대리 기록 (2층: 결과를 정하는 임상 과정에서 생기는 기록). 설계서의 proxies와 합쳐 쓴다.
OUTCOME_PROXIES: dict[str, list[dict]] = {
    "kdigo_creatinine": [
        {"id": "O.proxy.renal_orders", "source": "orders",
         "filter": {"order_type": ["dialysis_order", "nephrology_consult", "renal_ultrasound"]},
         "basis": f"{_DICT} orders.order_type: 신장 관련 오더는 AKI 무렵에 몰림"},
        {"id": "O.proxy.dialysis_procedure", "source": "procedures", "filter": {"code": ["5A1D70Z"]},
         "basis": f"{_DICT} procedures.code: 투석 처치는 AKI 무렵 (ICD-10-PCS 5A1D = 투석)"},
        {"id": "O.proxy.aki_code", "source": "diagnoses", "filter": {"icd_code": ["N17", "584"]},
         "basis": f"{_DICT} diagnoses.icd_code: AKI 진단 코드 (ICD-9 584)"},
        {"id": "O.proxy.aki_problem", "source": "problem_list", "filter": {"icd_code": ["N17"]},
         "basis": f"{_DICT} problem_list.icd_code: N17.9는 KDIGO 기준을 만족한 검사 보고 뒤에 기록"},
        {"id": "O.proxy.diuretic", "source": "medications", "filter": {"drug": ["loop_diuretic"]},
         "basis": f"{_DICT} medications.drug: AKI 입원의 40%는 발생 6~48시간 뒤 이뇨제 처방이 더 있음"},
    ],
    "next_admission": [],
    "diagnosis_code": [],   # 결과와 같은 코드의 문제 목록 항목을 실행 때 더한다
}

# 앞부분 일치로 거르는 코드 열 (N17 → N17.9)
CODE_COLUMNS = {"icd_code", "code"}

# ---------------------------------------------------------------- 가정 (3층) — 출력할 때 쓰는 문장
ASSUMPTIONS = {
    "A.date_only": ("날짜만 있는 값은 그날 중 언제인지 모른다. 설계서에 date_compare가 없으면 그날 23:59로 본다",
                    "DATE_ONLY_DEFAULT"),
    "A.family_missing": ("family_id가 비어 있는 행은 가족 관계를 모른다. 대체 키(fallback_key)로 묶는다. "
                         "기록되지 않은 가족은 학습·평가에 나뉠 수 있다", None),
    "A.outside_sites": ("A·B 밖 병원의 사건은 데이터에 없다. 결과 확인 범위 밖에서 생긴 결과는 보이지 않는다", None),
    "A.episode_last": (f"에피소드의 마지막 입원을 고르려면 퇴원 뒤 {EPISODE_GAP_MAX_H * 60:g}분 안에 이어진 입원이 "
                       f"없음을 알아야 한다. 퇴원 때 안다고 본다 (형식에 다른 올바른 표현이 없음)", "EPISODE_GAP_MAX_H"),
    "A.post_tp_exclusion": ("tₚ 뒤의 일(추적 소실, 결과 결측)로 행을 뺀다. 형식에 치우침 없는 다른 처리 값이 없어 "
                            "가정으로 남긴다", None),
}


def default_time_column(table: str) -> str | None:
    """창을 적용할 기본 시각 열: 확인 가능 시각 열 (입원은 입원 시각)."""
    a = table_rule(table).row_available
    if a.kind == "column":
        return a.column
    if table == "admissions":
        return "admit_time"
    return None


def table_rule(table: str) -> TableRule:
    try:
        return TABLES[table]
    except KeyError:
        raise RuleMissing(f"규칙표에 테이블 '{table}'의 규칙이 없다") from None


def availability(table: str, column: str | None = None) -> Avail:
    """(테이블, 열) 값이 알려지는 시각의 규칙. 열을 주지 않으면 행 규칙."""
    rule = table_rule(table)
    if column is None:
        return rule.row_available
    if column in rule.column_available:
        return rule.column_available[column]
    raise RuleMissing(f"규칙표에 '{table}.{column}'의 규칙이 없다")


def rule_id(table: str, column: str | None = None) -> str:
    return f"T.{table}" + (f".{column}" if column else "")


def split_level(name: str) -> str:
    try:
        return SPLIT_ALIASES[name]
    except KeyError:
        raise RuleMissing(f"분할 단위·키 '{name}'가 규칙표의 위계에 없다") from None
