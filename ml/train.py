"""
TFT Meta ML Trainer
- ดึงข้อมูลจาก DB
- Feature engineering: traits, augments, units, items
- Train XGBoost model ทำนาย top4 probability
- Cluster comps และ classify tier list (S/A/B/C/D)
- Save model และ tier list ออกมาเป็น JSON
"""

import os
import json
import joblib
import logging
from collections import Counter
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient
from sklearn.preprocessing import MultiLabelBinarizer
from sklearn.cluster import KMeans
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, classification_report
from xgboost import XGBClassifier

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
MONGO_URI = (
    f"mongodb://{os.getenv('MONGO_USER')}:{os.getenv('MONGO_PASSWORD')}"
    f"@{os.getenv('MONGO_HOST')}:{os.getenv('MONGO_PORT')}/?authSource=admin"
)

MODEL_PATH      = "model.joblib"
ENCODERS_PATH   = "encoders.joblib"
TIER_LIST_PATH  = "tier_list.json"

# Tier thresholds (top4 rate %)
TIER_THRESHOLDS = {
    "S": 65,
    "A": 55,
    "B": 45,
    "C": 35,
}

NUM_COMP_CLUSTERS = 50   # จำนวน comp cluster

client = MongoClient(MONGO_URI)
db     = client[os.getenv("MONGO_DB_NAME", "tft_predictor")]


# ── Tier Helper ───────────────────────────────────────────────────────────────
def classify_tier(top4_rate: float) -> str:
    if top4_rate >= TIER_THRESHOLDS["S"]: return "S"
    if top4_rate >= TIER_THRESHOLDS["A"]: return "A"
    if top4_rate >= TIER_THRESHOLDS["B"]: return "B"
    if top4_rate >= TIER_THRESHOLDS["C"]: return "C"
    return "D"


# ── Step 1: Load Data ─────────────────────────────────────────────────────────
def load_data() -> pd.DataFrame:
    log.info("Loading data from DB...")

    pipeline = [
        {"$match": {"traits": {"$ne": []}}},  # เอาเฉพาะ row ที่มี trait data
        {"$project": {
            "_id":            0,
            "participant_id": "$_id",
            "placement":      1,
            "augments":       1,
            "top4":           {"$cond": [{"$lte": ["$placement", 4]}, 1, 0]},

            # traits: รวมเป็น set ของ "name|style" (เฉพาะ style > 0)
            "active_traits": {"$setUnion": [{
                "$map": {
                    "input": {"$filter": {"input": "$traits", "cond": {"$gt": ["$$this.style", 0]}}},
                    "as":    "t",
                    "in":    {"$concat": ["$$t.name", "|", {"$toString": "$$t.style"}]},
                }
            }, []]},

            # units: รวมเป็น set ของ "character_id|tier"
            "units": {"$setUnion": [{
                "$map": {
                    "input": "$units",
                    "as":    "u",
                    "in":    {"$concat": ["$$u.character_id", "|", {"$toString": "$$u.tier"}]},
                }
            }, []]},

            # items: รวมทุก item จากทุก unit (dedup, ตัด empty string ทิ้ง)
            "items": {"$setDifference": [{
                "$reduce": {
                    "input":        "$units.items",
                    "initialValue": [],
                    "in":           {"$setUnion": ["$$value", "$$this"]},
                }
            }, [""]]},
        }},
    ]

    df = pd.DataFrame(list(db.participants.aggregate(pipeline)))
    log.info(f"Loaded {len(df):,} participants")

    df["augments"] = df["augments"].apply(lambda x: x if isinstance(x, list) else [])

    return df


