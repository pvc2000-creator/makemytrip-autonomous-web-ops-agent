"""Workflow-specific extraction schemas.

Each schema lists a primary CSS selector per field plus fallbacks. When the parser has to use a
fallback, confidence drops and a 'layout_changed' validation note is attached, so a page redesign
is flagged instead of silently producing bad data (CTO requirement).
"""
from pydantic import BaseModel, Field


class FieldSpec(BaseModel):
    selectors: list[str]
    attr: str | None = None          # read attribute instead of text
    kind: str = "text"               # text | price | date | int | availability
    required: bool = True


class ExtractionSchema(BaseModel):
    name: str
    item_selectors: list[str]        # first = primary, rest = fallbacks
    entity_fields: list[str]         # fields that form the stable entity key across runs
    fields: dict[str, FieldSpec]
    compare_fields: list[str]        # fields whose movement is meaningful
    page_level: bool = False         # one record per page (campaign pages)


class Record(BaseModel):
    entity_key: str
    entity: str
    fields: dict
    snippet: str
    source_url: str
    confidence: float = Field(ge=0, le=1)
    validation_notes: list[str] = []


F = FieldSpec

SCHEMAS: dict[str, ExtractionSchema] = {
    "competitor_offers": ExtractionSchema(
        name="competitor_offers",
        item_selectors=[".offer-card", "[data-offer]", "article.deal"],
        entity_fields=["competitor", "offer_name"],
        fields={
            "competitor": F(selectors=["[data-competitor]"], attr="data-competitor"),
            "offer_name": F(selectors=[".offer-title", ".deal-name", "h3"]),
            "destination": F(selectors=[".destination", "[data-destination]"]),
            "price": F(selectors=[".price", ".deal-price", "[data-price]"], kind="price"),
            "discount": F(selectors=[".discount", ".badge"], required=False),
            "validity": F(selectors=[".validity", "time"], kind="date", required=False),
            "cta": F(selectors=[".cta", "a.button", "button"], required=False),
        },
        compare_fields=["price", "discount", "validity", "cta"],
    ),
    "hotel_pricing": ExtractionSchema(
        name="hotel_pricing",
        item_selectors=[".hotel", ".property-card", "[data-hotel]"],
        entity_fields=["city", "hotel", "stay_date"],
        fields={
            "hotel": F(selectors=[".hotel-name", ".property-title", "h3"]),
            "city": F(selectors=["[data-city]"], attr="data-city"),
            "stay_date": F(selectors=["[data-stay-date]"], attr="data-stay-date", kind="date"),
            "price": F(selectors=[".price", ".rate-amount", "[data-rate]"], kind="price"),
            "availability": F(selectors=[".availability", ".rooms-left", ".status"], kind="availability"),
            "occupancy": F(selectors=[".occupancy"], required=False),
        },
        compare_fields=["price", "availability"],
    ),
    "campaign_page": ExtractionSchema(
        name="campaign_page",
        item_selectors=["main", "body"],
        entity_fields=["campaign"],
        page_level=True,
        fields={
            "campaign": F(selectors=["[data-campaign]"], attr="data-campaign"),
            "headline": F(selectors=["h1.headline", "h1"]),
            "offer_text": F(selectors=[".offer-text", ".hero p"]),
            "cta": F(selectors=[".cta", "a.button"]),
            "placement": F(selectors=["[data-position]"], attr="data-position", required=False),
            "validity": F(selectors=[".validity"], kind="date", required=False),
        },
        compare_fields=["headline", "offer_text", "cta", "placement", "validity"],
    ),
    "partner_updates": ExtractionSchema(
        name="partner_updates",
        item_selectors=["article.update", ".update-item"],
        entity_fields=["partner", "title"],
        fields={
            "partner": F(selectors=["[data-partner]"], attr="data-partner"),
            "title": F(selectors=["h3", ".update-title"]),
            "published": F(selectors=["time"], attr="datetime", kind="date"),
            "content": F(selectors=["p", ".body"]),
            "category": F(selectors=[".category"], required=False),
        },
        compare_fields=["content", "published"],
    ),
    "travel_trends": ExtractionSchema(
        name="travel_trends",
        item_selectors=["tr.signal", ".trend-row"],
        entity_fields=["destination"],
        fields={
            "destination": F(selectors=[".dest", "td:nth-of-type(1)"]),
            "search_index": F(selectors=[".index", "td:nth-of-type(2)"], kind="int"),
            "event": F(selectors=[".event", "td:nth-of-type(3)"], required=False),
            "trend": F(selectors=[".trend", "td:nth-of-type(4)"], required=False),
        },
        compare_fields=["search_index", "event"],
    ),
    "flight_results": ExtractionSchema(
        name="flight_results",
        item_selectors=[".flight-card", "[data-flight-id]"],
        entity_fields=["route", "date", "flight_no"],
        fields={
            "airline": F(selectors=[".airline"]),
            "flight_no": F(selectors=[".flight-no"]),
            "route": F(selectors=["[data-route]"], attr="data-route"),
            "date": F(selectors=["[data-date]"], attr="data-date", kind="date"),
            "depart": F(selectors=[".depart"]),
            "arrive": F(selectors=[".arrive"]),
            "stops": F(selectors=[".stops"]),
            "fare": F(selectors=[".fare"], kind="price"),
        },
        compare_fields=["fare", "stops", "depart"],
    ),
    "hotel_listings": ExtractionSchema(
        name="hotel_listings",
        item_selectors=[".hotel-card", ".hotel", ".property-card"],
        entity_fields=["city", "hotel", "stay_date"],
        fields={
            "hotel": F(selectors=[".hotel-name", "h3"]),
            "city": F(selectors=["[data-city]"], attr="data-city"),
            "stay_date": F(selectors=["[data-stay-date]"], attr="data-stay-date", kind="date"),
            "area": F(selectors=[".area"], required=False),
            "rating": F(selectors=[".rating"], required=False),
            "price": F(selectors=[".price", ".rate-amount"], kind="price"),
            "cancellation": F(selectors=[".cancel-policy"], required=False),
        },
        compare_fields=["price", "cancellation"],
    ),
    "train_results": ExtractionSchema(
        name="train_results",
        item_selectors=[".train-card"],
        entity_fields=["route", "date", "train_no", "travel_class"],
        fields={
            "train_name": F(selectors=[".train-name"]),
            "train_no": F(selectors=[".train-no"]),
            "route": F(selectors=["[data-route]"], attr="data-route"),
            "date": F(selectors=["[data-date]"], attr="data-date", kind="date"),
            "travel_class": F(selectors=["[data-travel-class]"], attr="data-travel-class"),
            "depart": F(selectors=[".depart"]),
            "arrive": F(selectors=[".arrive"]),
            "availability": F(selectors=[".class-avail.selected .avail"]),
            "fare": F(selectors=[".class-avail.selected .class-fare"], kind="price"),
        },
        compare_fields=["availability", "fare"],
    ),
    "activity_listings": ExtractionSchema(
        name="activity_listings",
        item_selectors=[".activity-card"],
        entity_fields=["city", "activity"],
        fields={
            "activity": F(selectors=[".activity-name"]),
            "city": F(selectors=["[data-city]"], attr="data-city"),
            "duration": F(selectors=[".activity-duration"], required=False),
            "rating": F(selectors=[".rating"], required=False),
            "reviews": F(selectors=[".reviews-count"], kind="int", required=False),
            "price": F(selectors=[".price"], kind="price"),
            "cancellation": F(selectors=[".free-cancel"], required=False),
        },
        compare_fields=["price", "cancellation"],
    ),
    "hotel_reviews": ExtractionSchema(
        name="hotel_reviews",
        item_selectors=["article.review", ".review"],
        entity_fields=["hotel", "review_id"],
        fields={
            "hotel": F(selectors=["[data-hotel]"], attr="data-hotel"),
            "review_id": F(selectors=["[data-review-id]"], attr="data-review-id"),
            "rating": F(selectors=[".review-rating"], kind="int"),
            "title": F(selectors=[".review-title"]),
            "reviewer": F(selectors=[".reviewer"], required=False),
            "published": F(selectors=["time"], attr="datetime", kind="date"),
            "text": F(selectors=[".review-text"]),
            "trip_type": F(selectors=[".trip-type"], required=False),
        },
        compare_fields=["rating", "text"],
    ),
    "travel_advisories": ExtractionSchema(
        name="travel_advisories",
        item_selectors=["article.advisory"],
        entity_fields=["country"],
        fields={
            "country": F(selectors=[".country"]),
            "level": F(selectors=[".level"]),
            "summary": F(selectors=[".summary"]),
            "visa": F(selectors=[".visa-rule"], required=False),
            "updated": F(selectors=["time.updated"], attr="datetime", kind="date"),
        },
        compare_fields=["level", "summary", "visa"],
    ),
    # books.toscrape.com: a public practice site built for scraping exercises
    "book_listings": ExtractionSchema(
        name="book_listings",
        item_selectors=["article.product_pod", ".product_pod"],
        entity_fields=["title"],
        fields={
            "title": F(selectors=["h3 a"], attr="title"),
            "price": F(selectors=[".price_color"], kind="price"),
            "availability": F(selectors=[".availability"], kind="availability"),
            "rating": F(selectors=["p.star-rating"], attr="class", required=False),
        },
        compare_fields=["price", "availability"],
    ),
}


def get_schema(name: str) -> ExtractionSchema:
    if name not in SCHEMAS:
        raise KeyError(f"No extraction schema named '{name}'")
    return SCHEMAS[name]
