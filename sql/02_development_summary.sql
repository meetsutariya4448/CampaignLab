-- 02_development_summary.sql — provisional arm summaries on DEVELOPMENT (TRAIN + VALIDATION) only.
-- Reads exclusively from the dev_outcomes view, which excludes TEST rows. No full-sample summary.
SELECT 'DEVELOPMENT' AS sample_scope, arm,
       count(*)                          AS n_rows,
       CAST(sum(visit) AS BIGINT)        AS visits,
       CAST(sum(conversion) AS BIGINT)   AS conversions,
       CAST(sum(spend_cents) AS BIGINT)  AS spend_cents,
       avg(visit)                        AS visit_rate,
       var_samp(visit)                   AS visit_var,
       avg(conversion)                   AS conversion_rate,
       var_samp(conversion)              AS conversion_var,
       avg(CAST(spend AS DOUBLE))        AS spend_mean,
       var_samp(CAST(spend AS DOUBLE))   AS spend_var
FROM dev_outcomes
GROUP BY arm
UNION ALL
SELECT partition AS sample_scope, arm,
       count(*), CAST(sum(visit) AS BIGINT), CAST(sum(conversion) AS BIGINT), CAST(sum(spend_cents) AS BIGINT),
       avg(visit), var_samp(visit), avg(conversion), var_samp(conversion),
       avg(CAST(spend AS DOUBLE)), var_samp(CAST(spend AS DOUBLE))
FROM dev_outcomes
GROUP BY partition, arm
ORDER BY sample_scope, arm;
