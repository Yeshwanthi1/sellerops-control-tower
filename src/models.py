"""
Domain models, enums, constants, and ID generation utilities for SellerOps Control Tower.
"""
from enum import Enum
from typing import NamedTuple, Optional

# --- Allowed Enum Values ---

class SellerTier(str, Enum):
    TIER_1 = "TIER_1"
    TIER_2 = "TIER_2"
    TIER_3 = "TIER_3"
    ENTERPRISE = "ENTERPRISE"

class SellerStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PROBATION = "PROBATION"
    SUSPENDED = "SUSPENDED"

class ListingStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"

class ProductCategory(str, Enum):
    ELECTRONICS = "Electronics"
    APPAREL = "Apparel"
    HOME_KITCHEN = "Home & Kitchen"
    BEAUTY = "Beauty"
    BOOKS = "Books"
    SPORTS = "Sports"

class OrderStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PARTIALLY_FULFILLED = "PARTIALLY_FULFILLED"
    DELIVERED = "DELIVERED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class FulfillmentStatus(str, Enum):
    ALLOCATED = "ALLOCATED"
    PICKED = "PICKED"
    PACKED = "PACKED"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    RETURNED = "RETURNED"
    FAILED = "FAILED"

class Carrier(str, Enum):
    FEDEX = "FedEx"
    UPS = "UPS"
    DHL = "DHL"
    USPS = "USPS"

class DisputeReason(str, Enum):
    ITEM_NOT_RECEIVED = "ITEM_NOT_RECEIVED"
    ITEM_DEFECTIVE = "ITEM_DEFECTIVE"
    INCORRECT_ITEM = "INCORRECT_ITEM"
    UNAUTHORIZED_CHARGE = "UNAUTHORIZED_CHARGE"
    LATE_DELIVERY = "LATE_DELIVERY"

class DisputeStatus(str, Enum):
    OPEN = "OPEN"
    UNDER_REVIEW = "UNDER_REVIEW"
    UPHELD = "UPHELD"
    REJECTED = "REJECTED"
    RESOLVED = "RESOLVED"

class PayoutStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    PROCESSING = "PROCESSING"
    PAID = "PAID"
    HELD = "HELD"

class PayoutLineType(str, Enum):
    GROSS_SALES = "GROSS_SALES"
    COMMISSION_FEE = "COMMISSION_FEE"
    RESERVE_HOLD = "RESERVE_HOLD"
    DISPUTE_DEDUCTION = "DISPUTE_DEDUCTION"

class EventActor(str, Enum):
    SYSTEM = "SYSTEM"
    WAREHOUSE_OPERATOR = "WAREHOUSE_OPERATOR"
    CUSTOMER = "CUSTOMER"
    OPS_MANAGER = "OPS_MANAGER"
    DISPUTE_AGENT = "DISPUTE_AGENT"

class AnomalyIssueType(str, Enum):
    PAYOUT_BEFORE_HOLD_RELEASE = "PAYOUT_BEFORE_HOLD_RELEASE"
    COMMISSION_APPLIED_TWICE = "COMMISSION_APPLIED_TWICE"
    SUSPENDED_SELLER_LISTING = "SUSPENDED_SELLER_LISTING"
    DISPUTE_NOT_DEDUCTED = "DISPUTE_NOT_DEDUCTED"
    PAYOUT_TOTAL_MISMATCH = "PAYOUT_TOTAL_MISMATCH"

# --- Exact ID Formatting Functions ---

def format_seller_id(seq: int) -> str:
    """Format: SELL-000001"""
    return f"SELL-{seq:06d}"

def format_listing_id(seller_id: str, seq: int) -> str:
    """Format: LIST-<seller-id>-000001 (e.g. LIST-SELL-000001-000001)"""
    return f"LIST-{seller_id}-{seq:06d}"

def format_order_id(seq: int, year: int = 2026) -> str:
    """Format: ORD-2026-000001"""
    return f"ORD-{year}-{seq:06d}"

def format_order_line_id(order_id: str, line_seq: int) -> str:
    """Format: LINE-2026-000001-01"""
    suffix = order_id.replace("ORD-", "")
    return f"LINE-{suffix}-{line_seq:02d}"

def format_fulfillment_id(order_line_id: str) -> str:
    """Format: FUL-<order-line-id> (e.g. FUL-LINE-2026-000001-01)"""
    return f"FUL-{order_line_id}"

def format_dispute_id(seq: int, year: int = 2026) -> str:
    """Format: DSP-2026-000001"""
    return f"DSP-{year}-{seq:06d}"

def format_payout_id(seq: int, year: int = 2026) -> str:
    """Format: PAYOUT-2026-000001"""
    return f"PAYOUT-{year}-{seq:06d}"

def format_payout_line_id(payout_id: str, line_seq: int) -> str:
    """Format: PAYLINE-2026-000001-01"""
    suffix = payout_id.replace("PAYOUT-", "")
    return f"PAYLINE-{suffix}-{line_seq:02d}"

def format_review_id(seq: int, year: int = 2026) -> str:
    """Format: REV-2026-000001"""
    return f"REV-{year}-{seq:06d}"

def format_commission_rule_id(seq: int) -> str:
    """Format: RULE-000001"""
    return f"RULE-{seq:06d}"

def format_reserve_rule_id(seq: int) -> str:
    """Format: RES-000001"""
    return f"RES-{seq:06d}"

def format_event_id(seq: int, year: int = 2026) -> str:
    """Format: EVT-2026-000001"""
    return f"EVT-{year}-{seq:06d}"
