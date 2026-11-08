/**
 * Shared ClementIQ API types + Zod schemas.
 * The backend (FastAPI/Pydantic) is the source of truth; these mirror its responses so the
 * frontend can validate critical payloads at runtime (`parseRunway`, `ShockRequestSchema`, …).
 */
import { z } from "zod";

export const EngineSchema = z.enum(["clement-core", "clement-gemini", "clement-core-template", "snowflake-cortex"]);
export type Engine = z.infer<typeof EngineSchema> | string;

export const RunwaySchema = z.object({
  months: z.number(),
  months_precise: z.number(),
  raw_months: z.number().nullable(),
  no_shortfall: z.boolean(),
  capped: z.boolean(),
  buffer_left: z.number(),
  gap: z.number(),
  status: z.enum(["depleted", "no_shortfall", "capped", "finite"]),
  display: z.string(),
  formula: z.string(),
});
export type Runway = z.infer<typeof RunwaySchema>;

export const ShockTypeSchema = z.enum([
  "job_loss", "income_reduction", "reduced_hours", "rent_increase", "bill_inflation", "emergency_expense",
  "vehicle_repair", "transport_cost", "grocery_cost", "loan_payment_increase", "spending_inflation",
]);
export type ShockType = z.infer<typeof ShockTypeSchema>;

export const ShockComponentSchema = z.object({
  type: ShockTypeSchema,
  income_replacement_pct: z.number().min(0).max(100).optional(),
  pct: z.number().min(0).max(500).optional(),
  amount: z.number().min(0).max(10_000_000).optional(),
  months_of_spending: z.number().min(0).max(36).optional(),
  duration_months: z.number().int().min(1).max(120).optional(),
  wage_share_pct: z.number().min(0).max(100).optional(),
});
export type ShockComponent = z.infer<typeof ShockComponentSchema>;

export const ShockRequestSchema = z.object({
  account_id: z.number().int(),
  components: z.array(ShockComponentSchema).min(1).max(12),
  mode: z.enum(["judging", "extended"]).default("judging"),
  horizon_months: z.number().int().min(3).max(120).default(24),
  discretionary_cut_pct: z.number().min(0).max(100).default(0),
});
export type ShockRequest = z.input<typeof ShockRequestSchema>;

export interface Calc {
  name: string; value: number | null; unit: string; formula: string; inputs: Record<string, unknown>;
  assumptions: string[]; provenance: string; warnings: string[]; engine: string; computed_at: string;
}

export interface Judging { I: number; S: number; F: number; H: number; B: number; P: number; runway: Runway; buffer_months: string[] }

export interface SeriesPoint {
  month: string; money_in: number; money_out: number; household_bills: number; insurance: number; loan_payments: number;
  bank_fees: number; discretionary: number; fixed: number; net_flow: number; month_end_balance: number;
  avg_daily_balance: number; min_balance: number; days_below_zero: number;
}

export interface ScoreComponent {
  key: string; label: string; weight: number; points: number; max_points: number; score: number;
  value: number | null; unit: string; display?: string;
}

export interface Resilience {
  score: number; band: string; breakdown: ScoreComponent[]; strengths: string[]; risks: string[];
  improvements: { component: string; action: string; potential_points: number }[];
  weights: Record<string, number>; warnings: string[]; disclaimer: string;
  history?: { month: string; score: number }[]; percentile?: number;
}

export interface Summary {
  engine: string; engine_version: string; computed_at: string; input_hash: string; account_id: number;
  profile: {
    account_id: number; frequency: string | null; account_opened: string | null;
    district: { district_id: number; name: string; region: string; average_salary: number | null; unemployment_rate_2023: number | null } | null;
    holders: { disposition_id: number; role: string }[]; cards: { card_type: string; issued: string | null }[];
    standing_orders: { purpose: string; amount: number; to_bank: string | null }[]; standing_orders_total: number;
  };
  judging: Judging; calculations: Calc[];
  metrics: {
    discretionary: number; monthly_surplus: number; avg_monthly_cash_flow: number; emergency_fund_target_3m: number;
    emergency_fund_progress: number | null; coverage_months: number | null; income_cv: number | null; spending_cv: number | null;
    days_below_zero_12m: number; category_medians: Record<string, number>; months_of_data: number; first_month: string; last_month: string;
  };
  loan: { loan_id: number; status: string; monthly_payment: number; running: boolean; amount: number; duration_months: number; loan_start: string } | null;
  series: SeriesPoint[];
  net_position: { available: boolean; label: string; series: { month: string; balance: number; loan_remaining: number; net_position: number }[] };
  resilience: Resilience;
  anomalies: { month: string; category: string; value: number; typical: number; robust_z: number; excess: number }[];
  trends: { category_changes: { category: string; prior_6m: number; recent_6m: number; change: number; change_pct: number | null }[] } & Record<string, unknown>;
  forecast: { available: boolean; points?: { month: string; forecast: number; lower: number; upper: number }[]; method?: string; label?: string };
  warnings: string[]; data_as_of: string; reference_date: string;
}

