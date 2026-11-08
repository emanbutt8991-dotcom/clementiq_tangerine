"""WorldPulse — global economic & geopolitical intelligence.

Pipeline (run by the worker on a schedule, or on demand via POST /api/worldpulse/refresh):
  fetch (adapters) → normalise timestamps → deduplicate (URL + title) → classify topic
  (deterministic keywords) → prefer official statistics (indicator-derived events) → Gemini
  neutral summaries of retrieved items (validated; template fallback) → store with sources
  → exposure categories → alert candidates.

If retrieval fails nothing is invented: the source is marked errored/stale in data_source_status.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models
from ..config import get_settings
from ..core.exposure import TOPIC_CHANNELS, TOPIC_LABELS
from .adapters.base import IndicatorSeries, NewsItem
from .adapters.markets import CoinGeckoAdapter
from .adapters.news import GdeltAdapter, NewsApiAdapter
from .adapters.official import BankOfCanadaAdapter, StatCanAdapter, WorldBankAdapter

log = logging.getLogger("clementiq.worldpulse")

TOPIC_RULES: list[tuple[str, re.Pattern]] = [
    ("crypto_regulation", re.compile(r"(crypto|bitcoin|stablecoin|solana|ethereum).{0,60}(regulat|rule|law|ban|sec\b|csa\b|license|framework)|(regulat|rule|law|ban).{0,60}(crypto|stablecoin)", re.I)),
    ("interest_rate", re.compile(r"interest rate|rate (cut|hike|decision)|bank of canada|federal reserve|\bfed\b|central bank|policy rate|overnight rate|mortgage rate", re.I)),
    ("inflation", re.compile(r"inflation|consumer price|\bcpi\b|cost of living", re.I)),
    ("energy", re.compile(r"\boil\b|crude|opec|gasoline|natural gas|energy price|fuel price|pipeline", re.I)),
    ("tariffs", re.compile(r"tariff|trade war|countervailing|duties|export ban|import ban|trade restriction", re.I)),
    ("supply_chain", re.compile(r"supply chain|shortage|shipping|port strike|rail strike|logistics", re.I)),
    ("employment", re.compile(r"unemployment|jobs report|layoff|lay-off|labour market|labor market|hiring|job cuts", re.I)),
    ("housing", re.compile(r"housing|home price|rent(s|al)?\b|real estate|home sales", re.I)),
    ("fx", re.compile(r"exchange rate|loonie|canadian dollar|currency|forex", re.I)),
    ("food", re.compile(r"food price|grocer", re.I)),
    ("market_volatility", re.compile(r"stock market|stocks|\btsx\b|s&p 500|nasdaq|dow jones|sell-?off|volatil|bitcoin|crypto", re.I)),
    ("geopolitical", re.compile(r"geopolit|sanction|conflict|\bwar\b|strait|blockade", re.I)),
    ("regulation", re.compile(r"regulat|osfi|securities commission|banking rules", re.I)),
    ("policy", re.compile(r"budget|fiscal|stimulus|government spending|tax (cut|hike|change)", re.I)),
]
# The existing keyword topic list; Cortex must classify into these (or "other").
KEYWORD_TOPICS: list[str] = [t for t, _ in TOPIC_RULES]
FORECAST_RE = re.compile(r"\b(forecast|expected|expects|could|may|might|predict|outlook|poised|likely|warns)\b", re.I)
OPINION_RE = re.compile(r"\b(opinion|column|op-ed|editorial|commentary|why you should|analysis:)\b", re.I)

RELIABLE_DOMAINS = {
    "reuters.com", "apnews.com", "bloomberg.com", "cbc.ca", "theglobeandmail.com", "financialpost.com",
    "bnnbloomberg.ca", "ctvnews.ca", "globalnews.ca", "wsj.com", "ft.com", "cnbc.com", "bbc.com", "bbc.co.uk",
    "nytimes.com", "economist.com", "thestar.com", "marketwatch.com", "canada.ca", "bankofcanada.ca", "statcan.gc.ca",
}

COUNTRY_NAME_TO_ISO3 = {
    "Canada": "CAN", "United States": "USA", "Mexico": "MEX", "United Kingdom": "GBR", "Germany": "DEU",
    "France": "FRA", "China": "CHN", "Japan": "JPN", "India": "IND", "Brazil": "BRA", "Saudi Arabia": "SAU",
    "South Korea": "KOR", "Korea, Rep.": "KOR", "Australia": "AUS", "South Africa": "ZAF", "Nigeria": "NGA",
}

# Hypothetical what-if templates. These are NOT news: they are labelled scenario starters for the
# event-impact simulator when no live development is selected.
HYPOTHETICAL_TEMPLATES = [
    {"id": "hyp_energy15", "topic": "energy", "magnitude": 15, "title": "What if energy prices rose 15%?"},
    {"id": "hyp_rate50", "topic": "interest_rate", "magnitude": 0.5, "title": "What if the policy rate rose 0.50 pp?"},
    {"id": "hyp_cpi3", "topic": "inflation", "magnitude": 3, "title": "What if consumer prices rose a further 3%?"},
    {"id": "hyp_food6", "topic": "food", "magnitude": 6, "title": "What if food prices rose 6%?"},
    {"id": "hyp_tariff25", "topic": "tariffs", "magnitude": 25, "title": "What if a 25% tariff hit imported goods?"},
    {"id": "hyp_fx8", "topic": "fx", "magnitude": 8, "title": "What if the Canadian dollar fell 8%?"},
    {"id": "hyp_rent7", "topic": "housing", "magnitude": 7, "title": "What if rents rose 7%?"},
]


def cortex_accepted(e: models.NewsEvent) -> bool:
    """A Cortex analysis may steer topic/alerts only if confident and not prompt-injected."""
    return (e.cortex_topic is not None and e.cortex_confidence not in (None, "low")
            and not e.cortex_injection_detected)


def effective_topic(e: models.NewsEvent) -> str:
    """Topic used for alerts: Cortex's when accepted and mappable, else the keyword tag."""
    if cortex_accepted(e) and e.cortex_topic in TOPIC_CHANNELS:
        return e.cortex_topic
    return e.topic


