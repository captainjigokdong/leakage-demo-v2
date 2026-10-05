"""점검기 규칙표(leakcheck/rules.py)를 사람이 읽는 표로 만든다 → skill_src/leakage-check/rules.md.

스킬 폴더 안에 두는 사본이다 (v2_plan.md 3.1의 1). 시험(tests/test_skill.py)이 파일이 이 함수의 출력과 같은지 확인한다.
rules.md에는 스킬 폴더 밖의 파일·위치를 적지 않는다.

실행: python -m tools.rules_md
"""
from __future__ import annotations

from pathlib import Path

from leakcheck import rules

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "skill_src" / "leakage-check" / "rules.md"
KIND = {"column": "같은 행의 시각 열", "row_anchor": "소속 입원의 기준 시각", "first_admit": "그 등록 번호의 첫 입원 시각",
        "linked_admit": "가리키는 입원의 입원 시각", "extraction": "자료 추출 시 (모든 tₚ 뒤)"}


def _when(a: rules.Avail) -> str:
    if a.kind == "column":
        s = f"`{a.column}`"
    elif a.kind == "row_anchor":
        s = "입원 시각" if a.column == "admit" else "퇴원 시각"
    else:
        s = KIND[a.kind]
    if a.offset_h:
        s += f" + {a.offset_h:g}h"
    if a.lag_from:
        s += " (" + ", ".join(f"`{c}`에서 지연 상한 {'없음' if v is None else f'{v:g}h'}" for c, v in a.lag_from.items()) + ")"
    return s


