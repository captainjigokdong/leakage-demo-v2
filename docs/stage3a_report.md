# 3단계 3a 점검기 보고 (승인 ③ 자료)

2026-10-04 3단계 세션. 점검기 `leakcheck/`만 돌린 결과다 (스킬·에이전트 없음). 본 데이터 `data/synth/`.

## 1. 공개 18개 사례 × 유형 (2c 패치를 `designs/prereview/` 기본 설계서에 적용)

기대 판정이 나왔는지(설계서만 / 본 데이터 포함)와, 기본 설계서에 없던 판정 전부. 실행 시간은 본 데이터 포함 점검 1회.

| 사례 | 유형 | 기대 | 설계서만 | 데이터 포함 | 기본 설계서에 없던 판정 (데이터 포함) | 시간 |
|---|---|---|---|---|---|---|
| E01 | dynamic | Q1 차단 | 통과 | 통과 | Q1 차단 `features.n_dx` — 규칙 T.diagnoses(1층: 설명서: 진단 코드는 코딩 완료 시각(coded_time)에 알려진다. 퇴원 뒤 최대 90일) · 값: diagnoses.icd_code: 범위 index_admission의 행은 언제 알려질지 상한이 없음 → 확인 가능 시각 상한 없음(tₚ 뒤일 수 있음)<br>Q4 경고 `features.n_dx` — 규칙 O.proxy.aki_code(2층: 설명서 diagnoses.icd_code: AKI 진단 코드 (ICD-9 584)) · 값: 특징 diagnoses 필터 없음, 범위 index_admission | 16.9s |
| E02 | dynamic | Q1 차단 | 통과 | 통과 | Q1 차단 `features.cr_last` — 규칙 T.labs.value(1층: 설명서: 검사 값은 보고 시각(report_time)에 알려진다. 채취→보고 지연 상한 6h) · 값: labs.value: 창 끝 tp (collect_time 기준) + collect_time→report_time 지연 상한 6h → 확인 가능 시각 상한 tₚ+6h<br>Q1 차단 `features.cr_rise` — 규칙 T.labs.value(1층: 설명서: 검사 값은 보고 시각(report_time)에 알려진다. 채취→보고 지연 상한 6h) · 값: 파생 특징: 재료 cr_last, cr_min_adm 중 가장 늦은 cr_last → labs.value: 창 끝 tp (collect_time 기준) + collect_time→report_time 지연 상한 6h → 확인 가능 시각 상한 tₚ+6h | 16.4s |
| E02 | fixed | Q1 차단 | 통과 | 통과 | Q1 차단 `features.cr_last` — 규칙 T.labs.value(1층: 설명서: 검사 값은 보고 시각(report_time)에 알려진다. 채취→보고 지연 상한 6h) · 값: labs.value: 창 끝 tp (collect_time 기준) + collect_time→report_time 지연 상한 6h → 확인 가능 시각 상한 tₚ+6h<br>Q1 차단 `features.cr_last_over_hgb` — 규칙 T.labs.value(1층: 설명서: 검사 값은 보고 시각(report_time)에 알려진다. 채취→보고 지연 상한 6h) · 값: 파생 특징: 재료 cr_last, hgb_min 중 가장 늦은 cr_last → labs.value: 창 끝 tp (collect_time 기준) + collect_time→report_time 지연 상한 6h → 확인 가능 시각 상한 tₚ+6h | 3.2s |
| E03 | dynamic | Q1 차단 | 통과 | 통과 | Q1 차단 `features.cr_max_adm` — 규칙 T.labs(1층: 설명서: 검사 값은 보고 시각(report_time)에 알려진다. 채취→보고 지연 상한 6h) · 값: labs.value: 창 끝 discharge (report_time 기준) → 확인 가능 시각 상한 없음(tₚ 뒤일 수 있음)<br>Q4 차단 `features.cr_max_adm` — 규칙 O.same_rows(같은 테이블·겹치는 필터·범위·시간 구간) · 값: 특징 구간 (tₚ-24h, 없음(tₚ 뒤일 수 있음)] ∩ 결과 구간 (tₚ, tₚ+48h] | 16.6s |
| E04 | dynamic | Q1 차단 | 통과 | 통과 | Q1 차단 `features.n_proc` — 규칙 T.procedures(1층: 설명서: 시술 코드는 코드 입력 시각(coded_time)에 알려진다. 시술 날짜(chart_date)에서 입력까지 지연 상한 없음, 퇴원 뒤 최대 90일) · 값: procedures.code: 창이 chart_date 기준인데 chart_date에서 확인 가능 시각(coded_time)까지 지연 상한이 없음, 날짜 비교 same_date_ok → 창 끝 날짜의 끝까지 → 확인 가능 시각 상한 없음(tₚ 뒤일 수 있음)<br>Q4 경고 `features.n_proc` — 규칙 O.proxy.dialysis_procedure(2층: 설명서 procedures.code: 투석 처치는 AKI 무렵 (ICD-10-PCS 5A1D = 투석)) · 값: 특징 procedures 필터 없음, 범위 index_admission | 17.1s |
| E05 | dynamic | Q2 차단 | 통과 | 통과 | Q2 차단 `split.key` — 규칙 S.levels(위계 index_row < admission < episode < patient < person < family) · 값: split.key=landmark_row_id → index_row < family<br>Q2 차단 `split.key` — 규칙 S.levels(위계 index_row < admission < episode < patient < person < family) · 값: 데이터 배정에서 admission 4,394/7,668, episode 4,324/7,449, patient 3,512/5,087, person 3,472/4,976, family 388/411 | 17.3s |
| E06 | fixed | Q2 차단 | 통과 | 통과 | Q2 차단 `split.key` — 규칙 S.levels(위계 index_row < admission < episode < patient < person < family) · 값: split.key=admission_id → admission < family<br>Q2 차단 `split.key` — 규칙 S.levels(위계 index_row < admission < episode < patient < person < family) · 값: 데이터 배정에서 episode 73/6,516, patient 777/4,466, person 800/4,374, family 258/407 | 3.3s |
| E07 | dynamic | Q2 차단 | 통과 | 통과 | Q2 차단 `split.key` — 규칙 S.levels(위계 index_row < admission < episode < patient < person < family) · 값: split.key=patient_id → patient < family<br>Q2 차단 `split.key` — 규칙 S.levels(위계 index_row < admission < episode < patient < person < family) · 값: 데이터 배정에서 person 45/4,976, family 224/411 | 17.3s |
| E07 | fixed | Q2 차단 | 통과 | 통과 | Q2 차단 `split.key` — 규칙 S.levels(위계 index_row < admission < episode < patient < person < family) · 값: split.key=patient_id → patient < family<br>Q2 차단 `split.key` — 규칙 S.levels(위계 index_row < admission < episode < patient < person < family) · 값: 데이터 배정에서 person 44/4,374, family 173/407 | 3.1s |
| E08 | dynamic | Q3 차단 | 통과 | 통과 | Q3 차단 `preprocessing.median_impute` — 규칙 F.fit_scope(추정은 학습 부분에서만: train, train_fold, validation) · 값: fit_scope=all | 16.6s |
| E08 | fixed | Q3 차단 | 통과 | 통과 | Q3 차단 `preprocessing.median_impute` — 규칙 F.fit_scope(추정은 학습 부분에서만: train, train_fold, validation) · 값: fit_scope=all | 3.0s |
| E09 | fixed | Q3 차단 | 통과 | 통과 | Q3 차단 `preprocessing.dx_encode` — 규칙 F.fit_scope(추정은 학습 부분에서만: train, train_fold, validation) · 값: fit_scope=all<br>Q3 차단 `preprocessing.dx_encode` — 규칙 F.before_split · 값: before_split=true, stateless=false | 2.9s |
| E10 | dynamic | Q3 차단 | 통과 | 통과 | Q3 차단 `preprocessing.select_k` — 규칙 F.fit_scope(추정은 학습 부분에서만: train, train_fold, validation) · 값: fit_scope=all | 16.5s |
| E10 | fixed | Q3 차단 | 통과 | 통과 | Q3 차단 `preprocessing.select_k` — 규칙 F.fit_scope(추정은 학습 부분에서만: train, train_fold, validation) · 값: fit_scope=all | 3.0s |
| E11 | dynamic | Q4 차단 | 통과 | 통과 | Q1 차단 `features.cr_change_48h` — 규칙 T.labs.value(1층: 설명서: 검사 값은 보고 시각(report_time)에 알려진다. 채취→보고 지연 상한 6h) · 값: labs.value: 창 끝 tp+2d (collect_time 기준) + collect_time→report_time 지연 상한 6h → 확인 가능 시각 상한 tₚ+54h<br>Q4 차단 `features.cr_change_48h` — 규칙 O.same_rows(같은 테이블·겹치는 필터·범위·시간 구간) · 값: 특징 구간 (tₚ, tₚ+48h] ∩ 결과 구간 (tₚ, tₚ+48h] | 16.4s |
| E12 | fixed | Q4 차단 | 통과 | 통과 | Q1 차단 `features.ward_type` — 규칙 T.admissions.unit(1층: 설명서: 입원 시 알려진다) · 값: admissions.unit: 소속 입원의 입원 시각(범위 next_admission) → 확인 가능 시각 상한 없음(tₚ 뒤일 수 있음)<br>Q4 차단 `features.ward_type` — 규칙 O.same_rows(같은 테이블·겹치는 필터·범위·시간 구간) · 값: 특징 구간 (tₚ, 없음(tₚ 뒤일 수 있음)] ∩ 결과 구간 (tₚ, tₚ+720h] | 2.9s |
| E13 | dynamic | Q4 경고 | 통과 | 통과 | Q4 경고 `features.renal_ordered` — 규칙 O.proxy.renal_orders(2층: 설명서 orders.order_type: 신장 관련 오더는 AKI 무렵에 몰림) · 값: 특징 orders {'order_type': ['dialysis_order', 'nephrology_consult']}, 범위 index_admission | 15.2s |
| E14 | dynamic | Q5 차단 | 통과 | 통과 | Q5 차단 `cohort.inclusion.los_7d` — 규칙 T.admissions.length_of_stay_h(1층: 설명서: 퇴원 시 알려진다 (discharge_time)) · 값: admissions.length_of_stay_h: 소속 입원의 퇴원 시각(범위 index_admission) → 확인 가능 시각 상한 없음(tₚ 뒤일 수 있음) | 8.6s |
| E15 | dynamic | Q5 차단 | 통과 | 통과 | Q5 차단 `cohort.inclusion.cr_monitored` — 규칙 T.labs(1층: 설명서: 검사 값은 보고 시각(report_time)에 알려진다. 채취→보고 지연 상한 6h) · 값: labs.value: 창 끝 discharge (report_time 기준) → 확인 가능 시각 상한 없음(tₚ 뒤일 수 있음) | 15.0s |
| E16 | fixed | Q5 차단 | 통과 | 통과 | Q5 차단 `cohort.inclusion.clinic_visit` — 규칙 T.outpatient_visits(1층: 설명서: 방문 시각(visit_time)에 알려진다) · 값: outpatient_visits.visit_type: 범위 patient_history의 행은 언제 알려질지 상한이 없음 → 확인 가능 시각 상한 없음(tₚ 뒤일 수 있음) | 2.9s |
| E17 | dynamic | Q7 경고 | 통과 | 통과 | Q7 경고 `outcome.ascertainment.by_stratum` — 규칙 O.strata.unit(2층: 설명서 labs.collect_time: ICU는 하루 1~2회, 병동은 30~72시간 간격으로 채혈 (vitals도 ICU 1~2시간, 병동 4~8시간)) · 값: 비 2.2 ≥ 2 | 16.9s |
| E18 | fixed | Q7 경고 | 통과 | 통과 | Q7 경고 `outcome.ascertainment.scope.sites` — 규칙 O.strata.discharge_status(2층: 설명서 데이터 전체의 성질: 퇴원처에 따라 퇴원 뒤 다른 병원(B)으로 재입원하는 비율이 다르다 (전원 > 자택)) · 값: 놓치는 비율의 비 15.8 ≥ 2 | 2.9s |

