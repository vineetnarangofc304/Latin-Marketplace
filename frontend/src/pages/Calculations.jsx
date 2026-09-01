import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { fmtCurrency, fmtInt } from "@/lib/format";
import { toast } from "sonner";
import { PlayCircle, RefreshCw, Search, X, Filter } from "lucide-react";
import PeriodSelector from "@/components/PeriodSelector";
import { SortableTh, nextDir } from "@/components/SortableTable";

export default function Calculations() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialPeriodType = searchParams.get("period_type") || "month";
  const initialPeriodValue = searchParams.get("period_value") || "";
  const [period, setPeriod] = useState({ period_type: initialPeriodType, period_value: initialPeriodValue });

  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [running, setRunning] = useState(false);
  const [search, setSearch] = useState(searchParams.get("search") || "");
  const [filters, setFilters] = useState({
    sub_category: searchParams.get("sub_category") || "",
    master_category: searchParams.get("master_category") || "",
    zone: searchParams.get("zone") || "",
    order_type: searchParams.get("order_type") || "",
    severity_flag: searchParams.get("unmapped") === "1" ? "unmapped" : "",
  });
  const [sort, setSort] = useState({ by: "settlement", dir: "desc" });
  const [drawer, setDrawer] = useState(null);

  const load = async () => {
    const params = {
      period_type: period.period_type,
      period_value: period.period_value || undefined,
      search: search || undefined,
      sub_category: filters.sub_category || undefined,
      master_category: filters.master_category || undefined,
      zone: filters.zone || undefined,
      order_type: filters.order_type || undefined,
      severity_flag: filters.severity_flag || undefined,
      sort_by: sort.by, sort_dir: sort.dir,
      limit: 500,
    };
    const { data } = await api.get("/calculations", { params });
    setItems(data.items);
    setTotal(data.total);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [period.period_type, period.period_value, filters.sub_category, filters.master_category, filters.zone, filters.order_type, filters.severity_flag, sort.by, sort.dir]);

  // Debounced search
  useEffect(() => {
    const t = setTimeout(() => { load(); }, 400);
    return () => clearTimeout(t);
    /* eslint-disable-next-line */
  }, [search]);

  const runAll = async () => {
    setRunning(true);
    try {
      const { data } = await api.post("/calculations/run", {
        report_month: period.period_type === "month" ? period.period_value || undefined : undefined,
        recalculate: true,
      });
      toast.success(`${data.fully_mapped_count} mapped · ${data.unmapped_count} unmapped`);
      await load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setRunning(false);
    }
  };

  const onSort = (key) => setSort((s) => nextDir(s.by, s.dir, key));

  const clearFilters = () => {
    setFilters({ sub_category: "", master_category: "", zone: "", severity_flag: "" });
    setSearch("");
    setSearchParams({});
  };

  const activeFilterCount = Object.values(filters).filter(Boolean).length + (search ? 1 : 0);

  const openDrawer = async (row) => {
    setDrawer({ loading: true });
    try {
      const { data } = await api.get(`/calculations/by-sale/${row.sales_id}`);
      setDrawer(data);
    } catch (e) {
      toast.error("Failed to load detail");
      setDrawer(null);
    }
  };

  return (
    <div className="p-6 space-y-4" data-testid="calculations-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="overline">Calculation Engine</div>
          <h1 className="text-2xl font-semibold tracking-tight mt-1 text-slate-900">Expected Commission &amp; Deductions</h1>
          <p className="text-sm text-slate-500 mt-1 mono">{fmtInt(total)} rows · component-level breakdown · click row for full trail</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <PeriodSelector value={period} onChange={setPeriod} testIdPrefix="calc-period" />
          <button onClick={load} data-testid="btn-calc-refresh" className="btn"><RefreshCw size={12} /> Refresh</button>
          <button data-testid="btn-run-all-calcs" onClick={runAll} disabled={running} className="btn btn-primary">
            <PlayCircle size={12} /> {running ? "Running…" : "Run Calculations"}
          </button>
        </div>
      </div>

      {/* Filter bar */}
      <div className="border border-border bg-white p-3 rounded-sm flex items-center gap-2 flex-wrap">
        <div className="inline-flex items-center gap-1 text-xs mono text-slate-500 pr-2 border-r border-border">
          <Filter size={12} /> Filters
          {activeFilterCount > 0 && <span className="chip chip-neutral text-[9px] py-0">{activeFilterCount}</span>}
        </div>
        <div className="relative">
          <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
          <input data-testid="calc-search" value={search} onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
            placeholder="Search Order ID / SKU" className="input pl-7 w-52" />
        </div>
        <select data-testid="filter-master" value={filters.master_category} onChange={(e) => setFilters({ ...filters, master_category: e.target.value })} className="input">
          <option value="">All Categories</option>
          <option value="APPAREL">APPAREL</option>
          <option value="ACCESSORIES">ACCESSORIES</option>
        </select>
        <input data-testid="filter-subcat" value={filters.sub_category} onChange={(e) => setFilters({ ...filters, sub_category: e.target.value })} placeholder="Sub-Category (exact)" className="input w-40" />
        <select data-testid="filter-zone" value={filters.zone} onChange={(e) => setFilters({ ...filters, zone: e.target.value })} className="input">
          <option value="">All Zones</option>
          <option value="Local">Local</option>
          <option value="Zonal">Zonal</option>
          <option value="National">National</option>
        </select>
        <select data-testid="filter-mapped" value={filters.severity_flag} onChange={(e) => setFilters({ ...filters, severity_flag: e.target.value })} className="input">
          <option value="">Mapped + Unmapped</option>
          <option value="mapped">Fully mapped</option>
          <option value="unmapped">Unmapped only</option>
        </select>
        {activeFilterCount > 0 && (
          <button data-testid="clear-filters" onClick={clearFilters} className="btn text-xs">
            <X size={10} /> Clear
          </button>
        )}
      </div>

      <div className="border border-border bg-white overflow-auto max-h-[calc(100vh-320px)] rounded-sm">
        <table className="w-full text-xs">
          <thead className="grid-header sticky top-0 z-10">
            <tr>
              <SortableTh label="Order ID" sortKey="order_id" sort={sort} onSort={onSort} className="frozen-col" />
              <SortableTh label="SKU" sortKey="sku" sort={sort} onSort={onSort} />
              <SortableTh label="Sub-Cat" sortKey="sub_category" sort={sort} onSort={onSort} />
              <SortableTh label="Month" sortKey="month" sort={sort} onSort={onSort} />
              <SortableTh label="NSV" sortKey="nsv" sort={sort} onSort={onSort} align="right" />
              <SortableTh label="Comm (incl GST)" sortKey="commission" sort={sort} onSort={onSort} align="right" />
              <SortableTh label="Fixed" sortKey="fixed_fee" sort={sort} onSort={onSort} align="right" />
              <SortableTh label="GT" sortKey="gt_charge" sort={sort} onSort={onSort} align="right" />
              <SortableTh label="Deductions" sortKey="deductions" sort={sort} onSort={onSort} align="right" />
              <SortableTh label="Expected Payout" sortKey="settlement" sort={sort} onSort={onSort} align="right" />
              <th className="grid-cell text-left">Status</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr><td colSpan={11} className="grid-cell text-center text-slate-400 py-10">No calculations. Run engine from Uploads or click &quot;Run Calculations&quot;.</td></tr>
            ) : items.map((c) => (
              <tr key={c.id} className="grid-row drill" data-testid={`calc-row-${c.id}`} onClick={() => openDrawer(c)}>
                <td className="grid-cell frozen-col drill-link">{(c.online_order_id || "").slice(0, 14)}…</td>
                <td className="grid-cell">{c.sku}</td>
                <td className="grid-cell text-slate-600">{c.breakdown?.sub_category}</td>
                <td className="grid-cell text-slate-500">{c.report_month || "—"}</td>
                <td className="grid-cell text-right">{fmtCurrency(c.breakdown?.nsv_val)}</td>
                <td className="grid-cell text-right fin-neg">{fmtCurrency(c.commission_incl_gst)}</td>
                <td className="grid-cell text-right fin-neg">{fmtCurrency(c.fixed_fee_incl_gst)}</td>
                <td className="grid-cell text-right fin-neg">{fmtCurrency(c.gt_charge)}</td>
                <td className="grid-cell text-right fin-neg font-semibold">{fmtCurrency(c.total_deductions)}</td>
                <td className="grid-cell text-right fin-pos font-semibold">{fmtCurrency(c.expected_settlement)}</td>
                <td className="grid-cell">
                  {c.unmapped ? (
                    <span className="chip chip-high" title={(c.unmapped_reasons || []).join(" · ")}>Unmapped</span>
                  ) : (
                    <span className="chip chip-matched">OK</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {drawer && <CalcDrawer data={drawer} onClose={() => setDrawer(null)} />}
    </div>
  );
}

function CalcDrawer({ data, onClose }) {
  const c = data?.calculation;
  const s = data?.sale;
  return (
    <div className="fixed inset-0 z-40" data-testid="calc-drawer">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="absolute right-0 top-0 h-full w-full max-w-2xl bg-white border-l border-border overflow-auto">
        <div className="p-5 border-b border-border flex items-start justify-between">
          <div>
            <div className="overline">Calculation Explainer</div>
            <div className="text-lg mt-1 mono text-slate-900">{s?.online_order_id || "…"}</div>
            <div className="text-xs text-slate-500 mono">{s?.sku}</div>
          </div>
          <button onClick={onClose} className="btn" data-testid="close-drawer"><X size={14} /></button>
        </div>
        {data.loading ? (
          <div className="p-8 text-center text-slate-400 mono text-xs">Loading…</div>
        ) : c ? (
          <div className="p-5 space-y-5">
            {c.unmapped && (
              <div className="border border-amber-300 bg-amber-50 p-3 text-xs">
                <div className="font-semibold text-amber-800">Unmapped — {c.unmapped_reasons?.length} reason(s)</div>
                <ul className="mt-1 list-disc pl-4 text-slate-700">
                  {c.unmapped_reasons.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
              </div>
            )}
            <div>
              <div className="overline mb-2">Source (Sales Row)</div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs mono border border-border p-3 rounded-sm">
                {[["Category", s?.category], ["Sub Category", s?.sub_category], ["Zone", s?.zone], ["Order Status", s?.order_status],
                  ["Qty", s?.qty], ["MRP", fmtCurrency(s?.mrp)], ["Customer Discount", fmtCurrency(s?.customer_discount)],
                  ["NSV", fmtCurrency(s?.nsv_val)]].map(([k, v]) => (
                  <div key={k} className="flex justify-between border-b border-border/50 py-1">
                    <span className="text-slate-500">{k}</span><span>{v ?? "—"}</span>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div className="overline mb-2">Matched Rules</div>
              <div className="text-xs mono space-y-1 border border-border p-3 rounded-sm">
                <div className="flex justify-between border-b border-border/50 py-1"><span className="text-slate-500">Commission {c.breakdown?.commission_rule?.commission_pct ? `@ ${(c.breakdown.commission_rule.commission_pct * 100).toFixed(2)}%` : ""}</span><span>{c.breakdown?.commission_rule?.price_range || "—"}</span></div>
                <div className="flex justify-between border-b border-border/50 py-1"><span className="text-slate-500">Fixed Fee Slab</span><span>{c.breakdown?.fixed_fee_slab?.label || "—"} → ₹{c.breakdown?.fixed_fee_slab?.fixed_fee || 0}</span></div>
                <div className="flex justify-between border-b border-border/50 py-1"><span className="text-slate-500">GT ({c.breakdown?.level || "—"})</span><span>{c.breakdown?.gt_charge_cell?.price_range || "—"} × {c.breakdown?.gt_charge_cell?.qty || 0} → ₹{c.breakdown?.gt_charge_cell?.unit_charge || 0}/u</span></div>
                <div className="flex justify-between py-1"><span className="text-slate-500">Return Fee (Zone {c.breakdown?.zone || "—"})</span><span>{c.breakdown?.return_fee_cell?.applied ? `₹${c.breakdown?.return_fee_cell?.fee}` : "Not applied"}</span></div>
              </div>
            </div>
            <div>
              <div className="overline mb-2">Expected Charges &amp; Deductions</div>
              <table className="w-full text-xs mono border border-border">
                <tbody>
                  {[
                    ["Commission base (ex GST)", c.commission_base, "neg"],
                    ["GST on Commission (18%)", c.commission_gst, "neg"],
                    ["Fixed Fee (ex GST)", c.fixed_fee, "neg"],
                    ["GST on Fixed Fee (18%)", c.fixed_fee_gst, "neg"],
                    ["GT Charge (incl GST)", c.gt_charge, "neg"],
                    ["Return Fee (Level/Zone)", c.return_fee, "neg"],
                    ["TCS", c.tcs, "neg"],
                    ["TDS", c.tds, "neg"],
                    ["Total Deductions", c.total_deductions, "neg", true],
                    ["Expected Settlement", c.expected_settlement, "pos", true],
                  ].map(([k, v, tone, bold]) => (
                    <tr key={k}>
                      <td className={`px-3 py-2 border-b border-border/40 ${bold ? "font-semibold" : "text-slate-500"}`}>{k}</td>
                      <td className={`px-3 py-2 border-b border-border/40 text-right ${bold ? "font-semibold" : ""} ${tone === "neg" ? "fin-neg" : tone === "pos" ? "fin-pos" : ""}`}>{fmtCurrency(v)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
