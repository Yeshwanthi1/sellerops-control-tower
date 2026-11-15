"""
Data export utilities: CSV, JSON, and SQL dump generation.
Supports both default demo database and full-scale database exports into clearly named directories.
"""
import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path
from typing import List, Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.config import DB_PATH, EXPORTS_DIR, DATA_DIR
from src.database import get_db_connection

TABLES = [
    "sellers",
    "product_listings",
    "commission_rules",
    "reserve_rules",
    "orders",
    "order_lines",
    "fulfillments",
    "customer_reviews",
    "disputes",
    "payouts",
    "payout_lines",
    "event_logs"
]

class Exporter:
    def __init__(self, db_conn: sqlite3.Connection = None, export_root: Path = EXPORTS_DIR):
        self.conn = db_conn or get_db_connection()
        self.export_root = Path(export_root)
        self.csv_dir = self.export_root / "csv"
        self.json_dir = self.export_root / "json"
        self.sql_dir = self.export_root / "sql"
        
        self.csv_dir.mkdir(parents=True, exist_ok=True)
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.sql_dir.mkdir(parents=True, exist_ok=True)

    def export_csv(self) -> Dict[str, str]:
        """Export all database tables to individual CSV files."""
        results = {}
        cur = self.conn.cursor()
        print(f"[*] Exporting CSV tables to {self.csv_dir}...")
        for table in TABLES:
            out_file = self.csv_dir / f"{table}.csv"
            cur.execute(f"SELECT * FROM {table};")
            col_names = [desc[0] for desc in cur.description]
            with open(out_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(col_names)
                row_cnt = 0
                for row in cur:
                    writer.writerow(list(row))
                    row_cnt += 1
            results[table] = str(out_file)
            print(f"  [+] {table}.csv: {row_cnt:,} rows written")
        return results

    def export_json(self) -> Dict[str, str]:
        """Export all database tables to structured JSON files with memory-efficient streaming."""
        results = {}
        cur = self.conn.cursor()
        print(f"[*] Exporting JSON tables to {self.json_dir}...")
        for table in TABLES:
            out_file = self.json_dir / f"{table}.json"
            cur.execute(f"SELECT * FROM {table};")
            col_names = [desc[0] for desc in cur.description]
            row_cnt = 0
            with open(out_file, "w", encoding="utf-8") as f:
                f.write("[\n")
                first = True
                for row in cur:
                    if not first:
                        f.write(",\n")
                    first = False
                    row_dict = dict(zip(col_names, row))
                    f.write("  " + json.dumps(row_dict, default=str))
                    row_cnt += 1
                f.write("\n]\n")
            results[table] = str(out_file)
            print(f"  [+] {table}.json: {row_cnt:,} records written")
        return results

    def export_sql(self) -> str:
        """Export full SQLite database to a standard SQL dump script."""
        out_file = self.sql_dir / "sellerops_dump.sql"
        print(f"[*] Exporting SQL dump to {out_file}...")
        line_cnt = 0
        with open(out_file, "w", encoding="utf-8") as f:
            for line in self.conn.iterdump():
                f.write(f"{line}\n")
                line_cnt += 1
        print(f"  [+] sellerops_dump.sql: {line_cnt:,} SQL statements written")
        return str(out_file)

    def export_all(self) -> Dict[str, Any]:
        """Run all export formats."""
        csv_files = self.export_csv()
        json_files = self.export_json()
        sql_file = self.export_sql()
        return {
            "csv_exports": csv_files,
            "json_exports": json_files,
            "sql_dump": sql_file
        }

def main():
    parser = argparse.ArgumentParser(description="Export database to CSV, JSON, and SQL dump")
    parser.add_argument("--full", action="store_true", help="Export from full-scale database (data/sellerops_full.db) to exports/full_scale/")
    parser.add_argument("--db", type=str, default=None, help="Custom database path")
    parser.add_argument("--out-dir", type=str, default=None, help="Custom output export directory")
    args = parser.parse_args()

    if args.full:
        db_file = DATA_DIR / "sellerops_full.db"
        out_directory = EXPORTS_DIR / "full_scale"
        print(f"[*] FULL-SCALE EXPORT MODE: DB = {db_file}, Output = {out_directory}")
    else:
        db_file = Path(args.db) if args.db else DB_PATH
        out_directory = Path(args.out_dir) if args.out_dir else EXPORTS_DIR
        print(f"[*] STANDARD EXPORT MODE: DB = {db_file}, Output = {out_directory}")

    if not db_file.exists():
        print(f"[!] Target database does not exist: {db_file}")
        sys.exit(1)

    conn = get_db_connection(db_file)
    try:
        exporter = Exporter(db_conn=conn, export_root=out_directory)
        res = exporter.export_all()
        print("\n[✓] All exports completed successfully!")
        print(f"  CSV:  {exporter.csv_dir}")
        print(f"  JSON: {exporter.json_dir}")
        print(f"  SQL:  {res['sql_dump']}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
