"""ClementIQ API — FastAPI application."""
from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from . import secrets_store
from .config import get_settings
from .db import Base, get_engine
from .ratelimit import RateLimitMiddleware
from .routers import accounts, ai, alerts, insights, integrations, investments, profile, reports, scenarios, solana, system, worldpulse


class _RedactFilter(logging.Filter):
    """Production-safe logging: never write tokens or API keys."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = str(record.getMessage())
        for marker in ("Bearer ", "x-goog-api-key", "api_key="):
            if marker in msg:
                record.msg = msg.split(marker)[0] + marker + "[redacted]"
                record.args = ()
        return True


def create_app() -> FastAPI:
    s = get_settings()
    logging.basicConfig(level=logging.INFO if s.is_production else logging.DEBUG if s.environment == "debug" else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for h in logging.getLogger().handlers:
        h.addFilter(_RedactFilter())
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Dev convenience: ensure tables exist on SQLite. Production uses `alembic upgrade head`.
        if s.is_sqlite:
            Base.metadata.create_all(get_engine())
        secrets_store.refresh(force=True)  # API keys saved from Settings override .env
        yield

    app = FastAPI(title="ClementIQ API", version="1.0.0", lifespan=lifespan,
                  description="Clement Core (deterministic financial engine) + Clement Gemini (explanations).",
                  docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in s.cors_origins.split(",") if o.strip()],
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid = request.headers.get("x-request-id", uuid.uuid4().hex[:12])
        if secrets_store.is_stale():  # pick up keys saved through another worker process
            await run_in_threadpool(secrets_store.refresh)
        resp = await call_next(request)
        resp.headers["x-request-id"] = rid
        resp.headers["x-content-type-options"] = "nosniff"
        return resp

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):  # pragma: no cover - safety net
        logging.getLogger("clementiq").exception("unhandled error on %s", request.url.path)
        return JSONResponse({"detail": "internal error"}, status_code=500)

    for r in (system, accounts, scenarios, worldpulse, investments, solana, ai, alerts, insights, integrations, profile, reports):
        app.include_router(r.router)
    return app


app = create_app()
