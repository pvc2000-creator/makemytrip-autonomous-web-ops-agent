"""Reasoning loop: compares current records with the prior snapshot and decides what happens next.

Change classes
  material      business-relevant movement (price beyond threshold, offer launched/withdrawn,
                availability flip, copy/CTA/placement change, new partner update, demand swing)
  noise         movement below threshold
  formatting    same value, different presentation ('₹ 7,499' vs 'INR 7499')
  missing_data  a field or entity disappeared while the source looked degraded

Decisions
  rerun         a source returned zero records but had records last time (possible transient failure)
  review        low confidence, large price swings, layout drift, or policy warnings
"""
from dataclasses import dataclass, field

from backend.config import settings

TREND_THRESHOLD_PCT = 15.0


@dataclass
class Change:
    entity_key: str
    entity: str
    change_type: str
    classification: str
    field: str | None
    before: object
    after: object
    delta_pct: float | None
    source_url: str
    confidence: float


@dataclass
class Decision:
    changes: list[Change]
    needs_rerun_urls: list[str] = field(default_factory=list)
    needs_review: bool = False
    review_reasons: list[str] = field(default_factory=list)
    is_baseline: bool = False


def _norm(v):
    if isinstance(v, dict):
        return v.get("amount_inr", v.get("status"))
    return str(v).strip().lower() if v is not None else None


def compare(current: list[dict], prior: list[dict], compare_fields: list[str], template: str) -> list[Change]:
    cur = {r["entity_key"]: r for r in current}
    old = {r["entity_key"]: r for r in prior}
    out: list[Change] = []
    for key, r in cur.items():
        if key not in old:
            out.append(Change(key, r["entity"], "new", "material", None, None, r["fields"], None, r["source_url"], r["confidence"]))
            continue
        p = old[key]
        for f in compare_fields:
            a, b = p["fields"].get(f), r["fields"].get(f)
            conf = min(r["confidence"], p["confidence"])
            if a == b:
                continue
            if b is None and a is not None:
                out.append(Change(key, r["entity"], "field_missing", "missing_data", f, a, None, None, r["source_url"], conf))
                continue
            if f == "price" and isinstance(a, dict) and isinstance(b, dict):
                if a["amount_inr"] == b["amount_inr"]:
                    out.append(Change(key, r["entity"], "format_changed", "formatting", f, a["raw"], b["raw"], 0.0, r["source_url"], conf))
                    continue
                d = (b["amount_inr"] - a["amount_inr"]) / a["amount_inr"] * 100
                cls = "material" if abs(d) >= settings.price_change_threshold_pct else "noise"
                out.append(Change(key, r["entity"], "price_up" if d > 0 else "price_down", cls, f,
                                  a["amount_inr"], b["amount_inr"], round(d, 2), r["source_url"], conf))
                continue
            if f == "availability" and isinstance(a, dict) and isinstance(b, dict):
                if a.get("status") != b.get("status"):
                    out.append(Change(key, r["entity"], "availability", "material", f, a["status"], b["status"], None, r["source_url"], conf))
                elif a.get("rooms_left") != b.get("rooms_left"):
                    out.append(Change(key, r["entity"], "availability", "noise", f, a.get("rooms_left"), b.get("rooms_left"), None, r["source_url"], conf))
                continue
            if f == "search_index" and isinstance(a, int) and isinstance(b, int) and a:
                d = (b - a) / a * 100
                cls = "material" if abs(d) >= TREND_THRESHOLD_PCT else "noise"
                out.append(Change(key, r["entity"], "demand_up" if d > 0 else "demand_down", cls, f, a, b, round(d, 2), r["source_url"], conf))
                continue
            if _norm(a) == _norm(b):
                out.append(Change(key, r["entity"], "format_changed", "formatting", f, a, b, None, r["source_url"], conf))
            else:
                out.append(Change(key, r["entity"], "copy_changed", "material", f, a, b, None, r["source_url"], conf))
    for key, p in old.items():
        if key not in cur:
            out.append(Change(key, p["entity"], "removed", "material", None, p["fields"], None, None, p["source_url"], p["confidence"]))
    return out


def reason(current: list[dict], prior: list[dict], compare_fields: list[str], template: str,
           page_warnings: dict[str, list[str]], attempted_rerun: bool) -> Decision:
    if not prior:
        d = Decision(changes=[], is_baseline=True)
    else:
        d = Decision(changes=compare(current, prior, compare_fields, template))

    # A source that produced nothing now but had data before looks like a transient failure: rerun once.
    cur_urls = {r["source_url"] for r in current}
    prior_urls = {r["source_url"] for r in prior}
    missing_sources = prior_urls - cur_urls
    if missing_sources and not attempted_rerun:
        d.needs_rerun_urls = sorted(missing_sources)
    elif missing_sources:
        # after a rerun the source still yields nothing: its disappearances are not trustworthy removals
        for c in d.changes:
            if c.change_type == "removed" and c.source_url in missing_sources:
                c.classification, c.change_type = "missing_data", "source_empty"
        d.needs_review = True
        d.review_reasons.append(f"{len(missing_sources)} source(s) returned no records after a rerun")

    low = [r for r in current if r["confidence"] < settings.min_confidence]
    if low:
        d.needs_review = True
        d.review_reasons.append(f"{len(low)} record(s) below {settings.min_confidence:.0%} extraction confidence")
    layout = [u for u, ws in page_warnings.items() if any(w.startswith(("layout_changed", "no_items")) for w in ws)]
    if layout:
        d.needs_review = True
        d.review_reasons.append(f"Layout drift detected on {len(layout)} page(s); schema may need an update")
    big = [c for c in d.changes if c.delta_pct is not None and abs(c.delta_pct) >= 10 and c.field == "price"]
    if big:
        d.needs_review = True
        d.review_reasons.append(f"{len(big)} price move(s) of 10% or more; confirm before external action")
    return d
