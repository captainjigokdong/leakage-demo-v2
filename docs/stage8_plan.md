# 8단계 계획 — 누수 효과 시연 (보조 분석)

사용자 승인 2026-10-07. **학습 전에 커밋한다.** 이 문서를 고친 뒤 학습했다면 커밋 순서로 드러난다.
v2 판정(H1·H2)과 무관한 보조 분석이다. 7단계 채점 결과, 판정, `results/report.md`, 잠긴 파일 7개, 동결 폴더(`leakcheck/`, `skill_src/`, `designs/schema.json`)는 고치지 않는다. 결과는 `results/stage8/`에 따로 둔다.

## 1. 지키는 것

a. 효과가 작거나 예상과 달라도 **조건, 시드, 특징, 설정을 바꿔 다시 돌리지 않는다.** 바꾸면 별도 파일에 "사후 분석"으로 표시한다.
b. `designs/variants/`, `sealed/`, `experiment/runs/`를 읽지 않는다. 변형끼리, 변형과 깨끗한 설계서를 비교하지 않는다. 에이전트를 띄우지 않는다.
- 결정 잠금: 설계 × 시드마다 결정 카드 → 승인 → 잠금 뒤에만 `leakcheck.lock.auroc`로 AUROC를 계산한다. 승인자 문구 "사용자 (8단계 계획 승인 2026-10-07, 누수 효과 시연용 설계 일괄 승인)".
- 특징은 `leakcheck.features.make_feature`로만 만든다 (출처 불명 열이 생기면 멈춤).
- 해석은 절대값이 아니라 수정 설계(또는 참조 조건) 대비 AUROC 차이로 한다. 합성 데이터라 임상적 의미는 없다.

## 2. 데이터와 설계

| 묶음 | 데이터 | 설계 | 조건 |
|---|---|---|---|
| 본-고정 | `data/synth` (v2 본 데이터) | `designs/base/fixed_readmission.json` (v1) | 수정, F1, F2, F3, F4, 모두(F1~F4), **F4 참조** |
| 본-동적 | `data/synth` | `designs/base/dynamic_aki.json` (v1) | 수정, D1~D6, 모두(D1~D6), **D5 참조** |
| 보조-B | `data/synth_aux` (200명, 검사 500종) | `designs/base/dynamic_aki.json` (v1 그대로) | 수정, D4, D5, D4+D5, **D5 참조** |
| 보조-A | `data/synth_aux` | `experiment/stage8/dynamic_aki_aux500.json` | 수정, D4, D5, D4+D5, **D5 참조** |

- 데이터는 v2 로더 `leakcheck.data.load(folder)`로 읽는다.
- 누수 조건 F1~F4, D1~D6은 v1 `docs/step7_analysis_plan.md` 4.1과 같다 (`experiment/leakage_effect.py`의 `LEAKS`).
- **g. 보조-A는 v1 설계가 아니라 8단계 시연용 설계다.** v1 동적 AKI 설계(특징 10개)에 특징 500개를 더했다: 검사 `t001`~`t500` 각각에 대해 `labs`, 시각 열 `report_time`(확인 가능 시각), 창 입원 ~ tₚ, agg `last` (tₚ 이전에 보고된 값 중 보고 시각이 가장 늦은 값). 그 밖(코호트, 결과, 분할, 전처리, 모델)은 v1 설계와 같다.
- 보조 데이터의 고정 시점(30일 재입원) 설계는 실행하지 않는다: 1인당 입원 1회라 결과 양성이 0 (194행 중 0). "보조 데이터에서 표현 안 됨"으로 기록한다.
- **e. 참조 조건**: v1 수정 설계에는 특징 선택 단계가 없다. 그래서 F4·D5와 같은 방법·개수의 특징 선택을 **학습 집합에서만** 적합한 조건(F4 참조, D5 참조)을 더한다. 특징 선택이 들어간 조건(F4, 모두(본-고정), D5, 모두(본-동적), D4+D5)은 수정 설계 대비 차이(v1 방식)와 참조 대비 차이를 둘 다 보고한다. "모두"의 참조 대비 차이는 F4 참조/D5 참조를 기준으로 한다 (특징 열 수가 달라 k도 다르다는 점을 표에 적는다).

## 3. 전처리 (v1 규칙 그대로)

- 중앙값 대치 → (고정 시점만) 원-핫 → 표준화. `fit_scope`가 train이면 학습 행만, all이면 시험 행 포함으로 적합.
- **d. 특징 선택**: 단변량 F 검정(`sklearn.feature_selection.f_classif`) 상위 k개, k = 전처리 뒤 열 수의 절반(올림). 열 수는 사전 점검(성능·관련성 계산 없이 행렬 모양만)에서 셌다.

