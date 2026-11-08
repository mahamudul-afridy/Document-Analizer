import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import {
  CheckCircle2,
  FileImage,
  FileSpreadsheet,
  FileText,
  Loader2,
  RotateCcw,
  Trash2,
  UploadCloud,
  XCircle,
} from "lucide-react";
import { DragEvent, useCallback, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Button, Card, CardHeader, PageHeader } from "../components/ui";
import { api, uploadFile } from "../lib/api";
import { useAuth } from "../lib/auth";
import { bytes, label } from "../lib/format";
import { useJobStream } from "../lib/jobs";

const EXT = [".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".xlsx", ".xls", ".csv"];
const STAGES = ["uploaded", "classification", "text_extraction", "ai_extraction", "validation", "cross_verification", "completed"];

type Status = "ready" | "invalid" | "uploading" | "uploaded" | "duplicate" | "error";
interface Item {
  id: string;
  file: File;
  status: Status;
  progress: number;
  error?: string;
  documentId?: string;
  jobId?: string;
  duplicateOf?: string;
}

function iconFor(name: string) {
  const ext = name.toLowerCase().split(".").pop() || "";
  if (["xlsx", "xls", "csv"].includes(ext)) return <FileSpreadsheet className="h-5 w-5" />;
  if (["jpg", "jpeg", "png", "tif", "tiff"].includes(ext)) return <FileImage className="h-5 w-5" />;
  return <FileText className="h-5 w-5" />;
}

export default function Upload() {
  const { can } = useAuth();
  const { live } = useJobStream();
  const { data: sys } = useQuery({ queryKey: ["system"], queryFn: () => api("/settings/system") });
  const maxMb = sys?.max_upload_mb ?? 25;
  const [items, setItems] = useState<Item[]>([]);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const validate = useCallback(
    (f: File): string | undefined => {
      const ext = "." + (f.name.toLowerCase().split(".").pop() || "");
      if (!EXT.includes(ext)) return `Unsupported type ${ext}`;
      if (f.size === 0) return "File is empty";
      if (f.size > maxMb * 1024 * 1024) return `Larger than ${maxMb} MB`;
      return undefined;
    },
    [maxMb],
  );

  const add = (files: FileList | File[]) => {
    const next = Array.from(files).map((file) => {
      const error = validate(file);
      return { id: `${file.name}-${file.size}-${Math.random()}`, file, status: (error ? "invalid" : "ready") as Status, progress: 0, error };
    });
    setItems((cur) => [...cur, ...next]);
  };

  const patch = (id: string, p: Partial<Item>) => setItems((cur) => cur.map((i) => (i.id === id ? { ...i, ...p } : i)));

  const uploadOne = async (it: Item, force = false) => {
    patch(it.id, { status: "uploading", progress: 0, error: undefined });
    try {
      const [r] = await uploadFile(it.file, (p) => patch(it.id, { progress: p }), force);
      if (r.ok) patch(it.id, { status: "uploaded", progress: 100, documentId: r.document_id, jobId: r.job_id });
      else if (r.duplicate_of) patch(it.id, { status: "duplicate", error: r.error, duplicateOf: r.duplicate_of });
      else patch(it.id, { status: "error", error: r.error });
    } catch (e: any) {
      patch(it.id, { status: "error", error: e.message });
    }
  };

  const uploadAll = async () => {
    setBusy(true);
    const queue = items.filter((i) => i.status === "ready" || i.status === "error");
    const workers = Array.from({ length: Math.min(3, queue.length) }, async () => {
      while (queue.length) {
        const it = queue.shift()!;
        await uploadOne(it);
      }
    });
    await Promise.all(workers);
    setBusy(false);
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDrag(false);
    if (e.dataTransfer.files?.length) add(e.dataTransfer.files);
  };

  const ready = items.filter((i) => i.status === "ready").length;
  const failed = items.filter((i) => i.status === "error").length;
  const done = items.filter((i) => i.status === "uploaded").length;

  if (!can("reviewer"))
    return (
      <Card className="p-8 text-center text-muted">Your role (viewer) can't upload documents. Ask an administrator for reviewer access.</Card>
    );

  return (
    <div className="animate-fade-in">
      <PageHeader title="Upload Documents" subtitle="Add invoices and financial documents for automated extraction and verification." />
      <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
            className={clsx(
              "card flex cursor-pointer flex-col items-center justify-center border-2 border-dashed px-6 py-14 text-center transition",
              drag ? "border-brand-500 bg-brand-50" : "border-brand-200 hover:border-brand-400 hover:bg-brand-50/50",
            )}
          >
            <div className={clsx("mb-4 rounded-2xl p-4 transition", drag ? "bg-brand-800 text-white" : "bg-brand-100 text-brand-800")}>
              <UploadCloud className="h-8 w-8" />
            </div>
            <h3 className="font-sans text-lg font-semibold">Drag & drop files here</h3>
            <p className="mt-1 text-sm text-muted">
              or <span className="font-semibold text-brand-700 underline-offset-2 hover:underline">browse your computer</span>. Multiple files supported.
            </p>
            <div className="mt-5 flex flex-wrap justify-center gap-1.5">
              {["PDF", "JPG", "PNG", "TIFF", "XLSX", "XLS", "CSV"].map((t) => (
                <Badge key={t} tone="gray">{t}</Badge>
              ))}
            </div>
            <p className="mt-3 text-xs text-muted">Max {maxMb} MB per file</p>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept={EXT.join(",")}
              className="hidden"
              onChange={(e) => {
                if (e.target.files) add(e.target.files);
                e.target.value = "";
              }}
            />
          </div>

          {items.length > 0 && (
            <Card className="overflow-hidden">
              <CardHeader
                title={`${items.length} file${items.length > 1 ? "s" : ""}`}
                subtitle={`${done} uploaded · ${ready} ready${failed ? ` · ${failed} failed` : ""}`}
                action={
                  <div className="flex gap-2">
                    <Button variant="ghost" size="sm" onClick={() => setItems((c) => c.filter((i) => i.status === "uploading"))}>
                      Clear
                    </Button>
                    {failed > 0 && (
                      <Button variant="secondary" size="sm" icon={<RotateCcw className="h-3.5 w-3.5" />} onClick={uploadAll} disabled={busy}>
                        Retry failed
                      </Button>
                    )}
                    <Button size="sm" onClick={uploadAll} loading={busy} disabled={!ready && !failed} icon={<UploadCloud className="h-3.5 w-3.5" />}>
                      Upload {ready ? ready : ""}
                    </Button>
                  </div>
                }
              />
              <ul className="divide-y divide-line">
                {items.map((it) => {
                  const ev = it.jobId ? live[it.jobId] : undefined;
                  const stageIdx = ev ? STAGES.indexOf(ev.stage) : 0;
                  return (
                    <li key={it.id} className="flex items-center gap-4 px-5 py-4">
                      <div className={clsx("rounded-xl p-2.5", it.status === "invalid" || it.status === "error" ? "bg-bad-bg text-bad" : "bg-brand-50 text-brand-700")}>
                        {iconFor(it.file.name)}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="truncate text-sm font-semibold">{it.file.name}</span>
                          <span className="shrink-0 text-xs text-muted">{bytes(it.file.size)}</span>
                        </div>
                        {it.status === "uploading" && (
                          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-line">
                            <div className="h-full rounded-full bg-brand-gradient transition-all" style={{ width: `${it.progress}%` }} />
                          </div>
                        )}
                        {it.status === "uploaded" && (
                          <div className="mt-1.5">
                            <div className="flex gap-1">
                              {STAGES.map((s, i) => (
                                <div
                                  key={s}
                                  title={label(s)}
                                  className={clsx(
                                    "h-1.5 flex-1 rounded-full",
                                    ev?.job_status === "failed" && i === stageIdx ? "bg-bad" : i <= stageIdx || ev?.job_status === "completed" ? "bg-brand-600" : "bg-line",
                                  )}
                                />
                              ))}
                            </div>
                            <div className="mt-1 text-xs text-muted">
                              {ev?.job_status === "completed" ? "Processing completed" : ev?.job_status === "failed" ? `Failed at ${label(ev.stage)}` : ev ? `${label(ev.stage)}…` : "Queued for processing…"}
                            </div>
                          </div>
                        )}
                        {it.error && <div className="mt-1 text-xs text-bad">{it.error}</div>}
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        {it.status === "uploading" && <Loader2 className="h-5 w-5 animate-spin text-brand-600" />}
                        {it.status === "uploaded" && ev?.job_status === "completed" && <CheckCircle2 className="h-5 w-5 text-ok" />}
                        {it.status === "uploaded" && it.documentId && (
                          <Link to={`/documents/${it.documentId}`} className="text-xs font-semibold text-accent-600 hover:underline">
                            Open
                          </Link>
                        )}
                        {it.status === "duplicate" && (
                          <>
                            <Link to={`/documents/${it.duplicateOf}`} className="text-xs font-semibold text-accent-600 hover:underline">View existing</Link>
                            <Button size="sm" variant="secondary" onClick={() => uploadOne(it, true)}>Upload anyway</Button>
                          </>
                        )}
                        {it.status === "error" && (
                          <Button size="sm" variant="secondary" icon={<RotateCcw className="h-3.5 w-3.5" />} onClick={() => uploadOne(it)}>
                            Retry
                          </Button>
                        )}
                        {it.status === "invalid" && <XCircle className="h-5 w-5 text-bad" />}
                        {it.status !== "uploading" && (
                          <button onClick={() => setItems((c) => c.filter((x) => x.id !== it.id))} className="rounded-lg p-1.5 text-muted hover:bg-cream hover:text-bad" aria-label="Remove">
                            <Trash2 className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </Card>
          )}
        </div>

        <div className="space-y-6">
          <Card className="p-6">
            <h3 className="font-sans text-base font-semibold">What happens after upload</h3>
            <ol className="mt-4 space-y-3">
              {STAGES.map((s, i) => (
                <li key={s} className="flex items-center gap-3 text-sm">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-100 text-xs font-bold text-brand-800">{i + 1}</span>
                  {s === "uploaded" ? "File Uploaded" : s === "text_extraction" ? "Text Extraction / OCR" : s === "ai_extraction" ? "AI Information Extraction" : s === "validation" ? "Data Validation" : s === "cross_verification" ? "Cross-Document Verification" : s === "completed" ? "Processing Completed" : label(s)}
                </li>
              ))}
            </ol>
            <Link to="/queue" className="mt-5 inline-flex text-sm font-semibold text-accent-600 hover:underline">
              Open processing queue →
            </Link>
          </Card>
          <Card className="p-6 text-sm text-ink-soft">
            <h3 className="mb-2 font-sans text-base font-semibold text-ink">Tips for best results</h3>
            <ul className="list-disc space-y-1.5 pl-5">
              <li>Scans at 200–300 DPI give the most accurate OCR.</li>
              <li>English-language documents are supported.</li>
              <li>Identical files are detected automatically and not processed twice.</li>
              <li>Upload the Excel or CSV export of an invoice too, to cross-verify it against the PDF.</li>
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
