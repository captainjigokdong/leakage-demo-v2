# 사후 확인: 특징 선택 조건이 고른 열

**사후 확인**이다. 8단계 계획(`docs/stage8_plan.md`)에 없던 확인으로, 결과(본 데이터 D5와 D5 참조의 AUROC가 시드 5개 모두 같음)를 본 뒤 사용자 요청으로 했다. 성능을 다시 계산하지 않았다: 열 선택만 같은 설계·분할 시드로 다시 돌렸고, AUROC가 같은지는 `leakage_effect_*.json`에 이미 있는 값으로 비교했다. 기존 결과 파일은 바꾸지 않았다. 생성: `python -m experiment.stage8.posthoc_selected_columns`.

고른 열은 다른데 AUROC(로지스틱·부스팅 중 하나라도)가 같은 시드: 0개

## main · fixed: F4(전체 데이터로 적합) vs F4ref(학습 집합만)

k = 8. 고른 열이 같은 시드 1/5. 겹치는 열 수 7~8 (k개 중).

| 시드 | 같음 | 겹침 | AUROC 같음 (로지스틱/부스팅) | F4만 고른 열 | F4ref만 고른 열 | 둘 다 고른 열 |
|---|---|---|---|---|---|---|
| 0 | 아니요 | 7 | 아니요/아니요 | age | los_h | n_dx, cr_last, dialysis_ordered, unit=ICU, unit=ward, discharge_status=home, discharge_status=transfer |
| 1 | 아니요 | 7 | 아니요/아니요 | dialysis_ordered | los_h | age, n_dx, cr_last, unit=ICU, unit=ward, discharge_status=home, discharge_status=transfer |
| 2 | 아니요 | 7 | 아니요/아니요 | age | los_h | n_dx, cr_last, dialysis_ordered, unit=ICU, unit=ward, discharge_status=home, discharge_status=transfer |
| 3 | 예 | 8 | 예/예 | - | - | age, n_dx, cr_last, dialysis_ordered, unit=ICU, unit=ward, discharge_status=home, discharge_status=transfer |
| 4 | 아니요 | 7 | 아니요/아니요 | age | los_h | n_dx, cr_last, dialysis_ordered, unit=ICU, unit=ward, discharge_status=home, discharge_status=transfer |

## main · dynamic: D5(전체 데이터로 적합) vs D5ref(학습 집합만)

k = 6. 고른 열이 같은 시드 5/5. 겹치는 열 수 6~6 (k개 중).

| 시드 | 같음 | 겹침 | AUROC 같음 (로지스틱/부스팅) | D5만 고른 열 | D5ref만 고른 열 | 둘 다 고른 열 |
|---|---|---|---|---|---|---|
| 0 | 예 | 6 | 예/예 | - | - | cr_last, cr_min_adm, cr_max_48h, bun_last, unit=ICU, unit=ward |
| 1 | 예 | 6 | 예/예 | - | - | cr_last, cr_min_adm, cr_max_48h, bun_last, unit=ICU, unit=ward |
| 2 | 예 | 6 | 예/예 | - | - | cr_last, cr_min_adm, cr_max_48h, bun_last, unit=ICU, unit=ward |
| 3 | 예 | 6 | 예/예 | - | - | cr_last, cr_min_adm, cr_max_48h, bun_last, unit=ICU, unit=ward |
| 4 | 예 | 6 | 예/예 | - | - | cr_last, cr_min_adm, cr_max_48h, bun_last, unit=ICU, unit=ward |

## aux_A · dynamic: D5(전체 데이터로 적합) vs D5ref(학습 집합만)

k = 256. 고른 열이 같은 시드 0/20. 겹치는 열 수 174~194 (k개 중).

| 시드 | 겹치는 열 수 | AUROC 같음 (로지스틱/부스팅) |
|---|---|---|
| 0 | 185 | 아니요/아니요 |
| 1 | 188 | 아니요/아니요 |
| 2 | 183 | 아니요/아니요 |
| 3 | 189 | 아니요/아니요 |
| 4 | 180 | 아니요/아니요 |
| 5 | 190 | 아니요/아니요 |
| 6 | 189 | 아니요/아니요 |
| 7 | 191 | 아니요/아니요 |
| 8 | 189 | 아니요/아니요 |
| 9 | 176 | 아니요/아니요 |
| 10 | 194 | 아니요/아니요 |
| 11 | 183 | 아니요/아니요 |
| 12 | 185 | 아니요/아니요 |
| 13 | 174 | 아니요/아니요 |
| 14 | 189 | 아니요/아니요 |
| 15 | 181 | 아니요/아니요 |
| 16 | 184 | 아니요/아니요 |
| 17 | 180 | 아니요/아니요 |
| 18 | 191 | 아니요/아니요 |
| 19 | 185 | 아니요/아니요 |

