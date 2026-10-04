"""설계서 형식 설명(docs/design_format_v2.md)이 schema.json의 모든 칸을 같은 형식으로 다루는지 (v2 2단계)."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "designs" / "schema.json"
DOC = ROOT / "docs" / "design_format_v2.md"

TAG = re.compile(r"^(K L[123](\.[1-4])?|P [1-4]\.[1-9]|P\+AI (참여자·데이터 출처|예측변수|결과|분석)"
                 r"|Albu|Kaufman|Suissa|관리)$")
ROW = re.compile(r"^\| `([^`]+)` \| (.+?) \| (.+?) \|$")


def _walk(node: dict, prefix: str, out: list[str]) -> None:
    for key, sub in node.get("properties", {}).items():
        path = f"{prefix}.{key}" if prefix else key
        out.append(path)
        if "$ref" in sub:
            continue
        if sub.get("type") == "array" and "properties" in sub.get("items", {}):
            _walk(sub["items"], path + "[]", out)
        else:
            _walk(sub, path, out)


def schema_paths() -> set[str]:
    """$ref는 펼치지 않는다. 공통 정의는 '정의 이름.칸'으로 한 번만 센다."""
    s = json.loads(SCHEMA.read_text(encoding="utf-8"))
    out: list[str] = []
    _walk(s, "", out)
    for name, d in s["$defs"].items():
        if "properties" in d:
            _walk(d, name, out)
        elif "$ref" not in d:
            out.append(name)
    return set(out)


def doc_rows() -> dict[str, tuple[str, str]]:
    rows = {}
    for line in DOC.read_text(encoding="utf-8").splitlines():
        m = ROW.match(line)
        if m and not m.group(1).startswith(("K L", "P ", "P+AI", "Albu", "관리")):
            assert m.group(1) not in rows, f"설명서에 같은 칸이 두 번: {m.group(1)}"
            rows[m.group(1)] = (m.group(2).strip(), m.group(3).strip())
    return rows


def test_every_schema_field_documented():
    missing = schema_paths() - set(doc_rows())
    assert not missing, f"설명서에 없는 칸: {sorted(missing)}"


def test_no_documented_field_missing_from_schema():
    extra = set(doc_rows()) - schema_paths()
    assert not extra, f"schema에 없는 칸: {sorted(extra)}"


def test_every_row_has_description_and_valid_basis():
    for path, (desc, basis) in doc_rows().items():
        assert desc, path
        tags = [t.strip() for t in basis.split(";")]
        bad = [t for t in tags if not TAG.match(t)]
        assert not bad, f"{path}: 근거 꼬리표 형식이 아님 {bad}"
        assert len(tags) == len(set(tags)), f"{path}: 근거 중복"
