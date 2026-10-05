import csv
import re
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


def _run(*args, cwd):
    return subprocess.run([sys.executable, str(RUN), *map(str, args)], capture_output=True, text=True, cwd=cwd)


def test_cli_exit_codes(tmp_path):
    ok = _run(TEST_BASE_DIR / "fixed_readmission.json", cwd=tmp_path)   # 경고만 있음 (차단 없음)
    assert json.loads((tmp_path / "checker.json").read_text(encoding="utf-8"))["blocked"] is False   # 기본 저장 위치
    assert ok.returncode == 0, ok.stderr
    assert "종료 코드 0 = 차단 없음" in ok.stdout
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(apply_ops(load_test_bases()["fixed"], V1_CASE_PATCHES["E08"]), ensure_ascii=False),
                   encoding="utf-8")
    out = tmp_path / "out.json"
    blocked = _run(bad, "--json", out, cwd=tmp_path)
    assert blocked.returncode == 1
    assert json.loads(out.read_text(encoding="utf-8"))["blocked"] is True
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps({"design_id": "x"}), encoding="utf-8")
    err = _run(broken, cwd=tmp_path)
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


# --- 스킬 폴더 내용 (3단계 3b) ---

SKILL_FILES = {"SKILL.md", "rules.md", "scripts/run_check.py"}


def _skill_files():
    return {str(p.relative_to(SKILL)) for p in SKILL.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


def test_skill_folder_has_only_known_files():
    assert _skill_files() == SKILL_FILES


def test_rules_md_matches_rules_table():
    """rules.md는 점검기 규칙표에서 만든 사본이다 (python -m tools.rules_md로 다시 만든다)."""
    from tools.rules_md import render
    assert (SKILL / "rules.md").read_text(encoding="utf-8") == render()


def test_skill_md_names_rules_location_first():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    body = text.split("---", 2)[2].strip().splitlines()
    first = next(l for l in body if l and not l.startswith("#"))
    assert "`rules.md`" in first


def test_skill_md_mentions_only_files_inside_skill_folder():
    """SKILL.md가 언급하는 파일·경로는 모두 스킬 폴더 안에 실제로 있다. <자리표시>는 예외."""
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    tokens = set(re.findall(r"[\w./<>\- ]*?[\w\-]+\.(?:md|py|json|csv|gz|enc|txt)\b", text))
    for t in tokens:
        t = t.strip().split()[-1]
        if t.startswith("<"):
            continue
        rel = t.split(">/", 1)[-1]           # "<이 스킬 폴더>/scripts/run_check.py" → "scripts/run_check.py"
        assert rel in SKILL_FILES, f"SKILL.md가 스킬 폴더 밖 파일을 언급: {t}"
    assert not re.search(r"(?<![\w<])(/|\.\./|~/)[A-Za-z]", text.replace("<이 스킬 폴더>/", "")), "절대·상위 경로 언급"
    for word in ("LEAKCHECK_HOME", "designs/", "data/", "leakcheck/", "skill_src", ".claude"):
        assert word not in text, word


def _forbidden_words():
    from designs.patches_v1_cases import V1_CASE_PATCHES
    words = {"prereview", "patches_v1", "error_catalog", "sealed", "holdout", "보류", "candidates"}
    for ops in V1_CASE_PATCHES.values():
        for op in ops:
            v = op.get("value")
            if isinstance(v, dict) and "name" in v:
                words.add(v["name"])
    with open(ROOT / "designs" / "error_catalog_public.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            words |= {r["id"], r["name"], r["how_to_inject"]}
    return words


def test_agent_visible_files_contain_no_case_material():
    """에이전트가 읽을 수 있는 파일(스킬 폴더, 점검기 사본)에 공개 사례 목록·패치 항목 이름·봉인 관련 낱말이 없다."""
    words = _forbidden_words()
    files = [SKILL / f for f in SKILL_FILES] + sorted((ROOT / "leakcheck").glob("*.py"))
    for p in files:
        text = p.read_text(encoding="utf-8")
        hits = [w for w in words if re.search(rf"(?<![\w]){re.escape(w)}(?![\w])", text)]
        assert not hits, (p.name, hits)
    for f in SKILL_FILES:
        text = (SKILL / f).read_text(encoding="utf-8")
        assert "tests/" not in text and "docs/" not in text, f


def test_every_rule_id_in_checker_is_explained():
    """점검기 출력의 rule 번호는 모두 rules.md(규칙표)에 설명이 있다."""
    from leakcheck import checks, rules
    src = (ROOT / "leakcheck" / "checks.py").read_text(encoding="utf-8")
    ids = set(re.findall(r'"((?:S|F|O|C|R|D)\.[a-z_]+)"', src)) - {"O.proxy.same_code_problem"}
    known = set(rules.PRINCIPLES) | {p["id"] for ps in rules.OUTCOME_PROXIES.values() for p in ps}
    assert ids <= known, ids - known
    md = (SKILL / "rules.md").read_text(encoding="utf-8")
    assert "O.proxy.same_code_problem" in md
    for i in ids:
        assert f"`{i}`" in md, i
    assert set(checks.A_QUESTION) == set(rules.ASSUMPTIONS)


def test_repeated_runs_never_overwrite_and_record_design(tmp_path):
    """같은 폴더에서 두 번 돌리면 결과 파일 두 개가 남고 첫 파일은 그대로다. 각 결과에 점검한 설계서의 이름·해시가 있다
    (6단계에서 원래 설계서를 점검한 결과를 골라낸다)."""
    import hashlib
    orig = tmp_path / "design.json"
    orig.write_bytes((TEST_BASE_DIR / "fixed_readmission.json").read_bytes())
    first = _run(orig, cwd=tmp_path)
    assert first.returncode == 0, first.stderr
    saved1 = (tmp_path / "checker.json").read_bytes()
    fixed = tmp_path / "design_fixed.json"
    d = json.loads(orig.read_text(encoding="utf-8"))
    d["split"]["method"] = "temporal"
    fixed.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    second = _run(fixed, cwd=tmp_path)
    third = _run(orig, "--json", "checker.json", cwd=tmp_path)    # 이름을 직접 줘도 덮어쓰지 않는다
    assert second.returncode in (0, 1) and third.returncode == 0
    assert sorted(p.name for p in tmp_path.glob("checker*.json")) == ["checker.json", "checker_2.json", "checker_3.json"]
    assert (tmp_path / "checker.json").read_bytes() == saved1
    runs = [json.loads((tmp_path / n).read_text(encoding="utf-8"))["checked"]
            for n in ("checker.json", "checker_2.json", "checker_3.json")]
    assert [r["design_file"] for r in runs] == ["design.json", "design_fixed.json", "design.json"]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assert [r["design_sha256"] for r in runs] == [sha(orig), sha(fixed), sha(orig)]
    assert "checker_2.json" in second.stdout
