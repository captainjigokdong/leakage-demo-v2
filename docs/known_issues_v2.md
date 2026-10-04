# 알려진 문제 (v2)

`skill-frozen-v2` 태그 뒤에 `leakcheck/`, `skill_src/`에서 발견한 버그는 고치지 않고 여기에 적는다 (CLAUDE.md 절대 규칙 3).
각 항목: 날짜, 발견 경위, 증상, 영향받는 질문(Q), 채점에 미치는 영향.

## 동결 시점에 알고 있는 한계 (3단계, 2026-10-04)

### 점검기를 만든 방식

- **원리를 공개 사례를 본 상태에서 썼다.** 3단계 점검기의 원리(Q1~Q7 판정 경로)는 공개 사례 18개(E01~E18)와 그 2c 패치를 읽은 뒤에 썼다. 사례 이름이나 특정 값에 맞춘 규칙은 넣지 않았고(시험 `test_agent_visible_files_contain_no_case_material`, `test_check_code_knows_no_case_ids`), 새 판정 경로마다 18개에 없는 예시로 원리 시험을 두었다(`tests/test_principles_v2.py`). 점검기를 다 쓴 뒤 처음 돌렸을 때 22행이 모두 기대 판정이었고, 사례 실패로 고친 원리는 없다. 그래도 공개 사례에 대한 점검기 탐지율은 보류 사례보다 높게 나올 수 있다 (`v2_plan.md` 8절 한계와 같은 종류).
- **테이블 규칙과 대리 기록 목록은 데이터 설명서(`docs/data_dictionary_v2.md`)에서 왔다.** 테이블 규칙은 "값이 알려지는 때" 칸, 지연 상한은 "지연·불확실성"·"생성 방식" 칸, 대리 기록 목록(`O.proxy.*`)과 확인 강도 층(`O.strata.*`)은 열 설명과 "데이터 전체의 성질"에서 왔다. 설명서는 2a에서 후보 전체를 보고 정한 테이블·열을 설명하므로, 규칙표도 같은 단서를 담는다 (`v2_plan.md` 8절).

### 대리 기록 목록 (Q4)

- **이뇨제(`O.proxy.diuretic`, medications loop_diuretic)를 규칙표 목록에서 뺐다** (2026-10-04 사용자 결정 A안). 이뇨제는 결과(AKI) 전에도 흔히 처방된다 (설명서: 기본 처방 확률 병동 15%, ICU 35%. AKI 입원의 40%에서 발생 뒤 추가 처방). 올바른 설계의 특징일 수 있어, 목록에 두면 깨끗한 설계서에서 오경보가 난다. "결과 창과 겹칠 때만 경고"는 이미 Q4 차단(`O.window_reuse`)이 나는 경우라 의미가 없었다. 설계서 작성자가 대리 기록으로 보면 `outcome.proxies`에 적고, 그러면 경고한다.
- 남은 목록 다섯 개(신장 관련 오더, 투석 처치, AKI 진단 코드, AKI 문제 목록 항목, 진단 코드 결과의 같은 코드 문제 목록)는 "결과를 알아챈 뒤에 생기는 기록"이다. 신장 초음파는 일부 결과 전 검사로도 쓰일 수 있다.
- 대리 기록 판정은 **시간 창을 보지 않는다**: 결과와 같은 입원 범위의 특징이 목록과 일치하면 tₚ 이전 기록이어도 경고한다 (v1과 같은 동작). 결과 창과 겹치면 경고가 아니라 차단(`O.window_reuse`)이다.

### 가정으로 내린 판정 3건 (조건 1: 형식 안에 피하는 올바른 표현이 없으면 차단·경고가 아니라 가정)

| 칸 | 원리상 판정 | 가정으로 내린 이유 |
|---|---|---|
| `cohort.rows_per_unit` = 에피소드 단위 `last` (`A.episode_last`) | Q5 차단 (마지막 입원인지 알려면 퇴원 뒤 0~60분 안에 이어진 입원이 없음을 알아야 함) | `all`/`first`로 바꾸면 이어진 입원이 재입원으로 세어진다. 결과(outcome)에는 `episode` 칸이 없어 "같은 에피소드 제외"를 쓸 수 없다 |
| `outcome.censoring.lost_to_followup: exclude` (`A.post_tp_exclusion`) | Q5 차단 (tₚ 뒤의 추적 소실로 행을 뺌) | 고를 수 있는 값이 exclude / count_as_negative / not_applicable뿐이고, count_as_negative도 다른 치우침이다 |
| `analysis.missing_data.outcome_missing: exclude` (`A.post_tp_exclusion`) | Q5 차단 (tₚ 뒤 결과 결측으로 행을 뺌) | 같은 이유 |

