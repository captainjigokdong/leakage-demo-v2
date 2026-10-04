"""KDIGO 크레아티닌 기준 (KDIGO 2012). 점검기가 데이터 생성기 없이 돌도록 leakcheck 안에 둔다.

기준 (어느 하나):
- 앞선 48시간 안의 어떤 측정보다 0.3 mg/dL 이상 높음
- 앞선 7일 안의 최솟값(기저치)의 1.5배 이상
"""
from __future__ import annotations

KDIGO_ABS_RISE = 0.3  # mg/dL, 48시간 안
KDIGO_ABS_WINDOW_H = 48
KDIGO_REL_RISE = 1.5  # 기저치 대비 배수, 7일 안
KDIGO_REL_WINDOW_H = 7 * 24
EPS = 1e-9


def kdigo_first(hours, values) -> int | None:
    """크레아티닌 측정(채취 시각 순 정렬)에서 KDIGO 기준을 처음 만족한 측정의 위치. 없으면 None."""
    for j in range(1, len(values)):
        prior = hours[:j] >= hours[j] - KDIGO_REL_WINDOW_H
        if not prior.any():
            continue
        if values[j] >= KDIGO_REL_RISE * values[:j][prior].min() - EPS:
            return j
        recent = hours[:j] >= hours[j] - KDIGO_ABS_WINDOW_H
        if recent.any() and values[j] - values[:j][recent].min() >= KDIGO_ABS_RISE - EPS:
            return j
    return None


def kdigo_event(h, v, in_window) -> bool:
    """결과 창 안의 측정(in_window) 중 하나가 그보다 먼저 잰 값과 비교해 KDIGO 기준을 만족하는가."""
    import numpy as np
    for j in np.flatnonzero(in_window):
        prior = np.arange(len(v)) < j
        rel = prior & (h >= h[j] - KDIGO_REL_WINDOW_H)
        if rel.any() and v[j] >= KDIGO_REL_RISE * v[rel].min() - EPS:
            return True
        ab = prior & (h >= h[j] - KDIGO_ABS_WINDOW_H)
        if ab.any() and v[j] - v[ab].min() >= KDIGO_ABS_RISE - EPS:
            return True
    return False
