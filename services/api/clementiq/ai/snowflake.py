"""Optional Snowflake Cortex adapter (AI_COMPLETE through the SQL API).

Used for ONE clearly labelled feature: an independent "second-opinion" narrative of the Insights
dashboard findings (structured economic analysis). Gemini remains the primary AI engine.
Enabled only when SNOWFLAKE_ACCOUNT_URL and SNOWFLAKE_PAT are set.
"""
from __future__ import annotations

import json
import time
from typing import Any

import httpx

from ..config import get_settings


class SnowflakeUnavailable(RuntimeError):
    pass


def cortex_complete(prompt: str, max_tokens: int = 600) -> dict[str, Any]:
    s = get_settings()
    if not s.snowflake_enabled:
        raise SnowflakeUnavailable("Snowflake not configured (SNOWFLAKE_ACCOUNT_URL, SNOWFLAKE_PAT)")
    base = s.snowflake_account_url.rstrip("/")
    body = {
        "statement": "SELECT AI_COMPLETE(?, ?, PARSE_JSON(?))",
        "timeout": 45,
        "bindings": {
            "1": {"type": "TEXT", "value": s.snowflake_model},
            "2": {"type": "TEXT", "value": prompt},
            "3": {"type": "TEXT", "value": json.dumps({"max_tokens": max_tokens, "temperature": 0.2})},
        },
    }
    if s.snowflake_warehouse:
        body["warehouse"] = s.snowflake_warehouse
    headers = {"Authorization": f"Bearer {s.snowflake_pat}", "Content-Type": "application/json",
               "Accept": "application/json", "X-Snowflake-Authorization-Token-Type": "PROGRAMMATIC_ACCESS_TOKEN"}
    try:
        deadline = time.monotonic() + 55
        with httpx.Client(headers=headers, timeout=45) as client:
            r = client.post(base + "/api/v2/statements", json=body)
            while r.status_code in (202, 408):
                handle = r.json().get("statementHandle", "")
                if not handle or any(c not in "0123456789abcdefABCDEF-" for c in handle):
                    raise SnowflakeUnavailable("Cortex returned an invalid statement handle")
                remaining = deadline - time.monotonic()
                if remaining <= 1:
                    raise SnowflakeUnavailable("Cortex SQL statement timed out")
                time.sleep(1)
                r = client.get(base + "/api/v2/statements/" + handle, timeout=remaining - 1)
    except httpx.HTTPError as exc:
        raise SnowflakeUnavailable(f"network error: {exc.__class__.__name__}") from exc
    except (ValueError, TypeError, AttributeError) as exc:
        raise SnowflakeUnavailable("Cortex returned an invalid statement status") from exc
    if r.status_code != 200:
        raise SnowflakeUnavailable(f"Cortex HTTP {r.status_code}: {r.text[:200]}")
    try:
        text = r.json()["data"][0][0]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise SnowflakeUnavailable("Cortex returned no completion") from exc
    if not isinstance(text, str) or not text.strip():
        raise SnowflakeUnavailable("Cortex returned an empty completion")
    # VARIANT results in SQL API cells can contain a JSON-encoded string.
    try:
        decoded = json.loads(text)
    except ValueError:
        decoded = None
    if isinstance(decoded, str):
        text = decoded
    if not text.strip():
        raise SnowflakeUnavailable("Cortex returned an empty completion")
    return {"text": text, "engine": "snowflake-cortex", "model": s.snowflake_model}


def insights_second_opinion(findings: list[dict[str, Any]]) -> dict[str, Any]:
    prompt = ("You are reviewing statistical findings from an anonymized bank dataset about household "
              "financial resilience. Using ONLY the JSON below, write a 120-word neutral analysis: what the "
              "findings suggest, which are associations rather than causes, and one question for further "
              "research. Do not add numbers that are not in the JSON.\n" + json.dumps(findings, default=str))
    return cortex_complete(prompt)
