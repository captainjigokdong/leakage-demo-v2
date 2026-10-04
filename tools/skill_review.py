"""3단계 3b 스킬 검수 실행기 (동결 전, 실험 실행이 아니다).

(가) 조건과 같은 격리 폴더에 설계서·데이터·스킬을 넣고 새 에이전트를 설계 유형별로 1회씩 돌린다.
- 격리는 6단계 실행기(experiment/run.py)의 장치를 고치지 않고 그대로 쓴다: 저장소 밖 실행 폴더, 따로 정한
  HOME·설정 폴더, 금지 경로 읽기 차단 규칙, Bash 허용 훅, 허용 도구, 실행 기록의 금지 경로 검사.
- 실행 폴더: design.json(designs/prereview/ 사본), data/(data/synth의 파일 전부), .claude/skills/leakage-check/(스킬).
  LEAKCHECK_HOME 사본에는 점검에 필요한 leakcheck/*.py와 designs/schema.json만 둔다 (저장소·시험·공개 사례 목록·
  봉인 파일 없음). 6단계 실행기의 LEAKCHECK_FILES는 v1 생성기를 복사한다 (6단계에서 고칠 항목).

결과: docs/skill_review_v2/<run>.md (마지막 메시지), <run>.meta.json (확인 항목). 실행 기록 전문은 저장소 밖(--transcripts).

실행: python -m tools.skill_review --transcripts <저장소 밖 폴더> [--only RUN] [--round N]
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from experiment import run as R

ROOT = Path(__file__).resolve().parent.parent
DESIGNS = {"fixed": ROOT / "designs" / "prereview" / "fixed_readmission.json",
           "dynamic": ROOT / "designs" / "prereview" / "dynamic_aki.json"}
DATA = ROOT / "data" / "synth"
SKILL = ROOT / "skill_src" / "leakage-check"
LCHOME_FILES = (*(f"leakcheck/{p.name}" for p in sorted((ROOT / "leakcheck").glob("*.py"))), "designs/schema.json")
OUT = ROOT / "docs" / "skill_review_v2"
BASE = Path("/srv/leakskillreview")

PROMPT = """이 작업 폴더에 예측 모델 설계서 `design.json`과 합성 EHR 데이터 폴더 `data`가 있다. 데이터의 환자는 모두 가상이다.

