"""누수 효과 시연 시험 (docs/step7_analysis_plan.md 4절)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from experiment import leakage_effect as le
from leakcheck import lock as lk


def test_leak_list_matches_plan():
    assert set(le.LEAKS["fixed"]) == {"F1", "F2", "F3", "F4"}
    assert set(le.LEAKS["dynamic"]) == {"D1", "D2", "D3", "D4", "D5", "D6"}


@pytest.mark.parametrize("t", ["fixed", "dynamic"])
def test_variants_change_only_their_leak(t):
    vs = le.variants(t)
    base = vs["fixed"][1]
    assert set(vs) == {"fixed", "all", *le.LEAKS[t]}
    for lid in le.LEAKS[t]:
        d = vs[lid][1]
        assert d != base and d["design_id"].endswith(lid)
        assert {k for k in base if base[k] != d[k]} <= {"design_id", "features", "split", "preprocessing"}
    assert le.variants(t)["fixed"][1] == base   # 원본을 바꾸지 않는다


def test_seed_changes_design_hash_so_each_needs_its_own_lock():
    from leakcheck import design as dz
    d = le.variants("fixed")["fixed"][1]
    assert dz.design_hash(le.with_seed(d, 0)) != dz.design_hash(le.with_seed(d, 1))


def test_auroc_requires_lock():
    d = le.variants("fixed")["fixed"][1]
    with pytest.raises(lk.LockError):
        lk.auroc(None, d, [0, 1], [0.1, 0.9])


def test_group_folds_keep_groups_together_and_count_calls():
    g = np.array(["a", "a", "b", "c", "c", "c", "d", "e"])
    f = le.GroupFolds(g, 3, seed=1)
    before = le.GroupFolds.total_calls
    for tr, te in f.split():
        assert not set(g[tr]) & set(g[te])
    assert f.crossing_groups() == 0 and le.GroupFolds.total_calls == before + 1
    import sklearn.model_selection as ms
    assert ms.check_cv(f, np.array([0, 1] * 4), classifier=True) is f   # TPOT가 그대로 쓴다


def test_rowwise_kfold_splits_groups():
    g = np.repeat(np.arange(50), 4)
    y = np.tile([0, 1], 100)
    r = le.row_kfold_crossing(g, y, 5, seed=0)
    assert r["groups_with_multiple_rows"] == 50 and r["groups_split_across_folds"] > 0


def test_preprocess_fit_scope():
    X = pd.DataFrame({"a": [1.0, np.nan, 3.0, 100.0, np.nan, 200.0], "s": ["M", "F", "M", "F", "M", "F"]})
    y = np.array([0, 1, 0, 1, 0, 1])
    train = np.array([True, True, True, False, False, False])
    zt, names = le.preprocess(X, y, train, [{"kind": "impute", "fit_scope": "train"}])
    za, _ = le.preprocess(X, y, train, [{"kind": "impute", "fit_scope": "all"}])
    i = names.index("a")
    assert zt[1, i] == 2.0 and za[1, i] == np.median([1.0, 3.0, 100.0, 200.0])
    zs, ns = le.preprocess(X, y, train, [{"kind": "impute", "fit_scope": "train"}, {"kind": "select", "fit_scope": "all"}])
    assert zs.shape[1] == len(ns) == 2   # 열 3개(a, s=F, s=M) → 올림 절반


# ---------------------------------------------------------------- 8단계 (docs/stage8_plan.md)

def test_stage8_bundles_match_plan():
    assert le.BUNDLES["main"]["seeds"] == 5 and le.BUNDLES["aux_A"]["seeds"] == le.BUNDLES["aux_B"]["seeds"] == 20
    assert le.BUNDLES["main"]["data"].name == "synth" and le.BUNDLES["aux_A"]["data"].name == "synth_aux"
    names = {b: {n for t, p, ids, c, _ in cfg["parts"] for n in le.variants8(t, le._base(p), ids, c)}
             for b, cfg in le.BUNDLES.items()}
    assert names["main"] == {"fixed", "F1", "F2", "F3", "F4", "all", "F4ref", "D1", "D2", "D3", "D4", "D5", "D6", "D5ref"}
    assert names["aux_A"] == names["aux_B"] == {"fixed", "D4", "D5", "D4+D5", "D5ref"}
    assert {c for cfg in le.BUNDLES.values() for *_, tc in cfg["parts"] for c in tc} == {"fixed", "all", "D4+D5"}


def test_stage8_refs_select_on_train_only():
    for t in ("fixed", "dynamic"):
        vs = le.variants8(t, le._base(le.BASES[t]), None, "all")
        ref = next(iter(le.REFS[t]))
        leak = {"fixed": "F4", "dynamic": "D5"}[t]
        assert vs[ref][1]["preprocessing"][-1] == {"name": "select_k", "kind": "select", "fit_scope": "train"}
        assert vs[leak][1]["preprocessing"][-1]["fit_scope"] == "all"
        assert all(p["kind"] != "select" for p in vs["fixed"][1]["preprocessing"])   # 수정 설계에는 특징 선택 없음


def test_stage8_aux500_adds_only_lab_features():
    base, a = le._base(le.BASES["dynamic"]), le._base(le.AUX500)
    assert {k for k in base if base[k] != a[k]} == {"design_id", "features"}
    extra = a["features"][len(base["features"]):]
    assert a["features"][:len(base["features"])] == base["features"] and len(extra) == 500
    assert {f["filter"]["test"][0] for f in extra} == {f"t{i:03d}" for i in range(1, 501)}
    assert all(f["time_column"] == "report_time" and f["window"] == {"start": "admit", "end": "tp"}
               and f["agg"] == "last" for f in extra)


def test_stage8_summary_paired_diffs():
    recs = [{"type": "dynamic", "design": n, "seed_step": s, "auroc": {"lr": v}}
            for n, vals in {"fixed": [0.6, 0.7], "D5": [0.8, 0.8], "D5ref": [0.65, 0.6]}.items()
            for s, v in enumerate(vals)]
    t = le.summarize(recs)["dynamic"]
    assert t["D5"]["lr"]["vs_fixed"]["mean"] == pytest.approx(0.15)
    assert t["D5"]["lr"]["vs_ref"]["by_seed"] == {"0": pytest.approx(0.15), "1": pytest.approx(0.2)}
    assert "vs_ref" not in t["fixed"]["lr"] and "vs_fixed" not in t["fixed"]["lr"]


def test_stage8_stop_conditions():
    ok = {"design": "fixed", "patients_or_families_in_both": 0, "skipped_features": {}, "unexpected_empty": []}
    le.check_stop(ok)
    for bad in ({"patients_or_families_in_both": 3}, {"skipped_features": {"x": "y"}}, {"unexpected_empty": ["x"]},
                {"tpot": {"cv_groups_crossing_folds": 1, "cv_gen_is_group_folds": True, "cv_split_calls": 1, "seconds": 1}},
                {"tpot": {"cv_groups_crossing_folds": 0, "cv_gen_is_group_folds": False, "cv_split_calls": 1, "seconds": 1}},
                {"tpot": {"cv_groups_crossing_folds": 0, "cv_gen_is_group_folds": True, "cv_split_calls": 1, "seconds": 601}}):
        with pytest.raises(le.StopRun):
            le.check_stop({**ok, **bad})


def test_stage8_uses_v2_loader():
    import inspect
    src = inspect.getsource(le.run_bundle)
    assert "ld.load(" in src and "synth.generate" not in inspect.getsource(le)
