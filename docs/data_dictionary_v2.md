# 데이터 설명서 (v2)

v2 합성 데이터의 **모든 테이블의 모든 열**에 대해, 값이 언제 생기고 언제 알려지는지를 같은 형식으로 적는다.
모든 환자·수치는 가상 값이다. 날짜는 실제 날짜와 섞이지 않게 2150년대로 옮겨 두었다.

- 테이블·열 목록의 기준은 `synth/tables_v2.py`이다. 시험(`tests/test_data_dictionary.py`)이 목록의 모든 열과 파생 열이 이 문서에 있고, 칸이 모두 채워졌는지 확인한다.
- v2에서 데이터 구조를 확정하며 전체 재생성한다 (2단계 2b). 생성기는 `synth/generate_v2.py`. 설명서만으로 정할 수 없던 값은 2b에서 D1~D23으로 정했고(2026-10-04 사용자 승인), 아래 "생성 규칙" 절과 각 열의 칸에 적었다.
- 결측·값의 범위 칸은 2b에서 **실측값**으로 바꿨다 (2026-10-04, `synth/profile_v2.py`). 형식은 `실측 <값> (설계 <원래 설계값>)`. 본 데이터 `data/synth/MANIFEST.json` sha256 앞 16자 `56ad70bc11c00eec`, 보조 데이터는 맨 끝 "보조 데이터 실측값" 표 (`data/synth_aux/MANIFEST.json` `1b5f1fa4d1bfb877`). 시험(`tests/test_data_dictionary.py`)이 실측 부분이 저장된 데이터에서 다시 계산한 값과 같은지 확인한다.
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

- 연구 기간: 2150-01-01 ~ 자료 추출 종료 시각(2160-01-01 00:00). 모든 사건 시각과 기록 시각은 자료 추출 종료 시각 이전이다. 예외: 입원 예약의 예정일(`admission_bookings.planned_date`)은 일어난 사건이 아니라 앞으로의 예정이므로 종료 뒤일 수 있다.
- 종료 시각까지 보고·입력·코딩되지 않은 기록(검사 보고, 활력 입력, 진단·시술 코딩, 문제 목록 수정, 원외 사망 연계)은 행이 없다. 퇴원이 종료 뒤로 넘어가는 입원은 데이터에 없고, 그 사람의 기록은 그 입원 전에서 끝난다.
- 병원 두 곳(A, B)의 기록이 모두 들어 있다. 대부분 A에서 입원한다.
- 사망 뒤에는 새 사건(입원, 검사 채취, 처방, 오더, 외래 등)이 없다. 사망 전에 생긴 사건의 기록(검사 보고, 코딩, 문제 목록 수정)은 사망 뒤에 있을 수 있다. 사망 연계가 아직 반영되지 않은 원외 사망은 `deaths`에 없지만, 그 사람의 사건도 사망 뒤에는 없다.
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
| `extract_info.extraction_end_time` | 시각 | 자료 추출 시 | 자료 추출 시 | 없음 | 실측 0.0% (설계 0%) | 실측 2160-01-01 00:00 ~ 2160-01-01 00:00 (설계 2160-01-01 00:00:00) | 고정값 | P 1.1; P 4.6; P+AI 참여자·데이터 출처; Albu |
| `extract_info.sites_covered` | 문자 | 자료 추출 시 | 자료 추출 시 | 없음 | 실측 0.0% (설계 0%) | 실측 A;B (설계 "A;B") | 고정값 | K L3.3; P 1.1; P+AI 참여자·데이터 출처 |
| `extract_info.death_linkage_through` | 날짜 | 자료 추출 시 | 자료 추출 시 | 이 날짜 이후의 원외 사망은 아직 연계되지 않았다 | 실측 0.0% (설계 0%) | 실측 2159-07-01 ~ 2159-07-01 (설계 2159-07-01 (자료 추출 종료 6개월 전)) | 고정값 | P 3.6; P 4.6; P+AI 결과; Albu |

## patients

행 하나 = 등록 번호 하나. 키: `patient_id`.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `patients.patient_id` | 문자 | 등록 시 | 첫 입원 시 | 없음 | 실측 0.0% (설계 0%) | 실측 P00001 ~ P05111 (고유값 5111개) (설계 P00001 형식. 사람 5,000명의 번호(P00001~P05000) + 새 등록 번호(P05001부터, 약 2%)) | 일련번호. 새 등록 번호는 person_links 참고 | K L3.2; P+AI 분석 |
| `patients.family_id` | 문자 | 정적 | 첫 입원 시 | 가족 연결은 일부만 기록된다 | 실측 80.4% (설계 약 80% (가족 연결 미기록)) | 실측 F0001 ~ F0411 (고유값 411개) (설계 F0001 형식) | 사람의 40%가 가족(2~3명)에 속함. 가족 단위로 50%만 기록(기록된 가족만 번호를 받음). 기록되지 않은 가족도 잠재 위험을 공유. 새 등록 번호도 같은 값 | K L3.2; P 4.6; P+AI 분석 |
| `patients.age` | 정수 | 정적 (그 등록 번호의 첫 입원 시 나이) | 첫 입원 시 | 없음 | 실측 0.0% (설계 0%) | 실측 18 ~ 95 (설계 18~95) | 연령 분포에서 추출. 새 등록 번호는 그 번호로 처음 입원할 때의 나이(95 상한) | P 2.3; P+AI 예측변수 |
| `patients.sex` | 문자 | 정적 | 첫 입원 시 | 없음 | 실측 0.0% (설계 0%) | 실측 F, M (설계 M, F) | 반반 | P 2.3; P+AI 예측변수 |

## person_links

행 하나 = 등록 번호 하나. 키: `patient_id`. 같은 사람의 등록 번호는 같은 `person_id`를 가진다.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `person_links.patient_id` | 문자 | 등록 시 | 첫 입원 시 | 없음 | 실측 0.0% (설계 0%) | 실측 P00001 ~ P05111 (고유값 5111개) (설계 patients와 같음) | 모든 등록 번호에 한 행 | K L1.4; K L3.2; P+AI 분석 |
| `person_links.person_id` | 문자 | 정적 | 자료 추출 시 (등록 번호 연결 작업) | 연결은 추출 때 한 번에 한다 | 실측 0.0% (설계 0%) | 실측 H00001 ~ H05000 (고유값 5000개) (설계 H00001 형식) | 사람마다 하나. 입원 2회 이상인 사람의 7%(사람 전체의 약 2%)는 두 번째 이후의 어느 입원(이어진 입원 제외)부터 새 등록 번호로 기록됨. 그 시각 뒤의 외래·예약·문제 목록도 새 번호. 사망은 마지막 번호로. 성별·family_id는 같음 | K L1.4; K L3.2; P+AI 분석; Albu |

