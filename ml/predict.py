"""
TFT Comp Analyzer & Predictor
รับ comp ที่เล่นไป แล้ว predict:
- top4 probability (%)
- tier (S/A/B/C/D)
- เทียบกับ comp tier list ที่ใกล้เคียงที่สุด
"""

import json
import joblib
import logging
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

MODEL_PATH     = "model.joblib"
ENCODERS_PATH  = "encoders.joblib"
TIER_LIST_PATH = "tier_list.json"

TIER_THRESHOLDS = {
    "S": 65,
    "A": 55,
    "B": 45,
    "C": 35,
}


def classify_tier(top4_rate: float) -> str:
    if top4_rate >= TIER_THRESHOLDS["S"]: return "S"
    if top4_rate >= TIER_THRESHOLDS["A"]: return "A"
    if top4_rate >= TIER_THRESHOLDS["B"]: return "B"
    if top4_rate >= TIER_THRESHOLDS["C"]: return "C"
    return "D"


class TFTPredictor:
    def __init__(self):
        log.info("Loading model and encoders...")
        self.model    = joblib.load(MODEL_PATH)
        self.encoders = joblib.load(ENCODERS_PATH)

        with open(TIER_LIST_PATH, "r", encoding="utf-8") as f:
            tier_data = json.load(f)

        self.trait_tier_list = tier_data["trait_tier_list"]
        self.comp_tier_list  = tier_data["comp_tier_list"]
        log.info("Ready.")

    def _build_feature_vector(
        self,
        active_traits: list[str],   # ["TraitName|style", ...]  เช่น ["Rebel|3", "Invoker|2"]
        units: list[str],            # ["character_id|tier", ...] เช่น ["TFT13_Jinx|2"]
        items: list[str],            # ["ItemName", ...]
        augments: list[str],         # ["AugmentName", ...]
    ) -> np.ndarray:

        mlb_traits   = self.encoders["traits"]
        mlb_units    = self.encoders["units"]
        mlb_items    = self.encoders["items"]
        mlb_augments = self.encoders["augments"]

        # transform แต่ละ group (ต้องใช้ transform ไม่ใช่ fit_transform)
        X_traits   = mlb_traits.transform([active_traits])
        X_units    = mlb_units.transform([units])
        X_items    = mlb_items.transform([items])
        X_augments = mlb_augments.transform([augments])

        return np.hstack([X_traits, X_units, X_items, X_augments])

    def predict_comp(
        self,
        active_traits: list[str],
        units: list[str],
        items: list[str],
        augments: list[str],
    ) -> dict:
        """
        ทำนาย top4 probability และ tier ของ comp ที่ให้มา
        """
        X = self._build_feature_vector(active_traits, units, items, augments)

        top4_prob = float(self.model.predict_proba(X)[0, 1]) * 100
        tier      = classify_tier(top4_prob)

        # หา trait tier ของแต่ละ trait ที่ active
        trait_analysis = self._analyze_traits(active_traits)

        # หา comp ที่ใกล้เคียงที่สุดจาก tier list
        similar_comp = self._find_similar_comp(active_traits)

        return {
            "top4_probability": round(top4_prob, 1),
            "tier":             tier,
            "trait_analysis":   trait_analysis,
            "similar_comp":     similar_comp,
        }

    def _analyze_traits(self, active_traits: list[str]) -> list[dict]:
        """
        วิเคราะห์แต่ละ trait ที่ active ว่า tier ไหน
        """
        style_map = {1: "Bronze", 2: "Silver", 3: "Gold", 4: "Prismatic"}

        # สร้าง lookup จาก tier list
        trait_lookup = {
            f"{t['name']}|{t['style']}": t
            for t in self.trait_tier_list
        }

        result = []
        for trait_str in active_traits:
            info = trait_lookup.get(trait_str)
            if info:
                parts     = trait_str.rsplit("|", 1)
                style_str = style_map.get(int(parts[1]), "") if len(parts) == 2 else ""
                result.append({
                    "trait":         parts[0],
                    "style":         style_str,
                    "top4_rate":     info["top4_rate"],
                    "avg_placement": info["avg_placement"],
                    "tier":          info["tier"],
                })

        result.sort(key=lambda x: x["top4_rate"], reverse=True)
        return result

    def _find_similar_comp(self, active_traits: list[str]) -> dict | None:
        """
        หา comp จาก tier list ที่มี key_traits ตรงกับ input มากที่สุด
        """
        if not self.comp_tier_list:
            return None

        best_match = None
        best_score = -1

        input_trait_names = set(t.rsplit("|", 1)[0] for t in active_traits)

        for comp in self.comp_tier_list:
            key_trait_names = set(t.rsplit("|", 1)[0] for t in comp["key_traits"])
            if not key_trait_names:
                continue

            # Jaccard similarity
            intersection = len(input_trait_names & key_trait_names)
            union        = len(input_trait_names | key_trait_names)
            score        = intersection / union if union > 0 else 0

            if score > best_score:
                best_score = score
                best_match = comp

        if best_match and best_score > 0:
            return {
                "comp_label":    best_match["comp_label"],
                "top4_rate":     best_match["top4_rate"],
                "avg_placement": best_match["avg_placement"],
                "tier":          best_match["tier"],
                "similarity":    round(best_score * 100, 1),
            }
        return None

    def get_trait_tier_list(self, tier_filter: str = None) -> list[dict]:
        """คืน trait tier list ทั้งหมด หรือ filter ตาม tier"""
        if tier_filter:
            return [t for t in self.trait_tier_list if t["tier"] == tier_filter.upper()]
        return self.trait_tier_list

    def get_comp_tier_list(self, tier_filter: str = None) -> list[dict]:
        """คืน comp tier list ทั้งหมด หรือ filter ตาม tier"""
        if tier_filter:
            return [c for c in self.comp_tier_list if c["tier"] == tier_filter.upper()]
        return self.comp_tier_list


# ── Example Usage ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    predictor = TFTPredictor()

    # ตัวอย่าง input (ต้องใช้ format เดียวกับที่ train)
    result = predictor.predict_comp(
        active_traits=["Rebel|3", "Invoker|2", "Slayer|2"],
        units=["TFT13_Jinx|2", "TFT13_Ekko|1", "TFT13_Vi|1"],
        items=["TFT_Item_RabadonsDeathcap", "TFT_Item_GuinsoosRageblade"],
        augments=["TFT_Augment_RebelHeart"],
    )

    print("\n═══ Comp Analysis ═══")
    print(f"Top4 Probability : {result['top4_probability']}%")
    print(f"Tier             : {result['tier']}")

    print("\n── Trait Analysis ──")
    for t in result["trait_analysis"]:
        print(f"  {t['trait']} ({t['style']:>9}) → {t['top4_rate']}% top4 | {t['tier']} tier")

    if result["similar_comp"]:
        sc = result["similar_comp"]
        print(f"\n── Similar Comp ──")
        print(f"  {sc['comp_label']}")
        print(f"  Top4 Rate : {sc['top4_rate']}% | Tier: {sc['tier']}")
        print(f"  Similarity: {sc['similarity']}%")