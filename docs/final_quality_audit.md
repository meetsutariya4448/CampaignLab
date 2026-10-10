# Final quality audit

This audit reviews the finished project against the five-phase build instructions and blueprint documents 01–12. Status key: ✅ met, ⚠️ met with a disclosed deviation or limitation, ⛔ not done (with reason). Evidence paths are relative to the repository root.

## Phase 1 — plan, environment, data (M0–M2)

| Requirement | Status | Evidence |
|---|---|---|
| Read all blueprint documents; verify blueprint integrity | ✅ | All 14 files matched `blueprint_quality_audit.json` hashes (`docs/implementation_log.md` M0) |
| Compact repository structure (doc 05) | ⚠️ | Planned layout implemented. Added `config.py`, `governance.py`, `simulation.py`, `report_text.py` and `scripts/` (plan §12.7). Optional notebook not created |
| Versioned SAP, data dictionary, rights/assumptions, config, frozen before arm-specific exploration | ✅ | Commit `60d32e3`; `docs/analysis_plan.md`, `config/analysis.yaml` |
| Prior inspection disclosed; not called blinded preregistration | ✅ | SAP "Disclosure" section; README; technical report §4 |
| Isolated environment, supported Python, exact lock | ⚠️ | CPython 3.14.3 because 3.12 is not installed (deviation logged); `requirements.lock` |
| Exact publisher bytes acquired and preserved privately | ✅ | 3,964,977 bytes, pinned SHA-256; read-only `data/raw/` |
| Schema/type/domain/missingness/consistency/treatment/matching/bucket validation | ✅ | 23 named checks with 0 failures in Python and SQL (`reports/tables/data/contract_checks.csv`); all planning quality facts reproduced |
| "Surburban" preserved; matching rows and 5 boundary cases retained; no identity inference | ✅ | `data_quality.json`; tests `test_surburban_spelling_preserved`, `test_matching_rows_reported_not_dropped` |
| Source-ordinal row IDs before sorting; covariate/assignment/outcome separation | ✅ | `data.parse_source`; DuckDB tables `covariates`, `assignment`, `outcomes` |
| Exact deterministic split, no outcomes in the key: 38,399 / 12,799 / 12,802 | ✅ | `reports/tables/data/split_counts.csv`; split tests |
| Private provenance and split manifests | ✅ | `artifacts/private/` (ignored) |
| Typed DuckDB validation and development SQL | ✅ | `sql/01_validate.sql`, `sql/02_development_summary.sql`; SQL equals Python |
| TEST outcomes and full-sample arm summaries kept out of development outputs | ✅ | Store scopes, `dev_outcomes` view, access log, `test_store_scopes_and_one_to_one_joins`, pipeline test |
| Acquisition, contract, grain, split and leakage tests | ✅ | `tests/test_data.py` (28 tests) |

## Phase 2 — experimental inference and sensitivity (M3–M4)

| Requirement | Status | Evidence |
|---|---|---|
| Provisional DEVELOPMENT analysis, N = 51,198 | ✅ | `reports/tables/development/`; labeled scope |
| Both primary ITT contrasts with denominators, events, rates, differences, pp, SE, CI, raw and Holm p | ✅ | `itt_effects.csv` (development), `full_itt_effects.csv` (final) |
| Sample-variance SE; explicit `method="holm"` | ✅ | `inference.mean_difference`, `inference.holm`; fixture tests |
| Ordinary vs Bonferroni simultaneous intervals distinguished; never called Holm-adjusted | ✅ | Separate columns and labels; `test_effect_table_labels_ordinary_vs_simultaneous` |
| Secondary conversion and spend per assigned customer; zeros kept; sparse support disclosed | ✅ | Secondary family of 4; Newcombe; event counts |
| Balance and SMD for all arm pairs | ✅ | `balance_full_sample.csv`, `balance_development.csv`; Figure 2 |
| Centered, fully interacted OLS with HC2, HC3 sensitivity | ✅ | `full_adjusted_ols.csv`; rank and condition checks |
| Bootstrap, spend-tail, profile-dependence, exploratory heterogeneity | ✅ | Spend bootstrap 2,000 / 5,000 (+5,000 stability); winsor thresholds frozen from TRAIN; profile clustering; subgroups and Wald tests |
| Randomization inference labeled (assumed mechanism, sharp null) | ✅ | `full_randomization_inference.csv` columns `null` and `mechanism` |
| No invented pre-period visits, timestamps, IDs or randomization details | ✅ | None created |
| Arithmetic, sign, unit, covariance, multiplicity, degenerate, bootstrap and SQL/Python tests | ✅ | `tests/test_inference.py` (19 tests); stage-level SQL/Python assertions |
| Results provisional until release | ✅ | Development scope labels; final values released only after the evaluation record |