## admissions

행 하나 = 입원 기록 하나. 키: `admission_id`.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `admissions.admission_id` | 문자 | 입원 시 | 입원 시 | 없음 | 실측 0.0% (설계 0%) | 실측 A000001 ~ A007724 (고유값 7724개) (설계 A000001 형식) | 일련번호 | K L3.2; P+AI 분석 |
| `admissions.patient_id` | 문자 | 입원 시 | 입원 시 | 없음 | 실측 0.0% (설계 0%) | 실측 P00001 ~ P05111 (고유값 5111개) (설계 patients와 같음) | 입원한 등록 번호 | K L3.2; P+AI 분석 |
| `admissions.admit_time` | 시각 | 입원 시 | 입원 시 | 없음 | 실측 0.0% (설계 0%) | 실측 2150-01-01 13:29 ~ 2159-12-29 09:24 (설계 연구 기간 안) | 첫 입원은 연구 기간 전체에서 무작위 (2150-01-01 ~ 자료 추출 종료 30일 전. 재원 기간 상한이 30일이라 첫 입원의 퇴원은 종료 전). 다음 입원은 응급 재입원(30일 안: 위험 z·AKI·나이·ICU에 따른 확률, 그 밖 18%는 31~720일 뒤; 응급 입원은 1인 4회까지)·예약 입원·이어진 입원 중 먼저 오는 것. 원외 사망이 먼저면 다음 입원 없음. 1인 8회까지 | K L3.1; P 2.3; P 3.6; P+AI 예측변수; Albu |
| `admissions.discharge_time` | 시각 | 퇴원(또는 원내 사망) 시 | 퇴원 시 | 없음 | 실측 0.0% (설계 0%) | 실측 2150-01-03 16:07 ~ 2159-12-31 08:47 (설계 admit_time 이후) | 재원 기간 로그정규 분포(중앙값 ICU 110시간, 병동 80시간, 24시간~30일). AKI 입원은 회복까지 길어짐. 원내 사망이면 사망 시각. 퇴원이 자료 추출 종료 뒤인 입원은 만들지 않음 | K L3.1; P 2.3; P 3.6; P+AI 예측변수; Albu |
| `admissions.discharge_status` | 문자 | 퇴원 시 | 퇴원 시 | 없음 | 실측 0.0% (설계 0%) | 실측 died, home, transfer (설계 home, transfer, died) | 원내 사망 1% + ICU 3% + 중증 AKI 6%, 전원 12%, 나머지 자택. 이어진 입원의 앞 입원은 transfer | P 3.4; P 4.6; P+AI 결과; Albu |
| `admissions.unit` | 문자 | 입원 시 (처음 배정된 병동) | 입원 시 | 이후 이동은 transfers에 | 실측 0.0% (설계 0%) | 실측 ICU, ward (설계 ICU, ward) | 위험도에 따라 배정. ICU 입실 logit이 연구 기간 10년 동안 0.3 증가. 예약 입원은 낮음 | P 2.1; P 3.4; P+AI 결과 |

## admission_info

행 하나 = 입원 기록 하나. 키: `admission_id`.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `admission_info.admission_id` | 문자 | 입원 시 | 입원 시 | 없음 | 실측 0.0% (설계 0%) | 실측 A000001 ~ A007724 (고유값 7724개) (설계 admissions와 같음) | 모든 입원에 한 행 | 관리 |
| `admission_info.site` | 문자 | 입원 시 | 입원 시 | 없음 | 실측 0.0% (설계 0%) | 실측 A, B (설계 A, B) | 첫 입원과 예약 입원은 A. 응급 재입원이 B로 갈 확률은 직전 퇴원처가 자택이면 5%, 전원이면 40%. 이어진 입원은 절반이 병원을 바꿈. B 입원도 모든 테이블에 같은 구조로 기록 | K L3.3; P 1.1; P 3.4; P+AI 참여자·데이터 출처 |
| `admission_info.admission_type` | 문자 | 입원 시 | 입원 시 | 없음 | 실측 0.0% (설계 0%) | 실측 elective, emergency (설계 emergency, elective) | 예약(admission_bookings)대로 이루어진 입원이면 elective, 그 밖 emergency. 이어진 입원은 앞 입원과 같음 | P 1.2; P 2.3; P+AI 참여자·데이터 출처 |
| `admission_info.service` | 문자 | 입원 시 | 입원 시 | 없음 | 실측 0.0% (설계 0%) | 실측 medicine, surgery (설계 medicine, surgery) | 내과 70% / 외과 30%. 이어진 입원은 절반이 진료과를 바꿈 | P 2.1; P 3.4; P+AI 결과 |
| `admission_info.episode_id` | 문자 | 입원 시 | 입원 시 (이어지는 입원이면 이전 입원과 같은 값) | 없음 | 실측 0.0% (설계 0%) | 실측 E000001 ~ E007504 (고유값 7504개) (설계 E000001 형식) | 입원마다 새 값. 이어진 입원이 아니면서 살아서 퇴원한 입원의 3%(실측 3.0%, 220쌍)는 병원·진료과 이동으로 바로 이어진 입원(앞 입원 퇴원 0~60분 뒤, 같은 등록 번호)과 같은 값 (한 에피소드 최대 두 입원). 입원 기록으로 세면 두 건 모두 세므로 약 5.7%(440건)가 이런 에피소드에 속한다 | K L3.2; P 4.6; P+AI 분석; Albu |

## transfers

행 하나 = 입원 중 한 병동에 머문 구간. 키: `transfer_id`.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `transfers.transfer_id` | 문자 | 병동 입실 시 | 병동 입실 시 | 없음 | 실측 0.0% (설계 0%) | 실측 T000001 ~ T008981 (고유값 8981개) (설계 T000001 형식) | 일련번호 | 관리 |
| `transfers.admission_id` | 문자 | 병동 입실 시 | 병동 입실 시 | 없음 | 실측 0.0% (설계 0%) | 실측 A000001 ~ A007724 (고유값 7724개) (설계 admissions와 같음) | 입원마다 1개 이상 | 관리 |
| `transfers.unit` | 문자 | 병동 입실 시 | 병동 입실 시 | 없음 | 실측 0.0% (설계 0%) | 실측 ICU, ward (설계 ICU, ward) | 첫 구간은 admissions.unit. ICU 입원의 60%는 1~4일 뒤 병동으로 이동(남은 기간이 12시간 넘을 때). 병동 입원의 5%는 입원 기간의 20~70% 시점에 ICU로 이동. 한 입원 최대 두 구간 | K L3.3; P 1.2; P 2.1; P+AI 참여자·데이터 출처; Suissa |
| `transfers.in_time` | 시각 | 병동 입실 시 | 병동 입실 시 | 없음 | 실측 0.0% (설계 0%) | 실측 2150-01-01 13:29 ~ 2159-12-29 09:24 (설계 입원 기간 안) | 첫 구간은 admit_time | K L3.1; P 2.3; P+AI 예측변수; Albu |
| `transfers.out_time` | 시각 | 병동 퇴실 시 | 병동 퇴실 시 | 없음 | 실측 0.0% (설계 0%) | 실측 2150-01-03 16:07 ~ 2159-12-31 08:47 (설계 입원 기간 안) | 마지막 구간은 discharge_time | K L3.1; P 2.3; P+AI 예측변수; Albu |