| 묶음 | 조건 | 특징 수 | 전처리 뒤 열 수 | k |
|---|---|---|---|---|
| 본-고정 | F4, F4 참조 | 12 | 15 | 8 |
| 본-고정 | 모두 | 13 | 18 | 9 |
| 본-동적 | D5, D5 참조 | 10 | 12 | 6 |
| 본-동적 | 모두 | 13 | 15 | 8 |
| 보조-B | D5, D4+D5, D5 참조 | 10 | 12 | 6 |
| 보조-A | D5, D4+D5, D5 참조 | 510 | 512 | 256 |

- **f. 전부 비어 있는 열**: 보조 데이터에는 bun, potassium, hemoglobin 검사가 없어 `bun_last`, `k_last`, `hgb_min` 3열이 모든 행에서 비어 있다 (보조-A·B 모두). 설계를 고치지 않고 그대로 둔다. 처리: 중앙값이 없으므로 0으로 채움 → 상수 열 → 표준화에서 표준편차 0은 1로 나눔(0 유지) → 특징 선택의 F 값은 NaN → 0으로 바꿔 순위 맨 아래. 열 수(k 계산)에는 들어간다. 이 3열은 "계획에 없던 특징 누락"으로 세지 않는다.

## 4. 모델, 시드, 지표

- 모델: 로지스틱 회귀(`LogisticRegression(max_iter=3000)`), HistGradientBoosting(`random_state` = 분할 시드), TPOT 1.1.0.
- 시드(분할 시드 = 20261002 + 단계): 본 데이터 로지스틱·부스팅 5개(0~4). **보조 데이터 로지스틱·부스팅 20개(0~19).**
- **c. TPOT 설정 (v1과 같은 값)**: `search_space="linear"`, `scorers=["roc_auc"]`, `generations=5`, `population_size=12`, `max_time_mins=5`, `max_eval_time_mins=1`, `n_jobs=4`, `processes=False`, `random_state=20261002`(시드 1개, 단계 0), `cv` = 학습 집합 안에서 가족 단위로 미리 나눈 조각 5개.
- TPOT 실행: 수정 설계와 "모두"(본-고정, 본-동적), 수정 설계와 D4+D5(보조-A, 보조-B). 모두 8회.
- 지표: 시험 집합 AUROC. 조건별 평균, 범위(최소~최대), 시드별 값, 수정 설계 대비 차이(시드별 짝 차이의 평균·범위), 특징 선택 조건은 참조 대비 차이도.
- 분할: 가족 단위 group holdout, 시험 30% (`leakcheck.splitting.assign`). 분할 누수 조건(F2, D3)만 학습·시험이 그 누수 분할로 바뀐다.
- TPOT 조각 점검(실행마다 기록): 조각 사이에 걸친 가족 수, 조각 분할 함수 호출 수, TPOT가 넘긴 조각 객체를 그대로 썼는지, 고른 파이프라인, 걸린 시간.

## 5. 설치

`SETUPTOOLS_USE_DISTUTILS=stdlib pip install tpot==1.1.0 matplotlib`. 설치한 버전과 Python 3.13.16을 `requirements-stage8-lock.txt`에 적는다. `requirements-lock.txt`는 바꾸지 않는다.

## 6. 멈추는 조건

- TPOT 조각 사이에 걸친 가족 수 ≠ 0, 또는 조각이 쓰이지 않음
- 수정 설계에서 학습·시험 양쪽에 든 가족 수 ≠ 0
- 출처 불명 열, 계획에 없던 특징 누락(위 3열 제외), 결정 잠금 오류
- tpot·matplotlib 설치 실패, 또는 설치 뒤 `requirements-lock.txt`에 적힌 패키지 버전이 하나라도 바뀜
- 설치 뒤 시험이 통과 626 / 건너뜀 8 / 실패 0이 아님 (8단계 시험 추가 전 기준)
- TPOT 1회가 10분 초과
- 잠긴 파일, 동결 폴더, `results/`의 7단계 파일, `experiment/runs/`, `sealed/`에 변경이 생김

## 7. 산출물

- `results/stage8/leakage_effect_{main,aux_A,aux_B}.json` (실행별 기록 + 요약)
- `results/stage8/leakage_effect_*.png` (그림), `results/stage8/leakage_effect.md` (표, 표현 안 된 항목, TPOT 점검)
