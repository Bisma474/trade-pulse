# TradePulse
## Project Initiation Document (PID)

**End-to-End Financial Trading Data Pipeline & Medallion Analytics Lakehouse**

---

| | |
|---|---|
| **Course** | Big Data |
| **Program** | BS Data Science |
| **University** | Punjab University College of Information Technology (PUCIT) |
| **Term** | Fall 2026 |
| **Instructor** | _<instructor name>_ |
| **Submission Date** | _<date>_ |
| **Document Version** | 1.0 |

### Group Members

| # | Name | Roll No. | Primary Role |
|---|---|---|---|
| 1 | Bisma Munir | BSDSF23M005 | Data Engineer & Dashboard Lead |
| 2 | Naimah Rehman | BSDSF23M011 | Backend Developer & DevOps Lead |

---

## Table of Contents

1. Executive Summary
2. Problem Statement & Motivation
3. Project Objectives
4. Scope
5. Domain & Use Case
6. System Architecture
7. Data Strategy & Sources
8. Relational Schema Design (OLTP)
9. Technology Stack & Justification
10. Big Data Concepts Coverage
11. Medallion Architecture (Bronze / Silver / Gold)
12. Dimensional Model (Gold Layer Star Schema)
13. Data Volume Plan — 1 Million Records
14. Deployment Strategy — Blue-Green
15. Testing & Code Quality Strategy
16. Analytics & Dashboard Deliverables
17. Team Roles & Responsibilities
18. Timeline & Milestones
19. Risk Assessment
20. Expected Deliverables
21. Success Criteria
22. References

---

## 1. Executive Summary

TradePulse is a cloud-native **quantitative trading platform and data engineering pipeline**. It exposes a REST API through which traders place buy/sell orders, the transactional records are persisted in a relational database, and the accumulated trade history is then processed through a **Medallion Architecture (Bronze → Silver → Gold)** into an **analytical star schema** that powers a business intelligence dashboard.

The project deliberately covers the complete modern big data lifecycle in one continuous, verifiable pipeline:

> API ingestion → relational storage → 1M+ record scale → lakehouse transformation → dimensional model → analytics dashboard, all delivered through automated testing, containerization, CI/CD with a static-analysis quality gate, and a zero-downtime cloud deployment.

Rather than selecting a generic retail or messaging use case, the project uses **quantitative finance** as its domain. This choice is justified because financial market data is genuinely high-volume and time-series in nature, because system downtime in a trading system has direct monetary consequences (which makes blue-green deployment a real requirement rather than an academic checkbox), and because risk/portfolio analytics naturally produce the numeric facts and descriptive dimensions required by dimensional modelling.

---

## 2. Problem Statement & Motivation

### 2.1 The Problem

Retail and small-scale trading activity generates a high-volume stream of transactional records, but this data is almost always left in its raw operational form. Three concrete gaps motivate this project:

1. **Raw transactional data is not analytical.** An order-book table answers "what happened" but cannot answer "which sector generated the most traded value last quarter" without expensive, repeated joins over millions of rows.
2. **Scale degrades naive reporting.** Once the trade table grows into the millions of rows, dashboards that query the OLTP database directly become slow and begin to compete with live transaction processing for resources.
3. **Deployment downtime is unacceptable in finance.** A retail trading service that goes offline for even a few minutes during a release can miss order executions, produce stale quotes, and create a direct financial and reputational loss.

### 2.2 The Solution

TradePulse solves these gaps by separating the pipeline into clear layers:

- The **API + relational database** remain optimised for fast transactional writes (OLTP).
- A **Medallion pipeline** extracts that operational data into an S3 lakehouse, progressively cleans and enriches it, and finally materialises a **dimensional star schema** (Gold layer) optimised for analytical reads (OLAP).
- The **dashboard** queries only the Gold layer, so it stays fast regardless of how large the transactional table becomes.
- **Blue-green deployment** guarantees that releasing a new version never interrupts live traffic.

---

## 3. Project Objectives

