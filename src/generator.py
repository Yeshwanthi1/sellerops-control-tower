"""
Deterministic parameterized synthetic data generator for SellerOps Control Tower.
Default seed: 20261022
Supports --scale demo (default) and --scale full.
Parent records are generated before dependent records.
Deliberate anomalies are injected with labels saved to data/ground_truth.csv and data/ground_truth.json.
"""
import argparse
import csv
import datetime
import json
import random
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.config import (
    DB_PATH,
    DATA_DIR,
    DEFAULT_SEED,
    GROUND_TRUTH_CSV,
    GROUND_TRUTH_JSON,
    SCALE_CONFIGS,
)
from src.database import init_db, get_db_connection
from src.models import (
    SellerTier,
    SellerStatus,
    ListingStatus,
    ProductCategory,
    OrderStatus,
    FulfillmentStatus,
    Carrier,
    DisputeReason,
    DisputeStatus,
    PayoutStatus,
    PayoutLineType,
    EventActor,
    AnomalyIssueType,
    format_seller_id,
    format_listing_id,
    format_order_id,
    format_order_line_id,
    format_fulfillment_id,
    format_dispute_id,
    format_payout_id,
    format_payout_line_id,
    format_review_id,
    format_commission_rule_id,
    format_reserve_rule_id,
    format_event_id,
)

# Product title templates per category
PRODUCT_CATALOG = {
    ProductCategory.ELECTRONICS: [
        "Wireless Noise-Cancelling Headphones", "Ultra HD 4K Webcam", "Mechanical Gaming Keyboard",
        "USB-C Multi-Port Hub", "Portable Bluetooth Speaker", "Smart Fitness Tracker Band",
        "100W GaN Fast Charger", "High-Speed HDMI 2.1 Cable", "True Wireless Earbuds", "Wireless Charging Pad"
    ],
    ProductCategory.APPAREL: [
        "Men's Merino Wool Crew Sweater", "Women's High-Rise Yoga Leggings", "Classic Denim Jacket",
        "Waterproof Hiking Shell Jacket", "Breathable Running Sneakers", "Organic Cotton Crew Neck Tee",
        "Thermal Baselayer Top", "Everyday Canvas Backpack", "All-Weather Polarized Sunglasses", "Leather Dress Belt"
    ],
    ProductCategory.HOME_KITCHEN: [
        "Enameled Cast Iron Dutch Oven", "Pour-Over Glass Coffee Maker", "Chef's 8-Inch Santoku Knife",
        "Digital Kitchen Food Scale", "Stainless Steel Mixing Bowls Set", "Silicone Baking Mat Set",
        "Non-Stick Ceramic Frying Pan", "Electric Rapid Boil Kettle", "Bamboo Cutting Board", "Aroma Oil Diffuser"
    ],
    ProductCategory.BEAUTY: [
        "Hydrating Hyaluronic Acid Serum", "Vitamin C Brightening Daily Cleanser", "SPF 50 Mineral Sunscreen",
        "Exfoliating AHA/BHA Night Peel", "Gentle Foaming Face Wash", "Argan Oil Hair Treatment",
        "Peptide Eye Recovery Cream", "Shea Butter Moisturizing Body Balm", "Matte Velvet Lip Stain", "Clarifying Clay Face Mask"
    ],
    ProductCategory.BOOKS: [
        "Mastering Distributed Systems", "The Data-Driven Product Playbook", "Clean Architecture for Microservices",
        "Modern Python Cookbook", "Designing Resilient Cloud Workflows", "Foundations of Financial Engineering",
        "Principles of Operational Excellence", "The Pragmatic Engineering Leader", "High-Output Team Leadership", "Algorithms for Scale"
    ],
    ProductCategory.SPORTS: [
        "Adjustable Speed Jump Rope", "Extra Thick High-Density Yoga Mat", "Resistance Bands Exercise Set",
        "Insulated Stainless Steel Sports Bottle", "Quick-Drying Microfiber Gym Towel", "Pro Grip Cycling Gloves",
        "Deep Tissue Foam Muscle Roller", "Ankle Support Recovery Braces", "Tactical Running Hydration Vest", "Compact Travel Trekking Poles"
    ]
}

REVIEW_COMMENTS_POSITIVE = [
    ("Excellent product!", "Arrived faster than expected and works flawlessly. Highly recommend this seller."),
    ("Great quality", "Superb build quality, matches description exactly."),
    ("Very satisfied", "Packed securely and delivered on time. Will buy again."),
    ("Top notch", "Five stars! Smooth transaction and great customer service.")
]

REVIEW_COMMENTS_NEGATIVE = [
    ("Late delivery and damaged box", "Took twice as long to arrive as promised and box was crushed."),
    ("Not as described", "Item feels cheap and stopped working after 3 days."),
    ("Poor seller communication", "Delayed shipping with no notification or tracking update."),
    ("Disappointed", "Expected better quality for this price.")
]

