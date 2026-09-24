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

## Status: not yet created in AWS — documented status, not silently assumed

Unlike every other phase in this repo, this one has an honest gap: **the two
budgets above do not exist in the AWS account yet.** This was caught while
pulling real numbers for Phase 10, not assumed away.

Why: `iam/clickstream-dev-policy.json` intentionally grants the
`clickstream-dev` IAM user (the one this whole project's CLI work runs as)
only `budgets:View*` — read-only. Creating a budget requires
`budgets:ModifyBudget`, which the project's own least-privilege design
deliberately withholds from this user (see `iam/iam-notes.md`, setup step 5:
"Budgets/Cost Explorer setup itself still needs to be done as root or an
admin-level user once"). Confirmed live:

```
$ aws budgets create-budget --account-id <redacted> --budget file://budget-soft.json ...
AccessDeniedException: User: .../clickstream-dev is not authorized to
perform: budgets:ModifyBudget
```

This is the IAM design working as intended, not a bug — it's just a manual
step that was never actually carried out. **Action item:** log in as the
account root user (or an admin identity) and either click through the two
budgets above in the AWS Budgets console, or run `cdk deploy` once an admin
identity is available to it (the CDK stack's `_add_budget` calls will create
them, since the CDK deploy role has broader permissions than `clickstream-dev`
does directly).

## Cost Explorer

Enabled, with a view bookmarked and filtered by the `Project: clickstream-lake`
tag. See `docs/cost-report.md` for the pulled numbers.
