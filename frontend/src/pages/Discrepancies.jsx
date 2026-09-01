import { useEffect, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { fmtCurrency, fmtInt } from "@/lib/format";
import { toast } from "sonner";
import { AlertTriangle, X, Search, Filter, Wallet } from "lucide-react";
import PeriodSelector from "@/components/PeriodSelector";
import { SortableTh, nextDir } from "@/components/SortableTable";

export default function Discrepancies() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [period, setPeriod] = useState({
    period_type: searchParams.get("period_type") || "month",
    period_value: searchParams.get("period_value") || "",
  });
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [severity, setSeverity] = useState(searchParams.get("severity") || "");
  const [status, setStatus] = useState(searchParams.get("match_status") || "");
  const [search, setSearch] = useState(searchParams.get("search") || "");
  const [sort, setSort] = useState({ by: "recoverable", dir: "desc" });
  const [drawer, setDrawer] = useState(null);
  const runId = searchParams.get("run") || "";

  const load = async () => {
    const { data } = await api.get("/reconciliation/discrepancies", {
      params: {
        period_type: period.period_type,
        period_value: period.period_value || undefined,
        recon_run_id: runId || undefined,
        severity: severity || undefined,
        match_status: status || undefined,
        search: search || undefined,
        sort_by: sort.by, sort_dir: sort.dir,
        limit: 500,
      },
    });
    setItems(data.items);
    setTotal(data.total);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [period.period_type, period.period_value, severity, status, sort.by, sort.dir, runId]);

  const onSort = (key) => setSort((s) => nextDir(s.by, s.dir, key));

  const activeFilterCount = [severity, status, search, runId].filter(Boolean).length;
  const clearFilters = () => { setSeverity(""); setStatus(""); setSearch(""); setSearchParams({}); };

  return (
    <div className="p-6 space-y-4" data-testid="discrepancies-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="overline">Discrepancy Workbench</div>
          <h1 className="text-2xl font-semibold tracking-tight mt-1 text-slate-900 flex items-center gap-2">
            <AlertTriangle size={18} className="text-amber-500" /> {fmtInt(total)} Discrepancies
          </h1>
          <p className="text-sm text-slate-500 mt-1 mono">
            {runId ? `Run: ${runId.slice(0, 8)}` : "All runs"} · click any row for full component compare
          </p>
        </div>
        <PeriodSelector value={period} onChange={setPeriod} testIdPrefix="disc-period" />
      </div>

      <div className="border border-border bg-white p-3 rounded-sm flex items-center gap-2 flex-wrap">
        <div className="inline-flex items-center gap-1 text-xs mono text-slate-500 pr-2 border-r border-border">
          <Filter size={12} /> Filters
          {activeFilterCount > 0 && <span className="chip chip-neutral text-[9px] py-0">{activeFilterCount}</span>}
        </div>
        <div className="relative">
          <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
          <input data-testid="disc-search" value={search} onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
            placeholder="Order ID / SKU" className="input pl-7 w-52" />
        </div>
        <select data-testid="filter-severity" value={severity} onChange={(e) => setSeverity(e.target.value)} className="input">
          <option value="">All severity</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <select data-testid="filter-status" value={status} onChange={(e) => setStatus(e.target.value)} className="input">
          <option value="">All status</option>
          <option value="variance">Variance</option>
          <option value="unmatched">Unmatched</option>
        </select>
        {activeFilterCount > 0 && (
          <button onClick={clearFilters} className="btn text-xs"><X size={10} /> Clear</button>
        )}
      </div>

      <div className="border border-border bg-white overflow-auto max-h-[calc(100vh-300px)] rounded-sm">
        <table className="w-full text-xs">
          <thead className="grid-header sticky top-0 z-10">
            <tr>
              <SortableTh label="Severity" sortKey="severity" sort={sort} onSort={onSort} />
              <SortableTh label="Order ID" sortKey="order_id" sort={sort} onSort={onSort} />
              <SortableTh label="SKU" sortKey="sku" sort={sort} onSort={onSort} />
              <th className="grid-cell text-left">Status</th>
              <th className="grid-cell text-left">Reason</th>
              <SortableTh label="Settle Variance" sortKey="settle_variance" sort={sort} onSort={onSort} align="right" />
              <SortableTh label="Recoverable" sortKey="recoverable" sort={sort} onSort={onSort} align="right" />
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr><td colSpan={7} className="grid-cell text-center text-slate-400 py-10">
                No discrepancies for this period. Upload a settlement file and run reconciliation.
              </td></tr>
            ) : items.map((d) => (
              <tr key={d.id} onClick={() => setDrawer(d)} className="grid-row drill" data-testid={`disc-row-${d.id}`}
                  style={{ borderLeft: `3px solid ${d.severity === "critical" ? "#DC2626" : d.severity === "high" ? "#EA580C" : d.severity === "medium" ? "#CA8A04" : "#0284C7"}` }}>
                <td className="grid-cell"><span className={`chip chip-${d.severity}`}>{d.severity}</span></td>
                <td className="grid-cell drill-link">{(d.online_order_id || "").slice(0, 14)}…</td>
                <td className="grid-cell">{d.sku}</td>
                <td className="grid-cell">
                  <span className={`chip ${d.match_status === "unmatched" ? "chip-unmatched" : "chip-variance"}`}>{d.match_status}</span>
                </td>
                <td className="grid-cell text-slate-500 text-xs max-w-[380px] truncate" title={d.reason}>{d.reason}</td>
                <td className={`grid-cell text-right ${d.settle_variance > 0 ? "fin-pos" : "fin-neg"}`}>
                  {d.settle_variance !== undefined ? fmtCurrency(d.settle_variance) : "—"}
                </td>
                <td className="grid-cell text-right fin-pos font-semibold">{fmtCurrency(d.recoverable)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {drawer && <DiscDrawer disc={drawer} onClose={() => setDrawer(null)} />}
    </div>
  );
}

function DiscDrawer({ disc, onClose }) {
  const nav = useNavigate();
  const [creating, setCreating] = useState(false);
  const createRecoveryCase = async () => {
    setCreating(true);
    try {
      const { data } = await api.post("/recovery/cases", { discrepancy_id: disc.id });
      toast.success(`Recovery case created (${data.id.slice(0, 8)})`);
      nav(`/recovery?period_type=month&period_value=${disc.report_month || ""}`);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally { setCreating(false); }
  };
  return (
    <div className="fixed inset-0 z-40" data-testid="disc-drawer">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="absolute right-0 top-0 h-full w-full max-w-3xl bg-white border-l border-border overflow-auto">
        <div className="p-5 border-b border-border flex items-start justify-between">
          <div>
            <div className="overline">Discrepancy Detail</div>
            <div className="text-lg mt-1 mono text-slate-900">{disc.online_order_id}</div>
            <div className="text-xs text-slate-500 mono">{disc.sku}</div>
            <div className="mt-2 flex gap-2">
              <span className={`chip chip-${disc.severity}`}>{disc.severity}</span>
              <span className={`chip ${disc.match_status === "unmatched" ? "chip-unmatched" : "chip-variance"}`}>{disc.match_status}</span>
            </div>
          </div>
          <button onClick={onClose} className="btn" data-testid="close-disc-drawer"><X size={14} /></button>
        </div>

        <div className="p-5 space-y-5">
          <div className="flex justify-end">
            <button
              data-testid="btn-create-recovery-case"
              onClick={createRecoveryCase}
              disabled={creating || !disc.recoverable}
              className="btn btn-primary text-xs"
              title={!disc.recoverable ? "Only discrepancies with ₹>0 recoverable can become cases" : ""}
            >
              <Wallet size={12} /> {creating ? "Creating…" : "Open Recovery Case"}
            </button>
          </div>
          <div className="border border-border p-4 rounded-sm">
            <div className="overline mb-2">Reason</div>
            <div className="text-sm">{disc.reason}</div>
            <div className="mt-3 grid grid-cols-2 gap-3 text-xs mono">
              <div><div className="overline">Recoverable</div><div className="fin-pos text-base mt-1">{fmtCurrency(disc.recoverable)}</div></div>
              <div><div className="overline">Settle Variance</div><div className={`text-base mt-1 ${disc.settle_variance > 0 ? "fin-pos" : "fin-neg"}`}>{fmtCurrency(disc.settle_variance)}</div></div>
            </div>
          </div>

          <div>
            <div className="overline mb-2">Component-Level Compare</div>
            <table className="w-full text-xs mono border border-border">
              <thead className="grid-header">
                <tr>
                  <th className="grid-cell text-left">Component</th>
                  <th className="grid-cell text-right">Expected</th>
                  <th className="grid-cell text-right">Actual</th>
                  <th className="grid-cell text-right">Variance</th>
                  <th className="grid-cell text-left">Status</th>
                </tr>
              </thead>
              <tbody>
                {(disc.components || []).map((c) => (
                  <tr key={c.component} className="grid-row">
                    <td className="grid-cell">{c.component}</td>
                    <td className="grid-cell text-right">{fmtCurrency(c.expected)}</td>
                    <td className="grid-cell text-right">{fmtCurrency(c.actual)}</td>
                    <td className={`grid-cell text-right ${c.variance > 0 ? "fin-pos" : c.variance < 0 ? "fin-neg" : ""}`}>{fmtCurrency(c.variance)}</td>
                    <td className="grid-cell">
                      <span className={`chip ${c.status === "matched" ? "chip-matched" : c.status === "overcharged" ? "chip-variance" : "chip-unmatched"}`}>{c.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div>
            <div className="overline mb-2">Marketplace-Reported (Settled)</div>
            <pre className="text-[10px] mono bg-slate-50 p-3 border border-border rounded-sm overflow-auto">
{JSON.stringify(disc.settled, null, 2)}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}
