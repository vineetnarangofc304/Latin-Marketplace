export default function StatChip({ label, value, sub, tone = "neutral", testId, onClick, drillHint }) {
  const toneClass = {
    neutral: "border-border bg-white",
    positive: "border-emerald-200 bg-emerald-50/50",
    negative: "border-rose-200 bg-rose-50/50",
    warning: "border-amber-200 bg-amber-50/50",
    critical: "border-rose-300 bg-rose-50",
  }[tone];
  const valueClass = {
    neutral: "text-slate-900",
    positive: "text-emerald-700",
    negative: "text-rose-700",
    warning: "text-amber-700",
    critical: "text-rose-700",
  }[tone];
  const clickable = !!onClick;
  return (
    <div
      className={`border ${toneClass} p-4 rounded-sm ${clickable ? "cursor-pointer hover:shadow-sm hover:border-slate-400 transition" : ""}`}
      data-testid={testId}
      onClick={onClick}
      role={clickable ? "button" : undefined}
      tabIndex={clickable ? 0 : undefined}
    >
      <div className="flex items-start justify-between">
        <div className="overline">{label}</div>
        {clickable && drillHint ? (
          <span className="text-[9px] mono text-slate-400 uppercase tracking-widest">Drill →</span>
        ) : null}
      </div>
      <div className={`kpi-value mt-1.5 ${valueClass}`}>{value}</div>
      {sub ? <div className="text-xs text-slate-500 mt-1 mono">{sub}</div> : null}
    </div>
  );
}
