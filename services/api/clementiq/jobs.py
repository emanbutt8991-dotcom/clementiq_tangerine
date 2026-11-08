"""Background jobs shared by the worker service and on-demand API triggers.

Every run is recorded in job_runs (start, finish, status, detail) so the UI can show when monitoring
last succeeded and whether the worker is running. All jobs are idempotent.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .db import session_factory

log = logging.getLogger("clementiq.jobs")

JOB_INTERVALS_MIN = {"worldpulse_refresh": 60, "market_refresh": 15, "alerts_generate": 30}


def run_job(name: str, fn: Callable[[Session], Any], runner: str = "worker") -> dict[str, Any]:
    from .secrets_store import refresh
    refresh()  # the worker process picks up API keys saved from Settings
    SessionLocal = session_factory()
    with SessionLocal() as db:
        run = models.JobRun(job=name, runner=runner, status="running")
        db.add(run)
        db.commit()
        try:
            detail = fn(db) or {}
            run.status = "success"
            run.detail = detail if isinstance(detail, dict) else {"result": detail}
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            run = db.merge(run)
            run.status = "failed"
            run.detail = {"error": f"{exc.__class__.__name__}: {str(exc)[:500]}"}
            log.exception("job %s failed", name)
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        return {"job": name, "status": run.status, "detail": run.detail}


def job_worldpulse(db: Session) -> dict[str, Any]:
    from .worldpulse.service import refresh_all
    return refresh_all(db)


def job_markets(db: Session) -> dict[str, Any]:
    from .worldpulse.adapters.markets import AlphaVantageAdapter, CoinGeckoAdapter, StooqAdapter
    from .worldpulse.service import _status, store_quotes
    from .config import get_settings

    syms = sorted({h.symbol.upper() for h in db.execute(select(models.PortfolioHolding)).scalars()})
    crypto = [s for s in syms if s in ("SOL", "BTC", "ETH", "USDC", "BONK", "JUP")] or ["SOL", "BTC", "ETH", "USDC"]
    equities = [s for s in syms if s not in crypto and s != "CASH"]
    out = {}
    for name, fn in (("coingecko", lambda: CoinGeckoAdapter().fetch(crypto)),
                     ("stooq", lambda: StooqAdapter().fetch(equities) if equities else []),
                     ("alpha_vantage", lambda: AlphaVantageAdapter().fetch(equities) if get_settings().alpha_vantage_key and equities else [])):
        try:
            n = store_quotes(db, fn())
            _status(db, name, "market", True, n)
            out[name] = n
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            _status(db, name, "market", False, error=str(exc)[:300])
            out[name] = f"error: {exc.__class__.__name__}"
    return out


def watched_pairs(db: Session) -> list[tuple[str, int]]:
    pairs: set[tuple[str, int]] = set()
    for p in db.execute(select(models.UserPreference)).scalars():
        for acc in (p.data or {}).get("watched_accounts", []):
            pairs.add((p.owner, int(acc)))
        if p.owner.startswith("customer:"):
            try:
                pairs.add((p.owner, int(p.owner.split(":")[1])))
            except ValueError:
                pass
    return sorted(pairs)


def job_alerts(db: Session) -> dict[str, Any]:
    from .alerts.service import generate_alerts

    res = {}
    for owner, acc in watched_pairs(db):
        try:
            res[f"{owner}:{acc}"] = generate_alerts(db, owner, acc, explain=1)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            res[f"{owner}:{acc}"] = {"error": str(exc)[:200]}
    return {"pairs": len(res), "results": res}


JOBS: dict[str, Callable[[Session], Any]] = {
    "worldpulse_refresh": job_worldpulse,
    "market_refresh": job_markets,
    "alerts_generate": job_alerts,
}


def monitoring_status(db: Session) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    out = {}
    worker_alive = False
    for name, interval in JOB_INTERVALS_MIN.items():
        last = db.execute(select(models.JobRun).where(models.JobRun.job == name).order_by(models.JobRun.id.desc())).scalars().first()
        last_ok = db.execute(select(models.JobRun).where(models.JobRun.job == name, models.JobRun.status == "success")
                             .order_by(models.JobRun.id.desc())).scalars().first()
        lw = db.execute(select(models.JobRun).where(models.JobRun.job == name, models.JobRun.runner == "worker")
                        .order_by(models.JobRun.id.desc())).scalars().first()

        def iso(x):
            if x is None:
                return None
            return (x if x.tzinfo else x.replace(tzinfo=timezone.utc)).isoformat()

        if lw and lw.started_at:
            st = lw.started_at if lw.started_at.tzinfo else lw.started_at.replace(tzinfo=timezone.utc)
            if now - st < timedelta(minutes=interval * 2 + 5):
                worker_alive = True
        out[name] = {"interval_minutes": interval, "last_run": iso(last.started_at) if last else None,
                     "last_status": last.status if last else None,
                     "last_success": iso(last_ok.finished_at) if last_ok else None,
                     "last_runner": last.runner if last else None}
    hb = db.get(models.DataSourceStatus, "worker_heartbeat")
    if hb and hb.last_success_at:
        t = hb.last_success_at if hb.last_success_at.tzinfo else hb.last_success_at.replace(tzinfo=timezone.utc)
        worker_alive = worker_alive or (now - t) < timedelta(minutes=5)
    return {"worker_running": worker_alive, "jobs": out,
            "note": None if worker_alive else "Continuous monitoring is not running. Start the worker "
                    "(services/worker) or use 'Refresh World Intelligence' for a one-off update."}
