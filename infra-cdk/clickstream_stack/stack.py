"""
stack.py

Defines the entire clickstream data lake pipeline as one CDK stack:
S3 (with lifecycle rules), Glue (databases, crawlers, ETL job), Kinesis +
Firehose (the Path B streaming ingestion chosen back in Phase 3), IAM
roles for each service, and AWS Budgets.

This is a deliberate one-stack design rather than splitting into nested
stacks per service — at this project's scale, one stack keeps
`cdk deploy` / `cdk destroy` as true one-command operations (the Phase 9
goal), and the resource count here doesn't approach CloudFormation's
per-stack limits. A production version of this pipeline serving real
traffic would likely split storage, compute, and ingestion into separate
stacks for independent deploy cadences — noted here as the scaling path
not taken, deliberately, for a portfolio project of this size.
"""

import json

from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_s3 as s3,
    aws_iam as iam,
    aws_glue as glue,
    aws_kinesis as kinesis,
    aws_kinesisfirehose as firehose,
    aws_budgets as budgets,
    aws_s3_assets as s3_assets,
)
from constructs import Construct


class ClickstreamStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        bucket_suffix: str | None = None,
        alert_email: str = "",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        bucket_name = f"clickstream-lake-{bucket_suffix}" if bucket_suffix else None

        # ------------------------------------------------------------------
        # S3 — the data lake bucket, with Phase 4's lifecycle rules built in
        # ------------------------------------------------------------------
        self.bucket = s3.Bucket(
            self,
            "ClickstreamLakeBucket",
            bucket_name=bucket_name,
            versioned=False,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="raw-zone-tiering",
                    prefix="raw/",
                    enabled=True,
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=Duration.days(30),
                        ),
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER_INSTANT_RETRIEVAL,
                            transition_after=Duration.days(90),
                        ),
                    ],
                ),
                s3.LifecycleRule(
                    id="athena-results-expiry",
                    prefix="athena-results/",
                    enabled=True,
                    expiration=Duration.days(7),
                ),
                s3.LifecycleRule(
                    id="abort-incomplete-multipart-uploads",
                    enabled=True,
                    abort_incomplete_multipart_upload_after=Duration.days(7),
                ),
                # Note: curated/ intentionally has NO lifecycle rule — see
                # lifecycle/lifecycle-notes.md for the documented rationale
                # (actively queried, stays on Standard).
            ],
        )

        # ------------------------------------------------------------------
        # IAM — one role per service, matching iam/*-role-policy.json docs
        # ------------------------------------------------------------------
        glue_crawler_role = iam.Role(
            self,
            "GlueCrawlerRole",
            role_name="clickstream-glue-crawler-role-cdk",
            assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
        )
        self.bucket.grant_read(glue_crawler_role, "raw/*")
        self.bucket.grant_read(glue_crawler_role, "curated/*")
        glue_crawler_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "glue:GetDatabase",
                    "glue:CreateTable",
                    "glue:UpdateTable",
                    "glue:GetTable",
                    "glue:GetTables",
                    "glue:BatchCreatePartition",
                    "glue:GetPartitions",
                    "glue:BatchUpdatePartition",
                ],
                resources=["*"],
            )
        )

        glue_etl_role = iam.Role(
            self,
            "GlueEtlRole",
            role_name="clickstream-glue-etl-role-cdk",
            assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
        )
        self.bucket.grant_read(glue_etl_role, "raw/*")
        self.bucket.grant_read_write(glue_etl_role, "curated/*")
        glue_etl_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "glue:GetDatabase",
                    "glue:GetTable",
                    "glue:GetTables",
                    "glue:GetPartitions",
                    "glue:CreateTable",
                    "glue:UpdateTable",
                    "glue:BatchCreatePartition",
                ],
                resources=["*"],
            )
        )

        firehose_role = iam.Role(
            self,
            "FirehoseDeliveryRole",
            role_name="clickstream-firehose-delivery-role-cdk",
            assumed_by=iam.ServicePrincipal("firehose.amazonaws.com"),
        )
        self.bucket.grant_write(firehose_role, "raw/*")
        self.bucket.grant_read(firehose_role)

        # ------------------------------------------------------------------
        # Glue — databases, crawlers, ETL job
        # ------------------------------------------------------------------
        raw_database = glue.CfnDatabase(
            self,
            "RawDatabase",
            catalog_id=self.account,
            database_input=glue.CfnDatabase.DatabaseInputProperty(name="clickstream_raw"),
        )
        curated_database = glue.CfnDatabase(
            self,
            "CuratedDatabase",
            catalog_id=self.account,
            database_input=glue.CfnDatabase.DatabaseInputProperty(name="clickstream_curated"),
        )

        raw_crawler = glue.CfnCrawler(
            self,
            "RawCrawler",
            name="clickstream-raw-crawler-cdk",
            role=glue_crawler_role.role_arn,
            database_name="clickstream_raw",
            targets=glue.CfnCrawler.TargetsProperty(
                s3_targets=[glue.CfnCrawler.S3TargetProperty(path=f"s3://{self.bucket.bucket_name}/raw/")]
            ),
            schema_change_policy=glue.CfnCrawler.SchemaChangePolicyProperty(
                update_behavior="UPDATE_IN_DATABASE", delete_behavior="LOG"
            ),
            configuration=json.dumps(
                {"Version": 1.0, "Grouping": {"TableGroupingPolicy": "CombineCompatibleSchemas"}}
            ),
        )
        raw_crawler.add_dependency(raw_database)

        curated_crawler = glue.CfnCrawler(
            self,
            "CuratedCrawler",
            name="clickstream-curated-crawler-cdk",
            role=glue_crawler_role.role_arn,
            database_name="clickstream_curated",
            targets=glue.CfnCrawler.TargetsProperty(
                s3_targets=[glue.CfnCrawler.S3TargetProperty(path=f"s3://{self.bucket.bucket_name}/curated/")]
            ),
            schema_change_policy=glue.CfnCrawler.SchemaChangePolicyProperty(
                update_behavior="UPDATE_IN_DATABASE", delete_behavior="LOG"
            ),
        )
        curated_crawler.add_dependency(curated_database)

        # Upload the ETL script as a CDK asset so the Glue job can
        # reference a real S3 location without a manual `aws s3 cp` step.
        etl_script_asset = s3_assets.Asset(
            self,
            "EtlScriptAsset",
            path="../glue/etl_job.py",
        )
        etl_script_asset.grant_read(glue_etl_role)

        glue.CfnJob(
            self,
            "EtlJob",
            name="clickstream-json-to-parquet-cdk",
            role=glue_etl_role.role_arn,
            command=glue.CfnJob.JobCommandProperty(
                name="glueetl",
                script_location=etl_script_asset.s3_object_url,
                python_version="3",
            ),
            default_arguments={
                "--raw_database": "clickstream_raw",
                "--raw_table": "raw",
                "--curated_s3_path": f"s3://{self.bucket.bucket_name}/curated/",
                "--enable-metrics": "true",
                "--enable-continuous-cloudwatch-log": "true",
            },
            glue_version="4.0",
            worker_type="G.1X",
            number_of_workers=2,
            max_retries=0,
            timeout=30,
        )

        # ------------------------------------------------------------------
        # Kinesis + Firehose — Path B streaming ingestion (Phase 3 choice)
        # ------------------------------------------------------------------
        stream = kinesis.CfnStream(
            self,
            "ClickstreamEventsStream",
            name="clickstream-events-stream-cdk",
            stream_mode_details=kinesis.CfnStream.StreamModeDetailsProperty(stream_mode="ON_DEMAND"),
        )

        stream_arn = f"arn:aws:kinesis:{self.region}:{self.account}:stream/{stream.name}"
        firehose_role.add_to_policy(
            iam.PolicyStatement(
                actions=["kinesis:DescribeStream", "kinesis:GetShardIterator", "kinesis:GetRecords", "kinesis:ListShards"],
                resources=[stream_arn],
            )
        )

        firehose.CfnDeliveryStream(
            self,
            "ClickstreamFirehose",
            delivery_stream_name="clickstream-firehose-cdk",
            delivery_stream_type="KinesisStreamAsSource",
            kinesis_stream_source_configuration=firehose.CfnDeliveryStream.KinesisStreamSourceConfigurationProperty(
                kinesis_stream_arn=stream_arn,
                role_arn=firehose_role.role_arn,
            ),
            extended_s3_destination_configuration=firehose.CfnDeliveryStream.ExtendedS3DestinationConfigurationProperty(
                bucket_arn=self.bucket.bucket_arn,
                role_arn=firehose_role.role_arn,
                prefix="raw/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/",
                error_output_prefix="firehose-errors/!{firehose:error-output-type}/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/",
                buffering_hints=firehose.CfnDeliveryStream.BufferingHintsProperty(
                    interval_in_seconds=60, size_in_m_bs=5
                ),
                compression_format="GZIP",
            ),
        )

        # ------------------------------------------------------------------
        # Budgets — the two guardrails from Phase 0, now provisioned as code
        # ------------------------------------------------------------------
        self._add_budget(
            construct_id="SoftLimitBudget",
            budget_name="clickstream-soft-limit-cdk",
            limit_amount=150,
            thresholds=[80, 100],
            alert_email=alert_email,
        )
        self._add_budget(
            construct_id="HardStopBudget",
            budget_name="clickstream-hard-stop-cdk",
            limit_amount=180,
            thresholds=[100],
            alert_email=alert_email,
        )

    def _add_budget(
        self,
        construct_id: str,
        budget_name: str,
        limit_amount: float,
        thresholds: list[int],
        alert_email: str,
    ) -> None:
        notifications = [
            budgets.CfnBudget.NotificationWithSubscribersProperty(
                notification=budgets.CfnBudget.NotificationProperty(
                    notification_type="ACTUAL",
                    comparison_operator="GREATER_THAN",
                    threshold=threshold,
                    threshold_type="PERCENTAGE",
                ),
                subscribers=[
                    budgets.CfnBudget.SubscriberProperty(
                        subscription_type="EMAIL",
                        address=alert_email,
                    )
                ],
            )
            for threshold in thresholds
        ]

        budgets.CfnBudget(
            self,
            construct_id,
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_name=budget_name,
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(amount=limit_amount, unit="USD"),
                cost_filters={"TagKeyValue": [f"user:Project$clickstream-lake"]},
            ),
            notifications_with_subscribers=notifications,
        )