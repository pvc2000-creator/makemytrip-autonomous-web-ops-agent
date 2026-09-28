"""Workflow library. Each template defines its kind, the inputs it needs and how to turn a task into
browser steps. Tools available to steps (all enforced by the runner and the browser policy):

  navigate, dismiss_popups, wait_for, click, fill, select, check, uncheck, press, scroll,
  extract, paginate, pick_best, capture, assert_text, screenshot, approval,
  compare, summarize, route   (post-processing, run by the orchestrator)
"""
from extraction.schemas import get_schema

TOOLS = {
    "navigate": "Open a URL (allowlist, rate limit and page cap enforced)",
    "dismiss_popups": "Close cookie banners and modal overlays",
    "wait_for": "Wait until content is present",
    "click": "Click an element by CSS selector or visible text",
    "fill": "Type a value into a field (refuses payment, OTP and password fields)",
    "select": "Choose an option in a dropdown",
    "check": "Tick a checkbox", "uncheck": "Untick a checkbox",
    "press": "Press a key", "scroll": "Scroll the page",
    "extract": "Capture the page and extract structured records with the workflow schema",
    "paginate": "Extract, then follow the next-page link, up to a page limit",
    "pick_best": "Compare listed options by price and select the best one",
    "capture": "Read a value from the page into a variable",
    "assert_text": "Check the page shows expected text",
    "screenshot": "Save a full-page evidence screenshot",
    "approval": "Pause and ask a person to approve before continuing",
    "compare": "Compare extracted records with the previous run",
    "summarize": "Write the grounded summary",
    "route": "Deliver results to dashboards, alerts and review queues",
}
POPUPS = ["#accept-cookies", ".cookie-banner button", "#onetrust-accept-btn-handler", "button[aria-label='Close']"]

B = "{BASE}"  # replaced with PUBLIC_BASE_URL when seeding

