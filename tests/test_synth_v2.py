"""v2 생성기 시험 (2단계 2b). 작은 데이터로 생성기의 성질을 확인한다. 저장된 데이터는 test_data_v2.py."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from synth import consistency_v2 as cv
from synth.generate import to_csv_bytes
from synth.generate_v2 import (CR_METHOD_SWITCH, EPOCH, ICD10_SWITCH, generate, load, save)
from synth.stats import kdigo_table
from synth.tables_v2 import TABLES_V2

N = 1500
SEED = 7


@pytest.fixture(scope="module")
def ehr():
    return generate("main", SEED, N)


@pytest.fixture(scope="module")
def aux():
    return generate("aux", SEED, 60)


def _ts(minutes: pd.Series) -> pd.Series:
    return EPOCH + pd.to_timedelta(minutes.astype("float64"), unit="min")


# --- 재현성·저장 ---

def test_same_seed_same_bytes(ehr):
    again = generate("main", SEED, N)
    for name in TABLES_V2:
        assert to_csv_bytes(ehr.tables[name]) == to_csv_bytes(again.tables[name]), name


def test_different_seed_differs(ehr):
    assert to_csv_bytes(ehr.tables["labs"]) != to_csv_bytes(generate("main", SEED + 1, N).tables["labs"])


def test_aux_is_reproducible(aux):
    again = generate("aux", SEED, 60)
    for name in TABLES_V2:
        assert to_csv_bytes(aux.tables[name]) == to_csv_bytes(again.tables[name]), name


def test_save_writes_only_tables_and_manifest_without_latent(ehr, tmp_path):
    (tmp_path / "stray.csv.gz").write_bytes(b"x")
    (tmp_path / "OUTPATIENT_MANIFEST.json").write_text("{}")
    m = save(ehr, tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([f"{t}.csv.gz" for t in TABLES_V2] + ["MANIFEST.json"])
    assert set(m["tables"]) == set(TABLES_V2)
    assert set(m) == {"generator", "generator_version", "profile", "seed", "n_persons", "packages", "tables"}
    text = (tmp_path / "MANIFEST.json").read_text()
    for word in ("latent", "aki_latent", "onset", "death_linked", "\"z\""):
        assert word not in text
    loaded = load(tmp_path)
    for name in TABLES_V2:
        assert list(loaded[name].columns) == TABLES_V2[name], name
        assert to_csv_bytes(loaded[name]) == to_csv_bytes(ehr.tables[name]), name
    first = (tmp_path / "vitals.csv.gz").read_bytes()
    save(ehr, tmp_path)
    assert (tmp_path / "vitals.csv.gz").read_bytes() == first
    assert json.loads((tmp_path / "MANIFEST.json").read_text()) == m


def test_n_persons_is_configurable():
    e = generate("main", 1, 30)
    assert e.tables["person_links"]["person_id"].nunique() == 30
    with pytest.raises(ValueError):
        generate("main", 1, 0)


# --- 구조 ---

def test_columns_exactly_table_list(ehr, aux):
    assert cv.column_mismatches(ehr.tables) == {}
    assert cv.column_mismatches(aux.tables) == {}


def test_keys_unique_and_foreign_keys(ehr):
    t = ehr.tables
    for name, key in (("patients", ["patient_id"]), ("person_links", ["patient_id"]),
                      ("admissions", ["admission_id"]), ("admission_info", ["admission_id"]),
                      ("transfers", ["transfer_id"]), ("labs", ["lab_id"]), ("vitals", ["vital_id"]),
                      ("medications", ["med_id"]), ("orders", ["order_id"]), ("diagnoses", ["admission_id", "seq"]),
                      ("procedures", ["admission_id", "code", "chart_date"]), ("problem_list", ["entry_id", "version"]),
                      ("outpatient_visits", ["visit_id"]), ("outpatient_labs", ["lab_id"]),
                      ("admission_bookings", ["booking_id"]), ("deaths", ["patient_id"])):
        assert not t[name].duplicated(key).any(), name
    pids, aids = set(t["patients"]["patient_id"]), set(t["admissions"]["admission_id"])
    assert set(t["person_links"]["patient_id"]) == pids
    for name in ("admission_info", "transfers", "labs", "vitals", "medications", "orders", "diagnoses", "procedures",
                 "problem_list"):
        assert set(t[name]["admission_id"]) <= aids, name
    for name in ("admissions", "problem_list", "outpatient_visits", "outpatient_labs", "admission_bookings", "deaths"):
        assert set(t[name]["patient_id"]) <= pids, name
    assert set(t["outpatient_labs"]["visit_id"]) <= set(t["outpatient_visits"]["visit_id"])
    b = t["admission_bookings"]
    assert set(b["source_admission_id"].dropna()) <= aids and set(b["admission_id"].dropna()) <= aids


def test_one_admission_per_person_in_aux(aux):
    t = aux.tables
    assert len(t["admissions"]) == t["person_links"]["person_id"].nunique() == 60
    assert len(t["admission_bookings"]) == 0
    tests = set(t["labs"]["test"])
    assert "creatinine" in tests and tests - {"creatinine"} <= {f"t{i:03d}" for i in range(1, 501)}
    panel = t["labs"][t["labs"]["test"] != "creatinine"].merge(t["admissions"], on="admission_id")
    assert ((panel["collect_time"] - panel["admit_time"]) < pd.Timedelta(hours=24)).all()   # tₚ = 24시간 이전


# --- 일관성 ---

def test_no_events_after_recorded_death(ehr, aux):
    assert sum(cv.events_after_death(ehr.tables).values()) == 0
    assert sum(cv.events_after_death(aux.tables).values()) == 0


def test_no_events_after_true_death_including_unlinked(ehr):
    lp = ehr.latent["persons"].dropna(subset=["death_min"])
    true = pd.Series(_ts(lp["death_min"]).values, index=lp["person_id"].values)
    assert sum(cv.events_after_death(ehr.tables, true).values()) == 0
    unlinked = lp[lp["death_linked"] == False]  # noqa: E712
    links = ehr.tables["person_links"]
    recorded = set(ehr.tables["deaths"]["patient_id"].map(links.set_index("patient_id")["person_id"]))
    assert recorded.isdisjoint(set(unlinked["person_id"]))


def test_nothing_after_extraction_end(ehr, aux):
    assert sum(cv.after_extraction_end(ehr.tables).values()) == 0
    assert sum(cv.after_extraction_end(aux.tables).values()) == 0
    assert cv.unlinked_out_of_hospital(ehr.tables) == 0


def test_record_not_before_event(ehr, aux):
    assert sum(cv.record_before_event(ehr.tables).values()) == 0
    assert sum(cv.record_before_event(aux.tables).values()) == 0


def test_consistency_checks_catch_violations(ehr):
    t = {k: v.copy() for k, v in ehr.tables.items()}
    d = t["deaths"].iloc[0]
    aid = t["admissions"].loc[t["admissions"]["patient_id"] == d["patient_id"], "admission_id"].iloc[0]
    t["labs"] = pd.concat([t["labs"], t["labs"].iloc[[0]].assign(
        admission_id=aid, collect_time=pd.Timestamp(d["death_time"]) + pd.Timedelta(hours=1),
        report_time=pd.Timestamp(d["death_time"]) + pd.Timedelta(hours=2))])
    assert cv.events_after_death(t)["labs.collect_time"] == 1
    t["vitals"].loc[0, "entered_time"] = pd.Timestamp("2160-01-02")
    assert cv.after_extraction_end(t)["vitals.entered_time"] == 1
    t["diagnoses"].loc[0, "coded_time"] = pd.Timestamp("2150-01-01")
    assert cv.record_before_event(t)["diagnoses.coded_time"] == 1
    t["orders"] = t["orders"].assign(extra=1)
    assert "orders" in cv.column_mismatches(t)


def test_planned_date_may_follow_extraction_end_but_booked_time_not(ehr):
    b = ehr.tables["admission_bookings"]
    assert (pd.to_datetime(b["booked_time"]) <= pd.Timestamp("2160-01-01")).all()
    assert (pd.to_datetime(b["planned_date"]) > pd.to_datetime(b["booked_time"]).dt.normalize()).all()


# --- 설명서의 일반 성질 ---

def test_admissions_do_not_overlap_within_person(ehr):
    t = ehr.tables
    a = t["admissions"].merge(t["person_links"], on="patient_id").sort_values(["person_id", "admit_time"])
    prev = a.groupby("person_id")["discharge_time"].shift(1)
    assert (a["admit_time"][prev.notna()] >= prev.dropna()).all()
    assert (a["discharge_time"] > a["admit_time"]).all()


def test_split_episodes(ehr):
    t = ehr.tables
    a = t["admissions"].merge(t["admission_info"], on="admission_id").sort_values("admit_time")
    multi = a[a["episode_id"].duplicated(keep=False)]
    assert multi["episode_id"].nunique() > 0
    for _, g in multi.groupby("episode_id"):
        assert len(g) == 2
        first, second = g.iloc[0], g.iloc[1]
        assert first["discharge_status"] == "transfer"
        assert pd.Timedelta(0) <= second["admit_time"] - first["discharge_time"] <= pd.Timedelta(minutes=60)
        assert (first["site"], first["service"]) != (second["site"], second["service"])


def test_some_people_have_two_ids_and_later_admissions_use_new_id(ehr):
    t = ehr.tables
    links = t["person_links"]
    two = links.groupby("person_id")["patient_id"].apply(sorted)
    two = two[two.map(len) == 2]
    assert len(two) > 0
    a = t["admissions"]
    for ids in two:
        old, new = ids
        assert a.loc[a["patient_id"] == old, "admit_time"].max() < a.loc[a["patient_id"] == new, "admit_time"].min()


def test_family_mostly_unrecorded(ehr):
    miss = ehr.tables["patients"]["family_id"].isna().mean()
    assert 0.70 <= miss <= 0.90


def test_creatinine_method_switches_once(ehr):
    cr = ehr.tables["labs"][ehr.tables["labs"]["test"] == "creatinine"]
    switch = _ts(pd.Series([CR_METHOD_SWITCH])).iloc[0]
    assert set(cr.loc[cr["collect_time"] < switch, "method"]) == {"jaffe"}
    assert set(cr.loc[cr["collect_time"] >= switch, "method"]) == {"enzymatic"}
    assert set(ehr.tables["labs"].loc[ehr.tables["labs"]["test"] != "creatinine", "method"]) == {"standard"}


def test_code_system_switches_once(ehr):
    dx = ehr.tables["diagnoses"]
    switch = _ts(pd.Series([ICD10_SWITCH])).iloc[0]
    assert set(dx.loc[dx["coded_time"] < switch, "code_system"]) == {"ICD9"}
    assert set(dx.loc[dx["coded_time"] >= switch, "code_system"]) == {"ICD10"}
    assert not dx.loc[dx["code_system"] == "ICD9", "icd_code"].str.contains(r"^[A-Z]").any()


def test_ward_misses_more_latent_aki(ehr):
    """측정이 드문 병동에서 잠재 AKI가 KDIGO로 덜 잡힌다 (결과 확인 강도 차이)."""
    m = (ehr.tables["admissions"].merge(kdigo_table(ehr.tables["labs"]), on="admission_id")
         .merge(ehr.latent["admissions"], on="admission_id"))
    m = m[m["aki_latent"]]
    detect = m.groupby("unit")["aki"].mean()
    assert detect["ICU"] > detect["ward"]
