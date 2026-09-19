"""
dashboard_notebook.py

Phase 8 fallback for QuickSight: queries Athena directly via boto3 and
renders the same 3 visuals a QuickSight dashboard would show (funnel,
revenue trend, device/country breakdown), saved as PNG files for the
README/portfolio.

Chosen over QuickSight for this project specifically because QuickSight
bills on a separate pricing/trial structure outside the $200 Free Tier
credit pool this whole project is scoped against (see risk register) —
this keeps the dashboard entirely within the same cost boundary as
everything else.

Structured with '# %%' cell markers so it opens as a notebook-like
experience in VS Code / Jupyter, but also runs top-to-bottom as a plain
script:

    python dashboard_notebook.py

Requires the curated Glue table (Phase 6) and the queries in
athena/queries/ to exist and be queryable.
"""

# %% Imports and Athena helper
import time
import io

import boto3
import pandas as pd
import matplotlib.pyplot as plt

ATHENA_DATABASE = "clickstream_curated"
ATHENA_OUTPUT_LOCATION = "s3://clickstream-lake-mtusharaug/athena-results/"
ATHENA_RESULTS_BUCKET = "clickstream-lake-mtusharaug"
POLL_INTERVAL_SECONDS = 2
POLL_TIMEOUT_SECONDS = 120

athena_client = None
s3_client = None


def _get_clients():
    global athena_client, s3_client
    if athena_client is None:
        athena_client = boto3.client("athena")
    if s3_client is None:
        s3_client = boto3.client("s3")
    return athena_client, s3_client


def run_athena_query(query: str, database: str = ATHENA_DATABASE) -> pd.DataFrame:
    """Submit a query to Athena, poll until it finishes, and return the
    result as a pandas DataFrame. Reads the CSV result object straight
    out of S3 rather than paginating get_query_results, since Athena's
    own result CSV is simpler to parse for a report script like this."""
    athena_client, s3_client = _get_clients()
    response = athena_client.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": database},
        ResultConfiguration={"OutputLocation": ATHENA_OUTPUT_LOCATION},
    )
    query_id = response["QueryExecutionId"]

    elapsed = 0
    while elapsed < POLL_TIMEOUT_SECONDS:
        status_response = athena_client.get_query_execution(QueryExecutionId=query_id)
        state = status_response["QueryExecution"]["Status"]["State"]

        if state == "SUCCEEDED":
            break
        if state in ("FAILED", "CANCELLED"):
            reason = status_response["QueryExecution"]["Status"].get("StateChangeReason", "unknown")
            raise RuntimeError(f"Athena query {query_id} {state}: {reason}")

        time.sleep(POLL_INTERVAL_SECONDS)
        elapsed += POLL_INTERVAL_SECONDS
    else:
        raise TimeoutError(f"Athena query {query_id} did not finish within {POLL_TIMEOUT_SECONDS}s")

    result_key = f"athena-results/{query_id}.csv"
    obj = s3_client.get_object(Bucket=ATHENA_RESULTS_BUCKET, Key=result_key)
    return pd.read_csv(io.BytesIO(obj["Body"].read()))


# %% Query 1 — Funnel (view -> cart -> purchase)
FUNNEL_QUERY = """
SELECT
    COUNT(DISTINCT CASE WHEN event_type = 'product_view' THEN session_id END) AS viewed,
    COUNT(DISTINCT CASE WHEN event_type = 'add_to_cart' THEN session_id END) AS added_to_cart,
    COUNT(DISTINCT CASE WHEN event_type = 'checkout_start' THEN session_id END) AS checkout_started,
    COUNT(DISTINCT CASE WHEN event_type = 'purchase' THEN session_id END) AS purchased
FROM clickstream_curated.curated
"""

# %% Query 2 — Revenue trend over time (see athena/queries/revenue_trend.sql)
REVENUE_TREND_QUERY = """
SELECT year, month, day, ROUND(SUM(price), 2) AS daily_revenue
FROM clickstream_curated.curated
WHERE event_type = 'purchase'
GROUP BY year, month, day
ORDER BY year, month, day
"""

# %% Query 3 — Revenue by device/country (see athena/queries/revenue_by_country.sql)
DEVICE_COUNTRY_QUERY = """
SELECT country, device_type, ROUND(SUM(price), 2) AS total_revenue
FROM clickstream_curated.curated
WHERE event_type = 'purchase'
GROUP BY country, device_type
ORDER BY total_revenue DESC
"""


# %% Chart builders — pure functions of a DataFrame, so they're testable
# without needing a live Athena connection (see the local test in this
# module's accompanying test run, not shipped as part of this file).

def build_funnel_chart(df: pd.DataFrame, out_path: str):
    stages = ["viewed", "added_to_cart", "checkout_started", "purchased"]
    labels = ["Product View", "Add to Cart", "Checkout Start", "Purchase"]
    values = [int(df.iloc[0][s]) for s in stages]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.barh(labels[::-1], values[::-1], color="#2563eb")
    ax.set_xlabel("Sessions")
    ax.set_title("Conversion Funnel: View → Cart → Checkout → Purchase")
    for bar, value in zip(bars, values[::-1]):
        ax.text(bar.get_width() + max(values) * 0.01, bar.get_y() + bar.get_height() / 2,
                 str(value), va="center")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def build_revenue_trend_chart(df: pd.DataFrame, out_path: str):
    df = df.copy()
    df["date"] = pd.to_datetime(
        df["year"].astype(str) + "-" + df["month"].astype(str).str.zfill(2) + "-" + df["day"].astype(str).str.zfill(2)
    )
    df = df.sort_values("date")

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(df["date"], df["daily_revenue"], marker="o", color="#16a34a")
    ax.set_xlabel("Date")
    ax.set_ylabel("Revenue ($)")
    ax.set_title("Daily Revenue Trend")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def build_device_country_chart(df: pd.DataFrame, out_path: str):
    pivot = df.pivot_table(index="country", columns="device_type", values="total_revenue", fill_value=0)

    fig, ax = plt.subplots(figsize=(9, 5))
    pivot.plot(kind="bar", stacked=True, ax=ax, colormap="viridis")
    ax.set_ylabel("Revenue ($)")
    ax.set_title("Revenue by Country and Device Type")
    ax.legend(title="Device")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


# %% Run everything
if __name__ == "__main__":
    print("Querying Athena...")
    funnel_df = run_athena_query(FUNNEL_QUERY)
    trend_df = run_athena_query(REVENUE_TREND_QUERY)
    device_country_df = run_athena_query(DEVICE_COUNTRY_QUERY)

    print("Building charts...")
    build_funnel_chart(funnel_df, "../docs/dashboard-funnel.png")
    build_revenue_trend_chart(trend_df, "../docs/dashboard-revenue-trend.png")
    build_device_country_chart(device_country_df, "../docs/dashboard-device-country.png")

    print("Done. Charts saved to docs/.")