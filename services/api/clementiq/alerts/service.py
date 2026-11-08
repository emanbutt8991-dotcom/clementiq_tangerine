"""Alert generation, deduplication, preference filtering and delivery.

Idempotent: every candidate has a deterministic dedup_key (owner + account + type + period/event),
enforced by a UNIQUE constraint, so re-running jobs never duplicates alerts.
"""
from __future__ import annotations

import logging
import smtplib
from datetime import datetime, time, timedelta, timezone
from email.message import EmailMessage
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models
from ..config import get_settings
from ..core.analytics import detect_anomalies
from ..core.exposure import CHANNELS, INVESTMENT_CHANNELS, TOPIC_CHANNELS, TOPIC_LABELS, ImpactRequest, event_impact
from ..core.runway import compute_runway
from ..repository import get_baseline, get_prefs, monthly_frame
from ..worldpulse.service import effective_topic, latest_magnitude_for_topic, source_reliability
from .relevance import SEVERITY_RANK, score_event, severity_for

log = logging.getLogger("clementiq.alerts")

# Illustrative magnitudes when an article does not quantify the development (labelled in the alert).
DEFAULT_MAGNITUDE = {"energy": 10.0, "inflation": 1.0, "food": 3.0, "interest_rate": 0.25, "tariffs": 10.0,
                     "supply_chain": 3.0, "fx": 3.0, "housing": 3.0, "geopolitical": 5.0, "policy": 1.0}

CATEGORY_OF_TOPIC = {"crypto_regulation": "crypto", "market_volatility": "investments"}


def _candidate(**kw) -> dict[str, Any]:
    kw.setdefault("modeled_impact", {})
    kw.setdefault("score_breakdown", {})
    kw.setdefault("event_timestamp", None)
    kw.setdefault("news_event_id", None)
    return kw


def financial_health_candidates(db: Session, owner: str, account_id: int, prefs: dict[str, Any]) -> list[dict[str, Any]]:
    b = get_baseline(db, account_id)
    rw = compute_runway(b.B, b.I, b.S)
    rw_ei = compute_runway(b.B, 0.55 * b.I, b.S)
    period = b.last_month
    out = []
    thr = float(prefs["alerts"]["runway_threshold_months"])
    link = f"/simulator?account={account_id}"
    if not rw.no_shortfall and rw.months < thr:
        out.append(_candidate(
            dedup_key=f"{owner}:{account_id}:runway:{period}:{thr}", category="financial_health",
            severity="high" if rw.months < 1 else "medium", title=f"Runway below {thr:g} months",
            source="Clement Core (monthly_summary.csv)", relevance=f"Typical spending exceeds income by ${b.S - b.I:,.0f}/month; "
            f"the buffer covers {rw.display} months.", relevance_score=90 if rw.months < 1 else 70,
            modeled_impact={"runway": rw.display, "gap": b.S - b.I}, confidence="calculated",
            suggested_action="Open the Backup Plan to compare options for closing the gap.", simulation_link=link))
    cov = b.B / b.S if b.S > 0 else None
    if cov is not None and cov < 1:
        out.append(_candidate(
            dedup_key=f"{owner}:{account_id}:lowsavings:{period}", category="savings_goals", severity="medium",
            title="Emergency savings under one month of spending", source="Clement Core",
            relevance=f"Buffer ${b.B:,.0f} covers {cov:.1f} months of typical spending (${b.S:,.0f}). Under a job loss with EI at 55% "
                      f"runway would be {rw_ei.display} months.", relevance_score=65,
            modeled_impact={"coverage_months": cov, "runway_ei55": rw_ei.display}, confidence="calculated",
            suggested_action="Start a Goal Plan for a 3-month emergency fund.", simulation_link=f"/recovery?account={account_id}"))
    df = monthly_frame(db, account_id)
    for a in detect_anomalies(df, recent=2):
        cat = "household bills" if a["category"] == "household_bills" else a["category"].replace("_", " ")
        out.append(_candidate(
            dedup_key=f"{owner}:{account_id}:anomaly:{a['category']}:{a['month']}", category="financial_health",
            severity="low" if a["robust_z"] < 6 else "medium", title=f"Unusually high {cat} in {a['month']}",
            source="Clement Core anomaly detection (robust z-score)",
            relevance=f"{cat.capitalize()} were ${a['value']:,.0f} vs a typical ${a['typical']:,.0f} (robust z = {a['robust_z']:.1f}).",
            relevance_score=50 + min(a["robust_z"], 10) * 2, modeled_impact={"excess": a["excess"]}, confidence="calculated",
            suggested_action="Check whether this was a one-off or a new recurring cost.", simulation_link=link))
    if b.P > 0 and b.I > 0 and b.P / b.I > 0.3:
        out.append(_candidate(
            dedup_key=f"{owner}:{account_id}:loanburden:{period}", category="loan_exposure", severity="medium",
            title="Loan payment is a large share of income", source="loans.csv + Clement Core",
            relevance=f"Running loan payment ${b.P:,.0f}/month is {b.P / b.I:.0%} of typical income.", relevance_score=60,
            modeled_impact={"loan_to_income": b.P / b.I}, confidence="calculated",
            suggested_action="Model a rate rise in WorldPulse to see how sensitive the payment could be.",
            simulation_link=f"/worldpulse?account={account_id}&topic=interest_rate"))
    return out


