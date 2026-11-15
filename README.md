# SellerOps Control Tower

> **SellerOps Control Tower** is an enterprise-grade marketplace operations intelligence system built to monitor seller service levels (SLAs), multi-seller fulfillment workflows, disputes, effective commissions, rolling risk reserves, and payout reconciliation. It autonomously audits and surfaces financial anomalies and compliance exceptions while maintaining complete, immutable traceability.

---

## 1. Quick Start Guide (Windows)

The application has **zero external package dependencies** and runs natively on Windows using Python 3.8+ standard library and SQLite.

### Option A: One-Click Launch (Recommended)
Double-click `run.bat` or run in Command Prompt / PowerShell:
```cmd
run.bat
```
This automatically verifies the database, initializes the quick-start sample if needed, and starts the server at `http://127.0.0.1:8000/`.

### Option B: Manual Launch
1. Ensure your current working directory is the project root directory.
2. Start the Control Tower server:
   ```cmd
   python src\server.py
   ```
3. Open your browser and navigate to:
   ```text
   http://127.0.0.1:8000/
   ```

*(Note: If FastAPI and Uvicorn are installed, you may also launch via `uvicorn src.server:app --port 8000`)*.

---

## 2. Dataset Generation Commands

The data generator is parameterized and deterministic with fixed seed `20261022`.

### Quick-Start Demo Dataset (Default, Instant App Launch)
Generates in $\sim 1.2$ seconds with 50 sellers, 250 listings, 1,000 orders, and 80 disputes:
```cmd
python src\generator.py --scale demo --seed 20261022
```

### Full-Scale Dataset (Target Enterprise Benchmark)
Generates 2,000 sellers, 20,000 listings, 100,000 orders, 10,000 disputes, and 25,000 payouts in $\sim 35$ seconds:
```cmd
python src\generator.py --scale full --seed 20261022
```
*(A pre-generated full-scale copy is also archived at `data\sellerops_full.db`)*.

---

## 3. Automated Validation & Reproducibility Commands

Run all automated integrity and reproducibility checks from the command line:

### 1. Integrity & Business Rule Verification
Verifies Primary Key uniqueness, Foreign Key referential integrity, enum/domain rules, chronological date ordering, and arithmetic reconciliation:
```cmd
python tests\validate_integrity.py
```

### 2. Bit-for-Bit Deterministic Reproducibility
Runs two independent generations into isolated databases and validates row counts and table-level SHA-256 hashes:
```cmd
python tests\verify_reproducibility.py
```

### 3. Rules Engine & Anomaly Detection Evaluation
Audits database records autonomously and scores precision, recall, and F1 against `data\ground_truth.csv`:
```cmd
python src\rules_engine.py
```

### 4. Full Data Exports (CSV, JSON, SQL)
Generates complete exports in `exports\csv\`, `exports\json\`, and `exports\sql\`:
```cmd
python src\exporter.py
```

---

## 4. System Architecture

The solution implements a strict 3-tier architecture:

```text
├── Presentation Tier (Vanilla HTML5, Modern CSS3, ES6 JavaScript)
│   ├── Operations Dashboard (Overview KPIs, Seller Metrics, SLA Rates, Financials)
│   ├── Demo Role Selector (Operations Manager, Warehouse Operator, Analyst, Customer)
│   ├── Fulfillment Operations Work Queue (Pick, Pack, Ship, Carrier Dispatch)
│   ├── Exception Queue (Severity, Rules, Evidence, Remediation Actions)
│   └── Evaluation & Ground Truth Comparison View (Precision, Recall, F1 Matrix)
│
├── Application Tier (Python 3.11 Runtime)
│   ├── Threading REST API Server (src/server.py)
│   ├── Business Rules Engine (Commissions, Reserves, Eligibility) (src/rules_engine.py)
│   ├── Autonomous Anomaly Auditor (src/rules_engine.py)
│   └── Data Exporters (src/exporter.py)
│
└── Data Tier (SQLite Relational Persistence & Exports)
    ├── Relational Database (data/sellerops.db)
    ├── Event History Audit Logs (Immutable chronological transitions)
    ├── Isolated Ground Truth (data/ground_truth.csv / json)
    └── File Exports (exports/csv/, exports/json/, exports/sql/)
