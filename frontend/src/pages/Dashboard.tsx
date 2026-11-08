import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  AlertOctagon,
  ArrowRight,
  CheckCircle2,
  Clock3,
  Eye,
  FileStack,
  Receipt,
  Sparkles,
  UploadCloud,
} from "lucide-react";
import { ReactNode, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ActivityChart, DonutChart, Legendary, StackedBars } from "../components/charts";
import { Button, Card, CardHeader, DemoBadge, EmptyState, PageHeader, Skeleton, StatusBadge, Toggle, useToast } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { compact, date, label, money, pct, timeAgo } from "../lib/format";

function Kpi({ icon, label: l, value, hint, tone = "brand", to }: { icon: ReactNode; label: string; value: ReactNode; hint?: ReactNode; tone?: "brand" | "ok" | "warn" | "bad" | "info"; to?: string }) {
  const tones = { brand: "bg-brand-50 text-brand-800", ok: "bg-ok-bg text-ok", warn: "bg-accent-50 text-accent-600", bad: "bg-bad-bg text-bad", info: "bg-info-bg text-info" };
  const body = (
    <Card className="group h-full p-5 transition hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-lift">
      <div className="flex items-start justify-between">
        <div className={clsx("rounded-full p-2.5", tones[tone])}>{icon}</div>
        {to && <ArrowRight className="h-4 w-4 text-accent-500 opacity-0 transition group-hover:opacity-100" />}
      </div>
      <div className="mt-4 font-display text-[32px] font-extrabold leading-none tabular-nums text-brand-800">{value}</div>
      <div className="mt-2 text-[11px] font-bold uppercase tracking-[0.1em] text-muted">{l}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </Card>
  );
  return to ? <Link to={to}>{body}</Link> : body;
}

