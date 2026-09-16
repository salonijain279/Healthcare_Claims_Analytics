# Data Generation Notes

Ground truth for what `python/generate_synthetic_data.py` seeds into the data,
kept separate from the polished data dictionary so it can be used to verify
the SQL/Python data-quality checks actually find what's really there.

## Design parameters

- Seed: 42 (fully reproducible — rerunning the script regenerates identical data)
- 5,000 members, 250 providers, 24 months (2023-01 to 2024-12)
- Annual utilization (pre-multiplier): Professional 5.5, Outpatient 1.8, ED 0.18,
  Inpatient 0.07, Pharmacy 6.0 events/member/year
- Cost trend: ~5%/year medical inflation, compounded monthly
- Seasonality: +15% Dec/Jan/Feb (respiratory season), −5% Jun/Jul/Aug
- Chronic-condition members cost 1.6x+ (utilization) and 1.15x+ per-condition
  (cost) more than members without conditions
- Result: ~$720 PMPM allowed / ~$8,640 allowed per member per year — in line
  with commercial-payer benchmarks for a population skewed toward chronic
  disease (62.7% of members have ≥1 of 7 modeled chronic conditions)

## Seeded data-quality issues (the "answer key")

| Issue | Where | Target rate | How it was introduced |
|---|---|---|---|
| Exact duplicate claims | fact_claims | 0.3% of pre-injection claims | Full row copied with same claim_id |
| Near-duplicate claims | fact_claims | 0.4% of pre-injection claims | Same member/provider/date/amount, new claim_id (simulates duplicate billing submission) |
| Missing diagnosis code | fact_claims, non-pharmacy | 1% | Set to null |
| Orphaned member_id | fact_claims | 0.3% | Set to `M999999`, which does not exist in dim_members |
| Orphaned provider_id | fact_claims | 0.3% | Set to `P999999`, which does not exist in dim_providers |
| Invalid inpatient dates | fact_claims, Inpatient only | 2% of inpatient claims | admission_date and discharge_date swapped (discharge before admission) |
| Extreme cost outlier | fact_claims | 0.1% | allowed_amount multiplied by 50x |
| Negative paid amount | fact_claims | 0.1% | paid_amount set negative |
| Missing gender | dim_members | 1% | Set to null |
| Missing state | dim_members | 0.8% | Set to null |

Not a data-quality issue (by design, not a bug):
- `diagnosis_code` is null for **all** Pharmacy claims — pharmacy claims in
  real claims data typically don't carry a diagnosis. A correct DQ check
  should exclude `claim_type = 'Pharmacy'` when flagging missing diagnoses.

## Regenerating the data

```bash
python3 python/generate_synthetic_data.py
```

Deterministic given the seed — safe to rerun after editing the script.
