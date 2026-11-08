import clsx from "clsx";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Eye,
  Info,
  Loader2,
  X,
  XCircle,
} from "lucide-react";
import {
  ButtonHTMLAttributes,
  createContext,
  forwardRef,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { label as fmtLabel } from "../lib/format";

// ---------------------------------------------------------------- Button
// Reference-site button language: pill shapes, orange primary CTA, navy solid, outlined secondary.
type Variant = "primary" | "navy" | "secondary" | "ghost" | "danger" | "soft";
const variants: Record<Variant, string> = {
  primary: "bg-accent-500 text-white hover:bg-accent-600 shadow-cta hover:-translate-y-px",
  navy: "bg-brand-800 text-white hover:bg-brand-900 shadow-sm hover:-translate-y-px",
  secondary: "bg-white text-brand-800 border border-line hover:border-brand-300 hover:bg-brand-50",
  ghost: "text-ink-soft hover:bg-brand-50 hover:text-brand-800",
  danger: "bg-bad text-white hover:brightness-95",
  soft: "bg-brand-50 text-brand-800 hover:bg-brand-100",
};

interface BtnProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, BtnProps>(function Button(
  { variant = "primary", size = "md", loading, icon, className, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-full font-semibold transition-all duration-150",
        "disabled:opacity-50 disabled:cursor-not-allowed active:scale-[.98]",
        size === "sm" && "px-3.5 py-1.5 text-xs",
        size === "md" && "px-5 py-2.5 text-sm",
        size === "lg" && "px-7 py-3.5 text-base",
        variants[variant],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : icon}
      {children}
    </button>
  );
});

// ---------------------------------------------------------------- Card
export function Card({ className, children, ...rest }: { className?: string; children: ReactNode } & Record<string, any>) {
  return (
    <div className={clsx("card", className)} {...rest}>
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, action, icon }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4 sm:px-6">
      <div className="flex items-start gap-3">
        {icon && <div className="mt-0.5 rounded-xl bg-accent-50 p-2 text-accent-600">{icon}</div>}
        <div>
          <h3 className="font-display text-base font-bold text-ink">{title}</h3>
          {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  );
}

