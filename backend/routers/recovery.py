"""Recovery Management — case tracking for discrepancies.

Cases are created from discrepancies (auto or manual). Each case has
status transitions, notes/communication log, and evidence attachments
(files stored in-doc as base64 to keep the stack simple).
"""
import base64
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Literal

from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Form, Response
from pydantic import BaseModel, Field

from db import db
from period_utils import month_query


router = APIRouter(prefix="/recovery", tags=["recovery"])


CASE_STATUSES = ("open", "in_review", "submitted", "recovered", "rejected", "closed")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _nid() -> str:
    return str(uuid.uuid4())


def _clean(doc: dict) -> dict:
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


# ---------- Models ----------
class CreateCaseIn(BaseModel):
    discrepancy_id: str
    assigned_to: Optional[str] = None
    priority: Optional[Literal["low", "medium", "high", "critical"]] = None
    notes: Optional[str] = None


class UpdateCaseIn(BaseModel):
    status: Optional[Literal["open", "in_review", "submitted", "recovered", "rejected", "closed"]] = None
    assigned_to: Optional[str] = None
    priority: Optional[Literal["low", "medium", "high", "critical"]] = None
    recovered_amount: Optional[float] = None
    resolution_notes: Optional[str] = None


class AddNoteIn(BaseModel):
    channel: Literal["email", "call", "chat", "note", "myntra_ticket"] = "note"
    direction: Literal["outbound", "inbound", "internal"] = "internal"
    subject: Optional[str] = None
    body: str


class AutoCreateIn(BaseModel):
    period_type: Literal["month", "quarter", "year", "ytd", "all"] = "month"
    period_value: Optional[str] = None
    min_recoverable: float = 0.0
    severities: Optional[List[str]] = None  # e.g. ["critical", "high"]
    only_open: bool = True  # skip discrepancies already tied to an open case


