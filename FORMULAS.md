# Latin Quarter — Marketplace OS: Calculation & Reconciliation Formulas

This document publishes **every formula** used to compute each column across the
Sales Ledger, Calculations, and Discrepancies screens. It is the single source of
truth for "how each number is derived".

- **Expected** figures are computed by the **Contract Engine** (`backend/routers/calculations.py :: compute_expected`) from Latin Quarter's negotiated contract masters.
- **Actual** figures come from Myntra's **payout files** (`backend/latin_loader.py :: load_payouts`).
- **Discrepancies** compare Expected vs Actual (`backend/routers/reconciliation.py`).

All GST/TCS/TDS rates are read from the `tax_rates` master (not hard-coded).
Current values: **GST = 18%**, **TCS = 0.5%**, **TDS = 0.1%** (verify on Masters → Tax).

---

## 1. Base inputs (per order-line)

| Column | Formula |
|---|---|
| **Qty** | `qty` from source (defaults to 1 if blank) |
| **NSV** (Net Sales Value) | `nsv_val` = absolute seller product amount for the line |
| **ISP** (Item Selling Price) | `nsv_per_unit` if present, else `NSV ÷ Qty` |
| **Master Category** | `APPAREL` if source category contains "APPAREL"; `ACCESSORIES` if it contains "ACCESS"/"DETAIL"; else *unmapped* |
| **Level** | looked up from `subcat_levels` master by Sub-Category (case-insensitive) |
| **Zone** | normalized to Local / Zonal / National; if missing and a default zone is configured in Settlement Settings, that default is applied |

---

## 2. Order-type classification

Each row is classified from `order_status` + `txn_type`:

| Condition | Type | Effect |
|---|---|---|
| `order_status = RTO` | **rto** | All fees nullified → settlement = 0 |
| `order_status = Internal Cancellation` | **internal_cancel** | All fees nullified → settlement = 0 |
| `txn_type = Return` **and** `order_status = DTO` | **return_dto** | Only the Return Fee applies |
| `txn_type = Return` (any other status) | **return** | All components reversed (sign-flipped); Return Fee added |
| everything else | **sales** | Standard forward calculation |

---

## 3. Master-rate matching (strict, no fallback)

| Rate | Matched on |
|---|---|
| **Commission %** | `master_category` + `sub_category` + `ISP ∈ [lower_limit, upper_limit]` |
| **Fixed Fee** | `sub_category` + `ISP ∈ [aisp_lower, aisp_upper]` |
| **GT (logistics) unit charge** | `sub_category` + `level` + `ISP ∈ [price_lower, price_upper]` |
| **Return Fee** | `level` + `zone` |

If any required rate is missing, that component is left `NULL` and the row is flagged
`unmapped` (it appears as *unmatched* in the Discrepancy workbench until the master is fixed).

---

## 4. Component formulas

Let `GST = 0.18`, `TCS = 0.005`, `TDS = 0.001`.

### 4.1 GT (Grand Total / logistics) charge
```
GT_total = GT_unit_charge × Qty
```

### 4.2 NSV after GT  (the base for commission, TCS, TDS)
```
NSV_after_GT = NSV − GT_total
```

### 4.3 Commission
```
Commission_base     = NSV_after_GT × Commission%
Commission_GST      = Commission_base × GST
Commission_incl_GST = Commission_base + Commission_GST
```

### 4.4 Fixed Fee
```
Fixed_Fee_base      = master Fixed Fee for the slab
Fixed_Fee_GST       = Fixed_Fee_base × GST
Fixed_Fee_incl_GST  = Fixed_Fee_base + Fixed_Fee_GST
```

### 4.5 Return Fee
```
Return_Fee = master fee for (level, zone)     # applied only on return / return_dto
```

### 4.6 Taxes
```
TCS = NSV_after_GT × TCS_rate
TDS = NSV_after_GT × TDS_rate
```

---

## 5. Settlement (per order-type)

### 5.1 SALES
```
NSV_after_GT       = NSV − GT_total
Total_Deductions   = Commission_incl_GST + Fixed_Fee_incl_GST + GT_total + TCS + TDS
Expected_Settlement = NSV − Total_Deductions
```

### 5.2 RETURN  (all components sign-flipped)
```
Signed_NSV         = −|NSV|
GT_charge          = −GT_total
NSV_after_GT       = Signed_NSV − GT_charge          (= Signed_NSV + GT_total)
Commission_incl_GST, Fixed_Fee_incl_GST, TCS, TDS  computed on NSV_after_GT (negative)
Return_Fee added as a new positive charge
Expected_Settlement = Signed_NSV − (Commission + Fixed + GT_charge + Return_Fee + TCS + TDS)
```

### 5.3 RETURN + DTO  (only the Return Fee applies)
```
Expected_Settlement = −|NSV| − Return_Fee
(all other components = 0)
```

### 5.4 RTO / INTERNAL CANCELLATION
```
Every component = 0  →  Expected_Settlement = 0
```

---

## 6. Actual (Myntra payout) columns

Each order-line can appear as **multiple payout rows** — a **Forward** (sale) row and
a **Reverse** (return) row. Actuals are the **sum across all payout rows** for the line:

```
settled_commission = Σ Commission
settled_fixed_fee  = Σ fixed_fee
settled_gt_charge  = Σ Logistics_Commission
settled_tcs        = Σ (IGST_TCS + CGST_TCS + SGST_TCS)
settled_tds        = Σ TDS
settled_amount     = Σ Settled_Amount      # this is the NET of Forward + Reverse
```

---

## 7. Reconciliation (Expected vs Actual)

Because `settled_amount` is already the **net** of Forward+Reverse, the Expected side is
**netted the same way**: for a returned line with two legs (a sale leg + a return leg),
the expected components are summed across both legs before comparison.

For every component (commission, fixed_fee, gt_charge, return_fee, tcs, tds, net_settlement):

```
Variance = Actual − Expected
```

### 7.1 Match status (per component)
```
matched      if |Variance| ≤ absolute_tolerance (₹1 default)
             OR (|Variance| ÷ |Expected|) × 100 ≤ percentage_tolerance (0.5% default)
overcharged  if Variance > 0   (Myntra deducted MORE than expected → recoverable)
undercharged if Variance < 0
```

### 7.2 Recoverable
```
Recoverable = Σ (Variance where Variance > 0)      # sum of over-charged components
```

### 7.3 Severity (by |recoverable|, materiality ₹100 default)
```
critical  if ≥ 10 × materiality   (₹1,000)
high      if ≥  3 × materiality   (₹300)
medium    if ≥  1 × materiality   (₹100)
low       otherwise
```

### 7.4 Row status
```
matched   if every component matched AND net_settlement matched
variance  if any component/settlement differs
unmatched if no sales/calculation row exists, or the expected calc is unmapped
```

---

## 8. Tunable settings (Masters screen)

| Setting | Default | Meaning |
|---|---|---|
| `absolute_inr` | ₹1.00 | Any variance ≤ this is treated as matched |
| `percentage` | 0.5% | Any variance within this % of expected is matched |
| `materiality_inr` | ₹100 | Base threshold for severity buckets |
| `gst_rate` | 0.18 | GST on commission & fixed fee |
| `tcs_rate` | 0.005 | TCS on NSV-after-GT |
| `tds_rate` | 0.001 | TDS on NSV-after-GT |
| `default_zone_when_missing` | (config) | Zone applied when the row's zone is blank |
