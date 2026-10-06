# 설계서 형식 설명

설계서(JSON)의 모든 칸을 설명한다.

경로 표기: `a.b`는 객체 안의 칸, `a[]`는 목록의 각 항목이다. 여러 곳에서 같이 쓰는 정의(행 명세 `rowset`, 전처리 단계 `step` 등)는 마지막 절에 한 번만 적는다.

시각 표기: `기준점+간격` (`tp`, `tp-48h`, `admit+24h`, `discharge+30d`, `-inf`, `inf`). 구간은 (start, end] 반열린 구간.

## 기본

| 칸 | 설명 |
|---|---|
| `design_id` | 설계서 식별자 |
| `question` | 연구 질문 (자유 서술) |
| `notes` | 메모 |
| `design_type` | fixed: 입원당 예측 시점 하나 / dynamic: 입원 중 여러 랜드마크 |
| `tp` | 예측 시점 |
| `tp.anchor` | 예측 시점의 기준점 (admit / discharge) |
| `tp.offsets_h` | 기준점에서의 시간 간격 목록. 간격마다 예측 행 하나 |
| `intended_use` | 모형의 사용 목적 |
| `intended_use.purpose` | 전향 사용 / 후향 설명 / 연구용 |
| `intended_use.deployment_start` | 사용을 시작할 시점 |
| `intended_use.setting` | 사용할 병원·병동 |

## 데이터 출처

| 칸 | 설명 |
|---|---|
| `data_source` | 데이터 출처 |
| `data_source.extraction_end` | 자료 추출 종료 시각 |
| `data_source.sites` | 사용한 병원 |
| `data_source.study_period` | 연구 기간 |
| `data_source.death_source` | 사망 정보 출처 (원내 기록만 / 사망 연계 포함) |

## 결과

| 칸 | 설명 |
|---|---|
| `outcome` | 결과 정의 |
| `outcome.name` | 결과 이름 |
| `outcome.description` | 결과 설명 |
| `outcome.definition` | 결과 계산 방식 (크레아티닌 KDIGO / 다음 입원 / 진단 코드) |
| `outcome.prespecified` | 결과 정의를 분석 전에 정했는가 |
| `outcome.definition_source` | 결과 정의의 근거 |
| `outcome.source` | 결과를 정하는 행의 테이블 |
| `outcome.filter` | 결과 행 필터 |
| `outcome.scope` | 결과 행을 어느 입원에서 가져오나 |
| `outcome.time_column` | 결과 창을 적용할 시각 열 |
| `outcome.window` | 결과 사건 창 |
| `outcome.reference_window` | 결과 판정 기준값을 읽는 구간 |
| `outcome.reference` | 결과 판정 기준값의 출처 (reference_window보다 자세히) |
| `outcome.reference.sources` | 기준값 출처의 우선순위 목록 (앞 출처에 값이 없으면 다음) |
| `outcome.reference.agg` | 기준값 계산 |
| `outcome.reference.compare_to` | 결과 창의 각 값을 무엇과 비교하나: 각 값보다 먼저 잰 값 / 정해진 기준값 하나 |
| `outcome.planned` | 예정(계획) 입원을 결과에 넣는가 |
| `outcome.planned_by` | 예정(계획) 입원을 판정하는 테이블과 조건. planned와 함께 쓴다 |
| `outcome.planned_by.source` | 판정에 쓰는 테이블 |
| `outcome.planned_by.filter` | 예정 입원으로 보는 행 조건 (`filter`) |
| `outcome.match_key` | 결과 사건을 어디까지 찾나: 같은 등록 번호 / 같은 사람(person_links로 묶은 모든 등록 번호) |
| `outcome.pending_at_tp` | tp 전에 생겼지만 tp에는 아직 알려지지 않은 결과 사건(예: tp 전 채취, tp 뒤 보고)의 처리: 행 제외 / 결과로 셈 / 무시 |
| `outcome.proxies` | 결과를 정하는 과정에서 생기는 기록 |
| `outcome.ascertainment` | 결과 확인 방식 |
| `outcome.ascertainment.method` | 확인 방식 설명 |
| `outcome.ascertainment.by_stratum` | 확인 강도 차이를 층별로 다룬 열 |
| `outcome.ascertainment.scope` | 결과 확인 범위: 결과 사건을 어디서 찾았나 |
| `outcome.ascertainment.scope.sites` | 결과를 찾은 병원 |
| `outcome.ascertainment.scope.settings` | 결과를 찾은 진료 형태 (입원 / 외래) |
| `outcome.ascertainment.scope.sources` | 결과를 찾은 테이블 |
| `outcome.ascertainment.min_followup` | 결과 확인에 필요한 최소 추적 |
| `outcome.ascertainment.blind_to_predictors` | 예측변수를 모른 채 결과를 정했는가 |
| `outcome.history` | 연구 기간 중 결과 정의·측정법·코드 체계가 바뀐 이력 |
| `outcome.history[].from` | 변경 전 기간 시작 |
| `outcome.history[].to` | 변경 전 기간 끝 |
| `outcome.history[].change` | 무엇이 바뀌었나 |
| `outcome.history[].handled` | 분석에서 어떻게 다뤘나 |
| `outcome.censoring` | 결과 창을 끝까지 보지 못한 행의 처리 |
| `outcome.censoring.end_of_data` | 자료 추출 종료로 결과 창이 잘린 행 |
| `outcome.censoring.death` | 결과 창 안 사망 (제외 / 음성 / 복합 결과 / 경쟁 위험) |
| `outcome.censoring.lost_to_followup` | 추적 소실 |

