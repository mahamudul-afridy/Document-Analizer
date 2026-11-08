import { ReactNode } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { compact, label } from "../lib/format";

export const PALETTE = ["#1C3461", "#E57824", "#2F5FB0", "#94ACD4", "#F4AE6E", "#059669", "#64748B", "#13254A"];
// status colors stay semantic (orange is reserved for brand accents / calls to action)
export const SEV_COLORS = {
  failed: "#DC2626", review: "#2F5FB0", warning: "#F59E0B", passed: "#059669",
  completed: "#059669", needs_review: "#2F5FB0", pending: "#94A3B8",
};
const axis = { stroke: "#94A3B8", fontSize: 12, tickLine: false, axisLine: false };

function TooltipBox({ active, payload, label: l, money }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-line bg-white px-3 py-2 text-xs shadow-lift">
      {l && <div className="mb-1 font-semibold text-ink">{l}</div>}
      {payload.map((p: any) => (
        <div key={p.dataKey ?? p.name} className="flex items-center gap-2 text-ink-soft">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color || p.payload?.fill }} />
          <span>{label(String(p.name))}:</span>
          <span className="font-semibold tabular-nums text-ink">{money ? Number(p.value).toLocaleString("en-US", { maximumFractionDigits: 2 }) : p.value}</span>
        </div>
      ))}
    </div>
  );
}

export function ChartEmpty({ children = "No data yet" }: { children?: ReactNode }) {
  return <div className="flex h-full min-h-[200px] items-center justify-center text-sm text-muted">{children}</div>;
}

export function ActivityChart({ data }: { data: { date: string; uploaded: number; processed: number; failed: number }[] }) {
  if (!data.some((d) => d.uploaded || d.processed || d.failed)) return <ChartEmpty>No processing activity in this period</ChartEmpty>;
  const fmt = (d: string) => new Date(d + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={data} margin={{ top: 10, right: 8, left: -18, bottom: 0 }}>
        <defs>
          <linearGradient id="gUp" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#E57824" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#E57824" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="gDone" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#1C3461" stopOpacity={0.3} />
            <stop offset="100%" stopColor="#1C3461" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="#EEF2F7" vertical={false} />
        <XAxis dataKey="date" tickFormatter={fmt} {...axis} minTickGap={24} />
        <YAxis allowDecimals={false} {...axis} />
        <Tooltip content={<TooltipBox />} labelFormatter={fmt} />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} formatter={(v) => label(v)} />
        <Area type="monotone" dataKey="uploaded" stroke="#E57824" fill="url(#gUp)" strokeWidth={2} />
        <Area type="monotone" dataKey="processed" stroke="#1C3461" fill="url(#gDone)" strokeWidth={2} />
        <Area type="monotone" dataKey="failed" stroke="#DC2626" fill="transparent" strokeWidth={2} strokeDasharray="4 3" />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function DonutChart({ data, height = 240, center }: { data: { name: string; value: number }[]; height?: number; center?: ReactNode }) {
  const total = data.reduce((s, d) => s + d.value, 0);
  if (!total) return <ChartEmpty />;
  return (
    <div className="relative">
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius="62%" outerRadius="88%" paddingAngle={2} stroke="none">
            {data.map((d, i) => (
              <Cell key={d.name} fill={(SEV_COLORS as any)[d.name] || PALETTE[i % PALETTE.length]} />
            ))}
          </Pie>
          <Tooltip content={<TooltipBox />} />
        </PieChart>
      </ResponsiveContainer>
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
        {center ?? (
          <>
            <span className="font-display text-3xl font-semibold">{compact(total)}</span>
            <span className="text-xs text-muted">total</span>
          </>
        )}
      </div>
    </div>
  );
}

export function Legendary({ data }: { data: { name: string; value: number }[] }) {
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  return (
    <ul className="space-y-2">
      {data.map((d, i) => (
        <li key={d.name} className="flex items-center justify-between gap-3 text-sm">
          <span className="flex items-center gap-2 text-ink-soft">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: (SEV_COLORS as any)[d.name] || PALETTE[i % PALETTE.length] }} />
            {label(d.name)}
          </span>
          <span className="tabular-nums text-muted">
            <span className="font-semibold text-ink">{d.value}</span> · {Math.round((d.value / total) * 100)}%
          </span>
        </li>
      ))}
    </ul>
  );
}

export function StackedBars({ data, keys, xKey, height = 260, horizontal, money }: { data: any[]; keys: string[]; xKey: string; height?: number; horizontal?: boolean; money?: boolean }) {
  if (!data.length) return <ChartEmpty />;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout={horizontal ? "vertical" : "horizontal"} margin={{ top: 8, right: 12, left: horizontal ? 8 : -12, bottom: 0 }}>
        <CartesianGrid stroke="#EEF2F7" vertical={!!horizontal} horizontal={!horizontal} />
        {horizontal ? (
          <>
            <XAxis type="number" {...axis} allowDecimals={false} tickFormatter={money ? compact : undefined} />
            <YAxis type="category" dataKey={xKey} {...axis} width={140} tickFormatter={(v) => label(String(v)).slice(0, 22)} />
          </>
        ) : (
          <>
            <XAxis dataKey={xKey} {...axis} tickFormatter={(v) => label(String(v))} />
            <YAxis {...axis} allowDecimals={false} tickFormatter={money ? compact : undefined} />
          </>
        )}
        <Tooltip content={<TooltipBox money={money} />} cursor={{ fill: "#EEF2FB" }} />
        {keys.length > 1 && <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} formatter={(v) => label(v)} />}
        {keys.map((k, i) => (
          <Bar key={k} dataKey={k} stackId="a" fill={(SEV_COLORS as any)[k] || PALETTE[i % PALETTE.length]} radius={i === keys.length - 1 ? (horizontal ? [0, 6, 6, 0] : [6, 6, 0, 0]) : 0} maxBarSize={36} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
