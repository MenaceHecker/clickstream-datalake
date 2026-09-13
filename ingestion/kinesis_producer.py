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