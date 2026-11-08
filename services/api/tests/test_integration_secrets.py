"""API keys entered in Settings: admin-only, encrypted at rest, never returned in plaintext."""
from __future__ import annotations

from clementiq import models
from clementiq.config import get_settings
from clementiq.db import session_factory

KEY = "AIzaSyTEST-demo-key-0000-abcd"


def test_only_admin_can_read_or_write(client, judge, customer_1001):
    for h in (judge, customer_1001):
        assert client.get("/api/admin/integrations", headers=h).status_code == 403
        assert client.put("/api/admin/integrations", headers=h, json={"values": {"gemini_api_key": "x"}}).status_code == 403
    assert client.get("/api/admin/integrations").status_code == 401


def test_saved_key_is_encrypted_masked_applied_and_clearable(client, admin):
    r = client.put("/api/admin/integrations", headers=admin, json={"values": {"gemini_api_key": KEY}})
    assert r.status_code == 200, r.text
    assert KEY not in r.text
    field = next(f for f in r.json()["fields"] if f["name"] == "gemini_api_key")
    assert field["source"] == "settings" and field["display"] == "••••abcd"

    with session_factory()() as db:
        row = db.get(models.IntegrationSecret, "gemini_api_key")
        assert row is not None and KEY not in row.ciphertext

    # Applied live: the rest of the app sees the key without a restart.
    assert get_settings().gemini_api_key == KEY
    assert client.get("/api/settings", headers=admin).json()["integrations"]["gemini"] is True

    r = client.put("/api/admin/integrations", headers=admin, json={"values": {"gemini_api_key": ""}})
    field = next(f for f in r.json()["fields"] if f["name"] == "gemini_api_key")
    assert field["source"] == "unset"
    assert not get_settings().gemini_api_key


def test_unknown_names_rejected(client, admin):
    r = client.put("/api/admin/integrations", headers=admin, json={"values": {"jwt_secret": "pwned"}})
    assert r.status_code == 422
    assert get_settings().jwt_secret != "pwned"