LOW_CONFIDENCE_FACTOR = 0.6


def event_candidates(db: Session, owner: str, account_id: int, prefs: dict[str, Any], max_events: int = 25) -> list[dict[str, Any]]:
    b = get_baseline(db, account_id)
    rw = compute_runway(b.B, b.I, b.S)
    holdings = db.execute(select(models.PortfolioHolding.asset_class).where(models.PortfolioHolding.owner == owner)).scalars().all()
    held = set(holdings)
    since = datetime.now(timezone.utc) - timedelta(days=14)
    events = db.execute(select(models.NewsEvent).where(models.NewsEvent.retrieved_at >= since)
                        .order_by(models.NewsEvent.published_at.desc()).limit(max_events)).scalars().all()
    out = []
    for e in events:
        # Snowflake Cortex: skip items it judged irrelevant or prompt-injected; use its topic when accepted.
        if e.cortex_injection_detected or e.cortex_relevant is False:
            continue
        topic = effective_topic(e)
        inv_assets = {c["asset"] for c in INVESTMENT_CHANNELS.get(topic, [])}
        inv_match = bool(held & inv_assets)
        channels = TOPIC_CHANNELS.get(topic, [])
        magnitude, mag_basis = None, None
        if e.source_type == "official":
            magnitude = latest_magnitude_for_topic(db, topic)
            mag_basis = "latest official data"
        if magnitude is None and topic in DEFAULT_MAGNITUDE:
            magnitude, mag_basis = DEFAULT_MAGNITUDE[topic], "illustrative (article does not quantify the change)"
        impact = None
        if channels and magnitude:
            impact = event_impact(b, ImpactRequest(account_id=account_id, topic=topic, magnitude=magnitude, level="medium",
                                                   event_id=e.id, event_title=e.headline))
        exposed = sum(CHANNELS[c].baseline(b) for c in channels if CHANNELS[c].kind == "spending")
        monthly = (impact["additional_monthly_spending"] - impact["additional_monthly_income"]) if impact else 0.0
        sc = score_event(spending=b.S, exposed_baseline=exposed, monthly_impact=monthly, published_at=e.published_at,
                         reliability=source_reliability(e.source_type, e.source_name), runway_months=rw.months,
                         no_shortfall=rw.no_shortfall, topic=topic, interests=prefs.get("interests", []),
                         investment_match=inv_match)
        if e.cortex_confidence == "low":  # weak analysis: keep the alert but rank it lower
            sc = {**sc, "score": round(sc["score"] * LOW_CONFIDENCE_FACTOR, 1),
                  "breakdown": {**sc["breakdown"], "cortex_low_confidence_factor": LOW_CONFIDENCE_FACTOR}}
        category = CATEGORY_OF_TOPIC.get(topic, "loan_exposure" if topic == "interest_rate" and b.P > 0 else "global_events")
        if not channels and not inv_match:
            continue  # no personal channel and no holdings exposed: not relevant to this user
        rel = (f"{TOPIC_LABELS.get(topic, topic)} could affect your "
               + (", ".join(CHANNELS[c].label.lower() for c in channels) if channels else "investment holdings")
               + (f". Modeled (medium pass-through, {mag_basis}): about ${monthly:,.0f}/month." if impact else "."))
        out.append(_candidate(
            dedup_key=f"{owner}:{account_id}:event:{e.id}", category=category, severity=severity_for(sc["score"]),
            title=e.headline[:300], source=f"{e.source_name} ({e.source_type})", event_timestamp=e.published_at,
            relevance=rel, relevance_score=sc["score"], score_breakdown=sc["breakdown"],
            modeled_impact={"monthly_change": monthly, "magnitude": magnitude, "magnitude_basis": mag_basis,
                            "runway_after": impact["scenario"]["runway"]["display"] if impact else None},
            confidence="official data" if e.source_type == "official" else
                       ("reported" if e.classification == "reported" else e.classification),
            suggested_action="Simulate the impact to see low/medium/high scenarios.",
            simulation_link=f"/worldpulse?account={account_id}&event={e.id}&topic={topic}" + (f"&magnitude={magnitude}" if magnitude else ""),
            news_event_id=e.id))
    return out


