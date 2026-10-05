"""4단계 4a: 패치를 깨끗한 설계서에 적용했을 때 서술 문장이 바뀐 칸과 어긋나는지 (점검기는 쓰지 않는다).

패치가 바꾼 칸마다, 바뀌기 전 값 중 패치 뒤에 없어진 것(문자열·목록의 원소, 테이블 이름 제외)이 패치를 적용한 설계서의 **다른** 서술 칸
(description, notes, basis, method 문장 등)에 남아 있으면 "모순 후보"로 낸다. 기계적 대조라 뜻으로만 어긋나는 문장
(예: "폴드마다 다시 맞춘다"와 fit_scope=all)은 잡지 못하므로, 사람이 사례마다 함께 읽는다 (docs/clean_review_v2.md).

4b의 봉인 확인(후보 30개 × 깨끗한 설계서 8개)에서도 같은 함수를 쓴다 (`hits`).

실행: python -m tools.clean_v2_textcheck
"""
from __future__ import annotations

import json
from pathlib import Path

from designs.inject import apply_ops

ROOT = Path(__file__).resolve().parent.parent
CLEAN = ROOT / "designs" / "clean_v2"
TEXT_KEYS = {"description", "notes", "basis", "method", "question", "definition_source", "deployment_start",
             "setting", "change", "handled", "agg"}
from synth.tables_v2 import TABLES_V2

TABLES = set(TABLES_V2)
SKIP_TOKENS = {"value", "last", "first", "train", "test", "all", "any", "count", "tp", "admit", "index_admission"}


def _get(d, path: str):
    from designs.inject import _walk
    parent, key = _walk(d, path)
    return parent[key] if isinstance(parent, dict) and key in parent else None


def _leaves(v) -> list[str]:
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        return [x for e in v for x in _leaves(e)]
    if isinstance(v, dict):
        return [x for e in v.values() for x in _leaves(e)]
    return []


def _texts(d, path: str = "") -> list[tuple[str, str]]:
    out = []
    if isinstance(d, dict):
        for k, v in d.items():
            p = f"{path}.{k}" if path else k
            if k in TEXT_KEYS and isinstance(v, str):
                out.append((p, v))
            elif k == "name" or not isinstance(v, (dict, list)):
                continue
            else:
                out += _texts(v, p)
    elif isinstance(d, list):
        for i, x in enumerate(d):
            key = f"{path}[{x['name']}]" if isinstance(x, dict) and "name" in x else f"{path}[{i}]"
            out += _texts(x, key)
    return out


def hits(base: dict, ops: list[dict]) -> list[dict]:
    """패치 적용 뒤 남는 모순 후보: 바뀌기 전 값 또는 바뀐 칸 이름이 다른 서술 칸에 남아 있음."""
    patched = apply_ops(base, ops)
    out = []
    for op in ops:
        path = op["path"]
        tokens = set()
        if op["op"] in ("set", "remove"):
            old = set(_leaves(_get(base, path)))
            new = set(_leaves(op.get("value"))) if op["op"] == "set" else set()
            tokens |= {t for t in old - new if len(t) >= 3 and t not in SKIP_TOKENS and t not in TABLES
                       and " " not in t}
        changed_prefix = path.split("[")[0] if op["op"] in ("append", "insert_after", "insert_before") else path
        for tp, text in _texts(patched):
            if tp.startswith(changed_prefix) and op["op"] in ("set", "remove"):
                continue                       # 바뀐 칸 자신 (패치가 바꾼 서술 포함)
            for t in sorted(tokens):
                if t in text:
                    out.append({"op_path": path, "token": t, "text_path": tp, "text": text[:160]})
    return out


def main() -> int:
    from designs.patches_v1_cases import V1_CASE_PATCHES
    from tests.test_injectability_v2 import V1_ROWS
    from designs.inject import TYPE_KO
    bases = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(CLEAN.glob("*.json"))}
    n = bad = 0
    for cid, ops in V1_CASE_PATCHES.items():
        for name, d in bases.items():
            if d["design_type"] not in TYPE_KO[V1_ROWS[cid]["design_types"]]:
                continue
            n += 1
            h = hits(d, ops)
            if h:
                bad += 1
                for x in h:
                    print(cid, name, x["op_path"], "|", x["token"], "→", x["text_path"], "|", x["text"])
    print(f"조합 {n}, 모순 후보가 남는 조합 {bad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
