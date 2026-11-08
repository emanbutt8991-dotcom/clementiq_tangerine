"use client";
import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Line, LineChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import { Activity, CheckCircle2, CircleSlash, ExternalLink, Landmark, Newspaper, XCircle } from "lucide-react";
import type { Indicator, NewsEvent, SourceStatus } from "@clementiq/shared-types";
import { api } from "@/lib/api";
import { date, money, signedMoney, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { ErrorState, Skeleton } from "@/components/ui/misc";
import { ChartTooltip, SERIES } from "@/components/finance/chart-kit";
import { ShockParameterSlider } from "@/components/finance/Shock";
import { FinancialRunwayGauge } from "@/components/finance/Gauges";
import { AIInsightCard } from "@/components/ai/AIInsightCard";
import type { Monitoring } from "@/lib/hooks";
import { CortexEventBadge } from "@/components/world/Cortex";

const CLASS_TONE: Record<string, "good" | "blue" | "warn" | "violet" | "neutral"> = {
  confirmed: "good", reported: "blue", forecast: "warn", opinion: "violet", speculation: "warn", unclear: "neutral",
};

export function WorldPulseNewsCard({ e, onSimulate, selected }: { e: NewsEvent; onSimulate?: (e: NewsEvent) => void; selected?: boolean }) {
  return (
    <Card className={cn("p-4 transition", selected && "ring-2 ring-tangerine")}>
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        {e.source_type === "official" ? <Badge tone="good"><Landmark /> Official statistic</Badge> : <Badge tone="neutral"><Newspaper /> News report</Badge>}
        <Badge tone={CLASS_TONE[e.classification] ?? "neutral"}>{e.classification}</Badge>
        <Badge tone="orange">{e.topic_label}</Badge>
        {e.country && <span className="text-[0.6875rem] text-ink-3">{e.country}</span>}
      </div>
      <a href={e.url} target="_blank" rel="noopener noreferrer" className="group text-[0.9375rem] font-semibold leading-snug hover:text-tangerine">
        {e.headline} <ExternalLink className="inline size-3 opacity-50 group-hover:opacity-100" />
      </a>
      <p className="mt-1 text-[0.6875rem] text-ink-2">{e.source_name} · published {date(e.published_at)}{e.event_date && ` · event ${date(e.event_date)}`} · retrieved {timeAgo(e.retrieved_at)}</p>
      {e.summary && <p className="mt-2 text-sm text-ink">{e.summary} {e.summary_engine && <span className="text-[0.625rem] text-ink-3">({e.summary_engine})</span>}</p>}
      {e.exposure_categories.length > 0 && <p className="mt-2 text-xs text-ink-2">Possible exposure: {e.exposure_categories.map((c) => c.replace(/_/g, " ")).join(", ")}</p>}
      {e.confidence_note && <p className="mt-1 text-[0.6875rem] italic text-ink-3">{e.confidence_note}</p>}
      <CortexEventBadge e={e} />
      <div className="mt-3 flex items-center justify-between">
        <span className="text-[0.625rem] text-ink-3">Source reliability {Math.round(e.reliability * 100)}%</span>
        {onSimulate && <Button size="sm" variant="secondary" onClick={() => onSimulate(e)}>Simulate impact</Button>}
      </div>
    </Card>
  );
}

export function EconomicIndicatorCard({ i }: { i: Indicator }) {
  const ch = i.previous ? i.latest.value - i.previous.value : null;
  return (
    <Card className="p-4">
      <p className="text-xs font-medium text-ink-2">{i.name}</p>
      <div className="flex items-end justify-between gap-2">
        <p className="tabular text-2xl font-bold">{i.latest.value.toLocaleString("en-CA", { maximumFractionDigits: 4 })}<span className="ml-1 text-xs font-normal text-ink-2">{i.unit}</span></p>
        {ch !== null && <span className="tabular text-xs text-ink-2">{ch > 0 ? "▲" : ch < 0 ? "▼" : "■"} {Math.abs(ch).toLocaleString("en-CA", { maximumFractionDigits: 3 })}</span>}
      </div>
      <div className="h-12"><ResponsiveContainer width="100%" height="100%">
        <LineChart data={i.history}><YAxis hide domain={["auto", "auto"]} /><Tooltip content={<ChartTooltip fmt={(v) => v.toLocaleString("en-CA", { maximumFractionDigits: 3 })} />} />
          <Line dataKey="value" name={i.unit} stroke={SERIES.income} strokeWidth={2} dot={false} /></LineChart>
      </ResponsiveContainer></div>
      <p className="mt-1 text-[0.625rem] text-ink-3">As of {i.latest.date} · <a className="underline" href={i.source_url} target="_blank" rel="noopener noreferrer">{i.source.replace(/_/g, " ")}</a></p>
    </Card>
  );
}

export function DataSourceStatus({ sources, monitoring }: { sources: SourceStatus[]; monitoring?: Monitoring }) {
  return (
    <div className="space-y-2">
      {monitoring && (
        <div className={cn("flex items-start gap-2 rounded-xl p-2.5 text-xs", monitoring.worker_running ? "bg-green-50 text-green-800 dark:bg-green-950 dark:text-green-200" : "bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-200")}>
          <Activity className="mt-0.5 size-4 shrink-0" />
          <span>{monitoring.worker_running ? "Continuous monitoring is running." : monitoring.note}</span>
        </div>
      )}
      <ul className="divide-y divide-line text-xs">
        {sources.filter((s) => s.kind !== "worker").map((s) => (
          <li key={s.source} className="flex items-center justify-between gap-2 py-1.5">
            <span className="flex items-center gap-1.5">
              {s.status === "ok" ? <CheckCircle2 className="size-3.5 text-good" /> : s.status === "disabled" ? <CircleSlash className="size-3.5 text-ink-3" /> : <XCircle className="size-3.5 text-bad" />}
              {s.source.replace(/_/g, " ")}
            </span>
            <span className={cn("text-right", s.stale && s.status === "ok" ? "text-warn" : "text-ink-2")} title={s.last_error ?? undefined}>
              {s.status === "ok" ? `${timeAgo(s.last_success_at)}${s.stale ? " · stale" : ""}` : s.status === "disabled" ? "disabled" : `error · last ok ${timeAgo(s.last_success_at)}`}
            </span>
          </li>
        ))}
        {!sources.length && <li className="py-2 text-ink-3">No retrieval has run yet.</li>}
      </ul>
    </div>
  );
}

interface Impact {
  computed_at: string; topic_label: string; magnitude_unit: string; label: string; additional_monthly_spending: number; additional_monthly_income: number;
  channels: { channel: string; label: string; kind: string; baseline_monthly: number; baseline_description: string; is_estimate: boolean; passthrough: number; effective_change_pct: number | null; monthly_change: number }[];
  baseline: { income: number; spending: number; surplus: number; runway: import("@clementiq/shared-types").Runway };
  scenario: { income: number; spending: number; surplus: number; runway: import("@clementiq/shared-types").Runway };
  levels: Record<string, { additional_monthly_spending: number; additional_monthly_income: number; surplus: number; runway: { display: string } }>;
  investment_channels: { asset: string; channel: string }[]; assumptions: string[]; limitations: string[];
}

export function EventImpactSimulator({ accountId, topics, initial }: { accountId: number; topics: Record<string, string>; initial?: { topic: string; magnitude: number; event?: NewsEvent | null } }) {
  const [topic, setTopic] = useState(initial?.topic ?? "energy");
  const [magnitude, setMagnitude] = useState(initial?.magnitude ?? 10);
  const [level, setLevel] = useState<"low" | "medium" | "high">("medium");
  const body = { account_id: accountId, topic, magnitude, level, event_id: initial?.event?.id ?? null, event_title: initial?.event?.headline ?? null };
  const q = useQuery({ queryKey: ["impact", body], queryFn: () => api<Impact>("/worldpulse/impact", { method: "POST", json: body }), placeholderData: keepPreviousData });
  const r = q.data;
  const isRate = topic === "interest_rate";
  return (
    <div className="grid gap-4 xl:grid-cols-[320px_1fr]">
      <Card className="space-y-4 p-4">
        {initial?.event && <div className="rounded-xl bg-peach p-2.5 text-xs"><b>Event:</b> {initial.event.headline}<span className="block text-ink-2">{initial.event.source_name} · {date(initial.event.published_at)}</span></div>}
        <div><label className="mb-1 block text-xs font-medium text-ink-2">Development</label>
          <Select value={topic} onChange={(e) => { setTopic(e.target.value); setMagnitude(e.target.value === "interest_rate" ? 0.5 : 10); }}>
            {Object.entries(topics).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select></div>
        <ShockParameterSlider label={isRate ? "Rate change (percentage points)" : "Price / index change"} unit="%" value={magnitude} min={isRate ? -3 : -30} max={isRate ? 5 : 60} step={isRate ? 0.25 : 1} onChange={setMagnitude}
          hint={isRate ? "pp, not %" : "change in the underlying price, not in your bills"} />
        <div><p className="mb-1 text-xs font-medium text-ink-2">Pass-through scenario</p>
          <div className="grid grid-cols-3 gap-1 rounded-xl bg-peach p-1">{(["low", "medium", "high"] as const).map((l) => (
            <button key={l} onClick={() => setLevel(l)} aria-pressed={level === l} className={cn("cursor-pointer rounded-lg py-1.5 text-xs font-semibold capitalize", level === l ? "bg-surface text-tangerine shadow-sm" : "text-ink-2")}>{l}</button>
          ))}</div></div>
        <p className="text-[0.6875rem] text-ink-3">A global price change never flows one-for-one into a household budget. Clement Core applies explicit pass-through assumptions per spending channel.</p>
      </Card>
      <div className="space-y-4">
        {q.error && <ErrorState error={q.error} />}
        {!r ? <Skeleton className="h-72" /> : (
          <>
            <Card className="p-4">
              <Badge tone="warn">{r.label}</Badge>
              <div className="mt-3 grid gap-4 md:grid-cols-[1fr_200px]">
                <div className="space-y-2">
                  <div className="grid grid-cols-2 gap-2">
                    <div className="rounded-xl bg-cream p-3"><p className="text-[0.6875rem] text-ink-2">Additional monthly spending</p><p className="tabular text-xl font-bold">{signedMoney(r.additional_monthly_spending)}</p></div>
                    <div className="rounded-xl bg-cream p-3"><p className="text-[0.6875rem] text-ink-2">New monthly surplus / shortfall</p><p className={cn("tabular text-xl font-bold", r.scenario.surplus < 0 ? "text-bad" : "text-good")}>{signedMoney(r.scenario.surplus)}</p></div>
                  </div>
                  {r.additional_monthly_income !== 0 && <p className="text-xs text-ink-2">Savings interest change: {signedMoney(r.additional_monthly_income)}/month</p>}
                  <table className="w-full text-xs">
                    <thead><tr className="text-left text-ink-2"><th className="py-1 font-medium">Channel</th><th className="font-medium">Your baseline</th><th className="text-right font-medium">Pass-through</th><th className="text-right font-medium">Monthly change</th></tr></thead>
                    <tbody>{r.channels.map((c) => (
                      <tr key={c.channel} className="border-t border-line"><td className="py-1.5">{c.label} {c.is_estimate && <Badge tone="warn">estimate</Badge>}</td><td className="text-ink-2">{c.baseline_description}</td>
                        <td className="tabular text-right">{c.passthrough}{c.effective_change_pct !== null && ` (${c.effective_change_pct.toFixed(1)}%)`}</td><td className="tabular text-right font-semibold">{signedMoney(c.monthly_change)}</td></tr>
                    ))}</tbody>
                  </table>
                  {!r.channels.length && <p className="text-xs text-ink-2">{r.limitations[0]}</p>}
                </div>
                <div className="text-center"><p className="text-xs text-ink-2">Runway {r.baseline.runway.display} → </p><FinancialRunwayGauge runway={r.scenario.runway} size={180} /></div>
              </div>
            </Card>
            <div className="grid gap-4 lg:grid-cols-2">
              <Card className="p-4">
                <p className="mb-2 text-sm font-semibold">Low / medium / high</p>
                <table className="w-full text-xs"><thead><tr className="text-left text-ink-2"><th className="py-1 font-medium">Scenario</th><th className="text-right font-medium">Extra spending</th><th className="text-right font-medium">Surplus</th><th className="text-right font-medium">Runway</th></tr></thead>
                  <tbody>{Object.entries(r.levels).map(([k, v]) => (
                    <tr key={k} className={cn("border-t border-line", k === level && "font-semibold text-tangerine")}><td className="py-1.5 capitalize">{k}</td><td className="tabular text-right">{money(v.additional_monthly_spending)}</td><td className="tabular text-right">{signedMoney(v.surplus)}</td><td className="tabular text-right">{v.runway.display}</td></tr>
                  ))}</tbody></table>
                {r.investment_channels.length > 0 && <div className="mt-3"><p className="text-xs font-semibold">Investment transmission channels (qualitative)</p>{r.investment_channels.map((c) => <p key={c.channel} className="text-[0.6875rem] text-ink-2">• <b>{c.asset}</b>: {c.channel}</p>)}</div>}
                <details className="mt-3 text-[0.6875rem] text-ink-2"><summary className="cursor-pointer font-semibold">Assumptions & limitations</summary>{[...r.assumptions, ...r.limitations].map((a) => <p key={a} className="mt-1">• {a}</p>)}</details>
              </Card>
              <AIInsightCard title="Explain this development" endpoint="/worldpulse/impact" kind="scenario" key={JSON.stringify(body)} body={{ ...body, explain: true }} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
