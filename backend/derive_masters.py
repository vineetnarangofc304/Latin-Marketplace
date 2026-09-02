"""Derive the GT (logistics) charge matrix and Return Fee matrix for Latin Quarter
from their own loaded Myntra data, populate the gt_charges / return_fees collections,
and export a complete masters seed (all 5 contract-master collections) to
latin_masters_seed.json so bootstrap can auto-seed a fresh DB (production).
"""
import os
import json
import asyncio
import statistics
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from motor.motor_asyncio import AsyncIOMotorClient
import uuid

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
SEED_PATH = Path(__file__).parent / "latin_masters_seed.json"

BANDS = [(0, 250, "0-250"), (250, 450, "250-450"), (450, 700, "450-700"),
         (700, 1050, "700-1050"), (1050, 1800, "1050-1800"), (1800, 10000000, ">1800")]
ZONES = ["Local", "Zonal", "National"]


def _uid():
    return str(uuid.uuid4())


def _band(isp):
    for lo, hi, label in BANDS:
        if lo <= isp <= hi:
            return lo, hi, label
    return BANDS[-1]


async def derive():
    level_map = {}
    async for s in db.subcat_levels.find({}, {"_id": 0}):
        level_map[(s["sub_category"] or "").strip().lower()] = s["level"]

    # Collect logistics values per (sub_category, band) for forward sales, and
    # per (level, zone) for returns, from calculations joined with breakdown.
    gt_samples = {}   # (subcat, band_label) -> [charges]
    lvlband_samples = {}  # (level, band_label) -> [charges]
    lvl_samples = {}  # level -> [charges]
    global_gt = []
    ret_samples = {}  # (level, zone) -> [fees]
    subcat_names = {}  # lower -> original casing

    async for c in db.calculations.find({}, {"_id": 0, "breakdown": 1, "gt_charge": 1,
                                             "fixed_fee": 1, "order_type": 1}):
        bd = c.get("breakdown") or {}
        sub = (bd.get("sub_category") or "").strip()
        if not sub:
            continue
        subl = sub.lower()
        subcat_names[subl] = sub
        isp = abs(float(bd.get("isp") or bd.get("nsv_val") or 0))
        _, _, band_label = _band(isp)
        gt = abs(float(c.get("gt_charge") or 0))
        level = level_map.get(subl) or bd.get("level")
        if c.get("order_type") in ("return", "return_dto"):
            zone = bd.get("zone")
            if level and zone:
                ret_samples.setdefault((level, zone), []).append(gt)
        else:
            if gt > 0:
                gt_samples.setdefault((subl, band_label), []).append(gt)
                if level:
                    lvlband_samples.setdefault((level, band_label), []).append(gt)
                    lvl_samples.setdefault(level, []).append(gt)
                global_gt.append(gt)

    # Build GT matrix: every sub-category in the level map x every band.
    def _med(vals):
        return round(statistics.median(vals), 2) if vals else None

    global_med = _med(global_gt) or 0.0
    gt_rows = []
    for subl, level in level_map.items():
        sub = subcat_names.get(subl, subl.title())
        sub_all = [v for (s, b), vals in gt_samples.items() if s == subl for v in vals]
        sub_fallback = _med(sub_all)
        lvl_fallback = _med(lvl_samples.get(level))
        for lo, hi, label in BANDS:
            charge = (_med(gt_samples.get((subl, label)))
                      or sub_fallback
                      or _med(lvlband_samples.get((level, label)))
                      or lvl_fallback
                      or global_med)
            gt_rows.append({
                "id": _uid(), "sub_category": sub, "level": level,
                "price_range": label, "price_lower": lo, "price_upper": hi,
                "charge": round(charge, 2), "active": True,
            })

    # Build Return Fee matrix: every level present x every zone.
    levels = sorted(set(level_map.values()))
    # global median as fallback
    all_ret = [v for vals in ret_samples.values() for v in vals]
    ret_fallback = round(statistics.median(all_ret), 2) if all_ret else 0.0
    ret_rows = []
    for level in levels:
        lvl_vals = [v for (l, z), vals in ret_samples.items() if l == level for v in vals]
        lvl_fallback = round(statistics.median(lvl_vals), 2) if lvl_vals else ret_fallback
        for zone in ZONES:
            vals = ret_samples.get((level, zone))
            fee = round(statistics.median(vals), 2) if vals else lvl_fallback
            ret_rows.append({"id": _uid(), "level": level, "zone": zone, "fee": fee, "active": True})

    await db.gt_charges.delete_many({})
    await db.return_fees.delete_many({})
    if gt_rows:
        await db.gt_charges.insert_many([dict(r) for r in gt_rows])
    if ret_rows:
        await db.return_fees.insert_many([dict(r) for r in ret_rows])
    print(f"[derive] gt_charges={len(gt_rows)} return_fees={len(ret_rows)} levels={levels}")

    # Export complete masters seed for bootstrap (production fresh DB).
    seed = {}
    for coll in ("commission_rules", "fixed_fees", "subcat_levels", "gt_charges", "return_fees"):
        seed[coll] = await db[coll].find({}, {"_id": 0}).to_list(100000)
    with open(SEED_PATH, "w") as f:
        json.dump(seed, f)
    print(f"[derive] wrote {SEED_PATH} sizes=" +
          ", ".join(f"{k}={len(v)}" for k, v in seed.items()))


if __name__ == "__main__":
    asyncio.run(derive())
