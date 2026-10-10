# Interview preparation — CampaignLab

These notes cover what was actually built and found. They are reasoning to rehearse, not a script to memorize. Practice each point on a whiteboard with different numbers. All results come from `reports/tables/`.

## One-minute overview

- **0–10 s, the decision.** A retailer can send a men's email, a women's email, or nothing. Which works, and is personalization worth it? I used the public Hillstrom experiment: 64,000 customers randomized into thirds, with visits measured over two weeks.
- **10–25 s, the experiment.** I estimated intention-to-treat effects. Men's email raised the two-week visit rate by 7.7 points and women's by 4.5 points versus no email. Both survive Holm correction. I kept all 64,000 rows even though about 6,500 are exact duplicates, because equal values don't prove the same customer.
- **25–40 s, personalization.** I froze the plan, split the data by a hash of the row ID, fit uplift models on TRAIN, picked the comparator and the policy on VALIDATION, and locked everything before touching TEST.
- **40–55 s, the result.** On TEST the learned policy was 0.44 points *below* simply sending everyone the men's email, with a 95% interval of −1.29 to +0.42. That rules out a gain worth caring about, so I recommend the simple policy.
- **55–60 s, the caveat.** Visits aren't profit, and this is 2008 data. The next step is a modern randomized test with real costs.

## Five-minute technical walkthrough

1. **Data and design (minute 1).** The publisher describes nominal one-third random assignment, and the counts are 21,306 / 21,307 / 21,387. There are 578 purchases in total, so visit is the primary outcome. Of the 7,634 rows in identical-row groups, 6,562 are excess copies. They were kept and handled with a profile-clustered check. The exact file hash is pinned.
2. **Estimation (minute 2).**
   - Estimator: difference in means with SE √(s²₁/n₁ + s²₀/n₀), Holm over the two primary contrasts, and separate Bonferroni 97.5% simultaneous intervals.
   - Adjustment: Lin-style centered, fully interacted OLS with HC2 errors (HC3 as a check). It cut the visit SEs by about 1.5% and moved no conclusion.
   - Spend: a within-arm bootstrap. Conversion: Newcombe intervals.
3. **Models (minute 3).**
   - Nine-column basis with log(1+history), standardized on TRAIN only and refit inside each CV fold.
   - S-learner: one logistic model with the arm and all arm × feature interactions. Without interactions the policy is constant, and I demonstrated that with an ablation.
   - T-learner: three arm-specific models, gated on support.
   - C chosen by three-fold TRAIN-CV log loss.
4. **Evaluation (minute 4).**
   - VALIDATION picked men's-for-all as C* and the S-learner as π*. The S-learner won on simplicity after an exact one-SE tie with the T-learner.
   - The lock recorded the hashes, then TEST was read once.
   - Value estimator: allocation-normalized IPW, which equals the arm mean for a constant policy.
   - Uncertainty: paired differences on the same rows, a paired within-arm bootstrap, and one-sided Bonferroni bounds against all three constants.
   - Capacity limits use hash-quota baselines.
5. **Decision (minute 5).** Δ = −0.44 pp, 95% CI −1.29 to +0.42. The upper bound is below δ = 0.5 pp, so a worthwhile gain is excluded. Nominal-1/3, DR, bootstrap and clustering all agree. The economics are hypothetical and kept in two separate panels. What would change my mind: a modern test with real costs and enough power.

## Deep-dive outline (20–30 minutes)

1. Derive identification of E[Y(a) − Y(0)] under randomization, and why conditioning on visitors or purchasers breaks it.
2. Toy variance: compute SE for arms {1,0,1,1} vs {0,0,1,0} (Δ = 0.5, SE = √0.125). This fixture is in `tests/test_inference.py`.
3. Multiplicity families: primary (2, Holm), secondary (4, Holm), policy family (3 constants, one-sided Bonferroni), exploratory (none claimed).
4. IPW derivation, the constant-policy identity, and the paired Δ variance (tested in `tests/test_policy.py`).
5. DR: augmentation plus weighted residual; why it stays unbiased with a bad outcome model under correct allocation (synthetic test).
6. Artifacts: the lock manifest, the access log, and the end-to-end tamper test (`tests/test_pipeline.py`).
7. Duplicates, sparse purchases, quotas, and which financial claims are and aren't supportable.
8. Show figures 3, 5, 6 and 7 and the decision table.

