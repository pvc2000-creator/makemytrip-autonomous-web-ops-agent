from extraction.normalizers import normalize_availability, normalize_date, normalize_price
from extraction.parsers import parse
from extraction.schemas import get_schema


def test_price_formats():
    for raw in ["₹ 7,499", "INR 7499", "Rs.7,499/night"]:
        v, note = normalize_price(raw)
        assert v["amount_inr"] == 7499 and v["currency"] == "INR" and note == ""
    v, note = normalize_price("7,499")
    assert v["amount_inr"] == 7499 and "assumed INR" in note
    assert normalize_price("$120")[0]["amount_inr"] == 120 * 83
    assert normalize_price("")[0] is None


def test_dates_and_availability():
    assert normalize_date("Valid till 03 Oct 2026")[0] == "2026-10-03"
    assert normalize_date("2026-10-10")[0] == "2026-10-10"
    assert normalize_date("soon")[1].startswith("unparsed")
    assert normalize_availability("Sold out")[0]["status"] == "sold_out"
    assert normalize_availability("Only 2 rooms left")[0] == {"status": "limited", "rooms_left": 2}


HOTEL = '<body data-city="goa" data-stay-date="2026-10-10"><div class="hotel"><h3 class="hotel-name">A</h3><div class="price">₹ 5,000</div><div class="availability">8 rooms available</div><div class="occupancy">2 adults</div></div></body>'
HOTEL_REDESIGN = '<body data-city="goa" data-stay-date="2026-10-10"><section class="property-card"><h3 class="property-title">A</h3><span class="rate-amount">₹ 5,000</span><em class="status">8 rooms available</em></section></body>'


def test_parser_primary_selectors_full_confidence():
    recs, warns = parse(HOTEL, "u", get_schema("hotel_pricing"))
    assert len(recs) == 1 and recs[0].confidence == 1.0 and not warns
    assert recs[0].fields["price"]["amount_inr"] == 5000 and recs[0].fields["city"] == "Goa"


def test_layout_drift_lowers_confidence_and_warns():
    recs, warns = parse(HOTEL_REDESIGN, "u", get_schema("hotel_pricing"))
    assert recs and recs[0].confidence < 0.7
    assert any(w.startswith("layout_changed") for w in warns)
    # same entity key as the original layout so comparison still lines up
    assert recs[0].entity_key == parse(HOTEL, "u", get_schema("hotel_pricing"))[0][0].entity_key


def test_duplicates_are_removed():
    html = '<body data-competitor="x">' + '<div class="offer-card"><h3 class="offer-title">O</h3><span class="destination">Goa</span><div class="price">₹ 9,999</div></div>' * 2 + "</body>"
    recs, warns = parse(html, "u", get_schema("competitor_offers"))
    assert len(recs) == 1 and any("duplicate" in w for w in warns)


def test_unrecognised_page_yields_warning_not_garbage():
    recs, warns = parse("<html><body><p>Maintenance</p></body></html>", "u", get_schema("hotel_pricing"))
    assert recs == [] and warns[0].startswith("no_items")