# ── Step 2: Feature Engineering ───────────────────────────────────────────────
def build_features(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, dict]:
    log.info("Building features...")

    # MultiLabelBinarizer สำหรับแต่ละ feature group
    mlb_traits   = MultiLabelBinarizer()
    mlb_units    = MultiLabelBinarizer()
    mlb_items    = MultiLabelBinarizer()
    mlb_augments = MultiLabelBinarizer()

    X_traits   = mlb_traits.fit_transform(df["active_traits"])
    X_units    = mlb_units.fit_transform(df["units"])
    X_items    = mlb_items.fit_transform(df["items"])
    X_augments = mlb_augments.fit_transform(df["augments"])

    X = np.hstack([X_traits, X_units, X_items, X_augments])
    y = df["top4"].values

    encoders = {
        "traits":   mlb_traits,
        "units":    mlb_units,
        "items":    mlb_items,
        "augments": mlb_augments,
        "n_traits": X_traits.shape[1],
        "n_units":  X_units.shape[1],
        "n_items":  X_items.shape[1],
    }

    log.info(f"Feature matrix: {X.shape[0]:,} rows × {X.shape[1]:,} features")
    log.info(f"  Traits: {X_traits.shape[1]} | Units: {X_units.shape[1]} | Items: {X_items.shape[1]} | Augments: {X_augments.shape[1]}")
    log.info(f"  Top4 rate overall: {y.mean()*100:.1f}%")

    return X, y, encoders


# ── Step 3: Train XGBoost ─────────────────────────────────────────────────────
def train_model(X: np.ndarray, y: np.ndarray) -> XGBClassifier:
    log.info("Training XGBoost model...")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    model = XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        use_label_encoder=False,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=50,
    )

    # Evaluate
    y_pred_proba = model.predict_proba(X_test)[:, 1]
    y_pred       = (y_pred_proba >= 0.5).astype(int)
    auc          = roc_auc_score(y_test, y_pred_proba)

    log.info(f"  AUC-ROC: {auc:.4f}")
    log.info(f"\n{classification_report(y_test, y_pred, target_names=['bot4', 'top4'])}")

    return model


# ── Step 4: Trait Tier List ───────────────────────────────────────────────────
def build_trait_tier_list() -> list[dict]:
    log.info("Building trait tier list...")

    pipeline = [
        {"$unwind": "$traits"},
        {"$match": {"traits.style": {"$gt": 0}}},
        {"$group": {
            "_id":           {"name": "$traits.name", "style": "$traits.style"},
            "play_count":    {"$sum": 1},
            "avg_placement": {"$avg": "$placement"},
            "top4_count":    {"$sum": {"$cond": [{"$lte": ["$placement", 4]}, 1, 0]}},
        }},
        {"$match": {"play_count": {"$gte": 30}}},
    ]

    rows = list(db.participants.aggregate(pipeline))

    tier_list = []
    for row in rows:
        play_count = row["play_count"]
        top4_rate  = round(100.0 * row["top4_count"] / play_count, 1)
        tier_list.append({
            "name":          row["_id"]["name"],
            "style":         int(row["_id"]["style"]),
            "play_count":    int(play_count),
            "avg_placement": round(float(row["avg_placement"]), 2),
            "top4_rate":     top4_rate,
            "tier":          classify_tier(top4_rate),
        })

    tier_list.sort(key=lambda x: x["top4_rate"], reverse=True)
    log.info(f"  Trait tier list: {len(tier_list)} entries")
    return tier_list


