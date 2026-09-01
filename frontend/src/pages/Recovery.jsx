import { useEffect, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { fmtCurrency, fmtInt } from "@/lib/format";
import { toast } from "sonner";
import PeriodSelector from "@/components/PeriodSelector";
import StatChip from "@/components/StatChip";
import { SortableTh, nextDir } from "@/components/SortableTable";
import {
  Wallet, Wand2, RefreshCw, Search, X, Filter, Paperclip, Send, Trash2, Download, ChevronRight,
} from "lucide-react";

const STATUS_TONE = {
  open: "chip-high",
  in_review: "chip-variance",
  submitted: "chip-neutral",
  recovered: "chip-matched",
  rejected: "chip-unmatched",
  closed: "chip-neutral",
};

export default function Recovery() {
  const nav = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [period, setPeriod] = useState({
    period_type: searchParams.get("period_type") || "month",
    period_value: searchParams.get("period_value") || "",
  });
  const [summary, setSummary] = useState(null);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [filters, setFilters] = useState({
    status: searchParams.get("status") || "",
    priority: searchParams.get("priority") || "",
    severity: searchParams.get("severity") || "",
    search: "",
  });
  const [sort, setSort] = useState({ by: "recoverable_amount", dir: "desc" });
  const [drawer, setDrawer] = useState(null);
  const [autoBusy, setAutoBusy] = useState(false);

  const loadSummary = async () => {
    const { data } = await api.get("/recovery/summary", {
      params: { period_type: period.period_type, period_value: period.period_value || undefined },
    });
    setSummary(data);
  };
  const loadCases = async () => {
    const { data } = await api.get("/recovery/cases", {
      params: {
        period_type: period.period_type,
        period_value: period.period_value || undefined,
        status: filters.status || undefined,
        priority: filters.priority || undefined,
        severity: filters.severity || undefined,
        search: filters.search || undefined,
        sort_by: sort.by,
        sort_dir: sort.dir,
        limit: 500,
      },
    });
    setItems(data.items);
    setTotal(data.total);
  };

  useEffect(() => {
    loadSummary();
    loadCases();
    /* eslint-disable-next-line */
  }, [period.period_type, period.period_value, filters.status, filters.priority, filters.severity, sort.by, sort.dir]);

  const autoCreate = async () => {
    setAutoBusy(true);
    try {
      const { data } = await api.post("/recovery/cases/auto-create", {
        period_type: period.period_type,
        period_value: period.period_value || undefined,
        min_recoverable: 1,
        only_open: true,
      });
      toast.success(`${data.created} cases created · ${data.skipped} already tracked · ${data.candidates} candidates`);
      await Promise.all([loadCases(), loadSummary()]);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setAutoBusy(false);
    }
  };

  const onSort = (key) => setSort((s) => nextDir(s.by, s.dir, key));
  const clearFilters = () => {
    setFilters({ status: "", priority: "", severity: "", search: "" });
    setSearchParams({});
  };
  const activeFilterCount = Object.values(filters).filter(Boolean).length;

  const totals = summary?.totals || {};
  const coveragePct = summary?.case_coverage_pct || 0;

  return (
    <div className="p-6 space-y-4" data-testid="recovery-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="overline">Recovery Workbench</div>
          <h1 className="text-2xl font-semibold tracking-tight mt-1 text-slate-900 flex items-center gap-2">
            <Wallet size={18} className="text-emerald-600" /> Recovery Case Management
          </h1>
          <p className="text-sm text-slate-500 mt-1 mono">
            {fmtInt(total)} cases · Track each recoverable discrepancy through Myntra ticketing to closure.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <PeriodSelector value={period} onChange={setPeriod} testIdPrefix="rec-period" />
          <button data-testid="btn-auto-create" onClick={autoCreate} disabled={autoBusy} className="btn btn-primary">
            <Wand2 size={12} /> {autoBusy ? "Creating…" : "Auto-create cases"}
          </button>
          <button data-testid="btn-recovery-refresh" onClick={() => { loadCases(); loadSummary(); }} className="btn">
            <RefreshCw size={12} /> Refresh
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatChip testId="rec-kpi-cases" label="Open Cases" value={fmtInt(totals.total_cases)} sub={`${(coveragePct * 100).toFixed(0)}% of universe`} />
        <StatChip testId="rec-kpi-recoverable" label="Total Recoverable" value={fmtCurrency(totals.total_recoverable)} tone="warning" />
        <StatChip testId="rec-kpi-recovered" label="Recovered" value={fmtCurrency(totals.total_recovered)} tone="positive" />
        <StatChip testId="rec-kpi-universe" label="Discrepancy Universe" value={fmtInt(summary?.discrepancy_universe)} sub="Rows with ₹>0 recoverable" onClick={() => nav(`/discrepancies?period_type=${period.period_type}&period_value=${period.period_value || ""}`)} drillHint />
        <StatChip testId="rec-kpi-critical" label="Critical Priority" value={fmtInt((summary?.by_priority || []).find((p) => p.priority === "critical")?.count)} tone="critical" />
      </div>

      <div className="border border-border bg-white p-3 rounded-sm flex items-center gap-2 flex-wrap">
        <div className="inline-flex items-center gap-1 text-xs mono text-slate-500 pr-2 border-r border-border">
          <Filter size={12} /> Filters
          {activeFilterCount > 0 && <span className="chip chip-neutral text-[9px] py-0">{activeFilterCount}</span>}
        </div>
        <div className="relative">
          <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
          <input data-testid="rec-search" value={filters.search} onChange={(e) => setFilters({ ...filters, search: e.target.value })}
            onKeyDown={(e) => e.key === "Enter" && loadCases()}
            placeholder="Order / SKU" className="input pl-7 w-52" />
        </div>
        <select data-testid="rec-filter-status" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })} className="input">
          <option value="">All statuses</option>
          <option value="open">Open</option>
          <option value="in_review">In Review</option>
          <option value="submitted">Submitted</option>
          <option value="recovered">Recovered</option>
          <option value="rejected">Rejected</option>
          <option value="closed">Closed</option>
        </select>
        <select data-testid="rec-filter-priority" value={filters.priority} onChange={(e) => setFilters({ ...filters, priority: e.target.value })} className="input">
          <option value="">All priorities</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <select data-testid="rec-filter-severity" value={filters.severity} onChange={(e) => setFilters({ ...filters, severity: e.target.value })} className="input">
          <option value="">All severity</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        {activeFilterCount > 0 && <button onClick={clearFilters} className="btn text-xs"><X size={10} /> Clear</button>}
      </div>

      <div className="border border-border bg-white overflow-auto max-h-[calc(100vh-360px)] rounded-sm">
        <table className="w-full text-xs">
          <thead className="grid-header sticky top-0 z-10">
            <tr>
              <th className="grid-cell text-left">Priority</th>
              <SortableTh label="Order" sortKey="order_id" sort={sort} onSort={onSort} />
              <th className="grid-cell text-left">SKU</th>
              <th className="grid-cell text-left">Severity</th>
              <th className="grid-cell text-left">Status</th>
              <SortableTh label="Recoverable" sortKey="recoverable_amount" sort={sort} onSort={onSort} align="right" />
              <th className="grid-cell text-right">Recovered</th>
              <th className="grid-cell text-left">Assigned</th>
              <SortableTh label="Updated" sortKey="updated" sort={sort} onSort={onSort} />
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr><td colSpan={9} className="grid-cell text-center text-slate-400 py-10">
                No recovery cases for this period. Click <span className="mono">Auto-create</span> to open cases from open discrepancies.
              </td></tr>
            ) : items.map((c) => (
              <tr key={c.id} className="grid-row drill" data-testid={`rec-row-${c.id}`} onClick={() => setDrawer({ id: c.id })}>
                <td className="grid-cell"><span className={`chip chip-${c.priority}`}>{c.priority}</span></td>
                <td className="grid-cell drill-link">{(c.online_order_id || "").slice(0, 14)}…</td>
                <td className="grid-cell">{c.sku}</td>
                <td className="grid-cell"><span className={`chip chip-${c.severity}`}>{c.severity}</span></td>
                <td className="grid-cell"><span className={`chip ${STATUS_TONE[c.status] || "chip-neutral"}`}>{c.status}</span></td>
                <td className="grid-cell text-right fin-pos font-semibold">{fmtCurrency(c.recoverable_amount)}</td>
                <td className="grid-cell text-right">{c.recovered_amount ? fmtCurrency(c.recovered_amount) : "—"}</td>
                <td className="grid-cell text-slate-500">{c.assigned_to || "—"}</td>
                <td className="grid-cell text-slate-500 text-xs">{c.updated_at ? new Date(c.updated_at).toLocaleDateString() : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {drawer?.id && <CaseDrawer caseId={drawer.id} onClose={() => { setDrawer(null); loadCases(); loadSummary(); }} />}
    </div>
  );
}

function CaseDrawer({ caseId, onClose }) {
  const [detail, setDetail] = useState(null);
  const [notes, setNotes] = useState([]);
  const [evidence, setEvidence] = useState([]);
  const [note, setNote] = useState({ channel: "note", direction: "internal", subject: "", body: "" });
  const [saving, setSaving] = useState(false);
  const [statusForm, setStatusForm] = useState({ status: "", recovered_amount: "", resolution_notes: "", assigned_to: "" });

  const load = async () => {
    const { data } = await api.get(`/recovery/cases/${caseId}`);
    setDetail(data);
    setStatusForm({
      status: data.case.status,
      recovered_amount: data.case.recovered_amount || "",
      resolution_notes: data.case.resolution_notes || "",
      assigned_to: data.case.assigned_to || "",
    });
    const n = await api.get(`/recovery/cases/${caseId}/notes`);
    setNotes(n.data);
    const e = await api.get(`/recovery/cases/${caseId}/evidence`);
    setEvidence(e.data);
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [caseId]);

  const addNote = async () => {
    if (!note.body.trim()) return;
    setSaving(true);
    try {
      await api.post(`/recovery/cases/${caseId}/notes`, note);
      setNote({ ...note, subject: "", body: "" });
      await load();
      toast.success("Note added");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  const uploadFile = async (file) => {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      await api.post(`/recovery/cases/${caseId}/evidence`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Evidence uploaded");
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const downloadEvidence = async (ev) => {
    try {
      const res = await api.get(`/recovery/evidence/${ev.id}/download`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = ev.filename || "evidence";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) { toast.error("Download failed"); }
  };

  const deleteEvidence = async (ev) => {
    if (!window.confirm(`Delete ${ev.filename}?`)) return;
    await api.delete(`/recovery/evidence/${ev.id}`);
    await load();
  };

  const updateCase = async () => {
    setSaving(true);
    try {
      const payload = {};
      if (statusForm.status) payload.status = statusForm.status;
      if (statusForm.recovered_amount !== "") payload.recovered_amount = Number(statusForm.recovered_amount);
      if (statusForm.resolution_notes !== "") payload.resolution_notes = statusForm.resolution_notes;
      if (statusForm.assigned_to !== "") payload.assigned_to = statusForm.assigned_to;
      await api.patch(`/recovery/cases/${caseId}`, payload);
      toast.success("Case updated");
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  const c = detail?.case;

  return (
    <div className="fixed inset-0 z-40" data-testid="recovery-drawer">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="absolute right-0 top-0 h-full w-full max-w-3xl bg-white border-l border-border overflow-auto">
        <div className="p-5 border-b border-border flex items-start justify-between">
          <div>
            <div className="overline">Recovery Case</div>
            <div className="text-lg mt-1 mono text-slate-900">{c?.online_order_id || "…"}</div>
            <div className="text-xs text-slate-500 mono">{c?.sku}</div>
            {c && (
              <div className="mt-2 flex flex-wrap gap-2">
                <span className={`chip chip-${c.priority}`}>{c.priority} priority</span>
                <span className={`chip chip-${c.severity}`}>{c.severity} severity</span>
                <span className={`chip ${STATUS_TONE[c.status] || "chip-neutral"}`}>{c.status}</span>
              </div>
            )}
          </div>
          <button data-testid="close-recovery-drawer" onClick={onClose} className="btn"><X size={14} /></button>
        </div>

        {!c ? <div className="p-8 text-center text-slate-400 mono text-xs">Loading…</div> : (
        <div className="p-5 space-y-5">
          <div className="grid grid-cols-2 gap-3">
            <div className="border border-border p-3 rounded-sm">
              <div className="overline">Recoverable</div>
              <div className="fin-pos text-lg mono mt-1">{fmtCurrency(c.recoverable_amount)}</div>
            </div>
            <div className="border border-border p-3 rounded-sm">
              <div className="overline">Recovered so far</div>
              <div className="fin-pos text-lg mono mt-1">{fmtCurrency(c.recovered_amount)}</div>
            </div>
          </div>

          <div className="border border-border p-4 rounded-sm">
            <div className="overline">Discrepancy Context</div>
            <div className="text-sm mt-2">{c.reason}</div>
            <div className="text-xs mono text-slate-500 mt-1">Match status: {c.match_status} · Report month: {c.report_month}</div>
          </div>

          <div className="border border-border p-4 rounded-sm space-y-3" data-testid="case-update-form">
            <div className="overline">Update Case</div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <label className="space-y-1">
                <span className="overline">Status</span>
                <select data-testid="case-status-select" value={statusForm.status} onChange={(e) => setStatusForm({ ...statusForm, status: e.target.value })} className="input w-full">
                  {["open", "in_review", "submitted", "recovered", "rejected", "closed"].map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </label>
              <label className="space-y-1">
                <span className="overline">Assigned to</span>
                <input data-testid="case-assigned-input" value={statusForm.assigned_to} onChange={(e) => setStatusForm({ ...statusForm, assigned_to: e.target.value })} placeholder="Owner email" className="input w-full" />
              </label>
              <label className="space-y-1">
                <span className="overline">Recovered amount (₹)</span>
                <input data-testid="case-recovered-input" type="number" value={statusForm.recovered_amount} onChange={(e) => setStatusForm({ ...statusForm, recovered_amount: e.target.value })} className="input w-full mono" />
              </label>
              <label className="space-y-1 col-span-2">
                <span className="overline">Resolution notes</span>
                <textarea data-testid="case-resolution-notes" value={statusForm.resolution_notes} onChange={(e) => setStatusForm({ ...statusForm, resolution_notes: e.target.value })} rows={2} className="input w-full" />
              </label>
            </div>
            <button data-testid="btn-save-case" disabled={saving} onClick={updateCase} className="btn btn-primary text-xs">
              {saving ? "Saving…" : "Save"}
            </button>
          </div>

          <div>
            <div className="flex items-center justify-between">
              <div className="overline">Communication Log</div>
              <span className="text-xs mono text-slate-500">{notes.length} entries</span>
            </div>
            <div className="mt-2 space-y-2 max-h-72 overflow-auto">
              {notes.map((n) => (
                <div key={n.id} className="border border-border p-3 rounded-sm text-xs" data-testid={`note-${n.id}`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="chip chip-neutral">{n.channel}</span>
                      <span className="mono text-slate-500">{n.direction}</span>
                      {n.subject && <span className="text-slate-700 font-medium">{n.subject}</span>}
                    </div>
                    <span className="mono text-slate-400">{new Date(n.created_at).toLocaleString()}</span>
                  </div>
                  <div className="mt-1 text-slate-700 whitespace-pre-wrap">{n.body}</div>
                </div>
              ))}
              {notes.length === 0 && <div className="text-xs text-slate-400 mono">No entries yet.</div>}
            </div>
            <div className="mt-3 border border-border p-3 rounded-sm space-y-2">
              <div className="flex gap-2">
                <select data-testid="note-channel" value={note.channel} onChange={(e) => setNote({ ...note, channel: e.target.value })} className="input text-xs">
                  <option value="note">Note</option>
                  <option value="email">Email</option>
                  <option value="call">Call</option>
                  <option value="chat">Chat</option>
                  <option value="myntra_ticket">Myntra Ticket</option>
                </select>
                <select data-testid="note-direction" value={note.direction} onChange={(e) => setNote({ ...note, direction: e.target.value })} className="input text-xs">
                  <option value="internal">Internal</option>
                  <option value="outbound">Outbound</option>
                  <option value="inbound">Inbound</option>
                </select>
                <input data-testid="note-subject" value={note.subject} onChange={(e) => setNote({ ...note, subject: e.target.value })} placeholder="Subject (optional)" className="input text-xs flex-1" />
              </div>
              <textarea data-testid="note-body" value={note.body} onChange={(e) => setNote({ ...note, body: e.target.value })} rows={2} placeholder="Add note…" className="input w-full text-xs" />
              <button data-testid="btn-add-note" disabled={saving} onClick={addNote} className="btn btn-primary text-xs">
                <Send size={12} /> Add entry
              </button>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between">
              <div className="overline">Evidence</div>
              <label className="btn text-xs cursor-pointer" data-testid="btn-upload-evidence">
                <Paperclip size={12} /> Attach file
                <input data-testid="evidence-input" type="file" className="hidden" onChange={(e) => uploadFile(e.target.files?.[0])} />
              </label>
            </div>
            <div className="mt-2 space-y-1">
              {evidence.map((ev) => (
                <div key={ev.id} className="border border-border px-3 py-2 rounded-sm text-xs flex items-center justify-between" data-testid={`evidence-${ev.id}`}>
                  <div className="flex items-center gap-2 min-w-0">
                    <Paperclip size={12} className="text-slate-400 shrink-0" />
                    <div className="truncate">
                      <div className="font-medium text-slate-700 truncate">{ev.filename}</div>
                      <div className="mono text-slate-400">{Math.round((ev.size_bytes || 0) / 1024)} KB · {new Date(ev.uploaded_at).toLocaleString()}</div>
                    </div>
                  </div>
                  <div className="flex gap-1">
                    <button onClick={() => downloadEvidence(ev)} className="btn text-xs" data-testid={`btn-download-${ev.id}`}><Download size={12} /></button>
                    <button onClick={() => deleteEvidence(ev)} className="btn btn-danger text-xs" data-testid={`btn-delete-evidence-${ev.id}`}><Trash2 size={12} /></button>
                  </div>
                </div>
              ))}
              {evidence.length === 0 && <div className="text-xs text-slate-400 mono">No evidence attached.</div>}
            </div>
          </div>
        </div>
        )}
      </div>
    </div>
  );
}
