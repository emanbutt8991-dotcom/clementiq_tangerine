"use client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Eye, EyeOff, KeyRound, Lock, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { ErrorState, Skeleton, Spinner } from "@/components/ui/misc";

interface SecretField {
  name: string; env: string; group: string; label: string; secret: boolean; placeholder: string;
  source: "settings" | "environment" | "unset" | "unreadable"; is_set: boolean; display: string;
  updated_at: string | null; updated_by: string | null;
}
interface SecretsResponse { fields: SecretField[]; encryption: string }
interface TestResult { group: string; ok: boolean; message: string }

const GROUPS: { id: string; title: string; blurb: string; link?: { href: string; label: string } }[] = [
  { id: "gemini", title: "Google Gemini", blurb: "Powers the AI Financial Advisor, Explain cards, WorldPulse summaries and the orchard avatar.",
    link: { href: "https://aistudio.google.com/apikey", label: "Get a key in Google AI Studio" } },
  { id: "snowflake", title: "Snowflake Cortex", blurb: "Optional second-opinion review on the Insights page.",
    link: { href: "https://app.snowflake.com", label: "Snowflake → Settings → Authentication → Programmatic access tokens" } },
  { id: "news_api", title: "NewsAPI.org", blurb: "Optional extra news source for WorldPulse (free RSS feeds work without it).",
    link: { href: "https://newsapi.org/register", label: "Register at newsapi.org" } },
  { id: "alpha_vantage", title: "Alpha Vantage", blurb: "Optional live stock quotes for Investments.",
    link: { href: "https://www.alphavantage.co/support/#api-key", label: "Free key at alphavantage.co" } },
  { id: "email", title: "SMTP email", blurb: "Optional alert emails for users who opt in. The port stays in .env (default 587)." },
];

const SOURCE_LABEL: Record<SecretField["source"], string> = {
  settings: "saved here", environment: "from .env", unset: "not set", unreadable: "unreadable: re-enter",
};

export function IntegrationKeys() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["integration-secrets"], queryFn: () => api<SecretsResponse>("/admin/integrations") });
  const onSaved = (d: SecretsResponse) => {
    qc.setQueryData(["integration-secrets"], d);
    for (const k of ["settings", "ai-status", "sources"]) qc.invalidateQueries({ queryKey: [k] });
  };
  if (q.error) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  if (!q.data) return <Skeleton className="h-64" />;
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle className="flex items-center gap-2"><KeyRound className="size-4" /> API keys</CardTitle>
          <CardDescription>
            Paste keys here to switch integrations on immediately, no restart needed. Saved keys override <code>.env</code>,
            are encrypted at rest ({q.data.encryption}) and are never sent back to the browser. Only the last four characters are shown.
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {GROUPS.map((g) => (
          <GroupForm key={g.id} group={g} fields={q.data.fields.filter((f) => f.group === g.id)} onSaved={onSaved} />
        ))}
      </CardContent>
    </Card>
  );
}

function GroupForm({ group, fields, onSaved }: { group: (typeof GROUPS)[number]; fields: SecretField[]; onSaved: (d: SecretsResponse) => void }) {
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [reveal, setReveal] = useState<Record<string, boolean>>({});
  const [test, setTest] = useState<TestResult | null>(null);
  const dirty = Object.values(draft).some((v) => v.trim() !== "");

  const save = useMutation({
    mutationFn: (values: Record<string, string | null>) => api<SecretsResponse>("/admin/integrations", { method: "PUT", json: { values } }),
    onSuccess: (d) => { setDraft({}); setTest(null); onSaved(d); },
  });
  const runTest = useMutation({
    mutationFn: () => api<TestResult>(`/admin/integrations/test/${group.id}`, { method: "POST" }),
    onSuccess: setTest,
    onError: (e) => setTest({ group: group.id, ok: false, message: e instanceof Error ? e.message : "Test failed" }),
  });
  const anySet = fields.some((f) => f.is_set);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const values = Object.fromEntries(Object.entries(draft).filter(([, v]) => v.trim() !== ""));
    if (Object.keys(values).length) save.mutate(values);
  };

  return (
    <form onSubmit={submit} className="rounded-2xl border border-line p-4" autoComplete="off">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold text-ink">{group.title}</h3>
          <p className="text-xs text-ink-2">{group.blurb}</p>
          {group.link && <a href={group.link.href} target="_blank" rel="noreferrer" className="text-xs text-tangerine underline-offset-4 hover:underline">{group.link.label}</a>}
        </div>
        {anySet
          ? <span className="flex items-center gap-1 text-xs text-good"><CheckCircle2 className="size-3.5" /> configured</span>
          : <span className="text-xs text-ink-3">not configured</span>}
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {fields.map((f) => {
          const id = `int-${f.name}`;
          const shown = !f.secret || reveal[f.name];
          return (
            <div key={f.name}>
              <Label htmlFor={id} className="flex items-center justify-between gap-2">
                <span>{f.label} <span className="font-mono text-[10px] text-ink-3">{f.env}</span></span>
                <span className={f.source === "unreadable" ? "text-bad" : f.source === "unset" ? "text-ink-3" : "text-ink-2"}>
                  {f.secret && f.is_set && <Lock className="mr-0.5 inline size-3" />}{SOURCE_LABEL[f.source]}
                </span>
              </Label>
              <div className="flex gap-1.5">
                <div className="relative flex-1">
                  <Input id={id} name={id} type={shown ? "text" : "password"} autoComplete={f.secret ? "new-password" : "off"} spellCheck={false}
                    value={draft[f.name] ?? ""} onChange={(e) => setDraft((d) => ({ ...d, [f.name]: e.target.value }))}
                    placeholder={f.display ? `${f.display} · type to replace` : f.placeholder || "Not set"}
                    className={f.secret ? "pr-9 font-mono" : undefined} />
                  {f.secret && (
                    <button type="button" onClick={() => setReveal((r) => ({ ...r, [f.name]: !r[f.name] }))}
                      aria-label={shown ? `Hide ${f.label}` : `Show ${f.label}`}
                      className="absolute inset-y-0 right-0 flex w-9 cursor-pointer items-center justify-center text-ink-3 hover:text-ink">
                      {shown ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                    </button>
                  )}
                </div>
                {(f.source === "settings" || f.source === "unreadable") && (
                  <Button type="button" variant="ghost" size="sm" className="h-10" disabled={save.isPending}
                    title="Remove the saved value and fall back to .env" onClick={() => save.mutate({ [f.name]: null })}>Clear</Button>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button type="submit" size="sm" disabled={!dirty || save.isPending}>{save.isPending && <Spinner />} Save</Button>
        <Button type="button" variant="outline" size="sm" disabled={!anySet || runTest.isPending || dirty}
          title={dirty ? "Save first, then test" : undefined} onClick={() => runTest.mutate()}>
          {runTest.isPending && <Spinner />} Test connection
        </Button>
        {save.error && <span className="text-xs text-bad">{save.error.message}</span>}
        {test && (
          <span role="status" className={`flex items-center gap-1 text-xs ${test.ok ? "text-good" : "text-bad"}`}>
            {test.ok ? <CheckCircle2 className="size-3.5" /> : <XCircle className="size-3.5" />} {test.message}
          </span>
        )}
      </div>
    </form>
  );
}
