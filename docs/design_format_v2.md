# 설계서 형식 설명 (v2)

`designs/schema.json`의 모든 칸을 설명하고, 칸마다 근거가 된 분류 항목을 적는다.
v2 2단계에서 형식을 확정했다 (2a 151칸, 2b 예비 검수로 10칸을 보탬). 이후 단계에서 칸을 더하지 않는다.

## 근거 표기

모든 칸의 "근거"는 아래 꼬리표를 `;`로 이어 쓴다 (순서: K → P → P+AI → 기타 문헌 → 예비 검수). 시험(`tests/test_design_format_doc.py`)이 꼬리표 형식을 확인한다.

| 꼬리표 | 뜻 |
|---|---|
| `K L1.1`~`K L3.3`, `K L2` | Kapoor & Narayanan 2023 누수 분류 (`v2_plan.md` 9절 1) |
| `P 1.1`~`P 4.9` | PROBAST 2019 신호 질문 번호 (9절 3) |
| `P+AI 참여자·데이터 출처` / `예측변수` / `결과` / `분석` | PROBAST+AI 2025의 영역 (9절 2). 항목 번호는 쓰지 않는다 |
| `Albu`, `Kaufman`, `Suissa` | 9절 4, 5, 6의 문헌 |
| `예비 검수` | 2단계 2b 예비 검수에서 형식에 표현할 칸이 없다고 드러나 보탠 칸 (`docs/prereview_v2.md`의 지적 번호를 설명에 적음) |
| `관리` | 분류 항목과 무관한 식별·설명용 칸 |

경로 표기: `a.b`는 객체 안의 칸, `a[]`는 목록의 각 항목이다. 여러 곳에서 같이 쓰는 정의(행 명세 `rowset`, 전처리 단계 `step` 등)는 마지막 절에 한 번만 적는다.

시각 표기는 v1과 같다: `기준점+간격` (`tp`, `tp-48h`, `admit+24h`, `discharge+30d`, `-inf`, `inf`). 구간은 (start, end] 반열린 구간.

## 기본

| 칸 | 설명 | 근거 |
|---|---|---|
| `design_id` | 설계서 식별자 | 관리 |
| `question` | 연구 질문 (자유 서술) | 관리 |
| `notes` | 메모 | 관리 |
| `design_type` | fixed: 입원당 예측 시점 하나 / dynamic: 입원 중 여러 랜드마크 | P 2.3; P+AI 예측변수 |
| `tp` | 예측 시점 | K L3.1; P 2.3; P+AI 예측변수 |
| `tp.anchor` | 예측 시점의 기준점 (admit / discharge) | K L3.1; P 2.3; P+AI 예측변수 |
| `tp.offsets_h` | 기준점에서의 시간 간격 목록. 간격마다 예측 행 하나 | K L3.1; P 2.3; P+AI 예측변수 |
| `intended_use` | 모형의 사용 목적 | K L3.1; P+AI 참여자·데이터 출처 |
| `intended_use.purpose` | 전향 사용 / 후향 설명 / 연구용 | K L3.1; P+AI 참여자·데이터 출처 |
| `intended_use.deployment_start` | 사용을 시작할 시점 | K L3.1; P+AI 참여자·데이터 출처 |
| `intended_use.setting` | 사용할 병원·병동 | K L3.3; P+AI 참여자·데이터 출처 |

## 데이터 출처

| 칸 | 설명 | 근거 |
|---|---|---|
| `data_source` | 데이터 출처 | P 1.1; P+AI 참여자·데이터 출처 |
| `data_source.extraction_end` | 자료 추출 종료 시각 | P 1.1; P 4.6; P+AI 참여자·데이터 출처; Albu |
| `data_source.sites` | 사용한 병원 | K L3.3; P 1.1; P+AI 참여자·데이터 출처 |
| `data_source.study_period` | 연구 기간 | K L3.1; P 1.1; P+AI 참여자·데이터 출처 |
| `data_source.death_source` | 사망 정보 출처 (원내 기록만 / 사망 연계 포함) | P 3.1; P 4.6; P+AI 결과; Albu |

