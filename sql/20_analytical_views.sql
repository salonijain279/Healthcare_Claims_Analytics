-- Analytical views on top of the mart star schema.
-- Demonstrates: GROUP BY + HAVING, window functions (RANK/NTILE/LAG/SUM OVER),
-- subqueries, and joins across the fact/dim tables.
-- Run after 10_transform_star_schema.sql.

-- ---------------------------------------------------------------------------
-- v_member_annual_cost: total allowed cost per member, ranked into cost
-- deciles with NTILE -- the "high-cost population" cohort is decile 10.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.v_member_annual_cost AS
SELECT
    m.member_id,
    m.age_band,
    m.plan_type,
    m.region,
    COUNT(f.claim_id)                                   AS claim_count,
    SUM(f.allowed_amount)                                AS total_allowed,
    SUM(f.paid_amount)                                   AS total_paid,
    RANK() OVER (ORDER BY SUM(f.allowed_amount) DESC)    AS cost_rank,
    NTILE(10) OVER (ORDER BY SUM(f.allowed_amount) DESC) AS cost_decile
FROM mart.fact_claims f
JOIN mart.dim_members m ON f.member_id = m.member_id
WHERE m.member_id != 'M999999'
GROUP BY m.member_id, m.age_band, m.plan_type, m.region;

-- ---------------------------------------------------------------------------
-- v_provider_summary: GROUP BY + HAVING to surface providers whose average
-- allowed cost per claim is materially above their specialty's norm.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.v_provider_summary AS
SELECT
    p.provider_id,
    p.provider_name,
    p.specialty,
    COUNT(f.claim_id)          AS claim_count,
    SUM(f.allowed_amount)      AS total_allowed,
    AVG(f.allowed_amount)      AS avg_allowed_per_claim
FROM mart.fact_claims f
JOIN mart.dim_providers p ON f.provider_id = p.provider_id
WHERE p.provider_id != 'P999999'
GROUP BY p.provider_id, p.provider_name, p.specialty
HAVING COUNT(f.claim_id) >= 10;   -- exclude low-volume providers from cost comparisons

-- High-cost providers: average cost per claim more than 1.5x their own
-- specialty's average (subquery + join back to the specialty benchmark).
CREATE OR REPLACE VIEW mart.v_high_cost_providers AS
SELECT
    v.*,
    spec_avg.specialty_avg_cost,
    ROUND((v.avg_allowed_per_claim / spec_avg.specialty_avg_cost)::numeric, 2) AS vs_specialty_ratio
FROM mart.v_provider_summary v
JOIN (
    SELECT specialty, AVG(avg_allowed_per_claim) AS specialty_avg_cost
    FROM mart.v_provider_summary
    GROUP BY specialty
) spec_avg ON v.specialty = spec_avg.specialty
WHERE v.avg_allowed_per_claim > 1.5 * spec_avg.specialty_avg_cost;

-- ---------------------------------------------------------------------------
-- v_repeat_ed_users: window function LAG() to find members with an ED visit
-- within 30 days of a prior ED visit.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.v_ed_visit_gaps AS
SELECT
    member_id,
    service_date,
    LAG(service_date) OVER (PARTITION BY member_id ORDER BY service_date) AS prior_ed_visit,
    service_date - LAG(service_date) OVER (PARTITION BY member_id ORDER BY service_date) AS days_since_prior_ed
FROM mart.fact_claims
WHERE claim_type = 'ED' AND member_id != 'M999999';

CREATE OR REPLACE VIEW mart.v_repeat_ed_users AS
SELECT DISTINCT member_id
FROM mart.v_ed_visit_gaps
WHERE days_since_prior_ed IS NOT NULL AND days_since_prior_ed <= 30;

-- ---------------------------------------------------------------------------
-- v_monthly_trend: GROUP BY month + window functions for MoM % change and
-- running YTD total.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.v_monthly_trend AS
SELECT
    d.year_month,
    d.year,
    COUNT(f.claim_id)     AS claim_count,
    SUM(f.allowed_amount) AS total_allowed,
    LAG(SUM(f.allowed_amount)) OVER (ORDER BY d.year_month) AS prior_month_allowed,
    ROUND(
        100.0 * (SUM(f.allowed_amount) - LAG(SUM(f.allowed_amount)) OVER (ORDER BY d.year_month))
        / NULLIF(LAG(SUM(f.allowed_amount)) OVER (ORDER BY d.year_month), 0)
    , 2) AS mom_pct_change,
    SUM(SUM(f.allowed_amount)) OVER (
        PARTITION BY d.year ORDER BY d.year_month
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS ytd_allowed
FROM mart.fact_claims f
JOIN mart.dim_date d ON f.service_date = d.date_key
GROUP BY d.year_month, d.year
ORDER BY d.year_month;

-- ---------------------------------------------------------------------------
-- v_utilization_per_1000: monthly IP/ED/Outpatient utilization normalized
-- per 1,000 member-months (the standard payer utilization metric).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.v_utilization_per_1000 AS
WITH member_months AS (
    SELECT to_char(month_start, 'YYYY-MM') AS year_month, COUNT(*) AS members
    FROM mart.fact_member_month
    GROUP BY 1
),
events AS (
    SELECT to_char(service_date, 'YYYY-MM') AS year_month, claim_type, COUNT(*) AS events
    FROM mart.fact_claims
    WHERE claim_type IN ('Inpatient', 'ED', 'Outpatient')
    GROUP BY 1, 2
)
SELECT
    e.year_month,
    e.claim_type,
    e.events,
    mm.members,
    ROUND(1000.0 * e.events / mm.members, 2) AS utilization_per_1000
FROM events e
JOIN member_months mm ON e.year_month = mm.year_month
ORDER BY e.year_month, e.claim_type;

-- ---------------------------------------------------------------------------
-- v_chronic_condition_cost: cost comparison for members with vs without each
-- chronic condition (subquery + join).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.v_chronic_condition_cost AS
SELECT
    cc.condition,
    COUNT(DISTINCT cc.member_id)                    AS member_count,
    ROUND(AVG(mac.total_allowed)::numeric, 2)        AS avg_annual_cost_with_condition,
    (SELECT ROUND(AVG(total_allowed)::numeric, 2)
     FROM mart.v_member_annual_cost mac2
     WHERE mac2.member_id NOT IN (
         SELECT member_id FROM raw.src_chronic_conditions
     ))                                              AS avg_annual_cost_no_conditions
FROM raw.src_chronic_conditions cc
JOIN mart.v_member_annual_cost mac ON cc.member_id = mac.member_id
GROUP BY cc.condition
ORDER BY avg_annual_cost_with_condition DESC;
