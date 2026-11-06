"""GET /api/patients/{id}/overview — the patient page's eight reads in one call.

Every part must be exactly what its own route answers: the console seeds its
per-resource caches from this payload, and a component reading a seeded cache
must see the same bytes it would have fetched itself.
"""

OVERVIEW_PARTS = {
    "detail", "care_metrics", "next_steps", "plan", "checkins", "timeline", "messages", "wearables",
}


def test_overview_is_the_individual_endpoints_verbatim(client):
    r = client.get("/api/patients/reyes/overview")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == OVERVIEW_PARTS
    for part, path in (
        ("detail", "/api/patients/reyes"),
        ("care_metrics", "/api/patients/reyes/care-metrics"),
        ("plan", "/api/patients/reyes/plan"),
        ("checkins", "/api/patients/reyes/checkins"),
        ("timeline", "/api/patients/reyes/timeline"),
        ("messages", "/api/patients/reyes/messages"),
        ("wearables", "/api/patients/reyes/wearables"),
    ):
        assert body[part] == client.get(path).json(), part
    # generated_at is the clock at the moment of the call; the steps are the contract
    steps = client.get("/api/patients/reyes/next-steps").json()
    assert body["next_steps"]["steps"] == steps["steps"]
    assert body["next_steps"]["generated_at"]


def test_overview_of_an_unknown_patient_is_404(client):
    assert client.get("/api/patients/nobody/overview").status_code == 404
