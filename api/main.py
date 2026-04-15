"""
TFT Meta Analyzer API
Endpoints for analyzing traits, augments, units, and items
from high-ranked TFT players across regions.
"""

from fastapi import FastAPI, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from database import get_db

app = FastAPI(
    title="TFT Meta Analyzer",
    description="Analyze TFT meta from top-ranked players across regions",
    version="1.0.0"
)


# ── Filter Helper ─────────────────────────────────────────────────────────────
def build_summoner_filter(region: Optional[str], tier: Optional[str]) -> tuple[str, dict]:
    """
    สร้าง SQL snippet สำหรับ filter summoner ตาม region และ tier
    คืน (where_clause, params)
    """
    conditions = []
    params = {}

    if region:
        conditions.append("s.region = :region")
        params["region"] = region

    if tier:
        conditions.append("s.tier = :tier")
        params["tier"] = tier

    where = ("AND " + " AND ".join(conditions)) if conditions else ""
    return where, params


# ── GET /meta/traits ──────────────────────────────────────────────────────────
@app.get("/meta/traits")
def get_meta_traits(
    region: Optional[str] = Query(None, description="kr, na1, euw1, sg2, br1"),
    tier:   Optional[str] = Query(None, description="challenger, grandmaster, master"),
    top_n:  int           = Query(20,   description="จำนวนผลลัพธ์"),
    db:     Session       = Depends(get_db)
):
    """
    Top traits เรียงตาม avg_placement (ต่ำ = ดี)
    แสดง avg_placement, top4_rate, play_rate แยกตาม style
    """
    where, params = build_summoner_filter(region, tier)
    params["top_n"] = top_n

    rows = db.execute(text(f"""
        SELECT
            t.name,
            t.style,
            COUNT(*)                                        AS play_count,
            ROUND(AVG(p.placement)::numeric, 2)            AS avg_placement,
            ROUND(
                100.0 * SUM(CASE WHEN p.placement <= 4 THEN 1 ELSE 0 END)
                / COUNT(*), 1
            )                                               AS top4_rate,
            ROUND(
                100.0 * SUM(CASE WHEN p.placement = 1 THEN 1 ELSE 0 END)
                / COUNT(*), 1
            )                                               AS win_rate
        FROM traits t
        JOIN participants p ON t.participant_id = p.id
        JOIN summoners s    ON p.puuid = s.puuid
        WHERE t.style > 0   -- เฉพาะ trait ที่ active (ไม่เอา style=0)
        {where}
        GROUP BY t.name, t.style
        HAVING COUNT(*) >= 50   -- กรอง noise จาก trait ที่มีข้อมูลน้อยเกินไป
        ORDER BY avg_placement ASC
        LIMIT :top_n
    """), params).fetchall()

    return {
        "filter": {"region": region, "tier": tier},
        "count": len(rows),
        "data": [
            {
                "name":          r.name,
                "style":         r.style,  # 1=bronze, 2=silver, 3=gold, 4=prismatic
                "play_count":    r.play_count,
                "avg_placement": float(r.avg_placement),
                "top4_rate":     float(r.top4_rate),
                "win_rate":      float(r.win_rate),
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
    db:     Session       = Depends(get_db)
):
    """
    Top augments เรียงตาม avg_placement (ต่ำ = ดี)
    augments เป็น TEXT[] ใน participants จึงต้อง unnest ก่อน
    """
    where, params = build_summoner_filter(region, tier)
    params["top_n"] = top_n

    rows = db.execute(text(f"""
        SELECT
            augment,
            COUNT(*)                                        AS play_count,
            ROUND(AVG(p.placement)::numeric, 2)            AS avg_placement,
            ROUND(
                100.0 * SUM(CASE WHEN p.placement <= 4 THEN 1 ELSE 0 END)
                / COUNT(*), 1
            )                                               AS top4_rate,
            ROUND(
                100.0 * SUM(CASE WHEN p.placement = 1 THEN 1 ELSE 0 END)
                / COUNT(*), 1
            )                                               AS win_rate
        FROM participants p
        JOIN summoners s ON p.puuid = s.puuid
        CROSS JOIN UNNEST(p.augments) AS augment
        WHERE TRUE {where}
        GROUP BY augment
        HAVING COUNT(*) >= 50
        ORDER BY avg_placement ASC
        LIMIT :top_n
    """), params).fetchall()

    return {
        "filter": {"region": region, "tier": tier},
        "count": len(rows),
        "data": [
            {
                "augment":       r.augment,
                "play_count":    r.play_count,
                "avg_placement": float(r.avg_placement),
                "top4_rate":     float(r.top4_rate),
                "win_rate":      float(r.win_rate),
            }
            for r in rows
        ]
    }


# ── GET /meta/units ───────────────────────────────────────────────────────────
@app.get("/meta/units")
def get_meta_units(
    region: Optional[str] = Query(None, description="kr, na1, euw1, sg2, br1"),
    tier:   Optional[str] = Query(None, description="challenger, grandmaster, master"),
    top_n:  int           = Query(20,   description="จำนวนผลลัพธ์"),
    db:     Session       = Depends(get_db)
):
    """
    Top units เรียงตาม avg_placement ของแมตช์ที่มี unit นั้นในบอร์ด
    แสดง avg_tier (star level) และ play_count ด้วย
    """
    where, params = build_summoner_filter(region, tier)
    params["top_n"] = top_n

    rows = db.execute(text(f"""
        SELECT
            u.character_id,
            COUNT(DISTINCT p.id)                            AS play_count,
            ROUND(AVG(p.placement)::numeric, 2)            AS avg_placement,
            ROUND(AVG(u.tier)::numeric, 2)                 AS avg_star,
            ROUND(
                100.0 * SUM(CASE WHEN p.placement <= 4 THEN 1 ELSE 0 END)
                / COUNT(DISTINCT p.id), 1
            )                                               AS top4_rate,
            ROUND(
                100.0 * SUM(CASE WHEN p.placement = 1 THEN 1 ELSE 0 END)
                / COUNT(DISTINCT p.id), 1
            )                                               AS win_rate
        FROM units u
        JOIN participants p ON u.participant_id = p.id
        JOIN summoners s    ON p.puuid = s.puuid
        WHERE TRUE {where}
        GROUP BY u.character_id
        HAVING COUNT(DISTINCT p.id) >= 50
        ORDER BY avg_placement ASC
        LIMIT :top_n
    """), params).fetchall()

    return {
        "filter": {"region": region, "tier": tier},
        "count": len(rows),
        "data": [
            {
                "character_id":  r.character_id,
                "play_count":    r.play_count,
                "avg_placement": float(r.avg_placement),
                "avg_star":      float(r.avg_star),
                "top4_rate":     float(r.top4_rate),
                "win_rate":      float(r.win_rate),
            }
            for r in rows
        ]
    }


# ── GET /meta/items ───────────────────────────────────────────────────────────
@app.get("/meta/items")
def get_meta_items(
    region: Optional[str] = Query(None, description="kr, na1, euw1, sg2, br1"),
    tier:   Optional[str] = Query(None, description="challenger, grandmaster, master"),
    top_n:  int           = Query(20,   description="จำนวนผลลัพธ์"),
    db:     Session       = Depends(get_db)
):
    """
    Top items เรียงตาม avg_placement ของแมตช์ที่มี item นั้น
    items เป็น TEXT[] ใน units จึงต้อง unnest ก่อน
    """
    where, params = build_summoner_filter(region, tier)
    params["top_n"] = top_n

    rows = db.execute(text(f"""
        SELECT
            item,
            COUNT(*)                                        AS play_count,
            ROUND(AVG(p.placement)::numeric, 2)            AS avg_placement,
            ROUND(
                100.0 * SUM(CASE WHEN p.placement <= 4 THEN 1 ELSE 0 END)
                / COUNT(*), 1
            )                                               AS top4_rate,
            ROUND(
                100.0 * SUM(CASE WHEN p.placement = 1 THEN 1 ELSE 0 END)
                / COUNT(*), 1
            )                                               AS win_rate
        FROM units u
        JOIN participants p ON u.participant_id = p.id
        JOIN summoners s    ON p.puuid = s.puuid
        CROSS JOIN UNNEST(u.items) AS item
        WHERE item != ''    -- กรอง empty string
        {where}
        GROUP BY item
        HAVING COUNT(*) >= 50
        ORDER BY avg_placement ASC
        LIMIT :top_n
    """), params).fetchall()

    return {
        "filter": {"region": region, "tier": tier},
        "count": len(rows),
        "data": [
            {
                "item":          r.item,
                "play_count":    r.play_count,
                "avg_placement": float(r.avg_placement),
                "top4_rate":     float(r.top4_rate),
                "win_rate":      float(r.win_rate),
            }
            for r in rows
        ]
    }


# ── Health Check ──────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}