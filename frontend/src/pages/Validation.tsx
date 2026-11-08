import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, Check, Eye, GitCompare, Search, ShieldCheck, Undo2, X, XCircle } from "lucide-react";
import { ReactNode, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { StackedBars } from "../components/charts";
import {
  Badge,
  Card,
  CardHeader,
  DemoBadge,
  EmptyState,
  PageHeader,
  Pagination,
  Select,
  Skeleton,
  StatusBadge,
  Tabs,
  useToast,
} from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { FIELD_LABELS, label } from "../lib/format";

function Stat({ icon, value, text, tone }: { icon: ReactNode; value: number | undefined; text: string; tone: string }) {
  return (
    <Card className="flex items-center gap-4 p-5">
      <div className={clsx("rounded-full p-3", tone)}>{icon}</div>
      <div>
        <div className="font-display text-[28px] font-extrabold leading-none tabular-nums text-brand-800">{value ?? "—"}</div>
        <div className="mt-1.5 text-[11px] font-bold uppercase tracking-[0.1em] text-muted">{text}</div>
      </div>
    </Card>
  );
}

const RULES = ["missing_field", "numeric_validation", "duplicate_invoice", "subtotal_verification", "tax_calculation", "line_item_total", "invoice_total", "low_confidence", "cross_document"];

function Issues() {
  const { can } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [severity, setSeverity] = useState("failed,review,warning");
  const [review, setReview] = useState("pending");
  const [rule, setRule] = useState("");
  const [q, setQ] = useState("");
  const [dq, setDq] = useState("");
  const [page, setPage] = useState(1);
  useEffect(() => {
    const t = setTimeout(() => setDq(q), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => setPage(1), [severity, review, rule, dq]);

  const { data, isLoading } = useQuery({
    queryKey: ["validation", "results", severity, review, rule, dq, page],
    queryFn: () => api("/validation/results", { query: { severity, review_status: review, rule, q: dq, page, page_size: 25 } }),
  });
  const act = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => api(`/validation/results/${id}`, { method: "PATCH", body: { review_status: status } }),
    onSuccess: (_r, v) => {
      toast("success", v.status === "approved" ? "Marked as approved" : v.status === "rejected" ? "Marked as rejected" : "Review reset");
      qc.invalidateQueries({ queryKey: ["validation"] });
    },
    onError: (e: Error) => toast("error", e.message),
  });

  return (
    <Card className="overflow-hidden">
      <div className="grid gap-3 border-b border-line p-4 md:grid-cols-2 xl:grid-cols-[2fr_1fr_1fr_1fr]">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <input className="input pl-10" placeholder="Invoice #, supplier or document…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <Select value={severity} onChange={(e) => setSeverity(e.target.value)}>
          <option value="failed,review,warning">All issues</option>
          <option value="failed">Failed</option>
          <option value="review">Requires manual review</option>
          <option value="warning">Warnings</option>
          <option value="passed">Passed checks</option>
        </Select>
        <Select value={review} onChange={(e) => setReview(e.target.value)}>
          <option value="">Any review status</option>
          <option value="pending">Pending review</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </Select>
        <Select value={rule} onChange={(e) => setRule(e.target.value)}>
          <option value="">All rules</option>
          {RULES.map((r) => <option key={r} value={r}>{label(r)}</option>)}
        </Select>
      </div>
      {isLoading ? (
        <div className="space-y-2 p-5">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-14" />)}</div>
      ) : !data?.items.length ? (
        <EmptyState icon={<ShieldCheck className="h-6 w-6" />} title="Nothing to review" description="No validation results match these filters." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1100px]">
            <thead>
              <tr>
                {["Severity", "Validation rule", "Expected", "Extracted", "Difference", "Source document", "Review", ""].map((h) => (
                  <th key={h} className="table-head">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.items.map((v: any) => (
                <tr key={v.id} className="align-top">
                  <td className="table-cell"><StatusBadge status={v.severity} /></td>
                  <td className="table-cell max-w-[300px]">
                    <div className="text-xs font-semibold uppercase tracking-wide text-muted">{label(v.rule)}{v.field ? ` · ${FIELD_LABELS[v.field] || label(v.field)}` : ""}</div>
                    <div className="mt-0.5 text-sm">{v.message}</div>
                    {v.related_document_id && (
                      <Link to={`/documents/${v.related_document_id}`} className="mt-1 inline-block text-xs font-semibold text-accent-600 hover:underline">
                        vs {v.related_document_name} →
                      </Link>
                    )}
                  </td>
                  <td className="table-cell font-mono text-xs">{v.expected ?? "—"}</td>
                  <td className="table-cell font-mono text-xs">{v.extracted ?? "—"}</td>
                  <td className={clsx("table-cell font-mono text-xs", v.difference && "font-semibold text-bad")}>{v.difference ?? "—"}</td>
                  <td className="table-cell max-w-[220px]">
                    <Link to={`/documents/${v.document_id}`} className="block truncate text-sm font-medium hover:text-accent-600">{v.document_name}</Link>
                    <div className="flex items-center gap-1.5 text-xs text-muted">
                      <span className="font-mono">{v.invoice_number || "no invoice #"}</span>
                      {v.is_demo && <DemoBadge />}
                    </div>
                  </td>
                  <td className="table-cell"><StatusBadge status={v.severity === "passed" ? "approved" : v.review_status} /></td>
                  <td className="table-cell">
                    {can("reviewer") && v.severity !== "passed" && (
                      <div className="flex justify-end gap-1">
                        {v.review_status === "pending" ? (
                          <>
                            <button title="Approve: accept as is" onClick={() => act.mutate({ id: v.id, status: "approved" })} className="rounded-lg border border-line p-1.5 text-ok hover:bg-ok-bg"><Check className="h-4 w-4" /></button>
                            <button title="Reject: needs correction" onClick={() => act.mutate({ id: v.id, status: "rejected" })} className="rounded-lg border border-line p-1.5 text-bad hover:bg-bad-bg"><X className="h-4 w-4" /></button>
                          </>
                        ) : (
                          <button title="Reset review" onClick={() => act.mutate({ id: v.id, status: "pending" })} className="rounded-lg p-1.5 text-muted hover:bg-cream"><Undo2 className="h-4 w-4" /></button>
                        )}
                        <Link to={`/documents/${v.document_id}`} title="Open & correct" className="rounded-lg border border-line p-1.5 text-brand-700 hover:bg-brand-50"><Eye className="h-4 w-4" /></Link>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && <Pagination page={page} pageSize={25} total={data.total} onPage={setPage} />}
    </Card>
  );
}

function CrossVerification() {
  const [type, setType] = useState("");
  const [onlyMismatch, setOnlyMismatch] = useState(true);
  const [page, setPage] = useState(1);
  const { data: summary } = useQuery({ queryKey: ["validation", "cross-summary"], queryFn: () => api("/verification/summary") });
  const { data, isLoading } = useQuery({
    queryKey: ["validation", "cross", type, onlyMismatch, page],
    queryFn: () => api("/verification", { query: { comparison_type: type, only_mismatches: onlyMismatch, page, page_size: 50 } }),
  });
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {(summary || []).length === 0 && <Card className="p-5 text-sm text-muted sm:col-span-2 lg:col-span-4">No related documents compared yet. Upload the same invoice in two formats (e.g. PDF + Excel) to see cross-verification.</Card>}
        {(summary || []).map((s: any) => (
          <Card key={s.comparison_type} className="cursor-pointer p-5 transition hover:shadow-lift" onClick={() => setType(type === s.comparison_type ? "" : s.comparison_type)}>
            <div className="flex items-center justify-between">
              <Badge tone={type === s.comparison_type ? "brand" : "gray"}>{s.comparison_type.split("_").map((x: string) => x.toUpperCase()).join(" ↔ ")}</Badge>
              <GitCompare className="h-4 w-4 text-muted" />
            </div>
            <div className="mt-3 flex items-baseline gap-3">
              <span className="font-display text-2xl font-extrabold text-ok">{s.matched}</span><span className="text-xs text-muted">matched fields</span>
            </div>
            <div className="flex items-baseline gap-3">
              <span className="font-display text-2xl font-extrabold text-bad">{s.mismatched}</span><span className="text-xs text-muted">mismatches</span>
            </div>
          </Card>
        ))}
      </div>
      <Card className="overflow-hidden">
        <CardHeader
          title="Field comparisons"
          subtitle={type ? `Filtered: ${type.replace("_", " ↔ ")}` : "PDF ↔ PDF, PDF ↔ Excel, Excel ↔ CSV and more"}
          action={
            <Select value={onlyMismatch ? "1" : "0"} onChange={(e) => setOnlyMismatch(e.target.value === "1")}>
              <option value="1">Mismatches only</option>
              <option value="0">All comparisons</option>
            </Select>
          }
        />
        {isLoading ? (
          <div className="p-5"><Skeleton className="h-40" /></div>
        ) : !data?.items.length ? (
          <EmptyState icon={<GitCompare className="h-6 w-6" />} title="No comparisons" description="Nothing matches these filters." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px]">
              <thead>
                <tr>{["Type", "Field", "Document", "Value", "Compared with", "Value", "Difference", "Result"].map((h, i) => <th key={i} className="table-head">{h}</th>)}</tr>
              </thead>
              <tbody>
                {data.items.map((c: any) => (
                  <tr key={c.id}>
                    <td className="table-cell"><Badge tone="gray">{c.comparison_type.replace("_", " ↔ ")}</Badge></td>
                    <td className="table-cell font-medium">{FIELD_LABELS[c.field] || label(c.field)}</td>
                    <td className="table-cell max-w-[180px] truncate"><Link className="hover:text-accent-600" to={`/documents/${c.source_document_id}`}>{c.source_document_name}</Link></td>
                    <td className="table-cell font-mono text-xs">{c.source_value ?? "—"}</td>
                    <td className="table-cell max-w-[180px] truncate"><Link className="hover:text-accent-600" to={`/documents/${c.target_document_id}`}>{c.target_document_name}</Link></td>
                    <td className="table-cell font-mono text-xs">{c.target_value ?? "—"}</td>
                    <td className={clsx("table-cell font-mono text-xs", !c.is_match && "text-bad")}>{c.difference ?? "—"}</td>
                    <td className="table-cell">{c.is_match ? <StatusBadge status="passed" /> : <StatusBadge status={c.severity} />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && <Pagination page={page} pageSize={50} total={data.total} onPage={setPage} />}
      </Card>
    </div>
  );
}

export default function Validation() {
  const [tab, setTab] = useState<"issues" | "cross">("issues");
  const { data: s } = useQuery({ queryKey: ["validation", "summary"], queryFn: () => api("/validation/summary") });
  return (
    <div className="animate-fade-in">
      <PageHeader title="Validation & Verification" subtitle="Financial checks, duplicates and cross-document discrepancies. Extracted values are never changed silently." />
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat icon={<XCircle className="h-5 w-5" />} tone="bg-bad-bg text-bad" value={s?.invoices_by_status.failed} text="Invoices failed" />
        <Stat icon={<Eye className="h-5 w-5" />} tone="bg-info-bg text-info" value={s?.invoices_by_status.review} text="Require manual review" />
        <Stat icon={<AlertTriangle className="h-5 w-5" />} tone="bg-warn-bg text-warn" value={s?.invoices_by_status.warning} text="With warnings" />
        <Stat icon={<ShieldCheck className="h-5 w-5" />} tone="bg-ok-bg text-ok" value={s?.invoices_by_status.passed} text="Passed all checks" />
      </div>
      {s?.by_rule?.length > 0 && (
        <Card className="mb-6">
          <CardHeader title="Issues by rule" subtitle={`${s.pending_reviews} issue(s) awaiting a review decision`} />
          <div className="p-4"><StackedBars data={s.by_rule} keys={["failed", "review", "warning"]} xKey="rule" horizontal height={Math.max(160, s.by_rule.length * 38)} /></div>
        </Card>
      )}
      <div className="mb-4">
        <Tabs value={tab} onChange={setTab} tabs={[{ key: "issues", label: "Validation results", count: s?.pending_reviews }, { key: "cross", label: "Cross-document verification" }]} />
      </div>
      {tab === "issues" ? <Issues /> : <CrossVerification />}
    </div>
  );
}
