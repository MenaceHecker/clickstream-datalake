import json
import random
from datetime import datetime, timezone

from faker import Faker

from event_generator import generate, make_event, write_batches


def _seeded(seed=42):
    random.seed(seed)
    Faker.seed(seed)


def test_funnel_is_lossy_in_the_documented_order():
    """Regression test for the funnel shape the whole project's dashboard
    story depends on (README: 100 -> ~40 -> ~15 -> ~10 -> ~7). A typo in
    any of the P_*_GIVEN_* constants in event_generator.py should break
    this test rather than silently produce an unbelievable dashboard."""
    _seeded()
    from schema import Product

    catalog = [Product(product_id="p1", category="electronics", price=9.99)]
    events = generate(
        total_events=4000,
        start_time=datetime.now(timezone.utc),
        users=[f"user-{i}" for i in range(200)],
        catalog=catalog,
    )

    counts = {}
    for e in events:
        counts[e["event_type"]] = counts.get(e["event_type"], 0) + 1

    stages = ["page_view", "product_view", "add_to_cart", "checkout_start", "purchase"]
    for stage in stages:
        assert counts.get(stage, 0) > 0, f"expected at least one {stage} event"

    # Each stage must be strictly smaller than the one before it. That's
    # the "funnel" shape, independent of the exact conversion percentages.
    for earlier, later in zip(stages, stages[1:]):
        assert counts[earlier] > counts[later], (
            f"expected {earlier} ({counts[earlier]}) > {later} ({counts[later]})"
        )

    # Loose bounds around the documented ~7% page_view -> purchase rate,
    # wide enough to not be flaky but tight enough to catch a real
    # regression (e.g. a probability constant accidentally set to 0.9).
    purchase_rate = counts["purchase"] / counts["page_view"]
    assert 0.02 < purchase_rate < 0.15


def test_schema_evolution_introduces_discount_code_partway_through():
    """discount_code should be entirely absent from early events (not just
    null) and present as a key (possibly null) once generation has passed
    the halfway point. This is what gives Phase 6's Glue ETL job a real
    schema-evolution case to handle."""
    ts = datetime.now(timezone.utc)

    early_event = make_event(
        "checkout_start", "u1", "s1", ts, "mobile", "direct", "US",
        product=None, total_generated_so_far=10, total_planned=100,
    )
    assert "discount_code" not in early_event

    late_event = make_event(
        "checkout_start", "u1", "s1", ts, "mobile", "direct", "US",
        product=None, total_generated_so_far=90, total_planned=100,
    )
    assert "discount_code" in late_event


def test_write_batches_groups_by_time_window_and_writes_valid_jsonl(tmp_path):
    events = [
        {"event_id": "1", "timestamp": "2026-09-06T14:02:00"},
        {"event_id": "2", "timestamp": "2026-09-06T14:04:00"},  # same 5-min window as above
        {"event_id": "3", "timestamp": "2026-09-06T14:07:00"},  # next window
    ]
    files = write_batches(events, str(tmp_path), batch_minutes=5)

    assert len(files) == 2
    names = sorted(f.split("/")[-1] for f in files)
    assert names == ["events_20260906_1400.jsonl", "events_20260906_1405.jsonl"]

    first_window = [f for f in files if "1400" in f][0]
    with open(first_window) as f:
        lines = [json.loads(line) for line in f if line.strip()]
    assert {e["event_id"] for e in lines} == {"1", "2"}