def market_candidates(db: Session, owner: str) -> list[dict[str, Any]]:
    held = {h.symbol.upper(): h for h in db.execute(select(models.PortfolioHolding).where(models.PortfolioHolding.owner == owner)).scalars()}
    out = []
    for sym, h in held.items():
        p = db.execute(select(models.MarketPrice).where(models.MarketPrice.symbol == sym)
                       .order_by(models.MarketPrice.observed_at.desc())).scalars().first()
        if not p or p.change_24h_pct is None or abs(p.change_24h_pct) < 8:
            continue
        cat = "crypto" if h.asset_class == "crypto" else "investments"
        out.append(_candidate(
            dedup_key=f"{owner}:market:{sym}:{p.observed_at.date()}", category=cat, severity="medium",
            title=f"{sym} moved {p.change_24h_pct:+.1f}% in 24h", source=f"{p.provider} (price {p.price:,.2f} {p.currency})",
            event_timestamp=p.observed_at, relevance=f"You hold {h.quantity:g} {sym} ({h.holding_kind} holding).",
            relevance_score=60, modeled_impact={"position_change": h.quantity * p.price * p.change_24h_pct / (100 + p.change_24h_pct)},
            confidence="retrieved price", suggested_action="Review concentration and the crypto shock simulator; no action is required.",
            simulation_link="/solana" if cat == "crypto" else "/investments"))
    return out


def reminder_candidates(db: Session, owner: str, account_id: int) -> list[dict[str, Any]]:
    """Gentle reminder when the user has not saved a stress test for this account in 30 days."""
    now = datetime.now(timezone.utc)
    last = db.execute(select(func.max(models.SavedScenario.created_at)).where(
        models.SavedScenario.owner == owner, models.SavedScenario.account_id == account_id)).scalar()
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if last is not None and now - last < timedelta(days=30):
        return []
    period = now.strftime("%Y-%m")
    return [_candidate(
        dedup_key=f"{owner}:{account_id}:shock-reminder:{period}", category="reminders", severity="low",
        title="Time for a quick resilience check-up", source="ClementIQ reminder",
        relevance=("You haven't saved a stress test for this account in the last 30 days." if last
                   else "You haven't saved a stress test for this account yet."),
        relevance_score=45, confidence="reminder",
        suggested_action="Run the EI 55% preset in the Shock Simulator and save it to track changes over time.",
        simulation_link=f"/simulator?account={account_id}&preset=ei55_6m")]


def _in_quiet_hours(prefs: dict[str, Any], now: datetime) -> bool:
    qh = prefs["alerts"]["quiet_hours"]
    if not qh.get("enabled"):
        return False
    local = now.astimezone(ZoneInfo(qh.get("timezone") or "America/Toronto")).time()
    start, end = time.fromisoformat(qh["start"]), time.fromisoformat(qh["end"])
    return (start <= local or local < end) if start > end else (start <= local < end)


