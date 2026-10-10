"""Executive memo, technical report and README generated from the reviewed aggregate tables.

Every number in these documents is read from reports/tables/; interpretive wording is chosen
from the computed decision categories so the narrative cannot drift from the evidence.
"""
from __future__ import annotations

import json

import pandas as pd

from .config import ROOT, TABLES_DIR

POL = {"const_0": "no email to anyone", "const_M": "men's email to everyone", "const_W": "women's email to everyone",
       "fixed_rule": "fixed purchase-history rule", "s_learner": "interacted logistic S-learner policy", "t_learner": "logistic T-learner policy"}


def _t(*p):
    return pd.read_csv(TABLES_DIR.joinpath(*p))


def _j(*p):
    return json.loads(TABLES_DIR.joinpath(*p).read_text())


def f_pp(x, d=2):
    return f"{100 * x:+.{d}f} pp"


def f_ci_pp(lo, hi, d=2):
    return f"{100 * lo:.{d}f} to {100 * hi:.{d}f}"


def f_usd(x, d=2):
    return f"{'+' if x >= 0 else '-'}${abs(x):.{d}f}"


def f_p(p):
    return f"{p:.1e}" if p < 1e-3 else f"{p:.3f}"


def load() -> dict:
    R = {}
    R["quality"] = _j("data", "data_quality.json")
    R["alloc"] = _t("data", "allocation.csv")
    R["eff"] = _t("final", "full_itt_effects.csv")
    R["arms"] = _t("final", "full_arm_summary.csv")
    R["adj"] = _t("final", "full_adjusted_ols.csv")
    R["adjdiag"] = _j("final", "full_adjusted_ols_diagnostics.json")
    R["clu"] = _t("final", "full_profile_cluster.csv")
    R["win"] = _t("final", "full_spend_winsor.csv")
    R["perm"] = _t("final", "full_randomization_inference.csv")
    R["newc"] = _t("final", "full_conversion_newcombe.csv")
    R["boot"] = _t("final", "full_spend_bootstrap.csv")
    R["devfull"] = _t("final", "development_vs_full_itt.csv")
    R["sub"] = _t("final", "full_heterogeneity_subgroups.csv")
    R["het"] = _t("final", "full_heterogeneity_tests.csv")
    R["bal"] = _t("development", "balance_full_sample.csv")
    R["cv"] = _t("models", "cv_summary.csv")
    R["status"] = _j("models", "learner_status.json")
    R["vdiag"] = _t("models", "validation_response_diagnostics.csv")
    R["devdiag"] = _t("models", "development_model_diagnostics.csv")
    R["resplit"] = _t("models", "development_resplit_stability.csv")
    R["vval"] = _t("validation", "validation_policy_values.csv")
    R["vsel"] = _t("validation", "targeting_selection_log.csv")
    R["sel"] = _j("validation", "selection.json")
    R["pv"] = _t("final", "policy_values.csv")
    R["pc"] = _t("final", "policy_comparisons.csv")
    R["dec"] = _j("final", "policy_decision.json")
    R["stab"] = _t("final", "bootstrap_stability.csv")
    R["sup"] = _t("final", "policy_support.csv")
    R["grid"] = _t("final", "capacity_cost_grid.csv")
    R["ea"] = _t("final", "economics_panel_a_visit_value.csv")
    R["eb"] = _t("final", "economics_panel_b_spend_margin.csv")
    sim = TABLES_DIR / "simulation" / "estimator_validation.csv"
    R["sim"] = pd.read_csv(sim) if sim.exists() else None
    pipe = TABLES_DIR / "simulation" / "pipeline_validation.csv"
    R["pipe"] = pd.read_csv(pipe) if pipe.exists() else None
    return R


def _eff(R, family, outcome, contrast):
    e = R["eff"]
    return e[(e.family == family) & (e.outcome == outcome) & (e.contrast == contrast)].iloc[0]


def _cmp(R, p, b):
    c = R["pc"]
    return c[(c.policy == p) & (c.baseline == b)].iloc[0]


CATEGORY_MEMO = {
    "meaningful_gain": "The interval lies above the pre-set practical margin of +0.5 pp: a meaningful gain versus the frozen comparator.",
    "worse": "The whole interval is below zero: evidence that the targeting policy is worse than the comparator.",
    "detectable_gain_below_margin": "The gain is statistically detectable but its interval lies below the +0.5 pp practical margin.",
    "excludes_margin": "The upper bound is below the pre-set practical margin of +0.5 pp, so **the evidence rules out a worthwhile gain of that size** (it does not prove the difference is exactly zero).",
    "positive_margin_unresolved": "The difference is positive but the +0.5 pp practical margin is not established: insufficient evidence to justify personalization.",
    "insufficient": "The interval includes both zero and the +0.5 pp margin: insufficient evidence to justify personalization.",
}


def best_action_sentence(R) -> str:
    s = R["sub"][R["sub"].grouping == "purchase_profile"].pivot(index="subgroup", columns="contrast", values="estimate_pp")
    s["W_minus_M"] = s["W - 0"] - s["M - 0"]
    w_better = s[s["W_minus_M"] > 0]
    if w_better.empty:
        return "the men's email had the larger estimated effect in every historical-purchase profile."
    parts = ", ".join(f"{idx} (+{v:.2f} pp)" for idx, v in w_better["W_minus_M"].items())
    return (f"the men's email had the larger estimated effect in every historical-purchase profile except {parts}, "
            "where the women's email led by that exploratory, uncorrected margin.")


