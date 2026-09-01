# KAZO Marketplace Finance & Reconciliation Platform — PRD

## Original Problem Statement
KAZO Marketplace Finance Operating System — ingests marketplace reports, calculates expected charges, reconciles settlements, identifies leakage, manages recoveries. First connector: Myntra. Marketplace-agnostic core.

## User Choices (2026-02)
- Auth: Simple username/password (JWT, bcrypt), role-based (admin/finance/ops/viewer)
- File storage: MongoDB (uploaded XLSX parsed and stored as normalized rows)
- Frontend: React JS (agent's choice)
- AI insights: Deferred to a later iteration

## Iteration 2 — Production Hardening (2026-02, session 2)
User: "Make it production ready...no hard code no fallback. Make it ready for monthly reports to be uploaded in the formats. Please pre-configure the rules of Myntra and add them and create report based on the June data uploaded and rules given."

### Delivered in iteration 2
- **No fallbacks in the calculation engine** — every fee component either resolves to a strict rule match OR is left `null` with a specific `unmapped_reasons[]` entry. `unmapped=True` flag surfaces at row & aggregate level.
- **Configurable defaults instead of hardcoded values**:
  - Zone default (`Local / Zonal / National`) editable in Masters → Settlement Config; toggleable to force strict mode
  - GST / TCS / TDS rates editable in Masters → Tax Rates
  - Tolerance thresholds editable in Masters → Tolerance
- **Full 173-rule Myntra commission set** loaded from `/app/backend/data_myntra_commission_rules.json` (extracted from KAZO's own Myntra master file), with a `POST /api/masters/reset-defaults` (admin-only) to re-seed
- **Monthly report engine**:
  - `report_month` (YYYY-MM) extracted from `Month` / `Posting Date` / `Order Date` on every row
  - `GET /api/reports/months` — list of available months
  - `GET /api/reports/monthly?month=YYYY-MM` — full JSON aggregate (KPIs, category/sub-cat/zone breakdowns, reconciliation summary)
  - `GET /api/reports/monthly/export?month=YYYY-MM` — 7-sheet Excel workbook (Summary, By Category, By Sub-Category, By Zone, Order Detail, Discrepancies, Unmapped Orders)
- **Flexible file format handling** — parser scans headers with an alias table, picks the best-matching sheet automatically, requires `Order Id + SKU + NSV + Sub-Category` at minimum; rejects rows with placeholder "-" SKUs
- **Month filter** on dashboards, calculations, reconciliation, discrepancies
- **Admin-only guards** on all destructive master endpoints (POST/DELETE on commission-rules, fixed-fees, gt-charges, return-fees, subcat-levels, tolerance, tax-rates, settlement-settings, reset-defaults)
- **Format validation** — bad month strings (`bad-01`, etc.) return 400 instead of empty aggregates

### Verified on real data (Apr-26 file — 14,219 orders)
- 173 authoritative commission rules seeded
- 14,219 orders calculated
- **37 unmapped (0.26%)** — all `Clothing Set` variants missing from source master file; surfaced explicitly with reasons for ops
- ₹2.61 Cr NSV → ₹31.5 L expected commission (12.03%) → ₹1.94 Cr expected settlement (74.2% margin)
- Reconciliation on synthetic 296-row settlement: 231 matched, 65 variance, ₹1,264 recoverable

## Architecture
- **Backend**: FastAPI + Motor (Mongo async), JWT bcrypt auth
  - `server.py` — auth, JWT, admin seed
  - `deps.py` — `current_user`, `require_admin`
  - `routers/masters.py` — commission rules, fixed fee, GT, return fee, sub-cat level, tolerance, tax_rates, settlement_settings
  - `routers/uploads_r.py` — flexible XLSX parsers (sales/settlement) with alias-based header matching
  - `routers/calculations.py` — strict calc engine, unmapped detection, month tagging
  - `routers/reconciliation.py` — component-level compare, month propagation
  - `routers/dashboards.py` — KPI aggregates with month filter
  - `routers/reports.py` — monthly report JSON + Excel export
- **Frontend**: React 19 + Tailwind + shadcn/ui + recharts
  - Pages: Login, Overview, Reports, Uploads, SalesLedger, Calculations, Reconciliation, Discrepancies, Masters
- **DB collections**: `users`, `uploads`, `sales`, `settlement`, `commission_rules`, `fixed_fees`, `gt_charges`, `return_fees`, `subcat_levels`, `tolerances`, `tax_rates`, `settlement_settings`, `calculations`, `discrepancies`, `recon_runs`
- **Indexes**: `report_month` on `sales`, `calculations`, `settlement`, `discrepancies`

## Test Results (iteration 2)
- Backend: **29/29 pytest passed** (15 legacy + 14 new production tests)
- Frontend: All new data-testids present and functional
- Security: auth guard + admin-only enforcement verified end-to-end

## Iteration 9 — Production login "long wait then fails" (2026-07-21)
User: login on production https://kazob2b.fundlezone.com hangs then errors with "Something went wrong. Please try again."

### Root causes
1. **CORS spec violation** — server had `allow_origins=["*"]` **and** `allow_credentials=True`. Per CORS spec, `Access-Control-Allow-Origin: *` is invalid when credentials are used, so browsers reject the response. Frontend sends `withCredentials:true`, so cross-origin requests silently failed.
2. **bcrypt blocks the event loop** — `bcrypt.checkpw` / `bcrypt.hashpw` are CPU-bound (~250 ms). Being called directly inside `async def login` stalls every concurrent request behind it.
3. **Admin seed in background** — since we moved bootstrap to a background task in iteration 4, the very first login attempt after a cold pod restart could race the seed and 401.

### Delivered
- **CORS**: middleware now uses `allow_origin_regex=".*"` when `CORS_ORIGINS="*"`. Response reflects the caller's origin + `access-control-allow-credentials: true` — spec compliant.
- **Async bcrypt**: new `hash_pwd_async` / `verify_pwd_async` wrap the bcrypt calls in `asyncio.to_thread` so the event loop stays free. Login now handles concurrent requests without stacking.
- **Inline admin seed**: `@app.on_event("startup")` seeds/rehashes admin **inline** (fast — one Atlas round-trip + at most one bcrypt hash), then kicks off the rest of bootstrap (40+ indexes + masters) in the background. Login is available from the very first request after a pod restart.

### Test Results (iteration 9)
- `testing_agent_v3_fork` iteration_9 PASS. 10/10 backend regressions. Cold-start login within 230 ms of supervisor restart returns 200. Frontend login redirects in ~0.3 s. No CORS blocks. Zero bugs.

## Iteration 8 — Return-DTO fix + drawer base+GST split (2026-07-21)
User: (1) "commission & fixed fee should always be before GST for all calc"; (2) "return fee logic is based on the tables attached.. its coming same as fixed fee, while it has to come based on tables attached".

### Delivered
- **Backend `compute_expected` — Return-DTO branch**: now uses `return_fee_master` from the Return Fee_TABLE (level, zone) instead of `fixed_fee_incl_gst`. Fixed Fee, Commission, GT, TCS, TDS are all set to zero for return_dto rows. Test order `DFC4F34A-58F6-40EA-9AA1-2C13EB9F2140` (nsv=-646, zone=Zonal, Level 1) now correctly returns ₹112 (was ₹71.98) and expected_settlement=-758.
- **Drawer UI** (`SalesLedger` order detail + `Calculations` explainer): each Expected-Calculation row shows base and GST separately — `Commission (ex GST)`, `GST on Commission (18%)`, `Fixed Fee (ex GST)`, `GST on Fixed Fee (18%)`, `GT Charge (incl GST)`, `Return Fee (Level/Zone)`, `TCS`, `TDS`, `Total Deductions`, `Expected Settlement`.
- **Return Velocity widget**: metric renamed from `fixed_fee_leakage` → `leakage` (now sums `return_fee` on return_dto rows). April Return-fee leakage: **₹6,58,488** total; worst: Dresses ₹1.72L (58.6%), Tops ₹1.57L (52.6%), Shirts ₹75K.

### Test Results (iteration 8)
- `testing_agent_v3_fork` iteration_8 PASS (6/6 backend + drawer UI). Zero bugs, zero action items. Sample validated end-to-end.

## Iteration 7 — Return Velocity widget on CEO Overview (2026-07-21)

User approved the iteration 6 suggestion. Added:
- **New endpoint** `GET /api/dashboard/return-velocity?period_type&period_value&top` returns `{overall: {sales_orders, return_dto_orders, return_orders, rto_orders, internal_cancel_orders, velocity_pct, total_fixed_fee_leakage}, by_sub_category: [{sub_category, orders, return_dto_orders, velocity_pct, fixed_fee_leakage, sales_nsv, ...}]}`. Sorted by fixed-fee leakage desc.
- **New backend filter** `GET /api/calculations?order_type=return_dto|sales|return|rto|internal_cancel` — enables drill-through.
- **Overview panel** `data-testid='return-velocity-panel'` — headline "X% of sales orders flipped to Return-DTO", plus table with row-level drill (each row → `/calculations?sub_category=&order_type=return_dto&period=...`). Colored velocity heatmap (blue/orange/red bands).
- **April 2026 data**: 44.4% overall velocity, ₹2.85L fixed-fee leakage. Worst offenders: Dresses (58.6%, ₹88,599), Trousers (55.5%, ₹16,563), Shirts (53.6%, ₹36,838).

Test agent iteration_7 PASS — no bugs, no action items.

## Iteration 6 — Return rows dropped by parser (2026-07-21)
Reported: "the original April sales file also had return orders. those seem to have not got processed."

### Root cause
The raw file has 21,614 rows: 14,219 with `txn_type='Sales'` and **7,395 with `txn_type='Return'`**. Every return row has a **negative NSV / QTY** (Myntra's convention for reversals). The sales parser rejected all rows with `nsv_val < 0`, silently dropping the 7,395 return rows. Additionally, the previous classifier tagged both Sales+DTO and Return+DTO as `dto` — after importing returns, this would have double-counted refunds.

### Delivered in iteration 6
- **Parser** (`uploads_r._parse_sales_xlsx`): removed the negative-NSV rejection so Return rows import cleanly.
- **Classifier** (`_classify_order`): now emits **5 order types**:
  - `sales` — everything with `txn_type='Sales'` and no RTO/InternalCancellation status (includes Sales+DTO — the original sale record for a DTO order)
  - `return_dto` — `txn_type='Return' AND order_status='DTO'` — applies only Fixed Fee (incl GST) as Return Fee
  - `return` — any other `txn_type='Return'` (e.g. Return+Delivered, Return+Status NF) — sign-flipped with return fee from (level, zone) matrix
  - `rto` — any `order_status='RTO'` (Sales+RTO or Return+RTO) — all fees nullified
  - `internal_cancel` — any `order_status='Internal Cancellation'` — all fees nullified
- **compute_expected**: the `sales` branch now uses `abs(nsv_val)` (defensive); `return_dto` branch mirrors the old `dto` branch (fixed fee only). Net-effect for a DTO order across both Sales and Return rows = seller loses one fixed fee — matches the user's spec exactly.
- **Data reload**: uploaded raw file → 21,614 accepted / 0 rejected; recalculated all → distribution matches expected exact counts.

### Test Results (iteration 6)
- 21,614 sales rows imported (was 14,219; +7,395 returns now processed)
- Order-type distribution: sales=12,246 · return_dto=5,443 · rto=3,705 · internal_cancel=128 · return=92 (sums to 21,614 ✓)
- Aggregate April expected settlement: **₹4,631,550** (previously ₹16,575,054 which was inflated because returns weren't offsetting)
  - Sales: +₹14,690,173
  - Return DTO: −₹9,797,947
  - Return: −₹260,676
  - RTO / Internal Cancel: 0
- `testing_agent_v3_fork` iteration_6 PASS — no bugs, no action items.

## Iteration 5 — Bug-fix punchlist from CEO (2026-07-21)
Reported items:
1. NSV − GT amount = NSV-after-GT; all downstream calculations to use this base
2. Return transactions to be deducted (signed negative)
3. Search by Order ID not working
4. Commission Masters — download / upload option for configuration
5. Return Fee zonal charges to be considered
6. Sub-category → GTA charges level master
7. Return DTO — only fixed charges applied as return fee
8. RTO / Internal Cancellation — all fees nullified

### Delivered in iteration 5
- **Calculation engine rewrite (`compute_expected` + new `_classify_order`)**:
  - `order_type` ∈ {sales, return, dto, rto, internal_cancel} — classified by `order_status` (exact 'RTO' / 'Internal Cancellation' / 'DTO') and `txn_type` (contains 'return')
  - `nsv_after_gt = nsv_val − gt_charge` for sales; sign-flipped for returns/DTO
  - Commission base, TCS, TDS all computed on `nsv_after_gt` (previously used raw NSV)
  - **DTO**: only Fixed Fee (incl GST) applies, counted as Return Fee; everything else 0; expected_settlement = −|NSV| − FixedFeeInclGST
  - **RTO / Internal Cancellation**: every fee = 0; expected_settlement = 0; no unmapped flag
  - **Return**: all component signs reversed, plus return_fee (positive) from the (level, zone) matrix
  - New `nsv_after_gt` field in `breakdown` and top-level for reporting
- **Search fixes**:
  - Regex-escape `search` param on `/api/sales` and `/api/calculations` so UUIDs / meta-chars don't 500
  - Debounced search (400 ms) on both `SalesLedger.jsx` and `Calculations.jsx` — fires on every keystroke, not just Enter
- **Commission Masters download/upload**:
  - New `GET /api/masters/export` → single multi-sheet Excel with 8 sheets: Commission Rules, Fixed Fee, GT Charges, Return Fee, Sub-Cat Levels, Tolerance, Tax Rates, Settlement Config
  - New `POST /api/masters/import?mode=replace|merge` — round-trips the exported file; wipes/upserts collections; auto-invalidates cache
  - Masters page: `Download config` / `Upload (replace)` / `Upload (merge)` buttons with confirmation prompt

### Test Results (iteration 5)
- `testing_agent_v3_fork` iteration_5 → PASS. Verified DTO math (−6561.98 for the ₹6490 handbag test row), sales math (NSV-after-GT commission base), RTO/internal-cancel nullification, order-type classification on 14,219 rows, search-by-fragment on both Sales and Calculations, Masters download → import roundtrip (replace + merge). No bugs.

## Iteration 4 — Rebrand + Production Performance (2026-02, session 3)
User: "Pls add this logo.. powered by fundle on all pages... remove emergent mentions everywhere... all reports taking time to load... please help adding indexes on the DB and also compound indexing on all relevant fields... pls optimise reports dashboards and DB indexes fully for this to run smoothly on Production."

### Delivered in iteration 4
- **Rebrand to Fundle**:
  - Browser title → "KAZO Marketplace Finance · Powered by Fundle"
  - `Powered by [fundle logo]` badge on login page (data-testid `powered-by-fundle-login`) and in the sidebar footer of every authenticated page (data-testid `powered-by-fundle-sidebar`), linking to https://fundle.ai
  - Removed all `Emergent` references from rendered DOM: `index.html` title/description, PostHog block, `emergent-main.js` script, "Emergent Universal Key" text on `/insights`, and the dead `constants/testIds/` folder
- **Performance — DB indexes**:
  - Compound indexes on `sales` (report_month + sub_category / zone / order_status / txn_type)
  - Compound indexes on `calculations` (report_month + breakdown.sub_category / master_category / zone / unmapped / expected_settlement)
  - Compound indexes on `discrepancies` (report_month + severity, report_month + recoverable, recon_run_id + severity)
  - Compound indexes on `recovery_cases` (report_month + status / priority, recoverable_amount desc)
  - Compound indexes on `settlement` (report_month + online_order_id + sku)
  - Extra indexes on `insights_briefs` and `commission_rules`
- **Performance — parallelization**:
  - Dashboards (`overview`, `commission-summary`, `reconciliation-summary`) now run their sub-aggregations in parallel via `asyncio.gather`
  - Reports `_period_aggregate` runs 9 sub-queries in parallel (KPI, sales KPI, 4 group-bys, count, severity, recoverable)
- **Performance — caching**:
  - New `cache_utils.py`: in-memory TTL cache with tag-based invalidation
  - 30s TTL on all hot dashboard + reports endpoints, 60s on period lists
  - Auto-invalidation on writes: uploads (sales/settlement), delete-upload, run-calculations, run-reconciliation
- **Performance — transport**: GZipMiddleware enabled (minimum_size=1024)
- **Observed timings on preview**: cold 150–240ms, warm cached 106–140ms across dashboards + reports + insights + recovery

### Test Results (iteration 4)
- Testing agent verified: title/badges/anti-emergent DOM check across 11 routes, 7 endpoints cache-hot <1.5s with 2nd call ≤ 1st, GZip present, all required compound Mongo indexes exist, drill-downs regression pass. No bugs, no action items.

## Iteration 3 — Recovery Management + AI Insights (2026-02, session 3)
User: "go ahead and complete pending tasks" — deliver Phase 6 & Phase 7 from the backlog.

### Delivered in iteration 3
- **Phase 6 — Recovery Management** (new `routers/recovery.py`, new page `/recovery`)
  - Case tracking with statuses `open → in_review → submitted → recovered | rejected | closed`
  - Auto-create cases from open discrepancies (period-filtered, ₹>0 recoverable)
  - Manual case creation from any discrepancy via a new "Open Recovery Case" button in the Discrepancies drawer
  - Communication log (channel: note/email/call/chat/myntra_ticket, direction: inbound/outbound/internal)
  - Evidence file upload (≤15MB), download, delete — stored in Mongo (`recovery_evidence`, base64)
  - Summary endpoint: totals + by_status + by_priority + coverage % of discrepancy universe
  - Endpoints: `POST /api/recovery/cases`, `POST /api/recovery/cases/auto-create`, `GET/PATCH/DELETE /api/recovery/cases/{id}`, `GET/POST /api/recovery/cases/{id}/notes`, `GET/POST /api/recovery/cases/{id}/evidence`, `GET /api/recovery/evidence/{id}/download`, `GET /api/recovery/summary`
  - New collections: `recovery_cases`, `recovery_notes`, `recovery_evidence` with indexes
- **Phase 7 — AI Insights** (new `routers/insights.py`, new page `/insights`)
  - Deterministic Health Score (0–100, Grade A–F) from four weighted components: Mapping (25%), Leakage (35%), Margin (25%), Recovery (15%)
  - Morning Finance Brief — Claude Sonnet 4.6 via Emergent Universal Key (`EMERGENT_LLM_KEY`), rule-based fallback when LLM unavailable
  - Radial gauge, per-component progress bars, tone selector (executive/operational/concise), audit log of past briefs
  - Endpoints: `GET /api/insights/health-score`, `POST /api/insights/morning-brief`, `GET /api/insights/briefs`
  - Numbers never fabricated — LLM receives only real aggregates from Mongo and is instructed to quote them verbatim
- **Fix** — `period_utils.month_query()` now tolerates missing `period_value` (returns `{}` instead of raising) so dashboards do not 500 on initial load

### Test Results (iteration 3)
- 10/10 new pytest tests pass covering Recovery + Insights (create, duplicate 409, PATCH transitions, notes, evidence upload/download/delete, LLM brief with source='llm', period switching)
- Frontend Recovery + Insights render correctly on 2026-04; Overview health-check regression passes
- Insights Morning Brief validated end-to-end with live Claude Sonnet 4.6 output

## Prioritized Backlog (updated)

### P0 (blocking for pilot)
- Rule versioning + effective_from/effective_to + maker-checker approval workflow
- Full audit log (who edited which master, when, what value changed)

### P1 (next iteration)
- Raw-file retention with checksum in object storage (currently only parsed rows)
- Scheduled report generation + email delivery via Resend
- Visual nested rule builder (IF/AND/OR) instead of slab tables
- Additional export formats — PDF, CSV, Power BI dataflow
- Bulk edit of commission rules

### P2 (future)
- Additional marketplace connectors (Ajio, Amazon, Flipkart, Nykaa) via connector SDK
- Vector-based finance copilot (MongoDB Atlas Vector Search)
- ERP integrations (SAP, Business Central, Tally)
- Multi-entity / multi-GST support
- SSO / stricter tenant boundaries

## Latin Quarter tenant fork — 2026-06-01
- **Tenant (client):** Latin Quarter. **Platform:** Fundle (branding kept 100% intact — Fundle logo, "Powered by Fundle", fundle.ai, "Marketplace AutoPilot", Nunito Sans palette).
- **Source commit:** `2947106a1c87e12e4b42c58fadd3a1fc4e4f7ca2` (github.com/vineetnarangofc304/Marketplace-Platform-Kazo, main).
- **Rebrand:** KAZO/Kazo → Latin Quarter in user-facing copy only (titles, login, layout, report headers/filenames, masters export name). Calc engine sign conventions, marketplace names, DB collection names untouched. localStorage keys (`kazo_token`) left as internal identifiers.
- **Env:** freshly generated `JWT_SECRET` (not reused from KAZO); `PUBLIC_APP_URL=https://latinquarter.fundlezone.com` (replaces leftover `kazob2b.fundlezone.com`); EMERGENT_LLM_KEY + PLAYWRIGHT_BROWSERS_PATH set. MONGO_URL/DB_NAME/REACT_APP_BACKEND_URL preserved.
- **Seed:** admin `admin@fundle.ai` / `admin123` (static, per client override), marketing `marketing@fundle.ai` / `admin123`. Config singletons (tax/tolerance/settlement) seeded; contract-rate masters NOT auto-seeded — loaded from tenant data.
- **Latin data loaded** (`backend/latin_loader.py`, from the attached RAR): 155 commission rules, 272 per-sub-category fixed fees, 16 sub-cat→level maps; 42,550 Myntra order lines → `sales` + `calculations`; 28,537 aggregated payout lines → `settlement`; reconciliation + 5,000 recovery cases generated.
- **Latin adapter:** because the order file already carries Myntra's own commission/fixed/logistics/tax figures (and LQ's contract masters are partial — no GT-charge amounts / Return Fee), `calculations` use the order file's reported values as EXPECTED. Join key across sales/settlement = `(order_release_id, order_line_id)` (payouts have no SKU).
- **KNOWN TUNING ITEM (needs LQ/Myntra semantics):** reconciliation currently returns 0 matched / all variance because (a) order-file `total_settlement` is frequently blank, and (b) payout files contain duplicate forward/reverse rows that the loader naively sums. Correct expected-vs-actual field mapping + payout dedupe (by Order_Type / prepaid-postpaid) is the next step before numbers are trustworthy.
- **First Next Action:** confirm reconciliation field semantics / payout dedupe rule, then re-run recon.

## Test Credentials
- **Admin**: `admin@fundle.ai` / `admin123`
- **Marketing**: `marketing@fundle.ai` / `admin123`
