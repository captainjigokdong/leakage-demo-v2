# 규칙표 (점검기와 같은 내용)

규칙표 판 2. 점검기의 규칙표에서 자동으로 만든 사본이다. 이 표와 점검기 출력의 `rule` 칸 번호가 같다.

규칙은 "값이 언제 알려지는가"만 말한다. 쓸 수 있는지는 설계의 예측 시점 tₚ가 정한다.

- 1층 구조: 데이터의 열이 곧 확인 가능 시각이다
- 2층 맥락: 데이터 밖의 지식 (데이터 설명서에 적힌 지연 상한, 확인 강도를 좌우하는 층)
- 3층 불확실: 아무도 확실히 모른다. 보수적 기본값을 쓰고 "가정"으로 따로 출력한다

## 1. 테이블별 확인 가능 시각 (`T.<테이블>.<열>`)

열 규칙이 행 규칙과 같으면 "행과 같음"으로 적는다. 행 규칙은 개수 집계처럼 열을 정하지 않을 때 쓴다.

### extract_info

연결: 전역 1행. 시각 열 `extraction_end_time`(시각), `death_linkage_through`(날짜만)

- 행 (`T.extract_info`): 자료 추출 시 (모든 tₚ 뒤) — 1층, 설명서: 자료 추출 시 알려진다 (모든 tₚ 뒤)
- `extraction_end_time`: 행과 같음
- `sites_covered`: 행과 같음
- `death_linkage_through`: 행과 같음

### patients

연결: 등록 번호로.

- 행 (`T.patients`): 그 등록 번호의 첫 입원 시각 — 1층, 설명서: 그 등록 번호의 첫 입원 시 알려진다
- `patient_id`: 행과 같음
- `family_id`: 행과 같음
- `age`: 행과 같음
- `sex`: 행과 같음

### person_links

연결: 등록 번호로.

- 행 (`T.person_links`): 그 등록 번호의 첫 입원 시각 — 1층, 설명서: 그 등록 번호의 첫 입원 시 알려진다
- `patient_id`: 행과 같음
- `person_id` (`T.person_links.person_id`): 자료 추출 시 (모든 tₚ 뒤) — 1층, 설명서: 등록 번호 연결은 자료 추출 때 한 번에 한다 (모든 tₚ 뒤)

### admissions

연결: 등록 번호로. 입원 범위 열 `admission_id`; 시각 열 `admit_time`(시각), `discharge_time`(시각)

- 행 (`T.admissions`): 입원 시각 — 1층, 설명서: 입원 시 알려진다
- `admission_id`: 행과 같음
- `patient_id`: 행과 같음
- `admit_time`: 행과 같음
- `unit`: 행과 같음
- `discharge_time` (`T.admissions.discharge_time`): 퇴원 시각 — 1층, 설명서: 퇴원 시 알려진다 (discharge_time)
- `discharge_status` (`T.admissions.discharge_status`): 퇴원 시각 — 1층, 설명서: 퇴원 시 알려진다 (discharge_time)
- `length_of_stay_h` (`T.admissions.length_of_stay_h`): 퇴원 시각 — 1층, 설명서: 퇴원 시 알려진다 (discharge_time)
- `length_of_stay_h`는 계산한 열: (discharge_time - admit_time) 시간

### admission_info

연결: 입원 번호로. 입원 범위 열 `admission_id`

- 행 (`T.admission_info`): 입원 시각 — 1층, 설명서: 입원 시 알려진다
- `admission_id`: 행과 같음
- `site`: 행과 같음
- `admission_type`: 행과 같음
- `service`: 행과 같음
- `episode_id`: 행과 같음

### transfers

연결: 입원 번호로. 입원 범위 열 `admission_id`; 시각 열 `in_time`(시각), `out_time`(시각)

- 행 (`T.transfers`): `in_time` — 1층, 설명서: 병동 입실 시각(in_time)에 알려진다
- `transfer_id`: 행과 같음
- `admission_id`: 행과 같음
- `unit`: 행과 같음
- `in_time`: 행과 같음
- `out_time` (`T.transfers.out_time`): `out_time` (`in_time`에서 지연 상한 없음) — 1층, 설명서: 병동 퇴실 시각(out_time)에 알려진다

### labs

연결: 입원 번호로. 입원 범위 열 `admission_id`; 퇴원 뒤 최대 6h에 알려짐; 시각 열 `collect_time`(시각), `report_time`(시각)

