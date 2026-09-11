"""Inventory-breakage / lost-in-return claim cases (roadmap #4 / #5).

Heuristic (adjustable via materiality): a return order line where the seller was net
debited (expected_settlement < 0) beyond the materiality threshold is treated as an
eligible inventory-breakage / lost-in-return claim. A ready-to-send marketplace claim
email is drafted and stored on each case; the finance user reviews, copies / opens it,
and marks the case emailed/resolved.
"""
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from pymongo import UpdateOne

from db import db
from deps import require_admin
from period_utils import month_query

router = APIRouter(tags=["claims"])

CLAIM_EMAIL_TO = os.environ.get("CLAIM_EMAIL_TO", "seller.support@myntra.com")
CLAIM_FROM = os.environ.get("CLAIM_FROM_NAME", "Latin Quarter Finance")


def _uid():
    return str(uuid.uuid4())


def _iso():
    return datetime.now(timezone.utc).isoformat()


def _draft_email(c: Dict[str, Any]):
    subj = f"Inventory Breakage / Lost-in-Return Claim - Order {c['online_order_id']} (SKU {c['sku']})"
    body = (
        "Dear Myntra Seller Support,\n\n"
        "We are filing a claim for inventory breakage / lost-in-return on the order below. "
        "Per our settlement reconciliation, the seller was net debited on this return and the "
        "item value is eligible for reimbursement.\n\n"
        f"Order ID: {c['online_order_id']}\n"
        f"Order Line ID: {c['order_line_id']}\n"
        f"SKU: {c['sku']}\n"
        f"Category: {c.get('sub_category') or '-'}\n"
        f"Return Month: {c.get('report_month') or '-'}\n"
        f"Item Value (NSV): INR {c['nsv']:.2f}\n"
        f"Net Settlement Impact: INR {c['settlement']:.2f}\n"
        f"Claim Amount: INR {c['claim_amount']:.2f}\n\n"
        "Kindly review and process the reimbursement. Supporting settlement details are "
        "available on request.\n\n"
        f"Regards,\n{CLAIM_FROM}\n(via Fundle Marketplace AutoPilot)"
    )
    return CLAIM_EMAIL_TO, subj, body


class ScanIn(BaseModel):
    materiality: float = 200.0


@router.post("/claims/breakage/scan")
async def scan_breakage(payload: ScanIn, _admin=Depends(require_admin)):
    mat = payload.materiality or 0
    calcs = await db.calculations.find(
        {"order_type": "return", "unmapped": False},
        {"_id": 0, "sales_id": 1, "online_order_id": 1, "order_line_id": 1, "sku": 1,
         "report_month": 1, "expected_settlement": 1, "breakdown": 1},
    ).to_list(300000)
    oli_map = {}
    async for s in db.sales.find({}, {"_id": 0, "id": 1, "order_line_id": 1}):
        oli_map[s["id"]] = s.get("order_line_id")
    ops = []
    total = 0.0
    n = 0
    now = _iso()
    for c in calcs:
        oli = c.get("order_line_id") or oli_map.get(c.get("sales_id"))
        key = oli or c.get("sales_id")
        if not key:
            continue
        settlement = round(c.get("expected_settlement") or 0, 2)
        if settlement >= 0 or abs(settlement) < mat:
            continue
        nsv = round((c.get("breakdown") or {}).get("nsv_val") or 0, 2)
        claim_amount = round(abs(settlement), 2)
        rec = {
            "claim_key": key,
            "online_order_id": c.get("online_order_id"), "order_line_id": oli,
            "sku": c.get("sku"), "sub_category": (c.get("breakdown") or {}).get("sub_category"),
            "report_month": c.get("report_month"), "nsv": nsv, "settlement": settlement,
            "claim_amount": claim_amount, "claim_type": "inventory_breakage",
        }
        to, subj, body = _draft_email(rec)
        rec.update({"email_to": to, "email_subject": subj, "email_body": body})
        ops.append(UpdateOne(
            {"claim_key": key},
            {"$set": rec, "$setOnInsert": {"id": _uid(), "status": "open", "created_at": now}},
            upsert=True,
        ))
        total += claim_amount
        n += 1
    for i in range(0, len(ops), 1000):
        await db.breakage_claims.bulk_write(ops[i:i + 1000], ordered=False)
    return {"scanned_returns": len(calcs), "eligible_cases": n,
            "total_claim_value": round(total, 2), "materiality": mat}


@router.get("/claims/breakage")
async def list_breakage(status: Optional[str] = None, search: Optional[str] = None,
                        period_type: Optional[str] = None, period_value: Optional[str] = None,
                        sort_by: str = "claim_amount", sort_dir: str = "desc",
                        limit: int = Query(500, le=10000), skip: int = 0):
    q: Dict[str, Any] = {}
    if status and status != "all":
        q["status"] = status
    if period_type:
        q.update(month_query(period_type, period_value))
    if search:
        q["$or"] = [{"sku": {"$regex": search, "$options": "i"}},
                    {"online_order_id": {"$regex": search, "$options": "i"}}]
    total = await db.breakage_claims.count_documents(q)
    agg = await db.breakage_claims.aggregate(
        [{"$match": q}, {"$group": {"_id": "$status", "n": {"$sum": 1}, "val": {"$sum": "$claim_amount"}}}]
    ).to_list(20)
    items = await db.breakage_claims.find(q, {"_id": 0}).sort(
        sort_by, -1 if sort_dir == "desc" else 1).skip(skip).limit(limit).to_list(limit)
    summary = {
        "total_cases": total,
        "total_value": round(sum(a["val"] for a in agg), 2),
        "by_status": {a["_id"]: {"n": a["n"], "val": round(a["val"], 2)} for a in agg},
    }
    return {"total": total, "items": items, "summary": summary}


class StatusIn(BaseModel):
    status: str


@router.patch("/claims/breakage/{claim_id}")
async def update_status(claim_id: str, payload: StatusIn, _admin=Depends(require_admin)):
    if payload.status not in ("open", "emailed", "resolved", "rejected"):
        raise HTTPException(400, "Invalid status")
    r = await db.breakage_claims.update_one(
        {"id": claim_id}, {"$set": {"status": payload.status, "updated_at": _iso()}})
    if not r.matched_count:
        raise HTTPException(404, "Claim not found")
    return {"ok": True}


@router.delete("/claims/breakage")
async def clear_breakage(_admin=Depends(require_admin)):
    r = await db.breakage_claims.delete_many({})
    return {"deleted": r.deleted_count}
