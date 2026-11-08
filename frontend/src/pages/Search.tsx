import { useMutation, useQuery } from "@tanstack/react-query";
import { FileSearch, FileText, Search as SearchIcon, Sparkles } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Badge, Button, Card, DemoBadge, EmptyState, ErrorBox, Input, PageHeader, Skeleton, StatusBadge, Tabs } from "../components/ui";
import { api } from "../lib/api";
import { date, money } from "../lib/format";

const EXAMPLES = [
  "Find all invoices from ABC Corporation above $5,000.",
  "Show invoices with inconsistent tax calculations.",
  "Find duplicate invoices uploaded last month.",
  "Invoices that need manual review",
  "Invoices in EUR between 1,000 and 10,000",
];

function ResultRow({ r }: { r: any }) {
  return (
    <Link to={`/documents/${r.document_id}`} className="group flex flex-col gap-3 px-5 py-4 transition hover:bg-brand-50/40 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-sm font-semibold">{r.invoice_number || "No invoice #"}</span>
          <StatusBadge status={r.validation_status} />
          {r.is_demo && <DemoBadge />}
          {r.score !== null && r.score !== undefined && <Badge tone="gray">relevance {Math.round(r.score * 100)}%</Badge>}
        </div>
        <div className="mt-1 text-sm text-ink-soft">
          {r.supplier_name || "Unknown supplier"} → {r.customer_name || "Unknown customer"} · {date(r.invoice_date)}
        </div>
        <div className="mt-1 flex items-center gap-1.5 text-xs text-muted">
          <FileText className="h-3.5 w-3.5" /> Source: <span className="font-medium text-ink-soft group-hover:text-accent-600">{r.source.name}</span>
          {r.source.ref?.row && <span>· row {r.source.ref.row}</span>}
          {r.source.field_sources?.total?.page && <span>· total on page {r.source.field_sources.total.page}</span>}
        </div>
      </div>
      <div className="text-right font-display text-xl font-extrabold tabular-nums text-brand-800">{money(r.total, r.currency)}</div>
    </Link>
  );
}

