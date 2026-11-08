from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models
from ..ai import gemini
from ..ai.sanitize import financial_context
from ..ai.service import explain_scenario
from ..auth import Principal, authorize_account, current_principal, require_admin
from ..core.exposure import INVESTMENT_CHANNELS, TOPIC_CHANNELS, TOPIC_LABELS, ImpactRequest, event_impact
from ..db import get_db
from ..jobs import JOBS, monitoring_status, run_job
from ..repository import ai_allowed, audit, get_baseline
from ..worldpulse.service import (HYPOTHETICAL_TEMPLATES, KEYWORD_TOPICS, event_dict, latest_magnitude_for_topic, list_indicators,
                                  source_statuses)

router = APIRouter(prefix="/api/worldpulse", tags=["worldpulse"])


@router.get("/events")
def events(topic: str | None = None, classification: str | None = None, country: str | None = Query(None, max_length=3),
           limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0),
           p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    E = models.NewsEvent
    q = select(E)
    if topic:
        q = q.where(E.topic == topic)
    if classification:
        q = q.where(E.classification == classification)
    if country:
        q = q.where(E.country_code == country.upper())
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar()
    rows = db.execute(q.order_by(E.published_at.desc()).limit(limit).offset(offset)).scalars().all()
    last = db.execute(select(func.max(models.DataSourceStatus.last_success_at))
                      .where(models.DataSourceStatus.kind.in_(["news", "indicator"]))).scalar()
    return {"total": total, "items": [event_dict(e) for e in rows], "topics": TOPIC_LABELS,
            "last_successful_update": last.isoformat() if last else None,
            "hypothetical_templates": HYPOTHETICAL_TEMPLATES,
            "empty_reason": None if total else "No developments retrieved yet. Use Refresh World Intelligence; "
                                               "ClementIQ never invents news when retrieval fails."}