# ---------- Helpers ----------
async def _load_disc(disc_id: str) -> dict:
    d = await db.discrepancies.find_one({"id": disc_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Discrepancy not found")
    return d


async def _load_case(case_id: str) -> dict:
    c = await db.recovery_cases.find_one({"id": case_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Case not found")
    return c


async def _existing_case_for(disc_id: str) -> Optional[dict]:
    return await db.recovery_cases.find_one(
        {"discrepancy_id": disc_id, "status": {"$nin": ["closed", "rejected"]}},
        {"_id": 0},
    )


def _default_priority(severity: str) -> str:
    return {"critical": "critical", "high": "high", "medium": "medium"}.get(severity or "", "low")


# ---------- Routes ----------
@router.get("/cases")
async def list_cases(
    period_type: str = "all",
    period_value: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    severity: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "recoverable_amount",
    sort_dir: str = "desc",
    limit: int = 500,
    skip: int = 0,
):
    q: dict = {}
    q.update(month_query(period_type, period_value))
    if status:
        q["status"] = status
    if priority:
        q["priority"] = priority
    if severity:
        q["severity"] = severity
    if search:
        q["$or"] = [
            {"online_order_id": {"$regex": search, "$options": "i"}},
            {"sku": {"$regex": search, "$options": "i"}},
        ]

    sort_key = {
        "recoverable_amount": "recoverable_amount",
        "created": "created_at",
        "updated": "updated_at",
        "severity": "severity",
        "status": "status",
    }.get(sort_by, "recoverable_amount")
    direction = -1 if sort_dir == "desc" else 1

    cursor = db.recovery_cases.find(q, {"_id": 0}).sort(sort_key, direction).skip(skip).limit(limit)
    items = await cursor.to_list(limit)
    total = await db.recovery_cases.count_documents(q)
    return {"items": items, "total": total}


@router.get("/cases/{case_id}")
async def get_case(case_id: str):
    c = await _load_case(case_id)
    # Enrich with discrepancy detail
    disc = await db.discrepancies.find_one({"id": c["discrepancy_id"]}, {"_id": 0})
    return {"case": c, "discrepancy": disc}


@router.post("/cases")
async def create_case(payload: CreateCaseIn):
    disc = await _load_disc(payload.discrepancy_id)
    existing = await _existing_case_for(payload.discrepancy_id)
    if existing:
        raise HTTPException(409, f"Case {existing['id'][:8]} already open for this discrepancy")

    now = _now()
    case = {
        "id": _nid(),
        "discrepancy_id": disc["id"],
        "recon_run_id": disc.get("recon_run_id"),
        "online_order_id": disc.get("online_order_id"),
        "sku": disc.get("sku"),
        "sales_id": disc.get("sales_id"),
        "settlement_id": disc.get("settlement_id"),
        "severity": disc.get("severity"),
        "reason": disc.get("reason"),
        "match_status": disc.get("match_status"),
        "recoverable_amount": float(disc.get("recoverable") or 0),
        "settle_variance": float(disc.get("settle_variance") or 0),
        "report_month": disc.get("report_month"),
        "status": "open",
        "priority": payload.priority or _default_priority(disc.get("severity")),
        "assigned_to": payload.assigned_to,
        "recovered_amount": 0.0,
        "resolution_notes": None,
        "notes_count": 1 if payload.notes else 0,
        "evidence_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    await db.recovery_cases.insert_one(dict(case))

    if payload.notes:
        await db.recovery_notes.insert_one({
            "id": _nid(),
            "case_id": case["id"],
            "channel": "note",
            "direction": "internal",
            "subject": "Case opened",
            "body": payload.notes,
            "created_at": now,
        })
    return _clean(case)


@router.post("/cases/auto-create")
async def auto_create(payload: AutoCreateIn):
    """Bulk-create recovery cases from open discrepancies matching filters."""
    q: dict = {}
    q.update(month_query(payload.period_type, payload.period_value))
    if payload.severities:
        q["severity"] = {"$in": payload.severities}
    if payload.min_recoverable > 0:
        q["recoverable"] = {"$gte": payload.min_recoverable}
    else:
        q["recoverable"] = {"$gt": 0}

    discs = await db.discrepancies.find(q, {"_id": 0}).to_list(5000)

    created = 0
    skipped = 0
    for d in discs:
        if payload.only_open:
            existing = await _existing_case_for(d["id"])
            if existing:
                skipped += 1
                continue
        now = _now()
        case = {
            "id": _nid(),
            "discrepancy_id": d["id"],
            "recon_run_id": d.get("recon_run_id"),
            "online_order_id": d.get("online_order_id"),
            "sku": d.get("sku"),
            "sales_id": d.get("sales_id"),
            "settlement_id": d.get("settlement_id"),
            "severity": d.get("severity"),
            "reason": d.get("reason"),
            "match_status": d.get("match_status"),
            "recoverable_amount": float(d.get("recoverable") or 0),
            "settle_variance": float(d.get("settle_variance") or 0),
            "report_month": d.get("report_month"),
            "status": "open",
            "priority": _default_priority(d.get("severity")),
            "assigned_to": None,
            "recovered_amount": 0.0,
            "resolution_notes": None,
            "notes_count": 0,
            "evidence_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        await db.recovery_cases.insert_one(dict(case))
        created += 1

    return {"created": created, "skipped": skipped, "candidates": len(discs)}


@router.patch("/cases/{case_id}")
async def update_case(case_id: str, payload: UpdateCaseIn):
    c = await _load_case(case_id)
    update = {"updated_at": _now()}
    if payload.status is not None:
        update["status"] = payload.status
        if payload.status == "recovered" and payload.recovered_amount is None:
            update["recovered_amount"] = c.get("recoverable_amount", 0)
    if payload.assigned_to is not None:
        update["assigned_to"] = payload.assigned_to
    if payload.priority is not None:
        update["priority"] = payload.priority
    if payload.recovered_amount is not None:
        update["recovered_amount"] = float(payload.recovered_amount)
    if payload.resolution_notes is not None:
        update["resolution_notes"] = payload.resolution_notes

    await db.recovery_cases.update_one({"id": case_id}, {"$set": update})
    return await _load_case(case_id)


@router.get("/cases/{case_id}/notes")
async def list_notes(case_id: str):
    await _load_case(case_id)
    notes = await db.recovery_notes.find({"case_id": case_id}, {"_id": 0}).sort("created_at", 1).to_list(500)
    return notes


@router.post("/cases/{case_id}/notes")
async def add_note(case_id: str, payload: AddNoteIn):
    await _load_case(case_id)
    now = _now()
    note = {
        "id": _nid(),
        "case_id": case_id,
        "channel": payload.channel,
        "direction": payload.direction,
        "subject": payload.subject,
        "body": payload.body,
        "created_at": now,
    }
    await db.recovery_notes.insert_one(dict(note))
    await db.recovery_cases.update_one(
        {"id": case_id},
        {"$inc": {"notes_count": 1}, "$set": {"updated_at": now}},
    )
    return _clean(note)


@router.get("/cases/{case_id}/evidence")
async def list_evidence(case_id: str):
    await _load_case(case_id)
    items = await db.recovery_evidence.find(
        {"case_id": case_id},
        {"_id": 0, "data_b64": 0},  # exclude blob from list
    ).sort("uploaded_at", -1).to_list(200)
    return items


@router.post("/cases/{case_id}/evidence")
async def upload_evidence(case_id: str, file: UploadFile = File(...), description: Optional[str] = Form(None)):
    await _load_case(case_id)
    raw = await file.read()
    max_size = 15 * 1024 * 1024  # 15MB
    if len(raw) > max_size:
        raise HTTPException(413, f"File too large. Max {max_size // (1024*1024)}MB.")
    now = _now()
    doc = {
        "id": _nid(),
        "case_id": case_id,
        "filename": file.filename,
        "content_type": file.content_type or "application/octet-stream",
        "size_bytes": len(raw),
        "description": description,
        "data_b64": base64.b64encode(raw).decode("ascii"),
        "uploaded_at": now,
    }
    await db.recovery_evidence.insert_one(dict(doc))
    await db.recovery_cases.update_one(
        {"id": case_id},
        {"$inc": {"evidence_count": 1}, "$set": {"updated_at": now}},
    )
    doc.pop("data_b64", None)
    return _clean(doc)


@router.get("/evidence/{evidence_id}/download")
async def download_evidence(evidence_id: str):
    e = await db.recovery_evidence.find_one({"id": evidence_id})
    if not e:
        raise HTTPException(404, "Evidence not found")
    raw = base64.b64decode(e["data_b64"])
    headers = {"Content-Disposition": f'attachment; filename="{e.get("filename", "evidence.bin")}"'}
    return Response(content=raw, media_type=e.get("content_type", "application/octet-stream"), headers=headers)


@router.delete("/evidence/{evidence_id}")
async def delete_evidence(evidence_id: str):
    e = await db.recovery_evidence.find_one({"id": evidence_id}, {"_id": 0, "data_b64": 0})
    if not e:
        raise HTTPException(404, "Evidence not found")
    await db.recovery_evidence.delete_one({"id": evidence_id})
    await db.recovery_cases.update_one(
        {"id": e["case_id"]},
        {"$inc": {"evidence_count": -1}, "$set": {"updated_at": _now()}},
    )
    return {"ok": True}


@router.delete("/cases/{case_id}")
async def delete_case(case_id: str):
    await _load_case(case_id)
    await db.recovery_notes.delete_many({"case_id": case_id})
    await db.recovery_evidence.delete_many({"case_id": case_id})
    await db.recovery_cases.delete_one({"id": case_id})
    return {"ok": True}


@router.get("/summary")
async def summary(period_type: str = "all", period_value: Optional[str] = None):
    q: dict = {}
    q.update(month_query(period_type, period_value))

    # Aggregate by status
    by_status_cur = db.recovery_cases.aggregate([
        {"$match": q},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1},
            "recoverable": {"$sum": "$recoverable_amount"},
            "recovered": {"$sum": "$recovered_amount"},
        }},
    ])
    by_status = [{"status": r["_id"], "count": r["count"],
                  "recoverable": r["recoverable"], "recovered": r["recovered"]}
                 async for r in by_status_cur]

    by_priority_cur = db.recovery_cases.aggregate([
        {"$match": q},
        {"$group": {
            "_id": "$priority",
            "count": {"$sum": 1},
            "recoverable": {"$sum": "$recoverable_amount"},
        }},
    ])
    by_priority = [{"priority": r["_id"], "count": r["count"], "recoverable": r["recoverable"]}
                   async for r in by_priority_cur]

    total_cur = db.recovery_cases.aggregate([
        {"$match": q},
        {"$group": {
            "_id": None,
            "count": {"$sum": 1},
            "recoverable": {"$sum": "$recoverable_amount"},
            "recovered": {"$sum": "$recovered_amount"},
        }},
    ])
    totals = None
    async for r in total_cur:
        totals = {"total_cases": r["count"], "total_recoverable": r["recoverable"], "total_recovered": r["recovered"]}
    if totals is None:
        totals = {"total_cases": 0, "total_recoverable": 0.0, "total_recovered": 0.0}

    # Count discrepancies vs cases
    disc_match: dict = {}
    disc_match.update(month_query(period_type, period_value))
    disc_match["recoverable"] = {"$gt": 0}
    disc_total = await db.discrepancies.count_documents(disc_match)

    coverage_pct = (totals["total_cases"] / disc_total) if disc_total else 0

    return {
        "period_type": period_type,
        "period_value": period_value,
        "totals": totals,
        "by_status": by_status,
        "by_priority": by_priority,
        "discrepancy_universe": disc_total,
        "case_coverage_pct": coverage_pct,
    }
