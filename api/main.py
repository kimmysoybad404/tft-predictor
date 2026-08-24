"""
TFT Meta Analyzer API
Endpoints for analyzing traits, augments, units, and items
from high-ranked TFT players across regions.
"""

import sys
import os
import time
import asyncio
import logging
import requests
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo.database import Database
from typing import Optional
from database import get_db
import cdragon

RIOT_API_KEY = os.getenv("RIOT_API_KEY")

log = logging.getLogger(__name__)

CDRAGON_REFRESH_INTERVAL_HOURS = 12

# ── Predictor (load ตอน startup) ──────────────────────────────────────────────
predictor = None

def load_predictor():
    global predictor
    try:
        # ml folder ถูก mount ที่ /app/ml เสมอ
        ml_path = "/app/ml"
        sys.path.insert(0, ml_path)

        # เปลี่ยน working dir ไปที่ ml เพื่อให้ joblib.load หาไฟล์เจอ
        os.chdir(ml_path)

        from predict import TFTPredictor
        predictor = TFTPredictor()
        print("[INFO] Predictor loaded successfully")
    except Exception as e:
        print(f"[WARNING] Could not load predictor: {e}")
        predictor = None


async def periodic_cdragon_refresh():
    """เช็ค mapping ใหม่จาก Community Dragon เป็นระยะ กัน set ใหม่ออกแล้ว mapping ค้าง โดยไม่ต้อง restart service"""
    while True:
        await asyncio.sleep(CDRAGON_REFRESH_INTERVAL_HOURS * 60 * 60)
        try:
            await asyncio.to_thread(cdragon.refresh)
        except Exception as e:
            log.warning(f"periodic cdragon refresh failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_predictor()
    await asyncio.to_thread(cdragon.refresh)
    refresh_task = asyncio.create_task(periodic_cdragon_refresh())
    yield
    refresh_task.cancel()

app = FastAPI(
    title="TFT Meta Analyzer",
    description="Analyze TFT meta from top-ranked players across regions",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Pydantic Models ───────────────────────────────────────────────────────────
class PredictRequest(BaseModel):
    active_traits: list[str]  # ["TraitName|style", ...] เช่น ["Rebel|3", "Invoker|2"]
    units:         list[str]  # ["character_id|tier", ...] เช่น ["TFT13_Jinx|2"]
    items:         list[str]  # ["ItemName", ...]
    augments:      list[str]  # ["AugmentName", ...]


# ── Filter / Aggregation Helpers ────────────────────────────────────────────────
def build_summoner_filter(region: Optional[str], tier: Optional[str], tft_set: Optional[str]) -> dict:
    """
    สร้าง $match stage สำหรับ filter participants ตาม region, tier และ tft_set
    (ถูก denormalize ไว้บน participant document ตอน ingest แล้วทั้งหมด)
    """
    match = {}
    if region:
        match["region"] = region
    if tier:
        match["tier"] = tier
    if tft_set:
        match["tft_set"] = tft_set
    return match


def _parse_trait_key(trait_key: str) -> dict:
    """แปลง 'TraitApiName|style' (ที่ ml/train.py เก็บไว้ใน key_traits) ให้เป็น {api_name, style, display_name, icon_url}"""
    name, _, style = trait_key.rpartition("|")
    return {"api_name": name, "style": int(style) if style.isdigit() else None, **cdragon.trait_info(name)}


RATE_ACCUMULATORS = {
    "top4_count": {"$sum": {"$cond": [{"$lte": ["$placement", 4]}, 1, 0]}},
    "win_count":  {"$sum": {"$cond": [{"$eq": ["$placement", 1]}, 1, 0]}},
}


def with_rates(row: dict) -> dict:
    """เติม top4_rate / win_rate จาก play_count, top4_count, win_count และตัด _id ทิ้ง"""
    row.pop("_id", None)
    play_count = row["play_count"]
    row["top4_rate"] = round(100.0 * row.pop("top4_count") / play_count, 1)
    row["win_rate"]  = round(100.0 * row.pop("win_count") / play_count, 1)
    if "avg_placement" in row:
        row["avg_placement"] = round(row["avg_placement"], 2)
    if "avg_star" in row:
        row["avg_star"] = round(row["avg_star"], 2)
    return row


# ── GET /meta/sets ────────────────────────────────────────────────────────────
@app.get("/meta/sets")
def get_meta_sets(db: Database = Depends(get_db)):
    """
    รายชื่อ TFT set ที่มีข้อมูลอยู่จริงตอนนี้ (สำหรับทำ filter dropdown ฝั่ง frontend)
    ไม่ hardcode ไว้เพราะเปลี่ยนทุกครั้งที่มี set ใหม่/set เก่าหมดอายุจาก TTL
    """
    sets = sorted(s for s in db.participants.distinct("tft_set") if s)
    return {"data": sets}


# ── GET /meta/upcoming-set ───────────────────────────────────────────────────
@app.get("/meta/upcoming-set")
def get_upcoming_set():
    """
    Preview trait ของ set ถัดไปที่ยังไม่มีคนเล่น (เลยยังไม่มีสถิติจริง)
    ข้อมูลมาจาก Community Dragon ที่ datamine ไว้ล่วงหน้า — คืน data: null ถ้ายังไม่มี
    """
    return {"data": cdragon.UPCOMING_SET}


# ── GET /builder/sets ─────────────────────────────────────────────────────────
@app.get("/builder/sets")
def get_builder_sets():
    """
    รายชื่อ TFT set ทั้งหมดที่มี roster (trait/champion) ให้เล่น Comp Builder ได้ — ทุก set ที่ cdragon มีข้อมูล
    ไม่ใช่แค่ set ที่มีสถิติจริง (ต่างจาก /meta/sets) เรียงจากใหม่ไปเก่า
    """
    sets = sorted(cdragon.SET_ROSTERS.keys(), key=lambda s: cdragon.SET_ROSTERS[s]["number"], reverse=True)
    return {"data": sets}


# ── GET /builder/roster ───────────────────────────────────────────────────────
@app.get("/builder/roster")
def get_builder_roster(tft_set: Optional[str] = Query(None, description="เช่น TFTSet17 — ไม่ใส่ = set ล่าสุด")):
    """
    Roster เต็มของ set ที่เลือก (trait พร้อม tier breakpoints + champion พร้อม cost/trait ที่ติดตัว)
    สำหรับ Comp Builder — ใช้ได้ทุก set รวมถึง set ที่ยังไม่มีสถิติจริง
    """
    if not cdragon.SET_ROSTERS:
        raise HTTPException(status_code=503, detail="Set roster not loaded yet")

    if tft_set and tft_set not in cdragon.SET_ROSTERS:
        raise HTTPException(status_code=404, detail=f"No roster data for {tft_set}")

    if not tft_set:
        tft_set = max(cdragon.SET_ROSTERS, key=lambda s: cdragon.SET_ROSTERS[s]["number"])

    return cdragon.SET_ROSTERS[tft_set]


# ── GET /meta/traits ──────────────────────────────────────────────────────────
@app.get("/meta/traits")
def get_meta_traits(
    region: Optional[str] = Query(None, description="kr, na1, euw1, sg2, br1"),
    tier:   Optional[str] = Query(None, description="challenger, grandmaster, master"),
    tft_set: Optional[str] = Query(None, description="เช่น TFTSet17"),
    top_n:  int           = Query(20,   description="จำนวนผลลัพธ์"),
    db:     Database      = Depends(get_db)
):
    """
    Top traits เรียงตาม avg_placement (ต่ำ = ดี)
    แสดง avg_placement, top4_rate, play_rate แยกตาม style
    """
    match = build_summoner_filter(region, tier, tft_set)

    pipeline = [
        {"$match": match},
        {"$unwind": "$traits"},
        {"$match": {"traits.style": {"$gt": 0}}},  # เฉพาะ trait ที่ active (ไม่เอา style=0)
        {"$group": {
            "_id":           {"name": "$traits.name", "style": "$traits.style"},
            "play_count":    {"$sum": 1},
            "avg_placement": {"$avg": "$placement"},
            **RATE_ACCUMULATORS,
        }},
        {"$match": {"play_count": {"$gte": 50}}},  # กรอง noise จาก trait ที่มีข้อมูลน้อยเกินไป
        {"$sort": {"avg_placement": 1}},
        {"$limit": top_n},
    ]

    rows = list(db.participants.aggregate(pipeline))

    return {
        "filter": {"region": region, "tier": tier, "tft_set": tft_set},
        "count": len(rows),
        "data": [
            {
                "name":  r["_id"]["name"],
                "style": r["_id"]["style"],  # 1=bronze, 2=silver, 3=gold, 4=prismatic
                **cdragon.trait_info(r["_id"]["name"]),
                **with_rates(r),
            }
            for r in rows
        ]
    }


# ── GET /meta/augments ────────────────────────────────────────────────────────
@app.get("/meta/augments")
def get_meta_augments(
    region: Optional[str] = Query(None, description="kr, na1, euw1, sg2, br1"),
    tier:   Optional[str] = Query(None, description="challenger, grandmaster, master"),
    tft_set: Optional[str] = Query(None, description="เช่น TFTSet17"),
    top_n:  int           = Query(20,   description="จำนวนผลลัพธ์"),
    db:     Database      = Depends(get_db)
):
    """
    Top augments เรียงตาม avg_placement (ต่ำ = ดี)
    augments เป็น array ใน participant document จึงต้อง $unwind ก่อน
    """
    match = build_summoner_filter(region, tier, tft_set)

    pipeline = [
        {"$match": match},
        {"$unwind": "$augments"},
        {"$group": {
            "_id":           "$augments",
            "play_count":    {"$sum": 1},
            "avg_placement": {"$avg": "$placement"},
            **RATE_ACCUMULATORS,
        }},
        {"$match": {"play_count": {"$gte": 50}}},
        {"$sort": {"avg_placement": 1}},
        {"$limit": top_n},
    ]

    rows = list(db.participants.aggregate(pipeline))

    return {
        "filter": {"region": region, "tier": tier, "tft_set": tft_set},
        "count": len(rows),
        "data": [
            {"augment": r["_id"], **cdragon.item_info(r["_id"]), **with_rates(r)}
            for r in rows
        ]
    }


# ── GET /meta/units ───────────────────────────────────────────────────────────
@app.get("/meta/units")
def get_meta_units(
    region: Optional[str] = Query(None, description="kr, na1, euw1, sg2, br1"),
    tier:   Optional[str] = Query(None, description="challenger, grandmaster, master"),
    tft_set: Optional[str] = Query(None, description="เช่น TFTSet17"),
    top_n:  int           = Query(20,   description="จำนวนผลลัพธ์"),
    db:     Database      = Depends(get_db)
):
    """
    Top units เรียงตาม avg_placement ของแมตช์ที่มี unit นั้นในบอร์ด
    แสดง avg_tier (star level) และ play_count ด้วย
    """
    match = build_summoner_filter(region, tier, tft_set)

    pipeline = [
        {"$match": match},
        {"$unwind": "$units"},  # 1 board มี character_id ซ้ำไม่ได้ ดังนั้นเท่ากับ COUNT(DISTINCT participant)
        {"$group": {
            "_id":           "$units.character_id",
            "play_count":    {"$sum": 1},
            "avg_placement": {"$avg": "$placement"},
            "avg_star":      {"$avg": "$units.tier"},
            **RATE_ACCUMULATORS,
        }},
        {"$match": {"play_count": {"$gte": 50}}},
        {"$sort": {"avg_placement": 1}},
        {"$limit": top_n},
    ]

    rows = list(db.participants.aggregate(pipeline))

    return {
        "filter": {"region": region, "tier": tier, "tft_set": tft_set},
        "count": len(rows),
        "data": [
            {"character_id": r["_id"], **cdragon.unit_info(r["_id"]), **with_rates(r)}
            for r in rows
        ]
    }


# ── GET /meta/items ───────────────────────────────────────────────────────────
@app.get("/meta/items")
def get_meta_items(
    region: Optional[str] = Query(None, description="kr, na1, euw1, sg2, br1"),
    tier:   Optional[str] = Query(None, description="challenger, grandmaster, master"),
    tft_set: Optional[str] = Query(None, description="เช่น TFTSet17"),
    top_n:  int           = Query(20,   description="จำนวนผลลัพธ์"),
    db:     Database      = Depends(get_db)
):
    """
    Top items เรียงตาม avg_placement ของแมตช์ที่มี item นั้น
    items เป็น array ซ้อนอยู่ใน units จึงต้อง $unwind สองชั้น
    """
    match = build_summoner_filter(region, tier, tft_set)

    pipeline = [
        {"$match": match},
        {"$unwind": "$units"},
        {"$unwind": "$units.items"},
        {"$match": {"units.items": {"$ne": ""}}},  # กรอง empty string
        {"$group": {
            "_id":           "$units.items",
            "play_count":    {"$sum": 1},
            "avg_placement": {"$avg": "$placement"},
            **RATE_ACCUMULATORS,
        }},
        {"$match": {"play_count": {"$gte": 50}}},
        {"$sort": {"avg_placement": 1}},
        {"$limit": top_n},
    ]

    rows = list(db.participants.aggregate(pipeline))

    return {
        "filter": {"region": region, "tier": tier, "tft_set": tft_set},
        "count": len(rows),
        "data": [
            {"item": r["_id"], **cdragon.item_info(r["_id"]), **with_rates(r)}
            for r in rows
        ]
    }


# ── GET /meta/trends ─────────────────────────────────────────────────────────
@app.get("/meta/trends")
def get_meta_trends(
    tft_set:     Optional[str] = Query(None, description="เช่น TFTSet17 — ไม่ใส่ = set ล่าสุดที่มีข้อมูล"),
    window_days: int           = Query(3,    description="ขนาดหน้าต่างเทียบ (วัน) — recent N วันล่าสุด เทียบกับ N วันก่อนหน้านั้น"),
    min_games:   int           = Query(30,   description="ขั้นต่ำจำนวนเกมต่อ trait ต่อ window กันสัญญาณรบกวนจาก sample เล็กเกินไป"),
    limit:       int           = Query(8,    description="จำนวน rising/falling ที่จะคืนแต่ละฝั่ง"),
    db:          Database      = Depends(get_db),
):
    """
    Trait ไหน "กำลังมา" (win rate ขยับขึ้น) หรือ "กำลังร่วง" (ขยับลง) เทียบ 2 ช่วงเวลาที่ผ่านมา
    ใช้ประโยชน์จากการที่ ingestion ดึงข้อมูลต่อเนื่องทุกวัน ไม่ใช่แค่ snapshot นิ่งๆ
    """
    if not tft_set:
        latest = db.matches.find_one({}, sort=[("game_datetime", -1)], projection={"tft_set_core_name": 1})
        tft_set = latest.get("tft_set_core_name") if latest else None

    now           = datetime.utcnow()
    recent_start  = now - timedelta(days=window_days)
    previous_start = now - timedelta(days=window_days * 2)

    match = {"game_datetime": {"$gte": previous_start}}
    if tft_set:
        match["tft_set"] = tft_set

    pipeline = [
        {"$match": match},
        {"$unwind": "$traits"},
        {"$match": {"traits.style": {"$gt": 0}}},
        {"$project": {
            "name":     "$traits.name",
            "style":    "$traits.style",
            "placement": 1,
            "period": {"$cond": [{"$gte": ["$game_datetime", recent_start]}, "recent", "previous"]},
        }},
        {"$group": {
            "_id":        {"name": "$name", "style": "$style", "period": "$period"},
            "play_count": {"$sum": 1},
            "top4_count": {"$sum": {"$cond": [{"$lte": ["$placement", 4]}, 1, 0]}},
        }},
    ]

    by_trait: dict[tuple, dict] = {}
    for row in db.participants.aggregate(pipeline):
        key = (row["_id"]["name"], row["_id"]["style"])
        by_trait.setdefault(key, {})[row["_id"]["period"]] = {
            "play_count": row["play_count"],
            "top4_rate":  round(100.0 * row["top4_count"] / row["play_count"], 1),
        }

    movers = []
    for (name, style), periods in by_trait.items():
        recent, previous = periods.get("recent"), periods.get("previous")
        if not recent or not previous:
            continue
        if recent["play_count"] < min_games or previous["play_count"] < min_games:
            continue
        movers.append({
            "name": name, "style": style, **cdragon.trait_info(name),
            "recent_top4_rate":   recent["top4_rate"],
            "previous_top4_rate": previous["top4_rate"],
            "delta":              round(recent["top4_rate"] - previous["top4_rate"], 1),
            "recent_play_count":  recent["play_count"],
        })

    movers.sort(key=lambda m: m["delta"], reverse=True)
    rising  = [m for m in movers if m["delta"] > 0][:limit]
    falling = sorted([m for m in movers if m["delta"] < 0], key=lambda m: m["delta"])[:limit]

    return {
        "tft_set": tft_set,
        "recent_window":   {"start": recent_start.isoformat(), "end": now.isoformat()},
        "previous_window": {"start": previous_start.isoformat(), "end": recent_start.isoformat()},
        "rising":  rising,
        "falling": falling,
        # ทุก trait ที่มีข้อมูลพอเทียบได้ (ไม่ตัด limit) — ให้ frontend เอาไป join ใส่ตารางหลักได้ทุกแถว ไม่ใช่แค่ top mover
        "all": movers,
    }


# ── GET /tier-list/traits ─────────────────────────────────────────────────────
@app.get("/tier-list/traits")
def get_trait_tier_list(
    tier: Optional[str] = Query(None, description="S, A, B, C, D"),
):
    """
    Trait tier list จาก ML model
    เรียงตาม top4_rate descending
    filter ตาม tier ได้ (S/A/B/C/D)
    """
    if predictor is None:
        raise HTTPException(status_code=503, detail="Predictor not loaded. Run train.py first.")

    data = [{**row, **cdragon.trait_info(row["name"])} for row in predictor.get_trait_tier_list(tier_filter=tier)]
    return {
        "filter": {"tier": tier},
        "count":  len(data),
        "data":   data,
    }


# ── GET /tier-list/comps ──────────────────────────────────────────────────────
@app.get("/tier-list/comps")
def get_comp_tier_list(
    tier: Optional[str] = Query(None, description="S, A, B, C, D"),
):
    """
    Comp tier list จาก ML clustering
    เรียงตาม top4_rate descending
    filter ตาม tier ได้ (S/A/B/C/D)
    """
    if predictor is None:
        raise HTTPException(status_code=503, detail="Predictor not loaded. Run train.py first.")

    data = [
        {
            **row,
            "key_traits_info": [_parse_trait_key(k) for k in row.get("key_traits", [])],
            "key_units_info":  [{"character_id": u, **cdragon.unit_info(u)} for u in row.get("key_units", [])],
        }
        for row in predictor.get_comp_tier_list(tier_filter=tier)
    ]
    return {
        "filter": {"tier": tier},
        "count":  len(data),
        "data":   data,
    }


# ── POST /predict ─────────────────────────────────────────────────────────────
@app.post("/predict")
def predict_comp(req: PredictRequest):
    """
    วิเคราะห์ comp ที่ส่งเข้ามา
    คืน top4_probability, tier, trait analysis และ similar comp
    
    ตัวอย่าง input:
    {
        "active_traits": ["Rebel|3", "Invoker|2"],
        "units": ["TFT13_Jinx|2", "TFT13_Ekko|1"],
        "items": ["TFT_Item_RabadonsDeathcap"],
        "augments": ["TFT_Augment_RebelHeart"]
    }
    """
    if predictor is None:
        raise HTTPException(status_code=503, detail="Predictor not loaded. Run train.py first.")

    try:
        result = predictor.predict_comp(
            active_traits=req.active_traits,
            units=req.units,
            items=req.items,
            augments=req.augments,
        )
        result["trait_analysis"] = [
            {**t, **cdragon.trait_info(t["trait"])} for t in result["trait_analysis"]
        ]
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Prediction failed: {str(e)}")


def _top_traits(p: dict, n: int = 3) -> list[dict]:
    traits = sorted(
        [t for t in p.get("traits", []) if t.get("style", 0) > 0],
        key=lambda t: t["style"], reverse=True,
    )[:n]
    return [{"name": t["name"], "style": t["style"], **cdragon.trait_info(t["name"])} for t in traits]


def _display_name(p: dict) -> Optional[str]:
    return f"{p['riot_id_name']}#{p['riot_id_tag']}" if p.get("riot_id_name") else None


# ── GET /leaderboard/ranked ──────────────────────────────────────────────────
@app.get("/leaderboard/ranked")
def get_ranked_leaderboard(
    region: Optional[str] = Query(None, description="kr, na1, euw1, sg2, br1"),
    tier:   Optional[str] = Query(None, description="challenger, grandmaster, master, diamond"),
    limit:  int           = Query(50,   description="จำนวนผู้เล่น"),
    db:     Database      = Depends(get_db),
):
    """
    Ranked leaderboard แบบ op.gg — อันดับ, ชื่อ, tier, LP, top4 rate, จำนวนเกม เรียงตาม LP
    """
    match = {}
    if region:
        match["region"] = region
    if tier:
        match["tier"] = tier

    summoners = list(db.summoners.find(match).sort("lp", -1).limit(limit))
    puuids = [s["_id"] for s in summoners]

    stats_by_puuid = {
        s["_id"]: s
        for s in db.participants.aggregate([
            {"$match": {"puuid": {"$in": puuids}}},
            {"$group": {
                "_id":        "$puuid",
                "games":      {"$sum": 1},
                "top4_count": {"$sum": {"$cond": [{"$lte": ["$placement", 4]}, 1, 0]}},
            }},
        ])
    }

    # เอาชื่อล่าสุดที่เคยเจอของแต่ละคน (participant ไม่ได้มีชื่อเก็บไว้ทุกคน แมตช์เก่าก่อนหน้านี้ไม่มี riot_id_name)
    names_by_puuid = {
        n["_id"]: n
        for n in db.participants.aggregate([
            {"$match": {"puuid": {"$in": puuids}, "riot_id_name": {"$ne": None}}},
            {"$sort": {"game_datetime": -1}},
            {"$group": {"_id": "$puuid", "riot_id_name": {"$first": "$riot_id_name"}, "riot_id_tag": {"$first": "$riot_id_tag"}}},
        ])
    }

    data = []
    for i, s in enumerate(summoners):
        puuid = s["_id"]
        stats = stats_by_puuid.get(puuid, {"games": 0, "top4_count": 0})
        name  = names_by_puuid.get(puuid)
        games = stats["games"]
        data.append({
            # ใช้ตำแหน่งจริงในลิสต์ที่ sort แล้ว ไม่ใช้ rank_in_region ตรงๆ เพราะเป็นอันดับแยกตามภูมิภาค
            # พอรวมหลายภูมิภาคเข้าด้วยกัน (ไม่ filter region) เลข rank เดิมจะซ้ำกันได้
            "rank":         i + 1,
            "puuid":        puuid,
            "display_name": f"{name['riot_id_name']}#{name['riot_id_tag']}" if name else None,
            "region":       s.get("region"),
            "tier":         s.get("tier"),
            "lp":           s.get("lp"),
            "games":        games,
            "top4_count":   stats["top4_count"],
            "top4_rate":    round(100.0 * stats["top4_count"] / games, 1) if games else 0.0,
        })

    return {"data": data}


def _unit_summary(u: dict) -> dict:
    return {
        "character_id": u.get("character_id"),
        "star":         u.get("tier"),
        **cdragon.unit_info(u.get("character_id")),
        "items": [
            {"name": it, **cdragon.item_info(it)}
            for it in u.get("items", []) if it
        ],
    }


# ── GET /summoner/{puuid} ────────────────────────────────────────────────────
@app.get("/summoner/{puuid}")
def get_summoner_profile(
    puuid: str,
    limit: int = Query(30, description="จำนวนแมตช์ล่าสุดที่จะโชว์"),
    db: Database = Depends(get_db),
):
    """
    โปรไฟล์ + ประวัติแมตช์ของผู้เล่นคนเดียว (กดจากแถวใน leaderboard เข้ามา)
    """
    history = list(
        db.participants.find({"puuid": puuid})
        .sort("game_datetime", -1)
        .limit(limit)
    )
    if not history:
        raise HTTPException(status_code=404, detail="No matches found for this player")

    latest = history[0]
    placements = [p["placement"] for p in history]

    # หา riot_id_name ล่าสุดที่มีจริง — อาจไม่ใช่แมตช์ล่าสุดสุดถ้าแมตช์นั้นดึงมาก่อนที่จะเริ่มเก็บชื่อ (เหมือนที่ /leaderboard/ranked ทำ)
    named = db.participants.find_one(
        {"puuid": puuid, "riot_id_name": {"$ne": None}},
        sort=[("game_datetime", -1)],
    )

    summoner = db.summoners.find_one({"_id": puuid}, {"lp": 1})

    # game_length เก็บอยู่ที่ matches ไม่ใช่ participants เลยต้อง join เพิ่ม
    match_ids = [p["match_id"] for p in history]
    lengths = {
        m["_id"]: m.get("game_length")
        for m in db.matches.find({"_id": {"$in": match_ids}}, {"game_length": 1})
    }

    # Most Synergies — รวม trait ที่ active ทุกแมตช์ในประวัติที่ดึงมา นับความถี่ + avg placement ต่อ trait
    synergy_stats: dict[str, dict] = {}
    for p in history:
        for t in p.get("traits", []):
            if t.get("style", 0) <= 0:
                continue
            s = synergy_stats.setdefault(t["name"], {"matches": 0, "placement_sum": 0})
            s["matches"] += 1
            s["placement_sum"] += p["placement"]
    top_synergies = sorted(
        [
            {
                "name": name, **cdragon.trait_info(name),
                "matches": s["matches"],
                "avg_placement": round(s["placement_sum"] / s["matches"], 2),
            }
            for name, s in synergy_stats.items()
        ],
        key=lambda s: s["matches"], reverse=True,
    )[:5]

    placement_distribution = {str(i): placements.count(i) for i in range(1, 9)}

    return {
        "puuid":        puuid,
        "display_name": _display_name(named) if named else None,
        "region":       latest.get("region"),
        "tier":         latest.get("tier"),
        "lp":           summoner.get("lp") if summoner else None,
        "stats": {
            "games":                  len(placements),
            "avg_placement":          round(sum(placements) / len(placements), 2),
            "top4_rate":              round(100.0 * sum(1 for x in placements if x <= 4) / len(placements), 1),
            "win_rate":               round(100.0 * sum(1 for x in placements if x == 1) / len(placements), 1),
            "placement_distribution": placement_distribution,
        },
        "top_synergies": top_synergies,
        "matches": [
            {
                "match_id":      p["match_id"],
                "game_datetime": p["game_datetime"].isoformat() if p.get("game_datetime") else None,
                "game_length":   lengths.get(p["match_id"]),
                "last_round":    p.get("last_round"),
                "tft_set":       p.get("tft_set"),
                "placement":     p["placement"],
                "top_traits":    _top_traits(p),
                "units":         [_unit_summary(u) for u in p.get("units", [])],
            }
            for p in history
        ],
    }


# ── Health Check ──────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status":           "ok",
        "predictor_loaded": predictor is not None,
    }


# ── GET /admin/status ────────────────────────────────────────────────────────
_riot_key_check_cache = {"checked_at": 0.0, "valid": None}
RIOT_KEY_CHECK_TTL_SECONDS = 60  # กันไม่ให้ยิงไป Riot ทุกครั้งที่มีคนเปิด Settings รัวๆ

def _check_riot_key_valid() -> Optional[bool]:
    if not RIOT_API_KEY:
        return None
    now = time.time()
    if now - _riot_key_check_cache["checked_at"] < RIOT_KEY_CHECK_TTL_SECONDS:
        return _riot_key_check_cache["valid"]

    try:
        resp = requests.get(
            "https://na1.api.riotgames.com/tft/league/v1/challenger",
            headers={"X-Riot-Token": RIOT_API_KEY},
            timeout=5,
        )
        valid = resp.status_code != 401 and resp.status_code != 403
    except Exception:
        valid = None  # เช็คไม่ได้ (network ล่ม ฯลฯ) ไม่ใช่ว่า key ผิด

    _riot_key_check_cache["checked_at"] = now
    _riot_key_check_cache["valid"] = valid
    return valid


# summoners มี cap จริงจาก ingestion config (TARGET_PLAYERS=200 ต่อ region * 5 regions ใน ingestion/fetch_matches.py)
# ต้องแก้คู่กันถ้าเปลี่ยนค่านั้น — ส่วน matches/participants ไม่มี cap ตายตัว ถูกจำกัดด้วย TTL (DATA_RETENTION_DAYS) แทน
MAX_SUMMONERS = 200 * 5


@app.get("/admin/status")
def get_admin_status(db: Database = Depends(get_db)):
    """
    สถานะระบบเบื้องหลังสำหรับหน้า Settings — Riot API key ยังใช้ได้ไหม + ดึงข้อมูลล่าสุดเมื่อไหร่
    """
    latest_match = db.matches.find_one({}, sort=[("created_at", -1)], projection={"created_at": 1})
    return {
        "riot_api_key_valid": _check_riot_key_valid(),
        "last_ingested_at": latest_match["created_at"].isoformat() if latest_match else None,
        "data_retention_days": int(os.getenv("DATA_RETENTION_DAYS", 14)),
        "counts": {
            # estimated_document_count ใช้ metadata ของ collection ตอบเร็วกว่า count_documents({}) ที่ scan เต็มตาราง
            "matches":      db.matches.estimated_document_count(),
            "participants": db.participants.estimated_document_count(),
            "summoners":    db.summoners.estimated_document_count(),
        },
        "max_summoners": MAX_SUMMONERS,
    }