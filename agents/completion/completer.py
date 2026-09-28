"""Completion: turns classified changes into an action-oriented summary (what changed, why it matters,
evidence, confidence, owner), alerts, a CSV export and follow-up items.

The template summary is always produced and grounded in the records. When an LLM is configured it
may rewrite 'why_it_matters' and the headline, but evidence, numbers and owners always come from the
data, never from the model.
"""
import csv
import os

from backend.config import settings
from backend.services import llm

OWNERS = {
    "competitor_offers": "Growth",
    "hotel_pricing": "Pricing & Revenue",
    "campaign_page": "Marketing Ops",
    "partner_updates": "Partner Ops",
    "travel_trends": "Business Strategy",
    "flight_fares": "Pricing & Revenue",
    "flight_booking": "Travel Desk",
    "hotel_listings": "Pricing & Revenue",
    "book_listings": "Growth",
    "train_availability": "Rail Desk",
    "activity_listings": "Experiences",
    "review_watch": "Partner Ops",
    "advisory_watch": "Trust & Safety",
    "hotel_booking": "Travel Desk",
}


def _fmt(v):
    if isinstance(v, (int, float)):
        return f"₹{v:,.0f}" if v >= 100 else str(v)
    if isinstance(v, dict):
        return v.get("offer_name") or v.get("hotel") or v.get("title") or v.get("headline") or v.get("destination") or "record"
    return str(v)


def describe(c) -> str:
    if c.change_type == "new":
        return f"New: {c.entity}"
    if c.change_type == "removed":
        return f"Withdrawn: {c.entity}"
    if c.change_type in ("price_up", "price_down"):
        arrow = "up" if c.change_type == "price_up" else "down"
        return f"{c.entity}: price {arrow} {abs(c.delta_pct):.1f}% ({_fmt(c.before)} to {_fmt(c.after)})"
    if c.change_type in ("demand_up", "demand_down"):
        return f"{c.entity}: demand index {c.before} to {c.after} ({c.delta_pct:+.0f}%)"
    if c.change_type == "availability":
        return f"{c.entity}: availability {c.before} to {c.after}"
    if c.change_type == "copy_changed":
        return f"{c.entity}: {c.field} changed from '{_fmt(c.before)}' to '{_fmt(c.after)}'"
    return f"{c.entity}: {c.change_type.replace('_', ' ')} ({c.field})"


def _why(template, material):
    ups = sum(1 for c in material if c.change_type == "price_up")
    downs = sum(1 for c in material if c.change_type == "price_down")
    if template == "hotel_pricing":
        parts = []
        if downs:
            parts.append(f"{downs} hotel rate cut(s) may undercut our listed rates for the same stay date")
        if ups:
            parts.append(f"{ups} rate increase(s) open room to hold or raise our price")
        if any(c.change_type == "availability" for c in material):
            parts.append("inventory tightening signals demand pressure for these dates")
        return "; ".join(parts) or "Pricing position changed for tracked hotels."
    if template == "competitor_offers":
        return ("Competitor offer movement affects our price perception on the same destinations; "
                "new or withdrawn offers change what customers compare us against.")
    if template == "campaign_page":
        return "Landing page copy, CTA or placement changed; campaign messaging and tracking may need to follow."
    if template in ("flight_fares", "flight_booking"):
        return "Fare movement on this route changes how our flight prices compare; large drops may need a pricing response."
    if template == "hotel_listings":
        return "Search-result prices and cancellation terms are what customers compare; shifts affect conversion."
    if template == "train_availability":
        return "Seat availability moving between AVL, RAC and waitlist changes what we can sell and when to push rail bundles."
    if template == "activity_listings":
        return "Activity prices and cancellation terms affect package margins and upsell offers."
    if template == "review_watch":
        return "New or negative reviews can signal service problems at a partner hotel before they hit our own ratings."
    if template == "advisory_watch":
        return "Advisory level and visa changes affect what destinations we can promote and what customers must be told."
    if template == "book_listings":
        return "Catalogue price and stock changes on the monitored site."
    if template == "partner_updates":
        return "Partner policy or operational updates can affect listings, cancellation terms and customer promises."
    return "Demand signal movement can inform where to place campaign budget and inventory."


