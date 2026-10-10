"""T1 acquisition/typed contract and T2 grain, IDs and split reproducibility."""
import copy

import numpy as np
import pandas as pd
import pytest

from campaignlab import data as dt
from campaignlab import governance as gov
from campaignlab.models import FeatureBasis, LeakageError, assert_covariates_only
from conftest import private_data_available
from synthetic import HEADER, make_rows, to_bytes


def _typed(cfg, rows, header=HEADER):
    text = dt.parse_source(to_bytes(rows, header), cfg)
    return dt.type_and_validate(text, cfg)


def _cfg_rows(cfg, n):
    c = copy.deepcopy(cfg)
    c["dataset"]["expected_rows"] = n
    return c


# --------------------------------------------------------------------------- T1 contract

def test_clean_synthetic_file_passes_all_hard_checks(cfg):
    rows = make_rows(300)
    _, checks = _typed(_cfg_rows(cfg, 300), rows)
    assert all(v == 0 for v in checks.values()), checks


@pytest.mark.parametrize("col,value,check", [
    ("segment", "Kids E-Mail", "allowed_segment"),
    ("visit", "2", "binary_visit"),
    ("mens", "", "blank_fields"),
    ("history", "-5.00", "history_decimal_format"),
    ("spend", "12.345", "spend_decimal_format"),
    ("spend", "nan", "spend_nonnegative_finite"),
    ("history", "inf", "history_nonnegative_finite"),
    ("recency", "13", "recency_integer_in_range"),
    ("recency", "0", "recency_integer_in_range"),
    ("zip_code", "Suburban", "allowed_zip_code"),
    ("channel", "Email", "allowed_channel"),
])
def test_invalid_values_fail_named_check(cfg, col, value, check):
    rows = make_rows(30, seed=1)
    rows[5][HEADER.index(col)] = value
    _, checks = _typed(_cfg_rows(cfg, 30), rows)
    assert checks[check] >= 1
    with pytest.raises(dt.ContractError):
        dt.assert_contract(checks)


def test_absent_column_fails_before_typing(cfg):
    rows = [r[:-1] for r in make_rows(5)]
    with pytest.raises(dt.ContractError, match="header"):
        dt.parse_source(to_bytes(rows, HEADER[:-1]), cfg)


def test_outcome_consistency_checks(cfg):
    rows = make_rows(40, seed=2)
    rows[0][HEADER.index("visit")], rows[0][HEADER.index("conversion")], rows[0][HEADER.index("spend")] = "0", "1", "10.00"
    rows[1][HEADER.index("conversion")], rows[1][HEADER.index("spend")] = "0", "5.00"
    _, checks = _typed(_cfg_rows(cfg, 40), rows)
    assert checks["conversion_without_visit"] == 1
    assert checks["positive_spend_without_conversion"] == 1


def test_decimal_import_preserves_cents(cfg):
    rows = make_rows(50, seed=3)
    typed, _ = _typed(_cfg_rows(cfg, 50), rows)
    exact = sum(int(round(float(r[HEADER.index("history")]) * 100)) for r in rows)
    assert int(typed["history_cents"].sum()) == exact
    assert np.allclose(typed["history"].to_numpy() * 100, typed["history_cents"].to_numpy())


def test_surburban_spelling_preserved(cfg):
    rows = make_rows(60, seed=4)
    typed, checks = _typed(_cfg_rows(cfg, 60), rows)
    assert checks["allowed_zip_code"] == 0
    assert "Surburban" in set(typed["zip_code"]) and "Suburban" not in set(typed["zip_code"])
    assert cfg["dataset"]["display_aliases"]["zip_code"]["Surburban"].startswith("Suburban")


def test_history_bucket_boundaries_are_soft_warnings(cfg):
    rows = make_rows(20, seed=5)
    rows[3][HEADER.index("history")], rows[3][HEADER.index("history_segment")] = "100.00", "2) $100 - $200"
    typed, checks = _typed(_cfg_rows(cfg, 20), rows)
    assert all(v == 0 for v in checks.values())  # not a hard failure
    d = dt.history_bucket_disagreements(typed)
    assert int(d["row_count"].sum()) == 1
    assert len(typed) == 20  # retained


def test_matching_rows_reported_not_dropped(cfg):
    rows = make_rows(30, seed=6)
    rows += [list(rows[0]), list(rows[0])]
    typed, _ = _typed(_cfg_rows(cfg, 32), rows)
    assert len(typed) == 32 and typed["row_id"].is_unique
    m = dt.matching_summary(typed)
    assert m["full_row_match_excess"] >= 2 and m["largest_full_row_group"] >= 3


def test_acquire_rejects_changed_bytes(cfg, tmp_path, monkeypatch):
    c = copy.deepcopy(cfg)
    c["dataset"]["raw_path"] = str(tmp_path / "raw.csv")
    (tmp_path / "raw.csv").write_bytes(to_bytes(make_rows(5)))
    with pytest.raises(dt.ContractError, match="hash"):
        dt.acquire(c)


# --------------------------------------------------------------------------- T2 grain / split

def test_row_ids_follow_source_order_and_survive_reordering(cfg):
    text = dt.parse_source(to_bytes(make_rows(50, seed=7)), cfg)
    assert list(text["row_id"][:3]) == ["hillstrom-2008-v1:0", "hillstrom-2008-v1:1", "hillstrom-2008-v1:2"]
    shuffled = text.sample(frac=1, random_state=3)
    s1 = dt.assign_split(text["row_id"], text["segment"], cfg).set_index("row_id")["partition"]
    s2 = dt.assign_split(shuffled["row_id"], shuffled["segment"], cfg).set_index("row_id")["partition"]
    assert s1.sort_index().equals(s2.sort_index())


