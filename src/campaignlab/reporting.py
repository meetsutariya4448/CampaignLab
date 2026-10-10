"""Figures and reports built ONLY from reviewed aggregate tables in reports/tables/.

No estimator runs here: every plotted value is read from a CSV/JSON written by an earlier stage,
so charts, tables and narrative reconcile by construction.
"""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .config import FIGURES_DIR, TABLES_DIR  # noqa: E402

# ---- palette (validated: blue/orange/aqua pass light-mode categorical checks; aqua needs visible labels)
INK, INK2, MUTED, GRID, BASE, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
ARM_COLOR = {"No E-Mail": "#898781", "Mens E-Mail": "#2a78d6", "Womens E-Mail": "#eb6834"}
CONTRAST_COLOR = {"M - 0": "#2a78d6", "W - 0": "#eb6834", "W - M": "#1baf7a"}
POLICY_LABEL = {"const_0": "No email (all)", "const_M": "Men's email (all)", "const_W": "Women's email (all)",
                "fixed_rule": "Fixed purchase-history rule", "s_learner": "S-learner policy", "t_learner": "T-learner policy",
                "quota_M": "Men's hash quota", "quota_W": "Women's hash quota"}
KAPPA_RAMP = ["#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]  # ordinal blue steps 250/400/550/700

plt.rcParams.update({
    "font.family": ["Helvetica Neue", "Arial", "DejaVu Sans"], "font.size": 10, "axes.edgecolor": BASE,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "axes.titlecolor": INK, "axes.titlesize": 11,
    "axes.titleweight": "bold", "axes.grid": False, "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white", "svg.fonttype": "none",
    "svg.hashsalt": "campaignlab", "legend.frameon": False, "lines.solid_capstyle": "round",
})


def _t(*parts) -> pd.DataFrame:
    return pd.read_csv(TABLES_DIR.joinpath(*parts))


def _j(*parts) -> dict:
    return json.loads(TABLES_DIR.joinpath(*parts).read_text())


def _grid(ax, axis="x"):
    ax.grid(axis=axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _note(fig, text, y=0.01):
    fig.text(0.01, y, text, ha="left", va="bottom", fontsize=7.6, color=INK2, wrap=True)


def _save(fig, name):
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES_DIR / f"{name}.png", dpi=200, metadata={"Software": None})
    fig.savefig(FIGURES_DIR / f"{name}.svg", metadata={"Date": None, "Creator": None})
    plt.close(fig)


def pp(x, digits=2):
    return f"{100 * x:+.{digits}f}"


# =========================================================================== figures

def fig1_allocation():
    a = _t("data", "allocation.csv")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.6, 3.4), gridspec_kw={"width_ratios": [1.4, 1]})
    y = np.arange(3)[::-1]
    for yi, r in zip(y, a.itertuples()):
        ax1.barh(yi, r.n, height=0.45, color=ARM_COLOR[r.arm])
        ax1.text(r.n + 400, yi, f"{r.n:,} ({100 * r.fraction:.2f}%)", va="center", fontsize=9, color=INK)
        ax2.barh(yi, r.deviation_from_nominal_rows, height=0.45, color=ARM_COLOR[r.arm])
        ax2.text(r.deviation_from_nominal_rows + (3 if r.deviation_from_nominal_rows >= 0 else -3), yi,
                 f"{r.deviation_from_nominal_rows:+.1f}", va="center", ha="left" if r.deviation_from_nominal_rows >= 0 else "right", fontsize=9)
    nominal = a["n"].sum() / 3
    ax1.axvline(nominal, color=INK2, linewidth=1)
    ax1.text(nominal - 300, -0.45, f"nominal 1/3 = {nominal:,.0f}", ha="right", fontsize=8, color=INK2)
    ax1.set_ylim(-0.6, 2.5)
    ax1.set_yticks(y, a["arm"])
    ax1.set_xlim(0, 27000)
    ax1.set_xlabel("Assigned customers (rows)")
    ax1.set_title("Observed assignment counts", loc="left")
    ax2.axvline(0, color=BASE, linewidth=1)
    ax2.set_yticks(y, [""] * 3)
    ax2.set_ylim(-0.6, 2.5)
    ax2.set_xlim(-90, 90)
    ax2.set_xlabel("Rows above / below nominal 1/3")
    ax2.set_title("Deviation from nominal allocation", loc="left")
    _grid(ax1)
    _grid(ax2)
    _note(fig, "All 64,000 rows (assignment only, no outcomes). The publisher describes nominal one-third random allocation; counts are descriptive and do not prove randomization.")
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    _save(fig, "fig1_allocation")


