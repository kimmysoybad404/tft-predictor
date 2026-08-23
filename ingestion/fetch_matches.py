"""
TFT Match Ingestion Worker
Fetches match data from Riot API and stores in MongoDB.
Runs on a schedule every 30 minutes.
"""

import os
import time
import logging
import schedule
import requests
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING
from pymongo.errors import DuplicateKeyError, OperationFailure

load_dotenv()

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────
RIOT_API_KEY = os.getenv("RIOT_API_KEY")
GLOBAL_REGIONS = [
    {"name": "Korea",         "platform": "kr",  "routing": "asia"},
    {"name": "North America", "platform": "na1", "routing": "americas"},
    {"name": "Europe West",   "platform": "euw1","routing": "europe"},
    {"name": "Thailand",      "platform": "sg2", "routing": "sea"},
    {"name": "Brazil",        "platform": "br1", "routing": "americas"},
]

# ลำดับความสำคัญของ tier (สูงกว่า = rank สูงกว่า)
TIER_PRIORITY = {
    "challenger":  8,
    "grandmaster": 7,
    "master":      6,
    "diamond":     5,
    "emerald":     4,
    "platinum":    3,
    "gold":        2,
    "silver":      1,
}

# Division priority (I > II > III > IV)
DIVISION_PRIORITY = {"I": 4, "II": 3, "III": 2, "IV": 1}

# Fallback tiers ถ้า Challenger/Grandmaster/Master ยังไม่ครบ TARGET_PLAYERS
# หยุดแค่ Diamond เพื่อรักษาคุณภาพของ "high-ranked meta" ไม่ให้เจือจางลงไปถึง Gold/Silver
FALLBACK_TIERS = [
    ("DIAMOND",  "I"),
    ("DIAMOND",  "II"),
    ("DIAMOND",  "III"),
    ("DIAMOND",  "IV"),
]

TARGET_PLAYERS = 200

# จำนวนวันที่จะเก็บข้อมูลแมตช์ไว้ — เก่ากว่านี้ Mongo จะลบทิ้งอัตโนมัติ (TTL index)
# กันไม่ให้ storage โตไม่หยุดเวลา ingestion ดึงข้อมูลต่อเนื่องตลอด
DATA_RETENTION_DAYS = int(os.getenv("DATA_RETENTION_DAYS", 14))

MONGO_URI = (
    f"mongodb://{os.getenv('MONGO_USER')}:{os.getenv('MONGO_PASSWORD')}"
    f"@{os.getenv('MONGO_HOST')}:{os.getenv('MONGO_PORT')}/?authSource=admin"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Charset": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://developer.riotgames.com",
    "X-Riot-Token": RIOT_API_KEY
}

# ── VIP Watchlist ─────────────────────────────────────────────────────────────
TRACKED_SUMMONERS = [
    {"riot_id": "Bunny#5664", "routing": "SEA", "region_name": "THA"},
    {"riot_id": "Dinozexe#NAJA", "routing": "SEA", "region_name": "THA"},
    # {"riot_id": "TFTPro#NA1", "routing": "americas", "region_name": "North America"},
]

# ── DB Setup ──────────────────────────────────────────────────────────────────
client = MongoClient(MONGO_URI)
db = client[os.getenv("MONGO_DB_NAME", "tft_predictor")]


def ensure_ttl_index(collection, field: str, retention_days: int, index_name: str):
    """
    สร้าง TTL index (idempotent) — ถ้า DATA_RETENTION_DAYS เปลี่ยนไปจากตอน deploy ก่อนหน้า
    ต้อง drop index เดิมก่อนแล้วสร้างใหม่ เพราะ Mongo ไม่ยอมแก้ expireAfterSeconds ผ่าน create_index ตรงๆ
    """
    seconds = retention_days * 24 * 60 * 60
    try:
        collection.create_index(field, name=index_name, expireAfterSeconds=seconds)
    except OperationFailure:
        collection.drop_index(index_name)
        collection.create_index(field, name=index_name, expireAfterSeconds=seconds)