def _send_email(to: str, alert: models.Alert) -> bool:
    s = get_settings()
    if not s.smtp_host:
        return False
    msg = EmailMessage()
    msg["Subject"] = f"ClementIQ alert: {alert.title[:120]}"
    msg["From"] = s.smtp_from
    msg["To"] = to
    msg.set_content(f"{alert.relevance}\n\nSuggested: {alert.suggested_action}\n\n{s.public_web_url}/alerts\n\n"
                    "You receive this because you opted in. Unsubscribe in Settings → Alerts.")
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password or "")
            smtp.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException):
        log.warning("email delivery failed")
        return False


def generate_alerts(db: Session, owner: str, account_id: int, explain: int = 2) -> dict[str, Any]:
    prefs = get_prefs(db, owner)
    ap = prefs["alerts"]
    suppressed = {"disabled": 0, "category": 0, "severity": 0, "threshold": 0, "duplicate": 0, "rate_limit": 0}
    if not ap["enabled"]:
        return {"created": 0, "suppressed": {"disabled": 1}}
    cands = (financial_health_candidates(db, owner, account_id, prefs) + event_candidates(db, owner, account_id, prefs)
             + market_candidates(db, owner) + reminder_candidates(db, owner, account_id))
    # AI explanations on alerts are a separate, user-controlled notification type.
    if not (ap.get("ai_explanations", True) and prefs["privacy"].get("personalized_ai", True)):
        explain = 0
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    sent_today = db.execute(select(func.count()).select_from(models.Alert).where(
        models.Alert.owner == owner, models.Alert.created_at >= today)).scalar() or 0
    created = []
    cands.sort(key=lambda c: -c["relevance_score"])
    for c in cands:
        if not ap["categories"].get(c["category"], True):
            suppressed["category"] += 1
            continue
        if SEVERITY_RANK[c["severity"]] < SEVERITY_RANK[ap["min_severity"]]:
            suppressed["severity"] += 1
            continue
        if c["relevance_score"] < float(ap["relevance_threshold"]):
            suppressed["threshold"] += 1
            continue
        if db.execute(select(models.Alert.id).where(models.Alert.dedup_key == c["dedup_key"])).first():
            suppressed["duplicate"] += 1
            continue
        if sent_today + len(created) >= int(ap["max_per_day"]):
            suppressed["rate_limit"] += 1
            continue
        a = models.Alert(owner=owner, account_id=account_id, delivered_channels=["in_app"], **c)
        db.add(a)
        db.flush()
        created.append(a)
    db.commit()

    if created and explain:
        from ..ai.sanitize import financial_context
        from ..ai.service import explain_alert
        b = get_baseline(db, account_id)
        ctx = financial_context(b)
        for a in created[:explain]:
            res = explain_alert(db, {"title": a.title, "category": a.category, "relevance": a.relevance,
                                     "modeled_impact": a.modeled_impact, "suggested_action": a.suggested_action}, ctx)
            a.explanation = res["content"]["explanation"]
            a.explanation_engine = res["engine"]
        db.commit()

    email = prefs["channels"].get("email") or {}
    if created and email.get("opt_in") and email.get("address") and not _in_quiet_hours(prefs, datetime.now(timezone.utc)):
        for a in created:
            if a.severity in ("medium", "high") and _send_email(email["address"], a):
                a.delivered_channels = [*a.delivered_channels, "email"]
        db.commit()

    db.add(models.AlertGenerationLog(owner=owner, account_id=account_id, candidates=len(cands), created=len(created),
                                     suppressed=suppressed))
    db.commit()
    return {"candidates": len(cands), "created": len(created), "suppressed": suppressed}


def alert_dict(a: models.Alert) -> dict[str, Any]:
    return {
        "id": a.id, "account_id": a.account_id, "category": a.category, "severity": a.severity, "title": a.title,
        "source": a.source, "event_timestamp": a.event_timestamp.isoformat() if a.event_timestamp else None,
        "relevance": a.relevance, "relevance_score": a.relevance_score, "score_breakdown": a.score_breakdown,
        "modeled_impact": a.modeled_impact, "confidence": a.confidence, "suggested_action": a.suggested_action,
        "simulation_link": a.simulation_link, "news_event_id": a.news_event_id, "explanation": a.explanation,
        "explanation_engine": a.explanation_engine, "is_read": a.is_read, "delivered_channels": a.delivered_channels,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
