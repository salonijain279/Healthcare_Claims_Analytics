"""
EXTRACT stage.

Pulls from two source shapes, same as a real pipeline usually has to:
  1. Flat files (the CSVs in data/raw/) -> loaded as-is into a `raw` schema,
     columns kept as TEXT/loosely typed on purpose. Real source extracts are
     messy; casting/cleaning belongs in Transform, not here.
  2. A simulated NoSQL/JSON claims-submission feed -> the same claim facts,
     re-shaped as nested JSON documents and loaded into a JSONB column
     (raw.claims_json). This stands in for e.g. a claims-intake API that
     hands you semi-structured documents instead of flat rows.

Run after generate_synthetic_data.py (or after real source CSVs are dropped
into data/raw/). Idempotent: drops and recreates the `raw` schema each run.
"""
import json

import pandas as pd
import psycopg2
import psycopg2.extras as pg_extras

DB_DSN = "dbname=healthcare_claims"
RAW_DIR = "data/raw"

FLAT_FILE_TABLES = {
    "dim_calendar": "src_calendar",
    "dim_providers": "src_providers",
    "dim_members": "src_members",
    "dim_member_chronic_conditions": "src_chronic_conditions",
    "fact_claims": "src_claims",
}


def get_conn():
    return psycopg2.connect(DB_DSN)


def reset_schema(conn):
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS raw CASCADE;")
        cur.execute("CREATE SCHEMA raw;")
    conn.commit()


def load_flat_file(conn, csv_name, table_name):
    """Extract-as-is: every column lands as TEXT. No type coercion here."""
    df = pd.read_csv(f"{RAW_DIR}/{csv_name}.csv", dtype=str)
    cols = list(df.columns)
    col_defs = ", ".join(f'"{c}" TEXT' for c in cols)

    with conn.cursor() as cur:
        cur.execute(f'CREATE TABLE raw.{table_name} ({col_defs});')
    conn.commit()

    df = df.where(pd.notnull(df), None)
    quoted_cols = ", ".join(f'"{c}"' for c in cols)
    with conn.cursor() as cur:
        pg_extras.execute_values(
            cur,
            f"INSERT INTO raw.{table_name} ({quoted_cols}) VALUES %s",
            df.itertuples(index=False, name=None),
            page_size=5000,
        )
    conn.commit()
    print(f"  raw.{table_name}: {len(df):,} rows")


def build_claims_json_document(row) -> dict:
    """Reshape one flat claim row into a nested document, as if it had
    arrived from a claims-submission API rather than a flat extract."""
    return {
        "claim_id": row["claim_id"],
        "member_id": row["member_id"],
        "provider_id": row["provider_id"],
        "claim_type": row["claim_type"],
        "dates": {
            "service_date": row["service_date"],
            "admission_date": row["admission_date"] if pd.notna(row["admission_date"]) else None,
            "discharge_date": row["discharge_date"] if pd.notna(row["discharge_date"]) else None,
            "submission_date": row["submission_date"],
        },
        "place_of_service": row["place_of_service"],
        "diagnosis": {
            "code": row["diagnosis_code"] if pd.notna(row["diagnosis_code"]) else None,
            "description": row["diagnosis_desc"],
        },
        "procedure_or_drug": {
            "code": row["procedure_or_drug_code"],
            "description": row["procedure_or_drug_desc"],
        },
        "amounts": {
            "billed": row["billed_amount"],
            "allowed": row["allowed_amount"],
            "paid": row["paid_amount"],
            "member_responsibility": row["member_responsibility"],
        },
        "status": row["claim_status"],
    }


def load_claims_json(conn):
    """Simulated NoSQL/JSON source: same claims, semi-structured shape."""
    df = pd.read_csv(f"{RAW_DIR}/fact_claims.csv")

    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE raw.claims_json (
                claim_id TEXT PRIMARY KEY,
                doc JSONB NOT NULL
            );
        """)
    conn.commit()

    records = [
        (row["claim_id"], json.dumps(build_claims_json_document(row), default=str))
        for _, row in df.iterrows()
    ]
    # claim_id is the document key here (unlike the flat extract, which has no
    # PK). Source data has some duplicate claim_ids seeded in on purpose -- a
    # keyed document store can't silently accept those the way a flat table
    # did above, so we upsert (first write wins) and report what got skipped.
    with conn.cursor() as cur:
        pg_extras.execute_values(
            cur,
            "INSERT INTO raw.claims_json (claim_id, doc) VALUES %s "
            "ON CONFLICT (claim_id) DO NOTHING",
            records,
            template="(%s, %s::jsonb)",
            page_size=5000,
        )
        cur.execute("SELECT count(*) FROM raw.claims_json;")
        loaded = cur.fetchone()[0]
    conn.commit()
    skipped = len(records) - loaded
    print(f"  raw.claims_json: {loaded:,} documents loaded, {skipped:,} duplicate claim_id(s) skipped on upsert")


def main():
    conn = get_conn()
    print("Resetting raw schema...")
    reset_schema(conn)

    print("Loading flat-file sources...")
    for csv_name, table_name in FLAT_FILE_TABLES.items():
        load_flat_file(conn, csv_name, table_name)

    print("Loading simulated JSON/NoSQL claims feed...")
    load_claims_json(conn)

    with conn.cursor() as cur:
        cur.execute("""
            CREATE INDEX idx_claims_json_claim_type
            ON raw.claims_json ((doc->>'claim_type'));
        """)
    conn.commit()

    conn.close()
    print("\nExtract complete. Tables in `raw` schema:")
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'raw' ORDER BY table_name;
        """)
        for (t,) in cur.fetchall():
            print(f"  raw.{t}")
    conn.close()


if __name__ == "__main__":
    main()
