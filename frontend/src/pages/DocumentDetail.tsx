import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  ArrowLeft,
  Check,
  ChevronLeft,
  ChevronRight,
  Download,
  FileJson,
  Minus,
  Plus,
  RefreshCw,
  Save,
  Trash2,
  Undo2,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Badge,
  Button,
  Card,
  ConfidenceBar,
  ConfirmDialog,
  DemoBadge,
  EmptyState,
  ErrorBox,
  Input,
  PageLoader,
  Spinner,
  StatusBadge,
  Tabs,
  useToast,
} from "../components/ui";
import { api, apiBlob, download } from "../lib/api";
import { useAuth } from "../lib/auth";
import { bytes, dateTime, FIELD_LABELS, label, money } from "../lib/format";

const HEADER_FIELDS = ["invoice_number", "invoice_date", "supplier_name", "customer_name", "currency", "subtotal", "tax_rate", "tax", "total"] as const;
const NUMERIC = new Set(["subtotal", "tax", "total", "tax_rate"]);

// ---------------------------------------------------------------- viewer
function PageImage({ docId, page, boxes, active, onBoxClick, zoom }: { docId: string; page: number; boxes: { field: string; bbox: number[] }[]; active: string | null; onBoxClick: (f: string) => void; zoom: number }) {
  const { data: url, isLoading, error } = useQuery({
    queryKey: ["page-image", docId, page],
    queryFn: async () => URL.createObjectURL(await apiBlob(`/documents/${docId}/pages/${page}/image`)),
    staleTime: Infinity,
  });
  if (isLoading) return <div className="flex h-96 items-center justify-center"><Spinner /></div>;
  if (error) return <div className="p-6"><ErrorBox error={error} /></div>;
  return (
    <div className="relative mx-auto origin-top transition-transform" style={{ width: `${zoom * 100}%` }}>
      <img src={url} alt={`Page ${page}`} className="block w-full rounded-lg shadow-soft" draggable={false} />
      {boxes.map((b) => (
        <button
          key={b.field}
          onClick={() => onBoxClick(b.field)}
          title={FIELD_LABELS[b.field] || label(b.field)}
          className={clsx(
            "absolute rounded-[3px] border-2 transition-all",
            active === b.field ? "border-accent-500 bg-accent-400/25 ring-4 ring-accent-300/40" : "border-brand-500/60 bg-brand-200/20 hover:bg-accent-200/30",
          )}
          style={{
            left: `${b.bbox[0] * 100 - 0.4}%`,
            top: `${b.bbox[1] * 100 - 0.3}%`,
            width: `${(b.bbox[2] - b.bbox[0]) * 100 + 0.8}%`,
            height: `${(b.bbox[3] - b.bbox[1]) * 100 + 0.6}%`,
          }}
        />
      ))}
    </div>
  );
}

