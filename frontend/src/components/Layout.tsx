import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import {
  Activity,
  BarChart3,
  Bell,
  ChevronDown,
  FileSearch,
  FileText,
  KeyRound,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Receipt,
  Search,
  Settings,
  ShieldCheck,
  UploadCloud,
  User as UserIcon,
  X,
} from "lucide-react";
import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { label, timeAgo } from "../lib/format";
import { useJobStream } from "../lib/jobs";
import { Logo } from "./Logo";
import { Badge } from "./ui";

export const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/documents", label: "Documents", icon: FileText },
  { to: "/upload", label: "Upload Documents", icon: UploadCloud },
  { to: "/queue", label: "Processing Queue", icon: ListChecks },
  { to: "/invoices", label: "Extracted Invoices", icon: Receipt },
  { to: "/validation", label: "Validation & Verification", icon: ShieldCheck },
  { to: "/search", label: "Document Search", icon: FileSearch },
  { to: "/analytics", label: "Analytics & Reports", icon: BarChart3 },
  { to: "/api", label: "API Management", icon: KeyRound },
  { to: "/settings", label: "Settings", icon: Settings },
];

function titleFor(path: string) {
  if (path.startsWith("/documents/")) return "Document Inspection";
  return NAV.find((n) => (n.to === "/" ? path === "/" : path.startsWith(n.to)))?.label || "DocuMind AI";
}

