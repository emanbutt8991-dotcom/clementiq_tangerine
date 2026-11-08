"""News adapters: GDELT DOC 2.0 API (no key) and optional NewsAPI.org (NEWS_API_KEY)."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from ...config import get_settings
from .base import NewsItem, client

ECON_QUERY = ('("Bank of Canada" OR inflation OR "interest rate" OR tariff OR tariffs OR "oil price" OR '
              '"oil prices" OR unemployment OR "supply chain" OR "consumer prices" OR "housing market" OR '
              '"exchange rate" OR cryptocurrency OR "stock market")')
# GDELT rejects ECON_QUERY ("Your query was too short or too long"), so it gets a shorter list of the
# same core topics. Checked against the live API on 2026-11-08: this one returns results.
GDELT_QUERY = ('("Bank of Canada" OR inflation OR "interest rate" OR tariffs OR "oil prices" OR unemployment OR '
               '"housing market" OR "supply chain" OR "stock market")')


class GdeltAdapter:
    """GDELT DOC 2.0 — https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/ (headline metadata only)."""

    name = "gdelt"
    URL = "https://api.gdeltproject.org/api/v2/doc/doc"

    def fetch(self) -> list[NewsItem]:
        params = {"query": f"{GDELT_QUERY} sourcelang:english", "mode": "artlist", "format": "json",
                  "maxrecords": 75, "timespan": "3d", "sort": "datedesc"}
        # GDELT often takes 20-30 s to answer (measured 2026-11-08), well past the 12 s default.
        with client(timeout=max(45.0, get_settings().http_timeout_s)) as c:
            r = c.get(self.URL, params=params)
            if r.status_code == 429:  # GDELT allows ~1 request / 5 s per client; back off once
                time.sleep(6)
                r = c.get(self.URL, params=params)
            r.raise_for_status()
            if "json" not in r.headers.get("content-type", "") and not r.text.strip().startswith("{"):
                raise RuntimeError(f"GDELT returned non-JSON: {r.text[:120]}")
            data = r.json()
        out = []
        for a in data.get("articles", []):
            ts = None
            if a.get("seendate"):
                try:
                    ts = datetime.strptime(a["seendate"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                except ValueError:
                    ts = None
            out.append(NewsItem(headline=a.get("title", "").strip(), url=a.get("url", ""),
                                source_name=a.get("domain", "unknown"), provider=self.name,
                                source_type="news", published_at=ts, country_name=a.get("sourcecountry")))
        return [n for n in out if n.headline and n.url]


class NewsApiAdapter:
    """NewsAPI.org /v2/everything — only active when NEWS_API_KEY is set."""

    name = "newsapi"
    URL = "https://newsapi.org/v2/everything"

    def fetch(self) -> list[NewsItem]:
        key = get_settings().news_api_key
        if not key:
            raise RuntimeError("NEWS_API_KEY not configured")
        params = {"q": ECON_QUERY, "language": "en", "sortBy": "publishedAt", "pageSize": 50}
        with client() as c:
            r = c.get(self.URL, params=params, headers={"X-Api-Key": key})
            r.raise_for_status()
            data = r.json()
        out = []
        for a in data.get("articles", []):
            ts = None
            if a.get("publishedAt"):
                ts = datetime.fromisoformat(a["publishedAt"].replace("Z", "+00:00"))
            out.append(NewsItem(headline=(a.get("title") or "").strip(), url=a.get("url", ""),
                                source_name=(a.get("source") or {}).get("name", "unknown"), provider=self.name,
                                source_type="news", published_at=ts, summary=a.get("description")))
        return [n for n in out if n.headline and n.url and n.headline != "[Removed]"]