## 2. 깨끗한 설계서 2개: 고치기 전 / 후

고치기 전 = 3단계 시작 시점 점검기(main `41c86cc`), 설계서만 (v1 로더라 v2 데이터를 읽지 못함). 고친 뒤 = 3a 점검기, 설계서만과 본 데이터 포함.

### dynamic_aki

**고치기 전 (차단·경고만)**

- [경고] Q1~Q3 `features.cr_rise`: 출처 불명: 정해진 특징 함수(leakcheck.features)로 만들지 않았거나 원본 테이블이 없다. Q1~Q3 확인 불가.
- [경고] Q1~Q3 `features.unit_at_tp`: 규칙표에 없어 확인 불가: "규칙표에 테이블 'transfers'의 규칙이 없다". 규칙을 추가해야 한다.
- [경고] Q1~Q3 `features.service`: 규칙표에 없어 확인 불가: "규칙표에 테이블 'admission_info'의 규칙이 없다". 규칙을 추가해야 한다.
- [경고] Q1~Q3 `features.admission_type`: 규칙표에 없어 확인 불가: "규칙표에 테이블 'admission_info'의 규칙이 없다". 규칙을 추가해야 한다.
- [경고] Q1~Q3 `features.sbp_min_24h`: 규칙표에 없어 확인 불가: "규칙표에 테이블 'vitals'의 규칙이 없다". 규칙을 추가해야 한다.
- [경고] Q1~Q3 `features.hr_max_24h`: 규칙표에 없어 확인 불가: "규칙표에 테이블 'vitals'의 규칙이 없다". 규칙을 추가해야 한다.
- [경고] Q1~Q3 `features.temp_max_24h`: 규칙표에 없어 확인 불가: "규칙표에 테이블 'vitals'의 규칙이 없다". 규칙을 추가해야 한다.
- [경고] Q1~Q3 `features.nephrotoxic_by_tp`: 규칙표에 없어 확인 불가: "규칙표에 테이블 'medications'의 규칙이 없다". 규칙을 추가해야 한다.
- [경고] Q1~Q3 `features.problem_ckd_active`: 규칙표에 없어 확인 불가: "규칙표에 테이블 'problem_list'의 규칙이 없다". 규칙을 추가해야 한다.
- [경고] Q4 `outcome.aki_or_death_48h`: 규칙표에 없어 확인 불가: "규칙표에 테이블 'transfers'의 규칙이 없다". 규칙을 추가해야 한다.
- [차단] Q5 `cohort.inclusion.in_hospital_at_tp`: 포함·제외 기준의 확인 가능 시각이 기준 시점(tp) 뒤일 수 있다 (tₚ = admit+1d). admissions.discharge_time: 소속 입원의 퇴원 시각(범위 index_admission) → 확인 가능 시각 상한 없음(tₚ 뒤일 수 있음). 규칙(1층): 퇴원 시각·퇴원 상태·재원 기간은 퇴원 시각에 확정된다
- [경고] Q7 `outcome.aki_or_death_48h`: 결과가 측정(labs)으로 정해지는데 측정 강도가 다를 수 있는 층 'unit'을 함께 두고 층별로 다루지 않는다. 데이터 없이 측정 빈도 비를 확인할 수 없어 사람이 확인.

