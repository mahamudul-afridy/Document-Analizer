import clsx from "clsx";

/** Navy tile, white document, orange "verified" badge: matches the reference site's navy + orange identity. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={clsx("shrink-0", className)} aria-hidden="true">
      <rect width="64" height="64" rx="16" fill="#1C3461" />
      <path d="M20 13h16l10 10v26a3 3 0 0 1-3 3H20a3 3 0 0 1-3-3V16a3 3 0 0 1 3-3z" fill="#FFFFFF" />
      <path d="M36 13v8a2 2 0 0 0 2 2h8" fill="#DFE8F5" />
      <rect x="22" y="29" width="13" height="3" rx="1.5" fill="#94ACD4" />
      <rect x="22" y="36" width="17" height="3" rx="1.5" fill="#94ACD4" />
      <circle cx="43" cy="45" r="8" fill="#E57824" stroke="#1C3461" strokeWidth="2.5" />
      <path d="M39.6 45.2l2.3 2.3 4.4-4.7" stroke="#FFFFFF" strokeWidth="2.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Logo({ collapsed, light }: { collapsed?: boolean; light?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      {/* on navy backgrounds the navy tile needs a light ring to stay visible */}
      <LogoMark className={clsx("h-9 w-9", light && "rounded-[10px] ring-2 ring-white/70 shadow-lg")} />
      {!collapsed && (
        <div className="leading-tight">
          <div className={clsx("font-display text-lg font-extrabold tracking-tight", light ? "text-white" : "text-brand-800")}>
            DocuMind <span className="text-accent-500">AI</span>
          </div>
          <div className={clsx("text-[10px] font-bold uppercase tracking-[0.16em]", light ? "text-brand-200" : "text-muted")}>
            Document Intelligence
          </div>
        </div>
      )}
    </div>
  );
}
