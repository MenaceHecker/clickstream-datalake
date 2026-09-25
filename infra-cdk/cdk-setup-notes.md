# Phase 9 — CDK Rebuild: Setup, Deploy, and Teardown Notes

## What was validated before this was handed over

The stack was actually synthesized locally with `cdk synth` (not just
written and hoped for) before being finalized:

- Clean synth, zero warnings, in `--strict` mode
- Resource count matches design exactly: 1 S3 bucket, 2 Glue databases,
  2 crawlers, 1 ETL job, 1 Kinesis stream, 1 Firehose delivery stream,
  3 IAM roles/policies, 2 budgets
- S3 lifecycle rules confirmed to render identically to Phase 4's
  hand-written `lifecycle-policy.json` (`STANDARD_IA` at 30 days,
  `GLACIER_IR` at 90, 7-day expiry on `athena-results/`, `curated/`
  correctly left with no rule)
- The required-context-value check (`alert_email`) confirmed to fail
  loudly with a clear message rather than silently deploying budgets
  with no subscriber

This doesn't guarantee a clean `cdk deploy` against a real account (no
substitute for actually running it), but it means the CloudFormation
this stack generates is structurally sound before you spend real deploy
time on it.

## Design choice: one stack, not several

Everything (S3, Glue, Kinesis, Firehose, IAM, Budgets) lives in one
`ClickstreamStack` rather than being split into nested stacks per
service. At this project's resource count, splitting stacks would add
cross-stack reference complexity for no real benefit — and it keeps
`cdk deploy` / `cdk destroy` genuinely one-command, which is the actual
Phase 9 goal. Noted in the stack's own docstring as a scaling trade-off:
a production version of this pipeline would likely split storage,
compute, and ingestion into independently-deployable stacks.

## Important: your bucket already exists manually

`clickstream-lake-mtusharaug` was created by hand back in Phase 2.
CloudFormation cannot "adopt" an existing bucket into a new stack by
just reusing its name — if you deploy this CDK stack with
`bucket_suffix=mtusharaug`, it will try to create a bucket with that
exact name and fail, because it already exists (owned by you, but not
by this CloudFormation stack).

This is exactly the tension Phase 9's own goal creates: *"Tear down the
manually-created resources from earlier phases and redeploy entirely
via cdk deploy — this proves the IaC actually works end-to-end."*
Two honest options:

**Option A — full teardown and rebuild (matches the plan's intent)**:
Delete the manually-created resources first (S3 objects + bucket, Glue
databases/crawlers/job, Kinesis stream, Firehose delivery stream, the
manually-created IAM roles), then `cdk deploy` fresh with the same
`bucket_suffix=mtusharaug`. This is the version that actually
demonstrates "torn down and redeployed via IaC," which is what the
resume bullet claims.

**Option B — deploy alongside, different suffix**: Use a different
`bucket_suffix` (e.g. `mtusharaug-cdk`) so CDK creates a parallel set of
resources without touching what you already built by hand. Lower risk,
but doesn't actually prove the teardown/rebuild story — you'd have two
parallel pipelines, not one rebuilt one.

**Recommendation**: since this is a portfolio project and the data
itself has no real value to preserve, Option A is worth doing — it's
the version of this phase that's actually worth putting on a resume.
Back up nothing you need, then tear down for real.

### Teardown checklist (Option A)

```bash
# Empty and delete the bucket (must be empty first)
aws s3 rm s3://clickstream-lake-mtusharaug --recursive
aws s3api delete-bucket --bucket clickstream-lake-mtusharaug

# Delete Glue resources
aws glue delete-crawler --name clickstream-raw-crawler
aws glue delete-crawler --name clickstream-curated-crawler
aws glue delete-job --job-name clickstream-json-to-parquet
aws glue delete-database --name clickstream_raw
aws glue delete-database --name clickstream_curated

# Delete Kinesis + Firehose (if Phase 3 resources are still running)
aws firehose delete-delivery-stream --delivery-stream-name <your-firehose-name>
aws kinesis delete-stream --stream-name clickstream-events-stream

# Delete the manually-created IAM roles (CDK creates its own with "-cdk" suffix)
aws iam delete-role-policy --role-name clickstream-glue-crawler-role --policy-name clickstream-glue-crawler-permissions
aws iam delete-role --role-name clickstream-glue-crawler-role
# repeat for clickstream-glue-etl-role and clickstream-firehose-delivery-role if created
```

Verify everything's actually gone before deploying:
```bash
aws glue get-databases --query 'DatabaseList[].Name'
aws s3 ls | grep clickstream
```

## Deploying

### 1. One-time: bootstrap the CDK environment

See the caveat in `iam/iam-notes.md` — this needs broader-than-usual
permissions once. Either run as an admin identity, or temporarily
attach `AdministratorAccess` to `clickstream-dev` for this single
command:

```bash
cdk bootstrap aws://<account-id>/us-east-1
```

**Verified live (2026-09-24), not just predicted:** ran `cdk synth`
successfully with `clickstream-dev`'s scoped credentials (clean template,
no AWS calls needed), then actually attempted `cdk bootstrap` with those
same credentials to confirm this caveat for real rather than trusting it
on paper. It failed exactly as expected:

