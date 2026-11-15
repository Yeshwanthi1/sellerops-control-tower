"""
Reproducibility verifier for SellerOps Control Tower.
Runs two independent generations with identical seed (20261022) into separate databases.
Compares row counts and table-level SHA256 checksums to prove 100% deterministic reproducibility.
"""
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Any, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.config import DATA_DIR, DEFAULT_SEED
from src.database import init_db, get_db_connection
from src.generator import DataGenerator
from src.exporter import TABLES

def hash_table(conn: sqlite3.Connection, table_name: str) -> Tuple[int, str]:
    """Calculate row count and deterministic SHA-256 hash of table rows."""
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table_name} ORDER BY 1;")
    rows = cur.fetchall()
    count = len(rows)
    
    hasher = hashlib.sha256()
    for row in rows:
        row_str = "|".join("" if v is None else str(v) for v in row)
        hasher.update(row_str.encode("utf-8"))
        hasher.update(b"\n")
    return count, hasher.hexdigest()

def run_reproducibility_test(seed: int = DEFAULT_SEED, scale: str = "demo") -> Dict[str, Any]:
    print("=" * 70)
    print(f"VERIFYING DETERMINISTIC REPRODUCIBILITY (SEED: {seed}, SCALE: {scale})")
    print("=" * 70)

    db1_path = DATA_DIR / "test_repro_1.db"
    db2_path = DATA_DIR / "test_repro_2.db"

    for p in (db1_path, db2_path):
        if p.exists():
            p.unlink()

    # Run 1
    temp_dir = DATA_DIR / "temp_repro"
    temp_dir.mkdir(parents=True, exist_ok=True)
    print("[1/2] Generating first dataset run...")
    init_db(db1_path)
    conn1 = get_db_connection(db1_path)
    try:
        gen1 = DataGenerator(seed=seed, scale=scale, ground_truth_dir=temp_dir)
        gen1.run(conn1)
    finally:
        conn1.close()

    # Run 2
    print("[2/2] Generating second dataset run...")
    init_db(db2_path)
    conn2 = get_db_connection(db2_path)
    try:
        gen2 = DataGenerator(seed=seed, scale=scale, ground_truth_dir=temp_dir)
        gen2.run(conn2)
    finally:
        conn2.close()

    # Compare tables
    conn1 = get_db_connection(db1_path)
    conn2 = get_db_connection(db2_path)

    table_results = {}
    all_match = True

    print("\n%-22s | %-8s | %-8s | %-12s | %s" % ("Table", "Run1 Cnt", "Run2 Cnt", "Match?", "SHA-256 Checksum (Prefix)"))
    print("-" * 75)

    for table in TABLES:
        cnt1, hash1 = hash_table(conn1, table)
        cnt2, hash2 = hash_table(conn2, table)
        matched = (cnt1 == cnt2) and (hash1 == hash2)
        if not matched:
            all_match = False
        table_results[table] = {
            "count_run1": cnt1,
            "count_run2": cnt2,
            "hash_run1": hash1,
            "hash_run2": hash2,
            "match": matched
        }
        match_str = "[MATCH]" if matched else "[MISMATCH]"
        print(f"{table:<22} | {cnt1:<8} | {cnt2:<8} | {match_str:<12} | {hash1[:16]}...")

    conn1.close()
    conn2.close()

    # Cleanup test databases and temp dir
    for p in (db1_path, db2_path):
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass
    if temp_dir.exists():
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("=" * 75)
    print(f"REPRODUCIBILITY RESULT: {'100% BIT-FOR-BIT IDENTICAL [PASS]' if all_match else 'FAILED [X]'}")
    print("=" * 75)

    return {
        "seed": seed,
        "scale": scale,
        "all_match": all_match,
        "tables": table_results
    }

if __name__ == "__main__":
    import argparse
    from typing import Tuple
    parser = argparse.ArgumentParser(description="Deterministic reproducibility verification test")
    parser.add_argument("--scale", choices=["demo", "full"], default="demo", help="Dataset scale: demo or full")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"Random seed (default: {DEFAULT_SEED})")
    args = parser.parse_args()

    res = run_reproducibility_test(seed=args.seed, scale=args.scale)
    sys.exit(0 if res["all_match"] else 1)
