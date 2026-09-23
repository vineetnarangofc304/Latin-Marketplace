# Replication prompt — "Story At Home" Marketplace AutoPilot (fork of Latin Quarter)

Paste everything in the block below into a **new Emergent project** to reproduce this app for the brand **Story At Home**.

---

BUILD BRIEF — clone an existing app from GitHub and rebrand it for a new tenant.

## 1. Source
Pull the complete codebase from this **public GitHub repo** and reproduce it exactly as the starting point:

    <PASTE_YOUR_PUBLIC_GITHUB_REPO_URL_HERE>

It is a working **FastAPI + React + MongoDB** "Marketplace AutoPilot" — it ingests a marketplace's order + payout files, computes expected charges from the brand's contract, reconciles them against actual settlements, surfaces recoverable discrepancies, and manages recovery cases. Reproduce the full app first (all backend routers + all frontend pages) and get it running, THEN apply the rebrand and clean-seed below. Do **not** redesign or refactor — keep the architecture and logic identical.

## 2. What the app contains (reproduce all of it)
Backend (`/app/backend`, FastAPI + Motor async Mongo):
- `server.py` (JWT auth, admin/marketing seed, indexes, startup bootstrap), `deps.py`, `db.py`, `period_utils.py`, `cache_utils.py`
- `routers/`: `uploads_r.py` (sales + settlement upload/list), `calculations.py` (strict contract calc engine — no fallbacks, `unmapped` flagging), `reconciliation.py` (component-level compare with **dual basis** — see §5), `dashboards.py`, `reports.py` (monthly JSON + Excel export), `recovery.py` (recovery cases), `insights.py` (AI morning brief via Emergent LLM key), `masters.py` (commission/fixed/GT/return/level/tax/tolerance/settlement-settings), `pnl.py` (SKU cost + P&L), `claims.py` (breakage claim drafting), `sku`/ad-spend upload
- Data pipeline: `latin_loader.py` (marketplace raw-file loader), `derive_masters.py` (derives GT + return-fee matrices from the data and writes a masters seed JSON), `reingest_all.py` (orchestrates masters → orders → derive → calc → payouts → reconciliation)
- `FORMULAS.md` (methodology) — also surfaced in-app

Frontend (`/app/frontend`, React + Tailwind + shadcn/ui + recharts):
- Pages: Login, Overview, AI Insights, Reports, P&L, Uploads, SKU Costs, Claims, Sales Ledger, Calculations, Reconciliation, Discrepancies, Recovery, Masters, **Methodology**
- `components/Layout.jsx` (sidebar nav + branding), `App.js` (routes)

Mongo collections: `users, uploads, sales, settlement, calculations, discrepancies, recon_runs, commission_rules, fixed_fees, gt_charges, return_fees, subcat_levels, tolerances, tax_rates, settlement_settings, sku_costs, ad_spend, recovery_cases, recovery_notes, recovery_evidence, insights_briefs`.

## 3. Keep the platform branding (Fundle)
This is a **Fundle** product. KEEP all "Fundle" branding, the "Powered by Fundle" logo/footer, and the Fundle logo image URL in `Layout.jsx`. Only the **tenant/brand** name changes.

## 4. Rebrand: "Latin Quarter" → "Story At Home"
Replace every tenant string "Latin Quarter" (and the "LQ" logo monogram) with **"Story At Home"** (monogram **"SAH"**). Files to update:
- `frontend/public/index.html` — `<title>` + meta description
- `frontend/src/components/Layout.jsx` — sidebar brand name + "LQ" monogram box + header line
- `frontend/src/pages/Login.jsx` — title, footer copyright, helper text
- `frontend/src/pages/Masters.jsx` — hint text + sample brand string
- `backend/server.py` — module docstring + `FastAPI(title=...)`
- `backend/routers/masters.py` — default `brand` value + seed comments + restore message
- `backend/routers/reports.py` — Excel workbook title
- `backend/routers/claims.py` — `CLAIM_FROM_NAME` default
- `backend/latin_loader.py`, `backend/reingest_all.py` — source_file / filename labels (optionally rename files to `story_loader.py` / keep as-is)
I will provide the **Story At Home brand logo and brand guidelines (colors/fonts)** — apply the logo in the sidebar + login, and align accent colors to the brand palette while keeping the existing clean layout.

## 5. Reconciliation must keep the DUAL-BASIS engine (critical logic — do not simplify)
The reconciliation nets **Forward (sale) + Reverse (return) legs** of an order line and supports two bases (toggle on the Discrepancies page + selector on Reconciliation; only one basis stored at a time; `basis` stored on each run + discrepancy):
- **Settlement basis (default)** — expected = the marketplace's OWN invoiced charges from the order file (per-leg `actual_*` fields, summed as absolute values) and expected net settlement = the order file's `total_actual_settlement` field. Catches payout errors.
- **Contract-audit basis** — expected = the brand's negotiated contract rates via the calc engine, netted across legs. Catches contract overcharges.
Also keep: TCS captured from payout `IGST_TCS+CGST_TCS+SGST_TCS`; and sales legs are **never** month-filtered in reconciliation (a settlement paid in month X can have its sale row dated in another month).

## 6. Clean-seed for the new tenant (NO Latin Quarter data)
- Do **NOT** import any Latin Quarter transaction data or its `latin_masters_seed.json` rates.
- Start with EMPTY `sales/settlement/calculations/discrepancies` and empty contract masters.
- Seed only: admin + marketing users, tax rates (GST 18%, TCS 0.5%, TDS 0.1% — confirm for this brand), tolerance defaults, settlement settings.
- Admin login via env: `ADMIN_EMAIL` / `ADMIN_PASSWORD` (default `admin@fundle.ai` / `admin123`). Keep these in `backend/.env`.

## 7. New brand configuration (I will provide these files)
- **Commission masters workbook** (`.xlsx`) with sheets: `Commission Rules`, `Fixed Fee`, `GT Charges` (sub-category → level map). Load via the masters loader → then run `derive_masters` to build GT + return-fee matrices.
- **Raw marketplace export** — order files + payout files. NOTE: the current loader is written for **Myntra's** column schema. If Story At Home's marketplace/export schema differs, adapt the loader field mapping (`_order_to_docs` / `load_payouts`) to the new columns — keep the same output document shapes so the calc/recon engines work unchanged.
- After I upload both, run the equivalent of `python -m reingest_all` to populate everything, then verify the Discrepancies report (Settlement basis) reconciles cleanly.

## 8. Emergent environment rules (must follow)
- Use the pre-set env vars only: backend `MONGO_URL`, `DB_NAME` (never change), `REACT_APP_BACKEND_URL` on the frontend. All backend routes prefixed `/api`. No hardcoded URLs/keys/ports. Use `EMERGENT_LLM_KEY` for the AI Insights feature. Frontend uses `yarn`. Services run under supervisor.

## 9. Acceptance
App runs; login works; all 15 pages render; uploading the brand's masters + raw data populates Sales Ledger, Calculations, Reconciliation (both bases), Discrepancies, P&L; Methodology page shows the formulas; branding reads "Story At Home · Marketplace AutoPilot — Powered by Fundle".