function Viewer({ doc, invoice, activeField, setActiveField }: { doc: any; invoice: any; activeField: string | null; setActiveField: (f: string | null) => void }) {
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const pages = doc.page_count || doc.page_texts.length || 1;
  const sources = invoice?.field_sources || {};
  useEffect(() => {
    if (activeField && sources[activeField]?.page) setPage(sources[activeField].page);
  }, [activeField]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!["pdf", "image"].includes(doc.file_kind)) {
    return (
      <div className="h-full overflow-auto p-4 scrollbar-thin">
        {doc.page_texts.length === 0 && <p className="p-6 text-sm text-muted">No content extracted yet.</p>}
        {doc.page_texts.map((p: any) => (
          <div key={p.page_no} className="mb-4">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Sheet {p.page_no}</div>
            <table className="w-full border-collapse text-xs">
              <tbody>
                {p.text.split("\n").slice(1, 200).map((row: string, i: number) => (
                  <tr key={i} className={clsx(invoice?.source_ref?.row === i + 1 && "bg-brand-100")}>
                    <td className="w-8 border border-line bg-cream px-2 py-1 text-right text-muted">{i + 1}</td>
                    {row.split(" | ").map((c, j) => (
                      <td key={j} className="border border-line bg-white px-2 py-1">{c}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    );
  }

  const boxes = Object.entries(sources)
    .filter(([, s]: any) => s?.page === page && Array.isArray(s.bbox))
    .map(([field, s]: any) => ({ field, bbox: s.bbox }));

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-line bg-white px-3 py-2">
        <div className="flex items-center gap-1">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="rounded-lg p-1.5 hover:bg-cream disabled:opacity-40" aria-label="Previous page"><ChevronLeft className="h-4 w-4" /></button>
          <span className="text-xs font-medium tabular-nums text-ink-soft">Page {page} / {pages}</span>
          <button disabled={page >= pages} onClick={() => setPage(page + 1)} className="rounded-lg p-1.5 hover:bg-cream disabled:opacity-40" aria-label="Next page"><ChevronRight className="h-4 w-4" /></button>
        </div>
        <span className="hidden text-xs text-muted sm:block">Click a highlighted region or a field to locate it</span>
        <div className="flex items-center gap-1">
          <button onClick={() => setZoom(Math.max(0.6, zoom - 0.2))} className="rounded-lg p-1.5 hover:bg-cream" aria-label="Zoom out"><ZoomOut className="h-4 w-4" /></button>
          <span className="w-10 text-center text-xs tabular-nums text-muted">{Math.round(zoom * 100)}%</span>
          <button onClick={() => setZoom(Math.min(2.4, zoom + 0.2))} className="rounded-lg p-1.5 hover:bg-cream" aria-label="Zoom in"><ZoomIn className="h-4 w-4" /></button>
        </div>
      </div>
      <div className="flex-1 overflow-auto bg-cream-dark/60 p-4 scrollbar-thin">
        <PageImage docId={doc.id} page={page} boxes={boxes} active={activeField} onBoxClick={(f) => setActiveField(f)} zoom={zoom} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- extracted data editor
function toStr(v: any) {
  return v === null || v === undefined ? "" : String(v);
}

function ExtractedPanel({ invoice, activeField, setActiveField, canEdit }: { invoice: any; activeField: string | null; setActiveField: (f: string | null) => void; canEdit: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const initial = useMemo(() => {
    const h: Record<string, string> = {};
    HEADER_FIELDS.forEach((f) => (h[f] = toStr(invoice[f])));
    return h;
  }, [invoice]);
  const initialLines = useMemo(
    () => invoice.line_items.map((li: any) => ({ id: li.id, description: toStr(li.description), quantity: toStr(li.quantity), unit_price: toStr(li.unit_price), tax: toStr(li.tax), line_total: toStr(li.line_total), confidence: li.confidence, delete: false })),
    [invoice],
  );
  const [draft, setDraft] = useState(initial);
  const [lines, setLines] = useState<any[]>(initialLines);
  const [reason, setReason] = useState("");
  useEffect(() => {
    setDraft(initial);
    setLines(initialLines);
  }, [initial, initialLines]);

  const changed = HEADER_FIELDS.filter((f) => draft[f] !== initial[f]);
  const lineChanges = lines.filter((l) => {
    if (!l.id) return !l.delete && (l.description || l.line_total);
    if (l.delete) return true;
    const o = initialLines.find((x: any) => x.id === l.id);
    return ["description", "quantity", "unit_price", "tax", "line_total"].some((k) => l[k] !== o[k]);
  });
  const dirty = changed.length > 0 || lineChanges.length > 0;

  const save = useMutation({
    mutationFn: () => {
      const body: any = { reason: reason || null, clear_fields: [] as string[] };
      changed.forEach((f) => {
        if (draft[f] === "") body.clear_fields.push(f);
        else body[f] = NUMERIC.has(f) ? draft[f].replace(/,/g, "") : draft[f];
      });
      if (lineChanges.length) {
        body.line_items = lineChanges.map((l) => ({
          id: l.id || null,
          delete: l.delete,
          description: l.description || null,
          quantity: l.quantity === "" ? null : l.quantity.replace(/,/g, ""),
          unit_price: l.unit_price === "" ? null : l.unit_price.replace(/,/g, ""),
          tax: l.tax === "" ? null : l.tax.replace(/,/g, ""),
          line_total: l.line_total === "" ? null : l.line_total.replace(/,/g, ""),
        }));
      }
      return api(`/invoices/${invoice.id}`, { method: "PATCH", body });
    },
    onSuccess: () => {
      toast("success", "Corrections saved and invoice re-validated");
      setReason("");
      qc.invalidateQueries({ queryKey: ["document"] });
      qc.invalidateQueries({ queryKey: ["validation"] });
    },
    onError: (e: any) => toast("error", e.errors?.map((x: any) => `${x.field}: ${x.message}`).join("; ") || e.message),
  });

  const conf = invoice.confidence || {};
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={invoice.validation_status} />
        <Badge tone={invoice.engine.startsWith("builtin") ? "brand" : "blue"}>
          Engine: {invoice.engine.startsWith("builtin") ? `Built-in${invoice.engine.includes("fallback") ? " (fallback)" : ""}` : invoice.engine}
        </Badge>
        {invoice.source_ref && <Badge tone="gray">{invoice.source_ref.sheet}{invoice.source_ref.row ? ` · row ${invoice.source_ref.row}` : ""}</Badge>}
        {invoice.corrections.length > 0 && <Badge tone="amber">{invoice.corrections.length} manual correction(s)</Badge>}
      </div>

      <div className="grid gap-x-4 gap-y-3 sm:grid-cols-2">
        {HEADER_FIELDS.map((f) => {
          const c = conf[f];
          const low = invoice[f] !== null && c !== undefined && c < 0.75;
          const missing = invoice[f] === null && f !== "tax_rate";
          return (
            <div
              key={f}
              onMouseEnter={() => setActiveField(f)}
              className={clsx("rounded-xl border p-3 transition", activeField === f ? "border-brand-400 bg-brand-50/60" : "border-transparent", low && "bg-warn-bg/40", missing && "bg-bad-bg/30")}
            >
              <div className="mb-1 flex items-center justify-between gap-2">
                <label className="text-xs font-semibold uppercase tracking-wide text-muted">{FIELD_LABELS[f]}</label>
                {f !== "tax_rate" && <ConfidenceBar value={c ?? (invoice[f] === null ? 0 : null)} />}
              </div>
              <input
                className={clsx("input !py-2", draft[f] !== initial[f] && "border-warn bg-warn-bg/30")}
                type={f === "invoice_date" ? "date" : "text"}
                inputMode={NUMERIC.has(f) ? "decimal" : undefined}
                value={draft[f]}
                disabled={!canEdit}
                placeholder={missing ? "Not found in document" : ""}
                onFocus={() => setActiveField(f)}
                onChange={(e) => setDraft({ ...draft, [f]: e.target.value })}
              />
              {missing && <p className="mt-1 text-[11px] text-bad">Not found. Left empty rather than guessed.</p>}
              {low && <p className="mt-1 text-[11px] text-warn">Low confidence. Please verify.</p>}
            </div>
          );
        })}
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h4 className="font-sans text-sm font-semibold">Line items ({lines.filter((l) => !l.delete).length})</h4>
          {canEdit && (
            <Button size="sm" variant="ghost" icon={<Plus className="h-3.5 w-3.5" />} onClick={() => setLines([...lines, { id: null, description: "", quantity: "", unit_price: "", tax: "", line_total: "", delete: false }])}>
              Add line
            </Button>
          )}
        </div>
        <div className="overflow-x-auto rounded-xl border border-line">
          <table className="w-full min-w-[620px] text-sm">
            <thead>
              <tr>
                {["Description", "Qty", "Unit price", "Tax", "Line total", ""].map((h) => (
                  <th key={h} className="table-head !py-2">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {lines.length === 0 && (
                <tr><td colSpan={6} className="table-cell text-center text-muted">No line items detected</td></tr>
              )}
              {lines.map((l, i) => (
                <tr key={l.id || `new-${i}`} className={clsx(l.delete && "opacity-40 line-through")}>
                  {(["description", "quantity", "unit_price", "tax", "line_total"] as const).map((k) => (
                    <td key={k} className="border-t border-line p-1.5">
                      <input
                        className={clsx("w-full rounded-lg border border-transparent bg-transparent px-2 py-1.5 text-sm hover:border-line focus:border-brand-400 focus:bg-white focus:outline-none", k !== "description" && "text-right tabular-nums")}
                        value={l[k]}
                        disabled={!canEdit || l.delete}
                        onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, [k]: e.target.value } : x)))}
                      />
                    </td>
                  ))}
                  <td className="w-20 border-t border-line px-2">
                    <div className="flex items-center justify-end gap-1">
                      {l.confidence !== undefined && l.confidence !== null && !l.delete && (
                        <span className={clsx("h-2 w-2 rounded-full", l.confidence >= 0.9 ? "bg-ok" : l.confidence >= 0.75 ? "bg-brand-400" : "bg-warn")} title={`Confidence ${Math.round(l.confidence * 100)}%`} />
                      )}
                      {canEdit && (
                        <button onClick={() => (l.id ? setLines(lines.map((x, j) => (j === i ? { ...x, delete: !x.delete } : x))) : setLines(lines.filter((_, j) => j !== i)))} className="rounded p-1 text-muted hover:text-bad" aria-label="Remove line">
                          {l.delete ? <Undo2 className="h-3.5 w-3.5" /> : <Minus className="h-3.5 w-3.5" />}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {canEdit && dirty && (
        <div className="sticky bottom-0 -mx-5 animate-fade-in border-t border-line bg-white/95 px-5 py-4 backdrop-blur sm:-mx-6 sm:px-6">
          <div className="mb-3 text-xs text-muted">
            {changed.length + lineChanges.length} change(s). Original extracted values are kept in the audit history; validation re-runs on save.
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <input className="input flex-1" placeholder="Reason for correction (optional)" value={reason} onChange={(e) => setReason(e.target.value)} />
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => { setDraft(initial); setLines(initialLines); }} icon={<X className="h-4 w-4" />}>Discard</Button>
              <Button onClick={() => save.mutate()} loading={save.isPending} icon={<Save className="h-4 w-4" />}>Save corrections</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- validation list
export function ValidationList({ items, canReview, docNameFor }: { items: any[]; canReview: boolean; docNameFor?: (id: string) => string | undefined }) {
  const qc = useQueryClient();
  const toast = useToast();
  const review = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => api(`/validation/results/${id}`, { method: "PATCH", body: { review_status: status } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["document"] });
      qc.invalidateQueries({ queryKey: ["validation"] });
    },
    onError: (e: Error) => toast("error", e.message),
  });
  if (!items.length) return <p className="text-sm text-muted">No validation results.</p>;
  return (
    <ul className="space-y-2">
      {items.map((v) => (
        <li key={v.id} className={clsx("rounded-xl border p-3.5", v.severity === "failed" ? "border-bad/20 bg-bad-bg/30" : v.severity === "review" ? "border-info/20 bg-info-bg/40" : v.severity === "warning" ? "border-warn/20 bg-warn-bg/40" : "border-line bg-white")}>
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge status={v.severity} />
                <span className="text-xs font-semibold uppercase tracking-wide text-muted">{label(v.rule)}</span>
              </div>
              <p className="mt-1.5 text-sm text-ink">{v.message}</p>
              {(v.expected || v.extracted || v.difference) && (
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
                  {v.expected && <span className="text-muted">Expected <span className="font-mono font-semibold text-ink">{v.expected}</span></span>}
                  {v.extracted !== null && v.extracted !== undefined && <span className="text-muted">Extracted <span className="font-mono font-semibold text-ink">{v.extracted || "—"}</span></span>}
                  {v.difference && <span className="text-muted">Difference <span className="font-mono font-semibold text-bad">{v.difference}</span></span>}
                </div>
              )}
              {v.related_document_id && (
                <Link to={`/documents/${v.related_document_id}`} className="mt-1.5 inline-block text-xs font-semibold text-accent-600 hover:underline">
                  Source: {docNameFor?.(v.related_document_id) || v.related_document_name || "related document"} →
                </Link>
              )}
            </div>
            {v.severity !== "passed" && (
              <div className="flex shrink-0 items-center gap-1.5">
                <StatusBadge status={v.review_status} />
                {canReview && v.review_status === "pending" && (
                  <>
                    <button title="Approve (accept as is)" onClick={() => review.mutate({ id: v.id, status: "approved" })} className="rounded-lg border border-line bg-white p-1.5 text-ok hover:bg-ok-bg"><Check className="h-3.5 w-3.5" /></button>
                    <button title="Reject (needs correction)" onClick={() => review.mutate({ id: v.id, status: "rejected" })} className="rounded-lg border border-line bg-white p-1.5 text-bad hover:bg-bad-bg"><X className="h-3.5 w-3.5" /></button>
                  </>
                )}
                {canReview && v.review_status !== "pending" && (
                  <button title="Reset review" onClick={() => review.mutate({ id: v.id, status: "pending" })} className="rounded-lg p-1.5 text-muted hover:bg-cream"><Undo2 className="h-3.5 w-3.5" /></button>
                )}
              </div>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------- page
type Tab = "data" | "validation" | "cross" | "history" | "text";

export default function DocumentDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const { can } = useAuth();
  const [tab, setTab] = useState<Tab>("data");
  const [invIdx, setInvIdx] = useState(0);
  const [activeField, setActiveField] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const { data: doc, isLoading, error } = useQuery({
    queryKey: ["document", id],
    queryFn: () => api(`/documents/${id}`),
    refetchInterval: (q) => (["queued", "processing", "uploaded"].includes((q.state.data as any)?.status) ? 3000 : false),
  });
  const reprocess = useMutation({
    mutationFn: () => api(`/documents/${id}/reprocess`, { method: "POST" }),
    onSuccess: () => {
      toast("success", "Re-queued for processing");
      qc.invalidateQueries({ queryKey: ["document", id] });
    },
    onError: (e: Error) => toast("error", e.message),
  });
  const del = useMutation({
    mutationFn: () => api(`/documents/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast("success", "Document deleted");
      qc.invalidateQueries();
      nav("/documents");
    },
    onError: (e: Error) => toast("error", e.message),
  });

  if (isLoading) return <PageLoader />;
  if (error || !doc) return <ErrorBox error={error || "Not found"} />;

  const invoices = doc.invoices_detail || [];
  const invoice = invoices[Math.min(invIdx, invoices.length - 1)];
  const processing = ["queued", "processing", "uploaded"].includes(doc.status);
  const issues = invoice ? invoice.validations.filter((v: any) => v.severity !== "passed").length : 0;
  const crossFor = doc.cross_verification || [];
  const crossGroups = crossFor.reduce((acc: Record<string, any[]>, c: any) => {
    (acc[c.target_document_id] ||= []).push(c);
    return acc;
  }, {});

  return (
    <div className="animate-fade-in">
      <div className="mb-5 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <Link to="/documents" className="mb-2 inline-flex items-center gap-1 text-sm font-medium text-muted hover:text-accent-600">
            <ArrowLeft className="h-4 w-4" /> Document library
          </Link>
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="truncate text-xl font-semibold sm:text-2xl">{doc.original_name}</h1>
            <StatusBadge status={doc.status} />
            {doc.is_demo && <DemoBadge />}
          </div>
          <p className="mt-1 text-sm text-muted">
            {label(doc.doc_type || doc.file_kind)} · {bytes(doc.size_bytes)} · {doc.page_count ?? "?"} page(s){doc.is_scanned ? " · scanned (OCR)" : ""} · uploaded {dateTime(doc.created_at)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" icon={<Download className="h-4 w-4" />} onClick={() => download(`/documents/${doc.id}/file`, doc.original_name).catch((e) => toast("error", e.message))}>Original</Button>
          <Button variant="secondary" size="sm" icon={<FileJson className="h-4 w-4" />} disabled={!invoices.length} onClick={() => download(`/documents/${doc.id}/json`, doc.original_name.replace(/\.[^.]+$/, "") + ".json").catch((e) => toast("error", e.message))}>JSON</Button>
          {can("reviewer") && (
            <>
              <Button variant="secondary" size="sm" icon={<RefreshCw className="h-4 w-4" />} disabled={processing} loading={reprocess.isPending} onClick={() => reprocess.mutate()}>Reprocess</Button>
              <Button variant="ghost" size="sm" className="text-bad hover:bg-bad-bg hover:text-bad" icon={<Trash2 className="h-4 w-4" />} disabled={processing} onClick={() => setConfirmDelete(true)}>Delete</Button>
            </>
          )}
        </div>
      </div>

      {doc.status === "failed" && doc.error && <div className="mb-4"><ErrorBox error={`Processing failed: ${doc.error}`} /></div>}
      {processing && (
        <Card className="mb-4 flex items-center gap-3 p-4 text-sm">
          <Spinner /> Processing in progress. This page updates automatically.
        </Card>
      )}

      <div className="grid gap-5 xl:grid-cols-2">
        <Card className="h-[55vh] overflow-hidden xl:sticky xl:top-20 xl:h-[calc(100vh-11rem)]">
          <Viewer doc={doc} invoice={invoice} activeField={activeField} setActiveField={setActiveField} />
        </Card>

        <Card className="min-w-0">
          <div className="border-b border-line px-5 py-4 sm:px-6">
            {invoices.length > 1 && (
              <div className="mb-3 flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted">Invoice</span>
                <select className="input !w-auto !py-1.5" value={invIdx} onChange={(e) => setInvIdx(Number(e.target.value))}>
                  {invoices.map((inv: any, i: number) => (
                    <option key={inv.id} value={i}>
                      {inv.invoice_number || `Row ${inv.source_ref?.row ?? i + 1}`} · {money(inv.total, inv.currency)}
                    </option>
                  ))}
                </select>
                <span className="text-xs text-muted">{invoices.length} invoices in this file</span>
              </div>
            )}
            <Tabs<Tab>
              value={tab}
              onChange={setTab}
              tabs={[
                { key: "data", label: "Extracted data" },
                { key: "validation", label: "Validation", count: issues },
                { key: "cross", label: "Cross-verification", count: Object.keys(crossGroups).length },
                { key: "history", label: "History" },
                { key: "text", label: "Text" },
              ]}
            />
          </div>
          <div className="px-5 py-5 sm:px-6">
            {!invoice && tab !== "history" && tab !== "text" ? (
              <EmptyState icon={<FileJson className="h-6 w-6" />} title={processing ? "Extraction in progress" : "No invoice data"} description={doc.status === "failed" ? "Processing failed. Fix the issue and reprocess." : processing ? "Results will appear when processing finishes." : "No invoice information was found in this document."} />
            ) : tab === "data" ? (
              <ExtractedPanel invoice={invoice} activeField={activeField} setActiveField={setActiveField} canEdit={can("reviewer")} />
            ) : tab === "validation" ? (
              <ValidationList items={invoice.validations} canReview={can("reviewer")} />
            ) : tab === "cross" ? (
              Object.keys(crossGroups).length === 0 ? (
                <p className="text-sm text-muted">No related documents found (matched by invoice number, or by supplier + total + date).</p>
              ) : (
                <div className="space-y-5">
                  {Object.entries(crossGroups).map(([target, rows]: any) => (
                    <div key={target} className="overflow-hidden rounded-xl border border-line">
                      <div className="flex flex-wrap items-center justify-between gap-2 bg-cream/70 px-4 py-2.5">
                        <Link to={`/documents/${target}`} className="text-sm font-semibold hover:text-accent-600">{rows[0].target_document_name}</Link>
                        <div className="flex gap-2">
                          <Badge tone="brand">{label(rows[0].comparison_type).replace(/ /g, " ↔ ")}</Badge>
                          <Badge tone="gray">matched by {label(rows[0].match_basis)}</Badge>
                        </div>
                      </div>
                      <table className="w-full text-sm">
                        <thead>
                          <tr>{["Field", "This document", "Other document", "Difference", ""].map((h) => <th key={h} className="table-head !py-2">{h}</th>)}</tr>
                        </thead>
                        <tbody>
                          {rows.map((c: any) => (
                            <tr key={c.id}>
                              <td className="table-cell !py-2 font-medium">{FIELD_LABELS[c.field] || label(c.field)}</td>
                              <td className="table-cell !py-2 font-mono text-xs">{c.source_value ?? "—"}</td>
                              <td className="table-cell !py-2 font-mono text-xs">{c.target_value ?? "—"}</td>
                              <td className={clsx("table-cell !py-2 font-mono text-xs", !c.is_match && "text-bad")}>{c.difference ?? "—"}</td>
                              <td className="table-cell !py-2 text-right">{c.is_match ? <StatusBadge status="passed" /> : <StatusBadge status={c.severity} />}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ))}
                </div>
              )
            ) : tab === "history" ? (
              <div className="space-y-6">
                {doc.jobs.map((j: any) => (
                  <div key={j.id}>
                    <div className="mb-2 flex items-center gap-2 text-sm">
                      <StatusBadge status={j.status} />
                      <span className="text-muted">Job started {dateTime(j.created_at)} · attempt {j.attempts}</span>
                    </div>
                    <ol className="relative ml-2 space-y-3 border-l-2 border-line pl-5">
                      {j.history.map((h: any) => (
                        <li key={h.id} className="relative">
                          <span className={clsx("absolute -left-[27px] top-1 h-3 w-3 rounded-full border-2 border-white", h.status === "failed" ? "bg-bad" : "bg-brand-600")} />
                          <div className="text-sm font-medium">{label(h.stage)} <span className="font-normal text-muted">· {h.status}{h.duration_ms !== null ? ` · ${h.duration_ms} ms` : ""}</span></div>
                          {h.message && <div className="text-xs text-ink-soft">{h.message}</div>}
                        </li>
                      ))}
                    </ol>
                  </div>
                ))}
                {invoice?.corrections?.length > 0 && (
                  <div>
                    <h4 className="mb-2 font-sans text-sm font-semibold">Manual corrections</h4>
                    <ul className="space-y-2">
                      {invoice.corrections.map((c: any) => (
                        <li key={c.id} className="rounded-xl border border-line p-3 text-sm">
                          <div className="font-medium">{FIELD_LABELS[c.field_path] || c.field_path}</div>
                          <div className="mt-1 font-mono text-xs"><span className="text-bad line-through">{c.old_value ?? "∅"}</span> → <span className="text-ok">{c.new_value ?? "∅"}</span></div>
                          <div className="mt-1 text-xs text-muted">{dateTime(c.created_at)}{c.reason ? ` · ${c.reason}` : ""}</div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-4">
                {doc.page_texts.map((p: any) => (
                  <div key={p.page_no}>
                    <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">
                      Page {p.page_no} · {p.method}{p.ocr_confidence !== null ? ` · OCR confidence ${Math.round(p.ocr_confidence * 100)}%` : ""}
                    </div>
                    <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-xl bg-cream p-4 font-mono text-xs leading-relaxed text-ink-soft scrollbar-thin">{p.text || "(empty)"}</pre>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Card>
      </div>

      <ConfirmDialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        onConfirm={() => del.mutate()}
        loading={del.isPending}
        danger
        title="Delete document?"
        confirmText="Delete permanently"
        message={<p><span className="font-semibold">{doc.original_name}</span> and all extracted data will be permanently deleted. This is recorded in the audit log.</p>}
      />
    </div>
  );
}