## labs

행 하나 = 입원 중 검사 결과 하나. 키: `lab_id`.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `labs.lab_id` | 문자 | 채취 시 | 보고 시 | 없음 | 실측 0.0% (설계 0%) | 실측 L0000001 ~ L0116891 (고유값 116891개) (설계 L0000001 형식) | 일련번호 | 관리 |
| `labs.admission_id` | 문자 | 채취 시 | 보고 시 | 없음 | 실측 0.0% (설계 0%) | 실측 A000001 ~ A007724 (고유값 7724개) (설계 admissions와 같음) | 입원 중 채취 | 관리 |
| `labs.test` | 문자 | 채취 시 | 보고 시 | 없음 | 실측 0.0% (설계 0%) | 실측 bun, creatinine, hemoglobin, potassium (설계 creatinine, bun, potassium, hemoglobin) | 검사 묶음 | P 2.1; P+AI 예측변수 |
| `labs.value` | 실수 | 채취 시 (환자 상태) | report_time | 채취 뒤 30분~6시간 | 실측 0.0% (설계 0%) | 실측 0.46 ~ 105 (설계 검사별 생리적 범위) | 잠재 상태 + 측정 오차. 크레아티닌은 jaffe 측정이면 0.10 mg/dL 높음 | P 2.1; P 3.1; P+AI 예측변수 |
| `labs.unit` | 문자 | 정적 | 보고 시 | 없음 | 실측 0.0% (설계 0%) | 실측 g/dL, mg/dL, mmol/L (설계 mg/dL, mmol/L, g/dL) | 검사별 고정 | 관리 |
| `labs.method` | 문자 | 채취 시 | 보고 시 | 없음 | 실측 0.0% (설계 0%) | 실측 enzymatic, jaffe, standard (설계 크레아티닌: jaffe, enzymatic / 그 밖: standard) | 채취가 2155-01-01 전이면 jaffe, 그 뒤 enzymatic | P 2.1; P 3.4; P+AI 결과; Albu |
| `labs.collect_time` | 시각 | 채취 시 | 보고 시 (report_time) | 없음 | 실측 0.0% (설계 0%) | 실측 2150-01-01 14:00 ~ 2159-12-31 07:08 (설계 입원 기간 안) | 그 시각에 머문 병동(transfers) 기준. 입원 직후 1회. ICU는 하루 1~2회(6시·18시 무렵). 병동은 간격 40~72시간(연구 초)에서 30~60시간(연구 끝)으로 서서히 줄어듦. 야간(22~06시) 병동 채혈은 06~08시로 미룸, 주말 병동 채혈 30%는 건너뜀. 35%는 퇴원 직전 1회 | K L3.1; P 2.3; P+AI 예측변수; Albu |
| `labs.report_time` | 시각 | 보고 시 | 보고 시 | collect_time 뒤 30분~6시간. 퇴원·사망 뒤 보고 있음 | 실측 0.0% (설계 0% (종료까지 보고되지 않은 검사는 행이 없음)) | 실측 2150-01-01 15:18 ~ 2159-12-31 09:05 (설계 자료 추출 종료 이전) | 채취 시각 + 지연 (로그정규, 혈색소가 더 빠름) | K L3.1; P 2.3; P+AI 예측변수; Albu |

## vitals

행 하나 = 활력징후 관찰 하나. 키: `vital_id`.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `vitals.vital_id` | 문자 | 관찰 시 | 입력 시 | 없음 | 실측 0.0% (설계 0%) | 실측 V0000001 ~ V0667131 (고유값 667131개) (설계 V0000001 형식) | 일련번호 | 관리 |
| `vitals.admission_id` | 문자 | 관찰 시 | 입력 시 | 없음 | 실측 0.0% (설계 0%) | 실측 A000001 ~ A007724 (고유값 7724개) (설계 admissions와 같음) | 입원 중 관찰 | 관리 |
| `vitals.item` | 문자 | 관찰 시 | 입력 시 | 없음 | 실측 0.0% (설계 0%) | 실측 heart_rate, sbp, temperature (설계 heart_rate, sbp, temperature) | 관찰 묶음 | P 2.1; P+AI 예측변수 |
| `vitals.value` | 실수 | 관찰 시 | entered_time | 관찰 뒤 입력까지 지연 | 실측 0.0% (설계 0%) | 실측 35 ~ 183 (설계 항목별 생리적 범위) | 잠재 상태 + 측정 오차. 심박수 80 (+8 ICU, +15 패혈증, +8 AKI 무렵), 수축기 혈압 125 (−12 ICU, −15 패혈증, −10 AKI 무렵), 체온 36.8 (+1.0 패혈증 첫 72시간). AKI 무렵 = 발생부터 상승 끝 24시간 뒤까지 | P 2.1; P+AI 예측변수 |
| `vitals.charted_time` | 시각 | 관찰 시 (기록상 관찰 시각) | entered_time | 없음 | 실측 0.0% (설계 0%) | 실측 2150-01-01 14:19 ~ 2159-12-31 07:28 (설계 입원 기간 안) | 그 시각에 머문 병동 기준. ICU 1~2시간, 병동 4~8시간 간격. 야간(22~06시) 병동은 간격 ×1.5. 한 번에 세 항목 | K L3.1; P 2.3; P+AI 예측변수; Albu |
| `vitals.entered_time` | 시각 | 전산 입력 시 | 전산 입력 시 | charted_time 뒤 0~6시간 (병동이 더 김) | 실측 0.0% (설계 0% (종료 뒤 입력은 행이 없음)) | 실측 2150-01-01 15:54 ~ 2159-12-31 08:04 (설계 자료 추출 종료 이전) | 관찰 시각 + 지연. ICU 0~60분 균등, 병동 지수분포(평균 90분, 최대 6시간) | K L3.1; P 2.3; P+AI 예측변수; Albu |

