import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import PeriodSelector from "@/components/PeriodSelector";
import StatChip from "@/components/StatChip";
import { fmtCurrency, fmtInt } from "@/lib/format";
import { Sparkles, RefreshCw, Gauge } from "lucide-react";
import { RadialBarChart, RadialBar, PolarAngleAxis, ResponsiveContainer } from "recharts";
import ReactMarkdown from "react-markdown";

const GRADE_COLOR = { A: "#059669", B: "#22C55E", C: "#F59E0B", D: "#EA580C", F: "#DC2626" };

export default function Insights() {
  const [searchParams] = useSearchParams();
  const [period, setPeriod] = useState({
    period_type: searchParams.get("period_type") || "month",
    period_value: searchParams.get("period_value") || "",
  });
  const [tone, setTone] = useState("executive");
  const [health, setHealth] = useState(null);
  const [brief, setBrief] = useState(null);
  const [loadingHealth, setLoadingHealth] = useState(false);
  const [loadingBrief, setLoadingBrief] = useState(false);

  const loadHealth = async () => {
    if (period.period_type !== "all" && !period.period_value) return;
    setLoadingHealth(true);
    try {
      const { data } = await api.get("/insights/health-score", {
        params: { period_type: period.period_type, period_value: period.period_value || undefined },
      });
      setHealth(data);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setLoadingHealth(false); }
  };

  const generateBrief = async () => {
    setLoadingBrief(true);
    try {
      const { data } = await api.post("/insights/morning-brief", {
        period_type: period.period_type,
        period_value: period.period_value || undefined,
        tone,
      });
      setBrief(data);
      toast.success(data.source === "llm" ? "AI brief generated" : "Rule-based brief generated");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setLoadingBrief(false); }
  };

  useEffect(() => { loadHealth(); setBrief(null); /* eslint-disable-next-line */ }, [period.period_type, period.period_value]);

  const h = health?.health;
  const gradeColor = h ? GRADE_COLOR[h.grade] || "#475569" : "#94A3B8";
  const gaugeData = h ? [{ name: "score", value: h.score, fill: gradeColor }] : [];

  return (
    <div className="p-6 space-y-5" data-testid="insights-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="overline">AI Finance Intelligence</div>
          <h1 className="text-2xl font-semibold tracking-tight mt-1 text-slate-900 flex items-center gap-2">
            <Sparkles size={18} className="text-indigo-500" /> Health Score &amp; Morning Brief
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Deterministic metrics + AI narrative. Numbers never fabricated — pulled from your uploaded reports only.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <PeriodSelector value={period} onChange={setPeriod} testIdPrefix="insights-period" />
          <button data-testid="btn-refresh-insights" onClick={loadHealth} disabled={loadingHealth} className="btn">
            <RefreshCw size={12} className={loadingHealth ? "animate-spin" : ""} /> Refresh
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <div className="border border-border bg-white p-5 rounded-sm flex flex-col items-center justify-center" data-testid="health-gauge">
          <div className="overline flex items-center gap-1"><Gauge size={12} /> Marketplace Health</div>
          <div className="w-56 h-56 relative">
            <ResponsiveContainer>
              <RadialBarChart innerRadius="70%" outerRadius="100%" data={gaugeData} startAngle={220} endAngle={-40}>
                <PolarAngleAxis type="number" domain={[0, 100]} angleAxisId={0} tick={false} />
                <RadialBar dataKey="value" cornerRadius={8} background={{ fill: "#F1F5F9" }} clockWise />
              </RadialBarChart>
            </ResponsiveContainer>
            <div className="absolute inset-0 flex items-center justify-center flex-col pointer-events-none">
              <div className="text-4xl font-semibold" style={{ color: gradeColor }} data-testid="health-score-value">
                {h ? h.score : "—"}
              </div>
              <div className="mono text-xs text-slate-500">/ 100</div>
              {h && <div className="mono text-lg mt-1" style={{ color: gradeColor }}>Grade {h.grade}</div>}
            </div>
          </div>
          {h && <div className="text-sm text-slate-600 text-center mt-2 max-w-xs" data-testid="health-headline">{h.headline}</div>}
        </div>

        <div className="lg:col-span-2 border border-border bg-white p-5 rounded-sm">
          <div className="overline">Component Scores</div>
          <div className="grid grid-cols-2 gap-3 mt-3">
            {[
              ["Mapping", h?.components?.mapping_health, "% of orders correctly mapped to rules"],
              ["Leakage", h?.components?.leakage_health, "Inverse of ₹ leaked as % of NSV"],
              ["Margin", h?.components?.margin_health, "Expected settlement / NSV"],
              ["Recovery", h?.components?.recovery_health, "₹ recovered / ₹ recoverable"],
            ].map(([label, val, hint]) => (
              <div key={label} className="border border-border p-3 rounded-sm" data-testid={`component-${label.toLowerCase()}`}>
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium text-slate-700">{label}</div>
                  <div className="mono text-lg font-semibold" style={{ color: val >= 75 ? "#059669" : val >= 50 ? "#F59E0B" : "#DC2626" }}>
                    {val != null ? val.toFixed(1) : "—"}
                  </div>
                </div>
                <div className="text-xs text-slate-500 mt-1">{hint}</div>
                <div className="mt-2 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${Math.max(0, Math.min(100, val || 0))}%`, background: val >= 75 ? "#059669" : val >= 50 ? "#F59E0B" : "#DC2626" }} />
                </div>
              </div>
            ))}
          </div>
          {h && (
            <div className="mt-4 grid grid-cols-3 gap-2 text-xs mono border-t border-border pt-3">
              <StatChip testId="stat-nsv" label="NSV" value={fmtCurrency(h.raw?.nsv)} />
              <StatChip testId="stat-recoverable" label="Recoverable" value={fmtCurrency(h.raw?.recoverable)} tone="warning" />
              <StatChip testId="stat-unmapped" label="Unmapped" value={fmtInt(h.raw?.unmapped)} sub={`of ${fmtInt(h.raw?.orders)} orders`} />
            </div>
          )}
        </div>
      </div>

      <div className="border border-border bg-white p-5 rounded-sm">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <div className="overline flex items-center gap-1"><Sparkles size={12} /> Morning Finance Brief</div>
            <div className="text-sm text-slate-500 mt-1">
              AI-generated narrative summarizing the numbers above. Never fabricated — quotes only real numbers from your uploads.
            </div>
          </div>
          <div className="flex items-center gap-2">
            <select data-testid="brief-tone" value={tone} onChange={(e) => setTone(e.target.value)} className="input text-xs">
              <option value="executive">Executive</option>
              <option value="operational">Operational</option>
              <option value="concise">Concise</option>
            </select>
            <button data-testid="btn-generate-brief" onClick={generateBrief} disabled={loadingBrief} className="btn btn-primary">
              <Sparkles size={12} /> {loadingBrief ? "Generating…" : brief ? "Regenerate" : "Generate brief"}
            </button>
          </div>
        </div>

        <div className="mt-4 border-t border-border pt-4">
          {brief ? (
            <div data-testid="brief-content">
              <div className="text-xs mono text-slate-500 mb-3 flex items-center gap-2">
                <span>Source: <span className="chip chip-neutral">{brief.source}</span></span>
                <span>· Period: {brief.label}</span>
              </div>
              <div className="prose prose-sm max-w-none prose-slate">
                <ReactMarkdown>{brief.narrative}</ReactMarkdown>
              </div>
            </div>
          ) : (
            <div className="text-center py-10 text-sm text-slate-400 mono">
              Click <span className="chip chip-neutral">Generate brief</span> to produce a Morning Finance Brief for {health?.label || "the selected period"}.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
