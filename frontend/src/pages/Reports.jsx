import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { fmtCurrency, fmtInt, fmtPct } from "@/lib/format";
import { toast } from "sonner";
import { Download, RefreshCw } from "lucide-react";
import StatChip from "@/components/StatChip";
import PeriodSelector from "@/components/PeriodSelector";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, PieChart, Pie, Cell, LineChart, Line, Legend } from "recharts";

const SEV_COLORS = { critical: "#DC2626", high: "#EA580C", medium: "#CA8A04", low: "#0284C7" };

export default function Reports() {
  const nav = useNavigate();
  const [period, setPeriod] = useState({ period_type: "month", period_value: "" });
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    if (!period.period_type || (period.period_type !== "all" && !period.period_value)) return;
    setLoading(true);
    api.get("/reports/period", { params: { period_type: period.period_type, period_value: period.period_value || undefined } })
      .then((r) => setReport(r.data))
      .catch((e) => toast.error(e.response?.data?.detail || e.message))
      .finally(() => setLoading(false));
  }, [period.period_type, period.period_value]);

  const download = async () => {
    if (period.period_type !== "month" || !period.period_value) {
      toast.error("Excel export currently supports Month periods. Use Month + a value.");
      return;
    }
    setDownloading(true);
    try {
      const res = await api.get("/reports/monthly/export", { params: { month: period.period_value }, responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = `LatinQuarter_Myntra_Report_${period.period_value}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success(`Downloaded ${period.period_value}`);
    } catch (e) {
      toast.error("Download failed");
    } finally {
      setDownloading(false);
    }
  };

  const kpi = report?.kpi || {};
  const marginPct = useMemo(() => {
    const nsv = kpi.total_nsv || kpi.sales_nsv || 0;
    const s = kpi.expected_settlement || 0;
    return nsv ? s / nsv : 0;
  }, [kpi]);

  const goTo = (path, extra = {}) => {
    const p = new URLSearchParams();
    if (period.period_type) p.set("period_type", period.period_type);
    if (period.period_value) p.set("period_value", period.period_value);
    Object.entries(extra).forEach(([k, v]) => v !== undefined && p.set(k, v));
    nav(`${path}?${p.toString()}`);
  };

  return (
    <div className="p-6 space-y-6" data-testid="reports-page">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <div className="overline">Marketplace Finance Report</div>
          <h1 className="text-2xl font-semibold tracking-tight mt-1 text-slate-900">
            {report?.label ? `${report.label} — Marketplace Report` : "Select a period"}
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Monthly · Quarterly · YTD · Annual. Click any row / bar / chip to drill into underlying data.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <PeriodSelector value={period} onChange={setPeriod} testIdPrefix="report-period" />
          <button data-testid="btn-refresh-report" onClick={() => setPeriod({ ...period })} disabled={loading} className="btn">
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
          <button data-testid="btn-download-report" onClick={download} disabled={downloading || period.period_type !== "month"} className="btn btn-primary" title={period.period_type !== "month" ? "Excel export supports Month period only" : ""}>
            <Download size={12} /> {downloading ? "Preparing…" : "Download Excel"}
          </button>
        </div>
      </div>

      {loading ? (
        <div className="border border-border bg-white p-12 text-center text-slate-400 mono text-xs uppercase tracking-widest rounded-sm">Loading report…</div>
      ) : report ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatChip testId="rep-nsv" label="Total NSV" value={fmtCurrency(kpi.total_nsv || kpi.sales_nsv)} sub={`${fmtInt(kpi.total_orders || kpi.sales_rows)} orders`} onClick={() => goTo("/sales")} drillHint />
            <StatChip testId="rep-commission" label="Expected Commission" value={fmtCurrency(kpi.expected_commission)} sub="Incl 18% GST" tone="negative" onClick={() => goTo("/calculations")} drillHint />
            <StatChip testId="rep-deductions" label="Total Deductions" value={fmtCurrency(kpi.expected_deductions)} sub="Comm + Fixed + GT + Return + TCS/TDS" tone="negative" onClick={() => goTo("/calculations")} drillHint />
            <StatChip testId="rep-settlement" label="Expected Settlement" value={fmtCurrency(kpi.expected_settlement)} sub={`Margin ${fmtPct(marginPct, 1)}`} tone="positive" onClick={() => goTo("/calculations")} drillHint />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
            <div className="lg:col-span-2 border border-border bg-white p-5 rounded-sm">
              <div className="overline">Top Sub-Categories — click a bar to drill</div>
              <div className="h-72 mt-4">
                <ResponsiveContainer>
                  <BarChart data={report.by_sub_category?.slice(0, 12) || []} onClick={(e) => e?.activeLabel && goTo("/calculations", { sub_category: e.activeLabel })}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" />
                    <XAxis dataKey="sub_category" stroke="#6B7280" tick={{ fontSize: 10, fontFamily: "JetBrains Mono" }} />
                    <YAxis stroke="#6B7280" tick={{ fontSize: 10, fontFamily: "JetBrains Mono" }} />
                    <Tooltip contentStyle={{ background: "#FFFFFF", border: "1px solid #E1E4E8", fontFamily: "JetBrains Mono", fontSize: 11 }} />
                    <Legend wrapperStyle={{ fontFamily: "JetBrains Mono", fontSize: 11 }} />
                    <Bar dataKey="nsv" fill="#2563EB" name="NSV" cursor="pointer" />
                    <Bar dataKey="commission" fill="#DC2626" name="Commission" cursor="pointer" />
                    <Bar dataKey="gt_charge" fill="#F59E0B" name="GT Charge" cursor="pointer" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="border border-border bg-white p-5 rounded-sm">
              <div className="overline">Discrepancies</div>
              <div className="h-48 mt-4">
                {report.reconciliation?.by_severity?.length ? (
                  <ResponsiveContainer>
                    <PieChart>
                      <Pie data={report.reconciliation.by_severity} dataKey="count" nameKey="severity" innerRadius={40} outerRadius={70}
                        onClick={(e) => e?.severity && goTo("/discrepancies", { severity: e.severity })} cursor="pointer">
                        {report.reconciliation.by_severity.map((s, idx) => <Cell key={idx} fill={SEV_COLORS[s.severity] || "#94A3B8"} />)}
                      </Pie>
                      <Tooltip contentStyle={{ background: "#FFFFFF", border: "1px solid #E1E4E8", fontFamily: "JetBrains Mono", fontSize: 11 }} />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-xs mono text-slate-400 text-center px-4">
                    Upload a settlement file to see reconciliation.
                  </div>
                )}
              </div>
              <div className="mt-3 space-y-1">
                <div className="flex justify-between text-xs mono">
                  <span className="text-slate-500">Total Discrepancies</span>
                  <span>{fmtInt(report.reconciliation?.total_discrepancies || 0)}</span>
                </div>
                <div className="flex justify-between text-xs mono">
                  <span className="text-slate-500">Total Recoverable</span>
                  <span className="fin-pos">{fmtCurrency(report.reconciliation?.total_recoverable || 0)}</span>
                </div>
                {kpi.unmapped_orders > 0 && (
                  <div className="flex justify-between text-xs mono">
                    <span className="text-slate-500">Unmapped Orders</span>
                    <button onClick={() => goTo("/calculations", { unmapped: "1" })} className="sev-high underline">{fmtInt(kpi.unmapped_orders)}</button>
                  </div>
                )}
              </div>
            </div>
          </div>

          {report.by_month?.length > 1 && (
            <div className="border border-border bg-white p-5 rounded-sm">
              <div className="overline mb-2">Monthly Trend</div>
              <div className="h-64">
                <ResponsiveContainer>
                  <LineChart data={report.by_month}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" />
                    <XAxis dataKey="month" stroke="#6B7280" tick={{ fontSize: 10, fontFamily: "JetBrains Mono" }} />
                    <YAxis stroke="#6B7280" tick={{ fontSize: 10, fontFamily: "JetBrains Mono" }} />
                    <Tooltip contentStyle={{ background: "#FFFFFF", border: "1px solid #E1E4E8", fontFamily: "JetBrains Mono", fontSize: 11 }} />
                    <Legend wrapperStyle={{ fontFamily: "JetBrains Mono", fontSize: 11 }} />
                    <Line type="monotone" dataKey="nsv" stroke="#2563EB" name="NSV" strokeWidth={2} />
                    <Line type="monotone" dataKey="commission" stroke="#DC2626" name="Commission" strokeWidth={2} />
                    <Line type="monotone" dataKey="expected_settlement" stroke="#059669" name="Settlement" strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          <div className="border border-border bg-white rounded-sm">
            <div className="p-4 border-b border-border">
              <div className="overline">Sub-Category Breakdown — click any row to drill into calculations</div>
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
                    <th className="grid-cell text-right">Expected Settlement</th>
                    <th className="grid-cell text-right">Margin %</th>
                  </tr>
                </thead>
                <tbody>
                  {(report.by_sub_category || []).map((r) => {
                    const margin = r.nsv ? r.expected_settlement / r.nsv : 0;
                    return (
                      <tr key={r.sub_category} className="grid-row drill" data-testid={`report-sub-${r.sub_category}`}
                          onClick={() => goTo("/calculations", { sub_category: r.sub_category })}>
                        <td className="grid-cell drill-link">{r.sub_category}</td>
                        <td className="grid-cell text-right">{fmtInt(r.orders)}</td>
                        <td className="grid-cell text-right">{fmtCurrency(r.nsv)}</td>
                        <td className="grid-cell text-right fin-neg">{fmtCurrency(r.commission)}</td>
                        <td className="grid-cell text-right fin-neg">{fmtCurrency(r.fixed_fee)}</td>
                        <td className="grid-cell text-right fin-neg">{fmtCurrency(r.gt_charge)}</td>
                        <td className="grid-cell text-right fin-pos">{fmtCurrency(r.expected_settlement)}</td>
                        <td className={`grid-cell text-right ${margin < 0.5 ? "sev-high" : "fin-pos"}`}>{fmtPct(margin, 1)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
