# Data Dictionary

Source: `python/generate_synthetic_data.py` → `data/raw/*.csv`
Period: 2023-01-01 to 2024-12-31 (24 months) · 5,000 members · 250 providers

## dim_members

| Column | Type | Notes |
|---|---|---|
| member_id | string (PK) | `M000001`–`M005000` |
| first_name, last_name | string | synthetic |
| date_of_birth | date | |
| gender | string | `F`/`M`; ~1% seeded null |
| state | string | 2-letter; ~0.8% seeded null |
| region | string | Northeast/Midwest/South/West |
| zip3 | string | 3-digit synthetic |
| plan_type | string | HMO/PPO/EPO/HDHP |
| enrollment_start_date | date | |
| enrollment_end_date | date, nullable | null = still enrolled at 2024-12-31 |
| age_as_of_data_end | int | derived |

## dim_member_chronic_conditions

Bridge table, one row per member per condition (member can have 0+ rows).
`member_id`, `condition` (Diabetes, Hypertension, COPD, CHF, CKD, Asthma, Depression).

## dim_providers

| Column | Type | Notes |
|---|---|---|
| provider_id | string (PK) | `P000001`–`P000250` |
| provider_name | string | synthetic |
| provider_type | string | Individual / Facility |
| specialty | string | drives which claim types a provider can bill |
| state, region | string | |
| npi | string | synthetic 10-digit |

## dim_calendar

Standard date dimension, one row per day, 2023-01-01 to 2024-12-31.

## fact_claims

| Column | Type | Notes |
|---|---|---|
| claim_id | string | **not guaranteed unique** — duplicates seeded intentionally, see data_generation_notes.md |
| member_id | string (FK) | ~0.3% seeded orphan (`M999999`, does not exist in dim_members) |
| provider_id | string (FK) | ~0.3% seeded orphan (`P999999`, does not exist in dim_providers) |
| claim_type | string | Inpatient / Outpatient / ED / Professional / Pharmacy |
| service_date | date | |
| admission_date, discharge_date | date, nullable | populated only for Inpatient; ~2% of inpatient claims have them seeded swapped (discharge before admission) |
| place_of_service | string | |
| diagnosis_code | string, nullable | null for all Pharmacy claims (expected/legitimate); ~1% seeded null on medical claims (true DQ issue) |
| diagnosis_desc | string | |
| procedure_or_drug_code | string | CPT-style for medical claims, NDC-style for pharmacy, MS-DRG-style for inpatient |
| procedure_or_drug_desc | string | |
| billed_amount | float | > allowed_amount |
| allowed_amount | float | plan-negotiated allowed amount; ~0.1% seeded 50x outliers |
| paid_amount | float | 0 if claim_status != Paid; ~0.1% seeded negative |
| member_responsibility | float | allowed − paid, when paid |
| claim_status | string | Paid (90%) / Denied (6%) / Pending (4%) |
| submission_date | date | service_date + 1-30 days |

## Known relationships

- `fact_claims.member_id` → `dim_members.member_id` (mostly; see orphans above)
- `fact_claims.provider_id` → `dim_providers.provider_id` (mostly; see orphans above)
- `fact_claims.service_date` should fall within the member's enrollment window — this is true by construction for all real (non-orphaned) claims
