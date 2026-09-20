# Phase 5 — Glue Crawler & Data Catalog Setup

Goal: make the raw JSON queryable without manually defining a schema.

## 1. Create the Glue service role

See `iam/glue-crawler-role-policy.json` for the trust policy and
permissions. Either create it by hand from that file, or let the Glue
console's "Create crawler" wizard offer to create one for you (it'll
attach the AWS-managed `AWSGlueServiceRole` policy plus an S3 read
statement it generates from the path you give it — functionally similar
to the scoped version documented here, just less tightly scoped to this
one bucket/prefix).

```bash
aws iam create-role \
  --role-name clickstream-glue-crawler-role \
  --assume-role-policy-document file://../iam/glue-crawler-role-policy.json  # extract just the trust_policy block
```

(The JSON file bundles the trust policy and permissions policy together
for readability — when actually creating the role via CLI, pull out the
`trust_policy` object for `--assume-role-policy-document` and the
`permissions_policy` object for a separate `put-role-policy` call. The
console wizard doesn't have this problem since it handles both in one
flow.)

## 2. Create the Glue database

```bash
aws glue create-database --database-input '{"Name": "clickstream_raw"}'
```

## 3. Create and run the crawler

```bash
aws glue create-crawler --cli-input-json file://crawler-config.json
aws glue start-crawler --name clickstream-raw-crawler
```

Check status:
```bash
aws glue get-crawler --name clickstream-raw-crawler --query 'Crawler.State'
```

Crawlers run asynchronously — this typically takes 1-3 minutes for a
dataset this size. Poll until `State` returns to `READY`.

## 4. Verify the catalog table

```bash
aws glue get-table --database-name clickstream_raw --name raw
```

Check that:
- Partition keys show `year`, `month`, `day`, `hour` (inferred from the
  Hive-style S3 path structure built in Phase 2/3)
- Columns match the event schema: `event_id`, `event_type`, `user_id`,
  `session_id`, `timestamp`, `product_id`, `category`, `price`,
  `device_type`, `referrer`, `country`, and `discount_code`

## Handling the schema-evolution case

The generator (Phase 1) deliberately introduces `discount_code` partway
through data generation — earlier events don't have the key at all,
later ones do. This is exactly the kind of real-world schema drift a
crawler has to handle.

`crawler-config.json` sets `"TableGroupingPolicy":
"CombineCompatibleSchemas"` specifically so the crawler treats this as
one evolving table with an optional column, rather than splitting raw
data into two separate tables because their schemas don't match exactly.
`SchemaChangePolicy.UpdateBehavior: UPDATE_IN_DATABASE` means future
recrawls update the existing table definition instead of creating
duplicates.

After the first crawl, confirm this actually worked as intended:
```bash
aws glue get-table --database-name clickstream_raw --name raw \
  --query 'Table.StorageDescriptor.Columns[].Name'
```
`discount_code` should appear as a nullable column across the whole
table, not cause two different tables to exist.

## 5. Smoke-test with Athena (before Phase 6/7 exist)

Even before any ETL work, the raw catalog table should already be
queryable:

```sql
SELECT event_type, COUNT(*) 
FROM clickstream_raw.raw 
GROUP BY event_type;
```

Run this from the Athena console or CLI. If it returns funnel counts
that roughly match the ratios from Phase 1's generator (100:40:15:10:7),
the catalog is correctly wired up to the underlying data.

Note: Athena needs a query-result location configured
(`s3://clickstream-lake-mtusharaug/athena-results/`) before it will run
anything — set this once in the Athena console under Workgroup settings
if you haven't already.

## Definition of done

- [ ] Glue database `clickstream_raw` exists
- [ ] Crawler created and run successfully (`State: READY`, no errors)
- [ ] Catalog table shows correct columns and partition keys
- [ ] `discount_code` schema-evolution case confirmed handled as one
      table, not split
- [ ] Test query in Athena returns real data matching expected funnel
      shape

## Cost checkpoint

Glue crawlers are billed per DPU-hour with a 10-minute minimum per run.
At this data volume (a few hundred small JSON files), a single crawl run
should complete in 1-3 minutes but still bills the 10-minute minimum —
this is a fixed cost per crawl regardless of data size, worth remembering
before recrawling repeatedly out of habit while testing. Note the actual
duration and DPU count used here for the Phase 10 cost report; this is a
useful "small negligible cost, but understand why it has a floor"
data point.