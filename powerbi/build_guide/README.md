# Power BI Build Guide

Page-by-page instructions for assembling the executive dashboard in Power BI
Desktop (Windows-only, so this is built by hand following this guide rather
than automated).

## 0. Connect and model

1. Get Data → PostgreSQL database → server `localhost`, database
   `healthcare_claims` (or use the parameterized queries in
   [`../power_query/`](../power_query/)).
2. Import these tables from the `mart` schema: `dim_members`,
   `dim_providers`, `dim_date`, `dim_diagnosis`, `dim_procedure`,
   `fact_claims`, `fact_member_month`, `v_data_quality_summary`. Also import
   `raw.src_chronic_conditions` (rename to `ChronicConditions` in the model).
3. Build relationships as listed at the top of
   [`../dax/measures.md`](../dax/measures.md).
4. Mark `dim_date` as the Date Table (Table tools → Mark as Date Table →
   `date_key`).
5. Paste in the measures from `../dax/measures.md`, organized into a
   `_Measures` display folder (create a measures table via Modeling → New
   Table → `_Measures = {BLANK()}`, then assign each measure's Home Table to
   it — keeps them out of the field list clutter under FactClaims).
6. Add forecast tables from `python/forecasting/output/` once the
   forecasting step is built (see project README status).

## Page 1 — Executive Summary

- KPI cards (top row): `[Total Claims]`, `[Total Allowed Amount]`,
  `[PMPM Allowed]`, `[YoY Cost Change %]`
- Line chart: `[Total Allowed Amount]` by `dim_date[year_month]`, with
  `[MoM Cost Change %]` as a secondary line or tooltip
- Donut/bar: `[Total Allowed Amount]` by `fact_claims[claim_type]`
  (service category cost mix)
- Small multiples or 5 cards: utilization measures
  (`[Inpatient Admits per 1000]`, `[ED Visits per 1000]`,
  `[Outpatient Visits per 1000]`)
- Slicers: `dim_date[year]`, `dim_members[region]`, `dim_members[plan_type]`

## Page 2 — Utilization

- Line chart: admissions/ED/outpatient visits per 1,000, by month (three
  series, or small multiples per claim type)
- Table: `v_repeat_ed_users` member list with claim detail drill-through
- Bar: utilization per 1,000 by `dim_members[region]`
- Card: `[High Utilization Members]`

## Page 3 — Member & Cost Analytics

- Table/matrix: top members by `[Total Allowed Amount]`, with
  `[chronic_condition_count]` and `age_band` as columns — sort descending,
  this is the "high-cost population" view
- Bar: average annual cost by chronic condition (bind to
  `ChronicConditions[condition]` + `[Avg Cost per Member]`) — validate
  against `sql/20_analytical_views.sql`'s `v_chronic_condition_cost`
- Cards: `[High Cost Members]`, `[High Cost Member Share of Total Cost]`
- Scatter: cost vs. claim count per member, colored by chronic condition
  count — visually separates "high cost because chronically ill" from
  "high cost from one expensive event"

## Page 4 — Provider Analytics

- Table: providers with `[Provider Claim Volume]`,
  `[Avg Cost per Claim by Provider]`, `[Is High Cost Provider]` flag,
  filterable/sortable — conditional formatting on the flag column
- Bar: average cost per claim by specialty
- Scatter: claim volume vs. avg cost per claim, one dot per provider,
  colored by specialty — outliers in the top-right are the ones worth a
  second look

## Page 5 — Data Quality Scorecard

- Table straight off `v_data_quality_summary`: check_name, issue_count
- Card: `[Total DQ Issues]`, `[DQ Issue Rate (% of claims)]`
- Bar chart of issue_count by check_name, sorted descending — the
  "where do we lose the most data quality" view at a glance

## Page 6 — Forecast (after the Python forecasting step)

- Line chart: historical + forecasted monthly claim volume and allowed
  cost, with a shaded confidence band and a vertical line marking where
  history ends and forecast begins
- Cards: next-3-months forecasted total allowed cost, forecasted IP/ED
  utilization
- Table: forecast vs. holdout actuals with the validation metrics
  (see `python/forecasting/` once built)

## General formatting notes

- One consistent color per `claim_type` across every page (define once via
  a data-color theme JSON, Format → Themes → Browse for themes)
- Currency format `$#,##0` on all cost measures, no decimals on KPI cards
- Every page: title text box top-left, filter/slicer panel top-right or a
  collapsed filter pane