@router.get("/events/{event_id}")
def event(event_id: int, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    e = db.get(models.NewsEvent, event_id)
    if not e:
        raise HTTPException(404, "event not found")
    d = event_dict(e)
    d["investment_channels"] = INVESTMENT_CHANNELS.get(e.topic, [])
    d["suggested_magnitude"] = latest_magnitude_for_topic(db, e.topic)
    return d


@router.get("/indicators")
def indicators(country: str | None = "CAN", p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    return {"items": list_indicators(db, country), "sources": source_statuses(db)}


@router.get("/map")
def map_data(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Only markers with coordinates obtained from the World Bank country API are returned."""
    evs = db.execute(select(models.NewsEvent).where(models.NewsEvent.latitude.is_not(None))
                     .order_by(models.NewsEvent.published_at.desc()).limit(300)).scalars().all()
    countries = {c.iso3: {"iso3": c.iso3, "name": c.name, "capital": c.capital, "lat": c.latitude, "lon": c.longitude,
                          "region": c.region} for c in db.execute(select(models.CountryGeo)).scalars()}
    inds = list_indicators(db, None)
    by_country: dict[str, dict] = {}
    for e in evs:
        by_country.setdefault(e.country_code, {"events": [], "indicators": []})["events"].append(event_dict(e))
    for i in inds:
        if i["latitude"] is None:
            continue
        by_country.setdefault(i["country"], {"events": [], "indicators": []})["indicators"].append(
            {k: i[k] for k in ("name", "topic", "unit", "latest", "previous", "source", "source_url")})
    markers = []
    for iso3, d in by_country.items():
        c = countries.get(iso3)
        if not c or c["lat"] is None:
            continue
        markers.append({**c, "event_count": len(d["events"]), "events": d["events"][:15], "indicators": d["indicators"],
                        "topics": sorted({e["topic"] for e in d["events"]})})
    return {"markers": markers, "coordinate_source": "World Bank country API (capital city latitude/longitude)",
            "note": "A marker shows where a development was reported or measured; it does not by itself show financial impact."}


class ImpactBody(ImpactRequest):
    explain: bool = False


@router.post("/impact")
def impact(body: ImpactBody, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    authorize_account(p, body.account_id)
    if body.topic not in TOPIC_CHANNELS:
        raise HTTPException(422, "unknown topic")
    b = get_baseline(db, body.account_id)
    res = event_impact(b, ImpactRequest(**body.model_dump(exclude={"explain"})))
    ev = db.get(models.NewsEvent, body.event_id) if body.event_id else None
    res["event"] = event_dict(ev) if ev else None
    if body.explain:
        sim_like = {
            "baseline": {"income": b.I, "spending": b.S, "B": b.B, "H": b.H, "F": b.F, "P": b.P,
                         "runway": res["baseline"]["runway"]},
            "scenario": {"income": res["scenario"]["income"], "spending": res["scenario"]["spending"], "one_off_costs": 0.0,
                         "buffer_left": b.B, "gap": res["scenario"]["spending"] - res["scenario"]["income"],
                         "runway": res["scenario"]["runway"]},
            "effects": [{"label": c["label"], "rule": f"pass-through {c['passthrough']:g}", "delta_income":
                         c["monthly_change"] if c["kind"] == "income" else 0.0,
                         "delta_spending": c["monthly_change"] if c["kind"] == "spending" else 0.0, "one_off": 0.0}
                        for c in res["channels"]],
            "deltas": {"spending": res["additional_monthly_spending"], "income": res["additional_monthly_income"]},
            "assumptions": res["assumptions"] + res["limitations"],
        }
        sources = [{"id": ev.id, "headline": ev.headline, "summary": ev.summary, "source_name": ev.source_name,
                    "published_at": ev.published_at, "source_type": ev.source_type}] if ev else []
        res["explanation"] = explain_scenario(db, sim_like, financial_context(b), sources, allow_ai=ai_allowed(db, p.sub))
    return res


@router.post("/refresh")
def refresh(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    audit(db, p.sub, "worldpulse_refresh")
    res = run_job("worldpulse_refresh", JOBS["worldpulse_refresh"], runner="api")
    return {**res, "sources": source_statuses(db), "monitoring": monitoring_status(db)}


class ResearchBody(BaseModel):
    question: str = Field(min_length=3, max_length=500)


@router.post("/research")
def research(body: ResearchBody, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Gemini + Google Search grounding (if enabled). Citations come from grounding metadata."""
    audit(db, p.sub, "worldpulse_research", None, q=body.question[:200])
    try:
        return gemini.grounded_search(
            "Research recent, verifiable developments relevant to Canadian household finances for this question. "
            "Separate confirmed facts from forecasts and opinions. Be politically neutral. Question: " + body.question)
    except gemini.GeminiUnavailable as exc:
        return {"text": None, "citations": [], "engine": "unavailable", "reason": str(exc)}


# ---------------------------------------------------------------- Snowflake Cortex -----
class CortexAnalyzeBody(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    text: str = Field(min_length=1, max_length=20_000)


@router.get("/cortex/health")
def cortex_health(p: Principal = Depends(require_admin)):
    """Live round-trip to Cortex (a 10-token completion). Never returns the token."""
    from ..worldpulse.cortex import CortexClient, cortex_enabled
    if not cortex_enabled():
        return {"enabled": False}
    client = None
    try:
        client = CortexClient()
        return {"enabled": True, "ok": True, **client.health()}
    except Exception as exc:  # noqa: BLE001
        return {"enabled": True, "ok": False, "error": f"{exc.__class__.__name__}: {str(exc)[:300]}"}
    finally:
        if client is not None:
            client.close()


@router.post("/cortex/analyze")
def cortex_analyze(body: CortexAnalyzeBody, p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    """Admin demo: analyze one pasted news item (news text only, never customer data). Nothing is stored."""
    from ..worldpulse.cortex import CortexClient, cortex_enabled
    if not cortex_enabled():
        raise HTTPException(409, "Snowflake Cortex is disabled (SNOWFLAKE_CORTEX_ENABLED, SNOWFLAKE_ACCOUNT_URL, SNOWFLAKE_PAT)")
    audit(db, p.sub, "cortex_analyze", None, title=body.title[:120])
    client = CortexClient()
    try:
        a = client.analyze(body.title, body.text, KEYWORD_TOPICS)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Cortex analysis failed: {exc.__class__.__name__}: {str(exc)[:300]}") from exc
    finally:
        client.close()
    return {"analysis": a.model_dump(mode="json"), "topics": KEYWORD_TOPICS,
            "accepted": a.analysis_confidence != "low" and not a.injection_detected}