function Semantic({ initial }: { initial: string }) {
  const [q, setQ] = useState(initial);
  const m = useMutation({ mutationFn: (query: string) => api("/search/semantic", { body: { query, limit: 30 } }) });
  useEffect(() => {
    if (initial) m.mutate(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial]);
  const run = (e?: FormEvent, text?: string) => {
    e?.preventDefault();
    const query = text ?? q;
    if (text) setQ(text);
    if (query.trim().length >= 2) m.mutate(query.trim());
  };
  const r = m.data;
  const interp = r?.interpretation;
  return (
    <div className="space-y-5">
      <Card className="p-5">
        <form onSubmit={run} className="flex flex-col gap-3 sm:flex-row">
          <div className="relative flex-1">
            <Sparkles className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-brand-600" />
            <input className="input pl-10 !py-3 text-base" placeholder='Ask in plain English, e.g. "invoices from ABC Corporation above $5,000"' value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <Button type="submit" size="lg" loading={m.isPending} icon={<SearchIcon className="h-4 w-4" />}>Search</Button>
        </form>
        <div className="mt-3 flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button key={ex} onClick={() => run(undefined, ex)} className="rounded-full border border-line bg-cream px-3 py-1 text-xs text-ink-soft transition hover:border-brand-300 hover:bg-brand-50 hover:text-brand-800">
              {ex}
            </button>
          ))}
        </div>
      </Card>
      <ErrorBox error={m.error} />
      {m.isPending && <Skeleton className="h-48" />}
      {r && (
        <>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-muted">Understood as:</span>
            {interp.explanation.length === 0 && <Badge tone="gray">free-text similarity</Badge>}
            {interp.explanation.map((e: string) => <Badge key={e} tone="brand">{e}</Badge>)}
            {r.semantic_ranking && <Badge tone="blue">ranked by semantic similarity</Badge>}
          </div>
          <Card className="overflow-hidden">
            <div className="border-b border-line px-5 py-3 text-sm font-semibold">{r.invoices.length} matching invoice{r.invoices.length === 1 ? "" : "s"}</div>
            {r.invoices.length === 0 ? (
              <EmptyState icon={<FileSearch className="h-6 w-6" />} title="No matching invoices" description="Try a broader query or remove a filter." />
            ) : (
              <div className="divide-y divide-line">{r.invoices.map((x: any) => <ResultRow key={x.invoice_id} r={x} />)}</div>
            )}
          </Card>
          {r.pages.length > 0 && (
            <Card className="overflow-hidden">
              <div className="border-b border-line px-5 py-3 text-sm font-semibold">Related passages in documents</div>
              <ul className="divide-y divide-line">
                {r.pages.map((p: any, i: number) => (
                  <li key={i}>
                    <Link to={`/documents/${p.document_id}`} className="block px-5 py-3.5 hover:bg-brand-50/40">
                      <div className="flex items-center gap-2 text-sm font-medium">
                        {p.document_name} <span className="text-xs font-normal text-muted">· page {p.page_no} · {Math.round(p.score * 100)}%</span>
                      </div>
                      <p className="mt-1 text-xs leading-relaxed text-ink-soft">{p.snippet}</p>
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

function Keyword() {
  const [form, setForm] = useState({ q: "", invoice_number: "", supplier: "", customer: "", date_from: "", date_to: "", total: "", document_name: "" });
  const [query, setQuery] = useState<typeof form | null>(null);
  const { data, isFetching, error } = useQuery({
    queryKey: ["search", "keyword", query],
    queryFn: () => api("/search/keyword", { query: { ...query!, page_size: 50 } }),
    enabled: !!query,
  });
  const set = (k: keyof typeof form) => (e: any) => setForm({ ...form, [k]: e.target.value });
  return (
    <div className="space-y-5">
      <Card className="p-5">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setQuery({ ...form });
          }}
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
        >
          <Input className="sm:col-span-2" label="Any field" placeholder="Number, name, amount…" value={form.q} onChange={set("q")} />
          <Input label="Invoice number" value={form.invoice_number} onChange={set("invoice_number")} />
          <Input label="Document name" value={form.document_name} onChange={set("document_name")} />
          <Input label="Supplier" value={form.supplier} onChange={set("supplier")} />
          <Input label="Customer" value={form.customer} onChange={set("customer")} />
          <Input label="Date from" type="date" value={form.date_from} onChange={set("date_from")} />
          <Input label="Date to" type="date" value={form.date_to} onChange={set("date_to")} />
          <Input label="Exact total" type="number" step="0.01" value={form.total} onChange={set("total")} />
          <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-3 lg:justify-end">
            <Button type="button" variant="ghost" onClick={() => { setForm({ q: "", invoice_number: "", supplier: "", customer: "", date_from: "", date_to: "", total: "", document_name: "" }); setQuery(null); }}>Clear</Button>
            <Button type="submit" loading={isFetching} icon={<SearchIcon className="h-4 w-4" />}>Search</Button>
          </div>
        </form>
      </Card>
      <ErrorBox error={error} />
      {data && (
        <Card className="overflow-hidden">
          <div className="border-b border-line px-5 py-3 text-sm font-semibold">{data.total} result{data.total === 1 ? "" : "s"}</div>
          {data.items.length === 0 ? (
            <EmptyState icon={<FileSearch className="h-6 w-6" />} title="No results" />
          ) : (
            <div className="divide-y divide-line">{data.items.map((x: any) => <ResultRow key={x.invoice_id} r={x} />)}</div>
          )}
        </Card>
      )}
    </div>
  );
}

export default function SearchPage() {
  const [params] = useSearchParams();
  const initial = params.get("q") || "";
  const [tab, setTab] = useState<"semantic" | "keyword">("semantic");
  return (
    <div className="animate-fade-in">
      <PageHeader title="Document Search" subtitle="Search by exact fields, or ask questions in natural language. Results link back to their source documents." />
      <div className="mb-5">
        <Tabs value={tab} onChange={setTab} tabs={[{ key: "semantic", label: <><Sparkles className="h-4 w-4" /> Natural language</> }, { key: "keyword", label: <><SearchIcon className="h-4 w-4" /> Keyword</> }]} />
      </div>
      {tab === "semantic" ? <Semantic initial={initial} key={initial} /> : <Keyword />}
    </div>
  );
}