def test_split_sizes_disjoint_complete_and_deterministic(cfg):
    ids = [f"hillstrom-2008-v1:{i}" for i in range(1000)]
    arms = np.repeat([0, 1, 2], [333, 334, 333])
    a = dt.assign_split(ids, arms, cfg)
    b = dt.assign_split(ids, arms, cfg)
    assert a.equals(b)
    for arm, n in ((0, 333), (1, 334), (2, 333)):
        part = a.loc[a.arm == arm, "partition"].value_counts()
        assert part["TRAIN"] == (n * 60) // 100 and part["VALIDATION"] == (n * 20) // 100
        assert part.sum() == n
    assert a["row_id"].is_unique and set(a["partition"]) == {"TRAIN", "VALIDATION", "TEST"}


def test_split_key_uses_no_outcomes(cfg):
    import inspect
    params = inspect.signature(dt.assign_split).parameters
    assert list(params) == ["row_ids", "arms", "cfg"]
    rows = make_rows(90, seed=8)
    flipped = [r[:9] + [str(1 - int(r[9])), "0", "0"] for r in rows]
    t1, _ = _typed(_cfg_rows(cfg, 90), rows)
    t2, _ = _typed(_cfg_rows(cfg, 90), flipped)
    assert dt.assign_split(t1.row_id, t1.arm, cfg).equals(dt.assign_split(t2.row_id, t2.arm, cfg))


def test_expected_planned_counts_from_frozen_arithmetic(cfg):
    for seg, n in cfg["dataset"]["expected_quality"]["arm_counts"].items():
        exp = cfg["split"]["expected_by_arm"][seg]
        assert exp["TRAIN"] == (n * 60) // 100 and exp["VALIDATION"] == (n * 20) // 100 and sum(exp.values()) == n


def test_covariate_allowlist_excludes_ids_treatment_outcomes(cfg):
    assert "history_segment" in cfg["features"]["excluded"]
    assert not {"segment", "visit", "conversion", "spend", "row_id", "history_segment"} & set(cfg["features"]["raw"])
    assert "history_segment" not in "".join(FeatureBasis(cfg).columns)
    with pytest.raises(LeakageError):
        assert_covariates_only(pd.DataFrame({"recency": [1], "visit": [0]}))


def _build_synthetic_db(cfg, tmp_path, n=600):
    c = copy.deepcopy(cfg)
    c["dataset"]["expected_rows"] = n
    c["dataset"]["database_path"] = str(tmp_path / "syn.duckdb")
    text = dt.parse_source(to_bytes(make_rows(n, seed=9)), c)
    typed, checks = dt.type_and_validate(text, c)
    dt.assert_contract(checks)
    split = dt.assign_split(typed["row_id"], typed["arm"], c)
    res = dt.build_database(c, text, split)
    return c, typed, split, res


def test_sql_and_python_contracts_agree(cfg, tmp_path):
    c, typed, split, res = _build_synthetic_db(cfg, tmp_path)
    q = dt.global_quality(typed)
    for k in ("global_visits", "global_conversions", "positive_spend_rows", "full_row_match_groups", "full_row_match_excess",
              "distinct_pretreatment_profiles", "history_bucket_boundary_disagreements"):
        assert res["sql_quality"][k] == q[k], k
    assert all(v == 0 for v in res["sql_checks"].values())
    assert res["sql_quality"]["total_history_cents"] == int(typed["history_cents"].sum())


def test_store_scopes_and_one_to_one_joins(cfg, tmp_path):
    c, typed, split, _ = _build_synthetic_db(cfg, tmp_path)
    store = dt.Store(c, "test")
    dev = store.frame("development")
    assert len(dev) == int(split["partition"].isin(["TRAIN", "VALIDATION"]).sum())
    assert set(dev["partition"]) == {"TRAIN", "VALIDATION"} and dev["row_id"].is_unique
    sql = store.sql("02_development_summary.sql")
    assert sql.loc[sql.sample_scope == "DEVELOPMENT", "n_rows"].sum() == len(dev)
    with pytest.raises(gov.AccessError):
        store.outcomes("test")
    with pytest.raises(gov.AccessError):
        store.outcomes("full")
    with pytest.raises(gov.AccessError):
        store.sql("03_final_experiment_summary.sql")
    with pytest.raises(gov.AccessError):
        store.outcomes("test", token=gov.TestAccessToken("forged"))


def test_many_to_many_join_fixture_fails():
    left = pd.DataFrame({"row_id": ["a", "a"], "x": [1, 2]})
    right = pd.DataFrame({"row_id": ["a", "a"], "y": [3, 4]})
    with pytest.raises(pd.errors.MergeError):
        left.merge(right, on="row_id", validate="one_to_one")


# --------------------------------------------------------------------------- private pinned artifact

pytestmark_private = pytest.mark.skipif(not private_data_available(), reason="private Hillstrom CSV not acquired")


@pytest.mark.private_data
@pytestmark_private
def test_pinned_artifact_contract(cfg):
    raw = dt.read_verified_bytes(cfg)
    assert len(raw) == cfg["dataset"]["expected_bytes"] and raw.count(b"\r\n") == 64001
    text = dt.parse_source(raw, cfg)
    typed, checks = dt.type_and_validate(text, cfg)
    assert all(v == 0 for v in checks.values())
    q = dt.global_quality(typed)
    for k, v in cfg["dataset"]["expected_quality"].items():
        assert q[k] == v, k
    split = dt.assign_split(typed["row_id"], typed["arm"], cfg)
    assert dt.check_split(split, cfg)["matches_expected"]
