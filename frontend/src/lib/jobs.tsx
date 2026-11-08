/** Real-time processing updates over Server-Sent Events, shared app-wide. */
import { useQueryClient } from "@tanstack/react-query";
import { createContext, ReactNode, useContext, useEffect, useRef, useState } from "react";
import { getAccessToken, onTokenChange, refreshToken } from "./api";

export interface JobEvent {
  type: "job";
  job_id: string;
  document_id: string;
  document_name: string;
  stage: string;
  stage_status: string;
  job_status: string;
  progress: number;
  message?: string | null;
  document_status: string;
}

interface JobsState {
  live: Record<string, JobEvent>; // latest event per job
  connected: boolean;
  activeCount: number;
}

const Ctx = createContext<JobsState>({ live: {}, connected: false, activeCount: 0 });

export function JobStreamProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [live, setLive] = useState<Record<string, JobEvent>>({});
  const [connected, setConnected] = useState(false);
  const [token, setToken] = useState(getAccessToken());
  const pending = useRef<number | null>(null);

  useEffect(() => {
    const off = onTokenChange(setToken);
    return () => {
      off();
    };
  }, []);

  useEffect(() => {
    if (!token) return;
    const es = new EventSource(`/api/v1/jobs/stream?token=${encodeURIComponent(token)}`);
    es.onopen = () => setConnected(true);
    es.addEventListener("job", (e) => {
      const ev: JobEvent = JSON.parse((e as MessageEvent).data);
      setLive((prev) => ({ ...prev, [ev.job_id]: ev }));
      // batch cache invalidation so a burst of stage events causes one refetch
      if (pending.current) window.clearTimeout(pending.current);
      pending.current = window.setTimeout(() => {
        ["jobs", "documents", "document", "analytics", "invoices", "validation", "recent-docs", "job-counts"].forEach(
          (k) => qc.invalidateQueries({ queryKey: [k] }),
        );
      }, 400);
    });
    es.onerror = () => {
      setConnected(false);
      es.close();
      // the access token may have expired: refresh, which re-creates the stream via onTokenChange
      window.setTimeout(() => refreshToken(), 4000);
    };
    return () => es.close();
  }, [token, qc]);

  const activeCount = Object.values(live).filter((e) => ["queued", "running"].includes(e.job_status)).length;
  return <Ctx.Provider value={{ live, connected, activeCount }}>{children}</Ctx.Provider>;
}

export const useJobStream = () => useContext(Ctx);
