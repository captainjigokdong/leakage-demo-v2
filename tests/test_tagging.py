import pandas as pd
import pytest

from leakcheck import rules
from leakcheck.tagging import TAG_COLUMNS, TaggingError, available_series, tag_tables


@pytest.fixture(scope="module")
def tagged(small_tables):
    return tag_tables(small_tables)


def test_every_row_of_every_table_gets_four_tags(small_tables, tagged):
    assert set(tagged) == set(small_tables)
    for name, df in tagged.items():
        assert len(df) == len(small_tables[name])
        for c in TAG_COLUMNS:
            assert c in df, (name, c)
        if name != "extract_info":   # 전역 1행 (자료 추출 정보)은 개체가 없다
            assert df["_entity"].notna().all(), name
        assert df["_provenance"].str.startswith(f"{name}#").all(), name
        assert df["_available_time"].notna().all(), name


def test_rule_layers(tagged):
    labs = tagged["labs"]
    assert (labs["_available_time"] == labs["report_time"]).all()            # 1층: 보고 시각
    dx = tagged["diagnoses"]
    assert (dx["_available_time"] == dx["coded_time"]).all()                  # 1층: 코딩 완료 시각 (v2 데이터의 사실)
    assert (dx["coded_time"] > dx["_discharge_time"]).all()
    pr = tagged["procedures"]
    assert (pr["_available_time"] == pr["coded_time"]).all()                  # 1층: 코드 입력 시각
    pl = tagged["person_links"]
    assert (available_series(pl, "person_links", "person_id") == tagged["extract_info"]["extraction_end_time"].iloc[0]).all()


def test_date_only_values_use_day_end_by_default(tagged):
    """3층: 날짜만 있는 값은 기본으로 그날 23:59로 본다 (가정, rules.DATE_ONLY_DEFAULT)."""
    from leakcheck.features import date_times
    pr = tagged["procedures"]
    assert rules.DATE_ONLY_DEFAULT == "day_end"
    end = pd.to_datetime(pr["chart_date"]) + pd.Timedelta(hours=23, minutes=59)
    assert (date_times(pr, "chart_date", rules.DATE_ONLY_DEFAULT) == end).all()


def test_column_level_rule_differs_from_row_rule(tagged):
    adm = tagged["admissions"]
    assert (available_series(adm, "admissions", "unit") == adm["admit_time"]).all()
    assert (available_series(adm, "admissions", "discharge_status") == adm["discharge_time"]).all()
    assert (available_series(adm, "admissions", "length_of_stay_h") == adm["discharge_time"]).all()


def test_split_unit_follows_design(small_tables):
    fam = tag_tables(small_tables, "family")["patients"]
    has = fam["family_id"].notna()
    assert (fam.loc[has, "_split_unit"] == fam.loc[has, "family_id"]).all()
    person = fam["patient_id"].map(small_tables["person_links"].set_index("patient_id")["person_id"])
    assert (fam.loc[~has, "_split_unit"] == person[~has]).all()      # 가족이 비면 사람으로 (D6)
    pat = tag_tables(small_tables, "patient")["labs"]
    assert (pat["_split_unit"] == pat["_patient_id"]).all()
    per = tag_tables(small_tables, "person")["labs"]
    assert (per["_split_unit"] == per["_entity"]).all()            # 개체 = 사람 (D6)


def _broken(small_tables, table, fn):
    t = {k: v.copy() for k, v in small_tables.items()}
    fn(t[table])
    return t


def test_contradiction_report_before_collect_stops(small_tables):
    def f(labs):
        labs.loc[labs.index[0], "report_time"] = labs.loc[labs.index[0], "collect_time"] - pd.Timedelta(hours=1)
    with pytest.raises(TaggingError) as e:
        tag_tables(_broken(small_tables, "labs", f))
    assert "보고 시각이 채취 시각보다 이르다" in str(e.value)
    assert e.value.problems[0]["n_rows"] == 1


def test_contradiction_discharge_before_admit_stops(small_tables):
    def f(adm):
        adm.loc[adm.index[0], "discharge_time"] = adm.loc[adm.index[0], "admit_time"] - pd.Timedelta(hours=1)
    with pytest.raises(TaggingError, match="퇴원 시각이 입원 시각보다 이르다"):
        tag_tables(_broken(small_tables, "admissions", f))


def test_unlinked_and_missing_rows_stop(small_tables):
    def f(orders):
        orders.loc[orders.index[0], "admission_id"] = "A999999"
        orders.loc[orders.index[1], "order_time"] = pd.NaT
    with pytest.raises(TaggingError) as e:
        tag_tables(_broken(small_tables, "orders", f))
    msgs = " ".join(p["problem"] for p in e.value.problems)
    assert "입원 테이블에 없다" in msgs and "비어 있다" in msgs


def test_table_without_rule_stops(small_tables):
    t = dict(small_tables)
    t["icu_notes"] = pd.DataFrame({"admission_id": ["A000001"], "note": ["x"]})
    with pytest.raises(TaggingError, match="규칙표에 이 테이블의 규칙이 없다"):
        tag_tables(t)


def test_unknown_rule_lookup_raises():
    with pytest.raises(rules.RuleMissing):
        rules.availability("icu_notes")
    with pytest.raises(rules.RuleMissing):
        rules.availability("labs", "flag")
    with pytest.raises(rules.RuleMissing):
        rules.split_level("ward_id")