def fig2_balance():
    b = _t("development", "balance_full_sample.csv")
    feats = ["recency", "history", "log_history", "mens", "womens", "newbie", "channel_Phone", "channel_Web", "channel_Multichannel",
             "zip_Rural", "zip_Urban", "zip_Surburban"]
    labels = {"zip_Surburban": "zip_Surburban (Suburban)", "log_history": "log(1 + history)", "history": "history (raw, skewed)"}
    fig, ax = plt.subplots(figsize=(8.2, 5.0))
    offsets = {"M vs 0": -0.22, "W vs 0": 0.0, "W vs M": 0.22}
    colors = {"M vs 0": "#2a78d6", "W vs 0": "#eb6834", "W vs M": "#1baf7a"}
    for comp, off in offsets.items():
        sub = b[b.comparison == comp].set_index("feature").loc[feats]
        ax.scatter(sub["smd"], np.arange(len(feats))[::-1] + off, s=34, color=colors[comp], edgecolor="white", linewidth=1.5,
                   label=comp.replace("M", "Men's").replace("W", "Women's").replace(" 0", " no email"), zorder=3)
    for x in (-0.1, 0.1):
        ax.axvline(x, color=INK2, linewidth=0.8)
    ax.axvline(0, color=BASE, linewidth=1)
    ax.text(0.1, len(feats) - 0.3, "  |SMD| = 0.1 reference", fontsize=8, color=INK2, va="bottom")
    ax.set_yticks(np.arange(len(feats))[::-1], [labels.get(f, f) for f in feats])
    ax.set_xlim(-0.12, 0.12)
    ax.set_xlabel("Standardized mean difference (first arm minus second)")
    ax.set_title("Baseline covariate balance, all pairwise arm comparisons", loc="left")
    ax.legend(loc="lower left", fontsize=8.5, ncol=3, bbox_to_anchor=(0, -0.24))
    _grid(ax)
    mx = b["abs_smd"].max()
    _note(fig, f"All 64,000 rows; pre-treatment features only. Largest |SMD| = {mx:.3f}. The 0.1 line is a diagnostic convention, not a hypothesis test; balance is not proof of randomization.")
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    _save(fig, "fig2_balance")


def fig3_primary():
    e = _t("final", "full_itt_effects.csv")
    p = e[e.family == "primary"].set_index("contrast")
    fig, ax = plt.subplots(figsize=(8.8, 3.4))
    names = {"M - 0": "Men's email minus no email", "W - 0": "Women's email minus no email"}
    for yi, c in zip((1, 0), ("M - 0", "W - 0")):
        r = p.loc[c]
        ax.plot([r.simul_ci_low_pp, r.simul_ci_high_pp], [yi - 0.16, yi - 0.16], color=CONTRAST_COLOR[c], linewidth=1.6)
        ax.plot([r.ci_low_pp, r.ci_high_pp], [yi + 0.08, yi + 0.08], color=CONTRAST_COLOR[c], linewidth=4)
        ax.scatter([r.estimate_pp], [yi + 0.08], s=70, color=CONTRAST_COLOR[c], edgecolor="white", linewidth=2, zorder=3)
        ax.text(9.15, yi, f"{r.estimate_pp:+.2f} pp  [{r.ci_low_pp:.2f}, {r.ci_high_pp:.2f}]\nHolm-adj. p = {r.p_adj:.1e}",
                va="center", fontsize=8.5, color=INK)
    ax.axvline(0, color=BASE, linewidth=1)
    ax.set_yticks([1, 0], [names["M - 0"], names["W - 0"]])
    ax.set_ylim(-0.6, 1.6)
    ax.set_xlim(0, 12.6)
    ax.set_xticks(range(0, 10, 1))
    ax.set_xlabel("Two-week visit rate difference (percentage points)")
    ax.set_title("Primary result: assignment effect on visits (ITT)", loc="left")
    _grid(ax)
    ax.plot([], [], color=INK2, linewidth=4, label="Individual 95% CI (not multiplicity-adjusted)")
    ax.plot([], [], color=INK2, linewidth=1.6, label="Bonferroni simultaneous 97.5% CI (family of 2)")
    ax.legend(loc="lower left", fontsize=8)
    n0 = int(p.loc["M - 0", "n_control"]); nm = int(p.loc["M - 0", "n_treat"]); nw = int(p.loc["W - 0", "n_treat"])
    _note(fig, f"Full sample N=64,000 (no email {n0:,}; men's {nm:,}; women's {nw:,}), released after the policy lock. SE = sqrt(s1^2/n1 + s0^2/n0). "
               "Holm over the two primary contrasts.")
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    _save(fig, "fig3_primary_visit_effects")


