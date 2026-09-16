"""
Generates a synthetic healthcare claims dataset (members, providers, calendar,
claims) for the Healthcare Claims, Utilization & Cost Analytics project.

Output: data/raw/*.csv

Design notes live in docs/data_generation_notes.md.
"""
import random
from datetime import date, timedelta

import numpy as np
import pandas as pd
from faker import Faker

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
fake = Faker()
Faker.seed(SEED)

N_MEMBERS = 5000
N_PROVIDERS = 250
DATA_START = date(2023, 1, 1)
DATA_END = date(2024, 12, 31)
OUT_DIR = "data/raw"

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

STATE_WEIGHTS = {
    "CA": 0.12, "TX": 0.09, "FL": 0.07, "NY": 0.06, "PA": 0.04, "IL": 0.04,
    "OH": 0.035, "GA": 0.035, "NC": 0.03, "MI": 0.03, "NJ": 0.028, "VA": 0.026,
    "WA": 0.024, "AZ": 0.023, "MA": 0.021, "TN": 0.021, "IN": 0.02, "MO": 0.019,
    "MD": 0.019, "WI": 0.018, "CO": 0.018, "MN": 0.017, "SC": 0.016, "AL": 0.015,
    "LA": 0.014, "KY": 0.014, "OR": 0.013, "OK": 0.012, "CT": 0.011, "UT": 0.01,
    "IA": 0.01, "NV": 0.009, "AR": 0.009, "MS": 0.009, "KS": 0.009, "NM": 0.006,
    "NE": 0.006, "WV": 0.005, "ID": 0.005, "HI": 0.004, "NH": 0.004, "ME": 0.004,
    "MT": 0.003, "RI": 0.003, "DE": 0.003, "SD": 0.003, "ND": 0.002, "AK": 0.002,
    "VT": 0.002, "WY": 0.002,
}
_states = list(STATE_WEIGHTS.keys())
_weights = np.array(list(STATE_WEIGHTS.values()))
_weights = _weights / _weights.sum()

REGION_MAP = {
    "CT": "Northeast", "ME": "Northeast", "MA": "Northeast", "NH": "Northeast",
    "RI": "Northeast", "VT": "Northeast", "NJ": "Northeast", "NY": "Northeast",
    "PA": "Northeast",
    "IL": "Midwest", "IN": "Midwest", "MI": "Midwest", "OH": "Midwest",
    "WI": "Midwest", "IA": "Midwest", "KS": "Midwest", "MN": "Midwest",
    "MO": "Midwest", "NE": "Midwest", "ND": "Midwest", "SD": "Midwest",
    "DE": "South", "FL": "South", "GA": "South", "MD": "South", "NC": "South",
    "SC": "South", "VA": "South", "WV": "South", "AL": "South", "KY": "South",
    "MS": "South", "TN": "South", "AR": "South", "LA": "South", "OK": "South",
    "TX": "South",
    "AZ": "West", "CO": "West", "ID": "West", "MT": "West", "NV": "West",
    "NM": "West", "UT": "West", "WY": "West", "AK": "West", "CA": "West",
    "HI": "West", "OR": "West", "WA": "West",
}

PLAN_TYPES = ["HMO", "PPO", "EPO", "HDHP"]
PLAN_WEIGHTS = [0.35, 0.4, 0.15, 0.1]

CHRONIC_CONDITIONS = {
    "Diabetes": ("E11.9", "Type 2 diabetes mellitus without complications"),
    "Hypertension": ("I10", "Essential (primary) hypertension"),
    "COPD": ("J44.9", "Chronic obstructive pulmonary disease, unspecified"),
    "CHF": ("I50.9", "Heart failure, unspecified"),
    "CKD": ("N18.3", "Chronic kidney disease, stage 3"),
    "Asthma": ("J45.909", "Unspecified asthma, uncomplicated"),
    "Depression": ("F32.9", "Major depressive disorder, single episode, unspecified"),
}
# Rough US adult prevalence, applied independently per member
CHRONIC_PREVALENCE = {
    "Diabetes": 0.11, "Hypertension": 0.30, "COPD": 0.06, "CHF": 0.03,
    "CKD": 0.05, "Asthma": 0.08, "Depression": 0.09,
}