## medications

행 하나 = 처방 하나. 키: `med_id`.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `medications.med_id` | 문자 | 처방 시 | 처방 시 | 없음 | 실측 0.0% (설계 0%) | 실측 M0000001 ~ M0032995 (고유값 32995개) (설계 M0000001 형식) | 일련번호 | 관리 |
| `medications.admission_id` | 문자 | 처방 시 | 처방 시 | 없음 | 실측 0.0% (설계 0%) | 실측 A000001 ~ A007724 (고유값 7614개) (설계 admissions와 같음) | 입원 중 처방 | 관리 |
| `medications.drug` | 문자 | 처방 시 | 처방 시 | 없음 | 실측 0.0% (설계 0%) | 실측 ace_inhibitor, acetaminophen, heparin, insulin, loop_diuretic, nsaid, piperacillin_tazobactam, proton_pump_inhibitor, statin, vancomycin (설계 loop_diuretic, ace_inhibitor, nsaid, vancomycin, piperacillin_tazobactam, proton_pump_inhibitor, insulin, heparin, statin, acetaminophen (10종)) | 병동·ICU별 기본 확률. 패혈증이면 항생제, 당뇨면 인슐린, 고혈압 코드면 ACE 억제제, 60세 이상이면 statin이 늘어남. 처방은 AKI 발생에 영향을 주지 않음. AKI 입원의 40%는 발생 6~48시간 뒤 이뇨제 처방이 더 있음 | K L2; P 2.3; P+AI 예측변수; Kaufman |
| `medications.med_type` | 문자 | 처방 시 | 처방 시 | 없음 | 실측 0.0% (설계 0%) | 실측 discharge, inpatient (설계 inpatient, discharge) | 입원 중 처방 / 퇴원약. 생존 퇴원의 60%가 퇴원약 1~4종(ace_inhibitor, statin, proton_pump_inhibitor, loop_diuretic, insulin, acetaminophen 중) | K L3.1; P 2.3; P+AI 예측변수; Kaufman |
| `medications.order_time` | 시각 | 처방 시 | 처방 시 | 없음 | 실측 0.0% (설계 0%) | 실측 2150-01-01 20:40 ~ 2159-12-30 07:40 (설계 입원 기간 안) | 입원 중 처방은 입원 기간 안, 퇴원약은 퇴원 1~6시간 전 | K L3.1; P 2.3; P+AI 예측변수; Albu |

## orders

행 하나 = 오더 하나. 키: `order_id`.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `orders.order_id` | 문자 | 오더 시 | 오더 시 | 없음 | 실측 0.0% (설계 0%) | 실측 O0000001 ~ O0011920 (고유값 11920개) (설계 O0000001 형식) | 일련번호 | 관리 |
| `orders.admission_id` | 문자 | 오더 시 | 오더 시 | 없음 | 실측 0.0% (설계 0%) | 실측 A000002 ~ A007724 (고유값 6234개) (설계 admissions와 같음) | 입원 중 오더 | 관리 |
| `orders.order_type` | 문자 | 오더 시 | 오더 시 | 없음 | 실측 0.0% (설계 0%) | 실측 chest_xray, ct_head, dialysis_order, dietitian_consult, echocardiogram, nephrology_consult, physical_therapy_consult, renal_ultrasound, social_work_consult (설계 chest_xray, ct_head, echocardiogram, renal_ultrasound, dialysis_order, nephrology_consult, dietitian_consult, physical_therapy_consult, social_work_consult) | 환자 상태에 따라. 신장 관련 오더는 AKI 무렵에 몰림 | K L2; P 3.3; P+AI 예측변수; Kaufman |
| `orders.order_time` | 시각 | 오더 시 | 오더 시 | 없음 | 실측 0.0% (설계 0%) | 실측 2150-01-02 11:13 ~ 2159-12-31 05:37 (설계 입원 기간 안) | 상태 변화 뒤 | K L3.1; P 2.3; P+AI 예측변수; Albu |

## diagnoses

행 하나 = 입원 하나의 진단 코드 하나. 키: (`admission_id`, `seq`).

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `diagnoses.admission_id` | 문자 | 코딩 시 | coded_time | 없음 | 실측 0.0% (설계 0%) | 실측 A000001 ~ A007724 (고유값 7711개) (설계 admissions와 같음) | 퇴원한 입원마다 | 관리 |
| `diagnoses.seq` | 정수 | 코딩 시 | coded_time | 없음 | 실측 0.0% (설계 0%) | 실측 1 ~ 7 (설계 1부터) | 입원 안 순서 | 관리 |
| `diagnoses.icd_code` | 문자 | 코딩 시 (입원 중 상태를 퇴원 뒤 요약) | coded_time | 퇴원 뒤 코딩 | 실측 0.0% (설계 0%) | 실측 038.9 ~ R53.83 (고유값 28개) (설계 ICD-9 또는 ICD-10 코드) | 입원 중 상태에서. 코드 14종(N17.9, N18.3, A41.9, I50.9, E87.5, I10, E11.9, D64.9, J18.9, N39.0, E87.1, K21.9, F32.9, R53.83; 아무것도 없으면 R53.83). E11.9는 당뇨인 사람(22%)의 90%, A41.9는 입원 중 패혈증의 90%. AKI(N17.9) 코드: 크레아티닌으로 KDIGO 기준을 만족한 입원은 입원 때 병동이 ICU면 0.9, 병동이면 0.75, 외과면 여기에 ×0.8. 만족하지 않은 잠재 AKI는 그 값의 약 절반, 그 밖 0.01 | K L2; P 2.3; P 3.1; P+AI 예측변수; Albu |
| `diagnoses.code_system` | 문자 | 코딩 시 | coded_time | 없음 | 실측 0.0% (설계 0%) | 실측 ICD10, ICD9 (설계 ICD9, ICD10) | coded_time이 2155-10-01 전이면 ICD9 (코드마다 ICD-9로 대응, 예 N17.9 → 584.9), 그 뒤 ICD10 | P 3.4; P+AI 결과; Albu |
| `diagnoses.present_on_admission` | 문자 | 코딩 시 | coded_time | 없음 | 실측 0.0% (설계 0%) | 실측 N, Y (설계 Y, N) | 만성 질환(N18.3, I10, E11.9, F32.9, K21.9, D64.9, R53.83)은 Y, N17.9는 N, 패혈증·폐렴·심부전·요로감염은 70%가 Y, 전해질 이상(E87.5, E87.1)은 40%가 Y | K L3.1; P 2.3; P+AI 예측변수; Albu; Kaufman |
| `diagnoses.coded_time` | 시각 | 코딩 완료 시 | 코딩 완료 시 | 퇴원 뒤 1~14일 (일부 더 늦음) | 실측 0.0% (설계 0% (추출 종료까지 코딩이 끝나지 않은 입원은 행이 없음)) | 실측 2150-01-09 07:57 ~ 2159-12-29 10:04 (설계 퇴원 뒤, 자료 추출 종료 이전) | 퇴원 시각 + 지연. 90%는 1~14일, 10%는 15~90일 (입원 하나의 진단은 모두 같은 시각) | K L3.1; P 2.3; P+AI 예측변수; Albu |