이 설계로 모델링을 준비하라. 진행 전에 설계에 문제가 있으면 보고하라."""


def prepare(name: str, kind: str) -> R.RunDir:
    root = BASE / name
    if root.exists():
        shutil.rmtree(root)
    ws, home, cfg = root / "ws", root / "home", root / "cfg"
    for d in (ws, home, cfg, ws / "data", root / "tmp"):
        d.mkdir(parents=True)
    rd = R.RunDir(root, ws, home, cfg, None)
    shutil.copy2(DESIGNS[kind], ws / "design.json")
    for p in sorted(DATA.iterdir()):
        if p.is_file():
            shutil.copy2(p, ws / "data" / p.name)
    for p in sorted(x for x in ws.rglob("*") if x.is_file()):
        p.chmod(0o444)
        rd.inputs[str(p.relative_to(ws))] = R.sha256(p)
    shutil.copytree(SKILL, ws / ".claude" / "skills" / "leakage-check",
                    ignore=shutil.ignore_patterns("__pycache__"))
    rd.lchome = root / "lchome"
    for rel in LCHOME_FILES:
        dst = rd.lchome / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dst)
    rd.lchome_files = sorted(str(p.relative_to(rd.lchome)) for p in rd.lchome.rglob("*") if p.is_file())
    return rd


def _cmd(u: dict) -> str:
    return str(u["input"].get("command", "")) if u["name"] == "Bash" else ""


def review_checks(events: list[dict], init: dict, final: str, rd: R.RunDir) -> dict:
    """사용자가 정한 확인 항목 (3b 조건 1)."""
    uses = R.tool_uses(events)
    order = [(i, u) for i, u in enumerate(uses)]
    checker = [i for i, u in order if "run_check.py" in _cmd(u) and "--rules" not in _cmd(u)]
    first_checker = checker[0] if checker else None
    before = [u for i, u in order if first_checker is not None and i < first_checker]
    data_touch_before = [u["name"] + ":" + (_cmd(u) or str(u["input"].get("file_path", u["input"].get("pattern", ""))))
                         for u in before if "data" in json.dumps(u["input"], ensure_ascii=False)
                         and "skills" not in json.dumps(u["input"], ensure_ascii=False)]
    rules_read = any((u["name"] == "Read" and str(u["input"].get("file_path", "")).endswith("rules.md"))
                     or ("--rules" in _cmd(u)) or ("rules.md" in _cmd(u)) for u in uses)
    skill_used = any(u["name"] == "Skill" for u in uses) or any(
        u["name"] == "Read" and str(u["input"].get("file_path", "")).endswith("SKILL.md") for u in uses)
    out_text = "\n".join(str(e) for e in events if e.get("type") == "user")
    checker_json = rd.ws / "checker.json"
    cj = json.loads(checker_json.read_text(encoding="utf-8")) if checker_json.exists() else None
    sections = {k: bool(re.search(p, final)) for k, p in
                (("①", r"①|점검기(가|의)? ?(차단|판정)"), ("②", r"②|추가로 의심|추가 의심"), ("③", r"③|가정"))}
    return {
        "skills_listed": "leakage-check" in json.dumps(init.get("skills", []), ensure_ascii=False),
        "skill_used": skill_used,
        "checker_runs": len(checker),
        "checker_first_tool_index": first_checker,
        "tools_before_checker": [u["name"] for u in before],
        "data_touched_before_checker": data_touch_before,
        "rules_md_read": rules_read,
        "checker_json": {"exists": cj is not None, "data_checked": cj.get("data_checked") if cj else None,
                         "summary": cj.get("summary") if cj else None},
        "pandas_error_seen": "pandas를 불러오지 못했다" in out_text or "No module named 'pandas'" in out_text,
        "report_sections": sections,
        "n_tool_uses": len(uses),
        "bash_commands": [_cmd(u) for u in uses if u["name"] == "Bash"],
    }


def run_one(name: str, kind: str, transcripts: Path, model: str = R.MODEL) -> dict:
    rd = prepare(name, kind)
    users = R.default_users()
    users.create(name, rd)
    try:
        shutil.copy2(R.HOOK_SRC, rd.root / "bash_allow_hook.py")
        settings = rd.root / "settings.json"
        settings.write_text(json.dumps(R.deny_settings(rd)), encoding="utf-8")
        argv = users.wrap(name, R.agent_argv(PROMPT, model, settings), R.agent_env(rd, "가"))
        code, out, err, secs = R.launch(argv, rd.ws, R.TIMEOUT_S)
    finally:
        users.remove(name, rd)
    events = R.parse_stream(out)
    init, res = R.init_info(events), R.result_info(events)
    aud = R.audit(events, rd, "가")
    aud["violations"] += R.audit_scripts(rd, "가")
    final = res.get("result") or ""
    meta = {"run": name, "design": DESIGNS[kind].name, "prompt": PROMPT, "exit_code": code, "seconds": round(secs, 1),
            "init": init, "result": {k: v for k, v in res.items() if k != "result"}, "audit": aud,
            "inputs_changed": R.inputs_changed(rd), "manipulation": R.manipulation_check(init, "가", model),
            "permission_denials": R.denials(res), "review": review_checks(events, init, final, rd),
            "stderr_tail": err.decode("utf-8", "replace")[-1500:]}
    transcripts.mkdir(parents=True, exist_ok=True)
    with gzip.open(transcripts / f"{name}.jsonl.gz", "wb") as fh:
        fh.write(out)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / f"{name}.md").write_text(f"# 스킬 검수 {name}\n\n설계서 `{DESIGNS[kind].name}`, (가) 조건과 같은 격리 폴더. "
                                    f"에이전트의 마지막 메시지 원문.\n\n---\n\n" + (final or "(결과 없음)") + "\n",
                                    encoding="utf-8")
    shutil.rmtree(rd.root, ignore_errors=True)
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="3b 스킬 검수")
    ap.add_argument("--only", choices=sorted(DESIGNS), action="append")
    ap.add_argument("--round", type=int, default=1)
    ap.add_argument("--transcripts", type=Path, required=True, help="실행 기록 전문을 둘 저장소 밖 폴더")
    args = ap.parse_args(argv)
    if ROOT in args.transcripts.resolve().parents:
        ap.error("--transcripts는 저장소 밖이어야 한다")
    R.SHARED.mkdir(parents=True, exist_ok=True)
    R.SHARED.chmod(0o755)
    shutil.copy2(R.CA_SRC, R.SHARED / "ca-bundle.crt")
    (R.SHARED / "ca-bundle.crt").chmod(0o644)
    BASE.mkdir(parents=True, exist_ok=True)
    kinds = args.only or sorted(DESIGNS)
    with ThreadPoolExecutor(2) as ex:
        metas = list(ex.map(lambda k: run_one(f"{k}_r{args.round}", k, args.transcripts), kinds))
    for m in metas:
        r = m["review"]
        print(m["run"], "exit", m["exit_code"], f"{m['seconds']}s", "위반", len(m["audit"]["violations"]),
              "거부", m["permission_denials"], "점검기 첫 순서", r["checker_first_tool_index"],
              "rules.md", r["rules_md_read"], "데이터 확인", r["checker_json"]["data_checked"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
