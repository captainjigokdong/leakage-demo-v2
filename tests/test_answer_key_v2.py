"""4a: 정답표 형식 (designs/answer_key_v2.py, docs/answer_key_format_v2.md). 가짜 배치로만 시험한다."""
from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path

from designs import answer_key_v2 as K
from designs import build_v2 as B
from designs.patches_v1_cases import V1_CASE_PATCHES

ROOT = Path(__file__).resolve().parent.parent
SHA = "0" * 64


def public_entry(cid: str, question: str, verdict: str = "차단") -> dict:
    ex = K.PUBLIC_EXCEPTIONS.get(cid, {})
    return K.defect_entry(cid, question, False, verdict, V1_CASE_PATCHES[cid],
                          ex.get("support_targets"), ex.get("accept_questions"))


def sample_key() -> dict:
    return {"version": "v2", "priority": [list(r) for r in K.PRIORITY],
            "variants": {"design_0001.json": K.variant_entry(SHA, "aki_b", "dynamic",
                                                             [public_entry("E02", "Q1"), public_entry("E05", "Q2")]),
                         "design_0002.json": K.variant_entry(SHA, "readmit_b", "fixed", [public_entry("E09", "Q3")]),
                         "design_0003.json": K.variant_entry(SHA, "aki_a", "dynamic", [])}}


def test_sample_key_valid():
    assert K.validate_key(sample_key()) == []


def test_defaults_and_public_exceptions():
    e02 = public_entry("E02", "Q1")
    assert e02["accept_targets"] == ["features:cr_last"] and e02["support_targets"] == []
    assert e02["accept_questions"] == ["Q1"]
    e09 = public_entry("E09", "Q3")
    assert e09["accept_targets"] == ["preprocessing:dx_encode"]
    assert e09["support_targets"] == ["features:prior_dx_main"]
    assert public_entry("E04", "Q1")["accept_questions"] == ["Q1", "Q4"]
    e18 = public_entry("E18", "Q7", "경고")                 # 여러 칸 패치, 기본값 = 모두 accept
    assert len(e18["accept_targets"]) == len(set(e18["accept_targets"])) >= 2


def test_priority_order_fixed():
    assert [r[0] for r in K.PRIORITY] == ["accept", "support", "justified", "legit", "other"]
    assert [r[1] for r in K.PRIORITY] == ["탐지", "중립", "중립", "오경보", "오경보"]


def test_legit_and_justified_per_base():
    assert set(K.LEGIT_ITEMS) == {"aki_b", "aki_c", "readmit_b", "readmit_c"}
    for name in B.CLEAN_NAMES:
        cells = K.justified_cells(name)
        assert cells and all(c["cells"] for c in cells)
        ids = {c["id"] for c in cells}
        assert "L7" not in ids and ("L1" in ids) == name.startswith("aki")
    clean = B.load_clean()
    for base, items in K.LEGIT_ITEMS.items():                 # 항목이 바탕에 실제로 있음
        names = {f["name"] for f in clean[base]["features"]}
        assert all(t.split(":")[1] in names for t in items)


def test_validate_catches_errors():
    cases = []
    k = sample_key(); del k["variants"]["design_0001.json"]["justified"]; cases.append(k)
    k = sample_key(); k["variants"]["design_0003.json"]["kind"] = "defect"; cases.append(k)
    k = sample_key(); k["variants"]["design_0001.json"]["defects"][0]["support_targets"] = ["features:cr_last"]; cases.append(k)
    k = sample_key(); k["variants"]["design_0001.json"]["defects"][0]["accept_questions"] = ["Q2"]; cases.append(k)
    k = sample_key(); k["variants"]["design_0003.json"]["defects"] = [public_entry("E02", "Q1")]
    k["variants"]["design_0003.json"]["kind"] = "defect"; cases.append(k)                 # 같은 사례 두 번
    k = sample_key(); k["priority"] = list(reversed(k["priority"])); cases.append(k)
    k = sample_key(); k["variants"]["design_0002.json"]["sha256"] = "x"; cases.append(k)
    k = sample_key(); d = k["variants"]["design_0002.json"]["defects"]
    d.append(copy.deepcopy(d[0])); d[1]["id"] = "E99"; cases.append(k)                     # 한 변형 안 accept 겹침
    for k in cases:
        assert K.validate_key(k), k


def test_answer_key_module_does_not_import_checker():
    code = "import sys, designs.answer_key_v2; print(any(m.split('.')[0] == 'leakcheck' for m in sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