## procedures

행 하나 = 입원 하나의 시술 하나. 키: (`admission_id`, `code`, `chart_date`).

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `procedures.admission_id` | 문자 | 시술 시 | coded_time | 없음 | 실측 0.0% (설계 0%) | 실측 A000010 ~ A007722 (고유값 1550개) (설계 admissions와 같음) | 입원 중 시술 | 관리 |
| `procedures.code` | 문자 | 시술 시 | coded_time | 없음 | 실측 0.0% (설계 0%) | 실측 02HV33Z, 0BH17EZ, 30233N1, 5A1D70Z (설계 ICD-10-PCS 형식 코드) | 상태에 따라 (투석 처치는 AKI 무렵) | P 2.3; P+AI 예측변수 |
| `procedures.chart_date` | 날짜 | 시술한 날 | coded_time | 날짜만 있어 그날 중 언제인지 모름 | 실측 0.0% (설계 0%) | 실측 2150-01-08 ~ 2159-12-11 (설계 입원 기간 안) | 시술 시각의 날짜 | K L3.1; P 2.3; P+AI 예측변수; Albu |
| `procedures.coded_time` | 시각 | 코드 입력 시 | 코드 입력 시 | 시술 뒤. 대부분 퇴원 뒤 행정 코딩 단계에서 입력 | 실측 0.0% (설계 0% (추출 종료까지 입력되지 않은 시술은 행이 없음)) | 실측 2150-01-08 20:45 ~ 2159-12-19 14:16 (설계 자료 추출 종료 이전) | 20%는 시술 시각 + 0~12시간, 80%는 그 입원의 진단 coded_time과 같음 | K L3.1; P 2.3; P+AI 예측변수; Albu |

## problem_list

행 하나 = 문제 목록 항목의 한 버전. 키: (`entry_id`, `version`).

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `problem_list.entry_id` | 문자 | 항목 처음 기록 시 | 처음 기록 시 | 없음 | 실측 0.0% (설계 0%) | 실측 PL000001 ~ PL008787 (고유값 8787개) (설계 PL000001 형식) | 일련번호 | 관리 |
| `problem_list.patient_id` | 문자 | 처음 기록 시 | 처음 기록 시 | 없음 | 실측 0.0% (설계 0%) | 실측 P00002 ~ P05111 (고유값 4160개) (설계 patients와 같음) | 기록한 등록 번호 | 관리 |
| `problem_list.admission_id` | 문자 | 이 버전 기록 시 | recorded_time | 없음 | 실측 0.0% (설계 0%) | 실측 A000002 ~ A007721 (고유값 5437개) (설계 admissions와 같음) | 이 버전을 기록한 입원 | 관리 |
| `problem_list.version` | 정수 | 이 버전 기록 시 | recorded_time | 없음 | 실측 0.0% (설계 0%) | 실측 1 ~ 4 (설계 1부터) | 수정할 때마다 1 증가. 오류 표시 3%, 코드 변경 5%, resolved 15% | K L3.1; P 2.3; P+AI 예측변수; Albu |
| `problem_list.icd_code` | 문자 | 이 버전 기록 시 | recorded_time | 버전마다 다를 수 있음 | 실측 0.0% (설계 0%) | 실측 A41.51 ~ N18.4 (고유값 18개) (설계 ICD-10 코드) | 입원 중 상태. 만성 문제(N18.3, I10, E11.9, F32.9, K21.9)는 등록 번호마다 처음 나타난 입원에 한 번 기록하고, 뒤 입원의 10%에서 그 입원 id로 코드가 바뀐 새 버전. 급성 문제(A41.9, J18.9, I50.9)는 입원마다 입원 0~48시간에, N17.9는 크레아티닌 KDIGO 기준을 만족한 검사의 보고 0~24시간 뒤에 기록 (퇴원 전인 것만). 코드 변경 예: N17.9 → N17.0 | K L3.1; P 2.3; P+AI 예측변수; Albu |
| `problem_list.status` | 문자 | 이 버전 기록 시 | recorded_time | 없음 | 실측 0.0% (설계 0%) | 실측 active, entered_in_error, resolved (설계 active, resolved, entered_in_error) | 수정 버전에서 바뀜 | K L3.1; P 2.3; P+AI 예측변수; Albu |
| `problem_list.recorded_time` | 시각 | 이 버전 기록 시 | 이 버전 기록 시 | 첫 버전은 입원 중, 수정 버전은 입원 중 또는 퇴원 뒤 | 실측 0.0% (설계 0% (종료 뒤 수정은 행이 없음)) | 실측 2150-01-01 14:39 ~ 2159-12-29 00:49 (설계 자료 추출 종료 이전) | 첫 기록 + 수정 간격 (코드 변경 1시간~30일, 오류 표시 1~72시간, resolved는 퇴원 30일 뒤까지). 퇴원 뒤 수정도 admission_id는 그 항목을 기록한 입원 | K L3.1; P 2.3; P+AI 예측변수; Albu |

## outpatient_visits