- 행 (`T.labs`): `report_time` (`collect_time`에서 지연 상한 6h) — 1층, 설명서: 검사 값은 보고 시각(report_time)에 알려진다. 채취→보고 지연 상한 6h
- `lab_id`: 행과 같음
- `admission_id`: 행과 같음
- `test`: 행과 같음
- `value`: 행과 같음
- `unit`: 행과 같음
- `method`: 행과 같음
- `collect_time`: 행과 같음
- `report_time`: 행과 같음

### vitals

연결: 입원 번호로. 입원 범위 열 `admission_id`; 퇴원 뒤 최대 6h에 알려짐; 시각 열 `charted_time`(시각), `entered_time`(시각)

- 행 (`T.vitals`): `entered_time` (`charted_time`에서 지연 상한 6h) — 1층, 설명서: 활력징후는 전산 입력 시각(entered_time)에 알려진다. 관찰→입력 지연 상한 6h
- `vital_id`: 행과 같음
- `admission_id`: 행과 같음
- `item`: 행과 같음
- `value`: 행과 같음
- `charted_time`: 행과 같음
- `entered_time`: 행과 같음

### medications

연결: 입원 번호로. 입원 범위 열 `admission_id`; 시각 열 `order_time`(시각)

- 행 (`T.medications`): `order_time` — 1층, 설명서: 처방 시각(order_time)에 알려진다
- `med_id`: 행과 같음
- `admission_id`: 행과 같음
- `drug`: 행과 같음
- `med_type`: 행과 같음
- `order_time`: 행과 같음

### orders

연결: 입원 번호로. 입원 범위 열 `admission_id`; 시각 열 `order_time`(시각)

- 행 (`T.orders`): `order_time` — 1층, 설명서: 오더 시각(order_time)에 알려진다
- `order_id`: 행과 같음
- `admission_id`: 행과 같음
- `order_type`: 행과 같음
- `order_time`: 행과 같음

### diagnoses

연결: 입원 번호로. 입원 범위 열 `admission_id`; 퇴원 뒤 최대 2160h에 알려짐; 시각 열 `coded_time`(시각)

- 행 (`T.diagnoses`): `coded_time` — 1층, 설명서: 진단 코드는 코딩 완료 시각(coded_time)에 알려진다. 퇴원 뒤 최대 90일
- `admission_id`: 행과 같음
- `seq`: 행과 같음
- `icd_code`: 행과 같음
- `code_system`: 행과 같음
- `present_on_admission`: 행과 같음
- `coded_time`: 행과 같음

### procedures

연결: 입원 번호로. 입원 범위 열 `admission_id`; 퇴원 뒤 최대 2160h에 알려짐; 시각 열 `chart_date`(날짜만), `coded_time`(시각)

- 행 (`T.procedures`): `coded_time` (`chart_date`에서 지연 상한 없음) — 1층, 설명서: 시술 코드는 코드 입력 시각(coded_time)에 알려진다. 시술 날짜(chart_date)에서 입력까지 지연 상한 없음, 퇴원 뒤 최대 90일
- `admission_id`: 행과 같음
- `code`: 행과 같음
- `chart_date`: 행과 같음
- `coded_time`: 행과 같음

### problem_list

연결: 등록 번호로. 입원 범위 열 `admission_id`; 퇴원 뒤 최대 720h에 알려짐; 수정 이력: 항목 `entry_id`, 버전 `version` (as_of로 고름); 시각 열 `recorded_time`(시각)

- 행 (`T.problem_list`): `recorded_time` — 1층, 설명서: 문제 목록은 버전마다 기록 시각(recorded_time)에 알려진다
- `entry_id`: 행과 같음
- `patient_id`: 행과 같음
- `admission_id`: 행과 같음
- `version`: 행과 같음
- `icd_code`: 행과 같음
- `status`: 행과 같음
- `recorded_time`: 행과 같음

### outpatient_visits

연결: 등록 번호로. 시각 열 `visit_time`(시각)

- 행 (`T.outpatient_visits`): `visit_time` — 1층, 설명서: 방문 시각(visit_time)에 알려진다
- `visit_id`: 행과 같음
- `patient_id`: 행과 같음
- `visit_time`: 행과 같음
- `site`: 행과 같음
- `visit_type`: 행과 같음

### outpatient_labs

연결: 등록 번호로. 시각 열 `collect_time`(시각), `report_time`(시각)

- 행 (`T.outpatient_labs`): `report_time` (`collect_time`에서 지연 상한 24h) — 1층, 설명서: 외래 검사 값은 보고 시각(report_time)에 알려진다. 채취→보고 지연 상한 24h
- `lab_id`: 행과 같음
- `patient_id`: 행과 같음
- `visit_id`: 행과 같음
- `test`: 행과 같음
- `value`: 행과 같음
- `unit`: 행과 같음
- `method`: 행과 같음
- `collect_time`: 행과 같음
- `report_time`: 행과 같음

