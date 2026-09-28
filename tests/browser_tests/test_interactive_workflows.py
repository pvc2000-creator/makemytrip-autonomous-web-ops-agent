"""Real-browser tests: need Chromium (python -m playwright install chromium). Skipped otherwise."""
import time

import pytest

from tests.conftest import wait_run

pw = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module", autouse=True)
def need_chromium():
    try:
        with pw.sync_playwright() as p:
            p.chromium.launch().close()
    except Exception:
        pytest.skip("Chromium not installed")


def task(api, template):
    return next(t for t in api.get("/api/tasks").json() if t["template"] == template)


def wait_state(api, run_id, states, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        r = api.get(f"/api/runs/{run_id}").json()
        if r["state"] in states:
            return r
        time.sleep(0.3)
    raise AssertionError(f"stuck in {r['state']}")


def test_booking_waits_for_approval_then_books(api):
    rid = api.post("/api/runs", json={"task_id": task(api, "flight_booking")["id"], "options": {"speed": "fast"}}).json()["run_id"]
    wait_state(api, rid, {"awaiting_input"})
    live = api.get(f"/api/runs/{rid}/live").json()
    assert live["seq"] > 10 and live["control"]["awaiting_input"]["message"].startswith("Book this flight")
    assert api.get(f"/api/runs/{rid}/frames/1.jpg").headers["content-type"] == "image/jpeg"
    assert api.post(f"/api/runs/{rid}/input", json={"approve": True}, headers={"x-role": "creator"}).status_code == 403
    assert api.post(f"/api/runs/{rid}/input", json={"approve": True}, headers={"x-role": "reviewer"}).status_code == 200
    r = wait_state(api, rid, {"completed", "pending_review", "failed"})
    assert r["state"] == "completed", r["error"]
    assert r["outcome"]["booking_ref"].startswith("SR") and r["outcome"]["options_compared"] >= 1
    assert r["summary"]["headline"].startswith("Booked")


def test_declined_booking_does_not_confirm(api):
    rid = api.post("/api/runs", json={"task_id": task(api, "flight_booking")["id"], "options": {"speed": "fast"}}).json()["run_id"]
    wait_state(api, rid, {"awaiting_input"})
    api.post(f"/api/runs/{rid}/input", json={"approve": False, "note": "Over budget"})
    r = wait_state(api, rid, {"completed", "pending_review", "failed"})
    assert "booking_ref" not in r["outcome"] and r["outcome"]["declined"] == "Over budget"
    assert r["summary"]["headline"].startswith("Not booked")


def test_pause_and_stop(api):
    rid = api.post("/api/runs", json={"task_id": task(api, "hotel_listings")["id"], "options": {"speed": "slow", "step_mode": True}}).json()["run_id"]
    wait_state(api, rid, {"browser_execution"})
    time.sleep(2)
    s1 = api.get(f"/api/runs/{rid}/live").json()
    assert s1["control"]["paused"]
    time.sleep(1.5)
    assert api.get(f"/api/runs/{rid}/live").json()["seq"] == s1["seq"]  # nothing happens while paused
    api.post(f"/api/runs/{rid}/control", json={"action": "stop"})
    r = wait_state(api, rid, {"stopped", "failed", "completed"})
    assert r["state"] == "stopped"


def test_hotel_search_filters_and_paginates(api):
    rid = api.post("/api/runs", json={"task_id": task(api, "hotel_listings")["id"], "options": {"speed": "fast"}}).json()["run_id"]
    r = wait_run(api, rid, timeout=60)
    assert r["state"] in ("completed", "pending_review")
    assert len(r["records"]) == 12 and all(x["fields"]["cancellation"] == "Free cancellation" for x in r["records"])
    assert len(r["snapshots"]) >= 2  # page 1 and page 2


def test_custom_workflow_and_payment_field_guard(api):
    base = task(api, "hotel_pricing")["target_urls"][0].split("/mock")[0]
    steps = [{"tool": "navigate", "target": base + "/mock/travel", "purpose": "open"},
             {"tool": "dismiss_popups", "args": {"selectors": ["#accept-cookies"]}, "purpose": "cookies"},
             {"tool": "fill", "args": {"selector": "#from", "value": "Pune"}, "purpose": "type"},
             {"tool": "assert_text", "args": {"text": "Where to next"}, "purpose": "check"}]
    t = api.post("/api/tasks", json={"name": "Custom smoke", "template": "custom", "objective": "custom steps smoke test",
                                      "inputs": {"steps": steps}}).json()
    r = wait_run(api, api.post("/api/runs", json={"task_id": t["id"], "options": {"speed": "fast"}}).json()["run_id"])
    assert r["state"] in ("completed", "pending_review"), r["error"]
    from agents.browser_execution.runner import SENSITIVE
    assert SENSITIVE.search("#card-number") and SENSITIVE.search("cvv") and not SENSITIVE.search("#from")


def test_transactions_cannot_be_scheduled(api):
    r = api.post("/api/tasks", json={"name": "Nightly booking", "template": "flight_booking", "objective": "should be rejected",
                                      "schedule": "daily"})
    assert r.status_code == 422 and "on demand" in str(r.json())


def test_hotel_booking_picks_room_and_removes_addon(api):
    rid = api.post("/api/runs", json={"task_id": task(api, "hotel_booking")["id"], "options": {"speed": "fast"}}).json()["run_id"]
    wait_state(api, rid, {"awaiting_input"}, timeout=90)
    msg = api.get(f"/api/runs/{rid}/live").json()["control"]["awaiting_input"]["message"]
    assert msg.startswith("Book ") and "room" in msg.lower() and "₹" in msg
    api.post(f"/api/runs/{rid}/input", json={"approve": True})
    r = wait_state(api, rid, {"completed", "pending_review", "failed"})
    o = r["outcome"]
    assert o["booking_ref"].startswith("SH") and o["chosen_hotel"] and o["chosen_room"]
    # airport pickup (₹899) was unticked: total = room price + 12% tax
    assert abs(o["total_value"] - round(o["chosen_room_price"] * 1.12)) <= 1


def test_flight_approval_message_is_concise(api):
    rid = api.post("/api/runs", json={"task_id": task(api, "flight_booking")["id"], "options": {"speed": "fast"}}).json()["run_id"]
    wait_state(api, rid, {"awaiting_input"}, timeout=90)
    msg = api.get(f"/api/runs/{rid}/live").json()["control"]["awaiting_input"]["message"]
    assert "check-in" not in msg and "·" in msg
    api.post(f"/api/runs/{rid}/control", json={"action": "stop"})
    assert wait_state(api, rid, {"stopped", "failed", "completed"})["state"] == "stopped"


@pytest.mark.parametrize("template,min_records", [("train_availability", 7), ("activity_listings", 4),
                                                   ("review_watch", 6), ("advisory_watch", 7)])
def test_new_monitoring_sites(api, template, min_records):
    rid = api.post("/api/runs", json={"task_id": task(api, template)["id"], "options": {"speed": "fast"}}).json()["run_id"]
    r = wait_run(api, rid, timeout=90)
    assert r["state"] in ("completed", "pending_review"), r["error"]
    assert len(r["records"]) >= min_records
    assert all(x["confidence"] >= 0.7 for x in r["records"])


def test_review_watch_detects_new_reviews(api):
    t = task(api, "review_watch")
    wait_run(api, api.post("/api/runs", json={"task_id": t["id"], "options": {"speed": "fast"}}).json()["run_id"], timeout=90)
    api.post("/mock/advance")
    r = wait_run(api, api.post("/api/runs", json={"task_id": t["id"], "options": {"speed": "fast"}}).json()["run_id"], timeout=90)
    assert sum(1 for c in r["comparisons"] if c["change_type"] == "new") >= 2
