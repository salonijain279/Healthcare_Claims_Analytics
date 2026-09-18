"""
TRANSFORM stage (Python/pandas path).

Deliberately NOT a re-implementation of sql/10_transform_star_schema.sql --
that would just be the same work twice. Instead this covers what pandas is
actually good for in a real pipeline:

  1. An independent data-quality PROFILE, built with generic pandas
     functions (isnull/dtype checks) rather than the hand-written checks in
     sql/30_data_quality_checks.sql. Two different techniques finding the
     same problems is a real cross-validation of both.
  2. Reusable aggregation FUNCTIONS (not one-off scripts) that get imported
     directly by the forecasting notebook later -- the same monthly rollup
     shouldn't be written twice.
  3. An Excel export for stakeholders who live in spreadsheets, not SQL
     clients or Power BI.

Demonstrates: merge, groupby, null/dtype handling, reusable functions.
"""
import pandas as pd
from sqlalchemy import create_engine

ENGINE = create_engine("postgresql+psycopg2:///healthcare_claims")
PROCESSED_DIR = "data/processed"


def load_raw_tables():
    """Pull the same raw tables the SQL path reads from -- one source of
    truth, two transform techniques."""
    members = pd.read_sql("SELECT * FROM raw.src_members", ENGINE)
    providers = pd.read_sql("SELECT * FROM raw.src_providers", ENGINE)
    claims = pd.read_sql("SELECT * FROM raw.src_claims", ENGINE)
    chronic = pd.read_sql("SELECT * FROM raw.src_chronic_conditions", ENGINE)
    return members, providers, claims, chronic