### admission_bookings

연결: 등록 번호로. 입원 범위 열 `source_admission_id`; 시각 열 `booked_time`(시각), `planned_date`(날짜만)

- 행 (`T.admission_bookings`): `booked_time` — 1층, 설명서: 예약 시각(booked_time)에 알려진다
- `booking_id`: 행과 같음
- `patient_id`: 행과 같음
- `source_admission_id`: 행과 같음
- `booked_time`: 행과 같음
- `planned_date`: 행과 같음
- `admission_id` (`T.admission_bookings.admission_id`): 가리키는 입원의 입원 시각 — 1층, 설명서: 예약 입원이 이루어질 때(그 입원의 입원 시각) 채워진다

### deaths

연결: 등록 번호로. 시각 열 `death_time`(시각), `death_recorded_time`(시각)

- 행 (`T.deaths`): `death_recorded_time` (`death_time`에서 지연 상한 4320h) — 1층, 설명서: 사망은 사망 기록 시각(death_recorded_time)에 알려진다. 원외 사망은 사망 뒤 최대 180일
- `patient_id`: 행과 같음
- `death_time`: 행과 같음
- `place`: 행과 같음
- `death_recorded_time`: 행과 같음
- `source`: 행과 같음

## 2. 조정할 수 있는 값 (2층, 데이터 설명서의 값)

- `LAB_REPORT_LAG_MAX_H` = 6h
- `VITAL_ENTRY_LAG_MAX_H` = 6h
- `OUTPATIENT_LAB_LAG_MAX_H` = 24h
- `DX_CODING_MAX_AFTER_DISCHARGE_H` = 2160h
- `PROC_CODING_MAX_AFTER_DISCHARGE_H` = 2160h
- `PROBLEM_MAX_AFTER_DISCHARGE_H` = 720h
- `DEATH_RECORD_LAG_MAX_H` = 4320h
- `EPISODE_GAP_MAX_H` = 1h
- `Q7_RATIO_THRESHOLD` = 2 (층 사이 비가 이 값 이상이면 Q7 경고. 실험 전 고정값)
- `DATE_ONLY_DEFAULT` = day_end (3층: 날짜만 있는 값의 그날 시각)

## 3. 분할 (Q2)

- 위계: index_row < admission < episode < patient < person < family
- 열 이름 → 수준: `index_row` → index_row, `index_id` → index_row, `row` → index_row, `row_id` → index_row, `landmark_row_id` → index_row, `admission` → admission, `admission_id` → admission, `episode` → episode, `episode_id` → episode, `patient` → patient, `patient_id` → patient, `person` → person, `person_id` → person, `family` → family, `family_id` → family
- 개체 단위: person (설명서 person_links: 일부 사람은 등록 번호(patient_id)가 둘이다. 같은 사람은 person_id로 묶인다)
- 형식의 기본 독립 단위: patient
- 결측이 있는 묶음: family (결측 행은 fallback_key로, 없으면 등록 번호로 묶인다)
- 행 단위 분할 방법: random_rows
- 시간 순 분할(temporal): 묶음(key, 결측이면 fallback_key)째로 움직인다. 묶음의 모든 행이 cutoff 이전(≤)이면 학습. cutoff 뒤의 행이 하나라도 있는 묶음은 학습에 넣지 않고, 그 묶음의 cutoff + gap 뒤 행만 평가에 넣는다. 나머지 행(학습에 못 들어간 묶음의 cutoff + gap 이전 행)은 어느 쪽에도 쓰지 않는다. 기준 시각 열(time_column)이 없으면 tp. cutoff가 없으면 test_fraction 분위수

## 4. 적합 범위 (Q3)

- 허용 적합 범위: train, train_fold, validation
- 재표본 추출을 적용해도 되는 데이터: train, train_fold
- 뒤 행의 값을 쓰는 결측 대치: backward_fill, bfill, interpolate

## 5. 결과 (Q4, Q7)

### 결과 정의별 대리 기록 (`O.proxy.*`, Q4 경고)

결과와 같은 입원 범위의 특징이 아래 기록과 일치하면 경고한다. 설계서 `outcome.proxies`에 적은 것도 더한다.

