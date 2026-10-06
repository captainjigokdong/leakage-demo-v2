"""v2 보류 추첨과 배치 (4a에서 규칙·시드를 커밋, 4b에서 바꾸지 않는다).

docs/phases.md 4a "추첨·배치 스크립트와 시드". 이 파일에는 새 후보의 내용이 없다. 4b에서 봉인 기록
(`sealed/stage2c_record.enc`, 메모리에서만)을 아래 `Case` 꼴로 옮겨 `draw`와 `place`에 넣는다.

추첨 규칙
- D1. 새 후보 30개 중 추첨 전 규칙(R1~R3, docs/injection_log_v2.md)으로 제외된 것은 뺀다 (`excluded`).
- D2. 질문마다 남은 후보를 번호 순으로 놓고 `random.Random(f"{DRAW_SEED}-{질문}")`으로 순서를 섞는다.
- D3. 앞에서부터 2개를 고른다. 고른 사례가 어느 바탕에도 배치되지 않으면(P2~P4) 다음 후보로 넘어가고,
  넘어간 횟수를 이유별로 센다 (그중 분할 칸 규칙 P4 때문인 것).
- D4. 질문 하나에서 2개를 채우지 못하면 멈춘다 (다시 뽑지 않는다).

배치 규칙
- P1. 사례 30개(공개 18 + 보류 12)를 각각 정확히 1번 배치한다.
- P2. 사례마다 배치할 수 있는 유형 = 사례의 유형 중 전제가 있는 유형 (R1). 그중 수치 차이가 0인 유형은,
  다른 배치 가능한 유형의 수치 차이가 0보다 크면 뺀다 (수치 차이는 2c 숫자, known_issues_v2.md K3).
- P3. 바탕은 그 유형의 깨끗한 설계서 하나. 패치가 그 바탕에 적용되는 조합만 (`applies`).
- P4. 분할 칸을 바꾸는 패치(경로가 `split` 또는 `split.`으로 시작하는 명령이 있음)는 무작위 분할 바탕
  (split.method가 RANDOM_SPLIT_METHODS)에만. 사례 번호가 아니라 패치의 대상 칸으로 정한다.
- P5. 결함 변형 22개 = 1개짜리 14 + 2개짜리 8.
- P6. 유형별 결함 변형 수는 동적 11 / 고정 11. 그 배치가 없을 때만 10/12, 그다음 12/10.
- P7. 바탕마다 결함 변형 2~3개.
- P8. 2개짜리 변형: 두 사례의 지목 항목(`designs.inject.targets_of`)이 겹치지 않고, 두 패치를 차례로 적용한
  설계서가 `applies`를 통과한다. SOLO 사례(E16)는 2개짜리에 넣지 않는다.
- P9. 2개짜리 변형 안의 보류 사례 수 h는 |h − 16 × 보류 12/30| ≤ 1 (16 × 0.4 = 6.4 → h는 6 또는 7).
- P10. 깨끗한 변형 8개 = 깨끗한 설계서 8개 각 1번 (패치 없음).
- P11. 위 규칙을 만족하는 배치를 `random.Random(PLACE_SEED)`로 정한 순서의 깊이 우선 탐색으로 찾는다.
  같은 입력 → 같은 배치. 탐색이 상한에 걸리면 멈춘다 (다른 유형 비율로 넘어가지 않는다).

맹검 처리(파일 이름 코드, 항목 순서 섞기)는 공개 시드가 아니라 4b에서 새로 만드는 값으로 하고 정답표에 봉인한다.
이 파일은 점검기(leakcheck)를 불러오지 않는다.
"""
from __future__ import annotations

import json
import random
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from designs.inject import apply_ops, targets_of

ROOT = Path(__file__).resolve().parent.parent
CLEAN_DIR = ROOT / "designs" / "clean_v2"
CLEAN_NAMES = ["aki_a", "aki_b", "aki_c", "aki_d", "readmit_a", "readmit_b", "readmit_c", "readmit_d"]

