"use client";
import { useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Accessibility, Bell, CheckCircle2, CircleSlash, KeyRound, LayoutGrid, Palette, Plug, ShieldCheck } from "lucide-react";
import { useSettings, useSources, useVerifiedRole } from "@/lib/hooks";
import { useSession } from "@/lib/store";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/misc";
import { CustomizeDashboard } from "@/components/settings/CustomizeDashboard";
import { AccessibilitySettings, AppearanceSettings, NotificationSettings, PrivacySettings } from "@/components/settings/PersonalSettings";
import { IntegrationKeys } from "@/components/settings/IntegrationKeys";
import { DataSourceStatus } from "@/components/world/WorldPulse";

const INTEGRATION_LABEL: Record<string, string> = {
  gemini: "Google Gemini API", gemini_grounding: "Gemini Google Search grounding", snowflake: "Snowflake Cortex (optional)", news_api: "NewsAPI.org (optional)",
  alpha_vantage: "Alpha Vantage (optional)", email: "SMTP email delivery", worldpulse_live: "Live WorldPulse retrieval",
};

const SECTIONS = [
  { id: "dashboard", label: "Customize Dashboard", icon: LayoutGrid, blurb: "Choose which tools appear on Home and in the tool switcher, their order, favorites and layout." },
  { id: "accessibility", label: "Accessibility & Comfort", icon: Accessibility, blurb: "Text size, contrast, motion, Simple and Calm modes, chart tables and read-aloud." },
  { id: "appearance", label: "Appearance", icon: Palette, blurb: "Theme, orchard scenery and your character's visibility." },
  { id: "notifications", label: "Notifications", icon: Bell, blurb: "Which alerts you receive and how." },
  { id: "privacy", label: "Privacy & AI", icon: ShieldCheck, blurb: "AI personalization, privacy mode and image consent." },
  { id: "account", label: "Account & Integrations", icon: Plug, blurb: "API keys, server integrations and data-source health." },
] as const;
/** Older links keep working. */
const ALIASES: Record<string, string> = { integrations: "account" };
type SectionId = (typeof SECTIONS)[number]["id"];

function Integrations() {
  const s = useSettings();
  const sources = useSources();
  const role = useVerifiedRole();
  return (
    <div className="space-y-5">
    {role === "admin" ? <IntegrationKeys /> : (
      <p className="rounded-xl border border-line bg-surface px-4 py-3 text-sm text-ink-2">
        <KeyRound className="mr-1.5 inline size-4" />API keys can be entered here by an <b>admin</b>. Sign in with the admin access code to manage them.
      </p>
    )}
    <div className="grid gap-5 lg:grid-cols-2">
      <Card><CardHeader><div><CardTitle>Integrations</CardTitle><CardDescription>Set in <code>.env</code> or entered above by an admin. Keys never reach the browser.</CardDescription></div></CardHeader>
        <CardContent><ul className="space-y-1.5 text-sm">{s.data && Object.entries(s.data.integrations).filter(([k]) => k in INTEGRATION_LABEL).map(([k, v]) => (
          <li key={k} className="flex items-center justify-between">{INTEGRATION_LABEL[k]}{v ? <span className="flex items-center gap-1 text-xs text-good"><CheckCircle2 className="size-3.5" /> enabled</span> : <span className="flex items-center gap-1 text-xs text-ink-3"><CircleSlash className="size-3.5" /> not configured</span>}</li>
        ))}
        {s.data && <li className="flex items-center justify-between">Database<span className="text-xs text-ink-2">{String(s.data.integrations.database)}{s.data.integrations.gemini_model ? ` · Gemini ${s.data.integrations.gemini_model}` : ""}</span></li>}</ul></CardContent></Card>
      <Card><CardHeader><div><CardTitle>Data source status</CardTitle></div></CardHeader><CardContent>{sources.data ? <DataSourceStatus sources={sources.data.sources} monitoring={sources.data.monitoring} /> : <Skeleton className="h-24" />}</CardContent></Card>
    </div>
    </div>
  );
}

export default function SettingsPage() {
  const params = useSearchParams();
  const router = useRouter();
  const path = usePathname();
  const sub = useSession((s) => s.sub);
  const role = useVerifiedRole();
  const raw = params.get("section") ?? "dashboard";
  // Profile editing lives on its own page (/profile); keep old links working.
  useEffect(() => { if (raw === "profile") router.replace("/profile"); }, [raw, router]);
  const section = (SECTIONS.find((s) => s.id === (ALIASES[raw] ?? raw))?.id ?? "dashboard") as SectionId;
  const meta = SECTIONS.find((s) => s.id === section)!;
  const go = (id: SectionId) => router.replace(`${path}?section=${id}`, { scroll: false });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-ink">Settings</h1>
        <p className="text-sm text-ink-2">Your dashboard. Your money. Your financial garden. · signed in as <b>{sub}</b> ({role})</p>
      </div>
      <nav aria-label="Settings sections" className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1">
        {SECTIONS.map((s) => (
          <button key={s.id} onClick={() => go(s.id)} aria-current={section === s.id ? "page" : undefined}
            className={cn("inline-flex shrink-0 cursor-pointer items-center gap-2 rounded-full border px-4 py-2 text-sm font-semibold transition",
              section === s.id ? "border-tangerine bg-tangerine text-white shadow-sm" : "border-line bg-surface text-ink-2 hover:border-tangerine/50 hover:text-ink")}>
            <s.icon className="size-4" /> {s.label}
          </button>
        ))}
      </nav>
      <section aria-labelledby="section-title">
        <h2 id="section-title" className="text-lg font-bold text-ink">{meta.label}</h2>
        <p className="mb-4 text-sm text-ink-2">{meta.blurb}</p>
        {section === "dashboard" && <CustomizeDashboard />}
        {section === "accessibility" && <AccessibilitySettings />}
        {section === "appearance" && <AppearanceSettings />}
        {section === "notifications" && <NotificationSettings />}
        {section === "privacy" && <PrivacySettings />}
        {section === "account" && <Integrations />}
      </section>
    </div>
  );
}
