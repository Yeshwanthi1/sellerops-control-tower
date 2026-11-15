# SellerOps Control Tower — Tracked Samples

This directory contains small, lightweight samples of all 12 core operational tables in CSV, JSON, and SQL formats.
These samples are committed to version control to allow instant inspection without including bulky local databases (`*.db`) or full-scale exports (`exports/`).

## Relational Closure & Foreign Key Integrity
The sample records form a complete relational closure:
- Every child entity foreign key points to a valid parent record included in the sample.
- `sql/sellerops_sample.sql` includes `PRAGMA foreign_keys = ON;` and inserts tables in topological dependency order (`sellers` -> `orders` -> `product_listings` -> `payouts` -> `order_lines` -> `fulfillments`, `reviews`, `disputes`, `payout_lines`).
- Verified to load cleanly into a fresh SQLite database with **0 foreign key violations**.

## Sample Table Row Counts
| Table Name | Entity Scope | Sample Rows |
| :--- | :--- | :---: |
| `sellers` | Parent Merchants | 16 |
| `commission_rules` | Commission Schedule | 24 |
| `reserve_rules` | Escrow Tiers | 4 |
| `orders` | Parent Carts | 46 |
| `product_listings` | Catalog Items | 23 |
| `payouts` | Settlements | 5 |
| `order_lines` | Multi-Seller Line Items | 52 |
| `fulfillments` | Seller Shipments | 52 |
| `customer_reviews` | Verified Ratings | 10 |
| `disputes` | Claims & Chargebacks | 17 |
| `payout_lines` | Settlement Debits/Credits | 110 |
| `event_logs` | Audit Trail | 21 |

## Regeneration Commands
To regenerate local datasets and exports from the fixed deterministic seed `20261022`:

```bash
# 1. Regenerate starter/demo dataset (50 sellers, 1,000 orders):
python src/generator.py --scale demo --seed 20261022

# 2. Regenerate full-scale dataset (2,000 sellers, 100,000 orders):
python src/generator.py --scale full --seed 20261022

# 3. Export demo scale to CSV, JSON, and SQL:
python src/exporter.py

# 4. Export full scale to CSV, JSON, and SQL:
python src/exporter.py --full
```
