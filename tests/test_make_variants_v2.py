"""4b 변형 생성(`tools/make_variants_v2.py`) 시험. 가짜 사례로만 한다 (봉인 내용 없음). 점검기를 쓰지 않는다."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from designs import build_v2 as B
from designs.answer_key_v2 import PRIORITY, validate_key
from designs.inject import dumps, file_sha256
from tools import make_variants_v2 as M

ROOT = Path(__file__).resolve().parent.parent
BASES = B.load_clean()


def fake(cid, q, t, ops, holdout=True):
    return B.Case(id=cid, question=q, holdout=holdout, types=[t], ops={t: ops})


F1 = [{"op": "append", "path": "features", "value": {"name": "x_one", "source": "labs", "test": ["creatinine"],
                                                    "agg": "count", "window_h": 24, "anchor": "tp"}}]


def test_does_not_import_checker():
    code = "import sys, tools.make_variants_v2; print(any(m.startswith('leakcheck') for m in sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


def test_make_applies_respects_exclusions():
    c = fake("X1", "Q1", "dynamic", F1)
    applies = M.make_applies([c], {("X1", "aki_a")})
    assert not applies(F1, BASES["aki_a"])
    assert applies(F1, BASES["aki_b"]) == B.default_applies(F1, BASES["aki_b"])


def test_blind_renames_and_keeps_content():
    import random
    b = BASES["aki_a"]
    v = M.blind(b, "0A1B", random.Random(1))
    assert v["design_id"] == "design_0A1B"
    assert sorted(x["name"] for x in v["features"]) == sorted(x["name"] for x in b["features"])
    assert sorted(x["name"] for x in v["cohort"]["exclusion"]) == sorted(x["name"] for x in b["cohort"]["exclusion"])
    assert [x["name"] for x in v["preprocessing"]] == [x["name"] for x in b["preprocessing"]]
    assert b["design_id"] == "aki_a"                                   # 바탕은 그대로


def test_build_variants_with_fake_layout():
    cases = {"X1": fake("X1", "Q1", "dynamic", F1)}
    layout = {"defect": [{"base": "aki_b", "cases": ["X1"]}], "clean": ["aki_a", "readmit_a"]}
    entry = lambda cid, t: {"id": cid, "question": "Q1", "holdout": True, "expected_verdict": "차단",
                            "accept_targets": ["features:x_one"], "support_targets": [], "accept_questions": ["Q1"]}
    sub = {n: BASES[n] for n in ("aki_a", "aki_b", "readmit_a")}
    variants, key = M.build_variants(layout, cases, sub, entry, seed=5, avoid={"0000"})
    assert len(variants) == 3
    for f, v in variants.items():
        assert re.fullmatch(r"design_[0-9A-F]{4}\.json", f) and f != "design_0000.json"
        assert key[f]["sha256"] == file_sha256(dumps(v))
        assert not re.search(r"\b[EXC]\d{1,2}\b", dumps(v))
    kinds = sorted((k["base"], k["kind"]) for k in key.values())
    assert kinds == [("aki_a", "clean"), ("aki_b", "defect"), ("readmit_a", "clean")]
    full = {"version": "v2", "priority": [list(r) for r in PRIORITY],
            "variants": key}
    assert validate_key(full) == []
    again, _ = M.build_variants(layout, cases, sub, entry, seed=5, avoid={"0000"})
    assert again == variants                                            # 같은 시드 → 같은 결과


def test_variant_list_format_is_read_by_grader(tmp_path):
    from experiment.grader import injection_log_hashes
    key = {"design_00AA.json": {"sha256": "a" * 64}, "design_00BB.json": {"sha256": "b" * 64}}
    p = tmp_path / "list.md"
    p.write_text(M.write_list(key), encoding="utf-8")
    assert injection_log_hashes(p) == {f: v["sha256"] for f, v in key.items()}