## Phase 3 — policies, lock, evaluation (M5–M6)

| Requirement | Status | Evidence |
|---|---|---|
| No-send, two send-all, frozen history rule, hash-quota baselines | ✅ | `policy.py`; `test_policy.py` |
| TRAIN-only, fold-local transforms | ✅ | `FeatureBasis`; `test_basis_fitted_on_training_rows_only`; CV refits per fold |
| L2 logistic S-learner with arm × feature interactions | ✅ | 29 design columns; ablation shows main-effects-only is constant |
| T-learner only if gate passes | ✅ | 48/48 gate checks passed; converged; included |
| Exact C grid, CV metric, tie rules | ✅ | `cv_summary.csv`; `select_C` tests |
| Convergence, log loss, Brier and calibration recorded; not confused with uplift | ✅ | `validation_response_diagnostics.csv`, `validation_calibration.csv` |
| Positive-gain actions, deterministic ties, κ, capacity | ✅ | `best_gain_actions`, `capacity_limit`; tests |
| Action functions get only permitted inputs | ✅ | `assert_covariates_only`; leakage tests; TEST actions computed from covariates selected by split membership |
| VALIDATION selects C* and π* with simplicity rule; no TRAIN+VALIDATION refit | ✅ | `selection.json`, `targeting_selection_log.csv` (exact one-SE tie disclosed) |
| Lock manifest before TEST outcomes | ✅ | Lock `59e7e741…` at 01:03:14Z; first TEST read 01:03:37Z; committed `9dd6086` before evaluation |
| Allocation-normalized IPW, matched support, paired differences, paired within-arm bootstrap | ✅ | `policy_values.csv`, `policy_support.csv`, `policy_comparisons.csv` |
| Nominal 1/3 as sensitivity; observed fractions not called propensities | ✅ | `ht_nominal_*` columns; labels |
| Comparison with frozen C* and all three constants; simultaneous bounds | ✅ | `policy_decision.json` → `constant_family` |
| TRAIN-nuisance DR sensitivity | ✅ | `dr_*` columns; DR bootstrap |
| All capacity and cost scenarios vs feasible baselines | ✅ | `capacity_cost_grid.csv` (every q × κ) |
| Full-sample release only after evaluation | ✅ | Release token requires the evaluation record; `test_pipeline` |
| Nothing changed in response to TEST | ✅ | Locked code, config and environment hashes verified unchanged after evaluation |
| Identity checks (constant = arm mean; identical policies Δ = 0) | ✅ | Unit tests and synthetic pipeline test on real-style tables |
| Conclusion category stated | ✅ | "Evidence excludes a gain as large as δ", the same under all sensitivities |

## Phase 4 — report and presentation (M7)

| Requirement | Status | Evidence |
|---|---|---|
| Seven figures, PNG and SVG from aggregate tables | ✅ | `reports/figures/` (+1 supplementary economics figure, logged) |
| Captions include denominators, units, CI methods, scopes, exploratory labels | ✅ | Figure footnotes and report captions |
| Executive memo and complete technical report | ✅ | `reports/executive_memo.md`, `reports/technical_report.md` |
| Financial Panels A and B kept separate, labeled hypothetical, not profit, all frozen scenarios, sparse purchase support | ✅ | Economics tables, Figure S1, report §9 |
| Simple policy recommended when personalization is not justified; next evidence described | ✅ | Memo and report §12 |
| README and case study built on actual (negative) findings | ✅ | `README.md`, `docs/case_study.md` |
| No dashboard unless it adds material value | ✅ | Not built (reason in implementation log) |
| Figures and claims reconciled with executed artifacts | ✅ | Generated from tables; `scripts/audit_claims.py` finds 0 unmatched numbers |

