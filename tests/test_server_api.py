"""
Live HTTP integration tests for SellerOps REST API server and business rules.
Tests run against a temporary copy of the database on an ephemeral loopback socket.
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

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

from src.config import DB_PATH, STATIC_DIR
from src.server import SellerOpsAPIHandler
from src.rules_engine import RulesEngine
from src.exporter import Exporter

class TestServerAPIIntegration(unittest.TestCase):
    server = None
    server_thread = None
    base_url = ""
    temp_dir = None
    temp_db = None

    @classmethod
    def setUpClass(cls):
        # 1. Create a fresh temporary copy of the active database for isolated testing
        cls.temp_dir = tempfile.TemporaryDirectory()
        temp_dir_path = Path(cls.temp_dir.name)
        cls.temp_db = temp_dir_path / "temp_sellerops_test.db"

        # Copy existing db to temp path
        if DB_PATH.exists():
            shutil.copy2(DB_PATH, cls.temp_db)
        else:
            raise FileNotFoundError(f"Source database not found at {DB_PATH}")

        # Also copy ground truth if present
        source_gt = DB_PATH.parent / "ground_truth.csv"
        if source_gt.exists():
            shutil.copy2(source_gt, temp_dir_path / "ground_truth.csv")

        # 2. Configure handler to use the temporary database
        SellerOpsAPIHandler.db_path = cls.temp_db

        # 3. Spin up an ephemeral HTTP server on 127.0.0.1:0 (OS allocates available port)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), SellerOpsAPIHandler)
        port = cls.server.server_port
        cls.base_url = f"http://127.0.0.1:{port}"

        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        # 1. Shut down the HTTP server
        if cls.server:
            cls.server.shutdown()
            cls.server.server_close()

        # 2. Reset handler db_path
        SellerOpsAPIHandler.db_path = None

        # 3. Clean up temporary directory
        if cls.temp_dir:
            try:
                cls.temp_dir.cleanup()
            except Exception:
                pass

    def _http_get(self, path: str):
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req) as resp:
                status = resp.status
                body = resp.read().decode("utf-8")
                return status, json.loads(body) if "json" in resp.headers.get("Content-Type", "") else body
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            try:
                parsed_body = json.loads(body)
            except Exception:
                parsed_body = body
            return e.code, parsed_body

    def _http_post(self, path: str, payload: dict):
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as resp:
                status = resp.status
                body = resp.read().decode("utf-8")
                return status, json.loads(body) if "json" in resp.headers.get("Content-Type", "") else body
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            try:
                parsed_body = json.loads(body)
            except Exception:
                parsed_body = body
            return e.code, parsed_body

    def test_01_health_check(self):
        status, data = self._http_get("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["database"], "connected")
        self.assertIn("temp_sellerops_test.db", data["db_path"])

    def test_02_summary_kpis(self):
        status, data = self._http_get("/api/summary")
        self.assertEqual(status, 200)
        self.assertIn("orders", data)
        self.assertIn("financials", data)
        self.assertIn("sla", data)
        self.assertIn("exceptions", data)
        self.assertGreater(data["orders"]["gmv"], 0)
        self.assertGreater(data["orders"]["total"], 0)

    def test_03_paginated_sellers(self):
        status, data = self._http_get("/api/sellers?page=1&limit=5")
        self.assertEqual(status, 200)
        self.assertIn("items", data)
        self.assertIn("total", data)
        self.assertIn("total_pages", data)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["limit"], 5)
        self.assertLessEqual(len(data["items"]), 5)
        self.assertGreater(data["total"], 0)

    def test_04_paginated_fulfillments(self):
        status, data = self._http_get("/api/fulfillments?page=1&limit=10")
        self.assertEqual(status, 200)
        self.assertIn("items", data)
        self.assertIn("total", data)
        self.assertIn("total_pages", data)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["limit"], 10)
        self.assertLessEqual(len(data["items"]), 10)
        self.assertGreater(data["total"], 0)

    def test_05_paginated_payouts(self):
        status, data = self._http_get("/api/payouts?page=1&limit=5")
        self.assertEqual(status, 200)
        self.assertIn("items", data)
        self.assertIn("total", data)
        self.assertIn("total_pages", data)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["limit"], 5)
        self.assertLessEqual(len(data["items"]), 5)
        self.assertGreater(data["total"], 0)

    def test_06_paginated_events(self):
        status, data = self._http_get("/api/events?page=1&limit=10")
        self.assertEqual(status, 200)
        self.assertIn("items", data)
        self.assertIn("total", data)
        self.assertIn("total_pages", data)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["limit"], 10)
        self.assertLessEqual(len(data["items"]), 10)
        self.assertGreater(data["total"], 0)

    def test_07_fulfillment_status_update_action(self):
        # Query an allocated fulfillment in temp db
        conn = sqlite3.connect(str(self.temp_db))
        cur = conn.cursor()
        cur.execute("SELECT fulfillment_id FROM fulfillments WHERE status = 'ALLOCATED' LIMIT 1;")
        row = cur.fetchone()
        conn.close()

        if row:
            ful_id = row[0]
            status, res = self._http_post(f"/api/fulfillments/{ful_id}/update-status", {
                "status": "PICKED",
                "actor": "WAREHOUSE_OPERATOR"
            })
            self.assertEqual(status, 200)
            self.assertTrue(res.get("success"))
            self.assertEqual(res.get("new_status"), "PICKED")

            # Verify in DB and verify event log entry
            conn = sqlite3.connect(str(self.temp_db))
            cur = conn.cursor()
            cur.execute("SELECT status FROM fulfillments WHERE fulfillment_id = ?", (ful_id,))
            updated_status = cur.fetchone()[0]
            self.assertEqual(updated_status, "PICKED")

            cur.execute("SELECT event_type, actor FROM event_logs WHERE entity_id = ? ORDER BY event_id DESC LIMIT 1", (ful_id,))
            evt = cur.fetchone()
            self.assertEqual(evt[0], "FULFILLMENT_STATUS_UPDATE")
            self.assertEqual(evt[1], "WAREHOUSE_OPERATOR")
            conn.close()

    def test_08_dispute_resolution_with_financial_deduction(self):
        # Query an open dispute (excluding the 3 labelled anomaly disputes)
        conn = sqlite3.connect(str(self.temp_db))
        cur = conn.cursor()
        cur.execute("""
            SELECT dispute_id, seller_id, amount FROM disputes
            WHERE status = 'OPEN' AND dispute_id NOT IN ('DSP-2026-000001', 'DSP-2026-000002', 'DSP-2026-000003')
            LIMIT 1;
        """)
        row = cur.fetchone()
        conn.close()

        if row:
            dispute_id, seller_id, dispute_amt = row[0], row[1], row[2]
            status, res = self._http_post(f"/api/disputes/{dispute_id}/resolve", {
                "status": "UPHELD",
                "resolution_notes": "Upheld by Dispute Agent: Item arrived defective.",
                "actor": "DISPUTE_AGENT"
            })
            self.assertEqual(status, 200)
            self.assertTrue(res.get("success"))
            self.assertEqual(res.get("deducted_from_payout"), 1)
            self.assertIn("financial_action", res)

            # Verify database state
            conn = sqlite3.connect(str(self.temp_db))
            cur = conn.cursor()
            cur.execute("SELECT status, deducted_from_payout FROM disputes WHERE dispute_id = ?", (dispute_id,))
            disp_row = cur.fetchone()
            self.assertEqual(disp_row[0], "UPHELD")
            self.assertEqual(disp_row[1], 1)

            # Verify audit trail event log
            cur.execute("SELECT event_type, new_state, payload_json FROM event_logs WHERE entity_id = ? ORDER BY event_id DESC LIMIT 1", (dispute_id,))
            evt = cur.fetchone()
            self.assertEqual(evt[0], "FINANCIAL_DEDUCTION_RECORDED")
            self.assertEqual(evt[1], "UPHELD")
            self.assertTrue("clawback" in evt[2] or "deduction" in evt[2])
            conn.close()

    def test_09_payout_approval_blocked_before_delivery_and_hold_release(self):
        # Select an ordinary unreleased payout (excluding labelled anomalies)
        conn = sqlite3.connect(str(self.temp_db))
        cur = conn.cursor()
        excluded_pids = (
            "PAYOUT-2026-000001", "PAYOUT-2026-000002", "PAYOUT-2026-000003",
            "PAYOUT-2026-000026", "PAYOUT-2026-000027", "PAYOUT-2026-000028"
        )
        placeholders = ",".join("?" for _ in excluded_pids)
        cur.execute(f"""
            SELECT payout_id, hold_release_date FROM payouts
            WHERE payout_id NOT IN ({placeholders})
            LIMIT 1;
        """, excluded_pids)
        row = cur.fetchone()
        payout_id = row[0]
        # Set status to PENDING_APPROVAL and future hold release date to test rule enforcement
        cur.execute("UPDATE payouts SET status = 'PENDING_APPROVAL', hold_release_date = '2026-12-31' WHERE payout_id = ?", (payout_id,))
        conn.commit()
        conn.close()

        # Attempt to APPROVE the payout via API
        status, res = self._http_post(f"/api/payouts/{payout_id}/action", {
            "action": "APPROVE",
            "actor": "OPS_MANAGER"
        })

        # MUST return HTTP 400 Bad Request and detail Rule FIN-01 violation
        self.assertEqual(status, 400)
        self.assertFalse(res.get("success", True))
        self.assertIn("FIN-01", res.get("rule", ""))
        self.assertIn("violations", res)
        self.assertGreater(len(res["violations"]), 0)

        # Verify an APPROVAL_BLOCKED event was recorded in event history
        conn = sqlite3.connect(str(self.temp_db))
        cur = conn.cursor()
        cur.execute("SELECT event_type FROM event_logs WHERE entity_id = ? AND event_type = 'APPROVAL_BLOCKED'", (payout_id,))
        blocked_evt = cur.fetchone()
        self.assertIsNotNone(blocked_evt)
        conn.close()

    def test_10_rules_engine_and_evaluation(self):
        status, eval_data = self._http_get("/api/evaluation")
        self.assertEqual(status, 200)
        summary = eval_data["summary"]
        self.assertEqual(summary["precision"], 1.0)
        self.assertEqual(summary["recall"], 1.0)
        self.assertEqual(summary["f1_score"], 1.0)
        self.assertEqual(summary["true_positives"], 15)
        self.assertEqual(summary["false_positives"], 0)
        self.assertEqual(summary["false_negatives"], 0)

    def test_11_static_dashboard_pages(self):
        status, body = self._http_get("/")
        self.assertEqual(status, 200)
        self.assertIn("SellerOps Control Tower", body)
        self.assertIn("warehousePagination", body)
        self.assertIn("sellerPagination", body)
        self.assertIn("payoutPagination", body)
        self.assertIn("eventPagination", body)

        status, _ = self._http_get("/styles.css")
        self.assertEqual(status, 200)

        status, _ = self._http_get("/app.js")
        self.assertEqual(status, 200)

if __name__ == "__main__":
    unittest.main()
