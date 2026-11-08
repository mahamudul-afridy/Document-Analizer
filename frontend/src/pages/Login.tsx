import { CheckCircle2, FileCheck2, Lock, ScanText, ShieldCheck } from "lucide-react";
import { FormEvent, useState } from "react";
import { Logo } from "../components/Logo";
import { Button, ErrorBox, Input } from "../components/ui";
import { useAuth } from "../lib/auth";

const FACTS = [
  { value: "8", label: "Supported file formats" },
  { value: "7", label: "Stage verification pipeline" },
  { value: "0", label: "API keys needed to start" },
];

const FEATURES = [
  { icon: ScanText, text: "OCR for scanned invoices and photos" },
  { icon: FileCheck2, text: "Automatic tax, subtotal and total verification" },
  { icon: ShieldCheck, text: "Duplicate and cross-document checks" },
];

export default function Login() {
  const { login, setup, needsSetup } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (needsSetup) await setup(email, password, name);
      else await login(email, password);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen bg-white lg:grid-cols-[1.05fr_1fr]">
      {/* brand panel */}
      <div className="relative hidden overflow-hidden bg-navy-panel p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div className="pointer-events-none absolute -right-28 -top-28 h-96 w-96 rounded-full bg-brand-500/20 blur-2xl" />
        <div className="pointer-events-none absolute -bottom-32 -left-20 h-[26rem] w-[26rem] rounded-full bg-accent-500/15 blur-3xl" />
        <div className="relative">
          <Logo light />
        </div>
        <div className="relative max-w-xl">
          <p className="text-lg font-semibold text-brand-100">Welcome to DocuMind AI</p>
          <h1 className="mt-2 font-display text-[52px] font-extrabold leading-[1.05] text-white">
            Intelligent Document Processing.
            <span className="mt-1 block text-accent-400">Accurate Financial Insights.</span>
          </h1>
          <p className="mt-4 font-hand text-3xl text-accent-300">every invoice, checked twice</p>
          <ul className="mt-7 space-y-3">
            {FEATURES.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-center gap-3 text-brand-50">
                <span className="rounded-full bg-accent-500 p-1.5 text-white shadow-cta">
                  <Icon className="h-4 w-4" />
                </span>
                {text}
              </li>
            ))}
          </ul>
        </div>
        <div className="relative">
          <div className="grid grid-cols-3 gap-4">
            {FACTS.map((f) => (
              <div key={f.label} className="rounded-2xl border border-white/10 bg-white/[0.06] p-5 backdrop-blur-sm">
                <div className="font-display text-4xl font-extrabold text-white">{f.value}</div>
                <div className="mt-1.5 text-[10px] font-bold uppercase leading-snug tracking-[0.12em] text-brand-200">{f.label}</div>
              </div>
            ))}
          </div>
          <div className="mt-6 flex flex-wrap gap-2">
            {["Role-based access", "Audit logged", "Encrypted secrets", "Runs on your server"].map((b) => (
              <span key={b} className="rounded-full border border-white/15 px-3 py-1 text-xs font-semibold text-brand-100">{b}</span>
            ))}
          </div>
        </div>
      </div>

      {/* form */}
      <div className="flex items-center justify-center px-5 py-12 sm:px-10">
        <div className="w-full max-w-md animate-fade-in">
          <div className="mb-10 lg:hidden">
            <Logo />
          </div>
          <p className="eyebrow mb-2">{needsSetup ? "Get started" : "Secure sign in"}</p>
          <h2 className="text-3xl font-extrabold text-brand-800">{needsSetup ? "Welcome to DocuMind AI" : "Welcome back"}</h2>
          <p className="mt-2 text-muted">
            {needsSetup
              ? "Create the first administrator account to get started."
              : "Sign in to review documents, invoices and validation results."}
          </p>
          {needsSetup && (
            <div className="mt-5 flex items-start gap-2 rounded-xl border border-accent-100 bg-accent-50 px-4 py-3 text-sm text-accent-700">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
              Fresh installation detected. This account will have full admin access.
            </div>
          )}
          <form onSubmit={submit} className="mt-8 space-y-4">
            {needsSetup && <Input label="Full name" name="name" value={name} onChange={(e) => setName(e.target.value)} required autoComplete="name" />}
            <Input label="Email" type="email" name="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
            <Input
              label="Password"
              type="password"
              name="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={needsSetup ? 8 : 1}
              autoComplete={needsSetup ? "new-password" : "current-password"}
              hint={needsSetup ? "At least 8 characters." : undefined}
            />
            <ErrorBox error={error} />
            <Button type="submit" size="lg" className="w-full" loading={busy}>
              {needsSetup ? "Create admin account" : "Sign in"}
            </Button>
          </form>
          <p className="mt-8 flex items-center justify-center gap-1.5 text-xs text-muted">
            <Lock className="h-3.5 w-3.5" /> Secured with encrypted sessions, role-based access and audit logging
          </p>
        </div>
      </div>
    </div>
  );
}
