#!/usr/bin/env python3
"""
app.py

CDK entry point. Reads account-specific parameters from context (cdk.json
or -c flags at the CLI) rather than hardcoding them, so this stack is
portable across accounts/regions per the Phase 9 goal.

If not provided, bucket_suffix falls back to the CDK-resolved account ID
(still globally unique, just less readable), and alert_email must be
provided explicitly — CDK will raise a clear error rather than silently
skipping budget notifications if it's missing.
"""

import os

import aws_cdk as cdk

from clickstream_stack.stack import ClickstreamStack

app = cdk.App()

bucket_suffix = app.node.try_get_context("bucket_suffix")
alert_email = app.node.try_get_context("alert_email")
# Default True (the intended architecture); pass -c enable_streaming=false
# to skip Kinesis+Firehose if this account rejects Kinesis stream creation
# (see the note in clickstream_stack/stack.py and cdk-setup-notes.md).
enable_streaming = str(app.node.try_get_context("enable_streaming") or "true").lower() != "false"

if not alert_email:
    raise ValueError(
        "Missing required context value 'alert_email'. "
        "Pass it with: cdk deploy -c alert_email=you@example.com"
    )

env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
)

stack = ClickstreamStack(
    app,
    "ClickstreamDataLakeStack",
    bucket_suffix=bucket_suffix,
    alert_email=alert_email,
    enable_streaming=enable_streaming,
    env=env,
)

cdk.Tags.of(stack).add("Project", "clickstream-lake")

app.synth()