def fig4_secondary():
    e = _t("final", "full_itt_effects.csv").set_index(["outcome", "contrast"])
    nc = _t("final", "full_conversion_newcombe.csv").set_index("contrast")
    bs = _t("final", "full_spend_bootstrap.csv").set_index("contrast")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.2, 3.4))
    for yi, c in zip((1, 0), ("M - 0", "W - 0")):
        r = e.loc[("conversion", c)]
        ax1.plot([100 * r.ci_low, 100 * r.ci_high], [yi + 0.1, yi + 0.1], color=CONTRAST_COLOR[c], linewidth=4)
        ax1.plot([100 * nc.loc[c, "newcombe_ci_low"], 100 * nc.loc[c, "newcombe_ci_high"]], [yi - 0.12, yi - 0.12], color=CONTRAST_COLOR[c], linewidth=1.4)
        ax1.scatter([100 * r.estimate], [yi + 0.1], s=60, color=CONTRAST_COLOR[c], edgecolor="white", linewidth=2, zorder=3)
        ax1.text(1.02, yi, f"{100 * r.estimate:+.2f} pp\n{int(r.events_treat)} vs {int(r.events_control)} purchases", va="center", fontsize=8.2)
        s = e.loc[("spend", c)]
        ax2.plot([s.ci_low, s.ci_high], [yi + 0.1, yi + 0.1], color=CONTRAST_COLOR[c], linewidth=4)
        ax2.plot([bs.loc[c, "bootstrap_ci_low"], bs.loc[c, "bootstrap_ci_high"]], [yi - 0.12, yi - 0.12], color=CONTRAST_COLOR[c], linewidth=1.4)
        ax2.scatter([s.estimate], [yi + 0.1], s=60, color=CONTRAST_COLOR[c], edgecolor="white", linewidth=2, zorder=3)
        ax2.text(1.12, yi, f"{s.estimate:+.2f} USD\n{int(s.events_treat)} vs {int(s.events_control)} buyers", va="center", fontsize=8.2)
    for ax, title, xl, xlim in ((ax1, "Conversion (secondary)", "Purchase-rate difference (pp)", (0, 1.4)),
                                (ax2, "Gross spend per assigned customer (secondary)", "Mean spend difference (USD per assigned customer)", (0, 1.55))):
        ax.axvline(0, color=BASE, linewidth=1)
        ax.set_yticks([1, 0], ["Men's - no email", "Women's - no email"])
        ax.set_ylim(-1.0, 1.6)
        ax.set_xlim(*xlim)
        ax.set_xlabel(xl)
        ax.set_title(title, loc="left")
        _grid(ax)
    ax1.plot([], [], color=INK2, linewidth=4, label="95% Wald CI")
    ax1.plot([], [], color=INK2, linewidth=1.4, label="95% Newcombe CI")
    ax1.legend(loc="lower left", fontsize=7.8)
    ax2.plot([], [], color=INK2, linewidth=4, label="95% analytic CI")
    ax2.plot([], [], color=INK2, linewidth=1.4, label="95% stratified bootstrap (5,000)")
    ax2.legend(loc="lower left", fontsize=7.8)
    _note(fig, "Full sample N=64,000; 578 purchases in total. All assigned rows kept (zeros retained); gross spend is not margin or profit. Separate axes by design. Holm over 4 secondary contrasts in the table.")
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    _save(fig, "fig4_secondary_conversion_spend")


