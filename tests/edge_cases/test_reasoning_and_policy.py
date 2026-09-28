from agents.reasoning_loop.reasoner import compare, reason
from backend.auth.policy import BrowserPolicy


def rec(key, price, conf=1.0, url="u", avail="available"):
    return {"entity_key": key, "entity": key, "source_url": url, "confidence": conf,
            "fields": {"price": {"amount_inr": price, "raw": f"₹ {price}"}, "availability": {"status": avail, "rooms_left": 5}}}


def test_price_threshold_noise_vs_material():
    ch = compare([rec("a", 102), rec("b", 110)], [rec("a", 100), rec("b", 100)], ["price"], "hotel_pricing")
    cls = {c.entity_key: c.classification for c in ch}
    assert cls == {"a": "noise", "b": "material"}


def test_formatting_only_change():
    cur = rec("a", 100); cur["fields"]["price"]["raw"] = "INR 100"
    ch = compare([cur], [rec("a", 100)], ["price"], "hotel_pricing")
    assert ch[0].classification == "formatting"


def test_new_removed_and_availability():
    ch = compare([rec("a", 100, avail="sold_out"), rec("n", 5)], [rec("a", 100), rec("gone", 1)], ["price", "availability"], "hotel_pricing")
    kinds = {(c.entity_key, c.change_type) for c in ch}
    assert ("n", "new") in kinds and ("gone", "removed") in kinds and ("a", "availability") in kinds


def test_reasoning_requests_rerun_then_marks_missing_data():
    prior = [rec("a", 100, url="u1"), rec("b", 100, url="u2")]
    d1 = reason([rec("a", 100, url="u1")], prior, ["price"], "hotel_pricing", {}, attempted_rerun=False)
    assert d1.needs_rerun_urls == ["u2"]
    d2 = reason([rec("a", 100, url="u1")], prior, ["price"], "hotel_pricing", {}, attempted_rerun=True)
    assert d2.needs_review and any(c.classification == "missing_data" for c in d2.changes)


def test_low_confidence_and_big_moves_route_to_review():
    d = reason([rec("a", 130, conf=0.4)], [rec("a", 100)], ["price"], "hotel_pricing", {}, False)
    assert d.needs_review and len(d.review_reasons) == 2


def test_policy_allowlist():
    p = BrowserPolicy()
    assert p.is_allowed("http://127.0.0.1:8000/mock/trends")
    assert not p.is_allowed("https://www.competitor.example/deals")
    assert not p.is_allowed("file:///etc/passwd")
