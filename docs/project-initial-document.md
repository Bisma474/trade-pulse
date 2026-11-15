# TradePulse

**End-to-End Financial Trading Data Pipeline & Medallion Analytics Lakehouse**

| | |
|---|---|
| **Course** | Big Data — BS Data Science |
| **University** | Punjab University College of Information Technology (PUCIT) |
| **Term** | Fall 2026 |
| **Instructor** | _<instructor name>_ |
| **Submitted** | _<date>_ |
| **Group Members** | Bisma Munir (BSDSF23M005), Naimah Rehman (BSDSF23M011) |

---

## 1. Project Title

**TradePulse — End-to-End Financial Trading Data Pipeline and Medallion Analytics Lakehouse.**

**Domain:** quantitative finance / capital markets data engineering. This document defines the project's title, description, problem statement, objectives, scope, exclusions, technology stack, architecture, data strategy, delivery plan and team responsibilities.

## 2. Project Description

TradePulse is a cloud-native quantitative trading platform whose real deliverable is not the trading application itself, but the **data pipeline behind it**. Traders interact with a REST API to place buy and sell orders; those records are stored transactionally in a relational database; the accumulated trade history is then refined through a **Medallion Architecture (Bronze → Silver → Gold)** into a dimensional star schema that feeds an analytics dashboard.

The project demonstrates the complete modern big data lifecycle in one continuous, verifiable path:

> API ingestion → relational storage → million-record scale → lakehouse transformation → dimensional model → analytics dashboard, delivered through automated testing, containerization, CI/CD with a quality gate, and a zero-downtime cloud release.

Quantitative finance was chosen as the domain because market activity genuinely produces high-volume time-series data, downtime carries a direct financial cost, and trade records split naturally into facts and dimensions.

## 3. Problem Statement

Trading platforms generate a continuous stream of transactional records, but that data is almost always left in its raw operational form. Three gaps motivate this project:

- **Raw data is not analytical.** An order table records what happened, but answering "which sector generated the most traded value last quarter" requires expensive repeated joins over millions of rows.
- **Scale degrades reporting.** Past a few million rows, dashboards querying the transactional database directly become slow and compete with live transaction processing.
- **Downtime is unacceptable in finance.** A trading service offline during a release misses order executions and produces stale quotes — a direct financial loss.

**Solution:** keep the API and relational database optimised for fast transactional writes, extract that data into an S3 lakehouse, progressively clean and model it, and let the dashboard read only the aggregated Gold layer. Blue-green deployment ensures releases never interrupt live traffic.

## 4. Objectives

- Design a normalised relational schema for a trading platform (5+ related tables with documented relationships).
- Implement a REST API for trading operations with automatic OpenAPI documentation.
- Achieve automated verification: a passing `pytest` suite and a clean `flake8` run.
- Containerize the service for reproducible deployment.
- Gate and release automatically with GitHub Actions and a SonarQube quality gate.
- Deploy to AWS with **zero downtime** using blue-green traffic shifting.
- Operate at realistic scale with **1,000,000+ synthetic trade records** in AWS RDS.
- Build a medallion pipeline delivering a **star schema** in the Gold layer.
- Present the results on a Streamlit analytics dashboard.

## 5. Scope

The project covers, end to end:

- **Data layer:** relational schema design and DDL, synthetic data generation at million-record scale, loading into AWS RDS.
- **Service layer:** FastAPI implementation, containerization with Docker.
- **Quality and delivery:** pytest and flake8, GitHub Actions CI/CD with a SonarQube quality gate, blue-green deployment to AWS.
- **Analytics layer:** S3 lakehouse, Bronze → Silver → Gold ETL with PySpark, star schema modelling, Streamlit dashboard.

One member owns the data plane and the other the service plane, and the relational schema — the contract between them — is designed jointly.

## 6. Exclusions (Out of Scope)

The following are deliberately excluded so that the effort goes into the data pipeline rather than into untested peripheral features:

