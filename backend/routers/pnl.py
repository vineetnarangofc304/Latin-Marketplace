"""SKU cost sync + SKU-level / monthly P&L.

P&L per SKU (and per month):
  Net P&L = Net Sales Value - marketplace fees (commission/GT/fixed/return)
            - taxes (TCS/TDS) - product cost (net units x SKU cost) - ad spend

Since expected_settlement already = NSV - fees - taxes, Net P&L = Σ settlement - product_cost.
Returns/RTO are netted via signed settlement and net units.
"""
import io
import csv
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import APIRouter, File, UploadFile, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
import openpyxl

from db import db
from deps import require_admin
from period_utils import month_query

router = APIRouter(tags=["pnl"])


def _uid():
    return str(uuid.uuid4())


def _iso():
    return datetime.now(timezone.utc).isoformat()


def _num(v):
    if v is None or v == "":
        return 0.0
    try:
        return float(str(v).replace(",", "").replace("\u20b9", "").strip())
    except Exception:
        return 0.0


def _s(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


# ---------------- SKU costs ----------------
def _find_cols(header):
    sku_i = cost_i = None
    for i, h in enumerate(header):
        hn = str(h or "").strip().lower()
        if sku_i is None and hn in ("sku", "sku_code", "sku code", "style", "style code", "seller sku", "sku id"):
            sku_i = i
        if cost_i is None and ("cost" in hn or hn in ("cp", "landing", "landing cost", "unit cost", "product cost")):
            cost_i = i
    return sku_i, cost_i


@router.post("/sku-costs/upload")
async def upload_sku_costs(file: UploadFile = File(...), _admin=Depends(require_admin)):
    content = await file.read()
    name = (file.filename or "").lower()
    if name.endswith(".csv"):
        rows = list(csv.reader(content.decode("utf-8", errors="replace").splitlines()))
    else:
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
    if not rows:
        raise HTTPException(400, "Empty file")
    sku_i, cost_i = _find_cols(rows[0])
    if sku_i is None or cost_i is None:
        raise HTTPException(400, "Could not find 'SKU' and 'Cost' columns. The header row must include a SKU column and a Cost column.")

    accepted = 0
    rejected = 0
    sample = []
    now = _iso()
    for r in rows[1:]:
        if r is None or len(r) <= max(sku_i, cost_i):
            continue
        sku = _s(r[sku_i])
        cost = _num(r[cost_i])
        if not sku:
            rejected += 1
            if len(sample) < 5:
                sample.append({"reason": "missing SKU", "row": [str(x) for x in r][:6]})
            continue
        await db.sku_costs.update_one(
            {"sku": sku},
            {"$set": {"sku": sku, "cost": round(cost, 2), "updated_at": now},
             "$setOnInsert": {"id": _uid()}},
            upsert=True,
        )
        accepted += 1
    total = await db.sku_costs.count_documents({})
    return {"filename": file.filename, "accepted_count": accepted,
            "rejected_count": rejected, "rejections_sample": sample, "total_costs": total}


@router.get("/sku-costs")
async def list_sku_costs(search: Optional[str] = None, limit: int = Query(200, le=10000), skip: int = 0):
    q: Dict[str, Any] = {}
    if search:
        q["sku"] = {"$regex": search, "$options": "i"}
    total = await db.sku_costs.count_documents(q)
    items = await db.sku_costs.find(q, {"_id": 0}).sort("sku", 1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "items": items}


@router.delete("/sku-costs")
async def clear_sku_costs(_admin=Depends(require_admin)):
    r = await db.sku_costs.delete_many({})
    return {"deleted": r.deleted_count}


@router.get("/sku-costs/template")
async def sku_cost_template():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SKU Costs"
    ws.append(["SKU", "Cost"])
    ws.append(["LTQRSHRT118021261", 350])
    ws.append(["LTQRTOPS119573072", 220])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="sku-cost-template.xlsx"'},
    )


# ---------------- P&L ----------------
_GROUP = {
    "sales_units": {"$sum": {"$cond": [{"$eq": ["$order_type", "sales"]}, 1, 0]}},
    "return_units": {"$sum": {"$cond": [{"$eq": ["$order_type", "return"]}, 1, 0]}},
    "gross_nsv": {"$sum": {"$cond": [{"$eq": ["$order_type", "sales"]}, "$breakdown.nsv_val", 0]}},
    "return_nsv": {"$sum": {"$cond": [{"$eq": ["$order_type", "return"]}, "$breakdown.nsv_val", 0]}},
    "commission": {"$sum": "$commission_incl_gst"},
    "gt": {"$sum": "$gt_charge"},
    "fixed": {"$sum": "$fixed_fee_incl_gst"},
    "return_fee": {"$sum": "$return_fee"},
    "tcs": {"$sum": "$tcs"},
    "tds": {"$sum": "$tds"},
    "settlement": {"$sum": "$expected_settlement"},
}


async def _cost_map():
    m = {}
    async for c in db.sku_costs.find({}, {"_id": 0, "sku": 1, "cost": 1}):
        m[c["sku"]] = c["cost"]
    return m