| # | Objective | Measure of Success |
|---|---|---|
| O1 | Design a normalised relational schema for a trading platform | 5+ related tables, documented ERD, referential integrity enforced |
| O2 | Implement a REST API for trading operations | 6+ functional endpoints, OpenAPI docs auto-generated at `/docs` |
| O3 | Achieve automated test and style compliance | pytest suite passing, flake8 clean (exit code 0) |
| O4 | Package the service for portable deployment | Multi-stage Dockerfile + docker-compose running API and DB together |
| O5 | Automate quality gating and release | GitHub Actions pipeline: lint → test → SonarQube gate → image push |
| O6 | Deploy with zero downtime | Blue-green release on AWS with health-checked traffic switch and rollback |
| O7 | Operate at realistic data scale | **1,000,000+ synthetic trade records** loaded into AWS RDS |
| O8 | Implement a lakehouse medallion pipeline | Working Bronze, Silver and Gold layers in S3 |
| O9 | Deliver an analytical model, not raw tables | Gold star schema: 3 dimension tables + 1 fact table |
| O10 | Deliver decision-support analytics | Streamlit dashboard with KPIs and 4+ visualisations on Gold data |

---

## 4. Scope

### 4.1 In Scope

- Relational schema design and DDL for the trading domain
- FastAPI REST service (stocks, orders, portfolios, health, batch ingestion)
- Unit + integration testing with pytest; linting with flake8
- Multi-stage Docker build and a local docker-compose stack
- GitHub Actions CI/CD with SonarQube/SonarCloud quality gate
- AWS deployment: RDS PostgreSQL, S3 lakehouse, ECS Fargate, ALB, blue-green traffic shift
- Synthetic data generation at 1M+ record scale
- PySpark/AWS Glue Medallion ETL (Bronze → Silver → Gold)
- Star schema dimensional model in the Gold layer
- Streamlit analytics dashboard

### 4.2 Out of Scope

- Real money movement, brokerage licences, or live exchange connectivity
- Real-time streaming ingestion (Kafka/Kinesis) — batch ingestion is used
- Machine learning price prediction or forecasting models
- Mobile or web front-end beyond the analytical dashboard
- User authentication and payment gateway integration
- Multi-region disaster recovery

The exclusion of ML is a deliberate design decision: the Gold layer's deliverable is a **dimensional model** for reporting, which is the standard analytical end-state for a data engineering project. This keeps the scope achievable within the term while remaining architecturally complete.

---

## 5. Domain & Use Case

**Domain:** Quantitative finance / retail trading systems.

TradePulse models a simplified electronic trading platform. A trader holds a portfolio, places buy or sell orders on listed stocks, and each fulfilled order produces an executed trade with price, quantity, commission and realised profit/loss.

**Core entities and their business meaning:**

- **Trader** — the account holder, classified by risk appetite
- **Stock** — a listed security belonging to a sector
- **Portfolio** — a trader's holdings and cash balance
- **Order** — an instruction to buy or sell (may be pending, filled or cancelled)
- **Trade** — the executed result of an order, with actual price and timestamp

**Why this domain fits the course:**

| Requirement | How the trading domain satisfies it |
|---|---|
| High data volume | Market activity produces thousands of trades per trading day |
| Time-series character | Every trade carries an execution timestamp, enabling trend analysis |
| Clear analytical questions | Volume by sector, peak trading hours, trader profitability, P&L trends |
| Real downtime cost | Financial services are the canonical example of downtime-sensitive systems |
| Natural fact/dimension split | Trades (facts) described by stock, trader and calendar (dimensions) |
| No hardware dependency | All data is software-generated or publicly available market data |

---

## 6. System Architecture

```
                        ┌──────────────────────────┐
                        │      Client / Tester     │
                        └────────────┬─────────────┘
                                     │ REST (JSON)
                                     ▼
                     ┌───────────────────────────────┐
                     │   FastAPI Service (Docker)    │
                     │  /health  /stocks  /orders    │
                     │  /portfolios  /data/ingest    │
                     └───────┬───────────────┬───────┘
                             │               │
             transactional   │               │  health check
                writes       │               │  (ALB target group)
                             ▼               ▼
              ┌──────────────────────┐  ┌──────────────────────────┐
              │  AWS RDS PostgreSQL  │  │  AWS ECS Fargate         │
              │  (OLTP, 1M+ trades)  │  │  Blue ▲   Green ▲        │
              └──────────┬───────────┘  │  via ALB + CodeDeploy    │
                         │              └──────────────────────────┘
                         │ batch extract
                         ▼
              ┌──────────────────────────────────────────┐
              │           AWS S3 Data Lake               │
              │  bronze/  raw Parquet, as-is             │
              │  silver/  cleaned, deduped, enriched     │
              │  gold/    star schema (facts + dims)     │
              └──────────────────┬───────────────────────┘
                                 │ PySpark / AWS Glue
                                 ▼
                    ┌────────────────────────────┐
                    │  Streamlit Dashboard       │
                    │  KPIs, trends, leaderboards│
                    └────────────────────────────┘
```

