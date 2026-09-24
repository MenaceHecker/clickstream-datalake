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

Pulled via `aws ce get-cost-and-usage` grouped by `SERVICE`, 2026-09-01 to
2026-09-24, filtered where possible by the `Project: clickstream-lake` tag:

| Service | Cost | Notes |
|---|---|---|
| S3 | $0.000000001 | Storage + requests across raw/curated/athena-results — 196 raw JSON objects (~2.4 MB) + 196 curated Parquet objects (~2.0 MB) |
| Glue | $0 reported so far | Crawlers (10-min billing floor per run) + ETL job (1-min floor); the ETL job run and both crawler re-runs happened 2026-09-24, same day as this pull — Cost Explorer has up to ~24-48h reporting lag, so today's usage isn't reflected in this number yet |
| Athena | $0 reported so far | Same lag caveat — the Phase 7 cost-comparison queries scanned 4.15 MB + 118.3 KB combined, well under a cent either way (see `athena/queries/cost_comparison_notes.md`) |
| Kinesis | $0 | Not currently running |
| Firehose | $0 | Not currently running |
| Lambda | $0 | Path A (scheduled Lambda) was not used — Path B (Kinesis+Firehose) was chosen instead |
| CloudFormation / CDK | $0 | No direct charge — costs come from the resources it provisions, already counted above |
| **Total (as of this pull)** | **~$0.00** | Effectively free-tier scale; re-pull after 24-48h to see today's Glue/Athena usage reflected (still expected to be fractions of a cent at this data volume) |

## Against the $200 pool

- Total spend (as of 2026-09-24): effectively $0.00 — within Cost Explorer's
  measurement precision and reporting lag
- Percentage of pool used: ~0%
- Free Tier "set up a cost budget" onboarding credit applied: **no — see the
  Budgets gap below**

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

## Known gap: AWS Budgets never actually created

Cost Explorer is enabled and this report's numbers came from it directly,
but the two Phase 0 budgets (`clickstream-soft-limit` at $150,
`clickstream-hard-stop` at $180) were never actually created in AWS — only
documented and encoded in the CDK stack. The `clickstream-dev` IAM user this
project's CLI work runs as only has read (`budgets:View*`) access by design
(see `iam/iam-notes.md`); creating a budget needs root/admin credentials,
which is a manual step that was skipped. See
`cost-guardrails/budget-config-notes.md` for the full account and the
action item to close it. Worth being upfront about this rather than
checking a box that wasn't actually true.

## Time span

- Project start: 2026-09-08 (first commit)
- Project end (this report): 2026-09-24
- Note: this account has a 6-month clock regardless of remaining credit
  balance (see the original plan's risk register) — this project stayed
  within that window: yes (well under 1 month elapsed)