행 하나 = 외래 방문 하나. 키: `visit_id`.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `outpatient_visits.visit_id` | 문자 | 방문 시 | 방문 시 | 없음 | 실측 0.0% (설계 0%) | 실측 OV000001 ~ OV010166 (고유값 10166개) (설계 OV000001 형식) | 일련번호 | 관리 |
| `outpatient_visits.patient_id` | 문자 | 방문 시 | 방문 시 | 없음 | 실측 0.0% (설계 0%) | 실측 P00001 ~ P05111 (고유값 4360개) (설계 patients와 같음) | 방문한 등록 번호 | 관리 |
| `outpatient_visits.visit_time` | 시각 | 방문 시 | 방문 시 | 없음 | 실측 0.0% (설계 0%) | 실측 2150-01-14 02:12 ~ 2159-12-31 19:48 (설계 사망·자료 추출 종료 이전) | 추적 외래: 생존 퇴원 뒤 5~28일, 자택 퇴원 70%, 전원 퇴원 35% (그 전에 재입원·사망하면 열리지 않음). 정기 외래: 첫 입원 뒤부터 다음 입원·사망·종료 전까지 1년 평균 0.25회. 첫 입원 전 외래는 없음 | K L3.3; P 1.2; P 3.6; P+AI 참여자·데이터 출처; Suissa |
| `outpatient_visits.site` | 문자 | 방문 시 | 방문 시 | 없음 | 실측 0.0% (설계 0%) | 실측 A, B (설계 A, B) | 외래 방문의 10%가 B (정기·추적 모두) | K L3.3; P 3.1; P 3.4; P+AI 결과; Albu |
| `outpatient_visits.visit_type` | 문자 | 방문 시 | 방문 시 | 없음 | 실측 0.0% (설계 0%) | 실측 follow_up, routine (설계 follow_up, routine) | 퇴원 뒤 추적 / 정기 | P 3.4; P+AI 결과; Albu |

## outpatient_labs

행 하나 = 외래 검사 결과 하나. 키: `lab_id`.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `outpatient_labs.lab_id` | 문자 | 채취 시 | 보고 시 | 없음 | 실측 0.0% (설계 0%) | 실측 OL000001 ~ OL012325 (고유값 12325개) (설계 OL000001 형식) | 일련번호 | 관리 |
| `outpatient_labs.patient_id` | 문자 | 채취 시 | 보고 시 | 없음 | 실측 0.0% (설계 0%) | 실측 P00002 ~ P05111 (고유값 3172개) (설계 patients와 같음) | 외래 방문한 등록 번호 | 관리 |
| `outpatient_labs.visit_id` | 문자 | 채취 시 | 보고 시 | 없음 | 실측 0.0% (설계 0%) | 실측 OV000004 ~ OV010162 (고유값 5145개) (설계 outpatient_visits와 같음) | 외래 방문의 50%에서 채취 | 관리 |
| `outpatient_labs.test` | 문자 | 채취 시 | 보고 시 | 없음 | 실측 0.0% (설계 0%) | 실측 creatinine, hemoglobin, potassium (설계 creatinine, potassium, hemoglobin) | 채취한 방문에서 크레아티닌 100%, 칼륨 80%, 혈색소 60% | P 2.1; P+AI 예측변수 |
| `outpatient_labs.value` | 실수 | 채취 시 | report_time | 채취 뒤 수 시간~1일 | 실측 0.0% (설계 0%) | 실측 0.5 ~ 17.1 (설계 검사별 생리적 범위) | 평소 상태 + 측정 오차 (크레아티닌은 기저치, jaffe면 +0.10 mg/dL) | P 2.1; P 3.1; P+AI 결과 |
| `outpatient_labs.unit` | 문자 | 정적 | 보고 시 | 없음 | 실측 0.0% (설계 0%) | 실측 g/dL, mg/dL, mmol/L (설계 mg/dL, mmol/L, g/dL) | 검사별 고정 | 관리 |
| `outpatient_labs.method` | 문자 | 채취 시 | 보고 시 | 없음 | 실측 0.0% (설계 0%) | 실측 enzymatic, jaffe, standard (설계 labs.method와 같음) | 입원 검사와 같은 시기에 같은 전환 | P 2.1; P 3.4; P+AI 결과; Albu |
| `outpatient_labs.collect_time` | 시각 | 채취 시 | 보고 시 | 없음 | 실측 0.0% (설계 0%) | 실측 2150-01-19 09:24 ~ 2159-12-31 08:06 (설계 방문 시각) | 방문 시각 | K L3.1; P 2.3; P+AI 예측변수; Albu |
| `outpatient_labs.report_time` | 시각 | 보고 시 | 보고 시 | collect_time 뒤 수 시간~1일 | 실측 0.0% (설계 0% (종료까지 보고되지 않은 검사는 행이 없음)) | 실측 2150-01-20 01:41 ~ 2159-12-31 22:07 (설계 자료 추출 종료 이전) | 채취 시각 + 2~24시간 | K L3.1; P 2.3; P+AI 예측변수; Albu |

## admission_bookings

행 하나 = 입원 예약 하나. 키: `booking_id`.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `admission_bookings.booking_id` | 문자 | 예약 시 | 예약 시 | 없음 | 실측 0.0% (설계 0%) | 실측 B000001 ~ B000764 (고유값 764개) (설계 B000001 형식) | 일련번호 | 관리 |
| `admission_bookings.patient_id` | 문자 | 예약 시 | 예약 시 | 없음 | 실측 0.0% (설계 0%) | 실측 P00018 ~ P05105 (고유값 670개) (설계 patients와 같음) | 예약한 등록 번호 | 관리 |
| `admission_bookings.source_admission_id` | 문자 | 예약 시 | 예약 시 | 없음 | 실측 23.4% (설계 일부 (외래에서 예약)) | 실측 A000026 ~ A007714 (고유값 585개) (설계 admissions와 같음) | 입원 중 예약이면 그 입원. 생존 퇴원의 8%가 퇴원 1~24시간 전에 예약, 외래 방문의 3%가 방문 시각에 예약 | K L2; P 3.3; P+AI 결과 |
| `admission_bookings.booked_time` | 시각 | 예약 시 | 예약 시 | 없음 | 실측 0.0% (설계 0%) | 실측 2150-01-25 11:19 ~ 2159-12-23 11:53 (설계 사망·자료 추출 종료 이전) | 입원 중(퇴원 1~24시간 전) 또는 외래 방문 시각 | K L3.1; P 2.3; P+AI 예측변수 |
| `admission_bookings.planned_date` | 날짜 | 예약 시 | 예약 시 | 날짜만. 앞으로의 예정이라 자료 추출 종료 뒤일 수 있음 | 실측 0.0% (설계 0%) | 실측 2150-03-19 ~ 2160-02-14 (설계 booked_time 뒤 (자료 추출 종료 뒤 가능)) | 예약 시각 + 7~60일. 예정일 08~12시에 입원 | K L2; P 3.1; P+AI 결과 |
| `admission_bookings.admission_id` | 문자 | 예약 입원 시 | 예약 입원 시 | 없음 | 실측 25.1% (설계 일부 (예약했지만 입원하지 않음, 또는 아직 입원 전)) | 실측 A000027 ~ A007715 (고유값 572개) (설계 admissions와 같음) | 예약의 85%가 예정일에 입원 (elective). 그 전에 다른 입원·사망이 오거나 입원이 종료 뒤면 비어 있음 | K L2; P 3.1; P+AI 결과 |

## deaths

