# CampaignLab statistical analysis plan — SAP v1.0 (frozen)

**Frozen:** 2026-10-09, at milestone M0, before any arm-by-outcome summary, split-level outcome table, model fit or policy selection.
**Machine-readable form:** [`config/analysis.yaml`](../config/analysis.yaml). Where this document and the config disagree, the config is authoritative for parameter values and this document for interpretation.
**Source design:** the approved CampaignLab blueprint (documents 01–12). All blueprint files were checked against the SHA-256 values in its `blueprint_quality_audit.json` before this freeze.

## Disclosure: what was seen before the freeze

This is a **retrospective analysis of a public benchmark dataset**, not a new randomized experiment and **not a fully blinded preregistration**. Before this plan was frozen, the planning stage had already inspected the file's schema, the three arm counts, global (not arm-specific) visit/conversion/positive-spend totals, missingness, numeric domains, outcome-consistency checks, full-row and profile matching counts, and the five history-bucket boundary cases. No arm-by-outcome comparison, test, split, model or policy result had been computed. The data are public, so outcome withholding in this project is an auditable workflow discipline, not cryptographic secrecy.

## 1. Question, population and estimands

- **Population/unit:** the publisher-described population of 64,000 recent-purchaser customers; one anonymous source row is assumed to represent one distinct randomized customer (this cannot be verified from the file).
- **Treatment:** assigned arm A ∈ {0 = No E-Mail, M = Mens E-Mail, W = Womens E-Mail}. Interpretation is **intention-to-treat** (assignment), not receipt/open/compliance.
- **Primary outcome:** `visit` within the publisher's two-week follow-up window.
- **Primary estimands:** τ(M, visit) = E[Y(M) − Y(0)] and τ(W, visit) = E[Y(W) − Y(0)], risk differences in probability units, also reported as percentage points.
- **Secondary estimands:** the same two contrasts for `conversion` (risk difference) and `spend` (mean gross spend per *assigned* customer, zeros retained). Purchaser-only spend is not an estimand.
- **Exploratory:** W − M visit contrast (descriptive), prespecified pre-treatment subgroup effects, policy capacity/cost curves.
- **Policy estimand:** V(π) = E[Y(π(X))] for visit; Δ(π, b) = V(π) − V(b) on held-out TEST rows.

## 2. Information-access sequence (frozen)

1. Acquire and hash the exact publisher bytes; validate the contract; assign source-ordinal IDs; separate covariates/assignment/outcomes; create the arm-stratified split.
2. Global contract checks and pre-treatment balance may use all rows (X and A only).
3. **M3/M4 development inference uses DEVELOPMENT = TRAIN + VALIDATION (N = 51,198) and is provisional.**
4. Only TRAIN fits transformations and response models; VALIDATION selects the constant comparator C* and the targeting candidate π*.
5. A lock manifest (data/split/code/config/environment/model/action hashes, selections, grids, margin, uncertainty protocol and seeds) is written **before** TEST outcomes are read.
6. TEST policy evaluation runs once against the lock. Then the prespecified **full 64,000-row** experimental analysis and sensitivities are released.
7. Nothing learned from TEST or full-sample results feeds back into policies, hyperparameters, comparators, features, thresholds or δ. Any post-unblinding correction is logged below with cause and effect; substantive redesign is labeled exploratory.

The software enforces steps 3–6: development code can only load TRAIN/VALIDATION outcomes; TEST outcomes require a verified lock token; full-sample outcomes require an evaluation-complete record. Every outcome load is written to a private access log.

## 3. Data rules

- Exact artifact: 3,964,977 bytes, SHA-256 `0e5893329d8b93cefecc571777672028290ab69865718020c78c7284f291aece`, 64,000 rows × 12 columns. A different hash stops the pipeline.
- **No row exclusions.** Matching full rows/profiles are retained and reported; no deduplication; no identity inference. The five history-bucket boundary rows are soft warnings, not exclusions.
- Source spelling `Surburban` is preserved; a display alias may read "Suburban (source: Surburban)".
- `row_id = hillstrom-2008-v1:<zero-based source ordinal>`, assigned before any sorting.
- Hard contract checks: schema/header, row count, blanks, allowed labels, binary indicators, recency 1–12, finite nonnegative amounts with ≤2 decimals, conversion ⇒ visit, positive spend ⇔ conversion.

