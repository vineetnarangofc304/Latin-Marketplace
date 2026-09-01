import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import StatChip from "@/components/StatChip";
import PeriodSelector from "@/components/PeriodSelector";
import { fmtCurrency, fmtInt, fmtPct } from "@/lib/format";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line, PieChart, Pie, Cell, CartesianGrid, Legend } from "recharts";
import { AlertTriangle, ArrowUpRight, RotateCcw } from "lucide-react";

const SEV_COLORS = { critical: "#DC2626", high: "#EA580C", medium: "#CA8A04", low: "#0284C7" };
const CHART_COLORS = ["#2563EB", "#059669", "#D97706", "#DC2626", "#7C3AED", "#DB2777"];

export default function Overview() {
  const nav = useNavigate();
  const [period, setPeriod] = useState({ period_type: "month", period_value: "" });
  const [overview, setOverview] = useState(null);
  const [commSum, setCommSum] = useState(null);
  const [reconSum, setReconSum] = useState(null);
  const [returnVel, setReturnVel] = useState(null);

  useEffect(() => {
    const params = { period_type: period.period_type, period_value: period.period_value || undefined };
    api.get("/dashboard/overview", { params }).then((r) => setOverview(r.data));
    api.get("/dashboard/commission-summary", { params }).then((r) => setCommSum(r.data));
    api.get("/dashboard/reconciliation-summary", { params }).then((r) => setReconSum(r.data));
    api.get("/dashboard/return-velocity", { params: { ...params, top: 12 } }).then((r) => setReturnVel(r.data));
  }, [period.period_type, period.period_value]);

  const kpi = commSum?.kpi || {};
  const marginPct = kpi.total_nsv ? (kpi.expected_settlement || 0) / kpi.total_nsv : 0;
  const commPct = kpi.total_nsv ? (kpi.expected_commission || 0) / kpi.total_nsv : 0;

  // Drill helpers — pass current period to detail pages
  const goTo = (path, extra = {}) => {
    const p = new URLSearchParams();
    if (period.period_type) p.set("period_type", period.period_type);
    if (period.period_value) p.set("period_value", period.period_value);
    Object.entries(extra).forEach(([k, v]) => v !== undefined && p.set(k, v));
    nav(`${path}?${p.toString()}`);
  };

  return (
    <div className="p-6 space-y-5" data-testid="overview-page">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <div className="overline">Executive Overview</div>
          <h1 className="text-2xl font-semibold tracking-tight mt-1 text-slate-900">Marketplace Finance Command Center</h1>
          <p className="text-sm text-slate-500 mt-1">
            Click any KPI, sub-category, or chart bar to drill into the underlying rows.
          </p>
        </div>
        <PeriodSelector value={period} onChange={setPeriod} testIdPrefix="overview-period" />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatChip testId="kpi-nsv" label="Total NSV" value={fmtCurrency(kpi.total_nsv)} sub={`${fmtInt(kpi.total_orders)} orders`} onClick={() => goTo("/sales")} drillHint />
        <StatChip testId="kpi-commission" label="Expected Commission" value={fmtCurrency(kpi.expected_commission)} sub={`${fmtPct(commPct, 2)} of NSV`} tone="negative" onClick={() => goTo("/calculations")} drillHint />
        <StatChip testId="kpi-deductions" label="Total Deductions" value={fmtCurrency(kpi.expected_deductions)} sub="Comm + Fixed + GT + TCS/TDS" tone="negative" onClick={() => goTo("/calculations")} drillHint />
        <StatChip testId="kpi-settlement" label="Expected Settlement" value={fmtCurrency(kpi.expected_settlement)} sub={`Margin ${fmtPct(marginPct, 1)}`} tone="positive" onClick={() => goTo("/calculations")} drillHint />
        <StatChip testId="kpi-critical" label="Open Discrepancies" value={fmtInt(overview?.total_discrepancies || 0)} sub={`${fmtInt(overview?.open_critical || 0)} critical · ${fmtInt(overview?.open_high || 0)} high`} tone={overview?.open_critical > 0 ? "critical" : "neutral"} onClick={() => goTo("/discrepancies")} drillHint />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <div className="lg:col-span-2 border border-border bg-white p-5 rounded-sm">
          <div className="flex items-center justify-between">
            <div>
              <div className="overline">Sub-Category Deep Dive</div>
              <div className="text-sm mt-1 text-slate-700">NSV vs Expected Commission — click a bar to drill</div>
            </div>
            <button onClick={() => goTo("/reports")} data-testid="link-view-reports" className="btn text-xs">
              Full report <ArrowUpRight size={12} />
            </button>
          </div>

          <div className="mt-4 h-72">
            <ResponsiveContainer>
              <BarChart data={commSum?.by_sub_category?.slice(0, 12) || []} onClick={(e) => {
                if (e && e.activeLabel) goTo("/calculations", { sub_category: e.activeLabel });
              }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" />
                <XAxis dataKey="sub_category" stroke="#6B7280" tick={{ fontSize: 10, fontFamily: "JetBrains Mono" }} />
                <YAxis stroke="#6B7280" tick={{ fontSize: 10, fontFamily: "JetBrains Mono" }} />
                <Tooltip contentStyle={{ background: "#FFFFFF", border: "1px solid #E1E4E8", fontFamily: "JetBrains Mono", fontSize: 11, borderRadius: 2 }} />
                <Legend wrapperStyle={{ fontFamily: "JetBrains Mono", fontSize: 11 }} />
                <Bar dataKey="nsv" fill="#2563EB" name="NSV" cursor="pointer" />
                <Bar dataKey="commission" fill="#DC2626" name="Commission" cursor="pointer" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="border border-border bg-white p-5 rounded-sm">
          <div className="overline">Discrepancies by Severity</div>
          <div className="mt-4 h-52">
            {reconSum?.by_severity?.length ? (
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={reconSum.by_severity} dataKey="count" nameKey="severity" innerRadius={45} outerRadius={80}
                    onClick={(e) => e?.severity && goTo("/discrepancies", { severity: e.severity })}
                    cursor="pointer">
                    {reconSum.by_severity.map((s, idx) => <Cell key={idx} fill={SEV_COLORS[s.severity] || CHART_COLORS[idx % CHART_COLORS.length]} />)}
                  </Pie>
                  <Tooltip contentStyle={{ background: "#FFFFFF", border: "1px solid #E1E4E8", fontFamily: "JetBrains Mono", fontSize: 11 }} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-xs mono text-slate-400 text-center px-4">
                Upload a settlement file and run reconciliation to see discrepancy breakdown.
              </div>
            )}
          </div>
          <div className="mt-2 space-y-1">
            {(reconSum?.by_severity || []).map((s) => (
              <button key={s.severity} onClick={() => goTo("/discrepancies", { severity: s.severity })}
                className="w-full flex items-center justify-between text-xs mono px-2 py-1 hover:bg-slate-50 rounded-sm">
                <span className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full" style={{ background: SEV_COLORS[s.severity] }} />
                  {s.severity?.toUpperCase()}
                </span>
                <span className="text-slate-600">{s.count} · <span className="fin-pos">{fmtCurrency(s.recoverable)}</span></span>
              </button>
            ))}
          </div>
          <div className="mt-4 border-t border-border pt-3">
            <div className="overline">Total Recoverable</div>
            <div className="mono text-lg fin-pos mt-1">{fmtCurrency(reconSum?.total_recoverable)}</div>
          </div>
        </div>
      </div>

      {commSum?.by_month?.length > 1 && (
        <div className="border border-border bg-white p-5 rounded-sm">
          <div className="overline mb-2">Monthly Trend — Commission vs Settlement</div>
          <div className="h-64">
            <ResponsiveContainer>
              <LineChart data={commSum.by_month} onClick={(e) => e?.activeLabel && goTo("/", { period_value: e.activeLabel })}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" />
                <XAxis dataKey="month" stroke="#6B7280" tick={{ fontSize: 10, fontFamily: "JetBrains Mono" }} />
                <YAxis stroke="#6B7280" tick={{ fontSize: 10, fontFamily: "JetBrains Mono" }} />
                <Tooltip contentStyle={{ background: "#FFFFFF", border: "1px solid #E1E4E8", fontFamily: "JetBrains Mono", fontSize: 11 }} />
                <Legend wrapperStyle={{ fontFamily: "JetBrains Mono", fontSize: 11 }} />
                <Line type="monotone" dataKey="commission" stroke="#DC2626" name="Commission" strokeWidth={2} />
                <Line type="monotone" dataKey="expected_settlement" stroke="#059669" name="Settlement" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {commSum?.by_sub_category?.length ? (
        <div className="border border-border bg-white rounded-sm">
          <div className="p-4 border-b border-border flex items-center justify-between">
            <div>
              <div className="overline">Sub-Category P&amp;L — click a row to drill</div>
              <div className="text-xs text-slate-500 mt-1">Top 15 by NSV · sorted by margin %</div>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="grid-header">
                <tr>
                  <th className="grid-cell text-left">Sub Category</th>
                  <th className="grid-cell text-right">Orders</th>
                  <th className="grid-cell text-right">NSV</th>
                  <th className="grid-cell text-right">Commission</th>
                  <th className="grid-cell text-right">Fixed Fee</th>
                  <th className="grid-cell text-right">GT Charge</th>
                  <th className="grid-cell text-right">Settlement</th>
                  <th className="grid-cell text-right">Margin %</th>
                </tr>
              </thead>
              <tbody>
                {(commSum.by_sub_category || []).slice(0, 15).map((r) => {
                  const margin = r.nsv ? r.expected_settlement / r.nsv : 0;
                  return (
                    <tr key={r.sub_category} className="grid-row drill" data-testid={`row-subcat-${r.sub_category}`}
                        onClick={() => goTo("/calculations", { sub_category: r.sub_category })}>
                      <td className="grid-cell drill-link">{r.sub_category}</td>
                      <td className="grid-cell text-right">{fmtInt(r.orders)}</td>
                      <td className="grid-cell text-right">{fmtCurrency(r.nsv)}</td>
                      <td className="grid-cell text-right fin-neg">{fmtCurrency(r.commission)}</td>
                      <td className="grid-cell text-right fin-neg">{fmtCurrency(r.fixed_fee)}</td>
                      <td className="grid-cell text-right fin-neg">{fmtCurrency(r.gt_charge)}</td>
                      <td className="grid-cell text-right fin-pos font-semibold">{fmtCurrency(r.expected_settlement)}</td>
                      <td className={`grid-cell text-right font-semibold ${margin < 0.5 ? "sev-high" : "fin-pos"}`}>{fmtPct(margin, 1)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {reconSum?.top_discrepancies?.length ? (
        <div className="border border-border bg-white rounded-sm">
          <div className="p-4 border-b border-border flex items-center gap-2">
            <AlertTriangle size={14} className="text-amber-500" />
            <div className="overline">Top Recoverable — click to drill</div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="grid-header">
                <tr>
                  <th className="grid-cell text-left">Order ID</th>
                  <th className="grid-cell text-left">SKU</th>
                  <th className="grid-cell text-left">Severity</th>
                  <th className="grid-cell text-left">Reason</th>
                  <th className="grid-cell text-right">Recoverable</th>
                </tr>
              </thead>
              <tbody>
                {reconSum.top_discrepancies.map((d) => (
                  <tr key={d.id} className="grid-row drill" onClick={() => goTo("/discrepancies", { search: d.online_order_id })}>
                    <td className="grid-cell drill-link">{d.online_order_id}</td>
                    <td className="grid-cell">{d.sku}</td>
                    <td className="grid-cell"><span className={`chip chip-${d.severity}`}>{d.severity}</span></td>
                    <td className="grid-cell text-slate-500 text-xs">{d.reason}</td>
                    <td className="grid-cell text-right fin-pos">{fmtCurrency(d.recoverable)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {overview?.unmapped_calculations > 0 && (
        <div className="border border-amber-300 bg-amber-50 p-4 flex items-start gap-3 rounded-sm" data-testid="unmapped-banner">
          <AlertTriangle size={16} className="text-amber-600 mt-0.5" />
          <div className="text-sm">
            <div className="font-semibold text-amber-800">{fmtInt(overview.unmapped_calculations)} orders are unmapped</div>
            <div className="text-xs text-slate-600 mt-1">Missing commission rule / GT charge / level mapping / zone.{" "}
              <button onClick={() => goTo("/calculations", { unmapped: "1" })} className="underline text-amber-700 font-medium">Review them</button> or{" "}
              <button onClick={() => nav("/masters")} className="underline text-amber-700 font-medium">edit masters</button>.
            </div>
          </div>
        </div>
      )}

      {returnVel?.overall && (returnVel.overall.sales_orders > 0 || returnVel.overall.return_dto_orders > 0) && (
        <div className="border border-border bg-white p-4 rounded-sm" data-testid="return-velocity-panel">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <div className="overline flex items-center gap-1"><RotateCcw size={12} /> Return Velocity</div>
              <div className="text-lg font-semibold text-slate-900 mt-1">
                {fmtPct(returnVel.overall.velocity_pct, 1)} of sales orders flipped to Return-DTO
              </div>
              <div className="text-xs text-slate-500 mono mt-1">
                {fmtInt(returnVel.overall.return_dto_orders)} return-DTO / {fmtInt(returnVel.overall.sales_orders)} sales · Return-fee leakage {fmtCurrency(returnVel.overall.total_leakage)}
              </div>
            </div>
            <button className="btn text-xs" data-testid="btn-drill-return-dto" onClick={() => goTo("/calculations", { order_type: "return_dto" })}>
              Drill to return-DTO rows <ArrowUpRight size={12} />
            </button>
          </div>
          <div className="mt-4 overflow-auto max-h-96">
            <table className="w-full text-xs">
              <thead className="grid-header sticky top-0 z-10">
                <tr>
                  <th className="grid-cell text-left">Sub-Category</th>
                  <th className="grid-cell text-right">Sales Orders</th>
                  <th className="grid-cell text-right">Return-DTO</th>
                  <th className="grid-cell text-right">Velocity</th>
                  <th className="grid-cell text-right">Return-Fee Leakage</th>
                  <th className="grid-cell text-right">Sales NSV</th>
                </tr>
              </thead>
              <tbody>
                {(returnVel.by_sub_category || []).map((r) => (
                  <tr key={r.sub_category} className="grid-row drill" data-testid={`rv-row-${(r.sub_category || "").replace(/\s+/g,"-")}`}
                      onClick={() => goTo("/calculations", { sub_category: r.sub_category, order_type: "return_dto" })}>
                    <td className="grid-cell drill-link">{r.sub_category}</td>
                    <td className="grid-cell text-right mono">{fmtInt(r.orders)}</td>
                    <td className="grid-cell text-right mono">{fmtInt(r.return_dto_orders)}</td>
                    <td className="grid-cell text-right mono font-semibold" style={{ color: r.velocity_pct >= 0.5 ? "#DC2626" : r.velocity_pct >= 0.3 ? "#EA580C" : "#0284C7" }}>
                      {fmtPct(r.velocity_pct, 1)}
                    </td>
                    <td className="grid-cell text-right fin-neg font-semibold">{fmtCurrency(r.leakage)}</td>
                    <td className="grid-cell text-right mono text-slate-500">{fmtCurrency(r.sales_nsv)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