def _apply_cortex(ev: models.NewsEvent, it: NewsItem, cortex, stats: dict[str, Any]) -> dict[str, Any] | None:
    """Run Cortex on one new item. Any failure keeps the keyword tag and never blocks the refresh.
    Only the news item's own title and text are sent (never customer data)."""
    text = (it.summary or "").strip() or it.headline  # GDELT often has only a title
    try:
        a = cortex.analyze(it.headline, text, KEYWORD_TOPICS)
    except Exception as exc:  # noqa: BLE001
        msg = f"{exc.__class__.__name__}: {str(exc)[:300]}"
        log.warning("Cortex analysis failed for event %s; keeping keyword topic %s (%s)", ev.id, ev.topic, msg)
        stats["cortex_errors"] += 1
        stats["cortex_last_error"] = msg
        return None
    data = a.model_dump(mode="json")
    ev.cortex_topic, ev.cortex_confidence = a.topic, a.analysis_confidence
    ev.cortex_injection_detected, ev.cortex_relevant = a.injection_detected, a.is_relevant
    ev.cortex_model, ev.cortex_request_id = (a.model or "")[:64], (a.request_id or "")[:128] or None
    ev.cortex_analysis = data
    stats["cortex_analyzed"] += 1
    if cortex_accepted(ev) and a.topic in TOPIC_CHANNELS:  # "other" has no spending mapping: keep keyword tag
        ev.topic = a.topic
        ev.exposure_categories = TOPIC_CHANNELS[a.topic]
    return data


def classify_topic(text: str) -> str | None:
    for topic, rx in TOPIC_RULES:
        if rx.search(text or ""):
            return topic
    return None


def classify_kind(text: str, source_type: str) -> str:
    if source_type == "official":
        return "confirmed"
    if OPINION_RE.search(text):
        return "opinion"
    if FORECAST_RE.search(text):
        return "forecast"
    return "reported"


def source_reliability(source_type: str, domain: str | None) -> float:
    if source_type == "official":
        return 1.0
    d = (domain or "").lower().removeprefix("www.")
    return 0.8 if any(d == r or d.endswith("." + r) for r in RELIABLE_DOMAINS) else 0.5


def normalize_url(url: str) -> str:
    p = urlsplit(url.strip())
    return urlunsplit((p.scheme.lower(), p.netloc.lower().removeprefix("www."), p.path.rstrip("/"), "", ""))


def dedup_key(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode()).hexdigest()


def title_key(title: str) -> str:
    return hashlib.sha256(re.sub(r"[^a-z0-9]", "", title.lower()).encode()).hexdigest()