SPECIALTY_CLAIM_MAP = {
    "Primary Care": ["Professional"],
    "Cardiology": ["Professional", "Outpatient"],
    "Endocrinology": ["Professional"],
    "Orthopedics": ["Professional", "Outpatient"],
    "General Surgery": ["Outpatient", "Inpatient"],
    "OB/GYN": ["Professional", "Outpatient", "Inpatient"],
    "Psychiatry": ["Professional"],
    "Pulmonology": ["Professional", "Outpatient"],
    "Nephrology": ["Professional", "Outpatient"],
    "Dermatology": ["Professional"],
    "Neurology": ["Professional", "Outpatient"],
    "Physical Therapy": ["Outpatient"],
    "Radiology": ["Outpatient"],
    "Emergency Medicine": ["ED"],
    "General Acute Care Hospital": ["Inpatient"],
    "Retail Pharmacy": ["Pharmacy"],
}
SPECIALTY_WEIGHTS = {
    "Primary Care": 0.22, "Cardiology": 0.06, "Endocrinology": 0.03,
    "Orthopedics": 0.06, "General Surgery": 0.04, "OB/GYN": 0.05,
    "Psychiatry": 0.05, "Pulmonology": 0.03, "Nephrology": 0.02,
    "Dermatology": 0.04, "Neurology": 0.03, "Physical Therapy": 0.06,
    "Radiology": 0.05, "Emergency Medicine": 0.05,
    "General Acute Care Hospital": 0.06, "Retail Pharmacy": 0.15,
}
FACILITY_SPECIALTIES = {
    "General Surgery", "OB/GYN", "Physical Therapy", "Radiology",
    "Emergency Medicine", "General Acute Care Hospital", "Retail Pharmacy",
}

ACUTE_DIAGNOSES = [
    ("Acute upper respiratory infection", "J06.9"),
    ("Urinary tract infection", "N39.0"),
    ("Low back pain", "M54.5"),
    ("Chest pain, unspecified", "R07.9"),
    ("Abdominal pain, unspecified", "R10.9"),
    ("Encounter for general adult medical examination", "Z00.00"),
    ("Acute bronchitis", "J20.9"),
    ("Sprain of ankle", "S93.409A"),
    ("Gastroenteritis, unspecified", "K52.9"),
    ("Migraine, unspecified", "G43.909"),
    ("Anxiety disorder, unspecified", "F41.9"),
    ("Osteoarthritis of knee", "M17.9"),
]
ED_DIAGNOSES = [
    ("Chest pain, unspecified", "R07.9"),
    ("Abdominal pain, unspecified", "R10.9"),
    ("Fracture of forearm", "S52.90XA"),
    ("Asthma exacerbation", "J45.901"),
    ("Laceration, unspecified", "T14.8"),
    ("Syncope and collapse", "R55"),
    ("Acute appendicitis", "K35.80"),
    ("Migraine, unspecified", "G43.909"),
]
IP_DIAGNOSES = [
    ("Pneumonia, unspecified organism", "J18.9", "193"),
    ("Heart failure, unspecified", "I50.9", "291"),
    ("Sepsis, unspecified organism", "A41.9", "871"),
    ("Acute myocardial infarction", "I21.9", "280"),
    ("Major joint replacement (hip/knee)", "M17.9", "470"),
    ("Chronic obstructive pulmonary disease with exacerbation", "J44.1", "190"),
    ("Acute appendicitis with peritonitis", "K35.32", "343"),
    ("Childbirth, single spontaneous delivery", "O80", "775"),
]
PROCEDURES_PROFESSIONAL = [
    ("Office visit, established patient, level 3", "99213"),
    ("Office visit, established patient, level 4", "99214"),
    ("Office visit, new patient, level 4", "99204"),
    ("Preventive visit, adult", "99396"),
]
PROCEDURES_OUTPATIENT = [
    ("Comprehensive metabolic panel", "80053"),
    ("X-ray, chest", "71046"),
    ("MRI, brain", "70551"),
    ("Physical therapy, therapeutic exercise", "97110"),
    ("Colonoscopy, diagnostic", "45378"),
    ("Echocardiogram", "93306"),
]
PROCEDURES_ED = [
    ("Emergency dept visit, level 3", "99283"),
    ("Emergency dept visit, level 4", "99284"),
    ("Emergency dept visit, level 5", "99285"),
]
DRUGS = [
    ("Metformin 500mg", "00093-1074-01", 12),
    ("Lisinopril 10mg", "00378-0210-01", 10),
    ("Atorvastatin 20mg", "00071-0155-23", 15),
    ("Albuterol HFA Inhaler", "00173-0682-20", 45),
    ("Sertraline 50mg", "00049-4960-66", 18),
    ("Insulin Glargine", "00088-2220-33", 320),
    ("Amoxicillin 500mg", "00093-3155-01", 14),
    ("Levothyroxine 50mcg", "00074-6624-13", 11),
    ("Omeprazole 20mg", "00186-5020-31", 13),
    ("Hydrochlorothiazide 25mg", "00185-0287-01", 9),
]

