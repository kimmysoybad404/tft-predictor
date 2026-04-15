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
RIOT_API_KEY  = os.getenv("RIOT_API_KEY")
GLOBAL_REGIONS = [
    {"name": "Korea", "platform": "kr", "routing": "asia"},
    {"name": "North America", "platform": "na1", "routing": "americas"},
    {"name": "Europe West", "platform": "euw1", "routing": "europe"},
    {"name": "Thailand", "platform": "th2", "routing": "sea"},
    {"name": "Brazil", "platform": "br1", "routing": "americas"},
]

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

# ── VIP Watchlist (ดึงข้อมูลคนเหล่านี้เสมอ ไม่ว่าแรงค์จะอยู่ระดับไหน) ──
TRACKED_SUMMONERS = [
    {"riot_id": "CookieMonster274#EUNE", "routing": "europe", "region_name": "EUNE"},
    # {"riot_id": "TFTPro#NA1", "routing": "americas", "region_name": "North America"},
]

# ── DB Setup ─────────────────────────────────────────────────────────────────
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


def get_top_1_tft_summoner_id(platform: str) -> str | None:
    url = f"https://{platform}.api.riotgames.com/tft/league/v1/challenger"
    data = riot_get(url)
    
    if data and "entries" in data:
        sorted_entries = sorted(data["entries"], key=lambda x: x["leaguePoints"], reverse=True)
        if sorted_entries:
            return sorted_entries[0]["summonerId"]
    return None

def get_puuid_by_summoner_id(summoner_id: str, platform: str) -> str | None:
    url = f"https://{platform}.api.riotgames.com/tft/summoner/v1/summoners/{summoner_id}"
    data = riot_get(url)
    return data["puuid"] if data else None

def get_puuid_by_riot_id(game_name: str, tag_line: str, routing: str) -> str | None:
    """แปลง Riot ID (Name#Tag) เป็น PUUID แบบ Global"""
    # ใช้ routing ที่ส่งเข้ามา (เช่น asia, americas, europe) เพื่อค้นหา ID สากล
    url = f"https://{routing}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    data = riot_get(url)
    return data["puuid"] if data else None

def get_match_ids(puuid: str, routing: str, count: int = 20) -> list[str]:
    # สังเกตว่าบรรทัดนี้ใช้ routing (ทวีป) แทน platform (ประเทศ)
    url = f"https://{routing}.api.riotgames.com/tft/match/v1/matches/by-puuid/{puuid}/ids"
    data = riot_get(url, params={"count": count, "queue": 1100})
    return data if data else []

def get_match_detail(match_id: str, routing: str) -> dict | None:
    url = f"https://{routing}.api.riotgames.com/tft/match/v1/matches/{match_id}"
    return riot_get(url)


# ── DB Insert Helpers ─────────────────────────────────────────────────────────
def upsert_summoner(session, puuid: str, region: str):
    session.execute(text("""
        INSERT INTO summoners (puuid, region)
        VALUES (:puuid, :region)
        ON CONFLICT (puuid) DO NOTHING
    """), {"puuid": puuid, "region": region})


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
    session.execute(text("""
        INSERT INTO matches (match_id, game_datetime, game_length, tft_set_number, tft_set_core_name, queue_id)
        VALUES (:match_id, :game_datetime, :game_length, :tft_set_number, :tft_set_core_name, :queue_id)
        ON CONFLICT (match_id) DO NOTHING
    """), {
        "match_id":          match_id,        "game_datetime":     datetime.fromtimestamp(info.get("game_datetime", 0) / 1000),
        "game_length":       info.get("game_length"),
        "tft_set_number":    info.get("tft_set_number"),
        "tft_set_core_name": info.get("tft_set_core_name"),
        "queue_id":          info.get("queue_id"),
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
        "match_id":                  match_id,
        "puuid":                     p["puuid"],
        "placement":                 p["placement"],
        "level":                     p.get("level"),
        "last_round":                p.get("last_round"),
        "time_eliminated":           p.get("time_eliminated"),
        "total_damage_to_players":   p.get("total_damage_to_players"),
        "players_eliminated":        p.get("players_eliminated"),
        "gold_left":                 p.get("gold_left"),
        "augments":                  p.get("augments", []),
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
def process_summoner_by_puuid(puuid: str, routing: str, region_name: str, log_name: str):
    log.info(f"Processing PUUID for: {log_name} ({region_name})")

    match_ids = get_match_ids(puuid, routing, count=20)
    log.info(f"Found {len(match_ids)} recent matches for {log_name}")

    new_count = 0
    with Session() as session:
        # บันทึกด้วยว่าผู้เล่นคนนี้อยู่ Routing ไหน
        upsert_summoner(session, puuid, routing)

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

    log.info(f"Ingested {new_count} new matches for {log_name} ({region_name})")


def run_ingestion():
    log.info("═══ Starting GLOBAL ingestion run ═══")
    
    for region in GLOBAL_REGIONS:
        platform = region["platform"]
        routing = region["routing"]
        r_name = region["name"]
        
        log.info(f"--- Fetching Data for {r_name} ---")
        top_1_id = get_top_1_tft_summoner_id(platform)
        
        if top_1_id:
            top_1_puuid = get_puuid_by_summoner_id(top_1_id, platform)
            if top_1_puuid:
                process_summoner_by_puuid(
                    puuid=top_1_puuid, 
                    routing=routing, 
                    region_name=r_name, 
                    log_name=f"{platform.upper()}_TOP_1"
                )
            else:
                log.error(f"Could not resolve PUUID for Top 1 in {r_name}.")
        else:
            log.error(f"Could not fetch Top 1 from {r_name} Leaderboard.")
            
        time.sleep(2)
        pass

    log.info("--- Fetching Data for VIP Watchlist ---")
    for vip in TRACKED_SUMMONERS:
        try:
            name, tag = vip["riot_id"].rsplit("#", 1)
            routing = vip["routing"]
            r_name = vip["region_name"]
            
            puuid = get_puuid_by_riot_id(name, tag, routing) 
            
            if puuid:
                process_summoner_by_puuid(
                    puuid=puuid, 
                    routing=routing, 
                    region_name=r_name, 
                    log_name=f"VIP_{vip['riot_id']}"
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
    run_ingestion()                        # run immediately on start
    schedule.every(30).minutes.do(run_ingestion)

    while True:
        schedule.run_pending()
        time.sleep(60)