export default function Dashboard() {
  const { user, can } = useAuth();
  const nav = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const [includeDemo, setIncludeDemo] = useState(true);
  const { data, isLoading } = useQuery({
    queryKey: ["analytics", "overview", includeDemo],
    queryFn: () => api("/analytics/overview", { query: { days: 30, include_demo: includeDemo } }),
  });
  const { data: recent } = useQuery({
    queryKey: ["recent-docs", includeDemo],
    queryFn: () => api("/analytics/recent-documents", { query: { limit: 8, include_demo: includeDemo } }),
  });
  const loadDemo = useMutation({
    mutationFn: () => api("/demo/load", { method: "POST" }),
    onSuccess: (r: any) => {
      toast("success", `${r.documents} sample documents queued for processing`);
      qc.invalidateQueries();
      nav("/queue");
    },
    onError: (e: Error) => toast("error", e.message),
  });

  const k = data?.kpis;
  const isEmpty = k && k.total_documents === 0;
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";

  const fin = (data?.financial || []) as any[];
  const valData = (data?.validation || []).slice(0, 6);
  const invStatus = data ? Object.entries(data.invoice_validation_status).map(([name, value]) => ({ name, value: value as number })).filter((d) => d.value) : [];
  const statusData = data
    ? [
        { name: "completed", value: data.status_counts.completed },
        { name: "needs_review", value: data.status_counts.needs_review },
        { name: "failed", value: data.status_counts.failed },
        { name: "pending", value: data.status_counts.queued + data.status_counts.processing + data.status_counts.uploaded },
      ]
    : [];

  return (
    <div className="animate-fade-in">
      <PageHeader
        eyebrow="Overview"
        title={`${greeting}, ${(user?.full_name || "").split(" ")[0] || "there"}`}
        subtitle="Here's what's happening with your documents today."
        actions={
          <>
            <Button variant="navy" onClick={() => nav("/validation")} icon={<Eye className="h-4 w-4" />}>
              Review queue
            </Button>
            {can("reviewer") && (
              <Button onClick={() => nav("/upload")} icon={<UploadCloud className="h-4 w-4" />}>
                Upload documents
              </Button>
            )}
          </>
        }
      />

      {isEmpty && (
        <Card className="mb-6 overflow-hidden border-0 shadow-navy">
          <div className="relative grid items-center gap-6 overflow-hidden bg-navy-panel p-6 text-white sm:p-10 md:grid-cols-[1fr_auto]">
            <div className="pointer-events-none absolute -right-20 -top-24 h-72 w-72 rounded-full bg-accent-500/20 blur-3xl" />
            <div className="relative">
              <p className="font-hand text-2xl text-accent-300">let's get started</p>
              <h2 className="mt-1 text-3xl font-extrabold text-white">Process your first documents</h2>
              <p className="mt-2 max-w-2xl text-brand-100">
                Upload invoices as PDF, scans (JPG, PNG, TIFF), Excel or CSV. DocuMind extracts the financial data, checks the
                arithmetic, and finds duplicates and mismatches across documents, with no API key required.
              </p>
            </div>
            <div className="relative flex flex-wrap gap-3">
              {can("reviewer") && <Button size="lg" onClick={() => nav("/upload")} icon={<UploadCloud className="h-5 w-5" />}>Upload documents</Button>}
              {can("admin") && (
                <Button size="lg" variant="secondary" className="!border-white/30 !bg-white/10 !text-white hover:!bg-white/20" loading={loadDemo.isPending} onClick={() => loadDemo.mutate()} icon={<Sparkles className="h-5 w-5" />}>
                  Load sample data
                </Button>
              )}
            </div>
          </div>
        </Card>
      )}

      <div className="mb-4 flex justify-end">
        <div className="w-full max-w-xs rounded-xl border border-line bg-white px-4 py-2.5">
          <Toggle checked={includeDemo} onChange={setIncludeDemo} label={<span className="text-xs">Include demo data</span>} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        {isLoading || !k ? (
          Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-36" />)
        ) : (
          <>
            <Kpi icon={<FileStack className="h-5 w-5" />} label="Total Documents" value={compact(k.total_documents)} hint={k.avg_processing_seconds ? `avg ${k.avg_processing_seconds}s per document` : undefined} to="/documents" />
            <Kpi icon={<CheckCircle2 className="h-5 w-5" />} tone="ok" label="Successfully Processed" value={compact(k.processed)} hint={k.success_rate !== null ? `${pct(k.success_rate, 1)} success rate` : undefined} to="/documents?status=completed,needs_review" />
            <Kpi icon={<Clock3 className="h-5 w-5" />} tone="info" label="Pending" value={compact(k.pending)} to="/queue" />
            <Kpi icon={<AlertOctagon className="h-5 w-5" />} tone="bad" label="Failed Jobs" value={compact(k.failed_jobs)} to="/queue?status=failed" />
            <Kpi icon={<Receipt className="h-5 w-5" />} label="Invoices Extracted" value={compact(k.invoices_extracted)} to="/invoices" />
            <Kpi icon={<Eye className="h-5 w-5" />} tone="warn" label="Need Manual Review" value={compact(k.needs_review)} to="/validation" />
          </>
        )}
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Processing activity" subtitle="Documents uploaded, processed and failed over the last 30 days" />
          <div className="p-4 sm:p-6">{data ? <ActivityChart data={data.activity} /> : <Skeleton className="h-64" />}</div>
        </Card>
        <Card>
          <CardHeader title="Successful vs failed" subtitle="Current document status" />
          <div className="grid grid-cols-1 items-center gap-4 p-6 sm:grid-cols-2 xl:grid-cols-1">
            <DonutChart data={statusData} height={190} />
            <Legendary data={statusData} />
          </div>
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader title="Document types" subtitle="By detected type and file format" />
          <div className="p-6">
            <DonutChart data={data?.document_formats || []} height={180} />
            <div className="mt-4">
              <Legendary data={data?.document_types || []} />
            </div>
          </div>
        </Card>
        <Card>
          <CardHeader title="Invoice financial overview" subtitle="Totals by currency (extracted values)" />
          <div className="divide-y divide-line">
            {fin.length === 0 && <p className="p-6 text-sm text-muted">No invoices extracted yet.</p>}
            {fin.map((f) => (
              <div key={f.currency} className="flex items-center justify-between px-6 py-4">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wide text-muted">{f.currency}</div>
                  <div className="font-display text-2xl font-extrabold tabular-nums text-brand-800">{money(f.total, f.currency !== "N/A" ? f.currency : null)}</div>
                </div>
                <div className="text-right text-xs text-muted">
                  <div>
                    <span className="font-semibold text-ink">{f.count}</span> invoices
                  </div>
                  <div>tax {money(f.tax, f.currency !== "N/A" ? f.currency : null)}</div>
                  <div>avg {money(f.average, f.currency !== "N/A" ? f.currency : null)}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>
        <Card>
          <CardHeader title="Validation errors" subtitle="Open issues by rule" action={<Link to="/validation" className="text-sm font-semibold text-accent-600 hover:underline">View</Link>} />
          <div className="p-4">
            {valData.length ? (
              <StackedBars data={valData} keys={["failed", "review", "warning"]} xKey="rule" horizontal height={220} />
            ) : (
              <div className="p-2">
                <DonutChart data={invStatus} height={180} center={<span className="text-xs text-muted">invoices</span>} />
              </div>
            )}
          </div>
        </Card>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Card className="overflow-hidden xl:col-span-2">
          <CardHeader title="Recent documents" action={<Link to="/documents" className="text-sm font-semibold text-accent-600 hover:underline">View all</Link>} />
          {recent && recent.length === 0 ? (
            <EmptyState icon={<FileStack className="h-6 w-6" />} title="No documents yet" description="Uploaded documents will appear here." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px]">
                <thead>
                  <tr>
                    {["Document", "Type", "Uploaded", "Status", "Invoice #", "Total", "Validation", ""].map((h) => (
                      <th key={h} className="table-head">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(recent || []).map((d: any) => (
                    <tr key={d.id} className="cursor-pointer transition hover:bg-brand-50/40" onClick={() => nav(`/documents/${d.id}`)}>
                      <td className="table-cell max-w-[220px]">
                        <div className="flex items-center gap-2">
                          <span className="truncate font-medium">{d.name}</span>
                          {d.is_demo && <DemoBadge />}
                        </div>
                      </td>
                      <td className="table-cell text-muted">{label(d.doc_type || d.file_kind)}</td>
                      <td className="table-cell whitespace-nowrap text-muted">{timeAgo(d.uploaded_at)}</td>
                      <td className="table-cell"><StatusBadge status={d.status} /></td>
                      <td className="table-cell font-mono text-xs">{d.invoice_number || "—"}{d.invoice_count > 1 && <span className="ml-1 text-muted">+{d.invoice_count - 1}</span>}</td>
                      <td className="table-cell whitespace-nowrap tabular-nums">{money(d.total, d.currency)}</td>
                      <td className="table-cell"><StatusBadge status={d.validation_status} /></td>
                      <td className="table-cell text-right"><ArrowRight className="ml-auto h-4 w-4 text-muted" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
        <Card>
          <CardHeader title="Recent processing activity" />
          <ul className="max-h-[440px] divide-y divide-line overflow-y-auto scrollbar-thin">
            {(data?.recent_activity || []).length === 0 && <li className="p-6 text-sm text-muted">No activity yet.</li>}
            {(data?.recent_activity || []).map((a: any, i: number) => (
              <li key={i} className="flex gap-3 px-5 py-3.5">
                <span className={clsx("mt-1.5 h-2 w-2 shrink-0 rounded-full", a.status === "failed" ? "bg-bad" : a.stage === "completed" ? "bg-ok" : "bg-accent-400")} />
                <div className="min-w-0 text-sm">
                  <Link to={`/documents/${a.document_id}`} className="block truncate font-medium hover:text-accent-600">{a.document_name}</Link>
                  <div className="text-xs text-muted">
                    {label(a.stage)} · {a.status} · {timeAgo(a.at)}
                  </div>
                  {a.message && <div className="mt-0.5 truncate text-xs text-ink-soft" title={a.message}>{a.message}</div>}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      </div>
      <p className="mt-6 text-center text-xs text-muted">
        Figures are computed live from processed documents. Items marked <DemoBadge /> are generated sample data. Last refreshed {date(new Date().toISOString())}.
      </p>
    </div>
  );
}