PLACE_OF_SERVICE = {
    "Professional": "Office",
    "Outpatient": "Outpatient Hospital",
    "ED": "Emergency Room",
    "Inpatient": "Inpatient Hospital",
    "Pharmacy": "Pharmacy",
}


def months_between(start: date, end: date):
    months = []
    cur = date(start.year, start.month, 1)
    while cur <= end:
        months.append(cur)
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return months


ALL_MONTHS = months_between(DATA_START, DATA_END)


def trend_and_seasonality(d: date) -> float:
    """Medical cost/utilization multiplier: ~5%/yr trend + winter respiratory bump."""
    months_elapsed = (d.year - DATA_START.year) * 12 + (d.month - DATA_START.month)
    trend = 1 + (0.05 / 12) * months_elapsed
    seasonal = 1.15 if d.month in (1, 2, 12) else (0.95 if d.month in (6, 7, 8) else 1.0)
    return trend * seasonal


def random_date_in_month(month_start: date) -> date:
    if month_start.month == 12:
        next_month = date(month_start.year + 1, 1, 1)
    else:
        next_month = date(month_start.year, month_start.month + 1, 1)
    days = (next_month - month_start).days
    return month_start + timedelta(days=random.randint(0, days - 1))


# ---------------------------------------------------------------------------
# Dimension builders
# ---------------------------------------------------------------------------

def build_calendar():
    days = pd.date_range(DATA_START, DATA_END, freq="D")
    df = pd.DataFrame({"date": days})
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["month_name"] = df["date"].dt.strftime("%B")
    df["quarter"] = df["date"].dt.quarter
    df["year_month"] = df["date"].dt.strftime("%Y-%m")
    df["day_of_week"] = df["date"].dt.day_name()
    df["is_weekend"] = df["date"].dt.dayofweek >= 5
    return df


def build_providers(n):
    specs = list(SPECIALTY_WEIGHTS.keys())
    spec_p = np.array(list(SPECIALTY_WEIGHTS.values()))
    spec_p = spec_p / spec_p.sum()
    rows = []
    for i in range(1, n + 1):
        specialty = np.random.choice(specs, p=spec_p)
        provider_type = "Facility" if specialty in FACILITY_SPECIALTIES else "Individual"
        state = np.random.choice(_states, p=_weights)
        name = (
            f"{fake.company()} {specialty}" if provider_type == "Facility"
            else f"Dr. {fake.last_name()}"
        )
        rows.append({
            "provider_id": f"P{i:06d}",
            "provider_name": name,
            "provider_type": provider_type,
            "specialty": specialty,
            "state": state,
            "region": REGION_MAP[state],
            "npi": f"{np.random.randint(1_000_000_000, 2_000_000_000)}",
        })
    return pd.DataFrame(rows)


