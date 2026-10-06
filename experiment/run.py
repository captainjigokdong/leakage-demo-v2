"""6단계 (가)/(나) 실행기 (v2).

변형 × 조건 × 반복마다 저장소 밖에 격리된 실행 폴더를 만들고, 같은 지시문·같은 모델로 에이전트(Claude Code 헤드리스)를 돌린다.
실행 규칙은 docs/phases.md 6단계의 "실행 규칙 (v2, 잠금)"을 따른다.

    python -m experiment.run schedule              # 실행표 만들기 (이미 있으면 같은지 확인)
    python -m experiment.run preflight             # 에이전트 환경의 python 패키지 확인
    python -m experiment.run pilot                 # 시험 실행: 시드로 고른 변형 1개 × 조건 2 → experiment/pilot/run<N>/
    python -m experiment.run main --batches 1      # 본 실행 1회차 60회 → experiment/runs/ (묶음을 꼭 지정한다)
    python -m experiment.run status [--out DIR]    # 진행 상황, 조건별 재실행·폐기·턴 상한·재제출 수

저장 (DIR = experiment/runs 또는 experiment/pilot/run<N>)
- DIR/reports/<id>.json      {"report_id", "variant", "findings": findings.json 내용 문자열 또는 None}  ← 채점 대상. 조건 표시 없음
- DIR/checker/<id>.json      {"report_id", "variant", "exit_code", "checker"}  ← (가)만. 에이전트가 남긴 checker*.json에서 고름
- DIR/checker_files/<id>/    에이전트가 남긴 checker*.json 전부 (원래 설계서가 아닌 것은 기록용)
- DIR/conditions.json        {id: {"condition", "rep", "batch", "variant", "order", "turn_capped", "format_retries"}}
- DIR/meta/<id>.json         실행 기록 요약 (시도별 상태·사유, 시간, 사용량, 스킬 목록, 접근 검사, 작업 폴더 파일 목록)
- DIR/transcripts/<id>.jsonl.gz (+ <id>.resubmit.jsonl.gz)   채택된 시도의 실행 기록 (stream-json)
- DIR/discarded/<id>/try<k>/       채택하지 않은 시도 (기계적 실패, 폐기). limit<시각>/ = 한도로 끊긴 부분 출력
작업 폴더(RUN_BASE/<id>-t<k>/)는 지우지 않고 남긴다 (커밋하지 않음).
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import random
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from experiment import grader, prompt

ROOT = Path(__file__).resolve().parent.parent
VARIANT_DIR = ROOT / "designs" / "variants"
DATA_DIR = ROOT / "data" / "synth"
SKILL_SRC = ROOT / "skill_src" / "leakage-check"
RUNS_OUT = ROOT / "experiment" / "runs"
HOOK_SRC = ROOT / "experiment" / "bash_allow_hook.py"
PILOT_OUT = ROOT / "experiment" / "pilot"

SCHEDULE_SEED = 20261004
PILOT_SEED = 20261005
REPS = 2                   # 반복 = 묶음. 묶음 하나 = 변형 30 × 조건 2 = 60회
CONDITIONS = ("가", "나")
MODEL = "claude-opus-5-5"
TIMEOUT_S = 20 * 60
MAX_RETRIES = 5            # 기계적 실패 시 다시 실행하는 최대 횟수 (시도는 최대 6회). 그래도 실패하면 빈칸
WORKERS = 3
# 턴 상한·형식 재제출은 잠긴 채점기의 값을 그대로 쓴다 (docs/success_criteria_v2.md 3절)
MAX_TURNS = grader.MAX_TURNS
MAX_TURNS_RETRY = grader.MAX_TURNS_RETRY
FORMAT_RETRIES = grader.FORMAT_RETRIES
FINDINGS_FILE = "findings.json"
# 형식 재제출 요청 (두 조건 같음). {errors}에는 grader.validate_findings의 오류 목록만 들어간다
RESUBMIT_TEXT = ("작업 폴더 맨 위의 findings.json이 형식 검사를 통과하지 못했다 (오류: {errors}). "
                 "지적 내용은 바꾸지 말고 파일 형식만 고쳐 같은 위치에 같은 이름(findings.json)으로 다시 저장하라. "
                 "마지막 메시지는 한 줄로 쓴다.")

RUN_BASE = Path("/srv/leakruns")       # 실행 폴더
SHARED = Path("/srv/leakshared")       # 실행 사용자가 읽을 수 있는 공용 파일 (CA 묶음만)
CA_SRC = Path("/root/.ccr/ca-bundle.crt")

# 두 조건에 똑같이 준다. 웹 검색·웹 가져오기는 둘 다 끈다.
DISALLOWED_TOOLS = ("WebSearch", "WebFetch")
# 권한 방식: bypassPermissions는 쓰지 않는다. dontAsk 모드에서 미리 허용한 도구만 쓰고 그 밖의 호출은 거부된다. 두 조건 같음.
READONLY_CMDS = ("cd", "ls", "cat", "head", "tail", "wc", "echo", "sed", "grep", "zcat", "mkdir", "pwd",
                 "cut", "sort", "uniq", "tr")
ALLOWED_TOOLS = ("Read", "Glob", "Grep", "Skill", "Write", "Bash(python:*)", "Bash(python3:*)",
                 *(f"Bash({c}:*)" for c in READONLY_CMDS),
                 "Bash(LEAKCHECK_HOME=*)", "Bash(export:*)")
# 에이전트에게 보이는 도구 (--tools). 두 조건 같음.
VISIBLE_TOOLS = ("Read", "Glob", "Grep", "Skill", "Write", "Bash")
PERMISSION_ARGS: tuple[str, ...] = ("--permission-mode", "dontAsk", "--allowedTools", *ALLOWED_TOOLS)

# (가) LEAKCHECK_HOME 사본: 점검에 필요한 파일만 (3b 검수와 같음). 생성기(synth/), tests/, docs/는 넣지 않는다.
LEAKCHECK_FILES = (
    *(f"leakcheck/{p.name}" for p in sorted((ROOT / "leakcheck").glob("*.py"))),
    "designs/schema.json",
)
LEAKCHECK_EXCLUDED = ("synth", "tests", "docs", "designs/inject.py", "designs/error_catalog_public.csv",
                      "designs/variants", "designs/base", "sealed", "experiment", "CLAUDE.md")

# 실행 사용자 환경: 세션 환경을 그대로 넘기되, 오염을 일으키는 것으로 확인된 변수만 뺀다.
ENV_DROP = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID",
            "CLAUDE_ADDITIONAL_DIRECTORIES", "CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD")
CA_VARS = ("NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "PIP_CERT",
           "AWS_CA_BUNDLE", "NIX_SSL_CERT_FILE", "DENO_CERT", "CLOUDSDK_CORE_CUSTOM_CA_CERTS_FILE", "HEX_CACERTS_PATH")

# 실행 기록에 나타나면 "기록"하는 경로 (실행 폴더 밖 민감 경로)
FORBIDDEN_PREFIXES = (str(ROOT), "/home/user", "/root", "/mnt/user-data", "/tmp/claude-0")
HARDEN_DIRS = (Path("/home/user"), Path("/mnt/user-data"))


# ---------------------------------------------------------------- 실행표

def variants() -> list[str]:
    return sorted(p.name for p in VARIANT_DIR.glob("design_*.json"))


def design_type(v: str) -> str:
    return json.loads((VARIANT_DIR / v).read_text(encoding="utf-8"))["design_type"]


SCHEDULE_KEYS = ("condition", "rep", "batch", "variant", "order")


def build_schedule(vs: list[str], reps: int, seed: int) -> dict[str, dict]:
    """{report_id: {condition, rep, batch, variant, order}}.

    반복 단위 묶음: 묶음 r = 반복 r의 (변형 × 조건) 전부. 묶음 1을 다 돌린 뒤 묶음 2로 간다.
    묶음 안에서는 순서를 섞어 조건·변형이 시간에 몰리지 않게 한다.
    """
    rng = random.Random(seed)
    out, used, order = {}, set(), 0
    for r in range(1, reps + 1):
        rows = [(v, c) for v in vs for c in CONDITIONS]
        rng.shuffle(rows)
        for v, c in rows:
            rid = "%012x" % rng.getrandbits(48)
            while rid in used:
                rid = "%012x" % rng.getrandbits(48)
            used.add(rid)
            out[rid] = {"condition": c, "rep": r, "batch": r, "variant": v, "order": order}
            order += 1
    return out


def pilot_variants(seed: int = PILOT_SEED) -> list[str]:
    """시험 실행 변형 1개 (시드로 추첨, 결함 여부는 모른다). 다시 해도 같은 변형."""
    return [random.Random(seed).choice(variants())]


def _sched_only(s: dict[str, dict]) -> dict[str, dict]:
    return {rid: {k: r[k] for k in SCHEDULE_KEYS if k in r} for rid, r in s.items()}


def ensure_schedule(out: Path, sched: dict[str, dict]) -> dict[str, dict]:
    f = out / "conditions.json"
    if f.exists():
        old = json.loads(f.read_text(encoding="utf-8"))
        if _sched_only(old) != _sched_only(sched):
            raise RuntimeError(f"{f}가 지금 만든 실행표와 다르다. 실행표는 바꾸지 않는다.")
        return old
    out.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(sched, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return sched


_COND_LOCK = threading.Lock()


def record_condition(out: Path, rid: str, **fields) -> None:
    """조건 파일에 행의 실행 결과 칸(turn_capped, format_retries)을 적는다. 일정 칸은 바꾸지 않는다."""
    with _COND_LOCK:
        f = out / "conditions.json"
        c = json.loads(f.read_text(encoding="utf-8"))
        c[rid].update(fields)
        _write_json(f, c)


# ---------------------------------------------------------------- 실행 폴더

def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@dataclass
class RunDir:
    root: Path
    ws: Path
    home: Path
    cfg: Path
    lchome: Path | None
    inputs: dict[str, str] = field(default_factory=dict)     # ws 상대 경로 → sha256
    lchome_files: list[str] = field(default_factory=list)


def prepare_run(base: Path, run_name: str, variant: str, condition: str) -> RunDir:
    root = base / run_name
    if root.exists():
        shutil.rmtree(root)
    ws, home, cfg = root / "ws", root / "home", root / "cfg"
    for d in (ws, home, cfg, ws / "data", root / "tmp"):
        d.mkdir(parents=True)
    rd = RunDir(root, ws, home, cfg, None)
    shutil.copy2(VARIANT_DIR / variant, ws / variant)
    for p in sorted(DATA_DIR.iterdir()):
        if p.is_file():
            shutil.copy2(p, ws / "data" / p.name)
    for name, b in prompt.agent_docs().items():         # 형식 설명·데이터 설명서 사본 (두 조건 같은 이름)
        (ws / name).write_bytes(b)
    for p in sorted(x for x in ws.rglob("*") if x.is_file()):
        p.chmod(0o444)
        rd.inputs[str(p.relative_to(ws))] = sha256(p)
    if condition == "가":
        shutil.copytree(SKILL_SRC, ws / ".claude" / "skills" / "leakage-check",
                        ignore=shutil.ignore_patterns("__pycache__"))
        rd.lchome = root / "lchome"
        for rel in LEAKCHECK_FILES:
            dst = rd.lchome / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, dst)
        rd.lchome_files = sorted(str(p.relative_to(rd.lchome)) for p in rd.lchome.rglob("*") if p.is_file())
    return rd


def inputs_changed(rd: RunDir) -> list[str]:
    return [rel for rel, h in rd.inputs.items() if not (rd.ws / rel).exists() or sha256(rd.ws / rel) != h]


def file_listing(rd: RunDir) -> list[dict]:
    """작업 폴더(ws)와 임시 폴더(tmp)의 파일 목록: 이름·크기·해시만 (내용은 남기지 않는다)."""
    out = []
    for top in (rd.ws, rd.root / "tmp"):
        if not top.exists():
            continue
        for p in sorted(top.rglob("*")):
            if p.is_file() and not p.is_symlink():
                out.append({"path": str(p.relative_to(rd.root)), "size": p.stat().st_size, "sha256": sha256(p)})
    return out


def read_findings(rd: RunDir) -> str | None:
    p = rd.ws / FINDINGS_FILE
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None


# ---------------------------------------------------------------- 에이전트 실행

def agent_env(rd: RunDir, condition: str, base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in (os.environ if base_env is None else base_env).items() if k not in ENV_DROP}
    ca = str(SHARED / "ca-bundle.crt")
    env.update({k: ca for k in CA_VARS if k in env or k in ("NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE")})
    env.update({"PATH": "/opt/node22/bin:/usr/local/bin:/usr/bin:/bin", "HOME": str(rd.home),
                "CLAUDE_CONFIG_DIR": str(rd.cfg), "TMPDIR": str(rd.root / "tmp")})
    env.pop("LEAKCHECK_HOME", None)
    if condition == "가":
        env["LEAKCHECK_HOME"] = str(rd.lchome)
    return env


# 실행 사용자: 이 세션과 같은 root로 실행한다. 격리는 권한 규칙(DENY_PATHS)과 사후 검사(audit)에 의존한다.
RUN_AS = "root"
DENY_PATHS = ("/home/user", "/root", "/mnt/user-data", "/tmp/claude-0")
# 훅을 돌릴 python (컨테이너마다 위치가 다르다: 지금은 /usr/bin/python3)
HOOK_PYTHON = shutil.which("python3", path="/usr/local/bin:/usr/bin:/bin") or sys.executable


def deny_settings(rd: "RunDir | None" = None) -> dict:
    """금지 경로 차단 + (실행 폴더를 주면) 자기 실행 폴더 안에서만 셸 출력 돌리기(> 파일) 허용."""
    rules = [f"{tool}(/{p}/**)" for p in DENY_PATHS for tool in ("Read", "Glob", "Grep")]
    perms = {"deny": rules}
    out = {"permissions": perms}
    if rd is not None:
        perms["allow"] = [f"Edit(/{rd.root}/**)"]
        out["hooks"] = {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": f"{HOOK_PYTHON} {rd.root / 'bash_allow_hook.py'}"}]}]}
    return out


def agent_argv(text: str, model: str, settings: Path | None = None, max_turns: int | None = MAX_TURNS,
               resume: str | None = None) -> list[str]:
    extra = ["--settings", str(settings)] if settings else []
    if resume:
        extra += ["--resume", resume]
    if max_turns:
        extra += ["--max-turns", str(max_turns)]
    return ["claude", "-p", text, "--model", model, "--output-format", "stream-json", "--verbose",
            "--strict-mcp-config", *extra, "--tools", *VISIBLE_TOOLS,
            "--disallowedTools", *DISALLOWED_TOOLS, *PERMISSION_ARGS]


class OsUser:
    """실행마다 새 OS 사용자 (지금은 쓰지 않음: RUN_AS = root)."""

    def create(self, name: str, rd: RunDir) -> None:
        subprocess.run(["useradd", "-M", "-d", str(rd.home), "-s", "/usr/sbin/nologin", name], check=True)
        subprocess.run(["chown", "-R", f"{name}:{name}", str(rd.root)], check=True)
        rd.root.chmod(0o700)

    def wrap(self, name: str, argv: list[str], env: dict[str, str]) -> list[str]:
        return ["setpriv", f"--reuid={name}", f"--regid={name}", "--clear-groups",
                "env", "-i", *(f"{k}={v}" for k, v in env.items()), *argv]

    def remove(self, name: str, rd: RunDir) -> None:
        subprocess.run(["chown", "-R", "root:root", str(rd.root)], check=False)
        subprocess.run(["userdel", name], check=False, capture_output=True)


class RootUser(OsUser):
    """이 세션과 같은 root로 실행한다. 환경 변수는 agent_env가 정한 것만 넘긴다."""

    def create(self, name: str, rd: RunDir) -> None:
        rd.root.chmod(0o700)

    def wrap(self, name: str, argv: list[str], env: dict[str, str]) -> list[str]:
        return ["env", "-i", *(f"{k}={v}" for k, v in env.items()), *argv]

    def remove(self, name: str, rd: RunDir) -> None:
        pass


def default_users() -> OsUser:
    return RootUser() if RUN_AS == "root" else OsUser()


def launch(argv: list[str], cwd: Path, timeout: int) -> tuple[int | None, bytes, bytes, float]:
    """(종료 코드 또는 시간 초과 None, stdout, stderr, 초)."""
    t0 = time.monotonic()
    p = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout)
        return p.returncode, out, err, time.monotonic() - t0
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        out, err = p.communicate()
        return None, out, err, time.monotonic() - t0


# ---------------------------------------------------------------- 실행 기록 분석

PATH_RE = re.compile(r"(?<![\w.~$])(/[A-Za-z0-9_.\-/]+)")
DOTDOT_RE = re.compile(r"""(?:^|[\s'"=(,:/])\.\.(?=/|['"\s),;]|$)""", re.M)
TOP_DIRS = ("/", "/home", "/root", "/mnt", "/srv", "/srv/leakruns", "/tmp", "/tmp/claude-0", "/var", "/etc",
            "/opt", "/usr", "/proc", "/media", "/run")
_TOP = "(?:(?:" + "|".join(re.escape(d.rstrip("/")) for d in TOP_DIRS if d != "/") + ")/?|/)"
LIST_RES = (
    re.compile(r"""\b(?:ls|find|tree|du|locate)\b[^|;&\n]*?\s['"]?""" + _TOP + r"""[*?]*['"]?(?=[\s;|&)]|$)""", re.M),
    re.compile(r"""\b(?:listdir|scandir|walk|glob|iglob)\s*\(\s*r?['"]""" + _TOP + r"""[*?]*['"]"""),
    re.compile(r"""Path\s*\(\s*r?['"]""" + _TOP + r"""['"]\s*\)\s*\.\s*(?:iterdir|rglob|glob)\b"""),
)
HOMEX_RE = re.compile(r"""expanduser\(\s*['"]~\w|['"]~(?:root|user)\b|Path\.home\(\)\.parent""")


def parse_stream(raw: bytes) -> list[dict]:
    ev = []
    for line in raw.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                ev.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return ev


def tool_uses(events: list[dict]) -> list[dict]:
    out = []
    for e in events:
        if e.get("type") != "assistant":
            continue
        for c in (e.get("message") or {}).get("content") or []:
            if isinstance(c, dict) and c.get("type") == "tool_use":
                out.append({"name": c.get("name"), "input": c.get("input") or {}, "id": c.get("id")})
    return out


def tool_results(events: list[dict]) -> dict[str, str]:
    """tool_use_id → 결과 문자열."""
    out = {}
    for e in events:
        if e.get("type") != "user":
            continue
        for c in (e.get("message") or {}).get("content") or []:
            if isinstance(c, dict) and c.get("type") == "tool_result":
                body = c.get("content")
                if isinstance(body, list):
                    body = "\n".join(str(x.get("text", "")) for x in body if isinstance(x, dict))
                out[c.get("tool_use_id")] = str(body or "")
    return out


def _strings(x) -> list[str]:
    if isinstance(x, str):
        return [x]
    if isinstance(x, dict):
        return [s for v in x.values() for s in _strings(v)]
    if isinstance(x, list):
        return [s for v in x for s in _strings(v)]
    return []


def own_tmp(p: str, rd: RunDir) -> bool:
    """/tmp/claude-0/ 아래에서 자기 실행 폴더 이름이 들어간 임시 폴더 (Claude Code의 작업용 임시 폴더)."""
    parts = p.split("/")
    return (p.startswith("/tmp/claude-0/") and len(parts) > 3
            and re.search(r"(?:^|-)" + re.escape(rd.root.name) + r"(?:-|$)", parts[3]) is not None)


def _token_at(text: str, i: int) -> str:
    stop = set(" \t\n'\"()[]{};|&,=<>")
    a = i
    while a > 0 and text[a - 1] not in stop:
        a -= 1
    b = i
    while b < len(text) and text[b] not in stop:
        b += 1
    return text[a:b]


def _dotdot_inside(tok: str, rd: RunDir, condition: str) -> bool:
    q = os.path.normpath(tok if tok.startswith("/") else os.path.join(str(rd.ws), tok))
    own = str(rd.root)
    if not (q == own or q.startswith(own + "/")):
        return False
    return condition == "가" or not (q + "/").startswith(own + "/lchome/")


def scan_text(text: str, rd: RunDir, condition: str) -> list[dict]:
    """명령·스크립트 문자열 하나에서 금지 경로, 상위 폴더 탐색, 최상위 폴더 조회를 찾는다 (기록용)."""
    own = str(rd.root)
    forbidden = [*FORBIDDEN_PREFIXES, str(RUN_BASE)]
    hits = []
    for m in PATH_RE.findall(text):
        p = m.rstrip(".")
        inside = p == own or p.startswith(own + "/") or own_tmp(p, rd)
        if inside and condition != "가" and (p + "/").startswith(own + "/lchome/"):
            hits.append({"path": p, "why": "(나)에서 점검기 사본 경로"})
        elif not inside and any(p == f or p.startswith(f + "/") for f in forbidden):
            hits.append({"path": p, "why": "실행 폴더 밖 금지 경로"})
    for m in DOTDOT_RE.finditer(text):
        tok = _token_at(text, m.end() - 1)
        if not _dotdot_inside(tok, rd, condition) or re.search(r"\bcd\s+['\"]?" + re.escape(tok), text):
            hits.append({"path": tok, "why": "상위 폴더 탐색 (..)"})
    for rx, why in (*((r, "최상위 폴더 조회·순회") for r in LIST_RES),
                    (HOMEX_RE, "다른 사용자 홈 확장")):
        for m in rx.finditer(text):
            hits.append({"path": m.group(0).strip(), "why": why})
    return hits


# ---- 폐기 판정 (실행 규칙 v2): ① 저장소·다른 실행·다른 세션 기록의 파일 내용을 읽음 ② (나)가 스킬·점검 코드를 읽음.
# "내용을 읽음"만 센다. 폴더·파일 이름 조회(ls, find, cd, Glob, listdir …)와 권한 거부된 호출은 기록만 한다.

NAME_ONLY_CMDS = frozenset({"ls", "find", "cd", "pwd", "echo", "mkdir", "stat", "du", "tree", "test", "export"})
SEPARATORS = {";", "&&", "||", "|", ";;", "&"}
ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# python 코드에서 이름만 보는 호출: os.listdir('…'), glob.glob('…'), os.path.exists('…'), Path('…').iterdir() …
PY_NAME_BEFORE = re.compile(r"(?:listdir|scandir|walk|glob|iglob|exists|isdir|isfile|islink|getsize|lstat|stat)"
                            r"\s*\(\s*[rbf]?['\"]$")
PY_NAME_AFTER = re.compile(r"^['\"]\s*\)\s*\.\s*(?:iterdir|glob|rglob|exists|is_dir|is_file|stat|name|parent)\b")
SKILL_MARKS = ("/.claude/skills/", "/lchome/", "/leakcheck/", "/skill_src/", "run_check.py", "SKILL.md", "rules.md")


def _resolve(p: str, cwd: str) -> str:
    return os.path.normpath(p if p.startswith("/") else os.path.join(cwd, p))


def area(p: str, rd: RunDir, condition: str, cwd: str | None = None) -> str | None:
    """경로 하나의 폐기 구분: "①" | "②" | None. 상대 경로는 cwd(기본: 작업 폴더) 기준."""
    q = _resolve(p, cwd or str(rd.ws))
    own = str(rd.root)
    under = lambda base: q == base or q.startswith(base.rstrip("/") + "/")
    if under(own):
        if (condition == "나" and (under(own + "/lchome") or "/.claude/skills/" in q + "/")
                and os.path.exists(q)):       # (나) 폴더에는 사본이 없다: 없는 파일은 읽을 수 없으므로 기록만
            return "②"
        return None
    if own_tmp(q, rd):
        return None
    if under(str(ROOT)) or under(str(RUN_BASE)) or under("/tmp/claude-0") or under("/root/.claude"):
        return "①"
    if condition == "나" and any(m in q for m in SKILL_MARKS):
        return "②"
    return None


def _path_tokens(text: str) -> list[tuple[int, str]]:
    """문자열 안의 경로 후보 (절대 경로, .. 가 든 상대 경로, .claude/… 상대 경로)와 위치."""
    out = [(m.start(1), m.group(1).rstrip(".")) for m in PATH_RE.finditer(text)]
    for m in DOTDOT_RE.finditer(text):
        i = m.end() - 1
        tok = _token_at(text, i)
        out.append((text.find(tok, max(0, i - len(tok))), tok))
    for m in re.finditer(r"(?<![\w/.])((?:\.claude|lchome)/[A-Za-z0-9_.\-/]*)", text):
        out.append((m.start(1), m.group(1)))
    return out


def python_reads(code: str, rd: RunDir, condition: str, cwd: str | None = None) -> list[dict]:
    """python 코드에서 금지 구역 경로가 내용을 읽는 자리에 쓰였는지 (이름만 보는 호출은 뺀다)."""
    hits = []
    for i, tok in _path_tokens(code):
        a = area(tok, rd, condition, cwd)
        if a is None:
            continue
        before, after = code[max(0, i - 40):i], code[i + len(tok):i + len(tok) + 40]
        if PY_NAME_BEFORE.search(before) or (re.search(r"Path\s*\(\s*[rbf]?['\"]$", before) and PY_NAME_AFTER.match(after)):
            continue
        hits.append({"class": a, "path": tok})
    return hits


def _segments(cmd: str) -> list[list[str]] | None:
    lx = shlex.shlex(cmd.replace("\n", " ; "), posix=True, punctuation_chars=True)
    lx.whitespace_split = True
    lx.commenters = ""
    try:
        toks = list(lx)
    except ValueError:
        return None
    segs, cur = [], []
    for t in toks:
        if t in SEPARATORS:
            segs.append(cur)
            cur = []
        else:
            cur.append(t)
    segs.append(cur)
    return [s for s in segs if s]


HEREDOC_RE = re.compile(r"^(?P<head>[^\n]*?)<<-?\s*(?P<q>['\"]?)(?P<tag>\w+)(?P=q)(?P<rest>[^\n]*)\n(?P<body>.*?)\n(?P=tag)[ \t]*(?:\n|$)", re.S)


def bash_reads(cmd: str, rd: RunDir, condition: str, state: dict) -> list[dict]:
    """Bash 명령 하나에서 금지 구역의 내용을 읽는 자리. state["cwd"]는 호출 사이에 이어지는 현재 폴더."""
    hits = []
    m = HEREDOC_RE.match(cmd)
    if m:                                   # 여러 줄 입력: 첫 줄은 셸, 본문은 그 명령의 입력
        head = m.group("head") + m.group("rest")
        words = [w for w in (_segments(head) or [[]])[-1] if not ASSIGN.match(w)]
        body = m.group("body")
        if words and words[0] in ("python", "python3"):
            hits += python_reads(body, rd, condition, state["cwd"])
        else:
            hits += [{"class": a, "path": t} for _, t in _path_tokens(body)
                     if (a := area(t, rd, condition, state["cwd"]))]
        return hits + bash_reads(head + "\n" + cmd[m.end():], rd, condition, state)
    segs = _segments(cmd)
    if segs is None:                        # 해석 못 함: 금지 구역 경로가 있으면 읽은 것으로 본다
        return [{"class": a, "path": t} for _, t in _path_tokens(cmd) if (a := area(t, rd, condition, state["cwd"]))]
    for seg in segs:
        words = list(seg)
        while words and (ASSIGN.match(words[0]) or words[0] in ("do", "then", "else", "!")):
            words = words[1:]
        if not words or words[0] in ("for", "done", "fi", "while", "if"):
            continue
        w0, args = words[0], words[1:]
        if w0 == "cd":
            target = args[0] if args else str(rd.ws)
            state["cwd"] = _resolve(target, state["cwd"])
            continue
        cwd_area = area(state["cwd"], rd, condition, state["cwd"])
        if w0 in NAME_ONLY_CMDS:
            continue
        if w0 in ("python", "python3"):
            if "-c" in args and args.index("-c") + 1 < len(args):
                k = args.index("-c")
                hits += python_reads(args[k + 1], rd, condition, state["cwd"])
                rest = args[:k] + args[k + 2:]
            else:
                rest = args
            for a_ in rest:
                if not a_.startswith("-") and (a := area(a_, rd, condition, state["cwd"])):
                    hits.append({"class": a, "path": a_})
            continue
        # 그 밖의 명령(cat, head, grep, sed, cut, sort …): 경로 인자 = 내용을 읽음. 금지 구역 안에서 상대 경로로 읽어도 같다
        for a_ in args:
            if a_.startswith("-"):
                continue
            a = area(a_, rd, condition, state["cwd"])
            if a is None and cwd_area and not a_.startswith("/") and re.search(r"[\w*]", a_):
                a = cwd_area
            if a:
                hits.append({"class": a, "path": a_})
    return hits


def discard_hits(events: list[dict], rd: RunDir, condition: str, scripts: list[tuple[str, str]] = ()) -> list[dict]:
    """폐기 사유가 되는 호출 (권한 거부된 호출은 뺀다). scripts = 작업 폴더에 남은 (이름, 내용) — 실행했으면 내용도 본다."""
    denied = {d.get("tool_use_id") for e in events if e.get("type") == "result"
              for d in (e.get("permission_denials") or [])} - {None}
    state = {"cwd": str(rd.ws)}
    hits = []
    written = dict(scripts)
    for u in tool_uses(events):
        if u["id"] in denied:
            continue
        inp, n = u["input"], u["name"]
        found = []
        if n == "Read" or n == "Grep":
            p = str(inp.get("file_path") or inp.get("path") or "")
            if p and (a := area(p, rd, condition, state["cwd"])):
                found.append({"class": a, "path": p})
        elif n == "Write" and str(inp.get("file_path", "")).endswith((".py", ".sh")):
            written[Path(str(inp["file_path"])).name] = str(inp.get("content", ""))
        elif n == "Bash":
            cmd = str(inp.get("command", ""))
            found += bash_reads(cmd, rd, condition, state)
            for name, body in written.items():          # 실행한 스크립트의 내용
                if re.search(r"\b(?:python3?|sh|bash)\s+(?:\S*/)?" + re.escape(name) + r"\b", cmd):
                    found += python_reads(body, rd, condition, state["cwd"])
        elif n == "Skill" and condition == "나" and "leakage-check" in json.dumps(inp, ensure_ascii=False):
            pass                                            # (나)에는 스킬이 없어 읽을 수 없다: 기록만
        hits += [{"tool": n, "id": u["id"], **h} for h in found]
    return hits


def audit(events: list[dict], rd: RunDir, condition: str) -> dict:
    """도구 호출 입력 전부를 검사한다. violations = 기록용 (폴더 탐색·금지 경로 시도, 권한 거부된 것 포함)."""
    uses = tool_uses(events)
    hits = []
    for u in uses:
        if u["name"] in DISALLOWED_TOOLS:
            hits.append({"tool": u["name"], "path": None, "why": "꺼 둔 도구"})
        for s in _strings(u["input"]):
            hits += [{"tool": u["name"], **h} for h in scan_text(s, rd, condition)]
        if u["name"] in ("Glob", "Grep", "Read") and u["input"].get("path") == "/":
            hits.append({"tool": u["name"], "path": "/", "why": "최상위 폴더 조회 (/)"})
    denied_ids = {d.get("tool_use_id") for e in events if e.get("type") == "result"
                  for d in (e.get("permission_denials") or [])} - {None}
    bash = [u["input"].get("command", "") for u in uses if u["name"] == "Bash" and u["id"] not in denied_ids]
    return {
        "tool_counts": {n: sum(u["name"] == n for u in uses) for n in sorted({u["name"] for u in uses})},
        "checker_invoked": any("run_check.py" in c and "--rules" not in c for c in bash),
        "skill_tool_invoked": any(u["name"] == "Skill" and "leakage-check" in json.dumps(u["input"], ensure_ascii=False)
                                  for u in uses),
        "skill_md_read": any(u["name"] == "Read" and str(u["input"].get("file_path", "")).endswith("SKILL.md")
                             for u in uses),
        "violations": hits,
        "discard": discard_hits(events, rd, condition),
    }


def ws_scripts(rd: RunDir) -> list[tuple[str, str]]:
    return [(f.name, f.read_text(encoding="utf-8", errors="replace")) for f in sorted(rd.ws.rglob("*"))
            if f.is_file() and f.suffix in (".py", ".sh") and ".claude" not in f.relative_to(rd.ws).parts]


def audit_scripts(rd: RunDir, condition: str) -> list[dict]:
    """실행 뒤 작업 폴더에 남은 스크립트(.py, .sh) 내용도 기록용으로 검사한다 (스킬 사본은 제외)."""
    hits = []
    for name, text in ws_scripts(rd):
        hits += [{"tool": f"file:{name}", **h} for h in scan_text(text, rd, condition)]
    return hits


def init_info(events: list[dict]) -> dict:
    for e in events:
        if e.get("type") == "system" and e.get("subtype") == "init":
            return {"model": e.get("model"), "skills": sorted(e.get("skills") or []),
                    "tools": sorted(e.get("tools") or []), "mcp_servers": e.get("mcp_servers") or [],
                    "cwd": e.get("cwd"), "permission_mode": e.get("permissionMode"),
                    "session_id": e.get("session_id")}
    return {}


def result_info(events: list[dict]) -> dict:
    for e in reversed(events):
        if e.get("type") == "result":
            return {k: e.get(k) for k in ("subtype", "is_error", "result", "num_turns", "duration_ms",
                                          "total_cost_usd", "usage", "modelUsage", "terminal_reason",
                                          "permission_denials", "api_error_status", "session_id")}
    return {}


LIMIT_RE = re.compile(r"usage limit|rate limit|limit reached|429|overloaded|too many requests", re.I)


def is_limit(res: dict, err: bytes) -> bool:
    """요금제 한도·속도 제한. 오류 문장만 본다."""
    if res.get("api_error_status") in (429, 529):
        return True
    if res and not res.get("is_error"):
        return False
    return bool(LIMIT_RE.search((res.get("result") or "") + err.decode("utf-8", "replace")[-2000:]))


def is_auth_error(res: dict) -> bool:
    return bool(res.get("is_error")) and bool(re.search(r"Authentication error|Not logged in|/login",
                                                         res.get("result") or ""))


def is_turn_capped(res: dict) -> bool:
    return res.get("subtype") == "error_max_turns"


def denials(res: dict) -> dict:
    d = res.get("permission_denials") or []
    return {"count": len(d), "by_tool": {n: sum(x.get("tool_name") == n for x in d) for n in sorted({x.get("tool_name") for x in d})},
            "checker_denied": sum("run_check.py" in json.dumps(x.get("tool_input") or {}, ensure_ascii=False) for x in d),
            "commands": [str((x.get("tool_input") or {}).get("command", x.get("tool_name")))[:200] for x in d]}


def manipulation_check(init: dict, condition: str, model: str) -> list[str]:
    """init 기록만으로 판정한다 (점검기를 부르지 않은 것은 사유가 아니다)."""
    bad = []
    if not init:
        return ["init 이벤트 없음"]
    if init.get("model") != model:
        bad.append(f"모델 불일치: {init.get('model')}")
    has = "leakage-check" in init.get("skills", [])
    if condition == "가" and not has:
        bad.append("(가)에 leakage-check 스킬이 로드되지 않음")
    if condition == "나" and has:
        bad.append("(나)에 leakage-check 스킬이 로드됨")
    if set(init.get("tools", [])) != set(VISIBLE_TOOLS):
        bad.append(f"보이는 도구가 허용 목록과 다름: {sorted(set(init.get('tools', [])) ^ set(VISIBLE_TOOLS))}")
    if init.get("mcp_servers"):
        bad.append("MCP 서버가 연결됨")
    return bad


# ---------------------------------------------------------------- 점검기 출력 수거 ((가)만)

def _checker_no(p: Path) -> int:
    m = re.fullmatch(r"checker(?:_(\d+))?", p.stem)
    return (int(m.group(1)) if m.group(1) else 1) if m else 10 ** 6


def collect_checker(rd: RunDir, variant: str, events: list[dict]) -> tuple[dict | None, list[dict], list[Path]]:
    """실행 폴더 전체(점검기 사본·스킬 사본 제외)의 checker*.json에서 원래 설계서(같은 해시)를 점검한 첫 결과를 고른다.
    순서: 작업 폴더 맨 위 먼저, 그다음 번호가 작은 것. 돌려주는 값: (고른 기록, 파일 목록, 파일 경로)."""
    want = rd.inputs.get(variant)
    skip = [p for p in (rd.lchome, rd.ws / ".claude") if p]
    cands = [p for p in rd.root.rglob("checker*.json")
             if p.is_file() and not any(p.is_relative_to(s) for s in skip)]
    cands.sort(key=lambda p: (p.parent != rd.ws, _checker_no(p), str(p)))
    chosen, files = None, []
    for p in cands:
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            c = None
        ch = (c or {}).get("checked") or {}
        ok = c is not None and ch.get("design_sha256") == want
        files.append({"path": str(p.relative_to(rd.root)), "design_file": ch.get("design_file"),
                      "design_sha256": ch.get("design_sha256"), "matches_original": ok})
        if ok and chosen is None:
            chosen = (p, c)
    if chosen is None:
        return None, files, cands
    p, c = chosen
    code = None
    for text in tool_results(events).values():      # 그 파일을 저장했다고 찍힌 도구 결과의 "종료 코드 N"
        if p.name in text and "sha256" in text:
            m = re.search(r"종료 코드 (\d)", text)
            if m:
                code = int(m.group(1))
                break
    return {"exit_code": code, "checker": c, "source_file": str(p.relative_to(rd.root))}, files, cands


# ---------------------------------------------------------------- 한 번 실행

@dataclass
class Attempt:
    status: str                    # "ok" | "fail" (기계적 실패, 재실행) | "discard" (폐기, 빈칸) | "limit" (한도·인증)
    reasons: list[str]
    exit_code: int | None
    seconds: float
    events: list[dict]
    raw: bytes
    stderr: bytes
    meta: dict
    rd: RunDir | None = None
    findings: str | None = None
    resubmit_raw: bytes = b""
    checker: dict | None = None
    checker_paths: list[Path] = field(default_factory=list)


def _judge(code, res, init, err, condition, model) -> tuple[str, list[str]]:
    if code is not None and is_auth_error(res):
        return "limit", ["인증 오류"]
    if code is not None and is_limit(res, err):
        return "limit", ["한도 도달"]
    reasons = []
    if code is None:
        reasons.append("시간 초과")
    elif not res:
        reasons.append(f"결과 없음 (code={code})")
    elif not is_turn_capped(res) and (code != 0 or res.get("is_error")):
        reasons.append(f"종료 코드 오류 (code={code}, subtype={res.get('subtype')})")
    reasons += [f"조작 확인 실패: {m}" for m in manipulation_check(init, condition, model)]
    return ("fail" if reasons else "ok"), reasons


def run_once(rid: str, row: dict, try_no: int, model: str, users: OsUser, launcher=launch,
             base: Path = RUN_BASE) -> Attempt:
    name = f"lr{rid[:10]}t{try_no}"
    cond = row["condition"]
    rd = prepare_run(base, f"{rid}-t{try_no}", row["variant"], cond)
    text = prompt.render(row["variant"], "data")
    users.create(name, rd)
    resub_raw, resub_meta, resub_events = b"", None, []
    try:
        shutil.copy2(HOOK_SRC, rd.root / "bash_allow_hook.py")
        settings = rd.root / "settings.json"
        settings.write_text(json.dumps(deny_settings(rd)), encoding="utf-8")
        env = agent_env(rd, cond)
        code, out, err, secs = launcher(users.wrap(name, agent_argv(text, model, settings), env), rd.ws, TIMEOUT_S)
        events = parse_stream(out)
        init, res = init_info(events), result_info(events)
        status, reasons = _judge(code, res, init, err, cond, model)
        disc = discard_hits(events, rd, cond, ws_scripts(rd))
        if status == "ok" and disc:
            status, reasons = "discard", ["폐기" + "·".join(sorted({h["class"] for h in disc}))]
        # 형식 재제출 1회 (두 조건 같음). 폐기·기계적 실패·한도에는 하지 않는다
        if status == "ok" and FORMAT_RETRIES and grader.validate_findings(read_findings(rd)):
            errs = grader.validate_findings(read_findings(rd))
            sid = init.get("session_id") or res.get("session_id")
            argv2 = agent_argv(RESUBMIT_TEXT.format(errors=", ".join(errs)), model, settings,
                               max_turns=MAX_TURNS_RETRY, resume=sid)
            c2, resub_raw, err2, s2 = launcher(users.wrap(name, argv2, env), rd.ws, TIMEOUT_S)
            resub_events = parse_stream(resub_raw)
            r2 = result_info(resub_events)
            secs += s2
            resub_meta = {"errors_before": errs, "exit_code": c2, "seconds": round(s2, 1),
                          "result": {k: v for k, v in r2.items() if k != "result"},
                          "turn_capped": is_turn_capped(r2), "permission_denials": denials(r2)}
            if c2 is not None and (is_auth_error(r2) or is_limit(r2, err2)):
                status, reasons = "limit", ["한도 도달 (재제출)"]
            else:
                d2 = discard_hits(resub_events, rd, cond, ws_scripts(rd))
                if d2:
                    disc += d2
                    status, reasons = "discard", ["폐기" + "·".join(sorted({h["class"] for h in disc})) + " (재제출)"]
                elif c2 is None or not r2 or (not is_turn_capped(r2) and (c2 != 0 or r2.get("is_error"))):
                    resub_meta["failed"] = True          # 재제출만 실패: 재실행하지 않고 그때의 파일을 그대로 쓴다
    finally:
        users.remove(name, rd)
    findings = read_findings(rd)
    aud = audit(events, rd, cond)
    aud["violations"] += audit_scripts(rd, cond)
    aud["discard"] = disc
    if resub_events:
        aud["resubmit_violations"] = audit(resub_events, rd, cond)["violations"]
    chk, chk_files, chk_paths = (collect_checker(rd, row["variant"], events + resub_events)
                                 if cond == "가" else (None, [], []))
    meta = {"try": try_no, "status": status, "reasons": reasons, "exit_code": code,
            "seconds": round(secs, 1), "init": init,
            "result": {k: v for k, v in res.items() if k != "result"},
            "turn_capped": is_turn_capped(res), "num_turns": res.get("num_turns"),
            "format_retries": 1 if resub_meta else 0, "resubmit": resub_meta,
            "findings_present": findings is not None, "findings_valid": not grader.validate_findings(findings),
            "audit": aud, "inputs_changed": inputs_changed(rd), "lchome_files": rd.lchome_files,
            "checker_files": chk_files, "permission_denials": denials(res), "files": file_listing(rd)}
    meta["no_checker_after_denial"] = (cond == "가" and not aud["checker_invoked"]
                                       and meta["permission_denials"]["count"] > 0)
    return Attempt(status, reasons, code, secs, events, out, err, meta, rd, findings, resub_raw, chk, chk_paths)


def _write_json(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(p)


def _fresh(d: Path) -> Path:
    n, cand = 1, d
    while cand.exists():
        n += 1
        cand = d.with_name(f"{d.name}_{n}")
    return cand


def _gz(p: Path, data: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(gzip.compress(data, mtime=0))


class LimitReached(Exception):
    """한도·인증 오류: 이 행은 시도로 세지 않고 멈춘다. 부분 출력은 채택하지 않고 따로 둔다. 이어 갈 때 일정 순서는 그대로."""


def _save_attempt(d: Path, a: Attempt) -> None:
    _gz(d / "transcript.jsonl.gz", a.raw)
    _gz(d / "stderr.txt.gz", a.stderr)
    if a.resubmit_raw:
        _gz(d / "resubmit.jsonl.gz", a.resubmit_raw)
    _write_json(d / "attempt.json", {**a.meta, "findings": a.findings})


def run_row(out: Path, rid: str, row: dict, model: str, users: OsUser, launcher=launch,
            base: Path = RUN_BASE) -> dict:
    tries = []
    for k in range(1, MAX_RETRIES + 2):
        a = run_once(rid, row, k, model, users, launcher, base)
        if a.status == "limit":
            ts = int(time.time())
            _save_attempt(_fresh(out / "discarded" / rid / f"limit{ts}"), a)
            if a.rd is not None and a.rd.root.exists():          # 작업 폴더도 다른 이름으로 남긴다
                a.rd.root.rename(_fresh(a.rd.root.with_name(f"{a.rd.root.name}-limit{ts}")))
            raise LimitReached(f"{rid}: {a.reasons[0]}")
        tries.append(a.meta)
        if a.status in ("ok", "discard"):
            break
        _save_attempt(_fresh(out / "discarded" / rid / f"try{k}"), a)
    final = tries[-1]
    status = {"ok": "done", "discard": "discarded"}.get(final["status"], "failed")
    meta = {"report_id": rid, "status": status, "attempts": tries, "retries": len(tries) - 1,
            "retry_reasons": [r for t in tries[:-1] for r in t["reasons"]] if status != "failed"
            else [r for t in tries for r in t["reasons"]]}
    if status == "done":
        _gz(out / "transcripts" / f"{rid}.jsonl.gz", a.raw)
        if a.resubmit_raw:
            _gz(out / "transcripts" / f"{rid}.resubmit.jsonl.gz", a.resubmit_raw)
        _write_json(out / "reports" / f"{rid}.json", {"report_id": rid, "variant": row["variant"], "findings": a.findings})
        if row["condition"] == "가":
            rec = {"report_id": rid, "variant": row["variant"], "exit_code": None, "checker": None}
            if a.checker:
                rec.update(a.checker)
            _write_json(out / "checker" / f"{rid}.json", rec)
            for p in a.checker_paths:
                dst = out / "checker_files" / rid / str(p.relative_to(a.rd.root)).replace("/", "__")
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dst)
        if (out / "conditions.json").exists() and rid in json.loads((out / "conditions.json").read_text(encoding="utf-8")):
            record_condition(out, rid, turn_capped=final["turn_capped"], format_retries=final["format_retries"])
    elif status == "discarded":
        _save_attempt(_fresh(out / "discarded" / rid / f"try{len(tries)}"), a)
    _write_json(out / "meta" / f"{rid}.json", meta)
    return meta


# ---------------------------------------------------------------- 실행 묶음

FINISHED = ("done", "discarded", "failed")


def pending(out: Path, sched: dict[str, dict]) -> list[str]:
    """끝나지 않은 행 (일정 순서). 채택·폐기·재실행 소진(빈칸)은 끝난 행이다."""
    done = set()
    for rid in sched:
        m = out / "meta" / f"{rid}.json"
        if m.exists() and json.loads(m.read_text(encoding="utf-8"))["status"] in FINISHED:
            done.add(rid)
    return [rid for rid in sorted(sched, key=lambda r: sched[r]["order"]) if rid not in done]


def batches(sched: dict[str, dict]) -> list[int]:
    return sorted({r.get("batch", r["rep"]) for r in sched.values()})


def run_all(out: Path, sched: dict[str, dict], model: str, workers: int = WORKERS, limit: int | None = None,
            users: OsUser | None = None, launcher=launch, base: Path = RUN_BASE) -> dict:
    """끝나지 않은 행을 순서대로 돌린다. 한도에 걸리면 새 행을 시작하지 않고 멈춘다."""
    users = users or default_users()
    todo = pending(out, sched)[:limit]
    lock = threading.Lock()
    results, stop = [], threading.Event()

    def one(rid: str) -> None:
        if stop.is_set():
            return
        try:
            m = run_row(out, rid, sched[rid], model, users, launcher, base)
        except LimitReached:
            stop.set()
            print(f"{rid} 한도 도달 또는 인증 오류: 새 실행을 시작하지 않는다", flush=True)
            return
        with lock:
            results.append(m)
            print(f"[{len(results)}/{len(todo)}] {rid} {m['status']} 재실행 {m['retries']}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(one, todo))
    return {"results": results, "limit_reached": stop.is_set()}


def git_commit_push(paths: list[Path], message: str, tries: int = 4) -> bool:
    subprocess.run(["git", "-C", str(ROOT), "add", *map(str, paths)], check=True)
    if subprocess.run(["git", "-C", str(ROOT), "diff", "--cached", "--quiet"]).returncode == 0:
        return True
    subprocess.run(["git", "-C", str(ROOT), "commit", "-q", "-m", message], check=True)
    for i in range(tries):
        if subprocess.run(["git", "-C", str(ROOT), "push", "-q", "-u", "origin", "HEAD"]).returncode == 0:
            return True
        time.sleep(2 ** (i + 1))
    return False


COMMIT_TRAILER = ("\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n"
                  "Claude-Session: https://claude.ai/code/session_01CiPpe7Uy11jkV6DjQEzYw1")


def run_batches(out: Path, sched: dict[str, dict], model: str, workers: int, commit: bool = True, **kw) -> bool:
    """묶음 단위로 돌리고, 묶음이 끝날 때마다 커밋·푸시한다. 한도에 걸리면 지금까지를 커밋하고 False."""
    for b in batches(sched):
        sub = {rid: r for rid, r in sched.items() if r.get("batch", r["rep"]) == b}
        if not pending(out, sub):
            continue
        res = run_all(out, sub, model, workers, **kw)
        left = len(pending(out, sub))
        msg = (f"6단계 {out.name}: 묶음 {b} " + ("완료" if left == 0 and not res["limit_reached"]
                                               else f"중단 (남은 {left}회, 한도 도달={res['limit_reached']})"))
        if commit:
            git_commit_push([out], msg + COMMIT_TRAILER)
        print(msg, flush=True)
        if res["limit_reached"]:
            return False
    return True


def status(out: Path) -> dict:
    sched = json.loads((out / "conditions.json").read_text(encoding="utf-8"))
    s = {c: {"planned": 0, "done": 0, "discarded": 0, "failed": 0, "retries": 0, "retry_reasons": {},
             "checker_invoked": 0, "findings_valid": 0, "findings_missing": 0, "turn_capped": 0, "format_retries": 0,
             "seconds": [], "turns": [], "cost_usd": 0.0, "permission_denials": 0, "checker_denied": 0,
             "no_checker_after_denial": 0, "skills": set(),
             "tokens": {"input": 0, "cache_creation": 0, "cache_read": 0, "output": 0}} for c in CONDITIONS}
    for rid, row in sched.items():
        c = s[row["condition"]]
        c["planned"] += 1
        m = out / "meta" / f"{rid}.json"
        if not m.exists():
            continue
        meta = json.loads(m.read_text(encoding="utf-8"))
        c[meta["status"]] += 1
        c["retries"] += meta["retries"]
        for r in meta["retry_reasons"]:
            c["retry_reasons"][r] = c["retry_reasons"].get(r, 0) + 1
        last = meta["attempts"][-1]
        if meta["status"] == "done":
            c["checker_invoked"] += last["audit"]["checker_invoked"]
            c["findings_valid"] += last["findings_valid"]
            c["findings_missing"] += not last["findings_present"]
            c["turn_capped"] += bool(last["turn_capped"])
            c["format_retries"] += last["format_retries"]
            c["permission_denials"] += last["permission_denials"]["count"]
            c["checker_denied"] += last["permission_denials"]["checker_denied"]
            c["no_checker_after_denial"] += bool(last.get("no_checker_after_denial"))
        for t in meta["attempts"]:
            c["skills"].update((t.get("init") or {}).get("skills") or [])
            c["seconds"].append(t["seconds"])
            if t.get("num_turns") is not None:
                c["turns"].append(t["num_turns"])
            c["cost_usd"] += (t["result"] or {}).get("total_cost_usd") or 0
            rs = [t["result"] or {}, ((t.get("resubmit") or {}).get("result") or {})]
            for r_ in rs:
                for mu in (r_.get("modelUsage") or {}).values():
                    for k, uk in (("input", "inputTokens"), ("cache_creation", "cacheCreationInputTokens"),
                                  ("cache_read", "cacheReadInputTokens"), ("output", "outputTokens")):
                        c["tokens"][k] += mu.get(uk) or 0
    for c in s.values():
        secs, turns = c.pop("seconds"), c.pop("turns")
        c["mean_seconds_per_attempt"] = round(sum(secs) / len(secs), 1) if secs else None
        c["turns_mean_max"] = [round(sum(turns) / len(turns), 1), max(turns)] if turns else None
        c["cost_usd"] = round(c["cost_usd"], 3)
        c["checker_invoked_rate"] = round(c["checker_invoked"] / c["done"], 3) if c["done"] else None
        c["blank"] = c["failed"] + c["discarded"]
        n = c["done"] + c["failed"] + c["discarded"]
        c["mean_tokens_per_row"] = {k: round(v / n) for k, v in c["tokens"].items()} if n else None
    a, b = s["가"].pop("skills"), s["나"].pop("skills")
    s["skills_only_in"] = {"가": sorted(a - b), "나": sorted(b - a)}
    return s


def _discarded_attempts(out: Path, rid: str) -> list[tuple[int, Path]]:
    d = out / "discarded" / rid
    if not d.exists():
        return []
    res = []
    for t in d.iterdir():
        m = re.fullmatch(r"try(\d+)(?:_\d+)?", t.name)
        if m and (t / "attempt.json").exists():
            res.append((int(m.group(1)), t))
    return sorted(res)


def discard_report(out: Path) -> dict:
    """묶음·조건별 폐기 요약: 폐기 구분(①·②)과 걸린 호출 (내용은 보지 않는다)."""
    sched = json.loads((out / "conditions.json").read_text(encoding="utf-8"))
    rep: dict = {}
    for rid, row in sched.items():
        for k, d in _discarded_attempts(out, rid):
            a = json.loads((d / "attempt.json").read_text(encoding="utf-8"))
            if a["status"] != "discard":
                continue
            key = f"묶음{row.get('batch', row['rep'])}/{row['condition']}"
            r = rep.setdefault(key, {"discards": 0, "①": 0, "②": 0, "calls": [], "by_variant": {}})
            r["discards"] += 1
            r["by_variant"][row["variant"]] = r["by_variant"].get(row["variant"], 0) + 1
            for cls in {h["class"] for h in a["audit"]["discard"]}:
                r[cls] += 1
            r["calls"] += [{"report_id": rid, "try": k, **{x: h.get(x) for x in ("class", "tool", "path")}}
                           for h in a["audit"]["discard"]]
    return rep


def export_first_attempts(out: Path, dest: Path) -> dict:
    """첫 시도 분석용: 행마다 첫 번째 시도(폐기·기계적 실패 포함)의 findings.json을 채점기 입력 형식으로 모은다.
    내용은 읽지 않고 옮기기만 한다."""
    sched = json.loads((out / "conditions.json").read_text(encoding="utf-8"))
    dest.mkdir(parents=True, exist_ok=True)
    n = {"from_discarded": 0, "from_reports": 0, "missing": 0}
    for rid, row in sched.items():
        first = [d for k, d in _discarded_attempts(out, rid) if k == 1 and d.name == "try1"]
        if first:
            findings = json.loads((first[0] / "attempt.json").read_text(encoding="utf-8")).get("findings")
            n["from_discarded"] += 1
        elif (out / "reports" / f"{rid}.json").exists():
            findings = json.loads((out / "reports" / f"{rid}.json").read_text(encoding="utf-8"))["findings"]
            n["from_reports"] += 1
        else:
            n["missing"] += 1
            continue
        _write_json(dest / f"{rid}.json", {"report_id": rid, "variant": row["variant"], "findings": findings})
    return n


AGENT_IMPORTS = "import pandas, numpy, sklearn, jsonschema, dateutil"


def preflight(base: Path = RUN_BASE) -> list[str]:
    """에이전트 환경(HOME 따로, 사용자 site 없음)에서 python 패키지를 불러올 수 있는지 확인한다. 문제 목록을 돌려준다.
    설치: PYTHONNOUSERSITE=1 python3 -m pip install -r requirements-lock.txt (시스템 위치에 설치된다)."""
    SHARED.mkdir(parents=True, exist_ok=True)
    SHARED.chmod(0o755)
    shutil.copy2(CA_SRC, SHARED / "ca-bundle.crt")
    (SHARED / "ca-bundle.crt").chmod(0o644)
    base.mkdir(parents=True, exist_ok=True)
    base.chmod(0o711)
    for d in HARDEN_DIRS:
        if d.exists():
            d.chmod(d.stat().st_mode & ~0o007)
    rd = prepare_run(base, "preflight", variants()[0], "나")
    try:
        env = agent_env(rd, "나")
        r = subprocess.run(["env", "-i", *(f"{k}={v}" for k, v in env.items()), "python3", "-c", AGENT_IMPORTS],
                           cwd=rd.ws, capture_output=True, text=True)
        return [] if r.returncode == 0 else [f"에이전트 환경에서 python 패키지를 못 불러옴: {r.stderr.strip()[-200:]}"]
    finally:
        shutil.rmtree(rd.root, ignore_errors=True)


def pilot_out() -> Path:
    """시험 실행은 할 때마다 새 폴더 (run1, run2 …). 시험 실행 횟수 = 폴더 수."""
    n = 1
    while (PILOT_OUT / f"run{n}").exists():
        n += 1
    return PILOT_OUT / f"run{n}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["schedule", "preflight", "pilot", "main", "status", "discards", "first-attempts"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--no-commit", action="store_true")
    ap.add_argument("--batches", type=int, nargs="+", help="이 묶음만 돌린다 (main에서는 꼭 지정: --batches 1)")
    a = ap.parse_args(argv)
    if a.cmd == "status":
        print(json.dumps(status(a.out or RUNS_OUT), ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "discards":
        print(json.dumps(discard_report(a.out or RUNS_OUT), ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "first-attempts":
        o = a.out or RUNS_OUT
        print(json.dumps(export_first_attempts(o, o / "first_attempt_reports"), ensure_ascii=False))
        return 0
    if a.cmd == "preflight":
        probs = preflight()
        print("\n".join(probs) or "패키지 확인 통과")
        return 1 if probs else 0
    if a.cmd == "pilot":
        out, sched = pilot_out(), build_schedule(pilot_variants(), 1, PILOT_SEED)
    else:
        out, sched = RUNS_OUT, build_schedule(variants(), REPS, SCHEDULE_SEED)
        if a.cmd == "main" and not a.batches:
            raise SystemExit("본 실행은 묶음을 지정한다 (예: --batches 1). 1회차 뒤에는 멈춘다.")
    sched = ensure_schedule(out, sched)
    if a.cmd == "schedule":
        print(f"{out / 'conditions.json'}: {len(sched)}행")
        return 0
    probs = preflight()
    if probs:
        raise SystemExit("사전 확인 실패:\n" + "\n".join(probs))
    prompt.text()
    if a.batches:
        sched = {rid: r for rid, r in sched.items() if r.get("batch", r["rep"]) in a.batches}
    finished = run_batches(out, sched, a.model, a.workers, commit=not a.no_commit, limit=a.limit)
    st = status(out)
    print(json.dumps(st, ensure_ascii=False, indent=1))
    return 0 if finished else 3


if __name__ == "__main__":
    raise SystemExit(main())
