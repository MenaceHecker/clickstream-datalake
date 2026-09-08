# E-Commerce Clickstream Data Lake & Cost-Optimized Analytics Pipeline

> Status:  In progress — building phase by phase. See `docs/` for architecture and cost details as they land.

A serverless AWS data lake that ingests simulated e-commerce clickstream events, stores them
in tiered S3 zones, catalogs and transforms them with Glue, and serves analytics through
Athena (and QuickSight or a notebook fallback).

## Architecture

```
[Event Generator (Python)]
        |
        v
[S3 Raw Zone] --(Glue Crawler)--> [Glue Data Catalog]
        |                                 |
        v                                 v
[Lifecycle Policy:                 [Glue ETL Job]
 Standard -> IA -> Glacier]               |
                                           v
                              [S3 Curated Zone (Parquet,
                               partitioned by event date)]
                                           |
                                           v
                                   [Amazon Athena]
                                           |
                                           v
                                 [Amazon QuickSight]
```

Cross-cutting: AWS Budgets + Cost Explorer (tagged `Project: clickstream-lake`) monitor spend
across every component.

## Repo structure

Each top-level folder maps to one build phase. See individual `*-notes.md` files inside each
folder for phase-specific decisions and rationale.

## Build log

- [x] Phase 0 — Cost guardrails & repo scaffold
- [ ] Phase 1 — Clickstream event generator
- [ ] Phase 2 — Raw zone ingestion to S3
- [ ] Phase 3 — Automated/streaming ingestion
- [ ] Phase 4 — Storage tiering & lifecycle policies
- [ ] Phase 5 — Glue Crawler & Data Catalog
- [ ] Phase 6 — Glue ETL: JSON → partitioned Parquet
- [ ] Phase 7 — Athena analytics & cost comparison
- [ ] Phase 8 — QuickSight dashboard
- [ ] Phase 9 — Infrastructure as Code (CDK rebuild)
- [ ] Phase 10 — Documentation & resume packaging

## Key decisions & trade-offs

_(Filled in as phases land — this section is the interview-relevant part.)_

## Real numbers

_(Filled in during Phase 7/10 — bytes scanned before/after Parquet, storage cost, events processed.)_

## How to run

_(Filled in during Phase 9, once the CDK stack exists.)_