def fig5_heterogeneity():
    s = _t("final", "full_heterogeneity_subgroups.csv")
    eff = _t("final", "full_itt_effects.csv")
    overall = {r.contrast: r.estimate for r in eff[eff.family == "primary"].itertuples()}
    order = [("newbie", "newbie=0 (existing)"), ("newbie", "newbie=1 (new)"), ("purchase_profile", "mens only"),
             ("purchase_profile", "womens only"), ("purchase_profile", "mens and womens"), ("channel", "Phone"), ("channel", "Web"),
             ("channel", "Multichannel")]
    fig, ax = plt.subplots(figsize=(9.2, 5.6))
    ys = np.arange(len(order))[::-1]
    for yi, (g, lvl) in zip(ys, order):
        for c, off in (("M - 0", 0.16), ("W - 0", -0.16)):
            r = s[(s.grouping == g) & (s.subgroup == lvl) & (s.contrast == c)].iloc[0]
            ax.plot([r.ci_low_pp, r.ci_high_pp], [yi + off] * 2, color=CONTRAST_COLOR[c], linewidth=3)
            ax.scatter([r.estimate_pp], [yi + off], s=40, color=CONTRAST_COLOR[c], edgecolor="white", linewidth=1.5, zorder=3)
        n = int(s[(s.grouping == g) & (s.subgroup == lvl)]["n_subgroup"].iloc[0])
        ax.text(17.3, yi, f"n = {n:,}", va="center", fontsize=8, color=INK2)
    for c in ("M - 0", "W - 0"):
        ax.axvline(100 * overall[c], color=CONTRAST_COLOR[c], linewidth=1, alpha=0.5)
    ax.axvline(0, color=BASE, linewidth=1)
    grp = {"newbie": "Newbie", "purchase_profile": "Purchase profile", "channel": "Channel (optional)"}
    ax.set_yticks(ys, [f"{grp[g]}: {lvl}" for g, lvl in order])
    for yb in (5.5, 2.5):
        ax.axhline(yb, color=GRID, linewidth=0.8)
    ax.set_xlim(-1, 19.5)
    ax.set_xlabel("Visit-rate difference vs no email (pp), 95% individual CI")
    ax.set_title("EXPLORATORY: visit effects by pre-treatment subgroup", loc="left")
    ax.scatter([], [], color=CONTRAST_COLOR["M - 0"], label="Men's - no email")
    ax.scatter([], [], color=CONTRAST_COLOR["W - 0"], label="Women's - no email")
    ax.legend(loc="upper right", bbox_to_anchor=(0.86, 0.995), fontsize=8.5)
    _grid(ax)
    _note(fig, "Full sample N=64,000. Exploratory, uncorrected; thin vertical lines = overall effects. No subgroup was flagged for low support (<200 rows or <20 visits per arm). "
               "No row has mens=0 and womens=0. Historical purchase flags are not gender. Group averages, not individual effects.")
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    _save(fig, "fig5_exploratory_heterogeneity")


def fig6_policies():
    v = _t("final", "policy_values.csv").set_index("policy")
    c = _t("final", "policy_comparisons.csv")
    dec = _j("final", "policy_decision.json")
    pi, cstar, delta = dec["pi_star"], dec["constant_comparator"], dec["delta"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.6, 5.2), gridspec_kw={"width_ratios": [1, 1.25]})
    pols = ["const_0", "const_W", "fixed_rule", "t_learner", pi, "const_M"]
    pols = list(dict.fromkeys(pols))
    ys = np.arange(len(pols))[::-1]
    for yi, p in zip(ys, pols):
        r = v.loc[p]
        col = INK if p in (pi, cstar) else MUTED
        ax1.plot([100 * r.ci_low, 100 * r.ci_high], [yi, yi], color=col, linewidth=3)
        ax1.scatter([100 * r.ipw_value], [yi], s=55, color=col, edgecolor="white", linewidth=1.8, zorder=3)
        ax1.text(100 * r.ci_high + 0.3, yi, f"{100 * r.ipw_value:.1f}%", va="center", fontsize=8.5)
    tag = {pi: "  [pi*, locked]", cstar: "  [C*, frozen]"}
    ax1.set_yticks(ys, [POLICY_LABEL[p] + tag.get(p, "") + ("  (not selected)" if p in ("fixed_rule", "t_learner") else "") for p in pols])
    ax1.set_xlim(0, 23)
    ax1.set_xlabel("Estimated visit rate under policy (%), 95% CI")
    ax1.set_title("Held-out policy values (TEST)", loc="left")
    _grid(ax1)
    rows = [(pi, cstar, "pi* - C* (primary)"), (pi, "const_0", "pi* - no email"), (pi, "const_W", "pi* - women's (all)"),
            (pi, "fixed_rule", "pi* - fixed rule"), ("fixed_rule", cstar, "Fixed rule - C* (secondary)")]
    ys2 = np.arange(len(rows))[::-1]
    z3 = dec["constant_family"]["z"]
    for yi, (p, b, lab) in zip(ys2, rows):
        r = c[(c.policy == p) & (c.baseline == b)].iloc[0]
        col = INK if p == pi and b == cstar else INK2
        ax2.plot([r.ci_low_pp, r.ci_high_pp], [yi + 0.1] * 2, color=col, linewidth=3.2)
        ax2.plot([100 * r.boot_ci_low, 100 * r.boot_ci_high], [yi - 0.13] * 2, color=col, linewidth=1.2, alpha=0.7)
        ax2.scatter([r.estimate_pp], [yi + 0.1], s=55, color=col, edgecolor="white", linewidth=1.8, zorder=3)
        if p == pi and b.startswith("const"):
            lb = r.estimate_pp - z3 * 100 * r.se
            ax2.plot([lb], [yi + 0.1], marker="|", markersize=12, color="#1baf7a", markeredgewidth=2)
        ax2.text(10.4, yi, f"{r.estimate_pp:+.2f} [{r.ci_low_pp:+.2f}, {r.ci_high_pp:+.2f}]", va="center", fontsize=8.2)
    ax2.axvline(0, color=BASE, linewidth=1)
    ax2.axvline(100 * delta, color=INK2, linewidth=0.9)
    ax2.text(100 * delta, -0.75, f" delta = +{100 * delta:.1f} pp", fontsize=8, color=INK2, va="center")
    ax2.set_ylim(-0.95, len(rows) - 0.5)
    ax2.set_yticks(ys2, [r[2] for r in rows])
    ax2.set_xlim(-3.5, 15)
    ax2.set_xlabel("Paired difference in visit rate (pp)")
    ax2.set_title("Paired differences on the same TEST rows", loc="left")
    ax2.plot([], [], color=INK2, linewidth=3.2, label="95% paired CI")
    ax2.plot([], [], color=INK2, linewidth=1.2, alpha=0.7, label="95% paired bootstrap (5,000)")
    ax2.plot([], [], marker="|", linestyle="none", color="#1baf7a", markersize=10, markeredgewidth=2, label="1-sided Bonferroni bound (3 constants)")
    ax2.legend(loc="upper left", bbox_to_anchor=(-0.02, -0.15), ncol=1, fontsize=7.6)
    _grid(ax2)
    _note(fig, f"TEST N=12,802 only, evaluated once against the pre-unblinding lock. Allocation-normalized IPW (observed TEST arm fractions, not documented propensities). "
               f"pi* and C* were chosen on VALIDATION. Category: {dec['category_text']}.")
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    _save(fig, "fig6_heldout_policy_comparisons")


