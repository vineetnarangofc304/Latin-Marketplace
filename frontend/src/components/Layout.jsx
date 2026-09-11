import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import {
  LayoutDashboard, Upload, Table2, Calculator, GitCompareArrows,
  AlertTriangle, Settings2, LogOut, FileText, Wallet, Sparkles,
  TrendingUp, Coins, FileWarning, BookOpen,
} from "lucide-react";

const nav = [
  { to: "/", label: "Overview", icon: LayoutDashboard, testId: "nav-overview" },
  { to: "/insights", label: "AI Insights", icon: Sparkles, testId: "nav-insights" },
  { to: "/reports", label: "Reports", icon: FileText, testId: "nav-reports" },
  { to: "/pnl", label: "P&L", icon: TrendingUp, testId: "nav-pnl" },
  { to: "/uploads", label: "Uploads", icon: Upload, testId: "nav-uploads" },
  { to: "/sku-costs", label: "SKU Costs", icon: Coins, testId: "nav-sku-costs" },
  { to: "/claims", label: "Claims", icon: FileWarning, testId: "nav-claims" },
  { to: "/sales", label: "Sales Ledger", icon: Table2, testId: "nav-sales" },
  { to: "/calculations", label: "Calculations", icon: Calculator, testId: "nav-calculations" },
  { to: "/reconciliation", label: "Reconciliation", icon: GitCompareArrows, testId: "nav-recon" },
  { to: "/discrepancies", label: "Discrepancies", icon: AlertTriangle, testId: "nav-disc" },
  { to: "/recovery", label: "Recovery", icon: Wallet, testId: "nav-recovery" },
  { to: "/masters", label: "Masters", icon: Settings2, testId: "nav-masters" },
  { to: "/methodology", label: "Methodology", icon: BookOpen, testId: "nav-methodology" },
];

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const nav_ = useNavigate();
  const loc = useLocation();

  return (
    <div className="min-h-screen flex bg-background text-foreground">
      <aside className="w-56 border-r border-border bg-white flex flex-col shrink-0">
        <div className="px-5 py-5 border-b border-border">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 bg-primary text-primary-foreground flex items-center justify-center text-[10px] font-bold rounded-sm">LQ</div>
            <div>
              <div className="text-sm font-semibold tracking-tight">Latin Quarter</div>
              <div className="overline">Marketplace OS</div>
            </div>
          </div>
        </div>
        <nav className="flex-1 py-3 flex flex-col">
          {nav.map((n) => {
            const active = loc.pathname === n.to || (n.to !== "/" && loc.pathname.startsWith(n.to));
            const Icon = n.icon;
            return (
              <NavLink
                key={n.to}
                to={n.to}
                data-testid={n.testId}
                className={`flex items-center gap-3 px-5 py-2.5 text-sm border-l-2 ${active ? "border-primary bg-slate-50 text-foreground font-medium" : "border-transparent text-slate-600 hover:text-foreground hover:bg-slate-50"}`}
              >
                <Icon size={16} strokeWidth={1.5} />
                <span>{n.label}</span>
              </NavLink>
            );
          })}
        </nav>
        <div className="p-4 border-t border-border bg-slate-50/40">
          <div className="overline mb-1">Signed in</div>
          <div className="text-xs truncate text-slate-700">{user?.email}</div>
          <div className="overline mt-0.5">{user?.role}</div>
          <button
            data-testid="btn-logout"
            className="mt-3 w-full inline-flex items-center gap-2 justify-center text-xs py-2 border border-border hover:bg-white rounded-sm"
            onClick={async () => { await logout(); nav_("/login"); }}
          >
            <LogOut size={12} /> Sign out
          </button>
        </div>
        <a
          href="https://fundle.ai"
          target="_blank"
          rel="noopener noreferrer"
          data-testid="powered-by-fundle-sidebar"
          className="flex items-center justify-center gap-2 py-3 bg-slate-900 hover:bg-slate-800 transition-colors border-t border-slate-800"
          title="Powered by Fundle"
        >
          <span className="text-[9px] mono uppercase tracking-widest text-slate-400">Powered by</span>
          <img
            src="https://customer-assets-v7afamib.emergentagent.net/job_commission-hub-156/artifacts/f3pobwkf_fundle_logo-white-min-382x100.png"
            alt="Fundle"
            className="h-4 w-auto"
          />
        </a>
      </aside>

      <main className="flex-1 min-w-0 flex flex-col">
        <header className="h-12 border-b border-border bg-white flex items-center justify-between px-6">
          <div className="text-xs uppercase tracking-widest text-slate-500 mono">
            {loc.pathname === "/" ? "Overview / Command Center" : loc.pathname.slice(1).replace(/\//g, " / ")}
          </div>
          <div className="text-xs mono text-slate-500">
            Myntra · Latin Quarter · {new Date().toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })}
          </div>
        </header>
        <div className="flex-1 overflow-auto">{children}</div>
      </main>
    </div>
  );
}
