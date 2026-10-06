"""4단계 4a 깨끗한 설계서 검수 실행기 (실험 실행이 아니다).

깨끗한 설계서(designs/clean_v2/) 하나와 본 데이터만 든 격리 폴더에서 새 에이전트에게 "진행 전에 설계에 문제가
있으면 보고하라"로 검토시킨다. 격리는 6단계 실행기(experiment/run.py)의 장치를 고치지 않고 그대로 쓴다
(2b 예비 검수 tools/prereview.py와 같은 방식): 저장소 밖 실행 폴더, 따로 정한 HOME·설정 폴더(스킬 없음),
금지 경로 읽기 차단, 허용 도구, 실행 기록의 금지 경로 검사.

회차 (2026-10-05 사용자 결정)
- r1: 스킬 없음, 데이터 설명서 있음, 8개 × 1회
- r2: 스킬 없음, 데이터 설명서 없음, 8개 × 1회 (고친 뒤)
- r3: 스킬 있음(동결된 skill_src), 데이터 설명서 없음, aki_b·aki_c·readmit_b·readmit_c × 1회.
  격리는 3b 스킬 검수(tools/skill_review.py)와 같다: (가) 조건 폴더(.claude/skills/leakage-check, LEAKCHECK_HOME 사본).
- r4: 3회차 뒤 확인 실행 (스킬 없음, 설명서 없음, 고친 설계서만).
- r5: 4b 봉인 확인 뒤 확인 실행 (스킬 없음, 설명서 없음, 바뀐 설계서 중 2개, 2026-10-06 사용자 결정).
- r6: r5와 같은 조건, 평가 하위 집단 수정 뒤 r5에서 쓰지 않은 바뀐 설계서 1개 (2026-10-06 사용자 결정).
r3부터는 사용량을 줄이려고 보고서 본문을 쓰지 않고 findings.json만 내게 한다 (2026-10-06 사용자 결정).

지시문: 3b 스킬 검수 지시문(findings.json 초안 형식 포함)에서 스킬과 무관한 부분을 그대로 쓰고, 2b 예비 검수의
제약(학습·성능 계산 금지, 파일 수정 금지, 한국어)과 스크립트 안내(2b 2회차, 사용자 결정 2026-10-04)를 더했다.
5단계에서 확정할 실험 지시문이 아니다.

결과: docs/clean_review_v2/<run>.md (마지막 메시지), <run>.findings.json (제출 파일), <run>.meta.json.
실행 기록 전문은 저장소 밖(--transcripts)에만 둔다.

실행: python -m tools.clean_review --round r1 --transcripts <저장소 밖 폴더> [--only 이름 ...]
"""
from __future__ import annotations

import argparse
import gzip
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from experiment import run as R
from tools import skill_review as SR
from tools.prereview import dictionary_copy

ROOT = Path(__file__).resolve().parent.parent
CLEAN = ROOT / "designs" / "clean_v2"
DATA = ROOT / "data" / "synth"
OUT = ROOT / "docs" / "clean_review_v2"
BASE = Path("/srv/leakcleanreview")
R3_NAMES = ["aki_b", "aki_c", "readmit_b", "readmit_c"]     # 3회차 설계서 (2026-10-06 사용자 결정)
NAMES = ["aki_a", "aki_b", "aki_c", "aki_d", "readmit_a", "readmit_b", "readmit_c", "readmit_d"]
ROUNDS = {"r1": {"dict": True, "skill": False, "short": False}, "r2": {"dict": False, "skill": False, "short": False},
          "r3": {"dict": False, "skill": True, "short": True}, "r4": {"dict": False, "skill": False, "short": True},
          "r5": {"dict": False, "skill": False, "short": True},
          "r6": {"dict": False, "skill": False, "short": True}}