def _row(g, cost):
    sales_u = g.get("sales_units", 0) or 0
    ret_u = g.get("return_units", 0) or 0
    net_units = sales_u - ret_u
    net_nsv = round((g.get("gross_nsv", 0) or 0) - (g.get("return_nsv", 0) or 0), 2)
    commission = round(g.get("commission", 0) or 0, 2)
    gt = round(g.get("gt", 0) or 0, 2)
    fixed = round(g.get("fixed", 0) or 0, 2)
    return_fee = round(g.get("return_fee", 0) or 0, 2)
    fees = round(commission + gt + fixed + return_fee, 2)
    taxes = round((g.get("tcs", 0) or 0) + (g.get("tds", 0) or 0), 2)
    settlement = round(g.get("settlement", 0) or 0, 2)
    ad_spend = 0.0
    product_cost = round(net_units * (cost or 0), 2)
    net_pnl = round(settlement - product_cost - ad_spend, 2)
    margin = round(net_pnl / net_nsv * 100, 2) if net_nsv else 0.0
    return {
        "sales_units": sales_u, "return_units": ret_u, "net_units": net_units,
        "net_nsv": net_nsv, "commission": commission, "gt_charge": gt, "fixed_fee": fixed,
        "return_fee": return_fee, "fees": fees, "taxes": taxes, "settlement": settlement,
        "product_cost": product_cost, "ad_spend": ad_spend, "net_pnl": net_pnl, "margin_pct": margin,
    }


@router.get("/pnl/summary")
async def pnl_summary(period_type: Optional[str] = None, period_value: Optional[str] = None):
    match: Dict[str, Any] = {"unmapped": False}
    if period_type:
        match.update(month_query(period_type, period_value))
    groups = await db.calculations.aggregate(
        [{"$match": match}, {"$group": {"_id": "$sku", **_GROUP}}]
    ).to_list(20000)
    costs = await _cost_map()
    agg = {k: 0.0 for k in ("net_nsv", "fees", "taxes", "settlement", "product_cost", "net_pnl", "net_units")}
    skus = 0
    missing = 0
    for g in groups:
        sku = g["_id"]
        if not sku:
            continue
        cost = costs.get(sku)
        r = _row(g, cost)
        for k in agg:
            agg[k] += r[k]
        skus += 1
        if cost is None:
            missing += 1
    for k in ("net_nsv", "fees", "taxes", "settlement", "product_cost", "net_pnl"):
        agg[k] = round(agg[k], 2)
    agg["net_units"] = int(agg["net_units"])
    agg["margin_pct"] = round(agg["net_pnl"] / agg["net_nsv"] * 100, 2) if agg["net_nsv"] else 0.0
    agg["skus"] = skus
    agg["skus_missing_cost"] = missing
    return agg


@router.get("/pnl/sku")
async def pnl_by_sku(period_type: Optional[str] = None, period_value: Optional[str] = None,
                     search: Optional[str] = None, sort_by: str = "net_pnl", sort_dir: str = "asc",
                     limit: int = Query(500, le=10000), skip: int = 0):
    match: Dict[str, Any] = {"unmapped": False}
    if period_type:
        match.update(month_query(period_type, period_value))
    groups = await db.calculations.aggregate(
        [{"$match": match}, {"$group": {"_id": "$sku", **_GROUP}}]
    ).to_list(20000)
    costs = await _cost_map()
    rows = []
    for g in groups:
        sku = g["_id"]
        if not sku:
            continue
        if search and search.lower() not in sku.lower():
            continue
        cost = costs.get(sku)
        r = _row(g, cost)
        r["sku"] = sku
        r["cost"] = cost
        r["cost_missing"] = cost is None
        rows.append(r)
    rows.sort(key=lambda x: (x.get(sort_by) if isinstance(x.get(sort_by), (int, float)) else 0),
              reverse=(sort_dir == "desc"))
    total = len(rows)
    return {"total": total, "items": rows[skip:skip + limit]}


@router.get("/pnl/monthly")
async def pnl_monthly():
    groups = await db.calculations.aggregate(
        [{"$match": {"unmapped": False}},
         {"$group": {"_id": {"month": "$report_month", "sku": "$sku"}, **_GROUP}}]
    ).to_list(300000)
    costs = await _cost_map()
    months: Dict[str, Any] = {}
    for g in groups:
        m = g["_id"].get("month")
        sku = g["_id"].get("sku")
        if not m:
            continue
        r = _row(g, costs.get(sku))
        mm = months.setdefault(m, {k: 0.0 for k in ("net_nsv", "fees", "taxes", "settlement", "product_cost", "net_pnl", "net_units")})
        for k in mm:
            mm[k] += r[k]
    out = []
    for m in sorted(months):
        mm = months[m]
        for k in ("net_nsv", "fees", "taxes", "settlement", "product_cost", "net_pnl"):
            mm[k] = round(mm[k], 2)
        mm["net_units"] = int(mm["net_units"])
        mm["month"] = m
        mm["margin_pct"] = round(mm["net_pnl"] / mm["net_nsv"] * 100, 2) if mm["net_nsv"] else 0.0
        out.append(mm)
    return out
