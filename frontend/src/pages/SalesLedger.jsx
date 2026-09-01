import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import { fmtCurrency, fmtInt } from "@/lib/format";
import { Search, X, Filter } from "lucide-react";
import PeriodSelector from "@/components/PeriodSelector";
import { SortableTh, nextDir } from "@/components/SortableTable";

export default function SalesLedger() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [period, setPeriod] = useState({
    period_type: searchParams.get("period_type") || "month",
    period_value: searchParams.get("period_value") || "",
  });
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState({
    sub_category: searchParams.get("sub_category") || "",
    zone: searchParams.get("zone") || "",
    order_status: "",
    txn_type: "",
  });
  const [sort, setSort] = useState({ by: "order_date", dir: "desc" });
  const [drawer, setDrawer] = useState(null);
  const [calc, setCalc] = useState(null);

  const load = async () => {
    const params = {
      period_type: period.period_type, period_value: period.period_value || undefined,
      search: search || undefined,
      sub_category: filters.sub_category || undefined,
      zone: filters.zone || undefined,
      order_status: filters.order_status || undefined,
      txn_type: filters.txn_type || undefined,
      sort_by: sort.by, sort_dir: sort.dir,
      limit: 500,
    };
    const { data } = await api.get("/sales", { params });
    setItems(data.items);
    setTotal(data.total);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [period.period_type, period.period_value, filters.sub_category, filters.zone, filters.order_status, filters.txn_type, sort.by, sort.dir]);

  // Debounced search: fire 400ms after user stops typing (also on manual Enter).
  useEffect(() => {
    const t = setTimeout(() => { load(); }, 400);
    return () => clearTimeout(t);
    /* eslint-disable-next-line */
  }, [search]);

  const onSort = (key) => setSort((s) => nextDir(s.by, s.dir, key));

  const openDrawer = async (row) => {
    setDrawer(row);
    setCalc(null);
    try {
      const { data } = await api.get(`/calculations/by-sale/${row.id}`);
      setCalc(data.calculation);
    } catch (e) {
      setCalc({ error: "No calculation found — run calculations first." });
    }
  };

  const activeFilterCount = Object.values(filters).filter(Boolean).length + (search ? 1 : 0);
  const clearFilters = () => { setFilters({ sub_category: "", zone: "", order_status: "", txn_type: "" }); setSearch(""); };

  return (
    <div className="p-6 space-y-4" data-testid="sales-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="overline">Canonical Sales Ledger</div>
          <h1 className="text-2xl font-semibold tracking-tight mt-1 text-slate-900">Order Items</h1>
          <p className="text-sm text-slate-500 mt-1 mono">{fmtInt(total)} rows · click any row to view calc breakdown</p>
        </div>
        <PeriodSelector value={period} onChange={setPeriod} testIdPrefix="sales-period" />
      </div>

      <div className="border border-border bg-white p-3 rounded-sm flex items-center gap-2 flex-wrap">
        <div className="inline-flex items-center gap-1 text-xs mono text-slate-500 pr-2 border-r border-border">
          <Filter size={12} /> Filters
          {activeFilterCount > 0 && <span className="chip chip-neutral text-[9px] py-0">{activeFilterCount}</span>}
        </div>
        <div className="relative">
          <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
          <input data-testid="sales-search" value={search} onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
            placeholder="Order ID / SKU / Invoice" className="input pl-7 w-52" />
        </div>
        <input data-testid="filter-subcat" value={filters.sub_category} onChange={(e) => setFilters({ ...filters, sub_category: e.target.value })} placeholder="Sub-Category" className="input w-40" />
        <select data-testid="filter-zone" value={filters.zone} onChange={(e) => setFilters({ ...filters, zone: e.target.value })} className="input">
          <option value="">All Zones</option>
          <option value="Local">Local</option>
          <option value="Zonal">Zonal</option>
          <option value="National">National</option>
          <option value="-">— (unset)</option>
        </select>
        <select data-testid="filter-txn" value={filters.txn_type} onChange={(e) => setFilters({ ...filters, txn_type: e.target.value })} className="input">
          <option value="">All Txn Types</option>
          <option value="Sales">Sales</option>
          <option value="Return">Return</option>
        </select>
        <input data-testid="filter-status" value={filters.order_status} onChange={(e) => setFilters({ ...filters, order_status: e.target.value })} placeholder="Order Status" className="input w-32" />
        {activeFilterCount > 0 && <button onClick={clearFilters} className="btn text-xs"><X size={10} /> Clear</button>}
      </div>

      <div className="border border-border bg-white overflow-auto max-h-[calc(100vh-320px)] rounded-sm">
        <table className="w-full text-xs">
          <thead className="grid-header sticky top-0 z-10">
            <tr>
              <SortableTh label="Order ID" sortKey="order_id" sort={sort} onSort={onSort} className="frozen-col" />
              <SortableTh label="SKU" sortKey="sku" sort={sort} onSort={onSort} />
              <th className="grid-cell text-left">Status</th>
              <SortableTh label="Sub-Cat" sortKey="sub_category" sort={sort} onSort={onSort} />
              <SortableTh label="Zone" sortKey="zone" sort={sort} onSort={onSort} />
              <SortableTh label="Month" sortKey="month" sort={sort} onSort={onSort} />
              <SortableTh label="Qty" sortKey="qty" sort={sort} onSort={onSort} align="right" />
              <SortableTh label="MRP" sortKey="mrp" sort={sort} onSort={onSort} align="right" />
              <th className="grid-cell text-right">Discount</th>
              <SortableTh label="NSV" sortKey="nsv" sort={sort} onSort={onSort} align="right" />
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr><td colSpan={10} className="grid-cell text-center text-slate-400 py-10">No sales rows for this filter. Upload sales data or clear filters.</td></tr>
            ) : items.map((r) => (
              <tr key={r.id} onClick={() => openDrawer(r)} className="grid-row drill" data-testid={`sales-row-${r.id}`}>
                <td className="grid-cell frozen-col drill-link">{(r.online_order_id || "").slice(0, 14)}…</td>
                <td className="grid-cell">{r.sku}</td>
                <td className="grid-cell text-slate-500">{r.order_status}</td>
                <td className="grid-cell">{r.sub_category}</td>
                <td className="grid-cell text-slate-500">{r.zone}</td>
                <td className="grid-cell text-slate-500">{r.report_month}</td>
                <td className="grid-cell text-right">{fmtInt(r.qty)}</td>
                <td className="grid-cell text-right">{fmtCurrency(r.mrp)}</td>
                <td className="grid-cell text-right fin-neg">{fmtCurrency(r.customer_discount)}</td>
                <td className="grid-cell text-right">{fmtCurrency(r.nsv_val)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {drawer && (
        <div className="fixed inset-0 z-40" data-testid="sales-drawer">
          <div className="absolute inset-0 bg-black/30" onClick={() => setDrawer(null)} />
          <div className="absolute right-0 top-0 h-full w-full max-w-2xl bg-white border-l border-border overflow-auto">
            <div className="p-5 border-b border-border flex items-start justify-between">
              <div>
                <div className="overline">Order Detail</div>
                <div className="text-lg mt-1 mono text-slate-900">{drawer.online_order_id}</div>
                <div className="text-xs text-slate-500 mono">{drawer.sku}</div>
              </div>
              <button onClick={() => setDrawer(null)} className="btn" data-testid="close-drawer"><X size={14} /></button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <div className="overline mb-2">Sales Data</div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs mono border border-border p-3 rounded-sm">
                  {[["Category", drawer.category], ["Sub Category", drawer.sub_category], ["Zone", drawer.zone], ["Status", drawer.order_status],
                    ["Qty", drawer.qty], ["MRP", fmtCurrency(drawer.mrp)], ["Discount", fmtCurrency(drawer.customer_discount)],
                    ["NSV", fmtCurrency(drawer.nsv_val)], ["Month", drawer.report_month], ["Txn Type", drawer.txn_type]].map(([k, v]) => (
                    <div key={k} className="flex justify-between border-b border-border/50 py-1">
                      <span className="text-slate-500">{k}</span><span>{v ?? "—"}</span>
                    </div>
                  ))}
                </div>
              </div>
              {calc?.error ? (
                <div className="border border-amber-300 bg-amber-50 text-amber-700 p-3 text-xs mono rounded-sm">{calc.error}</div>
              ) : calc ? (
                <div>
                  <div className="overline mb-2">Expected Calculation</div>
                  <table className="w-full text-xs mono border border-border">
                    <tbody>
                      {[["Commission (ex GST)", calc.commission_base, "neg"],
                        ["GST on Commission (18%)", calc.commission_gst, "neg"],
                        ["Fixed Fee (ex GST)", calc.fixed_fee, "neg"],
                        ["GST on Fixed Fee (18%)", calc.fixed_fee_gst, "neg"],
                        ["GT Charge (incl GST)", calc.gt_charge, "neg"],
                        ["Return Fee (Level/Zone)", calc.return_fee, "neg"],
                        ["TCS", calc.tcs, "neg"], ["TDS", calc.tds, "neg"],
                        ["Total Deductions", calc.total_deductions, "neg", true],
                        ["Expected Settlement", calc.expected_settlement, "pos", true]].map(([k, v, tone, bold]) => (
                        <tr key={k}>
                          <td className={`px-3 py-2 border-b border-border/40 ${bold ? "font-semibold" : "text-slate-500"}`}>{k}</td>
                          <td className={`px-3 py-2 border-b border-border/40 text-right ${bold ? "font-semibold" : ""} ${tone === "neg" ? "fin-neg" : "fin-pos"}`}>{fmtCurrency(v)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-xs text-slate-400 mono">Loading calculation…</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
