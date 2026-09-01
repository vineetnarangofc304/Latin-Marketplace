"""Dashboard aggregates — support Month / Quarter / Year / YTD / All periods.

Hot aggregations run in parallel via ``asyncio.gather`` and results are cached
in a tiny in-memory TTL store (30s) to smooth over UI bursts.
"""
import asyncio
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Query
from db import db
from period_utils import month_query, parse_period
from cache_utils import get_or_set

router = APIRouter(tags=["dashboards"])

CACHE_TTL = 30  # seconds


def _period_filter(period_type: Optional[str], period_value: Optional[str], report_month: Optional[str]) -> Dict[str, Any]:
    if period_type:
        return month_query(period_type, period_value)
    if report_month:
        return {"report_month": report_month}
    return {}


def _strip_id(rows: List[dict]) -> List[dict]:
    for r in rows:
        r.pop("_id", None) if isinstance(r, dict) and "_id" not in ("_id",) else None
    return rows


@router.get("/dashboard/commission-summary")
async def commission_summary(
    upload_id: Optional[str] = None,
    report_month: Optional[str] = None,
    period_type: Optional[str] = None,
    period_value: Optional[str] = None,
):
    match: Dict[str, Any] = _period_filter(period_type, period_value, report_month)
    if upload_id:
        match["upload_id"] = upload_id

    cache_key = f"comm-summary::{match}"

    async def _load():
        kpi_pipe = [
            {"$match": match},
            {"$group": {
                "_id": None,
                "total_orders": {"$sum": 1},
                "total_nsv": {"$sum": {"$ifNull": ["$breakdown.nsv_val", 0]}},
                "expected_commission": {"$sum": {"$ifNull": ["$commission_incl_gst", 0]}},
                "expected_fixed_fee": {"$sum": {"$ifNull": ["$fixed_fee_incl_gst", 0]}},
                "expected_gt_charge": {"$sum": {"$ifNull": ["$gt_charge", 0]}},
                "expected_return_fee": {"$sum": {"$ifNull": ["$return_fee", 0]}},
                "expected_tcs": {"$sum": {"$ifNull": ["$tcs", 0]}},
                "expected_tds": {"$sum": {"$ifNull": ["$tds", 0]}},
                "expected_settlement": {"$sum": {"$ifNull": ["$expected_settlement", 0]}},
                "expected_deductions": {"$sum": {"$ifNull": ["$total_deductions", 0]}},
                "unmapped_orders": {"$sum": {"$cond": ["$unmapped", 1, 0]}},
            }},
        ]

        def _group_pipe(field, sort_field="nsv", limit=25):
            return [
                {"$match": match},
                {"$group": {
                    "_id": field,
                    "orders": {"$sum": 1},
                    "nsv": {"$sum": {"$ifNull": ["$breakdown.nsv_val", 0]}},
                    "commission": {"$sum": {"$ifNull": ["$commission_incl_gst", 0]}},
                    "fixed_fee": {"$sum": {"$ifNull": ["$fixed_fee_incl_gst", 0]}},
                    "gt_charge": {"$sum": {"$ifNull": ["$gt_charge", 0]}},
                    "return_fee": {"$sum": {"$ifNull": ["$return_fee", 0]}},
                    "expected_settlement": {"$sum": {"$ifNull": ["$expected_settlement", 0]}},
                }},
                {"$sort": {sort_field: -1}},
                {"$limit": limit},
            ]

        kpi_t = db.calculations.aggregate(kpi_pipe, allowDiskUse=True).to_list(1)
        by_cat_t = db.calculations.aggregate(_group_pipe("$breakdown.master_category", limit=10), allowDiskUse=True).to_list(10)
        by_subcat_t = db.calculations.aggregate(_group_pipe("$breakdown.sub_category", limit=25), allowDiskUse=True).to_list(25)
        by_zone_t = db.calculations.aggregate(_group_pipe("$breakdown.zone", limit=10), allowDiskUse=True).to_list(10)
        by_month_t = db.calculations.aggregate(_group_pipe("$report_month", sort_field="_id", limit=24), allowDiskUse=True).to_list(24)

        kpi_r, by_cat, by_subcat, by_zone, by_month = await asyncio.gather(
            kpi_t, by_cat_t, by_subcat_t, by_zone_t, by_month_t
        )
        kpi = kpi_r[0] if kpi_r else {}
        kpi.pop("_id", None)
        by_month.sort(key=lambda x: x.get("_id") or "")

        return {
            "kpi": kpi,
            "by_category": [{"category": c["_id"], **{k: v for k, v in c.items() if k != "_id"}} for c in by_cat],
            "by_sub_category": [{"sub_category": c["_id"], **{k: v for k, v in c.items() if k != "_id"}} for c in by_subcat],
            "by_zone": [{"zone": c["_id"], **{k: v for k, v in c.items() if k != "_id"}} for c in by_zone],
            "by_month": [{"month": c["_id"], **{k: v for k, v in c.items() if k != "_id"}} for c in by_month],
        }

    return await get_or_set(cache_key, CACHE_TTL, _load, tag="calculations")


