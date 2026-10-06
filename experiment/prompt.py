"""에이전트 지시문 (5단계에 고정). (가)/(나) 두 조건에 똑같이 쓴다.

지시문과 에이전트용 문서(형식 설명·데이터 설명서 사본, `tools/make_agent_docs.py`)가 바뀌면 해시가 달라져 멈춘다.
값은 docs/success_criteria_v2.md에도 적혀 있다. 6단계 실행기는 두 문서를 두 조건의 작업 폴더에 같은 이름으로 복사한다.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPT_FILE = Path(__file__).resolve().parent / "agent_prompt.md"
PROMPT_SHA256 = "d5824ec50fef2b3afb5c6e40c8e16d1c0edff81be9fdbac7e4d4d30c8406b4bd"
FORMAT_FILE = ROOT / "docs" / "agent" / "design_format.md"
DICTIONARY_FILE = ROOT / "docs" / "agent" / "data_dictionary.md"
AGENT_DOC_SHA256 = {
    "design_format.md": "c43fc1e1b90521d6d5267a5098872bbf179a6685e5f418d5a7c27f0da934ea41",
    "data_dictionary.md": "1b4e78b49fe358975af8d2af6383c39d28423eb5304d1948f6000ba1afcc04f6",
}


def _check(path: Path, want: str) -> bytes:
    b = path.read_bytes()
    got = hashlib.sha256(b).hexdigest()
    if got != want:
        raise RuntimeError(f"{path.name}가 고정본과 다르다 (sha256 {got}). 5단계 이후 바꾸지 않는다.")
    return b


def text() -> str:
    return _check(PROMPT_FILE, PROMPT_SHA256).decode("utf-8")


def agent_docs() -> dict[str, bytes]:
    """작업 폴더에 둘 문서 (이름 → 내용). 두 조건 같음."""
    return {p.name: _check(p, AGENT_DOC_SHA256[p.name]) for p in (FORMAT_FILE, DICTIONARY_FILE)}


def render(design_file: str, data_dir: str, format_file: str = "design_format.md",
           dictionary_file: str = "data_dictionary.md") -> str:
    """조건과 무관하게 파일 경로만 채운다."""
    return (text().replace("{{DESIGN_FILE}}", design_file).replace("{{DATA_DIR}}", data_dir)
            .replace("{{FORMAT_FILE}}", format_file).replace("{{DICTIONARY_FILE}}", dictionary_file))
