"""Normalization: currency, dates, availability, numbers, whitespace.

Each normalizer returns (value, note). A non-empty note means the raw input was ambiguous.
"""
import re
from datetime import datetime

CURRENCY_TOKENS = {
    "₹": "INR", "inr": "INR", "rs": "INR", "rs.": "INR",
    "$": "USD", "usd": "USD", "€": "EUR", "eur": "EUR", "£": "GBP", "gbp": "GBP",
}

# Static reference rates for cross-currency comparisons in the demo; production reads a rates API.
FX_TO_INR = {"INR": 1.0, "USD": 83.0, "EUR": 90.0, "GBP": 105.0}


def clean_text(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def normalize_price(raw: str | None):
    """'₹ 7,499/night' -> {'amount': 7499.0, 'currency': 'INR', 'amount_inr': 7499.0}"""
    text = clean_text(raw)
    if not text:
        return None, "price missing"
    lowered = text.lower()
    currency, note = None, ""
    for token, code in CURRENCY_TOKENS.items():
        if token in lowered:
            currency = code
            break
    if currency is None:
        currency, note = "INR", "currency not shown; assumed INR"
    # Indian lakh grouping (1,23,456) and western grouping both collapse by removing commas.
    nums = re.findall(r"\d[\d,]*(?:\.\d+)?", text)
    if not nums:
        return None, f"no number in price text '{text}'"
    if len(nums) > 1:
        note = (note + "; " if note else "") + f"multiple numbers in '{text}', used first"
    amount = float(nums[0].replace(",", ""))
    if "k" in lowered and amount < 1000:
        amount *= 1000
    return {"amount": amount, "currency": currency,
            "amount_inr": round(amount * FX_TO_INR[currency], 2), "raw": text}, note


DATE_FORMATS = ["%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%dT%H:%M:%S"]


def normalize_date(raw: str | None):
    text = clean_text(raw)
    if not text:
        return None, "date missing"
    candidates = [text]
    candidates += re.findall(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2})?", text)
    candidates += re.findall(r"\d{1,2} [A-Za-z]{3,9} \d{4}", text)
    candidates += re.findall(r"[A-Za-z]{3} \d{1,2}, \d{4}", text)
    candidates += re.findall(r"\d{1,2}[/-]\d{1,2}[/-]\d{4}", text)
    for c in candidates:
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(c.strip(), fmt).date().isoformat(), ""
            except ValueError:
                continue
    return text, f"unparsed date '{text}'"


def normalize_availability(raw: str | None):
    text = clean_text(raw).lower()
    if not text:
        return None, "availability missing"
    if any(k in text for k in ("sold out", "unavailable", "no rooms", "not available", "out of stock")):
        return {"status": "sold_out", "rooms_left": 0}, ""
    m = re.search(r"(\d+)\s*(rooms?|left)", text)
    if m:
        n = int(m.group(1))
        return {"status": "limited" if n <= 3 else "available", "rooms_left": n}, ""
    if "available" in text or "book now" in text or "in stock" in text:
        return {"status": "available", "rooms_left": None}, ""
    return {"status": "unknown", "rooms_left": None}, f"unrecognized availability '{text}'"


def normalize_int(raw: str | None):
    text = clean_text(raw)
    m = re.search(r"-?\d[\d,]*", text)
    if not m:
        return None, f"no integer in '{text}'"
    return int(m.group(0).replace(",", "")), ""


LOCATION_ALIASES = {"bombay": "Mumbai", "bengaluru": "Bangalore", "new delhi": "Delhi", "panaji": "Goa"}


def normalize_location(raw: str | None) -> str:
    text = clean_text(raw)
    return LOCATION_ALIASES.get(text.lower(), text.title() if text.islower() else text)


NORMALIZERS = {
    "price": normalize_price,
    "date": normalize_date,
    "availability": normalize_availability,
    "int": normalize_int,
}
