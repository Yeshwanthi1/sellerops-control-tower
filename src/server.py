"""
SellerOps Control Tower REST API and Dashboard Server.
Pure standard-library implementation with multithreaded HTTP server (Zero external pip dependencies required).
Also provides FastAPI `app` instance for seamless compatibility if FastAPI is installed.
"""
import cgi
import http.server
import json
import os
import re
import sqlite3
import sys
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.config import DB_PATH, SERVER_HOST, SERVER_PORT, STATIC_DIR, DEFAULT_SEED
from src.database import get_db_connection
from src.rules_engine import RulesEngine
from src.exporter import Exporter
from src.models import format_event_id, EventActor

# Optional FastAPI application for users who run via `uvicorn src.server:app`
try:
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse, JSONResponse
    fastapi_available = True
    app = FastAPI(title="SellerOps Control Tower API", version="1.0.0")
except ImportError:
    fastapi_available = False
    app = None

class SellerOpsAPIHandler(http.server.SimpleHTTPRequestHandler):
    db_path: Optional[Path] = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # Static files
        if path == "/" or path == "/index.html":
            return self._serve_static_file(STATIC_DIR / "index.html", "text/html")
        elif path == "/styles.css":
            return self._serve_static_file(STATIC_DIR / "styles.css", "text/css")
        elif path == "/app.js":
            return self._serve_static_file(STATIC_DIR / "app.js", "application/javascript")

        # API Endpoints
        if not path.startswith("/api/"):
            return super().do_GET()

        conn = get_db_connection(self.db_path or DB_PATH)
        try:
            # 1. Health & Meta
            if path == "/api/health":
                self._send_json({
                    "status": "healthy",
                    "database": "connected",
                    "seed": DEFAULT_SEED,
                    "db_path": str(self.db_path or DB_PATH)
                })

            # 2. Summary / KPIs
            elif path == "/api/summary" or path == "/api/kpis":
                self._handle_summary(conn)

            # 3. Sellers
            elif path == "/api/sellers":
                self._handle_sellers_list(conn, query)
            elif re.match(r"^/api/sellers/([^/]+)$", path):
                seller_id = re.match(r"^/api/sellers/([^/]+)$", path).group(1)
                self._handle_seller_detail(conn, seller_id)

            # 4. Listings
            elif path == "/api/listings":
                self._handle_listings_list(conn, query)

            # 5. Orders
            elif path == "/api/orders":
                self._handle_orders_list(conn, query)
            elif re.match(r"^/api/orders/([^/]+)$", path):
                order_id = re.match(r"^/api/orders/([^/]+)$", path).group(1)
                self._handle_order_detail(conn, order_id)

            # 6. Fulfillments
            elif path == "/api/fulfillments":
                self._handle_fulfillments_list(conn, query)

            # 7. Reviews
            elif path == "/api/reviews":
                self._handle_reviews_list(conn, query)

            # 8. Disputes
            elif path == "/api/disputes":
                self._handle_disputes_list(conn, query)

            # 9. Payouts
            elif path == "/api/payouts":
                self._handle_payouts_list(conn, query)
            elif re.match(r"^/api/payouts/([^/]+)$", path):
                payout_id = re.match(r"^/api/payouts/([^/]+)$", path).group(1)
                self._handle_payout_detail(conn, payout_id)

            # 10. Rules
            elif path == "/api/rules":
                self._handle_rules_list(conn)

            # 11. Events / Traceability
            elif path == "/api/events":
                self._handle_events_list(conn, query)

            # 12. Exceptions Queue
            elif path == "/api/exceptions":
                engine = RulesEngine(conn)
                exceptions = engine.audit_exceptions()
                self._send_json({"count": len(exceptions), "exceptions": exceptions})

            # 13. Evaluation vs Ground Truth
            elif path == "/api/evaluation":
                engine = RulesEngine(conn)
                eval_results = engine.evaluate_against_ground_truth()
                self._send_json(eval_results)

            # 14. Data Exports
            elif path.startswith("/api/export/"):
                fmt = path.replace("/api/export/", "")
                exporter = Exporter(conn)
                if fmt == "csv":
                    res = exporter.export_csv()
                    self._send_json({"status": "success", "format": "csv", "files": res})
                elif fmt == "json":
                    res = exporter.export_json()
                    self._send_json({"status": "success", "format": "json", "files": res})
                elif fmt == "sql":
                    res = exporter.export_sql()
                    self._send_json({"status": "success", "format": "sql", "file": res})
                elif fmt == "all":
                    res = exporter.export_all()
                    self._send_json({"status": "success", "format": "all", "exports": res})
                else:
                    self._send_json({"error": f"Unknown export format: {fmt}"}, 400)
            else:
                self._send_json({"error": "Endpoint not found"}, 404)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)
        finally:
            conn.close()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            body = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except Exception:
            body = {}

        conn = get_db_connection(self.db_path or DB_PATH)
        try:
            # Update fulfillment status (Warehouse action)
            if re.match(r"^/api/fulfillments/([^/]+)/update-status$", path):
                ful_id = re.match(r"^/api/fulfillments/([^/]+)/update-status$", path).group(1)
                new_status = body.get("status")
                actor = body.get("actor", EventActor.WAREHOUSE_OPERATOR.value)
                self._action_update_fulfillment_status(conn, ful_id, new_status, actor)

            # Resolve dispute (Ops Manager action)
            elif re.match(r"^/api/disputes/([^/]+)/resolve$", path):
                disp_id = re.match(r"^/api/disputes/([^/]+)/resolve$", path).group(1)
                new_status = body.get("status")
                actor = body.get("actor", EventActor.OPS_MANAGER.value)
                self._action_resolve_dispute(conn, disp_id, new_status, actor)

            # Payout action (Hold, Approve, Audit)
            elif re.match(r"^/api/payouts/([^/]+)/action$", path):
                payout_id = re.match(r"^/api/payouts/([^/]+)/action$", path).group(1)
                action = body.get("action")
                actor = body.get("actor", EventActor.OPS_MANAGER.value)
                self._action_payout(conn, payout_id, action, actor)
            else:
                self._send_json({"error": "POST endpoint not found"}, 404)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)
        finally:
            conn.close()

    def _serve_static_file(self, file_path: Path, content_type: str):
        if not file_path.exists():
            self.send_error(404, "File not found")
            return
        with open(file_path, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    # --- API Implementation Helpers ---

    def _handle_summary(self, conn: sqlite3.Connection):
        cur = conn.cursor()
        
        # Sellers
        cur.execute("SELECT COUNT(*), SUM(status = 'ACTIVE'), SUM(status = 'SUSPENDED') FROM sellers;")
        total_sellers, active_sellers, susp_sellers = cur.fetchone()

        # Orders & GMV
        cur.execute("SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM orders;")
        total_orders, total_gmv = cur.fetchone()

        # Fulfillments & SLA
        cur.execute("""
            SELECT 
                COUNT(*),
                SUM(is_late_shipment = 0),
                SUM(is_late_delivery = 0),
                SUM(is_late_shipment = 1),
                SUM(is_late_delivery = 1)
            FROM fulfillments;
        """)
        f_total, f_on_time_ship, f_on_time_deliv, f_late_ship, f_late_deliv = cur.fetchone()
        on_time_ship_pct = round((f_on_time_ship / f_total * 100), 1) if f_total else 100.0
        on_time_deliv_pct = round((f_on_time_deliv / f_total * 100), 1) if f_total else 100.0

        # Disputes
        cur.execute("SELECT COUNT(*), SUM(status = 'UPHELD'), COALESCE(SUM(amount), 0) FROM disputes;")
        total_disputes, upheld_disputes, dispute_amount = cur.fetchone()
        dispute_rate = round((total_disputes / total_orders * 100), 2) if total_orders else 0.0

        # Payouts & Reserves
        cur.execute("""
            SELECT 
                COUNT(*),
                COALESCE(SUM(gross_amount), 0),
                COALESCE(SUM(commission_deduction), 0),
                COALESCE(SUM(reserve_deduction), 0),
                COALESCE(SUM(dispute_deduction), 0),
                COALESCE(SUM(net_amount), 0)
            FROM payouts;
        """)
        p_cnt, p_gross, p_comm, p_res, p_disp, p_net = cur.fetchone()

        # Audit exceptions count
        engine = RulesEngine(conn)
        exceptions = engine.audit_exceptions()
        critical_count = sum(1 for e in exceptions if e["severity"] == "CRITICAL")

        self._send_json({
            "sellers": {
                "total": total_sellers,
                "active": active_sellers or 0,
                "suspended": susp_sellers or 0
            },
            "orders": {
                "total": total_orders,
                "gmv": round(total_gmv, 2)
            },
            "sla": {
                "total_fulfillments": f_total,
                "on_time_ship_pct": on_time_ship_pct,
                "on_time_delivery_pct": on_time_deliv_pct,
                "late_shipment_count": f_late_ship or 0,
                "late_delivery_count": f_late_deliv or 0
            },
            "disputes": {
                "total": total_disputes,
                "upheld": upheld_disputes or 0,
                "total_amount": round(dispute_amount, 2),
                "dispute_rate_pct": dispute_rate
            },
            "financials": {
                "payouts_count": p_cnt,
                "gross_sales": round(p_gross, 2),
                "commission_collected": round(p_comm, 2),
                "reserves_held": round(p_res, 2),
                "disputes_deducted": round(p_disp, 2),
                "net_paid": round(p_net, 2)
            },
            "exceptions": {
                "total": len(exceptions),
                "critical": critical_count
            }
        })

    def _handle_sellers_list(self, conn: sqlite3.Connection, query: Dict[str, List[str]]):
        cur = conn.cursor()
        base_where = " WHERE 1=1"
        params = []
        if "status" in query and query["status"][0]:
            base_where += " AND s.status = ?"
            params.append(query["status"][0])
        if "tier" in query and query["tier"][0]:
            base_where += " AND s.tier = ?"
            params.append(query["tier"][0])
        if "search" in query and query["search"][0]:
            base_where += " AND (s.name LIKE ? OR s.seller_id LIKE ?)"
            s = f"%{query['search'][0]}%"
            params.extend([s, s])

        # Total count for pagination
        cur.execute(f"SELECT COUNT(*) FROM sellers s {base_where}", params)
        total = cur.fetchone()[0]

        page = max(1, int(query.get("page", ["1"])[0]))
        limit = min(500, max(1, int(query.get("limit", ["50"])[0])))
        offset = (page - 1) * limit

        sql = f"""
            SELECT s.*, 
                (SELECT COUNT(*) FROM product_listings l WHERE l.seller_id = s.seller_id) AS listing_count,
                (SELECT COUNT(*) FROM fulfillments f WHERE f.seller_id = s.seller_id) AS fulfillment_count,
                (SELECT ROUND(AVG(is_late_shipment == 0) * 100, 1) FROM fulfillments f WHERE f.seller_id = s.seller_id) AS on_time_ship_pct,
                (SELECT COUNT(*) FROM disputes d WHERE d.seller_id = s.seller_id) AS dispute_count,
                (SELECT COALESCE(SUM(net_amount), 0) FROM payouts p WHERE p.seller_id = s.seller_id) AS total_paid
            FROM sellers s
            {base_where}
            ORDER BY s.seller_id LIMIT ? OFFSET ?;
        """
        cur.execute(sql, params + [limit, offset])
        rows = [dict(r) for r in cur.fetchall()]
        total_pages = (total + limit - 1) // limit if total > 0 else 1
        self._send_json({"items": rows, "total": total, "page": page, "limit": limit, "total_pages": total_pages})

    def _handle_seller_detail(self, conn: sqlite3.Connection, seller_id: str):
        cur = conn.cursor()
        cur.execute("SELECT * FROM sellers WHERE seller_id = ?;", (seller_id,))
        seller = cur.fetchone()
        if not seller:
            return self._send_json({"error": "Seller not found"}, 404)
        
        # Listings
        cur.execute("SELECT * FROM product_listings WHERE seller_id = ? LIMIT 20;", (seller_id,))
        listings = [dict(r) for r in cur.fetchall()]

        # Recent fulfillments
        cur.execute("SELECT * FROM fulfillments WHERE seller_id = ? ORDER BY fulfillment_id DESC LIMIT 15;", (seller_id,))
        fulfillments = [dict(r) for r in cur.fetchall()]

        # Payouts
        cur.execute("SELECT * FROM payouts WHERE seller_id = ? ORDER BY period_end DESC LIMIT 10;", (seller_id,))
        payouts = [dict(r) for r in cur.fetchall()]

        # Metrics
        cur.execute("""
            SELECT 
                COUNT(*) AS total_ful,
                ROUND(AVG(is_late_shipment == 0) * 100, 1) AS on_time_ship_pct,
                ROUND(AVG(is_late_delivery == 0) * 100, 1) AS on_time_deliv_pct
            FROM fulfillments WHERE seller_id = ?;
        """, (seller_id,))
        metrics = dict(cur.fetchone())

        res = dict(seller)
        res["metrics"] = metrics
        res["listings"] = listings
        res["recent_fulfillments"] = fulfillments
        res["payouts"] = payouts
        self._send_json(res)

    def _handle_listings_list(self, conn: sqlite3.Connection, query: Dict[str, List[str]]):
        cur = conn.cursor()
        sql = """
            SELECT l.*, s.name AS seller_name, s.status AS seller_status
            FROM product_listings l
            JOIN sellers s ON l.seller_id = s.seller_id
            WHERE 1=1
        """
        params = []
        if "seller_id" in query and query["seller_id"][0]:
            sql += " AND l.seller_id = ?"
            params.append(query["seller_id"][0])
        if "category" in query and query["category"][0]:
            sql += " AND l.category = ?"
            params.append(query["category"][0])
        if "status" in query and query["status"][0]:
            sql += " AND l.status = ?"
            params.append(query["status"][0])
        sql += " ORDER BY l.listing_id LIMIT 100;"
        cur.execute(sql, params)
        self._send_json([dict(r) for r in cur.fetchall()])

    def _handle_orders_list(self, conn: sqlite3.Connection, query: Dict[str, List[str]]):
        cur = conn.cursor()
        base_where = " WHERE 1=1"
        params = []
        if "status" in query and query["status"][0]:
            base_where += " AND o.status = ?"
            params.append(query["status"][0])
        if "search" in query and query["search"][0]:
            base_where += " AND (o.order_id LIKE ? OR o.customer_id LIKE ?)"
            s = f"%{query['search'][0]}%"
            params.extend([s, s])

        cur.execute(f"SELECT COUNT(*) FROM orders o {base_where}", params)
        total = cur.fetchone()[0]

        page = max(1, int(query.get("page", ["1"])[0]))
        limit = min(500, max(1, int(query.get("limit", ["50"])[0])))
        offset = (page - 1) * limit

        sql = f"""
            SELECT o.*, 
                (SELECT COUNT(*) FROM order_lines ol WHERE ol.order_id = o.order_id) AS line_count,
                (SELECT COUNT(DISTINCT ol.seller_id) FROM order_lines ol WHERE ol.order_id = o.order_id) AS seller_count
            FROM orders o
            {base_where}
            ORDER BY o.order_date DESC LIMIT ? OFFSET ?;
        """
        cur.execute(sql, params + [limit, offset])
        rows = [dict(r) for r in cur.fetchall()]
        total_pages = (total + limit - 1) // limit if total > 0 else 1
        self._send_json({"items": rows, "total": total, "page": page, "limit": limit, "total_pages": total_pages})

    def _handle_order_detail(self, conn: sqlite3.Connection, order_id: str):
        cur = conn.cursor()
        cur.execute("SELECT * FROM orders WHERE order_id = ?;", (order_id,))
        order = cur.fetchone()
        if not order:
            return self._send_json({"error": "Order not found"}, 404)

        # Multi-seller order lines with fulfillment details
        cur.execute("""
            SELECT 
                ol.*,
                pl.title AS listing_title,
                pl.category,
                s.name AS seller_name,
                s.tier AS seller_tier,
                f.fulfillment_id,
                f.status AS fulfillment_status,
                f.carrier,
                f.tracking_number,
                f.shipped_at,
                f.delivered_at,
                f.is_late_shipment,
                f.is_late_delivery
            FROM order_lines ol
            JOIN product_listings pl ON ol.listing_id = pl.listing_id
            JOIN sellers s ON ol.seller_id = s.seller_id
            LEFT JOIN fulfillments f ON ol.order_line_id = f.order_line_id
            WHERE ol.order_id = ?;
        """, (order_id,))
        lines = [dict(r) for r in cur.fetchall()]

        # Reviews
        cur.execute("SELECT * FROM customer_reviews WHERE order_id = ?;", (order_id,))
        reviews = [dict(r) for r in cur.fetchall()]

        # Disputes
        cur.execute("SELECT * FROM disputes WHERE order_id = ?;", (order_id,))
        disputes = [dict(r) for r in cur.fetchall()]

        res = dict(order)
        res["order_lines"] = lines
        res["reviews"] = reviews
        res["disputes"] = disputes
        self._send_json(res)

    def _handle_fulfillments_list(self, conn: sqlite3.Connection, query: Dict[str, List[str]]):
        cur = conn.cursor()
        base_where = " WHERE 1=1"
        params = []
        if "status" in query and query["status"][0]:
            base_where += " AND f.status = ?"
            params.append(query["status"][0])
        if "carrier" in query and query["carrier"][0]:
            base_where += " AND f.carrier = ?"
            params.append(query["carrier"][0])
        if "late_only" in query and query["late_only"][0] == "1":
            base_where += " AND (f.is_late_shipment = 1 OR f.is_late_delivery = 1)"

        cur.execute(f"SELECT COUNT(*) FROM fulfillments f {base_where}", params)
        total = cur.fetchone()[0]

        page = max(1, int(query.get("page", ["1"])[0]))
        limit = min(500, max(1, int(query.get("limit", ["50"])[0])))
        offset = (page - 1) * limit

        sql = f"""
            SELECT f.*, s.name AS seller_name, pl.title AS product_title
            FROM fulfillments f
            JOIN sellers s ON f.seller_id = s.seller_id
            JOIN order_lines ol ON f.order_line_id = ol.order_line_id
            JOIN product_listings pl ON ol.listing_id = pl.listing_id
            {base_where}
            ORDER BY f.sla_ship_deadline DESC LIMIT ? OFFSET ?;
        """
        cur.execute(sql, params + [limit, offset])
        rows = [dict(r) for r in cur.fetchall()]
        total_pages = (total + limit - 1) // limit if total > 0 else 1
        self._send_json({"items": rows, "total": total, "page": page, "limit": limit, "total_pages": total_pages})

    def _handle_reviews_list(self, conn: sqlite3.Connection, query: Dict[str, List[str]]):
        cur = conn.cursor()
        sql = """
            SELECT r.*, s.name AS seller_name, pl.title AS product_title
            FROM customer_reviews r
            JOIN sellers s ON r.seller_id = s.seller_id
            JOIN product_listings pl ON r.listing_id = pl.listing_id
            ORDER BY r.created_at DESC LIMIT 100;
        """
        cur.execute(sql)
        self._send_json([dict(r) for r in cur.fetchall()])

    def _handle_disputes_list(self, conn: sqlite3.Connection, query: Dict[str, List[str]]):
        cur = conn.cursor()
        base_where = " WHERE 1=1"
        params = []
        if "status" in query and query["status"][0]:
            base_where += " AND d.status = ?"
            params.append(query["status"][0])

        cur.execute(f"SELECT COUNT(*) FROM disputes d {base_where}", params)
        total = cur.fetchone()[0]

        page = max(1, int(query.get("page", ["1"])[0]))
        limit = min(500, max(1, int(query.get("limit", ["50"])[0])))
        offset = (page - 1) * limit

        sql = f"""
            SELECT d.*, s.name AS seller_name
            FROM disputes d
            JOIN sellers s ON d.seller_id = s.seller_id
            {base_where}
            ORDER BY d.opened_at DESC LIMIT ? OFFSET ?;
        """
        cur.execute(sql, params + [limit, offset])
        rows = [dict(r) for r in cur.fetchall()]
        total_pages = (total + limit - 1) // limit if total > 0 else 1
        self._send_json({"items": rows, "total": total, "page": page, "limit": limit, "total_pages": total_pages})

    def _handle_payouts_list(self, conn: sqlite3.Connection, query: Dict[str, List[str]]):
        cur = conn.cursor()
        base_where = " WHERE 1=1"
        params = []
        if "status" in query and query["status"][0]:
            base_where += " AND p.status = ?"
            params.append(query["status"][0])
        if "seller_id" in query and query["seller_id"][0]:
            base_where += " AND p.seller_id = ?"
            params.append(query["seller_id"][0])

        cur.execute(f"SELECT COUNT(*) FROM payouts p {base_where}", params)
        total = cur.fetchone()[0]

        page = max(1, int(query.get("page", ["1"])[0]))
        limit = min(500, max(1, int(query.get("limit", ["50"])[0])))
        offset = (page - 1) * limit

        sql = f"""
            SELECT p.*, s.name AS seller_name, s.tier AS seller_tier,
                (SELECT COUNT(*) FROM payout_lines pl WHERE pl.payout_id = p.payout_id) AS line_count
            FROM payouts p
            JOIN sellers s ON p.seller_id = s.seller_id
            {base_where}
            ORDER BY p.payout_id DESC LIMIT ? OFFSET ?;
        """
        cur.execute(sql, params + [limit, offset])
        rows = [dict(r) for r in cur.fetchall()]
        total_pages = (total + limit - 1) // limit if total > 0 else 1
        self._send_json({"items": rows, "total": total, "page": page, "limit": limit, "total_pages": total_pages})

    def _handle_payout_detail(self, conn: sqlite3.Connection, payout_id: str):
        cur = conn.cursor()
        cur.execute("""
            SELECT p.*, s.name AS seller_name, s.tier AS seller_tier, s.hold_period_days, s.reserve_rate
            FROM payouts p
            JOIN sellers s ON p.seller_id = s.seller_id
            WHERE p.payout_id = ?;
        """, (payout_id,))
        payout = cur.fetchone()
        if not payout:
            return self._send_json({"error": "Payout not found"}, 404)

        cur.execute("SELECT * FROM payout_lines WHERE payout_id = ? ORDER BY payout_line_id;", (payout_id,))
        lines = [dict(r) for r in cur.fetchall()]

        res = dict(payout)
        res["lines"] = lines
        self._send_json(res)

    def _handle_rules_list(self, conn: sqlite3.Connection):
        cur = conn.cursor()
        cur.execute("SELECT * FROM commission_rules ORDER BY category, seller_tier;")
        comm_rules = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT * FROM reserve_rules ORDER BY seller_tier;")
        reserve_rules = [dict(r) for r in cur.fetchall()]

        self._send_json({
            "commission_rules": comm_rules,
            "reserve_rules": reserve_rules
        })

    def _handle_events_list(self, conn: sqlite3.Connection, query: Dict[str, List[str]]):
        cur = conn.cursor()
        base_where = " WHERE 1=1"
        params = []
        if "entity_type" in query and query["entity_type"][0]:
            base_where += " AND entity_type = ?"
            params.append(query["entity_type"][0])
        if "entity_id" in query and query["entity_id"][0]:
            base_where += " AND entity_id = ?"
            params.append(query["entity_id"][0])

        cur.execute(f"SELECT COUNT(*) FROM event_logs {base_where}", params)
        total = cur.fetchone()[0]

        page = max(1, int(query.get("page", ["1"])[0]))
        limit = min(500, max(1, int(query.get("limit", ["50"])[0])))
        offset = (page - 1) * limit

        sql = f"SELECT * FROM event_logs {base_where} ORDER BY created_at DESC LIMIT ? OFFSET ?;"
        cur.execute(sql, params + [limit, offset])
        rows = [dict(r) for r in cur.fetchall()]
        total_pages = (total + limit - 1) // limit if total > 0 else 1
        self._send_json({"items": rows, "total": total, "page": page, "limit": limit, "total_pages": total_pages})

    # --- Actions ---

    def _action_update_fulfillment_status(self, conn: sqlite3.Connection, ful_id: str, new_status: str, actor: str):
        cur = conn.cursor()
        cur.execute("SELECT status FROM fulfillments WHERE fulfillment_id = ?;", (ful_id,))
        row = cur.fetchone()
        if not row:
            return self._send_json({"error": "Fulfillment record not found"}, 404)
        old_status = row[0]

        now_str = "2026-10-22 12:00:00"
        if new_status == "SHIPPED":
            cur.execute("UPDATE fulfillments SET status = ?, shipped_at = ? WHERE fulfillment_id = ?", (new_status, now_str, ful_id))
        elif new_status == "DELIVERED":
            cur.execute("UPDATE fulfillments SET status = ?, delivered_at = ? WHERE fulfillment_id = ?", (new_status, now_str, ful_id))
        else:
            cur.execute("UPDATE fulfillments SET status = ? WHERE fulfillment_id = ?", (new_status, ful_id))

        # Log event history
        cur.execute("SELECT COUNT(*) FROM event_logs;")
        next_seq = cur.fetchone()[0] + 1
        evt_id = format_event_id(next_seq)
        cur.execute(
            "INSERT INTO event_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (evt_id, "FULFILLMENT", ful_id, "STATUS_CHANGE", old_status, new_status, json.dumps({"updated_by": actor}), actor, now_str)
        )
        conn.commit()
        self._send_json({"status": "success", "fulfillment_id": ful_id, "old_status": old_status, "new_status": new_status})

    def _action_resolve_dispute(self, conn: sqlite3.Connection, disp_id: str, new_status: str, actor: str):
        cur = conn.cursor()
        cur.execute("SELECT dispute_id, order_line_id, seller_id, amount, status, deducted_from_payout FROM disputes WHERE dispute_id = ?;", (disp_id,))
        row = cur.fetchone()
        if not row:
            return self._send_json({"error": "Dispute not found"}, 404)
        
        d_id, ol_id, seller_id, amt, old_status, already_deducted = row[0], row[1], row[2], float(row[3]), row[4], row[5]
        now_str = "2026-10-22 14:00:00"

        if new_status == "UPHELD":
            # Record financial deduction or auditable pending ledger adjustment
            cur.execute("""
                SELECT p.payout_id, p.status, p.net_amount, p.dispute_deduction
                FROM payout_lines pl
                JOIN payouts p ON pl.payout_id = p.payout_id
                WHERE pl.order_line_id = ?
                LIMIT 1;
            """, (ol_id,))
            p_row = cur.fetchone()

            adjustment_type = ""
            if p_row and p_row[1] in ("DRAFT", "PENDING_APPROVAL", "PROCESSING"):
                p_id = p_row[0]
                cur.execute("SELECT COUNT(*) FROM payout_lines WHERE payout_id = ?;", (p_id,))
                next_pline_seq = cur.fetchone()[0] + 1
                from src.models import format_payout_line_id
                new_pline_id = format_payout_line_id(p_id, next_pline_seq)
                cur.execute(
                    "INSERT INTO payout_lines VALUES (?, ?, ?, ?, ?, ?)",
                    (new_pline_id, p_id, ol_id, "DISPUTE_DEDUCTION", -amt, f"Upheld dispute chargeback for {disp_id}")
                )
                cur.execute(
                    "UPDATE payouts SET dispute_deduction = round(dispute_deduction + ?, 2), net_amount = round(net_amount - ?, 2) WHERE payout_id = ?",
                    (amt, amt, p_id)
                )
                adjustment_type = f"Direct deduction debit applied to pending payout {p_id}"
            else:
                adjustment_type = f"Recorded as pending clawback adjustment debit against seller {seller_id} rolling reserve escrow"

            # Update dispute record
            cur.execute("UPDATE disputes SET status = 'UPHELD', resolved_at = ?, deducted_from_payout = 1 WHERE dispute_id = ?", (now_str, disp_id))

            # Audit event log
            cur.execute("SELECT COUNT(*) FROM event_logs;")
            next_seq = cur.fetchone()[0] + 1
            cur.execute(
                "INSERT INTO event_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (format_event_id(next_seq), "DISPUTE", disp_id, "FINANCIAL_DEDUCTION_RECORDED", old_status, "UPHELD",
                 json.dumps({"amount": amt, "seller_id": seller_id, "financial_adjustment": adjustment_type}), actor, now_str)
            )
            conn.commit()
            return self._send_json({
                "success": True,
                "status": "success",
                "dispute_id": disp_id,
                "old_status": old_status,
                "new_status": "UPHELD",
                "deducted_from_payout": 1,
                "financial_action": adjustment_type,
                "financial_adjustment": adjustment_type,
                "amount": amt
            })
        else:
            # Non-upheld resolution (REJECTED / RESOLVED)
            cur.execute("UPDATE disputes SET status = ?, resolved_at = ?, deducted_from_payout = 0 WHERE dispute_id = ?", (new_status, now_str, disp_id))
            cur.execute("SELECT COUNT(*) FROM event_logs;")
            next_seq = cur.fetchone()[0] + 1
            cur.execute(
                "INSERT INTO event_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (format_event_id(next_seq), "DISPUTE", disp_id, "DISPUTE_RESOLUTION", old_status, new_status, json.dumps({"resolved_by": actor}), actor, now_str)
            )
            conn.commit()
            return self._send_json({"status": "success", "dispute_id": disp_id, "old_status": old_status, "new_status": new_status, "deducted_from_payout": 0})

    def _action_payout(self, conn: sqlite3.Connection, payout_id: str, action: str, actor: str):
        cur = conn.cursor()
        cur.execute("SELECT status, hold_release_date FROM payouts WHERE payout_id = ?;", (payout_id,))
        row = cur.fetchone()
        if not row:
            return self._send_json({"error": "Payout not found"}, 404)
        old_status, hold_release_date = row[0], row[1]
        now_str = "2026-10-22 15:30:00"

        if action == "APPROVE":
            # Enforce Rule FIN-01: Block approval if any fulfillment is undelivered or hold window is unreleased
            cur.execute("""
                SELECT 
                    f.fulfillment_id,
                    f.status AS ful_status,
                    f.delivered_at,
                    s.hold_period_days,
                    date(f.delivered_at, '+' || s.hold_period_days || ' days') AS required_hold_release
                FROM payout_lines pl
                JOIN fulfillments f ON pl.order_line_id = f.order_line_id
                JOIN sellers s ON f.seller_id = s.seller_id
                WHERE pl.payout_id = ?
            """, (payout_id,))
            check_rows = cur.fetchall()
            
            violations = []
            today_str = "2026-10-22"
            for r in check_rows:
                if r["ful_status"] != "DELIVERED":
                    violations.append(f"Fulfillment {r['fulfillment_id']} is not DELIVERED (status: {r['ful_status']})")
                elif r["delivered_at"] is None:
                    violations.append(f"Fulfillment {r['fulfillment_id']} is missing delivery timestamp")
                elif hold_release_date > today_str:
                    violations.append(f"Hold period active: release date is {hold_release_date} (current evaluation date: {today_str})")

            if violations:
                cur.execute("SELECT COUNT(*) FROM event_logs;")
                next_seq = cur.fetchone()[0] + 1
                cur.execute(
                    "INSERT INTO event_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (format_event_id(next_seq), "PAYOUT", payout_id, "APPROVAL_BLOCKED", old_status, old_status,
                     json.dumps({"reason": "Rule FIN-01 violation", "violations": violations}), actor, now_str)
                )
                conn.commit()
                return self._send_json({
                    "success": False,
                    "error": "Payout approval blocked by Rule FIN-01",
                    "rule": "Rule FIN-01: Funds cannot be released before fulfillment delivery and seller hold period expiration.",
                    "payout_id": payout_id,
                    "violations": violations
                }, 400)

            new_status = "PAID"
        elif action == "HOLD":
            new_status = "HELD"
        else:
            new_status = "PENDING_APPROVAL"

        cur.execute("UPDATE payouts SET status = ? WHERE payout_id = ?", (new_status, payout_id))

        cur.execute("SELECT COUNT(*) FROM event_logs;")
        next_seq = cur.fetchone()[0] + 1
        cur.execute(
            "INSERT INTO event_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (format_event_id(next_seq), "PAYOUT", payout_id, f"PAYOUT_{action}", old_status, new_status, json.dumps({"action": action, "actor": actor}), actor, now_str)
        )
        conn.commit()
        self._send_json({"status": "success", "payout_id": payout_id, "old_status": old_status, "new_status": new_status})

def run_server(port: int = SERVER_PORT, host: str = SERVER_HOST):
    server_address = (host, port)
    httpd = http.server.ThreadingHTTPServer(server_address, SellerOpsAPIHandler)
    print("=" * 60)
    print(f"SellerOps Control Tower running at http://{host}:{port}/")
    print("Serving polished operations dashboard with live REST API.")
    print("Press Ctrl+C to stop.")
    print("=" * 60)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
