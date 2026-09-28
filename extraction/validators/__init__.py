"""Post-parse validation: plausibility bounds and stale-content checks. Adjusts confidence in place."""
from datetime import date

from extraction.schemas import Record

PRICE_BOUNDS_INR = {
    "hotel_pricing": (500, 300_000),
    "competitor_offers": (1_000, 1_000_000),
}


def validate(records: list[Record], schema_name: str) -> list[Record]:
    lo, hi = PRICE_BOUNDS_INR.get(schema_name, (0, float("inf")))
    today = date.today().isoformat()
    for r in records:
        price = r.fields.get("price")
        if isinstance(price, dict) and not (lo <= price["amount_inr"] <= hi):
            r.confidence = round(max(0, r.confidence - 0.3), 2)
            r.validation_notes.append(f"price {price['amount_inr']:.0f} INR outside plausible range {lo}-{hi}")
        validity = r.fields.get("validity")
        if isinstance(validity, str) and len(validity) == 10 and validity < today:
            r.validation_notes.append(f"offer validity {validity} already expired; possibly stale page")
            r.confidence = round(max(0, r.confidence - 0.1), 2)
        avail = r.fields.get("availability")
        if isinstance(avail, dict) and avail.get("status") == "sold_out" and isinstance(price, dict):
            r.validation_notes.append("sold out but price shown; price may be a stale teaser")
    return records