| Excluded | Reason |
|---|---|
| Real money movement, brokerage or exchange connectivity | Requires licensing and exchange membership; the project models trade records, not settlement |
| Real-time streaming ingestion (Kafka/Kinesis) | Adds infrastructure without changing the analytical model; batch extraction at million-row scale meets the requirement |
| Machine learning and price forecasting | The graded analytical end-state is a Kimball star schema for reporting; the synthetic data has no labelled outcome to predict |
| User authentication and authorisation | Excluded to keep focus on the data plane; the API stays open for evaluation |
| Mobile or web trading front end | The Streamlit dashboard is the presentation layer |
| Multi-region disaster recovery | Single-region blue-green proves the zero-downtime objective being assessed |

## 7. Technology Stack

| Component | Technology and justification |
|---|---|
| API | **FastAPI (Python 3.11)** — async performance, automatic OpenAPI docs, Pydantic validation (critical for financial records) |
| Data access | **SQLAlchemy + psycopg2** — portable models, connection pooling, safe parameterised queries, bulk inserts at scale |
| OLTP database | **AWS RDS PostgreSQL** — managed, backed-up, ACID-compliant store for transactional writes |
| Object storage | **AWS S3** — durable, low-cost storage for the Parquet lake layers; analytical files do not belong in the transactional database |
| ETL engine | **PySpark / AWS Glue** — distributed transformation of large Parquet datasets with partitioned columnar writes |
| Testing | **pytest** — standard framework; fixtures make API and database tests clean |
| Linting | **flake8** — enforces PEP 8, catches unused imports and excessive complexity |
| Quality gate | **SonarQube / SonarCloud** — objective gate on bugs, vulnerabilities and code smells; blocks bad code from production |
| Containerization | **Docker + Docker Compose** — identical runtime locally and in the cloud |
| CI/CD | **GitHub Actions** — automates lint, test, scan, build and release on every push |
| Deployment | **AWS ECS Fargate + ALB + CodeDeploy** — serverless containers with health-checked blue-green traffic shifting |
| Dashboard | **Streamlit** — fastest route to a Python data application |

## 8. System Architecture

```
   Client / Tester
         |  REST (JSON)
         v
   FastAPI Service  (Docker)
         |
         +------------------> AWS ECS Fargate + ALB
         |                    Blue / Green via CodeDeploy
         v
   AWS RDS PostgreSQL  (OLTP, 1M+ trade rows)
         |  batch extract as Parquet
         v
   AWS S3 Data Lake   bronze/ --> silver/ --> gold/
         |  PySpark / AWS Glue
         v
   Streamlit Dashboard  (KPIs on Gold layer)
```

**Flow:** the client calls the API → records are written to AWS RDS → a batch extract copies raw rows into S3 **Bronze** → a job cleans and conforms them into **Silver** → a modelling job builds the star schema in **Gold** → the dashboard reads only Gold.

## 9. Data Strategy and Scale

No paid vendor, private dataset or special hardware is required:

- **Stock reference data** — public market data retrieved programmatically (tickers, company names, sectors, reference prices).
- **Trader profiles** — generated with the `Faker` library, seeded for reproducibility.
- **1,000,000+ trades and orders** — produced by a custom generator constrained to real market rules: timestamps restricted to trading sessions, prices derived from real historical ranges, realistic share lots, commissions and partial fills.

**Why one million records is realistic:** one million trades over 24 months is roughly 4,000 trades per trading day — normal throughput for a small-to-mid brokerage serving 1,000 traders across 50 listed stocks. As a cross-check, one-minute bars for 50 tickers over a single year already exceed 4.8 million rows, so financial data reaches this volume naturally rather than by artificial padding. Loading uses batched bulk inserts, and a fixed random seed makes the dataset reproducible for grading.

## 10. Medallion Architecture and Analytical Model

- **Bronze — raw acquisition.** Direct extracts from RDS written to S3 as Parquet with no transformation, append-only and partitioned by extraction date. This is the immutable audit trail.
- **Silver — cleansed and conformed.** Duplicate trade IDs removed, timestamps standardised to one timezone, tickers normalised, business measures (`gross_amount`, `net_amount`, `commission_rate`) derived once, centrally, and cross-table financial reconciliation (`filled_quantity` vs. sum of fills) verified. Note that RDS constraints already reject negative prices, zero quantities and negative commissions, so Silver's cleaning is defence in depth: its real work is deduplication, conformance, late-arriving-record handling and quarantining genuinely bad source records.
- **Gold — business-ready model.** Aggregated to a defined grain with surrogate keys assigned and denormalised for instant dashboard queries.

