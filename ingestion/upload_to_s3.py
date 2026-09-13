import argparse
import glob
import json
import os
import sys
from datetime import datetime

import boto3
from botocore.exceptions import ClientError, NoCredentialsError


def first_event_timestamp(filepath: str) -> datetime:
    """Read just the first line of a JSONL file to derive its partition.
    Every event in one batch file falls in the same few-minute window, so
    the first event's timestamp is representative enough for partitioning."""
    with open(filepath, "r") as f:
        first_line = f.readline()
    event = json.loads(first_line)
    return datetime.fromisoformat(event["timestamp"])


def partition_key(ts: datetime, filename: str, prefix: str = "raw") -> str:
    """Build the Hive-style partitioned S3 key for a given timestamp."""
    return (
        f"{prefix}/year={ts.year:04d}/month={ts.month:02d}/"
        f"day={ts.day:02d}/hour={ts.hour:02d}/{filename}"
    )


def upload_file(s3_client, bucket: str, filepath: str, prefix: str, dry_run: bool) -> str:
    filename = os.path.basename(filepath)
    ts = first_event_timestamp(filepath)
    key = partition_key(ts, filename, prefix)

    if dry_run:
        print(f"[dry-run] would upload {filepath} -> s3://{bucket}/{key}")
        return key

    s3_client.upload_file(filepath, bucket, key)
    print(f"uploaded {filepath} -> s3://{bucket}/{key}")
    return key


def main():
    parser = argparse.ArgumentParser(description="Upload JSONL clickstream batches to the S3 raw zone.")
    parser.add_argument("--bucket", required=True, help="Target S3 bucket name.")
    parser.add_argument("--input-dir", default="../generator/output", help="Directory of JSONL batch files to upload.")
    parser.add_argument("--prefix", default="raw", help="Top-level S3 prefix (zone) to upload into.")
    parser.add_argument("--pattern", default="*.jsonl", help="Glob pattern for files to upload within input-dir.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be uploaded without calling S3.")
    parser.add_argument("--delete-after-upload", action="store_true", help="Delete local files after a successful upload (off by default).")
    args = parser.parse_args()

    files = sorted(glob.glob(os.path.join(args.input_dir, args.pattern)))
    if not files:
        print(f"No files matching {args.pattern} found in {args.input_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(files)} file(s) to upload from {args.input_dir}")

    s3_client = boto3.client("s3")

    uploaded, failed = 0, 0
    for filepath in files:
        try:
            upload_file(s3_client, args.bucket, filepath, args.prefix, args.dry_run)
            uploaded += 1
            if args.delete_after_upload and not args.dry_run:
                os.remove(filepath)
        except NoCredentialsError:
            print("No AWS credentials found. Run `aws configure` first.", file=sys.stderr)
            sys.exit(1)
        except ClientError as e:
            print(f"Failed to upload {filepath}: {e}", file=sys.stderr)
            failed += 1

    print(f"\nDone. {uploaded} uploaded, {failed} failed.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()