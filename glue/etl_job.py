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

import sys

from awsglue.transforms import *  # noqa: F401,F403
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as F

args = getResolvedOptions(
    sys.argv,
    [
        "JOB_NAME",
        "raw_database",
        "raw_table",
        "curated_s3_path",
    ],
)

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

RAW_DATABASE = args["raw_database"]
RAW_TABLE = args["raw_table"]
CURATED_S3_PATH = args["curated_s3_path"]  # e.g. s3://clickstream-lake-mtusharaug/curated/

# --- Read from the Glue Data Catalog (populated by the Phase 5 crawler) ---
raw_dynamic_frame = glueContext.create_dynamic_frame.from_catalog(
    database=RAW_DATABASE,
    table_name=RAW_TABLE,
)
df = raw_dynamic_frame.toDF()

print(f"Raw record count (pre-clean): {df.count()}")

# --- Clean: drop malformed / missing-critical-field records ---
# event_id and timestamp are the two fields every downstream query
# (funnel joins, session analysis) depends on; anything missing either
# is unusable and safe to drop rather than propagate as nulls.
cleaned = df.filter(
    (F.col("event_id").isNotNull())
    & (F.col("event_id") != "")
    & (F.col("timestamp").isNotNull())
)

dropped_count = df.count() - cleaned.count()
print(f"Dropped {dropped_count} malformed/incomplete record(s)")

# --- Normalize timestamp, derive zero-padded partition columns ---
cleaned = cleaned.withColumn("event_ts", F.to_timestamp("timestamp"))
cleaned = (
    cleaned.withColumn("year", F.date_format("event_ts", "yyyy"))
    .withColumn("month", F.date_format("event_ts", "MM"))
    .withColumn("day", F.date_format("event_ts", "dd"))
)

# discount_code is present as a nullable column automatically (see
# module docstring) — no special handling needed here, but this cast
# guards against a rare edge case where a partition's files ended up
# with discount_code inferred as a non-string type due to all-null
# values in that specific file.
if "discount_code" in cleaned.columns:
    cleaned = cleaned.withColumn("discount_code", F.col("discount_code").cast("string"))
else:
    # Extremely defensive: if the entire raw table somehow has zero
    # discount_code values anywhere, Spark may not have inferred the
    # column at all. Add it as an all-null string column so the
    # curated schema is stable regardless of what a given crawl saw.
    cleaned = cleaned.withColumn("discount_code", F.lit(None).cast("string"))

output_columns = [
    "event_id", "event_type", "user_id", "session_id", "timestamp",
    "product_id", "category", "price", "device_type", "referrer",
    "country", "discount_code", "year", "month", "day",
]
cleaned = cleaned.select(*output_columns)

print(f"Cleaned record count: {cleaned.count()}")
cleaned.printSchema()

# --- Write partitioned Parquet (Snappy is Spark/Glue's default codec) ---
cleaned.write.mode("overwrite").partitionBy("year", "month", "day").parquet(
    CURATED_S3_PATH
)

print(f"Wrote curated Parquet to {CURATED_S3_PATH}")

job.commit()