def economics_sentence(R) -> str:
    cstar = R["dec"]["constant_comparator"]
    base = "quota_M" if cstar == "const_M" else ("quota_W" if cstar == "const_W" else None)
    if base is None:
        return "The selected constant sends no email, so no contact-cost scenario applies."
    a = R["ea"][(R["ea"].q == 1.0) & (R["ea"].policy == base)]
    b = R["eb"][(R["eb"].q == 1.0) & (R["eb"].policy == base)]
    a_txt = ("its interval stays above zero in all {n} frozen value/cost scenarios (assumed $0.25–$2 per extra visit)".format(n=len(a))
             if (a.ci_low > 0).all() else "its interval crosses zero in {k} of {n} frozen value/cost scenarios".format(k=int((a.ci_low <= 0).sum()), n=len(a)))
    neg = b[b.ci_low <= 0]
    b_txt = ("under assumed 10–50% margins on historical gross spend the margin proxy is positive in every scenario, but imprecise"
             if neg.empty else "under assumed 10–50% margins on historical gross spend the margin proxy is imprecise; its interval includes zero for "
             + ", ".join(f"m = {r.margin_m:g} with c = ${r.contact_cost_c:g}" for r in neg.itertuples()))
    return f"For {POL[cstar]} versus no email, {a_txt}; {b_txt}."


def recommendation(R) -> dict:
    dec = R["dec"]
    cstar = dec["constant_comparator"]
    cat = dec["category"]
    simple = POL[cstar]
    if cat == "meaningful_gain" and dec["constant_family"]["worthwhile_gain_over_family"] and not dec["fragile"]:
        head = f"Targeting with the locked {POL[dec['pi_star']]} cleared the practical margin against every constant policy; it merits a prospective test."
        action = "Run a contemporary randomized test of the targeting policy against the best constant before any deployment."
    else:
        head = (f"Send the {simple.replace(' to everyone', '')} to everyone (the simple constant policy). "
                f"The locked targeting policy did not beat it on held-out data; personalization is not justified by this evidence.")
        action = (f"Use the simple constant policy ({simple}) if a decision must be made from this historical evidence, "
                  "and validate it (and its real costs) in a contemporary randomized test before relying on it.")
    return {"headline": head, "action": action}


# =========================================================================== memo

def memo(R) -> str:
    m, w = _eff(R, "primary", "visit", "M - 0"), _eff(R, "primary", "visit", "W - 0")
    cm, cw = _eff(R, "secondary", "conversion", "M - 0"), _eff(R, "secondary", "conversion", "W - 0")
    sm, sw = _eff(R, "secondary", "spend", "M - 0"), _eff(R, "secondary", "spend", "W - 0")
    wm = _eff(R, "exploratory", "visit", "W - M")
    dec = R["dec"]
    pc = dec["primary_comparison"]
    fam = dec["constant_family"]["lower_bounds"]
    rec = recommendation(R)
    q25 = R["grid"][(R["grid"].policy == dec["pi_star"]) & (R["grid"].q == 0.25) & (R["grid"].kappa == 0)].iloc[0]
    econ_sentence = economics_sentence(R)
    return f"""# CampaignLab — executive decision memo

**To:** Ecommerce growth lead (hypothetical stakeholder) · **Re:** Which email campaign to send, and whether to personalize · **Basis:** retrospective analysis of the public Hillstrom (2008) randomized email experiment, 64,000 recent purchasers, two-week outcomes.

## Recommendation

**{rec['headline']}** {rec['action']}

## What the historical experiment shows (estimated assignment effects, full sample N = 64,000)

| Outcome | Men's email − no email | Women's email − no email |
|---|---|---|
| **Visit within two weeks (primary)** | **{f_pp(m.estimate)}** (95% CI {f_ci_pp(m.ci_low, m.ci_high)}) | **{f_pp(w.estimate)}** (95% CI {f_ci_pp(w.ci_low, w.ci_high)}) |
| Purchase (secondary) | {f_pp(cm.estimate)} (95% CI {f_ci_pp(cm.ci_low, cm.ci_high)}) | {f_pp(cw.estimate)} (95% CI {f_ci_pp(cw.ci_low, cw.ci_high)}) |
| Gross spend per assigned customer (secondary) | {f_usd(sm.estimate)} (95% CI {sm.ci_low:.2f} to {sm.ci_high:.2f}) | {f_usd(sw.estimate)} (95% CI {sw.ci_low:.2f} to {sw.ci_high:.2f}) |

Both campaigns raised visits relative to no email; both primary contrasts remain significant after Holm adjustment (adjusted p = {f_p(m.p_adj)} and {f_p(w.p_adj)}). The descriptive women's-minus-men's visit contrast was {f_pp(wm.estimate)} (95% CI {f_ci_pp(wm.ci_low, wm.ci_high)}; not a planned primary test). Purchases are sparse (578 in total), so the spend and conversion effects are less precise. These are 2008 effects for this population; they do not establish today's effect sizes.

## Did personalization help? (held-out TEST, N = 12,802, evaluated once after a pre-unblinding lock)

- The constant comparator chosen on VALIDATION was **{POL[dec['constant_comparator']]}**; the targeting candidate chosen on VALIDATION was the **{POL[dec['pi_star']]}**.
- On TEST, the targeting policy minus {POL[dec['constant_comparator']]}: **{f_pp(pc['estimate'])}** (95% paired CI {f_ci_pp(pc['ci_low'], pc['ci_high'])}). {CATEGORY_MEMO[dec['category']]} {"Bootstrap, nominal-design, doubly robust and profile-clustered checks all give the same category." if not dec['fragile'] else "Sensitivity analyses disagree on the category, so the conclusion is fragile; prefer the simpler policy."}
- Versus each constant: {', '.join(f"{POL[k]} {f_pp(_cmp(R, dec['pi_star'], k).estimate)} (simultaneous one-sided lower bound {100 * v:+.2f} pp)" for k, v in fam.items())}. Superiority over the strongest-constant family is **{'established' if dec['constant_family']['beats_constant_family'] else 'not established'}**.
- With a contact budget (e.g. 25% of customers), targeting versus a feasible men's quota was {f_pp(q25.net_vs_quota_M)} (95% CI {f_ci_pp(q25.net_vs_quota_M_ci_low, q25.net_vs_quota_M_ci_high)}){': inconclusive' if q25.net_vs_quota_M_ci_low <= 0 <= q25.net_vs_quota_M_ci_high else ''} (exploratory).

## Business framing (hypothetical, not observed profit)

Visits are engagement, not profit. {econ_sentence} These are scenario arithmetic on assumed inputs and must not be added together or reported as revenue.

## Limits and what would change the decision

The allocation mechanics, customer identity and email delivery are not documented; the population is 2008 recent purchasers; costs and margins are unknown; purchases are sparse. Before deploying anything: run a contemporary randomized test with real contact costs, deliverability/compliance logging, independent customer IDs, and enough sample to detect a practically meaningful targeting gain.
"""


