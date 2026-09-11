import { useEffect, useRef, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { fmtCurrency, fmtInt } from "@/lib/format";
import { toast } from "sonner";
import { UploadCloud, Download, Trash2, Search, Coins, Megaphone } from "lucide-react";

function Uploader({ testId, onFile, busy, hint }) {
  const ref = useRef();
  return (
    <div
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => { e.preventDefault(); onFile(e.dataTransfer.files?.[0]); }}
      className="border border-dashed border-slate-300 p-6 text-center cursor-pointer rounded-sm hover:bg-slate-50"
      onClick={() => ref.current?.click()}
    >
      <UploadCloud size={24} className="mx-auto text-slate-400" strokeWidth={1.2} />
      <div className="mt-2 text-sm text-slate-700">{busy ? "Processing…" : "Drop .xlsx/.csv or click to select"}</div>
      <div className="text-xs text-slate-400 mt-1">{hint}</div>
      <input data-testid={testId} ref={ref} type="file" accept=".xlsx,.xls,.csv" className="hidden" onChange={(e) => onFile(e.target.files?.[0])} />
    </div>
  );
}

export default function SkuCosts() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [ad, setAd] = useState({ items: [], total_spend: 0 });
  const [adBusy, setAdBusy] = useState(false);

  const load = async () => {
    const [{ data }, adRes] = await Promise.all([
      api.get("/sku-costs", { params: { search: search || undefined, limit: 500 } }),
      api.get("/ad-spend"),
    ]);
    setItems(data.items); setTotal(data.total); setAd(adRes.data);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const upload = async (url, file, setB) => {
    if (!file) return;
    setB(true);
    try {
      const fd = new FormData(); fd.append("file", file);
      const { data } = await api.post(url, fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(`${fmtInt(data.accepted_count)} rows saved`);
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || e.message); }
    finally { setB(false); }
  };

  const dlTemplate = async (url, name) => {
    try {
      const res = await api.get(url, { responseType: "blob" });
      const u = URL.createObjectURL(res.data); const a = document.createElement("a");
      a.href = u; a.download = name; a.click(); URL.revokeObjectURL(u);
    } catch { toast.error("Template download failed"); }
  };

  const clearCosts = async () => { if (!window.confirm("Delete ALL SKU costs?")) return; await api.delete("/sku-costs"); await load(); toast.success("Cleared"); };

  return (
    <div className="p-6 space-y-5" data-testid="sku-costs-page">
      <div>
        <div className="overline">Costing Inputs</div>
        <h1 className="text-2xl font-semibold tracking-tight mt-1 text-slate-900 flex items-center gap-2">
          <Coins size={18} className="text-amber-600" /> SKU Costs &amp; Ad Spend
        </h1>
        <p className="text-sm text-slate-500 mt-1">Feed product cost (per SKU) and ad/marketing spend (per month) into P&amp;L.</p>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="border border-border bg-white p-5 rounded-sm" data-testid="sku-cost-upload">
          <div className="flex items-center justify-between">
            <div className="overline flex items-center gap-1"><Coins size={12} /> SKU Product Cost</div>
            <button data-testid="btn-download-template" onClick={() => dlTemplate("/sku-costs/template", "sku-cost-template.xlsx")} className="btn text-xs"><Download size={12} /> Template</button>
          </div>
          <div className="text-xs text-slate-500 mt-1 mb-3">Columns: <b>SKU</b>, <b>Cost</b>.</div>
          <Uploader testId="sku-cost-input" busy={busy} hint="Updates existing SKUs" onFile={(f) => upload("/sku-costs/upload", f, setBusy)} />
        </div>

        <div className="border border-border bg-white p-5 rounded-sm" data-testid="ad-spend-upload">
          <div className="flex items-center justify-between">
            <div className="overline flex items-center gap-1"><Megaphone size={12} /> Monthly Ad / Marketing Spend</div>
            <button data-testid="btn-ad-template" onClick={() => dlTemplate("/ad-spend/template", "ad-spend-template.xlsx")} className="btn text-xs"><Download size={12} /> Template</button>
          </div>
          <div className="text-xs text-slate-500 mt-1 mb-3">Columns: <b>Month</b> (YYYY-MM), <b>Amount</b>. Total on file: <b>{fmtCurrency(ad.total_spend)}</b></div>
          <Uploader testId="ad-spend-input" busy={adBusy} hint="Feeds Net Contribution in P&L" onFile={(f) => upload("/ad-spend/upload", f, setAdBusy)} />
          {ad.items?.length > 0 && (
            <div className="mt-3 max-h-32 overflow-auto border-t border-border pt-2">
              {ad.items.map((a) => (
                <div key={a.report_month} className="flex justify-between text-xs py-0.5 mono" data-testid={`ad-row-${a.report_month}`}>
                  <span>{a.report_month}</span><span>{fmtCurrency(a.amount)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="border border-border bg-white rounded-sm">
        <div className="flex items-center justify-between p-4 border-b border-border gap-2 flex-wrap">
          <div className="overline">Current SKU Costs · {fmtInt(total)} SKUs</div>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
              <input data-testid="sku-cost-search" value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()} placeholder="Search SKU" className="input pl-7 w-52" />
            </div>
            <button data-testid="btn-clear-costs" onClick={clearCosts} className="btn btn-danger text-xs"><Trash2 size={12} /> Clear all</button>
          </div>
        </div>
        <div className="overflow-auto max-h-[calc(100vh-460px)]">
          <table className="w-full text-sm">
            <thead className="grid-header sticky top-0"><tr>
              <th className="grid-cell text-left">SKU</th>
              <th className="grid-cell text-right">Cost</th>
              <th className="grid-cell text-left">Updated</th>
            </tr></thead>
            <tbody>
              {items.length === 0 ? (
                <tr><td colSpan={3} className="grid-cell text-center text-slate-400 py-8">No SKU costs yet — upload a sheet above.</td></tr>
              ) : items.map((c) => (
                <tr key={c.sku} className="grid-row" data-testid={`sku-cost-row-${c.sku}`}>
                  <td className="grid-cell mono">{c.sku}</td>
                  <td className="grid-cell text-right">{fmtCurrency(c.cost)}</td>
                  <td className="grid-cell text-xs text-slate-500">{c.updated_at ? new Date(c.updated_at).toLocaleDateString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
