import { BookOpen, Scale, Calculator, GitCompareArrows } from "lucide-react";

const Section = ({ title, icon: Icon, children }) => (
  <div className="border border-border bg-white rounded-sm">
    <div className="px-4 py-3 border-b border-border flex items-center gap-2">
      {Icon && <Icon size={14} className="text-primary" />}
      <div className="overline">{title}</div>
    </div>
    <div className="p-4 space-y-3 text-sm text-slate-700">{children}</div>
  </div>
);

const F = ({ children }) => (
  <pre className="mono text-xs bg-slate-50 border border-border rounded-sm p-3 overflow-auto whitespace-pre-wrap">{children}</pre>
);

const Row = ({ k, v }) => (
  <div className="flex gap-3 py-1 border-b border-border/40 text-xs">
    <span className="mono text-slate-900 min-w-[220px]">{k}</span>
    <span className="text-slate-600">{v}</span>
  </div>
);

export default function Methodology() {
  return (
    <div className="p-6 space-y-4 max-w-4xl" data-testid="methodology-page">
      <div>
        <div className="overline flex items-center gap-2"><BookOpen size={12} /> Methodology</div>
        <h1 className="text-2xl font-semibold tracking-tight mt-1 text-slate-900">How every number is computed</h1>
        <p className="text-sm text-slate-500 mt-1">
          The exact formulas behind the Sales Ledger, Calculations and Discrepancies screens.
          Rates (GST 18%, TCS 0.5%, TDS 0.1%) are read from the Tax master — verify on Masters → Tax.
        </p>
      </div>

      <Section title="1 · Base inputs (per order-line)" icon={Calculator}>
        <Row k="Qty" v="quantity from source (defaults to 1 if blank)" />
        <Row k="NSV" v="net sales value for the line (absolute seller product amount)" />
        <Row k="ISP" v="net sales value per unit, else NSV ÷ Qty" />
        <Row k="Master Category" v="APPAREL / ACCESSORIES, normalised from the source category text" />
        <Row k="Level" v="looked up from the Sub-category → Level master" />
        <Row k="Zone" v="Local / Zonal / National (falls back to configured default zone if blank)" />
      </Section>

      <Section title="2 · Order-type classification">
        <Row k="order_status = RTO" v="→ rto — all fees nullified, settlement = 0" />
        <Row k="order_status = Internal Cancellation" v="→ internal_cancel — all fees nullified" />
        <Row k="Return + DTO" v="→ return_dto — only the Return Fee applies" />
        <Row k="Return (other status)" v="→ return — all components reversed, Return Fee added" />
        <Row k="everything else" v="→ sales — standard forward calculation" />
      </Section>

      <Section title="3 · Component formulas (Contract Engine → Calculations page)" icon={Calculator}>
        <div className="text-xs text-slate-500">GST = 0.18, TCS = 0.005, TDS = 0.001</div>
        <F>{`GT_total            = GT_unit_charge × Qty
NSV_after_GT        = NSV − GT_total          (base for commission, TCS, TDS)

Commission_base     = NSV_after_GT × Commission%
Commission_GST      = Commission_base × GST
Commission_incl_GST = Commission_base + Commission_GST

Fixed_Fee_GST       = Fixed_Fee_base × GST
Fixed_Fee_incl_GST  = Fixed_Fee_base + Fixed_Fee_GST

Return_Fee          = master fee for (level, zone)   # returns only
TCS                 = NSV_after_GT × TCS
TDS                 = NSV_after_GT × TDS`}</F>
        <div className="font-medium text-slate-800 pt-1">Expected Settlement</div>
        <F>{`SALES        Expected = NSV − (Commission + Fixed + GT_total + TCS + TDS)
RETURN       all components sign-flipped; Return Fee added
RETURN+DTO   Expected = −|NSV| − Return_Fee   (others = 0)
RTO / CANCEL Expected = 0                     (everything nullified)`}</F>
      </Section>

      <Section title="4 · Actuals (from Myntra payout files)">
        <p className="text-xs">
          Each order-line can appear as a <b>Forward</b> (sale) row and a <b>Reverse</b> (return) row.
          Actuals are the <b>sum across all payout rows</b> for the line:
        </p>
        <F>{`settled_commission = Σ Commission
settled_fixed_fee  = Σ fixed_fee
settled_gt_charge  = Σ Logistics_Commission
settled_tcs        = Σ (IGST_TCS + CGST_TCS + SGST_TCS)
settled_tds        = Σ TDS
settled_amount     = Σ Settled_Amount        # NET of Forward + Reverse`}</F>
      </Section>

      <Section title="5 · Reconciliation — two bases (toggle on Discrepancies)" icon={Scale}>
        <div className="grid md:grid-cols-2 gap-3">
          <div className="border border-border rounded-sm p-3">
            <div className="font-semibold text-slate-800 text-sm">Settlement basis <span className="chip chip-matched text-[9px]">default</span></div>
            <p className="text-xs mt-1 text-slate-600">
              Expected = <b>Myntra's own invoiced figures</b> from the order file
              (netted across legs). Catches payout errors — did Myntra pay what its own invoice said?
            </p>
            <F>{`Expected commission = Σ |order-file commission|
Expected fixed/gt/tcs/tds = Σ |order-file value|
Expected settlement = Σ total_actual_settlement`}</F>
          </div>
          <div className="border border-border rounded-sm p-3">
            <div className="font-semibold text-slate-800 text-sm">Contract-audit basis</div>
            <p className="text-xs mt-1 text-slate-600">
              Expected = <b>your negotiated contract rates</b> (the Contract Engine, netted across legs).
              Catches contract overcharges — did Myntra charge per contract?
            </p>
            <F>{`Expected = contract-engine values
(Commission%, Fixed Fee, GT, Return Fee
 from your Masters), netted across legs`}</F>
          </div>
        </div>
      </Section>

      <Section title="6 · Variance, recoverable & severity" icon={GitCompareArrows}>
        <F>{`Variance = Actual − Expected     (per component)

matched      |Variance| ≤ ₹1  OR  ≤ 0.5% of Expected
overcharged  Variance > 0   → recoverable
undercharged Variance < 0

Recoverable = Σ (over-charged variances)

Severity by |recoverable| (materiality ₹100):
  critical ≥ ₹1,000   high ≥ ₹300   medium ≥ ₹100   low otherwise

Row status:
  matched    every component + net settlement matched
  variance   any component/settlement differs
  unmatched  no sales/calc row, or expected calc is unmapped`}</F>
      </Section>

      <Section title="7 · Tunable settings (Masters)">
        <Row k="absolute_inr = ₹1.00" v="variance ≤ this → matched" />
        <Row k="percentage = 0.5%" v="variance within this % of expected → matched" />
        <Row k="materiality_inr = ₹100" v="base threshold for severity buckets" />
        <Row k="gst_rate = 0.18 · tcs_rate = 0.005 · tds_rate = 0.001" v="tax rates applied above" />
        <Row k="default_zone_when_missing" v="zone applied when the row's zone is blank" />
      </Section>
    </div>
  );
}
