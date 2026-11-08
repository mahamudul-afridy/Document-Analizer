import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Eye, FileText, Filter, RefreshCw, Search, Trash2, UploadCloud, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  Button,
  Card,
  ConfirmDialog,
  DemoBadge,
  EmptyState,
  PageHeader,
  Pagination,
  Select,
  Skeleton,
  StatusBadge,
  useToast,
} from "../components/ui";
import { api, download } from "../lib/api";
import { useAuth } from "../lib/auth";
import { bytes, date, label, money } from "../lib/format";

const PAGE = 20;

export default function Documents() {
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const { can } = useAuth();
  const [q, setQ] = useState(params.get("q") || "");
  const [showFilters, setShowFilters] = useState(false);
  const [page, setPage] = useState(1);
  const [toDelete, setToDelete] = useState<any>(null);
  const f = {
    q: params.get("q") || "",
    status: params.get("status") || "",
    file_kind: params.get("file_kind") || "",
    doc_type: params.get("doc_type") || "",
    validation_status: params.get("validation_status") || "",
    is_demo: params.get("is_demo") || "",
    date_from: params.get("date_from") || "",
    date_to: params.get("date_to") || "",
    sort: params.get("sort") || "-created_at",
  };
  const activeFilters = Object.entries(f).filter(([k, v]) => v && !["q", "sort"].includes(k)).length;

  useEffect(() => {
    const t = setTimeout(() => setFilter("q", q), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  function setFilter(k: string, v: string) {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    if (next.toString() !== params.toString()) {
      setParams(next, { replace: true });
      setPage(1);
    }
  }

  const { data, isLoading } = useQuery({
    queryKey: ["documents", f, page],
    queryFn: () => api("/documents", { query: { ...f, page, page_size: PAGE } }),
  });

  const reprocess = useMutation({
    mutationFn: (id: string) => api(`/documents/${id}/reprocess`, { method: "POST" }),
    onSuccess: () => {
      toast("success", "Document re-queued for processing");
      qc.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: (e: Error) => toast("error", e.message),
  });
  const del = useMutation({
    mutationFn: (id: string) => api(`/documents/${id}`, { method: "DELETE" }),
    onSuccess: (r: any) => {
      toast("success", `Deleted ${r.deleted}`);
      setToDelete(null);
      qc.invalidateQueries();
    },
    onError: (e: Error) => toast("error", e.message),
  });

  return (
    <div className="animate-fade-in">
      <PageHeader
        title="Document Library"
        subtitle="Search, inspect and manage every processed document."
        actions={can("reviewer") && <Button onClick={() => nav("/upload")} icon={<UploadCloud className="h-4 w-4" />}>Upload</Button>}
      />

      <Card className="mb-4 p-4">
        <div className="flex flex-col gap-3 sm:flex-row">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <input className="input pl-10" placeholder="Search by file name, invoice number, supplier or customer…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <Select value={f.sort} onChange={(e) => setFilter("sort", e.target.value)} className="sm:w-52">
            <option value="-created_at">Newest first</option>
            <option value="created_at">Oldest first</option>
            <option value="original_name">Name A–Z</option>
            <option value="-size_bytes">Largest first</option>
          </Select>
          <Button variant={showFilters || activeFilters ? "soft" : "secondary"} icon={<Filter className="h-4 w-4" />} onClick={() => setShowFilters(!showFilters)}>
            Filters{activeFilters ? ` (${activeFilters})` : ""}
          </Button>
        </div>
        {showFilters && (
          <div className="mt-4 grid animate-fade-in gap-3 border-t border-line pt-4 sm:grid-cols-2 lg:grid-cols-4">
            <Select label="Processing status" value={f.status} onChange={(e) => setFilter("status", e.target.value)}>
              <option value="">Any</option>
              <option value="completed">Completed</option>
              <option value="needs_review">Needs review</option>
              <option value="queued,processing">In progress</option>
              <option value="failed">Failed</option>
            </Select>
            <Select label="Validation" value={f.validation_status} onChange={(e) => setFilter("validation_status", e.target.value)}>
              <option value="">Any</option>
              <option value="passed">Passed</option>
              <option value="warning">Warning</option>
              <option value="review">Manual review</option>
              <option value="failed">Failed</option>
            </Select>
            <Select label="File format" value={f.file_kind} onChange={(e) => setFilter("file_kind", e.target.value)}>
              <option value="">Any</option>
              <option value="pdf">PDF</option>
              <option value="image">Image / scan</option>
              <option value="spreadsheet">Excel</option>
              <option value="csv">CSV</option>
            </Select>
            <Select label="Document type" value={f.doc_type} onChange={(e) => setFilter("doc_type", e.target.value)}>
              <option value="">Any</option>
              <option value="invoice">Invoice</option>
              <option value="receipt">Receipt</option>
              <option value="statement">Statement</option>
              <option value="purchase_order">Purchase order</option>
              <option value="other">Other</option>
            </Select>
            <div>
              <label className="label">Uploaded from</label>
              <input type="date" className="input" value={f.date_from} onChange={(e) => setFilter("date_from", e.target.value)} />
            </div>
            <div>
              <label className="label">Uploaded to</label>
              <input type="date" className="input" value={f.date_to} onChange={(e) => setFilter("date_to", e.target.value)} />
            </div>
            <Select label="Data source" value={f.is_demo} onChange={(e) => setFilter("is_demo", e.target.value)}>
              <option value="">All documents</option>
              <option value="false">Real documents only</option>
              <option value="true">Demo samples only</option>
            </Select>
            <div className="flex items-end">
              <Button variant="ghost" icon={<X className="h-4 w-4" />} onClick={() => { setParams({}); setQ(""); }}>
                Reset filters
              </Button>
            </div>
          </div>
        )}
      </Card>

      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="space-y-2 p-5">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-12" />)}</div>
        ) : !data?.items.length ? (
          <EmptyState icon={<FileText className="h-6 w-6" />} title="No documents found" description={activeFilters || f.q ? "Try adjusting your search or filters." : "Upload your first document to get started."} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[960px]">
              <thead>
                <tr>
                  {["Document", "Type", "Uploaded", "Status", "Invoice #", "Total", "Validation", "Actions"].map((h) => (
                    <th key={h} className={`table-head ${h === "Actions" ? "text-right" : ""}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.items.map((d: any) => {
                  const inv = d.invoices[0];
                  return (
                    <tr key={d.id} className="transition hover:bg-brand-50/40">
                      <td className="table-cell max-w-[280px]">
                        <Link to={`/documents/${d.id}`} className="group flex items-center gap-3">
                          <span className="rounded-lg bg-brand-50 p-2 text-brand-700"><FileText className="h-4 w-4" /></span>
                          <span className="min-w-0">
                            <span className="flex items-center gap-2">
                              <span className="truncate font-semibold group-hover:text-accent-600">{d.original_name}</span>
                              {d.is_demo && <DemoBadge />}
                            </span>
                            <span className="text-xs text-muted">{bytes(d.size_bytes)}{d.page_count ? ` · ${d.page_count} page${d.page_count > 1 ? "s" : ""}` : ""}{d.is_scanned ? " · scanned" : ""}</span>
                          </span>
                        </Link>
                      </td>
                      <td className="table-cell text-muted">{label(d.doc_type || d.file_kind)}</td>
                      <td className="table-cell whitespace-nowrap text-muted">{date(d.created_at)}</td>
                      <td className="table-cell"><StatusBadge status={d.status} /></td>
                      <td className="table-cell font-mono text-xs">{inv?.invoice_number || "—"}{d.invoices.length > 1 && <span className="ml-1 font-sans text-muted">+{d.invoices.length - 1} more</span>}</td>
                      <td className="table-cell whitespace-nowrap tabular-nums">{inv ? money(inv.total, inv.currency) : "—"}</td>
                      <td className="table-cell"><StatusBadge status={inv?.validation_status} /></td>
                      <td className="table-cell">
                        <div className="flex justify-end gap-1">
                          <button title="Inspect" onClick={() => nav(`/documents/${d.id}`)} className="rounded-lg p-2 text-muted hover:bg-brand-50 hover:text-accent-600"><Eye className="h-4 w-4" /></button>
                          <button title="Download original" onClick={() => download(`/documents/${d.id}/file`, d.original_name).catch((e) => toast("error", e.message))} className="rounded-lg p-2 text-muted hover:bg-brand-50 hover:text-accent-600"><Download className="h-4 w-4" /></button>
                          {can("reviewer") && (
                            <>
                              <button title="Reprocess" disabled={["queued", "processing"].includes(d.status)} onClick={() => reprocess.mutate(d.id)} className="rounded-lg p-2 text-muted hover:bg-brand-50 hover:text-accent-600 disabled:opacity-40"><RefreshCw className="h-4 w-4" /></button>
                              <button title="Delete" onClick={() => setToDelete(d)} className="rounded-lg p-2 text-muted hover:bg-bad-bg hover:text-bad"><Trash2 className="h-4 w-4" /></button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {data && <Pagination page={page} pageSize={PAGE} total={data.total} onPage={setPage} />}
      </Card>

      <ConfirmDialog
        open={!!toDelete}
        onClose={() => setToDelete(null)}
        onConfirm={() => del.mutate(toDelete.id)}
        loading={del.isPending}
        danger
        title="Delete document?"
        confirmText="Delete permanently"
        message={
          <>
            <p><span className="font-semibold">{toDelete?.original_name}</span> and its extracted invoices, validation results and stored file will be permanently deleted.</p>
            <p className="mt-2 text-muted">The deletion is recorded in the audit log. This cannot be undone.</p>
          </>
        }
      />
    </div>
  );
}