def ensure_indexes():
    """สร้าง index ที่จำเป็น (idempotent — เรียกซ้ำได้ทุกครั้งที่ worker start)"""
    db.participants.create_index(
        [("match_id", ASCENDING), ("puuid", ASCENDING)], unique=True
    )
    db.participants.create_index("puuid")
    db.participants.create_index("match_id")
    db.participants.create_index("placement")
    db.participants.create_index([("region", ASCENDING), ("tier", ASCENDING)])
    db.participants.create_index("traits.name")
    db.participants.create_index("units.character_id")
    db.summoners.create_index([("region", ASCENDING), ("rank_in_region", ASCENDING)])
    db.summoners.create_index("tier")

    # TTL — ลบข้อมูลเก่าเกิน DATA_RETENTION_DAYS ทิ้งอัตโนมัติ กัน storage โตไม่หยุด
    # เพราะ ingestion ดึงข้อมูลต่อเนื่องทุก 30 นาทีตลอดเวลา
    ensure_ttl_index(db.participants, "game_datetime", DATA_RETENTION_DAYS, "ttl_game_datetime")
    ensure_ttl_index(db.matches, "game_datetime", DATA_RETENTION_DAYS, "ttl_game_datetime")
    # summoner ที่หลุด top1000 ไปนานแล้ว (ไม่ถูก upsert ต่อ) จะถูกลบทิ้งไปด้วยตามอายุของ fetched_at ล่าสุด
    ensure_ttl_index(db.summoners, "fetched_at", DATA_RETENTION_DAYS, "ttl_fetched_at")


# ── Riot API Helpers ──────────────────────────────────────────────────────────
def riot_get(url: str, params: dict = None) -> dict | None:
    """GET request with basic rate-limit handling."""
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 5))
            log.warning(f"Rate limited. Sleeping {retry_after}s…")
            time.sleep(retry_after)
            return riot_get(url, params)
        elif resp.status_code == 404:
            log.warning(f"404 Not Found: {url}")
            return None
        else:
            log.error(f"API error {resp.status_code}: {url}")
            return None
    except requests.RequestException as e:
        log.error(f"Request failed: {e}")
        return None


def get_apex_leaderboard(platform: str, tier: str) -> list[dict]:
    """
    ดึง Challenger / Grandmaster / Master (ใช้ endpoint /v1/{tier})
    inject field 'tier' และ 'division' เข้าไปทุก entry
    """
    url  = f"https://{platform}.api.riotgames.com/tft/league/v1/{tier}"
    data = riot_get(url)

    if not data or "entries" not in data:
        log.warning(f"  No data for {tier} on {platform}")
        return []

    entries = data["entries"]
    for entry in entries:
        entry["tier"]     = tier.lower()
        entry["division"] = "I"   # apex tier ไม่มี division จริงๆ ใส่ I ไว้เพื่อ sort

    log.info(f"  {tier.capitalize():>12} (apex)  : {len(entries):>4} players")
    return entries


def get_division_leaderboard(platform: str, tier: str, division: str) -> list[dict]:
    """
    ดึง Diamond / Emerald / Platinum / Gold / Silver แบบ pagination
    (/v1/entries/{tier}/{division}?page=N)
    คืน entries ทั้งหมดของ tier+division นั้น
    """
    all_entries = []
    page = 1

    while True:
        url  = f"https://{platform}.api.riotgames.com/tft/league/v1/entries/{tier}/{division}"
        data = riot_get(url, params={"page": page})

        if not data or not isinstance(data, list) or len(data) == 0:
            break

        for entry in data:
            entry["tier"]     = tier.lower()
            entry["division"] = division

        all_entries.extend(data)

        # Riot คืนหน้าละ 205 entries ถ้าน้อยกว่านั้นคือหน้าสุดท้าย
        if len(data) < 205:
            break

        page += 1
        time.sleep(0.3)

    log.info(f"  {tier.capitalize():>12} {division:<3}      : {len(all_entries):>4} players")
    return all_entries


def get_top1000_ranked(platform: str) -> list[dict]:
    """
    ดึง Challenger + Grandmaster + Master ก่อน
    ถ้ายังไม่ครบ 1000 → fallback ดึง Diamond I, II, ... ลงมาเรื่อยๆ
    sort by tier priority → division priority → LP
    คืน top 1000 พร้อม rank_in_region (1-based)
    """
    log.info(f"Fetching leaderboard for {platform}...")

    all_players = []

    # ── ดึง Apex tiers ก่อน ───────────────────────────────────────────────────
    for apex in ["challenger", "grandmaster", "master"]:
        entries = get_apex_leaderboard(platform, apex)
        all_players.extend(entries)
        time.sleep(0.5)

    log.info(f"  Apex total: {len(all_players)} players")

    # ── Fallback ดึง tier ล่างถ้ายังไม่ครบ ────────────────────────────────────
    if len(all_players) < TARGET_PLAYERS:
        log.info(f"  Not enough players ({len(all_players)}/{TARGET_PLAYERS}), fetching lower tiers...")

        for tier, division in FALLBACK_TIERS:
            if len(all_players) >= TARGET_PLAYERS:
                break

            entries = get_division_leaderboard(platform, tier, division)
            all_players.extend(entries)
            time.sleep(0.5)

            log.info(f"  Running total: {len(all_players)} players")

    log.info(f"  Total combined: {len(all_players)} players")

    # ── Sort: tier priority → division priority → LP (ทั้งหมด descending) ─────
    all_players.sort(
        key=lambda x: (
            TIER_PRIORITY.get(x.get("tier", "silver"), 0),
            DIVISION_PRIORITY.get(x.get("division", "IV"), 0),
            x.get("leaguePoints", 0),
        ),
        reverse=True,
    )

    # ── Slice top 1000 และ assign rank ────────────────────────────────────────
    top1000 = all_players[:TARGET_PLAYERS]
    for i, player in enumerate(top1000):
        player["rank_in_region"] = i + 1

    log.info(f"  → Selected top {len(top1000)} players")
    return top1000