```

---

## 5. Exact ID Formats

All primary keys strictly follow zero-padded immutable formats:

| Entity | ID Format | Example |
| :--- | :--- | :--- |
| **Seller** | `SELL-XXXXXX` | `SELL-000001` |
| **Product Listing** | `LIST-<seller-id>-XXXXXX` | `LIST-SELL-000001-000001` |
| **Order** | `ORD-YYYY-XXXXXX` | `ORD-2026-000001` |
| **Order Line** | `LINE-YYYY-XXXXXX-ZZ` | `LINE-2026-000001-01` |
| **Fulfillment** | `FUL-<order-line-id>` | `FUL-LINE-2026-000001-01` |
| **Customer Review** | `REV-YYYY-XXXXXX` | `REV-2026-000001` |
| **Dispute** | `DSP-YYYY-XXXXXX` | `DSP-2026-000001` |
| **Payout** | `PAYOUT-YYYY-XXXXXX` | `PAYOUT-2026-000001` |
| **Payout Line** | `PAYLINE-YYYY-XXXXXX-ZZ`| `PAYLINE-2026-000001-01` |
| **Commission Rule** | `RULE-XXXXXX` | `RULE-000001` |
| **Reserve Rule** | `RES-XXXXXX` | `RES-000001` |
| **Event History Log** | `EVT-YYYY-XXXXXX` | `EVT-2026-000001` |

---

## 6. Business Rules & Anomaly Classes

### Core Business Rules
- **Effective Commission Schedules:** Resolved dynamically from category and seller tier schedules; falls back to category defaults.
- **Rolling Risk Reserves:** Tier-based escrow holds (Enterprise 4% / 7 days, Tier 1 6% / 7 days, Tier 2 9% / 14 days, Tier 3 12% / 21 days).
- **Payout Settlement Eligibility:** Released only after fulfillment delivery and hold period expiration ($\text{delivery\_date} + \text{hold\_period\_days} \le \text{today}$).
- **Reconciliation Formula:**
  $$\text{Net Payout} = \text{Gross Item Subtotals} - \text{Commissions} - \text{Reserves Held} - \text{Upheld Disputes}$$

### Detected Anomaly Classes & Rules
1. `PAYOUT_BEFORE_HOLD_RELEASE` (`Rule FIN-01`): Funds released before delivery or prior to hold release date.
2. `COMMISSION_APPLIED_TWICE` (`Rule FIN-02`): Order line incurred multiple commission deduction lines or doubled commission fee.
3. `SUSPENDED_SELLER_LISTING` (`Rule SEC-01`): Suspended seller continues maintaining active listings or trading.
4. `DISPUTE_NOT_DEDUCTED` (`Rule DISP-01`): Upheld customer dispute was not deducted from seller payout settlement.
5. `PAYOUT_TOTAL_MISMATCH` (`Rule REC-01`): Payout header net amount does not equal the mathematical sum of its constituent payout lines.

---

## 7. REST API Endpoints

The system exposes a comprehensive JSON API at `http://127.0.0.1:8000/api/`:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Healthcheck and database status. |
| `GET` | `/api/summary` | Top-level KPIs (GMV, SLA %, disputes, payable, held, exceptions). |
| `GET` | `/api/sellers` | List sellers with filtering by tier, status, and search query. |
| `GET` | `/api/sellers/{id}` | Detailed seller scorecard, listings, fulfillments, and payouts. |
| `GET` | `/api/listings` | Product catalog with seller info and categories. |
| `GET` | `/api/orders` | Order headers with line item count and status. |
| `GET` | `/api/orders/{id}` | Order details partitioned across multi-seller lines with fulfillments. |
| `GET` | `/api/fulfillments` | Fulfillment work queue with status and carrier filtering. |
| `POST`| `/api/fulfillments/{id}/update-status`| Advance status (Pick $\rightarrow$ Pack $\rightarrow$ Ship $\rightarrow$ Deliver). |
| `GET` | `/api/reviews` | Verified buyer customer reviews. |
| `GET` | `/api/disputes` | Dispute claims with status and root cause. |
| `POST`| `/api/disputes/{id}/resolve`| Resolve dispute (`UPHELD`, `REJECTED`, `RESOLVED`). |
| `GET` | `/api/payouts` | Payout statements with gross, deductions, and net amount. |
| `GET` | `/api/payouts/{id}` | Detailed payout breakdown with constituent lines. |
| `POST`| `/api/payouts/{id}/action`| Governance actions (`HOLD`, `APPROVE`, `AUDIT`). |
| `GET` | `/api/exceptions` | Operational exceptions detected by autonomous rules engine. |
| `GET` | `/api/evaluation` | Evaluation metrics (Precision, Recall, F1) vs `ground_truth.csv`. |
| `GET` | `/api/events` | Immutable audit trail / event history log. |
| `GET` | `/api/export/{csv\|json\|sql\|all}`| Generate on-demand data exports. |

