# Postmortem: Raw-Zone Glue Crawler Silently Failing on Every Run

**Status:** Resolved
**Severity:** Low impact (caught during pre-production validation, before any
downstream query or dashboard depended on the affected data), but a real
bug that would have quietly produced incomplete results if it had gone
unnoticed longer.
**Date detected / resolved:** 2026-09-24
**Follow-up (monitoring) shipped:** 2026-09-29

## Summary

`clickstream-raw-crawler`, the Glue Crawler responsible for keeping the
`clickstream_raw.raw` Data Catalog table's partition list in sync with what's
actually in the S3 raw zone, was failing on every run with an
`AccessDeniedException`. It had been failing since at least 2026-09-19 (the
most recent failed run on record; AWS Glue's API only exposes the latest
crawl result, so an earlier true start time isn't recoverable). Nothing in
the account surfaced this failure to anyone. It was found by chance, while
manually re-verifying the pipeline end-to-end for Phase 10 documentation,
not by any monitoring, alert, or test.

## Impact

No downstream damage occurred in this project's timeline: Phase 7's Athena
queries and Phase 8's dashboard were both generated *after* this was found
and fixed, using a freshly-succeeded crawl. But the counterfactual is the
real lesson here. Had this gone uncaught:

- New S3 partitions written to the raw zone after 2026-09-19 would never
  have been added to the Glue Data Catalog.
- Every Athena query against `clickstream_raw.raw` after that point would
  have run against an incomplete partition set, silently. Athena doesn't
  error when a table has fewer partitions than the underlying S3 data;
  it just returns correct-looking results computed from a subset of the
  actual data.
- The Phase 7 cost-comparison numbers and the Phase 8 dashboard's funnel
  and revenue figures would all have been quietly wrong, with nothing in
  the output itself indicating the data was incomplete.

This is the specific failure mode that makes "the crawler didn't error, it
just stopped updating the catalog" worse than a loud failure. A loud
failure blocks you. A silent one hands you wrong numbers with full
confidence.

## Root Cause

`iam/glue-crawler-role-policy.json`, the IAM policy for the role Glue
Crawlers assume (`clickstream-glue-crawler-role`), granted:

```
glue:GetPartitions
glue:BatchUpdatePartition
glue:BatchCreatePartition
```

but not `glue:BatchGetPartition`, which the crawler actually calls internally
to look up existing partitions before deciding what to create or update.
Without it, every crawl run failed immediately with:

```
Service Principal: glue.amazonaws.com is not authorized to perform:
glue:BatchGetPartition on resource: arn:aws:glue:us-east-1:<account>:catalog
because no identity-based policy allows the glue:BatchGetPartition action
(Database name: clickstream_raw, Table name: raw)
```

The same gap existed independently in `infra-cdk/clickstream_stack/stack.py`'s
CDK-defined equivalent of this policy (`GlueCrawlerRole`). The CDK stack was
written to mirror the hand-applied IAM policy's actions, so it inherited the
same omission. One root cause, two places it needed fixing.

## Detection

Not automated. Found by running `aws glue get-crawler --name
clickstream-raw-crawler --query 'Crawler.LastCrawl'` directly, while manually
re-verifying every phase of the pipeline against the live AWS account for
Phase 10's documentation, specifically because the plan called for pulling
*real* numbers rather than trusting the repo's own "done" checklist. Nothing
about this failure was visible from the Glue Data Catalog itself: the
`clickstream_raw.raw` table still existed and was still queryable (from an
earlier successful crawl), giving no outward sign that it had stopped
updating.

## Resolution

1. Added `glue:BatchGetPartition` to the crawler role's inline policy, both
   live (`aws iam put-role-policy`) and in the source-of-truth
   `iam/glue-crawler-role-policy.json`.
2. Applied the same fix to the CDK stack's equivalent IAM statement in
   `stack.py`, so a future `cdk deploy` doesn't reintroduce the same bug.
3. Re-ran the crawler. It succeeded on the first attempt after the fix.

## Follow-up Actions

| Action | Status |
|---|---|
| Fix the immediate IAM gap (live + IaC) | Done, 2026-09-24 |
| Re-verify the full pipeline against real data (Phases 5-8) | Done, 2026-09-24 |
| Add monitoring so a future failure doesn't require someone to go looking | Done, 2026-09-29. SNS topic plus EventBridge rules on `Glue Crawler State Change` / `Glue Job State Change` events in `Failed`/`FAILED` state, verified live with a direct SNS publish (see `README.md`'s "Verified live" entry and `cost-guardrails/budget-config-notes.md`) |
| Add a CI check that would catch this class of bug pre-deploy | Not done, and can't fully be: this only surfaces against real AWS state (an actual crawl attempt), which `cdk synth` deliberately never touches. `ruff`/`pytest`/`cdk synth` (added in CI, see `.github/workflows/ci.yml`) catch code-level bugs, not IAM-sufficiency bugs. Noted as a real limit of static validation, not an oversight. |

## Lessons Learned

- **A resource existing is not the same as a process still succeeding.**
  The Glue table's continued presence and queryability masked the fact
  that its crawler had stopped working days earlier.
- **Least-privilege IAM policies get the action list wrong before they get
  it right.** This is the second such gap found in this project (the
  first: a Phase 6 `AccessDeniedException` on `glue:StartJobRun` from an
  overly clever tag `Condition`, documented in `iam/iam-notes.md`). Neither
  was caught by writing the policy carefully. Both were caught by actually
  running the thing the policy was meant to authorize.
- **Monitoring should be added *because* of a real failure, not in
  anticipation of a hypothetical one.** The SNS/EventBridge alerting this
  project now has exists specifically because this incident happened, not
  because "you should always have alerting." It's scoped to the two
  failure modes actually observed (crawler and job failures), not a
  speculative broader monitoring buildout.
