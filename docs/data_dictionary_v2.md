# 데이터 설명서 (v2)

v2 합성 데이터의 **모든 테이블의 모든 열**에 대해, 값이 언제 생기고 언제 알려지는지를 같은 형식으로 적는다.
모든 환자·수치는 가상 값이다. 날짜는 실제 날짜와 섞이지 않게 2150년대로 옮겨 두었다.

- 테이블·열 목록의 기준은 `synth/tables_v2.py`이다. 시험(`tests/test_data_dictionary.py`)이 목록의 모든 열과 파생 열이 이 문서에 있고, 칸이 모두 채워졌는지 확인한다.
- v2에서 데이터 구조를 확정하며 전체 재생성한다 (2단계 2b). 이 문서의 결측 비율·값의 범위는 **설계값**이다. 2b에서 생성한 뒤 실측값으로 바꾸고, 바꾼 사실을 기록한다.
- 3단계는 이 문서만 보고 `leakcheck/rules.py`의 테이블 규칙을 쓴다.
- 근거 꼬리표는 `docs/design_format_v2.md`와 같은 형식이다.
- 시각은 분 단위 (`YYYY-MM-DD HH:MM:SS`), 날짜는 일 단위 (`YYYY-MM-DD`).

## 칸 설명

| 칸 | 내용 |
|---|---|
| 자료형 | 정수 / 실수 / 문자 / 시각 / 날짜 / 참거짓 |
| 값이 생기는 때 | 그 값이 가리키는 사건의 시각. 시각과 무관한 값이면 "정적" |
| 값이 알려지는 때 | 기록·보고되어 조회할 수 있게 되는 시각. 어느 열로 알 수 있는지, 또는 고정된 지연 |
| 지연·불확실성 | 생기는 때와 알려지는 때의 차이, 시각의 단위·정밀도 |
| 결측 | 비율과 이유 |
| 값의 범위 | 범주 목록 또는 범위 |
| 생성 방식 | 생성기에서 어떻게 만드는가 |
| 근거 | 분류 꼬리표 |

## 데이터 전체의 성질 (생성기에 넣는 일반적 특성)

- 연구 기간: 2150-01-01 ~ 자료 추출 종료 시각(2160-01-01 00:00). 모든 사건 시각과 기록 시각은 자료 추출 종료 시각 이전이다.
- 병원 두 곳(A, B)의 기록이 모두 들어 있다. 대부분 A에서 입원한다.
- 사망 뒤에는 새 사건(입원, 검사 채취, 처방, 오더, 외래 등)이 없다. 사망 전에 생긴 사건의 기록(검사 보고, 코딩)은 사망 뒤에 있을 수 있다.
- 시간이 흐르며 진료 관행(검사 빈도, ICU 입실 비율)이 서서히 바뀐다.
- 주말·야간에는 병동 검사·관찰 빈도가 낮다.
- 연구 기간 중 크레아티닌 측정법이 한 번 바뀌고, 진단 코드 체계가 ICD-9에서 ICD-10으로 한 번 바뀐다.
- 진단 코드의 누락 정도는 병동·진료과에 따라 다르다.
- 퇴원처에 따라 퇴원 뒤 다른 병원(B)으로 재입원하는 비율이 다르다 (전원 퇴원 > 자택 퇴원).
- 일부 진료 에피소드는 병원·진료과 이동으로 입원 기록 두 건으로 나뉜다.
- 일부 사람은 등록 번호(patient_id)가 둘이다.
- 가족 정보(family_id)는 대부분 없다.

## extract_info (1행)

행 하나 = 이번 자료 추출. 키 없음.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `extract_info.extraction_end_time` | 시각 | 자료 추출 시 | 자료 추출 시 | 없음 | 0% | 2160-01-01 00:00:00 | 고정값 | P 1.1; P 4.6; P+AI 참여자·데이터 출처; Albu |
| `extract_info.sites_covered` | 문자 | 자료 추출 시 | 자료 추출 시 | 없음 | 0% | "A;B" | 고정값 | K L3.3; P 1.1; P+AI 참여자·데이터 출처 |
| `extract_info.death_linkage_through` | 날짜 | 자료 추출 시 | 자료 추출 시 | 이 날짜 이후의 원외 사망은 아직 연계되지 않았다 | 0% | 자료 추출 종료 약 6개월 전 | 고정값 | P 3.6; P 4.6; P+AI 결과; Albu |

