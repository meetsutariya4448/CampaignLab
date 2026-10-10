"""T4 features and model fitting: TRAIN-only transforms, interactions, T-learner arm mapping, CV rules, gates."""
import copy

import numpy as np
import pandas as pd
import pytest

from campaignlab import models as md
from campaignlab import policy as pl

COV_COLS = ["row_id", "recency", "history", "mens", "womens", "newbie", "channel", "zip_code"]


def test_basis_fitted_on_training_rows_only(cfg, toy_frame):
    tr, te = toy_frame.iloc[:600][COV_COLS], toy_frame.iloc[600:][COV_COLS].copy()
    b1 = md.FeatureBasis(cfg).fit(tr)
    stats_before = copy.deepcopy(b1.stats)
    te["history"] *= 50
    te["recency"] = 12
    Z = b1.transform(te)
    assert b1.stats == stats_before and b1.n_fit == 600
    assert Z.shape == (300, 9) and md.FeatureBasis(cfg).columns[1] == "log_history"
    assert np.allclose(b1.transform(tr)[:, 0].mean(), 0, atol=1e-12)


def test_unknown_category_fails(cfg, toy_frame):
    b = md.FeatureBasis(cfg).fit(toy_frame[COV_COLS])
    bad = toy_frame[COV_COLS].copy()
    bad.loc[0, "zip_code"] = "Suburban"
    with pytest.raises(md.UnknownCategoryError):
        b.transform(bad)


def test_basis_rejects_outcome_and_assignment_columns(cfg, toy_frame):
    with pytest.raises(md.LeakageError):
        md.FeatureBasis(cfg).fit(toy_frame)  # contains arm/visit/spend


def test_s_learner_has_all_arm_by_feature_interactions(cfg, toy_frame):
    m = md.SLearner(cfg, 1.0).fit(toy_frame[COV_COLS], toy_frame.arm.to_numpy(), toy_frame.visit.to_numpy())
    d = m.to_dict()
    assert len(d["design_columns"]) == 9 + 2 + 18 and len(d["params"]["coef"]) == 29
    assert sum(c.startswith("M_x_") for c in d["design_columns"]) == 9 and sum(c.startswith("W_x_") for c in d["design_columns"]) == 9
    allp = m.predict_all(toy_frame[COV_COLS])
    for a in (0, 1, 2):
        assert np.allclose(allp[:, a], m.predict_observed(toy_frame[COV_COLS], np.full(len(toy_frame), a)))


def test_main_effects_only_preserves_arm_ordering_but_interactions_can_cross(cfg):
    rng = np.random.default_rng(4)
    n = 6000
    cov = pd.DataFrame({"row_id": [f"s:{i}" for i in range(n)], "recency": rng.integers(1, 13, n), "history": rng.lognormal(5, 0.6, n),
                        "mens": rng.integers(0, 2, n), "womens": rng.integers(0, 2, n), "newbie": rng.integers(0, 2, n),
                        "channel": rng.choice(["Phone", "Web", "Multichannel"], n), "zip_code": rng.choice(["Urban", "Surburban", "Rural"], n)})
    arm = rng.integers(0, 3, n)
    # synthetic crossing effects: M helps mens-only rows, W helps womens-only rows
    p = 0.15 + 0.15 * (arm == 1) * (cov.mens - cov.womens) + 0.15 * (arm == 2) * (cov.womens - cov.mens)
    y = (rng.random(n) < np.clip(p, 0.01, 0.99)).astype(int)
    me = md.SLearner(cfg, 10.0, interactions=False).fit(cov, arm, y)
    full = md.SLearner(cfg, 10.0).fit(cov, arm, y)
    a_me, _ = pl.best_gain_actions(me.predict_all(cov), 0.0)
    a_full, _ = pl.best_gain_actions(full.predict_all(cov), 0.0)
    assert len(np.unique(a_me)) == 1  # constant: fixed log-odds shifts preserve ordering
    assert {1, 2} <= set(np.unique(a_full))


def test_t_learner_uses_only_its_arm(cfg, toy_frame):
    cov, arm, y = toy_frame[COV_COLS], toy_frame.arm.to_numpy(), toy_frame.visit.to_numpy().copy()
    m1 = md.TLearner(cfg, 1.0).fit(cov, arm, y)
    y2 = y.copy()
    y2[arm == 2] = 1 - y2[arm == 2]  # perturb only the W arm labels
    m2 = md.TLearner(cfg, 1.0).fit(cov, arm, y2)
    assert m1.params[0] == m2.params[0] and m1.params[1] == m2.params[1]
    assert m1.params[2] != m2.params[2]
    p = m1.predict_all(cov)
    assert np.allclose(m1.predict_observed(cov, arm), p[np.arange(len(arm)), arm])


def test_model_round_trip_through_json(cfg, toy_frame):
    cov = toy_frame[COV_COLS]
    for kind in ("s_learner", "t_learner"):
        m = md.LEARNERS[kind](cfg, 1.0).fit(cov, toy_frame.arm.to_numpy(), toy_frame.visit.to_numpy())
        r = md.model_from_dict(cfg, m.to_dict())
        assert np.array_equal(m.predict_all(cov), r.predict_all(cov))
        assert md.model_identity(m.to_dict()) == md.model_identity(r.to_dict())


def test_cv_is_fold_local_and_grid_matches_config(cfg, toy_frame):
    cov, arm, y = toy_frame[COV_COLS], toy_frame.arm.to_numpy(), toy_frame.visit.to_numpy()
    folds = md.cv_folds(arm, 3, 123)
    for k in range(3):
        counts = np.bincount(arm[folds == k], minlength=3)
        assert counts.max() - counts.min() <= 1  # arm-stratified
    per_fold, summ = md.cross_validate("s_learner", cov, arm, y, cfg["models"]["C_grid"], folds, cfg)
    assert sorted(summ.C) == sorted(cfg["models"]["C_grid"]) and len(per_fold) == 9
    assert (per_fold.n_train_fold + per_fold.n_heldout == len(y)).all()


def test_select_C_tie_rule():
    s = pd.DataFrame({"C": [0.1, 1.0, 10.0], "mean_logloss": [0.40000005, 0.4, 0.39]})
    assert md.select_C(s, 1e-6) == 10.0
    s = pd.DataFrame({"C": [0.1, 1.0, 10.0], "mean_logloss": [0.4000005, 0.4, 0.4000001]})
    assert md.select_C(s, 1e-6) == 0.1


def test_t_learner_gate_can_fail(cfg, toy_frame):
    cov, arm, y = toy_frame[COV_COLS], toy_frame.arm.to_numpy(), toy_frame.visit.to_numpy().copy()
    y[:] = 0
    y[:30] = 1
    gate = md.t_learner_gate(cov, arm, y, cfg)
    assert not gate["support_passed"]


def test_label_perturbation_outside_training_cannot_change_model(cfg, toy_frame):
    tr = toy_frame.iloc[:600]
    m1 = md.SLearner(cfg, 1.0).fit(tr[COV_COLS], tr.arm.to_numpy(), tr.visit.to_numpy())
    other = toy_frame.iloc[600:].copy()
    other["visit"] = 1 - other["visit"]
    m2 = md.SLearner(cfg, 1.0).fit(tr[COV_COLS], tr.arm.to_numpy(), tr.visit.to_numpy())
    assert m1.to_dict() == m2.to_dict()
    assert np.array_equal(m1.predict_all(other[COV_COLS]), m2.predict_all(toy_frame.iloc[600:][COV_COLS]))
