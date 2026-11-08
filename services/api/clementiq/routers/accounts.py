from __future__ import annotations

from datetime import date
from typing import Literal

import pandas as pd
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models
from ..auth import Principal, authorize_account, current_principal, require_judge
from ..core.analytics import detect_anomalies, forecast_balance, trends
from ..core.metrics import baseline_calcs
from ..core.provenance import envelope
from ..core.resilience import resilience_score, score_history
from ..core.runway import compute_runway
from ..db import get_db
from ..repository import account_profile, get_baseline, list_accounts, loan_records, monthly_frame, reference_date, search_accounts

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("")
def accounts(q: str | None = Query(None, max_length=10, pattern=r"^\d*$"), limit: int = Query(50, ge=1, le=200),
             offset: int = Query(0, ge=0), sort: str = "account_id",
             p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    if p.role == "customer":
        return list_accounts(db, str(p.account_id), 1, 0)
    return list_accounts(db, q, limit, offset, sort)


@router.get("/search")
def search(q: str = Query("", max_length=12), limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
           p: Principal = Depends(require_judge), db: Session = Depends(get_db)):
    """Judge account search across the whole authorized (challenge) dataset."""
    term = "".join(ch for ch in q.strip() if ch.isdigit())
    if q.strip() and not term:
        return {"query": q, "total": 0, "limit": limit, "offset": offset, "exact_match": False, "items": [],
                "message": "Account IDs are numbers — try digits only, e.g. 20111."}
    return search_accounts(db, term, limit, offset)


def _net_position(df: pd.DataFrame, loan) -> list[dict]:
    """Account balance minus remaining scheduled loan payments, month by month.
    Labelled 'net account position' — NOT net worth (other assets/debts are unknown)."""
    out = []
    start = pd.Timestamp(loan["loan_start"]) if loan and loan.get("loan_start") else None
    for _, r in df.iterrows():
        owed = 0.0
        if start is not None:
            m = pd.Timestamp(r["month_start"])
            if m >= start.to_period("M").to_timestamp():
                elapsed = (m.year - start.year) * 12 + (m.month - start.month)
                owed = max(int(loan["duration_months"]) - elapsed, 0) * float(loan["monthly_payment"])
        out.append({"month": r["month"], "balance": float(r["month_end_balance"]), "loan_remaining": owed,
                    "net_position": float(r["month_end_balance"]) - owed})
    return out


@router.get("/{account_id}/summary")
def summary(account_id: int, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    authorize_account(p, account_id)
    b = get_baseline(db, account_id)
    df = monthly_frame(db, account_id)
    rw = compute_runway(b.B, b.I, b.S)
    series = [{
        "month": r.month, "money_in": r.money_in, "money_out": r.money_out, "household_bills": r.household_bills,
        "insurance": r.insurance, "loan_payments": r.loan_payments, "bank_fees": r.bank_fees,
        "discretionary": r.cash_withdrawals_genuine + r.card_withdrawals + r.transfers_out_other,
        "fixed": r.household_bills + r.insurance + r.loan_payments, "net_flow": r.money_in - r.money_out,
        "month_end_balance": r.month_end_balance, "avg_daily_balance": r.avg_daily_balance,
        "min_balance": r.min_balance, "days_below_zero": r.days_below_zero,
    } for r in df.itertuples()]
    loans = loan_records(db, account_id)
    payload = {
        "account_id": account_id,
        "profile": account_profile(db, account_id),
        "judging": {**b.judging_dict(), "runway": rw.to_dict(), "buffer_months": b.buffer_months},
        "calculations": baseline_calcs(b),
        "metrics": {
            "discretionary": b.D, "monthly_surplus": b.I - b.S,
            "avg_monthly_cash_flow": float(df.money_in.mean() - df.money_out.mean()),
            "emergency_fund_target_3m": 3 * b.S, "emergency_fund_progress": min(max(b.B, 0) / (3 * b.S), 1) if b.S > 0 else None,
            "coverage_months": (b.B / b.S) if b.S > 0 else None, "income_cv": b.income_cv, "spending_cv": b.spending_cv,
            "days_below_zero_12m": b.days_below_zero_12m, "category_medians": b.category_medians,
            "months_of_data": b.months_of_data, "first_month": b.first_month, "last_month": b.last_month,
        },
        "loan": b.loan,
        "loans_count": len(loans),
        "series": series,
        "net_position": {"available": True, "label": "Net account position = month-end balance − remaining scheduled "
                         "loan payments. Not net worth: other assets and debts are not in the data.",
                         "series": _net_position(df, b.loan)},
        "resilience": resilience_score(b),
        "anomalies": detect_anomalies(df)[-12:],
        "trends": trends(df),
        "forecast": forecast_balance(df),
        "warnings": b.warnings,
        "data_as_of": b.last_month,
        "reference_date": reference_date().isoformat(),
    }
    return envelope(payload, {"account_id": account_id, "baseline": b.judging_dict()})


@router.get("/{account_id}/transactions")
def transactions(account_id: int, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
                 start: date | None = None, end: date | None = None,
                 direction: Literal["credit", "debit"] | None = None, operation: str | None = Query(None, max_length=48),
                 p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    authorize_account(p, account_id)
    T = models.Transaction
    q = select(T).where(T.account_id == account_id)
    if start:
        q = q.where(T.date >= start)
    if end:
        q = q.where(T.date <= end)
    if direction:
        q = q.where(T.direction.like(f"{direction}%"))
    if operation:
        q = q.where(T.operation == operation)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar()
    rows = db.execute(q.order_by(T.date.desc(), T.transaction_id.desc()).limit(limit).offset(offset)).scalars().all()
    return {"total": total, "limit": limit, "offset": offset, "items": [{
        "transaction_id": t.transaction_id, "date": t.date.isoformat(), "direction": t.direction, "operation": t.operation,
        "purpose": t.purpose, "amount": t.amount, "signed_amount": t.signed_amount, "balance": t.balance,
        "partner_bank": t.partner_bank} for t in rows]}


_ORDER_LABELS = {"household bills": "Household bills", "insurance": "Insurance", "leasing": "Leasing",
                 "loan payment": "Loan payment"}


@router.get("/{account_id}/obligations")
def obligations(account_id: int, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Fixed payments the account has committed to (standing orders + a running loan) against the latest balance.

    Answers "can this month's fixed payments come out of what is in the account?". The standing-order table is an
    undated end-of-data snapshot, so due DATES are unknown: this is a month-level check, not a calendar.
    """
    authorize_account(p, account_id)
    b = get_baseline(db, account_id)
    df = monthly_frame(db, account_id)
    last = df.iloc[-1] if len(df) else None
    orders = db.execute(select(models.StandingOrder).where(models.StandingOrder.account_id == account_id)).scalars().all()
    items: dict[str, float] = {}
    for o in orders:
        label = _ORDER_LABELS.get((o.purpose or "").strip().lower(), "Other transfer")
        items[label] = items.get(label, 0.0) + float(o.amount)
    loan = b.loan
    loan_running = bool(loan and loan.get("running"))
    if loan_running and "Loan payment" not in items:
        items["Loan payment"] = float(loan["monthly_payment"])
    lines = [{"label": k, "amount": round(v, 2)} for k, v in sorted(items.items(), key=lambda kv: -kv[1])]
    total = round(sum(items.values()), 2)
    balance = float(last.month_end_balance) if last is not None else None
    left = None if balance is None else round(balance - total, 2)
    status = ("unknown" if balance is None else "short" if left < 0
              else "tight" if b.S > 0 and left < 0.5 * b.S else "covered")
    loan_out = None
    if loan:
        meaning = {"A": "Finished, repaid", "B": "Finished, not repaid", "C": "Running, payments on track",
                   "D": "Running, behind on payments"}.get(loan["status"], loan["status"])
        loan_out = {"status": loan["status"], "meaning": meaning, "running": loan_running,
                    "behind": loan["status"] == "D", "monthly_payment": loan["monthly_payment"]}
    return {
        "account_id": account_id, "as_of_month": b.last_month,
        "balance": balance, "fixed_payments": lines, "fixed_total": total, "left_after_fixed": left, "status": status,
        "typical_spending": b.S, "loan": loan_out,
        "notes": ["Standing orders are an undated snapshot, so this is a monthly check, not a list of due dates.",
                  "The data has one loan per account and one insurance category: it cannot separate a car loan "
                  "from a mortgage, or health insurance from other policies."],
    }


@router.get("/{account_id}/loans")
def loans(account_id: int, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    authorize_account(p, account_id)
    ref = reference_date()
    rows = db.execute(select(models.Loan).where(models.Loan.account_id == account_id)).scalars().all()
    out = []
    for l in rows:
        elapsed = (ref.year - l.loan_start.year) * 12 + (ref.month - l.loan_start.month) if l.loan_start else None
        remaining = max(l.duration_months - elapsed, 0) if elapsed is not None else None
        out.append({"loan_id": l.loan_id, "loan_start": l.loan_start.isoformat() if l.loan_start else None,
                    "amount": l.amount, "duration_months": l.duration_months, "monthly_payment": l.monthly_payment,
                    "status": l.status, "status_meaning": l.status_meaning, "defaulted": bool(l.defaulted),
                    "running_at_reference": l.status in ("C", "D"), "months_remaining": remaining,
                    "remaining_scheduled": (remaining or 0) * l.monthly_payment if l.status in ("C", "D") else 0.0})
    return {"account_id": account_id, "reference_date": ref.isoformat(), "loans": out}


@router.get("/{account_id}/resilience")
def resilience(account_id: int, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    authorize_account(p, account_id)
    b = get_baseline(db, account_id)
    res = resilience_score(b)
    res["history"] = score_history(monthly_frame(db, account_id), loan_records(db, account_id))
    peers = db.execute(select(models.AccountBaseline.resilience_score)).scalars().all()
    if peers:
        res["percentile"] = sum(1 for x in peers if x is not None and x <= res["score"]) / len(peers) * 100
    return res


@router.get("/{account_id}/timeline")
def timeline(account_id: int, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Financial timeline: dated events from the customer's own records + detected anomalies."""
    authorize_account(p, account_id)
    prof = account_profile(db, account_id)
    df = monthly_frame(db, account_id)
    events = []
    if prof["account_opened"]:
        events.append({"date": prof["account_opened"], "type": "account", "title": "Account opened", "source": "accounts.csv"})
    for c in prof["cards"]:
        if c["issued"]:
            events.append({"date": c["issued"], "type": "card", "title": f"{c['card_type'].title()} card issued", "source": "cards.csv"})
    for l in db.execute(select(models.Loan).where(models.Loan.account_id == account_id)).scalars():
        if l.loan_start:
            events.append({"date": l.loan_start.isoformat(), "type": "loan",
                           "title": f"Loan granted: ${l.amount:,.0f} over {l.duration_months} months (${l.monthly_payment:,.0f}/mo)",
                           "detail": l.status_meaning, "source": "loans.csv"})
    for a in detect_anomalies(df):
        events.append({"date": a["month"] + "-01", "type": "anomaly",
                       "title": f"Unusually high {a['category'].replace('_', ' ')}: ${a['value']:,.0f} (typical ${a['typical']:,.0f})",
                       "source": "Clement Core anomaly detection"})
    for r in df.itertuples():
        if r.days_below_zero > 0:
            events.append({"date": r.month + "-01", "type": "overdraft", "title": f"{r.days_below_zero} day(s) below zero",
                           "detail": f"lowest balance ${r.min_balance:,.0f}", "source": "monthly_summary.csv"})
    events.sort(key=lambda e: e["date"])
    return {"account_id": account_id, "events": events,
            "balance_series": [{"month": r.month, "balance": r.month_end_balance, "net_flow": r.money_in - r.money_out}
                               for r in df.itertuples()]}
