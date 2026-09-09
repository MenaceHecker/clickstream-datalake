"""
event_generator.py

Generates realistic, funnel-shaped e-commerce clickstream data and writes
it locally as newline-delimited JSON (JSONL), batched into files that
simulate fixed time windows (default: 5 minutes each). No AWS calls here —
this phase proves the data is believable before anything touches S3.

Usage:
    python event_generator.py --events 5000
    python event_generator.py --events 200000 --batch-minutes 5 --out-dir output/
    python event_generator.py --events 5000 --start-hour-offset 3   # simulate a later hour

The funnel is deliberately lossy so downstream dashboards (Phase 8) tell a
believable story:
    page_view -> product_view -> add_to_cart -> checkout_start -> purchase
    100       -> ~40          -> ~15          -> ~10             -> ~7

Roughly halfway through a run, events start including a `discount_code`
field that didn't exist in earlier events. This is intentional — it gives
the Phase 6 Glue ETL job a real schema-evolution case to handle instead of
a hypothetical one.
"""

import argparse
import json
import os
import random
from datetime import datetime, timedelta, timezone

from faker import Faker

from schema import (
    ClickstreamEvent,
    Product,
    CATEGORIES,
    COUNTRIES,
    DEVICE_TYPES,
    DEVICE_TYPE_WEIGHTS,
    REFERRERS,
    new_id,
)

fake = Faker()

# Conditional stage-to-stage conversion rates, tuned so that starting from
# 100 page_views the expected counts land close to 40 / 15 / 10 / 7.
P_PRODUCT_VIEW_GIVEN_PAGE_VIEW = 0.40
P_ADD_TO_CART_GIVEN_PRODUCT_VIEW = 0.375
P_CHECKOUT_GIVEN_ADD_TO_CART = 0.667
P_PURCHASE_GIVEN_CHECKOUT = 0.70

# Fraction of sessions that throw in a search event before browsing.
P_SEARCH_EVENT = 0.30

# Discount codes only start appearing after this fraction of total events
# have been generated so this is what creates the schema-evolution case.
DISCOUNT_CODE_INTRODUCED_AT = 0.5
DISCOUNT_CODES = ["SAVE10", "WELCOME15", "FREESHIP", "VIP20"]


def build_product_catalog(n: int = 200) -> list[Product]:
    """Pre-generate a fixed catalog so product_ids repeat across sessions,
    the way a real catalog would."""
    catalog = []
    for _ in range(n):
        category = random.choice(CATEGORIES)
        price = round(fake.pyfloat(min_value=4.99, max_value=899.99, right_digits=2), 2)
        catalog.append(Product(product_id=str(fake.uuid4()), category=category, price=price))
    return catalog


def build_user_pool(n: int) -> list[str]:
    """Pre-generate a fixed pool of user_ids so some users appear in
    multiple sessions, rather than every session being a brand-new user."""
    return [str(fake.uuid4()) for _ in range(n)]


def pick_device_type() -> str:
    return random.choices(DEVICE_TYPES, weights=DEVICE_TYPE_WEIGHTS, k=1)[0]


def pick_country() -> str:
    # Fall back to our fixed list rather than Faker's full country pool so
    # results stay concentrated in a realistic e-commerce market mix.
    return random.choice(COUNTRIES)


def make_event(
    event_type: str,
    user_id: str,
    session_id: str,
    ts: datetime,
    device_type: str,
    referrer: str,
    country: str,
    product,
    total_generated_so_far: int,
    total_planned: int,
) -> dict:
    progress = total_generated_so_far / max(total_planned, 1)
    discount_code = None
    if event_type in ("add_to_cart", "checkout_start", "purchase"):
        if progress >= DISCOUNT_CODE_INTRODUCED_AT and random.random() < 0.35:
            discount_code = random.choice(DISCOUNT_CODES)

    event = ClickstreamEvent(
        event_id=new_id(),
        event_type=event_type,
        user_id=user_id,
        session_id=session_id,
        timestamp=ts.isoformat(),
        product_id=product.product_id if product else None,
        category=product.category if product else None,
        price=product.price if product else None,
        device_type=device_type,
        referrer=referrer,
        country=country,
        discount_code=discount_code,
    )

    d = event.to_dict()
    # Older events (before the schema-evolution point) shouldn't even have
    # the key present, not just null so that's the realistic case where a
    # field is genuinely new, not just sparsely populated.
    if discount_code is None and progress < DISCOUNT_CODE_INTRODUCED_AT:
        d.pop("discount_code", None)
    return d