The Gold layer is a **Kimball star schema** — the project's primary analytical deliverable:

| Gold table | Contents |
|---|---|
| `dim_stock` | Ticker, company name, sector, market cap category, exchange |
| `dim_date` | Full date, day name, month, quarter, year, trading-day flag |
| `dim_trader` | Anonymised trader code, risk tier, country, account creation date |
| `fact_daily_trades` | **Grain: one row per date × stock × trader** — trade count, buy/sell volume, total traded value, average execution price, total commission, net profit/loss |

Surrogate keys decouple the warehouse from OLTP identifiers, and `dim_date` is pre-populated over the full dataset range (24 months, with a trading-day flag) so time-series charts have a continuous axis. Additive measures (`trade_count`, volumes, `total_traded_value`, `total_commission`, `net_profit_loss`) aggregate with a simple `SUM`; `avg_execution_price` is **non-additive** and must be recalculated as `SUM(total_traded_value) / SUM(total_traded_quantity)`, which is why the fact table stores the quantity denominator.

## 11. Testing, CI/CD and Deployment

**Testing.** Unit tests cover business logic (portfolio balance after a buy, rejection of a sell exceeding holdings); integration tests cover API contracts through `TestClient` (201 on order creation, 422 on malformed input, 404 on an unknown ticker); `GET /health` is verified separately because the load balancer depends on it. Target coverage is 80%+ on the API layer, with `flake8` at maximum line length 100 and maximum complexity 10.

**CI/CD.** Every push runs `flake8` → `pytest` with coverage → **SonarQube quality gate** → Docker build → image push to AWS ECR. A failing stage stops the pipeline, so broken code cannot be released.

**Blue-green deployment.** CodeDeploy starts the new version in a **Green** target group while **Blue** serves 100% of traffic. The load balancer repeatedly calls `/health` on Green; only when Green is healthy does CodeDeploy shift traffic, and any failure rolls back automatically to Blue, which is retained until the release is confirmed. The result is **zero dropped requests during any release** — a functional requirement of a trading system, not a preference.

## 12. Team Roles

| Member | Role | Responsibilities |
|---|---|---|
| **Bisma Munir** (BSDSF23M005) | Data Engineer & Dashboard Lead | Synthetic data generation (1M records), RDS loading, S3 lakehouse design, Bronze→Silver→Gold ETL, star schema modelling, Streamlit dashboard |
| **Naimah Rehman** (BSDSF23M011) | Backend Developer & DevOps Lead | Schema and DDL, FastAPI implementation, pytest and flake8, Docker, GitHub Actions, SonarQube, AWS ECS/ALB/CodeDeploy blue-green release |

The split is complementary: one member owns the **data plane** (storage → lakehouse → analytics), the other the **service plane** (API → tests → containers → cloud).

## 13. Timeline

| Weeks | Milestone | Owner |
|---|---|---|
| 1 | Requirements, title and scope finalisation, schema design, repository setup | Both |
| 2–3 | FastAPI implementation, pytest suite, flake8 clean-up | Naimah |
| 4–5 | Dockerization, CI/CD pipeline with SonarQube gate | Naimah |
| 6 | AWS provisioning and blue-green deployment | Naimah |
| 7 | 1M synthetic records into RDS; Bronze and Silver ETL | Bisma |
| 8 | Gold star schema, dashboard, documentation and demo | Bisma |

Weeks 7–8 are paired so that if the AWS release slips, the data pipeline still progresses independently.

## 14. Expected Deliverables

1. Repository with a feature-branch workflow (`main`, `dev`, feature branches)
2. Relational schema with documented relationships
3. FastAPI service with OpenAPI documentation
4. Passing pytest suite with coverage report and a clean flake8 run
5. Dockerfile and docker-compose stack
6. GitHub Actions CI/CD pipeline with a SonarQube quality gate
7. Live AWS deployment with blue-green release evidence
8. AWS RDS populated with 1,000,000+ trade records
9. S3 lakehouse with Bronze, Silver and Gold Parquet layers
10. Star schema (three dimensions plus one fact table) in the Gold layer
11. Streamlit dashboard showing trading KPIs and trends
12. End-to-end demonstration of the complete pipeline
