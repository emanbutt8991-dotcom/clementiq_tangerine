"use client";
import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, CheckCircle2, UserRound, XCircle } from "lucide-react";
import type { ShockComponent } from "@clementiq/shared-types";
import { api } from "@/lib/api";
import { money } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useAccount, usePresets, useSummary } from "@/lib/hooks";
import { Badge } from "@/components/ui/badge";
import { ErrorState, Skeleton, Spinner } from "@/components/ui/misc";
import { CustomerSelector } from "@/components/layout/CustomerSelector";
import { useStaffGate } from "@/components/stress/useStaffGate";
import { ShockScenarioSelector } from "@/components/finance/Shock";
import { AIInsightCard } from "@/components/ai/AIInsightCard";
import {
  ANALYST_DEFAULT, BackupView, Disclosure, FEATURED, GoalCard, NowCard, Note, ResultView, Section, ShockPicker, TONE_TEXT, TypicalMonth,
  bigRunway, edgeCases, riskOf, runwayCaption, runwayTone, useAccountExtras, useShock,
} from "@/components/stress/parts";

interface Verify { inputs: Record<string, number>; rows: { twist: string; reference: string; engine: string; match: boolean }[]; all_match: boolean; formulas: Record<string, string> }

/**
 * Stress Test (staff). One screen, in the order a judge uses it:
 * who → summary strip → twist card → new runway right beneath → the two plans → details on demand.
 */
