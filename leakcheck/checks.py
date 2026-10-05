"""Q1~Q7 점검. 사례별 금지 목록이 아니라 세 가지 비교 원리로 판정한다.

1. 시각 비교   (Q1, Q5)  규칙표가 말하는 확인 가능 시각의 상한 ≤ 기준 시점(tₚ)인가
2. 단위 비교   (Q2)      분할 묶음이 선언된 독립 단위(그리고 개체 단위 = 사람) 이상인가
3. 범위 비교   (Q3, Q4)  데이터에서 추정한 것의 적합 범위 ⊆ 학습 부분인가 /
                          특징의 행·시간 구간이 결과를 정한 행·결과 창과 겹치는가

Q6는 기록만, Q7은 경고만 한다. 판정은 차단 · 경고 · 통과 · 기록, 그리고 따로
점검 불가(규칙 없음·출처 불명)와 가정(3층 규칙을 쓴 곳)을 낸다.
판정마다 "어느 규칙(rule), 어느 값(basis)"을 한 줄로 붙인다.

설계서만으로 판정하고(기호 시각), 데이터를 주면 같은 원리를 행 단위로 다시 확인해
근거(행 수)를 덧붙인다. 설계서 점검은 pandas 없이 돈다 (데이터 단계만 pandas를 쓴다).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from leakcheck import design as dz
from leakcheck import rules, splitting, timeline
from leakcheck.design import UNKNOWN
from leakcheck.timeline import INF, fmt_h

BLOCK, WARN, PASS, RECORD = "차단", "경고", "통과", "기록"
UNABLE, ASSUME = "점검 불가", "가정"
# 제출 형식의 kind (2026-10-04 사용자 결정 D9). 통과·기록에는 kind가 없다
KIND = {BLOCK: "문제", WARN: "문제", UNABLE: "점검 불가", ASSUME: "가정"}
QUESTIONS = ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"]
Q_NAMES = {"Q1": "가용 시점", "Q2": "독립 단위", "Q3": "적합 범위", "Q4": "결과 출처",
           "Q5": "선택 시점", "Q6": "다중 시도", "Q7": "결과 확인 균질성", "Q1~Q3": "출처 불명", "데이터": "데이터"}
TOL = 1e-9
CMP_OPS = {"==", "!=", ">=", ">", "<=", "<"}


@dataclass
class Finding:
    question: str
    verdict: str
    target: str
    reason: str
    rule: str = ""
    basis: str = ""

    def to_dict(self) -> dict:
        d = {"question": self.question, "verdict": self.verdict, "target": self.target,
             "reason": self.reason, "rule": self.rule, "basis": self.basis}
        if self.verdict in KIND:
            d["kind"] = KIND[self.verdict]
        return d


@dataclass
class Report:
    design_id: str
    design_type: str
    data_checked: bool
    findings: list[Finding] = field(default_factory=list)
    assumptions: list[Finding] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(f.verdict == BLOCK for f in self.findings)

    def problems(self) -> list[Finding]:
        return [f for f in self.findings if f.verdict in (BLOCK, WARN)]

    def unable(self) -> list[Finding]:
        return [f for f in self.findings if f.verdict == UNABLE]

    def summary(self) -> dict:
        out = {v: 0 for v in (BLOCK, WARN, PASS, RECORD, UNABLE)}
        for f in self.findings:
            out[f.verdict] += 1
        out[ASSUME] = len(self.assumptions)
        return out

    def to_dict(self) -> dict:
        return {"design_id": self.design_id, "design_type": self.design_type,
                "rules_version": rules.RULES_VERSION, "data_checked": self.data_checked,
                "blocked": self.blocked, "summary": self.summary(),
                "findings": [f.to_dict() for f in self.findings],
                "assumptions": [f.to_dict() for f in self.assumptions]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_text(self) -> str:
        s = self.summary()
        head = (f"설계 {self.design_id} ({self.design_type}) — 차단 {s[BLOCK]} · 경고 {s[WARN]} · "
                f"점검 불가 {s[UNABLE]} · 가정 {s[ASSUME]} · 통과 {s[PASS]} · 기록 {s[RECORD]}"
                f"{' (데이터 확인 포함)' if self.data_checked else ' (설계서만 확인)'}")
        lines = [head, "결론: " + ("차단 — 설계를 고치기 전에는 모델링을 진행하지 않는다" if self.blocked
                                  else "차단 없음" + (" — 경고는 사람이 확인" if s[WARN] else ""))]

        def block(title, items):
            if items:
                lines.append(f"\n[{title}]")
                for f in items:
                    lines.append(f"[{f.verdict}] {f.question} {Q_NAMES.get(f.question, '')} · {f.target}")
                    if f.basis:
                        lines.append(f"    근거: {f.basis}")
                    lines.append(f"    설명: {f.reason}")
        order = {BLOCK: 0, WARN: 1}
        block("차단·경고 (제출 kind: 문제)", sorted(self.problems(), key=lambda f: (order[f.verdict], f.question)))
        block("점검 불가 (제출 kind: 점검 불가)", self.unable())
        block("가정 — 판정 아님, 참고 (제출 kind: 가정)", self.assumptions)
        block("기록 (제출하지 않음)", [f for f in self.findings if f.verdict == RECORD])
        block("통과 (제출하지 않음)", [f for f in self.findings if f.verdict == PASS])
        return "\n".join(lines)


# ---------------------------------------------------------------- 기호 시각

@dataclass
class Sym:
    ub: float           # 확인 가능 시각 상한 (tₚ 대비 시간)
    why: str            # 값: 어떤 값 때문에
    rule: str           # 규칙 번호
    basis: str          # 규칙 내용
    assumes: list = field(default_factory=list)   # [(가정 번호, 대상 설명)]


def _scope_bounds(scope: str, fr: timeline.Frame) -> tuple[float, float]:
    """재료 입원의 (입원 시각 상한, 퇴원 시각 상한), tₚ 대비 시간."""
    if scope == "index_admission":
        return fr.hi("admit"), fr.hi("discharge")
    if scope == "prior_admissions":  # 이번 입원 전에 퇴원한 입원
        return fr.hi("admit"), fr.hi("admit")
    if scope in ("next_admission", "patient_history", "patient"):
        return INF, INF
    raise ValueError(f"알 수 없는 범위: {scope}")


def _lag(a: rules.Avail, table: str, col: str) -> float | None:
    """같은 행의 시각 열 col → 확인 가능 시각까지의 지연 상한. 0 = 같음, None = 상한 없음."""
    if a.kind == "column":
        if col == a.column:
            return a.offset_h
        return a.lag_from.get(col, None) if col in a.lag_from else None
    if a.kind == "row_anchor" and table == "admissions":
        return a.offset_h if col == {"admit": "admit_time", "discharge": "discharge_time"}[a.column] else None
    return None


def avail_upper(spec: dict, fr: timeline.Frame, specs: dict | None = None) -> Sym:
    """명세가 고르는 행들의 확인 가능 시각 상한(tₚ 대비 시간)과 그 근거."""
    if spec.get("derive"):
        names = spec["derive"].get("of", [])
        if not names or any(n not in (specs or {}) for n in names):
            raise rules.RuleMissing(f"파생 특징의 재료 {names} 중 설계서에 없는 것이 있다 ({UNKNOWN})")
        parts = [(n, avail_upper(specs[n], fr, specs)) for n in names]
        n, worst = max(parts, key=lambda p: p[1].ub)
        return Sym(worst.ub, f"파생 특징: 재료 {', '.join(names)} 중 가장 늦은 {n} → {worst.why}",
                   worst.rule, worst.basis, [a for _, p in parts for a in p.assumes])
    table = spec["source"]
    rule = rules.table_rule(table)
    col = spec.get("column")
    a = rules.availability(table, col)
    rid = rules.rule_id(table, col)
    scope = spec["scope"]
    what = f"{table}.{col or rule.value_column or '행'}"
    basis = f"{a.layer}층: {a.basis}"
    assumes = []
    hk = spec.get("history_key", "patient_id")

    if hk == "person_id" and scope in ("patient", "prior_admissions", "next_admission", "patient_history") \
            and table not in ("patients", "person_links", "extract_info"):
        pa = rules.availability("person_links", "person_id")
        return Sym(INF, f"{what}: history_key=person_id — 등록 번호를 사람으로 묶는 연결은 자료 추출 때 만들어진다 "
                        f"→ 확인 가능 시각 상한 {fmt_h(INF)}", "T.person_links.person_id", f"{pa.layer}층: {pa.basis}")
    if a.kind == "extraction":
        return Sym(INF, f"{what}: 자료 추출 시 → 확인 가능 시각 상한 {fmt_h(INF)}", rid, basis)
    if a.kind == "first_admit":
        return Sym(fr.hi("admit"), f"{what}: 그 등록 번호의 첫 입원 시각 ≤ 인덱스 입원 시각 "
                                   f"→ 확인 가능 시각 상한 {fmt_h(fr.hi('admit'))}", rid, basis)
    if a.kind == "linked_admit":
        return Sym(INF, f"{what}: 예약 입원이 이루어질 때(뒤의 입원) → 확인 가능 시각 상한 {fmt_h(INF)}", rid, basis)

    if rule.admission_column is None and scope in ("index_admission", "prior_admissions", "next_admission"):
        raise rules.RuleMissing(f"'{table}'에는 입원 범위({scope})가 없다")
    adm_hi, dis_hi = _scope_bounds(scope, fr) if rule.admission_column else (INF, INF)
    if a.kind == "row_anchor":
        ub = (adm_hi if a.column == "admit" else dis_hi) + a.offset_h
        why = f"소속 입원의 {'입원' if a.column == 'admit' else '퇴원'} 시각(범위 {scope})"
    else:
        extra = rule.max_after_discharge_h
        ub = dis_hi + extra if extra is not None else INF
        why = (f"범위 {scope}의 행은 언제 알려질지 상한이 없음" if ub == INF
               else f"범위 {scope}의 퇴원 시각 + {extra:g}h")

    w = spec.get("window")
    end = timeline.parse(w.get("end", "inf")) if w else None
    if end is not None and end.anchor != "inf":
        tc = spec.get("time_column") or rules.default_time_column(table)
        if tc is None:
            raise rules.RuleMissing(f"'{table}'에는 창을 적용할 시각 열이 없다")
        if tc not in rule.time_columns:
            raise rules.RuleMissing(f"'{table}.{tc}'은 규칙표의 시각 열이 아니다")
        e_hi = fr.hi(end)
        date_note = ""
        if rule.time_columns[tc] == "date":
            how = spec.get("date_compare")
            if how is None:
                how = rules.DATE_ONLY_DEFAULT
                assumes.append(("A.date_only", f"{tc} (날짜만)"))
            if how in ("day_start", "same_date_ok"):
                e_hi += 24
                date_note = f", 날짜 비교 {how} → 창 끝 날짜의 끝까지"
            else:
                date_note = ", 날짜를 그날 23:59로 봄"
        lag = _lag(a, table, tc)
        if lag is None:
            wub = INF
            wwhy = (f"창이 {tc} 기준인데 {tc}에서 확인 가능 시각({a.column or a.kind})까지 지연 상한이 없음{date_note}"
                    if a.kind != "static" else why)
        else:
            wub = e_hi + lag
            wwhy = (f"창 끝 {end} ({tc} 기준{date_note})" + (f" + {tc}→{a.column} 지연 상한 {lag:g}h" if lag else ""))
        if wub <= ub:
            ub, why = wub, wwhy
        elif ub == INF:
            why = wwhy
    if rule.versions:
        as_of = spec.get("as_of")
        if as_of == "latest":
            ub, why = INF, "as_of=latest: 최종본은 tₚ 뒤에 수정된 버전일 수 있음"
        elif as_of == "tp" and ub > 0:
            ub, why = 0.0, "as_of=tp: tₚ 시점에 있던 버전만"
    return Sym(ub, f"{what}: {why} → 확인 가능 시각 상한 {fmt_h(ub)}", rid, basis, assumes)


def _time_compare(spec: dict) -> tuple[str, timeline.TimeExpr] | None:
    """기준이 '사건 시각 열 ○ 시각 표현'(예: discharge_time > tp)이면 (열, 시각)."""
    col, val = spec.get("column"), spec.get("value")
    if spec.get("op") not in CMP_OPS or not isinstance(val, str) or col is None:
        return None
    if rules.table_rule(spec["source"]).time_columns.get(col) != "datetime":
        return None
    try:
        e = timeline.parse(val)
    except ValueError:
        return None
    return (col, e) if e.anchor not in ("-inf", "inf") else None


def criterion_upper(spec: dict, fr: timeline.Frame, specs=None) -> tuple[Sym, str]:
    """포함·제외 기준의 확인 가능 시각 상한과 꼬리표."""
    s = avail_upper(spec, fr, specs)
    tc = _time_compare(spec)
    if tc:
        col, e = tc
        a = rules.availability(spec["source"], col)
        lag = _lag(a, spec["source"], col)
        if lag is not None and fr.hi(e) + lag < s.ub:
            return Sym(fr.hi(e) + lag, f"{spec['source']}.{col} {spec['op']} {e}: 그 시각까지 사건이 있었는지는 "
                                       f"{e}{f' + 지연 {lag:g}h' if lag else ''}에 알 수 있다 → 확인 가능 시각 상한 "
                                       f"{fmt_h(fr.hi(e) + lag)}",
                       "C.time_compare", "2층: 사건 시각을 시각 표현과 비교하는 기준은 '그 시각까지 일어났는가'만 쓴다",
                       s.assumes), "시각 비교"
    a = rules.availability(spec["source"], spec.get("column")) if spec.get("source") else None
    tag = "정적" if a is not None and a.kind == "first_admit" else None
    return s, tag


def _span(spec: dict, fr: timeline.Frame) -> tuple[float, float] | None:
    """행들이 놓인 시간 구간 (lo, hi], tₚ 대비. 정적 정보는 None."""
    table = spec.get("source")
    if table is None:
        return None
    rule = rules.table_rule(table)
    scope = spec["scope"]
    if table in ("patients", "person_links", "extract_info"):
        return None
    if rule.admission_column is None or scope in ("patient", "patient_history"):
        lo, hi = -INF, INF
    elif scope == "index_admission":
        extra = rule.max_after_discharge_h
        lo, hi = fr.lo("admit"), fr.hi("discharge") + (extra if extra is not None else INF)
    elif scope == "prior_admissions":
        lo, hi = -INF, fr.hi("admit")
    elif scope == "next_admission":
        lo, hi = fr.lo("discharge"), INF
    else:
        lo, hi = -INF, INF
    w = spec.get("window")
    if w:
        lo = max(lo, fr.lo(w.get("start", "-inf")))
        hi = min(hi, fr.hi(w.get("end", "inf")))
    return lo, hi


def _overlap(a, b) -> bool:
    return a is not None and b is not None and max(a[0], b[0]) < min(a[1], b[1]) - TOL


def _scopes_overlap(a: str, b: str) -> bool:
    if "patient" in (a, b):
        return a == b
    return a == b or "patient_history" in (a, b)


def _filters_compatible(f1: dict, f2: dict) -> bool:
    for col in set(f1) & set(f2):
        v1, v2 = [str(x) for x in f1[col]], [str(x) for x in f2[col]]
        if col in rules.CODE_COLUMNS:
            if not any(x.startswith(y) or y.startswith(x) for x in v1 for y in v2):
                return False
        elif not set(v1) & set(v2):
            return False
    return True


A_QUESTION = {"A.date_only": "Q1", "A.family_missing": "Q2", "A.outside_sites": "Q7", "A.episode_last": "Q5",
              "A.post_tp_exclusion": "Q5"}


def _assumption(aid: str, target: str, extra: str = "") -> Finding:
    text, param = rules.ASSUMPTIONS[aid]
    return Finding(A_QUESTION[aid], ASSUME, target, text + (f" ({extra})" if extra else ""), aid,
                   f"3층 가정 {aid}" + (f" · 조정: rules.{param}" if param else " · 형식으로 피할 수 없음"))


# ---------------------------------------------------------------- 데이터 단계 준비

@dataclass
class DataCtx:
    tagged: dict
    base: object       # 포함·제외 적용 전 예측 행 (DataFrame)
    cohort: object     # 적용 후


def _compare(s, op, v):
    import pandas as pd
    if op == "in":
        return s.isin(v)
    if op == "not_in":
        return ~s.isin(v)
    return {"==": s.__eq__, "!=": s.__ne__, ">=": s.__ge__, ">": s.__gt__, "<=": s.__le__, "<": s.__lt__}[op](v)


def _criterion_value(spec, rows):
    import pandas as pd
    v = spec["value"]
    tc = _time_compare(spec)
    if tc:
        return timeline.resolve(tc[1], rows).to_numpy()
    col = spec.get("column")
    if isinstance(v, str) and col and rules.table_rule(spec["source"]).time_columns.get(col) == "datetime":
        return pd.Timestamp(v)
    return v


def _criterion_mask(tagged, spec, rows, specs=None):
    import numpy as np
    from leakcheck.features import make_feature
    r = make_feature(tagged, spec, rows, specs)
    val = r.frame.set_index("index_id")["value"].reindex(rows["index_id"]).reset_index(drop=True)
    res = _compare(val, spec["op"], _criterion_value(spec, rows.reset_index(drop=True)))
    return np.asarray(res.fillna(False), dtype=bool)


def _criterion_avail(tagged, spec, rows, specs=None):
    """기준의 확인 가능 시각 (예측 행마다). 시각 비교면 min(값의 확인 시각, 비교 시각 + 지연)."""
    import pandas as pd
    from leakcheck.features import make_feature
    r = make_feature(tagged, spec, rows, specs)
    at = r.frame.set_index("index_id")["available_time"].reindex(rows["index_id"])
    tc = _time_compare(spec)
    if tc:
        lag = _lag(rules.availability(spec["source"], tc[0]), spec["source"], tc[0])
        if lag is not None:
            when = timeline.resolve(tc[1], rows) + pd.Timedelta(hours=lag)
            at = pd.concat([at.reset_index(drop=True), when.reset_index(drop=True)], axis=1).min(axis=1)
            at.index = rows["index_id"]
    return at


def prepare_data(d: dict, tables: dict) -> DataCtx:
    import numpy as np
    from leakcheck.features import build_index
    from leakcheck.tagging import tag_tables
    tagged = tag_tables(tables, d["split_unit"] if d["split_unit"] in rules.SPLIT_ALIASES else "patient")
    base = build_index(d, tagged)
    specs = {f["name"]: f for f in d["features"]}
    keep = np.ones(len(base), dtype=bool)
    for part, sign in (("inclusion", True), ("exclusion", False)):
        for spec in d["cohort"][part]:
            if not dz.provenance_known(spec):
                continue
            try:
                m = _criterion_mask(tagged, spec, base, specs)
            except rules.RuleMissing:
                continue  # 적용하지 않고 Q5에서 "점검 불가"로 보고한다
            keep &= m if sign else ~m
    return DataCtx(tagged, base, base[keep].reset_index(drop=True))


# ---------------------------------------------------------------- Q1, Q5: 시각 비교

def _time_check(q: str, part: str, spec: dict, d: dict, ctx: DataCtx | None, ref: str, specs: dict
                ) -> tuple[list[Finding], list[Finding]]:
    target = f"{part}.{spec['name']}"
    worst, sym, label, tag = -INF, None, "", None
    for fr in dz.frames(d):
        s, t = criterion_upper(spec, fr, specs) if q == "Q5" else (avail_upper(spec, fr, specs), None)
        gap = s.ub - fr.lo(ref)
        if sym is None or gap > worst:
            worst, sym, label, tag = gap, s, fr.label(), t
    data_note, n_leak = "", 0
    if ctx is not None:
        rows = ctx.base if q == "Q5" else ctx.cohort
        if q == "Q5":
            at = _criterion_avail(ctx.tagged, spec, rows, specs)
        else:
            from leakcheck.features import make_feature
            at = make_feature(ctx.tagged, spec, rows, specs).frame.set_index("index_id")["available_time"] \
                .reindex(rows["index_id"])
        ref_t = timeline.resolve(ref, rows).set_axis(rows["index_id"])
        n_leak = int((at > ref_t).fillna(False).sum())
        data_note = f" 데이터: {n_leak:,}/{len(rows):,} 예측 행에서 확인 가능 시각 > {ref}."
    what = "특징" if q == "Q1" else "포함·제외 기준"
    if tag is None and q == "Q5":
        tag = f"{ref}까지 알려짐" if worst <= TOL else f"{ref} 뒤에 알려짐"
    tag_txt = f"[꼬리표: {tag}] " if q == "Q5" else ""
    assumes = [_assumption(aid, target, x) for aid, x in sym.assumes]
    basis = f"규칙 {sym.rule}({sym.basis}) · 값: {sym.why}"
    if worst > TOL:
        return [Finding(q, BLOCK, target, f"{tag_txt}{what}의 확인 가능 시각이 기준 시점({ref}) 뒤일 수 있다 "
                                          f"(tₚ = {label}).{data_note}", sym.rule, basis)], assumes
    if n_leak > 0:
        return [Finding(q, BLOCK, target, f"{tag_txt}규칙표로는 {ref} 이전이지만 데이터에서 늦게 알려진 행이 있다 "
                                          f"(규칙표 가정과 데이터 불일치).{data_note}", sym.rule, basis)], assumes
    return [Finding(q, PASS, target, f"{tag_txt}{what}의 확인 가능 시각 ≤ {ref}.{data_note}", sym.rule, basis)], assumes


def check_q1_other(d: dict) -> list[Finding]:
    out = []
    for step in d["preprocessing"]:
        m = str(step.get("method", "")).lower()
        if m in rules.FUTURE_FILL_METHODS:
            out.append(Finding("Q1", BLOCK, f"preprocessing.{step['name']}",
                               f"결측을 {m}로 채우면 같은 묶음의 뒤(나중) 행 값이 앞 행에 들어간다. tₚ에 알 수 없는 값이다.",
                               "F.future_fill", f"규칙 F.future_fill(뒤 행의 값을 쓰는 대치: "
                                                f"{', '.join(sorted(rules.FUTURE_FILL_METHODS))}) · 값: method={m}"))
    iu = d.get("intended_use", {})
    method = d["split"].get("method", "group_holdout")
    if iu.get("purpose") == "prospective_deployment" and method != "temporal":
        out.append(Finding("Q1", WARN, "split.method",
                           "전향 사용이 목적인데 학습·평가를 시간 순으로 나누지 않았다. 평가 부분보다 뒤의 기간이 학습에 "
                           "들어가 사용 시점에는 없는 정보(미래의 진료 관행·측정법)로 학습할 수 있다. "
                           "split.method=temporal(묶음 키 유지)로 쓸 수 있다.",
                           "S.temporal_deploy", f"규칙 S.temporal_deploy(Kapoor L3.1: 미래를 예측하는 모형은 평가 "
                                                f"기간이 학습 기간 뒤여야 함) · 값: intended_use.purpose="
                                                f"{iu.get('purpose')}, split.method={method}"))
    return out


# ---------------------------------------------------------------- Q2: 단위 비교

def _key_specs(d: dict) -> list[tuple[str, dict]]:
    out = [("split.key", d["split"])]
    t = d.get("model", {}).get("tuning", {})
    if isinstance(t, dict) and t.get("cv_key"):
        out.append(("model.tuning.cv_key", {"key": t["cv_key"], "fallback_key": t.get("fallback_key"),
                                            "method": "group_kfold"}))
    return out


def _window_len_h(w: dict) -> float | None:
    s, e = timeline.parse(w.get("start", "-inf")), timeline.parse(w.get("end", "inf"))
    if s.anchor == e.anchor and s.anchor not in ("-inf", "inf"):
        return e.offset_h - s.offset_h
    return None


def check_q2(d: dict, ctx: DataCtx | None) -> tuple[list[Finding], list[Finding]]:
    out, assumes = [], []
    L = rules.SPLIT_LEVELS
    E = rules.ENTITY_LEVEL
    unit = rules.split_level(d["split_unit"])
    lv_basis = f"위계 {' < '.join(rules.SPLIT_LEVELS)}"
    if L[unit] < L[E]:
        out.append(Finding("Q2", BLOCK, "split_unit",
                           f"독립 단위 '{unit}'이 개체 단위({E})보다 작다. 같은 사람의 행은 함께 움직여야 한다.",
                           "S.entity", f"규칙 S.entity(2층: {rules.ENTITY_BASIS}) · 값: split_unit={d['split_unit']} → "
                                       f"{unit} < {E}"))
    for target, ks in _key_specs(d):
        lv = splitting.key_level(ks)
        shown = ks["key"] + (f" (방법 {ks['method']}: 행 단위)" if ks.get("method") in rules.ROW_LEVEL_METHODS else "")
        note = ""
        if ctx is not None and target == "split.key":
            labels = splitting.assign(ctx.cohort, ks)
            n, tot = splitting.crossing(ctx.cohort, labels, unit)
            note = f" 데이터: {unit} {n:,}/{tot:,}개가 둘 이상의 배정에 나뉨."
        if L[lv] < L[unit]:
            out.append(Finding("Q2", BLOCK, target,
                               f"분할 묶음 {shown}({lv})이 선언된 독립 단위 {unit}보다 작아 같은 {unit}의 행이 "
                               f"학습·평가에 함께 들어갈 수 있다.{note}",
                               "S.levels", f"규칙 S.levels({lv_basis}) · 값: {target}={ks['key']} → {lv} < {unit}"))
        elif L[lv] < L[E]:
            out.append(Finding("Q2", BLOCK, target,
                               f"분할 묶음 {shown}({lv})이 개체 단위({E})보다 작아 같은 사람의 행이 나뉠 수 있다.{note}",
                               "S.entity", f"규칙 S.entity(2층: {rules.ENTITY_BASIS}) · 값: {target}={ks['key']} → "
                                           f"{lv} < {E}"))
        fb = splitting.fallback_level(ks)
        if fb is not None:
            fb_target = target.replace("cv_key", "fallback_key").replace("split.key", "split.fallback_key")
            given = ks.get("fallback_key")
            if L[fb] < L[E]:
                out.append(Finding("Q2", BLOCK, fb_target if given else target,
                                   f"{ks['key']}가 비어 있는 행은 {given or '등록 번호(대체 키 없음)'}({fb})로 묶이는데, "
                                   f"이는 개체 단위({E})보다 작아 같은 사람이 학습·평가에 나뉠 수 있다.",
                                   "S.fallback", f"규칙 S.fallback(2층: {ks['key']}는 결측이 있다 — 설명서 "
                                                 f"patients.family_id 결측 약 80%) · 값: fallback_key={given} → {fb} < {E}"))
            assumes.append(_assumption("A.family_missing", target, f"대체 키 {given or '없음 → 등록 번호'}"))
    split = d["split"]
    if split.get("method") == "temporal":
        wl = _window_len_h(d["outcome"]["window"])
        gap = timeline.parse_duration_h(split.get("gap"))
        if wl is None or gap is None or gap + TOL < wl:
            out.append(Finding("Q2", WARN, "split.gap",
                               f"시간 순 분할의 간격(gap={split.get('gap')})이 결과 창 길이"
                               f"({'알 수 없음' if wl is None else f'{wl:g}h'})보다 짧거나 정해지지 않아, "
                               f"학습 부분 끝의 결과 창이 평가 기간과 겹칠 수 있다.",
                               "S.temporal", f"규칙 S.temporal({rules.TEMPORAL_RULE}) · 값: gap={split.get('gap')}, "
                                             f"결과 창 {d['outcome']['window']}"))
    dd = d["cohort"].get("deduplication", {})
    if dd.get("when") in ("within_split", "none"):
        out.append(Finding("Q2", WARN, "cohort.deduplication.when",
                           f"중복 레코드를 분할 전에 지우지 않으면(when={dd.get('when')}) 같은 기록이 학습·평가에 함께 "
                           f"들어갈 수 있다. before_split으로 쓸 수 있다.",
                           "S.dedup", f"규칙 S.dedup(Kapoor L1.4 중복) · 값: deduplication.when={dd.get('when')}"))
    if ctx is not None:
        labels = splitting.assign(ctx.cohort, split)
        cross = [(lv, *splitting.crossing(ctx.cohort, labels, lv))
                 for lv in [x for x in L if L["admission"] <= L[x] <= max(L[unit], L[E])]]
        cross = [(lv, n, tot) for lv, n, tot in cross if n]
        if cross:
            detail = ", ".join(f"{lv} {n:,}/{tot:,}" for lv, n, tot in cross)
            out.append(Finding("Q2", BLOCK, "split.key",
                               f"데이터에서 학습·평가에 나뉜 묶음: {detail} (선언 단위 {unit}, 개체 단위 {E} 이하).",
                               "S.levels", f"규칙 S.levels({lv_basis}) · 값: 데이터 배정에서 {detail}"))
        for lv in [x for x in L if L[x] > max(L[unit], L[E])]:
            n, tot = splitting.crossing(ctx.cohort, labels, lv)
            if n:
                out.append(Finding("Q2", WARN, "split_unit",
                                   f"독립 단위를 {unit}로 선언했는데 데이터에서 같은 {lv} {n:,}/{tot:,}개가 학습·평가에 "
                                   f"나뉜다. {lv} 구성원이 위험을 공유하면 서로 독립이 아니므로 단위를 {lv}로 할지 사람이 확인.",
                                   "S.levels", f"규칙 S.levels({lv_basis}) · 값: 데이터 배정에서 {lv} {n:,}개가 나뉨"))
    return out, assumes


# ---------------------------------------------------------------- Q3: 적합 범위

def _find_key(obj, key: str, path: str = ""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if k == key:
                yield p, v
            yield from _find_key(v, key, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _find_key(v, key, f"{path}[{i}]")


def _uses_cv(d: dict) -> bool:
    m = d.get("model", {})
    t = m.get("tuning", {}) if isinstance(m.get("tuning"), dict) else {}
    return bool(t.get("cv_key")) or "kfold" in str(t.get("method", "")).lower() or any(
        isinstance(m.get(k), dict) and m[k].get("fit_scope") == "train_fold"
        for k in ("selection", "early_stopping", "threshold", "calibration"))


def check_q3(d: dict) -> list[Finding]:
    out = []
    ok = rules.FIT_SCOPES_OK
    fs_basis = f"규칙 F.fit_scope(추정은 학습 부분에서만: {', '.join(sorted(ok))})"
    cv = _uses_cv(d)
    for step in d["preprocessing"]:
        t = f"preprocessing.{step['name']}"
        stateless = step.get("stateless", False)
        fs = step.get("fit_scope")
        if not stateless:
            if fs is None:
                out.append(Finding("Q3", BLOCK, t, f"데이터에서 값을 추정하는 단계({step['kind']})인데 적합 범위가 "
                                                   f"적혀 있지 않아 학습 부분에서만 추정했는지 확인할 수 없다.",
                                   "F.fit_scope", f"{fs_basis} · 값: fit_scope 없음, stateless=false"))
            elif fs not in ok:
                out.append(Finding("Q3", BLOCK, t, f"{step['kind']} 단계를 '{fs}' 범위에서 적합한다. 평가 부분의 정보가 "
                                                   f"학습에 들어간다." + (" 결과값도 쓴다." if step.get("uses_outcome") else ""),
                                   "F.fit_scope", f"{fs_basis} · 값: fit_scope={fs}"))
            elif fs == "train" and cv:
                out.append(Finding("Q3", WARN, t, f"조율을 교차검증으로 하는데 {step['kind']} 단계를 학습 부분 전체(train)에서 "
                                                  f"한 번 적합한다. 조율의 검증 폴드 정보가 적합에 들어간다 (평가 부분과는 무관). "
                                                  f"fit_scope=train_fold로 쓸 수 있다.",
                                   "F.fold_refit", f"규칙 F.fold_refit(교차검증 조율이면 폴드마다 다시 적합) · 값: "
                                                   f"fit_scope=train, 조율 교차검증"))
            if step.get("before_split"):
                out.append(Finding("Q3", BLOCK, t, f"추정하는 단계({step['kind']})를 분할 전에 했다. 평가 부분이 적합에 들어간다.",
                                   "F.before_split", f"규칙 F.before_split · 값: before_split=true, stateless=false"))
        if str(step.get("kind", "")).lower() == "resample" and step.get("applies_to") and \
                step["applies_to"] not in rules.RESAMPLE_APPLY_OK:
            out.append(Finding("Q3", BLOCK, t, f"재표본 추출을 '{step['applies_to']}'에 적용한다. 평가 부분을 재표본 추출하면 "
                                               f"평가가 실제 분포를 반영하지 않는다.",
                               "F.resample", f"규칙 F.resample(재표본 추출은 학습 부분에만) · 값: applies_to={step['applies_to']}"))
    rest = {k: v for k, v in d.items() if k != "preprocessing"}
    for path, fs in _find_key(rest, "fit_scope"):
        if fs not in ok:
            out.append(Finding("Q3", BLOCK, path.rsplit(".fit_scope", 1)[0],
                               f"데이터에서 추정하는 값을 '{fs}' 범위에서 적합한다. 평가 부분의 정보가 들어간다.",
                               "F.fit_scope", f"{fs_basis} · 값: {path}={fs}"))
    ev = d.get("evaluation", {})
    if ev.get("data") in ("train", "all"):
        out.append(Finding("Q3", BLOCK, "evaluation.data", f"성능을 '{ev['data']}'에서 계산한다. 학습에 쓴 데이터로 평가한다.",
                           "F.eval_data", f"규칙 F.eval_data(평가는 학습에 쓰지 않은 부분에서) · 값: evaluation.data={ev['data']}"))
    if ev.get("data") == "validation":
        used = [k for k in ("selection", "early_stopping", "threshold", "calibration")
                if isinstance(d.get("model", {}).get(k), dict) and d["model"][k].get("fit_scope") == "validation"]
        if used:
            out.append(Finding("Q3", BLOCK, "evaluation.data",
                               f"검증 부분으로 {', '.join(used)}을 정하고 같은 검증 부분으로 성능을 계산한다.",
                               "F.eval_data", f"규칙 F.eval_data · 값: evaluation.data=validation, "
                                              f"{', '.join(f'model.{k}.fit_scope=validation' for k in used)}"))
    if isinstance(ev.get("test_set_uses"), int) and ev["test_set_uses"] > 1:
        out.append(Finding("Q3", WARN, "evaluation.test_set_uses",
                           f"평가 부분으로 성능을 {ev['test_set_uses']}번 봤다. 평가 부분이 모형 선택에 쓰였을 수 있다.",
                           "F.test_reuse", f"규칙 F.test_reuse(Kapoor L1.1) · 값: test_set_uses={ev['test_set_uses']}"))
    return out


# ---------------------------------------------------------------- Q4: 결과 출처

def _proxies(o: dict) -> list[dict]:
    out = [dict(p, id=p.get("id", "O.proxy")) for p in rules.OUTCOME_PROXIES.get(o["definition"], [])]
    if o["definition"] == "diagnosis_code" and o["filter"].get("icd_code"):
        out.append({"id": "O.proxy.same_code_problem", "source": "problem_list",
                    "filter": {"icd_code": o["filter"]["icd_code"]}, "basis": "결과와 같은 코드의 문제 목록 항목"})
    out += [dict(p, id="D.proxies") for p in o["proxies"]]
    return out


def check_q4(d: dict, feats: list[dict]) -> list[Finding]:
    out = []
    o = d["outcome"]
    proxies = _proxies(o)
    fr_list = dz.frames(d)
    for f in feats:
        if f.get("derive"):
            continue   # 재료 특징에서 따로 판정한다
        t = f"features.{f['name']}"
        same_rows = (f["source"] == o["source"] and _filters_compatible(f["filter"], o["filter"])
                     and _scopes_overlap(f["scope"], o["scope"]))
        hit = None
        for fr in fr_list:
            fs, os_ = _span(f, fr), _span(o, fr)
            ow = f"({o['window'].get('start', '-inf')}, {o['window'].get('end', 'inf')}]"
            if same_rows and _overlap(fs, os_):
                hit = (f"결과를 정한 행({o['source']}, 범위 {o['scope']}, 결과 창 {ow})과 같은 행을 특징이 쓴다 "
                       f"(tₚ = {fr.label()}).", "O.same_rows",
                       f"규칙 O.same_rows(같은 테이블·겹치는 필터·범위·시간 구간) · 값: 특징 구간 "
                       f"({fmt_h(fs[0])}, {fmt_h(fs[1])}] ∩ 결과 구간 ({fmt_h(os_[0])}, {fmt_h(os_[1])}]")
                break
            if f.get("window") and _overlap(fs, os_):
                hit = (f"특징의 창 ({f['window'].get('start', '-inf')}, {f['window'].get('end', 'inf')}]이 결과 창 {ow}과 "
                       f"겹친다 (결과 창 재사용, tₚ = {fr.label()}).", "O.window_reuse",
                       f"규칙 O.window_reuse(특징 창이 결과 창과 겹침) · 값: 특징 구간 ({fmt_h(fs[0])}, {fmt_h(fs[1])}] ∩ "
                       f"결과 구간 ({fmt_h(os_[0])}, {fmt_h(os_[1])}]")
                break
        if hit:
            out.append(Finding("Q4", BLOCK, t, hit[0], hit[1], hit[2]))
            continue
        for p in proxies:
            if (f["source"] == p["source"] and _filters_compatible(f["filter"], p.get("filter", {}))
                    and _scopes_overlap(f["scope"], o["scope"])):
                flt = ", ".join(f"{k}∈{v}" for k, v in p.get("filter", {}).items())
                out.append(Finding("Q4", WARN, t,
                                   f"결과({o['name']})의 대리 기록 목록과 일치: {p['source']} {flt}. 결과를 정하는 과정이 "
                                   f"남긴 기록일 수 있어 사람이 확인.", p["id"],
                                   f"규칙 {p['id']}(2층: {p.get('basis', '설계서 목록')}) · 값: 특징 {f['source']} "
                                   f"{f['filter'] or '필터 없음'}, 범위 {f['scope']}"))
                break
    if o["ascertainment"].get("blind_to_predictors") is False:
        out.append(Finding("Q4", WARN, "outcome.ascertainment.blind_to_predictors",
                           "결과를 예측변수 정보를 알고 정했다. 결과 판정에 예측변수가 섞였을 수 있다.",
                           "O.blind", "규칙 O.blind(PROBAST 3.5) · 값: blind_to_predictors=false"))
    return out


# ---------------------------------------------------------------- Q5: 표본·추적 처리 (기준 외)

def check_q5_other(d: dict) -> tuple[list[Finding], list[Finding]]:
    out, assumes = [], []
    c, o = d["cohort"], d["outcome"]
    sm = c.get("sampling", {})
    by_outcome = sm.get("uses_outcome") or sm.get("method") in ("case_control", "outcome_enriched")
    if by_outcome and sm.get("applies_to", "both") in ("evaluation", "both"):
        out.append(Finding("Q5", BLOCK, "cohort.sampling",
                           f"결과를 보고 표본을 뽑았고(method={sm.get('method')}, uses_outcome={sm.get('uses_outcome')}) "
                           f"평가 데이터에도 적용했다(applies_to={sm.get('applies_to', '없음 → both로 봄')}). tₚ 뒤 정보로 "
                           f"평가 표본을 골랐다.", "C.sampling",
                           f"규칙 C.sampling(결과 기준 표본 추출은 개발 데이터에만) · 값: method={sm.get('method')}, "
                           f"applies_to={sm.get('applies_to')}"))
    rpu = c.get("rows_per_unit", {})
    if rpu.get("choose") == "last":
        unit = rpu.get("unit")
        if unit in ("patient", "person") or (unit == "admission" and len(d["tp"]["offsets_h"]) > 1):
            out.append(Finding("Q5", BLOCK, "cohort.rows_per_unit",
                               f"{unit}마다 마지막 행만 쓴다. 마지막인지 알려면 그 뒤에 행이 없음을 알아야 한다 (tₚ 뒤 정보). "
                               f"choose=all 또는 first로 쓸 수 있다.", "C.rows_last",
                               f"규칙 C.rows_last(마지막을 고르려면 뒤의 행이 없음을 알아야 함) · 값: unit={unit}, choose=last"))
        elif unit == "episode":
            assumes.append(_assumption("A.episode_last", "cohort.rows_per_unit"))
    cen = o.get("censoring", {})
    if cen.get("death") == "exclude":
        out.append(Finding("Q5", BLOCK, "outcome.censoring.death",
                           "결과 창 안에서 사망한 행을 뺀다. tₚ 뒤의 사건으로 표본을 고른다. composite_outcome 또는 "
                           "competing_risk로 쓸 수 있다.", "C.post_tp_exclusion",
                           "규칙 C.post_tp_exclusion(tₚ 뒤 사건으로 행을 빼면 선택 시점 위반) · 값: censoring.death=exclude"))
    if cen.get("lost_to_followup") == "exclude":
        assumes.append(_assumption("A.post_tp_exclusion", "outcome.censoring.lost_to_followup"))
    if d.get("analysis", {}).get("missing_data", {}).get("outcome_missing") == "exclude":
        assumes.append(_assumption("A.post_tp_exclusion", "analysis.missing_data.outcome_missing"))
    if o.get("pending_at_tp") == "exclude_row":
        rule = rules.table_rule(o["source"])
        tc = o.get("time_column") or rules.default_time_column(o["source"])
        a = rule.row_available
        pending = a.kind == "column" and tc != a.column and tc in a.lag_from
        if pending:
            out.append(Finding("Q5", BLOCK, "outcome.pending_at_tp",
                               f"tₚ 전에 생겼지만 tₚ 뒤에 알려진 결과 사건({o['source']}.{tc} ≤ tₚ < {a.column})이 있는 행을 "
                               f"뺀다. tₚ 뒤 정보로 표본을 고른다. ignore 또는 count_as_outcome으로 쓸 수 있다.",
                               "C.pending", f"규칙 C.pending({rules.rule_id(o['source'])}: {a.basis}) · 값: "
                                            f"pending_at_tp=exclude_row, 결과 시각 열 {tc}"))
    return out, assumes


# ---------------------------------------------------------------- Q6, Q7

def check_q6(d: dict) -> list[Finding]:
    a = d.get("attempts")
    out = []
    if not a:
        out.append(Finding("Q6", RECORD, "attempts", "시도 횟수가 적혀 있지 않다. 설계·모델을 몇 번 시도했는지 기록할 것."))
    else:
        out.append(Finding("Q6", RECORD, "attempts",
                           f"설계 {a.get('n_designs_tried', '?')}개, 모델 {a.get('n_models_tried', '?')}개 시도, "
                           f"보정: {a.get('correction', '미기재')}."))
    if d["outcome"].get("prespecified") is False:
        out.append(Finding("Q6", RECORD, "outcome.prespecified", "결과 정의를 분석 전에 정하지 않았다 (사후 정의)."))
    return out


def _restricted(d: dict, members) -> bool:
    cols = {c for _, c in members}
    tables = {t for t, _ in members}
    for spec in d["cohort"]["inclusion"]:
        if spec.get("source") in tables and spec.get("column") in cols and (
                spec["op"] == "==" or (spec["op"] == "in" and len(spec["value"]) == 1)):
            return True
    return False


def _resolve_strata(d: dict, names) -> set[tuple[str, str]]:
    """by_stratum·subgroups의 이름 → (테이블, 열). 특징 이름이면 그 특징의 원본 열."""
    feats = {f["name"]: f for f in d["features"]}
    out = set()
    for n in names:
        if n in feats and feats[n].get("source"):
            f = feats[n]
            out.add((f["source"], f.get("column") or rules.table_rule(f["source"]).value_column))
        elif "." in n:
            out.add(tuple(n.split(".", 1)))
        else:
            out |= {(t, n) for t, r in rules.TABLES.items() if n in r.column_available}
    return out


def _window_can_pass_extraction(d: dict) -> bool:
    """결과 창이 자료 추출 종료를 넘을 수 있는가. 창 끝이 tₚ 이전이거나, 이번 입원 범위에서 창 끝이 퇴원 시각 이전이면
    넘을 수 없다 (설명서: 퇴원이 자료 추출 종료 뒤인 입원은 데이터에 없다)."""
    o = d["outcome"]
    end = timeline.parse(o["window"].get("end", "inf"))
    if end.anchor == "inf":
        return False
    if end.anchor == "discharge" and end.offset_h <= 0 and o["scope"] == "index_admission":
        return False
    return any(fr.hi(end) > TOL for fr in dz.frames(d))


def _end_of_data(d: dict, ctx: DataCtx | None) -> list[Finding]:
    o = d["outcome"]
    val = o.get("censoring", {}).get("end_of_data")
    if val in ("exclude_incomplete", "survival_model") or not _window_can_pass_extraction(d):
        return []
    note = ""
    if ctx is not None and "extract_info" in ctx.tagged:
        end_t = ctx.tagged["extract_info"]["extraction_end_time"].iloc[0]
        we = timeline.resolve(o["window"]["end"], ctx.cohort)
        n = int((we > end_t).sum())
        note = f" 데이터: {n:,}/{len(ctx.cohort):,} 예측 행의 결과 창이 자료 추출 종료({end_t})를 넘는다."
    return [Finding("Q7", WARN, "outcome.censoring.end_of_data",
                    f"결과 창 끝({o['window']['end']})이 자료 추출 종료를 넘을 수 있는데 그런 행의 처리가 "
                    f"{val or '없음'}이다. 종료 뒤의 사건·보고는 데이터에 없어 연구 끝 무렵 행은 결과를 덜 확인한다. "
                    f"exclude_incomplete 또는 survival_model로 쓸 수 있다.{note}",
                    "O.end_of_data", f"규칙 O.end_of_data(설명서: 자료 추출 종료 뒤의 사건·보고는 행이 없다) · 값: "
                                     f"end_of_data={val}, 결과 창 끝 {o['window']['end']}")]


def _beyond_index(o: dict) -> bool:
    return o["scope"] in ("patient_history", "next_admission") or o["definition"] == "next_admission"


def check_q7(d: dict, ctx: DataCtx | None) -> tuple[list[Finding], list[Finding]]:
    o = d["outcome"]
    rule = rules.table_rule(o["source"])
    asc = o["ascertainment"]
    handled = _resolve_strata(d, asc.get("by_stratum", []))
    out, assumes = [], []
    tgt = "outcome.ascertainment.by_stratum"
    if rule.measurement:
        rates = _measurement_rates(d, ctx) if ctx is not None else None
        for st in rules.ASCERTAINMENT_STRATA.get(o["source"], ()):
            if set(st.members) & handled or _restricted(d, st.members):
                continue
            mem = ", ".join(f"{t}.{c}" for t, c in st.members)
            if rates is None:
                out.append(Finding("Q7", WARN, tgt,
                                   f"결과가 측정({o['source']})으로 정해지는데 확인 강도가 다를 수 있는 층 '{st.name}'({mem})을 "
                                   f"층별로 다루지 않는다. 데이터 없이 측정 빈도 비를 확인할 수 없어 사람이 확인.",
                                   st.id, f"규칙 {st.id}(2층: {st.basis}) · 값: by_stratum={asc.get('by_stratum', [])}"))
                continue
            for (t, c), by in rates.items():
                if (t, c) not in st.members or len(by) < 2:
                    continue
                ratio = by.max() / by.min() if by.min() > 0 else INF
                if ratio >= rules.Q7_RATIO_THRESHOLD:
                    detail = ", ".join(f"{k} {v:.2f}" for k, v in by.items())
                    out.append(Finding("Q7", WARN, tgt,
                                       f"결과 측정 빈도가 '{st.name}'({t}.{c}) 층마다 다르다: {detail}. 자주 측정하는 층에서 "
                                       f"결과가 더 많이 확인된다. 층별로 다루는지 사람이 확인.", st.id,
                                       f"규칙 {st.id}(2층: {st.basis}) · 값: 비 {ratio:.1f} ≥ {rules.Q7_RATIO_THRESHOLD:g}"))
                    break
    if _beyond_index(o):
        assumes.append(_assumption("A.outside_sites", "outcome.ascertainment.scope.sites"))
        sites = asc.get("scope", {}).get("sites")
        data_sites = d.get("data_source", {}).get("sites") or list(rules.ALL_SITES)
        if sites and set(sites) < set(data_sites):
            miss = _site_miss(d, ctx, sites) if ctx is not None else None
            for st in rules.SITE_SCOPE_STRATA:
                if set(st.members) & handled or _restricted(d, st.members):
                    continue
                if miss is None:
                    out.append(Finding("Q7", WARN, "outcome.ascertainment.scope.sites",
                                       f"결과를 {sites} 병원에서만 찾는데 데이터에는 {data_sites}가 있다. 범위 밖에서 생긴 결과를 "
                                       f"놓치는 정도가 '{st.name}' 층마다 다를 수 있는데 층별로 다루지 않는다.", st.id,
                                       f"규칙 {st.id}(2층: {st.basis}) · 값: scope.sites={sites} ⊂ {data_sites}, "
                                       f"by_stratum={asc.get('by_stratum', [])}"))
                elif len(miss) >= 2:
                    ratio = miss.max() / miss.min() if miss.min() > 0 else (INF if miss.max() > 0 else 1.0)
                    if ratio >= rules.Q7_RATIO_THRESHOLD:
                        detail = ", ".join(f"{k} {v:.3f}" for k, v in miss.items())
                        out.append(Finding("Q7", WARN, "outcome.ascertainment.scope.sites",
                                           f"결과를 {sites} 병원에서만 찾아 놓치는 비율이 '{st.name}' 층마다 다르다: {detail}.",
                                           st.id, f"규칙 {st.id}(2층: {st.basis}) · 값: 놓치는 비율의 비 "
                                                  f"{ratio:.1f} ≥ {rules.Q7_RATIO_THRESHOLD:g}"))
        if o.get("match_key", "patient_id") != "person_id":
            out.append(Finding("Q7", WARN, "outcome.match_key",
                               f"결과를 같은 등록 번호({o.get('match_key', 'patient_id')})에서만 찾는다. 같은 사람의 다른 "
                               f"등록 번호에서 생긴 결과를 놓친다. match_key=person_id로 쓸 수 있다.", "O.match_key",
                               f"규칙 O.match_key(2층: {rules.ENTITY_BASIS}) · 값: match_key={o.get('match_key', '없음')}"))
    out += _end_of_data(d, ctx)
    period = d.get("data_source", {}).get("study_period", {})
    for ch in rules.OUTCOME_CHANGES:
        if ch["source"] != o["source"] or not _filters_compatible(o["filter"], ch["filter"]):
            continue
        if period.get("start", "0000") <= ch["date"] <= period.get("end", "9999") and not o.get("history"):
            out.append(Finding("Q7", WARN, "outcome.history",
                               f"연구 기간 중 {ch['what']}가 바뀌었는데({ch['date']}) 결과의 변경 이력(outcome.history)이 "
                               f"비어 있다. 기간마다 결과를 다르게 확인했을 수 있다.", ch["id"],
                               f"규칙 {ch['id']}(2층: 설명서) · 값: outcome.history 없음, 연구 기간 {period or '전체'}"))
    cen = o.get("censoring", {})
    if d.get("data_source", {}).get("death_source") == "in_hospital_only" and cen.get("death") == "composite_outcome":
        if any(fr.hi(o["window"].get("end", "inf")) > fr.lo("discharge") + TOL for fr in dz.frames(d)):
            out.append(Finding("Q7", WARN, "data_source.death_source",
                               "사망을 결과에 넣는데 원내 사망 기록만 쓴다. 결과 창 안에 퇴원한 행은 원외 사망을 놓친다. "
                               "death_source=linked_registry로 쓸 수 있다.", "O.death_source",
                               "규칙 O.death_source(설명서 deaths: 원외 사망은 퇴원 1~365일 뒤, 사망 연계로만 기록) · 값: "
                               "death_source=in_hospital_only, censoring.death=composite_outcome"))
    return out, assumes


def _stratum_values(d: dict, ctx: DataCtx, t: str, c: str, rows):
    """데이터 단계: 예측 행마다 층 (테이블, 열)의 값."""
    import pandas as pd
    from leakcheck.features import make_feature
    if t == "admissions" and c in rows:
        return rows[c]
    if t == "transfers" and c == "unit":
        spec = {"name": "_unit_at_tp", "source": "transfers", "column": "unit", "scope": "index_admission",
                "time_column": "in_time", "window": {"end": "tp"}, "agg": "last", "filter": {}}
        v = make_feature(ctx.tagged, spec, rows).frame.set_index("index_id")["value"]
        return pd.Series(v.reindex(rows["index_id"]).to_numpy(), index=rows.index)
    if t == "admission_info" and t in ctx.tagged:
        return rows["admission_id"].map(ctx.tagged[t].set_index("admission_id")[c])
    if t == "patients":
        return rows["patient_id"].map(ctx.tagged[t].set_index("patient_id")[c])
    return None


def _measurement_rates(d: dict, ctx: DataCtx) -> dict:
    """층마다 결과 측정 빈도 (결과 창이 정해져 있으면 창 안 측정 수/시간, 아니면 입원 하루당)."""
    import numpy as np
    import pandas as pd
    from leakcheck.features import _apply_filter
    o = d["outcome"]
    rows = ctx.cohort
    meas = _apply_filter(ctx.tagged[o["source"]], o["filter"])
    tc = o.get("time_column") or rules.default_time_column(o["source"])
    wl = _window_len_h(o["window"])
    if wl and wl > 0:
        m = rows[["index_id", "admission_id"]].merge(meas[["_admission_id", tc]], left_on="admission_id",
                                                     right_on="_admission_id")
        ir = rows.set_index("index_id")
        s = timeline.resolve(o["window"].get("start", "-inf"), ir).reindex(m["index_id"]).to_numpy()
        e = timeline.resolve(o["window"].get("end", "inf"), ir).reindex(m["index_id"]).to_numpy()
        tt = m[tc].to_numpy()
        n = m[(tt > s) & (tt <= e)].groupby("index_id").size().reindex(rows["index_id"], fill_value=0)
        rate = pd.Series(n.to_numpy() / wl, index=rows.index)
    else:
        n = meas.groupby("_admission_id").size().reindex(rows["admission_id"], fill_value=0).to_numpy()
        los_d = (rows["discharge_time"] - rows["admit_time"]).dt.total_seconds().to_numpy() / 86400
        rate = pd.Series(n / np.maximum(los_d, 1e-9), index=rows.index)
    out = {}
    cand = list(dict.fromkeys([m for st in rules.ASCERTAINMENT_STRATA.get(o["source"], ()) for m in st.members]
                              + rules.ASCERTAINMENT_CANDIDATES))
    for t, c in cand:
        g = _stratum_values(d, ctx, t, c, rows)
        if g is None:
            continue
        by = rate.groupby(g.to_numpy()).mean()
        out[(t, c)] = by
    return out


def _site_miss(d: dict, ctx: DataCtx, sites):
    """층마다: 전체 병원으로 찾은 결과 중 확인 범위 병원만으로는 놓치는 예측 행의 비율."""
    import pandas as pd
    from leakcheck import outcomes
    rows = ctx.cohort
    y_all = outcomes.label(d, ctx.tagged, rows).reindex(rows["index_id"]).to_numpy()
    info = ctx.tagged.get("admission_info")
    if info is None:
        return None
    keep = set(info.loc[info["site"].isin(sites), "admission_id"])
    tg = dict(ctx.tagged)
    tg["admissions"] = tg["admissions"][tg["admissions"]["admission_id"].isin(keep)]
    y_in = outcomes.label(d, tg, rows).reindex(rows["index_id"]).to_numpy()
    miss = pd.Series(y_all & ~y_in, index=rows.index)
    st = rules.SITE_SCOPE_STRATA[0]
    t, c = st.members[0]
    g = _stratum_values(d, ctx, t, c, rows)
    return miss.groupby(g.to_numpy()).mean()


# ---------------------------------------------------------------- 실행

def run_checks(design: dict, tables: dict | None = None, data_error: str | None = None) -> Report:
    """설계서 점검. tables를 주면 데이터로 다시 확인한다. data_error: 데이터 단계를 못 돌린 이유."""
    d = dz.normalize(design)
    ctx = prepare_data(d, tables) if tables is not None else None
    findings: list[Finding] = []
    assumes: list[Finding] = []
    if data_error:
        findings.append(Finding("데이터", UNABLE, "data", f"데이터 단계를 돌리지 못했다: {data_error}. "
                                                         f"아래 판정은 설계서만 확인한 것이다.", "R.data", ""))

    specs = {f["name"]: f for f in d["features"]}
    feats, crit = [], {"inclusion": [], "exclusion": []}
    for f in d["features"]:
        if dz.provenance_known(f):
            feats.append(f)
        else:
            findings.append(Finding("Q1~Q3", UNABLE, f"features.{f['name']}",
                                    f"{UNKNOWN}: 정해진 특징 함수(leakcheck.features)로 만들지 않았거나 원본 테이블이 "
                                    f"없다. Q1~Q3 확인 불가.", "R.provenance",
                                    f"규칙 R.provenance(특징은 정해진 함수로만) · 값: source={f.get('source')}, "
                                    f"made_by={f.get('made_by', dz.PROVENANCE_OK)}"))
    for part in ("inclusion", "exclusion"):
        for c in d["cohort"][part]:
            if dz.provenance_known(c):
                crit[part].append(c)
            else:
                findings.append(Finding("Q5", UNABLE, f"cohort.{part}.{c['name']}",
                                        f"{UNKNOWN}: 기준의 원본 테이블이 없어 선택 시점을 확인할 수 없다.", "R.provenance",
                                        f"규칙 R.provenance · 값: source={c.get('source')}"))

    def guarded(question, target, fn):
        try:
            r = fn()
        except rules.RuleMissing as e:
            return [Finding(question, UNABLE, target, f"규칙표에 없어 확인 불가: {e}.", "R.missing",
                            f"규칙 R.missing(규칙이 없으면 추측하지 않고 멈춤) · 값: {e}")], []
        return r if isinstance(r, tuple) else (r, [])

    def add(res):
        f, a = res
        findings.extend(f)
        assumes.extend(a)

    ref = d["cohort"]["index_time"]
    for f in feats:
        add(guarded("Q1~Q3", f"features.{f['name']}",
                    lambda f=f: _time_check("Q1", "features", f, d, ctx, "tp", specs)))
    add(guarded("Q1", "preprocessing", lambda: check_q1_other(d)))
    add(guarded("Q2", "split", lambda: check_q2(d, ctx)))
    add(guarded("Q3", "preprocessing", lambda: check_q3(d)))
    add(guarded("Q4", f"outcome.{d['outcome']['name']}", lambda: check_q4(d, feats)))
    for part in ("inclusion", "exclusion"):
        for c in crit[part]:
            add(guarded("Q5", f"cohort.{part}.{c['name']}",
                        lambda c=c, part=part: _time_check("Q5", f"cohort.{part}", c, d, ctx, ref, specs)))
    add(guarded("Q5", "cohort", lambda: check_q5_other(d)))
    add(guarded("Q6", "attempts", lambda: (check_q6(d), [])))
    add(guarded("Q7", f"outcome.{d['outcome']['name']}", lambda: check_q7(d, ctx)))

    # 같은 가정은 한 번만
    seen_a, uniq = set(), []
    for a in assumes:
        if (a.rule, a.target) not in seen_a:
            seen_a.add((a.rule, a.target))
            uniq.append(a)

    seen = {f.question for f in findings if f.verdict in (BLOCK, WARN, UNABLE)}
    checked = {
        "Q2": (f"분할 키 {d['split']['key']}(대체 {d['split'].get('fallback_key', '없음')}) ≥ 독립 단위 "
               f"{d['split_unit']} ≥ 개체 단위 {rules.ENTITY_LEVEL}", "S.levels"),
        "Q3": (f"전처리 {len(d['preprocessing'])}단계와 모형 결정의 적합 범위 ⊆ 학습 부분, 평가는 평가 부분", "F.fit_scope"),
        "Q4": ("특징이 결과 행·결과 창·대리 기록과 겹치지 않음", "O.same_rows"),
        "Q7": ("결과 확인 강도가 층마다 같음 (또는 층별로 다룸, 또는 측정 의존 결과 아님), 확인 범위·이력·사망 출처",
               "O.strata"),
    }
    for q, (txt, rid) in checked.items():
        if q not in seen:
            findings.append(Finding(q, PASS, "설계 전체", txt, rid, f"규칙 {rid} · 값: 위반 없음"))
    return Report(d["design_id"], d["design_type"], ctx is not None, findings, uniq)