## patients

행 하나 = 등록 번호 하나. 키: `patient_id`.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `patients.patient_id` | 문자 | 등록 시 | 첫 입원 시 | 없음 | 0% | P00001 형식 | 일련번호 | K L3.2; P+AI 분석 |
| `patients.family_id` | 문자 | 정적 | 첫 입원 시 | 가족 연결은 일부만 기록된다 | 약 80% (가족 연결 미기록) | F0001 형식 | 가족 묶음을 만든 뒤 일부에만 기록. 가족은 잠재 위험을 공유 | K L3.2; P 4.6; P+AI 분석 |
| `patients.age` | 정수 | 정적 (첫 입원 시 나이) | 첫 입원 시 | 없음 | 0% | 18~95 | 연령 분포에서 추출 | P 2.3; P+AI 예측변수 |
| `patients.sex` | 문자 | 정적 | 첫 입원 시 | 없음 | 0% | M, F | 반반 | P 2.3; P+AI 예측변수 |

## person_links

행 하나 = 등록 번호 하나. 키: `patient_id`. 같은 사람의 등록 번호는 같은 `person_id`를 가진다.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `person_links.patient_id` | 문자 | 등록 시 | 첫 입원 시 | 없음 | 0% | patients와 같음 | 모든 등록 번호에 한 행 | K L1.4; K L3.2; P+AI 분석 |
| `person_links.person_id` | 문자 | 정적 | 자료 추출 시 (등록 번호 연결 작업) | 연결은 추출 때 한 번에 한다 | 0% | H00001 형식 | 사람마다 하나. 일부(설계 약 2%) 사람은 나중 입원이 새 등록 번호로 기록됨 | K L1.4; K L3.2; P+AI 분석; Albu |

## admissions

행 하나 = 입원 기록 하나. 키: `admission_id`.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `admissions.admission_id` | 문자 | 입원 시 | 입원 시 | 없음 | 0% | A000001 형식 | 일련번호 | K L3.2; P+AI 분석 |
| `admissions.patient_id` | 문자 | 입원 시 | 입원 시 | 없음 | 0% | patients와 같음 | 입원한 등록 번호 | K L3.2; P+AI 분석 |
| `admissions.admit_time` | 시각 | 입원 시 | 입원 시 | 없음 | 0% | 연구 기간 안 | 첫 입원은 기간 안 무작위, 재입원은 퇴원 뒤 간격 | K L3.1; P 2.3; P 3.6; P+AI 예측변수; Albu |
| `admissions.discharge_time` | 시각 | 퇴원(또는 원내 사망) 시 | 퇴원 시 | 없음 | 0% | admit_time 이후 | 재원 기간 분포. 원내 사망이면 사망 시각 | K L3.1; P 2.3; P 3.6; P+AI 예측변수; Albu |
| `admissions.discharge_status` | 문자 | 퇴원 시 | 퇴원 시 | 없음 | 0% | home, transfer, died | 위험도에 따른 퇴원처 | P 3.4; P 4.6; P+AI 결과; Albu |
| `admissions.unit` | 문자 | 입원 시 (처음 배정된 병동) | 입원 시 | 이후 이동은 transfers에 | 0% | ICU, ward | 위험도에 따라 배정 | P 2.1; P 3.4; P+AI 결과 |

## admission_info

