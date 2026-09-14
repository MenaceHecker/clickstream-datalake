"""
etl_job.py

AWS Glue ETL job (Python Shell / PySpark). Reads the raw JSON clickstream
table from the Glue Data Catalog (populated by the Phase 5 crawler),
cleans it, and writes partitioned Parquet to the S3 curated zone.

This is the highest-leverage transformation in the whole pipeline — it's
what makes the Phase 7 Athena cost-comparison numbers exist at all.

Cleaning applied:
  - Drops records Spark's JSON reader flags as malformed
    (via columnNameOfCorruptRecord).
  - Drops records missing a non-empty event_id or a parseable timestamp —
    these are the "malformed" records this job is responsible for
    dropping per the Phase 6 goal.
  - Normalizes the timestamp string into a real timestamp type.
  - Derives year/month/day partition columns from the event's own
    timestamp — zero-padded (e.g. month=09, not month=9) to stay
    consistent with the raw zone's Hive-style partition format from
    Phase 2/3. Spark's default F.month()/F.dayofmonth() do NOT zero-pad;
    this job explicitly uses date_format(...) instead. Verified locally
    before writing this version — the unpadded default was caught in
    testing and is exactly the kind of subtle partition-format mismatch
    that would otherwise cause confusing Athena partition-pruning
    behavior later.

Schema evolution handling:
  Some raw records have a discount_code field, earlier ones don't at all
  (see generator/event_generator.py — this is deliberate). Spark's JSON
  reader natively handles this: it infers the union of all fields across
  every file it reads and fills genuinely missing keys with null. No
  special-casing is needed in this job for that reason specifically —
  the schema evolution is absorbed for free by using spark.read.json()
  across the whole raw-zone glob rather than processing files
  one-by-one with a fixed expected schema.

Run as a Glue job (this script is what you paste into the Glue Studio
script editor, or reference via --ScriptLocation when creating the job
via CLI/CDK). Cannot be run standalone with plain `python` — it depends
on the awsglue library, which only exists inside the Glue job runtime.
"""