def fig7_capacity_cost():
    g = _t("final", "capacity_cost_grid.csv")
    pi = _j("final", "policy_decision.json")["pi_star"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.0, 4.2))
    k0 = g[g.kappa == 0.0]
    styles = {"quota_M": ("#2a78d6", 2), "quota_W": ("#eb6834", 2), "fixed_rule": ("#1baf7a", 2), pi: (INK, 2.4)}
    for p, (col, lw) in styles.items():
        d = k0[k0.policy == p].sort_values("q")
        ax1.fill_between(100 * d.q, 100 * d.delta_vs_no_send_ci_low, 100 * d.delta_vs_no_send_ci_high, color=col, alpha=0.1, linewidth=0)
        ax1.plot(100 * d.q, 100 * d.delta_vs_no_send, color=col, linewidth=lw, marker="o", markersize=4.5, markeredgecolor="white")
        last = d.iloc[-1]
        ax1.text(101.5, 100 * last.delta_vs_no_send, POLICY_LABEL[p] + (" (pi*)" if p == pi else ""), va="center", fontsize=8)
    ax1.axhline(0, color=BASE, linewidth=1)
    ax1.set_xlim(0, 135)
    ax1.set_xticks([0, 25, 50, 75, 100])
    ax1.set_xlabel("Contact capacity q (% of TEST customers)")
    ax1.set_ylabel("Visit-rate gain vs no email (pp)")
    ax1.set_title("Capacity: feasible quota baselines (kappa = 0)", loc="left")
    _grid(ax1, "y")
    for col, kappa in zip(KAPPA_RAMP, sorted(g.kappa.unique())):
        d = g[(g.policy == pi) & (g.kappa == kappa)].sort_values("q")
        ax2.plot(100 * d.q, 100 * d.net_vs_quota_M, color=col, linewidth=2, marker="o", markersize=4.5, markeredgecolor="white",
                 label=f"kappa = {kappa:g}")
    d = g[(g.policy == pi) & (g.kappa == 0.0)].sort_values("q")
    ax2.fill_between(100 * d.q, 100 * d.net_vs_quota_M_ci_low, 100 * d.net_vs_quota_M_ci_high, color=KAPPA_RAMP[0], alpha=0.12, linewidth=0,
                     label="95% CI (kappa = 0)")
    ax2.axhline(0, color=BASE, linewidth=1)
    ax2.set_xticks([0, 25, 50, 75, 100])
    ax2.set_xlabel("Contact capacity q (%)")
    ax2.set_ylabel("Net utility difference, pp of visits")
    ax2.set_title("pi* minus men's quota, net of assumed cost kappa", loc="left")
    ax2.legend(fontsize=8, loc="lower left")
    ax2.text(0.98, 0.97, "Lines coincide where kappa does not change\npi*'s contacts (all estimated gains > kappa)", transform=ax2.transAxes,
             ha="right", va="top", fontsize=7.6, color=INK2)
    _grid(ax2, "y")
    _note(fig, "EXPLORATORY frozen scenarios on TEST N=12,802; intervals conditional on this cohort and fixed actions. kappa = ASSUMED cost in visits per contact (not observed). "
               "Send-all is infeasible at q<1, so hash-quota baselines are used. Net utility = visit gain - kappa x contact rate.")
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    _save(fig, "fig7_capacity_and_assumed_cost")