def build_members(n):
    rows = []
    for i in range(1, n + 1):
        state = np.random.choice(_states, p=_weights)
        dob = fake.date_of_birth(minimum_age=0, maximum_age=89)
        gender = np.random.choice(["F", "M"], p=[0.51, 0.49])
        plan = np.random.choice(PLAN_TYPES, p=PLAN_WEIGHTS)

        # 70% enrolled the full period; 15% terminate mid-period; 15% enroll mid-period
        r = np.random.random()
        if r < 0.70:
            enr_start, enr_end = DATA_START, None
        elif r < 0.85:
            enr_start = DATA_START
            term_month = random.choice(ALL_MONTHS[3:])
            enr_end = random_date_in_month(term_month)
        else:
            join_month = random.choice(ALL_MONTHS[:-2])
            enr_start = random_date_in_month(join_month)
            enr_end = None

        rows.append({
            "member_id": f"M{i:06d}",
            "first_name": fake.first_name_female() if gender == "F" else fake.first_name_male(),
            "last_name": fake.last_name(),
            "date_of_birth": dob,
            "gender": gender,
            "state": state,
            "region": REGION_MAP[state],
            "zip3": f"{np.random.randint(0, 999):03d}",
            "plan_type": plan,
            "enrollment_start_date": enr_start,
            "enrollment_end_date": enr_end,
        })
    df = pd.DataFrame(rows)
    df["date_of_birth"] = pd.to_datetime(df["date_of_birth"])
    df["age_as_of_data_end"] = (
        (pd.Timestamp(DATA_END) - df["date_of_birth"]).dt.days // 365
    )
    return df


def assign_chronic_conditions(members_df):
    rows = []
    for _, m in members_df.iterrows():
        # prevalence rises with age
        age_factor = 1 + max(0, (m["age_as_of_data_end"] - 40)) * 0.02
        for cond, base_rate in CHRONIC_PREVALENCE.items():
            if np.random.random() < min(base_rate * age_factor, 0.9):
                rows.append({"member_id": m["member_id"], "condition": cond})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Claims generation
# ---------------------------------------------------------------------------

UTILIZATION = {
    # annual events per member, before chronic-condition / age multipliers
    "Professional": 5.5,
    "Outpatient": 1.8,
    "ED": 0.18,
    "Inpatient": 0.07,
    "Pharmacy": 6.0,
}
COST_RANGES = {
    # (allowed_min, allowed_max) before trend/seasonality; calibrated so overall
    # PMPM lands near real commercial-payer benchmarks (~$550-700 allowed PMPM)
    "Professional": (60, 220),
    "Outpatient": (100, 1800),
    "ED": (200, 2800),
    "Inpatient": (6000, 35000),
    "Pharmacy": (8, 850),
}


def enrollment_window(member):
    start = max(DATA_START, member["enrollment_start_date"])
    end = member["enrollment_end_date"] or DATA_END
    end = min(end, DATA_END)
    return start, end


