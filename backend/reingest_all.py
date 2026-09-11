"""Full Latin Quarter re-ingestion orchestrator.

Runs the complete pipeline end-to-end against the configured Mongo DB:

  1. load_masters   — commission_rules / fixed_fees / subcat_levels (from xlsx)
  2. load_orders    — sales + adapter calcs (Myntra-reported values)
  3. derive         — gt_charges / return_fees matrices (from adapter calcs)
  4. run_calculations(recalculate) — recompute EXPECTED via the contract engine
  5. load_payouts   — settlement rows (net forward+reverse, incl TCS)
  6. run_reconciliation — component-level expected-vs-actual discrepancies

Idempotent: every stage clears its own collection before reloading.

Run:  python -m reingest_all      (from /app/backend)
"""
import asyncio

import latin_loader as L
import derive_masters as D
from db import db
from routers.calculations import run_calculations, RunCalcIn
from routers.reconciliation import run_reconciliation, RunReconIn


async def run(clear_recon: bool = True):
    print("=== [1/6] load_masters ===", flush=True)
    await L.load_masters()

    print("=== [2/6] load_orders (sales + adapter calcs) ===", flush=True)
    n_sales = await L.load_orders()

    print("=== [3/6] derive gt_charges / return_fees ===", flush=True)
    await D.derive()

    print("=== [4/6] run_calculations (contract engine, recalculate) ===", flush=True)
    res_calc = await run_calculations(RunCalcIn(recalculate=True))
    print("    ", res_calc, flush=True)

    print("=== [5/6] load_payouts (settlement) ===", flush=True)
    n_settle = await L.load_payouts()

    print("=== [6/6] run_reconciliation (order-file basis = default) ===", flush=True)
    if clear_recon:
        await db.discrepancies.delete_many({})
        await db.recon_runs.delete_many({})
    res_recon = await run_reconciliation(RunReconIn(basis="orderfile"))
    print("    ", {k: res_recon[k] for k in ("matched", "variance", "unmatched", "total_settled_rows", "total_recoverable")}, flush=True)

    print(f"=== DONE: sales={n_sales} settlement={n_settle} ===", flush=True)


if __name__ == "__main__":
    asyncio.run(run())
