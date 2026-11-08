"""Integration keys entered from Settings, encrypted at rest.

Admins can paste API keys in Settings → Account & Integrations during a demo instead of editing
`.env` and restarting. Values are Fernet-encrypted in `integration_secrets`; a saved value overrides
the matching environment variable and clearing it reverts to the environment.

Every module reads keys through `get_settings()` at call time, so overrides are applied onto the
cached Settings object. Each process (two uvicorn workers, the monitoring worker) re-reads the table
at most every REFRESH_SECONDS, so a key saved through one worker reaches the others quickly.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings

log = logging.getLogger("clementiq.secrets")
REFRESH_SECONDS = 15.0
MAX_VALUE_LEN = 4000


@dataclass(frozen=True)
class Field:
    name: str          # Settings attribute
    env: str           # environment variable it overrides
    group: str         # integration it belongs to (also the Test button id)
    label: str
    secret: bool = True
    placeholder: str = ""


FIELDS: tuple[Field, ...] = (
    Field("gemini_api_key", "GEMINI_API_KEY", "gemini", "Gemini API key", placeholder="AIza…"),
    Field("gemini_model", "GEMINI_MODEL", "gemini", "Gemini model", secret=False, placeholder="gemini-flash-latest"),
    Field("snowflake_account_url", "SNOWFLAKE_ACCOUNT_URL", "snowflake", "Account URL", secret=False,
          placeholder="https://<org>-<account>.snowflakecomputing.com"),
    Field("snowflake_pat", "SNOWFLAKE_PAT", "snowflake", "Programmatic access token"),
    Field("snowflake_warehouse", "SNOWFLAKE_WAREHOUSE", "snowflake", "Warehouse", secret=False, placeholder="COMPUTE_WH"),
    Field("snowflake_model", "SNOWFLAKE_MODEL", "snowflake", "Insights model (SQL API)", secret=False, placeholder="mistral-large3"),
    Field("cortex_model", "CORTEX_MODEL", "snowflake", "WorldPulse model (Cortex REST)", secret=False,
          placeholder="claude-sonnet-4-6"),
    Field("news_api_key", "NEWS_API_KEY", "news_api", "NewsAPI.org key"),
    Field("alpha_vantage_key", "ALPHA_VANTAGE_KEY", "alpha_vantage", "Alpha Vantage key"),
    Field("smtp_host", "SMTP_HOST", "email", "SMTP host", secret=False, placeholder="smtp.gmail.com"),
    Field("smtp_user", "SMTP_USER", "email", "SMTP username", secret=False),
    Field("smtp_password", "SMTP_PASSWORD", "email", "SMTP password"),
    Field("smtp_from", "SMTP_FROM", "email", "From address", secret=False, placeholder="alerts@example.com"),
)
BY_NAME = {f.name: f for f in FIELDS}

_lock = threading.Lock()
_env_values: dict[str, Any] = {}     # values from the environment, captured before any override
_overridden: set[str] = set()        # names currently overridden from the database
_undecryptable: set[str] = set()
_last_refresh = 0.0


def _fernet() -> Fernet:
    s = get_settings()
    if s.secrets_encryption_key:
        return Fernet(s.secrets_encryption_key.encode())
    digest = hashlib.sha256(b"clementiq-integration-secrets:" + s.jwt_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def _capture_env() -> None:
    s = get_settings()
    for f in FIELDS:
        _env_values.setdefault(f.name, getattr(s, f.name))


def apply_overrides(db: Session) -> None:
    """Load every saved value and write it onto the live Settings object (env value when absent)."""
    from .models import IntegrationSecret

    global _last_refresh
    rows = db.execute(select(IntegrationSecret)).scalars().all()
    values: dict[str, str] = {}
    bad: set[str] = set()
    for row in rows:
        if row.name not in BY_NAME:
            continue
        try:
            values[row.name] = decrypt(row.ciphertext)
        except (InvalidToken, ValueError):
            bad.add(row.name)
    with _lock:
        _capture_env()
        s = get_settings()
        for f in FIELDS:
            # Same mechanism db.reset_engine uses; Settings has no assignment validation.
            s.__dict__[f.name] = values.get(f.name, _env_values[f.name])
        _overridden.clear()
        _overridden.update(values)
        _undecryptable.clear()
        _undecryptable.update(bad)
        _last_refresh = time.monotonic()
    if bad:
        log.warning("could not decrypt saved integration values %s; was JWT_SECRET or SECRETS_ENCRYPTION_KEY changed?",
                    sorted(bad))


def is_stale() -> bool:
    return time.monotonic() - _last_refresh > REFRESH_SECONDS


def refresh(force: bool = False) -> None:
    """Re-read overrides if stale. Never raises: a missing table (before migration) keeps env values."""
    if not force and not is_stale():
        return
    from .db import session_factory

    global _last_refresh
    try:
        with session_factory()() as db:
            apply_overrides(db)
    except Exception as exc:  # noqa: BLE001
        _last_refresh = time.monotonic()
        log.debug("integration overrides not loaded: %s", exc.__class__.__name__)


def save(db: Session, values: dict[str, str | None], actor: str) -> list[str]:
    """Upsert (non-empty) or delete (empty/None) overrides. Returns the names changed."""
    from .models import IntegrationSecret

    changed = []
    for name, raw in values.items():
        if name not in BY_NAME:
            raise KeyError(name)
        value = (raw or "").strip()
        row = db.get(IntegrationSecret, name)
        if not value:
            if row is not None:
                db.delete(row)
                changed.append(name)
            continue
        if len(value) > MAX_VALUE_LEN:
            raise ValueError(f"{name} is too long")
        if row is None:
            db.add(IntegrationSecret(name=name, ciphertext=encrypt(value), updated_by=actor))
        else:
            row.ciphertext, row.updated_by, row.updated_at = encrypt(value), actor, datetime.now(timezone.utc)
        changed.append(name)
    db.commit()
    apply_overrides(db)
    return changed


def _mask(value: str) -> str:
    return "••••" + value[-4:] if len(value) >= 12 else "••••"


def describe(db: Session) -> list[dict[str, Any]]:
    """Per-field status for the Settings page. Secret values are only ever shown masked."""
    from .models import IntegrationSecret

    apply_overrides(db)
    rows = {r.name: r for r in db.execute(select(IntegrationSecret)).scalars()}
    s = get_settings()
    out = []
    for f in FIELDS:
        current = getattr(s, f.name)
        current = "" if current is None else str(current)
        if f.name in _undecryptable:
            source = "unreadable"
        elif f.name in _overridden:
            source = "settings"
        elif current:
            source = "environment"
        else:
            source = "unset"
        row = rows.get(f.name)
        out.append({"name": f.name, "env": f.env, "group": f.group, "label": f.label, "secret": f.secret,
                    "placeholder": f.placeholder, "source": source, "is_set": bool(current),
                    "display": (_mask(current) if f.secret else current) if current else "",
                    "updated_at": row.updated_at.isoformat() if row and source == "settings" else None,
                    "updated_by": row.updated_by if row and source == "settings" else None})
    return out
