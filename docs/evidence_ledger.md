# Evidence-to-claim ledger

Each public claim maps to an executed artifact, its denominator, and its definition. Paths are relative to the repository root. Category key:

- **O**: observed fact
- **E**: estimated historical effect
- **X**: exploratory
- **P**: model prediction
- **S**: synthetic test
- **H**: hypothetical scenario
- **R**: reproducibility/engineering

| # | Claim | Cat. | Value | Artifact | Denominator / scope | Definition / method |
|---|---|---|---|---|---|---|
| 1 | Exact publisher file analyzed | O | 3,964,977 bytes; SHA-256 0e58…aece | `reports/tables/data/data_quality.json` | whole file | Hash computed before parsing |
| 2 | Rows / columns / arms | O | 64,000 × 12; 21,306 / 21,307 / 21,387 | `reports/tables/data/data_quality.json`, `allocation.csv` | all rows | Count |
| 3 | Visits / purchases | O | 9,394 / 578 | `data_quality.json` | all rows | Count |
| 4 | Matching rows retained | O | 1,072 groups, 6,562 excess rows; 0 exclusions | `data_quality.json` | all rows | Identical 12-field rows; Σ(group size − 1) |
| 5 | Split sizes | O | 38,399 / 12,799 / 12,802 | `reports/tables/data/split_counts.csv` | all rows | SHA-256 rank within arm, 60/20/20 floors |
| 6 | Hard contract checks pass in Python and SQL | R | 0 failures (23 named checks: 20 in both Python and SQL, 3 SQL split-reconciliation) | `reports/tables/data/contract_checks.csv` | all rows | Typed DuckDB and Python validation |
| 7 | Men's email − no email, visit | E | +7.66 pp (95% CI 7.00 to 8.32); Holm p 5.5e-113 | `reports/tables/final/full_itt_effects.csv` | N = 64,000 (21,307 vs 21,306) | Difference in means, √(s²₁/n₁+s²₀/n₀), Holm over 2 |
| 8 | Women's email − no email, visit | E | +4.52 pp (95% CI 3.89 to 5.16); Holm p 1.9e-44 | same | N = 64,000 (21,387 vs 21,306) | same |
| 9 | Simultaneous primary intervals | E | 6.90–8.42 and 3.80–5.25 pp | same | N = 64,000 | Bonferroni two-sided 97.5% |
| 10 | Secondary conversion / spend | E | +0.68 / +0.31 pp; +$0.77 / +$0.42 per assigned customer | same | N = 64,000; 578 purchases | Difference in means; Holm over 4 |
| 11 | Adjustment does not change the result | E | adjusted M−0 +7.61 pp; SE ratio 0.984 | `reports/tables/final/full_adjusted_ols.csv` | N = 64,000 | Centered, fully interacted OLS, HC2 |
| 12 | Development estimates were provisional and close to final | E | +7.57 / +4.71 pp (dev) | `reports/tables/development/itt_effects.csv` | N = 51,198 | Same estimator, TRAIN+VALIDATION |
| 13 | Purchase-profile heterogeneity | X | W−0: +1.11 pp (men's only) vs +7.40 pp (women's only) | `reports/tables/final/full_heterogeneity_subgroups.csv` | subgroup Ns in table | Uncorrected subgroup differences |
| 14 | Selected policy and comparator | P/E | π* = S-learner, C* = men's-for-all | `reports/tables/validation/selection.json` | VALIDATION N = 12,799 | Frozen selection rules |
| 15 | Locked TEST comparison | E | −0.44 pp (95% paired CI −1.29 to +0.42) | `reports/tables/final/policy_comparisons.csv`, `policy_decision.json` | TEST N = 12,802 | Allocation-normalized IPW, paired stratified SE |
| 16 | Decision category robust to sensitivities | E | "excludes δ = 0.5 pp" under analytic, bootstrap, nominal-HT, DR, clustered | `policy_decision.json` | TEST N = 12,802 | Frozen decision table |
| 17 | Constant-family superiority not established | E | lower bound vs men's-for-all −1.36 pp | `policy_decision.json` | TEST | One-sided Bonferroni, z = 2.128 |
| 18 | Fixed rule worse than men's-for-all | E | −1.39 pp (−2.64 to −0.14) | `policy_comparisons.csv` | TEST | Secondary, not selected |
| 19 | Capacity curves inconclusive | X | q = 0.25: +0.35 pp (−0.71 to +1.41) vs men's quota | `reports/tables/final/capacity_cost_grid.csv` | TEST | Hash-quota baselines; frozen grid |
| 20 | Economics are scenarios only | H | Panels A and B tables | `economics_panel_a_visit_value.csv`, `economics_panel_b_spend_margin.csv` | TEST | Assumed b, c, m; panels never added |
| 21 | TEST read only after lock | R | Lock 01:03:14Z; first TEST access 01:03:37Z (UTC, 2026-10-10) | `docs/implementation_log.md` (private lock and access log) | — | Lock verified by recomputed hashes |
| 22 | Known-truth simulation coverage | S | see technical report §10 | `reports/tables/simulation/*.csv` | synthetic reps | Coverage ± MC SE vs superpopulation truth |
| 23 | Test suite | R | see `docs/reproduction.md` | pytest output recorded there | — | Unit, contract, leakage, end-to-end, simulation |
| 24 | Clean rerun reproduces artifacts | R | see `docs/reproduction.md` | rerun comparison record | — | Fresh clone, fresh environment, all stages |

Not supported by any artifact, and therefore never claimed: a live experiment, deployment, revenue or profit, modern-ecommerce performance, individual treatment effects, or methodological novelty.