행 하나 = 입원 기록 하나. 키: `admission_id`.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `admission_info.admission_id` | 문자 | 입원 시 | 입원 시 | 없음 | 0% | admissions와 같음 | 모든 입원에 한 행 | 관리 |
| `admission_info.site` | 문자 | 입원 시 | 입원 시 | 없음 | 0% | A, B | 대부분 A. 퇴원 뒤 재입원이 B로 갈 확률은 직전 퇴원처에 따라 다름 (전원 > 자택) | K L3.3; P 1.1; P 3.4; P+AI 참여자·데이터 출처 |
| `admission_info.admission_type` | 문자 | 입원 시 | 입원 시 | 없음 | 0% | emergency, elective | 예약된 입원(admission_bookings)이면 elective | P 1.2; P 2.3; P+AI 참여자·데이터 출처 |
| `admission_info.service` | 문자 | 입원 시 | 입원 시 | 없음 | 0% | medicine, surgery | 입원 사유에 따라 배정 | P 2.1; P 3.4; P+AI 결과 |
| `admission_info.episode_id` | 문자 | 입원 시 | 입원 시 (이어지는 입원이면 이전 입원과 같은 값) | 없음 | 0% | E000001 형식 | 대부분 입원마다 새 값. 병원·진료과 이동으로 바로 이어진 입원은 같은 값 | K L3.2; P 4.6; P+AI 분석; Albu |

## transfers

행 하나 = 입원 중 한 병동에 머문 구간. 키: `transfer_id`.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `transfers.transfer_id` | 문자 | 병동 입실 시 | 병동 입실 시 | 없음 | 0% | T000001 형식 | 일련번호 | 관리 |
| `transfers.admission_id` | 문자 | 병동 입실 시 | 병동 입실 시 | 없음 | 0% | admissions와 같음 | 입원마다 1개 이상 | 관리 |
| `transfers.unit` | 문자 | 병동 입실 시 | 병동 입실 시 | 없음 | 0% | ICU, ward | 첫 구간은 admissions.unit. 일부는 입원 중 병동↔ICU 이동 | K L3.3; P 1.2; P 2.1; P+AI 참여자·데이터 출처; Suissa |
| `transfers.in_time` | 시각 | 병동 입실 시 | 병동 입실 시 | 없음 | 0% | 입원 기간 안 | 첫 구간은 admit_time | K L3.1; P 2.3; P+AI 예측변수; Albu |
| `transfers.out_time` | 시각 | 병동 퇴실 시 | 병동 퇴실 시 | 없음 | 0% | 입원 기간 안 | 마지막 구간은 discharge_time | K L3.1; P 2.3; P+AI 예측변수; Albu |

## labs

행 하나 = 입원 중 검사 결과 하나. 키: `lab_id`.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `labs.lab_id` | 문자 | 채취 시 | 보고 시 | 없음 | 0% | L0000001 형식 | 일련번호 | 관리 |
| `labs.admission_id` | 문자 | 채취 시 | 보고 시 | 없음 | 0% | admissions와 같음 | 입원 중 채취 | 관리 |
| `labs.test` | 문자 | 채취 시 | 보고 시 | 없음 | 0% | creatinine, bun, potassium, hemoglobin | 검사 묶음 | P 2.1; P+AI 예측변수 |
| `labs.value` | 실수 | 채취 시 (환자 상태) | report_time | 채취 뒤 30분~6시간 | 0% | 검사별 생리적 범위 | 잠재 상태 + 측정 오차. 크레아티닌은 측정법에 따라 계통 차이 | P 2.1; P 3.1; P+AI 예측변수 |
| `labs.unit` | 문자 | 정적 | 보고 시 | 없음 | 0% | mg/dL, mmol/L, g/dL | 검사별 고정 | 관리 |
| `labs.method` | 문자 | 채취 시 | 보고 시 | 없음 | 0% | 크레아티닌: jaffe, enzymatic / 그 밖: standard | 크레아티닌 측정법이 연구 기간 중 한 번 바뀜 | P 2.1; P 3.4; P+AI 결과; Albu |
| `labs.collect_time` | 시각 | 채취 시 | 보고 시 (report_time) | 없음 | 0% | 입원 기간 안 | ICU는 하루 1~2회, 병동은 2~3일에 1회. 주말·야간 병동은 더 드묾. 시기에 따라 빈도 변화 | K L3.1; P 2.3; P+AI 예측변수; Albu |
| `labs.report_time` | 시각 | 보고 시 | 보고 시 | collect_time 뒤 30분~6시간. 퇴원·사망 뒤 보고 있음 | 0% | 자료 추출 종료 이전 | 채취 시각 + 지연 | K L3.1; P 2.3; P+AI 예측변수; Albu |

