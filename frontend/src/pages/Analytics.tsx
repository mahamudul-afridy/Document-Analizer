import { useQuery } from "@tanstack/react-query";
import { Download, Printer } from "lucide-react";
import { useState } from "react";
import { ActivityChart, DonutChart, Legendary, StackedBars } from "../components/charts";
import { Button, Card, CardHeader, PageHeader, Select, Skeleton, Toggle } from "../components/ui";
import { api } from "../lib/api";
import { compact, label, money, pct } from "../lib/format";

function csvEscape(v: unknown) {
  const s = v === null || v === undefined ? "" : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export default function Analytics() {
  const [days, setDays] = useState(30);
  const [includeDemo, setIncludeDemo] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["analytics", "overview", days, includeDemo],
    queryFn: () => api("/analytics/overview", { query: { days, include_demo: includeDemo } }),
  });

  const downloadReport = () => {
    if (!data) return;
    const rows: unknown[][] = [
      ["DocuMind AI report", new Date().toISOString()],
      ["Period (days)", days],
      ["Includes demo data", includeDemo ? "yes" : "no"],
      [],
      ["KPI", "Value"],
      ...Object.entries(data.kpis).map(([k, v]) => [label(k), v]),
      [],
      ["Currency", "Invoices", "Total", "Tax", "Average"],
      ...data.financial.map((f: any) => [f.currency, f.count, f.total, f.tax, f.average]),
      [],
      ["Top supplier", "Invoices", "Total"],
      ...data.top_suppliers.map((s: any) => [s.supplier, s.count, s.total]),
      [],
      ["Validation rule", "Failed", "Review", "Warning"],
      ...data.validation.map((v: any) => [v.rule, v.failed, v.review, v.warning]),
      [],
      ["Date", "Uploaded", "Processed", "Failed"],
      ...data.activity.map((a: any) => [a.date, a.uploaded, a.processed, a.failed]),
    ];
    const blob = new Blob([rows.map((r) => r.map(csvEscape).join(",")).join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `documind-report-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const monthly = (() => {
    const map: Record<string, any> = {};
    (data?.monthly_totals || []).forEach((m: any) => {
      map[m.month] ||= { month: m.month };
      map[m.month][m.currency] = Math.round(m.total * 100) / 100;
    });
    return Object.values(map);
  })();
  const currencies = Array.from(new Set((data?.monthly_totals || []).map((m: any) => m.currency))) as string[];
  const invStatus = data ? Object.entries(data.invoice_validation_status).map(([name, value]) => ({ name, value: value as number })) : [];
  const k = data?.kpis;

  return (
    <div className="animate-fade-in">
      <PageHeader
        title="Analytics & Reports"
        subtitle="Processing performance and financial insight from extracted data."
        actions={
          <>
            <Button variant="secondary" icon={<Printer className="h-4 w-4" />} onClick={() => window.print()}>Print</Button>
            <Button icon={<Download className="h-4 w-4" />} onClick={downloadReport} disabled={!data}>Download report</Button>
          </>
        }
      />
      <Card className="mb-6 flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between">
        <Select value={days} onChange={(e) => setDays(Number(e.target.value))} className="sm:w-56">
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
          <option value={365}>Last 12 months</option>
        </Select>
        <div className="sm:w-72">
          <Toggle checked={includeDemo} onChange={setIncludeDemo} label="Include demo data" description="Off = real processed documents only" />
        </div>
      </Card>

      {isLoading || !k ? (
        <Skeleton className="h-96" />
      ) : (
        <>
          <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
            {[
              ["Documents", compact(k.total_documents)],
              ["Success rate", pct(k.success_rate, 1)],
              ["Avg. processing time", k.avg_processing_seconds ? `${k.avg_processing_seconds}s` : "—"],
              ["Invoices extracted", compact(k.invoices_extracted)],
            ].map(([t, v]) => (
              <Card key={t} className="p-5">
                <div className="text-sm text-muted">{t}</div>
                <div className="mt-1 font-display text-3xl font-extrabold tabular-nums text-brand-800">{v}</div>
              </Card>
            ))}
          </div>
          <div className="grid gap-6 xl:grid-cols-2">
            <Card className="xl:col-span-2">
              <CardHeader title="Processing activity" subtitle={`Daily volume, last ${days} days`} />
              <div className="p-4 sm:p-6"><ActivityChart data={data.activity} /></div>
            </Card>
            <Card>
              <CardHeader title="Invoice value by month" subtitle="Sum of extracted totals, by currency" />
              <div className="p-4"><StackedBars data={monthly} keys={currencies} xKey="month" money /></div>
            </Card>
            <Card>
              <CardHeader title="Top suppliers" subtitle="By total invoiced value" />
              <div className="p-4">
                <StackedBars data={data.top_suppliers.map((s: any) => ({ supplier: s.supplier, total: s.total }))} keys={["total"]} xKey="supplier" horizontal money height={Math.max(200, data.top_suppliers.length * 36)} />
              </div>
            </Card>
            <Card>
              <CardHeader title="Validation outcomes" subtitle="Invoices by overall validation status" />
              <div className="grid items-center gap-4 p-6 sm:grid-cols-2">
                <DonutChart data={invStatus} height={200} />
                <Legendary data={invStatus} />
              </div>
            </Card>
            <Card>
              <CardHeader title="Validation issues by rule" />
              <div className="p-4"><StackedBars data={data.validation} keys={["failed", "review", "warning"]} xKey="rule" horizontal height={Math.max(200, data.validation.length * 36)} /></div>
            </Card>
            <Card>
              <CardHeader title="File formats" />
              <div className="grid items-center gap-4 p-6 sm:grid-cols-2">
                <DonutChart data={data.document_formats} height={200} />
                <Legendary data={data.document_formats} />
              </div>
            </Card>
            <Card>
              <CardHeader title="Financial summary" />
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead><tr>{["Currency", "Invoices", "Total", "Tax", "Average"].map((h) => <th key={h} className="table-head">{h}</th>)}</tr></thead>
                  <tbody>
                    {data.financial.map((f: any) => {
                      const c = f.currency !== "N/A" ? f.currency : null;
                      return (
                        <tr key={f.currency}>
                          <td className="table-cell font-semibold">{f.currency}</td>
                          <td className="table-cell tabular-nums">{f.count}</td>
                          <td className="table-cell tabular-nums">{money(f.total, c)}</td>
                          <td className="table-cell tabular-nums">{money(f.tax, c)}</td>
                          <td className="table-cell tabular-nums">{money(f.average, c)}</td>
                        </tr>
                      );
                    })}
                    {data.financial.length === 0 && <tr><td colSpan={5} className="table-cell text-center text-muted">No invoices yet</td></tr>}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
