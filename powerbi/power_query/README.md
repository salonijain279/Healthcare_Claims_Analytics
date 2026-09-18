# Power Query (M) scripts

Paste these into Power BI Desktop's Advanced Editor (Home → Transform Data →
Advanced Editor on a new blank query). They're not runnable outside Power BI
(no M interpreter here), so treat them as reference to build from, not a
guaranteed drop-in — check column names against whatever the live `mart`
schema looks like when you connect.

| File | Demonstrates |
|---|---|
| `01_connect_source_parameterized.pq` | Parameterized connection to the Postgres `mart` schema (PGServer/PGDatabase parameters) |
| `02_unpivot_wide_monthly_costs.pq` | `Table.UnpivotOtherColumns` — wide spreadsheet-shaped input → tidy long format |
| `03_pivot_claim_type_matrix.pq` | `Table.Group` + `Table.Pivot` — tidy long format → a claim-type-by-month matrix |

See [../build_guide/](../build_guide/) for the full page-by-page dashboard
build instructions these feed into.
