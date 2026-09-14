# Phase 4 — Storage Tiering & Lifecycle Policy Rationale

## What's configured

| Prefix | Rule | Rationale |
|---|---|---|
| `raw/` | Standard → Standard-IA at 30 days → Glacier Instant Retrieval at 90 days | Raw JSON is rarely re-queried once curated Parquet exists (Phase 6); ages out to cheaper tiers as it becomes cold. |
| `athena-results/` | Expire at 7 days | Query result cache so no reason to keep it past the session that generated it. |
| `test-intelligent-tiering/` | Immediate transition to Intelligent-Tiering | Empty test prefix, used only to compare Intelligent-Tiering's automatic behavior against the manual rules above. See comparison below. |
| `curated/` | **No rule — deliberately** | Actively queried by Athena/QuickSight; keeping it on Standard avoids retrieval latency and IA/Glacier retrieval fees on every query. |
| *(bucket-wide)* | Abort incomplete multipart uploads after 7 days | Housekeeping stray multipart uploads from interrupted transfers otherwise bill indefinitely with nothing to show for it. |

## The caveat that actually matters here: small-object overhead on IA

S3 Standard-IA (and by extension Glacier IR) has a **minimum billable
object size of 128 KB** so an object smaller than that is billed for
storage as if it were 128 KB, both for storage cost and for the
per-request retrieval fee that IA charges.

This project's raw JSONL batch files are typically 15–25 KB (see actual
Phase 2 upload sizes, e.g. `events_20260910_1725.jsonl` at ~13 KB). That
means transitioning them to IA doesn't just fail to save money at this
volume, it can make files *more expensive per byte stored* than leaving
them on Standard, because the 128 KB floor is being applied to a file a
fraction of that size.

This is not a mistake in the lifecycle policy — it's the realistic
behavior of a low-volume simulation, and it's worth stating outright
rather than letting the numbers look like a modeling error later in
`docs/cost-report.md`. At real production event volumes (continuous
ingestion producing much larger batched files, or many small files
consolidated by a compaction job before tiering), this trade-off flips:
IA becomes genuinely cheaper once individual objects clear the 128 KB
floor by a comfortable margin. The honest framing for this project is:
**the lifecycle rules are correctly configured to demonstrate the
pattern, but the actual dollar savings only materialize at a production
scale this simulation intentionally doesn't reach.**

## Manual rules vs. Intelligent-Tiering

Intelligent-Tiering automatically moves objects between access tiers
based on observed access patterns, for a small monitoring fee per object
(also has its own minimum-object-size consideration, though a smaller
one than IA's storage class).

| | Manual lifecycle rules (this project's raw zone) | Intelligent-Tiering |
|---|---|---|
| Predictability | You control exactly when transitions happen | AWS decides based on 30-day access-pattern windows |
| Cost at low, predictable volume | Cheaper — no monitoring fee | Slightly more expensive due to per-object monitoring fee |
| Cost when access patterns are unpredictable | Risk of moving data to a cold tier right before it's needed again (retrieval fee) | Automatically keeps frequently-accessed objects in a warmer tier |
| Best fit | Data with a known, predictable cooling pattern — which is exactly what clickstream data is: hot for days, then essentially never touched | Data where access patterns are genuinely unknown or highly variable |

**Decision for this project**: manual rules on `raw/`, since clickstream
data has a well-understood cooling curve (queried heavily right after
ingestion while validating the pipeline, then not touched again once
curated Parquet exists). The `test-intelligent-tiering/` prefix exists
purely to observe Intelligent-Tiering's behavior side-by-side for this
write-up, not because it's the better choice for this workload.

## Applying the policy

```bash
aws s3api put-bucket-lifecycle-configuration \
  --bucket clickstream-lake-mtusharaug \
  --lifecycle-configuration file://lifecycle-policy.json
```

Verify:
```bash
aws s3api get-bucket-lifecycle-configuration --bucket clickstream-lake-mtusharaug
```

## Definition of done

- [ ] Lifecycle rules active, confirmed via `get-bucket-lifecycle-configuration`
- [ ] Rules visible in S3 console under bucket → Management → Lifecycle rules
- [ ] Curated-zone Standard-only decision documented (this file)
- [ ] Small-object IA overhead caveat documented (this file) — this is the
      single most interview-relevant detail in this phase