## 결과

| 칸 | 설명 | 근거 |
|---|---|---|
| `outcome` | 결과 정의 | P 3.1; P+AI 결과 |
| `outcome.name` | 결과 이름 | 관리 |
| `outcome.description` | 결과 설명 | 관리 |
| `outcome.definition` | 결과 계산 방식 (크레아티닌 KDIGO / 다음 입원 / 진단 코드) | P 3.1; P 3.2; P+AI 결과 |
| `outcome.prespecified` | 결과 정의를 분석 전에 정했는가 | P 3.2; P+AI 결과 |
| `outcome.definition_source` | 결과 정의의 근거 | P 3.2; P+AI 결과 |
| `outcome.source` | 결과를 정하는 행의 테이블 | P 3.1; P 3.3; P+AI 결과 |
| `outcome.filter` | 결과 행 필터 | P 3.1; P 3.3; P+AI 결과 |
| `outcome.scope` | 결과 행을 어느 입원에서 가져오나 | P 3.1; P 3.3; P+AI 결과 |
| `outcome.time_column` | 결과 창을 적용할 시각 열 | K L3.1; P 3.6; P+AI 결과 |
| `outcome.window` | 결과 사건 창 | K L3.1; P 3.6; P+AI 결과 |
| `outcome.reference_window` | 결과 판정 기준값을 읽는 구간 | P 3.3; P+AI 결과 |
| `outcome.reference` | 결과 판정 기준값의 출처 (reference_window보다 자세히) | P 3.1; P 3.4; P+AI 결과; Albu |
| `outcome.reference.sources` | 기준값 출처의 우선순위 목록 (앞 출처에 값이 없으면 다음) | P 3.1; P 3.4; P+AI 결과; Albu |
| `outcome.reference.agg` | 기준값 계산 | P 3.1; P+AI 결과 |
| `outcome.reference.compare_to` | 결과 창의 각 값을 무엇과 비교하나: 각 값보다 먼저 잰 값 / 정해진 기준값 하나 (예비 검수 B14) | P 3.1; P 3.3; P+AI 결과; 예비 검수 |
| `outcome.planned` | 예정(계획) 입원을 결과에 넣는가 | K L2; P 3.1; P+AI 결과 |
| `outcome.planned_by` | 예정(계획) 입원을 판정하는 테이블과 조건. planned와 함께 쓴다 (예비 검수 B5) | K L2; P 3.1; P+AI 결과; 예비 검수 |
| `outcome.planned_by.source` | 판정에 쓰는 테이블 | P 3.1; P+AI 결과; 예비 검수 |
| `outcome.planned_by.filter` | 예정 입원으로 보는 행 조건 (`filter`) | P 3.1; P+AI 결과; 예비 검수 |
| `outcome.match_key` | 결과 사건을 어디까지 찾나: 같은 등록 번호 / 같은 사람(person_links로 묶은 모든 등록 번호) (예비 검수 B3) | K L3.2; P 3.1; P+AI 결과; 예비 검수 |
| `outcome.pending_at_tp` | tp 전에 생겼지만 tp에는 아직 알려지지 않은 결과 사건(예: tp 전 채취, tp 뒤 보고)의 처리: 행 제외 / 결과로 셈 / 무시 (예비 검수 B27) | K L3.1; P 3.6; P+AI 결과; Albu; 예비 검수 |
| `outcome.proxies` | 결과를 정하는 과정에서 생기는 기록 | K L2; P 3.3; P 3.5; P+AI 결과; Kaufman |
| `outcome.ascertainment` | 결과 확인 방식 | K L3.3; P 3.4; P+AI 결과 |
| `outcome.ascertainment.method` | 확인 방식 설명 | K L3.3; P 3.4; P+AI 결과 |
| `outcome.ascertainment.by_stratum` | 확인 강도 차이를 층별로 다룬 열 | K L3.3; P 3.4; P+AI 결과 |
| `outcome.ascertainment.scope` | 결과 확인 범위: 결과 사건을 어디서 찾았나 | K L3.3; P 3.1; P 3.4; P+AI 결과; Albu |
| `outcome.ascertainment.scope.sites` | 결과를 찾은 병원 | K L3.3; P 3.1; P 3.4; P+AI 결과; Albu |
| `outcome.ascertainment.scope.settings` | 결과를 찾은 진료 형태 (입원 / 외래) | P 3.1; P 3.4; P+AI 결과; Albu |
| `outcome.ascertainment.scope.sources` | 결과를 찾은 테이블 | P 3.1; P 3.4; P+AI 결과; Albu |
| `outcome.ascertainment.min_followup` | 결과 확인에 필요한 최소 추적 | P 3.6; P 4.6; P+AI 결과 |
| `outcome.ascertainment.blind_to_predictors` | 예측변수를 모른 채 결과를 정했는가 | P 3.5; P+AI 결과 |
| `outcome.history` | 연구 기간 중 결과 정의·측정법·코드 체계가 바뀐 이력 | P 3.4; P+AI 결과; Albu |
| `outcome.history[].from` | 변경 전 기간 시작 | P 3.4; P+AI 결과; Albu |
| `outcome.history[].to` | 변경 전 기간 끝 | P 3.4; P+AI 결과; Albu |
| `outcome.history[].change` | 무엇이 바뀌었나 | P 3.4; P+AI 결과; Albu |
| `outcome.history[].handled` | 분석에서 어떻게 다뤘나 | P 3.4; P+AI 결과; Albu |
| `outcome.censoring` | 결과 창을 끝까지 보지 못한 행의 처리 | P 3.6; P 4.6; P+AI 분석 |
| `outcome.censoring.end_of_data` | 자료 추출 종료로 결과 창이 잘린 행 | P 3.6; P 4.6; P+AI 분석; Albu |
| `outcome.censoring.death` | 결과 창 안 사망 (제외 / 음성 / 복합 결과 / 경쟁 위험) | P 4.6; P+AI 분석; Albu; Suissa |
| `outcome.censoring.lost_to_followup` | 추적 소실 | P 4.6; P+AI 분석 |

