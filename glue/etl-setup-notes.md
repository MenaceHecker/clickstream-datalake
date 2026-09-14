# Phase 6 — Glue ETL: JSON → Partitioned Parquet — Setup Notes

## What was validated locally before writing the real Glue script

`etl_job.py` depends on the `awsglue` library, which only exists inside
the actual Glue job runtime — it can't be run standalone with plain
`python`. Before finalizing it, the core transformation logic (cleaning,
timestamp normalization, partition columns) was tested locally with
plain PySpark against hand-built sample data that intentionally included:

- Records with `discount_code` and records without it at all (the real
  schema-evolution case from Phase 1)
- A record with an empty-string `event_id`
- A record with a `null` timestamp
- A genuinely malformed JSON line

Result: Spark's JSON reader naturally unions schemas across files
(discount_code shows up as nullable everywhere, no special code needed),
and the cleaning filter correctly dropped all three bad records while
keeping the four valid ones.

**One real bug this caught**: Spark's default `F.month()` / `F.dayofmonth()`
produce unpadded values (`month=9`, not `month=09`), which would have been
silently inconsistent with the zero-padded `month=09` format already used
in the raw zone since Phase 2. The final script uses `date_format(...,
"MM")` / `date_format(..., "dd")` instead, verified to produce matching
`month=09/day=10` partition folders. Worth mentioning in an interview as
a real "caught it by testing before deploying" story rather than
discovering it after Athena partition-pruning behaved unexpectedly.

## 1. Create the ETL service role

See `iam/glue-etl-role-policy.json`. Different permission shape than the
crawler role from Phase 5 — this one reads `raw/*`, writes `curated/*`,
and reads/writes the Data Catalog directly (rather than just the
crawler's read-catalog-write-catalog pattern).

## 2. Upload the script to S3

Glue jobs run from a script stored in S3, not inline:

```bash
aws s3 cp glue/etl_job.py s3://clickstream-lake-mtusharaug/glue-scripts/etl_job.py
```

## 3. Create the job

```bash
aws glue create-job --cli-input-json file://glue/etl-job-config.json
```

Note the job config uses **2 workers on G.1X** (Glue's smallest worker
type) — per the risk register, start minimal and only scale up if the
job actually needs it. At this data volume (a few hundred small JSON
files), 2 workers is generous, not a bottleneck.

## 4. Run it

```bash
aws glue start-job-run --job-name clickstream-json-to-parquet
```

Poll status:
```bash
aws glue get-job-runs --job-name clickstream-json-to-parquet \
  --query 'JobRuns[0].[JobRunState,ErrorMessage]'
```

Check CloudWatch Logs (`/aws-glue/jobs/output`) for the `print()`
statements in the script — record counts before/after cleaning, dropped
count, and final schema will show up there.

## 5. Verify the curated output

```bash
aws s3 ls s3://clickstream-lake-mtusharaug/curated/ --recursive
```

Should show `.snappy.parquet` files under `year=2026/month=09/day=XX/`
partitions.

## 6. Crawl the curated zone

Per the plan, run a second crawler so curated data is queryable too:

```bash
aws glue create-database --database-input '{"Name": "clickstream_curated"}'
aws glue create-crawler --cli-input-json file://glue/curated-crawler-config.json
aws glue start-crawler --name clickstream-curated-crawler
```

## 7. Confirm schema evolution survived the round-trip

```bash
aws glue get-table --database-name clickstream_curated --name curated \
  --query 'Table.StorageDescriptor.Columns[?Name==`discount_code`]'
```

Should show `discount_code` as a `string` column, nullable, present in
the curated schema exactly as it was in raw — confirming the ETL job
preserved the field through the transformation rather than silently
dropping it because some source files never had it.

## Definition of done

- [ ] ETL job runs successfully end-to-end (`JobRunState: SUCCEEDED`)
- [ ] Curated zone contains partitioned, Snappy-compressed Parquet files
- [ ] Partition format (`month=09`, zero-padded) matches the raw zone's
      convention — verified, not assumed
- [ ] Curated crawler run, `clickstream_curated.curated` table exists
- [ ] `discount_code` schema-evolution case confirmed present in curated
      schema, not dropped

## Cost checkpoint

Glue ETL jobs bill per DPU-hour with a 1-minute minimum billing
increment (unlike crawlers' 10-minute floor). At 2 workers (2 DPU) and a
job that should complete in well under a minute for this data volume,
this run costs a small fraction of a DPU-hour. Record the actual job run
duration from CloudWatch/Glue console for the Phase 10 cost report — this
is the number that turns into a real "$X for the transformation that
enabled a Y% query cost reduction" resume line.