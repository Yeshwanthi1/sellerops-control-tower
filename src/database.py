"""
SQLite database schema, connection helpers, and initialization.
"""
import sqlite3
import sys
from pathlib import Path

# Ensure workspace root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.config import DB_PATH

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sellers (
    seller_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    tier TEXT NOT NULL CHECK (tier IN ('TIER_1', 'TIER_2', 'TIER_3', 'ENTERPRISE')),
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'PROBATION', 'SUSPENDED')),
    onboarding_date TEXT NOT NULL,
    reserve_rate REAL NOT NULL CHECK (reserve_rate >= 0.0 AND reserve_rate <= 0.5),
    hold_period_days INTEGER NOT NULL CHECK (hold_period_days >= 0)
);

CREATE TABLE IF NOT EXISTS product_listings (
    listing_id TEXT PRIMARY KEY,
    seller_id TEXT NOT NULL REFERENCES sellers(seller_id),
    title TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('Electronics', 'Apparel', 'Home & Kitchen', 'Beauty', 'Books', 'Sports')),
    price REAL NOT NULL CHECK (price > 0),
    inventory_count INTEGER NOT NULL CHECK (inventory_count >= 0),
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'PAUSED', 'ARCHIVED')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS commission_rules (
    rule_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    seller_tier TEXT NOT NULL,
    rate REAL NOT NULL CHECK (rate >= 0.0 AND rate <= 1.0),
    effective_from TEXT NOT NULL,
    effective_to TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS reserve_rules (
    reserve_rule_id TEXT PRIMARY KEY,
    seller_tier TEXT NOT NULL,
    default_reserve_rate REAL NOT NULL CHECK (default_reserve_rate >= 0.0 AND default_reserve_rate <= 1.0),
    hold_period_days INTEGER NOT NULL CHECK (hold_period_days >= 0),
    effective_from TEXT NOT NULL,
    effective_to TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    order_date TEXT NOT NULL,
    total_amount REAL NOT NULL CHECK (total_amount >= 0),
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'PROCESSING', 'PARTIALLY_FULFILLED', 'DELIVERED', 'COMPLETED', 'CANCELLED')),
    shipping_address TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_lines (
    order_line_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    listing_id TEXT NOT NULL REFERENCES product_listings(listing_id),
    seller_id TEXT NOT NULL REFERENCES sellers(seller_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price REAL NOT NULL CHECK (unit_price > 0),
    subtotal REAL NOT NULL CHECK (subtotal >= 0),
    commission_rate REAL NOT NULL CHECK (commission_rate >= 0.0 AND commission_rate <= 1.0),
    commission_amount REAL NOT NULL CHECK (commission_amount >= 0)
);

CREATE TABLE IF NOT EXISTS fulfillments (
    fulfillment_id TEXT PRIMARY KEY,
    order_line_id TEXT UNIQUE NOT NULL REFERENCES order_lines(order_line_id),
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    seller_id TEXT NOT NULL REFERENCES sellers(seller_id),
    status TEXT NOT NULL CHECK (status IN ('ALLOCATED', 'PICKED', 'PACKED', 'SHIPPED', 'DELIVERED', 'RETURNED', 'FAILED')),
    carrier TEXT NOT NULL CHECK (carrier IN ('FedEx', 'UPS', 'DHL', 'USPS')),
    tracking_number TEXT NOT NULL,
    sla_ship_deadline TEXT NOT NULL,
    shipped_at TEXT,
    sla_delivery_deadline TEXT NOT NULL,
    delivered_at TEXT,
    returned_at TEXT,
    is_late_shipment INTEGER NOT NULL CHECK (is_late_shipment IN (0, 1)),
    is_late_delivery INTEGER NOT NULL CHECK (is_late_delivery IN (0, 1))
);

CREATE TABLE IF NOT EXISTS customer_reviews (
    review_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    order_line_id TEXT NOT NULL REFERENCES order_lines(order_line_id),
    seller_id TEXT NOT NULL REFERENCES sellers(seller_id),
    listing_id TEXT NOT NULL REFERENCES product_listings(listing_id),
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    title TEXT NOT NULL,
    comment TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS disputes (
    dispute_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    order_line_id TEXT NOT NULL REFERENCES order_lines(order_line_id),
    seller_id TEXT NOT NULL REFERENCES sellers(seller_id),
    amount REAL NOT NULL CHECK (amount > 0),
    reason TEXT NOT NULL CHECK (reason IN ('ITEM_NOT_RECEIVED', 'ITEM_DEFECTIVE', 'INCORRECT_ITEM', 'UNAUTHORIZED_CHARGE', 'LATE_DELIVERY')),
    status TEXT NOT NULL CHECK (status IN ('OPEN', 'UNDER_REVIEW', 'UPHELD', 'REJECTED', 'RESOLVED')),
    opened_at TEXT NOT NULL,
    resolved_at TEXT,
    deducted_from_payout INTEGER NOT NULL CHECK (deducted_from_payout IN (0, 1))
);

CREATE TABLE IF NOT EXISTS payouts (
    payout_id TEXT PRIMARY KEY,
    seller_id TEXT NOT NULL REFERENCES sellers(seller_id),
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    gross_amount REAL NOT NULL,
    commission_deduction REAL NOT NULL,
    reserve_deduction REAL NOT NULL,
    dispute_deduction REAL NOT NULL,
    net_amount REAL NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'PROCESSING', 'PAID', 'HELD')),
    created_at TEXT NOT NULL,
    hold_release_date TEXT NOT NULL,
    released_at TEXT
);

