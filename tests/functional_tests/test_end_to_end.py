from tests.conftest import wait_run


def tasks(c):
    return {t["template"]: t for t in c.get("/api/tasks").json()}


def test_seeded_workflows(api):
    t = tasks(api)
    assert {"competitor_offers", "hotel_pricing", "flight_booking", "hotel_listings", "book_listings"} <= set(t)


def test_baseline_then_change_detection(api):
    t = tasks(api)["competitor_offers"]
    r1 = wait_run(api, api.post("/api/runs", json={"task_id": t["id"]}).json()["run_id"])
    assert r1["state"] in ("completed", "pending_review")
    keys = [x["entity_key"] for x in r1["records"]]
    assert len(keys) >= 6 and len(keys) == len(set(keys))  # the duplicated card is removed
    api.post("/mock/advance")
    r2 = wait_run(api, api.post("/api/runs", json={"task_id": t["id"]}).json()["run_id"])
    material = [c for c in r2["comparisons"] if c["classification"] == "material"]
    assert material  # prices, promotions, withdrawals or launches move every market day
    s = r2["summary"]["body"]
    assert s["owner"] == "Growth" and s["evidence"] and all(e["source_url"] for e in s["evidence"])
    assert api.get(f"/api/runs/{r2['id']}/export.csv").status_code == 200


def test_sensitive_plan_waits_for_approval_and_rbac(api):
    t = tasks(api)["hotel_pricing"]
    r = wait_run(api, api.post("/api/runs", json={"task_id": t["id"]}).json()["run_id"])
    assert r["state"] == "awaiting_approval"
    denied = api.post(f"/api/plans/{r['plan_id']}/approve", json={"approve": True}, headers={"x-role": "creator"})
    assert denied.status_code == 403
    ok = api.post(f"/api/plans/{r['plan_id']}/approve", json={"approve": True}, headers={"x-role": "reviewer"})
    assert ok.status_code == 200 and r["id"] in ok.json()["resumed_runs"]
    r = wait_run(api, r["id"])
    assert r["state"] in ("completed", "pending_review") and len(r["records"]) == 7


def test_intake_validation_blocks_non_allowlisted(api):
    bad = api.post("/api/tasks", json={"name": "x" * 5, "template": "hotel_pricing", "objective": "watch prices everywhere",
                                        "target_urls": ["https://not-allowed.example/deals"]})
    assert bad.status_code == 422 and "allowlist" in str(bad.json())


def test_blocked_source_fails_visibly(api):
    base = api.get("/api/tasks").json()[0]["target_urls"][0].split("/mock")[0]
    t = api.post("/api/tasks", json={"name": "Blocked", "template": "competitor_offers", "objective": "blocked source test",
                                      "target_urls": [base + "/mock/blocked"]}).json()
    r = wait_run(api, api.post("/api/runs", json={"task_id": t["id"]}).json()["run_id"])
    assert r["state"] == "failed" and "browser_blocked" in r["error"]


def test_feedback_signs_off_review(api):
    runs = [r for r in api.get("/api/runs").json() if r["state"] == "pending_review"]
    if not runs:
        return
    r = api.get(f"/api/runs/{runs[0]['id']}").json()
    fb = api.post("/api/feedback", json={"run_id": r["id"], "target_type": "summary", "target_id": r["summary"]["id"],
                                         "verdict": "accepted"}, headers={"x-role": "reviewer"})
    assert fb.status_code == 201
    assert api.get(f"/api/runs/{r['id']}").json()["state"] == "completed"


def test_metrics(api):
    m = api.get("/api/metrics").json()
    assert m["runs_total"] >= 3 and "browser_blocked" in m["failure_reasons"]
