"""Settlement reconciliation engine.
Matches settlement rows to sales + calculations by (order_id, sku).
Compares actual vs expected for commission, fixed fee, GT, return fee, TCS/TDS, settlement.
Emits discrepancies with severity based on tolerance & materiality settings.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import uuid

from db import db

router = APIRouter(tags=["reconciliation"])


def _uid():
    return str(uuid.uuid4())


def _iso():
    return datetime.now(timezone.utc).isoformat()


async def _tolerance() -> Dict[str, float]:
    t = await db.tolerances.find_one({}, {"_id": 0})
    return t or {"absolute_inr": 1.0, "percentage": 0.5, "materiality_inr": 100.0}


def _classify(actual: float, expected: float, tol: Dict[str, float]) -> str:
    variance = actual - expected
    abs_var = abs(variance)
    if abs_var <= tol["absolute_inr"]:
        return "matched"
    if expected:
        pct = abs_var / abs(expected) * 100
        if pct <= tol["percentage"]:
            return "matched"
    return "overcharged" if variance > 0 else "undercharged"


def _severity(recoverable: float, tol: Dict[str, float]) -> str:
    r = abs(recoverable)
    if r >= tol["materiality_inr"] * 10:
        return "critical"
    if r >= tol["materiality_inr"] * 3:
        return "high"
    if r >= tol["materiality_inr"]:
        return "medium"
    return "low"


class RunReconIn(BaseModel):
    settlement_upload_id: Optional[str] = None
    sales_upload_id: Optional[str] = None
    report_month: Optional[str] = None


@router.post("/reconciliation/run")
async def run_reconciliation(payload: RunReconIn):
    tol = await _tolerance()
    run_id = _uid()

    settle_q: Dict[str, Any] = {}
    if payload.settlement_upload_id:
        settle_q["upload_id"] = payload.settlement_upload_id
    if payload.report_month:
        settle_q["report_month"] = payload.report_month
    settlements = await db.settlement.find(settle_q, {"_id": 0}).to_list(200000)

    if not settlements:
        raise HTTPException(400, "No settlement rows to reconcile. Please upload a settlement file for this month.")

    # Clear prior discrepancies for the same scope so the panel reflects ONLY the latest run
    # (otherwise stale rows from earlier runs linger and mismatch the calculation panel).
    disc_del_q: Dict[str, Any] = {}
    if payload.report_month:
        disc_del_q["report_month"] = payload.report_month
    await db.discrepancies.delete_many(disc_del_q)

    sales_q: Dict[str, Any] = {}
    if payload.sales_upload_id:
        sales_q["upload_id"] = payload.sales_upload_id
    if payload.report_month:
        sales_q["report_month"] = payload.report_month
    sales_docs = await db.sales.find(sales_q, {"_id": 0}).to_list(500000)
    sales_map = {(s["online_order_id"], s.get("order_line_id") or s["sku"]): s for s in sales_docs}

    sales_ids = [s["id"] for s in sales_docs]
    calc_docs = await db.calculations.find({"sales_id": {"$in": sales_ids}}, {"_id": 0}).to_list(200000)
    calc_map = {c["sales_id"]: c for c in calc_docs}

    matched_count = 0
    variance_count = 0
    unmatched_count = 0
    discrepancies = []
    total_recoverable = 0.0

    for settle in settlements:
        key = (settle["online_order_id"], settle.get("order_line_id") or settle["sku"])
        sale = sales_map.get(key)
        report_month = settle.get("report_month") or (sale.get("report_month") if sale else None)
        if not sale:
            unmatched_count += 1
            discrepancies.append({
                "id": _uid(), "recon_run_id": run_id,
                "report_month": report_month,
                "online_order_id": settle["online_order_id"], "sku": settle["sku"],
                "match_status": "unmatched",
                "severity": "high",
                "reason": "No matching sales record found",
                "recoverable": 0,
                "components": [],
                "settled": settle,
                "expected": None,
                "created_at": _iso(),
            })
            continue

        calc = calc_map.get(sale["id"])
        if not calc:
            unmatched_count += 1
            discrepancies.append({
                "id": _uid(), "recon_run_id": run_id,
                "report_month": report_month,
                "online_order_id": settle["online_order_id"], "sku": settle["sku"],
                "sales_id": sale["id"],
                "match_status": "unmatched",
                "severity": "medium",
                "reason": "Sale found but calculation missing — run calculations first",
                "recoverable": 0,
                "components": [],
                "settled": settle,
                "expected": None,
                "created_at": _iso(),
            })
            continue

        if calc.get("unmapped"):
            unmatched_count += 1
            discrepancies.append({
                "id": _uid(), "recon_run_id": run_id,
                "report_month": report_month,
                "online_order_id": settle["online_order_id"], "sku": settle["sku"],
                "sales_id": sale["id"], "calc_id": calc["id"],
                "match_status": "unmatched",
                "severity": "medium",
                "reason": "Expected calc has unmapped components: " + "; ".join(calc.get("unmapped_reasons", []))[:200],
                "recoverable": 0,
                "components": [],
                "settled": settle,
                "expected": None,
                "created_at": _iso(),
            })
            continue

        # Compare component-by-component
        components = []
        recoverable = 0.0
        any_variance = False
        checks = [
            ("commission", calc["commission_incl_gst"], settle.get("settled_commission", 0)),
            ("fixed_fee", calc["fixed_fee_incl_gst"], settle.get("settled_fixed_fee", 0)),
            ("gt_charge", calc["gt_charge"], settle.get("settled_gt_charge", 0)),
            ("return_fee", calc["return_fee"], settle.get("settled_return_fee", 0)),
            ("tcs", calc["tcs"], settle.get("settled_tcs", 0)),
            ("tds", calc["tds"], settle.get("settled_tds", 0)),
        ]
        for name, exp, act in checks:
            exp_f = float(exp or 0)
            act_f = float(act or 0)
            status = _classify(act_f, exp_f, tol)
            variance = act_f - exp_f
            recoverable_here = variance if variance > 0 else 0  # overcharged => recoverable
            if status != "matched":
                any_variance = True
                recoverable += recoverable_here
            components.append({
                "component": name,
                "expected": round(exp_f, 2),
                "actual": round(act_f, 2),
                "variance": round(variance, 2),
                "status": status,
            })

        # Settlement amount
        exp_settlement = float(calc["expected_settlement"])
        act_settlement = float(settle.get("settled_amount", 0))
        settle_variance = act_settlement - exp_settlement
        settle_status = _classify(act_settlement, exp_settlement, tol)
        components.append({
            "component": "net_settlement",
            "expected": round(exp_settlement, 2),
            "actual": round(act_settlement, 2),
            "variance": round(settle_variance, 2),
            "status": settle_status,
        })

        if not any_variance and settle_status == "matched":
            matched_count += 1
            continue

        variance_count += 1
        severity = _severity(recoverable if recoverable else abs(settle_variance), tol)
        reason_parts = []
        for c in components:
            if c["status"] not in ("matched", "net_settlement") or (c["component"] == "net_settlement" and c["status"] != "matched"):
                if c["status"] != "matched":
                    reason_parts.append(f"{c['component']}: {c['status']} by ₹{abs(c['variance']):.2f}")
        reason = "; ".join(reason_parts) or "Variance detected"
        total_recoverable += max(recoverable, 0)

        discrepancies.append({
            "id": _uid(), "recon_run_id": run_id,
            "report_month": report_month,
            "online_order_id": settle["online_order_id"], "sku": sale.get("sku") or settle.get("sku"),
            "sales_id": sale["id"], "calc_id": calc["id"],
            "match_status": "variance",
            "severity": severity,
            "reason": reason,
            "recoverable": round(max(recoverable, 0), 2),
            "settle_variance": round(settle_variance, 2),
            "components": components,
            "settled": settle,
            "expected": {
                "commission_incl_gst": calc["commission_incl_gst"],
                "fixed_fee_incl_gst": calc["fixed_fee_incl_gst"],
                "gt_charge": calc["gt_charge"],
                "return_fee": calc["return_fee"],
                "tcs": calc["tcs"],
                "tds": calc["tds"],
                "expected_settlement": calc["expected_settlement"],
            },
            "created_at": _iso(),
        })

    # Persist run + discrepancies (insert_many mutates docs by adding _id)
    sample = [dict(d) for d in discrepancies[:20]]  # snapshot before mutation
    if discrepancies:
        for i in range(0, len(discrepancies), 500):
            await db.discrepancies.insert_many(discrepancies[i:i + 500])

    run_doc = {
        "id": run_id,
        "created_at": _iso(),
        "settlement_upload_id": payload.settlement_upload_id,
        "sales_upload_id": payload.sales_upload_id,
        "total_settled_rows": len(settlements),
        "matched": matched_count,
        "variance": variance_count,
        "unmatched": unmatched_count,
        "total_recoverable": round(total_recoverable, 2),
    }
    await db.recon_runs.insert_one({**run_doc})

    # Invalidate cached aggregates so freshly-created discrepancies show up
    try:
        from cache_utils import invalidate as _inv
        _inv("discrepancies")
        _inv("overview")
    except Exception:
        pass

    return {**run_doc, "discrepancies_sample": sample}


@router.get("/reconciliation/runs")
async def list_runs():
    docs = await db.recon_runs.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return docs


@router.get("/reconciliation/discrepancies")
async def list_discrepancies(
    recon_run_id: Optional[str] = None,
    report_month: Optional[str] = None,
    period_type: Optional[str] = None,
    period_value: Optional[str] = None,
    severity: Optional[str] = None,
    match_status: Optional[str] = None,
    sub_category: Optional[str] = None,
    zone: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(200, le=2000),
    skip: int = 0,
    sort_by: str = "recoverable",
    sort_dir: str = "desc",
):
    from period_utils import month_query as _mq
    q: Dict[str, Any] = {}
    if period_type:
        q.update(_mq(period_type, period_value))
    elif report_month:
        q["report_month"] = report_month
    if recon_run_id:
        q["recon_run_id"] = recon_run_id
    if severity:
        q["severity"] = severity
    if match_status:
        q["match_status"] = match_status
    if search:
        q["$or"] = [
            {"online_order_id": {"$regex": search, "$options": "i"}},
            {"sku": {"$regex": search, "$options": "i"}},
        ]
    total = await db.discrepancies.count_documents(q)
    sort_map = {
        "recoverable": "recoverable", "severity": "severity", "sku": "sku",
        "order_id": "online_order_id", "created_at": "created_at",
        "settle_variance": "settle_variance",
    }
    sort_field = sort_map.get(sort_by, "recoverable")
    direction = -1 if sort_dir == "desc" else 1
    docs = await db.discrepancies.find(q, {"_id": 0}).sort(sort_field, direction).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "items": docs}


@router.get("/reconciliation/discrepancy/{disc_id}")
async def get_discrepancy(disc_id: str):
    doc = await db.discrepancies.find_one({"id": disc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Discrepancy not found")
    return doc