@router.get("/dashboard/reconciliation-summary")
async def reconciliation_summary(
    recon_run_id: Optional[str] = None,
    report_month: Optional[str] = None,
    period_type: Optional[str] = None,
    period_value: Optional[str] = None,
):
    q: Dict[str, Any] = _period_filter(period_type, period_value, report_month)
    if recon_run_id:
        q["recon_run_id"] = recon_run_id

    cache_key = f"recon-summary::{q}"

    async def _load():
        total_t = db.discrepancies.count_documents(q)
        by_sev_t = db.discrepancies.aggregate([
            {"$match": q},
            {"$group": {"_id": "$severity", "count": {"$sum": 1}, "recoverable": {"$sum": "$recoverable"}}},
        ], allowDiskUse=True).to_list(10)
        by_status_t = db.discrepancies.aggregate([
            {"$match": q},
            {"$group": {"_id": "$match_status", "count": {"$sum": 1}}},
        ], allowDiskUse=True).to_list(10)
        by_component_t = db.discrepancies.aggregate([
            {"$match": q},
            {"$unwind": "$components"},
            {"$match": {"components.status": {"$in": ["overcharged", "undercharged"]}}},
            {"$group": {"_id": "$components.component", "count": {"$sum": 1}, "variance_sum": {"$sum": {"$abs": "$components.variance"}}}},
            {"$sort": {"variance_sum": -1}},
        ], allowDiskUse=True).to_list(20)
        tr_t = db.discrepancies.aggregate([
            {"$match": q}, {"$group": {"_id": None, "sum": {"$sum": "$recoverable"}}},
        ]).to_list(1)
        top_t = db.discrepancies.find(q, {"_id": 0}).sort("recoverable", -1).limit(10).to_list(10)

        total, by_sev, by_status, by_component, tr, top = await asyncio.gather(
            total_t, by_sev_t, by_status_t, by_component_t, tr_t, top_t
        )
        total_recoverable = tr[0]["sum"] if tr else 0

        return {
            "total_discrepancies": total,
            "total_recoverable": round(total_recoverable or 0, 2),
            "by_severity": [{"severity": s["_id"], "count": s["count"], "recoverable": round(s.get("recoverable", 0), 2)} for s in by_sev],
            "by_match_status": [{"status": s["_id"], "count": s["count"]} for s in by_status],
            "by_component": [{"component": c["_id"], "count": c["count"], "variance_sum": round(c["variance_sum"], 2)} for c in by_component],
            "top_discrepancies": top,
        }

    return await get_or_set(cache_key, CACHE_TTL, _load, tag="discrepancies")


@router.get("/dashboard/overview")
async def overview(
    report_month: Optional[str] = None,
    period_type: Optional[str] = None,
    period_value: Optional[str] = None,
):
    q = _period_filter(period_type, period_value, report_month)
    cache_key = f"overview::{q}"

    async def _load():
        crit_q = {**q, "severity": "critical"}
        high_q = {**q, "severity": "high"}
        unm_q = {**q, "unmapped": True}
        results = await asyncio.gather(
            db.sales.count_documents(q),
            db.calculations.count_documents(q),
            db.settlement.count_documents(q),
            db.discrepancies.count_documents(q),
            db.discrepancies.count_documents(crit_q),
            db.discrepancies.count_documents(high_q),
            db.calculations.count_documents(unm_q),
            db.recon_runs.find({}, {"_id": 0}).sort("created_at", -1).limit(1).to_list(1),
        )
        total_sales, total_calcs, total_settle, total_disc, open_critical, open_high, unmapped, latest_run = results
        return {
            "total_sales": total_sales,
            "total_calculations": total_calcs,
            "total_settlement_rows": total_settle,
            "total_discrepancies": total_disc,
            "open_critical": open_critical,
            "open_high": open_high,
            "unmapped_calculations": unmapped,
            "latest_run": latest_run[0] if latest_run else None,
        }

    return await get_or_set(cache_key, CACHE_TTL, _load, tag="overview")


