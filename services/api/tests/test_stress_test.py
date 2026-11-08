"""Stress Test + Needs Attention (ported from Tony's branch): staff-only portfolio list, per-account
obligations check, and the mortgage-renewal twist card."""


def test_needs_attention_staff_only(client, judge, admin, customer_1001):
    for h in (judge, admin):
        r = client.get("/api/insights/needs-attention?limit=5", headers=h)
        assert r.status_code == 200
        d = r.json()
        assert set(d["counts"]) >= {"short", "behind", "thin", "green_under_formula"}
        assert d["matching"] == d["total"] and len(d["items"]) <= 5
        assert "not credit decisions" in d["use"]
        for it in d["items"]:
            assert it["flags"] and set(it["flags"]) <= {"short", "behind", "thin"}
    assert client.get("/api/insights/needs-attention", headers=customer_1001).status_code == 403


def test_needs_attention_flag_filter(client, judge):
    d = client.get("/api/insights/needs-attention?flag=thin&limit=500", headers=judge).json()
    assert all("thin" in it["flags"] for it in d["items"])
    assert d["matching"] == d["counts"]["thin"]
    assert client.get("/api/insights/needs-attention?flag=bogus", headers=judge).status_code == 422


def test_obligations(client, judge, customer_1001):
    r = client.get("/api/accounts/1001/obligations", headers=judge)
    assert r.status_code == 200
    o = r.json()
    assert o["status"] in ("covered", "tight", "short", "unknown")
    assert abs(o["fixed_total"] - sum(f["amount"] for f in o["fixed_payments"])) < 0.02
    if o["balance"] is not None:
        assert abs(o["left_after_fixed"] - (o["balance"] - o["fixed_total"])) < 0.02
    # A customer can read their own account's check.
    assert client.get("/api/accounts/1001/obligations", headers=customer_1001).status_code == 200


def test_mortgage_renewal_preset(client, judge):
    presets = client.get("/api/shocks/presets", headers=judge).json()["presets"]
    m = next(p for p in presets if p["id"] == "mortgage_renewal")
    assert m["judging"] and m["components"] == [{"type": "loan_payment_increase", "pct": 6}]


def test_new_features_are_staff_entitlements(client, judge, customer_1001):
    assert {"stressTest", "needsAttention"} <= set(client.get("/api/auth/me", headers=judge).json()["features_allowed"])
    r = client.patch("/api/settings", headers=customer_1001, json={"dashboard": {"features": {"stressTest": True}}})
    assert r.status_code == 403