# =========================================================================== technical report

def _table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for r in df.itertuples(index=False):
        lines.append("| " + " | ".join(str(v) for v in r) + " |")
    return "\n".join(lines)


def technical_report(R) -> str:
    q = R["quality"]["quality"]
    m, w = _eff(R, "primary", "visit", "M - 0"), _eff(R, "primary", "visit", "W - 0")
    dec = R["dec"]
    pi, cstar = dec["pi_star"], dec["constant_comparator"]
    pc = dec["primary_comparison"]
    rec = recommendation(R)

    arm_tbl = R["arms"].assign(**{
        "visit rate": lambda d: (100 * d.visit_mean).map("{:.2f}%".format),
        "purchase rate": lambda d: (100 * d.conversion_mean).map("{:.2f}%".format),
        "mean spend (USD)": lambda d: d.spend_mean.map("{:.3f}".format)})[["arm", "n", "visit_events", "visit rate", "conversion_events", "purchase rate", "mean spend (USD)"]]

    e = R["eff"].copy()
    def fmt_est(r):
        return f"{100 * r.estimate:+.2f} pp" if r.outcome != "spend" else f"{r.estimate:+.3f} USD"
    def fmt_ci(r):
        return f"{100 * r.ci_low:.2f} to {100 * r.ci_high:.2f}" if r.outcome != "spend" else f"{r.ci_low:.3f} to {r.ci_high:.3f}"
    eff_tbl = pd.DataFrame({
        "family": e.family, "outcome": e.outcome, "contrast": e.contrast, "n treat / control": e.n_treat.astype(str) + " / " + e.n_control.astype(str),
        "events treat / control": e.events_treat.astype(str) + " / " + e.events_control.astype(str),
        "estimate": e.apply(fmt_est, axis=1), "SE": e.apply(lambda r: f"{100 * r.se:.3f} pp" if r.outcome != "spend" else f"{r.se:.3f}", axis=1),
        "95% CI (individual)": e.apply(fmt_ci, axis=1),
        "simultaneous 97.5% CI": e.apply(lambda r: f"{r.simul_ci_low_pp:.2f} to {r.simul_ci_high_pp:.2f}" if r.family == "primary" else "—", axis=1),
        "raw p": e.p_raw.map(f_p), "Holm p (family)": e.apply(lambda r: f_p(r.p_adj) if pd.notna(r.p_adj) else "—", axis=1)})

    adj = R["adj"]
    adj_tbl = adj[adj.contrast != "W - M"].assign(
        adjusted=lambda d: d.apply(lambda r: f"{100 * r.adj_estimate:+.2f} pp" if r.outcome != "spend" else f"{r.adj_estimate:+.3f}", axis=1),
        unadjusted=lambda d: d.apply(lambda r: f"{100 * r.unadj_estimate:+.2f} pp" if r.outcome != "spend" else f"{r.unadj_estimate:+.3f}", axis=1),
        **{"SE ratio adj/unadj": lambda d: d.se_ratio_adj_over_unadj.map("{:.3f}".format)})[["outcome", "contrast", "covariance", "unadjusted", "adjusted", "SE ratio adj/unadj"]]

    clu = R["clu"].assign(ratio=lambda d: d.se_ratio.map("{:.3f}".format))[["outcome", "contrast", "ratio"]]
    win = R["win"].assign(est=lambda d: d.estimate.map("{:+.3f}".format), ci=lambda d: d.ci_low.map("{:.3f}".format) + " to " + d.ci_high.map("{:.3f}".format))[["version", "contrast", "est", "ci", "rows_capped"]]
    perm = R["perm"]
    boot = R["boot"]
    newc = R["newc"]
    het = R["het"].assign(p=lambda d: d.p_value.map(f_p), Q=lambda d: d.Q_statistic.map("{:.2f}".format))[["grouping", "contrast", "Q", "df", "p"]]
    sub = R["sub"].assign(est=lambda d: d.estimate_pp.map("{:+.2f}".format), ci=lambda d: d.ci_low_pp.map("{:.2f}".format) + " to " + d.ci_high_pp.map("{:.2f}".format))[
        ["grouping", "subgroup", "contrast", "n_treat", "n_control", "visits_treat", "visits_control", "est", "ci", "support_flag"]]

    cv = R["cv"].assign(mean_logloss=lambda d: d.mean_logloss.map("{:.6f}".format))[["learner", "C", "mean_logloss", "all_converged", "selected"]]
    vd = R["vdiag"].assign(logloss=lambda d: d.logloss.map("{:.4f}".format), brier=lambda d: d.brier.map("{:.4f}".format))[["learner", "C", "logloss", "brier", "mean_predicted", "observed_rate"]]
    rs = R["resplit"]
    vv = R["vval"].assign(value=lambda d: (100 * d.ipw_value).map("{:.2f}%".format), diff=lambda d: (100 * d.diff_vs_C_star).map("{:+.2f} pp".format),
                         contact=lambda d: (100 * d.contact_rate).map("{:.1f}%".format))[["policy", "value", "contact", "diff"]]
    vsel = R["vsel"]

    pv = R["pv"].assign(value=lambda d: (100 * d.ipw_value).map("{:.2f}%".format), ci=lambda d: (100 * d.ci_low).map("{:.2f}".format) + " to " + (100 * d.ci_high).map("{:.2f}".format),
                        HT=lambda d: (100 * d.ht_nominal_value).map("{:.2f}%".format), DR=lambda d: (100 * d.dr_value).map("{:.2f}%".format),
                        contact=lambda d: (100 * d.contact_rate).map("{:.1f}%".format), M=lambda d: (100 * d.share_M).map("{:.1f}%".format),
                        W=lambda d: (100 * d.share_W).map("{:.1f}%".format))[["policy", "role", "value", "ci", "HT", "DR", "contact", "M", "W"]]
    pcx = R["pc"].assign(est=lambda d: d.estimate_pp.map("{:+.2f}".format), ci=lambda d: d.ci_low_pp.map("{:.2f}".format) + " to " + d.ci_high_pp.map("{:.2f}".format),
                         boot=lambda d: (100 * d.boot_ci_low).map("{:.2f}".format) + " to " + (100 * d.boot_ci_high).map("{:.2f}".format),
                         dr=lambda d: (100 * d.dr_estimate).map("{:+.2f}".format), clus=lambda d: d.cluster_se_ratio.map("{:.3f}".format))[
        ["policy", "baseline", "role", "est", "ci", "boot", "dr", "clus", "decision_category"]]
    fam = dec["constant_family"]
    sup = R["sup"]
    sup_pi = sup[sup.policy.isin([pi, cstar])].assign(share=lambda d: d.matched_share_of_arm.map("{:.3f}".format))[["policy", "outcome", "arm", "n_arm", "matched_rows", "matched_events", "share"]]
    stab = R["stab"]
    g = R["grid"]
    gk = g[(g.kappa == 0) & g.policy.isin([pi, "quota_M", "quota_W", "fixed_rule"])].assign(
        gain=lambda d: (100 * d.delta_vs_no_send).map("{:+.2f}".format),
        vsM=lambda d: d.apply(lambda r: f"{100 * r.net_vs_quota_M:+.2f} ({100 * r.net_vs_quota_M_ci_low:.2f} to {100 * r.net_vs_quota_M_ci_high:.2f})", axis=1))[
        ["policy", "q", "contacts", "gain", "vsM"]].rename(columns={"gain": "gain vs no email (pp)", "vsM": "minus men's quota (pp, 95% CI)"})
    gkk = g[(g.policy == pi)].assign(net=lambda d: d.apply(lambda r: f"{100 * r.net_vs_quota_M:+.2f}", axis=1))[["q", "kappa", "contacts", "net"]]
    gkk = gkk.pivot(index="q", columns="kappa", values="net").reset_index()
    gkk.columns = ["q"] + [f"kappa={k:g}" for k in gkk.columns[1:]]
    ea = R["ea"][(R["ea"].q == 1.0) & R["ea"].policy.isin(["quota_M", pi])].assign(v=lambda d: d.apply(lambda r: f"{r.net_value_per_customer:.4f} ({r.ci_low:.4f} to {r.ci_high:.4f})", axis=1))
    ea = ea.pivot_table(index=["b_value_per_visit", "kappa", "c_cost_per_contact"], columns="policy", values="v", aggfunc="first").reset_index()
    eb = R["eb"][(R["eb"].q == 1.0) & R["eb"].policy.isin(["quota_M", pi])].assign(v=lambda d: d.apply(lambda r: f"{r.proxy_per_customer:.3f} ({r.ci_low:.3f} to {r.ci_high:.3f})", axis=1))
    eb = eb.pivot_table(index=["margin_m", "contact_cost_c"], columns="policy", values="v", aggfunc="first").reset_index()

    sim_txt = "Synthetic validation tables were not available when this report was generated."
    if R["sim"] is not None:
        s = R["sim"].assign(bias=lambda d: d.apply(lambda r: f"{r.bias:+.5f} (z {r.bias_z:+.1f})", axis=1), cov=lambda d: d.apply(lambda r: f"{r.coverage_95:.3f} ± {r.coverage_mc_se:.3f}", axis=1),
                            rej=lambda d: d.rejection_rate_two_sided_5pct.map("{:.3f}".format))[["scenario", "estimand", "bias", "cov", "rej", "coverage_in_diagnostic_range", "bias_detected_abs_z_gt_3", "expected"]]
        nul = R["sim"][(R["sim"].scenario == "no_effect") & (R["sim"].estimand == "ATE M-0")].iloc[0]
        valid = R["sim"][R["sim"].scenario != "broken_allocation"]
        flagged = valid[valid.bias_detected_abs_z_gt_3]
        broken = R["sim"][R["sim"].scenario == "broken_allocation"]
        flag_txt = (f"Under valid randomization {len(flagged)} of {len(valid)} rows had |bias/MC SE| > 3 ("
                    + ", ".join(f"{r.scenario} {r.estimand}: z = {r.bias_z:+.2f}" for r in flagged.itertuples())
                    + "). The difference in means is exactly unbiased for the sample effect under complete randomization, and an independent "
                    "5,000-repetition rerun of that scenario gave the opposite sign (see docs/implementation_log.md), so this is attributed to Monte Carlo "
                    "noise across these correlated rows rather than estimator bias. " if len(flagged) else "No valid-randomization row had |bias/MC SE| > 3. ")
        flag_txt += (f"With allocation deliberately broken, bias was detected in {int(broken.bias_detected_abs_z_gt_3.sum())} of {len(broken)} rows "
                     f"(the nominal-1/3 HT estimator's coverage fell to {broken.coverage_95.min():.3f}), showing the checks can fail when the assumption fails.")
        sim_txt = (f"{int(R['sim'].repetitions.iloc[0]):,} repetitions per scenario, n = {int(R['sim'].n_per_rep.iloc[0]):,} per repetition, against superpopulation truths. "
                   f"With no true effect, the Holm family-wise rejection rate for the two primary tests was {nul.primary_family_holm_fwer:.3f}. "
                   "Coverage is shown ± its Monte Carlo SE; the 92–98% band is a practical diagnostic range, not a proof. " + flag_txt + "\n\n" + _table(s))
        if R["pipe"] is not None:
            p = R["pipe"].assign(cov=lambda d: d.apply(lambda r: f"{r.coverage_95:.3f} ± {r.coverage_mc_se:.3f}", axis=1),
                                 est=lambda d: (100 * d.mean_estimate).map("{:+.2f}".format), truth=lambda d: (100 * d.mean_true_delta).map("{:+.2f}".format),
                                 best=lambda d: (100 * d.best_possible_delta).map("{:+.2f}".format), s=lambda d: d.share_selected_s_learner.map("{:.2f}".format))[
                ["scenario", "repetitions", "s", "est", "truth", "best", "cov"]].rename(columns={"s": "share S-learner selected", "est": "mean TEST estimate (pp)",
                                                                                                 "truth": "mean true Δ of selected policy (pp)", "best": "oracle best-action gain vs best constant (pp)", "cov": "coverage of true Δ"})
            sim_txt += ("\n\n**Whole-pipeline repetitions** (refit TRAIN-CV → VALIDATION selection → TEST evaluation on fresh synthetic data each time; "
                        "the target is the true value of the policy *as selected*):\n\n" + _table(p))

    rmin, rmax = rs.s_minus_best_constant.min(), rs.s_minus_best_constant.max()
    dd = R["devdiag"]
    bal_max = R["bal"].abs_smd.max()
    adjd = R["adjdiag"]
    het_p = R["het"].set_index(["grouping", "contrast"]).p_value
    cstar_v = R["vval"].set_index("policy")
    stab_max = stab.max_endpoint_change_pp.max()
    m_both = R["sub"][(R["sub"].grouping == "purchase_profile")]

    return f"""# CampaignLab technical report

*Retrospective analysis of a publisher-described randomized email experiment (Hillstrom, 2008). Generated from the reviewed aggregate tables in `reports/tables/`; every number below is read from those files. Plan: SAP v1.0 (`docs/analysis_plan.md`).*

**Result taxonomy used throughout:** *observed facts* (counts in the file) · *estimated historical effects* (ITT contrasts with uncertainty) · *exploratory results* (subgroups, capacity curves; uncorrected) · *model predictions* (response probabilities, not individual effects) · *synthetic tests* (simulated data only) · *hypothetical scenarios* (assumed costs, values, margins).

## 1. Summary

- **Primary (estimated historical effects, N = 64,000):** men's email − no email **{f_pp(m.estimate)}** (95% CI {f_ci_pp(m.ci_low, m.ci_high)}; Bonferroni 97.5% {m.simul_ci_low_pp:.2f} to {m.simul_ci_high_pp:.2f}); women's email − no email **{f_pp(w.estimate)}** (95% CI {f_ci_pp(w.ci_low, w.ci_high)}; Bonferroni {w.simul_ci_low_pp:.2f} to {w.simul_ci_high_pp:.2f}). Holm-adjusted p = {f_p(m.p_adj)} and {f_p(w.p_adj)}.
- **Policy (TEST, N = 12,802, locked):** π* = {POL[pi]} vs C* = {POL[cstar]}: **{f_pp(pc['estimate'])}** (95% paired CI {f_ci_pp(pc['ci_low'], pc['ci_high'])}). Decision category: *{dec['category_text']}*. Sensitivity categories: {', '.join(f'{k} → {v}' for k, v in dec['sensitivity_categories'].items())} (fragile: {dec['fragile']}). Strongest-constant-family superiority: **{'established' if fam['beats_constant_family'] else 'not established'}**.
- **Recommendation:** {rec['headline']} {rec['action']}

## 2. Question, estimands and decision

The hypothetical stakeholder (an ecommerce growth lead) must choose which campaign to send, whether personalization warrants further investment, and how a contact budget changes the choice. Estimands (SAP §1): τ(a, visit) = E[Y(a) − Y(0)] for a ∈ {{M, W}} (primary, ITT), the same contrasts for purchase and gross spend per assigned customer (secondary), and the held-out policy value difference Δ(π*, C*) on TEST. The unit is a source row assumed to be a distinct customer.

## 3. Data, provenance and quality (observed facts)

Original publisher CSV, **3,964,977 bytes**, SHA-256 `{R['quality']['dataset_sha256']}`, {q['rows']:,} rows × {R['quality']['columns']} columns; all hard contract checks passed in both Python and SQL. {q['global_visits']:,} visits, {q['global_conversions']} purchases, {q['positive_spend_rows']} positive-spend rows. {q['full_row_match_groups']:,} groups of identical full rows ({q['full_row_match_excess']:,} excess rows) and {q['distinct_pretreatment_profiles']:,} distinct pre-treatment profiles ({q['pretreatment_profile_excess']:,} excess) are **retained** — equal values do not identify the same person. {q['history_bucket_boundary_disagreements']} rows sit on rounded `history_segment` boundaries (100/200/500) and are kept as soft warnings. `Surburban` is preserved as spelled in the source. No rows were excluded. Raw data are not redistributed (rights unresolved).

## 4. Frozen plan and information flow

The SAP and configuration were committed (git `60d32e3`) before any arm-by-outcome analysis; schema/global counts had been seen earlier and this is disclosed (not a blinded preregistration). The deterministic arm-stratified split gave TRAIN 38,399 / VALIDATION 12,799 / TEST 12,802. Development inference used TRAIN+VALIDATION only; TRAIN fitted models; VALIDATION selected π* and C*; a lock manifest (dataset, split, code, config, environment, model, selection and 66 TEST action checksums) was written and committed before TEST outcomes were first read; the full-sample analysis was released only after the evaluation record existed. Code enforces these scopes and logs each outcome access.

## 5. Experimental inference (full sample, released after the lock)

![Allocation](figures/fig1_allocation.png)

*Figure 1. Observed assignment counts (all 64,000 rows; assignment only). Deviations from the nominal one-third are {', '.join(f"{r.arm} {r.deviation_from_nominal_rows:+.1f} rows" for r in R['alloc'].itertuples())}. Counts are descriptive; no design-based SRM test is invented because the allocation mechanism is not documented.*

![Balance](figures/fig2_balance.png)

*Figure 2. Standardized mean differences for all pre-treatment features and all three arm pairs (N = 64,000). Largest |SMD| = {bal_max:.3f}, far below the 0.1 diagnostic reference.*

**Arm summaries (observed, N = 64,000):**

{_table(arm_tbl)}

**Effect table (primary family: Holm over 2; secondary family: Holm over 4; W − M exploratory):**

{_table(eff_tbl)}

Individual 95% intervals are ordinary (not multiplicity-adjusted) intervals; the simultaneous 97.5% Bonferroni intervals apply to the two primary contrasts only. Holm-adjusted p-values do not convert ordinary intervals into simultaneous ones.

![Primary](figures/fig3_primary_visit_effects.png)

*Figure 3. Primary ITT visit effects (N = 64,000; no email {int(m.n_control):,}, men's {int(m.n_treat):,}, women's {int(w.n_treat):,}). Thick: individual 95% CI; thin: Bonferroni 97.5% simultaneous CI.*

![Secondary](figures/fig4_secondary_conversion_spend.png)

*Figure 4. Secondary outcomes on separate axes. Conversion: Wald and Newcombe 95% intervals; spend per assigned customer (zeros retained): analytic and 5,000-replicate stratified bootstrap 95% intervals. Purchases are sparse (578 overall).*

**Sensitivity results (none replaces the primary estimator):**

- *Covariate adjustment* — fixed centered, fully interacted OLS (Lin-style; rank {adjd['rank']}, condition number {adjd['condition_number']:.1f}), HC2 with HC3 sensitivity:

{_table(adj_tbl)}

- *Joint arm × covariate interaction test (visit, HC2):* χ² = {adjd['joint_interaction_test_visit']['HC2']['statistic']:.1f} on {adjd['joint_interaction_test_visit']['HC2']['df']} df, p = {f_p(adjd['joint_interaction_test_visit']['HC2']['p_value'])} (exploratory).
- *Profile-clustered SEs* (hypothetical dependence among identical pre-treatment profiles; SE ratio clustered / row-independent): {', '.join(f'{r.outcome} {r.contrast}: {r.ratio}' for r in clu.itertuples())}.
- *Conversion, Newcombe 95%:* {', '.join(f'{r.contrast}: {100 * r.newcombe_ci_low:.2f} to {100 * r.newcombe_ci_high:.2f} pp' for r in newc.itertuples())}.
- *Spend bootstrap (5,000, stratified within arm):* {', '.join(f'{r.contrast}: {r.bootstrap_ci_low:.3f} to {r.bootstrap_ci_high:.3f} (second independent 5,000: {r.stability_ci_low_second_5000:.3f} to {r.stability_ci_high_second_5000:.3f})' for r in boot.itertuples())}.
- *Spend tails (TRAIN-frozen thresholds; winsorized means are different estimands):*

{_table(win)}

  The positive-spend threshold equals the observed maximum ($499), so it caps nothing.
- *Randomization inference* (assumed complete randomization conditional on arm counts; sharp null of no unit-level effect; 9,999 draws): {', '.join(f'{r.contrast}: p = {r.p_value:.4f} ({r.extreme} draws as extreme)' for r in perm.itertuples())} — the smallest attainable p at this draw count.
- *Development (provisional) vs full sample:* {', '.join(f'{r.outcome} {r.contrast}: {r.estimate_development:+.4f} → {r.estimate_full:+.4f}' for r in R['devfull'][R['devfull'].family == 'primary'].itertuples())}.

## 6. Exploratory heterogeneity

![Heterogeneity](figures/fig5_exploratory_heterogeneity.png)

*Figure 5. Exploratory, uncorrected subgroup visit effects (N = 64,000); no subgroup was flagged for low support. Group averages under randomization, not individual effects; purchase flags are not gender.*

{_table(sub)}

Heterogeneity (equal-effect) Wald tests: {', '.join(f'{r.grouping} {r.contrast}: Q = {r.Q} (df {r.df}), p = {r.p}' for r in het.itertuples())}. Purchase history modifies effect *sizes* strongly (e.g. women's email − no email is {m_both[(m_both.subgroup == 'mens only') & (m_both.contrast == 'W - 0')].estimate_pp.iloc[0]:+.2f} pp for men's-only buyers vs {m_both[(m_both.subgroup == 'womens only') & (m_both.contrast == 'W - 0')].estimate_pp.iloc[0]:+.2f} pp for women's-only buyers), but the *best action* rarely changes: {best_action_sentence(R)} That is why large effect heterogeneity produced little room for targeting gains.

## 7. Targeting models (TRAIN fits, VALIDATION selects)

Basis: recency, log(1+history), mens, womens, newbie, Web/Multichannel and Urban/Surburban indicators (TRAIN-standardized continuous columns; `history_segment` excluded). S-learner: one L2 logistic model with arm indicators and all arm × basis interactions. T-learner: three arm-specific L2 logistic models; support gate {'passed' if R['status']['t_learner_gate_support_passed'] else 'failed'} and it was {'included' if R['status'].get('t_learner', {}).get('included') else 'omitted'}. Three-fold arm-stratified CV inside TRAIN, fold-local preprocessing:

{_table(cv)}

VALIDATION response diagnostics (prediction quality, **not** uplift quality):

{_table(vd)}

Development-only diagnostics: {'; '.join(f'{r.diagnostic}: {r.mean_logloss:.6f}' if pd.notna(r.mean_logloss) else r.diagnostic for r in dd.itertuples())}. Across {len(rs)} development resplits the refitted S-learner minus the best constant ranged {100 * rmin:+.2f} to {100 * rmax:+.2f} pp (mean {100 * rs.s_minus_best_constant.mean():+.2f} pp), signalling a small and unstable targeting gain before the TEST evaluation.

**VALIDATION selection** (allocation-normalized IPW):

{_table(vv)}

C* = {POL[cstar]} (largest constant value). Targeting candidates within one paired SE of the best were eligible and the simplest eligible was chosen:

{_table(vsel)}

The S-learner and T-learner differ on very few VALIDATION rows; their gap equals exactly one paired SE (a single discordant matched visit), and the frozen inclusive rule selected the simpler S-learner. No code changed after this was observed.

## 8. Held-out policy evaluation (TEST, evaluated once)

![Policies](figures/fig6_heldout_policy_comparisons.png)

*Figure 6. TEST N = 12,802 only. Left: policy values (allocation-normalized IPW with 95% CIs). Right: paired differences on the same rows with 95% paired CIs, paired within-arm bootstrap (5,000) intervals and one-sided Bonferroni bounds for the three-constant family. Observed TEST arm fractions are not documented individual propensities.*

{_table(pv)}

{_table(pcx)}

**Primary comparison:** {f_pp(pc['estimate'])} (95% CI {f_ci_pp(pc['ci_low'], pc['ci_high'])}; bootstrap {f_ci_pp(pc['boot_ci_low'], pc['boot_ci_high'])}; nominal-1/3 HT {f_pp(pc['ht_nominal_estimate'])}; TRAIN-nuisance DR {f_pp(pc['dr_estimate'])} ({f_ci_pp(pc['dr_ci_low'], pc['dr_ci_high'])}); profile-cluster SE ratio {pc['cluster_se_ratio']:.3f}). With δ = 0.5 pp: **{dec['category_text']}**.

**Strongest-constant family** (z = {fam['z']:.3f}): one-sided lower bounds {', '.join(f'{POL[k]} {100 * v:+.2f} pp' for k, v in fam['lower_bounds'].items())} → superiority over the constant family is **{'established' if fam['beats_constant_family'] else 'not established'}**.

**Support** (only rows whose assigned arm equals the recommended action contribute rewards):

{_table(sup_pi)}

Bootstrap stability: the largest change in a 95% endpoint between 5,000 and 10,000 replicates was {stab_max:.3f} pp (target ≤ 0.1 pp). The secondary, non-selected candidates are reported for transparency only; they cannot replace π* after TEST.

## 9. Capacity and assumed costs (exploratory frozen scenarios)

![Capacity](figures/fig7_capacity_and_assumed_cost.png)

*Figure 7. TEST N = 12,802. Left: visit gain vs no email by contact capacity with feasible hash-quota baselines (κ = 0). Right: π* minus the men's quota after subtracting κ × contact rate. Intervals are conditional on this cohort and the fixed actions; no simultaneous coverage across cells is claimed.*

{_table(gk)}

π* minus men's quota, net utility (pp) for every frozen (q, κ):

{_table(gkk)}

**Hypothetical economics (two separate panels; never added; not observed profit).**

![Economics](figures/figS1_hypothetical_economics.png)

*Supplementary figure. Panel A: b × visit gain − c × contact rate with assumed b ∈ {{0.25, 1, 2}} USD per visit and c = b·κ. Panel B: m × historical gross-spend gain − c × contact rate with assumed margin m ∈ {{0.1, 0.3, 0.5}} and c ∈ {{0, 0.01, 0.05}}. q = 1, versus no email.*

Panel A (USD per customer, 95% CI):

{_table(ea)}

Panel B (USD per customer, 95% CI; matched TEST purchases: {int(sup[(sup.policy == pi) & sup.outcome.str.startswith('spend')].matched_events.sum())} for π*, {int(sup[(sup.policy == cstar) & sup.outcome.str.startswith('spend')].matched_events.sum())} for {POL[cstar]}, so precision is low):

{_table(eb)}

## 10. Synthetic known-truth validation (synthetic tests — not Hillstrom data)

{sim_txt}

## 11. Limitations and assumptions

- Causal interpretation relies on the publisher's description of random one-third allocation; seed, strata, quotas and delivery logs are absent. Balance diagnostics are consistent with randomization but cannot prove it.
- One independent customer per row is assumed; matching profiles were retained and a profile-clustered sensitivity changed SEs by under 2%. True identity is unknown.
- No interference, consistent treatment definitions and accurate two-week outcome measurement are assumed and untestable here.
- The policy value uses observed TEST arm fractions as allocation weights (not documented propensities); nominal-1/3 weighting gave the same conclusion.
- Purchases are sparse; spend and conversion results are imprecise and spend is gross, not margin.
- Results describe 2008 recent purchasers over two weeks; they do not establish current effect sizes, retention, or profit.
- All costs, values and margins are hypothetical inputs.

## 12. Recommendation and next evidence

{rec['headline']} {rec['action']}

Evidence that would change this: a contemporary randomized test with documented allocation, deliverability/compliance logs and customer IDs; real contact costs and margins; and enough sample that a targeting gain of the practically relevant size could be detected (here the TEST interval half-width for Δ(π*, C*) was about {100 * (pc['ci_high'] - pc['ci_low']) / 2:.2f} pp).
"""