## Thirty-six questions with the reasoning I'd give

1. **What exactly is a row?** It is one source record, labeled `hillstrom-2008-v1:<ordinal>`. The publisher says rows are customers, but there is no customer ID, so "one row = one independent customer" is a working assumption, not a verified fact.
2. **(Hard) Why keep the 6,562 excess matching rows?** See the expanded answer below.
3. **Which fields come before treatment?** Recency, history, mens, womens, newbie, channel and zip_code describe the year before the campaign. The segment column is the assignment, and visit, conversion and spend are two-week outcomes. mens and womens record past merchandise purchases, not gender.
4. **Does the source give true propensities?** No. It describes nominal one-third allocation; there is no seed, strata or log. I weight by the observed TEST arm fractions and label them as such, and I report nominal-1/3 Horvitz–Thompson as a sensitivity. Both gave the same decision.
5. **Can balance prove randomization?** No. The largest |SMD| was 0.017 across 12 features and three pairs. That is consistent with randomization but is only a diagnostic; the design claim rests on the publisher.
6. **Why is visit primary?** It matches the engagement question, and there are 9,394 visits versus 578 purchases. Conversion and spend are secondary and reported with their event counts.
7. **What makes the ITT causal?** Exchangeable assignment, consistent arm definitions, no interference, accurate measurement, and keeping every assigned row. I never condition on opens, visits or purchases.
8. **Why not spend among purchasers?** Purchase is affected by treatment, so purchasers differ across arms. My estimand is spend per *assigned* customer, zeros included: +$0.77 for men's versus no email.
9. **(Hard) Why delay full-sample ATEs until after the lock?** See below.
10. **How is the SE computed?** √(s²ₜ/nₜ + s²₀/n₀) with n−1 variances. It is conservative for the finite population and approximate for a superpopulation. The two primary contrasts share a control arm, so a joint statement needs their covariance; Holm and Bonferroni don't need independence.
11. **What does a 95% CI mean?** The procedure covers the true value in 95% of repetitions under its assumptions. My synthetic simulations check that empirically. It is not a 95% posterior probability for this one interval.
12. **(Hard) What can an inconclusive interval establish?** See below.
13. **Why Holm?** It controls the family-wise error rate for the two planned primary tests and is valid under dependence. The shared control arm makes the tests dependent. Secondary and exploratory results sit in separate families.
14. **Are your ordinary CIs Holm-adjusted?** No. The table has three separate columns: individual 95% CIs, Holm-adjusted p-values, and Bonferroni 97.5% simultaneous CIs for the primary pair (6.90–8.42 and 3.80–5.25 pp).
15. **(Hard) How is a CATE identifiable when individual effects aren't?** See below.
16. **Why linear adjustment for a binary outcome?** The target is a risk difference. Centered covariates with full arm interactions (Lin) give a consistent average-effect estimate with robust HC2 errors. Logistic coefficients are odds ratios, a different estimand. The adjusted M − 0 was +7.61 pp versus +7.66 pp unadjusted.
17. **Why no CUPED?** There are no pre-period visits. Historical spend is already in the regression adjustment, and I didn't invent a pre-period metric.
18. **What's wrong with comparing two subgroups' p-values?** A difference in significance is not a significant difference. I report Wald heterogeneity tests and explicit differences of effects, all labeled exploratory. For newbie the M − 0 difference was −0.25 pp with p = 0.71.
19. **Can you report RMSE of uplift predictions?** No. Individual counterfactuals are never observed. I report log loss and Brier for *response* prediction (VALIDATION log loss 0.4038), policy value for decisions, and known-truth error only in simulation.
20. **(Hard) Why are interactions necessary in the S-learner?** See below.
21. **When is a T-learner better or riskier?** Separate arm surfaces avoid shared shrinkage but split the data. Here each TRAIN arm had at least 1,364 visits and all 48 gate checks passed. It chose almost the same actions as the S-learner and had the same TEST value. There was no reason to prefer the more complex model.
22. **(Hard) Derive the value estimator and the constant identity.** See below.
23. **Why not accuracy or Qini?** Accuracy rewards predicting "no visit". Qini curves depend on their definition and don't compare against the strongest feasible constant. I evaluate the policy's value against frozen baselines.
24. **(Hard) Why is send-all unfair at 25% capacity?** See below.
25. **(Hard) Why paired bootstraps?** See below.
26. **(Hard) Why not compare to the best TEST constant?** See below.
27. **(Hard) What does DR protect against?** See below.
28. **Why no cross-fitting with TEST labels?** The nuisance model was fit on TRAIN only and frozen in the lock, so TEST outcomes are never reused for fitting. Cross-fitting over TEST would put evaluation labels into the nuisance.
29. **How did you prevent preprocessing leakage?**
    - Scalers fit on TRAIN, and refit inside each CV fold.
    - A feature allowlist; policy functions reject frames that contain arm, outcome or split columns.
    - The split key uses only row IDs.
    - Tests show that perturbing labels outside training changes nothing.
    - The end-to-end test flips TEST outcomes and confirms the locked actions are unchanged.
