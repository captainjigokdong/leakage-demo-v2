import csv
import json
import subprocess
import sys
from pathlib import Path

from designs.inject import apply_ops
from designs.patches_v1_cases import TEST_BASE_DIR, V1_CASE_PATCHES, load_test_bases

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skill_src" / "leakage-check"
RUN = SKILL / "scripts" / "run_check.py"


def test_skill_not_in_autoload_location():
    assert not (ROOT / ".claude" / "skills").exists()
    assert (SKILL / "SKILL.md").exists()


def test_skill_md_has_frontmatter_and_no_public_case_examples():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: leakage-check\n")
    with open(ROOT / "designs" / "error_catalog_public.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            assert r["id"] not in text
            assert r["name"] not in text
    for q in ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"):
        assert q in text
    assert "run_check.py" in text


def _run(*args):
    return subprocess.run([sys.executable, str(RUN), *map(str, args)], capture_output=True, text=True, cwd=ROOT)


def test_cli_exit_codes(tmp_path):
    ok = _run(TEST_BASE_DIR / "fixed_readmission.json")   # 경고만 있음 (차단 없음)
    assert ok.returncode == 0, ok.stderr
    assert "종료 코드 0 = 차단 없음" in ok.stdout
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(apply_ops(load_test_bases()["fixed"], V1_CASE_PATCHES["E08"]), ensure_ascii=False),
                   encoding="utf-8")
    out = tmp_path / "out.json"
    blocked = _run(bad, "--json", out)
    assert blocked.returncode == 1
    assert json.loads(out.read_text(encoding="utf-8"))["blocked"] is True
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps({"design_id": "x"}), encoding="utf-8")
    err = _run(broken)
    assert err.returncode == 2 and "점검 불가" in err.stderr


def test_cli_without_pandas_checks_design_and_reports_data_unable(tmp_path):
    """D10: pandas를 불러오지 못해도 설계서 점검은 돌고, 데이터 단계는 점검 불가로 보고한다 (종료 코드 2)."""
    out = tmp_path / "out.json"
    code = ("import runpy, sys; sys.modules['pandas'] = None; "
            f"sys.argv = ['run_check.py', {str(TEST_BASE_DIR / 'fixed_readmission.json')!r}, '--data', "
            f"{str(ROOT / 'data' / 'synth')!r}, '--json', {str(out)!r}]; "
            f"runpy.run_path({str(RUN)!r}, run_name='__main__')")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 2, r.stderr
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["data_checked"] is False
    unable = [f for f in rep["findings"] if f["verdict"] == "점검 불가"]
    assert unable and unable[0]["target"] == "data" and "pandas" in unable[0]["reason"]
    assert any(f["verdict"] == "경고" for f in rep["findings"])   # 설계서 점검은 그대로 됨