WORKFLOWS = {
    "competitor_offers": {"kind": "monitor", "label": "Competitor offers", "schema": "competitor_offers",
                          "description": "Watch competitor holiday offer pages for price, promotion and validity changes."},
    "hotel_pricing": {"kind": "monitor", "label": "Hotel pricing", "schema": "hotel_pricing",
                      "description": "Track nightly rates and availability for specific hotels."},
    "campaign_page": {"kind": "monitor", "label": "Campaign page", "schema": "campaign_page",
                      "description": "Verify headline, offer copy, CTA and placement on landing pages."},
    "partner_updates": {"kind": "monitor", "label": "Partner updates", "schema": "partner_updates",
                        "description": "Follow partner update feeds and route new notices."},
    "travel_trends": {"kind": "monitor", "label": "Travel trends", "schema": "travel_trends",
                      "description": "Scan destination demand signals."},
    "hotel_listings": {"kind": "monitor", "label": "Hotel search and filter", "schema": "hotel_listings",
                       "description": "Open a hotel search, apply filters and sorting, read every results page.",
                       "inputs": [{"name": "city", "label": "City", "default": "goa"},
                                  {"name": "max_pages", "label": "Pages to read", "default": "3"},
                                  {"name": "free_cancellation", "label": "Free cancellation only (yes/no)", "default": "yes"}],
                       "default_urls": [B + "/mock/travel/hotels?city={{city}}"]},
    "flight_fares": {"kind": "monitor", "label": "Flight fare search", "schema": "flight_results",
                     "description": "Fill the flight search form, apply filters and record every fare for the route.",
                     "inputs": [{"name": "origin", "label": "From", "default": "Pune"},
                                {"name": "destination", "label": "To", "default": "Goa"},
                                {"name": "date", "label": "Date (YYYY-MM-DD)", "default": ""},
                                {"name": "passengers", "label": "Travellers", "default": "1"},
                                {"name": "nonstop", "label": "Non-stop only (yes/no)", "default": "no"}],
                     "default_urls": [B + "/mock/travel"]},
    "flight_booking": {"kind": "transaction", "label": "Flight booking", "schema": "flight_results",
                       "description": "Search, compare fares, pick the cheapest, fill traveller details and book after your approval.",
                       "inputs": [{"name": "origin", "label": "From", "default": "Pune"},
                                  {"name": "destination", "label": "To", "default": "Goa"},
                                  {"name": "date", "label": "Date (YYYY-MM-DD)", "default": ""},
                                  {"name": "passengers", "label": "Travellers", "default": "1"},
                                  {"name": "traveller_name", "label": "Traveller name", "default": "Test Traveller"},
                                  {"name": "traveller_email", "label": "Traveller email", "default": "ops-test@example.com"},
                                  {"name": "nonstop", "label": "Non-stop only (yes/no)", "default": "yes"}],
                       "default_urls": [B + "/mock/travel"]},
    "train_availability": {"kind": "monitor", "label": "Train seat availability", "schema": "train_results",
                           "description": "Search trains on a route and record seat availability (AVL/RAC/WL) and fares for a class.",
                           "inputs": [{"name": "origin", "label": "From station", "default": "Pune"},
                                      {"name": "destination", "label": "To station", "default": "Delhi"},
                                      {"name": "date", "label": "Date (YYYY-MM-DD)", "default": ""},
                                      {"name": "travel_class", "label": "Class (SL, 3A, 2A, 1A)", "default": "3A"}],
                           "default_urls": [B + "/mock/rail"]},
    "activity_listings": {"kind": "monitor", "label": "Activities and tours", "schema": "activity_listings",
                          "description": "Open a city's things-to-do page, filter by category, sort by price and read every page.",
                          "inputs": [{"name": "city", "label": "City (goa, jaipur, dubai)", "default": "goa"},
                                     {"name": "category", "label": "Category (all, tours, water, adventure, food, nightlife)", "default": "water"},
                                     {"name": "max_pages", "label": "Pages to read", "default": "2"}],
                          "default_urls": [B + "/mock/activities/{{city}}"]},
    "review_watch": {"kind": "monitor", "label": "Hotel reviews watch", "schema": "hotel_reviews",
                     "description": "Read the newest guest reviews for a hotel and flag new or negative ones.",
                     "inputs": [{"name": "hotel", "label": "Hotel page slug", "default": "sea-breeze-resort"},
                                {"name": "max_pages", "label": "Pages to read", "default": "2"}],
                     "default_urls": [B + "/mock/reviews/{{hotel}}"]},
    "advisory_watch": {"kind": "monitor", "label": "Travel advisory watch", "schema": "travel_advisories",
                       "description": "Track travel advisory levels and visa rules for destinations we sell.",
                       "default_urls": [B + "/mock/advisories"]},
    "hotel_booking": {"kind": "transaction", "label": "Hotel booking", "schema": "hotel_listings",
                      "description": "Search hotels, filter to free cancellation, pick the cheapest hotel and room, fill guest details and book after your approval.",
                      "inputs": [{"name": "city", "label": "City", "default": "goa"},
                                 {"name": "nights", "label": "Nights", "default": "2"},
                                 {"name": "guest_name", "label": "Lead guest name", "default": "Test Guest"},
                                 {"name": "guest_email", "label": "Guest email", "default": "ops-test@example.com"},
                                 {"name": "free_cancellation", "label": "Free cancellation only (yes/no)", "default": "yes"}],
                      "default_urls": [B + "/mock/travel/hotels?city={{city}}&nights={{nights}}"]},
    "book_listings": {"kind": "monitor", "label": "Catalogue scan (books.toscrape.com)", "schema": "book_listings",
                      "description": "Real public practice site: open a category and read listings across pages.",
                      "inputs": [{"name": "category", "label": "Category name", "default": "Travel"},
                                 {"name": "max_pages", "label": "Pages to read", "default": "2"}],
                      "default_urls": ["https://books.toscrape.com/"]},
    "custom": {"kind": "monitor", "label": "Custom steps", "schema": None,
               "description": "Write your own step list (JSON) for any allowlisted site."},
}


def step(tool, purpose, target=None, **args):
    return {"tool": tool, "target": target, "args": args, "purpose": purpose}


def _yes(v):
    return str(v).strip().lower() in ("yes", "y", "true", "1", "on")


def _monitor_page(url, schema):
    return [step("navigate", "Open the source page", url),
            step("dismiss_popups", "Clear cookie banners and overlays", url, selectors=POPUPS),
            step("wait_for", "Confirm the content loaded", url, selectors=schema.item_selectors, timeout_s=15),
            step("extract", f"Read {', '.join(list(schema.fields)[:5])}", url)]