def _status(db: Session, source: str, kind: str, ok: bool, records: int = 0, error: str | None = None) -> None:
    row = db.get(models.DataSourceStatus, source) or models.DataSourceStatus(source=source, kind=kind, status="never")
    now = datetime.now(timezone.utc)
    row.last_attempt_at = now
    if ok:
        row.status, row.last_success_at, row.records, row.last_error = "ok", now, records, None
    else:
        row.status, row.last_error = "error", (error or "")[:500]
    db.merge(row)
    db.commit()


def _geo(db: Session, iso3: str | None) -> models.CountryGeo | None:
    return db.get(models.CountryGeo, iso3) if iso3 else None


# ---------------------------------------------------------------- indicators -----------
def store_series(db: Session, series: list[IndicatorSeries]) -> int:
    n = 0
    for s in series:
        ind = db.execute(select(models.EconomicIndicator).where(
            models.EconomicIndicator.source == s.source, models.EconomicIndicator.series_code == s.series_code,
            models.EconomicIndicator.country == s.country)).scalars().first()
        g = _geo(db, s.country)
        if ind is None:
            ind = models.EconomicIndicator(source=s.source, series_code=s.series_code, name=s.name, country=s.country,
                                           topic=s.topic, unit=s.unit, source_url=s.source_url)
            db.add(ind)
            db.flush()
        if g:
            ind.latitude, ind.longitude = g.latitude, g.longitude
        existing = set(db.execute(select(models.EconomicObservation.observed_at)
                                  .where(models.EconomicObservation.indicator_id == ind.id)).scalars())
        for o in s.observations:
            if o.observed_at not in existing:
                db.add(models.EconomicObservation(indicator_id=ind.id, observed_at=o.observed_at, value=o.value))
                n += 1
    db.commit()
    return n


def _obs(db: Session, ind_id: int) -> list[models.EconomicObservation]:
    return list(db.execute(select(models.EconomicObservation).where(models.EconomicObservation.indicator_id == ind_id)
                           .order_by(models.EconomicObservation.observed_at)).scalars())


def indicator_events(db: Session) -> int:
    """Turn new official data points into verified 'confirmed' WorldPulse events."""
    created = 0
    inds = db.execute(select(models.EconomicIndicator).where(models.EconomicIndicator.country == "CAN")).scalars().all()
    for ind in inds:
        obs = _obs(db, ind.id)
        if len(obs) < 2:
            continue
        last, prev = obs[-1], obs[-2]
        headline = None
        magnitude = None
        if ind.series_code == "V39079":
            changes = [(a, b) for a, b in zip(obs, obs[1:]) if abs(b.value - a.value) > 1e-9]
            if changes:
                a, b = changes[-1]
                headline = (f"Bank of Canada target for the overnight rate moved from {a.value:.2f}% to {b.value:.2f}% "
                            f"(effective {b.observed_at.isoformat()}); latest value {last.value:.2f}%.")
                magnitude = b.value - a.value
                key_date = b.observed_at
            else:
                headline = f"Bank of Canada target for the overnight rate unchanged at {last.value:.2f}% as of {last.observed_at}."
                magnitude, key_date = 0.0, last.observed_at
        elif ind.series_code == "v41690973" and len(obs) >= 13:
            yo = obs[-13]
            yy = (last.value / yo.value - 1) * 100
            headline = (f"Statistics Canada CPI (all-items) {last.observed_at.strftime('%B %Y')}: {yy:+.1f}% year over year "
                        f"(index {last.value:.1f}).")
            magnitude, key_date = yy, last.observed_at
        elif ind.series_code == "v2062815":
            headline = (f"Statistics Canada Labour Force Survey {last.observed_at.strftime('%B %Y')}: unemployment rate "
                        f"{last.value:.1f}% ({last.value - prev.value:+.1f} pp vs previous month).")
            magnitude, key_date = last.value - prev.value, last.observed_at
        elif ind.series_code == "M.ENER" and len(obs) >= 13:
            yy = (last.value / obs[-13].value - 1) * 100
            headline = (f"Bank of Canada energy commodity price index {last.observed_at.strftime('%B %Y')}: {yy:+.1f}% "
                        f"year over year, {(last.value / prev.value - 1) * 100:+.1f}% month over month.")
            magnitude, key_date = yy, last.observed_at
        elif ind.series_code == "FXUSDCAD" and len(obs) >= 20:
            base = obs[-20]
            ch = (last.value / base.value - 1) * 100
            headline = (f"USD/CAD at {last.value:.4f} on {last.observed_at} ({ch:+.1f}% over 20 business days; "
                        "a higher value means a weaker Canadian dollar).")
            magnitude, key_date = ch, last.observed_at
        if not headline:
            continue
        key = hashlib.sha256(f"indicator:{ind.source}:{ind.series_code}:{key_date}".encode()).hexdigest()
        if db.execute(select(models.NewsEvent.id).where(models.NewsEvent.dedup_key == key)).first():
            continue
        g = _geo(db, "CAN")
        db.add(models.NewsEvent(
            dedup_key=key, headline=headline, source_name={"bank_of_canada": "Bank of Canada",
                                                            "statistics_canada": "Statistics Canada"}.get(ind.source, ind.source),
            source_type="official", provider=ind.source, url=ind.source_url,
            published_at=datetime.combine(key_date, datetime.min.time(), tzinfo=timezone.utc), event_date=key_date,
            country="Canada", country_code="CAN", latitude=g.latitude if g else None, longitude=g.longitude if g else None,
            location_basis="national statistic (capital-city coordinates, World Bank API)" if g else None,
            topic=ind.topic, classification="confirmed", summary=headline, summary_engine="clement-core",
            exposure_categories=TOPIC_CHANNELS.get(ind.topic, []),
            confidence_note=f"Official statistic; magnitude {magnitude:+.2f}{'pp' if ind.unit == '%' else '%'}." if magnitude is not None else None))
        created += 1
    db.commit()
    return created


