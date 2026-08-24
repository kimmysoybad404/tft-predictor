"""
Community Dragon mapping — แปลง Riot internal apiName (เช่น TFT17_Doomer, TFT_Item_Deathblade)
ให้เป็นชื่อที่โชว์ในเกมจริง + icon URL สำหรับ trait / unit / item (item ครอบคลุม augment ด้วย)

โหลดครั้งแรกตอน API startup แล้ว refresh เป็นระยะผ่าน periodic_refresh() เพื่อให้ตามทัน
เวลามี TFT set ใหม่ ไม่ต้อง restart service เอง
"""

import re
import logging
import requests
from database import db

log = logging.getLogger(__name__)

CDRAGON_URL = "https://raw.communitydragon.org/latest/cdragon/tft/en_us.json"
ASSET_BASE  = "https://raw.communitydragon.org/latest/game/"

# apiName -> {"display_name": str, "icon_url": str | None}
TRAIT_MAP: dict[str, dict] = {}
UNIT_MAP:  dict[str, dict] = {}
ITEM_MAP:  dict[str, dict] = {}  # ครอบคลุม item และ augment (มาจาก data["items"] เดียวกัน)

# preview ของ set ถัดไปที่ยังไม่มีสถิติจริง (ยังไม่มีคนเล่น) — {"set": "TFTSet18", "traits": [...]} หรือ None
UPCOMING_SET: dict | None = None

# roster เต็มของทุก set ที่ cdragon มีข้อมูล (สำหรับ Comp Builder) — mutator -> {"set", "number", "traits", "champions"}
SET_ROSTERS: dict[str, dict] = {}


def _icon_url(icon_path: str | None) -> str | None:
    if not icon_path:
        return None
    return ASSET_BASE + icon_path.lower().replace(".tex", ".png")


def _clean_description(desc: str, max_len: int = 200) -> str:
    """ตัด HTML tag, icon placeholder (%i:xxx%) และ template variable (@Var@) ออกจาก raw desc ของ cdragon แล้วตัดให้สั้นลง"""
    text = re.sub(r"<[^>]+>", " ", desc or "")
    text = re.sub(r"%i:\w+%", "", text)
    text = re.sub(r"@[\w*.]+@", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0] + "…"
    return text


def _build_roster(s: dict) -> dict:
    """
    แปลง setData entry เดียวให้เป็น roster เต็ม (trait พร้อม tier breakpoints + champion พร้อม cost/trait ที่ติดตัว)
    สำหรับใช้ใน Comp Builder — ไม่ผูกกับ set ปัจจุบันเหมือน TRAIT_MAP/UNIT_MAP ด้านบนซึ่งมีแค่ display_name/icon_url เฉยๆ
    """
    trait_name_to_api = {t["name"]: t["apiName"] for t in s.get("traits", []) if t.get("apiName") and t.get("name")}

    traits = [
        {
            "api_name":     t["apiName"],
            "display_name": t.get("name", t["apiName"]),
            "icon_url":     _icon_url(t.get("icon")),
            "description":  _clean_description(t.get("desc", "")),
            "tiers": [
                {"min_units": e.get("minUnits"), "max_units": e.get("maxUnits"), "style": e.get("style")}
                for e in t.get("effects", [])
            ],
        }
        for t in s.get("traits", []) if t.get("apiName")
    ]

    champions = [
        {
            "api_name":        c["apiName"],
            "display_name":    c.get("name", c["apiName"]),
            "icon_url":        _icon_url(c.get("squareIcon") or c.get("icon")),
            "cost":            c.get("cost"),
            # linkage ในข้อมูลดิบเป็นชื่อ trait ไม่ใช่ apiName ต้องแปลงกลับผ่าน trait_name_to_api
            "trait_api_names": [trait_name_to_api[n] for n in c.get("traits", []) if n in trait_name_to_api],
        }
        # ไม่มี traits เลย = หน่วย PVE/neutral monster หรือ item anvil ไม่ใช่แชมป์เปี้ยนที่ผู้เล่นซื้อได้จริง
        for c in s.get("champions", []) if c.get("apiName") and c.get("traits")
    ]

    return {"set": s.get("mutator"), "number": s.get("number"), "traits": traits, "champions": champions}


def _active_mutators() -> list[str]:
    """
    หา mutator (เช่น "TFTSet17") ของทุก set ที่มีแมตช์จริงอยู่ใน DB ตอนนี้ (ไม่ใช่แค่ set ที่เยอะสุด)
    เพราะช่วงเปลี่ยน set ใหม่จะมีแมตช์ set เก่าค้างอยู่ใน retention window (TTL) ด้วย ถ้า map แค่ set เดียว
    trait/unit ของ set เก่าที่ยังไม่หมดอายุจะไม่มี icon/ชื่อให้
    """
    return [c for c in db.matches.distinct("tft_set_core_name") if c]


