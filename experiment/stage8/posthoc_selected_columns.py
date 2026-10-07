"""사후 확인 (8단계, 사용자 요청 2026-10-07): 특징 선택 누수 조건과 참조 조건이 시드마다 고른 열 이름.

성능을 계산하지 않는다 (AUROC 없음, 결정 잠금 대상 아님). 기존 결과 파일은 읽기만 한다.
열 선택은 experiment.leakage_effect.preprocess를 실행 때와 같은 설계·분할 시드로 다시 돌려 얻는다.
AUROC 비교는 results/stage8/leakage_effect_*.json에 이미 있는 값으로만 한다.

  python -m experiment.stage8.posthoc_selected_columns
"""
from __future__ import annotations

import json
from pathlib import Path

from experiment import leakage_effect as le
from leakcheck import data as ld
from leakcheck import design as dz
from leakcheck import splitting

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "stage8"
# (묶음, 유형, 누수 조건, 참조 조건, 열 이름을 모두 적는가)
PAIRS = [("main", "fixed", "F4", "F4ref", True), ("main", "dynamic", "D5", "D5ref", True),
         ("aux_A", "dynamic", "D5", "D5ref", False)]


def selected(d: dict, built: dict, step: int) -> list[str]:
    d = le.with_seed(d, step)
    nd = dz.normalize(d)
    train = (splitting.assign(built["rows"], nd["split"]) == "train").to_numpy()
    _, names = le.preprocess(built["X"], built["y"], train, nd["preprocessing"])
    return names


def main() -> int:
    tables, rec = {}, []
    for bundle, t, leak, ref, full in PAIRS:
        cfg = le.BUNDLES[bundle]
        tables.setdefault(bundle, ld.load(cfg["data"]))
        part = next(p for p in cfg["parts"] if p[0] == t)
        vs = le.variants8(t, le._base(part[1]), part[2], part[3])
        res = json.loads((OUT / f"leakage_effect_{bundle}.json").read_text(encoding="utf-8"))
        auc = {(r["design"], r["seed_step"]): r["auroc"] for r in res["runs"] if r["type"] == t}
        built = {n: le.build(vs[n][1], tables[bundle]) for n in (leak, ref)}
        for step in range(cfg["seeds"]):
            a, b = selected(vs[leak][1], built[leak], step), selected(vs[ref][1], built[ref], step)
            same_auc = {m: auc[(leak, step)][m] == auc[(ref, step)][m] for m in ("logistic", "hgb")}
            rec.append({"bundle": bundle, "type": t, "leak": leak, "ref": ref, "seed_step": step, "k": len(a),
                        "overlap": len(set(a) & set(b)), "same_columns": set(a) == set(b), "same_auroc": same_auc,
                        "leak_columns": a if full else None, "ref_columns": b if full else None})
    stop = [r for r in rec if not r["same_columns"] and any(r["same_auroc"].values())]
    (OUT / "posthoc_selected_columns.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    L = ["# 사후 확인: 특징 선택 조건이 고른 열", "",
         "**사후 확인**이다. 8단계 계획(`docs/stage8_plan.md`)에 없던 확인으로, 결과(본 데이터 D5와 D5 참조의 AUROC가 시드 5개 모두 같음)를 본 뒤 "
         "사용자 요청으로 했다. 성능을 다시 계산하지 않았다: 열 선택만 같은 설계·분할 시드로 다시 돌렸고, AUROC가 같은지는 "
         "`leakage_effect_*.json`에 이미 있는 값으로 비교했다. 기존 결과 파일은 바꾸지 않았다. "
         "생성: `python -m experiment.stage8.posthoc_selected_columns`.", "",
         f"고른 열은 다른데 AUROC(로지스틱·부스팅 중 하나라도)가 같은 시드: {len(stop)}개", ""]
    for bundle, t, leak, ref, full in PAIRS:
        rs = [r for r in rec if r["bundle"] == bundle and r["type"] == t]
        same = sum(r["same_columns"] for r in rs)
        ov = [r["overlap"] for r in rs]
        L += [f"## {bundle} · {t}: {leak}(전체 데이터로 적합) vs {ref}(학습 집합만)", "",
              f"k = {rs[0]['k']}. 고른 열이 같은 시드 {same}/{len(rs)}. 겹치는 열 수 {min(ov)}~{max(ov)} (k개 중).", ""]
        if full:
            L += ["| 시드 | 같음 | 겹침 | AUROC 같음 (로지스틱/부스팅) | " + leak + "만 고른 열 | " + ref + "만 고른 열 | 둘 다 고른 열 |",
                  "|---|---|---|---|---|---|---|"]
            for r in rs:
                a, b = r["leak_columns"], r["ref_columns"]
                L.append(f"| {r['seed_step']} | {'예' if r['same_columns'] else '아니요'} | {r['overlap']} | "
                         f"{'예' if r['same_auroc']['logistic'] else '아니요'}/{'예' if r['same_auroc']['hgb'] else '아니요'} | "
                         f"{', '.join(c for c in a if c not in b) or '-'} | {', '.join(c for c in b if c not in a) or '-'} | "
                         f"{', '.join(c for c in a if c in b)} |")
        else:
            L += ["| 시드 | 겹치는 열 수 | AUROC 같음 (로지스틱/부스팅) |", "|---|---|---|"]
            for r in rs:
                L.append(f"| {r['seed_step']} | {r['overlap']} | "
                         f"{'예' if r['same_auroc']['logistic'] else '아니요'}/{'예' if r['same_auroc']['hgb'] else '아니요'} |")
        L.append("")
    (OUT / "posthoc_selected_columns.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(json.dumps({"stop_seeds": len(stop)}))
    return 1 if stop else 0


if __name__ == "__main__":
    raise SystemExit(main())