**Flow in words:**

1. The client calls the FastAPI REST endpoints.
2. Transactional records are written to AWS RDS PostgreSQL.
3. A batch extract copies raw rows from RDS to the S3 **Bronze** layer as Parquet.
4. A transformation job cleans and conforms the data into the S3 **Silver** layer.
5. A modelling job builds the star schema in the S3 **Gold** layer.
6. The Streamlit dashboard reads only Gold-layer data and renders analytics.

---

## 7. Data Strategy & Sources

The project does not depend on any paid vendor, private dataset, or physical sensor hardware. All data is obtained through software:

| Data | Source | Method |
|---|---|---|
| Stock reference data (tickers, company names, sectors, market cap tiers) | Public market data | Retrieved programmatically via a market-data Python library; stored once in the `stocks` table |
| Reference prices for realistic trade pricing | Same public market source | Daily OHLCV history sampled to price synthetic trades |
| Trader profiles (names, emails, signup dates, risk tiers) | `Faker` library | Procedurally generated, seeded for reproducibility |
| 1,000,000+ executed trades and orders | Custom generator script | Simulation constrained to market rules |

**Realism constraints applied to synthetic generation:**

- Timestamps restricted to trading sessions (market open to close, weekdays only)
- Prices derived from real historical ranges rather than uniform random numbers
- Quantities drawn from realistic share-lot distributions
- Buy/sell mix, commission rates and partial fills modelled explicitly
- A fixed random seed so the dataset can be regenerated identically for grading

This approach satisfies the requirement for synthetic data at scale while keeping every record internally consistent and business-plausible.

---

## 8. Relational Schema Design (OLTP)

The operational database is normalised (3NF) to keep transactional writes fast and consistent.

### 8.1 Entities

| Table | Purpose | Key Columns |
|---|---|---|
| `traders` | Platform users | `trader_id` (PK), `name`, `email` (unique), `risk_tier`, `created_at` |
| `stocks` | Listed securities | `stock_id` (PK), `ticker` (unique), `company_name`, `sector`, `current_price` |
| `portfolios` | Holdings and cash per trader | `portfolio_id` (PK), `trader_id` (FK), `cash_balance`, `total_equity` |
| `orders` | Buy/sell instructions | `order_id` (PK), `portfolio_id` (FK), `stock_id` (FK), `side`, `quantity`, `limit_price`, `status`, `created_at` |
| `trades` | Executed fills | `trade_id` (PK), `order_id` (FK), `execution_price`, `executed_quantity`, `commission`, `executed_at` |
| `price_history` | Daily OHLCV reference | `price_id` (PK), `stock_id` (FK), `trade_date`, `open`, `high`, `low`, `close`, `volume` |

### 8.2 Relationships

```
traders 1 ────< portfolios 1 ────< orders 1 ────< trades
                                      │
stocks  1 ────< orders                │
stocks  1 ────< price_history         │
stocks  1 ────────────────────────────┘
```

- One trader holds one or more portfolios
- One portfolio issues many orders
- One order produces one or more trades (partial fills)
- One stock appears in many orders and trades

Referential integrity is enforced with foreign keys, and indexes are placed on the high-selectivity columns (`traders.email`, `stocks.ticker`) and on join/filter columns (`orders.portfolio_id`, `trades.executed_at`) to keep API response times low at million-row scale.

### 8.3 From OLTP to OLAP

This normalised schema is correct for transactions but unsuitable for analytics. The Medallion pipeline exists precisely to transform it into the denormalised star schema described in Section 12.

---

## 9. Technology Stack & Justification

