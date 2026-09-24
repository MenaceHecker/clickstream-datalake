# Phase 7 — Athena Cost Comparison: JSON vs. Parquet

This is the single most interview-relevant artifact in the whole
project: hard numbers proving the Phase 6 ETL transformation was worth
doing, not just a "best practice" applied on faith.

## Method

Run the *same logical query* against both tables — raw JSON
(`clickstream_raw.raw`) and curated Parquet (`clickstream_curated.curated`)
— and compare Athena's reported "data scanned" for each.

The revenue-by-country query is the best one to use for this comparison:
it touches every row (aggregates over the whole `purchase` event set) and
uses the same column names in both tables, so it's a fair apples-to-apples
comparison rather than one query structure vs. a different one.

### Query A — against raw JSON

```sql
SELECT
    country,
    device_type,
    COUNT(*) AS purchase_count,
    ROUND(SUM(price), 2) AS total_revenue
FROM clickstream_raw.raw
WHERE event_type = 'purchase'
GROUP BY country, device_type
ORDER BY total_revenue DESC;
```

### Query B — against curated Parquet

Same query, `FROM clickstream_curated.curated` instead — this is exactly
`revenue_by_country.sql` from this same folder, minus the `avg_order_value`
column (dropped here only so both queries select identical columns for a
clean comparison).

## Getting the actual bytes-scanned numbers

Run each query from the Athena console, or via CLI:

```bash
QUERY_ID=$(aws athena start-query-execution \
  --query-string "SELECT country, device_type, COUNT(*) AS purchase_count, ROUND(SUM(price),2) AS total_revenue FROM clickstream_raw.raw WHERE event_type='purchase' GROUP BY country, device_type ORDER BY total_revenue DESC" \
  --query-execution-context Database=clickstream_raw \
  --result-configuration OutputLocation=s3://clickstream-lake-mtusharaug/athena-results/ \
  --query 'QueryExecutionId' --output text)

# wait a few seconds for it to finish, then:
aws athena get-query-execution --query-execution-id $QUERY_ID \
  --query 'QueryExecution.Statistics.DataScannedInBytes'
```

Repeat with `Database=clickstream_curated` and the curated table name to
get the second number.

## Cost math

Athena charges **$5.00 per TB scanned** (standard on-demand pricing,
verify current rate before finalizing the write-up since pricing can
change). To convert bytes scanned into a dollar figure:

```
cost = (bytes_scanned / 1_099_511_627_776) * 5.00   # bytes -> TiB -> dollars
```

Actual numbers, pulled via the CLI method above on 2026-09-24:

| | Raw JSON | Curated Parquet | Reduction |
|---|---|---|---|
| Data scanned | 4,350,579 bytes (4.15 MB) | 121,131 bytes (118.3 KB) | **97.22%** |
| Estimated cost | $0.0000198 | $0.00000055 | 97.22% |

(`DataScannedInBytes` from `GetQueryExecution`, both queries against the
full `purchase`-event set — 11,443 total curated events at the time of this
run, `SELECT COUNT(*) FROM clickstream_curated.curated`.)

## An honest caveat about this project's scale

At the data volumes this project generates (a few thousand simulated
events, well under a GB total), **both queries will scan a tiny amount of
data in absolute terms** — likely single-digit MB either way, meaning
the dollar costs involved round to fractions of a cent regardless of
which table you query. The *percentage* reduction should still be
meaningful and worth reporting (Parquet's columnar format + compression
+ predicate pushdown genuinely does scan less data, even at small scale),
but don't be surprised if it's a more modest number than the "reduced
scan by 94%" case studies quoted elsewhere for production-scale datasets
with much larger individual files.

The honest framing for a resume bullet or interview: report the actual
measured percentage from your own run, and be ready to explain *why* the
underlying mechanism (columnar storage, compression, partition pruning,
no per-record JSON parsing overhead) scales favorably even though this
particular simulation doesn't generate enough data to show its full
effect. That explanation is worth more to an interviewer than an
inflated number would be — you understand the mechanism, not just the
marketing claim, whatever the actual number is at this scale.

## What to fill in before Phase 10

- [x] Run Query A and Query B, record actual `DataScannedInBytes` for both
- [x] Fill in the comparison table above
- [x] Note current Athena per-TB pricing at the time you ran this (in
      case it's changed by the time you write the final README) — $5.00/TB,
      us-east-1, as of 2026-09-24
- [x] Carry the final numbers into `docs/cost-report.md` in Phase 10