def figS1_economics():
    a = _t("final", "economics_panel_a_visit_value.csv")
    b = _t("final", "economics_panel_b_spend_margin.csv")
    pi = _j("final", "policy_decision.json")["pi_star"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.0, 4.6))
    pa = a[(a.q == 1.0)]
    combos = [(bv, k) for bv in sorted(pa.b_value_per_visit.unique()) for k in sorted(pa.kappa.unique())]
    xs = np.arange(len(combos))
    for p, col, off in (("quota_M", "#2a78d6", -0.18), (pi, INK, 0.18)):
        d = pa[pa.policy == p].set_index(["b_value_per_visit", "kappa"]).loc[combos]
        ax1.vlines(xs + off, d.ci_low, d.ci_high, color=col, linewidth=2)
        ax1.scatter(xs + off, d.net_value_per_customer, color=col, s=24, zorder=3,
                    label=("Men's email (all) = quota at q=1" if p == "quota_M" else POLICY_LABEL[p] + " (pi*)"))
    ax1.set_xticks(xs, [f"b={bv:g}, c={bv * k:.4g}" for bv, k in combos], fontsize=7, rotation=50, ha="right")
    ax1.axhline(0, color=BASE, linewidth=1)
    ax1.set_ylabel("Hypothetical net value per customer (USD)")
    ax1.set_title("Panel A - HYPOTHETICAL visit value minus contact cost (q=1)", loc="left", fontsize=9.5)
    ax1.legend(fontsize=7.6, loc="upper left")
    _grid(ax1, "y")
    pb = b[b.q == 1.0]
    combos_b = [(m, cc) for m in sorted(pb.margin_m.unique()) for cc in sorted(pb.contact_cost_c.unique())]
    xs = np.arange(len(combos_b))
    for p, col, off in (("quota_M", "#2a78d6", -0.18), (pi, INK, 0.18)):
        d = pb[pb.policy == p].set_index(["margin_m", "contact_cost_c"]).loc[combos_b]
        ax2.vlines(xs + off, d.ci_low, d.ci_high, color=col, linewidth=2)
        ax2.scatter(xs + off, d.proxy_per_customer, color=col, s=24, zorder=3)
    ax2.set_xticks(xs, [f"m={m:g}, c={cc:g}" for m, cc in combos_b], fontsize=7, rotation=50, ha="right")
    ax2.axhline(0, color=BASE, linewidth=1)
    ax2.set_ylabel("Hypothetical margin proxy per customer (USD)")
    ax2.set_title("Panel B - HYPOTHETICAL margin x historical spend gain - cost (q=1)", loc="left", fontsize=9.5)
    _grid(ax2, "y")
    _note(fig, "Both panels are HYPOTHETICAL scenario arithmetic on TEST estimates vs no email (N=12,802); b, c and m are assumed, not observed. The panels must NOT be added "
               "(double counting). Neither is observed revenue or profit. TEST has few matched purchases (see support table), so Panel B is imprecise.")
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    _save(fig, "figS1_hypothetical_economics")


FIGURES = [fig1_allocation, fig2_balance, fig3_primary, fig4_secondary, fig5_heterogeneity, fig6_policies, fig7_capacity_cost, figS1_economics]


def build_figures():
    for f in FIGURES:
        f()


def build_all(cfg):
    build_figures()
    from . import report_text
    report_text.write_reports(cfg)
