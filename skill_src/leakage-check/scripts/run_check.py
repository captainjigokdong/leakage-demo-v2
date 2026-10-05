#!/usr/bin/env python3
"""설계서 누수 점검 실행기.

사용:
  python3 run_check.py 설계서.json                          # 설계서만 점검 (결과 JSON은 ./checker.json, 있으면 checker_2.json …)
  python3 run_check.py 설계서.json --data data              # 데이터로 행 단위 재확인까지
  python3 run_check.py 설계서.json --data data --json checker.json   # 구조화된 결과 저장
  python3 run_check.py 설계서.json --data data --card       # 결정 카드(기술 통계만) 출력
  python3 run_check.py --rules                               # 규칙표 출력

종료 코드: 0 차단 없음 · 1 차단 있음 · 2 점검 불가(형식 오류, 꼬리표 오류, 데이터 단계를 못 돌림)

leakcheck 패키지 위치: 환경 변수 LEAKCHECK_HOME, 없으면 현재 폴더와 이 스크립트에서 위로 찾는다.
pandas를 불러오지 못하면 설계서 점검만 하고 데이터 단계는 "점검 불가"로 보고한다 (종료 코드 2).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

EXIT_TEXT = {0: "차단 없음", 1: "차단 있음", 2: "점검 불가 (위 메시지를 그대로 보고)"}


def _find_home() -> Path | None:
    env = os.environ.get("LEAKCHECK_HOME")
    if env:
        return Path(env)
    for start in (Path.cwd(), Path(__file__).resolve().parent):
        for p in (start, *start.parents):
            if (p / "leakcheck" / "__init__.py").exists():
                return p
    return None


def _done(code: int) -> int:
    print(f"\n종료 코드 {code} = {EXIT_TEXT[code]}")
    return code


def _write_new(path: Path, text: str) -> Path:
    """기존 파일을 덮어쓰지 않는다: path가 있으면 <이름>_2, _3 … 중 비어 있는 첫 이름에 새로 만든다."""
    n = 1
    while True:
        target = path if n == 1 else path.with_name(f"{path.stem}_{n}{path.suffix}")
        try:
            with open(target, "x", encoding="utf-8") as fh:
                fh.write(text)
            return target
        except FileExistsError:
            n += 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="설계서 누수 점검 (Q1~Q7)")
    ap.add_argument("design", type=Path, nargs="?")
    ap.add_argument("--data", type=Path, help="합성 EHR 폴더 (*.csv.gz)")
    ap.add_argument("--json", type=Path, default=Path("checker.json"),
                    help="결과 JSON 저장 경로 (기본: 실행한 폴더의 checker.json). 이미 있으면 덮어쓰지 않고 "
                         "checker_2.json, checker_3.json … 중 비어 있는 첫 이름에 저장한다")
    ap.add_argument("--card", action="store_true", help="결정 카드 출력 (--data 필요)")
    ap.add_argument("--rules", action="store_true", help="규칙표(rules.md와 같은 내용) 출력")
    args = ap.parse_args(argv)

    if args.rules:
        rules_md = Path(__file__).resolve().parent.parent / "rules.md"
        if not rules_md.exists():
            print(f"점검 불가: 규칙표 파일이 없다 ({rules_md})", file=sys.stderr)
            return _done(2)
        print(rules_md.read_text(encoding="utf-8"))
        return 0
    if args.design is None:
        ap.error("설계서 경로가 필요하다")

    home = _find_home()
    if home is None:
        print("점검 불가: leakcheck 패키지를 찾지 못했다. LEAKCHECK_HOME을 저장소 루트로 지정하라.", file=sys.stderr)
        return _done(2)
    sys.path.insert(0, str(home))

    try:
        from leakcheck.checks import run_checks
        from leakcheck.design import DesignError, load
    except ImportError as e:
        print(f"점검 불가: 점검기를 불러오지 못했다 ({e}).", file=sys.stderr)
        return _done(2)

    tables, data_error = None, None
    if args.data:
        try:
            import pandas  # noqa: F401
        except ImportError as e:
            data_error = f"pandas를 불러오지 못했다 ({e})"
        else:
            from leakcheck.data import DataError, load as load_tables
            try:
                tables = load_tables(args.data)
            except DataError as e:
                data_error = str(e)

    try:
        design = load(args.design)
        from leakcheck.tagging import TaggingError
    except ImportError:
        TaggingError = RuntimeError   # pandas 없음: 데이터 단계를 돌리지 않으므로 꼬리표 오류도 없다
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"점검 불가: {e}", file=sys.stderr)
        return _done(2)
    try:
        report = run_checks(design, tables, data_error)
    except (DesignError, TaggingError) as e:
        print(f"점검 불가: {e}", file=sys.stderr)
        return _done(2)

    print(report.to_text())
    import hashlib
    from datetime import datetime, timezone
    out = report.to_dict()
    out["checked"] = {
        "design_file": args.design.name, "design_path": str(args.design),
        "design_sha256": hashlib.sha256(args.design.read_bytes()).hexdigest(),
        "data_folder": str(args.data) if args.data else None,
        "time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    saved = _write_new(args.json, json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(f"\n결과 JSON(판정마다 kind 칸 포함, 점검한 설계서 {args.design.name} sha256 "
          f"{out['checked']['design_sha256'][:12]}): {saved}")

    if args.card:
        if tables is None:
            print("결정 카드에는 --data가 필요하다.", file=sys.stderr)
            return _done(2)
        if report.blocked:
            print("\n차단이 있어 결정 카드를 만들지 않는다. 설계를 먼저 고친다.")
        else:
            from leakcheck.lock import decision_card
            print("\n" + decision_card(design, tables).to_text())
    if data_error:
        return _done(2)
    return _done(1 if report.blocked else 0)


if __name__ == "__main__":
    raise SystemExit(main())
