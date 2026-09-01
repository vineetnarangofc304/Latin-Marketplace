import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { fmtCurrency, fmtInt } from "@/lib/format";
import { toast } from "sonner";
import { GitCompareArrows, RefreshCw, Play, Info } from "lucide-react";
import PeriodSelector from "@/components/PeriodSelector";

export default function Reconciliation() {
  const nav = useNavigate();
  const [runs, setRuns] = useState([]);
  const [running, setRunning] = useState(false);
  const [period, setPeriod] = useState({ period_type: "month", period_value: "" });
  const [settlementCount, setSettlementCount] = useState(null);

  const load = async () => {
    const { data } = await api.get("/reconciliation/runs");
    setRuns(data);
  };
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (period.period_type === "month" && period.period_value) {
      api.get("/settlement", { params: { report_month: period.period_value, limit: 1 } })
        .then((r) => setSettlementCount(r.data.total))
        .catch(() => setSettlementCount(0));
    }
  }, [period.period_value, period.period_type]);

  const runNow = async () => {
    if (period.period_type !== "month" || !period.period_value) {
      toast.error("Select a Month to run reconciliation.");
      return;
    }
    setRunning(true);
    try {
      const { data } = await api.post("/reconciliation/run", { report_month: period.period_value });
      toast.success(`${data.matched} matched · ${data.variance} variance · ${data.unmatched} unmatched · ₹${data.total_recoverable} recoverable`);
      await load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="p-6 space-y-4" data-testid="recon-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="overline">Reconciliation Engine</div>
          <h1 className="text-2xl font-semibold tracking-tight mt-1 text-slate-900">Settlement vs Expected</h1>
          <p className="text-sm text-slate-500 mt-1">
            Component-by-component compare — surfaces overcharges, undercharges, missing, duplicate and unmatched rows.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <PeriodSelector value={period} onChange={setPeriod} testIdPrefix="recon-period" />
          <button data-testid="btn-run-recon" onClick={runNow} disabled={running || period.period_type !== "month" || !period.period_value} className="btn btn-primary">
            <Play size={12} /> {running ? "Reconciling…" : "Run Reconciliation"}
          </button>
        </div>
      </div>

      {settlementCount === 0 && period.period_value && (
        <div className="border border-sky-300 bg-sky-50 p-4 flex items-start gap-3 rounded-sm text-sm">
          <Info size={16} className="text-sky-600 mt-0.5" />
          <div>
            <div className="font-semibold text-sky-800">No settlement rows for {period.period_value}</div>
            <div className="text-xs text-slate-600 mt-1">
              Upload the Myntra settlement / payout report for this month before running reconciliation.
              Go to <button onClick={() => nav("/uploads")} className="underline text-sky-700 font-medium">Uploads</button>.
            </div>
          </div>
        </div>
      )}

      <div className="border border-border bg-white rounded-sm">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="overline flex items-center gap-2"><GitCompareArrows size={12} /> Reconciliation Runs</div>
          <button onClick={load} className="btn text-xs"><RefreshCw size={10} /> Refresh</button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="grid-header">
              <tr>
                <th className="grid-cell text-left">Run</th>
                <th className="grid-cell text-left">Month</th>
                <th className="grid-cell text-left">Created</th>
                <th className="grid-cell text-right">Settled</th>
                <th className="grid-cell text-right">Matched</th>
                <th className="grid-cell text-right">Variance</th>
                <th className="grid-cell text-right">Unmatched</th>
                <th className="grid-cell text-right">Recoverable</th>
                <th className="grid-cell text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {runs.length === 0 ? (
                <tr><td colSpan={9} className="grid-cell text-center text-slate-400 py-10">
                  No reconciliation runs. Upload a settlement file, pick the month, then click "Run Reconciliation".
                </td></tr>
              ) : runs.map((r) => (
                <tr key={r.id} className="grid-row drill" data-testid={`recon-run-${r.id}`}
                    onClick={() => nav(`/discrepancies?run=${r.id}${r.report_month ? `&period_type=month&period_value=${r.report_month}` : ""}`)}>
                  <td className="grid-cell text-xs drill-link">{r.id.slice(0, 8)}</td>
                  <td className="grid-cell text-xs mono">{r.report_month || "—"}</td>
                  <td className="grid-cell text-xs text-slate-500">{new Date(r.created_at).toLocaleString()}</td>
                  <td className="grid-cell text-right">{fmtInt(r.total_settled_rows)}</td>
                  <td className="grid-cell text-right fin-pos">{fmtInt(r.matched)}</td>
                  <td className="grid-cell text-right fin-neg">{fmtInt(r.variance)}</td>
                  <td className="grid-cell text-right sev-high">{fmtInt(r.unmatched)}</td>
                  <td className="grid-cell text-right fin-pos font-semibold">{fmtCurrency(r.total_recoverable)}</td>
                  <td className="grid-cell text-right"><span className="drill-link text-xs">View →</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
