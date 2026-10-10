# Implementation log

Chronological record of milestones, artifacts, checks, deviations and remaining work. Times are local (America, 2026-10-09). Results quoted here are copied from executed artifacts in `reports/tables/`.

## M0 — Plan freeze (complete)

- Read blueprint README and documents 01–12; verified every blueprint file against `blueprint_quality_audit.json` hashes (all matched).
- Wrote `config/analysis.yaml`, `docs/analysis_plan.md` (SAP v1.0, with disclosure of prior inspection and freeze-time interpretation clarifications), `docs/data_dictionary.md`, `docs/rights_and_assumptions.md`.
- Git commit `60d32e3` records the freeze **before** any arm-by-outcome summary, split-level outcome table, model fit or policy selection.

## M1 — Environment and acquisition (complete)

- Python 3.12 (blueprint proposal) is not installed; CPython **3.14.3** used (deviation logged in SAP §13). Isolated `.venv`; exact versions in `requirements.lock` (numpy 2.5.3, pandas 3.0.6, scipy 1.18.1, statsmodels 0.15.0, scikit-learn 1.9.1, duckdb 1.5.6, matplotlib 3.11.2, seaborn 0.13.2, PyYAML 6.0.3, pytest 9.1.1).
- Acquired the original publisher CSV over the original HTTP URL (HTTP 200). **3,964,977 bytes; SHA-256 `0e5893329d8b93cefecc571777672028290ab69865718020c78c7284f291aece` (matches the pin)**; 64,001 CRLF line endings. Stored read-only in ignored `data/raw/`; private provenance manifest in `artifacts/private/`.
- **Relocation:** the project was first created under `~/Documents/Codex/2026-10-09/.../CampaignLab`; at the user's instruction it was copied with `rsync -a` (history preserved, `60d32e3` intact) to `~/Desktop/CampaignLab`, the venv was recreated there with identical pinned versions, no absolute paths needed changing (all paths derive from the package location), and the Phase 1 checks were re-run successfully from the new location. Final deliverables live in `outputs/CampaignLab_Final/` inside the project (git-ignored copies).

## M2 — Validation, split and SQL (complete)

- Python typed contract and DuckDB SQL contract (`sql/01_validate.sql`) both report **zero hard-check failures** (25 named checks).
- Quality facts reproduce the planning record exactly: arms 21,306 / 21,307 / 21,387; 9,394 visits; 578 conversions; 578 positive-spend rows; 1,072 full-row matching groups, 6,562 excess rows (7,634 rows involved, largest group 31); 56,209 distinct pre-treatment profiles (7,791 excess, largest 83); 5 history-bucket boundary cases (rounded 100 ×2, 200 ×2, 500 ×1). All retained.
- SQL and Python agree on all global counts, total history cents and split totals.
- Split executed exactly as frozen: **TRAIN 38,399 / VALIDATION 12,799 / TEST 12,802** (by arm 12,783/4,261/4,262; 12,784/4,261/4,262; 12,832/4,277/4,278); disjoint and complete; private manifest with membership checksum.
- Logical tables `covariates`, `descriptive`, `assignment`, `outcomes`, `split`; development view `dev_outcomes` excludes TEST.
- Code-level access control: development stages can load TRAIN/VALIDATION outcomes only; TEST needs a verified-lock token; full sample needs an evaluation-complete record; each outcome load is logged.
- Tests at this point: `test_data.py` 28 passed (incl. private pinned-artifact test), `test_inference.py` 19, `test_models.py` + `test_policy.py` 35, `test_pipeline.py` 1 (synthetic end-to-end access/lock test) — 83 passed.

## Remaining work

M3–M9 (below as they complete).

## M3–M4 — Development inference (complete, provisional)

- `develop` stage loaded only DEVELOPMENT outcomes (N = 51,198; access log). Development SQL (`02_development_summary.sql`) and Python agree on counts, cents and means.
- Provisional primary ITT (visit): M − 0 = +7.57 pp (95% CI 6.83 to 8.31), W − 0 = +4.71 pp (3.99 to 5.42); Holm-adjusted p < 1e−37 for both. Covariate adjustment (HC2/HC3), profile clustering and the stratified bootstrap left these essentially unchanged.
- Spend-tail thresholds frozen from TRAIN: all-row 99.5th percentile = 60.7803; positive-spend 99.5th percentile = 499.00 (equal to the maximum, so the supplementary winsorization caps no rows; reported as such).
- Exploratory: no row has mens = 0 and womens = 0, so the purchase-profile grouping has three non-empty cells (the "neither" cell is empty).

