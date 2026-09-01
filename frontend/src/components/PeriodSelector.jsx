import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Calendar } from "lucide-react";

/**
 * Period selector supporting: All, Month, Quarter, Year, YTD.
 * Value shape: { period_type, period_value }.
 */
export default function PeriodSelector({ value, onChange, testIdPrefix = "period", allowAll = true }) {
  const [periods, setPeriods] = useState({ months: [], quarters: [], years: [] });
  const [type, setType] = useState(value?.period_type || "month");
  const [pval, setPval] = useState(value?.period_value || "");

  useEffect(() => {
    api.get("/reports/periods").then((r) => {
      setPeriods(r.data);
      // Auto-select latest month by default
      if (!value?.period_value && r.data.months?.length) {
        const latest = r.data.months[r.data.months.length - 1];
        setPval(latest);
        onChange?.({ period_type: "month", period_value: latest });
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setType(value?.period_type || "month");
    setPval(value?.period_value || "");
  }, [value?.period_type, value?.period_value]);

  const setBoth = (t, v) => {
    setType(t);
    setPval(v);
    onChange?.({ period_type: t, period_value: v });
  };

  const options = type === "month" ? periods.months
    : type === "quarter" ? periods.quarters
    : type === "year" ? periods.years
    : type === "ytd" ? periods.years : [];

  return (
    <div className="inline-flex items-center border border-border bg-white rounded-sm overflow-hidden" data-testid={`${testIdPrefix}-selector`}>
      <div className="pl-2.5 pr-1 text-slate-400"><Calendar size={12} /></div>
      <select
        data-testid={`${testIdPrefix}-type`}
        value={type}
        onChange={(e) => {
          const newType = e.target.value;
          if (newType === "all") {
            setBoth("all", "");
          } else {
            // Pick default for that type
            const list = newType === "month" ? periods.months
              : newType === "quarter" ? periods.quarters
              : newType === "year" ? periods.years
              : newType === "ytd" ? periods.years : [];
            const defaultVal = list?.length ? list[list.length - 1] : "";
            setBoth(newType, defaultVal);
          }
        }}
        className="text-xs mono px-2 py-2 outline-none bg-transparent border-r border-border"
      >
        <option value="month">Month</option>
        <option value="quarter">Quarter</option>
        <option value="year">Year</option>
        <option value="ytd">YTD</option>
        {allowAll && <option value="all">All</option>}
      </select>
      {type !== "all" && (
        <select
          data-testid={`${testIdPrefix}-value`}
          value={pval}
          onChange={(e) => setBoth(type, e.target.value)}
          className="text-xs mono px-2 py-2 outline-none bg-transparent min-w-[100px]"
        >
          <option value="">Select…</option>
          {options.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      )}
    </div>
  );
}
