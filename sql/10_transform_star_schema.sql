-- TRANSFORM stage (SQL path): raw -> mart star schema.
-- Run after python/etl_01_extract.py has populated the `raw` schema.
--
-- Techniques demonstrated: JOINs, normalization (diagnosis/procedure pulled
-- into their own dimensions instead of repeated text), CASE-based derived
-- columns, window functions (ROW_NUMBER for surrogate keys and dedup),
-- explicit handling of broken foreign keys via an UNKNOWN placeholder row
-- instead of silently dropping rows.

DROP SCHEMA IF EXISTS mart CASCADE;
CREATE SCHEMA mart;

-- ---------------------------------------------------------------------------
-- dim_date
-- ---------------------------------------------------------------------------
CREATE TABLE mart.dim_date AS
SELECT
    date::date                       AS date_key,
    year::int                        AS year,
    month::int                       AS month,
    month_name,
    quarter::int                     AS quarter,
    year_month,
    day_of_week,
    (is_weekend = 'True')            AS is_weekend
FROM raw.src_calendar;

ALTER TABLE mart.dim_date ADD PRIMARY KEY (date_key);

-- ---------------------------------------------------------------------------
-- dim_members (+ UNKNOWN placeholder for orphaned FKs in fact_claims)
-- ---------------------------------------------------------------------------
CREATE TABLE mart.dim_members AS
SELECT
    member_id,
    first_name,
    last_name,
    date_of_birth::date              AS date_of_birth,
    gender,                          -- ~1% null: seeded DQ issue, left as-is
    state,                           -- ~0.8% null: seeded DQ issue, left as-is
    region,
    zip3,
    plan_type,
    enrollment_start_date::date      AS enrollment_start_date,
    NULLIF(enrollment_end_date, '')::date AS enrollment_end_date,
    age_as_of_data_end::int          AS age_as_of_data_end,
    CASE
        WHEN age_as_of_data_end::int < 18 THEN 'Under 18'
        WHEN age_as_of_data_end::int BETWEEN 18 AND 34 THEN '18-34'
        WHEN age_as_of_data_end::int BETWEEN 35 AND 49 THEN '35-49'
        WHEN age_as_of_data_end::int BETWEEN 50 AND 64 THEN '50-64'
        ELSE '65+'
    END                               AS age_band
FROM raw.src_members;

INSERT INTO mart.dim_members (member_id, first_name, last_name, gender, age_band)
VALUES ('M999999', 'Unknown', 'Member', 'Unknown', 'Unknown');

ALTER TABLE mart.dim_members ADD PRIMARY KEY (member_id);

-- ---------------------------------------------------------------------------
-- dim_providers (+ UNKNOWN placeholder)
-- ---------------------------------------------------------------------------
CREATE TABLE mart.dim_providers AS
SELECT
    provider_id,
    provider_name,
    provider_type,
    specialty,
    state,
    region,
    npi
FROM raw.src_providers;

INSERT INTO mart.dim_providers (provider_id, provider_name, provider_type, specialty)
VALUES ('P999999', 'Unknown Provider', 'Unknown', 'Unknown');

ALTER TABLE mart.dim_providers ADD PRIMARY KEY (provider_id);

-- ---------------------------------------------------------------------------
-- dim_diagnosis: normalized out of the flat claims extract (same code/desc
-- pair was repeated on every claim row in raw.src_claims -- pulling it into
-- its own table removes that redundancy and gives us one place to enrich
-- diagnoses later, e.g. mapping to chronic-condition categories)
-- ---------------------------------------------------------------------------
-- Some codes carry more than one description in the source extract (e.g.
-- M17.9 shows up both as a standalone outpatient diagnosis and as the
-- admitting diagnosis on an inpatient joint-replacement stay). A dimension
-- needs one row per code, so we standardize on a single canonical
-- description per code (deterministic: alphabetically first) rather than
-- let the conflict fan out downstream joins.
CREATE TABLE mart.dim_diagnosis AS
SELECT
    ROW_NUMBER() OVER (ORDER BY diagnosis_code)::int AS diagnosis_key,
    diagnosis_code,
    diagnosis_desc
FROM (
    SELECT DISTINCT ON (diagnosis_code) diagnosis_code, diagnosis_desc
    FROM raw.src_claims
    WHERE diagnosis_code IS NOT NULL
    ORDER BY diagnosis_code, diagnosis_desc
) d;

INSERT INTO mart.dim_diagnosis (diagnosis_key, diagnosis_code, diagnosis_desc)
VALUES (0, NULL, 'Not applicable / missing');

ALTER TABLE mart.dim_diagnosis ADD PRIMARY KEY (diagnosis_key);
CREATE UNIQUE INDEX ON mart.dim_diagnosis (diagnosis_code);

-- ---------------------------------------------------------------------------
-- dim_procedure: same normalization for procedure/drug codes
-- ---------------------------------------------------------------------------
CREATE TABLE mart.dim_procedure AS
SELECT
    ROW_NUMBER() OVER (ORDER BY procedure_or_drug_code)::int AS procedure_key,
    procedure_or_drug_code  AS procedure_code,
    procedure_or_drug_desc  AS procedure_desc
