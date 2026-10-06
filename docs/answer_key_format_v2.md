# 정답표 형식 (v2, 4a에서 확정)

내용(어느 변형에 어느 사례가 있는지)은 4b에서 만들어 `sealed/answer_key.enc`에만 봉인한다. 형식과 검사 함수는 `designs/answer_key_v2.py`, 시험은 `tests/test_answer_key_v2.py`.

## 모양

```json
{
  "version": "v2",
  "priority": [["accept", "탐지", "..."], ["support", "중립", "..."], ["justified", "중립", "..."],
               ["legit", "오경보", "..."], ["other", "오경보", "..."]],
  "draw": {"seed": 0, "date": "", "skipped": {}},
  "placement": {"seed": 0, "type_split": [11, 11]},
  "blinding": {"seed": "4b에서 새로 만든 값"},
  "variants": {
    "design_XXXX.json": {
      "sha256": "변형 파일 SHA-256",
      "base": "aki_a",
      "design_type": "dynamic",
      "kind": "defect | clean",
      "defects": [{"id": "E02", "question": "Q1", "holdout": false, "expected_verdict": "차단",
                   "accept_targets": ["features:cr_last"], "support_targets": [], "accept_questions": ["Q1"]}],
      "legit_changes": [{"targets": ["features:k_last_6h"], "note": "결함 아님. 지적하면 오경보"}],
      "justified": [{"id": "L1", "cells": ["data_source.death_source"]}]
    }
  }
}
```

## 칸

| 칸 | 뜻 | 기본값 |
|---|---|---|
| `accept_targets` | 이 중 **하나라도** 지목하면 탐지 | 패치의 지목 항목(`designs.inject.targets_of`) 중 `support_targets`가 아닌 것 전부 |
| `support_targets` | 패치로 바뀌었지만 그것만 지목하면 탐지도 오경보도 아님 | 없음 |
| `accept_questions` | 보조 분석(항목 + 종류)에서 정당한 종류. 사례의 질문을 반드시 포함 | `[사례의 질문]` |
| `legit_changes` | 바탕의 "수상해 보이지만 정당한 항목" (`docs/clean_designs_v2.md` 4절). 지적하면 오경보 | 바탕마다 고정 (`LEGIT_ITEMS`: aki_b `k_last_6h`, aki_c `n_admissions_to_tp`, readmit_b `prior_dx_group`, readmit_c `prior_cr_last`) |
| `justified` | 바탕의 정당한 지적 목록 칸 (잠정 잠금된 `docs/justified_findings_v2.json`). 탐지도 오경보도 아님, 두 조건 같게 | 목록에서 바탕별로 자동 |

- 공개 사례 중 기본값과 다른 것 (2c 기록 근거): **E04** `accept_questions` = Q1, Q4 / **E09** `support_targets` = `features:prior_dx_main` (결함은 결과율 인코딩 `preprocessing:dx_encode`). 그 밖의 공개 사례(E17·E18 포함)는 기본값.
- 보류 사례를 기본값과 다르게 정하면 4b에서 근거와 함께 사용자 승인 (`docs/phases.md` 4b).

## 우선순위

지적 하나의 칸이 여러 줄에 맞으면 **앞 줄**로 판정한다.

1. `accept_targets` → 탐지 (결함 변형에서 같은 칸이 정당한 지적 목록에 있어도 탐지가 우선)
2. `support_targets` → 중립
3. `justified` → 중립 (칸 단위. 같은 항목 전체를 지목하는 지적이 `legit_changes`에 맞으면 4로)
4. `legit_changes` → 오경보
5. 그 밖 → 오경보

- 점검기 문제(K1·K5)에서 온 지적은 목록에 없으므로 5(오경보)다. 참고값 계산은 5단계 분석 계획에서 정한다.
- `kind`가 "가정"인 지적의 처리, 지적의 표기(점검기 target 표기)와 위 칸의 일치 규칙은 5단계 채점기에서 정한다 (`docs/phases.md` 5단계).

## 검사 (`validate_key`)

version·priority 순서, 변형마다 필수 칸, `kind`와 결함 수 일치, 결함 0~2개, `accept_targets` 비어 있지 않음, accept·support 겹침 없음, `accept_questions`가 사례 질문 포함, 한 변형 안 두 결함의 accept 겹침 없음, 사례가 한 번만 배치됨.
