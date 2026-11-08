/** API client. Access token lives in memory only; the refresh token is an httpOnly cookie. */
const BASE = "/api/v1";
let accessToken: string | null = null;
let refreshing: Promise<boolean> | null = null;
let onAuthLost: (() => void) | null = null;
const tokenListeners = new Set<(t: string | null) => void>();

export class ApiError extends Error {
  status: number;
  errors?: { field: string; message: string }[];
  constructor(status: number, message: string, errors?: { field: string; message: string }[]) {
    super(message);
    this.status = status;
    this.errors = errors;
  }
}

export function setAccessToken(t: string | null) {
  accessToken = t;
  tokenListeners.forEach((fn) => fn(t));
}
export const getAccessToken = () => accessToken;
export function onTokenChange(fn: (t: string | null) => void) {
  tokenListeners.add(fn);
  return () => tokenListeners.delete(fn);
}
export function setAuthLostHandler(fn: () => void) {
  onAuthLost = fn;
}

export async function refreshToken(): Promise<boolean> {
  if (!refreshing) {
    refreshing = fetch(`${BASE}/auth/refresh`, { method: "POST", credentials: "include" })
      .then(async (r) => {
        if (!r.ok) return false;
        const data = await r.json();
        setAccessToken(data.access_token);
        return true;
      })
      .catch(() => false)
      .finally(() => {
        setTimeout(() => (refreshing = null), 0);
      });
  }
  return refreshing;
}

type Query = Record<string, string | number | boolean | null | undefined>;
export interface RequestOpts {
  method?: string;
  body?: unknown;
  form?: FormData;
  query?: Query;
  raw?: boolean;
}

export function qs(query?: Query) {
  if (!query) return "";
  const p = new URLSearchParams();
  Object.entries(query).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : "";
}

export async function api<T = any>(path: string, opts: RequestOpts = {}, retried = false): Promise<T> {
  const headers: Record<string, string> = {};
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(`${BASE}${path}${qs(opts.query)}`, {
    method: opts.method || (body ? "POST" : "GET"),
    headers,
    body,
    credentials: "include",
  });
  if (res.status === 401 && !retried && !path.startsWith("/auth/")) {
    if (await refreshToken()) return api<T>(path, opts, true);
    onAuthLost?.();
  }
  if (!res.ok) {
    let msg = res.statusText;
    let errors;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
      errors = j.errors;
      if (errors?.length) msg = errors.map((e: { field: string; message: string }) => `${e.field ? e.field + ": " : ""}${e.message}`).join("; ");
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, msg || `Request failed (${res.status})`, errors);
  }
  if (opts.raw) return res as unknown as T;
  const ct = res.headers.get("content-type") || "";
  return (ct.includes("application/json") ? res.json() : res.text()) as Promise<T>;
}

/** Fetch an authenticated binary (images, downloads) as a Blob. */
export async function apiBlob(path: string, query?: Query): Promise<Blob> {
  const res = await api<Response>(path, { raw: true, query });
  return res.blob();
}

export async function download(path: string, filename: string, query?: Query) {
  const blob = await apiBlob(path, query);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

/** Upload one file with progress (XHR gives upload progress events; fetch does not). */
export function uploadFile(file: File, onProgress: (pct: number) => void, force = false): Promise<any[]> {
  const send = (token: string | null) =>
    new Promise<{ status: number; body: any }>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${BASE}/documents/upload${force ? "?force=true" : ""}`);
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.withCredentials = true;
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
      xhr.onload = () => {
        let body: any = null;
        try {
          body = JSON.parse(xhr.responseText);
        } catch {
          body = { detail: xhr.responseText };
        }
        resolve({ status: xhr.status, body });
      };
      xhr.onerror = () => reject(new ApiError(0, "Network error during upload"));
      const fd = new FormData();
      fd.append("files", file);
      xhr.send(fd);
    });
  return send(accessToken).then(async (r) => {
    if (r.status === 401 && (await refreshToken())) r = await send(accessToken);
    if (r.status >= 400) throw new ApiError(r.status, r.body?.detail || "Upload failed");
    return r.body;
  });
}
