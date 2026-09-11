import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { fmtCurrency, fmtInt } from "@/lib/format";
import { toast } from "sonner";
import { FileWarning, Search, Mail, Copy, RefreshCw, X } from "lucide-react";

const STATUS_TONE = { open: "chip-warn", emailed: "chip-info", resolved: "chip-pos", rejected: "chip-neutral" };

export default function Claims() {
  const [items, setItems] = useState([]);
  const [summary, setSummary] = useState(null);
  const [status, setStatus] = useState("all");
  const [search, setSearch] = useState("");
  const [materiality, setMateriality] = useState(200);
  const [busy, setBusy] = useState(false);
  const [drawer, setDrawer] = useState(null);

  const load = async () => {
    const { data } = await api.get("/claims/breakage", { params: { status: status === "all" ? undefined : status, search: search || undefined, limit: 1000 } });
    setItems(data.items); setSummary(data.summary);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [status]);

  const scan = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/claims/breakage/scan", { materiality: Number(materiality) || 0 });
      toast.success(`${fmtInt(data.eligible_cases)} eligible cases · ${fmtCurrency(data.total_claim_value)} claimable`);
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || e.message); }
    finally { setBusy(false); }
  };

  const setCaseStatus = async (c, s) => {
    try { await api.patch(`/claims/breakage/${c.id}`, { status: s }); toast.success(`Marked ${s}`); await load(); if (drawer?.id === c.id) setDrawer({ ...c, status: s }); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail) || e.message); }
  };

  const copyEmail = async (c) => { await navigator.clipboard.writeText(`To: ${c.email_to}\nSubject: ${c.email_subject}\n\n${c.email_body}`); toast.success("Email copied"); };
  const mailto = (c) => `mailto:${encodeURIComponent(c.email_to)}?subject=${encodeURIComponent(c.email_subject)}&body=${encodeURIComponent(c.email_body)}`;

  return (
    <div className="p-6 space-y-4" data-testid="claims-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="overline">Recovery</div>
          <h1 className="text-2xl font-semibold tracking-tight mt-1 text-slate-900 flex items-center gap-2">
            <FileWarning size={18} className="text-rose-600" /> Breakage &amp; Lost-in-Return Claims
          </h1>
          <p className="text-sm text-slate-500 mt-1">Auto-detected from returns where the seller was net debited. Each case has a ready-to-send marketplace claim email.</p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <div className="overline mb-1">Materiality (₹)</div>
            <input data-testid="claims-materiality" type="number" value={materiality} onChange={(e) => setMateriality(e.target.value)} className="input w-28" />
          </div>
          <button data-testid="claims-scan-btn" onClick={scan} disabled={busy} className="btn btn-primary text-xs"><RefreshCw size={12} className={busy ? "animate-spin" : ""} /> {busy ? "Scanning…" : "Scan returns"}</button>
        </div>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="border border-border bg-white p-4 rounded-sm" data-testid="claims-kpi-cases"><div className="overline">Total Cases</div><div className="text-xl font-semibold mono mt-1">{fmtInt(summary.total_cases)}</div></div>
          <div className="border border-border bg-white p-4 rounded-sm" data-testid="claims-kpi-value"><div className="overline">Total Claim Value</div><div className="text-xl font-semibold mono mt-1 fin-pos">{fmtCurrency(summary.total_value)}</div></div>
          <div className="border border-border bg-white p-4 rounded-sm" data-testid="claims-kpi-open"><div className="overline">Open</div><div className="text-xl font-semibold mono mt-1">{fmtInt(summary.by_status?.open?.n || 0)}</div></div>
          <div className="border border-border bg-white p-4 rounded-sm" data-testid="claims-kpi-resolved"><div className="overline">Resolved</div><div className="text-xl font-semibold mono mt-1">{fmtInt(summary.by_status?.resolved?.n || 0)}</div></div>
        </div>
      )}

      <div className="flex items-center gap-2 flex-wrap">
        <select data-testid="claims-status-filter" value={status} onChange={(e) => setStatus(e.target.value)} className="input w-40">
          <option value="all">All statuses</option><option value="open">Open</option><option value="emailed">Emailed</option><option value="resolved">Resolved</option><option value="rejected">Rejected</option>
        </select>
        <div className="relative">
          <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
          <input data-testid="claims-search" value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()} placeholder="Search SKU / order" className="input pl-7 w-56" />
        </div>
      </div>

      <div className="border border-border bg-white overflow-auto max-h-[calc(100vh-380px)] rounded-sm">
        <table className="w-full text-xs">
          <thead className="grid-header sticky top-0 z-10"><tr>
            <th className="grid-cell text-left">Order ID</th>
            <th className="grid-cell text-left">SKU</th>
            <th className="grid-cell text-left">Category</th>
            <th className="grid-cell text-left">Month</th>
            <th className="grid-cell text-right">Item Value</th>
            <th className="grid-cell text-right">Claim Amount</th>
            <th className="grid-cell text-left">Status</th>
            <th className="grid-cell text-right">Action</th>
          </tr></thead>
          <tbody>
            {items.length === 0 ? (
              <tr><td colSpan={8} className="grid-cell text-center text-slate-400 py-10">No claims yet — set a materiality and click <b>Scan returns</b>.</td></tr>
            ) : items.map((c) => (
              <tr key={c.id} className="grid-row" data-testid={`claims-row-${c.id}`}>
                <td className="grid-cell mono">{c.online_order_id}</td>
                <td className="grid-cell mono">{c.sku}</td>
                <td className="grid-cell">{c.sub_category || "—"}</td>
                <td className="grid-cell mono">{c.report_month || "—"}</td>
                <td className="grid-cell text-right">{fmtCurrency(c.nsv)}</td>
                <td className="grid-cell text-right font-semibold fin-pos">{fmtCurrency(c.claim_amount)}</td>
                <td className="grid-cell"><span className={`chip ${STATUS_TONE[c.status] || "chip-neutral"}`}>{c.status}</span></td>
                <td className="grid-cell text-right"><button data-testid={`claims-view-${c.id}`} onClick={() => setDrawer(c)} className="btn text-xs"><Mail size={12} /> Email</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {drawer && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={() => setDrawer(null)}>
          <div className="w-full max-w-xl bg-white h-full overflow-auto p-5 space-y-4" onClick={(e) => e.stopPropagation()} data-testid="claim-drawer">
            <div className="flex items-center justify-between">
              <div className="overline">Claim Email · {drawer.online_order_id}</div>
              <button onClick={() => setDrawer(null)} className="btn text-xs"><X size={14} /></button>
            </div>
            <div className="text-xs text-slate-500">To: <span className="mono text-slate-800">{drawer.email_to}</span></div>
            <div className="text-sm font-medium text-slate-800">{drawer.email_subject}</div>
            <textarea data-testid="claim-email-body" readOnly value={drawer.email_body} className="input w-full h-72 text-xs mono" />
            <div className="flex items-center gap-2 flex-wrap">
              <button data-testid="claim-copy-btn" onClick={() => copyEmail(drawer)} className="btn text-xs"><Copy size={12} /> Copy</button>
              <a data-testid="claim-mailto" href={mailto(drawer)} className="btn btn-primary text-xs"><Mail size={12} /> Open in mail app</a>
              <button data-testid="claim-mark-emailed" onClick={() => setCaseStatus(drawer, "emailed")} className="btn text-xs">Mark emailed</button>
              <button data-testid="claim-mark-resolved" onClick={() => setCaseStatus(drawer, "resolved")} className="btn text-xs">Mark resolved</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
