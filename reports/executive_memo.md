# CampaignLab — executive decision memo

**To:** Ecommerce growth lead (hypothetical stakeholder) · **Re:** Which email campaign to send, and whether to personalize · **Basis:** retrospective analysis of the public Hillstrom (2008) randomized email experiment, 64,000 recent purchasers, two-week outcomes.

## Recommendation

**Send the men's email to everyone (the simple constant policy). The locked targeting policy did not beat it on held-out data; personalization is not justified by this evidence.** Use the simple constant policy (men's email to everyone) if a decision must be made from this historical evidence, and validate it (and its real costs) in a contemporary randomized test before relying on it.

## What the historical experiment shows (estimated assignment effects, full sample N = 64,000)

| Outcome | Men's email − no email | Women's email − no email |
|---|---|---|
| **Visit within two weeks (primary)** | **+7.66 pp** (95% CI 7.00 to 8.32) | **+4.52 pp** (95% CI 3.89 to 5.16) |
| Purchase (secondary) | +0.68 pp (95% CI 0.50 to 0.86) | +0.31 pp (95% CI 0.15 to 0.47) |
| Gross spend per assigned customer (secondary) | +$0.77 (95% CI 0.49 to 1.05) | +$0.42 (95% CI 0.17 to 0.68) |

Both campaigns raised visits relative to no email; both primary contrasts remain significant after Holm adjustment (adjusted p = 5.5e-113 and 1.9e-44). The descriptive women's-minus-men's visit contrast was -3.14 pp (95% CI -3.84 to -2.43; not a planned primary test). Purchases are sparse (578 in total), so the spend and conversion effects are less precise. These are 2008 effects for this population; they do not establish today's effect sizes.

## Did personalization help? (held-out TEST, N = 12,802, evaluated once after a pre-unblinding lock)

- The constant comparator chosen on VALIDATION was **men's email to everyone**; the targeting candidate chosen on VALIDATION was the **interacted logistic S-learner policy**.
- On TEST, the targeting policy minus men's email to everyone: **-0.44 pp** (95% paired CI -1.29 to 0.42). The upper bound is below the pre-set practical margin of +0.5 pp, so **the evidence rules out a worthwhile gain of that size** (it does not prove the difference is exactly zero). Bootstrap, nominal-design, doubly robust and profile-clustered checks all give the same category.
- Versus each constant: no email to anyone +7.59 pp (simultaneous one-sided lower bound +5.95 pp), men's email to everyone -0.44 pp (simultaneous one-sided lower bound -1.36 pp), women's email to everyone +3.79 pp (simultaneous one-sided lower bound +2.29 pp). Superiority over the strongest-constant family is **not established**.
- With a contact budget (e.g. 25% of customers), targeting versus a feasible men's quota was +0.35 pp (95% CI -0.71 to 1.41): inconclusive (exploratory).

## Business framing (hypothetical, not observed profit)

Visits are engagement, not profit. For men's email to everyone versus no email, its interval stays above zero in all 12 frozen value/cost scenarios (assumed $0.25–$2 per extra visit); under assumed 10–50% margins on historical gross spend the margin proxy is imprecise; its interval includes zero for m = 0.1 with c = $0.05. These are scenario arithmetic on assumed inputs and must not be added together or reported as revenue.

## Limits and what would change the decision

The allocation mechanics, customer identity and email delivery are not documented; the population is 2008 recent purchasers; costs and margins are unknown; purchases are sparse. Before deploying anything: run a contemporary randomized test with real contact costs, deliverability/compliance logging, independent customer IDs, and enough sample to detect a practically meaningful targeting gain.