## 코호트

| 칸 | 설명 | 근거 |
|---|---|---|
| `cohort` | 포함·제외와 표본 | K L3.3; P 1.2; P+AI 참여자·데이터 출처 |
| `cohort.index_time` | 포함·제외를 정하는 기준 시점 | K L3.3; P 1.2; P+AI 참여자·데이터 출처; Suissa |
| `cohort.inclusion` | 포함 기준 목록 (`criterion`) | K L3.3; P 1.2; P+AI 참여자·데이터 출처; Suissa |
| `cohort.exclusion` | 제외 기준 목록 (`criterion`) | K L3.3; P 1.2; P+AI 참여자·데이터 출처; Suissa |
| `cohort.subgroups` | 결과율·확인 강도를 따로 볼 하위 집단 열 | K L3.3; P 3.4; P+AI 결과 |
| `cohort.sampling` | 표본 추출 방식 | K L3.3; P 1.1; P 4.6; P+AI 참여자·데이터 출처 |
| `cohort.sampling.method` | 전체 / 무작위 / 층화 / 환자-대조 / 결과 기준 보강 | K L3.3; P 1.1; P 4.6; P+AI 참여자·데이터 출처 |
| `cohort.sampling.by` | 층화·짝짓기 열 | K L3.3; P 4.6; P+AI 참여자·데이터 출처 |
| `cohort.sampling.fraction` | 추출 비율 | K L3.3; P 4.6; P+AI 참여자·데이터 출처 |
| `cohort.sampling.ratio` | 대조:사례 비 | K L3.3; P 4.6; P+AI 참여자·데이터 출처 |
| `cohort.sampling.uses_outcome` | 추출에 결과를 썼는가 | K L3.3; P 4.6; P+AI 참여자·데이터 출처 |
| `cohort.sampling.applies_to` | 개발·평가 중 어디에 적용했나 | K L3.3; P 4.7; P+AI 분석 |
| `cohort.rows_per_unit` | 단위마다 몇 행을 쓰나 | K L3.2; P 4.6; P+AI 분석 |
| `cohort.rows_per_unit.unit` | 단위 (입원 / 에피소드 / 환자 / 사람) | K L3.2; P 4.6; P+AI 분석 |
| `cohort.rows_per_unit.choose` | 전체 / 첫 / 마지막 / 무작위 하나 | K L3.2; P 4.6; P+AI 분석 |
| `cohort.deduplication` | 중복 레코드 처리 | K L1.4; P+AI 분석; Albu |
| `cohort.deduplication.key` | 중복 판정 키 | K L1.4; P+AI 분석; Albu |
| `cohort.deduplication.when` | 분할 전 / 분할 안 / 하지 않음 | K L1.4; P+AI 분석 |

