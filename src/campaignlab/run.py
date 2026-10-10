"""CampaignLab pipeline CLI.

    python -m campaignlab.run <stage>      stages: acquire validate develop fit select lock evaluate release report simulate all

Information flow (frozen): split first; DEVELOPMENT inference is provisional; TRAIN fits; VALIDATION
selects; the lock is written before TEST outcomes are read; TEST is evaluated once against the
verified lock; only then are full-sample results released.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import data as dt
from . import evaluation as ev
from . import governance as gov
from . import inference as inf
from . import models as md
from . import policy as pl
from .config import ARM_NAMES, PRIVATE_DIR, ROOT, TABLES_DIR, load_config, rng_for, seed_int_for

MODELS_DIR = PRIVATE_DIR / "models"
SELECTION_PATH = PRIVATE_DIR / "selection.json"
THRESHOLDS_PATH = PRIVATE_DIR / "frozen_thresholds.json"
CONST_NAME = {0: "const_0", 1: "const_M", 2: "const_W"}


def dev_scope(n: int) -> str:
    return f"DEVELOPMENT (TRAIN+VALIDATION, N={n:,}) - provisional"


def full_scope(n: int) -> str:
    return f"FULL SAMPLE (N={n:,}) - released after policy lock and TEST evaluation"


def table_dir(name: str) -> Path:
    p = TABLES_DIR / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_table(df: pd.DataFrame, folder: str, name: str) -> None:
    df.to_csv(table_dir(folder) / f"{name}.csv", index=False, lineterminator="\n")


def dataset_sha(cfg) -> str:
    return gov.read_json(dt.PROVENANCE_PATH)["sha256"]


# =========================================================================== M1 / M2

def stage_acquire(cfg):
    m = dt.acquire(cfg)
    gov.mark_stage("acquire", sha256=m["sha256"], bytes=m["bytes"])


def stage_validate(cfg):
    gov.require_stage("acquire")
    raw = dt.read_verified_bytes(cfg)
    text = dt.parse_source(raw, cfg)
    typed, py_checks = dt.type_and_validate(text, cfg)
    dt.assert_contract(py_checks)
    split = dt.assign_split(typed["row_id"], typed["arm"], cfg)
    split_meta = dt.write_split_manifest(split, cfg, gov.sha256_bytes(raw))
    sql = dt.build_database(cfg, text, split)
    dt.assert_contract(sql["sql_checks"])

    quality = dt.global_quality(typed)
    expected = cfg["dataset"]["expected_quality"]
    mismatch = {k: (quality.get(k), v) for k, v in expected.items() if quality.get(k) != v}
    if mismatch:
        raise dt.ContractError(f"pinned-artifact quality facts differ: {mismatch}")
    sql_q = sql["sql_quality"]
    agree_keys = ["global_visits", "global_conversions", "positive_spend_rows", "full_row_match_groups", "full_row_match_excess",
                  "distinct_pretreatment_profiles", "pretreatment_profile_excess", "history_bucket_boundary_disagreements"]
    agreement = {k: sql_q[k] == quality[k] for k in agree_keys}
    agreement["total_history_cents"] = sql_q["total_history_cents"] == int(typed["history_cents"].sum())
    agreement["split_totals"] = all(sql_q[f"split_{p}"] == split_meta["check"]["totals"][p] for p in ("TRAIN", "VALIDATION", "TEST"))
    if not all(agreement.values()):
        raise dt.ContractError(f"SQL/Python disagreement: {agreement}")

    checks = pd.DataFrame([{"check": k, "python_failures": py_checks.get(k), "sql_failures": sql["sql_checks"].get(k)}
                           for k in sorted(set(py_checks) | set(sql["sql_checks"]))])
    write_table(checks, "data", "contract_checks")
    write_table(dt.history_bucket_disagreements(typed), "data", "history_bucket_boundary_cases")
    counts = dt.split_counts(split).reset_index()
    counts["arm"] = counts["arm"].map(ARM_NAMES)
    counts.loc[len(counts)] = ["Total", *counts[["TRAIN", "VALIDATION", "TEST"]].sum().tolist()]
    write_table(counts, "data", "split_counts")
    write_table(inf.allocation_table(typed["arm"].to_numpy(), "FULL SAMPLE assignment (X/A only)"), "data", "allocation")
    gov.write_json(table_dir("data") / "data_quality.json", {
        "dataset_sha256": gov.sha256_bytes(raw), "bytes": len(raw), "rows": quality["rows"], "columns": len(cfg["dataset"]["expected_columns"]),
        "quality": quality, "sql_python_agreement": agreement,
        "split": {"totals": split_meta["check"]["totals"], "by_arm": split_meta["check"]["by_arm"],
                  "disjoint": split_meta["check"]["disjoint"], "complete": split_meta["check"]["complete"]},
        "exclusions": f"none (all {quality['rows']:,} rows retained; matching rows and bucket-boundary cases kept)",
        "scope_note": "Global contract counts only; no arm-by-outcome summary is produced at this stage.",
    })
    gov.mark_stage("validate", split_membership_checksum=split_meta["membership_checksum"])


# =========================================================================== M3 / M4 (development, provisional)

def stage_develop(cfg):
    gov.require_stage("validate")
    store = dt.Store(cfg, "develop")
    sha = dataset_sha(cfg)
    dev = store.frame("development")
    exp = cfg["split"]["expected_totals"]
    if len(dev) != exp["TRAIN"] + exp["VALIDATION"] or set(dev["partition"]) != {"TRAIN", "VALIDATION"}:
        raise gov.AccessError("development frame is not exactly TRAIN + VALIDATION")
    DEV_SCOPE = dev_scope(len(dev))
    out = "development"

    sql_summary = store.sql("02_development_summary.sql")
    write_table(sql_summary, out, "sql_arm_summary")
    py = inf.arm_summary(dev, DEV_SCOPE)
    sqld = sql_summary[sql_summary["sample_scope"] == "DEVELOPMENT"].sort_values("arm")
    agree = {
        "n": bool(np.array_equal(sqld["n_rows"].to_numpy(), py["n"].to_numpy())),
        "visits": bool(np.array_equal(sqld["visits"].to_numpy(), py["visit_events"].to_numpy())),
        "conversions": bool(np.array_equal(sqld["conversions"].to_numpy(), py["conversion_events"].to_numpy())),
        "spend_cents": bool(np.array_equal(sqld["spend_cents"].to_numpy(), [int(dev.loc[dev.arm == a, "spend_cents"].sum()) for a in (0, 1, 2)])),
        "visit_mean": bool(np.allclose(sqld["visit_rate"], py["visit_mean"], rtol=1e-12, atol=1e-12)),
        "spend_mean": bool(np.allclose(sqld["spend_mean"], py["spend_mean"], rtol=1e-10, atol=1e-10)),
        "visit_var": bool(np.allclose(sqld["visit_var"], py["visit_sd"] ** 2, rtol=1e-10, atol=1e-12)),
    }
    if not all(agree.values()):
        raise RuntimeError(f"development SQL/Python disagreement: {agree}")
    write_table(py, out, "arm_summary")

    effects = inf.effect_table(dev, cfg, DEV_SCOPE, sha)
    write_table(effects, out, "itt_effects")
    write_table(_newcombe(dev, DEV_SCOPE), out, "conversion_newcombe")
    boot = inf.bootstrap_table(dev, "spend", cfg["inference"]["bootstrap_development_replicates"], rng_for(cfg, "bootstrap_development"), DEV_SCOPE)
    write_table(boot, out, "spend_bootstrap")

    adj, diag = inf.adjusted_table(dev, cfg, DEV_SCOPE)
    write_table(adj, out, "adjusted_ols")
    gov.write_json(table_dir(out) / "adjusted_ols_diagnostics.json", diag)
    write_table(inf.profile_cluster_table(dev, dt.profile_ids(dev), DEV_SCOPE), out, "profile_cluster")

    train = dev[dev["partition"] == "TRAIN"]
    q = cfg["inference"]["winsor_quantile"]
    thresholds = {"winsor_quantile": q,
                  "spend_all_train_rows": float(np.quantile(train["spend"], q)),
                  "spend_positive_train_rows": float(np.quantile(train.loc[train["spend"] > 0, "spend"], q)),
                  "estimated_on": "TRAIN only (numpy linear-interpolation quantile)", "frozen_at_stage": "develop (before lock)"}
    gov.write_json(THRESHOLDS_PATH, thresholds)
    write_table(_winsor_table(dev, thresholds, DEV_SCOPE), out, "spend_winsor")

    het = []
    sub_rows = []
    for g in cfg["inference"]["heterogeneity_groupings"] + cfg["inference"]["heterogeneity_optional_groupings"]:
        optional = g in cfg["inference"]["heterogeneity_optional_groupings"]
        s, h = inf.subgroup_table(dev, g, DEV_SCOPE, cfg["inference"]["subgroup_min_rows"], cfg["inference"]["subgroup_min_visits"], optional)
        sub_rows.append(s)
        het.append(h)
    write_table(pd.concat(sub_rows), out, "heterogeneity_subgroups")
    write_table(pd.concat(het), out, "heterogeneity_tests")

    perm = _permutation_rows(dev, cfg, rng_for(cfg, "permutation"), DEV_SCOPE)
    write_table(perm, out, "randomization_inference")

    cov_all = store.covariates()
    asg = store.assignment()
    write_table(inf.balance_table(cov_all, asg["arm"].to_numpy(), "FULL SAMPLE (X/A only)"), out, "balance_full_sample")
    write_table(inf.balance_table(dev, dev["arm"].to_numpy(), DEV_SCOPE), out, "balance_development")
    gov.mark_stage("develop", n=len(dev), sql_python_agreement=agree)


def _newcombe(df, scope):
    rows = []
    for t in (1, 2):
        yt = df.loc[df.arm == t, "conversion"]
        yc = df.loc[df.arm == 0, "conversion"]
        lo, hi = inf.newcombe_interval(int(yt.sum()), len(yt), int(yc.sum()), len(yc))
        r = inf.mean_difference(yt, yc)
        rows.append({"sample_scope": scope, "contrast": f"{'M' if t == 1 else 'W'} - 0", "events_treat": int(yt.sum()), "n_treat": len(yt),
                     "events_control": int(yc.sum()), "n_control": len(yc), "estimate": r["estimate"],
                     "wald_ci_low": r["ci_low"], "wald_ci_high": r["ci_high"], "newcombe_ci_low": lo, "newcombe_ci_high": hi,
                     "note": "Newcombe hybrid-score interval: binary-interval sensitivity for sparse conversions"})
    return pd.DataFrame(rows)


def _winsor_table(df, thresholds, scope):
    rows = []
    for label, key in (("raw (primary)", None), ("winsorized at TRAIN 99.5th pct, all rows", "spend_all_train_rows"),
                       ("winsorized at TRAIN 99.5th pct, positive spend", "spend_positive_train_rows")):
        y = df["spend"].to_numpy(float) if key is None else inf.winsorized(df["spend"], thresholds[key])
        for t in (1, 2):
            r = inf.mean_difference(y[df.arm.to_numpy() == t], y[df.arm.to_numpy() == 0])
            rows.append({"sample_scope": scope, "version": label, "threshold": None if key is None else thresholds[key],
                         "contrast": f"{'M' if t == 1 else 'W'} - 0", "estimate": r["estimate"], "se": r["se"],
                         "ci_low": r["ci_low"], "ci_high": r["ci_high"], "p_raw": r["p_value"],
                         "rows_capped": 0 if key is None else int((df["spend"] > thresholds[key]).sum()),
                         "estimand_note": "raw mean is primary" if key is None else "different (winsorized) estimand; sensitivity only"})
    return pd.DataFrame(rows)


def _permutation_rows(df, cfg, rng, scope):
    rows = []
    for t in (1, 2):
        r = inf.permutation_test_binary(df.loc[df.arm == t, "visit"], df.loc[df.arm == 0, "visit"], cfg["inference"]["permutation_draws"], rng)
        rows.append({"sample_scope": scope, "outcome": "visit", "contrast": f"{'M' if t == 1 else 'W'} - 0", **r})
    return pd.DataFrame(rows)


# =========================================================================== M5 (TRAIN fitting)

def stage_fit(cfg):
    gov.require_stage("develop")
    store = dt.Store(cfg, "fit")
    train = store.frame("train")
    cov = train[["row_id"] + dt.PRETREATMENT_RAW]
    arm, y = train["arm"].to_numpy(), train["visit"].to_numpy()
    mcfg = cfg["models"]
    folds = md.cv_folds(arm, mcfg["cv_folds"], seed_int_for(cfg, "cv"))
    out = "models"
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    cv_rows, cv_summ, fitted, status = [], [], {}, {}
    gate = md.t_learner_gate(cov, arm, y, cfg)
    write_table(pd.DataFrame(gate["checks"]), out, "t_learner_gate")
    for kind in ("s_learner", "t_learner"):
        if kind == "t_learner" and not gate["support_passed"]:
            status[kind] = {"included": False, "reason": "support gate failed"}
            continue
        per_fold, summ = md.cross_validate(kind, cov, arm, y, mcfg["C_grid"], folds, cfg)
        C = md.select_C(summ, mcfg["tie_tolerance"])
        model = md.LEARNERS[kind](cfg, C).fit(cov, arm, y)
        cv_rows.append(per_fold)
        summ["selected"] = summ["C"] == C
        cv_summ.append(summ)
        cv_conv = bool(per_fold.loc[per_fold["C"] == C, "converged"].all())
        if kind == "t_learner" and not (model.converged and cv_conv):
            status[kind] = {"included": False, "reason": "convergence gate failed", "C": C}
            continue
        if kind == "s_learner" and not model.converged:
            raise RuntimeError("primary S-learner failed to converge; investigate before continuing")
        d = model.to_dict()
        gov.write_json(MODELS_DIR / f"{kind}.json", d)
        fitted[kind] = model
        status[kind] = {"included": True, "C": C, "converged": model.converged, "model_sha256": md.model_identity(d)}
        write_table(md.coefficient_table(d), out, f"{kind}_coefficients")
    write_table(pd.concat(cv_rows), out, "cv_folds")
    write_table(pd.concat(cv_summ), out, "cv_summary")
    gov.write_json(table_dir(out) / "learner_status.json", {"t_learner_gate_support_passed": gate["support_passed"], **status})

    # diagnostics: TRAIN-CV (above) and VALIDATION response prediction (not uplift quality)
    val = store.frame("validation")
    vcov = val[["row_id"] + dt.PRETREATMENT_RAW]
    summaries, calib = [], []
    for kind, model in fitted.items():
        s, c = md.response_diagnostics(model, vcov, val["arm"].to_numpy(), val["visit"].to_numpy(), "VALIDATION")
        summaries.append(s)
        calib.append(c)
    write_table(pd.DataFrame(summaries), out, "validation_response_diagnostics")
    write_table(pd.concat(calib), out, "validation_calibration")

    _development_model_diagnostics(cfg, store, train, folds, fitted["s_learner"].C)
    gov.mark_stage("fit", status=status)


def _development_model_diagnostics(cfg, store, train, folds, C):
    """Development-only diagnostics: profile-grouped CV, coarse history encoding, main-effects ablation, resplit stability."""
    out = "models"
    cov = train[["row_id"] + dt.PRETREATMENT_RAW]
    arm, y = train["arm"].to_numpy(), train["visit"].to_numpy()
    rows = []
    _, base = md.cross_validate("s_learner", cov, arm, y, [C], folds, cfg)
    rows.append({"diagnostic": "S-learner, arm-stratified 3-fold CV (selected C)", "C": C, "mean_logloss": float(base["mean_logloss"].iloc[0])})
    gfolds = md.cv_folds(arm, cfg["models"]["cv_folds"], seed_int_for(cfg, "cv"), groups=dt.profile_ids(train))
    _, grp = md.cross_validate("s_learner", cov, arm, y, [C], gfolds, cfg)
    rows.append({"diagnostic": "S-learner, profile-grouped 3-fold CV (identical profiles kept together)", "C": C,
                 "mean_logloss": float(grp["mean_logloss"].iloc[0])})
    desc = store.descriptive()
    cov_seg = cov.merge(desc, on="row_id", how="left", validate="one_to_one")
    _, seg = md.cross_validate("s_learner", cov_seg, arm, y, [C], folds, cfg, encoding="coarse_segment")
    rows.append({"diagnostic": "S-learner with history_segment indicators instead of log(1+history) (encoding diagnostic)", "C": C,
                 "mean_logloss": float(seg["mean_logloss"].iloc[0])})
    _, me = md.cross_validate("s_learner", cov, arm, y, [C], folds, cfg, interactions=False)
    rows.append({"diagnostic": "Main-effects-only S-learner (instructional ablation)", "C": C, "mean_logloss": float(me["mean_logloss"].iloc[0])})
    ablation = md.SLearner(cfg, C, interactions=False).fit(cov, arm, y)
    val_cov = store.frame("validation")[["row_id"] + dt.PRETREATMENT_RAW]
    acts, _ = pl.best_gain_actions(ablation.predict_all(val_cov), 0.0)
    shares = {ARM_NAMES[a]: float((acts == a).mean()) for a in (0, 1, 2)}
    rows.append({"diagnostic": f"Main-effects-only S-learner VALIDATION action shares at q=1,kappa=0: {shares}", "C": C, "mean_logloss": np.nan})
    write_table(pd.DataFrame(rows), out, "development_model_diagnostics")
    write_table(_resplit_stability(cfg, store, C), out, "development_resplit_stability")


def _resplit_stability(cfg, store, C):
    """Development-only: refit the S-learner on alternative 75/25 resplits of DEVELOPMENT (training-procedure variability)."""
    dev = store.frame("development")
    cov = dev[["row_id"] + dt.PRETREATMENT_RAW]
    arm, y = dev["arm"].to_numpy(), dev["visit"].to_numpy()
    primary = md.SLearner.from_dict(cfg, gov.read_json(MODELS_DIR / "s_learner.json"))
    tmpl = cfg["development_diagnostics"]["stability_key_template"]
    rows = []
    for k in range(1, cfg["development_diagnostics"]["stability_resplits"] + 1):
        keys = np.asarray(gov.hash_strings([tmpl.format(k=k, row_id=r) for r in dev["row_id"]]), dtype="U64")
        is_train = np.zeros(len(dev), bool)
        for a in (0, 1, 2):
            idx = np.flatnonzero(arm == a)
            order = idx[np.lexsort((dev["row_id"].to_numpy()[idx].astype(str), keys[idx]))]
            is_train[order[: (len(idx) * 75) // 100]] = True
        m = md.SLearner(cfg, C).fit(cov[is_train].reset_index(drop=True), arm[is_train], y[is_train])
        vcov = cov[~is_train].reset_index(drop=True)
        va, vy = arm[~is_train], y[~is_train]
        s_act, _ = pl.best_gain_actions(m.predict_all(vcov), 0.0)
        p_act, _ = pl.best_gain_actions(primary.predict_all(vcov), 0.0)
        consts = {a: ev.ipw_value(pl.constant_actions(len(va), a), va, vy) for a in (0, 1, 2)}
        cstar = ev.select_constant(consts, cfg["policy"]["constant_tie_order"], cfg["models"]["tie_tolerance"])["selected"]
        d = ev.paired_difference(s_act, pl.constant_actions(len(va), cstar), va, vy)
        rule = pl.fixed_rule_actions(vcov)
        dr = ev.paired_difference(s_act, rule, va, vy)
        rows.append({"resplit": k, "n_alt_train": int(is_train.sum()), "n_alt_validation": int((~is_train).sum()),
                     "converged": m.converged, "alt_best_constant": ARM_NAMES[cstar],
                     "s_minus_best_constant": d["estimate"], "s_minus_best_constant_se": d["se"],
                     "s_minus_fixed_rule": dr["estimate"], "s_minus_fixed_rule_se": dr["se"],
                     "s_share_M": float((s_act == 1).mean()), "s_share_W": float((s_act == 2).mean()), "s_share_none": float((s_act == 0).mean()),
                     "action_agreement_with_primary_model": float((s_act == p_act).mean()),
                     "scope": "DEVELOPMENT-only resplit (exploratory; training-procedure variability, not TEST evidence)"})
    return pd.DataFrame(rows)


# =========================================================================== M6a (VALIDATION selection)

def _load_models(cfg) -> dict:
    out = {}
    for kind in ("s_learner", "t_learner"):
        p = MODELS_DIR / f"{kind}.json"
        if p.exists():
            out[kind] = md.model_from_dict(cfg, gov.read_json(p))
    return out


def stage_select(cfg):
    gov.require_stage("fit")
    store = dt.Store(cfg, "select")
    val = store.frame("validation")
    cov = val[["row_id"] + dt.PRETREATMENT_RAW]
    A, Y = val["arm"].to_numpy(), val["visit"].to_numpy()
    models = _load_models(cfg)
    preds = {k: m.predict_all(cov) for k, m in models.items()}
    acts = pl.main_policy_actions(cov, preds, cfg)
    pol = cfg["policy"]
    consts = {a: ev.ipw_value(acts[CONST_NAME[a]], A, Y) for a in (0, 1, 2)}
    cstar = ev.select_constant(consts, pol["constant_tie_order"], cfg["models"]["tie_tolerance"])
    candidates = {k: acts[k] for k in pol["targeting_simplicity_order"] if k in acts}
    tsel = ev.select_targeting(candidates, A, Y, pol["targeting_simplicity_order"])
    comparator = CONST_NAME[cstar["selected"]]
    rows = []
    for name, a in acts.items():
        v = ev.value_with_se(a, A, Y)
        d = ev.paired_difference(a, acts[comparator], A, Y)
        rows.append({"sample_scope": f"VALIDATION (N={len(val):,})", "policy": name, "ipw_value": v["value"], "value_se": v["se"],
                     "contact_rate": float((a > 0).mean()), "share_M": float((a == 1).mean()), "share_W": float((a == 2).mean()),
                     "diff_vs_C_star": d["estimate"], "diff_se": d["se"], "diff_ci_low": d["ci_low"], "diff_ci_high": d["ci_high"],
                     "role": "constant" if name.startswith("const") else "targeting candidate"})
    write_table(pd.DataFrame(rows), "validation", "validation_policy_values")
    write_table(pd.DataFrame(tsel["log"]), "validation", "targeting_selection_log")
    selection = {"constant_comparator": comparator, "constant_selection": cstar, "pi_star": tsel["selected"],
                 "targeting_selection": tsel, "selected_on": "VALIDATION outcomes only"}
    gov.write_json(SELECTION_PATH, selection)
    gov.write_json(table_dir("validation") / "selection.json", selection)
    gov.mark_stage("select", pi_star=selection["pi_star"], constant_comparator=comparator)


# =========================================================================== M6b (lock)

def _test_covariates(store) -> pd.DataFrame:
    """TEST covariates only: rows chosen by split membership; no arm or outcome column is passed on."""
    asg = store.assignment()
    test_ids = set(asg.loc[asg["partition"] == "TEST", "row_id"])
    cov = store.covariates()
    cov = cov[cov["row_id"].isin(test_ids)].sort_values("source_ordinal", kind="mergesort").reset_index(drop=True)
    return cov[["row_id"] + dt.PRETREATMENT_RAW]


def _locked_actions(cfg, cov, models):
    preds = {k: m.predict_all(cov) for k, m in models.items()}
    main = pl.main_policy_actions(cov, preds, cfg)
    grid = pl.scenario_policy_actions(cov, preds, cfg)
    return preds, main, grid


def _lock_payload(cfg) -> dict:
    store = dt.Store(cfg, "lock")
    cov = _test_covariates(store)
    models = _load_models(cfg)
    preds, main, grid = _locked_actions(cfg, cov, models)
    sel = gov.read_json(SELECTION_PATH)
    split_meta = gov.read_json(dt.SPLIT_MANIFEST_JSON)
    model_dicts = {k: gov.read_json(MODELS_DIR / f"{k}.json") for k in models}
    dr_nuisance = "t_learner" if sel["pi_star"] == "t_learner" else "s_learner"
    return {
        "plan_version": cfg["plan_version"],
        "dataset": {"sha256": dataset_sha(cfg), "provenance_manifest_sha256": gov.sha256_file(dt.PROVENANCE_PATH)},
        "split": {"manifest_csv_sha256": split_meta["manifest_csv_sha256"], "membership_checksum": split_meta["membership_checksum"],
                  "totals": split_meta["check"]["totals"]},
        "code_sha256": gov.code_hashes(),
        "config_sha256": gov.config_hash(),
        "environment": {k: v for k, v in gov.environment_record().items() if k in ("python", "packages", "requirements_lock_sha256")},
        "models": {k: {"sha256_params": md.model_identity(d), "C": d["C"], "kind": d["kind"],
                       "file_sha256": gov.sha256_file(MODELS_DIR / f"{k}.json")} for k, d in model_dicts.items()},
        "learner_status": gov.read_json(TABLES_DIR / "models" / "learner_status.json"),
        "selection": {"constant_comparator": sel["constant_comparator"], "pi_star": sel["pi_star"],
                      "selection_file_sha256": gov.sha256_file(SELECTION_PATH)},
        "non_selected_candidates_reported_as_secondary": [k for k in cfg["policy"]["targeting_simplicity_order"]
                                                          if k in main and k != sel["pi_star"]],
        "practical_margin_delta": cfg["policy"]["practical_margin_delta"],
        "scenario_grid": {"q": cfg["policy"]["q_grid"], "kappa": cfg["policy"]["kappa_grid"], "main": cfg["policy"]["main"],
                          "economics": cfg["economics"]},
        "uncertainty_protocol": {"ordinary": "paired stratified SE, normal 95%", "bootstrap_replicates": cfg["evaluation"]["bootstrap_replicates"],
                                 "stability_extra_replicates": cfg["evaluation"]["stability_extra_replicates"],
                                 "constant_family": "one-sided Bonferroni lower bounds, z_(1-0.05/3)",
                                 "seeds": cfg["seeds"], "nominal_sensitivity": "Horvitz-Thompson with e(a)=1/3",
                                 "dr_nuisance_model": dr_nuisance, "profile_cluster_sensitivity": True},
        "frozen_thresholds": gov.read_json(THRESHOLDS_PATH),
        "test_rows": {"n": int(len(cov)), "row_id_checksum": gov.vector_checksum(cov["row_id"], range(len(cov)))},
        "test_prediction_checksums": {k: {str(a): gov.vector_checksum(cov["row_id"], p[:, a]) for a in (0, 1, 2)} for k, p in preds.items()},
        "test_action_checksums": {**{f"main:{k}": gov.vector_checksum(cov["row_id"], v) for k, v in main.items()},
                                  **{f"grid:{k}": gov.vector_checksum(cov["row_id"], v) for k, v in grid.items()}},
        "test_contact_counts": {**{f"main:{k}": int((v > 0).sum()) for k, v in main.items()},
                                **{f"grid:{k}": int((v > 0).sum()) for k, v in grid.items()}},
    }


def stage_lock(cfg):
    gov.require_stage("select")
    if gov.EVAL_RECORD_PATH.exists():
        raise gov.AccessError("TEST evaluation already recorded; a new lock would not be a pre-unblinding lock")
    payload = _lock_payload(cfg)
    payload["created_utc"] = gov.utc_now()
    payload["note"] = "Written before any TEST outcome was loaded. Evaluation accepts only this manifest."
    lock_sha = gov.write_json(gov.LOCK_PATH, payload)
    gov.mark_stage("lock", lock_sha256=gov.sha256_file(gov.LOCK_PATH))
    print(f"lock written: {gov.LOCK_PATH} ({lock_sha})")


def verify_lock(cfg) -> gov.TestAccessToken:
    if not gov.LOCK_PATH.exists():
        raise gov.AccessError("missing lock manifest; run the lock stage before evaluation")
    locked = gov.read_json(gov.LOCK_PATH)
    current = _lock_payload(cfg)
    mismatches = [k for k in current if gov.canonical_json(current[k]) != gov.canonical_json(locked.get(k))]
    if mismatches:
        raise gov.AccessError(f"lock verification failed; changed components: {mismatches}")
    sha = gov.sha256_file(gov.LOCK_PATH)
    gov.mark_stage("lock_verified", lock_sha256=sha)
    return gov.TestAccessToken(sha)


# =========================================================================== M6c (TEST evaluation)

def stage_evaluate(cfg):
    gov.require_stage("lock")
    token = verify_lock(cfg)
    lock = gov.read_json(gov.LOCK_PATH)
    store = dt.Store(cfg, "evaluate")
    cov = _test_covariates(store)
    models = _load_models(cfg)
    preds, main, grid = _locked_actions(cfg, cov, models)
    test = store.frame("test", token)
    if not np.array_equal(test["row_id"].to_numpy(), cov["row_id"].to_numpy()):
        raise RuntimeError("TEST outcome rows are not aligned with locked action rows")
    A, Y, S = test["arm"].to_numpy(), test["visit"].to_numpy(float), test["spend"].to_numpy(float)
    profiles = dt.profile_ids(test)
    pi_star, cstar = lock["selection"]["pi_star"], lock["selection"]["constant_comparator"]
    delta = lock["practical_margin_delta"]
    m_dr = preds[lock["uncertainty_protocol"]["dr_nuisance_model"]]
    out = "final"
    scope = f"TEST (N={len(test):,}), locked policies"

    # ---- values for every q=1, kappa=0 policy
    names = list(main.keys())
    rows, support = [], []
    for name in names:
        a = main[name]
        v = ev.value_with_se(a, A, Y)
        role = ("selected targeting policy (pi*)" if name == pi_star else "frozen comparator (C*)" if name == cstar
                else "constant" if name.startswith("const") else "targeting candidate, NOT selected (secondary)")
        rows.append({"sample_scope": scope, "policy": name, "role": role, "ipw_value": v["value"], "value_se": v["se"],
                     "ci_low": v["ci_low"], "ci_high": v["ci_high"], "ht_nominal_value": ev.ht_value_nominal(a, A, Y),
                     "dr_value": float(ev.dr_contributions(a, A, Y, m_dr).mean()), "contact_rate": float((a > 0).mean()),
                     "share_M": float((a == 1).mean()), "share_W": float((a == 2).mean()),
                     "spend_ipw_value": ev.ipw_value(a, A, S)})
        support += ev.support_table(name, a, A, Y, "visit") + ev.support_table(name, a, A, S, "spend (positive-spend events)")
    write_table(pd.DataFrame(rows), out, "policy_values")
    write_table(pd.DataFrame(support), out, "policy_support")

    # ---- paired bootstrap (all main policies, same resampled rows)
    ecfg = cfg["evaluation"]
    Cmat = np.column_stack([ev.contributions(main[n], A, Y) for n in names])
    B1 = ev.paired_bootstrap(Cmat, A, ecfg["bootstrap_replicates"], rng_for(cfg, "policy_bootstrap"), batch=ecfg["bootstrap_batch"])
    B2 = ev.paired_bootstrap(Cmat, A, ecfg["stability_extra_replicates"], rng_for(cfg, "policy_bootstrap_stability"), batch=ecfg["bootstrap_batch"])
    Dmat = np.column_stack([ev.dr_contributions(main[n], A, Y, m_dr) for n in names])
    w_dr = ev.dr_arm_weights(A)
    BD = ev.paired_bootstrap(Dmat, A, ecfg["bootstrap_replicates"], rng_for(cfg, "policy_bootstrap"), arm_weights=w_dr, batch=ecfg["bootstrap_batch"])
    col = {n: i for i, n in enumerate(names)}

    comparisons = []
    targets = [pi_star] + [k for k in lock["non_selected_candidates_reported_as_secondary"]]
    for target in targets:
        for base in [cstar] + [c for c in ("const_0", "const_M", "const_W") if c != cstar]:
            comparisons.append(_comparison_row(target, base, main, A, Y, S, profiles, m_dr, B1, B2, BD, col, delta, pi_star, cstar, scope))
        if target != "fixed_rule":
            comparisons.append(_comparison_row(target, "fixed_rule", main, A, Y, S, profiles, m_dr, B1, B2, BD, col, delta, pi_star, cstar, scope))
    comp = pd.DataFrame(comparisons)
    write_table(comp, out, "policy_comparisons")

    fam_rows = comp[(comp["policy"] == pi_star) & comp["baseline"].isin(["const_0", "const_M", "const_W"])]
    family = ev.constant_family_bounds({r.baseline: {"estimate": r.estimate, "se": r.se} for r in fam_rows.itertuples()}, delta,
                                       cfg["evaluation"]["constant_family_alpha"])
    primary = comp[(comp["policy"] == pi_star) & (comp["baseline"] == cstar)].iloc[0]
    sens_cats = {"analytic_95": primary["decision_category"], "bootstrap_95": primary["decision_category_bootstrap"],
                 "nominal_ht": primary["decision_category_ht"], "doubly_robust": primary["decision_category_dr"],
                 "profile_clustered": primary["decision_category_clustered"]}
    decision = {"pi_star": pi_star, "constant_comparator": cstar, "delta": delta,
                "primary_comparison": {k: (None if (isinstance(v, float) and np.isnan(v)) else v) for k, v in primary.to_dict().items()},
                "category": primary["decision_category"], "category_text": ev.DECISION_TEXT[primary["decision_category"]],
                "sensitivity_categories": sens_cats, "fragile": len(set(sens_cats.values())) > 1,
                "constant_family": family}
    gov.write_json(table_dir(out) / "policy_decision.json", decision)

    grid_df, econ_a, econ_b = _grid_tables(cfg, grid, A, Y, S, pi_star, lock)
    write_table(grid_df, out, "capacity_cost_grid")
    write_table(econ_a, out, "economics_panel_a_visit_value")
    write_table(econ_b, out, "economics_panel_b_spend_margin")

    stab = []
    for target in targets:
        for base in ("const_0", "const_M", "const_W"):
            d1 = B1[:, col[target]] - B1[:, col[base]]
            dall = np.concatenate([d1, B2[:, col[target]] - B2[:, col[base]]])
            lo1, hi1 = ev.percentile_ci(d1)
            lo2, hi2 = ev.percentile_ci(dall)
            stab.append({"policy": target, "baseline": base, "ci_low_5000": lo1, "ci_high_5000": hi1, "ci_low_10000": lo2, "ci_high_10000": hi2,
                         "max_endpoint_change_pp": 100 * max(abs(lo1 - lo2), abs(hi1 - hi2)),
                         "target_pp": cfg["evaluation"]["stability_target_pp"]})
    write_table(pd.DataFrame(stab), out, "bootstrap_stability")

    record = {"lock_sha256": token.lock_sha256, "completed_utc": gov.utc_now(),
              "result_table_sha256": {p.name: gov.sha256_file(p) for p in sorted(table_dir(out).glob("*")) if p.is_file()}}
    gov.write_json(gov.EVAL_RECORD_PATH, record)
    gov.mark_stage("evaluate", lock_sha256=token.lock_sha256)


def _comparison_row(target, base, main, A, Y, S, profiles, m_dr, B1, B2, BD, col, delta, pi_star, cstar, scope):
    d = ev.paired_difference(main[target], main[base], A, Y)
    boot = B1[:, col[target]] - B1[:, col[base]]
    blo, bhi = ev.percentile_ci(boot)
    ht = ev.ht_paired_difference(main[target], main[base], A, Y)
    dr = ev.dr_paired_difference(main[target], main[base], A, Y, m_dr)
    dlo, dhi = ev.percentile_ci(BD[:, col[target]] - BD[:, col[base]])
    diff_vec = ev.contributions(main[target], A, Y) - ev.contributions(main[base], A, Y)
    cl = ev.cluster_se_difference(diff_vec, A, profiles)
    cl_se = d["se"] * cl["ratio"] if np.isfinite(cl["ratio"]) else d["se"]
    sp = ev.paired_difference(main[target], main[base], A, S)
    role = "primary: pi* vs frozen C*" if (target == pi_star and base == cstar) else (
        "pi* vs constant (family member)" if target == pi_star and base.startswith("const") else
        "pi* vs fixed rule" if target == pi_star else "secondary: non-selected candidate")
    return {"sample_scope": scope, "policy": target, "baseline": base, "role": role,
            "estimate": d["estimate"], "estimate_pp": 100 * d["estimate"], "se": d["se"], "ci_low": d["ci_low"], "ci_high": d["ci_high"],
            "ci_low_pp": 100 * d["ci_low"], "ci_high_pp": 100 * d["ci_high"], "p_raw": d["p_value"], "status": d["status"],
            "boot_ci_low": blo, "boot_ci_high": bhi, "boot_se": float(boot.std(ddof=1)),
            "ht_nominal_estimate": ht["estimate"], "ht_ci_low": ht["ci_low"], "ht_ci_high": ht["ci_high"],
            "dr_estimate": dr["estimate"], "dr_se": dr["se"], "dr_ci_low": dr["ci_low"], "dr_ci_high": dr["ci_high"],
            "dr_boot_ci_low": dlo, "dr_boot_ci_high": dhi,
            "cluster_se_ratio": cl["ratio"], "clustered_ci_low": d["estimate"] - inf.Z95 * cl_se, "clustered_ci_high": d["estimate"] + inf.Z95 * cl_se,
            "decision_category": ev.decision_category(d["ci_low"], d["ci_high"], delta),
            "decision_category_bootstrap": ev.decision_category(blo, bhi, delta),
            "decision_category_ht": ev.decision_category(ht["ci_low"], ht["ci_high"], delta),
            "decision_category_dr": ev.decision_category(dr["ci_low"], dr["ci_high"], delta),
            "decision_category_clustered": ev.decision_category(d["estimate"] - inf.Z95 * cl_se, d["estimate"] + inf.Z95 * cl_se, delta),
            "spend_estimate": sp["estimate"], "spend_ci_low": sp["ci_low"], "spend_ci_high": sp["ci_high"],
            "contact_rate_policy": float((main[target] > 0).mean()), "contact_rate_baseline": float((main[base] > 0).mean())}


def _grid_tables(cfg, grid, A, Y, S, pi_star, lock):
    rows = []
    zero = next(acts for key, acts in grid.items() if key.startswith("const_0|"))
    for key, acts in grid.items():
        name, qs, ks = key.split("|")
        q, kappa_s = float(qs.split("=")[1]), ks.split("=")[1]
        kappas = cfg["policy"]["kappa_grid"] if kappa_s == "any" else [float(kappa_s)]
        v = ev.value_with_se(acts, A, Y)
        d0 = ev.paired_difference(acts, zero, A, Y)
        s0 = ev.paired_difference(acts, zero, A, S)
        contact = float((acts > 0).mean())
        for kappa in kappas:
            base = {}
            for bname in ("quota_M", "quota_W", "const_0"):
                bacts = grid[f"{bname}|q={q}|kappa=any"]
                bd = ev.paired_difference(acts, bacts, A, Y)
                bcontact = float((bacts > 0).mean())
                base[bname] = (bd["estimate"] - kappa * (contact - bcontact), bd["ci_low"] - kappa * (contact - bcontact),
                               bd["ci_high"] - kappa * (contact - bcontact))
            role = ("pi* (locked)" if name == pi_star else "feasible baseline" if name in ("const_0", "quota_M", "quota_W")
                    else "fixed rule (capped)" if name == "fixed_rule" else "non-selected learner (secondary)")
            rows.append({"sample_scope": f"TEST (N={len(A):,})", "policy": name, "role": role, "q": q, "kappa": kappa,
                         "action_depends_on_kappa": kappa_s != "any", "contacts": int((acts > 0).sum()), "contact_rate": contact,
                         "cap_floor_qN": pl.capacity_count(q, len(acts)), "visit_value": v["value"],
                         "delta_vs_no_send": d0["estimate"], "delta_vs_no_send_ci_low": d0["ci_low"], "delta_vs_no_send_ci_high": d0["ci_high"],
                         "net_utility_vs_no_send": d0["estimate"] - kappa * contact,
                         "net_utility_ci_low": d0["ci_low"] - kappa * contact, "net_utility_ci_high": d0["ci_high"] - kappa * contact,
                         **{f"net_vs_{b}": base[b][0] for b in base}, **{f"net_vs_{b}_ci_low": base[b][1] for b in base},
                         **{f"net_vs_{b}_ci_high": base[b][2] for b in base},
                         "spend_delta_vs_no_send": s0["estimate"], "spend_delta_ci_low": s0["ci_low"], "spend_delta_ci_high": s0["ci_high"],
                         "label": "exploratory frozen scenario; intervals conditional on this TEST cohort and fixed actions"})
    grid_df = pd.DataFrame(rows).sort_values(["kappa", "q", "policy"]).reset_index(drop=True)

    econ = cfg["economics"]
    a_rows = []
    for r in grid_df.itertuples():
        for b in econ["panel_a"]["value_per_visit_b"]:
            c = b * r.kappa
            a_rows.append({"policy": r.policy, "role": r.role, "q": r.q, "kappa": r.kappa, "b_value_per_visit": b, "c_cost_per_contact": c,
                           "contact_rate": r.contact_rate,
                           "net_value_per_customer": b * r.delta_vs_no_send - c * r.contact_rate,
                           "ci_low": b * r.delta_vs_no_send_ci_low - c * r.contact_rate,
                           "ci_high": b * r.delta_vs_no_send_ci_high - c * r.contact_rate,
                           "label": "HYPOTHETICAL engagement-value proxy (assumed b and c); not revenue or profit"})
    b_rows = []
    k0 = grid_df[grid_df["kappa"] == 0.0]
    for r in k0.itertuples():
        for m in econ["panel_b"]["margin_m"]:
            for c in econ["panel_b"]["contact_cost_c"]:
                b_rows.append({"policy": r.policy, "role": r.role, "q": r.q, "margin_m": m, "contact_cost_c": c, "contact_rate": r.contact_rate,
                               "spend_delta_vs_no_send": r.spend_delta_vs_no_send,
                               "proxy_per_customer": m * r.spend_delta_vs_no_send - c * r.contact_rate,
                               "ci_low": m * r.spend_delta_ci_low - c * r.contact_rate, "ci_high": m * r.spend_delta_ci_high - c * r.contact_rate,
                               "label": "HYPOTHETICAL margin-adjusted historical gross-spend proxy; not observed profit; do not add to Panel A"})
    return grid_df, pd.DataFrame(a_rows), pd.DataFrame(b_rows)


# =========================================================================== M6d (full-sample release)

def stage_release(cfg):
    gov.require_stage("evaluate")
    token = gov.issue_release_token()
    store = dt.Store(cfg, "release")
    full = store.frame("full", token)
    if len(full) != cfg["dataset"]["expected_rows"]:
        raise RuntimeError("full-sample frame does not reconcile with the pinned row count")
    FULL_SCOPE = full_scope(len(full))
    sha = dataset_sha(cfg)
    out = "final"
    sql = store.sql("03_final_experiment_summary.sql", token)
    write_table(sql, out, "sql_full_arm_summary")
    py = inf.arm_summary(full, FULL_SCOPE)
    agree = {"n": bool(np.array_equal(sql["n_rows"], py["n"])), "visits": bool(np.array_equal(sql["visits"], py["visit_events"])),
             "conversions": bool(np.array_equal(sql["conversions"], py["conversion_events"])),
             "spend_cents": bool(np.array_equal(sql["spend_cents"], [int(full.loc[full.arm == a, "spend_cents"].sum()) for a in (0, 1, 2)])),
             "visit_mean": bool(np.allclose(sql["visit_rate"], py["visit_mean"], rtol=1e-12, atol=1e-12)),
             "spend_mean": bool(np.allclose(sql["spend_mean"], py["spend_mean"], rtol=1e-10, atol=1e-10))}
    if not all(agree.values()):
        raise RuntimeError(f"final SQL/Python disagreement: {agree}")
    write_table(py, out, "full_arm_summary")
    effects = inf.effect_table(full, cfg, FULL_SCOPE, sha)
    write_table(effects, out, "full_itt_effects")
    write_table(_newcombe(full, FULL_SCOPE), out, "full_conversion_newcombe")
    B = cfg["inference"]["bootstrap_final_replicates"]
    boot = inf.bootstrap_table(full, "spend", B, rng_for(cfg, "bootstrap_final"), FULL_SCOPE)
    boot2 = inf.bootstrap_table(full, "spend", B, rng_for(cfg, "bootstrap_stability"), FULL_SCOPE)
    boot["stability_ci_low_second_5000"] = boot2["bootstrap_ci_low"].to_numpy()
    boot["stability_ci_high_second_5000"] = boot2["bootstrap_ci_high"].to_numpy()
    write_table(boot, out, "full_spend_bootstrap")
    adj, diag = inf.adjusted_table(full, cfg, FULL_SCOPE)
    write_table(adj, out, "full_adjusted_ols")
    gov.write_json(table_dir(out) / "full_adjusted_ols_diagnostics.json", diag)
    write_table(inf.profile_cluster_table(full, dt.profile_ids(full), FULL_SCOPE), out, "full_profile_cluster")
    write_table(_winsor_table(full, gov.read_json(THRESHOLDS_PATH), FULL_SCOPE), out, "full_spend_winsor")
    subs, hets = [], []
    for g in cfg["inference"]["heterogeneity_groupings"] + cfg["inference"]["heterogeneity_optional_groupings"]:
        optional = g in cfg["inference"]["heterogeneity_optional_groupings"]
        s, h = inf.subgroup_table(full, g, FULL_SCOPE, cfg["inference"]["subgroup_min_rows"], cfg["inference"]["subgroup_min_visits"], optional)
        subs.append(s)
        hets.append(h)
    write_table(pd.concat(subs), out, "full_heterogeneity_subgroups")
    write_table(pd.concat(hets), out, "full_heterogeneity_tests")
    write_table(_permutation_rows(full, cfg, rng_for(cfg, "permutation"), FULL_SCOPE), out, "full_randomization_inference")
    dev = pd.read_csv(TABLES_DIR / "development" / "itt_effects.csv")
    rep = effects[["outcome", "contrast", "family", "estimate", "ci_low", "ci_high"]].merge(
        dev[["outcome", "contrast", "family", "estimate", "ci_low", "ci_high"]], on=["outcome", "contrast", "family"], suffixes=("_full", "_development"))
    write_table(rep, out, "development_vs_full_itt")
    gov.mark_stage("release", sql_python_agreement=agree)


# =========================================================================== CLI

STAGES = {"acquire": stage_acquire, "validate": stage_validate, "develop": stage_develop, "fit": stage_fit, "select": stage_select,
          "lock": stage_lock, "evaluate": stage_evaluate, "release": stage_release}
ORDER = ["acquire", "validate", "develop", "fit", "select", "lock", "evaluate", "release", "report"]


def run_stage(name: str, cfg: dict) -> float:
    t0 = time.perf_counter()
    if name == "report":
        from . import reporting
        reporting.build_all(cfg)
    elif name == "simulate":
        from . import simulation
        simulation.run(cfg)
    else:
        STAGES[name](cfg)
    secs = time.perf_counter() - t0
    timings = PRIVATE_DIR / "stage_timings.jsonl"
    timings.parent.mkdir(parents=True, exist_ok=True)
    with open(timings, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"utc": gov.utc_now(), "stage": name, "seconds": round(secs, 3)}) + "\n")
    print(f"[campaignlab] {name}: {secs:.1f}s")
    return secs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=ORDER + ["simulate", "all"])
    args = parser.parse_args(argv)
    cfg = load_config()
    for name in (ORDER if args.stage == "all" else [args.stage]):
        run_stage(name, cfg)


if __name__ == "__main__":
    main()
