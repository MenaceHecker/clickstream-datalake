import json
from datetime import datetime

import boto3
from moto import mock_aws

from upload_to_s3 import first_event_timestamp, partition_key, upload_file


def test_partition_key_is_hive_style_and_zero_padded():
    ts = datetime(2026, 1, 5, 3, 0, 0)
    key = partition_key(ts, "events_20260105_0300.jsonl")
    assert key == "raw/year=2026/month=01/day=05/hour=03/events_20260105_0300.jsonl"


def test_partition_key_respects_custom_prefix():
    ts = datetime(2026, 9, 6, 14, 30, 0)
    key = partition_key(ts, "events.jsonl", prefix="curated")
    assert key == "curated/year=2026/month=09/day=06/hour=14/events.jsonl"


def test_first_event_timestamp_reads_only_first_line(tmp_path):
    filepath = tmp_path / "events.jsonl"
    filepath.write_text(
        '{"timestamp": "2026-09-06T14:30:00"}\n'
        '{"timestamp": "2026-09-06T23:59:59"}\n'  # would give a different partition
    )
    ts = first_event_timestamp(str(filepath))
    assert ts == datetime(2026, 9, 6, 14, 30, 0)


def test_upload_file_dry_run_never_touches_s3(tmp_path):
    filepath = tmp_path / "events_20260906_1430.jsonl"
    filepath.write_text('{"timestamp": "2026-09-06T14:30:00"}\n')

    # Passing s3_client=None proves this path never calls it. A real S3
    # client would raise on any method call against None only if actually
    # invoked, so this fails loudly if dry_run ever stops short-circuiting.
    key = upload_file(None, "unused-bucket", str(filepath), "raw", dry_run=True)

    assert key == "raw/year=2026/month=09/day=06/hour=14/events_20260906_1430.jsonl"


@mock_aws
def test_upload_file_lands_at_correct_partitioned_key(tmp_path):
    bucket = "test-clickstream-bucket"
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket=bucket)

    filepath = tmp_path / "events_20260906_1430.jsonl"
    filepath.write_text(json.dumps({"timestamp": "2026-09-06T14:30:00", "event_type": "page_view"}) + "\n")

    key = upload_file(s3, bucket, str(filepath), "raw", dry_run=False)

    assert key == "raw/year=2026/month=09/day=06/hour=14/events_20260906_1430.jsonl"
    obj = s3.get_object(Bucket=bucket, Key=key)
    body = json.loads(obj["Body"].read().decode().strip())
    assert body["event_type"] == "page_view"
