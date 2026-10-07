"""8단계 그림과 표: results/stage8/leakage_effect_{main,aux_A,aux_B}.json → leakage_effect_*.png, leakage_effect.md

그림: 조건마다 수정 설계 대비 AUROC 차이 (점 = 시드 평균, 가로선 = 시드 범위). 특징 선택 조건은 참조 대비 차이를 속 빈 점으로 겹친다.
TPOT는 시드 1개라 점만. 그림 글자는 영어(컨테이너에 한글 글꼴 없음).

  python -m experiment.stage8.report
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "stage8"
MODELS = {"logistic": ("Logistic", "#2a78d6"), "hgb": ("HistGB", "#eb6834"), "tpot": ("TPOT (1 seed)", "#1baf7a")}
BUNDLE_LABEL = {"main": "본 데이터 (v1 설계)", "aux_A": "보조 데이터 안 A (8단계 시연용 설계: v1 동적 + 검사 500종)",
                "aux_B": "보조 데이터 안 B (v1 동적 설계 그대로)"}


def load(b: str) -> dict:
    return json.loads((OUT / f"leakage_effect_{b}.json").read_text(encoding="utf-8"))


def order(t: str, names) -> list[str]:
    pref = ["fixed", "F1", "F2", "F3", "F4", "F4ref", "D1", "D2", "D3", "D4", "D5", "D5ref", "D4+D5", "all"]
    return [n for n in pref if n in names]


def plot(b: str, res: dict) -> Path:
    parts = list(res["summary"].items())
    fig, axes = plt.subplots(1, len(parts), figsize=(6.2 * len(parts), 4.6), squeeze=False)
    for ax, (t, ds) in zip(axes[0], parts):
        names = [n for n in order(t, ds) if n != "fixed"]
        for j, (m, (lab, col)) in enumerate(MODELS.items()):
            off = (j - 1) * 0.22
            for i, n in enumerate(names):
                e = ds[n].get(m)
                if not e or "vs_fixed" not in e:
                    continue
                v = e["vs_fixed"]
                ax.hlines(i + off, v["min"], v["max"], color=col, lw=2)
                ax.plot(v["mean"], i + off, "o", color=col, ms=8, label=lab if i == 0 or n == names[-1] else None)
                if "vs_ref" in e:
                    ax.plot(e["vs_ref"]["mean"], i + off, "o", mfc="white", mec=col, mew=2, ms=8)
        ax.axvline(0, color="#888888", lw=1)
        ax.set_yticks(range(len(names)), names)
        ax.invert_yaxis()
        ax.set_xlabel("Test AUROC minus fixed design (filled) / minus train-only selection ref (open)")
        ax.set_title(f"{b} · {t} (seeds: {res['seeds']})")
        ax.grid(axis="x", color="#e5e5e5")
        h, l = ax.get_legend_handles_labels()
        seen = dict(zip(l, h))
        ax.legend(seen.values(), seen.keys(), loc="lower right", fontsize=8, frameon=False)
    fig.tight_layout()
    p = OUT / f"leakage_effect_{b}.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    return p


def f3(x: float) -> str:
    return f"{x:+.3f}"


def tables(b: str, res: dict) -> list[str]:
    L = [f"## {BUNDLE_LABEL[b]}", "", f"데이터 `{res['data']}`, 시드 {res['seeds']}개 (분할 시드 20261002 + 0~{res['seeds'] - 1}). "
         "차이 = 시드별 짝 차이(조건 − 기준)의 평균 [최소, 최대].", ""]
    for t, ds in res["summary"].items():
        desc = {**res["leaks"][t], **res["refs"][t]}
        L += [f"### {t}", "", "| 조건 | 설명 | 모델 | AUROC 평균 [범위] | 수정 대비 차이 | 참조 대비 차이 |", "|---|---|---|---|---|---|"]
        for n in order(t, ds):
            for m in MODELS:
                e = ds[n].get(m)
                if not e:
                    continue
                d = desc.get(n, "수정 설계" if n == "fixed" else ("누수 모두" if n == "all" else n))
                vf = e.get("vs_fixed")
                vr = e.get("vs_ref")
                cell = lambda v: f"{f3(v['mean'])} [{f3(v['min'])}, {f3(v['max'])}]" if v and v["n"] > 1 else (f3(v["mean"]) if v else "")
                L.append(f"| {n} | {d} | {m} | {e['mean']:.3f} [{e['min']:.3f}, {e['max']:.3f}] | {cell(vf)} | "
                         f"{cell(vr) + (' (기준 ' + vr['against'] + ')' if vr else '')} |")
        L += ["", f"<details><summary>{t} 시드별 AUROC</summary>", ""]
        steps = sorted({int(s) for n in ds for m in ds[n] for s in ds[n][m]["by_seed"]})
        L += ["| 조건 | 모델 | " + " | ".join(str(s) for s in steps) + " |", "|---|---|" + "---|" * len(steps)]
        for n in order(t, ds):
            for m in MODELS:
                e = ds[n].get(m)
                if e:
                    L.append(f"| {n} | {m} | " + " | ".join(f"{e['by_seed'][str(s)]:.3f}" if str(s) in e["by_seed"] else ""
                                                       for s in steps) + " |")
        L += ["", "</details>", ""]
    tp = [r for r in res["runs"] if "tpot" in r]
    if tp:
        L += ["### TPOT 실행 점검", "", "| 유형 | 조건 | 조각 사이 걸친 가족 | 넘긴 조각 객체 그대로 사용 | split 호출 | 걸린 시간(초) | AUROC | 고른 파이프라인 |",
              "|---|---|---|---|---|---|---|---|"]
        for r in tp:
            x = r["tpot"]
            pipe = x["pipeline"].replace("\n", " ").replace("|", "/")
            pipe = " ".join(pipe.split())
            L.append(f"| {r['type']} | {r['design']} | {x['cv_groups_crossing_folds']} | "
                     f"{'예' if x['cv_gen_is_group_folds'] and x.get('cv_gen_is_passed_object') else '아니요'} | {x['cv_split_calls']} | "
                     f"{x['seconds']} | {r['auroc']['tpot']:.3f} | `{pipe}` |")
        L.append("")
    fx = {r["type"]: r["patients_or_families_in_both"] for r in res["runs"] if r["design"] == "fixed"}
    L += [f"수정 설계에서 학습·시험 양쪽에 든 가족 수: " + ", ".join(f"{t} {v}" for t, v in fx.items()), ""]
    empty = {k: v["all_empty_columns"] for k, v in res["built"].items() if v["all_empty_columns"]}
    if empty:
        L += ["전부 비어 있는 열 (계획 3절 f): " + "; ".join(f"{k} {', '.join(v)}" for k, v in empty.items()), ""]
    L += [f"![{b}](leakage_effect_{b}.png)", ""]
    return L


def main() -> int:
    L = ["# 8단계 누수 효과 시연 결과", "",
         "계획 `docs/stage8_plan.md`. v2 판정(H1·H2)과 무관한 보조 분석이다. 합성 데이터라 AUROC 절대값에는 임상적 의미가 없고, "
         "수정 설계(또는 참조 조건) 대비 차이로 읽는다. 생성: `python -m experiment.stage8.report`.", ""]
    for b in ("main", "aux_A", "aux_B"):
        res = load(b)
        plot(b, res)
        L += tables(b, res)
    (OUT / "leakage_effect.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
