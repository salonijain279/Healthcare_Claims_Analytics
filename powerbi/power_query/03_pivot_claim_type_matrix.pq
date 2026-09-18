// PIVOT EXAMPLE (the reverse direction)
// ---------------------------------------------------------------
// Takes the tidy long-format FactClaims query (see
// 01_connect_source_parameterized.pq) and produces a claim_type-by-month
// cost matrix -- useful for an executive summary tile that needs
// "Inpatient / Outpatient / ED / Professional / Pharmacy" as columns,
// without building five separate measures with SWITCH() in DAX.
//
// Paste after the FactClaims query steps (references it by name), or
// treat as its own query with Source = FactClaims.

let
    Source = FactClaims,
    AddYearMonth = Table.AddColumn(Source, "year_month",
        each Date.ToText([service_date], "yyyy-MM"), type text),

    Grouped = Table.Group(AddYearMonth, {"year_month", "claim_type"}, {
        {"allowed_amount", each List.Sum([allowed_amount]), type number}
    }),

    Pivoted = Table.Pivot(
        Grouped,
        List.Distinct(Grouped[claim_type]),
        "claim_type",
        "allowed_amount",
        List.Sum
    ),

    SortedByMonth = Table.Sort(Pivoted, {{"year_month", Order.Ascending}})
in
    SortedByMonth

// Result: year_month | ED | Inpatient | Outpatient | Pharmacy | Professional
// one row per month, one column per claim type.