| Layer | Technology | Why this choice is necessary |
|---|---|---|
| API framework | **FastAPI (Python 3.11)** | Async performance, automatic OpenAPI documentation, Pydantic request/response validation — validation is critical when ingesting financial records |
| ORM / DB driver | **SQLAlchemy + psycopg2** | Portable models, connection pooling, safe parameterised queries, and support for bulk inserts at million-row scale |
| Relational database | **AWS RDS PostgreSQL** | Managed, backed-up, ACID-compliant OLTP store; correct tool for transactional writes and joins |
| Object storage / lakehouse | **AWS S3** | Cheap, durable, virtually unlimited storage for Parquet lake layers. Analytical files should not live in the transactional database |
| ETL engine | **PySpark (locally) / AWS Glue** | Distributed transformation of large Parquet datasets; columnar reads and partitioned writes |
| Unit/integration testing | **pytest** | Standard Python test framework; fixtures make database and API tests clean |
| Style enforcement | **flake8** | Enforces PEP 8, catches unused imports and excessive complexity before review |
| Static analysis gate | **SonarQube / SonarCloud** | Objective quality gate on bugs, vulnerabilities, code smells and coverage — prevents low-quality code from reaching production |
| Containerization | **Docker + Docker Compose** | Guarantees identical runtime locally and in the cloud; compose brings up API and PostgreSQL together |
| CI/CD | **GitHub Actions** | Automates lint, test, scan, build and release on every push |
| Container registry | **AWS ECR** | Versioned private image storage consumed by ECS |
| Compute for deployment | **AWS ECS Fargate** | Serverless containers — no cluster to patch or scale manually |
| Load balancing | **AWS ALB + 2 target groups** | Enables the blue/green split and health-checked traffic shifting |
| Release orchestration | **AWS CodeDeploy** | Native blue-green deployments with automatic rollback |
| Dashboard | **Streamlit** | Fastest route to a data application in pure Python, ideal for an analytics deliverable |
| Version control | **Git + GitHub (branch strategy)** | Feature-branch workflow with `main` / `dev` / feature branches protects the production line |

---

## 10. Big Data Concepts Coverage

This table is the core justification of the project: every concept taught in the course maps to a concrete, submitted artefact.

| Course Concept | Where it appears in TradePulse |
|---|---|
| Use case selection & requirement analysis | Section 5 — trading domain with defined entities and questions |
| Schema design / data modelling | Section 8 — normalised 6-table OLTP schema with keys and indexes |
| REST API development | FastAPI service with 6+ endpoints and OpenAPI docs |
| Unit & integration testing | pytest suite covering business logic and endpoint contracts |
| Code quality / linting | flake8 with a documented configuration |
| Containerization | Multi-stage Dockerfile, docker-compose stack |
| CI/CD automation | GitHub Actions workflow across 5 stages |
| Static code analysis | SonarQube quality gate blocking the pipeline on new issues |
| Cloud deployment | AWS ECS Fargate behind an ALB |
| Zero-downtime release | Blue-green deployment with health checks and rollback |
| Managed database service | AWS RDS PostgreSQL |
| Synthetic data generation at scale | 1,000,000+ record generator with reproducibility seed |
| Object storage / data lake | S3 Bronze, Silver, Gold layers in Parquet |
| Batch ETL / distributed processing | PySpark / Glue transformation jobs |
| Medallion architecture | Three-layer progressive refinement pipeline |
| Dimensional modelling | Gold-layer star schema with fact and dimension tables |
| Analytical modelling | Aggregate KPIs and grain-defined fact table |
| Data visualisation | Streamlit dashboard over the Gold layer |

---

## 11. Medallion Architecture (Bronze / Silver / Gold)

### 11.1 Bronze — Raw Acquisition

- **Input:** direct extract from RDS (`trades`, `orders`, `traders`, `stocks`, `portfolios`)
- **Output:** `s3://tradepulse-lake/bronze/<entity>/` as Parquet
- **Rules:** no transformation, no filtering, no cleaning; append-only, partitioned by extraction date
- **Purpose:** an immutable audit trail — we can always reprocess from source truth

### 11.2 Silver — Cleansed & Conformed

Silver repairs the defects that are unavoidable in generated and operational data:

