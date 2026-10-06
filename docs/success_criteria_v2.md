# 성공 기준 v2 (실험 전 고정)

- **고정일: 2026-10-06** (5단계). 6단계 실행 전에 커밋하고 사용자가 `criteria-locked-v2` 태그를 단다. 결과를 본 뒤 바꾸지 않는다.
- 채점 규칙: `experiment/scoring_rules.md` / 채점기: `experiment/grader.py` / 지시문: `experiment/agent_prompt.md` / 분석 계획: `docs/analysis_plan_v2.md`
- 근거: `docs/v2_plan.md` 3.4·3.5, `docs/phases.md` 5단계, 5단계 사용자 결정 (계획 승인 ①~⑩, S1 승인과 조건 1~10).
- v1 기준(`docs/success_criteria.md`)은 v1 기록이다. v2는 v1 결과("H1 지지 안 됨, H2 지지")를 보고 고친 새 실험이다.

## 1. 용어

- **변형**: 맹검 설계서 30개 (결함 22 + 깨끗한 8). **배치**: 결함 변형에 심은 결함 하나 (30개: 공개 18 + 보류 12).
- **배치-실행**: 배치 × 실행. 한 조건에 배치 30 × 반복 수.
- **탐지**: 주 분석은 결함의 정답 칸을 가리킨 `문제` 지적이 있음 (`experiment/scoring_rules.md` 6절). 보조 분석은 거기에 문제 종류까지 맞음.
- **오경보**: 결함이 아닌 채점 대상 칸에 대한 `문제` 지적. 정당한 지적 목록 칸은 중립, legit 칸과 K 칸은 오경보. 한 제출에서 같은 항목은 한 번.

## 2. 가설과 기준 (주 분석으로 판정, 다섯 가지를 따로 판정·따로 보고)

가설마다 부트스트랩 단위·분자·분모·기준은 **`docs/analysis_plan_v2.md` 3절**(해시 잠금)에 한 번만 적는다. 다섯 가설: H1a 탐지율, H1b 오경보(절대), H1c 오경보(상대), H2a 보류 탐지(판정), H2b 일반화 격차(기술만).

- 오경보는 H1b·H1c 모두 깨끗한 변형에서만 센다 (결함 변형의 오경보는 함께 보고하는 지표).
- 보조 분석은 같은 계산을 해 나란히 보고하며 **판정에 쓰지 않는다**. 참고값(엄격판, 목록 우선, K 제외 등)도 판정에 쓰지 않는다 (`docs/analysis_plan_v2.md` 4절).
- v1에서 (가) 보류 0.783, (나) 보류 0.708이었다. H2a는 v1 기준보다 엄격하고, 지지되지 않을 수 있다.

## 3. 실행 규칙 (6단계 실행기가 따름)

- 실행당 턴 수 상한 **60**, 두 조건 같음 (`grader.MAX_TURNS`). 근거: 4a·3b 검수 실행 44회의 최대 23턴.
- 상한에 걸린 실행은 재실행하지 않는다 (기계적 실패가 아님). 그때까지의 `findings.json`을 채점한다. 상한에 걸린 수를 조건별로 보고하고, 뺀 참고값을 낸다.
- 형식 검사 실패(파일 없음 포함) 때 "파일 형식만 고쳐 다시 제출" **1회** (`grader.FORMAT_RETRIES`), 재제출 턴 상한 **5** (`grader.MAX_TURNS_RETRY`). 두 조건 같고 횟수를 기록한다.
- 두 조건의 작업 폴더에 지시문·설계서·데이터와 함께 형식 설명 사본·데이터 설명서 사본(`experiment/prompt.py`의 `agent_docs()`)을 같은 이름으로 둔다.
- 계정의 기본 제공 스킬 목록은 두 조건에 그대로 둔다. 실행마다 init 기록의 스킬 목록을 남기고, 조건 차이가 `leakage-check` 하나뿐인지 확인한다.
- 재실행·폐기·허용 도구는 `docs/v2_plan.md` 6절 (6단계에서 잠금). `experiment/run.py`는 6단계에서 위 값으로 고치므로 여기서 잠그지 않는다.

## 4. 고정한 파일 (SHA-256)

아래 파일이 바뀌면 `tests/test_grader.py::test_locked_files_match_success_criteria`가 실패한다. 6단계 이후 버그를 발견하면 고치지 않고 `docs/known_issues_v2.md`에 적는다.
지시문 해시: `experiment/prompt.py`의 `PROMPT_SHA256` = `d5824ec50fef2b3afb5c6e40c8e16d1c0edff81be9fdbac7e4d4d30c8406b4bd`

| 파일 | SHA-256 |
|---|---|
| `experiment/agent_prompt.md` | `d5824ec50fef2b3afb5c6e40c8e16d1c0edff81be9fdbac7e4d4d30c8406b4bd` |
| `experiment/prompt.py` | `a7bfbf401c134cc521d301815f26f4f3268641bfb599aae6b98f99eee7763a20` |
| `experiment/grader.py` | `19f3111a744a43fe5bffd70ee56ff1309ae8f4b8052b28227fc38be15119829c` |
| `experiment/scoring_rules.md` | `e63f23c1092944b760eadacbf1215eeb11451d30f0cae810664e1a3bcc8de45d` |
| `docs/agent/design_format.md` | `c43fc1e1b90521d6d5267a5098872bbf179a6685e5f418d5a7c27f0da934ea41` |
| `docs/agent/data_dictionary.md` | `1b4e78b49fe358975af8d2af6383c39d28423eb5304d1948f6000ba1afcc04f6` |
| `docs/analysis_plan_v2.md` | `14d5d034508a6c7cc7002baaf43ecc01c559a05c09ac0c0c122a332689ed33d2` |
