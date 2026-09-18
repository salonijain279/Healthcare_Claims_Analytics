-- Data-quality checks against mart.fact_claims / mart.dim_members.
-- Expected findings are documented in docs/data_generation_notes.md --
-- these queries should surface numbers close to those seeded rates.
-- Run after 10_transform_star_schema.sql.

-- 1. Exact duplicate claims in the RAW extract (caught before dedup)
SELECT 'raw_exact_duplicate_claim_ids' AS check_name, COUNT(*) - COUNT(DISTINCT claim_id) AS issue_count
FROM raw.src_claims;

-- 2. Near-duplicate claims in the CLEAN fact table: same member, provider,
-- service date and allowed amount but a different claim_id -- a likely
-- duplicate billing submission. Window function (COUNT OVER) flags the group.
WITH signatures AS (
    SELECT
        claim_id,
        member_id,
        COUNT(*) OVER (
            PARTITION BY member_id, provider_id, service_date, allowed_amount
        ) AS signature_count
    FROM mart.fact_claims
    WHERE member_id != 'M999999'
)
SELECT 'near_duplicate_claim_candidates' AS check_name, COUNT(*) AS issue_count
FROM signatures WHERE signature_count > 1;

-- 3. Missing diagnosis on MEDICAL claims (Pharmacy is expected to have none)
SELECT 'missing_diagnosis_on_medical_claims' AS check_name, COUNT(*) AS issue_count
FROM mart.fact_claims
WHERE diagnosis_key = 0 AND claim_type != 'Pharmacy';

-- 4. Orphaned member_id / provider_id (referential integrity)
SELECT 'orphan_member_id' AS check_name, COUNT(*) AS issue_count
FROM mart.fact_claims WHERE is_orphan_member;

SELECT 'orphan_provider_id' AS check_name, COUNT(*) AS issue_count
FROM mart.fact_claims WHERE is_orphan_provider;

-- 5. Invalid inpatient stay dates (discharge before admission)
SELECT 'invalid_inpatient_stay_dates' AS check_name, COUNT(*) AS issue_count
FROM mart.fact_claims WHERE has_invalid_stay_dates;

-- 6. Claim amount outliers: >3 standard deviations above the mean for that
-- claim type (subquery for the per-type mean/stddev, applied per row)
WITH stats AS (
    SELECT claim_type, AVG(allowed_amount) AS mean_amt, STDDEV(allowed_amount) AS sd_amt
    FROM mart.fact_claims
    GROUP BY claim_type
)
SELECT 'extreme_cost_outliers' AS check_name, COUNT(*) AS issue_count
FROM mart.fact_claims f
JOIN stats s ON f.claim_type = s.claim_type
WHERE f.allowed_amount > s.mean_amt + 3 * s.sd_amt;

-- 7. Negative paid amounts (should never happen)
SELECT 'negative_paid_amount' AS check_name, COUNT(*) AS issue_count
FROM mart.fact_claims WHERE paid_amount < 0;

-- 8. Missing member demographic fields
SELECT 'missing_member_gender' AS check_name, COUNT(*) AS issue_count
FROM mart.dim_members WHERE gender IS NULL AND member_id != 'M999999';

SELECT 'missing_member_state' AS check_name, COUNT(*) AS issue_count
FROM mart.dim_members WHERE state IS NULL AND member_id != 'M999999';

-- 9. Claims outside the member's enrollment window (would indicate a
-- billing/eligibility mismatch; expect zero here since synthetic data
-- was constructed to respect enrollment windows)
SELECT 'claims_outside_enrollment_window' AS check_name, COUNT(*) AS issue_count
FROM mart.fact_claims f
JOIN mart.dim_members m ON f.member_id = m.member_id
WHERE m.member_id != 'M999999'
  AND (f.service_date < m.enrollment_start_date
       OR f.service_date > COALESCE(m.enrollment_end_date, DATE '2024-12-31'));

-- ---------------------------------------------------------------------------
-- Consolidated summary, one row per check (handy for a Power BI DQ scorecard)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.v_data_quality_summary AS
SELECT 'raw_exact_duplicate_claim_ids' AS check_name,
       (SELECT COUNT(*) - COUNT(DISTINCT claim_id) FROM raw.src_claims) AS issue_count
UNION ALL
SELECT 'near_duplicate_claim_candidates',
       (SELECT COUNT(*) FROM (
            SELECT claim_id, COUNT(*) OVER (
                PARTITION BY member_id, provider_id, service_date, allowed_amount
            ) AS c
            FROM mart.fact_claims WHERE member_id != 'M999999'
        ) s WHERE c > 1)
UNION ALL
SELECT 'missing_diagnosis_on_medical_claims',
       (SELECT COUNT(*) FROM mart.fact_claims WHERE diagnosis_key = 0 AND claim_type != 'Pharmacy')
UNION ALL
SELECT 'orphan_member_id', (SELECT COUNT(*) FROM mart.fact_claims WHERE is_orphan_member)
UNION ALL
SELECT 'orphan_provider_id', (SELECT COUNT(*) FROM mart.fact_claims WHERE is_orphan_provider)
UNION ALL
SELECT 'invalid_inpatient_stay_dates', (SELECT COUNT(*) FROM mart.fact_claims WHERE has_invalid_stay_dates)
UNION ALL
SELECT 'negative_paid_amount', (SELECT COUNT(*) FROM mart.fact_claims WHERE paid_amount < 0)
UNION ALL
SELECT 'missing_member_gender', (SELECT COUNT(*) FROM mart.dim_members WHERE gender IS NULL AND member_id != 'M999999')
UNION ALL
SELECT 'missing_member_state', (SELECT COUNT(*) FROM mart.dim_members WHERE state IS NULL AND member_id != 'M999999');