def fix_dtypes(claims: pd.DataFrame) -> pd.DataFrame:
    """raw.src_claims lands everything as TEXT (see etl_01_extract.py) --
    this is the dtype-mismatch cleanup step every pandas pipeline needs
    before any numeric/date operation will work correctly."""
    df = claims.copy()
    numeric_cols = ["billed_amount", "allowed_amount", "paid_amount", "member_responsibility"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    date_cols = ["service_date", "admission_date", "discharge_date", "submission_date"]
    for col in date_cols:
        df[col] = pd.to_datetime(df[col], errors="coerce")

    return df


def profile_data_quality(claims: pd.DataFrame, members: pd.DataFrame) -> pd.DataFrame:
    """Generic pandas-native DQ profile -- independent of the hand-written
    SQL checks, as a sanity cross-check on the same underlying data."""
    checks = []

    dupe_claim_ids = claims["claim_id"].duplicated().sum()
    checks.append(("duplicate_claim_ids", int(dupe_claim_ids)))

    non_pharmacy = claims[claims["claim_type"] != "Pharmacy"]
    checks.append(("missing_diagnosis_non_pharmacy", int(non_pharmacy["diagnosis_code"].isna().sum())))

    known_members = set(members["member_id"])
    checks.append(("orphan_member_id", int((~claims["member_id"].isin(known_members)).sum())))

    numeric_claims = fix_dtypes(claims)
    checks.append(("negative_paid_amount", int((numeric_claims["paid_amount"] < 0).sum())))
    checks.append(("null_allowed_amount_after_cast", int(numeric_claims["allowed_amount"].isna().sum())))

    checks.append(("missing_gender", int(members["gender"].isna().sum())))
    checks.append(("missing_state", int(members["state"].isna().sum())))

    return pd.DataFrame(checks, columns=["check_name", "issue_count"])


def build_monthly_summary(claims: pd.DataFrame) -> pd.DataFrame:
    """Reusable: also imported by the forecasting script. groupby + merge
    of claim-count and cost aggregates, one row per (month, claim_type)."""
    df = fix_dtypes(claims)
    df["year_month"] = df["service_date"].dt.to_period("M").astype(str)

    counts = df.groupby(["year_month", "claim_type"]).size().rename("claim_count")
    costs = df.groupby(["year_month", "claim_type"])[["allowed_amount", "paid_amount"]].sum()

    summary = counts.to_frame().merge(costs, left_index=True, right_index=True).reset_index()
    return summary.sort_values(["year_month", "claim_type"])


def build_member_cost_summary(claims: pd.DataFrame, members: pd.DataFrame, chronic: pd.DataFrame) -> pd.DataFrame:
    """merge (claims -> members -> chronic-condition count) + groupby."""
    df = fix_dtypes(claims)
    df = df[df["member_id"] != "M999999"]

    member_totals = (
        df.groupby("member_id")
        .agg(claim_count=("claim_id", "count"), total_allowed=("allowed_amount", "sum"))
        .reset_index()
    )

    condition_counts = chronic.groupby("member_id").size().rename("chronic_condition_count")

    merged = member_totals.merge(members[["member_id", "age_band" if "age_band" in members.columns else "age_as_of_data_end", "plan_type", "region"]],
                                  on="member_id", how="left")
    merged = merged.merge(condition_counts, on="member_id", how="left")
    merged["chronic_condition_count"] = merged["chronic_condition_count"].fillna(0).astype(int)

    return merged.sort_values("total_allowed", ascending=False)


def build_high_cost_provider_summary(claims: pd.DataFrame, providers: pd.DataFrame) -> pd.DataFrame:
    df = fix_dtypes(claims)
    df = df[df["provider_id"] != "P999999"]

    prov_summary = (
        df.groupby("provider_id")
        .agg(claim_count=("claim_id", "count"), avg_allowed=("allowed_amount", "mean"))
        .reset_index()
    )
    prov_summary = prov_summary.merge(providers[["provider_id", "provider_name", "specialty"]], on="provider_id", how="left")
    prov_summary = prov_summary[prov_summary["claim_count"] >= 10]

    specialty_avg = prov_summary.groupby("specialty")["avg_allowed"].transform("mean")
    prov_summary["vs_specialty_ratio"] = (prov_summary["avg_allowed"] / specialty_avg).round(2)

    return prov_summary.sort_values("vs_specialty_ratio", ascending=False)


def main():
    import os
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    print("Loading raw tables from Postgres...")
    members, providers, claims, chronic = load_raw_tables()

    print("Profiling data quality (pandas-native checks)...")
    dq = profile_data_quality(claims, members)
    print(dq.to_string(index=False))
    dq.to_csv(f"{PROCESSED_DIR}/dq_profile_pandas.csv", index=False)

    print("\nBuilding monthly summary...")
    monthly = build_monthly_summary(claims)
    monthly.to_csv(f"{PROCESSED_DIR}/monthly_summary.csv", index=False)
    print(f"  {len(monthly)} (month, claim_type) rows -> data/processed/monthly_summary.csv")

    print("Building member cost summary...")
    member_cost = build_member_cost_summary(claims, members, chronic)
    member_cost.to_csv(f"{PROCESSED_DIR}/member_cost_summary.csv", index=False)
    print(f"  {len(member_cost)} members -> data/processed/member_cost_summary.csv")

    print("Building high-cost provider summary...")
    provider_summary = build_high_cost_provider_summary(claims, providers)
    provider_summary.to_csv(f"{PROCESSED_DIR}/high_cost_provider_summary.csv", index=False)
    print(f"  {len(provider_summary)} providers -> data/processed/high_cost_provider_summary.csv")

    print("\nWriting Excel workbook for spreadsheet-native stakeholders...")
    with pd.ExcelWriter(f"{PROCESSED_DIR}/healthcare_claims_summary.xlsx", engine="openpyxl") as writer:
        monthly.to_excel(writer, sheet_name="Monthly Summary", index=False)
        member_cost.head(500).to_excel(writer, sheet_name="Top 500 Members by Cost", index=False)
        provider_summary.to_excel(writer, sheet_name="Provider Cost Ratios", index=False)
        dq.to_excel(writer, sheet_name="Data Quality Profile", index=False)
    print(f"  data/processed/healthcare_claims_summary.xlsx")


if __name__ == "__main__":
    main()