# ---------------------------------------------------------------- news -----------------
def store_news(db: Session, items: list[NewsItem], summarize_limit: int = 8, cortex=None) -> dict[str, Any]:
    """`cortex`: an open CortexClient (or None). It analyzes the same new items Gemini summarises."""
    from ..ai.service import summarize_news

    stats: dict[str, Any] = {"fetched": len(items), "duplicates": 0, "irrelevant": 0, "stored": 0, "summarized": 0,
                             "cortex_analyzed": 0, "cortex_errors": 0}
    since = datetime.now(timezone.utc) - timedelta(days=7)
    recent_titles = {title_key(t) for t in db.execute(
        select(models.NewsEvent.headline).where(models.NewsEvent.retrieved_at >= since)).scalars()}
    for it in items:
        key = dedup_key(it.url)
        tk = title_key(it.headline)
        if tk in recent_titles or db.execute(select(models.NewsEvent.id).where(models.NewsEvent.dedup_key == key)).first():
            stats["duplicates"] += 1
            continue
        topic = it.topic_hint or classify_topic(f"{it.headline} {it.summary or ''}")
        if topic is None:
            stats["irrelevant"] += 1
            continue
        iso3 = COUNTRY_NAME_TO_ISO3.get(it.country_name or "")
        g = _geo(db, iso3)
        ev = models.NewsEvent(
            dedup_key=key, headline=it.headline[:500], source_name=it.source_name[:200], source_type=it.source_type,
            provider=it.provider, url=it.url[:1000], published_at=it.published_at, event_date=it.event_date,
            country=it.country_name, country_code=iso3, latitude=g.latitude if g else None,
            longitude=g.longitude if g else None,
            location_basis="publisher country (GDELT sourcecountry); capital coordinates from World Bank API" if g else None,
            topic=topic, classification=classify_kind(it.headline, it.source_type),
            summary=None, exposure_categories=TOPIC_CHANNELS.get(topic, []))
        db.add(ev)
        db.flush()
        recent_titles.add(tk)
        stats["stored"] += 1
        if stats["summarized"] < summarize_limit:
            analysis = _apply_cortex(ev, it, cortex, stats) if cortex is not None else None
            grounded = analysis if analysis is not None and not analysis["injection_detected"] else None
            res = summarize_news(db, {"id": ev.id, "headline": ev.headline, "summary": it.summary,
                                      "source_name": ev.source_name, "published_at": ev.published_at,
                                      "source_type": ev.source_type, "topic": ev.topic,
                                      "exposure_categories": ev.exposure_categories}, cortex=grounded)
            c = res["content"]
            ev.summary = c["summary"]
            ev.summary_engine = res["engine"]
            ev.confidence_note = c.get("confidence_note")
            if res["engine"] != "clement-core-template" and c.get("classification") in ("forecast", "opinion", "speculation", "confirmed"):
                ev.classification = c["classification"]
            stats["summarized"] += 1
    db.commit()
    return stats