class DataGenerator:
    def __init__(self, seed: int = DEFAULT_SEED, scale: str = "demo", ground_truth_dir: Path = None):
        self.seed = seed
        self.scale = scale
        self.rng = random.Random(seed)
        self.cfg = SCALE_CONFIGS.get(scale, SCALE_CONFIGS["demo"])
        self.ground_truth: List[Dict[str, Any]] = []
        self.ground_truth_dir = Path(ground_truth_dir) if ground_truth_dir else DATA_DIR

    def run(self, db_conn: sqlite3.Connection):
        """Execute full deterministic generation pipeline."""
        print(f"[*] Starting DataGenerator with seed={self.seed}, scale='{self.scale}'")
        cur = db_conn.cursor()
        
        # Optimize SQLite for batch insertions
        cur.execute("PRAGMA synchronous = OFF;")
        cur.execute("PRAGMA journal_mode = MEMORY;")
        cur.execute("PRAGMA cache_size = -64000;")

        # Clean existing tables
        tables = [
            "event_logs", "payout_lines", "payouts", "disputes", "customer_reviews",
            "fulfillments", "order_lines", "orders", "product_listings",
            "reserve_rules", "commission_rules", "sellers"
        ]
        for t in tables:
            cur.execute(f"DELETE FROM {t};")
        db_conn.commit()
        try:
            cur.execute("VACUUM;")
        except Exception:
            pass

        # Step 1: Rules
        commission_rules, reserve_rules = self._generate_rules()
        cur.executemany("INSERT INTO commission_rules VALUES (?,?,?,?,?,?,?)", commission_rules)
        cur.executemany("INSERT INTO reserve_rules VALUES (?,?,?,?,?,?)", reserve_rules)
        db_conn.commit()
        print(f"[+] Inserted {len(commission_rules)} commission rules and {len(reserve_rules)} reserve rules")

        # Step 2: Sellers
        sellers = self._generate_sellers(self.cfg["sellers"])
        cur.executemany("INSERT INTO sellers VALUES (?,?,?,?,?,?,?,?)", sellers)
        db_conn.commit()
        print(f"[+] Inserted {len(sellers)} sellers")

        # Step 3: Product Listings
        listings = self._generate_listings(sellers, self.cfg["listings"])
        cur.executemany("INSERT INTO product_listings VALUES (?,?,?,?,?,?,?,?)", listings)
        db_conn.commit()
        print(f"[+] Inserted {len(listings)} product listings")

        # Step 4: Orders & Order Lines (with multi-seller orders)
        orders, order_lines = self._generate_orders_and_lines(
            sellers, listings, commission_rules, self.cfg["orders"]
        )
        cur.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?)", orders)
        cur.executemany("INSERT INTO order_lines VALUES (?,?,?,?,?,?,?,?,?)", order_lines)
        db_conn.commit()
        print(f"[+] Inserted {len(orders)} orders with {len(order_lines)} order lines")

        # Step 5: Fulfillments (one per order line: FUL-<order-line-id>)
        order_dates = {o[0]: o[2] for o in orders}
        fulfillments = self._generate_fulfillments(order_lines, order_dates)
        cur.executemany("INSERT INTO fulfillments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", fulfillments)
        db_conn.commit()
        print(f"[+] Inserted {len(fulfillments)} fulfillments")

        # Step 6: Customer Reviews
        reviews = self._generate_reviews(order_lines, fulfillments)
        cur.executemany("INSERT INTO customer_reviews VALUES (?,?,?,?,?,?,?,?,?)", reviews)
        db_conn.commit()
        print(f"[+] Inserted {len(reviews)} customer reviews")

        # Step 7: Disputes
        disputes = self._generate_disputes(order_lines, fulfillments, self.cfg["disputes"])
        cur.executemany("INSERT INTO disputes VALUES (?,?,?,?,?,?,?,?,?,?)", disputes)
        db_conn.commit()
        print(f"[+] Inserted {len(disputes)} disputes")

        # Step 8: Payouts and Payout Lines
        payouts, payout_lines = self._generate_payouts(
            sellers, order_lines, fulfillments, disputes, self.cfg["payouts"]
        )
        cur.executemany("INSERT INTO payouts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", payouts)
        cur.executemany("INSERT INTO payout_lines VALUES (?,?,?,?,?,?)", payout_lines)
        db_conn.commit()
        print(f"[+] Inserted {len(payouts)} payouts with {len(payout_lines)} payout lines")

        # Step 9: Inject Deliberate Anomalies & create ground truth
        self._inject_anomalies(db_conn)
        db_conn.commit()

        # Step 10: Event History Logs for traceability (complete lifecycle, zero sample limits)
        self._generate_event_logs(db_conn)

        # Reset PRAGMA to standard
        cur.execute("PRAGMA synchronous = NORMAL;")
        db_conn.commit()

        # Save ground truth files
        self._save_ground_truth()
        print(f"[✓] Generation complete! Ground truth saved with {len(self.ground_truth)} anomalies.")

    # --- Generation Step Implementations ---

    def _generate_rules(self) -> Tuple[List[Tuple], List[Tuple]]:
        categories = [c.value for c in ProductCategory]
        tiers = [t.value for t in SellerTier]
        
        comm_rules = []
        rule_seq = 1
        # Category specific rules
        cat_rates = {
            "Electronics": 0.08,
            "Apparel": 0.15,
            "Home & Kitchen": 0.12,
            "Beauty": 0.14,
            "Books": 0.10,
            "Sports": 0.11
        }
        for cat in categories:
            for tier in tiers:
                rate = cat_rates.get(cat, 0.12)
                if tier == SellerTier.ENTERPRISE.value:
                    rate = max(0.04, rate - 0.02)
                elif tier == SellerTier.TIER_1.value:
                    rate = max(0.05, rate - 0.01)
                comm_rules.append((
                    format_commission_rule_id(rule_seq),
                    cat,
                    tier,
                    round(rate, 4),
                    "2026-01-01",
                    "2026-12-31",
                    f"2026 Standard Commission Rule for {cat} ({tier})"
                ))
                rule_seq += 1

        # Reserve rules
        reserve_rules = [
            (format_reserve_rule_id(1), SellerTier.ENTERPRISE.value, 0.04, 7, "2026-01-01", "2026-12-31"),
            (format_reserve_rule_id(2), SellerTier.TIER_1.value, 0.06, 7, "2026-01-01", "2026-12-31"),
            (format_reserve_rule_id(3), SellerTier.TIER_2.value, 0.09, 14, "2026-01-01", "2026-12-31"),
            (format_reserve_rule_id(4), SellerTier.TIER_3.value, 0.12, 21, "2026-01-01", "2026-12-31"),
        ]
        return comm_rules, reserve_rules

    def _generate_sellers(self, count: int) -> List[Tuple]:
        sellers = []
        tiers = [SellerTier.TIER_1.value, SellerTier.TIER_2.value, SellerTier.TIER_3.value, SellerTier.ENTERPRISE.value]
        tier_weights = [0.35, 0.40, 0.15, 0.10]

        prefixes = ["Apex", "Nova", "Prime", "Summit", "Vanguard", "Echo", "Atlas", "Zenith", "Quantum", "Falcon"]
        suffixes = ["Direct", "Supply", "Goods", "Trading", "Retail", "Enterprises", "Brands", "Tech", "Ventures", "Stores"]

        for seq in range(1, count + 1):
            seller_id = format_seller_id(seq)
            name = f"{self.rng.choice(prefixes)} {self.rng.choice(suffixes)} {seq}"
            email = f"ops@{name.lower().replace(' ', '')}.example.com"
            tier = self.rng.choices(tiers, weights=tier_weights)[0]
            
            # Status: guarantee at least 3 suspended sellers for anomaly injection
            if seq in (5, 10, 15):
                status = SellerStatus.SUSPENDED.value
            else:
                status_roll = self.rng.random()
                if status_roll < 0.90:
                    status = SellerStatus.ACTIVE.value
                elif status_roll < 0.96:
                    status = SellerStatus.PROBATION.value
                else:
                    status = SellerStatus.SUSPENDED.value

            days_ago = self.rng.randint(30, 700)
            onboarding_date = (datetime.date(2026, 1, 1) - datetime.timedelta(days=days_ago)).isoformat()

            if tier == SellerTier.ENTERPRISE.value:
                reserve_rate = 0.04
                hold_days = 7
            elif tier == SellerTier.TIER_1.value:
                reserve_rate = 0.06
                hold_days = 7
            elif tier == SellerTier.TIER_2.value:
                reserve_rate = 0.09
                hold_days = 14
            else:
                reserve_rate = 0.12
                hold_days = 21

            sellers.append((seller_id, name, email, tier, status, onboarding_date, reserve_rate, hold_days))
        return sellers

    def _generate_listings(self, sellers: List[Tuple], count: int) -> List[Tuple]:
        listings = []
        categories = list(ProductCategory)
        listings_per_seller = max(2, count // len(sellers))
        listing_seq_global = 1

        for seller in sellers:
            seller_id = seller[0]
            seller_status = seller[4]
            num_for_this = self.rng.randint(max(1, listings_per_seller - 1), listings_per_seller + 2)
            
            for seq in range(1, num_for_this + 1):
                listing_id = format_listing_id(seller_id, seq)
                cat = self.rng.choice(categories)
                title = f"{self.rng.choice(PRODUCT_CATALOG[cat])} (Edition {seq})"
                
                if cat == ProductCategory.ELECTRONICS:
                    price = round(self.rng.uniform(25.0, 350.0), 2)
                elif cat == ProductCategory.BOOKS:
                    price = round(self.rng.uniform(15.0, 85.0), 2)
                else:
                    price = round(self.rng.uniform(18.0, 180.0), 2)

                inventory = self.rng.randint(10, 500)
                
                # Baseline listing status rules: suspended sellers have ARCHIVED listings
                if seller_status == SellerStatus.SUSPENDED.value:
                    status = ListingStatus.ARCHIVED.value
                else:
                    status = ListingStatus.ACTIVE.value if self.rng.random() < 0.92 else ListingStatus.PAUSED.value

                created_at = "2026-01-05 10:00:00"
                listings.append((listing_id, seller_id, title, cat.value, price, inventory, status, created_at))
                listing_seq_global += 1
                if len(listings) >= count:
                    break
            if len(listings) >= count:
                break
        return listings

    def _generate_orders_and_lines(
        self, sellers: List[Tuple], listings: List[Tuple], comm_rules: List[Tuple], count: int
    ) -> Tuple[List[Tuple], List[Tuple]]:
        orders = []
        order_lines = []

        # Filter active listings for valid baseline order placement
        active_listings = [l for l in listings if l[6] == ListingStatus.ACTIVE.value]
        if not active_listings:
            active_listings = listings

        seller_lookup = {s[0]: s for s in sellers}
        comm_rule_lookup = {(r[1], r[2]): r[3] for r in comm_rules}

        start_date = datetime.date(2026, 1, 10)
        end_date = datetime.date(2026, 10, 15)
        total_days = (end_date - start_date).days

        line_seq_global = 1

        for order_seq in range(1, count + 1):
            order_id = format_order_id(order_seq)
            cust_id = f"CUST-{self.rng.randint(1000, 99999):05d}"
            
            # Date progression
            day_offset = self.rng.randint(0, total_days)
            order_d = start_date + datetime.timedelta(days=day_offset)
            order_dt = f"{order_d.isoformat()} {self.rng.randint(8, 20):02d}:{self.rng.randint(0, 59):02d}:{self.rng.randint(0, 59):02d}"

            # Multi-seller order: 1 to 4 items, potentially from different sellers!
            num_lines = self.rng.choices([1, 2, 3, 4], weights=[0.60, 0.25, 0.10, 0.05])[0]
            sampled_listings = self.rng.sample(active_listings, min(num_lines, len(active_listings)))

            order_subtotal = 0.0
            order_lines_for_this = []

            for l_idx, lst in enumerate(sampled_listings, start=1):
                listing_id = lst[0]
                seller_id = lst[1]
                category = lst[3]
                unit_price = lst[4]

                seller = seller_lookup.get(seller_id)
                seller_tier = seller[3] if seller else SellerTier.TIER_2.value

                qty = self.rng.choices([1, 2, 3], weights=[0.80, 0.15, 0.05])[0]
                line_subtotal = round(qty * unit_price, 2)
                order_subtotal += line_subtotal

                # Commission lookup
                rate = comm_rule_lookup.get((category, seller_tier), 0.12)
                comm_amt = round(line_subtotal * rate, 2)

                line_id = format_order_line_id(order_id, l_idx)
                order_lines_for_this.append((
                    line_id, order_id, listing_id, seller_id, qty, unit_price, line_subtotal, rate, comm_amt
                ))

            # Derive order status
            order_status = OrderStatus.DELIVERED.value if day_offset < (total_days - 10) else OrderStatus.PROCESSING.value
            address = f"{self.rng.randint(100, 9999)} Metro Blvd, Suite {self.rng.randint(1, 80)}, Dallas, TX 75201"

            orders.append((order_id, cust_id, order_dt, round(order_subtotal, 2), order_status, address))
            order_lines.extend(order_lines_for_this)

        return orders, order_lines

    def _generate_fulfillments(self, order_lines: List[Tuple], order_dates: Dict[str, str]) -> List[Tuple]:
        fulfillments = []
        carriers = [c.value for c in Carrier]

        for line in order_lines:
            line_id = line[0]
            order_id = line[1]
            seller_id = line[3]

            fulfillment_id = format_fulfillment_id(line_id)
            carrier = self.rng.choice(carriers)
            tracking_num = f"TRK-{self.rng.randint(100000000, 999999999)}"

            # Accurate chronological sequencing from actual order date
            order_dt_str = order_dates.get(order_id, "2026-03-01 10:00:00")
            order_dt = datetime.datetime.strptime(order_dt_str, "%Y-%m-%d %H:%M:%S")

            sla_ship_deadline = order_dt + datetime.timedelta(days=2)
            
            # 88% on-time shipment, 12% late shipment
            is_late_shipment = 1 if self.rng.random() < 0.12 else 0
            if is_late_shipment:
                shipped_at = order_dt + datetime.timedelta(days=self.rng.randint(3, 5), hours=self.rng.randint(1, 12))
            else:
                shipped_at = order_dt + datetime.timedelta(hours=self.rng.randint(12, 44))

            sla_delivery_deadline = shipped_at + datetime.timedelta(days=4)

            # 90% on-time delivery, 10% late delivery
            is_late_delivery = 1 if self.rng.random() < 0.10 else 0
            if is_late_delivery:
                delivered_at = shipped_at + datetime.timedelta(days=self.rng.randint(5, 8), hours=self.rng.randint(1, 10))
            else:
                delivered_at = shipped_at + datetime.timedelta(days=self.rng.randint(1, 3), hours=self.rng.randint(2, 20))

            # Status
            status_roll = self.rng.random()
            if status_roll < 0.90:
                status = FulfillmentStatus.DELIVERED.value
                returned_at = None
            elif status_roll < 0.94:
                status = FulfillmentStatus.RETURNED.value
                returned_at = (delivered_at + datetime.timedelta(days=self.rng.randint(2, 6))).strftime("%Y-%m-%d %H:%M:%S")
            else:
                status = FulfillmentStatus.SHIPPED.value
                delivered_at = None
                returned_at = None

            fulfillments.append((
                fulfillment_id,
                line_id,
                order_id,
                seller_id,
                status,
                carrier,
                tracking_num,
                sla_ship_deadline.strftime("%Y-%m-%d %H:%M:%S"),
                shipped_at.strftime("%Y-%m-%d %H:%M:%S"),
                sla_delivery_deadline.strftime("%Y-%m-%d %H:%M:%S"),
                delivered_at.strftime("%Y-%m-%d %H:%M:%S") if delivered_at else None,
                returned_at,
                is_late_shipment,
                is_late_delivery
            ))
        return fulfillments

    def _generate_reviews(self, order_lines: List[Tuple], fulfillments: List[Tuple]) -> List[Tuple]:
        reviews = []
        ful_lookup = {f[1]: f for f in fulfillments}
        rev_seq = 1

        for line in order_lines:
            # 25% of orders get a customer review
            if self.rng.random() > 0.25:
                continue

            line_id = line[0]
            order_id = line[1]
            listing_id = line[2]
            seller_id = line[3]

            ful = ful_lookup.get(line_id)
            if not ful or ful[4] != FulfillmentStatus.DELIVERED.value or not ful[10]:
                continue

            is_late = ful[12] or ful[13]
            if is_late or self.rng.random() < 0.15:
                rating = self.rng.choice([1, 2, 3])
                title, comment = self.rng.choice(REVIEW_COMMENTS_NEGATIVE)
            else:
                rating = self.rng.choice([4, 5])
                title, comment = self.rng.choice(REVIEW_COMMENTS_POSITIVE)

            created_at = (datetime.datetime.strptime(ful[10], "%Y-%m-%d %H:%M:%S") + datetime.timedelta(days=self.rng.randint(1, 4))).strftime("%Y-%m-%d %H:%M:%S")
            review_id = format_review_id(rev_seq)
            reviews.append((review_id, order_id, line_id, seller_id, listing_id, rating, title, comment, created_at))
            rev_seq += 1

        return reviews

    def _generate_disputes(self, order_lines: List[Tuple], fulfillments: List[Tuple], count: int) -> List[Tuple]:
        disputes = []
        ful_lookup = {f[1]: f for f in fulfillments}
        
        # Ensure delivered fulfillments from early orders are included so payouts have upheld disputes
        delivered_lines = [l for l in order_lines if ful_lookup.get(l[0]) and ful_lookup[l[0]][4] == FulfillmentStatus.DELIVERED.value]
        problem_lines = [l for l in order_lines if ful_lookup.get(l[0]) and (
            ful_lookup[l[0]][4] == FulfillmentStatus.RETURNED.value or 
            ful_lookup[l[0]][12] == 1 or ful_lookup[l[0]][13] == 1
        )]
        
        # Combine guaranteed delivered lines for dispute testing with problem lines
        candidate_lines = delivered_lines[:15] + problem_lines + delivered_lines[15:]
        # Remove duplicates while preserving order
        seen_lines = set()
        unique_candidates = []
        for l in candidate_lines:
            if l[0] not in seen_lines:
                seen_lines.add(l[0])
                unique_candidates.append(l)

        dispute_targets = unique_candidates[:count] if len(unique_candidates) >= count else unique_candidates
        reasons = [r.value for r in DisputeReason]

        for idx, line in enumerate(dispute_targets, start=1):
            dispute_id = format_dispute_id(idx)
            line_id = line[0]
            order_id = line[1]
            seller_id = line[3]
            subtotal = line[6]

            ful = ful_lookup.get(line_id)
            if ful and ful[4] == FulfillmentStatus.RETURNED.value:
                reason = DisputeReason.ITEM_DEFECTIVE.value
                amount = subtotal
            elif ful and ful[13] == 1:
                reason = DisputeReason.LATE_DELIVERY.value
                amount = round(min(subtotal, 35.0), 2)
            else:
                reason = self.rng.choice(reasons)
                amount = round(self.rng.uniform(15.0, subtotal), 2)

            status_roll = self.rng.random()
            # For the first 10, guarantee UPHELD
            if idx <= 10 or status_roll < 0.65:
                status = DisputeStatus.UPHELD.value
                deducted = 1
            elif status_roll < 0.85:
                status = DisputeStatus.REJECTED.value
                deducted = 0
            elif status_roll < 0.95:
                status = DisputeStatus.RESOLVED.value
                deducted = 0
            else:
                status = DisputeStatus.OPEN.value
                deducted = 0

            opened_at = "2026-05-10 14:00:00"
            resolved_at = "2026-05-15 11:30:00" if status in (DisputeStatus.UPHELD.value, DisputeStatus.REJECTED.value, DisputeStatus.RESOLVED.value) else None

            disputes.append((dispute_id, order_id, line_id, seller_id, amount, reason, status, opened_at, resolved_at, deducted))

        return disputes

    def _generate_payouts(
        self,
        sellers: List[Tuple],
        order_lines: List[Tuple],
        fulfillments: List[Tuple],
        disputes: List[Tuple],
        max_payouts: int
    ) -> Tuple[List[Tuple], List[Tuple]]:
        payouts = []
        payout_lines = []

        ful_lookup = {f[1]: f for f in fulfillments}
        # line_id -> dispute
        dispute_lookup = {d[2]: d for d in disputes}
        seller_lookup = {s[0]: s for s in sellers}

        # Group order lines by seller
        seller_orders: Dict[str, List[Tuple]] = {}
        for line in order_lines:
            seller_id = line[3]
            seller_orders.setdefault(seller_id, []).append(line)

        payout_seq = 1

        for seller_id, lines in seller_orders.items():
            seller = seller_lookup.get(seller_id)
            if not seller:
                continue

            seller_status = seller[4]
            reserve_rate = seller[6]
            hold_days = seller[7]

            # In valid baseline: suspended sellers get no new payouts
            if seller_status == SellerStatus.SUSPENDED.value:
                continue

            # Eligible lines: delivered fulfillments
            eligible_lines = []
            for line in lines:
                ful = ful_lookup.get(line[0])
                if ful and ful[4] == FulfillmentStatus.DELIVERED.value and ful[10]:
                    eligible_lines.append((line, ful))

            if not eligible_lines:
                continue

            # Chunk into batches of ~4 to 8 order lines per payout
            chunk_size = self.rng.randint(4, 8)
            for i in range(0, len(eligible_lines), chunk_size):
                chunk = eligible_lines[i:i + chunk_size]
                if not chunk:
                    continue

                payout_id = format_payout_id(payout_seq)
                gross_amount = round(sum(item[0][6] for item in chunk), 2)
                commission_deduction = round(sum(item[0][8] for item in chunk), 2)
                reserve_deduction = round(sum(round(item[0][6] * reserve_rate, 2) for item in chunk), 2)

                # Check disputes on these lines
                dispute_deduction = 0.0
                dispute_lines = []
                for item in chunk:
                    l_id = item[0][0]
                    dsp = dispute_lookup.get(l_id)
                    if dsp and dsp[6] == DisputeStatus.UPHELD.value:
                        dispute_amt = dsp[4]
                        dispute_deduction += dispute_amt
                        dispute_lines.append((l_id, dispute_amt))

                dispute_deduction = round(dispute_deduction, 2)
                net_amount = round(gross_amount - commission_deduction - reserve_deduction - dispute_deduction, 2)

                # Dates
                latest_delivery = max(
                    datetime.datetime.strptime(item[1][10], "%Y-%m-%d %H:%M:%S") for item in chunk
                )
                hold_release_date = (latest_delivery + datetime.timedelta(days=hold_days)).date().isoformat()
                created_at = (latest_delivery + datetime.timedelta(days=hold_days + 1)).strftime("%Y-%m-%d %H:%M:%S")
                released_at = (latest_delivery + datetime.timedelta(days=hold_days + 2)).strftime("%Y-%m-%d %H:%M:%S")

                period_start = (latest_delivery - datetime.timedelta(days=14)).date().isoformat()
                period_end = latest_delivery.date().isoformat()
                payout_status = PayoutStatus.PAID.value

                payouts.append((
                    payout_id, seller_id, period_start, period_end, gross_amount,
                    commission_deduction, reserve_deduction, dispute_deduction,
                    net_amount, payout_status, created_at, hold_release_date, released_at
                ))

                # Payout Lines (1-to-1 traceability per order line)
                payline_seq = 1
                for item in chunk:
                    l_id = item[0][0]
                    line_subtotal = item[0][6]
                    line_comm = item[0][8]
                    line_res = round(line_subtotal * reserve_rate, 2)

                    # Gross revenue line
                    payout_lines.append((
                        format_payout_line_id(payout_id, payline_seq),
                        payout_id,
                        l_id,
                        PayoutLineType.GROSS_SALES.value,
                        line_subtotal,
                        f"Gross item revenue for {l_id}"
                    ))
                    payline_seq += 1

                    # Commission deduction line
                    payout_lines.append((
                        format_payout_line_id(payout_id, payline_seq),
                        payout_id,
                        l_id,
                        PayoutLineType.COMMISSION_FEE.value,
                        -line_comm,
                        f"Platform commission fee ({item[0][7]*100:.1f}%)"
                    ))
                    payline_seq += 1

                    # Reserve deduction line
                    payout_lines.append((
                        format_payout_line_id(payout_id, payline_seq),
                        payout_id,
                        l_id,
                        PayoutLineType.RESERVE_HOLD.value,
                        -line_res,
                        f"Reserve hold ({reserve_rate*100:.1f}%)"
                    ))
                    payline_seq += 1

                # Dispute deduction lines
                for d_lid, d_amt in dispute_lines:
                    payout_lines.append((
                        format_payout_line_id(payout_id, payline_seq),
                        payout_id,
                        d_lid,
                        PayoutLineType.DISPUTE_DEDUCTION.value,
                        -round(d_amt, 2),
                        f"Upheld dispute chargeback for {d_lid}"
                    ))
                    payline_seq += 1

                payout_seq += 1
                if len(payouts) >= max_payouts:
                    break
            if len(payouts) >= max_payouts:
                break

        return payouts, payout_lines

    def _inject_anomalies(self, db_conn: sqlite3.Connection):
        """
        Inject exactly the 5 required anomaly types and document them into self.ground_truth.
        1. Payout before delivery or hold release
        2. Commission applied twice
        3. Suspended seller continues listing
        4. Dispute not deducted
        5. Payout total does not equal its lines
        """
        cur = db_conn.cursor()
        anom_id = 1

        # --- Anomaly 1: Payout before delivery or hold release ---
        # Find 3 paid payouts (use OFFSET 0)
        cur.execute("SELECT payout_id, seller_id, net_amount, hold_release_date FROM payouts WHERE status = 'PAID' LIMIT 3 OFFSET 0;")
        payouts_for_a1 = cur.fetchall()
        for p in payouts_for_a1:
            pid, sid, net_amt, hold_date = p[0], p[1], p[2], p[3]
            premature_release = "2026-03-01 10:00:00"
            cur.execute("UPDATE payouts SET released_at = ?, hold_release_date = '2026-04-15' WHERE payout_id = ?", (premature_release, pid))
            self.ground_truth.append({
                "anomaly_id": f"ANOM-{anom_id:06d}",
                "issue_type": AnomalyIssueType.PAYOUT_BEFORE_HOLD_RELEASE.value,
                "target_entity_type": "PAYOUT",
                "target_entity_id": pid,
                "seller_id": sid,
                "expected_financial_impact": net_amt,
                "description": f"Payout {pid} was released on {premature_release} prior to hold release date 2026-04-15"
            })
            anom_id += 1

        # --- Anomaly 2: Commission applied twice ---
        # Find 3 order lines in payout_lines from payouts with OFFSET >= 5
        cur.execute("""
            SELECT pl.payout_id, pl.order_line_id, ol.seller_id, ol.subtotal, ol.commission_rate, ol.commission_amount
            FROM payout_lines pl
            JOIN order_lines ol ON pl.order_line_id = ol.order_line_id
            WHERE pl.line_type = 'COMMISSION_FEE'
              AND pl.payout_id NOT IN (SELECT payout_id FROM payouts LIMIT 4)
            LIMIT 3;
        """)
        comm_targets = cur.fetchall()
        for idx, ct in enumerate(comm_targets, start=1):
            pid, olid, sid, subtotal, rate, comm_amt = ct[0], ct[1], ct[2], ct[3], ct[4], ct[5]
            dup_payline_id = f"PAYLINE-DUP-{idx:04d}"
            cur.execute(
                "INSERT INTO payout_lines VALUES (?, ?, ?, ?, ?, ?)",
                (dup_payline_id, pid, olid, PayoutLineType.COMMISSION_FEE.value, -comm_amt, f"Duplicate commission fee charged for {olid}")
            )
            # Update order_lines commission_amount and payout header so payout internal math stays balanced
            cur.execute("UPDATE order_lines SET commission_amount = ? WHERE order_line_id = ?", (comm_amt * 2, olid))
            cur.execute("UPDATE payouts SET commission_deduction = commission_deduction + ?, net_amount = round(net_amount - ?, 2) WHERE payout_id = ?", (comm_amt, comm_amt, pid))
            self.ground_truth.append({
                "anomaly_id": f"ANOM-{anom_id:06d}",
                "issue_type": AnomalyIssueType.COMMISSION_APPLIED_TWICE.value,
                "target_entity_type": "ORDER_LINE",
                "target_entity_id": olid,
                "seller_id": sid,
                "expected_financial_impact": comm_amt,
                "description": f"Order line {olid} had commission applied twice (duplicate deduction of ${comm_amt:.2f})"
            })
            anom_id += 1

        # --- Anomaly 3: Suspended seller continues listing ---
        cur.execute("SELECT seller_id, name FROM sellers WHERE status = 'SUSPENDED' LIMIT 3;")
        susp_sellers = cur.fetchall()
        for s in susp_sellers:
            sid, sname = s[0], s[1]
            cur.execute("SELECT listing_id, price, inventory_count FROM product_listings WHERE seller_id = ? LIMIT 1;", (sid,))
            listing = cur.fetchone()
            if listing:
                lid, price, inv = listing[0], listing[1], listing[2]
                cur.execute("UPDATE product_listings SET status = 'ACTIVE' WHERE listing_id = ?", (lid,))
                self.ground_truth.append({
                    "anomaly_id": f"ANOM-{anom_id:06d}",
                    "issue_type": AnomalyIssueType.SUSPENDED_SELLER_LISTING.value,
                    "target_entity_type": "PRODUCT_LISTING",
                    "target_entity_id": lid,
                    "seller_id": sid,
                    "expected_financial_impact": round(price * min(inv, 10), 2),
                    "description": f"Suspended seller {sid} ({sname}) maintains active listing {lid}"
                })
                anom_id += 1

        # --- Anomaly 4: Dispute not deducted ---
        # Find 3 payouts containing lines with UPHELD disputes (avoid first 4 payouts used above)
        cur.execute("""
            SELECT p.payout_id, p.seller_id, d.dispute_id, d.amount
            FROM payouts p
            JOIN payout_lines pl ON p.payout_id = pl.payout_id
            JOIN disputes d ON pl.order_line_id = d.order_line_id
            WHERE d.status = 'UPHELD' AND p.dispute_deduction > 0
              AND p.payout_id NOT IN (SELECT payout_id FROM payouts LIMIT 4)
            GROUP BY d.dispute_id
            LIMIT 3;
        """)
        disp_targets = cur.fetchall()
        for dt in disp_targets:
            pid, sid, did, amt = dt[0], dt[1], dt[2], dt[3]
            # Payout released funds WITHOUT deducting the dispute amount:
            # We remove the dispute deduction from the payout header and remove the deduction line
            # so the seller gets net_amount without dispute reduction, and the dispute is marked deducted_from_payout = 0
            cur.execute("UPDATE payouts SET dispute_deduction = 0.0, net_amount = round(gross_amount - commission_deduction - reserve_deduction, 2) WHERE payout_id = ?", (pid,))
            cur.execute("UPDATE disputes SET deducted_from_payout = 0 WHERE dispute_id = ?", (did,))
            cur.execute("DELETE FROM payout_lines WHERE payout_id = ? AND line_type = 'DISPUTE_DEDUCTION'", (pid,))
            self.ground_truth.append({
                "anomaly_id": f"ANOM-{anom_id:06d}",
                "issue_type": AnomalyIssueType.DISPUTE_NOT_DEDUCTED.value,
                "target_entity_type": "DISPUTE",
                "target_entity_id": did,
                "seller_id": sid,
                "expected_financial_impact": amt,
                "description": f"Upheld dispute {did} (${amt:.2f}) was not deducted from payout {pid}"
            })
            anom_id += 1

        # --- Anomaly 5: Payout total does not equal its lines ---
        # Find 3 payouts that were NOT used above (use OFFSET 25) and alter the header net_amount by +$125.00
        cur.execute("SELECT payout_id, seller_id, net_amount FROM payouts WHERE status = 'PAID' LIMIT 3 OFFSET 25;")
        mismatch_targets = cur.fetchall()
        for mt in mismatch_targets:
            pid, sid, net_amt = mt[0], mt[1], mt[2]
            corrupted_net = round(net_amt + 125.00, 2)
            cur.execute("UPDATE payouts SET net_amount = ? WHERE payout_id = ?", (corrupted_net, pid))
            self.ground_truth.append({
                "anomaly_id": f"ANOM-{anom_id:06d}",
                "issue_type": AnomalyIssueType.PAYOUT_TOTAL_MISMATCH.value,
                "target_entity_type": "PAYOUT",
                "target_entity_id": pid,
                "seller_id": sid,
                "expected_financial_impact": 125.00,
                "description": f"Payout {pid} header net amount (${corrupted_net:.2f}) does not match sum of lines (variance: $125.00)"
            })
            anom_id += 1

    def _generate_event_logs(self, db_conn: sqlite3.Connection):
        """
        Generate complete, deterministic, append-only lifecycle events for ALL relevant
        sellers, fulfillments, disputes, and payouts across the dataset (zero sample limits).
        """
        cur = db_conn.cursor()
        evt_seq = 1
        batch = []
        BATCH_SIZE = 5000

        def flush_batch():
            nonlocal batch
            if batch:
                cur.executemany("INSERT INTO event_logs VALUES (?,?,?,?,?,?,?,?,?)", batch)
                db_conn.commit()
                batch = []

        # 1. Sellers: SELLER_ONBOARDED for ALL sellers
        cur.execute("SELECT seller_id, onboarding_date, status FROM sellers ORDER BY seller_id;")
        for s_id, onb_date, status in cur.fetchall():
            batch.append((
                format_event_id(evt_seq),
                "SELLER",
                s_id,
                "SELLER_ONBOARDED",
                None,
                status,
                json.dumps({"onboarding_date": onb_date}),
                EventActor.SYSTEM.value,
                f"{onb_date} 09:00:00"
            ))
            evt_seq += 1
            if len(batch) >= BATCH_SIZE:
                flush_batch()

        # 2. Fulfillments: ALLOCATED, SHIPPED, DELIVERED, RETURNED for ALL fulfillments
        cur.execute("""
            SELECT f.fulfillment_id, f.status, f.carrier, f.tracking_number, f.shipped_at, f.delivered_at, f.returned_at, o.order_date
            FROM fulfillments f
            JOIN orders o ON f.order_id = o.order_id
            ORDER BY f.fulfillment_id;
        """)
        for f_id, status, carrier, trk, shipped_at, delivered_at, returned_at, order_date in cur.fetchall():
            # Allocation event at order placement
            batch.append((
                format_event_id(evt_seq),
                "FULFILLMENT",
                f_id,
                "FULFILLMENT_ALLOCATED",
                None,
                "ALLOCATED",
                json.dumps({"carrier": carrier}),
                EventActor.SYSTEM.value,
                order_date
            ))
            evt_seq += 1
            if len(batch) >= BATCH_SIZE:
                flush_batch()

            # Carrier dispatch event
            if shipped_at:
                batch.append((
                    format_event_id(evt_seq),
                    "FULFILLMENT",
                    f_id,
                    "SHIPMENT_DISPATCHED",
                    "ALLOCATED",
                    "SHIPPED",
                    json.dumps({"carrier": carrier, "tracking_number": trk}),
                    EventActor.WAREHOUSE_OPERATOR.value,
                    shipped_at
                ))
                evt_seq += 1
                if len(batch) >= BATCH_SIZE:
                    flush_batch()

            # Delivery confirmation event
            if delivered_at:
                batch.append((
                    format_event_id(evt_seq),
                    "FULFILLMENT",
                    f_id,
                    "DELIVERY_CONFIRMED",
                    "SHIPPED",
                    "DELIVERED",
                    json.dumps({"delivered_at": delivered_at}),
                    EventActor.SYSTEM.value,
                    delivered_at
                ))
                evt_seq += 1
                if len(batch) >= BATCH_SIZE:
                    flush_batch()

            # Return processing event
            if returned_at:
                batch.append((
                    format_event_id(evt_seq),
                    "FULFILLMENT",
                    f_id,
                    "RETURN_PROCESSED",
                    "DELIVERED",
                    "RETURNED",
                    json.dumps({"returned_at": returned_at}),
                    EventActor.CUSTOMER.value,
                    returned_at
                ))
                evt_seq += 1
                if len(batch) >= BATCH_SIZE:
                    flush_batch()

        # 3. Disputes: DISPUTE_FILED and DISPUTE_RESOLVED for ALL disputes
        cur.execute("SELECT dispute_id, order_line_id, amount, reason, status, opened_at, resolved_at, deducted_from_payout FROM disputes ORDER BY dispute_id;")
        for d_id, ol_id, amt, reason, status, opened_at, resolved_at, deducted in cur.fetchall():
            batch.append((
                format_event_id(evt_seq),
                "DISPUTE",
                d_id,
                "DISPUTE_FILED",
                None,
                "OPEN",
                json.dumps({"order_line_id": ol_id, "amount": amt, "reason": reason}),
                EventActor.CUSTOMER.value,
                opened_at
            ))
            evt_seq += 1
            if len(batch) >= BATCH_SIZE:
                flush_batch()

            if resolved_at:
                batch.append((
                    format_event_id(evt_seq),
                    "DISPUTE",
                    d_id,
                    "DISPUTE_RESOLVED",
                    "OPEN",
                    status,
                    json.dumps({"amount": amt, "deducted_from_payout": deducted}),
                    EventActor.OPS_MANAGER.value,
                    resolved_at
                ))
                evt_seq += 1
                if len(batch) >= BATCH_SIZE:
                    flush_batch()

        # 4. Payouts: PAYOUT_GENERATED and PAYOUT_SETTLED / HOLD_APPLIED for ALL payouts
        cur.execute("SELECT payout_id, seller_id, net_amount, status, created_at, released_at, hold_release_date FROM payouts ORDER BY payout_id;")
        for p_id, s_id, net_amt, status, created_at, released_at, hold_date in cur.fetchall():
            batch.append((
                format_event_id(evt_seq),
                "PAYOUT",
                p_id,
                "PAYOUT_GENERATED",
                None,
                "DRAFT",
                json.dumps({"seller_id": s_id, "net_amount": net_amt, "hold_release_date": hold_date}),
                EventActor.SYSTEM.value,
                created_at
            ))
            evt_seq += 1
            if len(batch) >= BATCH_SIZE:
                flush_batch()

            if status in ("PAID", "APPROVED"):
                batch.append((
                    format_event_id(evt_seq),
                    "PAYOUT",
                    p_id,
                    "PAYOUT_SETTLED",
                    "DRAFT",
                    status,
                    json.dumps({"net_amount": net_amt, "released_at": released_at or created_at}),
                    EventActor.OPS_MANAGER.value,
                    released_at or created_at
                ))
                evt_seq += 1
                if len(batch) >= BATCH_SIZE:
                    flush_batch()
            elif status == "HELD":
                batch.append((
                    format_event_id(evt_seq),
                    "PAYOUT",
                    p_id,
                    "HOLD_APPLIED",
                    "DRAFT",
                    "HELD",
                    json.dumps({"net_amount": net_amt, "reason": "Audit hold"}),
                    EventActor.OPS_MANAGER.value,
                    created_at
                ))
                evt_seq += 1
                if len(batch) >= BATCH_SIZE:
                    flush_batch()

        flush_batch()
        print(f"[+] Inserted {evt_seq - 1:,} complete lifecycle event history log entries (zero sample limits).")

    def _save_ground_truth(self):
        """Save ground truth anomalies to CSV and JSON."""
        self.ground_truth_dir.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "anomaly_id", "issue_type", "target_entity_type", "target_entity_id",
            "seller_id", "expected_financial_impact", "description"
        ]
        csv_path = self.ground_truth_dir / "ground_truth.csv"
        json_path = self.ground_truth_dir / "ground_truth.json"

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.ground_truth)

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self.ground_truth, f, indent=2)

        # If generating full scale, also save ground_truth_full.csv
        if self.scale == "full" and self.ground_truth_dir == DATA_DIR:
            full_csv = DATA_DIR / "ground_truth_full.csv"
            with open(full_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.ground_truth)

def main():
    parser = argparse.ArgumentParser(description="Deterministic synthetic data generator for SellerOps Control Tower")
    parser.add_argument("--scale", choices=["demo", "full"], default="demo", help="Dataset scale: demo (fast start) or full")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"Random seed (default: {DEFAULT_SEED})")
    args = parser.parse_args()

    init_db()
    conn = get_db_connection()
    try:
        generator = DataGenerator(seed=args.seed, scale=args.scale)
        generator.run(conn)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
