"use client";
import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, HeartHandshake } from "lucide-react";
import { api } from "@/lib/api";
import { money } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState, Skeleton } from "@/components/ui/misc";
import { useStaffGate } from "@/components/stress/useStaffGate";
import { FLAG_LABEL, type Attention, type Flag } from "@/components/stress/attention";

const PAGE = 25;

/** Accounts (staff start page): who needs a call this week, most urgent first. */
export default function AccountsPage() {
  const allowed = useStaffGate();
  const [flag, setFlag] = useState<Flag | null>(null);
  const [pages, setPages] = useState(1);
  const q = useQuery({
    queryKey: ["needs-attention", flag, pages],
    queryFn: () => api<Attention>(`/insights/needs-attention?limit=${PAGE * pages}${flag ? `&flag=${flag}` : ""}`),
    enabled: allowed, placeholderData: (prev) => prev,
  });
  if (!allowed) return null;
  const d = q.data;
  const pick = (f: Flag | null) => { setFlag(f); setPages(1); };

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="large-title">Needs Attention</h1>
        <p className="mt-1 text-[15px] text-ink-3">Who needs help now, most urgent first. Open one to run the stress test.</p>
      </div>

      {q.error && <ErrorState error={q.error} />}
      {!d ? <Skeleton className="h-24 rounded-2xl shadow-card" /> : (
        <section aria-label="Needs attention summary" className="rounded-2xl shadow-card bg-surface p-5">
          <p className="text-[15px] leading-relaxed">
            <span className="tabular text-[28px] font-bold leading-none">{d.total.toLocaleString()}</span>{" "}
            of {d.active_accounts.toLocaleString()} active accounts ({(d.share * 100).toFixed(1)}%) have a flag today.
            <span className={d.counts.green_under_formula > 0 ? undefined : "hidden"}> <span className="marker font-semibold">{d.counts.green_under_formula}</span> of them look safe under the runway formula alone.</span>
          </p>
          <div role="group" aria-label="Filter by flag" className="mt-4 flex flex-wrap gap-2">
            {([null, "short", "behind", "thin"] as const).map((f) => (
              <button key={f ?? "all"} onClick={() => pick(f)} aria-pressed={flag === f}
                className={cn("min-h-9 cursor-pointer rounded-full px-3.5 text-[13px] font-medium transition", flag === f ? "bg-ink text-white" : "bg-cream text-ink hover:bg-peach")}>
                <span>{f ? FLAG_LABEL[f] : "All"}</span> <span className="tabular opacity-70">{f ? d.counts[f] : d.total}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      {d && (
        <section aria-label="Needs attention list">
          <ul className="divide-y-[0.5px] divide-line overflow-hidden rounded-2xl shadow-card bg-surface">
            {d.items.map((it) => (
              <li key={it.account_id}>
                <Link href={`/stress-test?account=${it.account_id}`} className="flex min-h-16 items-center gap-4 px-5 py-3 hover:bg-cream active:bg-press">
                  <div className="w-20 shrink-0"><p className="tabular text-[17px] font-semibold">#{it.account_id}</p></div>
                  <div className="flex min-w-0 flex-1 flex-wrap gap-1.5">
                    {it.flags.map((f) => <Badge key={f} tone={f === "thin" ? "warn" : "bad"}>{FLAG_LABEL[f]}</Badge>)}
                  </div>
                  <div className="hidden text-right sm:block">
                    <p className="text-[12px] text-ink-3">After fixed payments</p>
                    <p className={cn("tabular text-[15px] font-semibold", (it.left_after_fixed ?? 0) < 0 ? "text-bad" : "text-ink")}>{money(it.left_after_fixed)}</p>
                  </div>
                  <div className="hidden w-28 text-right md:block">
                    <p className="text-[12px] text-ink-3">If laid off (EI 55%)</p>
                    <p className="tabular text-[15px] font-semibold">{it.runway_ei55 == null ? "120+" : `${it.runway_ei55.toFixed(1)} mo`}</p>
                  </div>
                  <ChevronRight className="size-4 shrink-0 text-chevron" aria-hidden />
                </Link>
              </li>
            ))}
            {d.items.length === 0 && <li className="p-8 text-center text-[15px] text-ink-3">No accounts with this flag.</li>}
          </ul>
          {d.items.length < d.matching && (
            <div className="mt-4 flex justify-center">
              <Button variant="secondary" onClick={() => setPages((n) => n + 1)} disabled={q.isFetching}>Show more ({d.matching - d.items.length} left)</Button>
            </div>
          )}
        </section>
      )}

      {d && (
        <footer className="space-y-1.5 px-1 text-[12px] leading-relaxed text-ink-3">
          <p className="flex items-center gap-1.5 font-semibold text-ink-2"><HeartHandshake className="size-4 text-tangerine" aria-hidden />{d.use}</p>
          {(Object.keys(d.rules) as Flag[]).map((f) => <p key={f}><b className="font-medium text-ink-2">{FLAG_LABEL[f]}:</b> {d.rules[f]}.</p>)}
        </footer>
      )}
    </div>
  );
}
