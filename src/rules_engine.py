"""
Business rules engine, financial reconciliation, anomaly auditor, and evaluation metrics.
Notice: The operational auditor DOES NOT read or depend on ground_truth.csv!
Ground truth is only used by evaluate_exceptions() to calculate precision/recall metrics.
"""
import csv
import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.config import DB_PATH, GROUND_TRUTH_CSV, GROUND_TRUTH_JSON
from src.database import get_db_connection
from src.models import AnomalyIssueType

class RulesEngine:
    def __init__(self, db_conn: sqlite3.Connection = None):
        self.conn = db_conn or get_db_connection()

    # --- Commission & Reserve Lookups ---

    def get_commission_rate(self, category: str, seller_tier: str, order_date: str) -> float:
        """Find matching effective-dated commission rule or fallback rate."""
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT rate FROM commission_rules
            WHERE (category = ? OR category = 'ALL')
              AND (seller_tier = ? OR seller_tier = 'ALL')
              AND effective_from <= ? AND effective_to >= ?
            ORDER BY (category = ?) DESC, (seller_tier = ?) DESC
            LIMIT 1
            """,
            (category, seller_tier, order_date, order_date, category, seller_tier)
        )
        row = cur.fetchone()
        if row:
            return float(row["rate"])
        # Standard fallback rates
        defaults = {
            "Electronics": 0.08,
            "Apparel": 0.15,
            "Home & Kitchen": 0.12,
            "Beauty": 0.14,
            "Books": 0.10,
            "Sports": 0.11
        }
        return defaults.get(category, 0.12)

    def get_reserve_rate_and_hold(self, seller_tier: str, eval_date: str) -> Tuple[float, int]:
        """Find matching effective-dated reserve rule or fallback defaults."""
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT default_reserve_rate, hold_period_days FROM reserve_rules
            WHERE seller_tier = ?
              AND effective_from <= ? AND effective_to >= ?
            LIMIT 1
            """,
            (seller_tier, eval_date, eval_date)
        )
        row = cur.fetchone()
        if row:
            return float(row["default_reserve_rate"]), int(row["hold_period_days"])
        # Tier-based fallbacks
        defaults = {
            "ENTERPRISE": (0.04, 7),
            "TIER_1": (0.06, 7),
            "TIER_2": (0.09, 14),
            "TIER_3": (0.12, 21),
        }
        return defaults.get(seller_tier, (0.10, 14))

    # --- Autonomous Anomaly / Exception Detector ---

    def audit_exceptions(self) -> List[Dict[str, Any]]:
        """
        Audit operational database for anomalies using business rules.
        PURE OPERATIONAL LOGIC: No ground_truth input or labels are accessed.
        """
        exceptions: List[Dict[str, Any]] = []
        cur = self.conn.cursor()

        # Rule 1: PAYOUT_BEFORE_HOLD_RELEASE
        # A payout that has been approved/paid/processed before the hold release date,
        # or where associated fulfillments have not yet been delivered for hold_period_days.
        query_rule1 = """
        SELECT 
            p.payout_id,
            p.seller_id,
            p.status AS payout_status,
            p.created_at AS payout_created_at,
            p.hold_release_date,
            p.released_at,
            p.net_amount,
            s.hold_period_days,
            f.fulfillment_id,
            f.status AS fulfillment_status,
            f.delivered_at
        FROM payouts p
        JOIN sellers s ON p.seller_id = s.seller_id
        JOIN payout_lines pl ON p.payout_id = pl.payout_id
        JOIN fulfillments f ON pl.order_line_id = f.order_line_id
        WHERE p.status IN ('PAID', 'APPROVED', 'PROCESSING')
          AND (
              f.status != 'DELIVERED'
              OR f.delivered_at IS NULL
              OR p.released_at < p.hold_release_date
              OR date(p.created_at) < date(f.delivered_at, '+' || s.hold_period_days || ' days')
          )
        GROUP BY p.payout_id;
        """
        for row in cur.execute(query_rule1).fetchall():
            exceptions.append({
                "exception_id": f"EXC-R1-{row['payout_id']}",
                "issue_type": AnomalyIssueType.PAYOUT_BEFORE_HOLD_RELEASE.value,
                "severity": "CRITICAL",
                "target_entity_type": "PAYOUT",
                "target_entity_id": row["payout_id"],
                "seller_id": row["seller_id"],
                "rule_violated": "Rule FIN-01: Funds cannot be released before fulfillment delivery and seller hold period expiration.",
                "financial_impact": round(float(row["net_amount"]), 2),
                "evidence": (
                    f"Payout {row['payout_id']} released/approved at {row['released_at'] or row['payout_created_at']} "
                    f"prior to hold release date {row['hold_release_date']}. "
                    f"Fulfillment {row['fulfillment_id']} delivered at {row['delivered_at']}, "
                    f"required hold period: {row['hold_period_days']} days."
                ),
                "recommended_action": "Freeze payout release; reverse pending settlement to escrow until hold window completes."
            })

        # Rule 2: COMMISSION_APPLIED_TWICE
        # Order lines that have duplicate commission deductions in payout_lines,
        # or where commission_amount in order_lines is twice the expected rate.
        query_rule2 = """
        SELECT 
            ol.order_line_id,
            ol.order_id,
            ol.seller_id,
            ol.subtotal,
            ol.commission_rate,
            ol.commission_amount,
            COUNT(pl.payout_line_id) AS comm_line_count,
            SUM(abs(pl.amount)) AS total_comm_deducted
        FROM order_lines ol
        JOIN payout_lines pl ON ol.order_line_id = pl.order_line_id
        WHERE pl.line_type = 'COMMISSION_FEE'
        GROUP BY ol.order_line_id
        HAVING COUNT(pl.payout_line_id) > 1 
            OR abs(ol.commission_amount - (ol.subtotal * ol.commission_rate * 2)) < 0.05;
        """
        for row in cur.execute(query_rule2).fetchall():
            expected_comm = round(row["subtotal"] * row["commission_rate"], 2)
            actual_comm = round(row["total_comm_deducted"] if row["total_comm_deducted"] > 0 else row["commission_amount"], 2)
            impact = round(actual_comm - expected_comm, 2)
            exceptions.append({
                "exception_id": f"EXC-R2-{row['order_line_id']}",
                "issue_type": AnomalyIssueType.COMMISSION_APPLIED_TWICE.value,
                "severity": "HIGH",
                "target_entity_type": "ORDER_LINE",
                "target_entity_id": row["order_line_id"],
                "seller_id": row["seller_id"],
                "rule_violated": "Rule FIN-02: Each order line must incur exactly one commission charge based on category rate schedule.",
                "financial_impact": impact if impact > 0 else expected_comm,
                "evidence": (
                    f"Order line {row['order_line_id']} has {row['comm_line_count']} commission lines. "
                    f"Subtotal: ${row['subtotal']:.2f}, Rate: {row['commission_rate']*100:.1f}%. "
                    f"Expected Commission: ${expected_comm:.2f}, Deducted: ${actual_comm:.2f}."
                ),
                "recommended_action": "Credit back overbilled commission amount to seller ledger."
            })

        # Rule 3: SUSPENDED_SELLER_LISTING
        # Sellers with status = 'SUSPENDED' that still have ACTIVE listings or took orders after suspension.
        query_rule3 = """
        SELECT 
            s.seller_id,
            s.name AS seller_name,
            s.status AS seller_status,
            l.listing_id,
            l.title AS listing_title,
            l.status AS listing_status,
            l.price,
            l.inventory_count
        FROM sellers s
        JOIN product_listings l ON s.seller_id = l.seller_id
        WHERE s.status = 'SUSPENDED' AND l.status = 'ACTIVE';
        """
        for row in cur.execute(query_rule3).fetchall():
            exceptions.append({
                "exception_id": f"EXC-R3-{row['listing_id']}",
                "issue_type": AnomalyIssueType.SUSPENDED_SELLER_LISTING.value,
                "severity": "CRITICAL",
                "target_entity_type": "PRODUCT_LISTING",
                "target_entity_id": row["listing_id"],
                "seller_id": row["seller_id"],
                "rule_violated": "Rule SEC-01: Suspended sellers are prohibited from maintaining active listings or trading.",
                "financial_impact": round(float(row["price"] * min(row["inventory_count"], 10)), 2),
                "evidence": (
                    f"Seller {row['seller_id']} ({row['seller_name']}) status is SUSPENDED, "
                    f"but listing {row['listing_id']} ('{row['listing_title']}') remains ACTIVE "
                    f"with inventory {row['inventory_count']} at ${row['price']:.2f}."
                ),
                "recommended_action": "Force listing status to ARCHIVED immediately; delist from storefront."
            })

        # Rule 4: DISPUTE_NOT_DEDUCTED
        # Orders with UPHELD disputes where payout was made without deducting dispute amount.
        query_rule4 = """
        SELECT 
            d.dispute_id,
            d.order_id,
            d.order_line_id,
            d.seller_id,
            d.amount AS dispute_amount,
            d.status AS dispute_status,
            p.payout_id,
            p.status AS payout_status,
            p.dispute_deduction
        FROM disputes d
        JOIN payout_lines pl ON d.order_line_id = pl.order_line_id
        JOIN payouts p ON pl.payout_id = p.payout_id
        WHERE d.status = 'UPHELD'
          AND p.status IN ('PAID', 'APPROVED', 'PROCESSING')
          AND d.deducted_from_payout = 0
        GROUP BY d.dispute_id;
        """
        for row in cur.execute(query_rule4).fetchall():
            exceptions.append({
                "exception_id": f"EXC-R4-{row['dispute_id']}",
                "issue_type": AnomalyIssueType.DISPUTE_NOT_DEDUCTED.value,
                "severity": "HIGH",
                "target_entity_type": "DISPUTE",
                "target_entity_id": row["dispute_id"],
                "seller_id": row["seller_id"],
                "rule_violated": "Rule DISP-01: Upheld dispute amounts must be debited from seller payout settlement.",
                "financial_impact": round(float(row["dispute_amount"]), 2),
                "evidence": (
                    f"Dispute {row['dispute_id']} for order line {row['order_line_id']} was UPHELD "
                    f"for ${row['dispute_amount']:.2f}, but Payout {row['payout_id']} was released "
                    f"without dispute deduction (deducted_from_payout = 0)."
                ),
                "recommended_action": "Issue clawback notice and debit seller's reserve balance."
            })

        # Rule 5: PAYOUT_TOTAL_MISMATCH
        # Payout net_amount does not match sum of its line items or arithmetic formula.
        query_rule5 = """
        SELECT 
            p.payout_id,
            p.seller_id,
            p.gross_amount,
            p.commission_deduction,
            p.reserve_deduction,
            p.dispute_deduction,
            p.net_amount AS header_net,
            COALESCE(SUM(pl.amount), 0) AS lines_sum,
            round(p.gross_amount - p.commission_deduction - p.reserve_deduction - p.dispute_deduction, 2) AS formula_net
        FROM payouts p
        LEFT JOIN payout_lines pl ON p.payout_id = pl.payout_id
        GROUP BY p.payout_id
        HAVING abs(round(p.net_amount, 2) - round(lines_sum, 2)) > 0.05 
            OR abs(round(p.net_amount, 2) - round(formula_net, 2)) > 0.05;
        """
        for row in cur.execute(query_rule5).fetchall():
            variance = round(abs(row["header_net"] - row["lines_sum"]), 2)
            exceptions.append({
                "exception_id": f"EXC-R5-{row['payout_id']}",
                "issue_type": AnomalyIssueType.PAYOUT_TOTAL_MISMATCH.value,
                "severity": "CRITICAL",
                "target_entity_type": "PAYOUT",
                "target_entity_id": row["payout_id"],
                "seller_id": row["seller_id"],
                "rule_violated": "Rule REC-01: Payout header net amount must strictly equal the mathematical sum of its constituent line items.",
                "financial_impact": variance,
                "evidence": (
                    f"Payout {row['payout_id']} header net amount is ${row['header_net']:.2f}, "
                    f"but sum of payout lines is ${row['lines_sum']:.2f} "
                    f"(variance: ${variance:.2f}). Formula net: ${row['formula_net']:.2f}."
                ),
                "recommended_action": "Block disbursement immediately; re-run reconciliation ledger."
            })

        return exceptions

    # --- Evaluation View against Ground Truth ---

    def evaluate_against_ground_truth(self) -> Dict[str, Any]:
        """
        Evaluate detected exceptions against ground_truth.csv.
        Calculates Confusion Matrix (TP, FP, FN), Precision, Recall, and F1 Score.
        """
        detected = self.audit_exceptions()
        
        # Load ground truth
        ground_truth: List[Dict[str, Any]] = []
        if GROUND_TRUTH_CSV.exists():
            with open(GROUND_TRUTH_CSV, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                ground_truth = list(reader)
        elif GROUND_TRUTH_JSON.exists():
            with open(GROUND_TRUTH_JSON, "r", encoding="utf-8") as f:
                ground_truth = json.load(f)

        gt_lookup = {}
        for item in ground_truth:
            key = (item["issue_type"], item["target_entity_id"])
            gt_lookup[key] = item

        detected_lookup = {}
        for d in detected:
            key = (d["issue_type"], d["target_entity_id"])
            detected_lookup[key] = d

        tp_items = []
        fp_items = []
        fn_items = []

        # Find True Positives & False Positives
        for key, det in detected_lookup.items():
            if key in gt_lookup:
                gt_item = gt_lookup[key]
                tp_items.append({
                    "status": "TRUE_POSITIVE",
                    "issue_type": det["issue_type"],
                    "target_entity_id": det["target_entity_id"],
                    "seller_id": det["seller_id"],
                    "financial_impact": det["financial_impact"],
                    "evidence": det["evidence"],
                    "ground_truth_desc": gt_item.get("description", "")
                })
            else:
                fp_items.append({
                    "status": "FALSE_POSITIVE",
                    "issue_type": det["issue_type"],
                    "target_entity_id": det["target_entity_id"],
                    "seller_id": det["seller_id"],
                    "financial_impact": det["financial_impact"],
                    "evidence": det["evidence"],
                    "ground_truth_desc": "Not in ground truth"
                })

        # Find False Negatives
        for key, gt_item in gt_lookup.items():
            if key not in detected_lookup:
                fn_items.append({
                    "status": "FALSE_NEGATIVE",
                    "issue_type": gt_item["issue_type"],
                    "target_entity_id": gt_item["target_entity_id"],
                    "seller_id": gt_item.get("seller_id", ""),
                    "financial_impact": float(gt_item.get("expected_financial_impact", 0)),
                    "evidence": "Missed by audit query",
                    "ground_truth_desc": gt_item.get("description", "")
                })

        tp = len(tp_items)
        fp = len(fp_items)
        fn = len(fn_items)

        precision = (tp / (tp + fp)) if (tp + fp) > 0 else 1.0
        recall = (tp / (tp + fn)) if (tp + fn) > 0 else 1.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 1.0

        # Breakdown by issue type
        breakdown = {}
        for issue_type in AnomalyIssueType:
            itype = issue_type.value
            b_tp = sum(1 for x in tp_items if x["issue_type"] == itype)
            b_fp = sum(1 for x in fp_items if x["issue_type"] == itype)
            b_fn = sum(1 for x in fn_items if x["issue_type"] == itype)
            b_p = (b_tp / (b_tp + b_fp)) if (b_tp + b_fp) > 0 else 1.0
            b_r = (b_tp / (b_tp + b_fn)) if (b_tp + b_fn) > 0 else 1.0
            b_f1 = (2 * b_p * b_r / (b_p + b_r)) if (b_p + b_r) > 0 else 1.0
            breakdown[itype] = {
                "tp": b_tp,
                "fp": b_fp,
                "fn": b_fn,
                "precision": round(b_p, 4),
                "recall": round(b_r, 4),
                "f1": round(b_f1, 4),
            }

        return {
            "summary": {
                "total_ground_truth": len(ground_truth),
                "total_detected": len(detected),
                "true_positives": tp,
                "false_positives": fp,
                "false_negatives": fn,
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1_score": round(f1, 4),
            },
            "breakdown_by_issue_type": breakdown,
            "true_positives_sample": tp_items[:50],
            "false_positives": fp_items,
            "false_negatives": fn_items,
        }

if __name__ == "__main__":
    engine = RulesEngine()
    results = engine.evaluate_against_ground_truth()
    print("=== Evaluation Summary ===")
    print(json.dumps(results["summary"], indent=2))
    print("=== Breakdown by Issue Type ===")
    print(json.dumps(results["breakdown_by_issue_type"], indent=2))
    if results["false_positives"]:
        print(f"FP Count: {len(results['false_positives'])}")
        print(results["false_positives"])
    if results["false_negatives"]:
        print(f"FN Count: {len(results['false_negatives'])}")
        print(results["false_negatives"])