def build_claims(members_df, providers_df, chronic_df):
    chronic_by_member = chronic_df.groupby("member_id")["condition"].apply(list).to_dict()
    providers_by_type = {
        ctype: providers_df[providers_df["specialty"].map(
            lambda s: ctype in SPECIALTY_CLAIM_MAP[s]
        )]
        for ctype in UTILIZATION
    }

    rows = []
    claim_seq = 1

    for _, member in members_df.iterrows():
        win_start, win_end = enrollment_window(member)
        if win_start > win_end:
            continue
        enrolled_days = (win_end - win_start).days + 1
        enrolled_frac = enrolled_days / ((DATA_END - DATA_START).days + 1)

        conditions = chronic_by_member.get(member["member_id"], [])
        chronic_multiplier = 1 + 0.6 * len(conditions)
        age = member["age_as_of_data_end"]
        age_multiplier = 1 + max(0, age - 50) * 0.01

        for claim_type, annual_rate in UTILIZATION.items():
            if claim_type == "Pharmacy" and not conditions and np.random.random() < 0.5:
                continue  # members with no chronic conditions fill fewer scripts
            expected = annual_rate * enrolled_frac * (DATA_END.year - DATA_START.year + 1) / 1
            expected *= chronic_multiplier * age_multiplier
            n_claims = np.random.poisson(max(expected, 0.01))
            if n_claims == 0:
                continue

            candidate_providers = providers_by_type[claim_type]
            if candidate_providers.empty:
                continue

            for _ in range(n_claims):
                span_days = (win_end - win_start).days
                svc_date = win_start + timedelta(days=random.randint(0, max(span_days, 0)))
                provider = candidate_providers.sample(1).iloc[0]
                mult = trend_and_seasonality(svc_date)

                lo, hi = COST_RANGES[claim_type]
                base_allowed = np.random.uniform(lo, hi)
                if conditions:
                    base_allowed *= 1 + 0.15 * len(conditions)
                allowed = round(base_allowed * mult, 2)
                billed = round(allowed * np.random.uniform(1.2, 2.8), 2)

                status = np.random.choice(["Paid", "Denied", "Pending"], p=[0.90, 0.06, 0.04])
                paid = 0.0 if status != "Paid" else round(allowed * np.random.uniform(0.6, 0.95), 2)
                member_resp = round(max(allowed - paid, 0), 2) if status == "Paid" else 0.0

                admission_date = discharge_date = pd.NaT
                if claim_type == "Inpatient":
                    los = max(1, int(np.random.exponential(4)))
                    admission_date = svc_date
                    discharge_date = svc_date + timedelta(days=los)

                if claim_type == "Inpatient":
                    dx_desc, dx_code, drg = random.choice(IP_DIAGNOSES)
                    proc_desc, proc_code = f"MS-DRG {drg}", drg
                elif claim_type == "ED":
                    dx_desc, dx_code = random.choice(ED_DIAGNOSES)
                    proc_desc, proc_code = random.choice(PROCEDURES_ED)
                elif claim_type == "Outpatient":
                    dx_desc, dx_code = random.choice(ACUTE_DIAGNOSES)
                    proc_desc, proc_code = random.choice(PROCEDURES_OUTPATIENT)
                elif claim_type == "Professional":
                    if conditions and np.random.random() < 0.5:
                        cond = random.choice(conditions)
                        dx_desc, dx_code = cond, CHRONIC_CONDITIONS[cond][0]
                        dx_desc = CHRONIC_CONDITIONS[cond][1]
                    else:
                        dx_desc, dx_code = random.choice(ACUTE_DIAGNOSES)
                    proc_desc, proc_code = random.choice(PROCEDURES_PROFESSIONAL)
                else:  # Pharmacy
                    drug_name, ndc, unit_cost = random.choice(DRUGS)
                    dx_desc, dx_code = "N/A (pharmacy claim)", None
                    proc_desc, proc_code = drug_name, ndc
                    allowed = round(unit_cost * np.random.uniform(0.8, 1.4) * mult, 2)
                    billed = round(allowed * np.random.uniform(1.1, 1.6), 2)
                    paid = 0.0 if status != "Paid" else round(allowed * np.random.uniform(0.7, 0.95), 2)
                    member_resp = round(max(allowed - paid, 0), 2) if status == "Paid" else 0.0

                rows.append({
                    "claim_id": f"C{claim_seq:08d}",
                    "member_id": member["member_id"],
                    "provider_id": provider["provider_id"],
                    "claim_type": claim_type,
                    "service_date": svc_date,
                    "admission_date": admission_date,
                    "discharge_date": discharge_date,
                    "place_of_service": PLACE_OF_SERVICE[claim_type],
                    "diagnosis_code": dx_code,
                    "diagnosis_desc": dx_desc,
                    "procedure_or_drug_code": proc_code,
                    "procedure_or_drug_desc": proc_desc,
                    "billed_amount": billed,
                    "allowed_amount": allowed,
                    "paid_amount": paid,
                    "member_responsibility": member_resp,
                    "claim_status": status,
                    "submission_date": svc_date + timedelta(days=random.randint(1, 30)),
                })
                claim_seq += 1

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Data-quality issue injection (see docs/data_generation_notes.md for the key)
# ---------------------------------------------------------------------------

