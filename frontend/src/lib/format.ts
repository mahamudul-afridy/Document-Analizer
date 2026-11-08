export function money(v: number | string | null | undefined, currency?: string | null) {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "string" ? Number(v) : v;
  if (Number.isNaN(n)) return String(v);
  try {
    if (currency && /^[A-Z]{3}$/.test(currency))
      return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(n);
  } catch {
    /* unknown currency code */
  }
  return new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n) +
    (currency ? ` ${currency}` : "");
}

export function compact(n: number) {
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

export function date(v: string | null | undefined) {
  if (!v) return "—";
  const d = new Date(v.length === 10 ? v + "T00:00:00" : v);
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

export function dateTime(v: string | null | undefined) {
  if (!v) return "—";
  return new Date(v).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function timeAgo(v: string | null | undefined) {
  if (!v) return "—";
  const s = Math.round((Date.now() - new Date(v).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function bytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 ** 2).toFixed(1)} MB`;
}

export function pct(v: number | null | undefined, digits = 0) {
  return v === null || v === undefined ? "—" : `${(v * 100).toFixed(digits)}%`;
}

export const label = (s: string | null | undefined) => {
  if (!s) return "—";
  const cross = s.match(/^cross_document_([a-z]+)_([a-z]+)$/); // e.g. cross_document_pdf_excel
  if (cross) return `${cross[1].toUpperCase()} ↔ ${cross[2].toUpperCase()} check`;
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
};

export const FIELD_LABELS: Record<string, string> = {
  invoice_number: "Invoice Number",
  invoice_date: "Invoice Date",
  supplier_name: "Supplier",
  customer_name: "Customer",
  subtotal: "Subtotal",
  tax: "Tax",
  tax_rate: "Tax Rate (%)",
  total: "Total Amount",
  currency: "Currency",
};
