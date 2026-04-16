"""
TFT Match Ingestion Worker
Fetches match data from Riot API and stores in PostgreSQL.
Runs on a schedule every 30 minutes.
"""

import os
import time
import logging
import schedule
import requests
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

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

# Fallback tiers ถ้า Challenger/Grandmaster/Master ยังไม่ครบ 1000
FALLBACK_TIERS = [
    ("DIAMOND",  "I"),
    ("DIAMOND",  "II"),
    ("DIAMOND",  "III"),
    ("DIAMOND",  "IV"),
    ("EMERALD",  "I"),
    ("EMERALD",  "II"),
    ("EMERALD",  "III"),
    ("EMERALD",  "IV"),
    ("PLATINUM", "I"),
    ("PLATINUM", "II"),
    ("PLATINUM", "III"),
    ("PLATINUM", "IV"),
    ("GOLD",     "I"),
    ("GOLD",     "II"),
    ("GOLD",     "III"),
    ("GOLD",     "IV"),
    ("SILVER",   "I"),
]

TARGET_PLAYERS = 1000

DB_URL = (
    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
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
    # {"riot_id": "TFTPro#NA1", "routing": "americas", "region_name": "North America"},
]

# ── DB Setup ──────────────────────────────────────────────────────────────────
engine = create_engine(DB_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine)


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
def upsert_summoner(session, puuid: str, region: str, tier: str, lp: int, rank_in_region: int):
    """
    บันทึกหรืออัปเดต summoner พร้อม tier, lp และ rank snapshot ล่าสุด
    """
    session.execute(text("""
        INSERT INTO summoners (puuid, region, tier, lp, rank_in_region, fetched_at)
        VALUES (:puuid, :region, :tier, :lp, :rank_in_region, NOW())
        ON CONFLICT (puuid) DO UPDATE SET
            region          = EXCLUDED.region,
            tier            = EXCLUDED.tier,
            lp              = EXCLUDED.lp,
            rank_in_region  = EXCLUDED.rank_in_region,
            fetched_at      = EXCLUDED.fetched_at
    """), {
        "puuid":           puuid,
        "region":          region,
        "tier":            tier,
        "lp":              lp,
        "rank_in_region":  rank_in_region,
    })


def match_exists(session, match_id: str) -> bool:
    result = session.execute(
        text("SELECT 1 FROM matches WHERE match_id = :mid"),
        {"mid": match_id}
    ).fetchone()
    return result is not None


def is_already_fetched(session, puuid: str, match_id: str) -> bool:
    result = session.execute(
        text("SELECT 1 FROM fetch_log WHERE puuid = :puuid AND match_id = :mid"),
        {"puuid": puuid, "mid": match_id}
    ).fetchone()
    return result is not None


def insert_match(session, match_id, info: dict):
    raw_time = info.get("game_datetime") or info.get("gameCreation") or 0

    session.execute(text("""
        INSERT INTO matches (match_id, game_datetime, game_length, tft_set_number, tft_set_core_name, queue_id)
        VALUES (:match_id, :game_datetime, :game_length, :tft_set_number, :tft_set_core_name, :queue_id)
        ON CONFLICT (match_id) DO NOTHING
    """), {
        "match_id":          match_id,
        "game_datetime":     datetime.fromtimestamp(raw_time / 1000),
        "game_length":       info.get("game_length") or info.get("gameDuration"),
        "tft_set_number":    info.get("tft_set_number", 16),
        "tft_set_core_name": info.get("tft_set_core_name", "TFTSet16"),
        "queue_id":          info.get("queue_id") or info.get("queueId"),
    })


def insert_participant(session, match_id: str, p: dict) -> int:
    result = session.execute(text("""
        INSERT INTO participants
            (match_id, puuid, placement, level, last_round, time_eliminated,
             total_damage_to_players, players_eliminated, gold_left, augments)
        VALUES
            (:match_id, :puuid, :placement, :level, :last_round, :time_eliminated,
             :total_damage_to_players, :players_eliminated, :gold_left, :augments)
        ON CONFLICT (match_id, puuid) DO NOTHING
        RETURNING id
    """), {
        "match_id":                match_id,
        "puuid":                   p["puuid"],
        "placement":               p["placement"],
        "level":                   p.get("level"),
        "last_round":              p.get("last_round"),
        "time_eliminated":         p.get("time_eliminated"),
        "total_damage_to_players": p.get("total_damage_to_players"),
        "players_eliminated":      p.get("players_eliminated"),
        "gold_left":               p.get("gold_left"),
        "augments":                p.get("augments", []),
    })
    row = result.fetchone()
    return row[0] if row else None


def insert_units(session, participant_id: int, units: list):
    for u in units:
        session.execute(text("""
            INSERT INTO units (participant_id, character_id, rarity, tier, items)
            VALUES (:pid, :character_id, :rarity, :tier, :items)
        """), {
            "pid":          participant_id,
            "character_id": u.get("character_id"),
            "rarity":       u.get("rarity"),
            "tier":         u.get("tier"),
            "items":        u.get("itemNames", []),
        })


def insert_traits(session, participant_id: int, traits: list):
    for t in traits:
        session.execute(text("""
            INSERT INTO traits (participant_id, name, num_units, style, tier_current, tier_total)
            VALUES (:pid, :name, :num_units, :style, :tier_current, :tier_total)
        """), {
            "pid":          participant_id,
            "name":         t.get("name"),
            "num_units":    t.get("num_units"),
            "style":        t.get("style"),
            "tier_current": t.get("tier_current"),
            "tier_total":   t.get("tier_total"),
        })


def log_fetch(session, puuid: str, match_id: str):
    session.execute(text("""
        INSERT INTO fetch_log (puuid, match_id)
        VALUES (:puuid, :mid)
        ON CONFLICT DO NOTHING
    """), {"puuid": puuid, "mid": match_id})


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
    with Session() as session:
        # อัปเดต summoner พร้อม rank snapshot
        upsert_summoner(session, puuid, region, tier, lp, rank)

        for match_id in match_ids:
            if is_already_fetched(session, puuid, match_id):
                continue

            detail = get_match_detail(match_id, routing)
            if not detail:
                continue

            info = detail["info"]
            match_id_str = detail["metadata"]["match_id"]

            if not match_exists(session, match_id_str):
                insert_match(session, match_id_str, info)

            for participant in info["participants"]:
                pid = insert_participant(session, match_id_str, participant)
                if pid:
                    insert_units(session, pid, participant.get("units", []))
                    insert_traits(session, pid, participant.get("traits", []))

            log_fetch(session, puuid, match_id_str)
            new_count += 1
            time.sleep(0.5)

        session.commit()

    log.info(f"  [{log_name}] Rank #{rank} | {tier.upper()} {lp} LP → {new_count} new matches")


def run_ingestion():
    log.info("═══ Starting GLOBAL ingestion run ═══")

    for region in GLOBAL_REGIONS:
        platform = region["platform"]
        routing  = region["routing"]

        log.info(f"🚀 [{region['name']}] Building top 1000 leaderboard...")

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
    run_ingestion()
    schedule.every(30).minutes.do(run_ingestion)

    while True:
        schedule.run_pending()
        time.sleep(60)