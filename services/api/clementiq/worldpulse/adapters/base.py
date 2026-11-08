"""Adapter contracts. Each provider can be swapped without touching the rest of WorldPulse."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

import httpx

from ...config import get_settings

USER_AGENT = "ClementIQ/1.0 (financial-resilience hackathon project)"


@dataclass
class Observation:
    observed_at: date
    value: float


@dataclass
class IndicatorSeries:
    source: str
    series_code: str
    name: str
    topic: str
    unit: str
    source_url: str
    country: str = "CAN"
    observations: list[Observation] = field(default_factory=list)


@dataclass
class NewsItem:
    headline: str
    url: str
    source_name: str
    provider: str
    source_type: str  # official | news | aggregator
    published_at: datetime | None
    country_name: str | None = None
    summary: str | None = None
    event_date: date | None = None
    topic_hint: str | None = None


@dataclass
class Quote:
    symbol: str
    price: float
    currency: str
    observed_at: datetime
    provider: str
    change_24h_pct: float | None = None


class IndicatorAdapter(Protocol):
    name: str

    def fetch(self) -> list[IndicatorSeries]: ...


class NewsAdapter(Protocol):
    name: str

    def fetch(self) -> list[NewsItem]: ...


def client(timeout: float | None = None) -> httpx.Client:
    return httpx.Client(timeout=timeout or get_settings().http_timeout_s, headers={"User-Agent": USER_AGENT},
                        follow_redirects=True)
