"""SQLAlchemy models.

Three groups of tables:
  1. RAW      – faithful copies of the nine Tangerine CSVs (never mutated after import).
  2. DERIVED  – analytical tables computed by Clement Core from the raw tables.
  3. APP      – WorldPulse, alerts, portfolios, Solana, AI audit, preferences, jobs.

Time-series tables (transactions, monthly_summaries, economic_observations, market_prices)
are converted into TimescaleDB hypertables on Tiger Data by database/timescale/*.sql.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- RAW ---------------
class District(Base):
    __tablename__ = "districts"
    district_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    district_name: Mapped[str] = mapped_column(String(120))
    region: Mapped[str] = mapped_column(String(120))
    inhabitants: Mapped[int | None] = mapped_column(Integer)
    municipalities_under_500: Mapped[int | None] = mapped_column(Integer)
    municipalities_500_1999: Mapped[int | None] = mapped_column(Integer)
    municipalities_2000_9999: Mapped[int | None] = mapped_column(Integer)
    municipalities_over_10000: Mapped[int | None] = mapped_column(Integer)
    num_cities: Mapped[int | None] = mapped_column(Integer)
    urban_ratio_pct: Mapped[float | None] = mapped_column(Float)
    average_salary: Mapped[float | None] = mapped_column(Float)
    unemployment_rate_2022: Mapped[float | None] = mapped_column(Float)
    unemployment_rate_2023: Mapped[float | None] = mapped_column(Float)
    entrepreneurs_per_1000: Mapped[int | None] = mapped_column(Integer)
    crimes_2022: Mapped[int | None] = mapped_column(Integer)
    crimes_2023: Mapped[int | None] = mapped_column(Integer)


class Account(Base):
    __tablename__ = "accounts"
    account_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.district_id"), index=True)
    frequency: Mapped[str | None] = mapped_column(String(64))
    account_opened: Mapped[date | None] = mapped_column(Date)


class Client(Base):
    __tablename__ = "clients"
    client_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    gender: Mapped[str | None] = mapped_column(String(1))
    birth_date: Mapped[date | None] = mapped_column(Date)
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.district_id"), index=True)


class Disposition(Base):
    __tablename__ = "dispositions"
    disposition_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.client_id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.account_id"), index=True)
    type: Mapped[str] = mapped_column(String(32))


class Card(Base):
    __tablename__ = "cards"
    card_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    disposition_id: Mapped[int] = mapped_column(ForeignKey("dispositions.disposition_id"), index=True)
    card_type: Mapped[str] = mapped_column(String(16))
    issued: Mapped[date | None] = mapped_column(Date)


class Loan(Base):
    __tablename__ = "loans"
    loan_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.account_id"), index=True)
    loan_start: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[float] = mapped_column(Float)
    duration_months: Mapped[int] = mapped_column(Integer)
    monthly_payment: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(1))
    status_meaning: Mapped[str | None] = mapped_column(String(64))
    defaulted: Mapped[int] = mapped_column(Integer)


class StandingOrder(Base):
    __tablename__ = "standing_orders"
    order_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.account_id"), index=True)
    to_bank: Mapped[str | None] = mapped_column(String(8))
    to_account: Mapped[str | None] = mapped_column(String(32))
    amount: Mapped[float] = mapped_column(Float)
    purpose: Mapped[str | None] = mapped_column(String(64))


class Transaction(Base):
    __tablename__ = "transactions"
    transaction_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.account_id"))
    date: Mapped[date] = mapped_column(Date)
    direction: Mapped[str] = mapped_column(String(24))
    operation: Mapped[str | None] = mapped_column(String(48))
    purpose: Mapped[str | None] = mapped_column(String(64))
    amount: Mapped[float] = mapped_column(Float)
    signed_amount: Mapped[float] = mapped_column(Float)
    balance: Mapped[float | None] = mapped_column(Float)
    partner_bank: Mapped[str | None] = mapped_column(String(8))
    partner_account: Mapped[str | None] = mapped_column(String(32))
    __table_args__ = (Index("ix_transactions_account_date", "account_id", "date"),)


class MonthlySummary(Base):
    __tablename__ = "monthly_summaries"
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.account_id"), primary_key=True)
    month: Mapped[str] = mapped_column(String(7), primary_key=True)  # YYYY-MM, as supplied
    month_start: Mapped[date] = mapped_column(Date, index=True)
    money_in: Mapped[float] = mapped_column(Float)
    money_out: Mapped[float] = mapped_column(Float)
    cash_deposits: Mapped[float] = mapped_column(Float)
    transfers_in: Mapped[float] = mapped_column(Float)
    pension_in: Mapped[float] = mapped_column(Float)
    interest_in: Mapped[float] = mapped_column(Float)
    household_bills: Mapped[float] = mapped_column(Float)
    insurance: Mapped[float] = mapped_column(Float)
    loan_payments: Mapped[float] = mapped_column(Float)
    bank_fees: Mapped[float] = mapped_column(Float)
    cash_withdrawals_genuine: Mapped[float] = mapped_column(Float)
    card_withdrawals: Mapped[float] = mapped_column(Float)
    transfers_out_other: Mapped[float] = mapped_column(Float)
    month_end_balance: Mapped[float] = mapped_column(Float)
    min_balance: Mapped[float] = mapped_column(Float)
    avg_daily_balance: Mapped[float] = mapped_column(Float)
    days_below_zero: Mapped[int] = mapped_column(Integer)


# ---------------------------------------------------------------- DERIVED -----------
class AccountBaseline(Base):
    """Clement Core judging-mode baseline per account, recomputed on every import."""

    __tablename__ = "account_baselines"
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.account_id"), primary_key=True)
    income_I: Mapped[float] = mapped_column(Float)
    spending_S: Mapped[float] = mapped_column(Float)
    fixed_costs_F: Mapped[float] = mapped_column(Float)
    household_bills_H: Mapped[float] = mapped_column(Float)
    buffer_B: Mapped[float] = mapped_column(Float)
    loan_payment_P: Mapped[float] = mapped_column(Float)
    months_of_data: Mapped[int] = mapped_column(Integer)
    first_month: Mapped[str] = mapped_column(String(7))
    last_month: Mapped[str] = mapped_column(String(7))
    income_cv: Mapped[float | None] = mapped_column(Float)
    spending_cv: Mapped[float | None] = mapped_column(Float)
    discretionary_D: Mapped[float] = mapped_column(Float)
    days_below_zero_12m: Mapped[int] = mapped_column(Integer)
    resilience_score: Mapped[float | None] = mapped_column(Float)
    runway_ei55: Mapped[float | None] = mapped_column(Float)  # None == no shortfall
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FinancialSnapshot(Base):
    __tablename__ = "financial_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.account_id"), index=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    engine_version: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON)


class ImportRun(Base):
    __tablename__ = "import_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))  # running|success|failed
    rows_read: Mapped[int] = mapped_column(Integer, default=0)
    rows_loaded: Mapped[int] = mapped_column(Integer, default=0)
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------- APP ---------------
class SavedScenario(Base):
    __tablename__ = "shock_scenarios"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.account_id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    spec: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScenarioResult(Base):
    __tablename__ = "scenario_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_id: Mapped[int | None] = mapped_column(ForeignKey("shock_scenarios.id"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.account_id"), index=True)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RecoveryPlan(Base):
    __tablename__ = "recovery_plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.account_id"), index=True)
    plan_type: Mapped[str] = mapped_column(String(16))  # goal|backup
    params: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    checklist_state: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EconomicIndicator(Base):
    __tablename__ = "economic_indicators"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(48))
    series_code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    country: Mapped[str] = mapped_column(String(3), default="CAN")
    topic: Mapped[str] = mapped_column(String(48))
    unit: Mapped[str] = mapped_column(String(48))
    source_url: Mapped[str] = mapped_column(String(500))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    __table_args__ = (UniqueConstraint("source", "series_code", "country", name="uq_indicator"),)


class EconomicObservation(Base):
    __tablename__ = "economic_observations"
    indicator_id: Mapped[int] = mapped_column(ForeignKey("economic_indicators.id"), primary_key=True)
    observed_at: Mapped[date] = mapped_column(Date, primary_key=True)
    value: Mapped[float] = mapped_column(Float)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NewsEvent(Base):
    __tablename__ = "news_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dedup_key: Mapped[str] = mapped_column(String(64), unique=True)
    headline: Mapped[str] = mapped_column(String(500))
    source_name: Mapped[str] = mapped_column(String(200))
    source_type: Mapped[str] = mapped_column(String(24))  # official|news|aggregator
    provider: Mapped[str] = mapped_column(String(48))
    url: Mapped[str] = mapped_column(String(1000))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    event_date: Mapped[date | None] = mapped_column(Date)
    country: Mapped[str | None] = mapped_column(String(64))
    country_code: Mapped[str | None] = mapped_column(String(3))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    location_basis: Mapped[str | None] = mapped_column(String(200))
    topic: Mapped[str] = mapped_column(String(48), index=True)
    classification: Mapped[str] = mapped_column(String(24), default="reported")
    summary: Mapped[str | None] = mapped_column(Text)
    summary_engine: Mapped[str | None] = mapped_column(String(48))
    exposure_categories: Mapped[list] = mapped_column(JSON, default=list)
    confidence_note: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Snowflake Cortex analysis (WorldPulse). Null when Cortex was off or failed for this item.
    cortex_topic: Mapped[str | None] = mapped_column(String(48))
    cortex_confidence: Mapped[str | None] = mapped_column(String(8))
    cortex_injection_detected: Mapped[bool | None] = mapped_column(Boolean)
    cortex_relevant: Mapped[bool | None] = mapped_column(Boolean)
    cortex_model: Mapped[str | None] = mapped_column(String(64))
    cortex_request_id: Mapped[str | None] = mapped_column(String(128))
    cortex_analysis: Mapped[dict | None] = mapped_column(JSON)


class MarketPrice(Base):
    __tablename__ = "market_prices"
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8))
    change_24h_pct: Mapped[float | None] = mapped_column(Float)
    provider: Mapped[str] = mapped_column(String(48))


class PortfolioHolding(Base):
    __tablename__ = "portfolio_holdings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(120))
    asset_class: Mapped[str] = mapped_column(String(24))
    sector: Mapped[str | None] = mapped_column(String(48))
    quantity: Mapped[float] = mapped_column(Float)
    cost_basis: Mapped[float | None] = mapped_column(Float)
    manual_price: Mapped[float | None] = mapped_column(Float)
    holding_kind: Mapped[str] = mapped_column(String(16))  # user|connected|demo|hypothetical
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SavingsGoal(Base):
    __tablename__ = "savings_goals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.account_id"))
    name: Mapped[str] = mapped_column(String(120))
    target_amount: Mapped[float] = mapped_column(Float)
    target_date: Mapped[date | None] = mapped_column(Date)
    salt: Mapped[str] = mapped_column(String(64))
    proof_hash: Mapped[str] = mapped_column(String(64))
    devnet_signature: Mapped[str | None] = mapped_column(String(128))
    devnet_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SolanaWallet(Base):
    __tablename__ = "solana_wallets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    public_key: Mapped[str] = mapped_column(String(64))
    network: Mapped[str] = mapped_column(String(16))
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("owner", "public_key", "network", name="uq_wallet"),)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dedup_key: Mapped[str] = mapped_column(String(128), unique=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.account_id"), index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    severity: Mapped[str] = mapped_column(String(8))
    title: Mapped[str] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(300))
    event_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    relevance: Mapped[str] = mapped_column(Text)
    relevance_score: Mapped[float] = mapped_column(Float)
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    modeled_impact: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[str] = mapped_column(String(24))
    suggested_action: Mapped[str] = mapped_column(Text)
    simulation_link: Mapped[str | None] = mapped_column(String(500))
    news_event_id: Mapped[int | None] = mapped_column(ForeignKey("news_events.id"))
    explanation: Mapped[str | None] = mapped_column(Text)
    explanation_engine: Mapped[str | None] = mapped_column(String(48))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    delivered_channels: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AlertGenerationLog(Base):
    __tablename__ = "alert_generation_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    owner: Mapped[str] = mapped_column(String(64))
    account_id: Mapped[int | None] = mapped_column(Integer)
    candidates: Mapped[int] = mapped_column(Integer)
    created: Mapped[int] = mapped_column(Integer)
    suppressed: Mapped[dict] = mapped_column(JSON, default=dict)


class AIExplanation(Base):
    __tablename__ = "ai_explanations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32))
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    engine: Mapped[str] = mapped_column(String(48))
    model: Mapped[str | None] = mapped_column(String(64))
    output: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    resource: Mapped[str | None] = mapped_column(String(128))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class UserPreference(Base):
    __tablename__ = "user_preferences"
    owner: Mapped[str] = mapped_column(String(64), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DataSourceStatus(Base):
    __tablename__ = "data_source_status"
    source: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))  # ok|error|disabled|never
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    records: Mapped[int] = mapped_column(Integer, default=0)


class UserMedia(Base):
    """Profile photo and generated orchard avatar per user (re-encoded, EXIF stripped).
    Served only to the owning, authenticated user."""

    __tablename__ = "user_media"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # photo | avatar
    mime: Mapped[str] = mapped_column(String(32))
    data: Mapped[bytes] = mapped_column(LargeBinary)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(64))  # upload | gemini:<model>
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("owner", "kind", name="uq_user_media_owner_kind"),)


class CountryGeo(Base):
    """Country reference with capital-city coordinates retrieved from the World Bank country API.
    Map markers only use coordinates from this table — never hand-entered positions."""

    __tablename__ = "country_geo"
    iso3: Mapped[str] = mapped_column(String(3), primary_key=True)
    iso2: Mapped[str] = mapped_column(String(2))
    name: Mapped[str] = mapped_column(String(120))
    capital: Mapped[str | None] = mapped_column(String(120))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    region: Mapped[str | None] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(200), default="World Bank country API")


class JobRun(Base):
    __tablename__ = "job_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job: Mapped[str] = mapped_column(String(64), index=True)
    runner: Mapped[str] = mapped_column(String(32))  # worker|api|cli
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class IntegrationSecret(Base):
    """Integration settings (API keys, endpoints) entered in Settings by an admin.

    `ciphertext` is Fernet-encrypted (AES-128-CBC + HMAC-SHA256); plaintext is never stored and never
    returned by the API. A row overrides the matching environment variable; deleting it reverts.
    """
    __tablename__ = "integration_secrets"
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    ciphertext: Mapped[str] = mapped_column(Text)
    updated_by: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
