import { useEffect, useRef, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { fmtCurrency, fmtInt } from "@/lib/format";
import { toast } from "sonner";
import { UploadCloud, Download, Trash2, Search, Coins } from "lucide-react";

export default function SkuCosts() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const inputRef = useRef();

  const load = async () => {
    const { data } = await api.get("/sku-costs", { params: { search: search || undefined, limit: 500 } });
    setItems(data.items);
    setTotal(data.total);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const doUpload = async (file) => {
    if (!file) return;
    setBusy(true);
    setResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/sku-costs/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setResult(data);
      toast.success(`${data.accepted_count} costs updated · ${data.rejected_count} rejected`);
      await load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || e.message);
    } finally { setBusy(false); }
  };

  const downloadTemplate = async () => {
    try {
      const res = await api.get("/sku-costs/template", { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = "sku-cost-template.xlsx"; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error("Template download failed"); }
  };

  const clearAll = async () => {
    if (!window.confirm("Delete ALL SKU costs?")) return;
    await api.delete("/sku-costs");
    await load();
    toast.success("Cleared");
  };

  return (
    <div className="p-6 space-y-5" data-testid="sku-costs-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="overline">Costing</div>
          <h1 className="text-2xl font-semibold tracking-tight mt-1 text-slate-900 flex items-center gap-2">
            <Coins size={18} className="text-amber-600" /> SKU Costs
          </h1>
          <p className="text-sm text-slate-500 mt-1">Upload per-SKU product cost. Used to compute SKU &amp; monthly P&amp;L. Re-uploading updates existing SKUs.</p>
        </div>
        <button data-testid="btn-download-template" onClick={downloadTemplate} className="btn text-xs"><Download size={12} /> Download template</button>
      </div>

      <div className="border border-border bg-white p-5 rounded-sm" data-testid="sku-cost-upload">
        <div className="overline">Upload SKU Cost Sheet</div>
        <div className="text-xs text-slate-500 mt-1">.xlsx or .csv with columns <b>SKU</b> and <b>Cost</b>.</div>
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); doUpload(e.dataTransfer.files?.[0]); }}
          className="mt-3 border border-dashed border-slate-300 p-8 text-center cursor-pointer rounded-sm hover:bg-slate-50"
          onClick={() => inputRef.current?.click()}
        >
          <UploadCloud size={28} className="mx-auto text-slate-400" strokeWidth={1.2} />
          <div className="mt-3 text-sm text-slate-700">{busy ? "Processing…" : "Drop .xlsx/.csv here or click to select"}</div>
          <input data-testid="sku-cost-input" ref={inputRef} type="file" accept=".xlsx,.xls,.csv" className="hidden" onChange={(e) => doUpload(e.target.files?.[0])} />
        </div>
        {result && (
          <div className="mt-3 text-xs mono border-t border-border pt-3">
            <span className="fin-pos">{result.accepted_count} updated</span>{" · "}
            <span className={result.rejected_count ? "fin-neg" : "text-slate-500"}>{result.rejected_count} rejected</span>{" · "}
            <span className="text-slate-500">{fmtInt(result.total_costs)} total on file</span>
          </div>
        )}
      </div>

      <div className="border border-border bg-white rounded-sm">
        <div className="flex items-center justify-between p-4 border-b border-border gap-2 flex-wrap">
          <div className="overline">Current Costs · {fmtInt(total)} SKUs</div>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
              <input data-testid="sku-cost-search" value={search} onChange={(e) => setSearch(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && load()} placeholder="Search SKU" className="input pl-7 w-52" />
            </div>
            <button data-testid="btn-clear-costs" onClick={clearAll} className="btn btn-danger text-xs"><Trash2 size={12} /> Clear all</button>
          </div>
        </div>
        <div className="overflow-auto max-h-[calc(100vh-420px)]">
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
