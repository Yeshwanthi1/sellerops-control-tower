# SellerOps Control Tower — Source Data Manifest

## 1. Data Provenance & External Data Declaration

> **EXPLICIT DECLARATION:**  
> **No external data sources, third-party datasets, external web scrapers, paid services, AI API keys, or real personal/confidential customer data were used in this project.**
> 
> All entities, transactions, listings, metrics, fulfillments, disputes, customer reviews, event logs, and anomalies are **100% synthetically generated** using a deterministic, parameterized generator implemented in `src/generator.py`.

---

## 2. Generator Configuration & Determinism

- **Generator Script:** `src/generator.py`
- **Fixed Random Seed:** `20261022` (default)
- **PRNG Engine:** Python standard library `random.Random(20261022)`
- **Target Scale Capabilities:**
  - **Starter / Demo Scale (Default for instant app launch):**
    - 50 Sellers
    - 250 Product Listings
    - 1,000 Orders
    - 1,581 Order Lines & Seller Fulfillments
    - 326 Customer Reviews
    - 80 Disputes
    - 200 Payouts
    - 3,151 Payout Lines (Reconciled verified count)
    - 687 Event History Log Entries (5,323 with complete unconstrained event generation)
    - 15 Injected Anomalies (with ground truth labels)
  - **Full Suggested Scale (Available via CLI):**
    - 2,000 Sellers
    - 20,000 Product Listings
    - 100,000 Orders
    - 160,414 Order Lines & Seller Fulfillments
    - 36,091 Customer Reviews
    - 10,000 Disputes
    - 25,000 Payouts
    - 412,068 Payout Lines (Reconciled verified count)
    - 732 Event History Log Entries (535,000+ with complete unconstrained event generation)
    - 15 Injected Anomalies (with ground truth labels)

---

## 3. Synthetic Data Generation Methodology

All attributes are generated using domain-appropriate statistical distributions and business rule derivations rather than independent random assignments:

1. **Sellers:**
   - Tier distribution: Tier 1 (35%), Tier 2 (40%), Tier 3 (15%), Enterprise (10%).
   - Status: Active (88%), Probation (7%), Suspended (5%).
   - Reserve rate and hold windows are derived strictly from seller tier.
2. **Product Listings:**
   - Distributed across 6 core retail categories: Electronics, Apparel, Home & Kitchen, Beauty, Books, Sports.
   - Prices range realistically by category ($15.00 to $350.00).
   - Suspended sellers have listings set to `ARCHIVED` by default (enforcing Rule SEC-01).
3. **Multi-Seller Orders:**
   - 1 to 4 items per order cart, sampled across distinct active seller listings.
   - Order total is strictly the mathematical sum of item line subtotals.
4. **Fulfillments:**
   - One fulfillment record per order line (`FUL-<order-line-id>`).
   - Realistic carrier assignments (FedEx, UPS, DHL, USPS).
   - 88% on-time shipment, 12% late shipment against 2-day ship SLA.
   - 90% on-time delivery, 10% late delivery against 4-day carrier transit SLA.
5. **Customer Reviews:**
   - Verifiable delivery check: reviews are generated only for delivered fulfillments.
   - Late delivery fulfillments correlate with lower ratings (1–3 stars).
6. **Disputes:**
   - Root causes correlate with fulfillment history (damaged box on late delivery, defective item on return).
   - Status breakdown: 65% Upheld, 20% Rejected, 10% Resolved, 5% Open.
7. **Payouts & Reserves:**
   - Payouts are computed strictly for delivered orders whose hold window has elapsed.
   - Formulas:
     $$\text{Gross} = \sum \text{Subtotals}$$
     $$\text{Commission} = \sum (\text{Subtotal} \times \text{Effective Rate})$$
     $$\text{Reserve} = \text{Gross} \times \text{Seller Reserve Rate}$$
     $$\text{Dispute Deduction} = \sum \text{Upheld Disputes}$$
     $$\text{Net} = \text{Gross} - \text{Commission} - \text{Reserve} - \text{Dispute}$$
8. **Anomalies & Ground Truth:**
   - Deliberate anomalies are injected with exact parameters and recorded into `data/ground_truth.csv` and `data/ground_truth.json`.
   - Never referenced in production detection queries.

---

## 4. Dataset Checksum & Verification Manifest

Both starter and full-scale datasets are completely reproducible bit-for-bit from seed `20261022`.

| Table Name | Entity Scope | Demo Row Count | Full Scale Row Count | Generator Target |
| :--- | :--- | :--- | :--- | :--- |
| `sellers` | Merchants | 50 | 2,000 | 2,000 |
| `product_listings` | Catalog Items | 250 | 20,000 | 20,000 |
| `commission_rules`| Rate Schedule | 24 | 24 | Category × Tier |
| `reserve_rules` | Escrow Rules | 4 | 4 | 4 Tiers |
| `orders` | Customer Carts | 1,000 | 100,000 | 100,000 |
| `order_lines` | Multi-Seller Lines | 1,581 | 160,414 | Variable (1–4 per order) |
| `fulfillments` | Seller Shipments | 1,581 | 160,414 | 1 per order line |
| `customer_reviews`| Verified Ratings | 326 | 36,091 | Delivered lines |
| `disputes` | Claims & Chargebacks| 80 | 10,000 | 10,000 |
| `payouts` | Settlements | 200 | 25,000 | Eligible merchants |
| `payout_lines` | Settlement Items | 3,151 | 412,068 | Itemized constituent debits |
| `event_logs` | Audit Trail | 687 (5,323 full lifecycle) | 732 (535,000+ full lifecycle) | System & User transitions |
| `ground_truth.csv`| Benchmark Labels | 15 | 15 | 3 per anomaly class |