def complete(run, task, changes, decision, records, outcome=None, kind="monitor") -> dict:
    outcome = outcome or {}
    material = [c for c in changes if c.classification == "material"]
    owner = OWNERS.get(task.template, task.owner_team)
    avg_conf = round(sum(r["confidence"] for r in records) / len(records), 2) if records else 0.0

    if decision.is_baseline:
        headline = f"Baseline captured: {len(records)} records from {len({r['source_url'] for r in records})} source(s)"
        why = "First run for this workflow. Future runs will be compared against this snapshot."
    elif not material:
        headline = f"No material change across {len(records)} tracked records"
        why = "Movements detected were below thresholds or formatting-only."
    else:
        headline = f"{len(material)} material change(s) detected"
        why = _why(task.template, material)

    if kind == "transaction":
        if outcome.get("booking_ref") and outcome.get("chosen_hotel"):
            headline = f"Booked {outcome['chosen_hotel']}, {outcome.get('chosen_room', '')}: ref {outcome['booking_ref']}, {outcome.get('total', '')}"
            why = (f"Cheapest free-cancellation hotel and room were selected for {outcome.get('nights', '?')} nights in "
                   f"{str(outcome.get('city', '')).title()}. The booking was confirmed after human approval.")
        elif outcome.get("booking_ref"):
            headline = f"Booked {outcome.get('origin', '')} to {outcome.get('destination', '')}: ref {outcome['booking_ref']}, {outcome.get('total', '')}"
            why = (f"Cheapest of {outcome.get('options_compared', '?')} options was selected ({outcome.get('chosen_option', '')[:90]}). "
                   "The booking was confirmed after human approval.")
        elif "declined" in outcome:
            headline = f"Not booked: {outcome['declined']}"
            why = "The agent prepared the booking and stopped before the irreversible step because it was not approved."
    evidence = [{"statement": describe(c), "source_url": c.source_url, "confidence": c.confidence,
                 "classification": c.classification} for c in material[:25]]
    actions = []
    if material:
        actions.append(f"{owner}: review {len(material)} change(s) and decide on response")
    if decision.needs_review:
        actions.append("Reviewer: confirm flagged records before any external action")
    for c in material:
        if c.change_type == "price_down" and (c.delta_pct or 0) <= -10:
            actions.append(f"Pricing: check parity for {c.entity}")
    if kind == "transaction" and outcome.get("booking_ref"):
        actions.insert(0, f"Share booking {outcome['booking_ref']} with the traveller")
    body = {
        "outcome": outcome,
        "kind": kind,
        "what_changed": [describe(c) for c in material] or ["Nothing material"],
        "why_it_matters": why,
        "evidence": evidence,
        "owner": owner,
        "confidence": avg_conf,
        "needs_human_confirmation": decision.needs_review,
        "review_reasons": decision.review_reasons,
        "recommended_actions": actions,
        "counts": {
            "records": len(records),
            "material": len(material),
            "noise": sum(1 for c in changes if c.classification == "noise"),
            "formatting": sum(1 for c in changes if c.classification == "formatting"),
            "missing_data": sum(1 for c in changes if c.classification == "missing_data"),
        },
    }
    generator, cost = "template", 0.0
    if material and kind == "monitor":
        res = llm.complete_json(
            system=("You write concise operations summaries for a travel company's growth team. Use only the "
                    "facts given. Return {\"headline\": str (max 14 words), \"why_it_matters\": str (max 45 words)}."),
            user=f"Workflow: {task.name}\nOwner: {owner}\nChanges:\n" + "\n".join(body["what_changed"][:20]))
        if res and isinstance(res.data.get("headline"), str) and isinstance(res.data.get("why_it_matters"), str):
            headline, body["why_it_matters"] = res.data["headline"][:160], res.data["why_it_matters"][:400]
            generator, cost = "llm", res.cost_usd

    alerts = []
    if material:
        alerts.append({"channel": "dashboard", "team": owner, "message": headline})
        if any(abs(c.delta_pct or 0) >= 10 for c in material) or task.template == "partner_updates":
            alerts.append({"channel": "alert_queue", "team": owner, "message": headline, "priority": "high"})
    if decision.needs_review:
        alerts.append({"channel": "review_queue", "team": "Reviewers", "message": "; ".join(decision.review_reasons)})

    os.makedirs(os.path.join(settings.snapshot_dir, "exports"), exist_ok=True)
    export_path = os.path.join(settings.snapshot_dir, "exports", f"{run.id}.csv")
    with open(export_path, "w", newline="", encoding="utf-8-sig") as f:  # BOM so Excel shows ₹ correctly
        w = csv.writer(f)
        w.writerow(["entity", "change_type", "classification", "field", "before", "after", "delta_pct", "confidence", "source_url"])
        for c in changes:
            w.writerow([c.entity, c.change_type, c.classification, c.field, _fmt(c.before) if c.before is not None else "",
                        _fmt(c.after) if c.after is not None else "", c.delta_pct, c.confidence, c.source_url])
    return {"headline": headline, "body": body, "generator": generator, "alerts": alerts,
            "export_path": export_path, "cost_usd": cost}