- kdigo_creatinine · `O.proxy.renal_orders`: `orders` order_type ∈ ['dialysis_order', 'nephrology_consult', 'renal_ultrasound'] — 설명서 orders.order_type: 신장 관련 오더는 AKI 무렵에 몰림
- kdigo_creatinine · `O.proxy.dialysis_procedure`: `procedures` code ∈ ['5A1D70Z'] — 설명서 procedures.code: 투석 처치는 AKI 무렵 (ICD-10-PCS 5A1D = 투석)
- kdigo_creatinine · `O.proxy.aki_code`: `diagnoses` icd_code ∈ ['N17', '584'] — 설명서 diagnoses.icd_code: AKI 진단 코드 (ICD-9 584)
- kdigo_creatinine · `O.proxy.aki_problem`: `problem_list` icd_code ∈ ['N17'] — 설명서 problem_list.icd_code: N17.9는 KDIGO 기준을 만족한 검사 보고 뒤에 기록
- kdigo_creatinine · `O.proxy.diuretic`: `medications` drug ∈ ['loop_diuretic'] — 설명서 medications.drug: AKI 입원의 40%는 발생 6~48시간 뒤 이뇨제 처방이 더 있음
- next_admission: 규칙표 목록 없음
- diagnosis_code: 규칙표 목록 없음
- diagnosis_code: 결과와 같은 코드의 `problem_list` 항목 (`O.proxy.same_code_problem`)

### 확인 강도를 좌우하는 층 (`O.strata.*`, Q7 경고)

- 결과 테이블 labs · `O.strata.unit` 머문 병동 (`admissions.unit`, `transfers.unit`) — 설명서 labs.collect_time: ICU는 하루 1~2회, 병동은 30~72시간 간격으로 채혈 (vitals도 ICU 1~2시간, 병동 4~8시간)
- 결과 테이블 vitals · `O.strata.unit` 머문 병동 (`admissions.unit`, `transfers.unit`) — 설명서 labs.collect_time: ICU는 하루 1~2회, 병동은 30~72시간 간격으로 채혈 (vitals도 ICU 1~2시간, 병동 4~8시간)
- 결과 테이블 diagnoses · `O.strata.unit` 머문 병동 (`admissions.unit`, `transfers.unit`) — 설명서 labs.collect_time: ICU는 하루 1~2회, 병동은 30~72시간 간격으로 채혈 (vitals도 ICU 1~2시간, 병동 4~8시간)
- 결과 테이블 diagnoses · `O.strata.service` 진료과 (`admission_info.service`) — 설명서 데이터 전체의 성질: 진단 코드의 누락 정도는 병동·진료과에 따라 다르다
- 결과 확인 범위(병원)가 데이터(A, B)보다 좁을 때 · `O.strata.discharge_status` 퇴원처 (`admissions.discharge_status`) — 설명서 데이터 전체의 성질: 퇴원처에 따라 퇴원 뒤 다른 병원(B)으로 재입원하는 비율이 다르다 (전원 > 자택)

`by_stratum`에는 열 이름(`unit`), `테이블.열`, 또는 그 열로 만든 특징 이름을 적을 수 있다.

### 연구 기간 중 바뀐 것 (`O.change.*`, Q7 경고: outcome.history가 비어 있으면)

- `O.change.creatinine_method`: 크레아티닌 측정법 jaffe → enzymatic (labs.method), 2155-01-01 (결과 테이블 labs)
- `O.change.icd`: 진단 코드 체계 ICD-9 → ICD-10 (diagnoses.code_system), 2155-10-01 (결과 테이블 diagnoses)

## 6. 가정 (3층, 판정이 아니라 참고)

- `A.date_only`: 날짜만 있는 값은 그날 중 언제인지 모른다. 설계서에 date_compare가 없으면 그날 23:59로 본다 (조정: `DATE_ONLY_DEFAULT`)
- `A.family_missing`: family_id가 비어 있는 행은 가족 관계를 모른다. 대체 키(fallback_key)로 묶는다. 기록되지 않은 가족은 학습·평가에 나뉠 수 있다
- `A.outside_sites`: A·B 밖 병원의 사건은 데이터에 없다. 결과 확인 범위 밖에서 생긴 결과는 보이지 않는다
- `A.episode_last`: 에피소드의 마지막 입원을 고르려면 퇴원 뒤 60분 안에 이어진 입원이 없음을 알아야 한다. 퇴원 때 안다고 본다 (형식에 다른 올바른 표현이 없음) (조정: `EPISODE_GAP_MAX_H`)
- `A.post_tp_exclusion`: tₚ 뒤의 일(추적 소실, 결과 결측)로 행을 뺀다. 형식에 치우침 없는 다른 처리 값이 없어 가정으로 남긴다

## 7. 판정 규칙 번호

