from __future__ import annotations

import threading
import time
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models
from ..ai.snowflake import SnowflakeUnavailable, insights_second_opinion
from ..auth import Principal, current_principal, require_judge
from ..core.attention import compute_attention
from ..core.insights import build_features, run_insights
from ..db import get_db

router = APIRouter(prefix="/api/insights", tags=["insights"])
_cache: dict[str, Any] = {}
_lock = threading.Lock()


def _fingerprint(db: Session) -> str:
    last = db.execute(select(func.max(models.ImportRun.id)).where(models.ImportRun.status == "success")).scalar()
    return str(last)


def compute(db: Session) -> dict[str, Any]:
    fp = _fingerprint(db)
    with _lock:
        if _cache.get("fp") == fp:
            return _cache["data"]
        t0 = time.perf_counter()
        eng = db.get_bind()
        ms = pd.read_sql("SELECT * FROM monthly_summaries", eng)
        loans = pd.read_sql("SELECT * FROM loans", eng)
        accounts = pd.read_sql("SELECT * FROM accounts", eng)
        districts = pd.read_sql("SELECT * FROM districts", eng)
        if ms.empty:
            return {"available": False, "reason": "No data imported yet."}
        data = run_insights(build_features(ms, loans, accounts, districts))
        data["compute_seconds"] = round(time.perf_counter() - t0, 2)
        data["available"] = True
        _cache.update(fp=fp, data=data)
        return data


@router.get("")
def insights(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    return compute(db)


_attention_cache: dict[str, Any] = {}


def _attention(db: Session) -> tuple[pd.DataFrame, int]:
    fp = _fingerprint(db)
    with _lock:
        if _attention_cache.get("fp") == fp:
            return _attention_cache["data"]
        eng = db.get_bind()
        data = compute_attention(
            pd.read_sql("SELECT account_id, income_I, spending_S, buffer_B, loan_payment_P, last_month, runway_ei55 "
                        "FROM account_baselines", eng),
            pd.read_sql("SELECT account_id, month, month_end_balance FROM monthly_summaries", eng),
            pd.read_sql("SELECT account_id, amount, purpose FROM standing_orders", eng),
            pd.read_sql("SELECT account_id, status, monthly_payment FROM loans", eng),
        )
        _attention_cache.update(fp=fp, data=data)
        return data


@router.get("/needs-attention")
def needs_attention(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
                    flag: str | None = Query(None, pattern="^(short|behind|thin)$"),
                    p: Principal = Depends(require_judge), db: Session = Depends(get_db)):
    """Accounts with a risk flag today, most urgent first: short this month > loan behind > under one month saved,
    then by the size of this month's gap. For outreach and help only, never credit decisions."""
    df, n_active = _attention(db)
    view = df[df[flag]] if flag and len(df) else df
    page = view.iloc[offset:offset + limit] if len(view) else view

    def num(v):
        return None if v is None or pd.isna(v) else round(float(v), 2)

    items = [{
        "account_id": int(r.account_id), "flags": list(r.flags), "balance": num(r.balance),
        "fixed_total": num(r.fixed_total), "left_after_fixed": num(r.left_after_fixed),
        "B": num(r.buffer_B), "S": num(r.spending_S), "I": num(r.income_I),
        "loan_status": None if pd.isna(r.status) else str(r.status),
        "runway_ei55": num(r.runway_ei55),  # None = no shortfall under EI 55%
    } for r in page.itertuples()]
    counts = {k: int(df[k].sum()) if len(df) else 0 for k in ("short", "behind", "thin")}
    # How many of these look safe under the judge formula alone (typical income >= spending -> "no shortfall, 120+").
    counts["green_under_formula"] = int(((df["income_I"] >= df["spending_S"]) & (df["buffer_B"] > 0)).sum()) if len(df) else 0
    return {
        "total": int(len(df)), "matching": int(len(view)), "flag": flag, "active_accounts": n_active,
        "share": round(len(df) / n_active, 4) if n_active else 0.0,
        "counts": counts, "limit": limit, "offset": offset, "items": items,
        "rules": {"short": "This month's fixed payments exceed the latest month-end balance",
                  "behind": "Loan status D: running, behind on payments",
                  "thin": "Buffer B below one month of typical spending S"},
        "use": "Flags are for outreach and help, not credit decisions.",
    }


@router.post("/snowflake-review")
def snowflake_review(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Optional: independent narrative of the computed findings via Snowflake Cortex."""
    data = compute(db)
    if not data.get("available"):
        return {"available": False, "reason": data.get("reason")}
    try:
        return {"available": True, **insights_second_opinion(data["findings"])}
    except SnowflakeUnavailable as exc:
        return {"available": False, "engine": "snowflake-cortex", "reason": str(exc)}
