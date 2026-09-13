# Phase 3 (Path B) — Kinesis Data Stream + Firehose Setup

Goal: replace manual/batch file uploads with a real streaming pipeline.
`kinesis_producer.py` pushes records continuously; Firehose buffers and
writes them to the S3 raw zone automatically so no Lambda in this path.

## 1. Create the Kinesis Data Stream

Console: Kinesis → Data Streams → Create data stream

| Setting | Value | Why |
|---|---|---|
| Stream name | `clickstream-events-stream` | |
| Capacity mode | **On-demand** | Volume here is low and bursty (a producer script, not real traffic); on-demand avoids paying for provisioned shard-hours you don't need. Provisioned (1 shard) is the cheaper choice only if you know you'll run the producer for many hours straight — on-demand is the safer default for a portfolio project you'll start and stop. |
| Tag | `Project: clickstream-lake` | |

CLI equivalent:
```bash
aws kinesis create-stream \
  --stream-name clickstream-events-stream \
  --stream-mode-details StreamMode=ON_DEMAND

aws kinesis tag-resource \
  --resource-arn arn:aws:kinesis:<region>:<account-id>:stream/clickstream-events-stream \
  --tags Project=clickstream-lake
```

## 2. Create the Firehose delivery stream

Console: Kinesis → Data Firehose → Create delivery stream

| Setting | Value |
|---|---|
| Source | Amazon Kinesis Data Streams |
| Kinesis stream | `clickstream-events-stream` |
| Destination | Amazon S3 |
| S3 bucket | `clickstream-lake-mtusharaug` |
| S3 prefix | `raw/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/` |
| S3 error output prefix | `firehose-errors/!{firehose:error-output-type}/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/` |
| Buffer size | 5 MB (minimum useful size given our low record volume) |
| Buffer interval | 60 seconds |
| Compression | GZIP |
| Firehose IAM role | New service role (see `iam/firehose-service-role-policy.json`) |

CLI is possible too but the console wizard auto-creates the IAM service
role and trust policy correctly on the first try, which is fiddly to get
right by hand — recommended to do this one step via console even though
everything else in this project favors CLI/CDK.

### Important trade-off: delivery-time vs. event-time partitioning

Phase 2's batch uploader (`upload_to_s3.py`) partitions by the **event's own
timestamp**, read from inside each file. Firehose's `!{timestamp:...}`
prefix expressions use **delivery time** — when Firehose flushes the
buffer — not the event's original timestamp.

In practice these are seconds to low-minutes apart (that's what the 60s
buffer means), so partitions still land in essentially the right hour.
But it's not identical, and it's worth stating explicitly rather than
letting it look like an oversight: **streamed data is partitioned by
approximate ingest time; batch-uploaded data is partitioned by exact
event time.** Both write into the same `raw/` zone with the same
partition key names (`year=/month=/day=/hour=`), so Glue crawls them
identically in Phase 5 — the distinction only matters if you're doing
time-sensitive analysis at minute-level granularity, which this project
isn't.

An alternative that removes the discrepancy entirely is Firehose's
**dynamic partitioning** feature, which can extract the real
`timestamp` field from each JSON record via a JQ expression instead of
using delivery time. It costs slightly more per GB processed and adds
setup complexity (requires enabling record de-aggregation + a JQ
expression per partition key). Documented here as the "more correct"
option but not implemented, in the interest of not over-engineering a
low-volume portfolio pipeline, this is itself a defensible cost/effort
trade-off worth mentioning if asked.

## 3. Run the producer

```bash
source venv/bin/activate
cd ingestion
python kinesis_producer.py --stream-name clickstream-events-stream --rate 5 --duration-seconds 300
```

Let it run a few minutes, then check S3 — Firehose's 60-second buffer
means the first objects should appear shortly after the run starts.

```bash
aws s3 ls s3://clickstream-lake-mtusharaug/raw/ --recursive | tail -20
```

## Definition of done

- [ ] Kinesis Data Stream `clickstream-events-stream` created, tagged
- [ ] Firehose delivery stream created, pointed at the stream and the
      correct S3 prefix
- [ ] Producer run for at least a few minutes without errors
- [ ] New partitions visible in S3 under `raw/`, populated automatically
      with no manual upload step
- [ ] Delivery-time-vs-event-time trade-off documented (this file)

## Cost checkpoint

On-demand Kinesis: charged per shard-hour equivalent + per-GB data
ingested, both negligible at this volume. Firehose: charged per GB
ingested, also negligible for a short producer run. Nothing here should
move the needle against the $200 pool but per the risk register, don't
forget to `aws kinesis delete-stream` and delete the Firehose delivery
stream when you're done experimenting, since Kinesis (unlike Lambda) has
an always-on cost component even when idle in provisioned mode. On-demand
avoids the worst of this but still isn't literally free to leave running
indefinitely.