- `S.levels`: Q2: 분할 묶음(key)은 선언된 독립 단위(split_unit) 이상이어야 한다. 위계 index_row < admission < episode < patient < person < family
- `S.entity`: Q2: 독립 단위와 분할 묶음은 개체 단위(사람) 이상이어야 한다
- `S.fallback`: Q2: 결측이 있는 묶음 열(family_id)의 대체 키(fallback_key)도 개체 단위(사람) 이상이어야 한다
- `S.temporal`: Q2: 시간 순 분할의 간격(gap)은 결과 창 길이 이상이어야 한다. 시간 순 분할의 해석: 묶음(key, 결측이면 fallback_key)째로 움직인다. 묶음의 모든 행이 cutoff 이전(≤)이면 학습. cutoff 뒤의 행이 하나라도 있는 묶음은 학습에 넣지 않고, 그 묶음의 cutoff + gap 뒤 행만 평가에 넣는다. 나머지 행(학습에 못 들어간 묶음의 cutoff + gap 이전 행)은 어느 쪽에도 쓰지 않는다. 기준 시각 열(time_column)이 없으면 tp. cutoff가 없으면 test_fraction 분위수
- `S.temporal_deploy`: Q1: 전향 사용(prospective_deployment)이 목적이면 시간 순으로 나눠야 한다 (경고)
- `S.dedup`: Q2: 중복 레코드는 분할 전에 지운다 (deduplication.when = before_split)
- `F.fit_scope`: Q3: 데이터에서 추정하는 것은 학습 부분에서만 (fit_scope ∈ train, train_fold, validation)
- `F.fold_refit`: Q3: 조율을 교차검증으로 하면 추정 단계는 폴드마다 다시 맞춘다 (fit_scope = train_fold, 경고)
- `F.before_split`: Q3: 추정하는 단계를 분할 전에 하지 않는다
- `F.resample`: Q3: 재표본 추출은 학습 부분에만 적용한다
- `F.eval_data`: Q3: 성능은 학습·모형 결정에 쓰지 않은 부분에서 계산한다
- `F.test_reuse`: Q3: 평가 부분으로 성능을 한 번만 본다 (경고)
- `F.future_fill`: Q1: 뒤(나중) 행의 값을 쓰는 결측 대치(backward_fill, bfill, interpolate)는 tₚ에 알 수 없는 값을 쓴다
- `O.same_rows`: Q4: 결과를 정한 행과 같은 행(같은 테이블, 겹치는 필터·범위·시간 구간)을 특징으로 쓰지 않는다
- `O.window_reuse`: Q4: 특징의 시간 창이 결과 창과 겹치지 않아야 한다
- `O.proxy`: Q4: 결과의 대리 기록(규칙표 목록 + 설계서 outcome.proxies)과 일치하는 특징은 사람이 확인한다 (경고)
- `D.proxies`: Q4: 설계서 outcome.proxies에 적힌 대리 기록과 일치 (경고)
- `O.blind`: Q4: 결과를 예측변수 정보를 모른 채 정한다 (blind_to_predictors, 경고)
- `O.strata`: Q7: 결과 확인 강도가 층마다 같거나 층별로 다룬다 (by_stratum, 또는 한 층으로 제한)
- `O.match_key`: Q7: 이번 입원 밖의 결과는 같은 사람(person_id)의 모든 등록 번호에서 찾는다 (경고)
- `O.end_of_data`: Q7: 결과 창이 자료 추출 종료를 넘는 행은 exclude_incomplete 또는 survival_model로 다룬다 (경고)
- `O.death_source`: Q7: 사망을 결과에 넣고 결과 창 안에 퇴원할 수 있으면 사망 연계 자료를 쓴다 (경고)
- `C.time_compare`: Q5: 사건 시각 열을 시각 표현과 비교하는 기준(예: 퇴원 시각 > tp)은 그 시각 + 지연에 알려진다
- `C.sampling`: Q5: 결과를 보고 뽑는 표본 추출은 개발 데이터에만 적용한다
- `C.rows_last`: Q5: 단위마다 마지막 행을 고르려면 그 뒤에 행이 없음을 알아야 한다 (tₚ 뒤 정보)
- `C.post_tp_exclusion`: Q5: 결과 창 안의 사건(사망 등)으로 행을 빼지 않는다
- `C.pending`: Q5: tₚ 전에 생겼지만 tₚ 뒤에 알려진 결과 사건으로 행을 빼지 않는다
- `R.missing`: 점검 불가: 규칙표에 없는 테이블·열·범위는 추측하지 않고 멈춘다
- `R.provenance`: 점검 불가: 특징은 정해진 특징 함수로만 만든다 (원본 테이블 또는 파생 특징). 그 밖은 출처 불명
- `R.data`: 점검 불가: 데이터 단계를 돌리지 못했다 (설계서 점검 결과만 있음)
