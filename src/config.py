"""
Configuration and constants for SellerOps Control Tower.
"""
import os
from pathlib import Path

# Base workspace path dynamically resolved from project root
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
EXPORTS_DIR = BASE_DIR / "exports"
STATIC_DIR = BASE_DIR / "src" / "static"

DB_PATH = DATA_DIR / "sellerops.db"
GROUND_TRUTH_CSV = DATA_DIR / "ground_truth.csv"
GROUND_TRUTH_JSON = DATA_DIR / "ground_truth.json"

DEFAULT_SEED = 20261022
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8000

# Scale definitions
SCALE_CONFIGS = {
    "demo": {
        "sellers": 50,
        "listings": 250,
        "orders": 1000,
        "disputes": 80,
        "payouts": 200,
    },
    "full": {
        "sellers": 2000,
        "listings": 20000,
        "orders": 100000,
        "disputes": 10000,
        "payouts": 25000,
    }
}
