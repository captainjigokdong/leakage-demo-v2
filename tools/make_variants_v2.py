"""4b: 보류 추첨 → 배치 → 변형 30개 생성 → 정답표 봉인 (v2).

추첨·배치는 `designs/build_v2.py`(4a 커밋, 시드 그대로)를 부른다. 4b 봉인 확인의 배치 제외 목록
(`sealed/stage4b_record.enc`, 해시는 `docs/lock_4a_v2.json`)은 `applies` 인자로만 넣는다 (build_v2.py는 바꾸지 않는다).
맹검 값(파일 이름 코드, 항목 순서)은 여기서 새로 만들고 정답표에만 봉인한다.

이 파일에는 후보 내용이 없다. 봉인 파일은 메모리에서만 연다 (암호: 환경 변수 SEAL_PASSWORD).
점검기(leakcheck)를 불러오지 않는다. 결함 변형에는 점검기를 돌리지 않는다.

실행: SEAL_PASSWORD=... python -m tools.make_variants_v2
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import os
import random
import secrets
from collections import Counter
from pathlib import Path

from designs import build_v2 as B
from designs.answer_key_v2 import PRIORITY, PUBLIC_EXCEPTIONS, VERSION, defect_entry, validate_key, variant_entry
from designs.inject import apply_ops, dumps, file_sha256
from tools.seal import decrypt_bytes, encrypt_bytes

ROOT = Path(__file__).resolve().parent.parent
SEALED = ROOT / "sealed"
VARIANT_DIR = ROOT / "designs" / "variants"
ANSWER_KEY = SEALED / "answer_key.enc"
LOCK = ROOT / "docs" / "lock_4a_v2.json"
LIST_DOC = ROOT / "docs" / "variants_v2.md"
PUBLIC_CSV = ROOT / "designs" / "error_catalog_public.csv"


# --- 봉인 파일 (메모리) --------------------------------------------------------

def open_sealed(password: str) -> tuple[dict, dict, dict]:
    rec = json.loads(decrypt_bytes((SEALED / "stage2c_record.enc").read_bytes(), password))
    text = decrypt_bytes((SEALED / "candidates.enc").read_bytes(), password).decode("utf-8")
    cands = {r["id"]: r for r in csv.DictReader(io.StringIO(text))}
    rec4b = json.loads(decrypt_bytes((SEALED / "stage4b_record.enc").read_bytes(), password))
    return rec, cands, rec4b


def exclusions_sha256(excl: list[dict]) -> str:
    return hashlib.sha256(json.dumps(excl, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def make_applies(cases: list[B.Case], excluded: set[tuple[str, str]]) -> B.Applies:
    """제외 목록의 (사례, 바탕) 조합은 적용되지 않는 것으로 본다. 그 밖은 build_v2.default_applies."""
    key = {}
    for c in cases:
        for ops in c.ops.values():
            key[json.dumps(ops, sort_keys=True, ensure_ascii=False)] = c.id

    def ids_of(ops):
        k = json.dumps(ops, sort_keys=True, ensure_ascii=False)
        if k in key:
            return [key[k]]
        for i in range(1, len(ops)):                       # 2개짜리 변형: 두 패치를 이어 붙인 것
            a = json.dumps(ops[:i], sort_keys=True, ensure_ascii=False)
            b = json.dumps(ops[i:], sort_keys=True, ensure_ascii=False)
            if a in key and b in key:
                return [key[a], key[b]]
        return []

    def applies(ops, base):
        if any((cid, base["design_id"]) in excluded for cid in ids_of(ops)):
            return False
        return B.default_applies(ops, base)
    return applies


# --- 추첨 기록 ----------------------------------------------------------------

def skip_reasons(new: list[B.Case], bases: dict, applies: B.Applies, excluded: set) -> dict:
    """질문마다 넘어간 횟수를 이유별로: 분할 칸 규칙 / 제외 목록 / 그 밖 (build_v2.draw와 같은 순서)."""
    out = {}
    for q in sorted(B.NEW_ALLOCATION):
        pool = sorted([c for c in new if not c.excluded and c.question == q], key=lambda c: c.id)
        order = random.Random(f"{B.DRAW_SEED}-{q}").sample(pool, len(pool))
        got, r = 0, {"split_rule": 0, "exclusion_list": 0, "other": 0}
        for c in order:
            if got == B.PER_QUESTION:
                break
            if B.compatible_bases(c, bases, applies):
                got += 1
            elif B.compatible_bases(c, bases, applies, split_rule=False):
                r["split_rule"] += 1
            elif all((c.id, n) in excluded for n in bases if bases[n]["design_type"] in B.placeable_types(c)):
                r["exclusion_list"] += 1
            else:
                r["other"] += 1
        out[q] = r
    return out


# --- 변형 ---------------------------------------------------------------------

def _code(rng: random.Random, used: set[str]) -> str:
    while True:
        c = "".join(rng.choice("0123456789ABCDEF") for _ in range(4))
        if c not in used:
            used.add(c)
            return c


def blind(d: dict, code: str, rng: random.Random) -> dict:
    """파일 이름 코드와 순서가 뜻을 갖지 않는 목록의 순서 섞기 (특징, 포함·제외 기준. 전처리는 단계 순서라 그대로)."""
    d = copy.deepcopy(d)
    d["design_id"] = f"design_{code}"
    rng.shuffle(d["features"])
    rng.shuffle(d["cohort"]["inclusion"])
    rng.shuffle(d["cohort"]["exclusion"])
    return d


def build_variants(layout: dict, cases: dict[str, B.Case], bases: dict, entry, seed: int,
                   avoid: set[str]) -> tuple[dict[str, dict], dict[str, dict]]:
    """→ ({파일 이름: 설계서}, {파일 이름: 정답표 칸}). 결함 22 + 깨끗한 8을 섞은 순서로 만든다."""
    rng = random.Random(seed)
    plans = [(v["base"], list(v["cases"])) for v in layout["defect"]] + [(b, []) for b in layout["clean"]]
    rng.shuffle(plans)
    used = set(avoid)
    variants, key = {}, {}
    for base, ids in plans:
        b = bases[base]
        t = b["design_type"]
        d = b
        for cid in ids:
            d = apply_ops(d, cases[cid].ops[t])
        code = _code(rng, used)
        fname = f"design_{code}.json"
        v = blind(d, code, rng)
        variants[fname] = v
        key[fname] = variant_entry(file_sha256(dumps(v)), base, t, [entry(cid, t) for cid in ids])
    return variants, key


def entry_maker(cases: dict[str, B.Case], cands: dict):
    """→ f(사례 id, 유형) = 정답표 결함 칸. 보류 사례는 기본값 (다르게 정하려면 사용자 승인), 공개는 PUBLIC_EXCEPTIONS."""
    with open(PUBLIC_CSV, newline="", encoding="utf-8") as f:
        pub = {r["id"]: r for r in csv.DictReader(f)}

    def make(cid: str, t: str) -> dict:
        c = cases[cid]
        row = cands[cid] if c.holdout else pub[cid]
        ex = {} if c.holdout else PUBLIC_EXCEPTIONS.get(cid, {})
        return defect_entry(cid, c.question, c.holdout, row["expected_verdict"], c.ops[t],
                            ex.get("support_targets"), ex.get("accept_questions"))
    return make


def write_list(key: dict) -> str:
    lines = ["# v2 변형 목록 (4b)", "",
             "변형 30개의 파일 SHA-256. 어느 변형에 무엇이 있는지는 `sealed/answer_key.enc`에만 있다.",
             "`experiment/grader.py`의 `injection_log_hashes(경로)`로 읽는다 (`tests/test_grader.py::test_verify_variants`).", "",
             "| 파일 | SHA-256 |", "|---|---|"]
    lines += [f"| designs/variants/{f} | `{key[f]['sha256']}` |" for f in sorted(key)]
    text = "\n".join(lines) + "\n"
    return text


def main() -> int:
    if ANSWER_KEY.exists():
        raise SystemExit(f"{ANSWER_KEY}가 이미 있다. 변형은 한 번만 만든다.")
    password = os.environ["SEAL_PASSWORD"]
    rec, cands, rec4b = open_sealed(password)
    excl_rows = rec4b["exclusions"]
    if exclusions_sha256(excl_rows) != json.loads(LOCK.read_text(encoding="utf-8"))["exclusions_4b_sha256"]:
        raise SystemExit("제외 목록 해시가 잠금과 다르다")
    excluded = {(e["case"], e["base"]) for e in excl_rows}
    sub = {c["id"]: c["substance"] for c in rec["cases"]}
    new = B.new_cases(rec, cands, lambda cid, t: sub[cid][t]["difference"])
    pub = B.public_cases()
    bases = B.load_clean()
    applies = make_applies(new + pub, excluded)

    drawn, log = B.draw(new, bases, applies)
    reasons = skip_reasons(new, bases, applies, excluded)
    chosen = pub + [c for c in new if c.id in drawn]
    layout = B.place(chosen, bases, applies)
    problems = B.check_layout(layout, chosen, bases, applies)
    if problems:
        raise SystemExit(f"배치 검사 실패: {problems}")

    by_id = {c.id: c for c in chosen}
    entry = entry_maker(by_id, cands)
    blind_seed = secrets.randbits(32)
    old = {p.stem.split("_")[1] for p in VARIANT_DIR.glob("design_*.json")}      # v1 이름은 다시 쓰지 않는다
    variants, vkey = build_variants(layout, by_id, bases, entry, blind_seed, old)

    key = {
        "version": VERSION,
        "created": "2026-10-06",
        "nonce": secrets.token_hex(16),
        "priority": [list(r) for r in PRIORITY],
        "draw": {"seed": B.DRAW_SEED, "date": "2026-10-06", "drawn": drawn, "skipped": log, "skipped_by_reason": reasons},
        "placement": {"seed": B.PLACE_SEED, "type_split": list(layout["type_split"]), "layout": layout},
        "blinding": {"seed": blind_seed},
        "exclusions_4b_sha256": rec4b["exclusions_sha256"],
        "base_sha256": {n: file_sha256((B.CLEAN_DIR / f"{n}.json").read_text(encoding="utf-8")) for n in bases},
        "variants": vkey,
    }
    key = json.loads(json.dumps(key, ensure_ascii=False))                       # 튜플 → 목록 (봉인 뒤 대조와 같게)
    bad = validate_key(key)
    if bad:
        raise SystemExit(f"정답표 형식 검사 실패: {bad}")
    blob = encrypt_bytes(json.dumps(key, ensure_ascii=False, indent=1).encode("utf-8"), password)
    assert json.loads(decrypt_bytes(blob, password)) == key

    for p in VARIANT_DIR.glob("design_*.json"):
        p.unlink()
    for fname, v in variants.items():
        (VARIANT_DIR / fname).write_text(dumps(v), encoding="utf-8")
    ANSWER_KEY.write_bytes(blob)
    LIST_DOC.write_text(write_list(vkey), encoding="utf-8")
    kinds = Counter((v["design_type"], len(v["defects"])) for v in vkey.values())
    print("variants", len(vkey), dict(sorted(kinds.items())))
    print("answer_key.enc", hashlib.sha256(blob).hexdigest())
    print("list", hashlib.sha256(LIST_DOC.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
