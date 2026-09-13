"""
kinesis_producer.py

Streams simulated clickstream events into a Kinesis Data Stream in
real time, reusing the funnel-simulation logic from generator/. This
replaces the "run the generator, then upload a file" batch pattern from
Phase 2 with a continuous producer — the streaming half of the Phase 3
ingestion story.

Kinesis Firehose (configured separately, see firehose-setup-notes.md)
subscribes to the stream, buffers records, and writes them to the S3 raw
zone automatically — no Lambda needed on this path.

Usage:
    # Run for 10 minutes, ~5 events/sec
    python kinesis_producer.py --stream-name clickstream-events-stream --duration-seconds 600 --rate 5

    # Run indefinitely until Ctrl+C
    python kinesis_producer.py --stream-name clickstream-events-stream --rate 10

    # Dry run : prints records instead of calling Kinesis
    python kinesis_producer.py --stream-name clickstream-events-stream --rate 5 --dry-run
"""

import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone

import boto3

sys.path.insert(0, "../generator")
from schema import CATEGORIES, COUNTRIES, DEVICE_TYPES, DEVICE_TYPE_WEIGHTS, REFERRERS, new_id  # noqa: E402


class SessionState:
    """Tracks a single in-flight simulated session so its events can be
    emitted one at a time, spaced out in real time, rather than all at
    once the way the batch generator does."""

    STAGES = ["page_view", "product_view", "add_to_cart", "checkout_start", "purchase"]

    def __init__(self, users, catalog):
        self.user_id = random.choice(users)
        self.session_id = new_id()
        self.device_type = random.choices(DEVICE_TYPES, weights=DEVICE_TYPE_WEIGHTS, k=1)[0]
        self.referrer = random.choice(REFERRERS)
        self.country = random.choice(COUNTRIES)
        self.product = random.choice(catalog)
        self.stage_index = 0
        self.alive = True
        self._advance_decided = False

    def next_event(self) -> dict | None:
        """Return the next event dict for this session, or None if the
        session has ended (dropped off the funnel or completed it)."""
        if not self.alive:
            return None

        stage = self.STAGES[self.stage_index]
        event = {
            "event_id": new_id(),
            "event_type": stage,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "product_id": self.product["product_id"] if stage != "page_view" else None,
            "category": self.product["category"] if stage != "page_view" else None,
            "price": self.product["price"] if stage != "page_view" else None,
            "device_type": self.device_type,
            "referrer": self.referrer,
            "country": self.country,
        }

        # Same conditional drop-off rates as the batch generator.
        continue_probs = {
            "page_view": 0.40,
            "product_view": 0.375,
            "add_to_cart": 0.667,
            "checkout_start": 0.70,
        }
        if stage in continue_probs and random.random() >= continue_probs[stage]:
            self.alive = False
        elif stage == "purchase":
            self.alive = False
        else:
            self.stage_index += 1

        return event


def build_product_catalog(n: int = 200) -> list[dict]:
    return [
        {
            "product_id": new_id(),
            "category": random.choice(CATEGORIES),
            "price": round(random.uniform(4.99, 899.99), 2),
        }
        for _ in range(n)
    ]


def build_user_pool(n: int = 500) -> list[str]:
    return [new_id() for _ in range(n)]


def put_records_batch(kinesis_client, stream_name: str, records: list[dict], dry_run: bool):
    if dry_run:
        for r in records:
            print(f"[dry-run] would PutRecord (partition_key={r['session_id']}): {json.dumps(r)}")
        return

    entries = [
        {
            "Data": (json.dumps(r) + "\n").encode("utf-8"),
            "PartitionKey": r["session_id"],
        }
        for r in records
    ]
    response = kinesis_client.put_records(StreamName=stream_name, Records=entries)
    if response.get("FailedRecordCount", 0) > 0:
        print(f"WARNING: {response['FailedRecordCount']} record(s) failed to put", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Stream simulated clickstream events into Kinesis.")
    parser.add_argument("--stream-name", required=True, help="Kinesis Data Stream name.")
    parser.add_argument("--rate", type=float, default=5.0, help="Approximate events per second to emit.")
    parser.add_argument("--duration-seconds", type=int, default=None, help="Stop after this many seconds. Omit to run until Ctrl+C.")
    parser.add_argument("--batch-size", type=int, default=25, help="Events per PutRecords call (Kinesis max is 500).")
    parser.add_argument("--max-concurrent-sessions", type=int, default=50, help="How many simulated sessions run in parallel.")
    parser.add_argument("--dry-run", action="store_true", help="Print records instead of calling Kinesis.")
    args = parser.parse_args()

    kinesis_client = None if args.dry_run else boto3.client("kinesis")

    catalog = build_product_catalog()
    users = build_user_pool()
    active_sessions: list[SessionState] = []

    start = time.time()
    events_sent = 0
    seconds_per_event = 1.0 / args.rate
    batch: list[dict] = []

    print(f"Streaming to '{args.stream_name}' at ~{args.rate} events/sec"
          f"{' (dry run)' if args.dry_run else ''}. Ctrl+C to stop.")

    try:
        while True:
            if args.duration_seconds and (time.time() - start) >= args.duration_seconds:
                break

            # Keep a pool of concurrent sessions alive, like real traffic.
            while len(active_sessions) < args.max_concurrent_sessions:
                active_sessions.append(SessionState(users, catalog))

            session = random.choice(active_sessions)
            event = session.next_event()
            if event is not None:
                batch.append(event)
                events_sent += 1

            if not session.alive:
                active_sessions.remove(session)

            if len(batch) >= args.batch_size:
                put_records_batch(kinesis_client, args.stream_name, batch, args.dry_run)
                batch = []

            time.sleep(seconds_per_event)

    except KeyboardInterrupt:
        print("\nStopping (Ctrl+C received)...")

    if batch:
        put_records_batch(kinesis_client, args.stream_name, batch, args.dry_run)

    elapsed = time.time() - start
    print(f"\nDone. Sent {events_sent} events over {elapsed:.1f}s (~{events_sent / max(elapsed, 1):.1f}/sec).")


if __name__ == "__main__":
    main()