# --- 시드와 상수 (4a 커밋, 4b에서 바꾸지 않는다) --------------------------------------
DRAW_SEED = 1937495026            # secrets.randbits(32), 2026-10-06
PLACE_SEED = 3216632932           # secrets.randbits(32), 2026-10-06
NEW_ALLOCATION = {"Q1": 8, "Q2": 4, "Q3": 5, "Q4": 4, "Q5": 5, "Q7": 4}   # docs/seal_log_v2.md
PER_QUESTION = 2
N_PUBLIC, N_HOLDOUT = 18, 12
N_SINGLE, N_PAIR = 14, 8
TYPE_SPLITS = [(11, 11), (10, 12), (12, 10)]   # (동적, 고정) 결함 변형 수, 앞에서부터
PER_BASE = (2, 3)
SOLO = {"E16"}                                  # v1 사용자 결정 유지
RANDOM_SPLIT_METHODS = {"group_holdout", "group_kfold", "random_rows"}
HOLDOUT_PAIR_TOL = 1.0
MAX_NODES = 2_000_000

# 공개 18개의 2c 수치 차이 (docs/injection_log_v2.md "v1 18개 결과" 표, known_issues_v2.md K3: 배치 규칙에는 이 숫자)
PUBLIC_DIFF_2C = {
    "E01": {"dynamic": 28034}, "E02": {"dynamic": 762, "fixed": 1241}, "E03": {"dynamic": 11294},
    "E04": {"dynamic": 862}, "E05": {"dynamic": 4671}, "E06": {"fixed": 698},
    "E07": {"dynamic": 186, "fixed": 171}, "E08": {"dynamic": 0, "fixed": 371}, "E09": {"fixed": 1912},
    "E10": {"dynamic": 10, "fixed": 4}, "E11": {"dynamic": 6729}, "E12": {"fixed": 2196},
    "E13": {"dynamic": 2064}, "E14": {"dynamic": 20766}, "E15": {"dynamic": 10535}, "E16": {"fixed": 693},
    "E17": {"dynamic": 1.61}, "E18": {"fixed": 67},
}

Applies = Callable[[list[dict], dict], bool]


@dataclass
class Case:
    id: str
    question: str
    holdout: bool
    types: list[str]                          # 전제가 있는 유형 (R1 적용 뒤)
    ops: dict[str, list[dict]]                # 유형 → 패치
    difference: dict[str, float] = field(default_factory=dict)   # 유형 → 2c 수치 차이
    excluded: bool = False                    # 추첨 전 규칙으로 제외 (새 후보만)


class PlacementError(RuntimeError):
    pass


# --- 기본 바탕·적용 확인 ------------------------------------------------------------

def load_clean() -> dict[str, dict]:
    return {n: json.loads((CLEAN_DIR / f"{n}.json").read_text(encoding="utf-8")) for n in CLEAN_NAMES}


def default_applies(ops: list[dict], base: dict) -> bool:
    """공개 패치 88조합 확인과 같은 점검 (적용·schema·지목한 곳만 바뀜·테이블·열·값). 점검기는 쓰지 않는다."""
    from tests.test_injectability_v2 import check_case
    return check_case(ops, [base["design_type"]], {base["design_type"]: base}) == []


def touches_split(ops: list[dict]) -> bool:
    """P4: 분할 칸(split 또는 split.*)을 바꾸는 명령이 있는가."""
    return any(op["path"] == "split" or op["path"].startswith("split.") for op in ops)


def random_split(base: dict) -> bool:
    return base["split"]["method"] in RANDOM_SPLIT_METHODS


def placeable_types(c: Case) -> list[str]:
    """P2: 전제가 있는 유형, 수치 차이 0인 유형은 다른 유형이 0보다 크면 뺀다."""
    pos = [t for t in c.types if c.difference.get(t, 1) > 0]
    return sorted(pos) if pos else sorted(c.types)


def compatible_bases(c: Case, bases: dict[str, dict], applies: Applies, split_rule: bool = True) -> list[str]:
    out = []
    for name in sorted(bases):
        b = bases[name]
        t = b["design_type"]
        if t not in placeable_types(c):
            continue
        if split_rule and touches_split(c.ops[t]) and not random_split(b):
            continue
        if applies(c.ops[t], b):
            out.append(name)
    return out