## 코호트

| 칸 | 설명 |
|---|---|
| `cohort` | 포함·제외와 표본 |
| `cohort.index_time` | 포함·제외를 정하는 기준 시점 |
| `cohort.inclusion` | 포함 기준 목록 (`criterion`) |
| `cohort.exclusion` | 제외 기준 목록 (`criterion`) |
| `cohort.subgroups` | 결과율·확인 강도를 따로 볼 하위 집단 열 |
| `cohort.sampling` | 표본 추출 방식 |
| `cohort.sampling.method` | 전체 / 무작위 / 층화 / 환자-대조 / 결과 기준 보강 |
| `cohort.sampling.by` | 층화·짝짓기 열 |
| `cohort.sampling.fraction` | 추출 비율 |
| `cohort.sampling.ratio` | 대조:사례 비 |
| `cohort.sampling.uses_outcome` | 추출에 결과를 썼는가 |
| `cohort.sampling.applies_to` | 개발·평가 중 어디에 적용했나 |
| `cohort.rows_per_unit` | 단위마다 몇 행을 쓰나 |
| `cohort.rows_per_unit.unit` | 단위 (입원 / 에피소드 / 환자 / 사람) |
| `cohort.rows_per_unit.choose` | 전체 / 첫 / 마지막 / 무작위 하나 |
| `cohort.deduplication` | 중복 레코드 처리 |
| `cohort.deduplication.key` | 중복 판정 키 |
| `cohort.deduplication.when` | 분할 전 / 분할 안 / 하지 않음 |

## 특징

| 칸 | 설명 |
|---|---|
| `features` | 특징 목록 (`rowset`) |

## 분할

| 칸 | 설명 |
|---|---|
| `split_unit` | 서로 독립으로 보는 묶음의 단위: index_row < admission < episode < patient < person < family |
| `split` | 학습·평가 분할 |
| `split.key` | 분할 묶음 열 |
| `split.fallback_key` | key가 결측인 행에 쓸 열 |
| `split.method` | group_holdout / group_kfold / random_rows / temporal |
| `split.time_column` | 시간 순 분할의 기준 시각 열 |
| `split.cutoff` | 시간 순 분할 경계 시각 |
| `split.gap` | 학습 끝과 평가 시작 사이 간격 |
| `split.by_site` | 병원별로 나눴는가 |
| `split.test_fraction` | 평가 부분 비율 |
| `split.n_folds` | 교차검증 폴드 수 |
| `split.seed` | 난수 시드 |

## 전처리·모형·평가

| 칸 | 설명 |
|---|---|
| `preprocessing` | 전처리 단계 목록 (`step`) |
| `model` | 모형 |
| `model.family` | 모형 종류 |
| `model.tuning` | 초매개변수 조율 |
| `model.tuning.method` | 조율 방법 |
| `model.tuning.cv_key` | 내부 교차검증의 묶음 열 |
| `model.tuning.fit_scope` | 조율에 쓴 데이터 |
| `model.selection` | 모형 종류·초매개변수를 고른 데이터 (`data_use`) |
| `model.early_stopping` | 조기 종료에 쓴 데이터 (`data_use`) |
| `model.threshold` | 분류 임계값을 정한 데이터 (`data_use`) |
| `model.calibration` | 보정에 쓴 데이터 (`data_use`) |
| `analysis` | 분석 처리 |
| `analysis.missing_data` | 결측 처리 |
| `analysis.missing_data.method` | 완전 사례 / 대치 / 결측 표시 / 없음 |
| `analysis.missing_data.drop_rows_when` | 결측 행을 지우는 시점 |
| `analysis.missing_data.outcome_missing` | 결과가 결측인 행 |
| `evaluation` | 성능 평가 |
| `evaluation.data` | 성능을 계산한 데이터 |
| `evaluation.metrics` | 지표 |
| `evaluation.test_set_uses` | 평가 부분으로 성능을 본 횟수 |
| `evaluation.subgroups` | 하위집단 보고 |
| `evaluation.calibration_reported` | 보정 보고 |
| `attempts` | 다중 시도 |
| `attempts.n_designs_tried` | 시도한 설계 수 |
| `attempts.n_models_tried` | 시도한 모형 수 |
| `attempts.correction` | 다중 시도 보정 방법 |