```
AccessDenied: User: .../clickstream-dev is not authorized to perform:
cloudformation:CreateChangeSet on resource:
arn:aws:cloudformation:us-east-1:<account-id>:stack/CDKToolkit/*
```

Two separate reasons bootstrap specifically needs an admin identity, not
just a policy tweak:
1. `clickstream-dev`'s policy was missing `cloudformation:CreateChangeSet`
   (modern CDK CLI deploys via change sets, not direct `CreateStack`/
   `UpdateStack` calls) — **fixed** in `iam/clickstream-dev-policy.json`,
   which now also covers ongoing `cdk deploy` calls against the
   `clickstream-*` stack post-bootstrap.
2. Even with that fixed, bootstrap itself creates resources that fall
   outside every ARN this policy scopes to by design — the
   `cdk-hnb659fds-*` IAM roles, a staging S3 bucket, an SSM parameter —
   none of which match the `clickstream-*`/`stack/CDKToolkit/*` prefixes
   `clickstream-dev` is deliberately restricted to. This part genuinely
   requires broader-than-`clickstream-dev` credentials; there's no policy
   fix that keeps it scoped, because bootstrap is an account-level,
   one-time setup operation by nature. Standard practice, not a workaround:
   an admin bootstraps the environment once, then scoped roles like
   `clickstream-dev` (via `AssumeCDKBootstrapRoles`) drive deploys after
   that.

### 2. Install dependencies

```bash
cd infra-cdk
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Update the `clickstream-dev` IAM policy

Apply the updated `iam/clickstream-dev-policy.json` (adds CDK bootstrap
role assumption + Budgets write access — see `iam-notes.md` for why).

### 4. Synthesize first (no AWS calls, just generates the template)

```bash
cdk synth -c bucket_suffix=mtusharaug -c alert_email=<your-real-email>
```

Read through the generated CloudFormation in `cdk.out/` if you want to
sanity-check it before actually deploying anything.

### 5. Deploy for real

```bash
cdk deploy -c bucket_suffix=mtusharaug -c alert_email=<your-real-email>
```

Review the IAM/security-sensitive changes CDK prompts you to confirm,
then approve.

### 6. Verify

```bash
aws s3 ls s3://clickstream-lake-mtusharaug
aws glue get-databases --query 'DatabaseList[].Name'
aws glue get-crawler --name clickstream-raw-crawler-cdk --query 'Crawler.State'
```

Then re-run the data pipeline: upload data (Phase 2/3), start the
crawlers, run the ETL job, and confirm Athena/the dashboard notebook
still work against the freshly-provisioned infrastructure.

## Tearing it all down again

```bash
cdk destroy -c bucket_suffix=mtusharaug -c alert_email=<your-real-email>
```

Note: the S3 bucket has `RemovalPolicy.RETAIN` set deliberately (see
`stack.py`) — `cdk destroy` will NOT delete the bucket or its contents,
even though it deletes everything else. This is intentional: losing the
Glue catalog or Kinesis stream costs nothing to recreate, but silently
losing S3 data on every `cdk destroy` would be a bad default for a
project that's supposed to demonstrate careful data-lake practices. To
actually delete the bucket too, empty it manually first
(`aws s3 rm s3://... --recursive`) then delete it
(`aws s3api delete-bucket`), same as the teardown checklist above.

## Definition of done

- [ ] `cdk synth` runs clean (already verified locally, see top of this file)
- [ ] Manual resources torn down (Option A) or deployed alongside
      (Option B) — document which you chose
- [ ] `cdk deploy` completes successfully
- [ ] Data pipeline re-verified working against CDK-provisioned resources
- [ ] `cdk destroy` documented and tested at least once