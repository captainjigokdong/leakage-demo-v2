"""설계서의 분할 방식대로 예측 행을 학습·평가(또는 폴드)에 배정한다 (Q2 데이터 단계 점검용).

- key가 결측인 행은 fallback_key로 묶는다. fallback_key가 없으면 등록 번호로 묶는다 (가정 A.family_missing)
- temporal: rules.TEMPORAL_RULE (2026-10-04 사용자 결정 D5). 어느 쪽에도 쓰지 않는 행은 "unused"
"""
from __future__ import annotations

from leakcheck import rules

UNUSED = "unused"


def key_level(split: dict) -> str:
    """분할 키의 수준. 행 단위 방법이면 키와 무관하게 index_row."""
    if split.get("method") in rules.ROW_LEVEL_METHODS:
        return "index_row"
    return rules.split_level(split["key"])


def fallback_level(split: dict) -> str | None:
    """key가 결측일 수 있을 때 그 행들이 실제로 묶이는 수준. 결측이 없는 키면 None."""
    if key_level(split) not in rules.NULLABLE_SPLIT_LEVELS:
        return None
    fb = split.get("fallback_key")
    return rules.split_level(fb) if fb else "patient"


def effective_levels(split: dict) -> list[str]:
    lv = [key_level(split)]
    fb = fallback_level(split)
    return lv + ([fb] if fb else [])


def group_values(index_rows, split: dict):
    import pandas as pd
    level = key_level(split)
    vals = index_rows[rules.SPLIT_KEY_COLUMN[level]].astype("string")
    fb = fallback_level(split)
    if fb:
        vals = vals.fillna(index_rows[rules.SPLIT_KEY_COLUMN[fb]].astype("string"))
    return pd.Series(vals.to_numpy(), index=index_rows.index)


def assign(index_rows, split: dict):
    """예측 행 → 배정 이름 (test/train/unused 또는 fold0..k-1). index는 index_rows와 같다."""
    import numpy as np
    import pandas as pd
    seed = split.get("seed", 0)
    method = split.get("method", "group_holdout")
    groups = group_values(index_rows, split)
    if method == "temporal":
        tcol = split.get("time_column") or "tp"
        t = index_rows[tcol] if tcol in index_rows else index_rows["tp"]
        cut = (pd.Timestamp(split["cutoff"]) if split.get("cutoff")
               else t.quantile(1 - split.get("test_fraction", 0.3)))
        gap = pd.Timedelta(hours=_gap_h(split) or 0.0)
        late_group = (t > cut).groupby(groups).transform("any")
        lab = np.where(~late_group, "train", np.where(t > cut + gap, "test", UNUSED))
        return pd.Series(lab, index=index_rows.index)
    uniq = np.array(sorted(groups.unique()))
    perm = np.random.default_rng(seed).permutation(len(uniq))
    if method == "group_kfold":
        k = split.get("n_folds", 5)
        lab = {g: f"fold{i % k}" for i, g in zip(range(len(uniq)), uniq[perm])}
    else:
        n_test = int(round(split.get("test_fraction", 0.3) * len(uniq)))
        test = set(uniq[perm[:n_test]])
        lab = {g: ("test" if g in test else "train") for g in uniq}
    return groups.map(lab)


def _gap_h(split: dict) -> float | None:
    from leakcheck.timeline import parse_duration_h
    return parse_duration_h(split.get("gap"))


def crossing(index_rows, labels, level: str) -> tuple[int, int]:
    """level 묶음 중 둘 이상의 배정에 나뉜 것의 수, 전체 묶음 수. 가족은 기록된 가족만 센다.
    어느 쪽에도 쓰지 않는 행(unused)은 세지 않는다."""
    import pandas as pd
    used = labels != UNUSED
    col = rules.SPLIT_KEY_COLUMN[level]
    mask = used & index_rows[col].notna()
    g = index_rows.loc[mask, col].astype("string")
    n = pd.DataFrame({"g": g, "lab": labels[mask]}).groupby("g")["lab"].nunique()
    return int((n > 1).sum()), int(len(n))