행 하나 = 사망 한 건. 키: `patient_id`. 사망 연계가 반영된 사망만 있다.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `deaths.patient_id` | 문자 | 사망 시 | death_recorded_time | 없음 | 실측 0.0% (설계 0%) | 실측 P00009 ~ P05107 (고유값 496개) (설계 patients와 같음) | 사망한 사람의 등록 번호 | 관리 |
| `deaths.death_time` | 시각 | 사망 시 | death_recorded_time | 원외 사망은 기록이 늦음 | 실측 0.0% (설계 0%) | 실측 2150-04-07 06:07 ~ 2159-10-29 05:11 (설계 자료 추출 종료 이전) | 원내 사망: discharge_time과 같음. 원외 사망: 생존 퇴원마다 1년 안 사망 확률(위험 z·나이·AKI·ICU에 따라, 평균 약 5~8%), 시점은 퇴원 1~365일 뒤 균등 | P 3.6; P 4.6; P+AI 분석; Suissa |
| `deaths.place` | 문자 | 사망 시 | death_recorded_time | 없음 | 실측 0.0% (설계 0%) | 실측 in_hospital, out_of_hospital (설계 in_hospital, out_of_hospital) | 원내 / 원외 | P 3.4; P 4.6; P+AI 결과; Albu |
| `deaths.death_recorded_time` | 시각 | 사망 기록 시 | 사망 기록 시 | 원내: 사망 즉시 (사망 시각과 같음). 원외: 사망 연계로 수 주~수 개월 뒤 | 실측 0.0% (설계 0%) | 실측 2150-04-07 06:07 ~ 2159-10-29 05:11 (설계 death_linkage_through 이전 (원외)) | 원내: 사망 시각. 원외: 사망 시각 + 14~180일. 기록 날짜가 death_linkage_through 뒤인 원외 사망은 행이 없음 | K L3.1; P 2.3; P+AI 예측변수; Albu |
| `deaths.source` | 문자 | 사망 기록 시 | 사망 기록 시 | 없음 | 실측 0.0% (설계 0%) | 실측 hospital_record, registry_link (설계 hospital_record, registry_link) | 원내 / 사망 연계 | P 3.1; P 3.4; P+AI 결과; Albu |

## 파생 열

데이터 파일에는 없지만 설계서가 열 이름으로 쓸 수 있는 값.

| 열 | 자료형 | 값이 생기는 때 | 값이 알려지는 때 | 지연·불확실성 | 결측 | 값의 범위 | 생성 방식 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `admissions.length_of_stay_h` | 실수 | 퇴원 시 | 퇴원 시 (discharge_time) | 없음 | 0% | 0 이상 | 계산식: (discharge_time − admit_time) 시간 | K L3.1; P 1.2; P 2.3; P+AI 참여자·데이터 출처; Suissa |
| `index_row.landmark_row_id` | 문자 | 설계가 예측 행을 만들 때 | 예측 행을 만들 때 | 없음 | 0% | 예측 행마다 하나 | 계산식: 동적 설계 (admission_id, 랜드마크 간격) 한 쌍 / 고정 설계 admission_id | K L3.2; P 4.6; P+AI 분석 |

## 보조 데이터 (`data/synth_aux/`)

본 데이터와 **같은 테이블·같은 열**을 쓰고, 열마다 위 설명이 그대로 적용된다. 다른 점만 적는다.

- 규모: 환자 200명, 1인당 입원 1회. 그래서 재입원·이어진 입원·새 등록 번호·입원 예약이 없다 (`admission_bookings`는 열만 있고 행이 없다).
- tₚ = 입원 24시간.
- `labs.test`: 검사 500종 (`t001`~`t500`) + creatinine (bun, potassium, hemoglobin은 없다). 대부분 결과와 무관한 잡음이고 10종만 약한 신호 (잠재 AKI 입원에서 0.3 SD 이동). 항목마다 tₚ 이전(입원 24시간 안) 측정 1~3회. 값은 항목마다 평균·척도가 다른 연속값.
- `labs.unit`: t001~t500은 `AU`(임의 단위), creatinine은 mg/dL. `labs.method`: t001~t500은 standard.
- 크레아티닌은 본 데이터와 같은 일정으로 입원 내내 측정한다. 결과(크레아티닌 KDIGO AKI) 유병률 약 30% (설계값).
- 다른 테이블은 본 데이터와 같은 규칙으로 만들되 규모에 맞게 줄인다.

### 보조 데이터 실측값

`data/synth_aux/`에서 계산. 열마다 결측과 값의 범위.

