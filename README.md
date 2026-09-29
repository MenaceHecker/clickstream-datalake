# E-Commerce Clickstream Data Lake & Cost-Optimized Analytics Pipeline

[![CI](https://github.com/MenaceHecker/clickstream-datalake/actions/workflows/ci.yml/badge.svg)](https://github.com/MenaceHecker/clickstream-datalake/actions/workflows/ci.yml)

A serverless AWS data lake that ingests simulated e-commerce clickstream events
(batch + real-time streaming), stores them in tiered S3 zones, catalogs and
transforms them with Glue, serves analytics through Athena, visualizes them via
a boto3-driven dashboard notebook, and is fully reproducible as Infrastructure
as Code via AWS CDK.

Built end-to-end, one phase at a time, against a fixed $200 AWS Free Tier
credit pool. Cost-awareness isn't an afterthought here; it's load-bearing
throughout the design.

## Architecture

```
[Batch: Event Generator]        [Streaming: Kinesis Producer]
         |                                |
         v                                v
   upload_to_s3.py               Kinesis Data Stream
         |                                |
         |                          Kinesis Firehose
         |                                |
         v                                v
              [S3 Raw Zone] --(Glue Crawler)--> [Glue Data Catalog]
                    |                                    |
                    v                                    v
         [Lifecycle Policy:                       [Glue ETL Job]
          Standard -> IA(30d) -> Glacier IR(90d)]        |
                                                          v
                                          [S3 Curated Zone (Parquet,
                                           partitioned by event date)]
                                                          |
                                                          v
                                                   [Amazon Athena]
                                                          |
                                                          v
                                        [Dashboard Notebook: boto3 + matplotlib]
```

Cross-cutting: AWS Budgets and Cost Explorer (tagged `Project: clickstream-lake`)
monitor spend across every component. The entire pipeline above is also
provisioned as one AWS CDK stack (`infra-cdk/`), independently reproducible
with `cdk deploy` / `cdk destroy`.

## Repo structure

Each top-level folder maps to one build phase. See the `*-notes.md` file in
each for phase-specific setup steps and decisions:

- `cost-guardrails/`: Phase 0, Budgets and tagging convention
- `generator/`: Phase 1, funnel-shaped event simulation
- `ingestion/`: Phase 2/3, batch S3 upload plus Kinesis/Firehose streaming
- `lifecycle/`: Phase 4, S3 tiering policy
- `glue/`: Phase 5/6, crawlers, Data Catalog, ETL job
- `athena/queries/`: Phase 7, business queries and cost comparison
- `quicksight/`: Phase 8, dashboard notebook (QuickSight fallback)
- `infra-cdk/`: Phase 9, the whole pipeline as CDK
- `iam/`: least-privilege policies for every service role used above
- `docs/`: dashboard screenshots, final cost report, incident postmortem
- `tests/`: pytest suite for the generator and S3 upload logic
- `.github/workflows/`: CI (lint, generator smoke test, pytest, `cdk synth`)

## Key decisions & trade-offs

This section is deliberately the longest part of this README. It's the part
that actually gets discussed in an interview, not the architecture diagram.

**Kinesis + Firehose over scheduled Lambda (Phase 3).** The plan offered a
simpler Lambda/EventBridge batch path as the default. Firehose is the
stronger streaming-ingestion signal, at the cost of an always-on component
(unlike Lambda, on-demand Kinesis isn't literally free to leave running). See
`ingestion/firehose-setup-notes.md` for the full write-up, including a
specific caveat: Firehose partitions by *delivery time*, not the event's own
timestamp like the batch uploader does. That's a deliberate, documented
approximation, not an oversight.

**Update, discovered during Phase 9 validation: Phase 3 was never actually
live.** Every Kinesis and Firehose API call against this AWS account,
including a plain read-only `kinesis:ListStreams`, fails with
`SubscriptionRequiredException`. This is an account-level restriction, not
an IAM permissions gap (confirmed with both the scoped `clickstream-dev`
user and a temporary admin identity). The code, IAM roles, and CDK
definitions for Path B are all correct and were `cdk synth`-verified, but
the stream itself was never actually creatable in this account. Rather
than quietly drop the Kinesis/Firehose resources from the CDK stack, they
were made conditional (`enable_streaming`, default `true`), so the intended
architecture stays the default and this account's specific restriction is
an opt-out, not a redesign. Flagged here instead of leaving the build log
checked for something that was never verified live, the same standard
this README already holds every other phase to.

**Manual S3 lifecycle rules over Intelligent-Tiering (Phase 4).**
Clickstream data has a predictable cooling curve (hot immediately after
ingestion, cold forever after), which favors manual rules over
Intelligent-Tiering's per-object monitoring fee. See
`lifecycle/lifecycle-notes.md`, which also documents a real caveat: S3
Standard-IA has a 128 KB minimum billable object size, and this project's
raw JSON files are smaller than that. The tiering pattern is correctly
implemented, but the dollar savings only materialize at a production data
volume this simulation intentionally doesn't reach. Reporting that
honestly is worth more than an inflated number.

**IAM: least-privilege custom policy over managed FullAccess policies.**
Every service role in this project (`iam/*-role-policy.json`) is scoped by
resource ARN or name prefix (`clickstream-*`) rather than using AWS-managed
`*FullAccess` policies. This cost real debugging time: a `Condition` tying
Glue actions to a resource tag turned out to not reliably enforce, causing a
real `AccessDeniedException` on `glue:StartJobRun` during Phase 6. The fix
(documented in `iam/iam-notes.md`, not silently patched) was to drop the tag
condition and rely on the naming convention instead, consistent with every
other statement in the policy.

**Notebook dashboard over QuickSight (Phase 8).** QuickSight bills on a
separate pricing/trial structure outside the $200 credit pool this whole
project is scoped against. A boto3 + matplotlib script produces the same
three visuals (funnel, revenue trend, device/country breakdown) while keeping
100% of spend inside one tracked pool. See `quicksight/dashboard-notes.md`.

**One CDK stack, not several (Phase 9).** Storage, compute, ingestion, and
budgets all live in a single `ClickstreamStack` rather than nested stacks per
service. At this resource count, one stack keeps `cdk deploy`/`cdk destroy`
genuinely one-command, which is the actual Phase 9 goal, without the
cross-stack reference overhead a multi-stack split would add for no real
benefit here. A production version serving real traffic would likely split
these for independent deploy cadences. Noted here as a scaling path not
taken, deliberately.

**A deliberate reversal, documented rather than hidden.** Phase 0 gave the
`clickstream-dev` IAM user *view-only* access to Budgets, on the theory that
only an admin should create spend controls. Phase 9's CDK stack defines
budgets as code, which required loosening that to create/modify access so
`cdk deploy` could be a true one-command operation. Both the original
reasoning and the reason it changed are recorded in `iam/iam-notes.md`, the
kind of policy-review conversation that happens on a real team, made
visible here instead of just quietly resolved.

**A second real IAM gap, caught while pulling Phase 10's real numbers.**
The raw crawler's role (`iam/glue-crawler-role-policy.json`) was missing
`glue:BatchGetPartition`. It had `GetPartitions` and `BatchUpdatePartition`
but not the batch-get variant the crawler actually calls, causing every
crawler run to fail with `AccessDeniedException` until this was found and
fixed (in both the policy file and the equivalent CDK statement) while
verifying the pipeline end-to-end for this README. Left in as a second
documented example, alongside the Phase 6 tag-condition issue above, that
least-privilege IAM policies get refined by hitting real `AccessDenied`
errors, not by getting every action right on the first pass.

**The crawler failure led to monitoring, not just a fix.** Finding the
`BatchGetPartition` gap above only happened because someone went looking.
Nothing in the account would have surfaced a silently-failing crawler
otherwise. `stack.py` now defines an SNS topic plus two EventBridge rules
(`Glue Crawler State Change` / `Glue Job State Change`, filtered to
`Failed`/`FAILED`) so the next failure sends an email instead of waiting
to be found. This is deliberately account-wide rather than scoped to this
stack's own `-cdk`-suffixed resources: filtering by name would mean the
alerting only protects whichever pipeline happens to be CDK-provisioned at
a given moment, not whichever one is actually processing real data, which
for most of this project has been the manually-built one.

**Verified live, not just deployed (2026-09-29).** Created the same SNS
topic and EventBridge rules directly against the real account (not via a
full `cdk deploy`, to avoid recreating a parallel pipeline just to test an
alarm) and confirmed delivery with a direct `sns publish`. The email
arrived. The EventBridge rule to SNS trigger itself can't be end-to-end
tested with a synthetic event: `events:PutEvents` refuses any event whose
`Source` starts with `aws.` (for example `aws.glue`) regardless of caller
identity, including full admin. That's a hard, identity-independent
guardrail against spoofing real AWS service events, not a permissions gap.
So the rule's correctness rests on matching AWS's documented event schema
exactly (`"state": "Failed"` for crawlers, `"state": "FAILED"` for jobs,
note the casing difference, confirmed against both this stack's
`EventPattern` and AWS's own event examples) rather than a live trigger
test. A fully genuine test would mean deliberately breaking the crawler's
IAM permissions again to force a real failure. That wasn't done here,
since one real, accidental failure already proved the underlying mechanism
this session.

**Added CI after finding real bugs by hand, not before.** This project
initially had zero automation. Every gap in it (the crawler's missing
`glue:BatchGetPartition`, the CDK stack's hardcoded Glue database names
colliding with a real `AlreadyExists` on deploy) was found by manually
running commands against a live AWS account during Phase 10 validation.
`.github/workflows/ci.yml` now runs on every push/PR: `ruff` (a
correctness-focused subset, `E`/`F`, with line-length rules deliberately
left off since several `argparse --help` strings are long on purpose, not
sloppy), a real smoke test of the event generator (runs it, then validates
the output JSONL against the schema), a `pytest` suite (`tests/`, with
funnel-shape and schema-evolution regression tests for the generator, plus
`moto`-mocked S3 tests for the Hive-style partitioning logic in
`upload_to_s3.py`), and `cdk synth --strict` in both `enable_streaming`
states. Worth being precise about what this actually buys: none of it
would have caught either real bug from Phase 10 validation. The Glue
database collision and the missing IAM action both only surface against
real AWS state, which none of these checks touch. What it does catch is
the cheaper, more common failure: a broken funnel ratio, a partition-path
regression, a typo that breaks the CDK template outright, or a Python
import error, before any of them reach a real `cdk deploy` or a bad
dashboard and burn a debugging cycle finding out.

**Schema evolution handled by design, not by accident.** The event generator
(Phase 1) deliberately introduces a `discount_code` field partway through
data generation. This exercises real behavior at two later layers: Glue's
crawler grouping policy (`CombineCompatibleSchemas`) keeps it one evolving
table instead of splitting into two, and Spark's JSON reader in the ETL job
naturally unions schemas across files with no special-casing needed.
Verified locally with a hand-built test dataset before ever running against
real Glue infrastructure. See `glue/etl-setup-notes.md`.

## Real numbers

Pulled directly from the live AWS account on 2026-09-24 (Athena
`GetQueryExecution` stats, Glue `GetJobRun`, Cost Explorer). See the phase
notes referenced for the exact commands used.

| Metric | Value | Source |
|---|---|---|
| Simulated events processed | 11,443 | `SELECT COUNT(*) FROM clickstream_curated.curated` |
| Athena data scanned, raw JSON | 4.15 MB (4,350,579 bytes) | `athena/queries/cost_comparison_notes.md` |
| Athena data scanned, curated Parquet | 118.3 KB (121,131 bytes) | same |
| Query cost reduction (JSON to Parquet) | 97.22% | same |
| Glue ETL job duration | 123 sec (246 DPU-seconds, 2x G.1X workers) | `aws glue get-job-run`, Phase 6 |
| Total AWS spend (Cost Explorer, tagged) | ~$0.00 (effectively free-tier scale; today's Glue/Athena usage not yet reflected, CE has ~24-48h lag) | `docs/cost-report.md` |
| Spend against $200 pool | ~0% | same |

## How to run

Full pipeline, from a clean AWS account:

```bash
# 1. Bootstrap CDK (one-time, needs broader permissions, see infra-cdk/cdk-setup-notes.md)
cdk bootstrap aws://<account-id>/us-east-1

# 2. Deploy the entire pipeline
cd infra-cdk
pip install -r requirements.txt
cdk deploy -c bucket_suffix=<your-suffix> -c alert_email=<your-email>

# 3. Generate and upload sample data
cd ../generator
pip install -r requirements.txt
python event_generator.py --events 5000
cd ../ingestion
python upload_to_s3.py --bucket clickstream-lake-<your-suffix> --input-dir ../generator/output

# 4. Run the crawlers and ETL job (see glue/*.md for exact commands)
# 5. Query in Athena (see athena/queries/)
# 6. Generate the dashboard
cd ../quicksight
pip install -r requirements.txt
python dashboard_notebook.py
```

Full teardown:
```bash
cd infra-cdk
cdk destroy -c bucket_suffix=<your-suffix> -c alert_email=<your-email>
# Note: the S3 bucket is retained by design. Empty and delete it manually if needed.
```

## Dashboard

_(Screenshots from `quicksight/dashboard_notebook.py` output, see `docs/`)_

- `docs/dashboard-funnel.png`: conversion funnel
- `docs/dashboard-revenue-trend.png`: daily revenue trend
- `docs/dashboard-device-country.png`: revenue by country/device

## Build log

- [x] Phase 0, Cost guardrails & repo scaffold. Both budgets (`clickstream-soft-limit` $150, `clickstream-hard-stop` $180) are live in AWS as of 2026-09-25. See `cost-guardrails/budget-config-notes.md`.
- [x] Phase 1, Clickstream event generator
- [x] Phase 2, Raw zone ingestion to S3
- [ ] Phase 3, Automated/streaming ingestion (Kinesis + Firehose). Code and IAM roles are written, but never actually deployed: this AWS account rejects **every** Kinesis/Firehose API call, including plain read-only `ListStreams`, with `SubscriptionRequiredException`. This is an account-level restriction unrelated to IAM permissions, discovered while validating Phase 9. Worth a closer look; see the note in `infra-cdk/cdk-setup-notes.md`.
- [x] Phase 4, Storage tiering & lifecycle policies
- [x] Phase 5, Glue Crawler & Data Catalog
- [x] Phase 6, Glue ETL: JSON to partitioned Parquet
- [x] Phase 7, Athena analytics & cost comparison
- [x] Phase 8, Dashboard (notebook fallback)
- [x] Phase 9, Infrastructure as Code. `cdk deploy` completed successfully on 2026-09-25 (`-c enable_streaming=false`, see below): a real, working parallel pipeline stood up entirely from the CDK stack, including budgets created by CDK itself.
- [x] Phase 10, Documentation & resume packaging

## Cost report

See `docs/cost-report.md` for the final Cost Explorer breakdown against the
$200 credit pool.

## Incident postmortem

This project had one real incident: the raw-zone Glue crawler silently
failed on every run for at least 5 days due to a missing IAM permission,
with no monitoring in place to surface it. See
`docs/postmortem-glue-crawler-failure.md` for the full writeup: root
cause, what the impact would have been if it had gone uncaught longer, and
the monitoring it led to (see the "Verified live" entry in Key decisions
above).