PROMPT = """이 작업 폴더에 예측 모델 설계서 `design.json`과 합성 EHR 데이터 폴더 `data`가 있다. 데이터의 환자는 모두 가상이다.{extra}

이 설계로 모델링을 준비하라. 진행 전에 설계에 문제가 있으면 보고하라.

- 모델을 학습하거나 성능을 계산하지 않는다.
- 설계서와 데이터 파일은 고치지 않는다.
- 보고서는 한국어로 쓴다.
- 데이터 확인에는 Write로 스크립트 파일을 만든 뒤 python으로 실행하라.

보고한 문제는 작업 폴더의 findings.json 파일에도 저장하라.
형식은 [{{"target": 설계서의 항목, "kind": "문제" 또는 "가정" 또는 "점검 불가", "problem": 설명}}] 이다.{short}"""
SHORT_LINE = ("\n보고서 본문은 따로 쓰지 않는다. 보고할 내용은 모두 findings.json에 넣고, 마지막 메시지는 "
              "findings.json을 저장했다는 한 줄로 끝낸다.")
DICT_LINE = "\n데이터 설명서는 `data_dictionary.md`이다."


def prepare(run: str, design: Path, with_dict: bool, skill: bool = False) -> R.RunDir:
    root = BASE / run
    if root.exists():
        shutil.rmtree(root)
    ws, home, cfg = root / "ws", root / "home", root / "cfg"
    for d in (ws, home, cfg, ws / "data", root / "tmp"):
        d.mkdir(parents=True)
    rd = R.RunDir(root, ws, home, cfg, None)
    shutil.copy2(design, ws / "design.json")
    for p in sorted(DATA.iterdir()):
        if p.is_file():
            shutil.copy2(p, ws / "data" / p.name)
    if with_dict:
        (ws / "data_dictionary.md").write_text(dictionary_copy(), encoding="utf-8")
    for p in sorted(x for x in ws.rglob("*") if x.is_file()):
        p.chmod(0o444)
        rd.inputs[str(p.relative_to(ws))] = R.sha256(p)
    if skill:                                   # 3b 스킬 검수와 같은 (가) 조건 준비
        shutil.copytree(SR.SKILL, ws / ".claude" / "skills" / "leakage-check",
                        ignore=shutil.ignore_patterns("__pycache__"))
        rd.lchome = root / "lchome"
        for rel in SR.LCHOME_FILES:
            dst = rd.lchome / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, dst)
        rd.lchome_files = sorted(str(p.relative_to(rd.lchome)) for p in rd.lchome.rglob("*") if p.is_file())
    return rd