**고친 뒤, 본 데이터 포함 (15.6s) — 전체 출력**

```
설계 prereview_dynamic_aki (dynamic) — 차단 1 · 경고 2 · 점검 불가 0 · 가정 2 · 통과 26 · 기록 1 (데이터 확인 포함)
결론: 차단 — 설계를 고치기 전에는 모델링을 진행하지 않는다

[차단·경고 (제출 kind: 문제)]
[차단] Q5 선택 시점 · outcome.pending_at_tp
    근거: 규칙 C.pending(T.labs: 설명서: 검사 값은 보고 시각(report_time)에 알려진다. 채취→보고 지연 상한 6h) · 값: pending_at_tp=exclude_row, 결과 시각 열 collect_time
    설명: tₚ 전에 생겼지만 tₚ 뒤에 알려진 결과 사건(labs.collect_time ≤ tₚ < report_time)이 있는 행을 뺀다. tₚ 뒤 정보로 표본을 고른다. ignore 또는 count_as_outcome으로 쓸 수 있다.
[경고] Q1 가용 시점 · split.method
    근거: 규칙 S.temporal_deploy(Kapoor L3.1: 미래를 예측하는 모형은 평가 기간이 학습 기간 뒤여야 함) · 값: intended_use.purpose=prospective_deployment, split.method=group_holdout
    설명: 전향 사용이 목적인데 학습·평가를 시간 순으로 나누지 않았다. 평가 부분보다 뒤의 기간이 학습에 들어가 사용 시점에는 없는 정보(미래의 진료 관행·측정법)로 학습할 수 있다. split.method=temporal(묶음 키 유지)로 쓸 수 있다.
[경고] Q7 결과 확인 균질성 · data_source.death_source
    근거: 규칙 O.death_source(설명서 deaths: 원외 사망은 퇴원 1~365일 뒤, 사망 연계로만 기록) · 값: death_source=in_hospital_only, censoring.death=composite_outcome
    설명: 사망을 결과에 넣는데 원내 사망 기록만 쓴다. 결과 창 안에 퇴원한 행은 원외 사망을 놓친다. death_source=linked_registry로 쓸 수 있다.

[가정 — 판정 아님, 참고 (제출 kind: 가정)]
[가정] Q2 독립 단위 · split.key
    근거: 3층 가정 A.family_missing · 형식으로 피할 수 없음
    설명: family_id가 비어 있는 행은 가족 관계를 모른다. 대체 키(fallback_key)로 묶는다. 기록되지 않은 가족은 학습·평가에 나뉠 수 있다 (대체 키 person_id)
[가정] Q2 독립 단위 · model.tuning.cv_key
    근거: 3층 가정 A.family_missing · 형식으로 피할 수 없음
    설명: family_id가 비어 있는 행은 가족 관계를 모른다. 대체 키(fallback_key)로 묶는다. 기록되지 않은 가족은 학습·평가에 나뉠 수 있다 (대체 키 person_id)

[기록 (제출하지 않음)]
[기록] Q6 다중 시도 · attempts
    설명: 설계 1개, 모델 1개 시도, 보정: none.

[통과 (제출하지 않음)]
[통과] Q1 가용 시점 · features.age
    근거: 규칙 T.patients.age(1층: 설명서: 그 등록 번호의 첫 입원 시 알려진다) · 값: patients.age: 그 등록 번호의 첫 입원 시각 ≤ 인덱스 입원 시각 → 확인 가능 시각 상한 tₚ-24h
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/25,834 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.sex
    근거: 규칙 T.patients.sex(1층: 설명서: 그 등록 번호의 첫 입원 시 알려진다) · 값: patients.sex: 그 등록 번호의 첫 입원 시각 ≤ 인덱스 입원 시각 → 확인 가능 시각 상한 tₚ-24h
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/25,834 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.unit_at_tp
    근거: 규칙 T.transfers.unit(1층: 설명서: 병동 입실 시각(in_time)에 알려진다) · 값: transfers.unit: 창 끝 tp (in_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/25,834 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.service
    근거: 규칙 T.admission_info.service(1층: 설명서: 입원 시 알려진다) · 값: admission_info.service: 소속 입원의 입원 시각(범위 index_admission) → 확인 가능 시각 상한 tₚ-24h
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/25,834 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.admission_type
    근거: 규칙 T.admission_info.admission_type(1층: 설명서: 입원 시 알려진다) · 값: admission_info.admission_type: 소속 입원의 입원 시각(범위 index_admission) → 확인 가능 시각 상한 tₚ-24h
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/25,834 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.cr_last
    근거: 규칙 T.labs.value(1층: 설명서: 검사 값은 보고 시각(report_time)에 알려진다. 채취→보고 지연 상한 6h) · 값: labs.value: 창 끝 tp (report_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/25,834 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.cr_min_adm
    근거: 규칙 T.labs.value(1층: 설명서: 검사 값은 보고 시각(report_time)에 알려진다. 채취→보고 지연 상한 6h) · 값: labs.value: 창 끝 tp (report_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/25,834 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.cr_max_48h
    근거: 규칙 T.labs.value(1층: 설명서: 검사 값은 보고 시각(report_time)에 알려진다. 채취→보고 지연 상한 6h) · 값: labs.value: 창 끝 tp (report_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/25,834 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.n_cr
    근거: 규칙 T.labs(1층: 설명서: 검사 값은 보고 시각(report_time)에 알려진다. 채취→보고 지연 상한 6h) · 값: labs.value: 창 끝 tp (report_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/25,834 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.cr_rise
    근거: 규칙 T.labs.value(1층: 설명서: 검사 값은 보고 시각(report_time)에 알려진다. 채취→보고 지연 상한 6h) · 값: 파생 특징: 재료 cr_last, cr_min_adm 중 가장 늦은 cr_last → labs.value: 창 끝 tp (report_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/25,834 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.bun_last
    근거: 규칙 T.labs.value(1층: 설명서: 검사 값은 보고 시각(report_time)에 알려진다. 채취→보고 지연 상한 6h) · 값: labs.value: 창 끝 tp (report_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/25,834 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.k_last
    근거: 규칙 T.labs.value(1층: 설명서: 검사 값은 보고 시각(report_time)에 알려진다. 채취→보고 지연 상한 6h) · 값: labs.value: 창 끝 tp (report_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/25,834 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.hgb_min
    근거: 규칙 T.labs.value(1층: 설명서: 검사 값은 보고 시각(report_time)에 알려진다. 채취→보고 지연 상한 6h) · 값: labs.value: 창 끝 tp (report_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/25,834 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.sbp_min_24h
    근거: 규칙 T.vitals.value(1층: 설명서: 활력징후는 전산 입력 시각(entered_time)에 알려진다. 관찰→입력 지연 상한 6h) · 값: vitals.value: 창 끝 tp (entered_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/25,834 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.hr_max_24h
    근거: 규칙 T.vitals.value(1층: 설명서: 활력징후는 전산 입력 시각(entered_time)에 알려진다. 관찰→입력 지연 상한 6h) · 값: vitals.value: 창 끝 tp (entered_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/25,834 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.temp_max_24h
    근거: 규칙 T.vitals.value(1층: 설명서: 활력징후는 전산 입력 시각(entered_time)에 알려진다. 관찰→입력 지연 상한 6h) · 값: vitals.value: 창 끝 tp (entered_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/25,834 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.nephrotoxic_by_tp
    근거: 규칙 T.medications(1층: 설명서: 처방 시각(order_time)에 알려진다) · 값: medications.drug: 창 끝 tp (order_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/25,834 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.prior_dx_ckd
    근거: 규칙 T.diagnoses(1층: 설명서: 진단 코드는 코딩 완료 시각(coded_time)에 알려진다. 퇴원 뒤 최대 90일) · 값: diagnoses.icd_code: 창 끝 tp (coded_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/25,834 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.problem_ckd_active
    근거: 규칙 T.problem_list(1층: 설명서: 문제 목록은 버전마다 기록 시각(recorded_time)에 알려진다) · 값: problem_list.icd_code: 창 끝 tp (recorded_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/25,834 예측 행에서 확인 가능 시각 > tp.
[통과] Q5 선택 시점 · cohort.inclusion.adult
    근거: 규칙 T.patients.age(1층: 설명서: 그 등록 번호의 첫 입원 시 알려진다) · 값: patients.age: 그 등록 번호의 첫 입원 시각 ≤ 인덱스 입원 시각 → 확인 가능 시각 상한 tₚ-24h
    설명: [꼬리표: 정적] 포함·제외 기준의 확인 가능 시각 ≤ tp. 데이터: 0/28,761 예측 행에서 확인 가능 시각 > tp.
[통과] Q5 선택 시점 · cohort.inclusion.in_hospital_at_tp
    근거: 규칙 C.time_compare(2층: 사건 시각을 시각 표현과 비교하는 기준은 '그 시각까지 일어났는가'만 쓴다) · 값: admissions.discharge_time > tp: 그 시각까지 사건이 있었는지는 tp에 알 수 있다 → 확인 가능 시각 상한 tₚ
    설명: [꼬리표: 시각 비교] 포함·제외 기준의 확인 가능 시각 ≤ tp. 데이터: 0/28,761 예측 행에서 확인 가능 시각 > tp.
[통과] Q5 선택 시점 · cohort.exclusion.aki_known_by_tp
    근거: 규칙 T.labs(1층: 설명서: 검사 값은 보고 시각(report_time)에 알려진다. 채취→보고 지연 상한 6h) · 값: labs.value: 창 끝 tp (report_time 기준) → 확인 가능 시각 상한 tₚ
    설명: [꼬리표: tp까지 알려짐] 포함·제외 기준의 확인 가능 시각 ≤ tp. 데이터: 0/28,761 예측 행에서 확인 가능 시각 > tp.
[통과] Q5 선택 시점 · cohort.exclusion.dialysis_by_tp
    근거: 규칙 T.orders(1층: 설명서: 오더 시각(order_time)에 알려진다) · 값: orders.order_type: 창 끝 tp (order_time 기준) → 확인 가능 시각 상한 tₚ
    설명: [꼬리표: tp까지 알려짐] 포함·제외 기준의 확인 가능 시각 ≤ tp. 데이터: 0/28,761 예측 행에서 확인 가능 시각 > tp.
[통과] Q2 독립 단위 · 설계 전체
    근거: 규칙 S.levels · 값: 위반 없음
    설명: 분할 키 family_id(대체 person_id) ≥ 독립 단위 family ≥ 개체 단위 person
[통과] Q3 적합 범위 · 설계 전체
    근거: 규칙 F.fit_scope · 값: 위반 없음
    설명: 전처리 3단계와 모형 결정의 적합 범위 ⊆ 학습 부분, 평가는 평가 부분
[통과] Q4 결과 출처 · 설계 전체
    근거: 규칙 O.same_rows · 값: 위반 없음
    설명: 특징이 결과 행·결과 창·대리 기록과 겹치지 않음
```