## Phase 5 — reproducibility and completion (M8–M9)

| Requirement | Status | Evidence |
|---|---|---|
| Test layers T1–T6 | ✅ | 85 tests: data 28, inference 19, models 11, policy 24, pipeline 1 (end-to-end), simulation 2 (slow) |
| Known-truth synthetic validation labeled, with MC uncertainty | ✅ | `reports/tables/simulation/`; report §10; one \|z\| > 3 row disclosed and investigated |
| Clean local rerun with documented commands and locked environment | ✅ | `docs/reproduction.md`: fresh clone, venv and download; 85 passed; 0 deterministic differences |
| Determinism, tolerances, bootstrap precision, consistent recommendation | ✅ | Comparison record; stability ≤ 0.047 pp |
| Runtime, versions, tests and checks recorded (no invented performance claims) | ✅ | `docs/reproduction.md`, `requirements.lock` |
| Public-file audit for row-level or private content | ✅ | `reports/publication_audit.json` (passed); ZIP audited separately; positive controls confirmed detection |
| Raw-data redistribution blocked; code-only license | ✅ | `.gitignore`, `LICENSE` data notice, `docs/rights_and_assumptions.md` |
| Attribution, assumptions, limitations, deviations complete | ✅ | Rights doc, SAP §13, technical report §11, implementation log |
| Publication-ready local repository (not pushed) | ✅ | Local git history; no remote configured |
| Evidence ledger and three resume bullet drafts; real resume untouched | ✅ | `docs/evidence_ledger.md`, `docs/resume_bullets.md` |
| One-minute, five-minute, deep-dive outlines; 36 questions; 10 hardest | ✅ | `docs/interview_prep.md` |
| Final deliverables and ZIP excluding data, private files, environment, caches | ✅ | `outputs/CampaignLab_Final/`; ZIP from `git archive` of tracked files only |

## Blueprint document 10 — twenty prohibitions

1. **No fabricated results.** ✅ Every number is in `reports/tables`.
2. **No invented business impact.** ✅ Scenarios are labeled hypothetical.
3. **No unsupported treatment-effect claims.** ✅ No individual-effect claims.
4. **No leakage.** ✅ Allowlist, scope guards and tests.
5. **No training on TEST.** ✅
6. **No tuning on TEST.** ✅ Hashes verified unchanged.
7. **No association/causation confusion.** ✅ ITT under stated assumptions.
8. **Visits are not profit.** ✅
9. **Gross spend is not margin.** ✅
10. **No deployment claim.** ✅
11. **No novelty claim.** ✅
12. **No modern generalization claim.** ✅
13. **No raw redistribution.** ✅
14. **No overengineered infrastructure.** ✅ Local batch pipeline.
15. **No unnecessary advanced ML.** ✅ Logistic S/T learners only.
16. **No selective reporting.** ✅ All planned rows and scenarios.
17. **No hidden inconclusive or negative results.** ✅ The negative result is the headline.
18. **No employer attribution.** ✅
19. **No unused-tool claims.** ✅ Seaborn is not claimed.
20. **No unverified resume metrics.** ✅ Each figure is linked to the ledger.

## Unresolved external limitations (cannot be fixed by this project)

- The original operational randomization (seed, strata, quotas, delivery) is undocumented; causal claims rest on the publisher's description.
- True customer identity and dependence are unknown.
- Raw-data redistribution rights are unresolved, so only code and aggregates may be published.
- Contemporary effect sizes, real contact costs and margins are unknown; the economics are scenarios only.

## Items for the owner

- The `LICENSE` copyright line uses the git handle `meetsutariya`. Change it to your preferred legal name before publishing.
- Commits use your global git identity. Nothing has been pushed and no remote exists.
- Optional work not done: AUUC/Qini curves, a Tableau or Streamlit view, and an exploration notebook. All were optional; none is required for the conclusions.