## 공통 정의 (`$defs`)

| 칸 | 설명 |
|---|---|
| `filter` | 열 → 허용 값 목록. 코드 열은 앞부분 일치 |
| `scope` | 행을 어느 입원에서 가져오나 (patient / index_admission / prior_admissions / next_admission / patient_history) |
| `fit_scope` | 추정·결정에 쓴 데이터 (train / train_fold / validation / all / train+test / test) |
| `window.start` | 구간 시작 |
| `window.end` | 구간 끝 |
| `period.start` | 기간 시작 |
| `period.end` | 기간 끝 |
| `rowset.name` | 이름 |
| `rowset.description` | 설명 |
| `rowset.source` | 원본 테이블. 없으면 출처 불명 |
| `rowset.column` | 값 열 (없으면 테이블 기본 값 열) |
| `rowset.filter` | 행 필터 |
| `rowset.scope` | 행을 어느 입원에서 가져오나 |
| `rowset.time_column` | 창을 적용할 시각 열 |
| `rowset.window` | 시간 창 |
| `rowset.date_compare` | 날짜만 있는 시각을 tp와 비교하는 규칙 (그날 끝 / 그날 시작 / 날짜끼리) |
| `rowset.as_of` | 수정 이력이 있는 기록을 어느 시점 내용으로 읽나 (tp 시점 / 최종본) |
| `rowset.version_order` | as_of로 버전을 고르는 것과 filter를 거는 것의 순서 |
| `rowset.episode` | 이어진 입원(같은 episode_id) 처리: 이번 입원 기록만 / 같은 에피소드의 tp까지 모든 입원 기록 / 같은 에피소드의 입원을 뺌 (이전 입원 집계용) |
| `rowset.history_key` | 환자 단위 범위(patient, prior_admissions, patient_history)의 행을 무엇으로 묶나: 같은 등록 번호 / 같은 사람 |
| `rowset.age_reference` | patients.age를 어느 시점 나이로 쓰나: 그 등록 번호의 첫 입원 때 값 / 인덱스 입원 때 나이(age + 첫 입원부터 경과 연수) |
| `rowset.agg` | 집계 (value, last, first, max, min, mean, count, any, kdigo_aki, delta, range, slope) |
| `rowset.derive` | 다른 특징·값으로 만든 파생 특징 |
| `rowset.derive.op` | 비율 / 차이 / 합 / 곱 |
| `rowset.derive.of` | 쓰인 특징 이름 |
| `rowset.made_by` | 출처 기록 (다르면 출처 불명) |
| `rowset.fit_scope` | 특징 계산에 쓴 추정값의 범위 |
| `rowset.assessment` | 측정 방식이 집단마다 다른가 |
| `rowset.assessment.by_stratum` | 측정 방식이 다른 층 |
| `rowset.assessment.method` | 측정 방식 설명 |
| `criterion.op` | 비교 연산 |
| `criterion.value` | 비교 값 |
| `proxy.source` | 대리 기록의 테이블 |
| `proxy.filter` | 대리 기록 필터 |
| `proxy.basis` | 대리 기록으로 본 근거 |
| `step.name` | 단계 이름 |
| `step.kind` | 대치·표준화·절단·선택·인코딩·재표본 추출·차원 축소·변환 |
| `step.method` | 방법 (예: 대치 median / mean / constant / forward_fill / backward_fill / interpolate, 인코딩 one_hot / target, 재표본 oversample / undersample / smote) |
| `step.stateless` | 데이터에서 아무것도 추정하지 않는 단계 |
| `step.fit_scope` | 추정에 쓴 데이터 |
| `step.applies_to` | 적용한 데이터 |
| `step.before_split` | 분할 전에 했는가 |
| `step.uses_outcome` | 결과값을 썼는가 |
| `step.columns` | 대상 열 |
| `data_use.method` | 방법 |
| `data_use.fit_scope` | 쓴 데이터 |
| `data_use.metric` | 고를 때 본 지표 |
