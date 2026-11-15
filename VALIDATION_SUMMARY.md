# SellerOps Control Tower — Validation & Reproducibility Summary

This report documents the automated integrity verification, bit-for-bit reproducibility tests, and autonomous anomaly detection evaluation conducted on the **SellerOps Control Tower** project.

---

## 1. Automated Integrity & Business Rule Verification

The test suite `tests/validate_integrity.py` executes 9 exhaustive categories of data integrity and business rule checks against the relational database.

### 1.1 Test Results Summary

| Check Category | Verification Scope | Status | Result & Notes |
| :--- | :--- | :---: | :--- |
| **Primary Key Uniqueness** | All 13 tables (`sellers`, `orders`, `fulfillments`, `payouts`, etc.) | **PASS** | 100% unique primary keys across all tables; 0 duplicate IDs. |
| **Foreign Key Integrity** | `PRAGMA foreign_key_check` + explicit referential join checks | **PASS** | 0 orphan records; all child foreign keys resolve to valid parents. |
| **Allowed Values & Enums** | 12 domain columns (`tier`, `status`, `category`, `carrier`, `reasons`) | **PASS** | Strict adherence to documented schema enum constraints. |
| **Chronological Date Ordering**| Order $\le$ Shipped $\le$ Delivered $\le$ Hold Release $\le$ Payout | **PASS** | 0 chronological inversions; valid timestamps across lifecycles. |
| **Arithmetic Reconciliation** | Line Subtotals, Order Totals, Payout Formulas | **PASS** | `line.subtotal == qty * price`; `order.total == sum(lines)`; variance: $0.00. |
| **Baseline & Anomalous Payouts**| Payout header $\text{net\_amount} = \sum \text{payout\_lines.amount}$ | **PASS** | Baseline payouts match line sums with $0.00 variance; anomalies exhibit planned variance. |
| **Lifecycle State Transitions**| `DELIVERED` has delivery timestamps; `RETURNED` has return times | **PASS** | All lifecycle states possess required chronological attributes. |
| **Strict ID Format Rules** | `SELL-XXXXXX`, `LIST-SELL-XXXXXX-XXXXXX`, `ORD-2026-XXXXXX`, `PAYLINE-2026-` | **PASS** | All IDs strictly follow zero-padded required regex patterns. |
| **Cross-Table Consistency & Status**| Seller/Listing/Order alignment & Suspended seller listing rules | **PASS** | 100% cross-table relational consistency; suspended seller listings match ground truth anomalies. |

---

## 2. Deterministic Reproducibility Verification

The reproducibility verifier `tests/verify_reproducibility.py` generates the entire dataset twice into two completely isolated SQLite databases (`test_repro_1.db` and `test_repro_2.db`) using fixed seed `20261022`.

### 2.1 Full-Scale Benchmark Reproducibility (100,000 Orders)

Command executed: `python tests/verify_reproducibility.py --scale full`

For every table, rows are extracted ordered by primary key, canonically serialized, and hashed using SHA-256:

| Relational Table | Run 1 Rows | Run 2 Rows | Row Delta | SHA-256 Hash Match? | SHA-256 Digest (First 24 chars) |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `sellers` | 2,000 | 2,000 | 0 | **MATCH** | `7ae71c92a02ec0d86927d63c...` |
| `product_listings` | 20,000 | 20,000 | 0 | **MATCH** | `b2bcfeec4103843eebc3f870...` |
| `commission_rules` | 24 | 24 | 0 | **MATCH** | `b8d6c6a95f7e3f5cbf5d09ec...` |
| `reserve_rules` | 4 | 4 | 0 | **MATCH** | `54277d7fb5f169b3620df946...` |
| `orders` | 100,000 | 100,000 | 0 | **MATCH** | `d23bec982c726fcad32f7881...` |
| `order_lines` | 160,414 | 160,414 | 0 | **MATCH** | `6a6baea966256129994c6bc2...` |
| `fulfillments` | 160,414 | 160,414 | 0 | **MATCH** | `335f5c5f31f26da35e6cae82...` |
| `customer_reviews` | 36,091 | 36,091 | 0 | **MATCH** | `dea10f0cd2a63295db2888ee...` |
| `disputes` | 10,000 | 10,000 | 0 | **MATCH** | `73eaef5e15829ffec356c9a3...` |
| `payouts` | 25,000 | 25,000 | 0 | **MATCH** | `7506d6a18c2d00a20bf781e4...` |
| `payout_lines` | 412,068 | 412,068 | 0 | **MATCH** | `1a5f14509ccc729f2da51610...` |
| `event_logs` | 732 | 732 | 0 | **MATCH** | `9d46910260297ea7aaef58a2...` |