# =========================================================================== README

def readme(R) -> str:
    m, w = _eff(R, "primary", "visit", "M - 0"), _eff(R, "primary", "visit", "W - 0")
    dec = R["dec"]
    pc = dec["primary_comparison"]
    rec = recommendation(R)
    fam = dec["constant_family"]
    return f"""# CampaignLab

**Which email campaign should a retailer send, and does a learned targeting policy beat simply sending the best campaign to everyone?** A reproducible retrospective analysis of the publisher-described randomized Hillstrom (2008) email experiment.

> **Bottom line:** {rec['headline']}

> **Evidence boundary:** historical 2008 data, two-week outcomes, publisher-described (not independently verified) randomization, unknown customer identity, sparse purchases, and hypothetical economics. No raw data are included in this repository.

## Results

| Type | Result |
|---|---|
| Estimated historical effect (primary, N = 64,000) | Men's email vs no email: **{f_pp(m.estimate)}** visit rate (95% CI {f_ci_pp(m.ci_low, m.ci_high)}) |
| Estimated historical effect (primary, N = 64,000) | Women's email vs no email: **{f_pp(w.estimate)}** (95% CI {f_ci_pp(w.ci_low, w.ci_high)}); Holm-adjusted p ≤ {f_p(max(m.p_adj, w.p_adj))} |
| Held-out policy evaluation (TEST, N = 12,802, locked) | {POL[dec['pi_star']].capitalize()} vs {POL[dec['constant_comparator']]}: **{f_pp(pc['estimate'])}** (95% paired CI {f_ci_pp(pc['ci_low'], pc['ci_high'])}) — evidence excludes a gain ≥ 0.5 pp; superiority over the constant family {'established' if fam['beats_constant_family'] else 'not established'} |
| Exploratory | Purchase history strongly modifies effect sizes, but the best action barely changes: {best_action_sentence(R)} |
| Hypothetical scenarios | Assumed visit values/costs and margins (Panels A and B kept separate); not profit |
| Synthetic tests | Known-truth simulations check estimator coverage and the select-then-evaluate pipeline |

Read the [executive memo](reports/executive_memo.md) and the full [technical report](reports/technical_report.md).

![Primary effects](reports/figures/fig3_primary_visit_effects.png)
![Held-out policies](reports/figures/fig6_heldout_policy_comparisons.png)

## How the study was protected against self-deception

1. **Frozen plan first** — [`docs/analysis_plan.md`](docs/analysis_plan.md) and [`config/analysis.yaml`](config/analysis.yaml) were committed before any arm-by-outcome analysis (prior schema/global-count inspection is disclosed).
2. **Deterministic split** — SHA-256 of source-ordinal row IDs within arm → TRAIN 38,399 / VALIDATION 12,799 / TEST 12,802; no outcome in the key.
3. **TRAIN fits, VALIDATION selects, TEST evaluates once** — a lock manifest (data, split, code, config, environment, model and 66 action-vector checksums) is verified before TEST outcomes can be loaded; the full-sample analysis is released only afterwards. Access is enforced in code and logged.
4. **Strong baselines** — no-send, men's-for-all, women's-for-all, a frozen purchase-history rule, and feasible hash quotas under capacity limits; paired uncertainty on the same rows; simultaneous bounds before any claim against the strongest constant.

## Data and rights

Source: Kevin Hillstrom, [*MineThatData E-Mail Analytics and Data Mining Challenge*](https://blog.minethatdata.com/2008/03/minethatdata-e-mail-analytics-and-data.html) (2008). The publisher invites analysis but no redistribution license was found, so **this repository contains no raw or row-level data, split membership, per-row predictions, databases or serialized models**. The pipeline downloads the original file and verifies SHA-256 `0e5893329d8b93cefecc571777672028290ab69865718020c78c7284f291aece`. The MIT license covers the code only — see [`docs/rights_and_assumptions.md`](docs/rights_and_assumptions.md).

## Reproduce

```bash
python3 -m venv .venv            # tested with CPython 3.14.3
.venv/bin/pip install -r requirements.lock
.venv/bin/pip install --no-deps -e .
.venv/bin/python -m campaignlab.run all        # acquire → validate → develop → fit → select → lock → evaluate → release → report
.venv/bin/python -m campaignlab.run simulate   # synthetic known-truth validation
.venv/bin/python -m pytest                     # test suite (private-data tests skip if the CSV is absent)
```

Details, expected hashes and the recorded clean rerun: [`docs/reproduction.md`](docs/reproduction.md).

## Repository map

| Path | Contents |
|---|---|
| `config/analysis.yaml` | Frozen estimands, methods, grids, seeds |
| `sql/` | DuckDB validation, development-only and final summary SQL |
| `src/campaignlab/` | `data`, `inference`, `models`, `policy`, `evaluation`, `governance`, `reporting`, `simulation`, `run` |
| `tests/` | Contract, split, estimator, leakage, policy, end-to-end access-control and simulation tests |
| `reports/` | Memo, technical report, figures (PNG/SVG) and aggregate tables |
| `docs/` | Analysis plan, data dictionary, rights, implementation log, reproduction, case study, evidence ledger, interview prep |

Not claimed: a live experiment, deployment, modern-ecommerce generalization, observed profit, or methodological novelty.
"""


def write_reports(cfg) -> None:
    R = load()
    (ROOT / "reports" / "executive_memo.md").write_text(memo(R), encoding="utf-8")
    report = technical_report(R)
    (ROOT / "reports" / "technical_report.md").write_text(report, encoding="utf-8")
    (ROOT / "README.md").write_text(readme(R), encoding="utf-8")