## 특징

| 칸 | 설명 | 근거 |
|---|---|---|
| `features` | 특징 목록 (`rowset`) | K L2; P 2.3; P+AI 예측변수 |

## 분할

| 칸 | 설명 | 근거 |
|---|---|---|
| `split_unit` | 독립 단위: index_row < admission < episode < patient < person < family | K L3.2; P 4.6; P+AI 분석 |
| `split` | 학습·평가 분할 | K L1.1; K L3.2; P+AI 분석 |
| `split.key` | 분할 묶음 열 | K L3.2; P+AI 분석 |
| `split.fallback_key` | key가 결측인 행에 쓸 열 | K L3.2; P 4.4; P+AI 분석 |
| `split.method` | group_holdout / group_kfold / random_rows / temporal | K L1.1; K L3.1; K L3.2; P+AI 분석 |
| `split.time_column` | 시간 순 분할의 기준 시각 열 | K L3.1; P+AI 분석 |
| `split.cutoff` | 시간 순 분할 경계 시각 | K L3.1; P+AI 분석 |
| `split.gap` | 학습 끝과 평가 시작 사이 간격 | K L3.1; P+AI 분석 |
| `split.by_site` | 병원별로 나눴는가 | K L3.3; P+AI 분석 |
| `split.test_fraction` | 평가 부분 비율 | K L1.1; P 4.8; P+AI 분석 |
| `split.n_folds` | 교차검증 폴드 수 | K L1.1; P 4.8; P+AI 분석 |
| `split.seed` | 난수 시드 | K L1.1; P 4.8; P+AI 분석 |

## 전처리·모형·평가

| 칸 | 설명 | 근거 |
|---|---|---|
| `preprocessing` | 전처리 단계 목록 (`step`) | K L1.2; K L1.3; P+AI 분석 |
| `model` | 모형 | P 4.8; P+AI 분석 |
| `model.family` | 모형 종류 | P 4.8; P+AI 분석 |
| `model.tuning` | 초매개변수 조율 | K L1.1; P 4.8; P+AI 분석 |
| `model.tuning.method` | 조율 방법 | K L1.1; P 4.8; P+AI 분석 |
| `model.tuning.cv_key` | 내부 교차검증의 묶음 열 | K L3.2; P 4.8; P+AI 분석 |
| `model.tuning.fit_scope` | 조율에 쓴 데이터 | K L1.1; P 4.8; P+AI 분석 |
| `model.selection` | 모형 종류·초매개변수를 고른 데이터 (`data_use`) | K L1.1; P 4.8; P+AI 분석 |
| `model.early_stopping` | 조기 종료에 쓴 데이터 (`data_use`) | K L1.1; P 4.8; P+AI 분석 |
| `model.threshold` | 분류 임계값을 정한 데이터 (`data_use`) | K L1.1; P 4.7; P+AI 분석 |
| `model.calibration` | 보정에 쓴 데이터 (`data_use`) | K L1.1; P 4.7; P+AI 분석 |
| `analysis` | 분석 처리 | P 4.4; P+AI 분석 |
| `analysis.missing_data` | 결측 처리 | P 4.3; P 4.4; P+AI 분석 |
| `analysis.missing_data.method` | 완전 사례 / 대치 / 결측 표시 / 없음 | P 4.4; P+AI 분석 |
| `analysis.missing_data.drop_rows_when` | 결측 행을 지우는 시점 | K L1.2; P 4.3; P+AI 분석 |
| `analysis.missing_data.outcome_missing` | 결과가 결측인 행 | P 4.3; P+AI 분석 |
| `evaluation` | 성능 평가 | K L1.1; P 4.7; P 4.8; P+AI 분석 |
| `evaluation.data` | 성능을 계산한 데이터 | K L1.1; P 4.8; P+AI 분석 |
| `evaluation.metrics` | 지표 | P 4.7; P+AI 분석 |
| `evaluation.test_set_uses` | 평가 부분으로 성능을 본 횟수 | K L1.1; P 4.8; P+AI 분석 |
| `evaluation.subgroups` | 하위집단 보고 | P 4.7; P+AI 분석 |
| `evaluation.calibration_reported` | 보정 보고 | P 4.7; P+AI 분석 |
| `attempts` | 다중 시도 | P 4.8; P+AI 분석 |
| `attempts.n_designs_tried` | 시도한 설계 수 | P 4.8; P+AI 분석 |
| `attempts.n_models_tried` | 시도한 모형 수 | P 4.8; P+AI 분석 |
| `attempts.correction` | 다중 시도 보정 방법 | P 4.8; P+AI 분석 |

