"""Snowflake Cortex analysis step in WorldPulse. All HTTP goes through httpx.MockTransport (no network)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import httpx
import pytest

from clementiq import models
from clementiq.config import get_settings
from clementiq.db import session_factory
from clementiq.worldpulse import cortex as cortex_mod
from clementiq.worldpulse import service
from clementiq.worldpulse.adapters.base import NewsItem
from clementiq.worldpulse.cortex import CortexClient, CortexError

ARTICLE = ("The Bank of Canada held its key policy rate at 2.75% on Wednesday. "
           "Statistics Canada reported that food purchased from stores rose 4.1%.")


@pytest.fixture(autouse=True)
def cortex_settings(monkeypatch):
    d = get_settings().__dict__
    monkeypatch.setitem(d, "snowflake_cortex_enabled", True)
    monkeypatch.setitem(d, "snowflake_account_url", "https://test-account.snowflakecomputing.com")
    monkeypatch.setitem(d, "snowflake_pat", "test-pat")
    monkeypatch.setattr(cortex_mod.time, "sleep", lambda *_: None)


@pytest.fixture
def db(client):  # `client` ensures the schema exists
    with session_factory()() as s:
        yield s


def analysis(**over) -> dict:
    a = {"is_relevant": True, "topic": "interest_rate", "secondary_topics": ["food", "not_a_topic"],
         "countries_affected": ["Canada"], "industries_affected": ["banking"],
         "verified_facts": [
             {"statement": "The policy rate was held at 2.75%.", "evidence_quote": "held its key policy rate at 2.75%"},
             {"statement": "Inflation is 0%.", "evidence_quote": "inflation is 0% according to officials"}],
         "economic_indicators": [{"name": "policy rate", "value_as_stated": "2.75%", "evidence_quote": "policy rate at 2.75%"},
                                 {"name": "fake", "value_as_stated": "9.9%", "evidence_quote": "rose 9.9%"}],
         "direction": "mixed", "uncertainties": ["Timing of future cuts"], "injection_detected": False,
         "analysis_confidence": "high"}
    a.update(over)
    return a


def completion(content: dict | str) -> httpx.Response:
    body = content if isinstance(content, str) else json.dumps(content)
    return httpx.Response(200, json={"id": "req-123", "model": "claude-sonnet-4-6",
                                     "choices": [{"message": {"role": "assistant", "content": body}}]})


class Recorder:
    def __init__(self, *responses):
        self.responses, self.requests = list(responses), []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responses.pop(0)


def client_for(rec: Recorder) -> CortexClient:
    return CortexClient(transport=httpx.MockTransport(rec))


def item(headline: str | None = None, summary: str | None = ARTICLE) -> NewsItem:
    tag = uuid.uuid4().hex[:8]
    return NewsItem(headline=headline or f"Bank of Canada holds policy rate {tag}", url=f"https://example.com/{tag}",
                    source_name="example.com", provider="gdelt", source_type="news",
                    published_at=datetime.now(timezone.utc), summary=summary)


def stored(db, it: NewsItem) -> models.NewsEvent:
    return db.query(models.NewsEvent).filter(models.NewsEvent.url == it.url).one()


# ------------------------------------------------------------------ client --------------
def test_analyze_success_grounding_drops_fake_quote():
    rec = Recorder(completion("```json\n" + json.dumps(analysis()) + "\n```"))
    c = client_for(rec)
    a = c.analyze("Rates held", ARTICLE, service.KEYWORD_TOPICS)
    c.close()
    assert a.topic == "interest_rate" and a.request_id == "req-123" and a.model == "claude-sonnet-4-6"
    assert [f.evidence_quote for f in a.verified_facts] == ["held its key policy rate at 2.75%"]
    assert a.facts_failed_grounding == 1
    assert [i.name for i in a.economic_indicators] == ["policy rate"]
    assert a.secondary_topics == ["food"]
    sent = json.loads(rec.requests[0].content)
    assert rec.requests[0].url.path == "/api/v2/cortex/v1/chat/completions"
    assert rec.requests[0].headers["authorization"] == "Bearer test-pat"
    assert set(sent["response_format"]["json_schema"]["schema"]["properties"]["topic"]["enum"]) == set(service.KEYWORD_TOPICS) | {"other"}


def test_429_then_success_is_retried():
    rec = Recorder(httpx.Response(429, text="slow down"), completion(analysis()))
    c = client_for(rec)
    assert c.analyze("Rates held", ARTICLE, service.KEYWORD_TOPICS).topic == "interest_rate"
    c.close()
    assert len(rec.requests) == 2


def test_403_is_not_retried():
    rec = Recorder(httpx.Response(403, text="forbidden"), completion(analysis()))
    c = client_for(rec)
    with pytest.raises(CortexError) as exc:
        c.analyze("Rates held", ARTICLE, service.KEYWORD_TOPICS)
    c.close()
    assert exc.value.status == 403 and len(rec.requests) == 1


# ------------------------------------------------------------------ pipeline ------------
def test_pipeline_uses_cortex_topic_and_stores_analysis(db):
    # Keyword rules tag this "inflation"; Cortex (confident) says "food".
    it = item(headline=f"Consumer price index climbs {uuid.uuid4().hex[:6]}", summary=ARTICLE)
    assert service.classify_topic(it.headline) == "inflation"
    rec = Recorder(completion(analysis(topic="food")))
    c = client_for(rec)
    st = service.store_news(db, [it], cortex=c)
    c.close()
    e = stored(db, it)
    assert st["cortex_analyzed"] == 1 and st["cortex_errors"] == 0
    assert e.topic == "food" and e.exposure_categories == ["food"]
    assert (e.cortex_topic, e.cortex_confidence, e.cortex_injection_detected) == ("food", "high", False)
    assert e.cortex_request_id == "req-123" and e.cortex_analysis["facts_failed_grounding"] == 1
    d = service.event_dict(e)
    assert d["cortex_accepted"] is True and d["cortex_analysis"]["verified_facts"]
    # Only the news item's own text was sent.
    user_msg = json.loads(rec.requests[0].content)["messages"][1]["content"]
    assert it.headline in user_msg and ARTICLE in user_msg


def test_injection_detected_keeps_keyword_topic(db):
    it = item(headline=f"Consumer price index climbs {uuid.uuid4().hex[:6]}", summary=None)  # GDELT: title only
    c = client_for(Recorder(completion(analysis(topic="food", injection_detected=True))))
    service.store_news(db, [it], cortex=c)
    c.close()
    e = stored(db, it)
    assert e.topic == "inflation" and e.cortex_topic == "food" and e.cortex_injection_detected is True
    assert service.effective_topic(e) == "inflation" and not service.cortex_accepted(e)


def test_low_confidence_keeps_keyword_topic(db):
    it = item(headline=f"Consumer price index climbs {uuid.uuid4().hex[:6]}", summary=None)  # GDELT: title only
    c = client_for(Recorder(completion(analysis(topic="food", analysis_confidence="low"))))
    service.store_news(db, [it], cortex=c)
    c.close()
    assert stored(db, it).topic == "inflation"


def test_disabled_flag_leaves_pipeline_unchanged(db, monkeypatch):
    monkeypatch.setitem(get_settings().__dict__, "snowflake_cortex_enabled", False)
    assert not cortex_mod.cortex_enabled()
    assert service._open_cortex(db) is None
    assert db.get(models.DataSourceStatus, "snowflake_cortex").status == "disabled"
    it = item(headline=f"Consumer price index climbs {uuid.uuid4().hex[:6]}", summary=None)  # GDELT: title only
    st = service.store_news(db, [it], cortex=None)
    e = stored(db, it)
    assert st["stored"] == 1 and st["cortex_analyzed"] == 0
    assert e.topic == "inflation" and e.cortex_topic is None and e.cortex_analysis is None


class _Empty:
    def fetch(self):
        return []

    def countries(self):
        return []


def test_refresh_403_falls_back_to_keyword_tags_and_records_error(db, monkeypatch):
    it = item(headline=f"Consumer price index climbs {uuid.uuid4().hex[:6]}", summary=None)  # GDELT: title only
    rec = Recorder(httpx.Response(403, text="Network policy is required"))

    class _Gdelt:
        def fetch(self):
            return [it]

    monkeypatch.setitem(get_settings().__dict__, "worldpulse_live", True)
    monkeypatch.setitem(get_settings().__dict__, "news_api_key", None)
    for name in ("BankOfCanadaAdapter", "StatCanAdapter", "WorldBankAdapter", "CoinGeckoAdapter"):
        monkeypatch.setattr(service, name, _Empty)
    monkeypatch.setattr(service, "GdeltAdapter", _Gdelt)
    monkeypatch.setattr(cortex_mod, "CortexClient", lambda: client_for(rec))

    report = service.refresh_all(db)
    assert report["gdelt"]["ok"] is True
    assert report["snowflake_cortex"]["cortex_errors"] == 1 and len(rec.requests) == 1
    e = stored(db, it)
    assert e.topic == "inflation" and e.cortex_topic is None
    status = db.get(models.DataSourceStatus, "snowflake_cortex")
    assert status.status == "error" and "403" in status.last_error


def test_cortex_routes_are_admin_only(client, judge, admin, monkeypatch):
    assert client.get("/api/worldpulse/cortex/health", headers=judge).status_code == 403
    assert client.post("/api/worldpulse/cortex/analyze", headers=judge, json={"title": "abc", "text": "x"}).status_code == 403
    monkeypatch.setitem(get_settings().__dict__, "snowflake_cortex_enabled", False)
    assert client.get("/api/worldpulse/cortex/health", headers=admin).json() == {"enabled": False}