@router.get("/dashboard/periods")
async def available_periods():
    async def _load():
        months = set()
        async for r in db.sales.aggregate([
            {"$match": {"report_month": {"$ne": None}}},
            {"$group": {"_id": "$report_month"}},
        ]):
            months.add(r["_id"])
        months_list = sorted(list(months))
        years = sorted({m[:4] for m in months_list})
        quarters = sorted({f"{m[:4]}-Q{((int(m[5:7]) - 1) // 3) + 1}" for m in months_list})
        return {"months": months_list, "quarters": quarters, "years": years}

    return await get_or_set("periods", 60, _load, tag="periods")


@router.get("/dashboard/return-velocity")
async def return_velocity(
    report_month: Optional[str] = None,
    period_type: Optional[str] = None,
    period_value: Optional[str] = None,
    top: int = 15,
):
    """% of orders that flipped from Sales to Return-DTO, by sub-category.

    fixed_fee_leakage = sum of fixed_fee_incl_gst on return_dto rows (that's the
    net loss for a DTO order — the seller keeps NSV but pays the fixed fee).
    """
    q = _period_filter(period_type, period_value, report_month)
    cache_key = f"return-velocity::{q}::{top}"

    async def _load():
        pipeline = [
            {"$match": q},
            {"$group": {
                "_id": "$breakdown.sub_category",
                "orders": {"$sum": {"$cond": [{"$eq": ["$order_type", "sales"]}, 1, 0]}},
                "return_dto_orders": {"$sum": {"$cond": [{"$eq": ["$order_type", "return_dto"]}, 1, 0]}},
                "return_orders": {"$sum": {"$cond": [{"$eq": ["$order_type", "return"]}, 1, 0]}},
                "rto_orders": {"$sum": {"$cond": [{"$eq": ["$order_type", "rto"]}, 1, 0]}},
                "leakage": {"$sum": {"$cond": [
                    {"$eq": ["$order_type", "return_dto"]},
                    {"$ifNull": ["$return_fee", 0]},
                    0,
                ]}},
                "sales_nsv": {"$sum": {"$cond": [
                    {"$eq": ["$order_type", "sales"]},
                    {"$ifNull": ["$breakdown.nsv_val", 0]},
                    0,
                ]}},
            }},
            {"$match": {"_id": {"$ne": None}}},
            {"$addFields": {
                "velocity_pct": {
                    "$cond": [
                        {"$gt": ["$orders", 0]},
                        {"$divide": ["$return_dto_orders", "$orders"]},
                        0,
                    ],
                },
            }},
            {"$sort": {"leakage": -1}},
            {"$limit": top},
        ]
        rows = [{"sub_category": r["_id"], **{k: v for k, v in r.items() if k != "_id"}}
                async for r in db.calculations.aggregate(pipeline, allowDiskUse=True)]

        totals_pipe = [
            {"$match": q},
            {"$group": {
                "_id": "$order_type",
                "count": {"$sum": 1},
                "return_fee": {"$sum": {"$ifNull": ["$return_fee", 0]}},
            }},
        ]
        totals: Dict[str, Any] = {}
        async for r in db.calculations.aggregate(totals_pipe):
            totals[r["_id"]] = {"count": r["count"], "return_fee": r["return_fee"]}

        sales_count = (totals.get("sales") or {}).get("count", 0)
        return_dto_count = (totals.get("return_dto") or {}).get("count", 0)
        overall_velocity = (return_dto_count / sales_count) if sales_count else 0
        total_leakage = (totals.get("return_dto") or {}).get("return_fee", 0)

        return {
            "overall": {
                "sales_orders": sales_count,
                "return_dto_orders": return_dto_count,
                "return_orders": (totals.get("return") or {}).get("count", 0),
                "rto_orders": (totals.get("rto") or {}).get("count", 0),
                "internal_cancel_orders": (totals.get("internal_cancel") or {}).get("count", 0),
                "velocity_pct": overall_velocity,
                "total_leakage": total_leakage,
            },
            "by_sub_category": rows,
        }

    return await get_or_set(cache_key, CACHE_TTL, _load, tag="calculations")