## 공통 정의 (`$defs`)

| 칸 | 설명 | 근거 |
|---|---|---|
| `filter` | 열 → 허용 값 목록. 코드 열은 앞부분 일치 | P 2.1; P+AI 예측변수 |
| `scope` | 행을 어느 입원에서 가져오나 (patient / index_admission / prior_admissions / next_admission / patient_history) | K L3.1; P 2.3; P+AI 예측변수 |
| `fit_scope` | 추정·결정에 쓴 데이터 (train / train_fold / validation / all / train+test / test) | K L1.1; K L1.2; P+AI 분석 |
| `window.start` | 구간 시작 | K L3.1; P 2.3; P+AI 예측변수 |
| `window.end` | 구간 끝 | K L3.1; P 2.3; P+AI 예측변수 |
| `period.start` | 기간 시작 | K L3.1; P 1.1; P+AI 참여자·데이터 출처 |
| `period.end` | 기간 끝 | K L3.1; P 1.1; P+AI 참여자·데이터 출처 |
| `rowset.name` | 이름 | 관리 |
| `rowset.description` | 설명 | 관리 |
| `rowset.source` | 원본 테이블. 없으면 출처 불명 | K L2; P 2.3; P+AI 예측변수 |
| `rowset.column` | 값 열 (없으면 테이블 기본 값 열) | K L2; P 2.3; P+AI 예측변수 |
| `rowset.filter` | 행 필터 | P 2.1; P+AI 예측변수 |
| `rowset.scope` | 행을 어느 입원에서 가져오나 | K L3.1; P 2.3; P+AI 예측변수 |
| `rowset.time_column` | 창을 적용할 시각 열 | K L3.1; P 2.3; P+AI 예측변수; Albu |
| `rowset.window` | 시간 창 | K L3.1; P 2.3; P+AI 예측변수 |
| `rowset.date_compare` | 날짜만 있는 시각을 tp와 비교하는 규칙 (그날 끝 / 그날 시작 / 날짜끼리) | K L3.1; P 2.3; P+AI 예측변수; Albu |
| `rowset.as_of` | 수정 이력이 있는 기록을 어느 시점 내용으로 읽나 (tp 시점 / 최종본) | K L3.1; P 2.3; P+AI 예측변수; Albu |
| `rowset.version_order` | as_of로 버전을 고르는 것과 filter를 거는 것의 순서 (예비 검수 B26) | K L3.1; P 2.3; P+AI 예측변수; Albu; 예비 검수 |
| `rowset.episode` | 이어진 입원(같은 episode_id) 처리: 이번 입원 기록만 / 같은 에피소드의 tp까지 모든 입원 기록 / 같은 에피소드의 입원을 뺌 (이전 입원 집계용) (예비 검수 B8, B24) | K L3.2; P 2.3; P+AI 예측변수; Albu; 예비 검수 |
| `rowset.history_key` | 환자 단위 범위(patient, prior_admissions, patient_history)의 행을 무엇으로 묶나: 같은 등록 번호 / 같은 사람 (예비 검수 B23) | K L1.4; K L3.2; P 2.3; P+AI 예측변수; 예비 검수 |
| `rowset.age_reference` | patients.age를 어느 시점 나이로 쓰나: 그 등록 번호의 첫 입원 때 값 / 인덱스 입원 때 나이(age + 첫 입원부터 경과 연수) (예비 검수 B21) | P 2.3; P+AI 예측변수; 예비 검수 |
| `rowset.agg` | 집계 (value, last, first, max, min, mean, count, any, kdigo_aki, delta, range, slope) | P 2.1; P 4.2; P+AI 예측변수 |
| `rowset.derive` | 다른 특징·값으로 만든 파생 특징 | K L2; P 2.1; P 3.3; P+AI 예측변수; Kaufman |
| `rowset.derive.op` | 비율 / 차이 / 합 / 곱 | K L2; P 2.1; P+AI 예측변수 |
| `rowset.derive.of` | 쓰인 특징 이름 | K L2; P 2.1; P 3.3; P+AI 예측변수 |
| `rowset.made_by` | 출처 기록 (다르면 출처 불명) | P 2.1; P+AI 예측변수 |
| `rowset.fit_scope` | 특징 계산에 쓴 추정값의 범위 | K L1.2; P+AI 분석 |
| `rowset.assessment` | 측정 방식이 집단마다 다른가 | P 2.1; P 2.2; P+AI 예측변수 |
| `rowset.assessment.by_stratum` | 측정 방식이 다른 층 | P 2.1; P+AI 예측변수 |
| `rowset.assessment.method` | 측정 방식 설명 | P 2.1; P 2.2; P+AI 예측변수 |
| `criterion.op` | 비교 연산 | K L3.3; P 1.2; P+AI 참여자·데이터 출처 |
| `criterion.value` | 비교 값 | K L3.3; P 1.2; P+AI 참여자·데이터 출처 |
| `proxy.source` | 대리 기록의 테이블 | K L2; P 3.3; P+AI 결과; Kaufman |
| `proxy.filter` | 대리 기록 필터 | K L2; P 3.3; P+AI 결과 |
| `proxy.basis` | 대리 기록으로 본 근거 | K L2; P 3.3; P+AI 결과 |
| `step.name` | 단계 이름 | 관리 |
| `step.kind` | 대치·표준화·절단·선택·인코딩·재표본 추출·차원 축소·변환 | K L1.2; K L1.3; P 4.4; P 4.5; P+AI 분석 |
| `step.method` | 방법 (예: 대치 median / mean / constant / forward_fill / backward_fill / interpolate, 인코딩 one_hot / target, 재표본 oversample / undersample / smote) | K L1.2; K L3.1; P 4.4; P+AI 분석; Kaufman |
| `step.stateless` | 데이터에서 아무것도 추정하지 않는 단계 | K L1.2; P+AI 분석 |
| `step.fit_scope` | 추정에 쓴 데이터 | K L1.2; K L1.3; P 4.5; P+AI 분석 |
| `step.applies_to` | 적용한 데이터 | K L1.2; P 4.6; P+AI 분석 |
| `step.before_split` | 분할 전에 했는가 | K L1.2; P+AI 분석 |
| `step.uses_outcome` | 결과값을 썼는가 | K L1.3; P 4.5; P+AI 분석 |
| `step.columns` | 대상 열 | K L1.2; P+AI 분석 |
| `data_use.method` | 방법 | K L1.1; P 4.8; P+AI 분석 |
| `data_use.fit_scope` | 쓴 데이터 | K L1.1; P 4.8; P+AI 분석 |
| `data_use.metric` | 고를 때 본 지표 | P 4.7; P+AI 분석 |