## 4. Split (frozen, document 04)

Within each arm, rank rows by the hexadecimal SHA-256 of `CampaignLab/split/v1/2027/<row_id>` ascending (row ID as tie-break). First ⌊0.60 n⌋ → TRAIN, next ⌊0.20 n⌋ → VALIDATION, remainder → TEST, using integer arithmetic. No covariate or outcome enters the key. Expected totals 38,399 / 12,799 / 12,802.

## 5. Experimental inference (SAP S1–S12)

| Item | Frozen method |
|---|---|
| Allocation (S1) | Counts, fractions, deviation from nominal 1/3. Descriptive only; no design-based SRM p-value is invented |
| ITT (S2–S3) | Arm means; τ̂ = mean(a) − mean(0); all assigned rows in denominators |
| SE/CI/test (S4–S5) | SE = √(s²ₐ/nₐ + s²₀/n₀) with n−1 sample variances; z = τ̂/SE; 95% CI τ̂ ± 1.959964·SE; two-sided normal p |
| Multiplicity (S6) | Primary family {M−0, W−0 visit}: Holm (statsmodels `method="holm"`), α = 0.05. Simultaneous intervals: two-sided 97.5% Bonferroni for the two primary contrasts, labeled as such. Secondary family of four (conversion, spend × M, W): Holm shown as transparency aid. Ordinary 95% CIs are never called Holm-adjusted |
| Arm rates | Wilson intervals, descriptive only |
| Balance (S7) | Means/SDs and pairwise SMD = Δmean / √((s²ₐ+s²_b)/2) for the nine-column basis plus raw history and all category levels; all three arm pairs; |SMD| = 0.1 is a diagnostic reference |
| Adjustment (S8) | Unpenalized OLS: arm indicators + basis centered at analyzed-sample means + all arm×basis interactions; HC2 covariance with normal reference (primary adjustment), HC3 sensitivity; rank and condition number checked. The unadjusted estimate remains primary |
| Spend bootstrap (S9) | Within-arm stratified bootstrap, 2,000 replicates (development) / 5,000 (final), percentile 2.5/97.5, fixed seed stream |
| Randomization inference (S9, optional) | Per treatment/control pair, conditional on observed arm counts, uniform complete-randomization mechanism **assumed**, 9,999 Monte Carlo draws, p = (extreme + 1)/(draws + 1); tests the **sharp null of no unit-level effect** |
| Sensitivity matrix (S10) | Unadjusted vs HC2/HC3; nominal-1/3 vs count-normalized weights (policy); profile-clustered uncertainty; raw vs winsorized spend; Newcombe interval for conversion differences; coarse-history encoding (development only); development-only resplit stability |
| Heterogeneity (S11) | Newbie 0/1 and purchase profile (mens×womens, four cells); channel as optional third grouping. Visit only. Support flag when either compared arm has < 200 rows or < 20 visits. Effect-difference (heterogeneity) Wald tests, plus a joint arm×covariate interaction Wald test in the HC2 interacted model. Exploratory |
| Sparse conversion (S12) | Event counts and denominators reported; no conversion CATE, no purchaser conditioning |

## 6. Features and models (document 04)