export default function StressTestPage() {
  const allowed = useStaffGate();
  const accountId = useAccount();

  const s = useSummary(accountId);
  const presets = usePresets();
  const [picked, setPicked] = useState<ShockComponent[] | null>(null);
  const components = picked ?? ANALYST_DEFAULT;
  const { shock, sim, backup } = useShock(accountId, components);
  const { goal, obl } = useAccountExtras(accountId);
  const verify = useQuery({ queryKey: ["verify", accountId], queryFn: () => api<Verify>(`/judge/verify/${accountId}`), enabled: !!accountId && allowed });

  const j = s.data?.judging;
  const risk = riskOf(j, obl.data);
  const others = (presets.data?.presets ?? []).filter((p) => p.judging && !(FEATURED as readonly string[]).includes(p.id));
  if (!allowed) return null;

  const flags = [
    risk.shortThisMonth && { tone: "bad" as const, text: "Short this month" },
    risk.loanBehind && { tone: "bad" as const, text: "Loan behind (D)" },
    risk.thinBuffer && { tone: "warn" as const, text: "Thin buffer" },
    risk.pastDefault && { tone: "warn" as const, text: "Past default (B)" },
  ].filter(Boolean) as { tone: "bad" | "warn"; text: string }[];

  return (
    <div className="space-y-5">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="large-title">Stress Test</h1>
          <p className="mt-1 text-[15px] text-ink-3">Enter any account, pick a twist card, read the new runway and the plan.</p>
        </div>
        <div className="flex flex-col gap-2 lg:items-end">
          <CustomerSelector />
        </div>
      </section>

      {!accountId && (
        <div className="rounded-2xl shadow-card bg-surface p-10 text-center">
          <p className="text-[17px] font-semibold">Choose a customer to begin</p>
          <p className="mt-1 text-[15px] text-ink-3">Pick an account above, or open one from <Link href="/accounts" className="text-tangerine">Needs Attention</Link>.</p>
        </div>
      )}
      {s.error && <ErrorState error={s.error} />}

      {accountId && (
        <>
          {/* 1 · Summary strip: the six README inputs at a glance, today's runway, and any risk flags. */}
          <section aria-label="Customer summary" className="rounded-2xl shadow-card bg-surface p-4 sm:p-5">
            {!j ? <Skeleton className="h-16" /> : (
              <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
                <div>
                  <p className="text-[13px] font-semibold text-ink-3">Account</p>
                  <p className="tabular text-[22px] font-bold leading-tight">#{accountId}</p>
                </div>
                <dl className="flex flex-wrap gap-x-5 gap-y-2">
                  {(["I", "S", "B", "P"] as const).map((k) => (
                    <div key={k}><dt className="text-[12px] text-ink-3">{({ I: "Income", S: "Spending", B: "Buffer", P: "Loan pmt" })[k]} ({k})</dt><dd className="tabular text-[17px] font-semibold">{money(j[k])}</dd></div>
                  ))}
                  <div><dt className="text-[12px] text-ink-3">Runway today</dt>
                    <dd className={cn("tabular text-[17px] font-semibold", TONE_TEXT[runwayTone(j.runway, j, risk)])}>{bigRunway(j.runway)} <span className="text-[12px] font-normal text-ink-3">{j.runway.no_shortfall ? "no shortfall" : "months"}</span></dd></div>
                </dl>
                <div className="flex flex-1 flex-wrap items-center justify-end gap-2">
                  {flags.length ? flags.map((f) => <Badge key={f.text} tone={f.tone === "bad" ? "bad" : "warn"}>{f.text}</Badge>) : obl.data && <Badge tone="good"><CheckCircle2 aria-hidden /> No flags</Badge>}
                  <Link href={`/dashboard?account=${accountId}`} className="flex min-h-9 items-center gap-1 rounded-full bg-cream px-3 text-[13px] font-medium text-ink hover:bg-peach"><UserRound className="size-3.5" aria-hidden />Account details</Link>
                </div>
              </div>
            )}
          </section>

          {/* 2 · Twist card, with the new numbers directly beneath it. */}
          <Section title="Twist card" desc="Judging Mode · README formulas only"
            right={<div className="flex items-center gap-2">{sim.isFetching && <Spinner />}{verify.data && (verify.data.all_match
              ? <Badge tone="good"><CheckCircle2 aria-hidden /> README check</Badge> : <Badge tone="bad"><XCircle aria-hidden /> mismatch</Badge>)}</div>}>
            <div className="space-y-5">
              {presets.data ? <ShockPicker presets={presets.data.presets} components={components} onPick={(c) => setPicked(c)} mode="analyst" /> : <Skeleton className="h-14" />}
              {presets.data && (
                <details className="group">
                  <summary className="flex min-h-11 cursor-pointer list-none items-center gap-1 text-[15px] font-medium text-tangerine [&::-webkit-details-marker]:hidden">More twist cards, sizes and combinations<ChevronDown className="size-4 transition-transform group-open:rotate-180" aria-hidden /></summary>
                  <div className="pt-3">
                    <ShockScenarioSelector components={components} onChange={setPicked} types={presets.data.types} presets={others}
                      onPreset={(p) => setPicked(p.components)} mode="judging" sValue={j?.S} />
                  </div>
                </details>
              )}
              <div className="border-t border-line pt-5">
                {sim.error ? <ErrorState error={sim.error} /> : !sim.data ? <Skeleton className="h-56" /> : <ResultView sim={sim.data} j={j} risk={risk} mode="analyst" />}
              </div>
              {j && edgeCases(j, "analyst").map((e) => <Note key={e.text} tone={e.tone}>{e.text}</Note>)}
            </div>
          </Section>

          {/* 3 · The two plans the README asks for, side by side. */}
          <div className="grid gap-5 lg:grid-cols-2">
            <GoalCard g={goal.data} j={j} mode="analyst" risk={risk} />
            <Section title="Backup Plan" desc="For the customer: if this twist happens">
              {backup.error ? <ErrorState error={backup.error} /> : !backup.data ? <Skeleton className="h-28" /> : <BackupView b={backup.data} risk={risk} mode="analyst" />}
            </Section>
          </div>

          {/* 4 · Details on demand. Payments open by themselves when something is wrong this month. */}
          <div className="space-y-3">
            {obl.data ? (
              <Disclosure title="This month: fixed payments vs balance" defaultOpen={risk.shortThisMonth || risk.loanBehind}
                badge={obl.data.status === "short" ? <Badge tone="bad">short</Badge> : obl.data.status === "tight" ? <Badge tone="warn">tight</Badge> : undefined}>
                <NowCard o={obl.data} j={j} risk={risk} mode="analyst" bare />
              </Disclosure>
            ) : obl.error ? <ErrorState error={obl.error} /> : null}
            {j && (
              <Disclosure title="Know the customer (README inputs)">
                <TypicalMonth j={j} mode="analyst" />
                <p className="mt-2 text-[13px] text-ink-3">Runway today: {bigRunway(j.runway)} {runwayCaption(j.runway)}.</p>
              </Disclosure>
            )}
            <Disclosure title="How these numbers are calculated">
              <table className="w-full text-[13px]">
                <caption className="sr-only">README twist cards recomputed independently</caption>
                <thead><tr className="text-left text-ink-3"><th className="py-1 font-medium">README twist</th><th className="text-right font-medium">Reference</th><th className="text-right font-medium">Engine</th><th className="text-right font-medium">Match</th></tr></thead>
                <tbody>{verify.data?.rows.map((r) => (
                  <tr key={r.twist} className="border-t border-line"><td className="py-2">{r.twist}</td><td className="tabular text-right">{r.reference}</td><td className="tabular text-right font-semibold">{r.engine}</td>
                    <td className="text-right">{r.match ? <span className="text-good">Yes</span> : <span className="text-bad">No</span>}</td></tr>
                ))}</tbody>
              </table>
              {verify.data && <dl className="mt-3 grid gap-1 text-[12px] text-ink-2 sm:grid-cols-2">{Object.entries(verify.data.formulas).map(([k, v]) => <div key={k}><dt className="inline font-semibold text-ink">{k}</dt> <dd className="inline">= {v}</dd></div>)}</dl>}
            </Disclosure>
            {shock && (
              <Disclosure title="Explain in plain language">
                <AIInsightCard title="Explanation" endpoint="/ai/explain-scenario" kind="scenario" key={JSON.stringify(shock)} body={{ request: shock }} />
              </Disclosure>
            )}
          </div>
        </>
      )}
    </div>
  );
}
