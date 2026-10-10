# Data dictionary

Source: Kevin Hillstrom, *MineThatData E-Mail Analytics and Data Mining Challenge* (March 20, 2008). Original CSV: `http://www.minethatdata.com/Kevin_Hillstrom_MineThatData_E-MailAnalytics_DataMiningChallenge_2008.03.20.csv`. Pinned artifact: 3,964,977 bytes, SHA-256 `0e5893329d8b93cefecc571777672028290ab69865718020c78c7284f291aece`, 64,000 data rows, 12 columns, CRLF line endings.

The publisher describes 64,000 customers who purchased within the last twelve months, randomly divided into three nominal one-third groups (men's merchandise email, women's merchandise email, no email) and followed for two weeks.

## Source fields

| Field | Role | SQL type in this project | Allowed values / domain | Used as |
|---|---|---|---|---|
| `recency` | Pre-treatment: months since last purchase | SMALLINT | integers 1–12 | Feature (numeric, standardized on TRAIN) |
| `history_segment` | Publisher's bucket of prior-year spend | VARCHAR | `1) $0 - $100`, `2) $100 - $200`, `3) $200 - $350`, `4) $350 - $500`, `5) $500 - $750`, `6) $750 - $1,000`, `7) $1,000 +` | Descriptive only; excluded from features (redundant; five rounded-boundary disagreements) |
| `history` | Pre-treatment: gross spend in prior year | DECIMAL(10,2) | finite, ≥ 0, ≤ 2 decimals | Feature as log(1 + history) |
| `mens` | Pre-treatment: bought men's merchandise in prior year | TINYINT | 0/1 | Feature; **not gender** |
| `womens` | Pre-treatment: bought women's merchandise in prior year | TINYINT | 0/1 | Feature; **not gender** |
| `zip_code` | Pre-treatment: broad area class | VARCHAR | `Urban`, `Surburban` (source spelling), `Rural` | Feature, one-hot, reference Rural. Not a postal code |
| `newbie` | Pre-treatment: new customer in prior twelve months | TINYINT | 0/1 | Feature |
| `channel` | Pre-treatment: prior-year purchase channel | VARCHAR | `Phone`, `Web`, `Multichannel` | Feature, one-hot, reference Phone |
| `segment` | Assigned campaign arm | VARCHAR | `No E-Mail`, `Mens E-Mail`, `Womens E-Mail` | Treatment (assignment table only) |
| `visit` | Visited website within two weeks | TINYINT | 0/1 | **Primary outcome** |
| `conversion` | Purchased within two weeks | TINYINT | 0/1 | Secondary outcome; never a feature |
| `spend` | Gross spend within two weeks | DECIMAL(10,2) | finite, ≥ 0, ≤ 2 decimals | Secondary outcome (gross, not margin or profit); never a feature |

`Surburban` is preserved in all stored tables. Figures and reports may display "Suburban (source: Surburban)".

## Derived/technical fields

| Field | Definition | Visibility |
|---|---|---|
| `row_id` | `hillstrom-2008-v1:<zero-based source row ordinal>`, assigned before sorting. A technical artifact-local key, **not** a customer identifier | Private |
| `source_ordinal` | Zero-based position of the data row in the original file | Private |
| `arm` | Integer action code: 0 = No E-Mail, 1 = Mens E-Mail, 2 = Womens E-Mail | Private (row level) |
| `partition` | TRAIN / VALIDATION / TEST from the frozen split | Private (row level); aggregate counts public |
| `spend_cents` | Exact integer cents parsed from the decimal string | Private |
| `log_history` | log(1 + history) | Model basis |
| `channel_Web`, `channel_Multichannel`, `zip_Urban`, `zip_Surburban` | One-hot indicators | Model basis |
| `profile_id` | Group code for identical values of the seven raw pre-treatment fields; used only for a hypothetical dependence sensitivity | Private |

## Logical tables (DuckDB, private)

| Table | Grain | Columns |
|---|---|---|
| `raw_text` | one row per source data row | `row_id`, `source_ordinal`, 12 source columns as text |
| `typed_rows` | one row per source row | explicit SQL types for all 12 fields |
| `covariates` | one row per `row_id` | `row_id`, `source_ordinal`, 7 raw features |
| `descriptive` | one row per `row_id` | `row_id`, `history_segment` |
| `assignment` | one row per `row_id` | `row_id`, `segment`, `arm` |
| `outcomes` | one row per `row_id` | `row_id`, `visit`, `conversion`, `spend`, `spend_cents` |
| `split` | one row per `row_id` | `row_id`, `arm`, `partition`, `split_key` |
| view `dev_outcomes` | TRAIN+VALIDATION rows only | outcomes joined to split/assignment |

Joins are on `row_id` and are asserted one-to-one; every table reconciles to 64,000 rows.

## Not available in the source

Customer identifiers, timestamps, pre-period visit outcomes, email delivery/open logs, the randomization seed/strata/quotas, household or network links, margins, costs and long-term outcomes. None are invented.