CREATE TABLE IF NOT EXISTS payout_lines (
    payout_line_id TEXT PRIMARY KEY,
    payout_id TEXT NOT NULL REFERENCES payouts(payout_id),
    order_line_id TEXT NOT NULL REFERENCES order_lines(order_line_id),
    line_type TEXT NOT NULL CHECK (line_type IN ('GROSS_SALES', 'COMMISSION_FEE', 'RESERVE_HOLD', 'DISPUTE_DEDUCTION')),
    amount REAL NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS event_logs (
    event_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('SELLER', 'ORDER', 'FULFILLMENT', 'DISPUTE', 'PAYOUT', 'EXCEPTION')),
    entity_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    old_state TEXT,
    new_state TEXT,
    payload_json TEXT,
    actor TEXT NOT NULL CHECK (actor IN ('SYSTEM', 'WAREHOUSE_OPERATOR', 'CUSTOMER', 'OPS_MANAGER', 'DISPUTE_AGENT')),
    created_at TEXT NOT NULL
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_listings_seller ON product_listings(seller_id);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_order_lines_order ON order_lines(order_id);
CREATE INDEX IF NOT EXISTS idx_order_lines_seller ON order_lines(seller_id);
CREATE INDEX IF NOT EXISTS idx_fulfillments_order ON fulfillments(order_id);
CREATE INDEX IF NOT EXISTS idx_fulfillments_seller ON fulfillments(seller_id);
CREATE INDEX IF NOT EXISTS idx_fulfillments_status ON fulfillments(status);
CREATE INDEX IF NOT EXISTS idx_disputes_seller ON disputes(seller_id);
CREATE INDEX IF NOT EXISTS idx_disputes_order ON disputes(order_id);
CREATE INDEX IF NOT EXISTS idx_payouts_seller ON payouts(seller_id);
CREATE INDEX IF NOT EXISTS idx_payout_lines_payout ON payout_lines(payout_id);
CREATE INDEX IF NOT EXISTS idx_events_entity ON event_logs(entity_type, entity_id);
"""

def get_db_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Return a configured SQLite connection with foreign keys enabled and row factory."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: Path = DB_PATH) -> None:
    """Initialize SQLite database with schema."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at", DB_PATH)
