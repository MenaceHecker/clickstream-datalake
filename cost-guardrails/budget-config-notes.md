# Phase 0 — Cost Guardrails

## Intended configuration

| Budget | Type | Amount | Alerts |
|---|---|---|---|
| `clickstream-soft-limit` | Cost, monthly | $150 (75% of the $200 pool) | Email at 80% and 100% actual spend |
| `clickstream-hard-stop` | Cost, monthly | $180 | Email at 100% actual spend |

Both filtered to `Project: clickstream-lake` (see tagging convention below), so
they track only this project's spend, not the whole account.

The exact same two budgets are also defined as code in
`infra-cdk/clickstream_stack/stack.py` (`_add_budget`, `SoftLimitBudget` /
`HardStopBudget`) — the thresholds above are not just a plan, they're the
literal values encoded there.

## Tagging convention

Every resource created for this project is tagged `Project: clickstream-lake`.
This is what lets Cost Explorer and the budgets above filter to just this
project instead of the whole account. Verified live on the S3 bucket, the
Glue crawler/ETL IAM roles, and the Glue ETL job itself.

## Status: live in AWS (2026-09-25)

Both budgets now exist, created directly with a temporary admin IAM
identity (`clickstream-dev` itself only has `budgets:View*` — read-only, by
design; see `iam/iam-notes.md` setup step 5). Confirmed via
`aws budgets describe-budgets`:

| Budget | Amount | Status |
|---|---|---|
| `clickstream-soft-limit` | $150 | HEALTHY |
| `clickstream-hard-stop` | $180 | HEALTHY |

The CDK stack's own `_add_budget` calls also created a second, parallel
pair (`clickstream-soft-limit-cdk`, `clickstream-hard-stop-cdk`) as part of
proving Phase 9's IaC end-to-end — see `infra-cdk/cdk-setup-notes.md` for
that deploy. Four budgets now exist in total; worth deciding whether to
keep both pairs or tear down one set once you're done treating this as a
side-by-side proof.

This closed the one real gap this project had: the least-privilege IAM
design correctly denied `clickstream-dev` from creating budgets directly
(confirmed live with a real `AccessDeniedException` before this was fixed),
exactly as documented — it just needed the manual admin step actually
carried out, which it now has been.

## Cost Explorer

Enabled, with a view bookmarked and filtered by the `Project: clickstream-lake`
tag. See `docs/cost-report.md` for the pulled numbers.