- Raw X: recency, history, mens, womens, newbie, channel, zip_code; `history_segment` excluded.
- Basis (9 columns): recency, log(1+history), mens, womens, newbie, channel_Web, channel_Multichannel, zip_Urban, zip_Surburban (references Phone/Rural). Recency and log-history are standardized with means/SDs fitted on the model's training rows only (fold-local in CV). Binary columns are unscaled. Unknown category levels raise an error.
- **S-learner (MVP):** one L2 logistic model on [basis, 1{A=M}, 1{A=W}, 1{A=M}×basis, 1{A=W}×basis] (29 columns + intercept).
- **T-learner (polished):** three L2 logistic models on the basis, one per TRAIN arm, common C. **Gate:** each TRAIN arm has ≥100 visits and ≥100 non-visits; each binary basis level (value 0 and 1 of every indicator) has ≥20 visits and ≥20 non-visits within each arm; all fits converge. Failure omits the T-learner and is recorded.
- Solver lbfgs, float64, tol 1e−6, max_iter 2,000; L2 via scikit-learn's `l1_ratio=0` (the `penalty` argument is deprecated in the installed version). Convergence = `n_iter_ < max_iter` and no convergence warning.
- C ∈ {0.1, 1, 10}; three-fold CV stratified by arm **inside TRAIN** (scikit-learn `StratifiedKFold`, shuffle, seed stream `cv`); selection metric = mean over folds of held-out binary log loss (T-learner: per-fold log loss pooled over all held-out rows of the three arms, i.e. sample-weighted); ties within 1e−6 prefer smaller C. Fit the chosen C on all TRAIN. No class weights, oversampling or recalibration. No refit on TRAIN+VALIDATION.
- Diagnostics: TRAIN-CV and VALIDATION log loss, Brier score, arm-level and decile calibration. These describe response prediction, not uplift quality.

## 7. Policies (document 04)

- Constants: no-send (0), men's-all (M), women's-all (W).
- Fixed purchase-history rule: M if mens=1, womens=0; W if mens=0, womens=1; otherwise 0. (Historical merchandise purchase, not gender.)
- Learned policies: g(a,X) = m̂(a,X) − m̂(0,X) − κ; choose the largest strictly positive gain, else 0; exact ties → 0, then M before W.
- Capacity q < 1: among rows with a positive best gain, contact at most ⌊qN⌋ ordered by gain descending, ties by ascending SHA-256 of `CampaignLab/policy-tiebreak/v1/<row_id>`. Feature-independent quota baselines rank rows by SHA-256 of `CampaignLab/contact-baseline-v1/<row_id>` and send the first ⌊qN⌋ the M (or W) campaign. The fixed rule is capped the same way when it exceeds ⌊qN⌋.
- Grids: q ∈ {0, 0.25, 0.5, 0.75, 1}; κ ∈ {0, 0.005, 0.02, 0.05} visits per contact. **Main claim: q = 1, κ = 0.**
- Action functions receive only permitted covariates, row IDs, fitted model parameters and q/κ; they reject frames containing arm, outcome or split columns.

## 8. Validation selection (document 04)

1. C* = argmax over constants of the VALIDATION allocation-normalized IPW visit value; ties within 1e−6 prefer 0, then M, then W.
2. Best targeting candidate among {fixed rule, S-learner, T-learner if gated in} by VALIDATION value at q=1, κ=0. Every candidate whose value is within one paired SE of the best (paired stratified SE of the candidate-minus-best difference on the same VALIDATION rows) is eligible; choose the first eligible in the order fixed rule → S-learner → T-learner. A degenerate zero SE uses the deterministic simpler fallback.
3. π* is locked even if a constant looks better on VALIDATION.
4. Non-selected candidates' TEST actions are also locked and reported as **secondary, not-selected** rows; they cannot replace π* after TEST.

## 9. TEST evaluation (document 04)

- Allocation-normalized IPW: V̂(π) = Σₐ mean_{i:Aᵢ=a}[1{π(Xᵢ)=a}Yᵢ]; observed TEST arm fractions are **not** documented individual propensities. Nominal 1/3 Horvitz–Thompson value is a sensitivity.
- Paired difference Δ̂(π,b) with conservative stratified SE √Σₐ s²(d|a)/nₐ, ordinary 95% CI; paired within-arm bootstrap (5,000 replicates; the same resampled rows for every policy; models/actions fixed) percentile CI; stability check with an additional predeclared 5,000 replicates (target endpoint change ≤ 0.1 pp, actual change reported).
- Comparisons: Δ(π*, C*) (frozen comparator) and Δ(π*, 0), Δ(π*, M), Δ(π*, W). "Beats the strongest constant family" requires all three one-sided Bonferroni lower bounds Δ̂ − z₁₋₀.₀₅/₃·SE to exceed 0 (and, for worthwhile-gain wording, δ).
- Matched support (rows with A = π(X)) and matched events by arm are reported.
- Sensitivities: nominal 1/3 HT; profile-clustered SE of paired differences; frozen TRAIN-nuisance doubly robust value (nuisance = the TRAIN-fitted S-learner, the MVP response model; the T-learner is used instead only if π* is the T-learner) with the same paired bootstrap.
- Capacity/cost grid: π*(q, κ) against feasible baselines (no-send and hash-quota M/W at the same q; the capped fixed rule shown alongside). Exploratory; no simultaneous coverage across grid cells.
- **Practical margin δ = 0.005** (0.5 pp; illustrative, not business-validated).

