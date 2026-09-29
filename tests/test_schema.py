from schema import (
    DEVICE_TYPES,
    DEVICE_TYPE_WEIGHTS,
    ClickstreamEvent,
    new_id,
)


def test_device_type_weights_match_device_types():
    # random.choices(DEVICE_TYPES, weights=DEVICE_TYPE_WEIGHTS) raises
    # ValueError at runtime if these two lists drift out of sync. This
    # catches that at test time instead of mid-generation.
    assert len(DEVICE_TYPES) == len(DEVICE_TYPE_WEIGHTS)


def test_new_id_returns_unique_strings():
    ids = {new_id() for _ in range(1000)}
    assert len(ids) == 1000


def test_clickstream_event_to_dict_includes_all_fields():
    event = ClickstreamEvent(
        event_id="e1",
        event_type="page_view",
        user_id="u1",
        session_id="s1",
        timestamp="2026-09-06T14:30:00",
        product_id=None,
        category=None,
        price=None,
        device_type="mobile",
        referrer="direct",
        country="US",
    )
    d = event.to_dict()
    assert d["event_id"] == "e1"
    assert d["discount_code"] is None
    assert set(d.keys()) == {
        "event_id", "event_type", "user_id", "session_id", "timestamp",
        "product_id", "category", "price", "device_type", "referrer",
        "country", "discount_code",
    }