# --- 추첨 ----------------------------------------------------------------------

def draw(candidates: list[Case], bases: dict[str, dict], applies: Applies = default_applies,
         seed: int = DRAW_SEED) -> tuple[list[str], dict]:
    """→ (뽑힌 id 목록, 기록 {질문: {"order_len", "skipped_no_base", "skipped_split_rule"}})."""
    by_q: dict[str, list[Case]] = {}
    for c in candidates:
        if not c.excluded:
            by_q.setdefault(c.question, []).append(c)
    drawn, log = [], {}
    for q in sorted(NEW_ALLOCATION):
        pool = sorted(by_q.get(q, []), key=lambda c: c.id)
        order = random.Random(f"{seed}-{q}").sample(pool, len(pool))
        got, skip, skip_split = [], 0, 0
        for c in order:
            if len(got) == PER_QUESTION:
                break
            if compatible_bases(c, bases, applies):
                got.append(c.id)
            else:
                skip += 1
                skip_split += bool(compatible_bases(c, bases, applies, split_rule=False))
        if len(got) < PER_QUESTION:
            raise PlacementError(f"{q}: 배치할 수 있는 후보가 {len(got)}개 (D4, 멈춤)")
        drawn += got
        log[q] = {"order_len": len(order), "skipped_no_base": skip, "skipped_split_rule": skip_split}
    return sorted(drawn), log


# --- 배치 ----------------------------------------------------------------------

def place(cases: list[Case], bases: dict[str, dict], applies: Applies = default_applies,
          seed: int = PLACE_SEED) -> dict:
    """→ {"type_split": (동적, 고정), "defect": [{"base", "cases"}...], "clean": [바탕 이름...]}."""
    if len(cases) != N_PUBLIC + N_HOLDOUT or len({c.id for c in cases}) != len(cases):
        raise PlacementError("사례 30개가 아니다 (P1)")
    if sum(c.holdout for c in cases) != N_HOLDOUT:
        raise PlacementError("보류 12개가 아니다")
    compat = {c.id: compatible_bases(c, bases, applies) for c in cases}
    empty = sorted(k for k, v in compat.items() if not v)
    if empty:
        raise PlacementError(f"배치할 바탕이 없는 사례 {len(empty)}개")
    for split in TYPE_SPLITS:
        layout = _search(cases, bases, applies, compat, dict(zip(("dynamic", "fixed"), split)), seed)
        if layout is not None:
            names = sorted(bases)
            return {"type_split": split, "defect": layout, "clean": names}
    raise PlacementError("규칙을 만족하는 배치가 없다")


