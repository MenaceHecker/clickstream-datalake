# Phase 0: Cost Guardrails

## Intended configuration

| Budget | Type | Amount | Alerts |
|---|---|---|---|
| `clickstream-soft-limit` | Cost, monthly | $150 (75% of the $200 pool) | Email at 80% and 100% actual spend |
| `clickstream-hard-stop` | Cost, monthly | $180 | Email at 100% actual spend |

Both filtered to `Project: clickstream-lake` (see tagging convention below), so
they track only this project's spend, not the whole account.

The exact same two budgets are also defined as code in
`infra-cdk/clickstream_stack/stack.py` (`_add_budget`, `SoftLimitBudget` /
`HardStopBudget`). The thresholds above aren't just a plan; they're the
literal values encoded there.

## Tagging convention

Every resource created for this project is tagged `Project: clickstream-lake`.
This is what lets Cost Explorer and the budgets above filter to just this
project instead of the whole account. Verified live on the S3 bucket, the
Glue crawler/ETL IAM roles, and the Glue ETL job itself.

## Status: live in AWS (2026-09-25)

Both budgets now exist, created directly with a temporary admin IAM
identity (`clickstream-dev` itself only has `budgets:View*`, read-only, by
design; see `iam/iam-notes.md` setup step 5). Confirmed via
`aws budgets describe-budgets`:

| Budget | Amount | Status |
|---|---|---|
| `clickstream-soft-limit` | $150 | HEALTHY |
| `clickstream-hard-stop` | $180 | HEALTHY |

The CDK stack's own `_add_budget` calls also created a second, parallel
pair (`clickstream-soft-limit-cdk`, `clickstream-hard-stop-cdk`) as part of
proving Phase 9's IaC end-to-end. See `infra-cdk/cdk-setup-notes.md`. That
parallel pipeline (and its budgets) was torn down the same day once the
proof was captured, so only the two budgets above remain.

This closed the one real gap this project had. The least-privilege IAM
design correctly denied `clickstream-dev` from creating budgets directly
(confirmed live with a real `AccessDeniedException` before this was fixed),
exactly as documented. It just needed the manual admin step actually
carried out, which it now has been.

## Two more real gotchas, found fixing a wrong subscriber email (2026-09-29)

While setting up SNS-based failure alerting (see the README's "Verified
live" entry), all three budget notification subscribers turned out to be
subscribed to the wrong email, a mistake on the assistant's part, using
an ambient default instead of this project's actual contact address. Two
things surfaced while fixing it:

1. **AWS Budgets deletes a notification entirely once its last subscriber
   is removed.** Running `delete-subscriber` on the only subscriber for
   each notification silently deleted all three notifications, not just
   the subscriber. `describe-notifications-for-budget` came back empty.
   The fix isn't "update the subscriber," it's `create-notification` with
   the subscriber included from the start, recreating the notification
   object itself.
2. **SNS email subscriptions require explicit confirmation before
   delivery works**, but budget notification subscribers do not. A
   budget alert would have gone to the wrong inbox immediately if a
   threshold had ever actually been crossed, with no confirmation step to
   catch the mistake first. The stale, unconfirmed SNS subscription to the
   wrong address was left to expire on its own (3-day default) rather than
   force-removed, since there's no clean API to cancel a pending
   confirmation before that.

## Cost Explorer

Enabled, with a view bookmarked and filtered by the `Project: clickstream-lake`
tag. See `docs/cost-report.md` for the pulled numbers.
