"""
TFT Meta Analyzer API
Endpoints for analyzing traits, augments, units, and items
from high-ranked TFT players across regions.
"""

import sys
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo.database import Database
from typing import Optional
from database import get_db

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_predictor()
    yield

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
def build_summoner_filter(region: Optional[str], tier: Optional[str]) -> dict:
    """
    สร้าง $match stage สำหรับ filter participants ตาม region และ tier
    (region/tier ถูก denormalize ไว้บน participant document ตอน ingest แล้ว)
    """
    match = {}
    if region:
        match["region"] = region
    if tier:
        match["tier"] = tier
    return match


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


# ── GET /meta/traits ──────────────────────────────────────────────────────────
@app.get("/meta/traits")
def get_meta_traits(
    region: Optional[str] = Query(None, description="kr, na1, euw1, sg2, br1"),
    tier:   Optional[str] = Query(None, description="challenger, grandmaster, master"),
    top_n:  int           = Query(20,   description="จำนวนผลลัพธ์"),
    db:     Database      = Depends(get_db)
):
    """
    Top traits เรียงตาม avg_placement (ต่ำ = ดี)
    แสดง avg_placement, top4_rate, play_rate แยกตาม style
    """
    match = build_summoner_filter(region, tier)

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
        "filter": {"region": region, "tier": tier},
        "count": len(rows),
        "data": [
            {
                "name":  r["_id"]["name"],
                "style": r["_id"]["style"],  # 1=bronze, 2=silver, 3=gold, 4=prismatic
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
    top_n:  int           = Query(20,   description="จำนวนผลลัพธ์"),
    db:     Database      = Depends(get_db)
):
    """
    Top augments เรียงตาม avg_placement (ต่ำ = ดี)
    augments เป็น array ใน participant document จึงต้อง $unwind ก่อน
    """
    match = build_summoner_filter(region, tier)

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
        "filter": {"region": region, "tier": tier},
        "count": len(rows),
        "data": [
            {"augment": r["_id"], **with_rates(r)}
            for r in rows
        ]
    }


# ── GET /meta/units ───────────────────────────────────────────────────────────
@app.get("/meta/units")
def get_meta_units(
    region: Optional[str] = Query(None, description="kr, na1, euw1, sg2, br1"),
    tier:   Optional[str] = Query(None, description="challenger, grandmaster, master"),
    top_n:  int           = Query(20,   description="จำนวนผลลัพธ์"),
    db:     Database      = Depends(get_db)
):
    """
    Top units เรียงตาม avg_placement ของแมตช์ที่มี unit นั้นในบอร์ด
    แสดง avg_tier (star level) และ play_count ด้วย
    """
    match = build_summoner_filter(region, tier)

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
        "filter": {"region": region, "tier": tier},
        "count": len(rows),
        "data": [
            {"character_id": r["_id"], **with_rates(r)}
            for r in rows
        ]
    }


# ── GET /meta/items ───────────────────────────────────────────────────────────
@app.get("/meta/items")
def get_meta_items(
    region: Optional[str] = Query(None, description="kr, na1, euw1, sg2, br1"),
    tier:   Optional[str] = Query(None, description="challenger, grandmaster, master"),
    top_n:  int           = Query(20,   description="จำนวนผลลัพธ์"),
    db:     Database      = Depends(get_db)
):
    """
    Top items เรียงตาม avg_placement ของแมตช์ที่มี item นั้น
    items เป็น array ซ้อนอยู่ใน units จึงต้อง $unwind สองชั้น
    """
    match = build_summoner_filter(region, tier)

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
        "filter": {"region": region, "tier": tier},
        "count": len(rows),
        "data": [
            {"item": r["_id"], **with_rates(r)}
            for r in rows
        ]
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

    data = predictor.get_trait_tier_list(tier_filter=tier)
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

    data = predictor.get_comp_tier_list(tier_filter=tier)
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
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Prediction failed: {str(e)}")


# ── Health Check ──────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status":           "ok",
        "predictor_loaded": predictor is not None,
    }