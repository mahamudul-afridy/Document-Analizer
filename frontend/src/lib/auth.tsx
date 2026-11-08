import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { api, refreshToken, setAccessToken, setAuthLostHandler } from "./api";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: "admin" | "reviewer" | "viewer";
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  needsSetup: boolean;
  login: (email: string, password: string) => Promise<void>;
  setup: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => Promise<void>;
  setUser: (u: User) => void;
  can: (role: "reviewer" | "admin") => boolean;
}

const Ctx = createContext<AuthState | null>(null);
const RANK = { viewer: 0, reviewer: 1, admin: 2 } as const;

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [needsSetup, setNeedsSetup] = useState(false);

  useEffect(() => {
    setAuthLostHandler(() => {
      setAccessToken(null);
      setUser(null);
    });
    (async () => {
      try {
        const s = await api<{ needs_setup: boolean }>("/auth/setup-status");
        setNeedsSetup(s.needs_setup);
        if (!s.needs_setup && (await refreshToken())) setUser(await api<User>("/auth/me"));
      } catch {
        /* backend unreachable: the login screen shows the error on submit */
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const r = await api<{ access_token: string; user: User }>("/auth/login", { body: { email, password } });
    setAccessToken(r.access_token);
    setUser(r.user);
  }, []);

  const setup = useCallback(async (email: string, password: string, full_name: string) => {
    const r = await api<{ access_token: string; user: User }>("/auth/setup", { body: { email, password, full_name } });
    setAccessToken(r.access_token);
    setNeedsSetup(false);
    setUser(r.user);
  }, []);

  const logout = useCallback(async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    setAccessToken(null);
    setUser(null);
  }, []);

  const can = useCallback((role: "reviewer" | "admin") => !!user && RANK[user.role] >= RANK[role], [user]);

  return (
    <Ctx.Provider value={{ user, loading, needsSetup, login, setup, logout, setUser, can }}>{children}</Ctx.Provider>
  );
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
}