def run_one(rnd: str, name: str, transcripts: Path, model: str = R.MODEL) -> dict:
    run = f"{name}_{rnd}"
    with_dict, skill = ROUNDS[rnd]["dict"], ROUNDS[rnd]["skill"]
    cond = "가" if skill else "나"
    design = CLEAN / f"{name}.json"
    rd = prepare(run, design, with_dict, skill)
    text = PROMPT.format(extra=DICT_LINE if with_dict else "", short=SHORT_LINE if ROUNDS[rnd]["short"] else "")
    users = R.default_users()
    users.create(run, rd)
    try:
        shutil.copy2(R.HOOK_SRC, rd.root / "bash_allow_hook.py")
        settings = rd.root / "settings.json"
        settings.write_text(json.dumps(R.deny_settings(rd)), encoding="utf-8")
        argv = users.wrap(run, R.agent_argv(text, model, settings), R.agent_env(rd, cond))
        code, out, err, secs = R.launch(argv, rd.ws, R.TIMEOUT_S)
    finally:
        users.remove(run, rd)
    events = R.parse_stream(out)
    init, res = R.init_info(events), R.result_info(events)
    aud = R.audit(events, rd, cond)
    aud["violations"] += R.audit_scripts(rd, cond)
    tools: dict[str, int] = {}
    for e in events:
        msg = e.get("message")
        for c in (msg.get("content") if isinstance(msg, dict) else None) or []:
            if isinstance(c, dict) and c.get("type") == "tool_use":
                tools[c["name"]] = tools.get(c["name"], 0) + 1
    OUT.mkdir(parents=True, exist_ok=True)
    review = None
    if skill:                                   # 3b와 같은 확인 항목: 점검기 첫 실행 순서, 점검기 결과 옮김
        review = SR.review_checks(events, init, res.get("result") or "", rd)
        orig = rd.inputs.get("design.json")
        cj = None
        for cp in sorted(rd.ws.glob("checker*.json"), key=lambda p: (len(p.stem), p.stem)):
            c = json.loads(cp.read_text(encoding="utf-8"))
            if cj is None and (c.get("checked") or {}).get("design_sha256") == orig:
                cj = c
                shutil.copy2(cp, OUT / f"{run}.checker.json")
        review["findings_json"] = SR.findings_checks(rd.ws, cj)
        review.pop("bash_commands", None)
    usage = res.get("usage") or {}
    tokens = {k: usage.get(k) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                                        "cache_read_input_tokens")}
    fj = rd.ws / "findings.json"
    findings_ok = False
    if fj.exists():
        try:
            data = json.loads(fj.read_text(encoding="utf-8"))
            findings_ok = isinstance(data, list)
            (OUT / f"{run}.findings.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                                                      encoding="utf-8")
        except (json.JSONDecodeError, UnicodeDecodeError):
            shutil.copy2(fj, OUT / f"{run}.findings.raw.txt")
    meta = {"run": run, "design": design.name, "design_sha256": R.sha256(design), "dictionary": with_dict,
            "skill": skill, "prompt": text, "tokens": tokens, "review": review, "exit_code": code,
            "seconds": round(secs, 1), "init": init,
            "result": {k: v for k, v in res.items() if k != "result"}, "tool_uses": tools, "audit": aud,
            "inputs_changed": R.inputs_changed(rd), "manipulation": R.manipulation_check(init, cond, model),
            "permission_denials": R.denials(res), "findings_json": {"exists": fj.exists(), "list": findings_ok},
            "stderr_tail": err.decode("utf-8", "replace")[-1500:]}
    transcripts.mkdir(parents=True, exist_ok=True)
    with gzip.open(transcripts / f"{run}.jsonl.gz", "wb") as fh:
        fh.write(out)
    (OUT / f"{run}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / f"{run}.md").write_text(f"# 깨끗한 설계서 검수 {run}\n\n설계서 `{design.name}`, 스킬 "
                                   f"{'있음' if skill else '없음'}, 데이터 설명서 {'있음' if with_dict else '없음'}. 에이전트의 마지막 메시지 원문.\n\n---\n\n"
                                   + (res.get("result") or "(결과 없음)") + "\n", encoding="utf-8")
    shutil.rmtree(rd.root, ignore_errors=True)
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="4a 깨끗한 설계서 검수")
    ap.add_argument("--round", choices=sorted(ROUNDS), required=True)
    ap.add_argument("--only", choices=NAMES, nargs="*")
    ap.add_argument("--transcripts", type=Path, required=True, help="실행 기록 전문을 둘 저장소 밖 폴더")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args(argv)
    if ROOT in args.transcripts.resolve().parents:
        ap.error("--transcripts는 저장소 밖이어야 한다")
    R.SHARED.mkdir(parents=True, exist_ok=True)
    R.SHARED.chmod(0o755)
    shutil.copy2(R.CA_SRC, R.SHARED / "ca-bundle.crt")
    (R.SHARED / "ca-bundle.crt").chmod(0o644)
    BASE.mkdir(parents=True, exist_ok=True)
    names = args.only or (R3_NAMES if args.round == "r3" else NAMES)
    with ThreadPoolExecutor(args.workers) as ex:
        metas = list(ex.map(lambda n: run_one(args.round, n, args.transcripts), names))
    for m in metas:
        print(m["run"], "exit", m["exit_code"], f"{m['seconds']}s", "위반", len(m["audit"]["violations"]),
              "거부", (m["permission_denials"] or {}).get("count"), "조작확인", m["manipulation"] or "ok",
              "입력변경", m["inputs_changed"] or "없음", "findings", m["findings_json"],
              "점검기 첫 순서", (m["review"] or {}).get("checker_first_tool_index"), "토큰", m["tokens"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
