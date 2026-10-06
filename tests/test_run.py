"""6단계 실행기 시험 (v2). 진짜 에이전트는 부르지 않는다 (가짜 실행기 + 가짜 OS 사용자)."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from experiment import grader, run

VALID = '[{"target": "split.key", "kind": "가정", "problem": "x"}]'


class FakeUsers(run.OsUser):
    def create(self, name, rd):
        pass

    def wrap(self, name, argv, env):
        return argv

    def remove(self, name, rd):
        pass


def stream(skills, result="끝", tools_used=(), model=run.MODEL, is_error=False, tools=run.VISIBLE_TOOLS,
           subtype="success", denied=(), results=()):
    """tools_used: (이름, 입력) 또는 (이름, 입력, id). denied: 권한 거부된 tool_use id. results: (id, 결과 문자열)."""
    ev = [{"type": "system", "subtype": "init", "model": model, "skills": list(skills), "tools": list(tools),
           "mcp_servers": [], "session_id": "sess-1"}]
    for i, t in enumerate(tools_used):
        name, inp = t[0], t[1]
        tid = t[2] if len(t) > 2 else f"t{i}"
        ev.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp,
                                                                 "id": tid}]}})
    for tid, text in results:
        ev.append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "content": text}]}})
    ev.append({"type": "result", "subtype": subtype, "is_error": is_error, "result": result,
               "num_turns": 3, "duration_ms": 1000, "total_cost_usd": 0.5, "session_id": "sess-1",
               "permission_denials": [{"tool_use_id": d, "tool_name": "Bash", "tool_input": {}} for d in denied]})
    return "\n".join(json.dumps(e, ensure_ascii=False) for e in ev).encode()


def launcher_from(plan, calls=None):
    """plan: 호출마다 (code, stream) — 작업 폴더에 유효한 findings.json을 쓴다 —, (code, stream, findings 문자열 또는 None),
    또는 함수(cwd)->(code, bytes)."""
    it = iter(plan)

    def launch(argv, cwd, timeout):
        if calls is not None:
            calls.append(argv)
        step = next(it)
        if callable(step):
            code, out = step(cwd)
        else:
            code, out = step[0], step[1]
            f = step[2] if len(step) > 2 else VALID
            if f is not None:
                (cwd / "findings.json").write_text(f, encoding="utf-8")
        return code, out, b"", 1.0
    return launch


def go(tmp_path, cond, plan, rid="abc123def456", calls=None):
    row = {"condition": cond, "rep": 1, "batch": 1, "variant": run.variants()[0], "order": 0}
    out = tmp_path / "out"
    run.ensure_schedule(out, {rid: row})
    meta = run.run_row(out, rid, row, run.MODEL, FakeUsers(), launcher_from(plan, calls), tmp_path / "runs")
    return out, meta


def skills(cond):
    return ["leakage-check"] if cond == "가" else []


def bash(cmd, tid="t0"):
    return [{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "id": tid,
                                                           "input": {"command": cmd}}]}}]


def use(name, inp, tid="t0"):
    return [{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "id": tid, "input": inp}]}}]


# ---------------------------------------------------------------- 실행표

def test_schedule_balanced_and_deterministic():
    vs = run.variants()
    assert len(vs) == 30 and run.REPS == 2
    s = run.build_schedule(vs, run.REPS, run.SCHEDULE_SEED)
    assert len(s) == 120 and s == run.build_schedule(vs, run.REPS, run.SCHEDULE_SEED)
    for v in vs:
        for c in run.CONDITIONS:
            assert sorted(r["rep"] for r in s.values() if r["variant"] == v and r["condition"] == c) == [1, 2]
    assert sorted(r["order"] for r in s.values()) == list(range(120))
    # 반복 단위 묶음: 묶음 b의 60행이 순서 60(b-1)..60b-1을 차지
    for b in (1, 2):
        rows = [r for r in s.values() if r["batch"] == b]
        assert len(rows) == 60 and all(r["rep"] == b for r in rows)
        assert sorted(r["order"] for r in rows) == list(range(60 * (b - 1), 60 * b))
        assert {(r["variant"], r["condition"]) for r in rows} == {(v, c) for v in vs for c in run.CONDITIONS}
    assert all(len(rid) == 12 for rid in s)


def test_pilot_one_variant_same_seed():
    vs = run.pilot_variants()
    assert len(vs) == 1 and vs == run.pilot_variants() and vs[0] in run.variants()
    s = run.build_schedule(vs, 1, run.PILOT_SEED)
    assert len(s) == 2 and {r["condition"] for r in s.values()} == set(run.CONDITIONS)
    assert s == run.build_schedule(run.pilot_variants(), 1, run.PILOT_SEED)


def test_schedule_is_not_changed(tmp_path):
    s = run.build_schedule(run.variants(), 2, 1)
    run.ensure_schedule(tmp_path, s)
    rid = next(iter(s))
    run.record_condition(tmp_path, rid, turn_capped=True, format_retries=1)   # 실행 결과 칸은 일정 비교에서 뺀다
    assert run.ensure_schedule(tmp_path, s)[rid]["turn_capped"] is True
    with pytest.raises(RuntimeError):
        run.ensure_schedule(tmp_path, run.build_schedule(run.variants(), 2, 2))


# ---------------------------------------------------------------- 실행 폴더

def test_run_dirs_differ_only_by_skill(tmp_path):
    v = run.variants()[0]
    a = run.prepare_run(tmp_path, "a", v, "가")
    b = run.prepare_run(tmp_path, "b", v, "나")
    assert (a.ws / ".claude" / "skills" / "leakage-check" / "SKILL.md").exists()
    assert not (b.ws / ".claude").exists() and b.lchome is None
    files = lambda rd: sorted(str(p.relative_to(rd.ws)) for p in rd.ws.rglob("*")
                              if p.is_file() and ".claude" not in p.parts)
    assert files(a) == files(b)
    assert a.inputs == b.inputs
    # 에이전트용 문서 2개가 두 조건에 같은 이름·같은 내용으로 있다
    for name, body in run.prompt.agent_docs().items():
        assert (a.ws / name).read_bytes() == body == (b.ws / name).read_bytes() and name in a.inputs


def test_no_skill_or_checker_code_in_na_folder(tmp_path):
    b = run.prepare_run(tmp_path, "b", run.variants()[0], "나")
    names = [str(p.relative_to(b.root)) for p in b.root.rglob("*")]
    assert not any(x in n for n in names for x in ("SKILL.md", "rules.md", "run_check.py", "leakcheck", "lchome"))
    assert not (run.ROOT / ".claude" / "skills").exists()


def test_lchome_copy_has_only_checker_files(tmp_path):
    a = run.prepare_run(tmp_path, "a", run.variants()[0], "가")
    assert "leakcheck/checks.py" in a.lchome_files and "designs/schema.json" in a.lchome_files
    for f in a.lchome_files:
        assert not any(f == x or f.startswith(x + "/") for x in run.LEAKCHECK_EXCLUDED), f
        assert not f.endswith(".csv") and not f.startswith("synth/")      # 생성기는 넣지 않는다
    assert not list(a.root.rglob("generate*.py")) and not list(a.root.rglob("__pycache__"))


def test_lchome_copy_runs_checker(tmp_path):
    """사본으로 점검기가 돈다. 변형에는 돌리지 않는다 (깨끗한 설계서로 확인)."""
    import os
    import subprocess
    import sys
    a = run.prepare_run(tmp_path, "a", run.variants()[0], "가")
    script = a.ws / ".claude" / "skills" / "leakage-check" / "scripts" / "run_check.py"
    env = {"PATH": os.environ["PATH"], "LEAKCHECK_HOME": str(a.lchome)}
    clean = run.ROOT / "designs" / "clean_v2" / "aki_a.json"
    p = subprocess.run([sys.executable, str(script), str(clean), "--json", str(tmp_path / "c.json")], cwd=tmp_path,
                       env=env, capture_output=True)
    assert p.returncode in (0, 1), p.stderr.decode()


def test_prompt_same_for_both_conditions():
    argv = run.agent_argv(run.prompt.render("design_X.json", "data"), run.MODEL)
    assert "WebSearch" in argv and "WebFetch" in argv and "--strict-mcp-config" in argv
    assert argv[argv.index("--max-turns") + 1] == "60"


def test_turn_limits_come_from_grader():
    assert (run.MAX_TURNS, run.MAX_TURNS_RETRY, run.FORMAT_RETRIES) == (grader.MAX_TURNS, grader.MAX_TURNS_RETRY,
                                                                        grader.FORMAT_RETRIES) == (60, 5, 1)
    argv = run.agent_argv("x", run.MODEL, max_turns=run.MAX_TURNS_RETRY, resume="s")
    assert argv[argv.index("--max-turns") + 1] == "5" and argv[argv.index("--resume") + 1] == "s"


def test_env_drops_only_contaminating_vars(tmp_path):
    base = {"CLAUDE_ADDITIONAL_DIRECTORIES": "/home/user/leakage-demo", "CLAUDE_CODE_SESSION_ID": "x",
            "CLAUDE_CODE_REMOTE_SESSION_ID": "x", "CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD": "1",
            "CLAUDECODE": "1", "SOME_OTHER": "kept", "SSL_CERT_FILE": "/root/.ccr/ca-bundle.crt",
            "LEAKCHECK_HOME": "/home/user/leakage-demo"}
    rd = run.prepare_run(tmp_path, "a", run.variants()[0], "가")
    env = run.agent_env(rd, "가", base)
    assert not set(run.ENV_DROP) & set(env)
    assert env["SOME_OTHER"] == "kept"
    assert env["CLAUDE_CONFIG_DIR"] == str(rd.cfg) and env["HOME"] == str(rd.home)
    assert not env["SSL_CERT_FILE"].startswith("/root") and env["LEAKCHECK_HOME"] == str(rd.lchome)
    rb = run.prepare_run(tmp_path, "b", run.variants()[0], "나")
    assert "LEAKCHECK_HOME" not in run.agent_env(rb, "나", base)
    assert "ANTHROPIC_API_KEY" not in open(run.__file__, encoding="utf-8").read()


# ---------------------------------------------------------------- 실행, 수거, 재제출

@pytest.mark.parametrize("cond", run.CONDITIONS)
def test_ok_run_saves_blinded_report(tmp_path, cond):
    out, meta = go(tmp_path, cond, [(0, stream(skills(cond)))])
    assert meta["status"] == "done" and meta["retries"] == 0
    rec = json.loads((out / "reports" / "abc123def456.json").read_text())
    assert rec == {"report_id": "abc123def456", "variant": run.variants()[0], "findings": VALID}
    assert (out / "checker" / "abc123def456.json").exists() == (cond == "가")
    assert (out / "transcripts" / "abc123def456.jsonl.gz").exists()
    assert not (out / "discarded").exists()
    c = json.loads((out / "conditions.json").read_text())["abc123def456"]
    assert c["turn_capped"] is False and c["format_retries"] == 0
    assert meta["attempts"][0]["init"]["skills"] == skills(cond)


def test_work_folder_kept_and_file_list_recorded(tmp_path):
    out, meta = go(tmp_path, "나", [(0, stream([]))])
    root = tmp_path / "runs" / "abc123def456-t1"
    assert (root / "ws" / "findings.json").exists()                       # 지우지 않고 보관
    files = {f["path"]: f for f in meta["attempts"][0]["files"]}
    assert set(files["ws/findings.json"]) == {"path", "size", "sha256"}   # 이름·크기·해시만
    assert VALID not in json.dumps(meta, ensure_ascii=False)               # 제출 내용은 meta에 없다


def test_missing_findings_resubmitted_once(tmp_path):
    calls = []
    out, meta = go(tmp_path, "나", [(0, stream([]), None), (0, stream([]))], calls=calls)
    assert len(calls) == 2 and meta["status"] == "done" and meta["retries"] == 0
    a = meta["attempts"][0]
    assert a["format_retries"] == 1 and a["resubmit"]["errors_before"] == ["파일 없음"] and a["findings_valid"]
    second = calls[1]
    assert second[second.index("--resume") + 1] == "sess-1" and second[second.index("--max-turns") + 1] == "5"
    assert second[2] == run.RESUBMIT_TEXT.format(errors="파일 없음")
    assert json.loads((out / "conditions.json").read_text())["abc123def456"]["format_retries"] == 1


def test_resubmit_only_once_then_score_as_is(tmp_path):
    out, meta = go(tmp_path, "나", [(0, stream([]), "not json"), (0, stream([]), None)])
    assert meta["status"] == "done" and meta["attempts"][0]["format_retries"] == 1
    assert json.loads((out / "reports" / "abc123def456.json").read_text())["findings"] == "not json"


def test_resubmit_text_same_for_both_conditions(tmp_path):
    texts = []
    for cond in run.CONDITIONS:
        calls = []
        go(tmp_path / cond, cond, [(0, stream(skills(cond)), None), (0, stream(skills(cond)))], calls=calls)
        texts.append(calls[1][2])
    assert texts[0] == texts[1]


def test_turn_capped_not_retried_and_resubmitted_if_missing(tmp_path):
    capped = stream([], subtype="error_max_turns", is_error=True)
    calls = []
    out, meta = go(tmp_path, "나", [(1, capped, None), (0, stream([]), None)], calls=calls)
    assert meta["status"] == "done" and meta["retries"] == 0 and len(calls) == 2
    a = meta["attempts"][0]
    assert a["turn_capped"] is True and a["format_retries"] == 1
    assert json.loads((out / "reports" / "abc123def456.json").read_text())["findings"] is None   # 재제출 뒤에도 없음 → 지적 0개
    c = json.loads((out / "conditions.json").read_text())["abc123def456"]
    assert c == {**c, "turn_capped": True, "format_retries": 1}


@pytest.mark.parametrize("bad,reason", [
    ((1, None), "종료 코드 오류"),
    ((None, None), "시간 초과"),
    ((0, "skills_wrong"), "조작 확인 실패"),
    ((0, "model"), "조작 확인 실패"),
])
def test_mechanical_failure_retried_and_discarded_separately(tmp_path, bad, reason):
    code, kind = bad
    cond = "가"
    if kind == "skills_wrong":
        s = stream([])
    elif kind == "model":
        s = stream(skills(cond), model="claude-haiku-4-5")
    else:
        s = stream(skills(cond), result="중간 결과")
    out, meta = go(tmp_path, cond, [(code, s), (0, stream(skills(cond)))])
    assert meta["status"] == "done" and meta["retries"] == 1
    assert any(reason in r for r in meta["retry_reasons"])
    d = out / "discarded" / "abc123def456" / "try1"
    assert (d / "transcript.jsonl.gz").exists() and (d / "attempt.json").exists()
    assert [p.name for p in (out / "reports").iterdir()] == ["abc123def456.json"]


def test_checker_not_run_is_not_a_failure(tmp_path):
    out, meta = go(tmp_path, "가", [(0, stream(skills("가")))])
    assert meta["status"] == "done" and meta["attempts"][0]["audit"]["checker_invoked"] is False


def test_all_attempts_fail(tmp_path):
    out, meta = go(tmp_path, "나", [(1, b"")] * (run.MAX_RETRIES + 1))
    assert meta["status"] == "failed" and len(meta["attempts"]) == run.MAX_RETRIES + 1
    assert not (out / "reports").exists()


def test_input_modification_recorded_only(tmp_path):
    def tamper(cwd: Path):
        f = next(cwd.glob("design_*.json"))
        f.chmod(0o644)
        f.write_text("{}")
        (cwd / "findings.json").write_text("[]")
        return 0, stream([])
    out, meta = go(tmp_path, "나", [tamper])
    assert meta["status"] == "done" and meta["retries"] == 0
    assert meta["attempts"][0]["inputs_changed"] == [run.variants()[0]]


def test_web_tool_use_recorded_only(tmp_path):
    out, meta = go(tmp_path, "나", [(0, stream([], tools_used=[("WebSearch", {"query": "x"})]))])
    assert meta["status"] == "done" and meta["retries"] == 0
    assert meta["attempts"][0]["audit"]["violations"]


def test_contamination_read_discards_without_retry(tmp_path):
    s = stream([], tools_used=[("Bash", {"command": f"cat {run.ROOT}/CLAUDE.md"})])
    calls = []
    out, meta = go(tmp_path, "나", [(0, s, None)], calls=calls)
    assert meta["status"] == "discarded" and len(calls) == 1             # 재실행·재제출 없음
    assert meta["attempts"][0]["reasons"] == ["폐기①"]
    assert not (out / "reports").exists()                                 # 빈칸
    assert (out / "discarded" / "abc123def456" / "try1" / "attempt.json").exists()


def test_lchome_path_forbidden_only_for_na(tmp_path):
    rd_a = run.prepare_run(tmp_path, "a", run.variants()[0], "가")
    cmd = lambda rd: bash(f"python {rd.root}/lchome/leakcheck/checks.py")
    assert run.audit(cmd(rd_a), rd_a, "가")["violations"] == []
    rd_b = run.prepare_run(tmp_path, "b", run.variants()[0], "나")
    assert run.audit(cmd(rd_b), rd_b, "나")["violations"]
    other = use("Read", {"file_path": f"{run.RUN_BASE}/zzz-t1/ws/x"})
    assert run.audit(other, rd_b, "나")["violations"]
    assert [h["class"] for h in run.audit(other, rd_b, "나")["discard"]] == ["①"]


def test_checker_invocation_recorded_not_required(tmp_path):
    out, meta = go(tmp_path, "가", [(0, stream(skills("가"), tools_used=[
        ("Bash", {"command": "python .claude/skills/leakage-check/scripts/run_check.py design.json --data data"})]))])
    assert meta["attempts"][-1]["audit"]["checker_invoked"] is True
    out2, meta2 = go(tmp_path / "2", "가", [(0, stream(skills("가")))])
    assert meta2["status"] == "done" and meta2["attempts"][-1]["audit"]["checker_invoked"] is False


# ---------------------------------------------------------------- 점검기 출력 수거 ((가))

def test_checker_collected_by_hash_first_number_ws_first(tmp_path):
    v = run.variants()[0]

    def agent(cwd: Path):
        sha = run.sha256(cwd / v)
        put = lambda p, h: p.write_text(json.dumps({"findings": [], "checked": {"design_file": v, "design_sha256": h}}))
        put(cwd / "checker.json", "0" * 64)                  # 고친 설계서를 점검 (기록만)
        put(cwd / "checker_3.json", sha)
        put(cwd / "checker_2.json", sha)                     # 원래 설계서, 번호가 가장 작음 → 채택
        put(cwd.parent / "tmp" / "checker.json", sha)        # 작업 폴더 밖 (실행 폴더 안): 작업 폴더가 먼저
        (cwd / "findings.json").write_text("[]")
        return 0, stream(skills("가"), tools_used=[("Bash", {"command": "python3 x"}, "c1")],
                         results=[("c1", "결과 JSON(… sha256 abc): checker_2.json\n\n종료 코드 1 = 차단 있음")])
    out, meta = go(tmp_path, "가", [agent])
    rec = json.loads((out / "checker" / "abc123def456.json").read_text())
    assert rec["source_file"] == "ws/checker_2.json" and rec["exit_code"] == 1
    assert set(rec) >= {"report_id", "variant", "exit_code", "checker"} and "condition" not in rec
    files = meta["attempts"][0]["checker_files"]
    assert [f["path"] for f in files][:3] == ["ws/checker.json", "ws/checker_2.json", "ws/checker_3.json"]
    assert len(list((out / "checker_files" / "abc123def456").iterdir())) == 4


def test_checker_missing_recorded_as_none(tmp_path):
    out, meta = go(tmp_path, "가", [(0, stream(skills("가")))])
    rec = json.loads((out / "checker" / "abc123def456.json").read_text())
    assert rec["checker"] is None and rec["exit_code"] is None


# ---------------------------------------------------------------- 폐기 판정: 내용을 읽음만 (권한 거부·이름 조회는 기록만)

R = str(run.ROOT)
OTHER = f"{run.RUN_BASE}/zzz999-t1"


@pytest.mark.parametrize("events", [
    bash(f"cat {R}/CLAUDE.md"),
    bash(f"head -3 {OTHER}/ws/findings.json"),
    bash(f"cd {OTHER}/ws && cat findings.json"),
    bash(f"cut -d, -f1 {OTHER}/ws/data/a.csv | sort | uniq -c"),
    bash(f"sort /root/.claude/projects/x.jsonl"),
    bash(f"tr a b < {R}/sealed/answer_key.enc"),
    bash(f"python3 -c \"print(open('{R}/docs/phases.md').read())\""),
    bash(f"python3 - <<'EOF'\nimport json\nprint(open('{OTHER}/ws/findings.json').read())\nEOF"),
    bash("python3 -c \"print(open('/tmp/claude-0/-home-user-leakage-demo-v2/x.jsonl').read())\""),
    use("Read", {"file_path": f"{R}/sealed/answer_key.enc"}),
    use("Grep", {"pattern": "x", "path": f"{R}/docs"}),
    use("Write", {"file_path": "/x/ws/s.py", "content": f"print(open('{R}/CLAUDE.md').read())\n"}) + bash("python3 s.py", "t1"),
])
def test_discard_when_content_read(tmp_path, events):
    rd = run.prepare_run(tmp_path, "abc-t1", run.variants()[0], "나")
    hits = run.audit(events, rd, "나")["discard"]
    assert hits and {h["class"] for h in hits} == {"①"}, hits
    assert all(h["basis"] in (run.CERTAIN, run.CONSERVATIVE) for h in hits)


@pytest.mark.parametrize("events,basis", [
    (use("Read", {"file_path": f"{R}/CLAUDE.md"}), "확실한 읽음"),
    (bash(f"cat {R}/CLAUDE.md"), "확실한 읽음"),
    (bash(f"python3 -c \"print(open('{R}/CLAUDE.md').read())\""), "확실한 읽음"),
    (bash(f"python3 -c \"from pathlib import Path; print(Path('{R}/CLAUDE.md').read_text())\""), "확실한 읽음"),
    (bash(f"python3 -c \"p = '{R}/CLAUDE.md'; print(p)\""), "보수적 판정"),          # 변수로 넘김: 여는지 모름
])
def test_discard_basis_recorded(tmp_path, events, basis):
    rd = run.prepare_run(tmp_path, "abc-t1", run.variants()[0], "나")
    assert [h["basis"] for h in run.audit(events, rd, "나")["discard"]] == [basis]


@pytest.mark.parametrize("events", [
    bash(f"ls {R}/sealed"),
    bash(f"find {run.RUN_BASE} -name '*.json'"),
    bash(f"cd {OTHER} && ls -R"),
    use("Glob", {"pattern": "**/*.enc", "path": R}),
    bash(f"python3 -c \"import os; print(os.listdir('{run.RUN_BASE}'))\""),
    bash(f"python3 -c \"from pathlib import Path; print(list(Path('{run.RUN_BASE}').iterdir()))\""),
    bash(f"cat {R}/CLAUDE.md", "d1"),                                     # 권한 거부됨 (아래에서 거부 목록에 넣음)
    use("Write", {"file_path": "/x/ws/s.py", "content": f"print(open('{R}/CLAUDE.md').read())\n"}),   # 쓰기만, 실행 안 함
    bash("cat data/labs.csv.gz | head; cat findings.json; python3 .claude/skills/leakage-check/scripts/run_check.py d.json"),
    use("Read", {"file_path": "/tmp/claude-0/-srv-leakruns-abc-t1-ws/x/y.py"}),
])
def test_no_discard_for_names_denied_or_own_files(tmp_path, events):
    rd = run.prepare_run(tmp_path, "abc-t1", run.variants()[0], "나")
    events = events + [{"type": "result", "permission_denials": [{"tool_use_id": "d1"}]}]
    assert run.audit(events, rd, "나")["discard"] == []


def test_skill_code_read_is_discard_2_only_for_na(tmp_path):
    ev = bash("cat /opt/elsewhere/lchome/leakcheck/checks.py")
    for cond, want in (("나", ["②"]), ("가", [])):
        rd = run.prepare_run(tmp_path, f"x{cond}", run.variants()[0], cond)
        assert [h["class"] for h in run.audit(ev, rd, cond)["discard"]] == want


# ---------------------------------------------------------------- 이어 실행, 상태

def test_resume_skips_done(tmp_path):
    vs = run.variants()[:2]
    sched = run.build_schedule(vs, 1, 3)
    out = tmp_path / "out"
    run.ensure_schedule(out, sched)
    calls = []

    def launch(argv, cwd, timeout):
        calls.append(cwd)
        (cwd / "findings.json").write_text("[]")
        has = (cwd / ".claude").exists()
        return 0, stream(["leakage-check"] if has else []), b"", 1.0

    kw = dict(users=FakeUsers(), launcher=launch, base=tmp_path / "runs")
    run.run_all(out, sched, run.MODEL, workers=2, limit=2, **kw)
    assert len(run.pending(out, sched)) == 2
    run.run_all(out, sched, run.MODEL, workers=2, **kw)
    assert run.pending(out, sched) == [] and len(calls) == 4
    st = run.status(out)
    assert st["가"]["done"] == 2 and st["나"]["done"] == 2 and st["가"]["retries"] == 0
    assert st["skills_only_in"] == {"가": ["leakage-check"], "나": []}


def test_permission_args_same_for_both_and_no_bypass():
    argv = run.agent_argv("x", run.MODEL)
    assert "bypassPermissions" not in " ".join(argv)
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert {"Read", "Glob", "Grep", "Skill", "Write", "Bash(python:*)", "Bash(python3:*)",
            "Bash(LEAKCHECK_HOME=*)", "Bash(export:*)"} <= set(run.ALLOWED_TOOLS)
    for c in ("cd", "ls", "cat", "head", "tail", "wc", "echo", "sed", "grep", "zcat", "mkdir", "pwd",
              "cut", "sort", "uniq", "tr"):
        assert f"Bash({c}:*)" in run.ALLOWED_TOOLS
    assert not any(x in " ".join(run.ALLOWED_TOOLS) for x in ("rm", "cp", "mv", "curl", "Edit(", "Agent"))
    assert run.MAX_RETRIES == 5


def test_permission_denials_recorded(tmp_path):
    s = stream(skills("가")).replace(b'"permission_denials": []', b'"permission_denials": '
        b'[{"tool_name": "Bash", "tool_input": {"command": "cd .claude && python scripts/run_check.py d.json"}},'
        b' {"tool_name": "Edit", "tool_input": {"file_path": "x"}}]')
    out, meta = go(tmp_path, "가", [(0, s)])
    d = meta["attempts"][-1]["permission_denials"]
    assert d["count"] == 2 and d["checker_denied"] == 1 and d["by_tool"] == {"Bash": 1, "Edit": 1}
    assert meta["status"] == "done"


def test_limit_stops_without_counting_attempt(tmp_path):
    lim = stream([], result="Claude usage limit reached", is_error=True)
    row = {"condition": "나", "rep": 1, "variant": run.variants()[0], "order": 0}
    with pytest.raises(run.LimitReached):
        run.run_row(tmp_path / "out", "abc123def456", row, run.MODEL, FakeUsers(), launcher_from([(1, lim)]),
                    tmp_path / "runs")
    assert not (tmp_path / "out" / "meta").exists() and not (tmp_path / "out" / "reports").exists()
    kept = list((tmp_path / "out" / "discarded" / "abc123def456").iterdir())
    assert len(kept) == 1 and kept[0].name.startswith("limit")           # 부분 출력은 따로 둔다
    assert not (tmp_path / "runs" / "abc123def456-t1").exists()          # 작업 폴더는 다른 이름으로 보관
    assert list((tmp_path / "runs").glob("abc123def456-t1-limit*"))


def test_report_mentioning_limit_is_not_limit():
    assert not run.is_limit({"is_error": False, "result": "rate limit 관련 특징 ..."}, b"")


def test_batches_resume_after_limit(tmp_path):
    vs = run.variants()[:2]
    sched = run.build_schedule(vs, 2, 3)        # 묶음 2개 × 4행
    out = tmp_path / "out"
    run.ensure_schedule(out, sched)
    n = {"calls": 0}
    order = []

    def launch(argv, cwd, timeout):
        n["calls"] += 1
        order.append(cwd.parent.name.split("-")[0])
        if n["calls"] == 6:
            return 1, stream([], result="usage limit reached", is_error=True), b"", 1.0
        (cwd / "findings.json").write_text("[]")
        has = (cwd / ".claude").exists()
        return 0, stream(["leakage-check"] if has else []), b"", 1.0

    kw = dict(users=FakeUsers(), launcher=launch, base=tmp_path / "runs")
    assert run.run_batches(out, sched, run.MODEL, 1, commit=False, **kw) is False
    first = {rid for rid, r in sched.items() if r["batch"] == 1}
    assert not set(run.pending(out, sched)) & first
    assert len(run.pending(out, sched)) == 3
    assert run.run_batches(out, sched, run.MODEL, 1, commit=False, **kw) is True
    assert run.pending(out, sched) == []
    # 이어 갈 때 일정 순서 그대로: 끊긴 행부터 다시
    by_order = sorted(sched, key=lambda r: sched[r]["order"])
    assert order[5] == order[6] == by_order[5]
    assert [o for i, o in enumerate(order) if i != 5] == by_order


def test_main_requires_batches():
    with pytest.raises(SystemExit):
        run.main(["main"])


# ---------------------------------------------------------------- root 실행: 권한 규칙과 기록용 접근 검사

def test_root_mode_and_deny_settings():
    assert run.RUN_AS == "root" and isinstance(run.default_users(), run.RootUser)
    rules = run.deny_settings()["permissions"]["deny"]
    for p in ("/home/user", "/root", "/mnt/user-data"):
        for t in ("Read", "Glob", "Grep"):
            assert f"{t}(/{p}/**)" in rules
    argv = run.RootUser().wrap("x", run.agent_argv("t", run.MODEL, Path("/s.json")), {"A": "1"})
    assert argv[:3] == ["env", "-i", "A=1"] and "--settings" in argv and "setpriv" not in argv
    i = argv.index("--tools")
    assert argv[i + 1:i + 7] == list(run.VISIBLE_TOOLS) and "Agent" not in run.VISIBLE_TOOLS
    assert Path(run.HOOK_PYTHON).exists()


@pytest.mark.parametrize("cmd", [
    "python3 -c \"import os; print(os.listdir('/'))\"",
    "python -c \"import os; [print(r) for r in os.walk('/home')]\"",
    "python3 -c \"open('../../home/x')\"",
    "python3 script.py ../..",
    "python3 -c \"import glob; print(glob.glob('/srv/*'))\"",
    "python3 -c \"print(open('/root/.claude/x').read())\"",
    "python3 -c \"import os; os.path.expanduser('~root')\"",
    "python3 -c \"from pathlib import Path; print(list(Path('/mnt').iterdir()))\"",
])
def test_broadened_audit_flags(tmp_path, cmd):
    rd = run.prepare_run(tmp_path, "a", run.variants()[0], "나")
    assert run.audit(bash(cmd), rd, "나")["violations"], cmd


@pytest.mark.parametrize("cmd", [
    "python3 -c \"import pandas as pd; df = pd.read_csv('data/labs.csv.gz'); print(df.x / 2)\"",
    "python .claude/skills/leakage-check/scripts/run_check.py design_0B14.json --data data",
    "python3 -c \"print(1/3, 'a/b')\"",
    "python3 -c \"x = [1, 2]; print(x[...])\"",
])
def test_broadened_audit_allows_normal_work(tmp_path, cmd):
    rd = run.prepare_run(tmp_path, "a", run.variants()[0], "가")
    a = run.audit(bash(cmd), rd, "가")
    assert a["violations"] == [] and a["discard"] == [], cmd


def test_written_script_content_audited(tmp_path):
    rd = run.prepare_run(tmp_path, "a", run.variants()[0], "나")
    ev = use("Write", {"file_path": f"{rd.ws}/s.py", "content": "import os\nfor r in os.walk('/'):\n    pass\n"})
    assert run.audit(ev, rd, "나")["violations"]
    (rd.ws / "t.py").write_text("print(open('/home/user/leakage-demo/CLAUDE.md').read())\n")
    assert run.audit_scripts(rd, "나")
    (rd.ws / "t.py").write_text("import pandas\n")
    assert run.audit_scripts(rd, "나") == []


def test_discards_counted(tmp_path):
    bad = stream([], tools_used=[("Read", {"file_path": f"{R}/sealed/answer_key.enc"})])
    row = {"condition": "나", "rep": 1, "batch": 1, "variant": run.variants()[0], "order": 0}
    out = tmp_path / "out"
    run.ensure_schedule(out, {"abc123def456": row})
    run.run_row(out, "abc123def456", row, run.MODEL, FakeUsers(), launcher_from([(0, bad)]), tmp_path / "runs")
    st = run.status(out)
    assert st["나"]["discarded"] == 1 and st["나"]["done"] == 0 and st["나"]["blank"] == 1
    assert run.pending(out, {"abc123def456": row}) == []                  # 폐기 행은 다시 돌리지 않는다


def test_auth_error_stops_without_retry(tmp_path):
    bad = stream([], result="Authentication error · This may be a temporary network issue", is_error=True)
    row = {"condition": "나", "rep": 1, "variant": run.variants()[0], "order": 0}
    with pytest.raises(run.LimitReached):
        run.run_row(tmp_path / "out", "abc123def456", row, run.MODEL, FakeUsers(), launcher_from([(1, bad)]),
                    tmp_path / "runs")


# ---------------------------------------------------------------- v1 시험 실행 3·4차 폐기 사례의 형태 (v2 가짜 기록으로 대체)
# v1 보관 기록(v1 저장소 experiment/pilot/_run3·_run4)은 가져오지 않는다. 주석에 남은 형태를 v2 판정으로 다시 확인한다.

def _audit(cmd_or_events, cond="나", name="278c665bce74-t2"):
    import tempfile
    d = Path(tempfile.mkdtemp())
    rd = run.prepare_run(d, name, run.variants()[0], cond)
    ev = bash(cmd_or_events) if isinstance(cmd_or_events, str) else cmd_or_events
    return run.audit(ev, rd, cond)


# 3차 오탐 4건: 자기 임시 폴더, 코드 안의 '/' 문자열 → 기록도 폐기도 없음
PILOT3_FP = [
    use("Read", {"file_path": "/tmp/claude-0/-srv-leakruns-278c665bce74-t2-ws/x/y.py"}),
    "cat /tmp/claude-0/-srv-leakruns-278c665bce74-t2-ws/scratch/a.txt",
    "python3 -c \"print('a/b'.split('/'))\"",
    "python3 -c \"x = '/'.join(['a', 'b'])\"",
]
# 3차 실제 탐색 2건: find /, 다른 실행 폴더 순회 → 기록하되 폐기는 아님 (이름 조회)
PILOT3_TP = ["find / -name '*.enc'", f"find {run.RUN_BASE} -name findings.json"]
# 4차 오탐 4건: 점검기 결과를 ws/../tmp/... (자기 실행 폴더 안)에 저장, 경로 없는 ls -R
PILOT4_FP = [
    "python3 .claude/skills/leakage-check/scripts/run_check.py d.json --json ../tmp/r.json",
    "python3 .claude/skills/leakage-check/scripts/run_check.py d.json --data data --json ../tmp/checker.json",
    "cat ../tmp/r.json | head -20",
    "ls -R",
]


@pytest.mark.parametrize("case", PILOT3_FP)
def test_pilot3_false_positives_cleared(case):
    a = _audit(case)
    assert a["violations"] == [] and a["discard"] == []


@pytest.mark.parametrize("cmd", PILOT3_TP)
def test_pilot3_real_exploration_still_flagged(cmd):
    a = _audit(cmd)
    assert a["violations"] and a["discard"] == []


@pytest.mark.parametrize("cmd", PILOT4_FP)
def test_pilot4_false_positives_cleared(cmd):
    a = _audit(cmd, cond="가")
    assert a["violations"] == [] and a["discard"] == []


def test_own_tmp_allowed_other_tmp_forbidden(tmp_path):
    rd = run.prepare_run(tmp_path, "abc123def456-t2", run.variants()[0], "나")
    read = lambda p: use("Read", {"file_path": p})
    assert run.audit(read("/tmp/claude-0/-srv-leakruns-abc123def456-t2-ws/x/y.py"), rd, "나")["violations"] == []
    for bad in ("/tmp/claude-0/-srv-leakruns-abc123def456-t1-ws/x", "/tmp/claude-0/-home-user-leakage-demo/x",
                "/tmp/claude-0"):
        assert run.audit(read(bad), rd, "나")["violations"], bad


@pytest.mark.parametrize("cmd", ["ls /", "find / -name x", "python3 -c \"import os; os.listdir('/')\"",
                                 "python3 -c \"import os; list(os.walk('/'))\"", "ls -la /srv",
                                 "python3 -c \"from pathlib import Path; list(Path('/').rglob('*'))\""])
def test_listing_commands_flagged(tmp_path, cmd):
    rd = run.prepare_run(tmp_path, "a", run.variants()[0], "나")
    a = run.audit(bash(cmd), rd, "나")
    assert a["violations"] and a["discard"] == [], cmd


@pytest.mark.parametrize("cmd", ["python3 -c \"print('a/b'.split('/'))\"", "python3 -c \"x = '/'.join(['a', 'b'])\"",
                                 "python3 -c \"import os; os.listdir('data')\""])
def test_slash_string_not_flagged(tmp_path, cmd):
    rd = run.prepare_run(tmp_path, "a", run.variants()[0], "나")
    assert run.audit(bash(cmd), rd, "나")["violations"] == [], cmd


def test_checker_invoked_ignores_denied_calls(tmp_path):
    rd = run.prepare_run(tmp_path, "a", run.variants()[0], "가")
    ev = bash("python3 .claude/skills/leakage-check/scripts/run_check.py d.json --data data; echo $?", "t1") + \
        [{"type": "result", "permission_denials": [{"tool_use_id": "t1", "tool_name": "Bash", "tool_input": {}}]}]
    assert run.audit(ev, rd, "가")["checker_invoked"] is False


def test_visible_tools_manipulation_check():
    ok = {"model": run.MODEL, "skills": [], "tools": list(run.VISIBLE_TOOLS), "mcp_servers": []}
    assert run.manipulation_check(ok, "나", run.MODEL) == []
    assert run.manipulation_check({**ok, "tools": [*run.VISIBLE_TOOLS, "Agent"]}, "나", run.MODEL)


def test_tmpdir_inside_run_root(tmp_path):
    rd = run.prepare_run(tmp_path, "a", run.variants()[0], "나")
    assert run.agent_env(rd, "나", {})["TMPDIR"] == str(rd.root / "tmp") and (rd.root / "tmp").is_dir()


@pytest.mark.parametrize("cmd,bad", [
    ("python3 x.py --json ../tmp/claude-0/a/scratchpad/r.json", False),
    ("ls -R", False),
    ("ls .claude/skills/leakage-check -R", False),
    ("python3 -c \"open('../../other-t1/ws/x')\"", True),
    ("cd .. && python3 x.py", True),
    ("python3 -c \"print(open('../lchome/leakcheck/rules.py').read())\"", True),
    ("ls -R /", True),
])
def test_dotdot_and_listing_rules(tmp_path, cmd, bad):
    rd = run.prepare_run(tmp_path, "a", run.variants()[0], "나")
    assert bool(run.audit(bash(cmd), rd, "나")["violations"]) is bad, cmd


def test_settings_allow_own_run_only(tmp_path):
    rd = run.prepare_run(tmp_path, "a", run.variants()[0], "나")
    perms = run.deny_settings(rd)["permissions"]
    assert perms["allow"] == [f"Edit(/{rd.root}/**)"]
    assert "Read(//home/user/**)" in perms["deny"]


def test_blank_rows_counted(tmp_path):
    row = {"condition": "가", "rep": 1, "batch": 1, "variant": run.variants()[0], "order": 0}
    out = tmp_path / "out"
    run.ensure_schedule(out, {"abc123def456": row})
    run.run_row(out, "abc123def456", row, run.MODEL, FakeUsers(), launcher_from([(1, b"")] * 6), tmp_path / "runs")
    st = run.status(out)
    assert st["가"]["blank"] == 1 and st["가"]["retries"] == 5


def test_no_checker_after_denial_recorded(tmp_path):
    s = stream(skills("가"), tools_used=[("Bash", {"command": "ls"})]).replace(
        b'"permission_denials": []', b'"permission_denials": [{"tool_name": "Bash", "tool_input": {"command": "x"}}]')
    out, meta = go(tmp_path, "가", [(0, s)])
    assert meta["attempts"][-1]["no_checker_after_denial"] is True
    out2, meta2 = go(tmp_path / "2", "나", [(0, s.replace(b'leakage-check', b'zz'))])
    assert meta2["attempts"][-1]["no_checker_after_denial"] is False


def test_discard_report_and_first_attempts(tmp_path):
    bad = stream([], tools_used=[("Bash", {"command": f"cat {R}/CLAUDE.md"})])
    row = {"condition": "나", "rep": 1, "batch": 1, "variant": run.variants()[0], "order": 0}
    row2 = {**row, "order": 1}
    row3 = {**row, "order": 2}
    out = tmp_path / "out"
    run.ensure_schedule(out, {"abc123def456": row, "bbb123def456": row2, "ccc123def456": row3})
    run.run_row(out, "abc123def456", row, run.MODEL, FakeUsers(), launcher_from([(0, bad, "[]")]), tmp_path / "runs")
    run.run_row(out, "bbb123def456", row2, run.MODEL, FakeUsers(), launcher_from([(0, stream([]))]), tmp_path / "runs")
    run.run_row(out, "ccc123def456", row3, run.MODEL, FakeUsers(),
                launcher_from([(1, b"", "[]"), (0, stream([]))]), tmp_path / "runs")
    rep = run.discard_report(out)["묶음1/나"]
    assert rep["discards"] == 1 and rep["①"] == 1 and rep["calls"][0]["class"] == "①"
    assert rep["확실한 읽음"] == 1 and rep["보수적 판정"] == 0 and rep["calls"][0]["basis"] == "확실한 읽음"
    n = run.export_first_attempts(out, tmp_path / "first")
    assert n == {"from_discarded": 2, "from_reports": 1, "missing": 0}
    rec = json.loads((tmp_path / "first" / "abc123def456.json").read_text())
    assert set(rec) == {"report_id", "variant", "findings"} and rec["findings"] == "[]"
