// UNPIVOT EXAMPLE
// ---------------------------------------------------------------
// Real scenario this represents: someone on finance hands you a
// spreadsheet shaped like data/raw/wide_examples/monthly_cost_wide.csv --
// one row per claim_type, one COLUMN per month. That's fine for a human
// to eyeball, unusable for a data model (you'd need a measure per month).
// Table.UnpivotOtherColumns turns it into tidy long format: one row per
// (claim_type, year_month) observation, which is what Power BI actually
// wants to build visuals and DAX measures against.
//
// How to use: Get Data -> Text/CSV -> point at
// data/raw/wide_examples/monthly_cost_wide.csv, then replace the
// auto-generated steps with this Advanced Editor code (adjust the file
// path for wherever you copied the repo).

let
    Source = Csv.Document(
        File.Contents("C:\path\to\Healthcare_Claims_Analytics\data\raw\wide_examples\monthly_cost_wide.csv"),
        [Delimiter=",", Columns=25, Encoding=1252, QuoteStyle=QuoteStyle.None]
    ),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    TypedClaimType = Table.TransformColumnTypes(PromotedHeaders, {{"claim_type", type text}}),

    // Everything except claim_type is a month column -- unpivot those into
    // (Attribute, Value) pairs, then rename to something readable.
    Unpivoted = Table.UnpivotOtherColumns(
        TypedClaimType, {"claim_type"}, "year_month", "allowed_amount"
    ),
    Renamed = Table.RenameColumns(Unpivoted, {{"claim_type", "ClaimType"}}),
    TypedValue = Table.TransformColumnTypes(Renamed, {{"allowed_amount", type number}})
in
    TypedValue

// Result: ClaimType | year_month | allowed_amount, one row per
// (claim_type, month) pair -- directly usable in a line chart or matrix
// without a measure per month.