// ---------------------------------------------------------------- Inputs
export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & { label?: string; hint?: string }>(
  function Input({ label, hint, className, id, ...rest }, ref) {
    const inputId = id || rest.name;
    return (
      <div className={className}>
        {label && (
          <label htmlFor={inputId} className="label">
            {label}
          </label>
        )}
        <input ref={ref} id={inputId} className="input" {...rest} />
        {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
      </div>
    );
  },
);

export function Select({ label, className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement> & { label?: string }) {
  return (
    <div className={className}>
      {label && <label className="label">{label}</label>}
      <select className="input appearance-none bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2212%22 height=%2212%22 viewBox=%220 0 24 24%22 fill=%22none%22 stroke=%22%2364748B%22 stroke-width=%222%22><path d=%22m6 9 6 6 6-6%22/></svg>')] bg-[right_12px_center] bg-no-repeat pr-9" {...rest}>
        {children}
      </select>
    </div>
  );
}

export function Toggle({ checked, onChange, label, description, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode; description?: ReactNode; disabled?: boolean }) {
  return (
    <label className={clsx("flex cursor-pointer items-start justify-between gap-4", disabled && "cursor-not-allowed opacity-60")}>
      <span>
        <span className="block text-sm font-semibold text-ink">{label}</span>
        {description && <span className="mt-0.5 block text-sm text-muted">{description}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={clsx("relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition-colors", checked ? "bg-accent-500" : "bg-slate-300")}
      >
        <span className={clsx("absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all", checked ? "left-[22px]" : "left-0.5")} />
      </button>
    </label>
  );
}

// ---------------------------------------------------------------- Badges
const tones = {
  green: "bg-ok-bg text-ok",
  amber: "bg-warn-bg text-warn",
  red: "bg-bad-bg text-bad",
  blue: "bg-info-bg text-info",
  gray: "bg-slate-100 text-slate-600",
  brand: "bg-brand-50 text-brand-800",
  orange: "bg-accent-50 text-accent-700",
} as const;
export type Tone = keyof typeof tones;

export function Badge({ tone = "gray", children, icon, className }: { tone?: Tone; children: ReactNode; icon?: ReactNode; className?: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold", tones[tone], className)}>
      {icon}
      {children}
    </span>
  );
}

const STATUS: Record<string, { tone: Tone; icon: ReactNode; text?: string }> = {
  passed: { tone: "green", icon: <CheckCircle2 className="h-3.5 w-3.5" />, text: "Passed" },
  warning: { tone: "amber", icon: <AlertTriangle className="h-3.5 w-3.5" />, text: "Warning" },
  failed: { tone: "red", icon: <XCircle className="h-3.5 w-3.5" />, text: "Failed" },
  review: { tone: "blue", icon: <Eye className="h-3.5 w-3.5" />, text: "Manual Review" },
  completed: { tone: "green", icon: <CheckCircle2 className="h-3.5 w-3.5" />, text: "Completed" },
  needs_review: { tone: "blue", icon: <Eye className="h-3.5 w-3.5" />, text: "Needs Review" },
  processing: { tone: "brand", icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />, text: "Processing" },
  running: { tone: "brand", icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />, text: "Running" },
  queued: { tone: "gray", icon: <Clock className="h-3.5 w-3.5" />, text: "Queued" },
  uploaded: { tone: "gray", icon: <Clock className="h-3.5 w-3.5" />, text: "Uploaded" },
  cancelled: { tone: "gray", icon: <X className="h-3.5 w-3.5" />, text: "Cancelled" },
  pending: { tone: "amber", icon: <Clock className="h-3.5 w-3.5" />, text: "Pending" },
  approved: { tone: "green", icon: <CheckCircle2 className="h-3.5 w-3.5" />, text: "Approved" },
  rejected: { tone: "red", icon: <XCircle className="h-3.5 w-3.5" />, text: "Rejected" },
};

export function StatusBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <span className="text-muted">—</span>;
  const s = STATUS[status] || { tone: "gray" as Tone, icon: <Info className="h-3.5 w-3.5" /> };
  return (
    <Badge tone={s.tone} icon={s.icon}>
      {s.text || fmtLabel(status)}
    </Badge>
  );
}

export function DemoBadge() {
  return (
    <Badge tone="orange" className="!px-2 !py-0 text-[10px] uppercase tracking-wider">
      Demo
    </Badge>
  );
}

export function ConfidenceBar({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return <span className="text-xs text-muted">—</span>;
  const pct = Math.round(value * 100);
  const color = value >= 0.9 ? "bg-ok" : value >= 0.75 ? "bg-brand-500" : value > 0 ? "bg-accent-400" : "bg-bad";
  return (
    <div className="flex items-center gap-2" title={`Confidence ${pct}%`}>
      <div className="h-1.5 w-14 overflow-hidden rounded-full bg-line">
        <div className={clsx("h-full rounded-full", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-8 text-xs tabular-nums text-muted">{pct}%</span>
    </div>
  );
}

// ---------------------------------------------------------------- States
export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={clsx("h-5 w-5 animate-spin text-brand-600", className)} />;
}

export function PageLoader() {
  return (
    <div className="flex h-64 items-center justify-center">
      <Spinner className="h-7 w-7" />
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("skeleton", className)} />;
}

export function EmptyState({ icon, title, description, action }: { icon: ReactNode; title: string; description?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <div className="mb-4 rounded-full bg-accent-50 p-4 text-accent-500">{icon}</div>
      <h3 className="font-display text-lg font-bold">{title}</h3>
      {description && <p className="mt-1 max-w-md text-sm text-muted">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div className="flex items-start gap-2 rounded-xl border border-bad/20 bg-bad-bg px-4 py-3 text-sm text-bad">
      <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{msg}</span>
    </div>
  );
}

export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total <= pageSize) return null;
  return (
    <div className="flex items-center justify-between border-t border-line px-5 py-3 text-sm text-muted">
      <span>
        {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} of {total}
      </span>
      <div className="flex items-center gap-1">
        <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)} icon={<ChevronLeft className="h-4 w-4" />} aria-label="Previous page" />
        <span className="px-2 tabular-nums">
          {page} / {pages}
        </span>
        <Button variant="ghost" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)} icon={<ChevronRight className="h-4 w-4" />} aria-label="Next page" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Modal / confirm
export function Modal({ open, onClose, title, children, footer, wide }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/40 p-0 backdrop-blur-[2px] sm:items-center sm:p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className={clsx("card w-full animate-fade-in rounded-b-none sm:rounded-2xl", wide ? "max-w-2xl" : "max-w-md")}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-line px-6 py-4">
          <h3 className="font-sans text-base font-semibold">{title}</h3>
          <button onClick={onClose} className="rounded-lg p-1 text-muted hover:bg-cream" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto px-6 py-5">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-line px-6 py-4">{footer}</div>}
      </div>
    </div>
  );
}

