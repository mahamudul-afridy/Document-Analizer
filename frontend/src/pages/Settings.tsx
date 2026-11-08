import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Bot, CheckCircle2, Cpu, Database, KeyRound, Plug, ScrollText, Sparkles, Trash2, UserPlus, Users, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  ConfirmDialog,
  ErrorBox,
  Input,
  Modal,
  PageHeader,
  Pagination,
  Select,
  Skeleton,
  Tabs,
  Toggle,
  useToast,
} from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { dateTime, label } from "../lib/format";

// ---------------------------------------------------------------- AI engine
function AIEngine() {
  const { can } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["settings-ai"], queryFn: () => api("/settings/ai") });
  const [form, setForm] = useState({ llm_enabled: false, provider: "anthropic", model: "", api_key: "", fallback_to_builtin: true, timeout_s: 60 });
  const [test, setTest] = useState<{ ok: boolean; message: string } | null>(null);
  useEffect(() => {
    if (data)
      setForm({
        llm_enabled: data.llm_enabled,
        provider: data.provider || "anthropic",
        model: data.model || data.providers[data.provider || "anthropic"].default_model,
        api_key: "",
        fallback_to_builtin: data.fallback_to_builtin,
        timeout_s: data.timeout_s,
      });
  }, [data]);

  const save = useMutation({
    mutationFn: (extra: Record<string, unknown> = {}) =>
      api("/settings/ai", { method: "PUT", body: { ...form, api_key: form.api_key || null, ...extra } }),
    onSuccess: () => {
      toast("success", "AI engine settings saved");
      setForm((f) => ({ ...f, api_key: "" }));
      qc.invalidateQueries({ queryKey: ["settings-ai"] });
    },
    onError: (e: Error) => toast("error", e.message),
  });
  const runTest = useMutation({
    mutationFn: () => api("/settings/ai/test", { body: { provider: form.provider, model: form.model, api_key: form.api_key || null } }),
    onSuccess: (r) => setTest(r),
    onError: (e: Error) => setTest({ ok: false, message: e.message }),
  });

  if (isLoading || !data) return <Skeleton className="h-96" />;
  const admin = can("admin");
  const providers = data.providers as Record<string, { label: string; default_model: string; models: string[] }>;
  const keyAvailable = form.api_key || (data.api_key_set && data.provider === form.provider);
  const usingLLM = data.active_engine !== "builtin";

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
      <Card>
        <CardHeader icon={<Bot className="h-4 w-4" />} title="AI Engine" subtitle="DocuMind works fully without an API key. Optionally connect an LLM for harder layouts." />
        <div className="space-y-6 p-6">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className={clsx("rounded-2xl border-2 p-4", !usingLLM ? "border-brand-600 bg-brand-50" : "border-line")}>
              <div className="flex items-center gap-2 font-semibold"><Cpu className="h-4 w-4 text-brand-700" /> Built-in engine {!usingLLM && <Badge tone="brand">Active</Badge>}</div>
              <p className="mt-1.5 text-sm text-muted">Rule-based, layout-aware extraction plus local semantic search. Free, private and offline. Always available as the fallback.</p>
            </div>
            <div className={clsx("rounded-2xl border-2 p-4", usingLLM ? "border-info bg-info-bg/50" : "border-line")}>
              <div className="flex items-center gap-2 font-semibold"><Sparkles className="h-4 w-4 text-info" /> LLM engine {usingLLM ? <Badge tone="blue">Active</Badge> : <Badge tone="gray">Off</Badge>}</div>
              <p className="mt-1.5 text-sm text-muted">Anthropic Claude or OpenAI for unusual invoice layouts. Needs an API key; document text is sent to the provider.</p>
            </div>
          </div>

          {!admin && <p className="rounded-xl bg-cream px-4 py-3 text-sm text-muted">Only administrators can change AI engine settings.</p>}

          <div className="space-y-5 rounded-2xl border border-line p-5">
            <Toggle
              checked={form.llm_enabled}
              disabled={!admin}
              onChange={(v) => setForm({ ...form, llm_enabled: v })}
              label="Enable LLM extraction"
              description={keyAvailable ? "New and reprocessed documents will use the selected provider." : "Add an API key below to enable."}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <Select label="Provider" value={form.provider} disabled={!admin} onChange={(e) => setForm({ ...form, provider: e.target.value, model: providers[e.target.value].default_model })}>
                {Object.entries(providers).map(([k, p]) => <option key={k} value={k}>{p.label}</option>)}
              </Select>
              <div>
                <label className="label">Model</label>
                <input className="input" list="models" value={form.model} disabled={!admin} onChange={(e) => setForm({ ...form, model: e.target.value })} />
                <datalist id="models">{providers[form.provider]?.models.map((m) => <option key={m} value={m} />)}</datalist>
              </div>
            </div>
            <div>
              <label className="label">API key</label>
              <div className="flex flex-col gap-2 sm:flex-row">
                <input
                  className="input flex-1 font-mono"
                  type="password"
                  autoComplete="off"
                  disabled={!admin}
                  placeholder={data.api_key_set && data.provider === form.provider ? `Saved: ${data.api_key_masked} (leave empty to keep)` : "Paste your API key"}
                  value={form.api_key}
                  onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                />
                <Button variant="secondary" icon={<Plug className="h-4 w-4" />} disabled={!admin || !keyAvailable} loading={runTest.isPending} onClick={() => runTest.mutate()}>
                  Test connection
                </Button>
              </div>
              <p className="mt-1.5 text-xs text-muted">Stored encrypted on the server and never shown again in full.</p>
              {test && (
                <div className={clsx("mt-3 flex items-start gap-2 rounded-xl px-4 py-3 text-sm", test.ok ? "bg-ok-bg text-ok" : "bg-bad-bg text-bad")}>
                  {test.ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> : <XCircle className="mt-0.5 h-4 w-4 shrink-0" />} {test.message}
                </div>
              )}
            </div>
            <Toggle
              checked={form.fallback_to_builtin}
              disabled={!admin}
              onChange={(v) => setForm({ ...form, fallback_to_builtin: v })}
              label="Fall back to the built-in engine on LLM errors"
              description="Recommended. If the provider times out or runs out of quota, documents are still processed."
            />
            <div className="sm:w-48">
              <Input label="Timeout (seconds)" type="number" min={5} max={300} disabled={!admin} value={form.timeout_s} onChange={(e) => setForm({ ...form, timeout_s: Number(e.target.value) })} />
            </div>
          </div>
          {admin && (
            <div className="flex flex-wrap justify-between gap-2">
              {data.api_key_set ? (
                <Button variant="ghost" className="text-bad hover:bg-bad-bg hover:text-bad" icon={<Trash2 className="h-4 w-4" />} onClick={() => save.mutate({ clear_api_key: true, llm_enabled: false, api_key: null })}>
                  Remove saved key
                </Button>
              ) : <span />}
              <Button onClick={() => save.mutate({})} loading={save.isPending}>Save settings</Button>
            </div>
          )}
        </div>
      </Card>
      <Card className="h-fit p-6">
        <h3 className="font-sans text-base font-semibold">Current status</h3>
        <dl className="mt-4 space-y-3 text-sm">
          <div className="flex justify-between"><dt className="text-muted">Active engine</dt><dd className="font-semibold">{usingLLM ? providers[data.provider]?.label : "Built-in"}</dd></div>
          <div className="flex justify-between"><dt className="text-muted">LLM enabled</dt><dd>{data.llm_enabled ? "Yes" : "No"}</dd></div>
          <div className="flex justify-between"><dt className="text-muted">Provider</dt><dd>{data.provider ? providers[data.provider]?.label : "—"}</dd></div>
          <div className="flex justify-between"><dt className="text-muted">Model</dt><dd className="font-mono text-xs">{data.model || "—"}</dd></div>
          <div className="flex justify-between"><dt className="text-muted">API key</dt><dd className="font-mono text-xs">{data.api_key_masked || "not set"}</dd></div>
          <div className="flex justify-between"><dt className="text-muted">Fallback</dt><dd>{data.fallback_to_builtin ? "On" : "Off"}</dd></div>
        </dl>
        <p className="mt-5 rounded-xl bg-cream p-3 text-xs text-muted">
          Changes apply to newly uploaded and reprocessed documents. Each invoice records which engine extracted it. Semantic search always runs locally.
        </p>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- profile