| Transformation | Reason |
|---|---|
| Remove duplicate `trade_id` records | Retries and batch re-runs can duplicate rows |
| Quarantine malformed or unparseable records | Defence in depth: RDS `CHECK` constraints already reject negative prices, zero quantities and negative commissions, so this catches corruption introduced in Bronze or in historical source data rather than dirty OLTP rows |
| Cast timestamps to a single timezone and truncate to the day | Enables consistent date-level aggregation |
| Standardise ticker symbols (uppercase, trimmed) | Prevents `aapl` and `AAPL` being treated as different stocks |
| Derive `gross_amount`, `net_amount`, `commission_rate` | Business metrics computed once, centrally |
| Validate that `executed_at` falls inside a trading session | Flags corrupted synthetic or edge-case rows |
| Reconcile `orders.filled_quantity` against the sum of its fills | The only invariant RDS cannot `CHECK` (it spans rows); catches a lost or duplicated fill |
| Join trade → order → stock → trader to create a denormalised conformed view | Removes repeated join cost from downstream steps |

**Output:** `s3://tradepulse-lake/silver/trades/` — clean, typed, keyed Parquet.

### 11.3 Gold — Business-Ready Analytical Model

- **Output:** `s3://tradepulse-lake/gold/` — star schema tables (Section 12)
- **Rules:** aggregated to a defined grain, surrogate keys assigned, fully denormalised for fast dashboard queries

**Layer summary:**

| Layer | Data quality | Consumer | Partitioning |
|---|---|---|---|
| Bronze | Raw, unvalidated | Data engineers (reprocessing) | By extraction date |
| Silver | Clean, typed, conformed | Downstream modelling jobs | By trade date |
| Gold | Aggregated, modelled | BI dashboard, analysts | By date key |

---

## 12. Dimensional Model (Gold Layer Star Schema)

The Gold layer's analytical model is a **Kimball star schema**. It is the project's primary analytical deliverable.

### 12.1 Diagram

```
        ┌────────────────────┐        ┌────────────────────────┐
        │      dim_date      │        │      dim_stock         │
        │  date_key   (PK)   │        │  stock_key      (PK)   │
        │  full_date         │        │  ticker                │
        │  day_name          │        │  company_name          │
        │  month             │        │  sector                │
        │  quarter           │        │  market_cap_category   │
        │  year              │        │  exchange              │
        │  is_trading_day    │        └───────────┬────────────┘
        └─────────┬──────────┘                    │
                  │                               │
                  ▼                               ▼
        ┌──────────────────────────────────────────────────────┐
        │                fact_daily_trades                     │
        │  date_key        (FK)                                │
        │  stock_key       (FK)                                │
        │  trader_key      (FK)                                │
        │  trade_count                                         │
        │  buy_volume / sell_volume                            │
        │  total_traded_value                                  │
        │  avg_execution_price                                 │
        │  total_commission                                    │
        │  net_profit_loss                                     │
        └───────────────────────────┬──────────────────────────┘
                                    │
                                    ▼
                        ┌───────────────────────┐
                        │      dim_trader       │
                        │  trader_key   (PK)    │
                        │  trader_code          │
                        │  risk_tier            │
                        │  country              │
                        │  account_created_date │
                        └───────────────────────┘
```

### 12.2 Grain

**One row per (trading date × stock × trader).**

This grain is chosen because it answers all the dashboard's questions (daily volume, sector performance, trader activity) while staying small enough to render instantly. Any finer grain would inflate row counts without adding reporting value.

### 12.3 Table Definitions

**`dim_stock`** — descriptive attributes of each security
`stock_key (PK)`, `ticker`, `company_name`, `sector`, `market_cap_category`, `exchange`

**`dim_date`** — calendar attributes for time intelligence
`date_key (PK)`, `full_date`, `day_name`, `day_of_week`, `month`, `quarter`, `year`, `is_trading_day`

**`dim_trader`** — anonymised trader attributes
`trader_key (PK)`, `trader_code`, `risk_tier`, `country`, `account_created_date`

**`fact_daily_trades`** — business measures (additive and non-additive, see 12.4)
`date_key (FK)`, `stock_key (FK)`, `trader_key (FK)`, `trade_count`, `buy_volume`, `sell_volume`, `total_traded_value`, `total_traded_quantity`, `avg_execution_price`, `total_commission`, `net_profit_loss`

### 12.4 Design Decisions Worth Noting

