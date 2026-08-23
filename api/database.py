import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = (
    f"mongodb://{os.getenv('MONGO_USER')}:{os.getenv('MONGO_PASSWORD')}"
    f"@{os.getenv('MONGO_HOST')}:{os.getenv('MONGO_PORT')}/?authSource=admin"
)

client = MongoClient(MONGO_URI)
db = client[os.getenv("MONGO_DB_NAME", "tft_predictor")]


def get_db():
    yield db