## vitals

행 하나 = 활력징후 관찰 하나. 키: `vital_id`.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `vitals.vital_id` | 문자 | 관찰 시 | 입력 시 | 없음 | 0% | V0000001 형식 | 일련번호 | 관리 |
| `vitals.admission_id` | 문자 | 관찰 시 | 입력 시 | 없음 | 0% | admissions와 같음 | 입원 중 관찰 | 관리 |
| `vitals.item` | 문자 | 관찰 시 | 입력 시 | 없음 | 0% | heart_rate, sbp, temperature | 관찰 묶음 | P 2.1; P+AI 예측변수 |
| `vitals.value` | 실수 | 관찰 시 | entered_time | 관찰 뒤 입력까지 지연 | 0% | 항목별 생리적 범위 | 잠재 상태 + 측정 오차 | P 2.1; P+AI 예측변수 |
| `vitals.charted_time` | 시각 | 관찰 시 (기록상 관찰 시각) | entered_time | 없음 | 0% | 입원 기간 안 | ICU 1~2시간, 병동 4~8시간 간격. 야간 병동은 더 드묾 | K L3.1; P 2.3; P+AI 예측변수; Albu |
| `vitals.entered_time` | 시각 | 전산 입력 시 | 전산 입력 시 | charted_time 뒤 0~6시간 (병동이 더 김) | 0% | 자료 추출 종료 이전 | 관찰 시각 + 지연 | K L3.1; P 2.3; P+AI 예측변수; Albu |

## medications

행 하나 = 처방 하나. 키: `med_id`.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `medications.med_id` | 문자 | 처방 시 | 처방 시 | 없음 | 0% | M0000001 형식 | 일련번호 | 관리 |
| `medications.admission_id` | 문자 | 처방 시 | 처방 시 | 없음 | 0% | admissions와 같음 | 입원 중 처방 | 관리 |
| `medications.drug` | 문자 | 처방 시 | 처방 시 | 없음 | 0% | 약물 계열 이름 (예: loop_diuretic, ace_inhibitor, nsaid, vancomycin 등) | 환자 상태에 따라 처방 | K L2; P 2.3; P+AI 예측변수; Kaufman |
| `medications.med_type` | 문자 | 처방 시 | 처방 시 | 없음 | 0% | inpatient, discharge | 입원 중 처방 / 퇴원약 | K L3.1; P 2.3; P+AI 예측변수; Kaufman |
| `medications.order_time` | 시각 | 처방 시 | 처방 시 | 없음 | 0% | 입원 기간 안 | 입원 중 처방은 입원 기간 안, 퇴원약은 퇴원 몇 시간 전 | K L3.1; P 2.3; P+AI 예측변수; Albu |

## orders

행 하나 = 오더 하나. 키: `order_id`.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `orders.order_id` | 문자 | 오더 시 | 오더 시 | 없음 | 0% | O0000001 형식 | 일련번호 | 관리 |
| `orders.admission_id` | 문자 | 오더 시 | 오더 시 | 없음 | 0% | admissions와 같음 | 입원 중 오더 | 관리 |
| `orders.order_type` | 문자 | 오더 시 | 오더 시 | 없음 | 0% | chest_xray, ct_head, echocardiogram, renal_ultrasound, dialysis_order, nephrology_consult, dietitian_consult, physical_therapy_consult, social_work_consult | 환자 상태에 따라. 신장 관련 오더는 AKI 무렵에 몰림 | K L2; P 3.3; P+AI 예측변수; Kaufman |
| `orders.order_time` | 시각 | 오더 시 | 오더 시 | 없음 | 0% | 입원 기간 안 | 상태 변화 뒤 | K L3.1; P 2.3; P+AI 예측변수; Albu |

## diagnoses