def refresh() -> bool:
    """ดึง mapping ล่าสุดจาก Community Dragon แล้วสลับเข้าไปแทนของเดิมทั้งชุด (fail-safe: error แล้วคงของเดิมไว้)"""
    global TRAIT_MAP, UNIT_MAP, ITEM_MAP, UPCOMING_SET, SET_ROSTERS

    try:
        resp = requests.get(CDRAGON_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning(f"cdragon refresh failed, keeping existing mapping: {e}")
        return False

    set_data  = data.get("setData", [])
    mutators  = _active_mutators()

    candidates = [s for s in set_data if s.get("mutator") in mutators]
    if not candidates:
        # cold start (ยังไม่มีแมตช์ใน DB เลย) — fallback ไปเอา set เลขสูงสุดที่เป็น mutator เปล่าๆ (ranked ปกติ ไม่ใช่ PVE/event mode)
        plain = [s for s in set_data if s.get("mutator") == f"TFTSet{s.get('number')}"]
        candidates = sorted(plain, key=lambda s: s.get("number", 0), reverse=True)[:1]

    if not candidates:
        log.warning("cdragon refresh: no matching set found, keeping existing mapping")
        return False

    # รวม trait/champion จากทุก set ที่ยังมีข้อมูลอยู่จริง (apiName มี prefix เลข set กำกับอยู่แล้วจึงไม่ชนกัน)
    new_traits: dict[str, dict] = {}
    new_units:  dict[str, dict] = {}
    for s in candidates:
        for t in s.get("traits", []):
            if t.get("apiName"):
                new_traits[t["apiName"]] = {"display_name": t.get("name", t["apiName"]), "icon_url": _icon_url(t.get("icon"))}
        for c in s.get("champions", []):
            if c.get("apiName"):
                new_units[c["apiName"]] = {"display_name": c.get("name", c["apiName"]), "icon_url": _icon_url(c.get("squareIcon") or c.get("icon"))}

    # items เป็น catalog รวมทุก set อยู่แล้วในตัว cdragon ไม่ต้อง filter ตาม set
    new_items = {
        it["apiName"]: {"display_name": it.get("name", it["apiName"]), "icon_url": _icon_url(it.get("icon"))}
        for it in data.get("items", []) if it.get("apiName")
    }

    TRAIT_MAP, UNIT_MAP, ITEM_MAP = new_traits, new_units, new_items
    log.info(f"cdragon mapping refreshed ({[s.get('mutator') for s in candidates]}): "
             f"{len(TRAIT_MAP)} traits, {len(UNIT_MAP)} units, {len(ITEM_MAP)} items")

    # ── Set rosters (Comp Builder) ────────────────────────────────────────────
    # cache roster เต็ม (trait tiers + champion/cost/trait linkage) ของทุก set ที่ cdragon มี "ranked ปกติ" (mutator เปล่าๆ)
    # ครอบคลุมทั้ง set เก่า, set ปัจจุบัน, และ set ถัดไปที่ยัง datamine มาไม่ครบ
    plain_sets = [s for s in set_data if s.get("mutator") == f"TFTSet{s.get('number')}"]
    SET_ROSTERS = {s["mutator"]: _build_roster(s) for s in plain_sets if s.get("champions")}
    log.info(f"set rosters cached: {sorted(SET_ROSTERS.keys())}")

    # ── Upcoming set preview ──────────────────────────────────────────────────
    # เช็คว่ามี set เลขถัดจาก set ล่าสุดที่มีคนเล่นจริงไหม (cdragon มักจะ datamine ไว้ล่วงหน้าจาก PBE)
    # ถ้ามี ก็แปะไว้ให้ frontend โชว์เป็น "coming soon" แทนสถิติที่ยังไม่มีอยู่จริง
    ingested_numbers = [
        int(m.group(1)) for c in mutators
        if (m := re.match(r"TFTSet(\d+)$", c))
    ]
    next_mutator = f"TFTSet{max(ingested_numbers) + 1}" if ingested_numbers else None
    UPCOMING_SET = SET_ROSTERS.get(next_mutator) if next_mutator else None
    if UPCOMING_SET:
        log.info(f"upcoming set preview available: {UPCOMING_SET['set']} ({len(UPCOMING_SET['traits'])} traits)")

    return True


def _lookup(mapping: dict, api_name: str | None) -> dict:
    if not api_name:
        return {"display_name": api_name, "icon_url": None}
    info = mapping.get(api_name)
    if not info:
        return {"display_name": api_name, "icon_url": None}
    return {"display_name": info["display_name"] or api_name, "icon_url": info["icon_url"]}


def trait_info(api_name: str | None) -> dict:
    return _lookup(TRAIT_MAP, api_name)


def unit_info(api_name: str | None) -> dict:
    return _lookup(UNIT_MAP, api_name)


def item_info(api_name: str | None) -> dict:
    return _lookup(ITEM_MAP, api_name)
