"""5단계 잠금 표 채우기: docs/success_criteria_v2.md의 고정 파일 해시 (한 번만, 사용자 승인 뒤 다시 실행하지 않는다).

    python -m tools.lock_criteria_v2
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "success_criteria_v2.md"
LOCKED = ["experiment/agent_prompt.md", "experiment/prompt.py", "experiment/grader.py", "experiment/scoring_rules.md",
          "docs/agent/design_format.md", "docs/agent/data_dictionary.md", "docs/analysis_plan_v2.md"]


def main() -> int:
    from experiment import prompt
    s = DOC.read_text(encoding="utf-8")
    table = "\n".join(f"| `{f}` | `{hashlib.sha256((ROOT / f).read_bytes()).hexdigest()}` |" for f in LOCKED)
    s = re.sub(r"(\| 파일 \| SHA-256 \|\n\|---\|---\|\n)(?:.*\n?)*", lambda m: m.group(1) + table + "\n", s)
    s = re.sub(r"`(\{\{PROMPT_SHA256\}\}|[0-9a-f]{64})`(?= *\n\n\| 파일)", f"`{prompt.PROMPT_SHA256}`", s)
    DOC.write_text(s, encoding="utf-8")
    print(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