def refresh_countries(db: Session) -> int:
    rows = WorldBankAdapter().countries()
    for r in rows:
        db.merge(models.CountryGeo(**r))
    db.commit()
    return len(rows)


def refresh_all(db: Session, include_news: bool = True) -> dict[str, Any]:
    s = get_settings()
    report: dict[str, Any] = {}
    if not s.worldpulse_live:
        for name in ("world_bank_geo", "bank_of_canada", "statistics_canada", "world_bank", "gdelt", "newsapi", "coingecko",
                     "snowflake_cortex"):
            row = db.get(models.DataSourceStatus, name) or models.DataSourceStatus(source=name, kind="external", status="disabled")
            row.status = "disabled"
            db.merge(row)
        db.commit()
        return {"disabled": "WORLDPULSE_LIVE=false — no external retrieval performed"}

    def run(name: str, kind: str, fn):
        try:
            n = fn()
            _status(db, name, kind, True, n if isinstance(n, int) else 0)
            report[name] = {"ok": True, "result": n}
        except Exception as exc:  # noqa: BLE001 - provider failures are recorded, never fabricated around
            db.rollback()
            _status(db, name, kind, False, error=f"{exc.__class__.__name__}: {exc}")
            report[name] = {"ok": False, "error": f"{exc.__class__.__name__}: {str(exc)[:200]}"}

    if db.execute(select(func.count()).select_from(models.CountryGeo)).scalar() == 0:
        run("world_bank_geo", "reference", lambda: refresh_countries(db))
    run("bank_of_canada", "indicator", lambda: store_series(db, BankOfCanadaAdapter().fetch()))
    run("statistics_canada", "indicator", lambda: store_series(db, StatCanAdapter().fetch()))
    run("world_bank", "indicator", lambda: store_series(db, WorldBankAdapter().fetch()))
    report["official_events_created"] = indicator_events(db)
    if include_news:
        cortex, cortex_stats = _open_cortex(db), {"cortex_analyzed": 0, "cortex_errors": 0}

        def news(adapter) -> int:
            st = store_news(db, adapter.fetch(), cortex=cortex)
            for k in ("cortex_analyzed", "cortex_errors"):
                cortex_stats[k] += st[k]
            if "cortex_last_error" in st:
                cortex_stats["cortex_last_error"] = st["cortex_last_error"]
            return st["stored"]

        try:
            run("gdelt", "news", lambda: news(GdeltAdapter()))
            if s.news_api_key:
                run("newsapi", "news", lambda: news(NewsApiAdapter()))
        finally:
            if cortex is not None:
                cortex.close()
                _record_cortex(db, cortex_stats)
                report["snowflake_cortex"] = cortex_stats
    run("coingecko", "market", lambda: store_quotes(db, CoinGeckoAdapter().fetch()))
    return report


def _open_cortex(db: Session):
    """One CortexClient per refresh, or None (status recorded as disabled/error)."""
    from .cortex import CortexClient, cortex_enabled

    if not cortex_enabled():
        row = db.get(models.DataSourceStatus, "snowflake_cortex") or models.DataSourceStatus(
            source="snowflake_cortex", kind="ai", status="disabled")
        row.status, row.last_attempt_at = "disabled", datetime.now(timezone.utc)
        db.merge(row)
        db.commit()
        return None
    try:
        return CortexClient()
    except Exception as exc:  # noqa: BLE001
        _status(db, "snowflake_cortex", "ai", False, error=f"{exc.__class__.__name__}: {exc}")
        return None


def _record_cortex(db: Session, st: dict[str, Any]) -> None:
    if st["cortex_errors"] and not st["cortex_analyzed"]:
        _status(db, "snowflake_cortex", "ai", False, error=st.get("cortex_last_error"))
    else:
        _status(db, "snowflake_cortex", "ai", True, st["cortex_analyzed"])


def store_quotes(db: Session, quotes) -> int:
    n = 0
    for q in quotes:
        if db.get(models.MarketPrice, (q.symbol, q.observed_at)) is None:
            db.add(models.MarketPrice(symbol=q.symbol, observed_at=q.observed_at, price=q.price, currency=q.currency,
                                      change_24h_pct=q.change_24h_pct, provider=q.provider))
            n += 1
    db.commit()
    return n


