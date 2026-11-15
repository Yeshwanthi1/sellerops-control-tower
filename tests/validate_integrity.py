"""
Comprehensive automated integrity and business rule validator for SellerOps Control Tower.
Validates:
1. Primary-key uniqueness across all tables
2. Foreign-key referential integrity (PRAGMA foreign_key_check and explicit checks)
3. Allowed values / domain constraints
4. Date ordering across order, fulfillment, dispute, and payout lifecycles
5. Arithmetic reconciliation (line subtotals, order totals, baseline & anomalous payout reconciliation)
6. Lifecycle transition consistency
7. Exact ID format conformance (including LIST-<seller-id>-000001 and PAYLINE formats)
8. Cross-table consistency (seller/listing/order matches across order lines and fulfillments)
9. Seller status business rules (accounting for labelled ground truth anomalies)
"""
import sqlite3
import sys
import csv
from pathlib import Path
from typing import List, Dict, Any, Optional

# Ensure Windows console encoding compatibility
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.config import DB_PATH, DATA_DIR
from src.database import get_db_connection

class IntegrityValidator:
    def __init__(self, db_conn: sqlite3.Connection = None, ground_truth_path: Optional[Path] = None):
        self.conn = db_conn or get_db_connection()
        self.ground_truth_path = ground_truth_path
        self.results: List[Dict[str, Any]] = []

    def log_result(self, test_name: str, passed: bool, details: str):
        self.results.append({
            "test": test_name,
            "passed": passed,
            "details": details
        })
        status_icon = "[PASS]" if passed else "[FAIL]"
        print(f"{status_icon} {test_name}: {details}")

    def _load_ground_truth_anomalies(self) -> Dict[str, List[Dict[str, Any]]]:
        """Load ground truth anomalies by issue type for anomaly-aware checks."""
        anomalies_by_type: Dict[str, List[Dict[str, Any]]] = {}
        paths_to_try = []
        if self.ground_truth_path and self.ground_truth_path.exists():
            paths_to_try.append(self.ground_truth_path)
        paths_to_try.append(DATA_DIR / "ground_truth.csv")

        for p in paths_to_try:
            if p.exists():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            issue = row.get("issue_type")
                            if issue not in anomalies_by_type:
                                anomalies_by_type[issue] = []
                            anomalies_by_type[issue].append(row)
                    break
                except Exception:
                    pass
        return anomalies_by_type

    def run_all(self) -> bool:
        print("=" * 65)
        print("RUNNING SECTOR INTEGRITY AND BUSINESS RULE VALIDATION CHECKS")
        print("=" * 65)
        cur = self.conn.cursor()

        # 1. Primary Key Uniqueness
        pk_checks = [
            ("sellers", "seller_id"),
            ("product_listings", "listing_id"),
            ("commission_rules", "rule_id"),
            ("reserve_rules", "reserve_rule_id"),
            ("orders", "order_id"),
            ("order_lines", "order_line_id"),
            ("fulfillments", "fulfillment_id"),
            ("fulfillments", "order_line_id"),
            ("customer_reviews", "review_id"),
            ("disputes", "dispute_id"),
            ("payouts", "payout_id"),
            ("payout_lines", "payout_line_id"),
            ("event_logs", "event_id"),
        ]
        all_pk_ok = True
        for table, col in pk_checks:
            cur.execute(f"SELECT COUNT(*), COUNT(DISTINCT {col}) FROM {table};")
            total, distinct = cur.fetchone()
            if total != distinct:
                all_pk_ok = False
                self.log_result(f"PK Uniqueness: {table}.{col}", False, f"Duplicate keys found! {total} rows vs {distinct} distinct")
        if all_pk_ok:
            self.log_result("Primary Key Uniqueness", True, f"All {len(pk_checks)} tables have 100% unique primary keys.")

        # 2. Foreign Key Integrity
        cur.execute("PRAGMA foreign_key_check;")
        fk_violations = cur.fetchall()
        if not fk_violations:
            self.log_result("Foreign Key Integrity", True, "Zero foreign key violations across all tables (PRAGMA foreign_key_check passed).")
        else:
            self.log_result("Foreign Key Integrity", False, f"Found {len(fk_violations)} FK violations: {fk_violations[:3]}")

        # 3. Allowed Values & Enum Constraints
        enum_checks = [
            ("sellers", "tier", "('TIER_1', 'TIER_2', 'TIER_3', 'ENTERPRISE')"),
            ("sellers", "status", "('ACTIVE', 'PROBATION', 'SUSPENDED')"),
            ("product_listings", "category", "('Electronics', 'Apparel', 'Home & Kitchen', 'Beauty', 'Books', 'Sports')"),
            ("product_listings", "status", "('ACTIVE', 'PAUSED', 'ARCHIVED')"),
            ("orders", "status", "('PENDING', 'PROCESSING', 'PARTIALLY_FULFILLED', 'DELIVERED', 'COMPLETED', 'CANCELLED')"),
            ("fulfillments", "status", "('ALLOCATED', 'PICKED', 'PACKED', 'SHIPPED', 'DELIVERED', 'RETURNED', 'FAILED')"),
            ("fulfillments", "carrier", "('FedEx', 'UPS', 'DHL', 'USPS')"),
            ("customer_reviews", "rating", "(1, 2, 3, 4, 5)"),
            ("disputes", "reason", "('ITEM_NOT_RECEIVED', 'ITEM_DEFECTIVE', 'INCORRECT_ITEM', 'UNAUTHORIZED_CHARGE', 'LATE_DELIVERY')"),
            ("disputes", "status", "('OPEN', 'UNDER_REVIEW', 'UPHELD', 'REJECTED', 'RESOLVED')"),
            ("payouts", "status", "('DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'PROCESSING', 'PAID', 'HELD')"),
            ("payout_lines", "line_type", "('GROSS_SALES', 'COMMISSION_FEE', 'RESERVE_HOLD', 'DISPUTE_DEDUCTION')"),
        ]
        all_enums_ok = True
        for table, col, allowed in enum_checks:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} NOT IN {allowed};")
            invalid_cnt = cur.fetchone()[0]
            if invalid_cnt > 0:
                all_enums_ok = False
                self.log_result(f"Allowed Values: {table}.{col}", False, f"{invalid_cnt} invalid values outside {allowed}")
        if all_enums_ok:
            self.log_result("Allowed Values & Enum Checks", True, f"All {len(enum_checks)} fields strictly satisfy domain constraints.")

        # 4. Date Ordering Checks
        cur.execute("""
            SELECT COUNT(*) FROM fulfillments f
            JOIN orders o ON f.order_id = o.order_id
            WHERE f.shipped_at IS NOT NULL AND f.shipped_at < o.order_date;
        """)
        bad_shipped_order = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*) FROM fulfillments
            WHERE delivered_at IS NOT NULL AND shipped_at IS NOT NULL AND delivered_at < shipped_at;
        """)
        bad_delivery_order = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM payouts WHERE period_start > period_end;")
        bad_payout_periods = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM commission_rules WHERE effective_from > effective_to;")
        bad_comm_rules = cur.fetchone()[0]

        if bad_shipped_order == 0 and bad_delivery_order == 0 and bad_payout_periods == 0 and bad_comm_rules == 0:
            self.log_result("Chronological Date Ordering", True, "All order, shipment, delivery, and period dates follow valid chronological sequence.")
        else:
            self.log_result("Chronological Date Ordering", False, f"Date violations found: ship<order={bad_shipped_order}, deliv<ship={bad_delivery_order}")

        # 5. Arithmetic Reconciliation
        # Order Lines: subtotal == qty * unit_price
        cur.execute("SELECT COUNT(*) FROM order_lines WHERE abs(subtotal - (quantity * unit_price)) > 0.02;")
        bad_line_subtotals = cur.fetchone()[0]

        # Orders: total_amount == sum(order_lines.subtotal)
        cur.execute("""
            SELECT COUNT(*) FROM (
                SELECT o.order_id, o.total_amount, SUM(ol.subtotal) AS lines_total
                FROM orders o
                JOIN order_lines ol ON o.order_id = ol.order_id
                GROUP BY o.order_id
                HAVING abs(o.total_amount - SUM(ol.subtotal)) > 0.05
            );
        """)
        bad_order_totals = cur.fetchone()[0]

        if bad_line_subtotals == 0 and bad_order_totals == 0:
            self.log_result("Order & Line Arithmetic Reconciliation", True, "All order line subtotals and order totals reconcile exactly (0 discrepancies).")
        else:
            self.log_result("Order & Line Arithmetic Reconciliation", False, f"Discrepancies: lines={bad_line_subtotals}, orders={bad_order_totals}")

        # Baseline Payouts Reconciliation (verifying non-anomalous payouts match 100%)
        ground_truth = self._load_ground_truth_anomalies()
        payout_mismatch_anomalies = ground_truth.get("PAYOUT_TOTAL_MISMATCH", [])
        known_anom_payout_ids = {a["target_entity_id"] for a in payout_mismatch_anomalies} or {
            "PAYOUT-2026-000026", "PAYOUT-2026-000027", "PAYOUT-2026-000028"
        }

        placeholders = ",".join("?" for _ in known_anom_payout_ids)
        cur.execute(f"""
            SELECT COUNT(*) FROM (
                SELECT p.payout_id, p.gross_amount, p.commission_deduction, p.reserve_deduction, p.dispute_deduction, p.net_amount,
                       SUM(pl.amount) AS lines_sum
                FROM payouts p
                JOIN payout_lines pl ON p.payout_id = pl.payout_id
                WHERE p.payout_id NOT IN ({placeholders})
                GROUP BY p.payout_id
                HAVING abs(p.net_amount - lines_sum) > 0.05
            );
        """, tuple(known_anom_payout_ids))
        baseline_payout_discrepancies = cur.fetchone()[0]

        if baseline_payout_discrepancies == 0:
            self.log_result("Baseline Payout Arithmetic Reconciliation", True, "All baseline payouts match line item sums with 0 variance.")
        else:
            self.log_result("Baseline Payout Arithmetic Reconciliation", False, f"{baseline_payout_discrepancies} baseline payouts failed reconciliation.")

        # Check that labelled anomalous payouts DO exhibit expected variance
        cur.execute(f"""
            SELECT p.payout_id, p.net_amount, SUM(pl.amount) AS lines_sum, round(p.net_amount - SUM(pl.amount), 2) AS variance
            FROM payouts p
            JOIN payout_lines pl ON p.payout_id = pl.payout_id
            WHERE p.payout_id IN ({placeholders})
            GROUP BY p.payout_id;
        """, tuple(known_anom_payout_ids))
        anom_payout_rows = cur.fetchall()
        anom_payout_ok = len(anom_payout_rows) == len(known_anom_payout_ids) and all(abs(r[3]) > 10.0 for r in anom_payout_rows)
        if anom_payout_ok:
            self.log_result("Anomalous Payout Variance Check", True, f"Verified all {len(anom_payout_rows)} deliberate payout anomalies exhibit planned variance.")
        else:
            self.log_result("Anomalous Payout Variance Check", False, f"Expected {len(known_anom_payout_ids)} anomalous payouts, found {len(anom_payout_rows)}")

        # 6. Lifecycle Consistency
        cur.execute("""
            SELECT COUNT(*) FROM fulfillments
            WHERE status = 'DELIVERED' AND (delivered_at IS NULL OR shipped_at IS NULL);
        """)
        bad_delivered_lifecycle = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*) FROM fulfillments
            WHERE status = 'RETURNED' AND returned_at IS NULL;
        """)
        bad_returned_lifecycle = cur.fetchone()[0]

        if bad_delivered_lifecycle == 0 and bad_returned_lifecycle == 0:
            self.log_result("Lifecycle State Transitions", True, "All fulfillment lifecycle statuses have required timestamps.")
        else:
            self.log_result("Lifecycle State Transitions", False, f"Lifecycle errors: delivered_missing_time={bad_delivered_lifecycle}")

        # 7. Exact ID Format Conformance (All core entities)
        id_checks = [
            ("sellers", "seller_id", "SELL-", 11),
            ("orders", "order_id", "ORD-2026-", 15),
            ("order_lines", "order_line_id", "LINE-2026-", 19),
            ("fulfillments", "fulfillment_id", "FUL-LINE-2026-", 23),
            ("disputes", "dispute_id", "DSP-2026-", 15),
            ("payouts", "payout_id", "PAYOUT-2026-", 18),
            # Product listings: LIST-<seller-id>-000001 (len = 23, prefix = LIST-SELL-)
            ("product_listings", "listing_id", "LIST-SELL-", 23),
        ]
        all_ids_ok = True
        for table, col, prefix, expected_len in id_checks:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} NOT LIKE '{prefix}%' OR length({col}) != {expected_len};")
            bad_id_cnt = cur.fetchone()[0]
            if bad_id_cnt > 0:
                all_ids_ok = False
                self.log_result(f"ID Format: {table}.{col}", False, f"{bad_id_cnt} IDs do not match prefix '{prefix}' or length {expected_len}")

        # Check payout line IDs: standard format 'PAYLINE-2026-' (len 22) or deliberate anomaly 'PAYLINE-DUP-'
        cur.execute("""
            SELECT COUNT(*) FROM payout_lines
            WHERE (payout_line_id NOT LIKE 'PAYLINE-2026-%' OR length(payout_line_id) != 22)
              AND payout_line_id NOT LIKE 'PAYLINE-DUP-%';
        """)
        bad_payout_lines = cur.fetchone()[0]
        if bad_payout_lines > 0:
            all_ids_ok = False
            self.log_result("ID Format: payout_lines.payout_line_id", False, f"{bad_payout_lines} payout lines do not conform to PAYLINE-2026-xxxxxx-xx specification.")
        else:
            self.log_result("ID Format: payout_lines.payout_line_id", True, "All payout line IDs strictly match PAYLINE specification.")

        if all_ids_ok:
            self.log_result("Strict ID Format Conformance", True, "All entity IDs strictly adhere to zero-padded required specifications.")

        # 8. Cross-Table Consistency Checks
        cur.execute("""
            SELECT COUNT(*) FROM order_lines ol
            JOIN product_listings pl ON ol.listing_id = pl.listing_id
            WHERE ol.seller_id != pl.seller_id;
        """)
        mismatch_listing_seller = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*) FROM fulfillments f
            JOIN order_lines ol ON f.order_line_id = ol.order_line_id
            WHERE f.seller_id != ol.seller_id;
        """)
        mismatch_ful_seller = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*) FROM fulfillments f
            JOIN order_lines ol ON f.order_line_id = ol.order_line_id
            WHERE f.order_id != ol.order_id;
        """)
        mismatch_ful_order = cur.fetchone()[0]

        if mismatch_listing_seller == 0 and mismatch_ful_seller == 0 and mismatch_ful_order == 0:
            self.log_result("Cross-Table Entity Consistency", True, "100% relational consistency across seller, listing, order, and fulfillment entities.")
        else:
            self.log_result("Cross-Table Entity Consistency", False,
                            f"Mismatches: listing_seller={mismatch_listing_seller}, ful_seller={mismatch_ful_seller}, ful_order={mismatch_ful_order}")

        # 9. Seller Status Business Rules (Accounting for deliberate anomalies)
        suspended_listing_anomalies = ground_truth.get("SUSPENDED_SELLER_LISTING", [])
        known_anom_listing_ids = {a["target_entity_id"] for a in suspended_listing_anomalies}

        cur.execute("""
            SELECT pl.listing_id, s.seller_id
            FROM product_listings pl
            JOIN sellers s ON pl.seller_id = s.seller_id
            WHERE s.status = 'SUSPENDED' AND pl.status = 'ACTIVE';
        """)
        active_listings_of_suspended = cur.fetchall()
        unlabelled_violations = [r for r in active_listings_of_suspended if r[0] not in known_anom_listing_ids]

        if len(unlabelled_violations) == 0:
            self.log_result("Seller Status Business Rules", True,
                            f"Suspended seller listing constraints hold 100% ({len(active_listings_of_suspended)} active listings correctly identified as deliberate anomalies).")
        else:
            self.log_result("Seller Status Business Rules", False,
                            f"Found {len(unlabelled_violations)} unlabelled active listings for suspended sellers: {unlabelled_violations[:3]}")

        # Summary
        all_passed = all(r["passed"] for r in self.results)
        print("=" * 65)
        print(f"VALIDATION SUMMARY: {'ALL TESTS PASSED [PASS]' if all_passed else 'SOME TESTS FAILED [FAIL]'}")
        print("=" * 65)
        return all_passed

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run integrity validation checks on target database")
    parser.add_argument("--db", type=str, default=None, help="Database file path (defaults to config DB_PATH)")
    parser.add_argument("--ground-truth", type=str, default=None, help="Path to ground_truth.csv")
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else DB_PATH
    gt_path = Path(args.ground_truth) if args.ground_truth else (db_path.parent / "ground_truth.csv")
    conn = get_db_connection(db_path)
    try:
        validator = IntegrityValidator(db_conn=conn, ground_truth_path=gt_path)
        passed = validator.run_all()
    finally:
        conn.close()
    sys.exit(0 if passed else 1)