### 2.2 Demo Starter Scale Reproducibility (1,000 Orders)

Command executed: `python tests/verify_reproducibility.py --scale demo`

| Relational Table | Run 1 Rows | Run 2 Rows | Row Delta | SHA-256 Hash Match? | SHA-256 Digest (First 24 chars) |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `sellers` | 50 | 50 | 0 | **MATCH** | `ba6757e55c7a54157d620573...` |
| `product_listings` | 250 | 250 | 0 | **MATCH** | `c0af80c8de8d8869c3a3fe46...` |
| `commission_rules` | 24 | 24 | 0 | **MATCH** | `b8d6c6a95f7e3f5cbf5d09ec...` |
| `reserve_rules` | 4 | 4 | 0 | **MATCH** | `54277d7fb5f169b3620df946...` |
| `orders` | 1,000 | 1,000 | 0 | **MATCH** | `cd1e19ef62c80150d188099c...` |
| `order_lines` | 1,581 | 1,581 | 0 | **MATCH** | `ad2f6aa2fb708f310f85882b...` |
| `fulfillments` | 1,581 | 1,581 | 0 | **MATCH** | `4b7d33976dc6662eb74f38fe...` |
| `customer_reviews` | 326 | 326 | 0 | **MATCH** | `130653f93926ea6b6efd8d6d...` |
| `disputes` | 80 | 80 | 0 | **MATCH** | `5017d1b0dcadc7ca23955627...` |
| `payouts` | 200 | 200 | 0 | **MATCH** | `b324aec59a3f1eb6289d04ba...` |
| `payout_lines` | 3,151 | 3,151 | 0 | **MATCH** | `ea563fb7a97bc9f182c16132...` |
| `event_logs` | 5,323 | 5,323 | 0 | **MATCH** | `d79c7289cedf81116a4f91bb...` |

**Conclusion:** The generation pipeline is **100% bit-for-bit deterministic and reproducible across both starter and full scales**.

---

## 3. Autonomous Anomaly Detection & Ground Truth Evaluation

The operational auditor in `src/rules_engine.py` audits transactional records using pure business rules without reading `ground_truth.csv`.

The evaluation module compares detected exceptions against the benchmark labels in `ground_truth.csv`:

### 3.1 Overall Confusion Matrix & Scoring

$$\text{Precision} = \frac{\text{TP}}{\text{TP} + \text{FP}} = \frac{15}{15 + 0} = \mathbf{1.0000} \;(100.0\%)$$
$$\text{Recall} = \frac{\text{TP}}{\text{TP} + \text{FN}} = \frac{15}{15 + 0} = \mathbf{1.0000} \;(100.0\%)$$
$$\text{F1 Score} = 2 \times \frac{\text{Precision} \times \text{Recall}}{\text{Precision} + \text{Recall}} = \mathbf{1.0000}$$

- **True Positives (TP):** 15 (Correctly identified violations)
- **False Positives (FP):** 0 (Zero spurious alarms)
- **False Negatives (FN):** 0 (Zero missed violations)

### 3.2 Performance Breakdown by Anomaly Category

| Anomaly Issue Type | Injected | Detected | TP | FP | FN | Precision | Recall | F1 Score |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `PAYOUT_BEFORE_HOLD_RELEASE` | 3 | 3 | 3 | 0 | 0 | 100% | 100% | 1.0000 |
| `COMMISSION_APPLIED_TWICE` | 3 | 3 | 3 | 0 | 0 | 100% | 100% | 1.0000 |
| `SUSPENDED_SELLER_LISTING` | 3 | 3 | 3 | 0 | 0 | 100% | 100% | 1.0000 |
| `DISPUTE_NOT_DEDUCTED` | 3 | 3 | 3 | 0 | 0 | 100% | 100% | 1.0000 |
| `PAYOUT_TOTAL_MISMATCH` | 3 | 3 | 3 | 0 | 0 | 100% | 100% | 1.0000 |
| **Total** | **15** | **15** | **15** | **0** | **0** | **100%** | **100%** | **1.0000** |

---

## 4. Operational Limitations & Edge Cases

1. **Local SQLite Concurrency:** SQLite is configured with WAL mode and normal synchronization for fast single-instance operations. In multi-server enterprise clustering, migration to PostgreSQL with distributed connection pools would be recommended.
2. **Offline Web Standards:** The frontend does not pull fonts or scripts from public CDNs. It renders fully offline on any modern browser.
3. **Synthetic Scale Performance:** Generating the full scale of 100,000 orders takes ~35–45 seconds on standard Windows hardware. The demo scale (1,000 orders) generates in ~1.2 seconds for instantaneous evaluation.