function Profile() {
  const { user, setUser } = useAuth();
  const toast = useToast();
  const [name, setName] = useState(user?.full_name || "");
  const [cur, setCur] = useState("");
  const [pw, setPw] = useState("");
  const m = useMutation({
    mutationFn: () => api("/auth/me", { method: "PATCH", body: { full_name: name, current_password: cur || null, new_password: pw || null } }),
    onSuccess: (u) => {
      setUser(u);
      setCur("");
      setPw("");
      toast("success", "Profile updated");
    },
    onError: (e: Error) => toast("error", e.message),
  });
  return (
    <Card className="max-w-2xl">
      <CardHeader title="Your profile" subtitle={`${user?.email} · ${user?.role}`} />
      <form className="space-y-4 p-6" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
        <Input label="Full name" value={name} onChange={(e) => setName(e.target.value)} required />
        <div className="grid gap-4 border-t border-line pt-4 sm:grid-cols-2">
          <Input label="Current password" type="password" value={cur} onChange={(e) => setCur(e.target.value)} autoComplete="current-password" />
          <Input label="New password" type="password" minLength={8} value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" hint="Leave empty to keep your password" />
        </div>
        <div className="flex justify-end"><Button type="submit" loading={m.isPending}>Save profile</Button></div>
      </form>
    </Card>
  );
}

