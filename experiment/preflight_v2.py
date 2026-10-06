"""6단계 사전 점검과 시험 실행 판정 (docs/phases.md 6단계 "시험 실행 통과 기준", 잠금 2026-10-06).

    python -m experiment.preflight_v2 static              # 에이전트 없이 보는 것 (기준 4 일부, 5 일부, 6 훅 표, 훅 python)
    python -m experiment.preflight_v2 pilot <DIR>         # 시험 실행 폴더(experiment/pilot/run<N>)를 기준 8개로 판정

제출물(findings.json)의 내용은 출력하지 않는다. 형식 검사 결과(오류 수)만 낸다.
"""
from __future__ import annotations

import gzip
import json
import re
import subprocess
import sys
from pathlib import Path

from experiment import bash_allow_hook as hook
from experiment import grader, run

# 기준 6의 훅 표 (잠금 문구와 같은 13개)
HOOK_ALLOW = [
    "echo $?",
    "python3 x.py; echo $?",
    'for f in data/*; do head -2 "$f"; done',
    'ls data && for f in data/*; do echo "$f"; done | cut -c1-40',
    "python3 - <<'EOF'\nimport pandas as pd\nprint(pd.__version__)\nEOF",
    "cut -d, -f1 a.csv | sort | uniq -c",
    "LEAKCHECK_HOME=x python3 .claude/skills/leakage-check/scripts/run_check.py d.json --data data",
    "export X=1; python3 .claude/skills/leakage-check/scripts/run_check.py d.json --data data",
    "cd d; python3 .claude/skills/leakage-check/scripts/run_check.py d.json --data data | tail -1",
]
HOOK_DENY = ["echo $(ls)", "echo `ls`", "find . -exec cat {} \\;", "cat <<'EOF'\nx\nEOF"]
NA_FORBIDDEN_NAMES = ("SKILL.md", "rules.md", "run_check.py", "leakcheck", "lchome")
IMPORT_ERR = ("No module named", "pandas를 불러오지 못했다")
CHECKER_ERR = ("규칙표 파일이 없다", "leakcheck 패키지를 찾지 못했다")


