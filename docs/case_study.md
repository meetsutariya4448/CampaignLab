# Case study — CampaignLab

*Portfolio write-up of a completed, reproducible retrospective analysis. Every number is taken from `reports/tables/`; see the [technical report](../reports/technical_report.md) for full tables and methods.*

## 1. The question

A retailer can email customers a men's-merchandise campaign, a women's-merchandise campaign, or nothing. Two decisions follow: **which campaign works on average**, and **is it worth personalizing** — sending different customers different campaigns — instead of sending one campaign to everyone? The data come from Kevin Hillstrom's public 2008 experiment: 64,000 recent purchasers, nominally randomized in thirds, with visits, purchases and spend recorded for two weeks.

## 2. Data, rights and the identity problem

The exact publisher file (3,964,977 bytes, pinned SHA-256) passed every contract check in both Python and SQL. Two quality facts shaped the analysis:

- **6,562 rows are exact copies of another row** (1,072 groups), and 7,791 rows repeat a pre-treatment profile. Equal values do not prove the same customer, and deduplicating on outcome columns would change the experiment, so **all rows were kept** and a profile-clustered uncertainty check was added. It changed standard errors by under 2%.
- **Five rows sit on rounded spend-bucket boundaries.** The redundant bucket field was excluded from features and the rows were kept.

No license for redistributing the data was found, so the repository ships only code and aggregate results. It downloads and verifies the file at run time.

## 3. Freezing the plan before looking

Before any arm-by-outcome number existed, the analysis plan and configuration were committed. That covered estimands, the δ = 0.5 pp practical margin, model grid, selection rules, uncertainty methods, and capacity and cost grids. One limitation is disclosed: schema and global counts had been inspected during planning, so this is not a blinded preregistration.

The information flow was then enforced in code:

```
split (hash of row ID, within arm) → DEVELOPMENT inference (provisional)
TRAIN fits models → VALIDATION picks the comparator and the targeting policy
→ LOCK (hashes of data, split, code, config, models, 66 TEST action vectors)
→ TEST evaluated once → full-sample results released
```

The access log shows TEST outcomes were first read 23 seconds after the lock was written, and the lock was verified again at that moment.

## 4. Did the emails work? (estimated historical effects, N = 64,000)

| | Men's − no email | Women's − no email |
|---|---|---|
| Visit (primary) | **+7.66 pp** (95% CI 7.00 to 8.32) | **+4.52 pp** (3.89 to 5.16) |
| Purchase | +0.68 pp (0.50 to 0.86) | +0.31 pp (0.15 to 0.47) |
| Spend per assigned customer | +$0.77 (0.49 to 1.05) | +$0.42 (0.17 to 0.68) |

Both primary effects survive Holm adjustment. Interacted covariate adjustment (HC2/HC3), a stratified bootstrap and randomization inference agree with them. The provisional development estimates (+7.57 and +4.71 pp) were close to the final ones.

## 5. Heterogeneity that doesn't help targeting

Prior-purchase history changes effect sizes a lot (exploratory). For customers who bought only men's items, the women's email added just +1.11 pp. For customers who bought both, the men's email added +13.44 pp. **But the best action barely changes.** The men's email has the larger estimated effect in every profile except women's-only buyers, where the women's email leads by only +0.34 pp. When one campaign is best for nearly everyone, there is little for personalization to gain.

## 6. The targeting test

The candidates were a frozen purchase-history rule and two logistic uplift-style models: an S-learner with all arm × feature interactions, and a T-learner that passed its support gate.

- **VALIDATION** chose men's-for-everyone as the comparator and the S-learner as the targeting policy. The one-SE simplicity rule decided an exact tie with the T-learner.
- **TEST**, evaluated once: the S-learner minus men's-for-everyone was **−0.44 pp (95% paired CI −1.29 to +0.42)**.

The upper bound is below the +0.5 pp practical margin, so **the evidence excludes a worthwhile gain**. The paired bootstrap, nominal-1/3 weighting, a doubly robust estimator and profile clustering all give the same category. Superiority over the constant family is not established. The intuitive purchase-history rule was worse than men's-for-everyone (−1.39 pp, −2.64 to −0.14).

Under contact budgets, the targeting policy was compared with *feasible* hash-quota baselines; send-all is impossible at partial capacity. At 25% capacity the difference was +0.35 pp (−0.71 to +1.41): inconclusive.

## 7. Recommendation

**Send the men's campaign to everyone** if a decision has to rest on this historical evidence. Then validate it, with real contact costs, in a contemporary randomized test. Personalization is not justified here.

The business scenarios are labeled hypothetical and kept in two separate panels:

- an assumed value per visit minus contact cost
- an assumed margin on gross spend minus contact cost

They are never added together and never called profit.

## 8. Checks on the method itself (synthetic)

Known-truth simulations test the estimators and the whole select-then-evaluate pipeline on simulated data. They check coverage, null rejection rates, and that a deliberately broken allocation assumption is detected. See the technical report, §10. These results describe the methods, not Hillstrom customers.

## 9. What I would do next

Run a prospective randomized test with documented allocation, delivery logs, customer IDs, real costs and margins, and enough sample to detect a 0.5 pp targeting gain. At the precision reached here, the TEST interval half-width for the key comparison was about 0.85 pp.