### fixed_readmission

**고치기 전 (차단·경고만)**

- [경고] Q1~Q3 `features.cr_last_over_hgb`: 출처 불명: 정해진 특징 함수(leakcheck.features)로 만들지 않았거나 원본 테이블이 없다. Q1~Q3 확인 불가.
- [경고] Q1~Q3 `features.icu_any`: 규칙표에 없어 확인 불가: "규칙표에 테이블 'transfers'의 규칙이 없다". 규칙을 추가해야 한다.
- [경고] Q1~Q3 `features.site`: 규칙표에 없어 확인 불가: "규칙표에 테이블 'admission_info'의 규칙이 없다". 규칙을 추가해야 한다.
- [경고] Q1~Q3 `features.service`: 규칙표에 없어 확인 불가: "규칙표에 테이블 'admission_info'의 규칙이 없다". 규칙을 추가해야 한다.
- [경고] Q1~Q3 `features.problem_ckd_active`: 규칙표에 없어 확인 불가: "규칙표에 테이블 'problem_list'의 규칙이 없다". 규칙을 추가해야 한다.
- [경고] Q1~Q3 `features.sbp_last`: 규칙표에 없어 확인 불가: "규칙표에 테이블 'vitals'의 규칙이 없다". 규칙을 추가해야 한다.
- [경고] Q1~Q3 `features.n_discharge_meds`: 규칙표에 없어 확인 불가: "규칙표에 테이블 'medications'의 규칙이 없다". 규칙을 추가해야 한다.
- [경고] Q4 `outcome.unplanned_readmit_or_death_30d`: 규칙표에 없어 확인 불가: "규칙표에 테이블 'transfers'의 규칙이 없다". 규칙을 추가해야 한다.

