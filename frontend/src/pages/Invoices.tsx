import { useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Download, Receipt, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Badge,
  Button,
  Card,
  ConfidenceBar,
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
import { date, money } from "../lib/format";

const PAGE = 20;
const KEYS = ["invoice_number", "invoice_date", "supplier_name", "customer_name", "subtotal", "tax", "total", "currency"];

export default function Invoices() {
  const nav = useNavigate();
  const toast = useToast();
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [status, setStatus] = useState("");
  const [currency, setCurrency] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [minTotal, setMinTotal] = useState("");
  const [maxTotal, setMaxTotal] = useState("");
  const [demo, setDemo] = useState("");
  const [sort, setSort] = useState("-created_at");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => setPage(1), [debounced, status, currency, dateFrom, dateTo, minTotal, maxTotal, demo, sort]);

  const query = { q: debounced, status, currency, date_from: dateFrom, date_to: dateTo, min_total: minTotal, max_total: maxTotal, is_demo: demo };
  const { data, isLoading } = useQuery({
    queryKey: ["invoices", query, sort, page],
    queryFn: () => api("/invoices", { query: { ...query, sort, page, page_size: PAGE } }),
  });

  const sortBy = (k: string) => setSort(sort === `-${k}` ? k : `-${k}`);
  const SortHead = ({ k, children, right }: { k: string; children: string; right?: boolean }) => (
    <th className={`table-head cursor-pointer select-none hover:text-ink ${right ? "text-right" : ""}`} onClick={() => sortBy(k)}>
      <span className="inline-flex items-center gap-1">
        {children}
        {sort === `-${k}` ? <ArrowDown className="h-3 w-3" /> : sort === k ? <ArrowUp className="h-3 w-3" /> : null}
      </span>
    </th>
  );

  return (
    <div className="animate-fade-in">
      <PageHeader
        title="Extracted Invoices"
        subtitle="Structured invoice data extracted from all documents."
        actions={
          <Button variant="secondary" icon={<Download className="h-4 w-4" />} onClick={() => download("/invoices/export", "invoices.csv", query).catch((e) => toast("error", e.message))}>
            Export CSV
          </Button>
        }
      />
      <Card className="mb-4 p-4">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-[2fr_1fr_1fr_1fr_1fr]">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <input className="input pl-10" placeholder="Invoice #, supplier, customer, file…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <Select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All validation states</option>
            <option value="passed">Passed</option>
            <option value="warning">Warning</option>
            <option value="review">Manual review</option>
            <option value="failed">Failed</option>
          </Select>
          <Select value={currency} onChange={(e) => setCurrency(e.target.value)}>
            <option value="">All currencies</option>
            {["USD", "EUR", "GBP", "CAD", "AUD", "INR"].map((c) => <option key={c}>{c}</option>)}
          </Select>
          <input className="input" type="number" min="0" placeholder="Min total" value={minTotal} onChange={(e) => setMinTotal(e.target.value)} />
          <input className="input" type="number" min="0" placeholder="Max total" value={maxTotal} onChange={(e) => setMaxTotal(e.target.value)} />
          <div className="flex items-center gap-2 md:col-span-2 xl:col-span-2">
            <input className="input" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} aria-label="Invoice date from" />
            <span className="text-muted">–</span>
            <input className="input" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} aria-label="Invoice date to" />
          </div>
          <Select value={demo} onChange={(e) => setDemo(e.target.value)}>
            <option value="">Real + demo</option>
            <option value="false">Real only</option>
            <option value="true">Demo only</option>
          </Select>
        </div>
      </Card>

      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="space-y-2 p-5">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-11" />)}</div>
        ) : !data?.items.length ? (
          <EmptyState icon={<Receipt className="h-6 w-6" />} title="No invoices found" description="Extracted invoices appear here after documents are processed." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1080px]">
              <thead>
                <tr>
                  <SortHead k="invoice_number">Invoice #</SortHead>
                  <SortHead k="invoice_date">Date</SortHead>
                  <SortHead k="supplier_name">Supplier</SortHead>
                  <th className="table-head">Customer</th>
                  <th className="table-head text-right">Subtotal</th>
                  <th className="table-head text-right">Tax</th>
                  <SortHead k="total" right>Total</SortHead>
                  <th className="table-head">Confidence</th>
                  <th className="table-head">Validation</th>
                  <th className="table-head">Source</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((inv: any) => {
                  const confs = KEYS.map((k) => inv.confidence?.[k]).filter((c) => c !== undefined && c !== null);
                  const minConf = confs.length ? Math.min(...confs) : null;
                  return (
                    <tr key={inv.id} onClick={() => nav(`/documents/${inv.document_id}`)} className="cursor-pointer transition hover:bg-brand-50/40">
                      <td className="table-cell font-mono text-xs font-semibold">{inv.invoice_number || <span className="font-sans text-bad">missing</span>}</td>
                      <td className="table-cell whitespace-nowrap">{date(inv.invoice_date)}</td>
                      <td className="table-cell max-w-[200px] truncate">{inv.supplier_name || "—"}</td>
                      <td className="table-cell max-w-[180px] truncate text-ink-soft">{inv.customer_name || "—"}</td>
                      <td className="table-cell text-right tabular-nums text-ink-soft">{money(inv.subtotal, inv.currency)}</td>
                      <td className="table-cell text-right tabular-nums text-ink-soft">{money(inv.tax, inv.currency)}</td>
                      <td className="table-cell text-right font-semibold tabular-nums">{money(inv.total, inv.currency)}</td>
                      <td className="table-cell"><ConfidenceBar value={minConf} /></td>
                      <td className="table-cell"><StatusBadge status={inv.validation_status} /></td>
                      <td className="table-cell max-w-[180px]">
                        <div className="flex items-center gap-1.5">
                          <span className="truncate text-xs text-muted">{inv.document_name}</span>
                          {inv.is_demo && <DemoBadge />}
                          {!inv.engine.startsWith("builtin") && <Badge tone="blue">LLM</Badge>}
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
      <p className="mt-3 text-xs text-muted">Confidence shows the lowest field confidence for each invoice. Click a row to open the split-view inspector.</p>
    </div>
  );
}
