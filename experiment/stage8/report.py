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
    fig, axes = plt.subplots(1, len(parts), figsize=(6.6 * len(parts), 5.2), squeeze=False)
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
                ax.plot(v["mean"], i + off, "o", color=col, ms=8, label=lab)
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
        seen["vs train-only selection ref"] = ax.plot([], [], "o", mfc="white", mec="#555555", mew=2, ms=8)[0]
        ax.legend(seen.values(), seen.keys(), loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=4, fontsize=8,
                  frameon=False)
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
    ks = {}
    for r in res["runs"]:
        if r["seed_step"] == 0 and r["design"] in ("F4", "F4ref", "D5", "D5ref", "D4+D5", "all"):
            ks[f"{r['type']}/{r['design']}"] = r["n_columns"]
    L += ["특징 선택 뒤 열 수 k (계획 3절 d): " + ", ".join(f"{k} {v}" for k, v in ks.items()), ""]
    fx = {r["type"]: r["patients_or_families_in_both"] for r in res["runs"] if r["design"] == "fixed"}
    L += [f"수정 설계에서 학습·시험 양쪽에 든 가족 수: " + ", ".join(f"{t} {v}" for t, v in fx.items()), ""]
    empty = {k: v["all_empty_columns"] for k, v in res["built"].items() if v["all_empty_columns"]}
    if empty:
        L += ["전부 비어 있는 열 (계획 3절 f): " + "; ".join(f"{k} {', '.join(v)}" for k, v in empty.items()), ""]
    L += [f"![{b}](leakage_effect_{b}.png)", ""]
    return L


def _r(v: dict) -> str:
    return f"{f3(v['mean'])} [{f3(v['min'])}, {f3(v['max'])}]"


def summary(R: dict) -> list[str]:
    """요약 문장 (사용자 요청 2026-10-07). 숫자는 모두 결과 파일에서 읽는다."""
    A, B, M = R["aux_A"]["summary"]["dynamic"], R["aux_B"]["summary"]["dynamic"], R["main"]["summary"]
    L = ["## 요약", "",
         "- **이 결과는 가설 판정이 아니다.** 7단계 판정(H1a·b·c, H2a·b)과 무관한 보조 분석이다.",
         f"- **안 A는 v1 설계가 아니라 8단계 시연용 설계다** (v1 동적 설계 + 검사 500종 특징). 안 A에서는 특징 선택 누수(D5)가 "
         f"참조 대비 로지스틱 {_r(A['D5']['logistic']['vs_ref'])}, 부스팅 {_r(A['D5']['hgb']['vs_ref'])}였다. "
         f"**안 B(v1 설계 그대로)에서는 효과가 없었다**: D5 참조 대비 로지스틱 {_r(B['D5']['logistic']['vs_ref'])}, "
         f"부스팅 {_r(B['D5']['hgb']['vs_ref'])}.",
         "- **특징 선택 누수의 효과는 참조 대비 차이로 읽는다.** v1 수정 설계에는 특징 선택 단계가 없어, 수정 대비 차이에는 "
         "누수 효과와 \"특징을 절반으로 줄인 효과\"가 섞인다. 참조(같은 선택을 학습 집합에서만 적합) 대비 차이가 누수 효과다. "
         f"예: 본 데이터 동적 D5는 수정 대비 로지스틱 {_r(M['dynamic']['D5']['logistic']['vs_fixed'])}이지만 참조 대비 "
         f"{_r(M['dynamic']['D5']['logistic']['vs_ref'])}이다 (두 조건이 고른 열이 같았다, `posthoc_selected_columns.md`).",
         f"- **TPOT(시드 1개)에서는 안 A의 D4+D5가 수정 대비 {A['D4+D5']['tpot']['vs_fixed']['mean']:+.3f}로 부풀림이 보이지 않았다.** "
         f"(안 B는 {B['D4+D5']['tpot']['vs_fixed']['mean']:+.3f}.) TPOT는 시드 1개라 범위가 없다.",
         f"- **부스팅의 D5 단독은 범위가 0에 걸친다** (안 A, 시드 20개): 수정 대비 {_r(A['D5']['hgb']['vs_fixed'])}, "
         f"참조 대비 {_r(A['D5']['hgb']['vs_ref'])}. 로지스틱은 두 차이 모두 범위가 0보다 크다 "
         f"(수정 대비 {_r(A['D5']['logistic']['vs_fixed'])}).",
         "- **수정 설계의 AUROC 절대값** (모델별 평균 [범위]; TPOT는 시드 1개). 합성 데이터라 임상적 의미는 없다.", "",
         "| 묶음 | 로지스틱 | 부스팅 | TPOT |", "|---|---|---|---|"]
    for lab, e in (("본 데이터 고정 시점 (시드 5)", M["fixed"]["fixed"]), ("본 데이터 동적 AKI (시드 5)", M["dynamic"]["fixed"]),
                   ("보조 안 A (시드 20)", A["fixed"]), ("보조 안 B (시드 20)", B["fixed"])):
        L.append(f"| {lab} | " + " | ".join(f"{e[m]['mean']:.3f} [{e[m]['min']:.3f}, {e[m]['max']:.3f}]" if m != "tpot"
                                             else f"{e[m]['mean']:.3f}" for m in ("logistic", "hgb", "tpot")) + " |")
    L += ["", "계획과 다르게 한 것: `docs/stage8_deviations.md`. 사후 확인: `posthoc_selected_columns.md`.", ""]
    return L


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-plot", action="store_true", help="그림은 다시 그리지 않고 표만 쓴다")
    a = ap.parse_args(argv)
    L = ["# 8단계 누수 효과 시연 결과", "",
         "계획 `docs/stage8_plan.md`. v2 판정(H1·H2)과 무관한 보조 분석이다. 합성 데이터라 AUROC 절대값에는 임상적 의미가 없고, "
         "수정 설계(또는 참조 조건) 대비 차이로 읽는다. 생성: `python -m experiment.stage8.report`.", "",
         "- TPOT는 시드 1개(분할 시드 20261002)라 범위가 없고, 참조 조건에는 돌리지 않아 참조 대비 차이가 없다.",
         "- \"모두\"의 참조 대비 차이는 F4 참조/D5 참조 기준이다. \"모두\"는 특징이 더 많아 k가 다르다 (각 절의 k 줄).", "",
         "**v2 데이터에서 표현되지 않은 항목** (설계를 고치지 않고 기록)", "",
         "- 보조 데이터의 고정 시점(30일 재입원) 설계: 1인당 입원 1회라 결과 양성 0 (194행). 실행하지 않음.",
         "- 보조 데이터의 동적 설계 특징 `bun_last`, `k_last`, `hgb_min`: 보조 데이터에 bun·potassium·hemoglobin 검사가 없어 모든 행이 빈 열. "
         "그대로 두고 0으로 채운 상수 열로 처리 (계획 3절 f).",
         "- v1 동적 설계(안 B)에는 검사 t001~t500이 특징으로 들어가지 않는다. 그래서 \"변수 많은\" 조건은 8단계 시연용 설계(안 A)로만 생긴다.", ""]
    R = {b: load(b) for b in ("main", "aux_A", "aux_B")}
    L += summary(R)
    for b, res in R.items():
        if not a.no_plot:
            plot(b, res)
        L += tables(b, res)
    (OUT / "leakage_effect.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
