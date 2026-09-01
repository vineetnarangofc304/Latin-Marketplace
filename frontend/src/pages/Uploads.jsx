import { useEffect, useRef, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { UploadCloud, FileSpreadsheet, Trash2, PlayCircle } from "lucide-react";
import { toast } from "sonner";
import { fmtInt } from "@/lib/format";

function UploadDrop({ kind, label, hint, onUploaded }) {
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const inputRef = useRef();

  const doUpload = async (file) => {
    if (!file) return;
    setBusy(true);
    setResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post(`/uploads/${kind}`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(data);
      toast.success(`${file.name}: ${data.accepted_count} accepted, ${data.rejected_count} rejected`);
      onUploaded?.(data);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border border-border bg-white p-5 rounded-sm" data-testid={`upload-drop-${kind}`}>
      <div className="overline">{label}</div>
      {hint && <div className="text-xs text-slate-500 mt-1">{hint}</div>}
      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); doUpload(e.dataTransfer.files?.[0]); }}
        className={`mt-3 border border-dashed ${drag ? "border-slate-500 bg-slate-50" : "border-slate-300"} p-8 text-center cursor-pointer rounded-sm hover:bg-slate-50`}
        onClick={() => inputRef.current?.click()}
      >
        <UploadCloud size={28} className="mx-auto text-slate-400" strokeWidth={1.2} />
        <div className="mt-3 text-sm text-slate-700">{busy ? "Processing…" : "Drop .xlsx here or click to select"}</div>
        <div className="overline mt-1">Myntra {label}</div>
        <input data-testid={`upload-input-${kind}`} ref={inputRef} type="file" accept=".xlsx,.xls" className="hidden" onChange={(e) => doUpload(e.target.files?.[0])} />
      </div>
      {result ? (
        <div className="mt-3 text-xs mono border-t border-border pt-3 space-y-0.5">
          <div>File: <span className="text-slate-500">{result.filename}</span></div>
          <div>Sheet: <span className="text-slate-500">{result.sheet}</span></div>
          <div>
            <span className="fin-pos">{result.accepted_count} accepted</span>
            {" · "}
            <span className={result.rejected_count ? "fin-neg" : "text-slate-500"}>{result.rejected_count} rejected</span>
          </div>
          {result.months && Object.keys(result.months).length > 0 && (
            <div>Months: {Object.entries(result.months).map(([m, n]) => <span key={m} className="chip chip-neutral mr-1">{m} · {n}</span>)}</div>
          )}
        </div>
      ) : null}
    </div>
  );
}

export default function Uploads() {
  const [uploads, setUploads] = useState([]);
  const [running, setRunning] = useState(false);

  const refresh = async () => {
    const { data } = await api.get("/uploads");
    setUploads(data);
  };
  useEffect(() => { refresh(); }, []);

  const deleteUpload = async (id) => {
    if (!window.confirm("Delete this upload and its data?")) return;
    await api.delete(`/uploads/${id}`);
    await refresh();
    toast.success("Deleted");
  };

  const runCalcs = async (upload_id) => {
    setRunning(true);
    try {
      const { data } = await api.post("/calculations/run", { upload_id, recalculate: true });
      toast.success(`${data.fully_mapped_count} mapped · ${data.unmapped_count} unmapped`);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="p-6 space-y-5" data-testid="uploads-page">
      <div>
        <div className="overline">Ingestion</div>
        <h1 className="text-2xl font-semibold tracking-tight mt-1 text-slate-900">Upload Marketplace Reports</h1>
        <p className="text-sm text-slate-500 mt-1">
          Every upload is auto-tagged with its report month (from the Month / Posting Date columns). Repeat monthly.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <UploadDrop kind="sales" label="Sales Data" hint="Myntra Raw Online Sale sheet — one row per order-item" onUploaded={refresh} />
        <UploadDrop kind="settlement" label="Settlement / Commission Report" hint="Myntra payout / settlement report for the same month" onUploaded={refresh} />
      </div>

      <div className="border border-border bg-white rounded-sm">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="overline">Upload History</div>
          <div className="text-xs mono text-slate-500">{uploads.length} uploads</div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="grid-header">
              <tr>
                <th className="grid-cell text-left">Type</th>
                <th className="grid-cell text-left">Filename</th>
                <th className="grid-cell text-left">Months</th>
                <th className="grid-cell text-left">Uploaded</th>
                <th className="grid-cell text-right">Accepted</th>
                <th className="grid-cell text-right">Rejected</th>
                <th className="grid-cell text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {uploads.length === 0 ? (
                <tr><td colSpan={7} className="grid-cell text-center text-slate-400 py-8">No uploads yet</td></tr>
              ) : uploads.map((u) => (
                <tr key={u.id} className="grid-row" data-testid={`upload-row-${u.id}`}>
                  <td className="grid-cell"><span className="inline-flex items-center gap-1"><FileSpreadsheet size={12} /> {u.type}</span></td>
                  <td className="grid-cell truncate max-w-[280px]">{u.filename}</td>
                  <td className="grid-cell text-xs">{u.months ? Object.keys(u.months).join(", ") : "—"}</td>
                  <td className="grid-cell text-xs text-slate-500">{new Date(u.uploaded_at).toLocaleString()}</td>
                  <td className="grid-cell text-right fin-pos">{fmtInt(u.accepted_count)}</td>
                  <td className="grid-cell text-right fin-neg">{fmtInt(u.rejected_count)}</td>
                  <td className="grid-cell text-right">
                    <div className="inline-flex items-center gap-2">
                      {u.type === "sales" ? (
                        <button disabled={running} onClick={() => runCalcs(u.id)} data-testid={`btn-run-calc-${u.id}`} className="btn text-xs">
                          <PlayCircle size={12} /> Run Calc
                        </button>
                      ) : null}
                      <button onClick={() => deleteUpload(u.id)} data-testid={`btn-delete-upload-${u.id}`} className="btn btn-danger text-xs">
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
