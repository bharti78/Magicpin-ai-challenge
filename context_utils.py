from __future__ import annotations

from datetime import datetime
from typing import Any


def _safe_get(obj: dict | None, *keys: str, default: Any = None) -> Any:
    cur = obj or {}
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


def owner_name(merchant: dict) -> str:
    return _safe_get(merchant, "identity", "owner_first_name", default="there")


def business_name(merchant: dict) -> str:
    return _safe_get(merchant, "identity", "name", default="your business")


def locality(merchant: dict) -> str:
    return _safe_get(merchant, "identity", "locality", default="")


def city(merchant: dict) -> str:
    return _safe_get(merchant, "identity", "city", default="")


def salutation(merchant: dict, category: dict) -> str:
    slug = category.get("slug", "")
    first = owner_name(merchant)
    if slug == "dentists" and first != "there":
        return f"Dr. {first}"
    if first != "there":
        return first
    return business_name(merchant)


def uses_hindi(merchant: dict, customer: dict | None = None) -> bool:
    langs = _safe_get(merchant, "identity", "languages", default=[]) or []
    if "hi" in langs:
        return True
    pref = _safe_get(customer, "identity", "language_pref", default="") or ""
    return "hi" in pref.lower()


def active_offers(merchant: dict) -> list[str]:
    return [
        o.get("title", "")
        for o in merchant.get("offers", [])
        if o.get("status") == "active" and o.get("title")
    ]


def first_active_offer(merchant: dict, category: dict) -> str:
    offers = active_offers(merchant)
    if offers:
        return offers[0]
    catalog = category.get("offer_catalog") or []
    if catalog:
        return catalog[0].get("title", "")
    return ""


def digest_item(category: dict, item_id: str | None) -> dict | None:
    if not item_id:
        return None
    for item in category.get("digest", []):
        if item.get("id") == item_id:
            return item
    return None


def digest_by_kind(category: dict, kind: str) -> dict | None:
    for item in category.get("digest", []):
        if item.get("kind") == kind:
            return item
    return None


def peer_ctr(category: dict) -> float:
    return float(_safe_get(category, "peer_stats", "avg_ctr", default=0.03))


def peer_rating(category: dict) -> float:
    return float(_safe_get(category, "peer_stats", "avg_rating", default=4.0))


def peer_reviews(category: dict) -> int:
    return int(_safe_get(category, "peer_stats", "avg_reviews", default=50))


def performance(merchant: dict) -> dict:
    return merchant.get("performance") or {}


def signals(merchant: dict) -> list[str]:
    return merchant.get("signals") or []


def customer_name(customer: dict | None) -> str:
    return _safe_get(customer, "identity", "name", default="there")


def months_since(date_str: str | None) -> int | None:
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        now = datetime(2026, 4, 26)
        return max(0, (now.year - dt.year) * 12 + now.month - dt.month)
    except ValueError:
        return None


def format_pct(value: float, signed: bool = True) -> str:
    pct = int(round(abs(value) * 100))
    if signed and value < 0:
        return f"-{pct}%"
    if signed and value > 0:
        return f"+{pct}%"
    return f"{pct}%"


def send_as(trigger: dict, customer: dict | None) -> str:
    if trigger.get("scope") == "customer" or customer is not None:
        return "merchant_on_behalf"
    return "vera"


def suppression_key(trigger: dict) -> str:
    return trigger.get("suppression_key") or trigger.get("id", "unknown")


def taboo_words(category: dict) -> set[str]:
    voice = category.get("voice") or {}
    taboos = voice.get("vocab_taboo") or voice.get("taboos") or []
    return {t.lower() for t in taboos}


def strip_taboos(text: str, category: dict) -> str:
    result = text
    for word in taboo_words(category):
        if len(word) < 4:
            continue
        import re

        result = re.sub(re.escape(word), "", result, flags=re.IGNORECASE)
    return " ".join(result.split())