- **Surrogate keys** (`stock_key`, `trader_key`) decouple the warehouse from OLTP identifiers, so source-system changes never break historical reporting.
- **`dim_date` is pre-populated**, including non-trading days, so time-series charts have a continuous axis and gaps become visible rather than silently collapsing.
- **Additive and non-additive measures are separated.** `trade_count`, `buy_volume`, `sell_volume`, `total_traded_value`, `total_traded_quantity`, `total_commission` and `net_profit_loss` are additive: any grouping (by sector, by month, by risk tier) is a simple `SUM`. `avg_execution_price` is **non-additive** — it must be recomputed as `SUM(total_traded_value) / SUM(total_traded_quantity)`, never averaged or summed, and therefore the fact table also stores `total_traded_quantity` as the denominator.
- **No personally identifying information** is carried into Gold; `dim_trader` exposes a code and a risk tier only, reflecting sound data-handling practice.

---

## 13. Data Volume Plan — 1 Million Records

### 13.1 Composition

| Entity | Target Rows |
|---|---|
| `trades` | **1,000,000** |
| `orders` | ~400,000 |
| `traders` | 1,000 |
| `portfolios` | 5,000 |
| `stocks` | 50 |
| `price_history` | ~25,000 (50 tickers × 500 trading days) |

### 13.2 Why these numbers are realistic

- 1,000,000 trades over 24 months ≈ 1,370 trades per calendar day, or roughly **4,000 trades per trading day** — normal throughput for a small-to-mid brokerage.
- 1,000 traders averaging 1,000 trades over two years is a plausible active-retail profile.
- 50 heavily traded large-cap tickers is a realistic watchlist size.
- As a cross-check, 50 tickers of one-minute OHLCV bars for a single year alone would exceed 4.8 million rows, confirming that financial market data reaches this volume naturally rather than by artificial padding.

### 13.3 Loading Strategy

- Generation and insertion are **decoupled**: the generator writes chunked batches, the loader inserts them.
- Inserts use **batched bulk loading (50,000 rows per commit)** rather than row-by-row inserts, which reduces load time from hours to minutes.
- A **fixed random seed** guarantees the same dataset on regeneration, so grading and demos are reproducible.
- The load is **idempotent**: re-running truncates or upserts rather than duplicating.

### 13.4 Purpose

Million-row scale is not a decoration — it is what forces the architectural decisions in this project. At this volume, direct dashboard queries against OLTP become visibly slow, the benefit of Parquet columnar storage and partitioning becomes measurable, and aggregation pushdown into Gold becomes demonstrably necessary.

---

## 14. Deployment Strategy — Blue-Green

### 14.1 Why zero downtime matters here

A trading API cannot be taken offline for a release. During downtime, order submissions fail, quotes go stale, and executed trades are missed — each of which is a direct financial and trust loss. This makes blue-green deployment a functional requirement of the domain, not a technical preference.

### 14.2 Mechanism

```
                    ┌───────────────────────────┐
        Traffic ───▶│  Application Load Balancer│
                    └─────────┬─────────────────┘
                              │ 100% traffic
                    ┌─────────▼─────────┐
                    │  BLUE target group│  ← current stable version
                    │  (v1.0 live)      │
                    └───────────────────┘

    New release:   ┌───────────────────┐
                    │ GREEN target group│  ← v1.1 deployed & health-checked
                    │ (staging traffic) │
                    └───────────────────┘

    After /health passes → ALB shifts traffic Blue → Green
    On any failure        → CodeDeploy rolls back to Blue automatically
```

### 14.3 Release Procedure

1. GitHub Actions builds the image and pushes it to **AWS ECR**.
2. **CodeDeploy** starts the new task definition in the **Green** target group; Blue keeps serving 100% of traffic.
3. The ALB performs repeated **`GET /health`** checks against Green.
4. Only after Green is healthy does CodeDeploy shift listener traffic to it.
5. If health checks fail, traffic never moves and CodeDeploy triggers an **automatic rollback**.
6. Blue is retained (not destroyed) until the release is confirmed, so rollback is instant.

**Result:** zero dropped requests during any release, with a one-command path back to the previous version.

---

## 15. Testing & Code Quality Strategy

### 15.1 Test Layers

