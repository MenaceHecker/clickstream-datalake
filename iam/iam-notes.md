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

## Known caveat: Glue's tag condition (UPDATE: hit this in Phase 6, resolved)

`GlueCatalogAndJobs` originally included a `Condition` requiring
`aws:ResourceTag/Project = clickstream-lake`. This caused a real
`AccessDeniedException` on `glue:StartJobRun` during Phase 6 — the job
didn't carry the tag reliably enough for the condition to evaluate as
satisfied, so the action was denied even though the base policy granted
it. **The condition has since been removed from this policy.** Glue
resource access here is now controlled by naming convention
(`clickstream-*` prefix) rather than tags, consistent with how every
other statement in this policy is scoped. This is left in the notes as a
real example of a documented risk actually happening, not a hypothetical
— worth mentioning as-is in an interview rather than cleaning up the
narrative after the fact.

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

## Phase 9 addition: CDK bootstrap role assumption + Budgets write access

Two more changes for the CDK rebuild:

1. **`AssumeCDKBootstrapRoles`** — modern CDK (v2, "new-style" bootstrap)
   deploys through a set of auto-generated IAM roles
   (`cdk-hnb659fds-deploy-role-*`, `cdk-hnb659fds-file-publishing-role-*`,
   etc.) rather than having the deploying identity call CloudFormation
   and S3 directly. `clickstream-dev` needs `sts:AssumeRole` on these
   specifically — this is the standard, secure way CDK expects to be
   used, not a workaround.

2. **`BudgetsWriteForCDKDeploy`** — a genuine, deliberate reversal of an
   earlier decision. Phase 0's original design gave `clickstream-dev`
   *view-only* budget access, on the reasoning that root/admin sets
   budgets up once and this user only needs to check them. Phase 9's CDK
   stack now defines the two budgets as code, meaning `clickstream-dev`
   needs to actually create/modify/delete them for `cdk deploy` /
   `cdk destroy` to be true one-command operations. This is worth being
   explicit about rather than quietly loosening it: the trade-off is
   "one-command IaC" (the actual Phase 9 goal) versus "budgets can only
   ever be touched by an admin" (the original, more conservative Phase 0
   posture). This project prioritizes the former once IaC is the goal —
   in a team/production setting, this is exactly the kind of change that
   would get flagged in a policy review before merging.

## `cdk bootstrap` itself still needs broader permissions (one-time)

Bootstrapping a CDK environment (`cdk bootstrap`) provisions the roles
and S3 asset bucket referenced above — a one-time, account-level setup
step that itself needs broader permissions than this scoped policy
grants (it's creating the very roles this policy later assumes). Run
`cdk bootstrap` once as an admin/root-equivalent identity, or
temporarily attach `AdministratorAccess` to `clickstream-dev` for that
single command, then revert. Document whichever approach you actually
used here once you've done it — this is intentionally left open rather
than guessed at, since it depends on what admin access you have
available.

## What this does NOT cover yet

- QuickSight (Phase 8) — QuickSight manages its own separate permission model
  (QuickSight-specific IAM role, not this user's policy). Revisit when you get there.
- Full CDK bootstrap permissions — `cdk bootstrap` provisions its own S3 bucket and ECR repo
  for asset staging, which may need a one-time broader permission grant (or running bootstrap
  as an admin user once). Document whatever you end up doing here in Phase 9.