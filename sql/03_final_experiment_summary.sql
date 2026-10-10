-- 03_final_experiment_summary.sql — full 64,000-row arm summaries.
-- Executed only by the release stage, after the policy lock and the locked TEST evaluation.
SELECT 'FULL' AS sample_scope, a.arm,
       count(*)                            AS n_rows,
       CAST(sum(o.visit) AS BIGINT)        AS visits,
       CAST(sum(o.conversion) AS BIGINT)   AS conversions,
       CAST(sum(o.spend_cents) AS BIGINT)  AS spend_cents,
       avg(o.visit)                        AS visit_rate,
       var_samp(o.visit)                   AS visit_var,
       avg(o.conversion)                   AS conversion_rate,
       var_samp(o.conversion)              AS conversion_var,
       avg(CAST(o.spend AS DOUBLE))        AS spend_mean,
       var_samp(CAST(o.spend AS DOUBLE))   AS spend_var
FROM outcomes o JOIN assignment a USING (row_id)
GROUP BY a.arm
ORDER BY a.arm;
