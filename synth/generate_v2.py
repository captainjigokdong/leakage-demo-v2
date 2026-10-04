"""v2 합성 EHR 생성기 (2단계 2b).

v2에서 데이터 구조를 확정하며 전체 재생성한다. 테이블·열은 synth/tables_v2.py, 열마다 값이 언제 생기고
언제 알려지는지는 docs/data_dictionary_v2.md가 기준이다. 정하지 못한 값은 2b 계획의 D1~D23(사용자 승인
2026-10-04)으로 정했고, 같은 값을 데이터 설명서에 적었다.

- 본 데이터(main): 사람 5,000명 → data/synth/
- 보조 데이터(aux, 환자 적고 변수 많은): 환자 200명, 1인당 입원 1회, 검사 500종 → data/synth_aux/

v1 생성기(synth/generate.py)는 그대로 둔다 (3단계 전까지 점검기 시험이 쓴다). 여기서는 v1의 잠재 위험 모형,
크레아티닌 궤적, 보고 지연, 진단·오더 확률을 불러 쓰고, 새 테이블과 시각 구조를 더한다.

생성기 안에서만 쓰는 정답 값(잠재 AKI, 잠재 위험 z, 연계되지 않은 사망 등)은 SynthV2.latent에만 있고
파일·MANIFEST에 저장하지 않는다.

난수: 사람마다 SeedSequence(seed)에서 갈라낸 난수 줄기를 정해진 순서로 쓴다. 같은 시드 → 같은 바이트.

실행: python -m synth.generate_v2 [--profile main|aux] [--seed N] [--out DIR] [--no-save]
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from synth.generate import OTHER_DX, OTHER_ORDERS, _cr_true, _logistic, _report_delay_min, to_csv_bytes
from synth.stats import kdigo_first
from synth.tables_v2 import TABLES_V2

GENERATOR_VERSION = "v2.1"

EPOCH = pd.Timestamp("2150-01-01")
H = 60
D = 24 * H


def minute_of(ts: str) -> int:
    return int((pd.Timestamp(ts) - EPOCH) / pd.Timedelta(minutes=1))


EXTRACTION_END = "2160-01-01 00:00:00"
END = minute_of(EXTRACTION_END)
SITES_COVERED = "A;B"
DEATH_LINKAGE_THROUGH = "2159-07-01"                        # D2
LINKAGE_END = minute_of(DEATH_LINKAGE_THROUGH) + D          # 원외 사망 기록 시각이 이 날짜 안이어야 연계됨
CR_METHOD_SWITCH = minute_of("2155-01-01")                  # D13 jaffe → enzymatic
JAFFE_OFFSET = 0.10                                         # D13 mg/dL
ICD10_SWITCH = minute_of("2155-10-01")                      # D14 (coded_time 기준)
EPOCH_WEEKDAY = EPOCH.weekday()
FIRST_ADMIT_SPAN_D = 3650 - 400                             # v1과 같음: 첫 입원은 이 범위 안 무작위

# --- 사람 (D1, D4, D5) ---
FAMILY_FRAC = 0.40          # 가족(2~3명)에 속한 사람
FAMILY_RECORD_P = 0.50      # 가족 단위로 family_id를 기록할 확률 → 결측 약 80%
ID_SWITCH_P = 0.07          # 입원 2회 이상인 사람 중 나중 입원이 새 등록 번호 (전체 사람의 약 2%)

# --- 입원 ---
MAX_UNPLANNED = 4           # v1 MAX_ADMISSIONS와 같음 (응급 입원 수 상한)
MAX_ADMISSIONS = 8          # 예약·이어진 입원 포함 전체 상한
AKI_INTERCEPT = -2.6        # v1과 같음
READMIT_INTERCEPT = -2.2    # v1과 같음
LATE_READMIT_P = 0.18       # v1과 같음
ICU_TREND = 0.3             # D12: 10년 동안 ICU 입실 logit 증가
ELECTIVE_RISK = -0.5        # D8: 예약 입원은 ICU·AKI 위험이 낮음
SURGERY_P = 0.30            # D7
SPLIT_P = 0.03              # D10: 입원의 3%가 바로 이어진 입원 두 건으로 나뉨
SPLIT_GAP_MIN = (0, 60)
B_READMIT_P = {"home": 0.05, "transfer": 0.40}   # D6
ICU_STEPDOWN_P = 0.60       # D11
ICU_STEPDOWN_DAYS = (1, 4)
WARD_TO_ICU_P = 0.05
# 검사 간격 (D11, D12): 병동은 연구 초 40~72시간 → 끝 30~60시간. ICU는 v1과 같이 하루 1~2회
WARD_LAB_GAP_START = (40.0, 72.0)
WARD_LAB_GAP_END = (30.0, 60.0)
WEEKEND_WARD_SKIP_P = 0.30
NIGHT = (22, 6)             # 22시~06시
PRE_DISCHARGE_DRAW_P = 0.35  # v1과 같음
# 활력 (D17)
VITAL_GAP_ICU_H = (1.0, 2.0)
VITAL_GAP_WARD_H = (4.0, 8.0)
NIGHT_WARD_VITAL_MULT = 1.5
# 사망 (D2)
OOH_DEATH_INTERCEPT = -3.0
LINK_DELAY_D = (14, 180)
# 코딩 (D16)
CODING_LATE_P = 0.10
PROC_SAME_DAY_P = 0.20
# 예약 (D8)
INPATIENT_BOOKING_P = 0.08
OUTPATIENT_BOOKING_P = 0.03
BOOKING_REALIZED_P = 0.85
BOOKING_LEAD_D = (7, 60)
# 외래 (D20; 추적 외래 매개변수는 v1 synth/outpatient.py와 같음)
FOLLOWUP_P = {"home": 0.70, "transfer": 0.35}
FOLLOWUP_DAYS = (5, 28)
ROUTINE_PER_YEAR = 0.25
OUTPATIENT_B_P = 0.10
OUTPATIENT_LAB_P = 0.50
OUTPATIENT_TEST_P = (("creatinine", 1.0, "mg/dL"), ("potassium", 0.8, "mmol/L"), ("hemoglobin", 0.6, "g/dL"))
# 문제 목록 (D19)
PL_RESOLVED_P = 0.15
PL_ERROR_P = 0.03
PL_CODE_CHANGE_P = 0.05
PL_CHRONIC_UPDATE_P = 0.10
CHRONIC = ("N18.3", "I10", "E11.9", "F32.9", "K21.9")
ACUTE = ("A41.9", "J18.9", "I50.9", "N17.9")
PL_CODE_CHANGE = {"N17.9": "N17.0", "I50.9": "I50.23", "E11.9": "E11.22", "J18.9": "J15.9",
                  "A41.9": "A41.51", "I10": "I11.9", "N18.3": "N18.4", "F32.9": "F33.1", "K21.9": "K21.0"}

# D14: v1 진단 코드의 ICD-9 대응
ICD9 = {"N17.9": "584.9", "N18.3": "585.3", "A41.9": "038.9", "I50.9": "428.0", "E87.5": "276.7",
        "I10": "401.9", "E11.9": "250.00", "D64.9": "285.9", "J18.9": "486", "N39.0": "599.0",
        "E87.1": "276.1", "K21.9": "530.81", "F32.9": "311", "R53.83": "780.79"}
# D15: 입원 당시 있던 진단(Y)일 확률
POA_Y_P = {"N18.3": 1.0, "I10": 1.0, "E11.9": 1.0, "F32.9": 1.0, "K21.9": 1.0, "D64.9": 1.0, "R53.83": 1.0,
           "N17.9": 0.0, "A41.9": 0.7, "J18.9": 0.7, "I50.9": 0.7, "N39.0": 0.7, "E87.5": 0.4, "E87.1": 0.4}

# D18: 약물 10종. (이름, 병동 확률, ICU 확률). 상태별 추가 확률은 _medications에
DRUGS = ("loop_diuretic", "ace_inhibitor", "nsaid", "vancomycin", "piperacillin_tazobactam",
         "proton_pump_inhibitor", "insulin", "heparin", "statin", "acetaminophen")
DRUG_BASE = {"loop_diuretic": (0.15, 0.35), "ace_inhibitor": (0.08, 0.05), "nsaid": (0.10, 0.05),
             "vancomycin": (0.06, 0.25), "piperacillin_tazobactam": (0.05, 0.20),
             "proton_pump_inhibitor": (0.35, 0.60), "insulin": (0.05, 0.20), "heparin": (0.50, 0.80),
             "statin": (0.15, 0.15), "acetaminophen": (0.50, 0.60)}
DISCHARGE_MED_P = 0.60
DISCHARGE_DRUGS = ("ace_inhibitor", "statin", "proton_pump_inhibitor", "loop_diuretic", "insulin", "acetaminophen")

# 보조 데이터 (D22)
AUX_N_TESTS = 500
AUX_N_SIGNAL = 10
AUX_SIGNAL_SD = 0.3
AUX_TP_H = 24.0
AUX_AKI_INTERCEPT = -1.1


@dataclass(frozen=True)
class Profile:
    name: str
    n_persons: int
    seed: int
    out: Path
    aux: bool


PROFILES = {
    "main": Profile("main", 5000, 20261040, Path("data/synth"), False),
    "aux": Profile("aux", 200, 20261041, Path("data/synth_aux"), True),
}

DATETIME_COLUMNS = {
    "extract_info": ["extraction_end_time"], "admissions": ["admit_time", "discharge_time"],
    "transfers": ["in_time", "out_time"], "labs": ["collect_time", "report_time"],
    "vitals": ["charted_time", "entered_time"], "medications": ["order_time"], "orders": ["order_time"],
    "diagnoses": ["coded_time"], "procedures": ["coded_time"], "problem_list": ["recorded_time"],
    "outpatient_visits": ["visit_time"], "outpatient_labs": ["collect_time", "report_time"],
    "admission_bookings": ["booked_time"], "deaths": ["death_time", "death_recorded_time"],
}
DATE_COLUMNS = {"extract_info": ["death_linkage_through"], "procedures": ["chart_date"],
                "admission_bookings": ["planned_date"]}


@dataclass
class SynthV2:
    tables: dict[str, pd.DataFrame]
    latent: dict[str, pd.DataFrame]   # 생성기 안의 정답 값. 저장하지 않는다
    profile: str
    seed: int
    n_persons: int


@dataclass
class _Adm:
    aid: str
    admit: int
    discharge: int
    status: str
    site: str
    typ: str
    service: str
    episode: str
    segments: list            # [(unit, in_min, out_min)]
    icu_any: bool
    aki: bool
    onset: int | None
    sepsis: bool
    observed: bool
    detect_report: int | None
    codes: list               # 진단 코드 (잠재; 코딩 완료 여부와 무관)
    coded_time: int | None
    continuation: bool = False


def _day(minute: int) -> str:
    return (EPOCH + pd.Timedelta(minutes=int(minute))).strftime("%Y-%m-%d")


def _hour_of(minute: float) -> float:
    return (minute % D) / H


def _weekday(minute: float) -> int:
    return (EPOCH_WEEKDAY + int(minute // D)) % 7


def _is_night(minute: float) -> bool:
    h = _hour_of(minute)
    return h >= NIGHT[0] or h < NIGHT[1]


def _year_frac(minute: int) -> float:
    return min(max(minute / END, 0.0), 1.0)


class _Gen:
    def __init__(self, prof: Profile, seed: int, n_persons: int):
        self.prof, self.seed, self.n = prof, seed, n_persons
        self.R: dict[str, list] = {t: [] for t in TABLES_V2}
        self.lat_adm: list = []
        self.lat_person: list = []
        self.c = {k: 0 for k in ("adm", "ep", "tr", "lab", "vit", "med", "ord", "pl", "ov", "ol", "bk", "newid")}
        if prof.aux:
            trng = np.random.default_rng(np.random.SeedSequence([seed, 1]))
            self.aux_mean = trng.normal(0, 1, AUX_N_TESTS)
            self.aux_scale = np.exp(trng.normal(0, 0.5, AUX_N_TESTS))
            self.aux_signal = set(int(i) for i in trng.choice(AUX_N_TESTS, AUX_N_SIGNAL, replace=False))

    def _next(self, k: str) -> int:
        self.c[k] += 1
        return self.c[k]

    # ------------------------------------------------------------ 사람
    def run(self) -> None:
        root = np.random.default_rng(np.random.SeedSequence([self.seed, 0]))
        n = self.n
        age = np.clip(np.round(root.normal(62, 16, n)), 18, 95).astype(int)
        sex = root.choice(np.array(["F", "M"]), n)
        fam_true, fam_rec = self._families(root, n)
        fam_effect = {f: float(root.normal(0, 0.7)) for f in sorted({f for f in fam_true if f})}
        own = root.normal(0, 0.7, n)
        indiv = root.normal(0, 0.4, n)
        children = np.random.SeedSequence([self.seed, 2]).spawn(n)
        self.R["extract_info"].append((EXTRACTION_END, SITES_COVERED, DEATH_LINKAGE_THROUGH))
        for i in range(n):
            z = (fam_effect[fam_true[i]] if fam_true[i] else own[i]) + indiv[i]
            self._person(i, np.random.default_rng(children[i]), int(age[i]), str(sex[i]), fam_rec[i], float(z))

    def _families(self, rng, n) -> tuple[list, list]:
        true: list[str | None] = [None] * n
        order = rng.permutation(n)
        target = int(round(FAMILY_FRAC * n))
        pos, k = 0, 0
        while pos < target and pos + 2 <= n:
            size = min(int(rng.choice([2, 3], p=[0.6, 0.4])), n - pos)
            k += 1
            for j in order[pos:pos + size]:
                true[j] = f"T{k:05d}"
            pos += size
        rec_map, r = {}, 0
        for f in sorted({f for f in true if f}):
            if rng.random() < FAMILY_RECORD_P:
                r += 1
                rec_map[f] = f"F{r:04d}"
        return true, [rec_map.get(f) if f else None for f in true]

    def _person(self, i, rng, age, sex, fam, z) -> None:
        prof = self.prof
        ckd = rng.random() < _logistic(-2.2 + 0.04 * (age - 60) + 0.8 * z)
        base_cr = (0.95 if sex == "M" else 0.75) * float(np.exp(rng.normal(0, 0.12)))
        base_cr *= 1 + 0.004 * max(age - 40, 0)
        if ckd:
            base_cr *= float(rng.uniform(1.5, 2.5))
        diabetic = rng.random() < 0.22

        adms: list[_Adm] = []
        visits: list[dict] = []
        bookings: list[dict] = []
        death: tuple[int, str] | None = None
        n_unplanned = 0
        pending = {"t": int(rng.integers(0, FIRST_ADMIT_SPAN_D * D)), "site": "A", "typ": "emergency",
                   "booking": None, "cont": None}
        while pending is not None and len(adms) < (1 if prof.aux else MAX_ADMISSIONS):
            cont = pending["cont"]
            a = self._admission(rng, age, sex, z, ckd, diabetic, base_cr, pending)
            if a is None:   # 퇴원이 자료 추출 종료 뒤로 넘어감 (D21): 이 사람의 기록은 여기서 끝
                break
            if pending["booking"] is not None:
                pending["booking"]["adm"] = a
            if cont is None and a.typ == "emergency":
                n_unplanned += 1
            adms.append(a)
            pending = None
            if a.status == "died":
                death = (a.discharge, "in_hospital")
                break
            if a.status == "transfer" and getattr(a, "split_next", None) is not None:
                pending = a.split_next
                continue
            if prof.aux:
                pending, death = self._after_discharge_aux(rng, a, age, z, visits)
                break
            pending, death = self._after_discharge(rng, a, age, z, n_unplanned, visits, bookings)
            if death is not None:
                break

        if not adms:
            return
        # 등록 번호 (D4)
        pid_old = f"P{i + 1:05d}"
        pid_new, switch_t = None, None
        starts = [k for k, a in enumerate(adms) if k >= 1 and not a.continuation]
        if not prof.aux and starts and rng.random() < ID_SWITCH_P:
            k = starts[int(rng.integers(0, len(starts)))]
            switch_t = adms[k].admit
            pid_new = f"P{self.n + self._next('newid'):05d}"
        pid_at = (lambda t: pid_new if switch_t is not None and t >= switch_t else pid_old)
        person = f"H{i + 1:05d}"
        R = self.R
        R["patients"].append((pid_old, fam, age, sex))
        R["person_links"].append((pid_old, person))
        if pid_new:
            yrs = int((switch_t - adms[0].admit) // (365.25 * D))
            R["patients"].append((pid_new, fam, min(age + yrs, 95), sex))
            R["person_links"].append((pid_new, person))

        for a in adms:
            R["admissions"].append((a.aid, pid_at(a.admit), a.admit, a.discharge, a.status, a.segments[0][0]))
            R["admission_info"].append((a.aid, a.site, a.typ, a.service, a.episode))
            for unit, tin, tout in a.segments:
                R["transfers"].append((f"T{self._next('tr'):06d}", a.aid, unit, tin, tout))
        self._problem_list(rng, adms, pid_at)
        for v in sorted(visits, key=lambda v: v["t"]):
            vid = f"OV{self._next('ov'):06d}"
            R["outpatient_visits"].append((vid, pid_at(v["t"]), v["t"], v["site"], v["type"]))
            if rng.random() < OUTPATIENT_LAB_P:
                self._outpatient_labs(rng, vid, pid_at(v["t"]), v["t"], sex, base_cr)
        for b in sorted(bookings, key=lambda b: b["booked"]):
            src = b["src"].aid if b["src"] is not None else None
            adm = b["adm"].aid if b.get("adm") is not None else None
            R["admission_bookings"].append((f"B{self._next('bk'):06d}", pid_at(b["booked"]), src, b["booked"],
                                            _day(b["planned"]), adm))
        linked = None
        if death is not None:
            t, place = death
            if place == "in_hospital":
                R["deaths"].append((pid_at(t), t, place, t, "hospital_record"))
                linked = True
            else:
                rec = t + int(rng.uniform(*LINK_DELAY_D) * D)
                linked = rec < LINKAGE_END
                if linked:
                    R["deaths"].append((pid_at(t), t, place, rec, "registry_link"))
        self.lat_person.append((person, z, ckd, death[0] if death else None, death[1] if death else None, linked))

    # ------------------------------------------------------------ 퇴원 뒤 (다음 입원·외래·예약·원외 사망)
    def _after_discharge(self, rng, a: _Adm, age, z, n_unplanned, visits, bookings):
        dis = a.discharge
        INF = 10 ** 12
        # 응급 재입원 (v1 모형)
        p30 = _logistic(READMIT_INTERCEPT + 0.6 * z + 0.9 * a.aki + 0.015 * (age - 60) + 0.3 * a.icu_any)
        t_u = INF
        if rng.random() < p30:
            t_u = dis + int(rng.integers(1 * D, 30 * D))
        elif rng.random() < LATE_READMIT_P:
            t_u = dis + int(rng.integers(31 * D, 720 * D))
        if n_unplanned >= MAX_UNPLANNED:
            t_u = INF
        # 원외 사망 (D2)
        p1y = _logistic(OOH_DEATH_INTERCEPT + 0.5 * z + 0.03 * (age - 60) + 0.5 * a.aki + 0.5 * a.icu_any)
        t_d = dis + int(rng.uniform(1, 365) * D) if rng.random() < p1y else INF
        # 입원 중 예약 (D8)
        t_b, bk = INF, None
        if rng.random() < INPATIENT_BOOKING_P:
            booked = max(a.admit + 10, dis - int(rng.uniform(1, 24) * H))
            b = self._booking(rng, booked, a)
            bookings.append(b)
            if b["realized"]:
                t_b, bk = b["admit_t"], b
        # 추적 외래
        t_f = dis + int(rng.uniform(*FOLLOWUP_DAYS) * D) if rng.random() < FOLLOWUP_P.get(a.status, 0) else INF

        # 정기 외래: 퇴원 뒤부터 다음 입원·사망·종료 전까지 (D20). 외래에서 예약하면 다음 입원이 될 수 있다
        t = dis
        while True:
            horizon = min(t_u, t_b, t_d, END)
            t += int(rng.exponential(365.0 / ROUTINE_PER_YEAR) * D)
            if t >= horizon:
                break
            v = {"t": t, "site": "B" if rng.random() < OUTPATIENT_B_P else "A", "type": "routine", "booking": None}
            visits.append(v)
            if rng.random() < OUTPATIENT_BOOKING_P:
                b = self._booking(rng, t, None)
                bookings.append(b)
                v["booking"] = b
                if b["realized"] and b["admit_t"] < min(t_u, t_b):
                    t_b, bk = b["admit_t"], b
        t_next = min(t_u, t_b)
        if t_f < min(t_next, t_d, END):
            visits.append({"t": t_f, "site": "B" if rng.random() < OUTPATIENT_B_P else "A", "type": "follow_up",
                           "booking": None})
        for b in bookings:   # 다른 입원이 먼저 와서 예약 입원이 이루어지지 않음
            if b is not bk:
                b["realized"] = False
        if t_d < t_next and t_d < END:
            return None, (t_d, "out_of_hospital")
        if t_next >= END:
            return None, None
        if bk is not None and t_b <= t_u:
            return {"t": t_b, "site": "A", "typ": "elective", "booking": bk, "cont": None}, None
        if bk is not None:
            bk["realized"] = False
        site = "B" if rng.random() < B_READMIT_P.get(a.status, 0.05) else "A"
        return {"t": t_u, "site": site, "typ": "emergency", "booking": None, "cont": None}, None

    def _after_discharge_aux(self, rng, a: _Adm, age, z, visits):
        dis = a.discharge
        p1y = _logistic(OOH_DEATH_INTERCEPT + 0.5 * z + 0.03 * (age - 60) + 0.5 * a.aki + 0.5 * a.icu_any)
        t_d = dis + int(rng.uniform(1, 365) * D) if rng.random() < p1y else 10 ** 12
        t_f = dis + int(rng.uniform(*FOLLOWUP_DAYS) * D) if rng.random() < FOLLOWUP_P.get(a.status, 0) else 10 ** 12
        t = dis
        while True:
            t += int(rng.exponential(365.0 / ROUTINE_PER_YEAR) * D)
            if t >= min(t_d, END):
                break
            visits.append({"t": t, "site": "B" if rng.random() < OUTPATIENT_B_P else "A", "type": "routine",
                           "booking": None})
        if t_f < min(t_d, END):
            visits.append({"t": t_f, "site": "B" if rng.random() < OUTPATIENT_B_P else "A", "type": "follow_up",
                           "booking": None})
        return None, ((t_d, "out_of_hospital") if t_d < END else None)

    def _booking(self, rng, booked: int, src: _Adm | None) -> dict:
        planned_day = (booked + int(rng.uniform(*BOOKING_LEAD_D) * D)) // D
        admit_t = planned_day * D + 8 * H + int(rng.integers(0, 4 * H))
        realized = bool(rng.random() < BOOKING_REALIZED_P) and admit_t < END
        return {"booked": booked, "planned": planned_day * D, "admit_t": admit_t, "realized": realized,
                "src": src, "adm": None}

    # ------------------------------------------------------------ 입원 하나
    def _admission(self, rng, age, sex, z, ckd, diabetic, base_cr, spec) -> _Adm | None:
        prof = self.prof
        admit, cont = int(spec["t"]), spec["cont"]
        f = _year_frac(admit)
        elective = spec["typ"] == "elective"
        if cont is not None:
            service = cont["service"]
            site = cont["site"]
        else:
            service = "surgery" if rng.random() < SURGERY_P else "medicine"
            site = spec["site"]
        icu = bool(rng.random() < _logistic(-1.3 + 0.5 * z + 0.01 * (age - 60) + ICU_TREND * f
                                            + ELECTIVE_RISK * elective))
        los_h = float(np.clip(np.exp(rng.normal(np.log(110 if icu else 80), 0.5)), 24, 30 * 24))
        icpt = AUX_AKI_INTERCEPT if prof.aux else AKI_INTERCEPT
        aki = bool(rng.random() < _logistic(icpt + 0.7 * z + 0.9 * icu + 0.7 * ckd + 0.02 * (age - 60)
                                            + ELECTIVE_RISK * elective))
        onset_h = rise = None
        peak = 1.0
        if aki:
            onset_h = float(rng.uniform(12, max(13.0, min(0.7 * los_h, 168))))
            rise = float(rng.uniform(12, 48))
            peak = float(rng.uniform(1.3, 3.5))
            los_h = max(los_h, onset_h + rise + float(rng.uniform(36, 144)))
        sepsis = bool(rng.random() < 0.05 + 0.15 * icu + 0.10 * aki)
        los_min = int(round(los_h * H))
        discharge = admit + los_min
        if discharge > END:
            return None
        aid = f"A{self._next('adm'):06d}"
        episode = cont["episode"] if cont is not None else f"E{self._next('ep'):06d}"

        # 퇴원처 (v1과 같음) + 이어진 입원 (D10)
        p_die = 0.01 + 0.03 * icu + 0.06 * (aki and peak > 2.5)
        u = rng.random()
        status = "died" if u < p_die else ("transfer" if u < p_die + 0.12 else "home")
        split_next = None
        if (status != "died" and cont is None and not prof.aux and rng.random() < SPLIT_P):
            status = "transfer"
            nxt = discharge + int(rng.integers(SPLIT_GAP_MIN[0], SPLIT_GAP_MIN[1] + 1))
            if rng.random() < 0.5:
                c = {"service": "surgery" if service == "medicine" else "medicine", "site": site}
            else:
                c = {"service": service, "site": "B" if site == "A" else "A"}
            c["episode"] = episode
            split_next = {"t": nxt, "site": c["site"], "typ": spec["typ"], "booking": None, "cont": c}

        # 병동 구간 (D11)
        segs_h: list[tuple[str, float, float]]
        if icu and rng.random() < ICU_STEPDOWN_P:
            cut = float(rng.uniform(*ICU_STEPDOWN_DAYS)) * 24
            segs_h = [("ICU", 0.0, cut), ("ward", cut, los_h)] if cut < los_h - 12 else [("ICU", 0.0, los_h)]
        elif not icu and rng.random() < WARD_TO_ICU_P:
            cut = float(rng.uniform(0.2, 0.7)) * los_h
            segs_h = [("ward", 0.0, cut), ("ICU", cut, los_h)]
        else:
            segs_h = [("ICU" if icu else "ward", 0.0, los_h)]
        segments = [(u_, admit + int(round(s * H)), admit + int(round(e * H))) for u_, s, e in segs_h]
        segments[-1] = (segments[-1][0], segments[-1][1], discharge)
        icu_any = any(u_ == "ICU" for u_, _, _ in segs_h)
        base_adm = base_cr * float(np.exp(rng.normal(0, 0.06)))
        onset_min = admit + int(round(onset_h * H)) if aki else None
        self.lat_adm.append((aid, aki, onset_min, peak, sepsis))

        # 검사
        cr_obs, hgb_min, k_max = self._labs(rng, aid, admit, los_h, segs_h, f, sex, icu, base_adm, onset_h, rise,
                                            peak, aki)
        j = kdigo_first(np.array([c[0] for c in cr_obs]), np.array([c[1] for c in cr_obs]))
        observed = j is not None
        detect_report = cr_obs[j][2] if observed else None

        self._vitals(rng, aid, admit, segs_h, onset_h, rise, aki, sepsis)

        # 진단 (v1 확률 + D7 병동·진료과별 AKI 코드 누락)
        unit0 = segs_h[0][0]
        code_factor = (0.9 if unit0 == "ICU" else 0.75) * (0.8 if service == "surgery" else 1.0)
        p_n17 = code_factor if observed else (0.4 * code_factor / 0.9 if aki else 0.01)
        codes = []
        if rng.random() < p_n17:
            codes.append("N17.9")
        if ckd and rng.random() < 0.9:
            codes.append("N18.3")
        if sepsis and rng.random() < 0.9:
            codes.append("A41.9")
        if rng.random() < 0.10 + 0.10 * icu:
            codes.append("I50.9")
        if k_max >= 5.5 and rng.random() < 0.7:
            codes.append("E87.5")
        for code, p in OTHER_DX:
            if code == "E11.9":
                if diabetic and rng.random() < 0.9:
                    codes.append(code)
            elif rng.random() < p:
                codes.append(code)
        if not codes:
            codes.append("R53.83")
        late = rng.random() < CODING_LATE_P
        coded = discharge + int(rng.uniform(15, 90) * D if late else rng.uniform(1, 14) * D)
        coded_time = coded if coded <= END else None
        if coded_time is not None:
            icd10 = coded_time >= ICD10_SWITCH
            for s, ci in enumerate(rng.permutation(len(codes)), start=1):
                c = codes[ci]
                poa = "Y" if rng.random() < POA_Y_P[c] else "N"
                self.R["diagnoses"].append((aid, s, c if icd10 else ICD9[c], "ICD10" if icd10 else "ICD9", poa,
                                            coded_time))

        self._procedures_orders(rng, aid, admit, discharge, los_min, icu, aki, ckd, peak, rise, onset_min,
                                observed, cr_obs, j, hgb_min, coded_time)
        self._medications(rng, aid, admit, discharge, los_min, icu, aki, onset_min, sepsis, diabetic, codes,
                          status, age)

        a = _Adm(aid, admit, discharge, status, site, spec["typ"], service, episode, segments, icu_any, aki,
                 onset_min, sepsis, observed, detect_report, codes, coded_time, continuation=cont is not None)
        a.split_next = split_next
        return a

    def _labs(self, rng, aid, admit, los_h, segs_h, f, sex, icu, base_adm, onset_h, rise, peak, aki):
        lo = WARD_LAB_GAP_START[0] + (WARD_LAB_GAP_END[0] - WARD_LAB_GAP_START[0]) * f
        hi = WARD_LAB_GAP_START[1] + (WARD_LAB_GAP_END[1] - WARD_LAB_GAP_START[1]) * f
        hours = [float(rng.uniform(0.2, 2.0))]
        for unit, s, e in segs_h:
            if unit == "ICU":
                day = int(s // 24)
                while day * 24 < e:
                    for off, p in ((6.0, 1.0), (18.0, 0.6)):
                        h = day * 24 + off + float(rng.normal(0, 0.7))
                        if s <= h < e and rng.random() < p:
                            hours.append(h)
                    day += 1
            else:
                h = max(s, hours[0])
                while True:
                    h += float(rng.uniform(lo, hi))
                    m = admit + h * H
                    if _is_night(m):   # 야간 병동 채혈은 아침(06~08시)으로 미룸
                        to6 = ((NIGHT[1] * H - (m % D)) % D)
                        h += (to6 + float(rng.uniform(0, 2 * H))) / H
                        m = admit + h * H
                    if h >= e:
                        break
                    if _weekday(m) >= 5 and rng.random() < WEEKEND_WARD_SKIP_P:
                        continue
                    hours.append(h)
        hours = sorted(x for x in hours if x < los_h - 0.5)
        kept: list[float] = []
        for x in hours:
            if not kept or x > kept[-1] + 1:
                kept.append(x)
        if rng.random() < PRE_DISCHARGE_DRAW_P:
            x = los_h - float(rng.uniform(0.5, 3.0))
            if not kept or x > kept[-1] + 1:
                kept.append(x)

        cr_obs: list[tuple[float, float, int]] = []
        hgb_min, k_max = 99.0, 0.0
        R = self.R
        for h in kept:
            collect = admit + int(round(h * H))
            true_cr = _cr_true(h, base_adm, onset_h, rise or 1.0, peak)
            cr = max(0.2, true_cr * float(np.exp(rng.normal(0, 0.03))) + float(rng.normal(0, 0.03)))
            jaffe = collect < CR_METHOD_SWITCH
            cr_rep = round(cr + (JAFFE_OFFSET if jaffe else 0.0), 2)
            values = [("creatinine", cr_rep, "mg/dL", "jaffe" if jaffe else "enzymatic")]
            if not self.prof.aux:
                bun = max(3, round(10 + 9 * cr + float(rng.normal(0, 4)) + 4 * icu))
                k = round(4.1 + 0.4 * (true_cr / base_adm - 1) + float(rng.normal(0, 0.35)), 1)
                values += [("bun", bun, "mg/dL", "standard"), ("potassium", k, "mmol/L", "standard")]
                k_max = max(k_max, k)
                if rng.random() < 0.75:
                    hgb = round((13.5 if sex == "M" else 12.2) - 1.2 * icu - 0.08 * h / 24
                                + float(rng.normal(0, 0.9)), 1)
                    values.append(("hemoglobin", hgb, "g/dL", "standard"))
                    hgb_min = min(hgb_min, hgb)
            for test, val, unit, method in values:
                report = collect + _report_delay_min(rng, test)
                if report > END:
                    continue
                R["labs"].append((f"L{self._next('lab'):07d}", aid, test, val, unit, method, collect, report))
                if test == "creatinine":
                    cr_obs.append((h, cr_rep, report))
        if self.prof.aux:
            self._aux_panel(rng, aid, admit, los_h, aki)
        return cr_obs, hgb_min, k_max

    def _aux_panel(self, rng, aid, admit, los_h, aki):
        R = self.R
        limit = min(AUX_TP_H - 1.0 / H, los_h - 0.5)   # 분 단위 반올림 뒤에도 tₚ 전
        for t in range(AUX_N_TESTS):
            n = int(rng.integers(1, 4))
            hs = np.sort(rng.uniform(0.2, limit, n))
            shift = AUX_SIGNAL_SD if (aki and t in self.aux_signal) else 0.0
            for h in hs:
                val = round(float(self.aux_mean[t] + self.aux_scale[t] * (rng.normal(0, 1) + shift)), 3)
                collect = admit + int(round(h * H))
                report = collect + _report_delay_min(rng, "other")
                if report > END:
                    continue
                R["labs"].append((f"L{self._next('lab'):07d}", aid, f"t{t + 1:03d}", val, "AU", "standard",
                                  collect, report))

    def _vitals(self, rng, aid, admit, segs_h, onset_h, rise, aki, sepsis):
        R = self.R
        for unit, s, e in segs_h:
            icu = unit == "ICU"
            gap = VITAL_GAP_ICU_H if icu else VITAL_GAP_WARD_H
            h = s + float(rng.uniform(0, gap[0]))
            while h < e:
                charted = admit + int(round(h * H))
                in_aki = aki and onset_h <= h <= onset_h + rise + 24
                early_sepsis = sepsis and h <= 72
                hr = round(80 + 8 * icu + 15 * sepsis + 8 * in_aki + float(rng.normal(0, 10)))
                sbp = round(125 - 12 * icu - 15 * sepsis - 10 * in_aki + float(rng.normal(0, 14)))
                temp = round(36.8 + 1.0 * early_sepsis + float(rng.normal(0, 0.35)), 1)
                delay = (int(rng.uniform(0, 60)) if icu
                         else int(np.clip(rng.exponential(90), 0, 360)))
                entered = charted + delay
                if entered <= END:
                    for item, val in (("heart_rate", hr), ("sbp", sbp), ("temperature", temp)):
                        R["vitals"].append((f"V{self._next('vit'):07d}", aid, item, val, charted, entered))
                step = float(rng.uniform(*gap))
                if not icu and _is_night(admit + h * H):
                    step *= NIGHT_WARD_VITAL_MULT
                h += step

    def _procedures_orders(self, rng, aid, admit, discharge, los_min, icu, aki, ckd, peak, rise, onset_min,
                           observed, cr_obs, j, hgb_min, coded_time):
        R = self.R
        procs: list[tuple[str, int]] = []

        def order(kind: str, minute: int) -> None:
            if minute >= discharge:
                return
            R["orders"].append((f"O{self._next('ord'):07d}", aid, kind, int(max(minute, admit + 10))))

        if icu:
            if rng.random() < 0.5:
                procs.append(("02HV33Z", admit + int(rng.integers(0, D))))
            if rng.random() < 0.25:
                procs.append(("0BH17EZ", admit + int(rng.integers(0, D))))
        if hgb_min < 8 and rng.random() < 0.6 or rng.random() < 0.03:
            procs.append(("30233N1", admit + int(rng.integers(0, los_min))))
        if aki and (peak >= 2.5 or (ckd and peak >= 2.0)) and rng.random() < 0.45:
            start = onset_min + int(round((rise + float(rng.uniform(0, 24))) * H))
            if start < discharge - 6 * H:
                order("dialysis_order", start - int(rng.integers(1 * H, 6 * H)))
                for d in range(int(rng.integers(1, 4))):
                    if start + d * D < discharge:
                        procs.append(("5A1D70Z", start + d * D))
        if observed:
            detect = cr_obs[j][2]
            if rng.random() < 0.6:
                if rng.random() < 0.25:
                    since = onset_min if aki else cr_obs[j - 1][2]
                    order("nephrology_consult", since + int(rng.integers(0, max(1, detect - since))))
                else:
                    order("nephrology_consult", detect + int(rng.integers(2 * H, 24 * H)))
        elif aki:
            if rng.random() < 0.2:
                order("nephrology_consult", onset_min + int(rng.integers(12 * H, 48 * H)))
        elif rng.random() < (0.12 if ckd else 0.03):
            order("nephrology_consult", admit + int(rng.integers(0, los_min)))
        if rng.random() < (0.4 if aki else 0.04):
            order("renal_ultrasound", (onset_min if aki else admit) + int(rng.integers(0, 36 * H)))
        for kind, p_ward, p_icu in OTHER_ORDERS:
            if rng.random() < (p_icu if icu else p_ward):
                order(kind, admit + int(rng.integers(0, los_min)))

        # 시술 코드 입력 (D16): 20%는 시술 당일, 나머지는 진단 코딩과 같은 시각
        seen = set()
        for code, minute in procs:
            key = (code, _day(minute))
            if key in seen:
                continue
            seen.add(key)
            if rng.random() < PROC_SAME_DAY_P:
                ct = minute + int(rng.uniform(0, 12) * H)
            else:
                ct = coded_time
            if ct is None or ct > END:
                continue
            R["procedures"].append((aid, code, key[1], ct))

    def _medications(self, rng, aid, admit, discharge, los_min, icu, aki, onset_min, sepsis, diabetic, codes,
                     status, age):
        R = self.R
        for drug in DRUGS:
            p = DRUG_BASE[drug][1 if icu else 0]
            if drug in ("vancomycin", "piperacillin_tazobactam") and sepsis:
                p = max(p, 0.6)
            if drug == "insulin" and diabetic:
                p = 0.7
            if drug == "ace_inhibitor" and "I10" in codes:
                p = 0.35
            if drug == "statin" and age >= 60:
                p = 0.35
            if rng.random() < p:
                R["medications"].append((f"M{self._next('med'):07d}", aid, drug, "inpatient",
                                         admit + 10 + int(rng.integers(0, max(1, los_min - 10)))))
            if drug == "loop_diuretic" and aki and rng.random() < 0.4:   # AKI 뒤 이뇨제 (대리 변수)
                t = onset_min + int(rng.integers(6 * H, 48 * H))
                if t < discharge:
                    R["medications"].append((f"M{self._next('med'):07d}", aid, drug, "inpatient", t))
        if status != "died" and rng.random() < DISCHARGE_MED_P:
            k = int(rng.integers(1, 5))
            for drug in sorted(rng.choice(DISCHARGE_DRUGS, k, replace=False)):
                t = max(admit + 10, discharge - int(rng.uniform(1, 6) * H))
                R["medications"].append((f"M{self._next('med'):07d}", aid, str(drug), "discharge", t))

    def _outpatient_labs(self, rng, vid, pid, t, sex, base_cr):
        jaffe = t < CR_METHOD_SWITCH
        for test, p, unit in OUTPATIENT_TEST_P:
            if rng.random() >= p:
                continue
            if test == "creatinine":
                val = round(max(0.2, base_cr * float(np.exp(rng.normal(0, 0.05)))) + (JAFFE_OFFSET if jaffe else 0), 2)
                method = "jaffe" if jaffe else "enzymatic"
            elif test == "potassium":
                val, method = round(4.2 + float(rng.normal(0, 0.4)), 1), "standard"
            else:
                val, method = round((13.8 if sex == "M" else 12.4) + float(rng.normal(0, 1.0)), 1), "standard"
            report = t + int(rng.uniform(2, 24) * H)
            if report > END:
                continue
            self.R["outpatient_labs"].append((f"OL{self._next('ol'):06d}", pid, vid, test, val, unit, method, t,
                                              report))

    def _problem_list(self, rng, adms: list[_Adm], pid_at) -> None:
        R = self.R
        active: dict[tuple[str, str], dict] = {}

        def add_versions(entry: dict, first_t: int, last_allowed: int, aid: str) -> None:
            t, code, status = first_t, entry["code"], "active"
            versions = [(t, code, status, aid)]
            u = rng.random()
            if u < PL_ERROR_P:
                t += int(rng.uniform(1, 72) * H)
                versions.append((t, code, "entered_in_error", aid))
            else:
                if rng.random() < PL_CODE_CHANGE_P and code in PL_CODE_CHANGE:
                    t += int(rng.uniform(1, 30 * 24) * H)
                    code = PL_CODE_CHANGE[code]
                    versions.append((t, code, status, aid))
                if rng.random() < PL_RESOLVED_P:
                    t = max(t + H, int(rng.uniform(t + H, max(t + 2 * H, last_allowed))))
                    versions.append((t, code, "resolved", aid))
            entry["code"], entry["status"], entry["v"] = code, versions[-1][2], 0
            for vt, vc, vs, va in versions:
                if vt > END:
                    break
                entry["v"] += 1
                R["problem_list"].append((entry["id"], entry["pid"], va, entry["v"], vc, vs, vt))
                entry["last_t"] = vt

        for a in adms:
            pid = pid_at(a.admit)
            for c in [c for c in a.codes if c in CHRONIC]:
                key = (pid, c)
                if key not in active:
                    e = {"id": f"PL{self._next('pl'):06d}", "pid": pid, "code": c}
                    t0 = min(a.admit + int(rng.uniform(0, 24) * H), a.discharge - 1)
                    add_versions(e, t0, a.discharge + 30 * D, a.aid)
                    if e.get("v", 0) > 0 and e["status"] == "active":
                        active[key] = e
                elif rng.random() < PL_CHRONIC_UPDATE_P:
                    e = active[key]
                    t = max(a.admit + int(rng.uniform(0, 24) * H), e["last_t"] + 1)
                    if t < a.discharge and t <= END:
                        new_code = PL_CODE_CHANGE.get(e["code"], e["code"])
                        e["v"] += 1
                        e["code"], e["last_t"] = new_code, t
                        R["problem_list"].append((e["id"], pid, a.aid, e["v"], new_code, "active", t))
            for c in [c for c in a.codes if c in ACUTE]:
                if c == "N17.9":
                    if a.detect_report is None:
                        continue
                    t0 = a.detect_report + int(rng.uniform(0, 24) * H)
                else:
                    t0 = a.admit + int(rng.uniform(0, 48) * H)
                if t0 >= a.discharge:
                    continue
                e = {"id": f"PL{self._next('pl'):06d}", "pid": pid, "code": c}
                add_versions(e, t0, a.discharge + 30 * D, a.aid)

    # ------------------------------------------------------------ 표
    def frames(self) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
        t = {}
        for name, cols in TABLES_V2.items():
            t[name] = pd.DataFrame(self.R[name], columns=cols)
        for name, cols in DATETIME_COLUMNS.items():
            if name == "extract_info":
                continue
            for c in cols:
                t[name][c] = EPOCH + pd.to_timedelta(t[name][c].astype("float64"), unit="min")
        sort_keys = {"patients": ["patient_id"], "person_links": ["patient_id"], "diagnoses": ["admission_id", "seq"],
                     "procedures": ["admission_id", "chart_date", "code"], "problem_list": ["entry_id", "version"],
                     "deaths": ["patient_id"], "admission_bookings": ["booking_id"],
                     "admissions": ["admission_id"], "admission_info": ["admission_id"],
                     "medications": ["med_id"]}
        for name, keys in sort_keys.items():
            t[name] = t[name].sort_values(keys, kind="stable").reset_index(drop=True)
        for col in ("source_admission_id", "admission_id"):
            t["admission_bookings"][col] = t["admission_bookings"][col].astype("string")
        t["patients"]["family_id"] = t["patients"]["family_id"].astype("string")
        latent = {
            "admissions": pd.DataFrame(self.lat_adm, columns=["admission_id", "aki_latent", "onset_min", "peak_mult",
                                                              "sepsis"]),
            "persons": pd.DataFrame(self.lat_person, columns=["person_id", "z", "ckd", "death_min", "death_place",
                                                              "death_linked"]),
        }
        return t, latent


def generate(profile: str = "main", seed: int | None = None, n_persons: int | None = None) -> SynthV2:
    prof = PROFILES[profile]
    seed = prof.seed if seed is None else seed
    n = prof.n_persons if n_persons is None else n_persons
    if n < 1:
        raise ValueError("n_persons는 1 이상이어야 한다")
    g = _Gen(prof, seed, n)
    g.run()
    tables, latent = g.frames()
    return SynthV2(tables=tables, latent=latent, profile=profile, seed=seed, n_persons=n)


def save(ehr: SynthV2, out_dir: Path) -> dict:
    """테이블 17개를 <name>.csv.gz로 저장하고 MANIFEST.json(행 수, 압축 전 CSV의 sha256)을 쓴다.

    폴더의 다른 파일은 지운다 (폴더의 파일 목록 = MANIFEST의 파일 목록 + MANIFEST.json).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    keep = {f"{n}.csv.gz" for n in TABLES_V2} | {"MANIFEST.json"}
    for p in out_dir.iterdir():
        if p.is_file() and p.name not in keep:
            p.unlink()
    manifest = {"generator": "synth.generate_v2", "generator_version": GENERATOR_VERSION, "profile": ehr.profile,
                "seed": ehr.seed, "n_persons": ehr.n_persons,
                "packages": {"numpy": np.__version__, "pandas": pd.__version__}, "tables": {}}
    for name in TABLES_V2:
        raw = to_csv_bytes(ehr.tables[name])
        with open(out_dir / f"{name}.csv.gz", "wb") as fh, gzip.GzipFile(
            filename="", mode="wb", fileobj=fh, mtime=0, compresslevel=9
        ) as gz:
            gz.write(raw)
        manifest["tables"][name] = {"file": f"{name}.csv.gz", "rows": len(ehr.tables[name]),
                                    "sha256_csv": hashlib.sha256(raw).hexdigest()}
    (out_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest


def load(out_dir: Path = PROFILES["main"].out) -> dict[str, pd.DataFrame]:
    """저장된 v2 테이블을 읽는다. 시각 열은 datetime, 날짜 열과 문자 키는 문자열로."""
    str_cols = {"family_id", "source_admission_id", "admission_id", "chart_date", "planned_date",
                "death_linkage_through", "patient_id", "visit_id", "icd_code", "code", "sites_covered"}
    tables = {}
    for name in TABLES_V2:
        df = pd.read_csv(out_dir / f"{name}.csv.gz",
                         dtype={c: "string" for c in TABLES_V2[name] if c in str_cols})
        for c in DATETIME_COLUMNS.get(name, []):
            df[c] = pd.to_datetime(df[c])
        tables[name] = df
    return tables


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="v2 합성 EHR 생성")
    ap.add_argument("--profile", choices=sorted(PROFILES), default="main")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--n-persons", type=int, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args(argv)
    ehr = generate(args.profile, args.seed, args.n_persons)
    if not args.no_save:
        out = args.out or PROFILES[args.profile].out
        m = save(ehr, out)
        print(f"저장: {out}/ (profile={args.profile}, seed={ehr.seed})")
        for n, info in m["tables"].items():
            print(f"  {n}: {info['rows']}행")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
