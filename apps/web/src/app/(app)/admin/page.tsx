"use client";
import Link from "next/link";
import { Lock } from "lucide-react";
import { useMe } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { SectionTitle, Skeleton } from "@/components/ui/misc";
import { ImportStatusPanel } from "@/components/admin/ImportStatusPanel";
import { CortexPanel } from "@/components/world/Cortex";

export default function AdminPage() {
  const me = useMe();
  if (me.isLoading) return <Skeleton className="h-64" />;
  if (!me.data?.entitlements.data_import_view) {
    return (
      <div className="mx-auto max-w-xl rounded-3xl border-2 border-line bg-surface p-8 text-center shadow-card" role="alert">
        <Lock className="mx-auto mb-3 size-8 text-ink-3" />
        <h1 className="text-xl font-bold text-ink">Data Import is only available to judges and admins</h1>
        <Button asChild className="mt-5"><Link href="/">Back to Home</Link></Button>
      </div>
    );
  }
  return (
    <div className="space-y-6">
      <SectionTitle title="Data Import" subtitle="Ingestion status of the nine Tangerine challenge datasets. Raw records are preserved; analytics live in derived tables." />
      <ImportStatusPanel />
      {me.data.role === "admin" && <CortexPanel />}
    </div>
  );
}