export interface Effect { type: ShockType; label: string; delta_income: number; delta_spending: number; one_off: number; rule: string }

export interface SimResult {
  engine: string; input_hash: string; computed_at: string; account_id: number; mode: "judging" | "extended";
  baseline: { I: number; S: number; F: number; H: number; B: number; P: number; income: number; spending: number; gap: number; runway: Runway };
  scenario: { income: number; spending: number; one_off_costs: number; buffer_left: number; gap: number; runway: Runway };
  deltas: { income: number; spending: number; monthly_shortfall_change: number; buffer_change: number; runway_change: number };
  effects: Effect[];
  verdict: { required_months: number; survives: boolean; text: string; shortfall_over_period: number } | null;
  behavioural_cut: { cut_amount: number; spending_after: number; runway: Runway } | null;
  projection: { month: number; baseline_balance: number; scenario_balance: number; scenario_income: number; scenario_spending: number }[];
  depletion_month: number | null; assumptions: string[]; warnings: string[];
}

export interface Preset { id: string; name: string; judging: boolean; components: ShockComponent[] }

export interface AIResult<T = Record<string, unknown>> {
  engine: string; model?: string; content: T; fallback_reason?: string; cached?: boolean;
  number_check?: { ok: boolean; checked: number; unverified: number[] };
}

export interface NewsEvent {
  id: number; headline: string; source_name: string; source_type: "official" | "news" | "aggregator"; provider: string; url: string;
  published_at: string | null; event_date: string | null; country: string | null; country_code: string | null;
  latitude: number | null; longitude: number | null; location_basis: string | null; topic: string; topic_label: string;
  classification: string; summary: string | null; summary_engine: string | null; exposure_categories: string[];
  confidence_note: string | null; reliability: number; retrieved_at: string | null;
  /** Snowflake Cortex analysis (null when Cortex was off or failed for this item). */
  cortex_topic?: string | null; cortex_confidence?: "low" | "medium" | "high" | null;
  cortex_injection_detected?: boolean | null; cortex_relevant?: boolean | null;
  cortex_model?: string | null; cortex_request_id?: string | null; cortex_accepted?: boolean;
  cortex_analysis?: CortexAnalysis | null;
}

export interface CortexAnalysis {
  is_relevant: boolean; topic: string; secondary_topics: string[]; countries_affected: string[]; industries_affected: string[];
  verified_facts: { statement: string; evidence_quote: string }[];
  economic_indicators: { name: string; value_as_stated: string | null; evidence_quote: string | null }[];
  direction: "increase" | "decrease" | "mixed" | "unclear"; uncertainties: string[]; injection_detected: boolean;
  analysis_confidence: "low" | "medium" | "high"; model: string; request_id: string | null; facts_failed_grounding: number;
}

export interface Indicator {
  id: number; source: string; series_code: string; name: string; country: string; topic: string; unit: string; source_url: string;
  latest: { date: string; value: number }; previous: { date: string; value: number } | null; retrieved_at: string | null;
  history: { date: string; value: number }[];
}

export interface SourceStatus { source: string; kind: string; status: string; last_success_at: string | null; last_attempt_at: string | null; last_error: string | null; records: number; stale: boolean }

export interface Alert {
  id: number; account_id: number | null; category: string; severity: "low" | "medium" | "high"; title: string; source: string;
  event_timestamp: string | null; relevance: string; relevance_score: number; score_breakdown: Record<string, number>;
  modeled_impact: Record<string, unknown>; confidence: string; suggested_action: string; simulation_link: string | null;
  news_event_id: number | null; explanation: string | null; explanation_engine: string | null; is_read: boolean;
  delivered_channels: string[]; created_at: string | null;
}

export interface Holding {
  id?: number; symbol: string; name: string; asset_class: "stock" | "etf" | "bond" | "mutual_fund" | "cash" | "crypto";
  sector: string | null; quantity: number; cost_basis: number | null; price: number | null; price_source: string | null;
  price_as_of: string | null; holding_kind: "user" | "connected" | "demo" | "hypothetical"; value: number | null;
  gain: number | null; gain_pct: number | null; weight: number | null;
}

export const HoldingFormSchema = z.object({
  symbol: z.string().min(1).max(32),
  name: z.string().max(120).optional(),
  asset_class: z.enum(["stock", "etf", "bond", "mutual_fund", "cash", "crypto"]),
  sector: z.string().max(48).optional(),
  quantity: z.number().positive(),
  cost_basis: z.number().min(0).optional(),
  price: z.number().min(0).optional(),
  holding_kind: z.enum(["user", "hypothetical"]),
});
export type HoldingForm = z.infer<typeof HoldingFormSchema>;

/** Base58 32-byte Solana public key (client-side pre-check; the server re-validates). */
export const SolanaAddressSchema = z.string().regex(/^[1-9A-HJ-NP-Za-km-z]{32,44}$/, "Not a valid Solana public address");

export function parseRunway(x: unknown): Runway {
  return RunwaySchema.parse(x);
}