def inject_data_quality_issues(claims_df, members_df, providers_df):
    df = claims_df.copy()
    n = len(df)
    rng = np.random.default_rng(SEED)

    exact_dupe_idx = rng.choice(df.index, size=int(n * 0.003), replace=False)
    exact_dupes = df.loc[exact_dupe_idx].copy()
    df = pd.concat([df, exact_dupes], ignore_index=True)

    near_dupe_idx = rng.choice(df.index, size=int(n * 0.004), replace=False)
    near_dupes = df.loc[near_dupe_idx].copy()
    near_dupes["claim_id"] = [f"C{9000000 + i:08d}" for i in range(len(near_dupes))]
    df = pd.concat([df, near_dupes], ignore_index=True)

    missing_dx_idx = rng.choice(df.index, size=int(len(df) * 0.01), replace=False)
    df.loc[missing_dx_idx, "diagnosis_code"] = None

    orphan_member_idx = rng.choice(df.index, size=int(len(df) * 0.003), replace=False)
    df.loc[orphan_member_idx, "member_id"] = "M999999"

    orphan_provider_idx = rng.choice(df.index, size=int(len(df) * 0.003), replace=False)
    df.loc[orphan_provider_idx, "provider_id"] = "P999999"

    ip_idx = df.index[df["claim_type"] == "Inpatient"]
    bad_date_idx = rng.choice(ip_idx, size=max(1, int(len(ip_idx) * 0.02)), replace=False)
    tmp = df.loc[bad_date_idx, "admission_date"].copy()
    df.loc[bad_date_idx, "admission_date"] = df.loc[bad_date_idx, "discharge_date"]
    df.loc[bad_date_idx, "discharge_date"] = tmp

    outlier_idx = rng.choice(df.index, size=int(len(df) * 0.001), replace=False)
    df.loc[outlier_idx, "allowed_amount"] = df.loc[outlier_idx, "allowed_amount"] * 50

    negative_idx = rng.choice(df.index, size=int(len(df) * 0.001), replace=False)
    df.loc[negative_idx, "paid_amount"] = -abs(df.loc[negative_idx, "paid_amount"] + 1)

    members_df = members_df.copy()
    missing_gender_idx = rng.choice(members_df.index, size=int(len(members_df) * 0.01), replace=False)
    members_df.loc[missing_gender_idx, "gender"] = None
    missing_state_idx = rng.choice(members_df.index, size=int(len(members_df) * 0.008), replace=False)
    members_df.loc[missing_state_idx, "state"] = None

    return df, members_df


def main():
    print(f"Generating {N_MEMBERS} members, {N_PROVIDERS} providers, "
          f"{DATA_START} to {DATA_END} ...")

    calendar_df = build_calendar()
    providers_df = build_providers(N_PROVIDERS)
    members_df = build_members(N_MEMBERS)
    chronic_df = assign_chronic_conditions(members_df)

    print("Generating claims (this is the slow step)...")
    claims_df = build_claims(members_df, providers_df, chronic_df)
    print(f"  {len(claims_df):,} claims generated before DQ injection")

    claims_df, members_df = inject_data_quality_issues(claims_df, members_df, providers_df)
    print(f"  {len(claims_df):,} claims after DQ injection")

    import os
    os.makedirs(OUT_DIR, exist_ok=True)
    calendar_df.to_csv(f"{OUT_DIR}/dim_calendar.csv", index=False)
    providers_df.to_csv(f"{OUT_DIR}/dim_providers.csv", index=False)
    members_df.to_csv(f"{OUT_DIR}/dim_members.csv", index=False)
    chronic_df.to_csv(f"{OUT_DIR}/dim_member_chronic_conditions.csv", index=False)
    claims_df.to_csv(f"{OUT_DIR}/fact_claims.csv", index=False)

    print("\nRow counts:")
    for name, d in [("dim_calendar", calendar_df), ("dim_providers", providers_df),
                     ("dim_members", members_df),
                     ("dim_member_chronic_conditions", chronic_df),
                     ("fact_claims", claims_df)]:
        print(f"  {name}: {len(d):,}")
    print(f"\nClaims by type:\n{claims_df['claim_type'].value_counts()}")
    print(f"\nTotal allowed amount: ${claims_df['allowed_amount'].sum():,.2f}")
    print(f"\nSaved to {OUT_DIR}/")


if __name__ == "__main__":
    main()