| Layer | What is verified | Example |
|---|---|---|
| **Unit** | Pure business logic in isolation | Portfolio balance decreases by `quantity × price + commission` after a buy |
| **Unit** | Validation rules | Rejecting a sell order that exceeds held quantity |
| **Integration** | API contract via FastAPI `TestClient` | `POST /api/v1/orders/create` returns 201; malformed body returns 422 |
| **Integration** | Read endpoints | `GET /api/v1/stocks/{ticker}` returns the correct payload; unknown ticker returns 404 |
| **Integration** | Health endpoint | `GET /health` returns 200 (used by ALB/CodeDeploy) |
| **Data** | ETL correctness | Deduplication actually reduces the row count; measures match source totals |

**Target:** ≥80% coverage on the `api/app` layer, with the pytest suite required to pass before any image is built.

### 15.2 Style & Static Analysis

- **flake8:** `max-line-length = 100`, `max-complexity = 10`, unused imports and undefined names treated as errors.
- **SonarQube/SonarCloud quality gate:** reports on bugs, vulnerabilities, security hotspots, code smells and duplication. The pipeline **fails** if the gate fails, so poor-quality code cannot reach `main` or production.

### 15.3 CI/CD Pipeline Stages

```
push / pull request
        │
        ▼
 1. Lint          flake8 api pipeline tests
        │
        ▼
 2. Test          pytest + coverage → coverage.xml
        │
        ▼
 3. Quality gate  SonarQube scan → gate pass/fail
        │
        ▼
 4. Build         docker build → tag with commit SHA
        │
        ▼
 5. Publish       push image to AWS ECR
        │
        ▼
 6. Release       CodeDeploy blue-green → health check → traffic shift
```

Any failing stage stops the pipeline, so a broken build cannot be released.

---

## 16. Analytics & Dashboard Deliverables

The dashboard consumes **only** the Gold layer.

### 16.1 KPI Cards

- Total traded value (period)
- Total trade count
- Active stocks traded
- Net profit/loss
- Average commission per trade

### 16.2 Visualisations

| Visualisation | Question answered |
|---|---|
| **Daily trading volume trend** (with moving average) | Is market participation rising or falling? |
| **Sector breakdown** (share of traded value) | Which sectors dominate trading activity? |
| **Top 10 most traded stocks** | Where is liquidity concentrated? |
| **Top 10 traders by P&L** | Which traders generate returns? |
| **Trading activity heatmap** (day of week × hour) | When does activity peak? |
| **Risk-tier distribution** | How is activity spread across conservative/moderate/aggressive accounts? |

Every chart is backed by a documented Gold table and a stated grain, so each number on screen is traceable to its source.

---

## 17. Team Roles & Responsibilities

| Member | Role | Responsibilities |
|---|---|---|
| **Bisma Munir** (BSDSF23M005) | Data Engineer & Dashboard Lead | Synthetic data generator (1M records), RDS data loading, S3 lakehouse design, PySpark/Glue Bronze→Silver→Gold jobs, star schema modelling, Streamlit dashboard, Gold-layer validation |
| **Naimah Rehman** (BSDSF23M011) | Backend Developer & DevOps Lead | OLTP schema and DDL, FastAPI implementation, pytest suite and flake8 configuration, Dockerfile and docker-compose, GitHub Actions workflow, SonarQube setup, AWS ECS/ALB/CodeDeploy blue-green release |
| **Both** | Integration & QA | Shared architecture decisions, end-to-end verification, documentation, final demonstration |

The split is deliberately complementary: one member owns the **data plane** (storage → lakehouse → analytics), the other owns the **service plane** (API → tests → containers → cloud), and the contract between them — the relational schema — is designed jointly in Stage 1.

---

## 18. Timeline & Milestones

Eight-week plan (dates indicative; adjusted to the course calendar).

| Week | Milestone | Owner | Deliverable |
|---|---|---|---|
| 1 | Requirements, schema design, repo & branch setup | Both | ERD, `main`/`dev`/feature branches |
| 2 | FastAPI implementation (models, schemas, routes) | Naimah | Working API with OpenAPI docs |
| 3 | pytest suite + flake8 clean-up | Naimah | Passing tests, lint report |
| 4 | Dockerization + docker-compose stack | Naimah | Reproducible local environment |
| 5 | CI/CD pipeline + SonarQube gate | Naimah | Green pipeline on every push |
| 6 | AWS provisioning and blue-green deployment | Naimah | Live URL, zero-downtime release proof |
| 7 | 1M synthetic records into RDS; Bronze + Silver ETL | Bisma | Seeded database, lake layers populated |
| 8 | Gold star schema, dashboard, documentation, demo | Bisma | Star schema, live dashboard, final report |

