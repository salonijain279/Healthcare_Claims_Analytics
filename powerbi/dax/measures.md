# DAX Measure Library

Written against a Power BI model with these tables loaded (via the Postgres
connector, see [`../power_query/`](../power_query/)) and relationships:

- `FactClaims` (from `mart.fact_claims`) `[member_id]` → `DimMembers[member_id]` (many-to-one)
- `FactClaims[provider_id]` → `DimProviders[provider_id]` (many-to-one)
- `FactClaims[service_date]` → `DimDate[date_key]` (many-to-one)
- `FactMemberMonth` (from `mart.fact_member_month`) `[member_id]` → `DimMembers[member_id]`
- `FactMemberMonth[month_start]` → `DimDate[date_key]` (many-to-one — `month_start` is always the 1st of the month, which exists as a row in `DimDate`)
- Mark `DimDate` as the model's official Date table (Table tools → Mark as Date Table)

Not tested against a live model (Power BI Desktop can't run on this machine)
— build in the order below and validate each measure's number against the
matching SQL view in `sql/20_analytical_views.sql` as you go.

## Claims & Cost

```dax
Total Claims = COUNTROWS ( FactClaims )

Total Allowed Amount = SUM ( FactClaims[allowed_amount] )

Total Paid Amount = SUM ( FactClaims[paid_amount] )

Avg Cost per Claim =
DIVIDE ( [Total Allowed Amount], [Total Claims] )

Member Months =
COUNTROWS ( FactMemberMonth )

PMPM Allowed =
DIVIDE ( [Total Allowed Amount], [Member Months] )

PMPM Paid =
DIVIDE ( [Total Paid Amount], [Member Months] )

-- Cost by service category: no DAX needed, just put ClaimType on an axis
-- with [Total Allowed Amount] -- listed here because it's a common ask.

Prior Month Allowed =
CALCULATE (
    [Total Allowed Amount],
    DATEADD ( DimDate[date_key], -1, MONTH )
)

MoM Cost Change % =
DIVIDE (
    [Total Allowed Amount] - [Prior Month Allowed],
    [Prior Month Allowed]
)

Prior Year Allowed =
CALCULATE (
    [Total Allowed Amount],
    SAMEPERIODLASTYEAR ( DimDate[date_key] )
)

YoY Cost Change % =
DIVIDE (
    [Total Allowed Amount] - [Prior Year Allowed],
    [Prior Year Allowed]
)

YTD Allowed Amount =
TOTALYTD ( [Total Allowed Amount], DimDate[date_key] )
```

## Utilization

```dax
Inpatient Admissions =
CALCULATE ( [Total Claims], FactClaims[claim_type] = "Inpatient" )

ED Visits =
CALCULATE ( [Total Claims], FactClaims[claim_type] = "ED" )

Outpatient Visits =
CALCULATE ( [Total Claims], FactClaims[claim_type] = "Outpatient" )

Professional Visits =
CALCULATE ( [Total Claims], FactClaims[claim_type] = "Professional" )

Pharmacy Claims =
CALCULATE ( [Total Claims], FactClaims[claim_type] = "Pharmacy" )

-- Utilization per 1,000 member-months -- the standard payer utilization metric.
Inpatient Admits per 1000 =
DIVIDE ( [Inpatient Admissions], [Member Months] ) * 1000

ED Visits per 1000 =
DIVIDE ( [ED Visits], [Member Months] ) * 1000

Outpatient Visits per 1000 =
DIVIDE ( [Outpatient Visits], [Member Months] ) * 1000

-- High-utilization members: 90th percentile of claim count, computed with a
-- measure so it responds to whatever filter context (region, plan, period)
-- is active rather than a hardcoded threshold.
Member Claim Count P90 =
CALCULATE (
    PERCENTILEX.INC (
        VALUES ( DimMembers[member_id] ),
        CALCULATE ( [Total Claims] )
    ),
    0.90
)

High Utilization Members =
CALCULATE (
    DISTINCTCOUNT ( FactClaims[member_id] ),
    FILTER (
        VALUES ( DimMembers[member_id] ),
        CALCULATE ( [Total Claims] ) >= [Member Claim Count P90]
    )
)

-- Repeat ED users: members with 2+ ED visits within the current filter
-- context (mirrors sql/20_analytical_views.sql's v_repeat_ed_users, which
-- uses a stricter 30-day-gap definition -- use that view directly via
-- DirectQuery/import if you need the exact 30-day version in the model).
Repeat ED Users (2+ visits) =
CALCULATE (
    DISTINCTCOUNT ( FactClaims[member_id] ),
    FILTER (
        VALUES ( DimMembers[member_id] ),
        CALCULATE ( [ED Visits] ) >= 2
    )
)
```

## Member Analytics

```dax
-- High-cost members: top decile by allowed cost, in the current context.
Member Cost P90 =
CALCULATE (
    PERCENTILEX.INC (
        VALUES ( DimMembers[member_id] ),
        CALCULATE ( [Total Allowed Amount] )
    ),
    0.90
)

High Cost Members =
CALCULATE (
    DISTINCTCOUNT ( FactClaims[member_id] ),
    FILTER (
        VALUES ( DimMembers[member_id] ),
        CALCULATE ( [Total Allowed Amount] ) >= [Member Cost P90]
    )
)

High Cost Member Share of Total Cost =
VAR HighCostFilter =
    FILTER (
        VALUES ( DimMembers[member_id] ),
        CALCULATE ( [Total Allowed Amount] ) >= [Member Cost P90]
    )
VAR HighCostAmount = CALCULATE ( [Total Allowed Amount], HighCostFilter )
RETURN
    DIVIDE ( HighCostAmount, [Total Allowed Amount] )

Distinct Members = DISTINCTCOUNT ( FactClaims[member_id] )

Avg Cost per Member =
DIVIDE ( [Total Allowed Amount], [Distinct Members] )
```

Chronic-condition and age/region cohorts don't need DAX beyond putting
`DimMembers[age_band]`, `DimMembers[region]`, or a chronic-condition bridge
table (`ChronicConditions[condition]`, loaded from
`raw.src_chronic_conditions`) on a slicer/axis alongside `[Total Allowed
Amount]` and `[PMPM Allowed]` — see `sql/20_analytical_views.sql`'s
`v_chronic_condition_cost` for the reference numbers to validate against.

## Provider Analytics

```dax
Provider Claim Volume =
CALCULATE ( [Total Claims] )   -- context transform via ProviderID on a table/matrix

Avg Cost per Claim by Provider =
DIVIDE (
    CALCULATE ( [Total Allowed Amount] ),
    CALCULATE ( [Total Claims] )
)

-- High-cost provider flag: >1.5x their specialty's average cost per claim
-- (mirrors sql/20_analytical_views.sql's v_high_cost_providers).
Specialty Avg Cost per Claim =
CALCULATE (
    [Avg Cost per Claim by Provider],
    ALLEXCEPT ( DimProviders, DimProviders[specialty] )
)

Is High Cost Provider =
IF (
    [Avg Cost per Claim by Provider] > 1.5 * [Specialty Avg Cost per Claim],
    "High Cost", "Normal"
)
```

## Data Quality (scorecard tile)

Simplest: import `mart.v_data_quality_summary` directly as a table (already
one row per check) and build a table/card visual straight off it — no DAX
needed. If you want a single "total open issues" KPI card:

```dax
Total DQ Issues =
CALCULATE (
    SUM ( DQSummary[issue_count] )
)

DQ Issue Rate (% of claims) =
DIVIDE ( [Total DQ Issues], [Total Claims] )
```
