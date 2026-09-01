"""AI Insights — deterministic health score + LLM-generated Morning Brief.

Deterministic metrics are computed from Mongo aggregates. The LLM (Claude
Sonnet 4.6 via emergentintegrations) produces narrative interpretation.
The endpoint remains callable even if the LLM key is missing / errors —
the narrative is then a static rule-based synopsis.
"""
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, Literal, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import db
from period_utils import month_query, parse_period


router = APIRouter(prefix="/insights", tags=["insights"])

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BriefIn(BaseModel):
    period_type: Literal["month", "quarter", "year", "ytd", "all"] = "month"
    period_value: Optional[str] = None
    tone: Literal["executive", "operational", "concise"] = "executive"


async def _collect_metrics(period_type: str, period_value: Optional[str]) -> Dict[str, Any]:
    match = month_query(period_type, period_value)
    _, label = parse_period(period_type, period_value) if period_value or period_type == "all" else ([], "")

    # Calculations rollup
    calc_agg = await db.calculations.aggregate([
        {"$match": match},
        {"$group": {
            "_id": None,
            "orders": {"$sum": 1},
            "unmapped": {"$sum": {"$cond": ["$unmapped", 1, 0]}},
            "nsv": {"$sum": {"$ifNull": ["$breakdown.nsv_val", 0]}},
            "expected_commission": {"$sum": {"$ifNull": ["$commission_incl_gst", 0]}},
            "expected_deductions": {"$sum": {"$ifNull": ["$total_deductions", 0]}},
            "expected_settlement": {"$sum": {"$ifNull": ["$expected_settlement", 0]}},
        }},
    ]).to_list(1)
    calc = calc_agg[0] if calc_agg else {}
    calc.pop("_id", None)

    # Discrepancy rollup
    disc_agg = await db.discrepancies.aggregate([
        {"$match": match},
        {"$group": {
            "_id": None,
            "count": {"$sum": 1},
            "recoverable": {"$sum": {"$ifNull": ["$recoverable", 0]}},
            "critical": {"$sum": {"$cond": [{"$eq": ["$severity", "critical"]}, 1, 0]}},
            "high": {"$sum": {"$cond": [{"$eq": ["$severity", "high"]}, 1, 0]}},
        }},
    ]).to_list(1)
    disc = disc_agg[0] if disc_agg else {}
    disc.pop("_id", None)

    # Recovery rollup
    rec_agg = await db.recovery_cases.aggregate([
        {"$match": match},
        {"$group": {
            "_id": None,
            "cases": {"$sum": 1},
            "recovered": {"$sum": {"$ifNull": ["$recovered_amount", 0]}},
            "open": {"$sum": {"$cond": [{"$in": ["$status", ["open", "in_review", "submitted"]]}, 1, 0]}},
        }},
    ]).to_list(1)
    rec = rec_agg[0] if rec_agg else {}
    rec.pop("_id", None)

    # Top 3 offending sub-categories by expected commission
    top_subs = await db.calculations.aggregate([
        {"$match": match},
        {"$group": {
            "_id": "$breakdown.sub_category",
            "orders": {"$sum": 1},
            "nsv": {"$sum": {"$ifNull": ["$breakdown.nsv_val", 0]}},
            "commission": {"$sum": {"$ifNull": ["$commission_incl_gst", 0]}},
        }},
        {"$match": {"_id": {"$ne": None}}},
        {"$sort": {"commission": -1}},
        {"$limit": 3},
    ]).to_list(3)
    top_subs = [{"sub_category": r["_id"], **{k: r[k] for k in ("orders", "nsv", "commission")}} for r in top_subs]

    return {
        "period_type": period_type,
        "period_value": period_value,
        "label": label,
        "calc": calc,
        "disc": disc,
        "recovery": rec,
        "top_sub_categories": top_subs,
    }


def _compute_health(m: Dict[str, Any]) -> Dict[str, Any]:
    """Return {score 0-100, components, grade, headline}.

    Components:
      mapping_health   — 100 * (1 - unmapped/orders)
      leakage_health   — 100 * (1 - recoverable/nsv), floored at 0
      margin_health    — 100 * settlement/nsv  (clip 0..100)
      recovery_health  — 100 * recovered/recoverable  (or 100 if no leakage)
    """
    calc = m["calc"] or {}
    disc = m["disc"] or {}
    rec = m["recovery"] or {}

    orders = float(calc.get("orders") or 0)
    unmapped = float(calc.get("unmapped") or 0)
    nsv = float(calc.get("nsv") or 0)
    settlement = float(calc.get("expected_settlement") or 0)
    recoverable = float(disc.get("recoverable") or 0)
    recovered = float(rec.get("recovered") or 0)

    mapping_health = 100 * (1 - (unmapped / orders)) if orders else 0
    leakage_ratio = (recoverable / nsv) if nsv else 0
    leakage_health = max(0, 100 * (1 - min(1, leakage_ratio * 20)))  # 5% leakage → 0
    margin_health = max(0, min(100, 100 * (settlement / nsv))) if nsv else 0
    if recoverable > 0:
        recovery_health = max(0, min(100, 100 * recovered / recoverable))
    else:
        recovery_health = 100

    # Weighted
    weights = {"mapping": 0.25, "leakage": 0.35, "margin": 0.25, "recovery": 0.15}
    score = (
        weights["mapping"] * mapping_health
        + weights["leakage"] * leakage_health
        + weights["margin"] * margin_health
        + weights["recovery"] * recovery_health
    )

    grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D" if score >= 45 else "F"
    headline = {
        "A": "Excellent — leakage contained, margins healthy.",
        "B": "Healthy — a few gaps to close.",
        "C": "Attention needed — leakage or mapping gaps building up.",
        "D": "At risk — meaningful revenue leakage detected.",
        "F": "Critical — urgent action required to reclaim margin.",
    }[grade]

    return {
        "score": round(score, 1),
        "grade": grade,
        "headline": headline,
        "components": {
            "mapping_health": round(mapping_health, 1),
            "leakage_health": round(leakage_health, 1),
            "margin_health": round(margin_health, 1),
            "recovery_health": round(recovery_health, 1),
        },
        "weights": weights,
        "raw": {
            "orders": orders, "unmapped": unmapped, "nsv": nsv,
            "settlement": settlement, "recoverable": recoverable, "recovered": recovered,
            "leakage_ratio": leakage_ratio,
        },
    }