def get_puuid_by_summoner_id(summoner_id: str, platform: str) -> str | None:
    url = f"https://{platform}.api.riotgames.com/tft/summoner/v1/summoners/{summoner_id}"
    data = riot_get(url)
    return data["puuid"] if data else None


def get_puuid_by_riot_id(game_name: str, tag_line: str, routing: str) -> str | None:
    url = f"https://{routing}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    data = riot_get(url)
    return data["puuid"] if data else None


def get_match_ids(puuid: str, routing: str, count: int = 20) -> list[str]:
    url = f"https://{routing}.api.riotgames.com/tft/match/v1/matches/by-puuid/{puuid}/ids"
    data = riot_get(url, params={"count": count, "queue": 1100})
    return data if data else []


def get_match_detail(match_id: str, routing: str) -> dict | None:
    url = f"https://{routing}.api.riotgames.com/tft/match/v1/matches/{match_id}"
    return riot_get(url)


# ── DB Insert Helpers ─────────────────────────────────────────────────────────
def upsert_summoner(puuid: str, region: str, tier: str, lp: int, rank_in_region: int):
    """
    บันทึกหรืออัปเดต summoner พร้อม tier, lp และ rank snapshot ล่าสุด
    """
    db.summoners.update_one(
        {"_id": puuid},
        {"$set": {
            "region":         region,
            "tier":           tier,
            "lp":             lp,
            "rank_in_region": rank_in_region,
            "fetched_at":     datetime.utcnow(),
        }},
        upsert=True,
    )


def is_already_fetched(puuid: str, match_id: str) -> bool:
    """
    เช็คว่าเคยดึงแมตช์นี้ของ summoner คนนี้ไปแล้วหรือยัง
    (ใช้ participants เป็น source of truth แทน fetch_log เดิม เพราะ unique index (match_id, puuid) รับประกันไม่ซ้ำอยู่แล้ว)
    """
    return db.participants.find_one(
        {"match_id": match_id, "puuid": puuid}, {"_id": 1}
    ) is not None


def insert_match(match_id: str, info: dict) -> datetime:
    raw_time = info.get("game_datetime") or info.get("gameCreation") or 0
    game_datetime = datetime.fromtimestamp(raw_time / 1000)

    db.matches.update_one(
        {"_id": match_id},
        {"$setOnInsert": {
            "game_datetime":     game_datetime,
            "game_length":       info.get("game_length") or info.get("gameDuration"),
            "tft_set_number":    info.get("tft_set_number", 16),
            "tft_set_core_name": info.get("tft_set_core_name", "TFTSet16"),
            "queue_id":          info.get("queue_id") or info.get("queueId"),
            "created_at":        datetime.utcnow(),
        }},
        upsert=True,
    )
    return game_datetime


def insert_participant(match_id: str, region: str, tier: str, game_datetime: datetime, p: dict):
    """
    สร้าง participant document เดียวที่ embed ทั้ง units และ traits ไว้ในตัว
    (แทนการ insert แยก 3 ตารางแบบ Postgres เดิม)
    """
    units = [
        {
            "character_id": u.get("character_id"),
            "rarity":       u.get("rarity"),
            "tier":         u.get("tier"),
            "items":        u.get("itemNames", []),
        }
        for u in p.get("units", [])
    ]
    traits = [
        {
            "name":         t.get("name"),
            "num_units":    t.get("num_units"),
            "style":        t.get("style"),
            "tier_current": t.get("tier_current"),
            "tier_total":   t.get("tier_total"),
        }
        for t in p.get("traits", [])
    ]

    db.participants.insert_one({
        "match_id":                match_id,
        "puuid":                   p["puuid"],
        "region":                  region,
        "tier":                    tier,
        "game_datetime":           game_datetime,
        "placement":               p["placement"],
        "level":                   p.get("level"),
        "last_round":              p.get("last_round"),
        "time_eliminated":         p.get("time_eliminated"),
        "total_damage_to_players": p.get("total_damage_to_players"),
        "players_eliminated":      p.get("players_eliminated"),
        "gold_left":               p.get("gold_left"),
        "augments":                p.get("augments", []),
        "units":                   units,
        "traits":                  traits,
    })