30. **What does a permutation test test?** Under assumed complete randomization conditional on the arm counts, it tests the sharp null of no effect for any unit. I used 9,999 draws with p = (extreme + 1)/(draws + 1). The binary case has an exact hypergeometric shortcut, which I verified against plain label permutation. It isn't a test of the weak average-effect null, and it isn't valid for a policy chosen on the same labels.
31. **Do zeros or large spends justify dropping rows?** No. The raw mean is primary. Winsorization at the TRAIN 99.5th percentile is a different estimand: +$0.32 versus +$0.77. Capping at the positive-spend 99.5th percentile ($499) changed nothing.
32. **What do the financial scenarios measure?** Two separate hypothetical panels: (A) an assumed value per visit minus cost, and (B) an assumed margin times the historical gross-spend gain, minus cost. They are not added and not profit. TEST had only 61 matched purchases for men's-for-all.
33. **Could spillovers violate the analysis?** Yes. Shared households or forwarded emails would break no-interference, and the data have no household links. It is stated as an untestable assumption.
34. **Why doesn't this show modern ecommerce performance?** It is a 2008 population, campaign content and channel mix, with a two-week window and unknown costs. External validity needs new randomized data.
35. **What can be published?** Code, plans and aggregate tables and figures with attribution. Not raw rows, the DuckDB database, split membership, per-row predictions or model files. The MIT license covers my code, not the data.
36. **What would change your recommendation?** New randomized evidence where a targeting interval's lower bound clears the practical margin against the best constant, with stable sensitivity checks, real costs and capacity, and independent customers.

## The ten hardest, expanded

**Q2 — Duplicate ambiguity.**
- Two different customers can share all twelve values. Two people with recency 1, $29.99 history, men's only, suburban, phone, no email assigned and no visit are plausible.
- Full-row deduplication uses the outcome and arm columns, so it would remove more zero-outcome rows in some arms than in others and change the estimand.
- I kept every row and clustered SEs on the seven pre-treatment fields as a hypothetical worst case. The ratios were 0.99–1.02. Profile-grouped CV log loss (0.398691) was no better than random-fold CV (0.398788), so the models showed no sign of memorizing repeated profiles.
- None of this proves the rows are distinct people. It shows the conclusions are not sensitive to that plausible kind of dependence.

**Q9 — Information leakage.**
- Full-sample ATEs include TEST outcomes. Seeing them could steer the choice of features, comparator or margin, which indirectly tunes on TEST.
- So development inference used only TRAIN+VALIDATION (N = 51,198) and was labeled provisional. The lock was written, verified and committed before TEST was read, and the full sample was released only after an evaluation-complete record existed.
- The access log shows the order. The public data could still be read by hand, so this is disciplined workflow rather than secrecy, and I say so.

**Q12 — Inconclusiveness.** Define Δ = V(π*) − V(C*) and δ = 0.5 pp before looking.

| CI result | What it means |
|---|---|
| Lower bound > δ | Meaningful gain |
| Upper bound < 0 | The policy is worse |
| Upper bound < δ | A gain as large as δ is excluded, which is what I observed (−1.29 to +0.42) |
| Spans 0 and δ | Uninformative |