행 하나 = 입원 하나의 진단 코드 하나. 키: (`admission_id`, `seq`).

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `diagnoses.admission_id` | 문자 | 코딩 시 | coded_time | 없음 | 0% | admissions와 같음 | 퇴원한 입원마다 | 관리 |
| `diagnoses.seq` | 정수 | 코딩 시 | coded_time | 없음 | 0% | 1부터 | 입원 안 순서 | 관리 |
| `diagnoses.icd_code` | 문자 | 코딩 시 (입원 중 상태를 퇴원 뒤 요약) | coded_time | 퇴원 뒤 코딩 | 0% | ICD-9 또는 ICD-10 코드 | 입원 중 상태에서. AKI 코드의 누락 정도는 병동·진료과에 따라 다름 | K L2; P 2.3; P 3.1; P+AI 예측변수; Albu |
| `diagnoses.code_system` | 문자 | 코딩 시 | coded_time | 없음 | 0% | ICD9, ICD10 | 코딩 시점에 따라 한 번 전환 | P 3.4; P+AI 결과; Albu |
| `diagnoses.present_on_admission` | 문자 | 코딩 시 | coded_time | 없음 | 0% | Y, N | 입원 전부터 있던 상태면 Y | K L3.1; P 2.3; P+AI 예측변수; Albu; Kaufman |
| `diagnoses.coded_time` | 시각 | 코딩 완료 시 | 코딩 완료 시 | 퇴원 뒤 1~14일 (일부 더 늦음) | 0% (추출 종료까지 코딩이 끝나지 않은 입원은 행이 없음) | 퇴원 뒤, 자료 추출 종료 이전 | 퇴원 시각 + 지연 | K L3.1; P 2.3; P+AI 예측변수; Albu |

## procedures

행 하나 = 입원 하나의 시술 하나. 키: (`admission_id`, `code`, `chart_date`).

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `procedures.admission_id` | 문자 | 시술 시 | coded_time | 없음 | 0% | admissions와 같음 | 입원 중 시술 | 관리 |
| `procedures.code` | 문자 | 시술 시 | coded_time | 없음 | 0% | ICD-10-PCS 형식 코드 | 상태에 따라 (투석 처치는 AKI 무렵) | P 2.3; P+AI 예측변수 |
| `procedures.chart_date` | 날짜 | 시술한 날 | coded_time | 날짜만 있어 그날 중 언제인지 모름 | 0% | 입원 기간 안 | 시술 시각의 날짜 | K L3.1; P 2.3; P+AI 예측변수; Albu |
| `procedures.coded_time` | 시각 | 코드 입력 시 | 코드 입력 시 | 시술 뒤. 대부분 퇴원 뒤 행정 코딩 단계에서 입력 | 0% (추출 종료까지 입력되지 않은 시술은 행이 없음) | 자료 추출 종료 이전 | 시술일 또는 퇴원 시각 + 지연 | K L3.1; P 2.3; P+AI 예측변수; Albu |

## problem_list

행 하나 = 문제 목록 항목의 한 버전. 키: (`entry_id`, `version`).

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `problem_list.entry_id` | 문자 | 항목 처음 기록 시 | 처음 기록 시 | 없음 | 0% | PL000001 형식 | 일련번호 | 관리 |
| `problem_list.patient_id` | 문자 | 처음 기록 시 | 처음 기록 시 | 없음 | 0% | patients와 같음 | 기록한 등록 번호 | 관리 |
| `problem_list.admission_id` | 문자 | 이 버전 기록 시 | recorded_time | 없음 | 0% | admissions와 같음 | 이 버전을 기록한 입원 | 관리 |
| `problem_list.version` | 정수 | 이 버전 기록 시 | recorded_time | 없음 | 0% | 1부터 | 수정할 때마다 1 증가 | K L3.1; P 2.3; P+AI 예측변수; Albu |
| `problem_list.icd_code` | 문자 | 이 버전 기록 시 | recorded_time | 버전마다 다를 수 있음 | 0% | ICD-10 코드 | 입원 중 상태. 일부 항목은 입원 뒤에 코드가 바뀜 | K L3.1; P 2.3; P+AI 예측변수; Albu |
| `problem_list.status` | 문자 | 이 버전 기록 시 | recorded_time | 없음 | 0% | active, resolved, entered_in_error | 수정 버전에서 바뀜 | K L3.1; P 2.3; P+AI 예측변수; Albu |
| `problem_list.recorded_time` | 시각 | 이 버전 기록 시 | 이 버전 기록 시 | 첫 버전은 입원 중, 수정 버전은 입원 중 또는 퇴원 뒤 | 0% | 자료 추출 종료 이전 | 첫 기록 + 수정 간격 | K L3.1; P 2.3; P+AI 예측변수; Albu |