## M5 — TRAIN fitting (complete)

- S-learner: TRAIN-CV selected C = 0.1 (mean log loss 0.398788; C grid differences < 3e−5); converged.
- T-learner: all 48 support-gate checks passed; C = 1.0; all fits converged → included (polished scope).
- Development-only diagnostics: profile-grouped CV log loss 0.398691 (no evidence of memorization through matching profiles); coarse history encoding 0.398976; main-effects-only ablation gives a constant policy (100% Mens E-Mail on VALIDATION), confirming the need for interactions; 20 development resplits give S-learner minus best-constant differences between −0.73 and +0.84 pp (each SE ≈ 0.5 pp).

## M6a — VALIDATION selection (complete)

- C* = **const_M** (VALIDATION values: 0 → 0.1058, M → 0.1847, W → 0.1564).
- Targeting values: fixed rule 0.1743, S-learner 0.1864, T-learner 0.1866. π* = **S-learner** under the frozen one-paired-SE simplicity rule.
- **Boundary note:** S and T actions differ on 14 of 12,799 VALIDATION rows, producing one discordant matched visit; the T − S gap and its paired SE are then both exactly 1/n_W (floating difference 8.5e−18). The frozen rule ("within one paired SE", implemented as ≤) makes S eligible; no code was changed after this was observed.

## M6b — Lock (complete)

- `artifacts/private/lock_manifest.json`, SHA-256 `59e7e741399d518b325e7306c323ed19391cc4a259e0f9736ef24d4e3a9dd0ec`, created 2026-10-10T01:03:14Z (UTC).
- Records dataset/provenance/split hashes, 11 code/SQL hashes, config hash, environment, model parameter hashes, selections (π* = s_learner, C* = const_M), δ = 0.005, grids, economics, uncertainty protocol/seeds, DR nuisance (S-learner), frozen thresholds and checksums of 66 TEST action vectors and all TEST predictions.
- Access log at lock time contains only `development`, `train`, `validation` and development-SQL scopes.

## M6c — Locked TEST evaluation (complete)

- `evaluate` re-verified the lock (all hashes and the 66 action checksums recomputed and matched) and only then loaded TEST outcomes (first `test` access: 2026-10-10T01:03:37Z, 23 s after the lock).
- π* (S-learner) vs C* (const_M), allocation-normalized IPW, TEST N = 12,802: **−0.44 pp (95% paired CI −1.29 to +0.42)**; paired bootstrap (5,000) −1.28 to +0.41; nominal-1/3 HT −0.42 pp (−1.29 to +0.45); TRAIN-nuisance DR −0.42 pp (−1.22 to +0.38); profile-clustered SE ratio 1.005. Category **"evidence excludes a gain as large as δ = 0.5 pp"** under every sensitivity (not fragile).
- π* vs const_0: +7.59 pp (6.08 to 9.10); vs const_W: +3.79 pp (2.41 to 5.18). Constant-family one-sided Bonferroni lower bounds: 0 → +5.95 pp, M → −1.36 pp, W → +2.29 pp ⇒ superiority over the constant family is **not** established.
- Secondary (not selected): fixed rule vs const_M −1.39 pp (−2.64 to −0.14, worse); T-learner identical TEST value to S-learner.
- Bootstrap stability: largest endpoint change between 5,000 and 10,000 replicates 0.047 pp (target ≤ 0.1 pp).
- Capacity/cost grid (exploratory): at every q < 1, π* vs the feasible men's hash quota has an interval including zero (e.g. q = 0.25: +0.35 pp, −0.71 to +1.41).
- No policy, hyperparameter, comparator, feature, threshold or δ was changed after TEST access.

## M6d — Full-sample release (complete)

- Release token issued from the evaluation-complete record; `03_final_experiment_summary.sql` and Python agree.
- Primary ITT, N = 64,000: M − 0 **+7.66 pp** (95% 7.00 to 8.32; Bonferroni 97.5% 6.90 to 8.42); W − 0 **+4.52 pp** (95% 3.89 to 5.16; Bonferroni 3.80 to 5.25); Holm p 5.5e−113 and 1.9e−44.
- Secondary: conversion +0.68 pp (M), +0.31 pp (W); spend per assigned customer +$0.77 (M), +$0.42 (W). Bootstrap, HC2/HC3 adjustment and profile clustering agree closely; all-row winsorization changes the estimand (+$0.32 / +$0.16).
- Exploratory heterogeneity: purchase profile modifies effects (W−0: 1.1 pp mens-only vs 7.4 pp womens-only), newbie and channel do not detectably.
