"""2단계 2b 예비 검수 실행기.

스킬 없는 새 에이전트에게 설계서 하나와 재생성한 데이터만 든 격리 폴더를 주고 "진행 전에 설계에 문제가 있으면
보고하라"로 한 번씩 검토시킨다. 4단계 정식 검수를 대신하지 않는다.

- 실행 4회 = 설계 유형 2개(designs/prereview/) × 데이터 설명서 없음/있음.
- 격리는 6단계 실행기(experiment/run.py)의 장치를 고치지 않고 그대로 쓴다: 저장소 밖 실행 폴더, 따로 정한 HOME·설정 폴더
  (스킬 없음), 금지 경로 읽기 차단 규칙, 허용 도구, 실행 기록의 금지 경로 검사.
- 실행 폴더에는 design.json, data/(data/synth의 파일 전부), (설명서 있음 조건만) data_dictionary.md만 둔다.
  저장소, 스킬, 점검 코드, 봉인 파일은 넣지 않는다.
- 설명서 사본은 docs/data_dictionary_v2.md에서 저장소 안내(머리말 목록)와 보조 데이터 절을 뺀 것이다.

결과: docs/prereview_v2/<run>.md (에이전트의 마지막 메시지), docs/prereview_v2/<run>.meta.json (도구 사용·검사 결과).
실행 기록 전문은 저장소 밖(--transcripts)에만 둔다.

실행: python -m tools.prereview [--only RUN] [--transcripts DIR]
"""
from __future__ import annotations

import argparse
import gzip
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from experiment import run as R

ROOT = Path(__file__).resolve().parent.parent
DESIGNS = {"fixed": ROOT / "designs" / "prereview" / "fixed_readmission.json",
           "dynamic": ROOT / "designs" / "prereview" / "dynamic_aki.json"}
DATA = ROOT / "data" / "synth"
DICT = ROOT / "docs" / "data_dictionary_v2.md"
OUT = ROOT / "docs" / "prereview_v2"
BASE = Path("/srv/leakprereview")
RUNS = {f"{kind}_{arm}": (kind, arm) for kind in ("fixed", "dynamic") for arm in ("nodict", "dict")}

PROMPT = """이 작업 폴더에 예측 모델 설계서 `design.json`과 합성 EHR 데이터 폴더 `data`가 있다. 데이터의 환자는 모두 가상이다.{extra}

진행 전에 설계에 문제가 있으면 보고하라.

- 모델을 학습하거나 성능을 계산하지 않는다.
- 설계서와 데이터 파일은 고치지 않는다.
- 보고서는 한국어로 쓴다."""
DICT_LINE = "\n데이터 설명서는 `data_dictionary.md`이다."


def dictionary_copy() -> str:
    """설명서에서 저장소 안내(머리말 목록)와 보조 데이터 절을 뺀다. 표와 전체 성질은 그대로."""
    text = DICT.read_text(encoding="utf-8")
    title = "# 데이터 설명서"
    body = text[text.index("## 칸 설명"):]
    body = body[:body.index("## 보조 데이터")].rstrip() + "\n"
    return f"{title}\n\n모든 환자·수치는 가상 값이다. 날짜는 2150년대로 옮겨 두었다.\n\n{body}"


def prepare(name: str, kind: str, arm: str) -> R.RunDir:
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
    if arm == "dict":
        (ws / "data_dictionary.md").write_text(dictionary_copy(), encoding="utf-8")
    for p in sorted(x for x in ws.rglob("*") if x.is_file()):
        p.chmod(0o444)
        rd.inputs[str(p.relative_to(ws))] = R.sha256(p)
    return rd


def run_one(name: str, kind: str, arm: str, transcripts: Path, model: str = R.MODEL) -> dict:
    rd = prepare(name, kind, arm)
    text = PROMPT.format(extra=DICT_LINE if arm == "dict" else "")
    users = R.default_users()
    users.create(name, rd)
    try:
        shutil.copy2(R.HOOK_SRC, rd.root / "bash_allow_hook.py")
        settings = rd.root / "settings.json"
        settings.write_text(json.dumps(R.deny_settings(rd)), encoding="utf-8")
        argv = users.wrap(name, R.agent_argv(text, model, settings), R.agent_env(rd, "나"))
        code, out, err, secs = R.launch(argv, rd.ws, R.TIMEOUT_S)
    finally:
        users.remove(name, rd)
    events = R.parse_stream(out)
    init, res = R.init_info(events), R.result_info(events)
    aud = R.audit(events, rd, "나")
    aud["violations"] += R.audit_scripts(rd, "나")
    meta = {"run": name, "design": DESIGNS[kind].name, "dictionary": arm == "dict", "prompt": text,
            "exit_code": code, "seconds": round(secs, 1), "init": init,
            "result": {k: v for k, v in res.items() if k != "result"}, "audit": aud,
            "inputs_changed": R.inputs_changed(rd), "manipulation": R.manipulation_check(init, "나", model),
            "permission_denials": R.denials(res), "stderr_tail": err.decode("utf-8", "replace")[-1500:]}
    transcripts.mkdir(parents=True, exist_ok=True)
    with gzip.open(transcripts / f"{name}.jsonl.gz", "wb") as fh:
        fh.write(out)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / f"{name}.md").write_text(f"# 예비 검수 {name}\n\n설계서 `{DESIGNS[kind].name}`, 데이터 설명서 "
                                    f"{'있음' if arm == 'dict' else '없음'}. 에이전트의 마지막 메시지 원문.\n\n---\n\n"
                                    + (res.get("result") or "(결과 없음)") + "\n", encoding="utf-8")
    shutil.rmtree(rd.root, ignore_errors=True)
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="2b 예비 검수")
    ap.add_argument("--only", choices=sorted(RUNS), action="append")
    ap.add_argument("--transcripts", type=Path, required=True, help="실행 기록 전문을 둘 저장소 밖 폴더")
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args(argv)
    if ROOT in args.transcripts.resolve().parents:
        ap.error("--transcripts는 저장소 밖이어야 한다")
    R.SHARED.mkdir(parents=True, exist_ok=True)
    R.SHARED.chmod(0o755)
    shutil.copy2(R.CA_SRC, R.SHARED / "ca-bundle.crt")
    (R.SHARED / "ca-bundle.crt").chmod(0o644)
    BASE.mkdir(parents=True, exist_ok=True)
    names = args.only or sorted(RUNS)
    with ThreadPoolExecutor(args.workers) as ex:
        metas = list(ex.map(lambda n: run_one(n, *RUNS[n], args.transcripts), names))
    for m in metas:
        print(m["run"], "exit", m["exit_code"], f"{m['seconds']}s", "위반", len(m["audit"]["violations"]),
              "조작확인", m["manipulation"] or "ok", "입력변경", m["inputs_changed"] or "없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