## outpatient_visits

행 하나 = 외래 방문 하나. 키: `visit_id`.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `outpatient_visits.visit_id` | 문자 | 방문 시 | 방문 시 | 없음 | 0% | OV000001 형식 | 일련번호 | 관리 |
| `outpatient_visits.patient_id` | 문자 | 방문 시 | 방문 시 | 없음 | 0% | patients와 같음 | 방문한 등록 번호 | 관리 |
| `outpatient_visits.visit_time` | 시각 | 방문 시 | 방문 시 | 없음 | 0% | 사망·자료 추출 종료 이전 | 생존 퇴원 뒤 추적 외래 (자택 퇴원이 더 잦음, 그 전에 재입원하면 열리지 않음) + 정기 외래 | K L3.3; P 1.2; P 3.6; P+AI 참여자·데이터 출처; Suissa |
| `outpatient_visits.site` | 문자 | 방문 시 | 방문 시 | 없음 | 0% | A, B | 대부분 A | K L3.3; P 3.1; P 3.4; P+AI 결과; Albu |
| `outpatient_visits.visit_type` | 문자 | 방문 시 | 방문 시 | 없음 | 0% | follow_up, routine | 퇴원 뒤 추적 / 정기 | P 3.4; P+AI 결과; Albu |

## outpatient_labs

행 하나 = 외래 검사 결과 하나. 키: `lab_id`.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `outpatient_labs.lab_id` | 문자 | 채취 시 | 보고 시 | 없음 | 0% | OL000001 형식 | 일련번호 | 관리 |
| `outpatient_labs.patient_id` | 문자 | 채취 시 | 보고 시 | 없음 | 0% | patients와 같음 | 외래 방문한 등록 번호 | 관리 |
| `outpatient_labs.visit_id` | 문자 | 채취 시 | 보고 시 | 없음 | 0% | outpatient_visits와 같음 | 일부 외래 방문에서 채취 | 관리 |
| `outpatient_labs.test` | 문자 | 채취 시 | 보고 시 | 없음 | 0% | creatinine, potassium, hemoglobin | 외래 검사 묶음 | P 2.1; P+AI 예측변수 |
| `outpatient_labs.value` | 실수 | 채취 시 | report_time | 채취 뒤 수 시간~1일 | 0% | 검사별 생리적 범위 | 평소 상태 + 측정 오차 | P 2.1; P 3.1; P+AI 결과 |
| `outpatient_labs.unit` | 문자 | 정적 | 보고 시 | 없음 | 0% | mg/dL, mmol/L, g/dL | 검사별 고정 | 관리 |
| `outpatient_labs.method` | 문자 | 채취 시 | 보고 시 | 없음 | 0% | labs.method와 같음 | 입원 검사와 같은 시기에 같은 전환 | P 2.1; P 3.4; P+AI 결과; Albu |
| `outpatient_labs.collect_time` | 시각 | 채취 시 | 보고 시 | 없음 | 0% | 방문 시각 | 방문 시각 | K L3.1; P 2.3; P+AI 예측변수; Albu |
| `outpatient_labs.report_time` | 시각 | 보고 시 | 보고 시 | collect_time 뒤 수 시간~1일 | 0% | 자료 추출 종료 이전 | 채취 시각 + 지연 | K L3.1; P 2.3; P+AI 예측변수; Albu |

## admission_bookings