def simulate_session(
    session_start: datetime,
    users: list[str],
    catalog: list[Product],
    total_generated_so_far: int,
    total_planned: int,
) -> list[dict]:
    """Simulate one browsing session through the funnel, returning the
    list of event dicts it produced (1 to 5 events)."""
    events = []
    user_id = random.choice(users)
    session_id = new_id()
    device_type = pick_device_type()
    referrer = random.choice(REFERRERS)
    country = pick_country()
    ts = session_start

    def emit(event_type: str, product=None):
        nonlocal ts, total_generated_so_far
        events.append(
            make_event(
                event_type, user_id, session_id, ts, device_type, referrer,
                country, product, total_generated_so_far, total_planned,
            )
        )
        total_generated_so_far += 1
        ts = ts + timedelta(seconds=random.randint(5, 90))

    # Every session starts with a page view.
    emit("page_view")

    if random.random() < P_SEARCH_EVENT:
        emit("search")

    if random.random() < P_PRODUCT_VIEW_GIVEN_PAGE_VIEW:
        product = random.choice(catalog)
        emit("product_view", product)

        if random.random() < P_ADD_TO_CART_GIVEN_PRODUCT_VIEW:
            emit("add_to_cart", product)

            if random.random() < P_CHECKOUT_GIVEN_ADD_TO_CART:
                emit("checkout_start", product)

                if random.random() < P_PURCHASE_GIVEN_CHECKOUT:
                    emit("purchase", product)

    return events


def generate(
    total_events: int,
    start_time: datetime,
    users: list[str],
    catalog: list[Product],
) -> list[dict]:
    """Keep simulating sessions until we've produced roughly total_events
    events, advancing simulated time as we go."""
    all_events: list[dict] = []
    current_time = start_time

    while len(all_events) < total_events:
        session_events = simulate_session(
            current_time, users, catalog, len(all_events), total_events,
        )
        all_events.extend(session_events)
        # Space sessions out by a few seconds of simulated time.
        current_time += timedelta(seconds=random.randint(1, 20))

    return all_events[:total_events]


def write_batches(events: list[dict], out_dir: str, batch_minutes: int) -> list[str]:
    """Group events into fixed-size simulated time windows and write each
    window to its own JSONL file, e.g. events_20260906_1400.jsonl"""
    os.makedirs(out_dir, exist_ok=True)
    batches: dict[str, list[dict]] = {}

    for event in events:
        ts = datetime.fromisoformat(event["timestamp"])
        window_start = ts.replace(
            minute=(ts.minute // batch_minutes) * batch_minutes, second=0, microsecond=0
        )
        key = window_start.strftime("%Y%m%d_%H%M")
        batches.setdefault(key, []).append(event)

    written = []
    for key, batch_events in sorted(batches.items()):
        filename = os.path.join(out_dir, f"events_{key}.jsonl")
        with open(filename, "w") as f:
            for e in batch_events:
                f.write(json.dumps(e) + "\n")
        written.append(filename)

    return written


def main():
    parser = argparse.ArgumentParser(description="Generate funnel-shaped clickstream events.")
    parser.add_argument("--events", type=int, default=5000, help="Total number of events to generate.")
    parser.add_argument("--out-dir", type=str, default="output", help="Directory to write JSONL batch files.")
    parser.add_argument("--batch-minutes", type=int, default=5, help="Size of each simulated time window / output file.")
    parser.add_argument("--users", type=int, default=500, help="Size of the simulated user pool.")
    parser.add_argument("--catalog-size", type=int, default=200, help="Size of the simulated product catalog.")
    parser.add_argument(
        "--start-hour-offset", type=int, default=0,
        help="Shift the simulated start time forward this many hours (useful for generating multiple, distinct hour partitions across separate runs).",
    )
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible runs.")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)
        Faker.seed(args.seed)

    start_time = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=args.start_hour_offset)

    print(f"Building catalog ({args.catalog_size} products) and user pool ({args.users} users)...")
    catalog = build_product_catalog(args.catalog_size)
    users = build_user_pool(args.users)

    print(f"Simulating funnel for ~{args.events} events starting at {start_time.isoformat()}...")
    events = generate(args.events, start_time, users, catalog)

    print(f"Writing batches (every {args.batch_minutes} min) to {args.out_dir}/ ...")
    files = write_batches(events, args.out_dir, args.batch_minutes)

    counts_by_type = {}
    for e in events:
        counts_by_type[e["event_type"]] = counts_by_type.get(e["event_type"], 0) + 1

    print(f"\nDone. {len(events)} events across {len(files)} files.")
    print("Funnel breakdown:")
    for event_type in ["page_view", "search", "product_view", "add_to_cart", "checkout_start", "purchase"]:
        print(f"  {event_type:16s} {counts_by_type.get(event_type, 0)}")


if __name__ == "__main__":
    main()