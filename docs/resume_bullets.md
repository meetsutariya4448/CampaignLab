# Resume bullet drafts (not applied to any resume)

These are drafts for the user to review. **No actual resume was edited.** Each figure maps to a row in [`evidence_ledger.md`](evidence_ledger.md). This is personal, retrospective work on a public dataset, not employer work, a live experiment or a deployment.

## Three verified drafts

1. **Retrospective experiment analysis.** Analyzed a publicly released, publisher-described randomized email experiment (64,000 customers, 3 arms) with SQL (DuckDB) and Python. Estimated two-week visit-rate lifts of +7.66 pp (95% CI 7.00–8.32) for the men's campaign and +4.52 pp (3.89–5.16) for the women's campaign versus no email, with Holm-adjusted tests, robust covariate adjustment and documented data-identity limitations.
   *Evidence: ledger rows 1–11.*

2. **Honest targeting evaluation.** Built interacted logistic uplift models (S-/T-learners) under a frozen plan and a hash-locked train/validation/test protocol. Evaluated the selected policy once on 12,802 held-out customers against all constant baselines. It did not beat sending the best campaign to everyone (−0.44 pp, 95% paired CI −1.29 to +0.42), which ruled out a 0.5 pp practical gain, so I recommended the simpler policy.
   *Evidence: ledger rows 14–18 and 21.*

3. **Reproducible decision reporting.** Shipped a reproducible Python/SQL study: locked environment, 85 automated tests (data contracts, estimator arithmetic, leakage and lock controls, known-truth simulations), a clean rerun that reproduces every reported table, seven figures, and a decision memo. Capacity limits and contact costs were kept as explicitly hypothetical scenarios.
   *Evidence: ledger rows 19–24 and `docs/reproduction.md`.*

## Usage notes

- Say "retrospective analysis of a public randomized experiment", not "ran an experiment".
- Do not convert the visit-rate effects into revenue or attribute them to an employer.
- If space is short, bullet 2 is the most distinctive: a negative held-out result reported honestly.
- List only tools that were used: Python, pandas, NumPy, SciPy, statsmodels, scikit-learn, DuckDB/SQL, Matplotlib, pytest, Git.