| Evidence for Δ(π*, C*) | Category |
|---|---|
| CI lower bound > δ | Meaningful gain versus frozen comparator (family wording additionally needs all three simultaneous bounds) |
| CI upper bound < 0 | Evidence targeting is worse |
| 0 < lower bound and upper bound < δ | Statistically detectable gain below δ (does not satisfy the practical requirement) |
| upper bound < δ (otherwise) | Evidence excludes a gain as large as δ (not proof of zero) |
| otherwise | Insufficient evidence to justify personalization |
| Sensitivities change the category | Fragile; prefer the simpler policy |

## 10. Economics (document 08) — hypothetical only

- **Panel A (engagement utility):** b × [V(π) − V(0)] − c × contact_rate, b ∈ {0.25, 1, 2}, c = bκ.
- **Panel B (historical gross spend with assumed margin):** m × [V_spend(π) − V_spend(0)] − c × contact_rate, m ∈ {0.1, 0.3, 0.5}, c ∈ {0, 0.01, 0.05}, using the same locked visit-based policies.
- Panels are never added together and neither is observed profit. Matched purchase support is shown.

## 11. Reproducibility

Primary seed 2027 with purpose-specific `SeedSequence` streams (config `seeds.streams`). Deterministic artifacts must reproduce exactly; floating estimates within 1e−10 absolute / 1e−8 relative. Bootstrap memory is processed in batches of 250 replicates.

## 12. Interpretation clarifications recorded at freeze

These are not changes to the blueprint; they make ambiguous points concrete before data access:

1. **Python version:** blueprint proposed 3.12 "if supported"; 3.12 is not installed on this Mac and the available supported interpreter is CPython 3.14.3. All dependencies install and are pinned for 3.14.3.
2. **Winsorization threshold:** SAP S10 says "TRAIN-estimated 99.5th percentile". The primary reading uses all assigned TRAIN rows (zeros retained, matching the per-assigned-customer estimand). Because ~0.9% of rows have positive spend, this threshold cuts into the body of the purchaser distribution, so a supplementary threshold at the 99.5th percentile of *positive* TRAIN spend is also frozen. Both are sensitivity estimands; raw spend stays primary.
3. **Scaling:** only the two continuous basis columns are standardized (TRAIN/fold-fitted).
4. **T-learner subgroup support** is operationalized as in §6.
5. **One-SE rule** uses the paired stratified SE of the candidate-minus-best VALIDATION difference.
6. **DR nuisance** model is fixed in advance as in §9.
7. **Module layout:** two small helper modules (`config.py`, `governance.py` for hashing/lock/access logging) and `simulation.py` (synthetic validation) are added to the blueprint's module list.

## 13. Deviation log

| Date | Stage | Deviation | Cause | Effect |
|---|---|---|---|---|
| 2026-10-09 | M1 | Python 3.14.3 instead of proposed 3.12 | 3.12 not installed; 3.14 supported by all pinned packages | None on methods; versions recorded in `requirements.lock` |

Further entries are appended as they occur (see also `docs/implementation_log.md`).
| 2026-10-09 | M7 | Seaborn installed (blueprint stack) but not used; figures drawn with Matplotlib directly | Fine-grained control over interval styles and labels | None on results; not claimed as a used tool |
| 2026-10-09 | M7 | One supplementary figure (hypothetical economics, Panels A and B) added to the seven planned figures | Panels must be shown separately and labeled hypothetical | Seven planned figures unchanged |
