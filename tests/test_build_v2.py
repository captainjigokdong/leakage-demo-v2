"""4a: 추첨·배치 스크립트(designs/build_v2.py)와 4a 잠정 잠금(docs/lock_4a_v2.json).

추첨·배치는 같은 구조의 가짜 기록으로 시험한다 (새 후보 내용 없음, 암호 불필요, 점검기 쓰지 않음).
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from designs import build_v2 as B

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "docs" / "lock_4a_v2.json"


# --- 가짜 바탕·가짜 사례 --------------------------------------------------------------

def fake_bases() -> dict[str, dict]:
    out = {}
    for t, prefix in (("dynamic", "aki"), ("fixed", "readmit")):
        for s, method in zip("abcd", ("temporal", "group_holdout", "temporal", "group_holdout")):
            out[f"{prefix}_{s}"] = {"design_id": f"{prefix}_{s}", "design_type": t, "split": {"method": method}}
    return out


def fake_applies(ops, base) -> bool:
    """가짜 패치: 'only' 칸이 있으면 그 바탕에서만 적용된다."""
    return all(base["design_id"] in op.get("only", [base["design_id"]]) for op in ops)


def op(i, path=None, **kw):
    return {"op": "set", "path": path or f"part{i}.x", "value": i, **kw}


def fake_cases(n_dyn_only=9, n_fix_only=9, n_both=12, holdout_idx=range(18, 30)) -> list[B.Case]:
    """가짜 사례 30개. holdout_idx 번째가 보류 (id H..), 나머지는 공개 (id E..)."""
    kinds = [["dynamic"]] * n_dyn_only + [["fixed"]] * n_fix_only + [["dynamic", "fixed"]] * n_both
    hold = set(holdout_idx)
    return [B.Case(id=f"{'H' if i in hold else 'E'}{i + 1:02d}", question="Q1", holdout=i in hold,
                   types=list(ts), ops={t: [op(i)] for t in ts}) for i, ts in enumerate(kinds)]


# --- 규칙 하나씩 ------------------------------------------------------------------

def test_touches_split_by_target_cell_not_case_id():
    assert B.touches_split([{"op": "set", "path": "split.key", "value": "x"}])
    assert B.touches_split([{"op": "remove", "path": "split"}])
    assert B.touches_split([op(1), {"op": "set", "path": "split.method", "value": "random_rows"}])
    assert not B.touches_split([{"op": "set", "path": "model.tuning.cv_key", "value": "x"}])
    assert not B.touches_split([{"op": "set", "path": "splitting.x", "value": 1}])


def test_split_patch_goes_only_to_random_split_bases():
    bases = fake_bases()
    c = B.Case("E99", "Q2", False, ["dynamic", "fixed"],
               {t: [{"op": "set", "path": "split.key", "value": "x"}] for t in ("dynamic", "fixed")})
    got = B.compatible_bases(c, bases, fake_applies)
    assert got == ["aki_b", "aki_d", "readmit_b", "readmit_d"]
    assert all(bases[b]["split"]["method"] in B.RANDOM_SPLIT_METHODS for b in got)
    assert len(B.compatible_bases(c, bases, fake_applies, split_rule=False)) == 8


def test_zero_difference_type_avoided_only_if_other_positive():
    c = B.Case("E08", "Q3", False, ["dynamic", "fixed"], {}, difference={"dynamic": 0, "fixed": 371})
    assert B.placeable_types(c) == ["fixed"]
    c0 = B.Case("E98", "Q3", False, ["dynamic", "fixed"], {}, difference={"dynamic": 0, "fixed": 0})
    assert B.placeable_types(c0) == ["dynamic", "fixed"]                 # 모두 0이면 그래도 배치


def test_public_diff_matches_injection_log_table():
    text = (ROOT / "docs" / "injection_log_v2.md").read_text(encoding="utf-8")
    ko = {"동적": "dynamic", "고정": "fixed"}
    got: dict[str, dict] = {}
    for m in re.finditer(r"^\| (E\d\d) \| (동적|고정) \| 있음 .*? \| ([\d,.]+) —", text, re.M):
        got.setdefault(m.group(1), {})[ko[m.group(2)]] = float(m.group(3).replace(",", ""))
    assert got == {k: {t: float(v) for t, v in d.items()} for k, d in B.PUBLIC_DIFF_2C.items()}


# --- 추첨 -----------------------------------------------------------------------

def draw_pool(no_base=(), split_only=()):
    """질문 6개 × 5개 후보. no_base: 어느 바탕에도 적용 안 됨, split_only: 분할 칸 패치 + 시간 순 바탕에서만 적용."""
    out = []
    for qi, q in enumerate(sorted(B.NEW_ALLOCATION)):
        for k in range(5):
            cid = f"C{qi * 5 + k + 1:02d}"
            ops = [op(qi * 5 + k)]
            if cid in no_base:
                ops = [op(0, only=[])]
            if cid in split_only:
                ops = [{"op": "set", "path": "split.key", "value": "x", "only": ["aki_a", "aki_c"]}]
            out.append(B.Case(cid, q, True, ["dynamic"], {"dynamic": ops}, excluded=(k == 4)))
    return out


def test_draw_two_per_question_deterministic_and_skips_excluded():
    pool = draw_pool()
    a, log = B.draw(pool, fake_bases(), fake_applies)
    b, _ = B.draw(pool, fake_bases(), fake_applies)
    assert a == b and len(a) == 12
    by = {c.id: c for c in pool}
    assert Counter(by[x].question for x in a) == {q: 2 for q in B.NEW_ALLOCATION}
    assert not any(by[x].excluded for x in a)
    assert all(v["skipped_no_base"] == 0 for v in log.values())
    assert a != B.draw(pool, fake_bases(), fake_applies, seed=B.DRAW_SEED + 1)[0]   # 시드가 순서를 정함


def test_draw_skips_unplaceable_and_counts_split_rule():
    pool = draw_pool()
    q1 = [c.id for c in pool if c.question == "Q1" and not c.excluded]
    order = [c.id for c in random_order(pool, "Q1")]
    first, second = order[0], order[1]
    pool = draw_pool(no_base={first}, split_only={second})
    got, log = B.draw(pool, fake_bases(), fake_applies)
    assert first not in got and second not in got
    assert log["Q1"]["skipped_no_base"] == 2 and log["Q1"]["skipped_split_rule"] == 1
    assert len([x for x in got if x in q1]) == 2


def random_order(pool, q):
    import random
    p = sorted((c for c in pool if c.question == q and not c.excluded), key=lambda c: c.id)
    return random.Random(f"{B.DRAW_SEED}-{q}").sample(p, len(p))


def test_draw_stops_when_question_cannot_fill():
    pool = draw_pool(no_base={"C01", "C02", "C03"})
    with pytest.raises(B.PlacementError):
        B.draw(pool, fake_bases(), fake_applies)


# --- 배치 -----------------------------------------------------------------------

def test_place_satisfies_rules_and_is_deterministic():
    cases = fake_cases()
    bases = fake_bases()
    lay = B.place(cases, bases, fake_applies)
    assert B.check_layout(lay, cases, bases, fake_applies) == []
    assert lay["type_split"] == (11, 11)
    assert lay == B.place(cases, bases, fake_applies)
    assert sorted(lay["clean"]) == sorted(bases)


def test_place_solo_and_split_rules():
    split_ops = [{"op": "set", "path": "split.key", "value": "x"}]
    extra = [B.Case("E01", "Q5", False, ["fixed"], {"fixed": [op(0)]}),
             B.Case("E16", "Q5", False, ["fixed"], {"fixed": [op(99)]}),
             B.Case("E02", "Q2", False, ["dynamic", "fixed"], {"dynamic": split_ops, "fixed": split_ops})]
    cases = [c for c in fake_cases() if c.id not in {"E01", "E02", "E16"}] + extra
    bases = fake_bases()
    lay = B.place(cases, bases, fake_applies)
    assert B.check_layout(lay, cases, bases, fake_applies) == []
    v16 = next(v for v in lay["defect"] if "E16" in v["cases"])
    assert v16["cases"] == ["E16"]
    v2 = next(v for v in lay["defect"] if "E02" in v["cases"])
    assert bases[v2["base"]]["split"]["method"] in B.RANDOM_SPLIT_METHODS


def test_place_pairs_never_share_targets():
    """지목 항목이 같은 사례(E10~E18 동적·고정 모두)는 같은 2개짜리 변형에 들어가지 않는다."""
    same = {"dynamic": [op(0, path="features[name=cr_last].time_column")],
            "fixed": [op(0, path="features[name=cr_last].time_column")]}
    cases = [B.Case(c.id, c.question, c.holdout, ["dynamic", "fixed"], same) if 9 <= i < 18 else c
             for i, c in enumerate(fake_cases())]
    lay = B.place(cases, fake_bases(), fake_applies)
    shared = {c.id for c in cases if c.ops.get("dynamic") == same["dynamic"]}
    pairs = [v["cases"] for v in lay["defect"] if len(v["cases"]) == 2]
    assert all(len(set(p) & shared) <= 1 for p in pairs)
    assert B.check_layout(lay, cases, fake_bases(), fake_applies) == []


def test_place_stops_when_rules_cannot_be_met(monkeypatch):
    """보류 12개가 모두 같은 지목 항목이면 2개짜리 안 보류 수(P9)를 맞출 수 없다 → 멈춘다 (다시 뽑지 않음)."""
    monkeypatch.setattr(B, "MAX_NODES", 20_000)
    cases = [c for c in fake_cases() if not c.holdout] + [
        B.Case(f"H{i:02d}", "Q1", True, ["dynamic", "fixed"],
               {t: [op(0, path="features[name=cr_last].time_column")] for t in ("dynamic", "fixed")})
        for i in range(19, 31)]
    cases = [c if c.holdout else B.Case(c.id, c.question, c.holdout, c.types,
                                         {t: [op(0, path="features[name=cr_last].time_column")] for t in c.types})
             for c in cases]
    with pytest.raises(B.PlacementError):           # 모든 사례의 지목 항목이 같아 2개짜리를 만들 수 없음
        B.place(cases, fake_bases(), fake_applies)


def test_place_falls_back_to_10_12_only_when_needed():
    cases = fake_cases(n_dyn_only=10, n_fix_only=20, n_both=0, holdout_idx=[0, 1, 2, 3, *range(10, 18)])
    lay = B.place(cases, fake_bases(), fake_applies)
    assert lay["type_split"] == (10, 12)
    assert B.check_layout(lay, cases, fake_bases(), fake_applies) == []


def test_check_layout_catches_broken_layouts():
    cases, bases = fake_cases(), fake_bases()
    lay = B.place(cases, bases, fake_applies)
    bad = json.loads(json.dumps(lay))
    bad["defect"][0]["cases"].append("E99")
    assert "P1" in B.check_layout(bad, cases, bases, fake_applies)
    bad = json.loads(json.dumps(lay))
    bad["clean"] = bad["clean"][:-1]
    assert "P10" in B.check_layout(bad, cases, bases, fake_applies)


def test_public_cases_place_on_clean_designs():
    """공개 18개(진짜 패치·진짜 깨끗한 설계서) + 가짜 보류 12개로 배치가 나온다."""
    bases = B.load_clean()
    pub = B.public_cases()
    assert len(pub) == 18 and all(B.compatible_bases(c, bases, B.default_applies) for c in pub)
    fakes = [c for c in fake_cases() if c.holdout]

    def applies(ops, base):
        real = [o for o in ops if not o["path"].startswith("part")]
        return not real or B.default_applies(real, base)
    lay = B.place(pub + fakes, bases, applies)
    assert B.check_layout(lay, pub + fakes, bases, applies) == []


def test_build_v2_does_not_import_checker():
    code = "import sys, designs.build_v2; print(any(m == 'leakcheck' or m.startswith('leakcheck.') for m in sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


# --- 4a 잠정 잠금 ----------------------------------------------------------------

def test_seeds_are_the_committed_constants():
    assert (B.DRAW_SEED, B.PLACE_SEED) == (1937495026, 3216632932)
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    assert lock["seeds"] == {"DRAW_SEED": B.DRAW_SEED, "PLACE_SEED": B.PLACE_SEED}


def test_locked_files_unchanged():
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    assert lock["status"].startswith("잠정")
    for group in ("provisional", "fixed_for_4b"):
        for rel, digest in lock[group].items():
            assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == digest, rel
    assert sorted(lock["provisional"]) == sorted(
        ["docs/justified_findings_v2.json"] + [f"designs/clean_v2/{n}.json" for n in B.CLEAN_NAMES])


def test_new_cases_adapter_with_fake_record():
    rec = {"cases": [{"id": "C02", "ops": {"dynamic": [op(2)], "fixed": [op(3)]}, "placeable_types": ["fixed"],
                      "excluded": False},
                     {"id": "C01", "ops": {"dynamic": [op(1)]}, "placeable_types": ["dynamic"], "excluded": True}]}
    cands = {"C01": {"question": "Q1"}, "C02": {"question": "Q7"}}
    got = B.new_cases(rec, cands, lambda cid, t: 5)
    assert [c.id for c in got] == ["C01", "C02"]
    assert got[1].types == ["fixed"] and got[1].ops == {"fixed": [op(3)]} and got[1].difference == {"fixed": 5}
    assert got[0].excluded and all(c.holdout for c in got)
