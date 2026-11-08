# TradePulse 📈⚡
**End-to-End Financial Trading Data Pipeline & Medallion Analytics Lakehouse**

TradePulse is a high-throughput, production-grade Quantitative Trading & Portfolio Analytics platform developed as a Term Project for **Big Data (BS Data Science - PUCIT)**.

---

## 🏗️ System Architecture

```
[ FastAPI REST Service ] ──(Transactional Ingestion)──> [ AWS RDS PostgreSQL ]
           │                                                    │
     (Unit Tests &                                     (1M+ Synthetic Trades)
   Flake8 + SonarQube)                                          │
           │                                          [ Medallion ETL Pipeline ]
           ▼                                                    │
 [ AWS Blue-Green ECS ]                                ┌────────┴────────┐
                                                       ▼                 ▼
                                               [ Bronze Layer ]   [ Silver Layer ]
                                               (Raw Parquet)      (Cleaned/Deduped)
                                                       │                 │
                                                       └────────┬────────┘
                                                                ▼
                                                        [ Gold Layer (S3) ]
                                                   (Star Schema: Fact & Dims)
                                                                │
                                                                ▼
                                                      [ Streamlit Dashboard ]
                                                      (Market & Portfolio KPIs)
```

---

## 🚀 Key Pipeline Stages

| Stage | Technology | Purpose |
|---|---|---|
| **1. API Layer** | FastAPI (Python 3.11) | High-performance REST endpoints for orders, portfolios, and quotes |
| **2. Code Quality** | pytest + flake8 | Comprehensive test coverage & PEP8 style compliance |
| **3. Containerization** | Docker & Docker Compose | Multi-stage production container setup |
| **4. CI/CD & Security** | GitHub Actions + SonarQube | Automated testing & static code vulnerability gate |
| **5. Cloud Deployment** | AWS ECS Fargate + ALB | Zero-downtime Blue-Green traffic shifting |
| **6. OLTP Storage** | AWS RDS (PostgreSQL) | Primary transactional data store holding 1M+ trade records |
| **7. Object Lakehouse** | AWS S3 | Data lake storage holding Bronze, Silver, and Gold Parquet/Delta tables |
| **8. Data Processing** | PySpark / AWS Glue | Medallion architecture transformations |
| **9. Analytical Model** | Dimensional Model (Star Schema) | `fact_trades` surrounded by `dim_stock`, `dim_date`, and `dim_trader` |
| **10. BI Dashboard** | Streamlit | Executive trading analytics, top stocks, and portfolio performance metrics |

---

## 👥 Authors
* **Bisma Munir** (Roll No: BSDSF23M005) - *Backend & DevOps Lead*
* **Naimah Rehman** (Roll No: BSDSF23M011) - *Data Engineer & Dashboard Lead*

**University:** Punjab University College of Information Technology (PUCIT)  
**Department:** Data Science  
**Course:** Big Data (Fall 2026)