---

## 8. GitHub Upload Suitability & Large File Management

To ensure compliance with GitHub file size constraints (50 MB warning threshold, 100 MB hard rejection limit), the repository is configured via `.gitignore` to track all source code, tests, documentation, and benchmark labels while keeping generated binaries and oversized datasets local:

### Files Tracked & Upload-Ready (< 200 KB Total)
- All Python source modules (`src/*.py`) and frontend dashboard assets (`src/static/*`).
- Test suites (`tests/*.py`) and launcher scripts (`run.bat`).
- All technical documentation (`README.md`, `ARCHITECTURE.md`, `SCHEMA.md`, `SOURCE_MANIFEST.md`, `VALIDATION_SUMMARY.md`).
- Ground truth benchmark files (`data/ground_truth.csv`, `data/ground_truth.json`).

### Oversized Generated Files Kept Local (Ignored by Git)
| File / Directory | Local Size | Reason for Git Exclusion |
| :--- | :---: | :--- |
| `data/sellerops_full.db` | ~200.5 MB | Exceeds GitHub 100 MB hard limit. |
| `exports/full_scale/sql/sellerops_dump.sql` | ~162.7 MB | Exceeds GitHub 100 MB hard limit. |
| `exports/full_scale/json/*.json` | ~260.0 MB | High-volume JSON exports exceed recommended limits. |
| `exports/full_scale/csv/*.csv` | ~120.0 MB | Redundant generated bulk exports. |
| `data/*.db` | Variable | Local SQLite database instances. |

### How to Regenerate Local Datasets Post-Clone
1. **Quick-Start Starter Dataset (Demo scale):**
   ```cmd
   python src\generator.py --scale demo --seed 20261022
   ```
2. **Full-Scale Enterprise Dataset (100,000 orders):**
   ```cmd
   python src\generator.py --scale full --seed 20261022
   ```
3. **Full-Scale Exports (CSV, JSON, SQL):**
   ```cmd
   python src\exporter.py --full
   ```

---

## 9. Workspace Directory Structure

```text
sellerops-control-tower/ (or your cloned repository root)
├── data/
│   ├── sellerops.db                # Default quick-start database
│   ├── sellerops_full.db           # Full-scale archive (100k orders)
│   ├── ground_truth.csv            # Ground truth anomaly benchmark
│   └── ground_truth.json           # JSON format benchmark labels
├── samples/                        # Tracked lightweight samples for GitHub
│   ├── csv/                        # Sample CSV files (10 rows each)
│   ├── json/                       # Sample JSON files (10 records each)
│   ├── sql/                        # Sample DDL + INSERT SQL script
│   └── README.md                   # Sample dataset documentation
├── exports/                        # Local generated bulk exports
│   ├── csv/                        # Table-by-table CSV exports
│   ├── json/                       # Table-by-table JSON exports
│   └── sql/
│       └── sellerops_dump.sql      # Full SQLite schema & INSERT dump
├── src/
│   ├── __init__.py
│   ├── config.py                   # Dynamic paths, seed, and scale configs
│   ├── database.py                 # SQLite DDL schema and connection
│   ├── generator.py                # Deterministic synthetic data generator
│   ├── models.py                   # Enums, data classes, ID formatters
│   ├── rules_engine.py             # Rules, reconciliation, auditor, evaluator
│   ├── exporter.py                 # CSV, JSON, SQL dump export routines
│   ├── server.py                   # Zero-dependency HTTP REST & dashboard server
│   └── static/
│       ├── index.html              # Operations dashboard UI with pagination
│       ├── app.js                  # Frontend client logic & role manager
│       └── styles.css              # Modern responsive CSS styling
├── tests/
│   ├── validate_integrity.py       # Comprehensive 9-category integrity validator
│   ├── verify_reproducibility.py   # Dual-run bit-for-bit SHA-256 verifier
│   └── test_server_api.py          # Real live HTTP endpoint and action tests
├── scripts/
│   └── generate_samples.py         # Tracked sample generator utility
├── run.bat                         # Portable Windows one-click launcher
├── README.md                       # Complete guide & documentation
├── ARCHITECTURE.md                 # 3-tier system architecture document
├── SCHEMA.md                       # Comprehensive data dictionary
├── SOURCE_MANIFEST.md              # Reconciled data manifest & provenance
└── VALIDATION_SUMMARY.md           # Integrity, reproducibility & test report
```
