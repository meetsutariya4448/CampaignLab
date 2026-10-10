-- 01_validate.sql — explicit typing, hard contract checks, logical tables, global quality summary.
-- Inputs: raw_text (all VARCHAR + row_id/source_ordinal, original order) and split (row_id, arm, partition).
-- Variables set by Python: expected_rows, allowed_zip, allowed_channel, allowed_segment, allowed_history_segment.
-- Produces no arm-by-outcome summary: outcome facts here are global contract counts only.

CREATE OR REPLACE TABLE typed_rows AS
SELECT
    row_id,
    CAST(source_ordinal AS BIGINT)            AS source_ordinal,
    TRY_CAST(recency AS SMALLINT)             AS recency,
    history_segment,
    TRY_CAST(history AS DECIMAL(10, 2))       AS history,
    TRY_CAST(mens AS TINYINT)                 AS mens,
    TRY_CAST(womens AS TINYINT)               AS womens,
    zip_code,
    TRY_CAST(newbie AS TINYINT)               AS newbie,
    channel,
    segment,
    TRY_CAST(visit AS TINYINT)                AS visit,
    TRY_CAST(conversion AS TINYINT)           AS conversion,
    TRY_CAST(spend AS DECIMAL(10, 2))         AS spend,
    regexp_full_match(recency, '-?[0-9]+')               AS recency_format_ok,
    regexp_full_match(history, '[0-9]+(\.[0-9]{1,2})?') AS history_format_ok,
    regexp_full_match(spend, '[0-9]+(\.[0-9]{1,2})?')   AS spend_format_ok
FROM raw_text;

CREATE OR REPLACE TABLE contract_checks AS
SELECT 'row_count' AS check_name,
       CAST(CASE WHEN (SELECT count(*) FROM typed_rows) = getvariable('expected_rows') THEN 0 ELSE 1 END AS BIGINT) AS failures
UNION ALL SELECT 'blank_fields', CAST(sum(
        (trim(recency) = '')::INT + (trim(history_segment) = '')::INT + (trim(history) = '')::INT + (trim(mens) = '')::INT
      + (trim(womens) = '')::INT + (trim(zip_code) = '')::INT + (trim(newbie) = '')::INT + (trim(channel) = '')::INT
      + (trim(segment) = '')::INT + (trim(visit) = '')::INT + (trim(conversion) = '')::INT + (trim(spend) = '')::INT) AS BIGINT)
    FROM raw_text
UNION ALL SELECT 'recency_integer_in_range', count(*) FROM typed_rows
    WHERE NOT recency_format_ok OR recency IS NULL OR recency NOT BETWEEN 1 AND 12
UNION ALL SELECT 'history_decimal_format', count(*) FROM typed_rows WHERE NOT history_format_ok
UNION ALL SELECT 'history_nonnegative_finite', count(*) FROM typed_rows WHERE NOT history_format_ok OR history IS NULL OR history < 0
UNION ALL SELECT 'spend_decimal_format', count(*) FROM typed_rows WHERE NOT spend_format_ok
UNION ALL SELECT 'spend_nonnegative_finite', count(*) FROM typed_rows WHERE NOT spend_format_ok OR spend IS NULL OR spend < 0
UNION ALL SELECT 'binary_mens', count(*) FROM raw_text WHERE mens NOT IN ('0', '1')
UNION ALL SELECT 'binary_womens', count(*) FROM raw_text WHERE womens NOT IN ('0', '1')
UNION ALL SELECT 'binary_newbie', count(*) FROM raw_text WHERE newbie NOT IN ('0', '1')
UNION ALL SELECT 'binary_visit', count(*) FROM raw_text WHERE visit NOT IN ('0', '1')
UNION ALL SELECT 'binary_conversion', count(*) FROM raw_text WHERE conversion NOT IN ('0', '1')
UNION ALL SELECT 'allowed_zip_code', count(*) FROM raw_text WHERE NOT list_contains(getvariable('allowed_zip'), zip_code)
UNION ALL SELECT 'allowed_channel', count(*) FROM raw_text WHERE NOT list_contains(getvariable('allowed_channel'), channel)
UNION ALL SELECT 'allowed_segment', count(*) FROM raw_text WHERE NOT list_contains(getvariable('allowed_segment'), segment)
UNION ALL SELECT 'allowed_history_segment', count(*) FROM raw_text WHERE NOT list_contains(getvariable('allowed_history_segment'), history_segment)
UNION ALL SELECT 'conversion_without_visit', count(*) FROM typed_rows WHERE conversion = 1 AND visit = 0
UNION ALL SELECT 'positive_spend_without_conversion', count(*) FROM typed_rows WHERE spend > 0 AND conversion = 0
UNION ALL SELECT 'conversion_without_positive_spend', count(*) FROM typed_rows WHERE conversion = 1 AND spend <= 0
UNION ALL SELECT 'row_id_unique', count(*) - count(DISTINCT row_id) FROM typed_rows
UNION ALL SELECT 'split_rows_reconcile',
    abs((SELECT count(*) FROM split) - (SELECT count(*) FROM typed_rows))
  + (SELECT count(*) FROM typed_rows t ANTI JOIN split s USING (row_id))