# ── Main Ingestion Logic ──────────────────────────────────────────────────────
def process_summoner(puuid: str, routing: str, region: str, tier: str, lp: int, rank: int, log_name: str):
    """
    ดึงแมตช์ของ summoner คนนึง แล้ว insert ลง DB
    พร้อมบันทึก tier, lp, rank snapshot ล่าสุด
    """
    match_ids = get_match_ids(puuid, routing, count=20)

    if not match_ids:
        log.info(f"  No matches found for {log_name}")
        return

    new_count = 0

    # อัปเดต summoner พร้อม rank snapshot
    upsert_summoner(puuid, region, tier, lp, rank)

    for match_id in match_ids:
        if is_already_fetched(puuid, match_id):
            continue

        detail = get_match_detail(match_id, routing)
        if not detail:
            continue

        info = detail["info"]
        match_id_str = detail["metadata"]["match_id"]

        game_datetime = insert_match(match_id_str, info)

        for participant in info["participants"]:
            try:
                insert_participant(match_id_str, region, tier, game_datetime, participant)
            except DuplicateKeyError:
                pass  # อีก 7 คนในแมตช์นี้อาจถูก insert ไปแล้วตอนประมวลผล summoner คนอื่น

        new_count += 1
        time.sleep(0.5)

    log.info(f"  [{log_name}] Rank #{rank} | {tier.upper()} {lp} LP → {new_count} new matches")


def run_ingestion():
    log.info("═══ Starting GLOBAL ingestion run ═══")

    for region in GLOBAL_REGIONS:
        platform = region["platform"]
        routing  = region["routing"]

        log.info(f"🚀 [{region['name']}] Building top {TARGET_PLAYERS} leaderboard...")

        # ── ดึง top 1000 เรียงตาม tier → LP ──────────────────────────────────
        top1000 = get_top1000_ranked(platform)

        if not top1000:
            log.warning(f"  No players found for {region['name']}, skipping.")
            continue

        # ── วน loop ตาม rank (1 → 1000) ──────────────────────────────────────
        for player in top1000:
            puuid = player.get("puuid")

            # บาง region API ไม่คืน puuid ตรงๆ ต้องดึงเพิ่ม
            if not puuid:
                summoner_id = player.get("summonerId")
                if not summoner_id:
                    continue
                puuid = get_puuid_by_summoner_id(summoner_id, platform)
                if not puuid:
                    continue
                time.sleep(0.5)

            rank      = player["rank_in_region"]
            tier      = player["tier"]
            lp        = player.get("leaguePoints", 0)
            log_name  = f"{platform.upper()}_RANK_{rank}"

            process_summoner(
                puuid   = puuid,
                routing = routing,
                region  = platform,
                tier    = tier,
                lp      = lp,
                rank    = rank,
                log_name= log_name,
            )

            time.sleep(1.2)

            if rank % 10 == 0:
                log.info(f"  ✅ Progress: {rank}/1000 [{region['name']}]")

        log.info(f"  ✅ Done [{region['name']}]")
        time.sleep(2)

    # ── VIP Watchlist ─────────────────────────────────────────────────────────
    log.info("--- Fetching VIP Watchlist ---")
    for vip in TRACKED_SUMMONERS:
        try:
            name, tag  = vip["riot_id"].rsplit("#", 1)
            routing    = vip["routing"]
            region_name= vip["region_name"]

            puuid = get_puuid_by_riot_id(name, tag, routing)
            if puuid:
                # VIP ไม่มี rank ใน leaderboard → ใส่ค่า default
                process_summoner(
                    puuid   = puuid,
                    routing = routing,
                    region  = region_name,
                    tier    = "vip",
                    lp      = 0,
                    rank    = 0,
                    log_name= f"VIP_{vip['riot_id']}",
                )
            else:
                log.error(f"Could not find PUUID for VIP {vip['riot_id']}")

            time.sleep(1)

        except Exception as e:
            log.error(f"Failed processing VIP {vip['riot_id']}: {e}")

    log.info("═══ GLOBAL ingestion run complete ═══")


# ── Scheduler ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("TFT Ingestion Worker started")
    ensure_indexes()
    run_ingestion()
    schedule.every(30).minutes.do(run_ingestion)

    while True:
        schedule.run_pending()
        time.sleep(60)