**고친 뒤, 본 데이터 포함 (3.0s) — 전체 출력**

```
설계 prereview_fixed_readmission (fixed) — 차단 0 · 경고 4 · 점검 불가 0 · 가정 4 · 통과 24 · 기록 1 (데이터 확인 포함)
결론: 차단 없음 — 경고는 사람이 확인

[차단·경고 (제출 kind: 문제)]
[경고] Q1 가용 시점 · split.method
    근거: 규칙 S.temporal_deploy(Kapoor L3.1: 미래를 예측하는 모형은 평가 기간이 학습 기간 뒤여야 함) · 값: intended_use.purpose=prospective_deployment, split.method=group_holdout
    설명: 전향 사용이 목적인데 학습·평가를 시간 순으로 나누지 않았다. 평가 부분보다 뒤의 기간이 학습에 들어가 사용 시점에는 없는 정보(미래의 진료 관행·측정법)로 학습할 수 있다. split.method=temporal(묶음 키 유지)로 쓸 수 있다.
[경고] Q3 적합 범위 · preprocessing.median_impute
    근거: 규칙 F.fold_refit(교차검증 조율이면 폴드마다 다시 적합) · 값: fit_scope=train, 조율 교차검증
    설명: 조율을 교차검증으로 하는데 impute 단계를 학습 부분 전체(train)에서 한 번 적합한다. 조율의 검증 폴드 정보가 적합에 들어간다 (평가 부분과는 무관). fit_scope=train_fold로 쓸 수 있다.
[경고] Q3 적합 범위 · preprocessing.one_hot
    근거: 규칙 F.fold_refit(교차검증 조율이면 폴드마다 다시 적합) · 값: fit_scope=train, 조율 교차검증
    설명: 조율을 교차검증으로 하는데 encode 단계를 학습 부분 전체(train)에서 한 번 적합한다. 조율의 검증 폴드 정보가 적합에 들어간다 (평가 부분과는 무관). fit_scope=train_fold로 쓸 수 있다.
[경고] Q3 적합 범위 · preprocessing.standardize
    근거: 규칙 F.fold_refit(교차검증 조율이면 폴드마다 다시 적합) · 값: fit_scope=train, 조율 교차검증
    설명: 조율을 교차검증으로 하는데 scale 단계를 학습 부분 전체(train)에서 한 번 적합한다. 조율의 검증 폴드 정보가 적합에 들어간다 (평가 부분과는 무관). fit_scope=train_fold로 쓸 수 있다.

[가정 — 판정 아님, 참고 (제출 kind: 가정)]
[가정] Q2 독립 단위 · split.key
    근거: 3층 가정 A.family_missing · 형식으로 피할 수 없음
    설명: family_id가 비어 있는 행은 가족 관계를 모른다. 대체 키(fallback_key)로 묶는다. 기록되지 않은 가족은 학습·평가에 나뉠 수 있다 (대체 키 person_id)
[가정] Q2 독립 단위 · model.tuning.cv_key
    근거: 3층 가정 A.family_missing · 형식으로 피할 수 없음
    설명: family_id가 비어 있는 행은 가족 관계를 모른다. 대체 키(fallback_key)로 묶는다. 기록되지 않은 가족은 학습·평가에 나뉠 수 있다 (대체 키 person_id)
[가정] Q5 선택 시점 · cohort.rows_per_unit
    근거: 3층 가정 A.episode_last · 조정: rules.EPISODE_GAP_MAX_H
    설명: 에피소드의 마지막 입원을 고르려면 퇴원 뒤 60분 안에 이어진 입원이 없음을 알아야 한다. 퇴원 때 안다고 본다 (형식에 다른 올바른 표현이 없음)
[가정] Q7 결과 확인 균질성 · outcome.ascertainment.scope.sites
    근거: 3층 가정 A.outside_sites · 형식으로 피할 수 없음
    설명: A·B 밖 병원의 사건은 데이터에 없다. 결과 확인 범위 밖에서 생긴 결과는 보이지 않는다

[기록 (제출하지 않음)]
[기록] Q6 다중 시도 · attempts
    설명: 설계 1개, 모델 1개 시도, 보정: none.

[통과 (제출하지 않음)]
[통과] Q1 가용 시점 · features.age
    근거: 규칙 T.patients.age(1층: 설명서: 그 등록 번호의 첫 입원 시 알려진다) · 값: patients.age: 그 등록 번호의 첫 입원 시각 ≤ 인덱스 입원 시각 → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/6,706 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.sex
    근거: 규칙 T.patients.sex(1층: 설명서: 그 등록 번호의 첫 입원 시 알려진다) · 값: patients.sex: 그 등록 번호의 첫 입원 시각 ≤ 인덱스 입원 시각 → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/6,706 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.unit
    근거: 규칙 T.admissions.unit(1층: 설명서: 입원 시 알려진다) · 값: admissions.unit: 소속 입원의 입원 시각(범위 index_admission) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/6,706 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.icu_any
    근거: 규칙 T.transfers.unit(1층: 설명서: 병동 입실 시각(in_time)에 알려진다) · 값: transfers.unit: 창 끝 tp (in_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/6,706 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.los_h
    근거: 규칙 T.admissions.length_of_stay_h(1층: 설명서: 퇴원 시 알려진다 (discharge_time)) · 값: admissions.length_of_stay_h: 소속 입원의 퇴원 시각(범위 index_admission) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/6,706 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.discharge_status
    근거: 규칙 T.admissions.discharge_status(1층: 설명서: 퇴원 시 알려진다 (discharge_time)) · 값: admissions.discharge_status: 소속 입원의 퇴원 시각(범위 index_admission) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/6,706 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.site
    근거: 규칙 T.admission_info.site(1층: 설명서: 입원 시 알려진다) · 값: admission_info.site: 소속 입원의 입원 시각(범위 index_admission) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/6,706 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.service
    근거: 규칙 T.admission_info.service(1층: 설명서: 입원 시 알려진다) · 값: admission_info.service: 소속 입원의 입원 시각(범위 index_admission) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/6,706 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.n_prior_adm
    근거: 규칙 T.admissions(1층: 설명서: 입원 시 알려진다) · 값: admissions.행: 소속 입원의 입원 시각(범위 prior_admissions) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/6,706 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.prior_dx_ckd
    근거: 규칙 T.diagnoses(1층: 설명서: 진단 코드는 코딩 완료 시각(coded_time)에 알려진다. 퇴원 뒤 최대 90일) · 값: diagnoses.icd_code: 창 끝 tp (coded_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/6,706 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.prior_dx_chf
    근거: 규칙 T.diagnoses(1층: 설명서: 진단 코드는 코딩 완료 시각(coded_time)에 알려진다. 퇴원 뒤 최대 90일) · 값: diagnoses.icd_code: 창 끝 tp (coded_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/6,706 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.problem_ckd_active
    근거: 규칙 T.problem_list(1층: 설명서: 문제 목록은 버전마다 기록 시각(recorded_time)에 알려진다) · 값: problem_list.icd_code: 창 끝 tp (recorded_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/6,706 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.cr_last
    근거: 규칙 T.labs.value(1층: 설명서: 검사 값은 보고 시각(report_time)에 알려진다. 채취→보고 지연 상한 6h) · 값: labs.value: 창 끝 tp (report_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/6,706 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.hgb_min
    근거: 규칙 T.labs.value(1층: 설명서: 검사 값은 보고 시각(report_time)에 알려진다. 채취→보고 지연 상한 6h) · 값: labs.value: 창 끝 tp (report_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/6,706 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.sbp_last
    근거: 규칙 T.vitals.value(1층: 설명서: 활력징후는 전산 입력 시각(entered_time)에 알려진다. 관찰→입력 지연 상한 6h) · 값: vitals.value: 창 끝 tp (entered_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/6,706 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.n_discharge_meds
    근거: 규칙 T.medications(1층: 설명서: 처방 시각(order_time)에 알려진다) · 값: medications.drug: 창 끝 tp (order_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/6,706 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.dialysis_ordered
    근거: 규칙 T.orders(1층: 설명서: 오더 시각(order_time)에 알려진다) · 값: orders.order_type: 창 끝 tp (order_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/6,706 예측 행에서 확인 가능 시각 > tp.
[통과] Q1 가용 시점 · features.cr_last_over_hgb
    근거: 규칙 T.labs.value(1층: 설명서: 검사 값은 보고 시각(report_time)에 알려진다. 채취→보고 지연 상한 6h) · 값: 파생 특징: 재료 cr_last, hgb_min 중 가장 늦은 cr_last → labs.value: 창 끝 tp (report_time 기준) → 확인 가능 시각 상한 tₚ
    설명: 특징의 확인 가능 시각 ≤ tp. 데이터: 0/6,706 예측 행에서 확인 가능 시각 > tp.
[통과] Q5 선택 시점 · cohort.inclusion.adult
    근거: 규칙 T.patients.age(1층: 설명서: 그 등록 번호의 첫 입원 시 알려진다) · 값: patients.age: 그 등록 번호의 첫 입원 시각 ≤ 인덱스 입원 시각 → 확인 가능 시각 상한 tₚ
    설명: [꼬리표: 정적] 포함·제외 기준의 확인 가능 시각 ≤ tp. 데이터: 0/7,724 예측 행에서 확인 가능 시각 > tp.
[통과] Q5 선택 시점 · cohort.exclusion.died_in_hospital
    근거: 규칙 T.admissions.discharge_status(1층: 설명서: 퇴원 시 알려진다 (discharge_time)) · 값: admissions.discharge_status: 소속 입원의 퇴원 시각(범위 index_admission) → 확인 가능 시각 상한 tₚ
    설명: [꼬리표: tp까지 알려짐] 포함·제외 기준의 확인 가능 시각 ≤ tp. 데이터: 0/7,724 예측 행에서 확인 가능 시각 > tp.
[통과] Q5 선택 시점 · cohort.exclusion.followup_incomplete
    근거: 규칙 T.admissions.discharge_time(1층: 설명서: 퇴원 시 알려진다 (discharge_time)) · 값: admissions.discharge_time: 소속 입원의 퇴원 시각(범위 index_admission) → 확인 가능 시각 상한 tₚ
    설명: [꼬리표: tp까지 알려짐] 포함·제외 기준의 확인 가능 시각 ≤ tp. 데이터: 0/7,724 예측 행에서 확인 가능 시각 > tp.
[통과] Q2 독립 단위 · 설계 전체
    근거: 규칙 S.levels · 값: 위반 없음
    설명: 분할 키 family_id(대체 person_id) ≥ 독립 단위 family ≥ 개체 단위 person
[통과] Q4 결과 출처 · 설계 전체
    근거: 규칙 O.same_rows · 값: 위반 없음
    설명: 특징이 결과 행·결과 창·대리 기록과 겹치지 않음
[통과] Q7 결과 확인 균질성 · 설계 전체
    근거: 규칙 O.strata · 값: 위반 없음
    설명: 결과 확인 강도가 층마다 같음 (또는 층별로 다룸, 또는 측정 의존 결과 아님), 확인 범위·이력·사망 출처
```