# ---------------------------------------------------------------- read models ----------
def event_dict(e: models.NewsEvent) -> dict[str, Any]:
    return {
        "id": e.id, "headline": e.headline, "source_name": e.source_name, "source_type": e.source_type,
        "provider": e.provider, "url": e.url, "published_at": e.published_at.isoformat() if e.published_at else None,
        "event_date": e.event_date.isoformat() if e.event_date else None, "country": e.country,
        "country_code": e.country_code, "latitude": e.latitude, "longitude": e.longitude,
        "location_basis": e.location_basis, "topic": e.topic, "topic_label": TOPIC_LABELS.get(e.topic, e.topic),
        "classification": e.classification, "summary": e.summary, "summary_engine": e.summary_engine,
        "exposure_categories": e.exposure_categories, "confidence_note": e.confidence_note,
        "reliability": source_reliability(e.source_type, e.source_name),
        "retrieved_at": e.retrieved_at.isoformat() if e.retrieved_at else None,
        "cortex_topic": e.cortex_topic, "cortex_confidence": e.cortex_confidence,
        "cortex_injection_detected": e.cortex_injection_detected, "cortex_relevant": e.cortex_relevant,
        "cortex_model": e.cortex_model, "cortex_request_id": e.cortex_request_id,
        "cortex_accepted": cortex_accepted(e), "cortex_analysis": e.cortex_analysis,
    }


def list_indicators(db: Session, country: str | None = "CAN") -> list[dict[str, Any]]:
    q = select(models.EconomicIndicator)
    if country:
        q = q.where(models.EconomicIndicator.country == country)
    out = []
    for ind in db.execute(q).scalars():
        obs = _obs(db, ind.id)
        if not obs:
            continue
        last = obs[-1]
        prev = obs[-2] if len(obs) > 1 else None
        out.append({"id": ind.id, "source": ind.source, "series_code": ind.series_code, "name": ind.name,
                    "country": ind.country, "topic": ind.topic, "unit": ind.unit, "source_url": ind.source_url,
                    "latest": {"date": last.observed_at.isoformat(), "value": last.value},
                    "previous": {"date": prev.observed_at.isoformat(), "value": prev.value} if prev else None,
                    "retrieved_at": last.retrieved_at.isoformat() if last.retrieved_at else None,
                    "history": [{"date": o.observed_at.isoformat(), "value": o.value} for o in obs[-60:]],
                    "latitude": ind.latitude, "longitude": ind.longitude})
    return out


def source_statuses(db: Session) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    out = []
    for r in db.execute(select(models.DataSourceStatus)).scalars():
        ls = r.last_success_at
        if ls is not None and ls.tzinfo is None:
            ls = ls.replace(tzinfo=timezone.utc)
        out.append({"source": r.source, "kind": r.kind, "status": r.status,
                    "last_success_at": ls.isoformat() if ls else None,
                    "last_attempt_at": r.last_attempt_at.isoformat() if r.last_attempt_at else None,
                    "last_error": r.last_error, "records": r.records,
                    "stale": ls is None or (now - ls) > timedelta(hours=24)})
    return out


def latest_magnitude_for_topic(db: Session, topic: str) -> float | None:
    """Most recent official magnitude to pre-fill the impact simulator (None if no data)."""
    m = {"interest_rate": "V39079", "inflation": "v41690973", "energy": "M.ENER", "fx": "FXUSDCAD"}.get(topic)
    if not m:
        return None
    ind = db.execute(select(models.EconomicIndicator).where(models.EconomicIndicator.series_code == m,
                                                            models.EconomicIndicator.country == "CAN")).scalars().first()
    if not ind:
        return None
    obs = _obs(db, ind.id)
    if topic == "interest_rate":
        ch = [(a, b) for a, b in zip(obs, obs[1:]) if abs(b.value - a.value) > 1e-9]
        return (ch[-1][1].value - ch[-1][0].value) if ch else 0.0
    if len(obs) >= 13 and topic in ("inflation", "energy"):
        return (obs[-1].value / obs[-13].value - 1) * 100
    if topic == "fx" and len(obs) >= 20:
        return (obs[-1].value / obs[-20].value - 1) * 100
    return None
