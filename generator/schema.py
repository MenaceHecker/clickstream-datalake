"""
schema.py

Defines the clickstream event schema and the reference data pools (users,
products, countries, device types) that event_generator.py draws from.

Keeping this separate from event_generator.py means the schema can be
reused later (Phase 6 ETL validation, Phase 7 query column references)
without importing generation logic.
"""

from dataclasses import dataclass, asdict
from typing import Optional
import uuid

# --- Event schema -----------------------------------------------------

EVENT_TYPES = [
    "page_view",
    "product_view",
    "search",
    "add_to_cart",
    "checkout_start",
    "purchase",
]

DEVICE_TYPES = ["mobile", "desktop", "tablet"]

# Weighted so mobile dominates, matching typical e-commerce traffic mix.
DEVICE_TYPE_WEIGHTS = [0.55, 0.35, 0.10]

REFERRERS = [
    "google_organic",
    "google_ads",
    "direct",
    "email_campaign",
    "social_instagram",
    "social_facebook",
    "affiliate",
]

COUNTRIES = [
    "US", "GB", "CA", "DE", "FR", "AU", "IN", "BR", "JP", "MX",
]

CATEGORIES = [
    "electronics", "apparel", "home_goods", "beauty", "sporting_goods",
    "toys", "books", "grocery",
]


@dataclass
class Product:
    product_id: str
    category: str
    price: float


@dataclass
class ClickstreamEvent:
    event_id: str
    event_type: str
    user_id: str
    session_id: str
    timestamp: str  # ISO8601
    product_id: Optional[str]
    category: Optional[str]
    price: Optional[float]
    device_type: str
    referrer: str
    country: str
    discount_code: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def new_id() -> str:
    """Shorthand for a fresh UUID4 string, used for event/user/session ids."""
    return str(uuid.uuid4())