// ---------------------------------------------------------------- users
function UsersAdmin() {
  const { user: me } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ email: "", full_name: "", password: "", role: "reviewer" });
  const { data, isLoading } = useQuery({ queryKey: ["users"], queryFn: () => api("/users") });
  const create = useMutation({
    mutationFn: () => api("/users", { body: form }),
    onSuccess: () => {
      toast("success", "User created");
      setOpen(false);
      setForm({ email: "", full_name: "", password: "", role: "reviewer" });
      qc.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (e: Error) => toast("error", e.message),
  });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: any }) => api(`/users/${id}`, { method: "PATCH", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
    onError: (e: Error) => toast("error", e.message),
  });
  return (
    <Card className="overflow-hidden">
      <CardHeader icon={<Users className="h-4 w-4" />} title="Users & roles" subtitle="Admin: everything · Reviewer: upload, correct, review · Viewer: read-only" action={<Button size="sm" icon={<UserPlus className="h-4 w-4" />} onClick={() => setOpen(true)}>Add user</Button>} />
      {isLoading ? <div className="p-5"><Skeleton className="h-24" /></div> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px]">
            <thead><tr>{["User", "Role", "Status", "Last login", ""].map((h) => <th key={h} className="table-head">{h}</th>)}</tr></thead>
            <tbody>
              {data.map((u: any) => (
                <tr key={u.id}>
                  <td className="table-cell"><div className="font-semibold">{u.full_name}</div><div className="text-xs text-muted">{u.email}</div></td>
                  <td className="table-cell w-44">
                    <select className="input !py-1.5" value={u.role} disabled={u.id === me?.id} onChange={(e) => update.mutate({ id: u.id, body: { role: e.target.value } })}>
                      <option value="admin">Admin</option><option value="reviewer">Reviewer</option><option value="viewer">Viewer</option>
                    </select>
                  </td>
                  <td className="table-cell">{u.is_active ? <Badge tone="green">Active</Badge> : <Badge tone="gray">Disabled</Badge>}</td>
                  <td className="table-cell text-sm text-muted">{dateTime(u.last_login_at)}</td>
                  <td className="table-cell text-right">
                    {u.id !== me?.id && (
                      <Button size="sm" variant="ghost" onClick={() => update.mutate({ id: u.id, body: { is_active: !u.is_active } })}>
                        {u.is_active ? "Disable" : "Enable"}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Modal open={open} onClose={() => setOpen(false)} title="Add user" footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button loading={create.isPending} onClick={() => create.mutate()}>Create user</Button></>}>
        <div className="space-y-4">
          <Input label="Full name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          <Input label="Email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <Input label="Temporary password" type="password" minLength={8} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} hint="At least 8 characters" />
          <Select label="Role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            <option value="viewer">Viewer</option><option value="reviewer">Reviewer</option><option value="admin">Admin</option>
          </Select>
        </div>
      </Modal>
    </Card>
  );
}

// ---------------------------------------------------------------- system / demo / audit
function SystemTab() {
  const { can } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [confirmClear, setConfirmClear] = useState(false);
  const { data: sys } = useQuery({ queryKey: ["system"], queryFn: () => api("/settings/system") });
  const load = useMutation({
    mutationFn: () => api("/demo/load", { method: "POST" }),
    onSuccess: (r: any) => { toast("success", `${r.documents} sample documents queued`); qc.invalidateQueries(); },
    onError: (e: Error) => toast("error", e.message),
  });
  const clear = useMutation({
    mutationFn: () => api("/demo", { method: "DELETE" }),
    onSuccess: (r: any) => { toast("success", `Removed ${r.deleted} demo documents`); setConfirmClear(false); qc.invalidateQueries(); },
    onError: (e: Error) => toast("error", e.message),
  });
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader icon={<Database className="h-4 w-4" />} title="Processing configuration" subtitle="Set via environment variables (.env)" />
        <dl className="divide-y divide-line text-sm">
          {sys && [
            ["Environment", sys.app_env],
            ["OCR engine", <span key="o" className="flex items-center gap-2">{sys.ocr_engine} {sys.ocr_available ? <Badge tone="green">available</Badge> : <Badge tone="red">not installed</Badge>}</span>],
            ["Embedding model (local)", <span key="e" className="font-mono text-xs">{sys.embedding_model}</span>],
            ["Max upload size", `${sys.max_upload_mb} MB`],
            ["Money tolerance", sys.validation_tolerance],
            ["Tax tolerance", `${sys.tax_tolerance_pct}%`],
            ["Low-confidence threshold", `${Math.round(sys.low_confidence_threshold * 100)}%`],
            ["Allowed formats", sys.allowed_extensions.join(" ")],
          ].map(([k, v]) => (
            <div key={String(k)} className="flex items-center justify-between gap-4 px-6 py-3"><dt className="text-muted">{k}</dt><dd className="text-right">{v}</dd></div>
          ))}
        </dl>
      </Card>
      {can("admin") && (
        <Card className="h-fit">
          <CardHeader icon={<Sparkles className="h-4 w-4" />} title="Demo data" subtitle="Generated sample invoices processed by the real pipeline, always labelled 'Demo'." />
          <div className="space-y-3 p-6 text-sm text-ink-soft">
            <p>Loads 12 sample files (PDF invoices, a duplicate, an Excel export and a CSV register) including deliberate tax and total errors, so you can explore validation and cross-verification.</p>
            <div className="flex flex-wrap gap-2 pt-2">
              <Button onClick={() => load.mutate()} loading={load.isPending} icon={<Sparkles className="h-4 w-4" />}>Load sample data</Button>
              <Button variant="secondary" onClick={() => setConfirmClear(true)} icon={<Trash2 className="h-4 w-4" />}>Remove demo data</Button>
            </div>
          </div>
        </Card>
      )}
      <ConfirmDialog open={confirmClear} onClose={() => setConfirmClear(false)} onConfirm={() => clear.mutate()} loading={clear.isPending} danger title="Remove all demo documents?" confirmText="Remove" message="All documents marked as Demo and their extracted data will be deleted. Real documents are not affected." />
    </div>
  );
}

function AuditLog() {
  const [page, setPage] = useState(1);
  const { data, isLoading, error } = useQuery({ queryKey: ["audit", page], queryFn: () => api("/audit-logs", { query: { page, page_size: 25 } }) });
  return (
    <Card className="overflow-hidden">
      <CardHeader icon={<ScrollText className="h-4 w-4" />} title="Audit log" subtitle="Security-relevant actions: logins, uploads, corrections, reviews, settings and deletions" />
      <ErrorBox error={error} />
      {isLoading ? <div className="p-5"><Skeleton className="h-40" /></div> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[800px]">
            <thead><tr>{["Time", "User", "Action", "Entity", "Details"].map((h) => <th key={h} className="table-head">{h}</th>)}</tr></thead>
            <tbody>
              {data?.items.map((a: any) => (
                <tr key={a.id}>
                  <td className="table-cell whitespace-nowrap text-xs text-muted">{dateTime(a.created_at)}</td>
                  <td className="table-cell text-sm">{a.user_email || "—"}</td>
                  <td className="table-cell"><Badge tone={a.action.includes("failed") || a.action.includes("deleted") ? "red" : "gray"}>{a.action}</Badge></td>
                  <td className="table-cell text-xs text-muted">{a.entity_type ? `${label(a.entity_type)} ${String(a.entity_id).slice(0, 8)}` : "—"}</td>
                  <td className="table-cell max-w-[360px] truncate font-mono text-[11px] text-muted" title={JSON.stringify(a.details)}>{Object.keys(a.details || {}).length ? JSON.stringify(a.details) : ""}</td>
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

type T = "ai" | "profile" | "users" | "system" | "audit";

export default function SettingsPage() {
  const { can } = useAuth();
  const [tab, setTab] = useState<T>("ai");
  const tabs: { key: T; label: any }[] = [
    { key: "ai", label: <><Bot className="h-4 w-4" /> AI Engine</> },
    { key: "profile", label: <><KeyRound className="h-4 w-4" /> Profile</> },
    ...(can("admin") ? [{ key: "users" as T, label: <><Users className="h-4 w-4" /> Users</> }] : []),
    { key: "system", label: <><Database className="h-4 w-4" /> System</> },
    ...(can("admin") ? [{ key: "audit" as T, label: <><ScrollText className="h-4 w-4" /> Audit log</> }] : []),
  ];
  return (
    <div className="animate-fade-in">
      <PageHeader title="Settings" subtitle="AI engine, users, profile and system configuration." />
      <div className="mb-6"><Tabs value={tab} onChange={setTab} tabs={tabs} /></div>
      {tab === "ai" && <AIEngine />}
      {tab === "profile" && <Profile />}
      {tab === "users" && <UsersAdmin />}
      {tab === "system" && <SystemTab />}
      {tab === "audit" && <AuditLog />}
    </div>
  );
}
