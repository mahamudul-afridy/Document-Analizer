import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Check, ListChecks, Loader2, RotateCcw, X } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Button, Card, EmptyState, PageHeader, Pagination, Skeleton, StatusBadge, Tabs, useToast } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { dateTime, label } from "../lib/format";
import { useJobStream } from "../lib/jobs";

const STAGES = [
  ["uploaded", "Uploaded"],
  ["classification", "Classification"],
  ["text_extraction", "Text / OCR"],
  ["ai_extraction", "AI Extraction"],
  ["validation", "Validation"],
  ["cross_verification", "Cross-check"],
  ["completed", "Completed"],
] as const;

function Timeline({ job, liveStage, liveStatus }: { job: any; liveStage?: string; liveStatus?: string }) {
  const doneStages = new Set(job.history.filter((h: any) => h.status === "completed").map((h: any) => h.stage));
  const status = liveStatus || job.status;
  const current = liveStage || job.current_stage;
  const failedStage = status === "failed" ? current : null;
  return (
    <div className="flex items-center">
      {STAGES.map(([key, text], i) => {
        const done = doneStages.has(key) || status === "completed";
        const active = !done && current === key && status === "running";
        const failed = failedStage === key;
        return (
          <div key={key} className="flex flex-1 items-center last:flex-none">
            <div className="flex flex-col items-center gap-1.5" title={text}>
              <div
                className={clsx(
                  "flex h-7 w-7 items-center justify-center rounded-full border-2 text-[11px] font-bold transition",
                  done && "border-brand-800 bg-brand-800 text-white",
                  active && "border-accent-500 bg-accent-50 text-accent-600",
                  failed && "border-bad bg-bad text-white",
                  !done && !active && !failed && "border-line bg-white text-muted",
                )}
              >
                {done ? <Check className="h-3.5 w-3.5" /> : failed ? <X className="h-3.5 w-3.5" /> : active ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : i + 1}
              </div>
              <span className={clsx("hidden whitespace-nowrap text-[10px] font-medium md:block", done || active ? "text-ink-soft" : "text-muted")}>{text}</span>
            </div>
            {i < STAGES.length - 1 && <div className={clsx("mx-1 h-0.5 flex-1 rounded md:mb-5", done ? "bg-brand-gradient" : "bg-line")} />}
          </div>
        );
      })}
    </div>
  );
}

export default function Queue() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") || "";
  const [page, setPage] = useState(1);
  const { can } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const { live } = useJobStream();

  const { data, isLoading } = useQuery({
    queryKey: ["jobs", status, page],
    queryFn: () => api("/jobs", { query: { status, page, page_size: 20 } }),
    refetchInterval: 15000,
  });
  const { data: counts } = useQuery({ queryKey: ["job-counts"], queryFn: () => api("/jobs/counts") });

  const retry = useMutation({
    mutationFn: (id: string) => api(`/jobs/${id}/retry`, { method: "POST" }),
    onSuccess: () => {
      toast("success", "Job re-queued");
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e: Error) => toast("error", e.message),
  });
  const cancel = useMutation({
    mutationFn: (id: string) => api(`/jobs/${id}/cancel`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
    onError: (e: Error) => toast("error", e.message),
  });
  const retryAll = useMutation({
    mutationFn: () => api("/jobs/retry-failed", { method: "POST" }),
    onSuccess: (r: any) => {
      toast("success", `${r.retried} failed document(s) re-queued`);
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  const tabs = [
    { key: "", label: "All" },
    { key: "queued,running", label: "Active", count: counts ? counts.queued + counts.running : undefined },
    { key: "completed", label: "Completed", count: counts?.completed },
    { key: "failed", label: "Failed", count: counts?.failed },
    { key: "cancelled", label: "Cancelled", count: counts?.cancelled },
  ];

  return (
    <div className="animate-fade-in">
      <PageHeader
        title="Processing Queue"
        subtitle="Monitor background processing in real time."
        actions={
          can("reviewer") && counts?.failed ? (
            <Button variant="secondary" icon={<RotateCcw className="h-4 w-4" />} loading={retryAll.isPending} onClick={() => retryAll.mutate()}>
              Retry all failed
            </Button>
          ) : null
        }
      />
      <div className="mb-4">
        <Tabs
          tabs={tabs}
          value={status}
          onChange={(v) => {
            setPage(1);
            setParams(v ? { status: v } : {});
          }}
        />
      </div>
      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="space-y-3 p-5">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20" />)}</div>
        ) : !data?.items.length ? (
          <EmptyState icon={<ListChecks className="h-6 w-6" />} title="No jobs here" description="Upload documents to start processing." action={<Link to="/upload"><Button>Upload documents</Button></Link>} />
        ) : (
          <ul className="divide-y divide-line">
            {data.items.map((job: any) => {
              const ev = live[job.id];
              const st = ev?.job_status || job.status;
              const duration =
                job.started_at && job.finished_at ? ((new Date(job.finished_at).getTime() - new Date(job.started_at).getTime()) / 1000).toFixed(1) + "s" : null;
              return (
                <li key={job.id} className="grid gap-4 px-5 py-5 lg:grid-cols-[minmax(220px,1fr)_minmax(360px,2fr)_auto] lg:items-center">
                  <div className="min-w-0">
                    <Link to={`/documents/${job.document_id}`} className="block truncate font-semibold hover:text-accent-600">
                      {job.document_name}
                    </Link>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
                      <StatusBadge status={st} />
                      <span>{dateTime(job.created_at)}</span>
                      {duration && <span>· {duration}</span>}
                      {job.attempts > 1 && <span>· attempt {job.attempts}</span>}
                    </div>
                    {(ev?.job_status === "failed" ? ev.message : job.error) && (
                      <p className="mt-1.5 line-clamp-2 text-xs text-bad" title={job.error || ev?.message || ""}>{ev?.message || job.error}</p>
                    )}
                  </div>
                  <Timeline job={job} liveStage={ev?.stage} liveStatus={ev?.job_status} />
                  <div className="flex justify-end gap-2">
                    {can("reviewer") && ["failed", "cancelled"].includes(st) && (
                      <Button size="sm" variant="secondary" icon={<RotateCcw className="h-3.5 w-3.5" />} onClick={() => retry.mutate(job.id)} loading={retry.isPending && retry.variables === job.id}>
                        Retry
                      </Button>
                    )}
                    {can("reviewer") && st === "queued" && (
                      <Button size="sm" variant="ghost" onClick={() => cancel.mutate(job.id)}>Cancel</Button>
                    )}
                    {st === "completed" && (
                      <Link to={`/documents/${job.document_id}`}>
                        <Button size="sm" variant="soft">View results</Button>
                      </Link>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        {data && <Pagination page={page} pageSize={20} total={data.total} onPage={setPage} />}
      </Card>
      <p className="mt-3 text-xs text-muted">Live updates stream from the server; stage history is stored for every job ({label("processing_history")}).</p>
    </div>
  );
}