그 밖의 가정(3층): `A.family_missing`(가족 결측 행은 대체 키로 묶음), `A.outside_sites`(A·B 밖 병원 사건은 데이터에 없음), `A.date_only`(날짜만 있는 값은 기본 그날 23:59). 가정은 판정이 아니며 제출 kind는 `가정`이다.

### 깨끗한 기본 설계서에서 나는 판정 (승인 표, 2026-10-04)

2b 시험용 기본 설계서(`designs/prereview/`)에서 동적은 D2 차단(`outcome.pending_at_tp`), D5·D3 경고, 고정은 D5 경고, D4 경고 3건(전처리 단계마다)이 난다. 모두 형식 안에 피하는 표현이 있다 (`docs/stage3a_report.md`). 4단계 깨끗한 설계서 8개를 쓸 때 실제 약점인지 판단해 고친다 (`docs/phases.md` 4단계).

### 점검기가 판정에 쓰지 않는 칸

자유 서술 칸과 판정 원리가 없는 칸은 읽지 않는다 (목록은 스킬 지침서 4절). 특히 `outcome.reference.compare_to`는 결정 카드의 결과 계산에도 쓰지 않는다 (결과 계산은 항상 "각 값보다 먼저 잰 값"과 비교). `rowset.version_order`, `rowset.age_reference`, `outcome.planned_by`는 데이터 단계의 값 계산에만 쓰고 판정에는 쓰지 않는다. `rowset.assessment`(예측변수 측정 이질성)는 Q1~Q7 밖이다.

### 판정 방식의 한계

- **설계서만 볼 때 상한이 보수적이다.** 확인 가능 시각의 상한에 설명서의 최대 지연(진단 코딩 퇴원 뒤 90일 등)을 쓴다. 데이터를 주면 실제 시각으로 다시 센다.
- **시간 순 분할(D5)의 해석은 형식 설명서에 없는 부분을 보수적으로 정했다** (`leakcheck/rules.py` `TEMPORAL_RULE`, rules.md 3절). 묶음이 cutoff를 걸치면 학습에서 빼고, cutoff + gap 이전 행은 어디에도 쓰지 않는다.
- **Q7 층 처리 확인**: 결과 확인 강도 층(병동)은 `by_stratum`에 그 층의 열(`admissions.unit`, `transfers.unit`) 또는 그 열로 만든 특징 이름이 있거나, 포함 기준이 그 열을 한 값으로 제한하면 "다룸"으로 본다. `admissions.unit`(처음 병동)으로 제한해도 입원 중 병동 이동은 남는다.
- **Q7 데이터 단계**는 규칙표의 후보 층(병동, 성별)과 확인 강도 층의 열만 비교한다. 진단 코드로 정하는 결과는 데이터 단계 측정 빈도 비교를 하지 않는다 (설계서 단계 경고만).
- **기준 시점이 tₚ가 아닌 Q5** (v1 한계 그대로): `cohort.index_time`을 tₚ가 아닌 값으로 두면 고정 시점 설계에서 입원 시각의 하한이 정해지지 않아 보수적으로 차단할 수 있다.
- **문제 목록 항목 번호·등록 번호**는 설명서상 "처음 기록 시" 알려지지만, 규칙은 버전마다 그 버전의 기록 시각을 쓴다 (같거나 늦은 쪽, 보수적).

### 6단계로 넘기는 것

- `experiment/run.py`의 `LEAKCHECK_FILES`는 v1 생성기(`synth/generate.py`, `synth/stats.py`)를 복사한다. 3단계 점검기는 이 파일들이 필요 없다 (자체 로더 `leakcheck/data.py`, KDIGO `leakcheck/kdigo.py`). 3b 검수 실행기(`tools/skill_review.py`)는 `leakcheck/*.py`와 `designs/schema.json`만 복사했다.