FROM (
    SELECT DISTINCT ON (procedure_or_drug_code) procedure_or_drug_code, procedure_or_drug_desc
    FROM raw.src_claims
    WHERE procedure_or_drug_code IS NOT NULL
    ORDER BY procedure_or_drug_code, procedure_or_drug_desc
) p;

ALTER TABLE mart.dim_procedure ADD PRIMARY KEY (procedure_key);
CREATE UNIQUE INDEX ON mart.dim_procedure (procedure_code);

-- ---------------------------------------------------------------------------
-- fact_claims
--   - dedup exact-duplicate claim_id rows (DISTINCT ON, a window-function-
--     adjacent technique) -- these are the same ETL-duplication issue the
--     JSON extract had to upsert around
--   - remap orphaned member_id/provider_id to the UNKNOWN placeholder rows
--     instead of dropping the claim (dollars still reconcile to source)
--   - join out to the normalized diagnosis/procedure dimensions
-- ---------------------------------------------------------------------------
CREATE TABLE mart.fact_claims AS
WITH deduped AS (
    SELECT DISTINCT ON (claim_id) *
    FROM raw.src_claims
    ORDER BY claim_id, service_date
),
typed AS (
    SELECT
        claim_id,
        CASE WHEN member_id = 'M999999' THEN 'M999999' ELSE member_id END AS member_id,
        CASE WHEN provider_id = 'P999999' THEN 'P999999' ELSE provider_id END AS provider_id,
        claim_type,
        service_date::date AS service_date,
        NULLIF(admission_date, '')::date AS admission_date,
        NULLIF(discharge_date, '')::date AS discharge_date,
        place_of_service,
        diagnosis_code,
        procedure_or_drug_code,
        billed_amount::numeric(12,2)     AS billed_amount,
        allowed_amount::numeric(12,2)    AS allowed_amount,
        paid_amount::numeric(12,2)       AS paid_amount,
        member_responsibility::numeric(12,2) AS member_responsibility,
        claim_status,
        submission_date::date AS submission_date
    FROM deduped
)
SELECT
    t.claim_id,
    m.member_id,
    pr.provider_id,
    t.claim_type,
    t.service_date,
    t.admission_date,
    t.discharge_date,
    CASE
        WHEN t.discharge_date IS NOT NULL AND t.admission_date IS NOT NULL
             AND t.discharge_date < t.admission_date
        THEN TRUE ELSE FALSE
    END AS has_invalid_stay_dates,       -- surfaced, not silently fixed
    t.place_of_service,
    COALESCE(dx.diagnosis_key, 0)        AS diagnosis_key,
    COALESCE(pc.procedure_key, -1)       AS procedure_key,
    t.billed_amount,
    t.allowed_amount,
    t.paid_amount,
    t.member_responsibility,
    t.claim_status,
    t.submission_date,
    (t.member_id NOT IN (SELECT member_id FROM raw.src_members))   AS is_orphan_member,
    (t.provider_id NOT IN (SELECT provider_id FROM raw.src_providers)) AS is_orphan_provider
FROM typed t
LEFT JOIN mart.dim_members m   ON t.member_id = m.member_id
LEFT JOIN mart.dim_providers pr ON t.provider_id = pr.provider_id
LEFT JOIN mart.dim_diagnosis dx ON t.diagnosis_code = dx.diagnosis_code
LEFT JOIN mart.dim_procedure pc ON t.procedure_or_drug_code = pc.procedure_code;

ALTER TABLE mart.fact_claims ADD PRIMARY KEY (claim_id);
CREATE INDEX ON mart.fact_claims (member_id);
CREATE INDEX ON mart.fact_claims (provider_id);
CREATE INDEX ON mart.fact_claims (service_date);
CREATE INDEX ON mart.fact_claims (claim_type);

-- ---------------------------------------------------------------------------
-- fact_member_month: one row per enrolled member per month -- the
-- denominator every PMPM / utilization-per-1,000 measure needs. Built with
-- generate_series rather than in DAX, per the "transform at the pipeline
-- level, not the destination tool" principle.
-- ---------------------------------------------------------------------------
CREATE TABLE mart.fact_member_month AS
SELECT
    m.member_id,
    gs.month_start::date AS month_start
FROM raw.src_members m
CROSS JOIN LATERAL generate_series(
    date_trunc('month', m.enrollment_start_date::date),
    date_trunc('month', COALESCE(NULLIF(m.enrollment_end_date, '')::date, DATE '2024-12-31')),
    interval '1 month'
) AS gs(month_start)
WHERE m.enrollment_start_date::date <= DATE '2024-12-31';

CREATE INDEX ON mart.fact_member_month (member_id);
CREATE INDEX ON mart.fact_member_month (month_start);

-- ---------------------------------------------------------------------------
-- Sanity totals (compare to data_generation_notes.md / DQ notes)
-- ---------------------------------------------------------------------------
SELECT 'dim_members' AS table_name, count(*) FROM mart.dim_members
UNION ALL SELECT 'dim_providers', count(*) FROM mart.dim_providers
UNION ALL SELECT 'dim_diagnosis', count(*) FROM mart.dim_diagnosis
UNION ALL SELECT 'dim_procedure', count(*) FROM mart.dim_procedure
UNION ALL SELECT 'fact_claims', count(*) FROM mart.fact_claims
UNION ALL SELECT 'fact_member_month', count(*) FROM mart.fact_member_month;