행 하나 = 입원 예약 하나. 키: `booking_id`.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `admission_bookings.booking_id` | 문자 | 예약 시 | 예약 시 | 없음 | 0% | B000001 형식 | 일련번호 | 관리 |
| `admission_bookings.patient_id` | 문자 | 예약 시 | 예약 시 | 없음 | 0% | patients와 같음 | 예약한 등록 번호 | 관리 |
| `admission_bookings.source_admission_id` | 문자 | 예약 시 | 예약 시 | 없음 | 일부 (외래에서 예약) | admissions와 같음 | 입원 중 예약이면 그 입원 | K L2; P 3.3; P+AI 결과 |
| `admission_bookings.booked_time` | 시각 | 예약 시 | 예약 시 | 없음 | 0% | 사망·자료 추출 종료 이전 | 입원 중 또는 외래 | K L3.1; P 2.3; P+AI 예측변수 |
| `admission_bookings.planned_date` | 날짜 | 예약 시 | 예약 시 | 날짜만 | 0% | booked_time 뒤 | 예약 간격 | K L2; P 3.1; P+AI 결과 |
| `admission_bookings.admission_id` | 문자 | 예약 입원 시 | 예약 입원 시 | 없음 | 일부 (예약했지만 입원하지 않음, 또는 아직 입원 전) | admissions와 같음 | 예약대로 입원하면 그 입원 (elective) | K L2; P 3.1; P+AI 결과 |

## deaths

행 하나 = 사망 한 건. 키: `patient_id`. 사망 연계가 반영된 사망만 있다.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `deaths.patient_id` | 문자 | 사망 시 | death_recorded_time | 없음 | 0% | patients와 같음 | 사망한 사람의 등록 번호 | 관리 |
| `deaths.death_time` | 시각 | 사망 시 | death_recorded_time | 원외 사망은 기록이 늦음 | 0% | 자료 추출 종료 이전 | 원내 사망: discharge_time과 같음. 원외 사망: 마지막 퇴원 뒤 위험도에 따라 | P 3.6; P 4.6; P+AI 분석; Suissa |
| `deaths.place` | 문자 | 사망 시 | death_recorded_time | 없음 | 0% | in_hospital, out_of_hospital | 원내 / 원외 | P 3.4; P 4.6; P+AI 결과; Albu |
| `deaths.death_recorded_time` | 시각 | 사망 기록 시 | 사망 기록 시 | 원내: 사망 즉시. 원외: 사망 연계로 수 주~수 개월 뒤 | 0% | death_linkage_through 이전 (원외) | 사망 시각 + 지연 | K L3.1; P 2.3; P+AI 예측변수; Albu |
| `deaths.source` | 문자 | 사망 기록 시 | 사망 기록 시 | 없음 | 0% | hospital_record, registry_link | 원내 / 사망 연계 | P 3.1; P 3.4; P+AI 결과; Albu |

## 파생 열

데이터 파일에는 없지만 설계서가 열 이름으로 쓸 수 있는 값.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `admissions.length_of_stay_h` | 실수 | 퇴원 시 | 퇴원 시 (discharge_time) | 없음 | 0% | 0 이상 | 계산식: (discharge_time − admit_time) 시간 | K L3.1; P 1.2; P 2.3; P+AI 참여자·데이터 출처; Suissa |
| `index_row.landmark_row_id` | 문자 | 설계가 예측 행을 만들 때 | 예측 행을 만들 때 | 없음 | 0% | 예측 행마다 하나 | 계산식: 동적 설계 (admission_id, 랜드마크 간격) 한 쌍 / 고정 설계 admission_id | K L3.2; P 4.6; P+AI 분석 |

## 보조 데이터 (`data/synth_aux/`)

본 데이터와 **같은 테이블·같은 열**을 쓰고, 열마다 위 설명이 그대로 적용된다. 다른 점만 적는다.

- 규모: 환자 200명, 1인당 입원 1회.
- `labs.test`: 검사 500종 (`t001`~`t500`) + creatinine. 대부분 결과와 무관한 잡음이고 10종만 약한 신호. 항목마다 tₚ 이전 측정 1~3회.
- 결과(크레아티닌 KDIGO AKI) 유병률 약 30% (설계값).
- 다른 테이블은 본 데이터와 같은 규칙으로 만들되 규모에 맞게 줄인다.