def _fallback_brief(m: Dict[str, Any], health: Dict[str, Any]) -> str:
    calc = m["calc"] or {}
    disc = m["disc"] or {}
    rec = m["recovery"] or {}
    label = m.get("label") or "the selected period"

    lines = [
        f"**{label} — Finance Snapshot**",
        f"Health score: **{health['score']}/100 ({health['grade']})** — {health['headline']}",
        "",
        "**Key numbers**",
        f"- Orders processed: {int(calc.get('orders') or 0):,} (unmapped: {int(calc.get('unmapped') or 0):,})",
        f"- NSV: ₹{calc.get('nsv', 0):,.0f} · Expected settlement: ₹{calc.get('expected_settlement', 0):,.0f}",
        f"- Discrepancies: {int(disc.get('count') or 0):,} · Recoverable: ₹{disc.get('recoverable', 0):,.0f}",
        f"- Recovery cases: {int(rec.get('cases') or 0):,} · Recovered so far: ₹{rec.get('recovered', 0):,.0f}",
        "",
        "**Where to look first**",
    ]
    for s in m.get("top_sub_categories", [])[:3]:
        lines.append(f"- {s['sub_category']}: ₹{s['commission']:,.0f} commission on ₹{s['nsv']:,.0f} NSV ({s['orders']:,} orders)")
    return "\n".join(lines)


async def _llm_narrative(m: Dict[str, Any], health: Dict[str, Any], tone: str) -> Optional[str]:
    if not EMERGENT_LLM_KEY:
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except Exception:
        return None
    try:
        system = (
            "You are the CFO's marketplace-finance analyst for a fashion brand selling on Myntra. "
            "You produce short, structured daily briefs in a "
            f"{tone} tone. Never invent numbers — only use the ones supplied. "
            "Format the output in clean Markdown with headings (H3), bullet points, and no code fences."
        )
        prompt = (
            f"Period: {m.get('label')}\n"
            f"Health score: {health['score']} ({health['grade']}) — {health['headline']}\n"
            f"Components: {health['components']}\n"
            f"Calculations: {m.get('calc')}\n"
            f"Discrepancies: {m.get('disc')}\n"
            f"Recovery: {m.get('recovery')}\n"
            f"Top sub-categories by expected commission: {m.get('top_sub_categories')}\n\n"
            "Write a Morning Finance Brief with these sections in order:\n"
            "1. **Headline** — one crisp sentence.\n"
            "2. **What went well** — 2 bullets max.\n"
            "3. **What needs attention** — 2-3 bullets, most material first, quote the numbers.\n"
            "4. **Recommended actions today** — 2-3 imperative bullets tied to the numbers.\n"
        )
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"insights-{uuid.uuid4()}",
            system_message=system,
        ).with_model("anthropic", "claude-sonnet-4-6")
        resp = await chat.send_message(UserMessage(text=prompt))
        # send_message returns str for non-streaming
        return str(resp) if resp else None
    except Exception as e:
        return f"_LLM narrative unavailable ({type(e).__name__}). Showing rule-based summary instead._"


@router.get("/health-score")
async def health_score(
    period_type: Literal["month", "quarter", "year", "ytd", "all"] = "month",
    period_value: Optional[str] = None,
):
    metrics = await _collect_metrics(period_type, period_value)
    health = _compute_health(metrics)
    return {
        "period_type": period_type,
        "period_value": period_value,
        "label": metrics.get("label"),
        "health": health,
        "metrics": {
            "calc": metrics["calc"],
            "disc": metrics["disc"],
            "recovery": metrics["recovery"],
        },
    }


@router.post("/morning-brief")
async def morning_brief(payload: BriefIn):
    metrics = await _collect_metrics(payload.period_type, payload.period_value)
    health = _compute_health(metrics)

    narrative = await _llm_narrative(metrics, health, payload.tone)
    if not narrative:
        narrative = _fallback_brief(metrics, health)
        source = "rule_based"
    else:
        source = "llm"

    # Cache the last brief per period for lightweight audit trail
    await db.insights_briefs.insert_one({
        "id": str(uuid.uuid4()),
        "period_type": payload.period_type,
        "period_value": payload.period_value,
        "tone": payload.tone,
        "score": health["score"],
        "grade": health["grade"],
        "narrative": narrative,
        "source": source,
        "created_at": _now(),
    })

    return {
        "label": metrics.get("label"),
        "health": health,
        "narrative": narrative,
        "source": source,
    }


@router.get("/briefs")
async def list_briefs(limit: int = 20):
    items = await db.insights_briefs.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return items