| 열 | 결측 | 값의 범위 |
|---|---|---|
| `extract_info.extraction_end_time` | 0.0% | 2160-01-01 00:00 ~ 2160-01-01 00:00 |
| `extract_info.sites_covered` | 0.0% | A;B |
| `extract_info.death_linkage_through` | 0.0% | 2159-07-01 ~ 2159-07-01 |
| `patients.patient_id` | 0.0% | P00001 ~ P00200 (고유값 200개) |
| `patients.family_id` | 76.5% | F0001 ~ F0019 (고유값 19개) |
| `patients.age` | 0.0% | 27 ~ 95 |
| `patients.sex` | 0.0% | F, M |
| `person_links.patient_id` | 0.0% | P00001 ~ P00200 (고유값 200개) |
| `person_links.person_id` | 0.0% | H00001 ~ H00200 (고유값 200개) |
| `admissions.admission_id` | 0.0% | A000001 ~ A000200 (고유값 200개) |
| `admissions.patient_id` | 0.0% | P00001 ~ P00200 (고유값 200개) |
| `admissions.admit_time` | 0.0% | 2150-01-18 05:31 ~ 2159-11-18 10:41 |
| `admissions.discharge_time` | 0.0% | 2150-01-20 17:05 ~ 2159-11-27 03:22 |
| `admissions.discharge_status` | 0.0% | died, home, transfer |
| `admissions.unit` | 0.0% | ICU, ward |
| `admission_info.admission_id` | 0.0% | A000001 ~ A000200 (고유값 200개) |
| `admission_info.site` | 0.0% | A |
| `admission_info.admission_type` | 0.0% | emergency |
| `admission_info.service` | 0.0% | medicine, surgery |
| `admission_info.episode_id` | 0.0% | E000001 ~ E000200 (고유값 200개) |
| `transfers.transfer_id` | 0.0% | T000001 ~ T000238 (고유값 238개) |
| `transfers.admission_id` | 0.0% | A000001 ~ A000200 (고유값 200개) |
| `transfers.unit` | 0.0% | ICU, ward |
| `transfers.in_time` | 0.0% | 2150-01-18 05:31 ~ 2159-11-18 10:41 |
| `transfers.out_time` | 0.0% | 2150-01-19 14:24 ~ 2159-11-27 03:22 |
| `labs.lab_id` | 0.0% | L0000001 ~ L0200557 (고유값 200557개) |
| `labs.admission_id` | 0.0% | A000001 ~ A000200 (고유값 200개) |
| `labs.test` | 0.0% | creatinine ~ t500 (고유값 501개) |
| `labs.value` | 0.0% | -11.523 ~ 14.005 |
| `labs.unit` | 0.0% | AU, mg/dL |
| `labs.method` | 0.0% | enzymatic, jaffe, standard |
| `labs.collect_time` | 0.0% | 2150-01-18 05:46 ~ 2159-11-26 18:10 |
| `labs.report_time` | 0.0% | 2150-01-18 06:42 ~ 2159-11-26 19:17 |
| `vitals.vital_id` | 0.0% | V0000001 ~ V0021345 (고유값 21345개) |
| `vitals.admission_id` | 0.0% | A000001 ~ A000200 (고유값 200개) |
| `vitals.item` | 0.0% | heart_rate, sbp, temperature |
| `vitals.value` | 0.0% | 35.6 ~ 169 |
| `vitals.charted_time` | 0.0% | 2150-01-18 08:32 ~ 2159-11-27 03:20 |
| `vitals.entered_time` | 0.0% | 2150-01-18 08:47 ~ 2159-11-27 03:59 |
| `medications.med_id` | 0.0% | M0000001 ~ M0000898 (고유값 898개) |
| `medications.admission_id` | 0.0% | A000001 ~ A000200 (고유값 198개) |
| `medications.drug` | 0.0% | ace_inhibitor, acetaminophen, heparin, insulin, loop_diuretic, nsaid, piperacillin_tazobactam, proton_pump_inhibitor, statin, vancomycin |
| `medications.med_type` | 0.0% | discharge, inpatient |
| `medications.order_time` | 0.0% | 2150-01-18 14:39 ~ 2159-11-27 02:19 |
| `orders.order_id` | 0.0% | O0000001 ~ O0000351 (고유값 351개) |
| `orders.admission_id` | 0.0% | A000003 ~ A000200 (고유값 169개) |
| `orders.order_type` | 0.0% | chest_xray, ct_head, dialysis_order, dietitian_consult, echocardiogram, nephrology_consult, physical_therapy_consult, renal_ultrasound, social_work_consult |
| `orders.order_time` | 0.0% | 2150-01-19 04:48 ~ 2159-11-26 07:32 |
| `diagnoses.admission_id` | 0.0% | A000001 ~ A000200 (고유값 200개) |
| `diagnoses.seq` | 0.0% | 1 ~ 6 |
| `diagnoses.icd_code` | 0.0% | 038.9 ~ R53.83 (고유값 26개) |
| `diagnoses.code_system` | 0.0% | ICD10, ICD9 |
| `diagnoses.present_on_admission` | 0.0% | N, Y |
| `diagnoses.coded_time` | 0.0% | 2150-01-31 22:14 ~ 2159-12-06 07:18 |
| `procedures.admission_id` | 0.0% | A000004 ~ A000194 (고유값 48개) |
| `procedures.code` | 0.0% | 02HV33Z, 0BH17EZ, 30233N1, 5A1D70Z |
| `procedures.chart_date` | 0.0% | 2150-02-10 ~ 2159-11-19 |
| `procedures.coded_time` | 0.0% | 2150-02-24 18:01 ~ 2159-12-06 07:18 |
| `problem_list.entry_id` | 0.0% | PL000001 ~ PL000287 (고유값 287개) |
| `problem_list.patient_id` | 0.0% | P00001 ~ P00199 (고유값 160개) |
| `problem_list.admission_id` | 0.0% | A000001 ~ A000199 (고유값 160개) |
| `problem_list.version` | 0.0% | 1 ~ 3 |
| `problem_list.icd_code` | 0.0% | A41.51 ~ N18.4 (고유값 16개) |
| `problem_list.status` | 0.0% | active, entered_in_error, resolved |
| `problem_list.recorded_time` | 0.0% | 2150-01-18 10:05 ~ 2159-10-03 02:54 |
| `outpatient_visits.visit_id` | 0.0% | OV000001 ~ OV000334 (고유값 334개) |
| `outpatient_visits.patient_id` | 0.0% | P00002 ~ P00200 (고유값 166개) |
| `outpatient_visits.visit_time` | 0.0% | 2150-02-11 04:29 ~ 2159-12-22 16:18 |
| `outpatient_visits.site` | 0.0% | A, B |
| `outpatient_visits.visit_type` | 0.0% | follow_up, routine |
| `outpatient_labs.lab_id` | 0.0% | OL000001 ~ OL000425 (고유값 425개) |
| `outpatient_labs.patient_id` | 0.0% | P00003 ~ P00200 (고유값 119개) |
| `outpatient_labs.visit_id` | 0.0% | OV000003 ~ OV000333 (고유값 177개) |
| `outpatient_labs.test` | 0.0% | creatinine, hemoglobin, potassium |
| `outpatient_labs.value` | 0.0% | 0.51 ~ 15.7 |
| `outpatient_labs.unit` | 0.0% | g/dL, mg/dL, mmol/L |
| `outpatient_labs.method` | 0.0% | enzymatic, jaffe, standard |
| `outpatient_labs.collect_time` | 0.0% | 2150-07-16 05:39 ~ 2159-12-22 16:18 |
| `outpatient_labs.report_time` | 0.0% | 2150-07-16 11:36 ~ 2159-12-23 03:49 |
| `admission_bookings.booking_id` | 행 없음 | 값 없음 |
| `admission_bookings.patient_id` | 행 없음 | 값 없음 |
| `admission_bookings.source_admission_id` | 행 없음 | 값 없음 |
| `admission_bookings.booked_time` | 행 없음 | 값 없음 |
| `admission_bookings.planned_date` | 행 없음 | 값 없음 |
| `admission_bookings.admission_id` | 행 없음 | 값 없음 |
| `deaths.patient_id` | 0.0% | P00016 ~ P00199 (고유값 26개) |
| `deaths.death_time` | 0.0% | 2150-10-18 23:34 ~ 2159-02-11 18:01 |
| `deaths.place` | 0.0% | in_hospital, out_of_hospital |
| `deaths.death_recorded_time` | 0.0% | 2150-12-24 17:12 ~ 2159-03-13 22:30 |
| `deaths.source` | 0.0% | hospital_record, registry_link |
