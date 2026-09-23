# Cost Report — Clickstream Data Lake Project

Final Cost Explorer summary, filtered by tag `Project: clickstream-lake`,
against the $200 AWS Free Tier credit pool this project was scoped
against from Phase 0 onward.

## How to generate this

1. AWS Console → Cost Explorer → use the bookmarked view from Phase 0
   (filtered by `Project: clickstream-lake` tag, grouped by service)
2. Set the date range to cover this project's actual build window
3. Export the chart/table (Cost Explorer supports CSV export)
4. Fill in the table below with real numbers

## Spend by service

| Service | Cost | Notes |
|---|---|---|
| S3 | `$___` | Storage + requests across raw/curated/athena-results |
| Glue | `$___` | Crawlers (10-min billing floor per run) + ETL job (1-min floor) |
| Athena | `$___` | Per-TB-scanned, business queries + cost comparison queries |
| Kinesis | `$___` | On-demand stream, billed while producer was running |
| Firehose | `$___` | Per-GB ingested |
| Lambda | `$___` | Only if Path A was ever tested alongside Path B |
| CloudFormation / CDK | `$0` | No direct charge — costs come from the resources it provisions, already counted above |
| **Total** | `$___` | |

## Against the $200 pool

- Total spend: `$___`
- Percentage of pool used: `___%`
- Free Tier "set up a cost budget" onboarding credit applied: yes (Phase 0)

## What actually cost money vs. what was negligible

Most of this project's real-world cost lessons aren't about the dollar
total (which should be small) — they're about understanding *why* each
number is what it is:

- **Glue crawlers have a 10-minute minimum billing increment per run**,
  regardless of how fast they actually finish. Running them repeatably
  "just to check" adds up faster than the actual crawl time would
  suggest.
- **S3 Standard-IA has a 128 KB minimum billable object size** — this
  project's raw JSON files are smaller than that, meaning the Phase 4
  lifecycle rules demonstrate the tiering pattern correctly without
  necessarily saving money at this data volume. See
  `lifecycle/lifecycle-notes.md`.
- **Kinesis (on-demand) has an always-on cost component** that Lambda
  doesn't — the one piece of this pipeline that isn't "free while idle"
  the way everything else here is. Worth remembering to tear down
  between working sessions if cost matters.
- **Athena's per-TB pricing means small datasets round to fractions of a
  cent regardless of JSON vs. Parquet** — the percentage reduction from
  Phase 7 is the meaningful number here, not the absolute dollar
  difference, at this project's scale.

## Time span

- Project start: `___`
- Project end (this report): `___`
- Note: this account has a 6-month clock regardless of remaining credit
  balance (see the original plan's risk register) — this project stayed
  within that window: `yes / no`