def render() -> str:
    L = []
    w = L.append
    w("# 규칙표 (점검기와 같은 내용)\n")
    w(f"규칙표 판 {rules.RULES_VERSION}. 점검기의 규칙표에서 자동으로 만든 사본이다. 이 표와 점검기 출력의 `rule` 칸 번호가 같다.\n")
    w("규칙은 \"값이 언제 알려지는가\"만 말한다. 쓸 수 있는지는 설계의 예측 시점 tₚ가 정한다.\n")
    w("- 1층 구조: 데이터의 열이 곧 확인 가능 시각이다")
    w("- 2층 맥락: 데이터 밖의 지식 (데이터 설명서에 적힌 지연 상한, 확인 강도를 좌우하는 층)")
    w("- 3층 불확실: 아무도 확실히 모른다. 보수적 기본값을 쓰고 \"가정\"으로 따로 출력한다\n")
    w("## 1. 테이블별 확인 가능 시각 (`T.<테이블>.<열>`)\n")
    w("열 규칙이 행 규칙과 같으면 \"행과 같음\"으로 적는다. 행 규칙은 개수 집계처럼 열을 정하지 않을 때 쓴다.\n")
    for name, r in rules.TABLES.items():
        link = {"admission_id": "입원 번호로", "patient_id": "등록 번호로", None: "전역 1행"}[r.entity_via]
        extra = []
        if r.admission_column:
            extra.append(f"입원 범위 열 `{r.admission_column}`")
        if r.admission_column and r.max_after_discharge_h is None:
            extra.append("퇴원 뒤 알려지는 시각의 상한 없음")
        elif r.admission_column and r.max_after_discharge_h:
            extra.append(f"퇴원 뒤 최대 {r.max_after_discharge_h:g}h에 알려짐")
        if r.versions:
            extra.append(f"수정 이력: 항목 `{r.versions[0]}`, 버전 `{r.versions[1]}` (as_of로 고름)")
        if r.time_columns:
            extra.append("시각 열 " + ", ".join(f"`{c}`({'날짜만' if k == 'date' else '시각'})" for c, k in r.time_columns.items()))
        w(f"### {name}\n")
        w(f"연결: {link}. " + "; ".join(extra) + "\n" if extra else f"연결: {link}.\n")
        row = r.row_available
        w(f"- 행 (`T.{name}`): {_when(row)} — {row.layer}층, {row.basis}")
        for c, a in r.column_available.items():
            if a == row:
                w(f"- `{c}`: 행과 같음")
            else:
                w(f"- `{c}` (`T.{name}.{c}`): {_when(a)} — {a.layer}층, {a.basis}")
        for c, f in r.derived.items():
            w(f"- `{c}`는 계산한 열: {f}")
        w("")
    w("## 2. 조정할 수 있는 값 (2층, 데이터 설명서의 값)\n")
    for n in ("LAB_REPORT_LAG_MAX_H", "VITAL_ENTRY_LAG_MAX_H", "OUTPATIENT_LAB_LAG_MAX_H",
              "DX_CODING_MAX_AFTER_DISCHARGE_H", "PROC_CODING_MAX_AFTER_DISCHARGE_H", "PROBLEM_MAX_AFTER_DISCHARGE_H",
              "DEATH_RECORD_LAG_MAX_H", "EPISODE_GAP_MAX_H"):
        w(f"- `{n}` = {getattr(rules, n):g}h")
    w(f"- `Q7_RATIO_THRESHOLD` = {rules.Q7_RATIO_THRESHOLD:g} (층 사이 비가 이 값 이상이면 Q7 경고. 실험 전 고정값)")
    w(f"- `DATE_ONLY_DEFAULT` = {rules.DATE_ONLY_DEFAULT} (3층: 날짜만 있는 값의 그날 시각)\n")
    w("## 3. 분할 (Q2)\n")
    w(f"- 위계: {' < '.join(rules.SPLIT_LEVELS)}")
    w(f"- 열 이름 → 수준: " + ", ".join(f"`{k}` → {v}" for k, v in rules.SPLIT_ALIASES.items()))
    w(f"- 개체 단위: {rules.ENTITY_LEVEL} ({rules.ENTITY_BASIS})")
    w(f"- 형식의 기본 독립 단위: {rules.DEFAULT_SPLIT_UNIT}")
    w(f"- 결측이 있는 묶음: {', '.join(sorted(rules.NULLABLE_SPLIT_LEVELS))} (결측 행은 fallback_key로, 없으면 등록 번호로 묶인다)")
    w(f"- 행 단위 분할 방법: {', '.join(sorted(rules.ROW_LEVEL_METHODS))}")
    w(f"- 시간 순 분할(temporal): {rules.TEMPORAL_RULE}\n")
    w("## 4. 적합 범위 (Q3)\n")
    w(f"- 허용 적합 범위: {', '.join(sorted(rules.FIT_SCOPES_OK))}")
    w(f"- 재표본 추출을 적용해도 되는 데이터: {', '.join(sorted(rules.RESAMPLE_APPLY_OK))}")
    w(f"- 뒤 행의 값을 쓰는 결측 대치: {', '.join(sorted(rules.FUTURE_FILL_METHODS))}\n")
    w("## 5. 결과 (Q4, Q7)\n")
    w("### 결과 정의별 대리 기록 (`O.proxy.*`, Q4 경고)\n")
    w("결과와 같은 입원 범위의 특징이 아래 기록과 일치하면 경고한다. 설계서 `outcome.proxies`에 적은 것도 더한다.\n")
    for d, ps in rules.OUTCOME_PROXIES.items():
        if not ps:
            w(f"- {d}: 규칙표 목록 없음")
        for p in ps:
            flt = ", ".join(f"{k} ∈ {v}" for k, v in p["filter"].items())
            w(f"- {d} · `{p['id']}`: `{p['source']}` {flt} — {p['basis']}")
    w("- diagnosis_code: 결과와 같은 코드의 `problem_list` 항목 (`O.proxy.same_code_problem`)\n")
    w("### 확인 강도를 좌우하는 층 (`O.strata.*`, Q7 경고)\n")
    for src, sts in rules.ASCERTAINMENT_STRATA.items():
        for st in sts:
            mem = ", ".join(f"`{t}.{c}`" for t, c in st.members)
            w(f"- 결과 테이블 {src} · `{st.id}` {st.name} ({mem}) — {st.basis}")
    for st in rules.SITE_SCOPE_STRATA:
        mem = ", ".join(f"`{t}.{c}`" for t, c in st.members)
        w(f"- 결과 확인 범위(병원)가 데이터({', '.join(rules.ALL_SITES)})보다 좁을 때 · `{st.id}` {st.name} ({mem}) — {st.basis}")
    w("\n`by_stratum`에는 열 이름(`unit`), `테이블.열`, 또는 그 열로 만든 특징 이름을 적을 수 있다.\n")
    w("### 연구 기간 중 바뀐 것 (`O.change.*`, Q7 경고: outcome.history가 비어 있으면)\n")
    for ch in rules.OUTCOME_CHANGES:
        w(f"- `{ch['id']}`: {ch['what']}, {ch['date']} (결과 테이블 {ch['source']})")
    w("\n## 6. 가정 (3층, 판정이 아니라 참고)\n")
    for aid, (text, param) in rules.ASSUMPTIONS.items():
        w(f"- `{aid}`: {text}" + (f" (조정: `{param}`)" if param else ""))
    w("\n## 7. 판정 규칙 번호\n")
    for k, v in rules.PRINCIPLES.items():
        w(f"- `{k}`: {v}")
    return "\n".join(L) + "\n"


def main() -> int:
    OUT.write_text(render(), encoding="utf-8")
    print(f"썼다: {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
