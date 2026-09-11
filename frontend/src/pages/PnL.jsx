import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { fmtCurrency, fmtInt } from "@/lib/format";
import { toast } from "sonner";
import { TrendingUp, Search, AlertTriangle } from "lucide-react";
import PeriodSelector from "@/components/PeriodSelector";
import { SortableTh, nextDir } from "@/components/SortableTable";

const money = (v) => <span className={v > 0 ? "fin-pos" : v < 0 ? "fin-neg" : ""}>{fmtCurrency(v)}</span>;

function Kpi({ label, value, tone, testId }) {
  return (
    <div className="border border-border bg-white p-4 rounded-sm" data-testid={testId}>
      <div className="overline">{label}</div>
      <div className={`text-xl font-semibold mt-1 mono ${tone || "text-slate-900"}`}>{value}</div>
    </div>
  );
}

export default function PnL() {
  const [period, setPeriod] = useState({ period_type: "month", period_value: "" });
  const [tab, setTab] = useState("sku");
  const [summary, setSummary] = useState(null);
  const [skuRows, setSkuRows] = useState([]);
  const [monthly, setMonthly] = useState([]);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState({ by: "net_pnl", dir: "asc" });

  const params = () => ({
    period_type: period.period_type,
    period_value: period.period_value || undefined,
  });

  const load = async () => {
    try {
      const [s, sku, mon] = await Promise.all([
        api.get("/pnl/summary", { params: params() }),
        api.get("/pnl/sku", { params: { ...params(), search: search || undefined, sort_by: sort.by, sort_dir: sort.dir, limit: 1000 } }),
        api.get("/pnl/monthly"),
      ]);
      setSummary(s.data);
      setSkuRows(sku.data.items);
      setMonthly(mon.data);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || e.message);
    }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [period.period_type, period.period_value, sort.by, sort.dir]);

  const onSort = (key) => setSort((s) => nextDir(s.by, s.dir, key));

  return (
    <div className="p-6 space-y-4" data-testid="pnl-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="overline">Profitability</div>
          <h1 className="text-2xl font-semibold tracking-tight mt-1 text-slate-900 flex items-center gap-2">
            <TrendingUp size={18} className="text-emerald-600" /> SKU &amp; Monthly P&amp;L
          </h1>
          <p className="text-sm text-slate-500 mt-1">Net P&amp;L = Net Sales Value − marketplace fees − taxes − product cost (from SKU Costs).</p>
        </div>
        <PeriodSelector value={period} onChange={setPeriod} testIdPrefix="pnl-period" />
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          <Kpi label="Net Sales Value" value={fmtCurrency(summary.net_nsv)} testId="pnl-kpi-nsv" />
          <Kpi label="Marketplace Fees" value={fmtCurrency(summary.fees)} tone="fin-neg" testId="pnl-kpi-fees" />
          <Kpi label="Taxes (TCS/TDS)" value={fmtCurrency(summary.taxes)} tone="fin-neg" testId="pnl-kpi-taxes" />
          <Kpi label="Product Cost" value={fmtCurrency(summary.product_cost)} tone="fin-neg" testId="pnl-kpi-cost" />
          <Kpi label="Net P&L" value={fmtCurrency(summary.net_pnl)} tone={summary.net_pnl >= 0 ? "fin-pos" : "fin-neg"} testId="pnl-kpi-netpnl" />
          <Kpi label="Margin %" value={`${summary.margin_pct}%`} tone={summary.margin_pct >= 0 ? "fin-pos" : "fin-neg"} testId="pnl-kpi-margin" />
        </div>
      )}

      {summary?.skus_missing_cost > 0 && (
        <div className="border border-amber-300 bg-amber-50 text-amber-800 text-xs p-3 rounded-sm flex items-center gap-2" data-testid="pnl-missing-cost-warning">
          <AlertTriangle size={14} /> {fmtInt(summary.skus_missing_cost)} of {fmtInt(summary.skus)} SKUs have no cost yet — their Product Cost is treated as ₹0. Upload costs in <b>SKU Costs</b> for accurate P&amp;L.
        </div>
      )}

      <div className="flex items-center gap-2">
        <button data-testid="pnl-tab-sku" onClick={() => setTab("sku")} className={`btn text-xs ${tab === "sku" ? "btn-primary" : ""}`}>By SKU</button>
        <button data-testid="pnl-tab-monthly" onClick={() => setTab("monthly")} className={`btn text-xs ${tab === "monthly" ? "btn-primary" : ""}`}>Monthly</button>
        {tab === "sku" && (
          <div className="relative ml-auto">
            <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
            <input data-testid="pnl-search" value={search} onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && load()} placeholder="Search SKU" className="input pl-7 w-52" />
          </div>
        )}
      </div>

      {tab === "sku" ? (
        <div className="border border-border bg-white overflow-auto max-h-[calc(100vh-360px)] rounded-sm">
          <table className="w-full text-xs">
            <thead className="grid-header sticky top-0 z-10">
              <tr>
                <SortableTh label="SKU" sortKey="sku" sort={sort} onSort={onSort} />
                <SortableTh label="Net Units" sortKey="net_units" sort={sort} onSort={onSort} align="right" />
                <SortableTh label="Net NSV" sortKey="net_nsv" sort={sort} onSort={onSort} align="right" />
                <SortableTh label="Fees" sortKey="fees" sort={sort} onSort={onSort} align="right" />
                <SortableTh label="Taxes" sortKey="taxes" sort={sort} onSort={onSort} align="right" />
                <SortableTh label="Product Cost" sortKey="product_cost" sort={sort} onSort={onSort} align="right" />
                <SortableTh label="Net P&L" sortKey="net_pnl" sort={sort} onSort={onSort} align="right" />
                <SortableTh label="Margin %" sortKey="margin_pct" sort={sort} onSort={onSort} align="right" />
              </tr>
            </thead>
            <tbody>
              {skuRows.length === 0 ? (
                <tr><td colSpan={8} className="grid-cell text-center text-slate-400 py-10">No data for this period.</td></tr>
              ) : skuRows.map((r) => (
                <tr key={r.sku} className="grid-row" data-testid={`pnl-sku-row-${r.sku}`}>
                  <td className="grid-cell mono">{r.sku} {r.cost_missing && <span className="chip chip-neutral text-[9px]">no cost</span>}</td>
                  <td className="grid-cell text-right">{fmtInt(r.net_units)}</td>
                  <td className="grid-cell text-right">{money(r.net_nsv)}</td>
                  <td className="grid-cell text-right">{money(-Math.abs(r.fees))}</td>
                  <td className="grid-cell text-right">{money(-Math.abs(r.taxes))}</td>
                  <td className="grid-cell text-right">{money(-Math.abs(r.product_cost))}</td>
                  <td className="grid-cell text-right font-semibold">{money(r.net_pnl)}</td>
                  <td className="grid-cell text-right">{r.margin_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="border border-border bg-white overflow-auto rounded-sm">
          <table className="w-full text-sm">
            <thead className="grid-header">
              <tr>
                <th className="grid-cell text-left">Month</th>
                <th className="grid-cell text-right">Net Units</th>
                <th className="grid-cell text-right">Net NSV</th>
                <th className="grid-cell text-right">Fees</th>
                <th className="grid-cell text-right">Taxes</th>
                <th className="grid-cell text-right">Product Cost</th>
                <th className="grid-cell text-right">Net P&L</th>
                <th className="grid-cell text-right">Margin %</th>
              </tr>
            </thead>
            <tbody>
              {monthly.length === 0 ? (
                <tr><td colSpan={8} className="grid-cell text-center text-slate-400 py-10">No data yet.</td></tr>
              ) : monthly.map((m) => (
                <tr key={m.month} className="grid-row" data-testid={`pnl-month-row-${m.month}`}>
                  <td className="grid-cell mono">{m.month}</td>
                  <td className="grid-cell text-right">{fmtInt(m.net_units)}</td>
                  <td className="grid-cell text-right">{money(m.net_nsv)}</td>
                  <td className="grid-cell text-right">{money(-Math.abs(m.fees))}</td>
                  <td className="grid-cell text-right">{money(-Math.abs(m.taxes))}</td>
                  <td className="grid-cell text-right">{money(-Math.abs(m.product_cost))}</td>
                  <td className="grid-cell text-right font-semibold">{money(m.net_pnl)}</td>
                  <td className="grid-cell text-right">{m.margin_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
