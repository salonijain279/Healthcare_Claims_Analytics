// PARAMETERIZED SOURCE CONNECTION
// ---------------------------------------------------------------
// How to use in Power BI Desktop:
//   1. Home -> Manage Parameters -> New Parameter, create two text
//      parameters named exactly PGServer and PGDatabase (defaults
//      below), so the whole model can be re-pointed at a different
//      Postgres instance (dev/prod, another analyst's machine) by
//      editing two values instead of rewriting every query.
//   2. Home -> Transform Data -> New Source -> Blank Query -> Advanced
//      Editor, paste the "FactClaims" query below, rename the query
//      to FactClaims.
//   3. Repeat for the other mart tables you want (DimMembers,
//      DimProviders, DimDate, DimDiagnosis, DimProcedure) by swapping
//      the table name in the Source step.
//
// Requires the Npgsql PostgreSQL driver installed on the Windows
// machine running Power BI Desktop (Power BI's built-in PostgreSQL
// connector depends on it). Local Postgres install here has no
// password on localhost -- if you move this to a hosted Postgres,
// add a Data Source Settings credential in Power BI rather than
// hardcoding one in M.

// --- Parameters (create these via Manage Parameters, not pasted as code) ---
// PGServer   (text, default "localhost")
// PGDatabase (text, default "healthcare_claims")

// --- Query: FactClaims ---
let
    Source = PostgreSQL.Database(PGServer, PGDatabase),
    mart_fact_claims = Source{[Schema="mart", Item="fact_claims"]}[Data],
    // Keep the transform-at-the-pipeline-level principle even in Power
    // Query: this is a thin pass-through, not a place to re-derive
    // business logic that already lives in the SQL layer.
    ChangedTypes = Table.TransformColumnTypes(mart_fact_claims, {
        {"service_date", type date},
        {"allowed_amount", type number},
        {"paid_amount", type number}
    })
in
    ChangedTypes