def _search(cases, bases, applies, compat, target, seed):
    """P11: 사례를 바탕에 나누는 깊이 우선 탐색. 끝에서 바탕마다 변형 수(2~3)와 2개짜리 묶음을 정한다.
    바탕 b에 사례 n_b개, 변형 q_b개이면 2개짜리는 n_b − q_b개 (q_b ≤ n_b ≤ 2·q_b). Σ q = 22, Σ n = 30 → 2개짜리 8."""
    rng = random.Random(seed)
    by_id = {c.id: c for c in cases}
    order = sorted(cases, key=lambda c: (len(compat[c.id]), rng.random()))
    exp_h = 2 * N_PAIR * N_HOLDOUT / (N_PUBLIC + N_HOLDOUT)
    lo, hi = PER_BASE
    names = sorted(bases)
    btype = {b: bases[b]["design_type"] for b in names}
    assigned: dict[str, list[str]] = {b: [] for b in names}
    pair_ok: dict[tuple, bool] = {}
    nodes = 0

    def can_pair(x: str, y: str, base: str) -> bool:
        key = (min(x, y), max(x, y), base)
        if key not in pair_ok:
            a, b = by_id[key[0]], by_id[key[1]]
            t = btype[base]
            ok = (a.id not in SOLO and b.id not in SOLO
                  and not set(targets_of(a.ops[t])) & set(targets_of(b.ops[t])))
            if ok:
                try:
                    ok = applies(a.ops[t] + b.ops[t], bases[base])
                except (KeyError, ValueError):
                    ok = False
            pair_ok[key] = ok
        return pair_ok[key]

    def pairings(ids: list[str], n_pairs: int, base: str):
        """ids를 2개짜리 n_pairs개 + 1개짜리로 나누는 방법들 (규칙 P8을 만족하는 것만)."""
        if n_pairs == 0:
            yield [[x] for x in ids]
            return
        if len(ids) < 2 * n_pairs:
            return
        first, rest = ids[0], ids[1:]
        if len(rest) >= 2 * n_pairs:                       # first를 1개짜리로
            for p in pairings(rest, n_pairs, base):
                yield [[first]] + p
        for j, y in enumerate(rest):                       # first를 y와 묶음
            if can_pair(first, y, base):
                for p in pairings(rest[:j] + rest[j + 1:], n_pairs - 1, base):
                    yield [[first, y]] + p

    def q_choices(t: str):
        bs = [b for b in names if btype[b] == t]
        opts = [[q for q in range(lo, hi + 1) if q <= len(assigned[b]) <= 2 * q] for b in bs]

        def rec(i, acc, total):
            if i == len(bs):
                if total == target[t]:
                    yield dict(zip(bs, acc))
                return
            for q in opts[i]:
                yield from rec(i + 1, acc + [q], total + q)
        yield from rec(0, [], 0)

    def finish():
        """끝: 유형마다 q를 고르고, 바탕마다 묶음을 고르고, 2개짜리 안의 보류 수(P9)를 맞춘다."""
        q_lists = [list(q_choices(t)) for t in ("dynamic", "fixed")]
        for qd in q_lists[0]:
            for qf in q_lists[1]:
                q = {**qd, **qf}
                per_base = []
                for b in names:
                    ids = sorted(assigned[b])
                    opts = {}
                    for p in pairings(ids, len(ids) - q[b], b):
                        h = sum(by_id[x].holdout for g in p if len(g) == 2 for x in g)
                        opts.setdefault(h, p)                   # 보류 수마다 처음 나온 묶음 하나
                    if not opts:
                        break
                    per_base.append((b, opts))
                else:
                    pick = _pick_holdout(per_base, exp_h)
                    if pick is not None:
                        return [{"base": b, "cases": g} for b, groups in pick for g in groups]
        return None

    def prune(i: int) -> bool:
        rest = order[i:]
        for t in ("dynamic", "fixed"):
            bs = [b for b in names if btype[b] == t]
            if sum(max(lo, -(-len(assigned[b]) // 2)) for b in bs) > target[t]:
                return True                                  # 변형이 너무 많이 필요
            room = sum(min(hi, len(assigned[b])) for b in bs)
            can = sum(any(btype[b] == t for b in compat[c.id]) for c in rest)
            if room + can < target[t]:
                return True                                  # 변형을 채울 사례가 모자람
        for b in names:
            if len(assigned[b]) < lo and len(assigned[b]) + sum(b in compat[c.id] for c in rest) < lo:
                return True
        return False

    def rec(i: int):
        nonlocal nodes
        nodes += 1
        if nodes > MAX_NODES:
            raise PlacementError("탐색 상한 (P11, 멈춤)")
        if prune(i):
            return None
        if i == len(order):
            return finish()
        c = order[i]
        opts = [b for b in compat[c.id] if len(assigned[b]) < 2 * hi]
        rng.shuffle(opts)
        for b in opts:
            assigned[b].append(c.id)
            got = rec(i + 1)
            if got is not None:
                return got
            assigned[b].pop()
        return None

    out = rec(0)
    if out is None:
        return None
    return sorted(({"base": v["base"], "cases": sorted(v["cases"])} for v in out),
                  key=lambda v: (v["base"], v["cases"]))


def _pick_holdout(per_base, exp_h):
    """바탕마다 {2개짜리 안 보류 수: 묶음} 중 하나씩 골라 합이 |h − exp_h| ≤ HOLDOUT_PAIR_TOL이 되게."""
    reach = {0: []}
    for b, opts in per_base:
        nxt = {}
        for h0, picks in reach.items():
            for h, p in sorted(opts.items()):
                nxt.setdefault(h0 + h, picks + [(b, p)])
        reach = nxt
    for h in sorted(reach, key=lambda h: (abs(h - exp_h), h)):
        if abs(h - exp_h) <= HOLDOUT_PAIR_TOL:
            return reach[h]
    return None


def check_layout(layout: dict, cases: list[Case], bases: dict[str, dict], applies: Applies = default_applies) -> list[str]:
    """배치가 P1~P10을 만족하는지 다시 확인한다 (시험과 4b 기록용). 문제 목록(비면 통과)."""
    by_id = {c.id: c for c in cases}
    p = []
    placed = [x for v in layout["defect"] for x in v["cases"]]
    if sorted(placed) != sorted(by_id):
        return ["P1"]
    sizes = Counter(len(v["cases"]) for v in layout["defect"])
    if sizes != Counter({1: N_SINGLE, 2: N_PAIR}):
        p.append("P5")
    per_type = Counter(bases[v["base"]]["design_type"] for v in layout["defect"])
    if (per_type["dynamic"], per_type["fixed"]) not in TYPE_SPLITS:
        p.append("P6")
    per_base = Counter(v["base"] for v in layout["defect"])
    if any(not PER_BASE[0] <= per_base[b] <= PER_BASE[1] for b in bases):
        p.append("P7")
    exp_h = 2 * N_PAIR * N_HOLDOUT / (N_PUBLIC + N_HOLDOUT)
    h = 0
    for v in layout["defect"]:
        b = bases[v["base"]]
        t = b["design_type"]
        cs = [by_id[x] for x in v["cases"]]
        for c in cs:
            if t not in placeable_types(c):
                p.append(f"P2 {c.id}")
            if touches_split(c.ops[t]) and not random_split(b):
                p.append(f"P4 {c.id}")
        if not applies([op for c in cs for op in c.ops[t]], b):
            p.append(f"P3 {v['cases']}")
        if len(cs) == 2:
            h += sum(c.holdout for c in cs)
            if {c.id for c in cs} & SOLO or set(targets_of(cs[0].ops[t])) & set(targets_of(cs[1].ops[t])):
                p.append(f"P8 {v['cases']}")
    if abs(h - exp_h) > HOLDOUT_PAIR_TOL:
        p.append("P9")
    if sorted(layout["clean"]) != sorted(bases):
        p.append("P10")
    return p


def public_cases() -> list[Case]:
    """공개 18개 (암호 불필요). 유형은 목록의 design_types, 전제는 2c에서 모든 유형에 있음."""
    import csv
    from designs.inject import TYPE_KO
    from designs.patches_v1_cases import V1_CASE_PATCHES
    with open(ROOT / "designs" / "error_catalog_public.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [Case(id=r["id"], question=r["question"], holdout=False, types=TYPE_KO[r["design_types"]],
                 ops={t: V1_CASE_PATCHES[r["id"]] for t in TYPE_KO[r["design_types"]]},
                 difference=PUBLIC_DIFF_2C[r["id"]]) for r in rows]


def new_cases(record: dict, candidates: dict[str, dict], difference) -> list[Case]:
    """4b: 봉인 기록(메모리) → 새 후보 30개의 Case. 칸 이름은 tests/test_injectability_v2.py의 봉인 시험과 같다.
    record["cases"][i] = {id, ops: {유형: 패치}, placeable_types, excluded, ...}, candidates = {id: 후보 행}.
    difference(id, 유형) → 2c 수치 차이 (봉인 기록의 확인 함수 NEW_SUBSTANCE[id](유형)["difference"])."""
    out = []
    for c in sorted(record["cases"], key=lambda c: c["id"]):
        types = sorted(c["placeable_types"])
        out.append(Case(id=c["id"], question=candidates[c["id"]]["question"], holdout=True, types=types,
                        ops={t: c["ops"][t] for t in types},
                        difference={t: difference(c["id"], t) for t in types}, excluded=bool(c["excluded"])))
    return out
