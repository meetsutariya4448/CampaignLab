# Rights, attribution and assumptions

## Source attribution

Data: Kevin Hillstrom, *MineThatData E-Mail Analytics and Data Mining Challenge*, MineThatData blog, March 20, 2008 — <https://blog.minethatdata.com/2008/03/minethatdata-e-mail-analytics-and-data.html>. Original file: <http://www.minethatdata.com/Kevin_Hillstrom_MineThatData_E-MailAnalytics_DataMiningChallenge_2008.03.20.csv>.

## Rights position

- The publisher invites analysis of the file. **No explicit redistribution license for the data was found.** An invitation to analyze is not permission to rehost rows.
- This repository therefore **does not contain or redistribute** the raw CSV, processed rows, the DuckDB database, row IDs, split membership, per-row predictions/actions, or serialized models. These live in git-ignored `data/` and `artifacts/private/` directories.
- Reproduction downloads the original file locally and verifies its SHA-256 before use.
- The repository's code license (MIT) covers **only the authored code and documentation**. It does not license the Hillstrom data or any row-level derivative.
- Published content is limited to code, plans, and reviewed **aggregate** tables/figures (counts, means, effect estimates, intervals, model coefficients). Aggregate cells are computed over thousands of rows; no published table has a cell that identifies or reconstructs an individual row.
- Raw-data redistribution remains blocked unless artifact-specific rights are established.

## Assumption register (from blueprint document 12, with project status)

| ID | Statement | Category | How the project handles it |
|---|---|---|---|
| A1 | The publisher describes random assignment with nominal one-third arms | Documented source statement; operational execution unverified | Causal interpretation is conditional on faithful assignment; no seed/strata invented; allocation shown descriptively |
| A2 | Each row is a distinct, independent customer | Working assumption; identity unknown | Default row-level uncertainty, qualified; profile-clustered sensitivity; no deduplication |
| A3 | Consistent treatment/outcome definitions, no material interference | Untestable identification assumptions | Stated as limitations; robust SEs do not fix violations |
| A4 | Pre-treatment fields precede assignment; outcomes cover two weeks | Publisher definitions | Seven-field feature allowlist; no invented timestamps or pre-period visits |
| A5 | Source-ordinal hash split, 60/20/20 within arm | Frozen protocol | Implemented and reconciled in M2 |
| A6 | Practical margin δ = 0.005 visit probability | Illustrative design choice, not stakeholder-validated | Frozen at M0; reported as 0.5 pp; never an observed lift |
| A7 | Capacity, cost, value and margin grids | Explicitly hypothetical scenarios | Frozen before TEST; visit-value proxy and spend-margin proxy kept separate |
| A8 | Exchangeability/support with count-normalized evaluation weights | Estimation assumption | Constant-policy identities tested; nominal-1/3 sensitivity; no fitted propensity model |
| A9 | Historical findings inform modern decisions only with new validation | Generalization limit | No modern performance, retention or profit claims |
| A10 | Public access does not establish redistribution rights | Rights unresolved | Code + aggregates only |
| A11 | Effort/runtime estimates | Planning estimates | Actual runtimes recorded from executed runs only |
| A12 | Package compatibility and tests | Engineering requirement | Verified by executed tests and a clean rerun (see implementation log) |

## Things this project cannot establish

Original operational randomization; true customer identity or dependence; source authenticity beyond the retrieved bytes; email delivery/compliance; contemporary effect sizes; actual margins, costs or profit; long-term or retention effects; individual-level treatment effects.
