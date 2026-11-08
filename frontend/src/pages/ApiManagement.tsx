import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Check, Copy, KeyRound, Plus, ShieldAlert, Trash2 } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, CardHeader, ConfirmDialog, EmptyState, Input, Modal, PageHeader, Skeleton, useToast } from "../components/ui";
import { api } from "../lib/api";
import { dateTime, timeAgo } from "../lib/format";

function CopyBtn({ text }: { text: string }) {
  const [ok, setOk] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        setOk(true);
        setTimeout(() => setOk(false), 1500);
      }}
      className="rounded-lg p-1.5 text-muted hover:bg-white hover:text-accent-600"
      aria-label="Copy"
    >
      {ok ? <Check className="h-4 w-4 text-ok" /> : <Copy className="h-4 w-4" />}
    </button>
  );
}

export default function ApiManagement() {
  const qc = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [created, setCreated] = useState<any>(null);
  const [revoke, setRevoke] = useState<any>(null);
  const { data, isLoading } = useQuery({ queryKey: ["api-keys"], queryFn: () => api("/api-keys") });
  const create = useMutation({
    mutationFn: () => api("/api-keys", { body: { name } }),
    onSuccess: (k) => {
      setCreated(k);
      setOpen(false);
      setName("");
      qc.invalidateQueries({ queryKey: ["api-keys"] });
    },
    onError: (e: Error) => toast("error", e.message),
  });
  const del = useMutation({
    mutationFn: (id: string) => api(`/api-keys/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast("success", "API key revoked");
      setRevoke(null);
      qc.invalidateQueries({ queryKey: ["api-keys"] });
    },
  });
  const origin = window.location.origin;
  const examples = [
    { title: "Upload a document", code: `curl -X POST ${origin}/api/v1/documents/upload \\\n  -H "X-API-Key: $DOCUMIND_KEY" \\\n  -F "files=@invoice.pdf"` },
    { title: "Check processing status", code: `curl ${origin}/api/v1/jobs/<job_id> \\\n  -H "X-API-Key: $DOCUMIND_KEY"` },
    { title: "Get extracted invoices", code: `curl "${origin}/api/v1/invoices?status=failed&page_size=50" \\\n  -H "X-API-Key: $DOCUMIND_KEY"` },
    { title: "Natural-language search", code: `curl -X POST ${origin}/api/v1/search/semantic \\\n  -H "X-API-Key: $DOCUMIND_KEY" -H "Content-Type: application/json" \\\n  -d '{"query": "invoices from ABC Corporation above $5,000"}'` },
  ];

  return (
    <div className="animate-fade-in">
      <PageHeader
        title="API Management"
        subtitle="Integrate DocuMind with your systems using the REST API."
        actions={
          <>
            <a href="/api/docs" target="_blank" rel="noreferrer"><Button variant="secondary" icon={<BookOpen className="h-4 w-4" />}>API documentation</Button></a>
            <Button icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)}>New API key</Button>
          </>
        }
      />
      <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <Card className="overflow-hidden">
          <CardHeader title="Your API keys" subtitle="Keys act with your permissions. Keep them secret." icon={<KeyRound className="h-4 w-4" />} />
          {isLoading ? (
            <div className="p-5"><Skeleton className="h-24" /></div>
          ) : !data?.length ? (
            <EmptyState icon={<KeyRound className="h-6 w-6" />} title="No API keys yet" description="Create a key to call the API from scripts or other systems." action={<Button onClick={() => setOpen(true)} icon={<Plus className="h-4 w-4" />}>Create key</Button>} />
          ) : (
            <ul className="divide-y divide-line">
              {data.map((k: any) => (
                <li key={k.id} className="flex items-center gap-4 px-5 py-4">
                  <div className="rounded-xl bg-brand-50 p-2.5 text-brand-700"><KeyRound className="h-4 w-4" /></div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-semibold">{k.name}</span>
                      {k.revoked_at ? <Badge tone="red">Revoked</Badge> : <Badge tone="green">Active</Badge>}
                    </div>
                    <div className="mt-0.5 text-xs text-muted">
                      <span className="font-mono">{k.key_prefix}…</span> · created {dateTime(k.created_at)} · {k.last_used_at ? `last used ${timeAgo(k.last_used_at)}` : "never used"}
                    </div>
                  </div>
                  {!k.revoked_at && (
                    <Button size="sm" variant="ghost" className="text-bad hover:bg-bad-bg hover:text-bad" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={() => setRevoke(k)}>
                      Revoke
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card>
          <CardHeader title="Quick start" subtitle="Authenticate with the X-API-Key header (or a Bearer token)." />
          <div className="space-y-4 p-5">
            {examples.map((ex) => (
              <div key={ex.title}>
                <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">{ex.title}</div>
                <div className="relative rounded-xl bg-ink">
                  <pre className="overflow-x-auto p-4 pr-10 font-mono text-xs leading-relaxed text-brand-100 scrollbar-thin">{ex.code}</pre>
                  <div className="absolute right-2 top-2"><CopyBtn text={ex.code} /></div>
                </div>
              </div>
            ))}
            <p className="text-xs text-muted">Rate limits apply per client. Full interactive reference: <a className="font-semibold text-accent-600 hover:underline" href="/api/docs" target="_blank" rel="noreferrer">/api/docs</a></p>
          </div>
        </Card>
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title="Create API key" footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button onClick={() => create.mutate()} loading={create.isPending} disabled={!name.trim()}>Create</Button></>}>
        <Input label="Key name" placeholder="e.g. Accounting system integration" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
      </Modal>

      <Modal open={!!created} onClose={() => setCreated(null)} title="API key created" footer={<Button onClick={() => setCreated(null)}>I've saved it</Button>}>
        <div className="mb-4 flex items-start gap-2 rounded-xl bg-warn-bg px-4 py-3 text-sm text-warn">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" /> Copy this key now. For security it is only shown once.
        </div>
        <div className="flex items-center gap-2 rounded-xl border border-line bg-cream px-3 py-2">
          <code className="flex-1 break-all font-mono text-sm">{created?.key}</code>
          <CopyBtn text={created?.key || ""} />
        </div>
      </Modal>

      <ConfirmDialog open={!!revoke} onClose={() => setRevoke(null)} onConfirm={() => del.mutate(revoke.id)} loading={del.isPending} danger title="Revoke API key?" confirmText="Revoke" message={<>Applications using <span className="font-semibold">{revoke?.name}</span> will stop working immediately.</>} />
    </div>
  );
}
