from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="clementiq-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["GEMINI_API_KEY"] = ""
# Tests never use real credentials from the root .env (env vars take precedence over .env).
for _k in ("SNOWFLAKE_ACCOUNT_URL", "SNOWFLAKE_PAT", "NEWS_API_KEY", "ALPHA_VANTAGE_KEY", "SMTP_HOST", "SMTP_PASSWORD"):
    os.environ[_k] = ""
os.environ["SNOWFLAKE_CORTEX_ENABLED"] = "false"
os.environ["WORLDPULSE_LIVE"] = "false"
os.environ["CLEMENTIQ_ENV"] = "test"
os.environ["RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["AI_RATE_LIMIT_PER_MINUTE"] = "100000"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from tests.fixture_data import write_dataset  # noqa: E402

DATA_DIR = write_dataset(_TMP / "data")


@pytest.fixture(scope="session")
def data_dir() -> Path:
    return DATA_DIR


@pytest.fixture(scope="session")
def imported(data_dir):
    from clementiq.ingestion.importer import run_import
    return run_import(data_dir, force=True)


@pytest.fixture(scope="session")
def client(imported):
    from fastapi.testclient import TestClient
    from clementiq.main import app
    with TestClient(app) as c:
        yield c


def _login(client, role, code, account_id=None):
    r = client.post("/api/auth/demo-login", json={"role": role, "access_code": code, "account_id": account_id})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def judge(client):
    return _login(client, "judge", "tangerine-judge")


@pytest.fixture(scope="session")
def customer_1001(client):
    return _login(client, "customer", "tangerine-customer", 1001)


@pytest.fixture(scope="session")
def admin(client):
    return _login(client, "admin", "tangerine-admin")