def build_steps(task) -> tuple[list[dict], str | None]:
    t = task.template
    inp = dict(task.inputs or {})
    urls = task.target_urls or []
    if t in ("competitor_offers", "hotel_pricing", "campaign_page", "partner_updates", "travel_trends"):
        schema = get_schema(t)
        steps = [s for u in urls for s in _monitor_page(u, schema)]
    elif t == "hotel_listings":
        start = urls[0]
        steps = [step("navigate", "Open the hotel search results", start),
                 step("dismiss_popups", "Accept the cookie banner", start, selectors=POPUPS)]
        if _yes(inp.get("free_cancellation", "yes")):
            steps.append(step("check", "Filter to free cancellation", start, selector="#free-cancel"))
        steps += [step("select", "Sort by lowest price", start, selector="#sort", value="price"),
                  step("wait_for", "Wait for listings", start, selectors=[".hotel-card"]),
                  step("paginate", "Read every results page", start, next_selector=".pagination a.next",
                       max_pages=int(inp.get("max_pages") or 3))]
    elif t in ("flight_fares", "flight_booking"):
        start = urls[0]
        steps = [step("navigate", "Open the travel site", start),
                 step("dismiss_popups", "Accept the cookie banner", start, selectors=POPUPS),
                 step("fill", "Enter the origin city", start, selector="#from", value="{{origin}}"),
                 step("fill", "Enter the destination city", start, selector="#to", value="{{destination}}"),
                 step("fill", "Set the travel date", start, selector="#date", value="{{date}}"),
                 step("select", "Set the number of travellers", start, selector="#pax", value="{{passengers}}"),
                 step("click", "Search flights", start, selector="#search", label="search"),
                 step("wait_for", "Wait for results", start, selectors=[".flight-card"])]
        if _yes(inp.get("nonstop", "no")):
            steps.append(step("check", "Filter to non-stop flights", start, selector="#filter-nonstop"))
        steps.append(step("select", "Sort by cheapest", start, selector="#sort", value="price"))
        steps.append(step("extract", "Record all fares on the results page", start))
        if t == "flight_booking":
            steps += [step("pick_best", "Pick the cheapest flight", start, items=".flight-card", value=".fare",
                           click=".select-btn", strategy="min",
                           label_selector=[".airline", ".flight-no", ".depart", ".arrive", ".stops", ".fare"]),
                      step("fill", "Enter traveller name", start, selector="#name", value="{{traveller_name}}"),
                      step("fill", "Enter traveller email", start, selector="#email", value="{{traveller_email}}"),
                      step("uncheck", "Remove the pre-ticked travel insurance add-on", start, selector="#insurance"),
                      step("click", "Continue to the review page", start, selector="#continue", label="continue"),
                      step("capture", "Read the total price", start, selector=".total-fare", name="total", kind="price"),
                      step("screenshot", "Save the review page as evidence", start, caption="Review page saved"),
                      step("approval", "Ask a person to approve the booking", start,
                           message="Book this flight for {{traveller_name}}: {{chosen_option}}. Total to pay {{total}}."),
                      step("click", "Confirm the booking", start, selector="#confirm-booking", label="confirm booking"),
                      step("assert_text", "Check the booking was confirmed", start, text="Booking confirmed"),
                      step("capture", "Read the booking reference", start, selector=".booking-ref", name="booking_ref"),
                      step("screenshot", "Save the confirmation as evidence", start, caption="Confirmation saved")]
    elif t == "train_availability":
        start = urls[0]
        steps = [step("navigate", "Open the railway booking site", start),
                 step("dismiss_popups", "Accept the cookie banner", start, selectors=POPUPS),
                 step("fill", "Enter the from station", start, selector="#rail-from", value="{{origin}}"),
                 step("fill", "Enter the to station", start, selector="#rail-to", value="{{destination}}"),
                 step("fill", "Set the journey date", start, selector="#rail-date", value="{{date}}"),
                 step("select", "Choose the travel class", start, selector="#rail-class", value="{{travel_class}}"),
                 step("click", "Find trains", start, selector="#find-trains", label="find trains"),
                 step("wait_for", "Wait for the train list", start, selectors=[".train-card"]),
                 step("extract", "Record availability and fare for every train", start)]
    elif t == "activity_listings":
        start = urls[0]
        steps = [step("navigate", "Open the things-to-do page", start),
                 step("dismiss_popups", "Accept the cookie banner", start, selectors=POPUPS),
                 step("select", "Filter by category", start, selector="#category", value="{{category}}"),
                 step("select", "Sort by lowest price", start, selector="#sort", value="price"),
                 step("wait_for", "Wait for results", start, selectors=[".activity-card"]),
                 step("paginate", "Read every results page", start, next_selector=".pagination a.next",
                      max_pages=int(inp.get("max_pages") or 2))]
    elif t == "review_watch":
        start = urls[0]
        steps = [step("navigate", "Open the hotel's reviews", start),
                 step("dismiss_popups", "Accept the cookie banner", start, selectors=POPUPS),
                 step("select", "Sort newest first", start, selector="#sort", value="newest"),
                 step("wait_for", "Wait for reviews", start, selectors=["article.review"]),
                 step("paginate", "Read the latest review pages", start, next_selector=".pagination a.next",
                      max_pages=int(inp.get("max_pages") or 2))]
    elif t == "advisory_watch":
        steps = [s for u in urls for s in _monitor_page(u, get_schema("travel_advisories"))]
    elif t == "hotel_booking":
        start = urls[0]
        steps = [step("navigate", "Open hotel search results", start),
                 step("dismiss_popups", "Accept the cookie banner", start, selectors=POPUPS)]
        if _yes(inp.get("free_cancellation", "yes")):
            steps.append(step("check", "Filter to free cancellation", start, selector="#free-cancel"))
        steps += [step("select", "Sort by lowest price", start, selector="#sort", value="price"),
                  step("wait_for", "Wait for listings", start, selectors=[".hotel-card"]),
                  step("extract", "Record the hotel prices on this page", start),
                  step("pick_best", "Pick the cheapest hotel", start, items=".hotel-card", value=".price", click=".view-btn",
                       strategy="min", label_selector=".hotel-name", save_as="chosen_hotel"),
                  step("pick_best", "Pick the cheapest room", start, items=".room-card", value=".room-price", click=".choose-room",
                       strategy="min", label_selector=".room-name", save_as="chosen_room"),
                  step("fill", "Enter the lead guest name", start, selector="#guest-name", value="{{guest_name}}"),
                  step("fill", "Enter the guest email", start, selector="#guest-email", value="{{guest_email}}"),
                  step("uncheck", "Remove the pre-ticked airport pickup add-on", start, selector="#pickup"),
                  step("click", "Continue to the review page", start, selector="#continue", label="continue"),
                  step("capture", "Read the total price", start, selector=".total-fare", name="total", kind="price"),
                  step("screenshot", "Save the review page as evidence", start, caption="Review page saved"),
                  step("approval", "Ask a person to approve the booking", start,
                       message="Book {{chosen_hotel}} ({{chosen_room}}) for {{guest_name}}, {{nights}} nights. Total to pay {{total}}."),
                  step("click", "Confirm the booking", start, selector="#confirm-booking", label="confirm booking"),
                  step("assert_text", "Check the booking was confirmed", start, text="Booking confirmed"),
                  step("capture", "Read the booking reference", start, selector=".booking-ref", name="booking_ref"),
                  step("screenshot", "Save the confirmation as evidence", start, caption="Confirmation saved")]
    elif t == "book_listings":
        start = urls[0]
        steps = [step("navigate", "Open the catalogue", start),
                 step("click", "Open the category", start, text=inp.get("category") or "Travel", exact=True, label="category"),
                 step("wait_for", "Wait for listings", start, selectors=["article.product_pod"]),
                 step("paginate", "Read listings across pages", start, next_selector="li.next a",
                      max_pages=int(inp.get("max_pages") or 2))]
    elif t == "custom":
        steps = [dict(s, args=s.get("args") or {}, purpose=s.get("purpose") or s["tool"]) for s in inp.get("steps", [])]
        if not steps:
            raise ValueError("Custom workflows need at least one step")
        bad = [s["tool"] for s in steps if s["tool"] not in TOOLS]
        if bad:
            raise ValueError(f"Unknown tools: {', '.join(bad)}")
    else:
        raise ValueError(f"Unknown workflow type '{t}'")
    steps += [step("compare", "Compare with the previous run"), step("summarize", "Write the summary"),
              step("route", f"Deliver to {task.owner_team}")]
    for n, s in enumerate(steps, 1):
        s["order"] = n
    return steps, WORKFLOWS[t]["schema"] or (inp.get("schema") if t == "custom" else None)


def catalog():
    return [{"name": k, **{kk: vv for kk, vv in v.items()}} for k, v in WORKFLOWS.items()]


def resolved_inputs(task) -> dict:
    """Task inputs merged with template defaults; empty date means two weeks from today."""
    from datetime import date, timedelta
    out = {i["name"]: i.get("default", "") for i in WORKFLOWS.get(task.template, {}).get("inputs", [])}
    out.update({k: v for k, v in (task.inputs or {}).items() if v not in (None, "")})
    if "date" in out and not out["date"]:
        out["date"] = (date.today() + timedelta(days=14)).isoformat()
    if "passengers" in out:
        out["passengers"] = str(out["passengers"] or "1")
    return out