UNION ALL SELECT 'split_partition_labels', count(*) FROM split WHERE partition NOT IN ('TRAIN', 'VALIDATION', 'TEST')
UNION ALL SELECT 'split_arm_matches_assignment', count(*) FROM split s JOIN typed_rows t USING (row_id)
    WHERE s.arm <> CASE t.segment WHEN 'No E-Mail' THEN 0 WHEN 'Mens E-Mail' THEN 1 WHEN 'Womens E-Mail' THEN 2 END;

-- Logical separation: covariates / descriptive / assignment / outcomes, one row per row_id each.
CREATE OR REPLACE TABLE covariates AS
SELECT row_id, source_ordinal, recency, history, mens, womens, newbie, channel, zip_code FROM typed_rows;

CREATE OR REPLACE TABLE descriptive AS
SELECT row_id, history_segment FROM typed_rows;

CREATE OR REPLACE TABLE assignment AS
SELECT row_id, segment,
       CAST(CASE segment WHEN 'No E-Mail' THEN 0 WHEN 'Mens E-Mail' THEN 1 WHEN 'Womens E-Mail' THEN 2 END AS TINYINT) AS arm
FROM typed_rows;

CREATE OR REPLACE TABLE outcomes AS
SELECT row_id, visit, conversion, spend, CAST(spend * 100 AS INTEGER) AS spend_cents FROM typed_rows;

-- Development view: the only outcome view used by development SQL. TEST rows are filtered out here.
CREATE OR REPLACE VIEW dev_outcomes AS
SELECT o.row_id, s.arm, s.partition, o.visit, o.conversion, o.spend, o.spend_cents
FROM outcomes o JOIN split s USING (row_id)
WHERE s.partition IN ('TRAIN', 'VALIDATION');

-- Global quality facts (all previously inspected during planning; none is arm-by-outcome).
CREATE OR REPLACE TABLE quality_summary AS
SELECT 'rows' AS metric, CAST(count(*) AS BIGINT) AS value FROM typed_rows
UNION ALL SELECT 'arm_count_No E-Mail', count(*) FROM typed_rows WHERE segment = 'No E-Mail'
UNION ALL SELECT 'arm_count_Mens E-Mail', count(*) FROM typed_rows WHERE segment = 'Mens E-Mail'
UNION ALL SELECT 'arm_count_Womens E-Mail', count(*) FROM typed_rows WHERE segment = 'Womens E-Mail'
UNION ALL SELECT 'global_visits', CAST(sum(visit) AS BIGINT) FROM typed_rows
UNION ALL SELECT 'global_conversions', CAST(sum(conversion) AS BIGINT) FROM typed_rows
UNION ALL SELECT 'positive_spend_rows', count(*) FILTER (WHERE spend > 0) FROM typed_rows
UNION ALL SELECT 'total_history_cents', CAST(sum(history * 100) AS BIGINT) FROM typed_rows
UNION ALL SELECT 'full_row_match_groups', count(*) FROM (
    SELECT count(*) AS c FROM typed_rows
    GROUP BY recency, history_segment, history, mens, womens, zip_code, newbie, channel, segment, visit, conversion, spend
    HAVING count(*) > 1)
UNION ALL SELECT 'full_row_match_excess', CAST(coalesce(sum(c - 1), 0) AS BIGINT) FROM (
    SELECT count(*) AS c FROM typed_rows
    GROUP BY recency, history_segment, history, mens, womens, zip_code, newbie, channel, segment, visit, conversion, spend)
UNION ALL SELECT 'distinct_pretreatment_profiles', count(*) FROM (
    SELECT 1 FROM typed_rows GROUP BY recency, history, mens, womens, newbie, channel, zip_code)
UNION ALL SELECT 'pretreatment_profile_excess', CAST(sum(c - 1) AS BIGINT) FROM (
    SELECT count(*) AS c FROM typed_rows GROUP BY recency, history, mens, womens, newbie, channel, zip_code)
UNION ALL SELECT 'history_bucket_boundary_disagreements', count(*) FROM typed_rows
    WHERE CAST(substr(history_segment, 1, 1) AS INTEGER) <> CASE
        WHEN history <= 100 THEN 1 WHEN history <= 200 THEN 2 WHEN history <= 350 THEN 3
        WHEN history <= 500 THEN 4 WHEN history <= 750 THEN 5 WHEN history <= 1000 THEN 6 ELSE 7 END
UNION ALL SELECT 'split_TRAIN', count(*) FROM split WHERE partition = 'TRAIN'
UNION ALL SELECT 'split_VALIDATION', count(*) FROM split WHERE partition = 'VALIDATION'
UNION ALL SELECT 'split_TEST', count(*) FROM split WHERE partition = 'TEST';