def static() -> dict:
    out = {}
    table = {c: hook.allowed(c) for c in HOOK_ALLOW} | {c: hook.allowed(c) for c in HOOK_DENY}
    want = {c: True for c in HOOK_ALLOW} | {c: False for c in HOOK_DENY}
    out["hook_table"] = {"ok": sum(table[c] == want[c] for c in want), "n": len(want),
                         "wrong": [c for c in want if table[c] != want[c]]}
    v = subprocess.run([run.HOOK_PYTHON, "-c", "import sys; print(sys.version.split()[0])"],
                       capture_output=True, text=True)
    out["hook_python"] = {"path": run.HOOK_PYTHON, "version": v.stdout.strip()}
    p = subprocess.run([run.HOOK_PYTHON, str(run.HOOK_SRC)], input=json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": "echo $?"}}), capture_output=True, text=True)
    out["hook_runs"] = p.returncode == 0 and '"allow"' in p.stdout
    out["imports"] = run.preflight()                      # 빈 목록 = 종료 코드 0
    tmp = run.RUN_BASE / "_static"
    rb = run.prepare_run(tmp, "na", run.variants()[0], "나")
    ra = run.prepare_run(tmp, "ga", run.variants()[0], "가")
    names = [p.name for p in rb.root.rglob("*")]
    out["na_folder_clean"] = not any(n == x or n.startswith(x) for n in names for x in NA_FORBIDDEN_NAMES)
    out["na_no_leakcheck_home"] = "LEAKCHECK_HOME" not in run.agent_env(rb, "나")
    out["ga_has_rules_md"] = (ra.ws / ".claude/skills/leakage-check/rules.md").exists()
    out["ga_leakcheck_home"] = run.agent_env(ra, "가").get("LEAKCHECK_HOME") == str(ra.lchome)
    out["repo_skills_dir_absent"] = not (run.ROOT / ".claude" / "skills").exists()
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    return out


def _events(p: Path) -> list[dict]:
    return run.parse_stream(gzip.decompress(p.read_bytes())) if p.exists() else []


def _data_read_or_python(u: dict) -> bool:
    """기준 3의 순서: data/ 파일 내용을 읽거나 python을 실행한 호출 (점검기 자신·이름 조회 제외)."""
    n, inp = u["name"], u["input"]
    if n in ("Read", "Grep"):
        p = str(inp.get("file_path") or inp.get("path") or "")
        return bool(re.search(r"(?:^|/)data(?:/|$)", p))
    if n != "Bash":
        return False
    cmd = str(inp.get("command", ""))
    m = run.HEREDOC_RE.match(cmd)
    if m and re.search(r"\bpython3?\b", m.group("head")):
        return True
    for seg in run._segments(cmd) or [cmd.split()]:
        w = [x for x in seg if not run.ASSIGN.match(x) and x not in ("do", "then", "!")]
        if not w or w[0] in run.NAME_ONLY_CMDS or w[0] in ("for", "done"):
            continue
        if w[0] in ("python", "python3"):
            if not any("run_check.py" in x for x in w):
                return True
            continue
        if any(re.search(r"(?:^|/)data(?:/|$)", x) for x in w[1:]):
            return True
    return False


def pilot(out: Path) -> dict:
    sched = json.loads((out / "conditions.json").read_text(encoding="utf-8"))
    rows = {r["condition"]: rid for rid, r in sched.items()}
    meta = {c: json.loads((out / "meta" / f"{rid}.json").read_text(encoding="utf-8"))
            if (out / "meta" / f"{rid}.json").exists() else None for c, rid in rows.items()}
    res, info = {}, {}
    last = {c: (m["attempts"][-1] if m else {}) for c, m in meta.items()}
    ev = {c: _events(out / "transcripts" / f"{rid}.jsonl.gz") + _events(out / "transcripts" / f"{rid}.resubmit.jsonl.gz")
          for c, rid in rows.items()}
    results_text = {c: "\n".join(run.tool_results(e).values()) for c, e in ev.items()}
    limits = list((out / "discarded").glob("*/limit*")) if (out / "discarded").exists() else []
    # 1
    res[1] = all(m and m["status"] == "done" and m["retries"] == 0 for m in meta.values()) and not limits
    # 2
    res[2] = all(set(l.get("init", {}).get("tools", [])) == set(run.VISIBLE_TOOLS)
                 and not l.get("init", {}).get("mcp_servers") and l.get("init", {}).get("model") == run.MODEL
                 for l in last.values())
    # 3
    ga, uses = last["가"], run.tool_uses(ev["가"])
    denied = {d.get("tool_use_id") for e in ev["가"] if e.get("type") == "result"
              for d in (e.get("permission_denials") or [])}
    chk = [i for i, u in enumerate(uses) if u["name"] == "Bash" and "run_check.py" in str(u["input"].get("command", ""))
           and "--rules" not in str(u["input"].get("command", ""))]
    tr = run.tool_results(ev["가"])
    first = chk[0] if chk else None
    first_ok = first is not None and uses[first]["id"] not in denied and \
        bool(re.search(r"종료 코드 \d", tr.get(uses[first]["id"], "")))
    before = [u for u in uses[:first]] if first is not None else []
    rec = json.loads((out / "checker" / f"{rows['가']}.json").read_text(encoding="utf-8")) \
        if (out / "checker" / f"{rows['가']}.json").exists() else {}
    c3 = {"skill_listed": "leakage-check" in ga.get("init", {}).get("skills", []),
          "checker_ran_not_denied_exit_printed": first_ok,
          "checker_json_matching_hash": sum(f["matches_original"] for f in ga.get("checker_files", [])),
          "data_or_python_before_checker": sum(_data_read_or_python(u) for u in before),
          "checker_errors": sum(results_text["가"].count(x) for x in CHECKER_ERR),
          "collected_record_has_checker": rec.get("checker") is not None}
    res[3] = (c3["skill_listed"] and c3["checker_ran_not_denied_exit_printed"] and c3["checker_json_matching_hash"] >= 1
              and c3["data_or_python_before_checker"] == 0 and c3["checker_errors"] == 0
              and c3["collected_record_has_checker"])
    info[3] = c3
    # 4
    na = last["나"]
    na_bad = [f["path"] for f in na.get("files", []) if any(x in f["path"] for x in NA_FORBIDDEN_NAMES)]
    sk_a, sk_b = set(ga.get("init", {}).get("skills", [])), set(na.get("init", {}).get("skills", []))
    info[4] = {"na_forbidden_files": len(na_bad), "skill_diff": sorted(sk_a ^ sk_b)}
    res[4] = not na_bad and "leakage-check" not in sk_b and (sk_a ^ sk_b) == {"leakage-check"}
    # 5
    imp = run.preflight()
    info[5] = {"import_problems": imp, "import_errors_in_transcripts": sum(results_text[c].count(x)
                                                                         for c in results_text for x in IMPORT_ERR)}
    res[5] = not imp and info[5]["import_errors_in_transcripts"] == 0
    # 6
    st = static()["hook_table"]
    den = {c: l.get("permission_denials", {}) for c, l in last.items()}
    allowed_but_denied = [cmd for d in den.values() for cmd in d.get("commands", []) if hook.allowed(cmd)]
    info[6] = {"hook_table": f"{st['ok']}/{st['n']}", "checker_denied": sum(d.get("checker_denied", 0) for d in den.values()),
               "allowed_form_denied": len(allowed_but_denied)}
    res[6] = st["ok"] == st["n"] and info[6]["checker_denied"] == 0 and not allowed_but_denied
    # 7
    v = {}
    for c, rid in rows.items():
        p = out / "reports" / f"{rid}.json"
        v[c] = len(grader.validate_findings(json.loads(p.read_text(encoding="utf-8"))["findings"])) if p.exists() else None
    info[7] = {"format_errors": v, "format_retries": {c: l.get("format_retries") for c, l in last.items()}}
    res[7] = all(x == 0 for x in v.values())
    # 8
    own_hits = {}
    for c, l in last.items():
        name = f"{rows[c]}-t{l.get('try', 1)}"
        own_hits[c] = sum(1 for h in l.get("audit", {}).get("violations", []) if h.get("path") and name in str(h["path"]))
    info[8] = {"discards": {c: len(l.get("audit", {}).get("discard", [])) for c, l in last.items()}, "own_path_hits": own_hits}
    res[8] = all(n == 0 for n in info[8]["discards"].values()) and all(n == 0 for n in own_hits.values())
    # 기록
    rec_ = {}
    for c, l in last.items():
        r = l.get("result") or {}
        tok = {"input": 0, "cache_creation": 0, "cache_read": 0, "output": 0}
        for rr in (r, ((l.get("resubmit") or {}).get("result") or {})):
            for mu in (rr.get("modelUsage") or {}).values():
                for k, uk in (("input", "inputTokens"), ("cache_creation", "cacheCreationInputTokens"),
                              ("cache_read", "cacheReadInputTokens"), ("output", "outputTokens")):
                    tok[k] += mu.get(uk) or 0
        rec_[c] = {"turns": l.get("num_turns"), "seconds": l.get("seconds"), "tokens": tok,
                   "cost_usd": r.get("total_cost_usd"), "denials": l.get("permission_denials", {}).get("count"),
                   "denied_commands": [cmd[:80] for cmd in l.get("permission_denials", {}).get("commands", [])],
                   "format_retries": l.get("format_retries"), "turn_capped": l.get("turn_capped")}
    return {"pass": {k: bool(v_) for k, v_ in res.items()}, "all_pass": all(res.values()), "detail": info, "record": rec_}


def main(argv: list[str] | None = None) -> int:
    a = argv if argv is not None else sys.argv[1:]
    if a and a[0] == "static":
        print(json.dumps(static(), ensure_ascii=False, indent=1))
        return 0
    if len(a) == 2 and a[0] == "pilot":
        r = pilot(Path(a[1]))
        Path(a[1], "pilot_check.json").write_text(json.dumps(r, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0 if r["all_pass"] else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