## 3. 원리 시험 (`tests/test_principles_v2.py`, 공개 18개에 없는 예시)

bad = 원리를 어긴 설계에서 기대 판정이 나옴, good = 형식 안의 올바른 표현으로 고치면 그 판정이 사라짐 (조건 1). 결과는 모두 통과.

| 번호 | 유형 | 원리 | 기대 판정 |
|---|---|---|---|
| `q1_history_person` | fixed | history_key=person_id는 자료 추출 때 연결 | Q1 차단 `features.outpatient_k` |
| `q1_as_of_latest` | fixed | 버전 기록의 최종본은 tₚ 뒤 수정일 수 있음 | Q1 차단 `features.pl_htn` |
| `q1_date_only_same_day` | fixed | 날짜만 있는 예정일을 같은 날까지 비교 + 예약 테이블 확인 시각과의 지연 상한 없음 | Q1 차단 `features.planned_soon` |
| `q1_linked_admission` | fixed | 예약의 admission_id는 예약 입원 때 채워짐 | Q1 차단 `features.booking_realized` |
| `q1_extraction_value` | dynamic | 자료 추출 정보는 모든 tₚ 뒤 | Q1 차단 `features.linkage_date` |
| `q1_future_fill` | dynamic | 뒤 행의 값으로 결측 대치 | Q1 차단 `preprocessing.bfill_vitals` |
| `q1_temporal_deploy` | fixed | 전향 사용인데 시간 순 분할 아님 (D5) | Q1 경고 `split.method` |
| `q1_derived_inherits` | dynamic | 파생 특징은 재료의 확인 시각을 물려받음 | Q1 차단 `features.k_over_cr` |
| `q1_derived_missing_part` | dynamic | 파생 특징의 재료가 설계서에 없으면 점검 불가 | Q1~Q3 점검 불가 `features.x_ratio` |
| `q2_fallback_patient` | fixed | 대체 키가 개체 단위(사람)보다 작음 | Q2 차단 `split.fallback_key` |
| `q2_no_fallback` | dynamic | 결측이 있는 키에 대체 키 없음 → 등록 번호로 묶인다고 가정 + 차단 | Q2 차단 `split.key` |
| `q2_cv_key_rows` | dynamic | 조율 교차검증 키가 예측 행 | Q2 차단 `model.tuning.cv_key` |
| `q2_dedup_within` | fixed | 중복 제거를 분할 안에서 | Q2 경고 `cohort.deduplication.when` |
| `q2_temporal_gap` | dynamic | 시간 순 분할의 간격이 결과 창보다 짧음 | Q2 경고 `split.gap` |
| `q3_fold_refit` | dynamic | 교차검증 조율인데 학습 부분 전체에서 한 번 적합 (D4) | Q3 경고 `preprocessing.scale_all` |
| `q3_eval_on_train` | fixed | 학습 부분으로 성능 평가 | Q3 차단 `evaluation.data` |
| `q3_validation_reuse` | fixed | 검증 부분으로 임계값을 정하고 같은 부분으로 평가 | Q3 차단 `evaluation.data` |
| `q3_test_reuse` | fixed | 평가 부분을 여러 번 봄 | Q3 경고 `evaluation.test_set_uses` |
| `q3_resample_test` | fixed | 재표본 추출을 평가 부분에도 적용 | Q3 차단 `preprocessing.smote` |
| `q3_before_split` | fixed | 추정 단계를 분할 전에 | Q3 차단 `preprocessing.winsor` |
| `q4_proxy_diuretic` | dynamic | 결과의 대리 기록(이뇨제 처방) | Q4 경고 `features.diuretic_by_tp` |
| `q4_vitals_window_reuse` | dynamic | 다른 테이블 특징의 창이 결과 창과 겹침 | Q4 차단 `features.hr_next` |
| `q4_not_blind` | fixed | 결과를 예측변수를 알고 정함 | Q4 경고 `outcome.ascertainment.blind_to_predictors` |
| `q5_last_per_person` | fixed | 사람마다 마지막 행 (D1) | Q5 차단 `cohort.rows_per_unit` |
| `q5_last_landmark` | dynamic | 입원마다 마지막 랜드마크 (퇴원 시각을 알아야 함) | Q5 차단 `cohort.rows_per_unit` |
| `q5_death_exclude` | fixed | 결과 창 안 사망으로 행을 뺌 | Q5 차단 `outcome.censoring.death` |
| `q5_sampling_eval` | fixed | 결과 기준 표본 추출을 평가에도 적용 | Q5 차단 `cohort.sampling` |
| `q5_time_compare_lag` | dynamic | 채취 시각을 tₚ와 비교: 보고까지 지연 6h | Q5 차단 `cohort.exclusion.cr_drawn_after_tp` |
| `q5_patient_table_future` | fixed | 환자 단위 테이블의 tₚ 뒤 기록으로 포함 | Q5 차단 `cohort.inclusion.has_outpatient_k` |
| `q5_lost_exclude` | fixed | 추적 소실로 행을 뺌 → 형식에 대안이 없어 가정 | 가정 A.post_tp_exclusion `outcome.censoring.lost_to_followup` |
| `q5_outcome_missing_exclude` | fixed | 결과 결측 행을 뺌 → 가정 | 가정 A.post_tp_exclusion `analysis.missing_data.outcome_missing` |
| `q7_match_key` | fixed | 결과를 같은 등록 번호에서만 찾음 | Q7 경고 `outcome.match_key` |
| `q7_history` | dynamic | 결과 측정법이 바뀌었는데 이력 없음 | Q7 경고 `outcome.history` |
| `q7_end_of_data` | fixed | 결과 창이 추출 종료를 넘는 행을 음성으로 | Q7 경고 `outcome.censoring.end_of_data` |
| `q7_death_source` | dynamic | 원내 사망만으로 사망 포함 결과 (D3) | Q7 경고 `data_source.death_source` |
| `q7_site_scope_handled` | fixed | 확인 범위가 B만 — 퇴원처 층을 다루면 경고 없음 | Q7 경고 `outcome.ascertainment.scope.sites` |
| `q7_unit_stratum` | dynamic | 측정 결과의 확인 강도 층(병동)을 다루지 않음 → 기본 설계서는 특징 이름(unit_at_tp)으로 다룸 | Q7 경고 `outcome.ascertainment.by_stratum` |
| `a_date_only` | dynamic | 날짜만 있는 열을 date_compare 없이 | 가정 A.date_only `features.proc_coded` |
| `test_temporal_split_keeps_groups_together_in_data` | fixed | D5 해석: 묶음째로, 학습 ≤ cutoff, 평가 > cutoff+gap | Q2 차단 없음 (데이터) |

## 4. 실행 시간 (본 데이터)

- 데이터 읽기(자체 로더): 2.5s
- dynamic 설계서 점검 + 데이터 확인: 평균 15.9s (최소 8.6s, 최대 17.3s, 13회)
- fixed 설계서 점검 + 데이터 확인: 평균 3.0s (최소 2.9s, 최대 3.3s, 9회)