export function ConfirmDialog({ open, onClose, onConfirm, title, message, confirmText = "Confirm", danger, loading }: {
  open: boolean; onClose: () => void; onConfirm: () => void; title: string; message: ReactNode; confirmText?: string; danger?: boolean; loading?: boolean;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button variant={danger ? "danger" : "primary"} onClick={onConfirm} loading={loading}>
            {confirmText}
          </Button>
        </>
      }
    >
      <div className="text-sm text-ink-soft">{message}</div>
    </Modal>
  );
}

// ---------------------------------------------------------------- Toasts
type ToastT = { id: number; tone: "success" | "error" | "info"; text: string };
const ToastCtx = createContext<(tone: ToastT["tone"], text: string) => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastT[]>([]);
  const push = useCallback((tone: ToastT["tone"], text: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, tone, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[calc(100%-2rem)] max-w-sm flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={clsx(
              "pointer-events-auto flex animate-fade-in items-start gap-2.5 rounded-xl border bg-white px-4 py-3 text-sm shadow-lift",
              t.tone === "success" && "border-ok/20",
              t.tone === "error" && "border-bad/20",
              t.tone === "info" && "border-line",
            )}
          >
            {t.tone === "success" && <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-ok" />}
            {t.tone === "error" && <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-bad" />}
            {t.tone === "info" && <Info className="mt-0.5 h-4 w-4 shrink-0 text-info" />}
            <span className="text-ink">{t.text}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);

// ---------------------------------------------------------------- Tabs
export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { key: T; label: ReactNode; count?: number }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="flex w-fit max-w-full gap-1 overflow-x-auto rounded-full border border-line bg-white p-1 shadow-soft scrollbar-thin">
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={clsx(
            "flex items-center gap-1.5 whitespace-nowrap rounded-full px-4 py-1.5 text-sm font-semibold transition",
            value === t.key ? "bg-brand-800 text-white shadow-sm" : "text-muted hover:bg-brand-50 hover:text-brand-800",
          )}
        >
          {t.label}
          {t.count !== undefined && (
            <span className={clsx("rounded-full px-1.5 text-[11px] font-bold", value === t.key ? "bg-accent-500 text-white" : "bg-slate-100")}>{t.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions, eyebrow }: { title: string; subtitle?: ReactNode; actions?: ReactNode; eyebrow?: string }) {
  return (
    <div className="mb-7 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        {eyebrow && <p className="eyebrow mb-1.5">{eyebrow}</p>}
        <h1 className="text-2xl font-extrabold text-brand-800 sm:text-[30px]">{title}</h1>
        {subtitle && <p className="mt-1.5 text-sm text-muted sm:text-base">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}
