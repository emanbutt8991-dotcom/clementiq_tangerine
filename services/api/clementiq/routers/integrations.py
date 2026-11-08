"""Admin-only integration keys (Settings → Account & Integrations).

Keys are write-only from the browser's point of view: the API stores them encrypted and only ever
returns a masked hint (last four characters) plus where the active value came from.
"""
from __future__ import annotations

import smtplib
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import secrets_store
from ..auth import Principal, require_admin
from ..config import get_settings
from ..db import get_db
from ..repository import audit

router = APIRouter(prefix="/api/admin/integrations", tags=["integrations"])


class SecretsPatch(BaseModel):
    # name -> new value; "" or null clears the saved value (reverts to the environment variable)
    values: dict[str, str | None] = Field(default_factory=dict)


@router.get("")
def list_integration_settings(p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    return {"fields": secrets_store.describe(db), "encryption": _encryption_note()}


@router.put("")
def save_integration_settings(body: SecretsPatch, p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    unknown = sorted(set(body.values) - set(secrets_store.BY_NAME))
    if unknown:
        raise HTTPException(422, f"Unknown setting: {', '.join(unknown)}")
    try:
        changed = secrets_store.save(db, body.values, p.sub)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    audit(db, p.sub, "integration_settings_update", None, keys=changed)  # names only, never values
    return {"changed": changed, "fields": secrets_store.describe(db), "encryption": _encryption_note()}


@router.post("/test/{group}")
def test_integration(group: str, p: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    secrets_store.refresh(force=True)
    tests = {"gemini": _test_gemini, "snowflake": _test_snowflake, "news_api": _test_news,
             "alpha_vantage": _test_alpha_vantage, "email": _test_email}
    if group not in tests:
        raise HTTPException(404, "Unknown integration")
    try:
        ok, message = tests[group]()
    except Exception as exc:  # noqa: BLE001
        ok, message = False, f"{exc.__class__.__name__}: {str(exc)[:200]}"
    audit(db, p.sub, "integration_test", None, group=group, ok=ok)
    return {"group": group, "ok": ok, "message": message}


def _encryption_note() -> str:
    return ("Fernet (AES-128 + HMAC-SHA256) with SECRETS_ENCRYPTION_KEY" if get_settings().secrets_encryption_key
            else "Fernet (AES-128 + HMAC-SHA256) with a key derived from JWT_SECRET")


def _test_gemini() -> tuple[bool, str]:
    s = get_settings()
    if not s.gemini_api_key:
        return False, "No Gemini API key set"
    r = httpx.get(f"https://generativelanguage.googleapis.com/v1beta/models/{s.gemini_model}",
                  headers={"x-goog-api-key": s.gemini_api_key}, timeout=s.http_timeout_s)
    if r.status_code == 200:
        return True, f"Key accepted; model {s.gemini_model} is available"
    msg = (r.json().get("error", {}) or {}).get("message", "") if r.headers.get("content-type", "").startswith("application/json") else ""
    return False, f"Gemini HTTP {r.status_code}: {msg[:200]}"


def _test_snowflake() -> tuple[bool, str]:
    from ..ai.snowflake import SnowflakeUnavailable, cortex_complete
    try:
        out = cortex_complete("Reply with the single word OK.", max_tokens=5)
    except SnowflakeUnavailable as exc:
        return False, str(exc)
    return True, f"Cortex answered with {out['model']}"


def _test_news() -> tuple[bool, str]:
    s = get_settings()
    if not s.news_api_key:
        return False, "No NewsAPI key set"
    r = httpx.get("https://newsapi.org/v2/top-headlines", params={"country": "us", "pageSize": 1},
                  headers={"X-Api-Key": s.news_api_key, "User-Agent": "ClementIQ"}, timeout=s.http_timeout_s)
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code == 200 and data.get("status") == "ok":
        return True, "Key accepted"
    return False, f"NewsAPI HTTP {r.status_code}: {str(data.get('message', ''))[:200]}"


def _test_alpha_vantage() -> tuple[bool, str]:
    s = get_settings()
    if not s.alpha_vantage_key:
        return False, "No Alpha Vantage key set"
    r = httpx.get("https://www.alphavantage.co/query",
                  params={"function": "GLOBAL_QUOTE", "symbol": "IBM", "apikey": s.alpha_vantage_key}, timeout=s.http_timeout_s)
    data = r.json()
    if (data.get("Global Quote") or {}).get("05. price"):
        return True, "Key accepted (IBM quote returned)"
    note = data.get("Error Message") or data.get("Information") or data.get("Note") or "no quote returned"
    return False, str(note)[:200]


def _test_email() -> tuple[bool, str]:
    s = get_settings()
    if not s.smtp_host:
        return False, "No SMTP host set"
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.http_timeout_s) as smtp:
        smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password or "")
    return True, "Connected and signed in (no email sent)"
