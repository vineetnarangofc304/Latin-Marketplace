import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { formatApiError } from "@/lib/api";
import { toast } from "sonner";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("admin@fundle.ai");
  const [password, setPassword] = useState("admin123");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await login(email.trim().toLowerCase(), password);
      toast.success("Signed in");
      nav("/");
    } catch (e) {
      const msg = formatApiError(e.response?.data?.detail) || e.message;
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full flex bg-background text-foreground">
      <div className="hidden md:flex flex-1 relative bg-white border-r border-border p-10 flex-col justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-primary text-primary-foreground flex items-center justify-center text-[10px] font-bold rounded-sm">LQ</div>
          <div className="text-sm tracking-tight font-semibold">Latin Quarter · Marketplace AutoPilot</div>
        </div>
        <div className="max-w-md">
          <div className="overline mb-3">Enterprise Reconciliation OS</div>
          <h1 className="text-4xl md:text-5xl font-light tracking-tight leading-tight text-slate-900">
            Recover leakage. <span className="font-semibold">Own your marketplace math.</span>
          </h1>
          <p className="mt-5 text-sm text-slate-600 leading-relaxed">
            Ingest Myntra reports, calculate expected commissions with configurable logic,
            and reconcile settlements down to the paisa. Discrepancies surface first — by
            severity, financial impact and ageing.
          </p>
          <div className="mt-8 grid grid-cols-3 gap-3">
            {[["Commission Engine", "Contract-based"], ["Reconciliation", "Component-level"], ["Monthly MIS", "Excel export"]].map(([t, s]) => (
              <div key={t} className="border border-border p-3 bg-white rounded-sm">
                <div className="overline">{t}</div>
                <div className="mono text-[11px] text-slate-500 mt-1">{s}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="text-[10px] mono text-slate-400 uppercase tracking-widest">© Latin Quarter · Rev 2026.06</div>
      </div>

      <div className="flex-1 flex items-center justify-center px-6 py-10 bg-slate-50/40 flex-col">
        <form onSubmit={submit} className="w-full max-w-sm bg-white p-8 border border-border rounded-sm" data-testid="login-form">
          <div className="overline mb-2">Sign In</div>
          <h2 className="text-2xl font-semibold tracking-tight">Marketplace Command Center</h2>
          <p className="mt-2 text-sm text-slate-500">Use your Latin Quarter Finance credentials to continue.</p>

          <div className="mt-8">
            <label className="overline block mb-2">Email</label>
            <input data-testid="login-email" type="email" className="w-full input py-2.5" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
          </div>
          <div className="mt-4">
            <label className="overline block mb-2">Password</label>
            <input data-testid="login-password" type="password" className="w-full input py-2.5" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
          </div>

          {error ? <div className="mt-4 border border-rose-300 bg-rose-50 text-rose-700 text-xs p-3 mono" data-testid="login-error">{error}</div> : null}

          <button data-testid="login-submit" type="submit" disabled={loading} className="mt-6 w-full btn btn-primary justify-center py-2.5">
            {loading ? "Authenticating…" : "Sign in →"}
          </button>

          <div className="mt-8 border-t border-border pt-4">
            <div className="overline mb-1">Demo Credentials</div>
            <div className="text-xs mono text-slate-500">admin@fundle.ai · admin123</div>
          </div>
        </form>
        <a
          href="https://fundle.ai"
          target="_blank"
          rel="noopener noreferrer"
          data-testid="powered-by-fundle-login"
          className="mt-6 inline-flex items-center gap-2 px-4 py-2 bg-slate-900 hover:bg-slate-800 transition-colors rounded-sm"
          title="Powered by Fundle"
        >
          <span className="text-[10px] mono uppercase tracking-widest text-slate-400">Powered by</span>
          <img
            src="https://customer-assets-v7afamib.emergentagent.net/job_commission-hub-156/artifacts/f3pobwkf_fundle_logo-white-min-382x100.png"
            alt="Fundle"
            className="h-5 w-auto"
          />
        </a>
      </div>
    </div>
  );
}