function Sidebar({ collapsed, onToggle, mobile, onClose }: { collapsed: boolean; onToggle: () => void; mobile?: boolean; onClose?: () => void }) {
  const { user } = useAuth();
  const { data: counts } = useQuery({ queryKey: ["job-counts"], queryFn: () => api("/jobs/counts"), refetchInterval: 30000 });
  const active = counts ? (counts.queued || 0) + (counts.running || 0) : 0;
  return (
    <aside
      className={clsx(
        "flex h-full flex-col border-r border-line bg-white transition-[width] duration-200",
        mobile ? "w-72" : collapsed ? "w-[76px]" : "w-64",
      )}
    >
      <div className={clsx("flex h-16 items-center border-b border-line", collapsed && !mobile ? "justify-center px-2" : "justify-between px-5")}>
        <Link to="/" onClick={onClose}>
          <Logo collapsed={collapsed && !mobile} />
        </Link>
        {mobile && (
          <button onClick={onClose} className="rounded-lg p-1.5 text-muted hover:bg-cream" aria-label="Close menu">
            <X className="h-5 w-5" />
          </button>
        )}
      </div>
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-4 scrollbar-thin">
        {NAV.map(({ to, label: text, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            onClick={onClose}
            title={collapsed ? text : undefined}
            className={({ isActive }) =>
              clsx(
                "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition",
                collapsed && !mobile && "justify-center",
                isActive
                  ? "bg-brand-800 text-white shadow-navy before:absolute before:left-0 before:top-2 before:bottom-2 before:w-1 before:rounded-r-full before:bg-accent-500"
                  : "text-ink-soft hover:bg-brand-50 hover:text-brand-800",
              )
            }
          >
            <Icon className="h-[18px] w-[18px] shrink-0" />
            {(!collapsed || mobile) && <span className="truncate">{text}</span>}
            {to === "/queue" && active > 0 && (
              <span className={clsx("ml-auto rounded-full bg-accent-500 px-1.5 text-[11px] font-bold text-white", collapsed && !mobile && "absolute right-1 top-1")}>
                {active}
              </span>
            )}
          </NavLink>
        ))}
      </nav>
      {!mobile && (
        <button onClick={onToggle} className="mx-3 mb-2 flex items-center gap-3 rounded-xl px-3 py-2 text-sm text-muted hover:bg-cream" aria-label="Toggle sidebar">
          {collapsed ? <PanelLeftOpen className="mx-auto h-[18px] w-[18px]" /> : <><PanelLeftClose className="h-[18px] w-[18px]" /> Collapse</>}
        </button>
      )}
      <div className={clsx("border-t border-line p-3", collapsed && !mobile && "flex justify-center")}>
        <Link to="/settings" onClick={onClose} className="flex items-center gap-3 rounded-xl p-2 hover:bg-cream">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent-500 text-sm font-bold text-white">
            {(user?.full_name || user?.email || "?").slice(0, 1).toUpperCase()}
          </div>
          {(!collapsed || mobile) && (
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold">{user?.full_name || user?.email}</div>
              <div className="text-xs capitalize text-muted">{user?.role}</div>
            </div>
          )}
        </Link>
      </div>
    </aside>
  );
}

function useClickOutside(ref: React.RefObject<HTMLElement>, fn: () => void) {
  useEffect(() => {
    const h = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && fn();
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [ref, fn]);
}

function Topbar({ onMenu }: { onMenu: () => void }) {
  const loc = useLocation();
  const nav = useNavigate();
  const { user, logout } = useAuth();
  const { live, connected, activeCount } = useJobStream();
  const [q, setQ] = useState("");
  const [openNotif, setOpenNotif] = useState(false);
  const [openUser, setOpenUser] = useState(false);
  const [seen, setSeen] = useState(0);
  const notifRef = useRef<HTMLDivElement>(null);
  const userRef = useRef<HTMLDivElement>(null);
  useClickOutside(notifRef, () => setOpenNotif(false));
  useClickOutside(userRef, () => setOpenUser(false));

  const events = Object.values(live)
    .filter((e) => ["completed", "failed", "cancelled"].includes(e.job_status) || e.stage === "uploaded")
    .reverse()
    .slice(0, 12);
  const finished = Object.values(live).filter((e) => ["completed", "failed"].includes(e.job_status)).length;
  const unread = Math.max(0, finished - seen);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (q.trim()) nav(`/search?q=${encodeURIComponent(q.trim())}`);
  };

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-line bg-white/90 px-4 backdrop-blur sm:px-6">
      <button onClick={onMenu} className="rounded-lg p-2 text-ink-soft hover:bg-cream lg:hidden" aria-label="Open menu">
        <Menu className="h-5 w-5" />
      </button>
      <h2 className="hidden truncate font-display text-base font-bold text-brand-800 md:block md:w-56 lg:w-64">{titleFor(loc.pathname)}</h2>
      <form onSubmit={submit} className="relative mx-auto w-full max-w-lg flex-1">
        <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search invoices, suppliers, or ask a question…"
          className="input rounded-full !bg-cream !py-2 pl-10 focus:!bg-white"
          aria-label="Global search"
        />
      </form>
      <div className="flex items-center gap-1 sm:gap-2">
        <Link
          to="/queue"
          title={connected ? "Live updates connected" : "Live updates reconnecting…"}
          className="hidden items-center gap-2 rounded-full border border-line bg-white px-3 py-1.5 text-xs font-semibold text-ink-soft hover:border-brand-300 sm:flex"
        >
          <span className="relative flex h-2 w-2">
            {activeCount > 0 && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent-400 opacity-75" />}
            <span className={clsx("relative inline-flex h-2 w-2 rounded-full", connected ? "bg-ok" : "bg-warn")} />
          </span>
          {activeCount > 0 ? `${activeCount} processing` : connected ? "All caught up" : "Connecting"}
          <Activity className="h-3.5 w-3.5" />
        </Link>

        <div ref={notifRef} className="relative">
          <button
            onClick={() => {
              setOpenNotif(!openNotif);
              setSeen(finished);
            }}
            className="relative rounded-full p-2 text-ink-soft hover:bg-cream"
            aria-label="Notifications"
          >
            <Bell className="h-5 w-5" />
            {unread > 0 && <span className="absolute right-1 top-1 h-2.5 w-2.5 rounded-full border-2 border-white bg-accent-500" />}
          </button>
          {openNotif && (
            <div className="card absolute right-0 mt-2 w-80 animate-fade-in overflow-hidden">
              <div className="border-b border-line px-4 py-3 text-sm font-semibold">Processing notifications</div>
              <div className="max-h-80 overflow-y-auto">
                {events.length === 0 && <p className="px-4 py-6 text-center text-sm text-muted">No activity in this session yet.</p>}
                {events.map((e) => (
                  <Link
                    key={e.job_id}
                    to={`/documents/${e.document_id}`}
                    onClick={() => setOpenNotif(false)}
                    className="flex items-start gap-3 border-b border-line px-4 py-3 text-sm last:border-0 hover:bg-cream"
                  >
                    <span className={clsx("mt-1.5 h-2 w-2 shrink-0 rounded-full", e.job_status === "failed" ? "bg-bad" : e.job_status === "completed" ? "bg-ok" : "bg-accent-400")} />
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{e.document_name}</span>
                      <span className="text-xs text-muted">
                        {e.job_status === "completed" ? "Processing completed" : e.job_status === "failed" ? `Failed: ${e.message || label(e.stage)}` : label(e.stage)}
                      </span>
                    </span>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>

        <div ref={userRef} className="relative">
          <button onClick={() => setOpenUser(!openUser)} className="flex items-center gap-1.5 rounded-full p-1 pr-2 hover:bg-cream" aria-label="User menu">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-800 text-sm font-bold text-white">
              {(user?.full_name || user?.email || "?").slice(0, 1).toUpperCase()}
            </span>
            <ChevronDown className="hidden h-4 w-4 text-muted sm:block" />
          </button>
          {openUser && (
            <div className="card absolute right-0 mt-2 w-60 animate-fade-in overflow-hidden py-1">
              <div className="border-b border-line px-4 py-3">
                <div className="truncate text-sm font-semibold">{user?.full_name}</div>
                <div className="truncate text-xs text-muted">{user?.email}</div>
                <Badge tone="brand" className="mt-2 capitalize">{user?.role}</Badge>
              </div>
              <Link to="/settings" onClick={() => setOpenUser(false)} className="flex items-center gap-2 px-4 py-2.5 text-sm hover:bg-cream">
                <UserIcon className="h-4 w-4 text-muted" /> Profile & settings
              </Link>
              <Link to="/api" onClick={() => setOpenUser(false)} className="flex items-center gap-2 px-4 py-2.5 text-sm hover:bg-cream">
                <KeyRound className="h-4 w-4 text-muted" /> API keys
              </Link>
              <button onClick={logout} className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-bad hover:bg-bad-bg">
                <LogOut className="h-4 w-4" /> Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem("dm.sidebar") === "1";
    } catch {
      return false;
    }
  });
  const [mobileOpen, setMobileOpen] = useState(false);
  const toggle = () => {
    setCollapsed((c) => {
      try {
        localStorage.setItem("dm.sidebar", c ? "0" : "1");
      } catch {
        /* storage blocked */
      }
      return !c;
    });
  };
  return (
    <div className="flex h-screen overflow-hidden">
      <div className="hidden lg:block">
        <Sidebar collapsed={collapsed} onToggle={toggle} />
      </div>
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-ink/40" onClick={() => setMobileOpen(false)} />
          <div className="relative h-full animate-fade-in">
            <Sidebar collapsed={false} onToggle={toggle} mobile onClose={() => setMobileOpen(false)} />
          </div>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Topbar onMenu={() => setMobileOpen(true)} />
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</div>
        </main>
      </div>
    </div>
  );
}
