# IAM — Custom Least-Privilege Policy for `clickstream-dev`

## Why a custom policy instead of managed FullAccess policies

AWS-managed policies like `AmazonS3FullAccess` or `AWSGlueConsoleFullAccess` would work and
be faster to attach, but they grant access to *every* bucket/job/table in the account, not
just this project's. Scoping a custom policy to this project's resources — by bucket name,
name prefix (`clickstream-*`), and tag (`Project: clickstream-lake`) — is a small amount of
extra upfront work that pays off twice: it's a real safety boundary in a multi-project
account, and it's a concrete "how do you think about least privilege" answer for interviews
that a checkbox managed policy doesn't give you.

## How each statement is scoped

| Statement | Scope | Why |
|---|---|---|
| `S3ProjectBucketOnly` | This project's bucket ARN only | Object/lifecycle/encryption ops confined to `clickstream-lake-<id>` |
| `S3CreateAndListOwnBuckets` | Account-wide (`*`) | `CreateBucket` and `ListAllMyBuckets` don't support resource-level scoping in IAM |
| `GlueCatalogAndJobs` | `*` + `Project` tag condition | See caveat below — tag condition doesn't reliably apply to Glue |
| `GlueCatalogDiscovery` | `*`, read-only | Fallback so catalog/crawler/job listing works regardless of the caveat above |
| `AthenaQueryExecution` | `*` | Athena query actions don't support per-database resource ARNs |
| `LambdaForScheduledIngestion` | `function:clickstream-*` | Name-prefix scoped (Phase 3) |
| `EventBridgeSchedulingOnly` | `rule/clickstream-*` | Name-prefix scoped (Phase 3) |
| `CloudWatchLogsForDebugging` | `/aws/lambda/clickstream-*`, `/aws-glue/*` | Just enough to read/write logs for this project's functions and jobs |
| `BudgetsAndCostExplorerReadOnly` | `*`, read-only | Root/admin creates the actual budgets (Phase 0); this user only views them |
| `IAMReadOnlyForCDK` | `*`, read-only | CDK synth needs to inspect existing roles/policies |
| `IAMRoleManagementForProjectResourcesOnly` | `role/clickstream-*` | CDK and Lambda both need to create/attach execution roles, scoped by name prefix |
| `CloudFormationForCDKDeploy` | `stack/CDKToolkit/*`, `stack/clickstream-*/*` | CDK deploys through CloudFormation under the hood (Phase 9) |

## Known caveat: Glue's tag condition

`GlueCatalogAndJobs` includes a `Condition` requiring `aws:ResourceTag/Project =
clickstream-lake`. In practice, several Glue actions (`CreateDatabase`, `CreateCrawler`,
`CreateJob`) don't consistently enforce resource-tag conditions at the API level — this is a
known inconsistency in Glue's IAM integration, not a mistake in this policy. The
`GlueCatalogDiscovery` statement exists specifically so read/list operations keep working
even if the tag condition ends up not applying as strictly as written. If Glue actions get
denied unexpectedly while working through Phases 5–6, this condition is the first thing to
loosen — drop the `Condition` block entirely and rely on naming convention instead (all Glue
resources named with a `clickstream_` prefix) rather than debugging tag propagation.

## Setup steps

1. IAM console → Users → create `clickstream-dev`.
2. Attach this policy as an inline policy (or create it as a standalone customer-managed
   policy and attach that — cleaner if you want to version/reuse it).
3. Before attaching, find-and-replace `<YOUR_ID>` in `clickstream-dev-policy.json` with your
   actual bucket suffix from Phase 2.
4. Generate access keys for `clickstream-dev` and run `aws configure` locally with them —
   never use root credentials for `aws configure`.
5. Budgets/Cost Explorer setup itself (Phase 0) still needs to be done as root or an
   admin-level user once, since this policy only grants *viewing* budgets, not creating them.

## Phase 3 addition: Kinesis + Firehose (Path B)

Two more statements were added to `clickstream-dev-policy.json` for the
streaming ingestion path: `KinesisStreamForStreamingIngestion` (create/
manage the stream, push records) and `FirehoseDeliveryStreamManagement`
(create/manage the delivery stream). Both are scoped by the
`clickstream-*` name prefix, same convention as everything else.

This is separate from `iam/firehose-service-role-policy.json`, which is
**not** a policy attached to `clickstream-dev` at all — it documents the
service role Firehose itself assumes to read from Kinesis and write to
S3. That role gets created automatically by the console's delivery-stream
wizard; the JSON file here exists so the same permissions can be
recreated deliberately via CDK in Phase 9, rather than relying on
console-generated defaults that are easy to forget the shape of later.

## What this does NOT cover yet

- QuickSight (Phase 8) — QuickSight manages its own separate permission model
  (QuickSight-specific IAM role, not this user's policy). Revisit when you get there.
- Full CDK bootstrap permissions — `cdk bootstrap` provisions its own S3 bucket and ECR repo
  for asset staging, which may need a one-time broader permission grant (or running bootstrap
  as an admin user once). Document whatever you end up doing here in Phase 9.