**Buffer:** Weeks 7–8 are intentionally paired so that if the AWS release slips, the data pipeline still progresses independently — the two workstreams are decoupled after Week 1.

---

## 19. Risk Assessment

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | AWS free-tier limits, cost overruns or credit exhaustion | Medium | High | Keep RDS instance class and ECS task size minimal; stop resources when idle; document all provisioned resources |
| R2 | Synthetic data proves unrealistic or duplicates on re-run | Medium | Medium | Fixed seed, business-rule constraints, idempotent loader, validation queries on aggregates |
| R3 | SonarQube quality gate blocks releases late in the schedule | Medium | Medium | Introduce the gate in Week 5, not at the end; fix issues incrementally as they appear |
| R4 | Blue-green misconfiguration (target group, health check path) | Medium | High | Verify `/health` first via ALB directly; rehearse the release with a trivial image change; confirm rollback works |
| R5 | PySpark local setup friction (Java dependency) | Medium | Medium | Provide a documented environment setup; keep transformations portable so they also run as plain Python on small samples |
| R6 | Scope creep (requests for ML, auth, streaming) | High | Medium | Scope is fixed in Section 4; extras logged as future work rather than implemented |
| R7 | Team member unavailability near submission | Low | High | Parallel workstreams; every artefact committed to its own branch so partial work is never lost |

---

## 20. Expected Deliverables

1. **GitHub repository** with `main`, `dev` and feature branches, showing a real feature-branch workflow
2. **Relational schema** (DDL + ERD) for the trading domain
3. **FastAPI service** with OpenAPI documentation
4. **pytest suite** with coverage report; **flake8** clean run
5. **Dockerfile** and **docker-compose** stack
6. **GitHub Actions CI/CD workflow** with a SonarQube quality gate
7. **Live AWS deployment** using blue-green release, including release log evidence
8. **AWS RDS PostgreSQL** populated with **1,000,000+ trade records**
9. **S3 lakehouse** with Bronze, Silver and Gold Parquet layers
10. **PySpark/Glue transformation jobs** implementing each medallion layer
11. **Star schema** in the Gold layer (3 dimensions + 1 fact table)
12. **Streamlit dashboard** with KPIs and visualisations
13. **Documentation:** README, architecture notes, this PID, and a final report
14. **Demonstration** of the full pipeline end to end

---

## 21. Success Criteria

The project is considered complete and successful when:

- A new trade can be submitted through the API, persisted in RDS, and observed in the Gold-layer star schema after the pipeline runs
- The pytest suite passes and flake8 reports zero issues
- The CI/CD pipeline runs to completion with a passing SonarQube gate
- A release can be deployed to production with **no failed requests** and with a verified automatic rollback path
- The database holds **1,000,000+ trade records** and the dashboard still responds in interactive time
- Every dashboard figure is reproducible from a documented Gold table

---

## 22. References

1. FastAPI Documentation — <https://fastapi.tiangolo.com>
2. SQLAlchemy Documentation — <https://docs.sqlalchemy.org>
3. pytest Documentation — <https://docs.pytest.org>
4. flake8 Documentation — <https://flake8.pycqa.org>
5. Docker Documentation — <https://docs.docker.com>
6. GitHub Actions Documentation — <https://docs.github.com/actions>
7. SonarQube Documentation — <https://docs.sonarsource.com>
8. AWS Well-Architected Framework — <https://aws.amazon.com/architecture/well-architected>
9. AWS CodeDeploy Blue/Green Deployments — <https://docs.aws.amazon.com/codedeploy>
10. Apache Spark Documentation — <https://spark.apache.org/docs/latest>
11. Databricks, "What is the Medallion Architecture?" — <https://docs.databricks.com>
12. Kimball, R. & Ross, M., *The Data Warehouse Toolkit*, 3rd Edition, Wiley, 2013
13. Streamlit Documentation — <https://docs.streamlit.io>