Excluding δ is not "zero effect" and not formal equivalence, because the interval still allows small gains up to +0.42 pp.

**Q15 — CATE vs individual effects.**
- τ(x) = E[Y(1) − Y(0) | X = x] is identified because randomization makes A independent of the potential outcomes given X, so E[Y | A=a, X=x] = E[Y(a) | X=x].
- Each person reveals one potential outcome, so their personal effect is never observed.
- The model's τ̂(x) carries estimation error, and individuals vary around τ(x). Policy value is still evaluable on held-out randomized data, because it only needs an average of observed outcomes where A = π(X).

**Q20 — S-learner structure.**
- With logit m(a,x) = f(x) + βₐ, the ranking of arms is the ranking of the β's for every x, because the inverse logit is monotone. So at q = 1 and κ = 0 the policy is constant.
- My ablation confirmed it: the main-effects-only model sent the men's email to 100% of VALIDATION.
- Adding a × x terms lets arms cross: f(x) + βₐ + γₐᵀx.
- Costs or quotas can still make a main-effects model contact only some rows, because gains differ in size on the probability scale. Flexibility does not prove real heterogeneity.

**Q22 — Value derivation.**
- E[1{A=π(X)} Y / e(A)] = E_X[ Σₐ e(a) · 1{π(X)=a} · E[Y(a)|X] / e(a) ] = E[Y(π(X))].
- With ê(a) = nₐ/N, the estimate is (1/N) Σᵢ 1{Aᵢ=π(Xᵢ)} Yᵢ N/n_{Aᵢ} = Σₐ mean over {A=a} of 1{π=a} Y.
- For a constant policy π ≡ a this is exactly the arm-a mean. My TEST table reproduces the arm means to machine precision.
- Nominal e = 1/3 gives 3·mean(1{A=π}Y), which differs slightly in finite samples, for example 18.49% vs 18.51% for men's-for-all.

**Q24 — Capacity.**
- At q = 0.25 the feasible class contacts at most ⌊0.25 · 12,802⌋ = 3,200 people. Send-all contacts 12,802, so it isn't in that class.
- The fair baseline is a feature-independent quota: hash-rank the IDs with a separate salt and send the first 3,200.
- π* versus the men's quota at q = 0.25 was +0.35 pp (−0.71 to +1.41).
- These intervals are conditional on this TEST cohort and the fixed actions. They ignore retraining and future-batch variability.

**Q25 — Paired uncertainty.**
- Var(V̂π − V̂b) = Var(V̂π) + Var(V̂b) − 2Cov. Both policies are scored on the same rows, so the covariance is large.
- The normalized contrast reduces to Σₐ mean over arm a of dᵢ, with dᵢ = (1{π=A} − 1{b=A})Y. Its SE is √Σ s²(d|a)/nₐ.
- Bootstrapping each policy independently throws away the covariance and widens the interval. Identical policies give d ≡ 0, which my tests check.
- None of this includes the variability from retraining or reselecting the policy.

**Q26 — Adaptive comparator.**
- The largest of three TEST means is biased upward. Attaching a single-comparison CI to that maximum understates the uncertainty, the winner's curse.
- I froze C* on VALIDATION (men's-for-all) and compared π* with all three constants using one-sided Bonferroni bounds (z = 2.128).
- The bound against men's-for-all was −1.36 pp, so superiority over the family was not established. The cost is some power, and I accept it.

**Q27 — DR limits.**
- V̂_DR = mean[ m̂(π(X),X) + 1{A=π(X)}/ê(A) · (Y − m̂(A,X)) ].
- If the allocation weights are right, the residual term corrects any bias in m̂. My test with a constant m̂ = 0.3 still recovers the arm means.
- If m̂ is right, the residual term has mean zero.
- If both are wrong, there is no guarantee.
- DR does not fix interference, unknown duplication, tuning on TEST, or a bogus allocation model. Fitting the nuisance on independent TRAIN data addresses reuse, not identification. Here DR gave −0.42 pp (−1.22 to +0.38), the same category as IPW.