# ── Step 5: Comp Tier List (Clustering) ──────────────────────────────────────
def build_comp_tier_list(df: pd.DataFrame, X: np.ndarray, model: XGBClassifier, encoders: dict) -> list[dict]:
    log.info("Building comp tier list via clustering...")

    # ใช้เฉพาะ trait features สำหรับ clustering (ไม่รวม units/items/augments)
    n_traits = encoders["n_traits"]
    X_traits_only = X[:, :n_traits]

    # KMeans clustering
    n_clusters = min(NUM_COMP_CLUSTERS, len(df))
    log.info(f"  Clustering into {n_clusters} comp groups...")

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    df = df.copy()
    df["cluster"] = kmeans.fit_predict(X_traits_only)

    # predict top4 probability สำหรับทุก row
    df["top4_prob"] = model.predict_proba(X)[:, 1] * 100

    # สร้าง tier list ต่อ cluster
    mlb_traits = encoders["traits"]
    comp_tier_list = []

    for cluster_id in range(n_clusters):
        cluster_df = df[df["cluster"] == cluster_id]

        if len(cluster_df) < 10:
            continue

        top4_rate   = cluster_df["top4"].mean() * 100
        avg_prob    = cluster_df["top4_prob"].mean()
        avg_placement = cluster_df["placement"].mean()
        play_count  = len(cluster_df)

        # หา dominant traits ของ cluster นี้
        # ดู centroid ของ cluster แล้วเอา trait ที่ค่าสูงสุด
        centroid     = kmeans.cluster_centers_[cluster_id]
        top_indices  = centroid.argsort()[::-1][:6]   # เอา top 6 traits
        trait_names  = [
            mlb_traits.classes_[i]
            for i in top_indices
            if centroid[i] > 0.2   # threshold ว่า trait นี้ dominant จริง
        ]

        # แปลง "TraitName|style" → "TraitName (Gold)" เป็นต้น
        style_map  = {1: "Bronze", 2: "Silver", 3: "Gold", 4: "Prismatic"}
        comp_label_parts = []
        for t in trait_names:
            parts = t.rsplit("|", 1)
            if len(parts) == 2:
                name, style = parts
                style_str   = style_map.get(int(style), "")
                comp_label_parts.append(f"{name} ({style_str})")
            else:
                comp_label_parts.append(t)

        comp_label = " + ".join(comp_label_parts) if comp_label_parts else f"Comp #{cluster_id}"

        # หา champion ที่ใช้บ่อยที่สุดใน cluster นี้ (ไม่สนดาว เอาแค่ตัวละคร) — ไม่ได้มาจาก centroid
        # เพราะ clustering ใช้แค่ trait features เลยต้องนับความถี่จาก raw units ของแต่ละแถวในคลัสเตอร์แทน
        champion_counter = Counter()
        for units in cluster_df["units"]:
            champion_counter.update({u.rsplit("|", 1)[0] for u in units})
        key_units = [champ for champ, _ in champion_counter.most_common(8)]

        comp_tier_list.append({
            "cluster_id":    cluster_id,
            "comp_label":    comp_label,
            "play_count":    int(play_count),
            "avg_placement": round(float(avg_placement), 2),
            "top4_rate":     round(float(top4_rate), 1),
            "avg_top4_prob": round(float(avg_prob), 1),
            "tier":          classify_tier(top4_rate),
            "key_traits":    trait_names,
            "key_units":     key_units,
        })

    # เรียงตาม top4_rate
    comp_tier_list.sort(key=lambda x: x["top4_rate"], reverse=True)
    log.info(f"  Comp tier list: {len(comp_tier_list)} comps")
    return comp_tier_list


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    log.info("═══ TFT ML Trainer Started ═══")

    # 1. Load
    df = load_data()
    if len(df) < 100:
        log.error(f"Not enough data to train ({len(df)} rows). Need at least 100.")
        return

    # 2. Features
    X, y, encoders = build_features(df)

    # 3. Train model
    model = train_model(X, y)

    # 4. Trait tier list (ไม่ต้องใช้ model ตรงๆ)
    trait_tier_list = build_trait_tier_list()

    # 5. Comp tier list
    comp_tier_list = build_comp_tier_list(df, X, model, encoders)

    # 6. Save
    log.info("Saving model and tier lists...")

    joblib.dump(model,    MODEL_PATH)
    joblib.dump(encoders, ENCODERS_PATH)

    tier_list_output = {
        "trait_tier_list": trait_tier_list,
        "comp_tier_list":  comp_tier_list,
    }

    with open(TIER_LIST_PATH, "w", encoding="utf-8") as f:
        json.dump(tier_list_output, f, ensure_ascii=False, indent=2)

    log.info(f"  Model saved     → {MODEL_PATH}")
    log.info(f"  Encoders saved  → {ENCODERS_PATH}")
    log.info(f"  Tier list saved → {TIER_LIST_PATH}")
    log.info("═══ Training Complete ═══")

    # Summary
    tier_counts = {}
    for comp in comp_tier_list:
        t = comp["tier"]
        tier_counts[t] = tier_counts.get(t, 0) + 1

    log.info("Comp Tier Summary:")
    for tier in ["S", "A", "B", "C", "D"]:
        count = tier_counts.get(tier, 0)
        log.info(f"  {tier}: {count} comps")


if __name__ == "__main__":
    main()