# TradePulse — OLTP Schema Design

**Layer:** AWS RDS PostgreSQL 15 · **Status:** v1.2 — review items applied · **Version:** 1.2
**Owners:** Bisma Munir (BSDSF23M005), Naimah Rehman (BSDSF23M011)

---

## 1. Purpose

The OLTP schema is the contract between the two workstreams and serves three consumers:

| Consumer | Access pattern | Needs |
|---|---|---|
| FastAPI service | single-row reads/writes | PK lookups, enforceable invariants |
| Bronze extractor | incremental scan of ~1M rows | a watermark to slice on (8.1) |
| Gold job | aggregates | every measure derivable, unambiguous keys |

Two requirements outrank elegance: **every PID business rule must be enforceable or detectable**, and **a re-run of the loader must not duplicate rows**.

---

## 2. Conventions

| Decision | Choice | Why |
|---|---|---|
| Primary keys | `BIGINT GENERATED ALWAYS AS IDENTITY` | Dense B-tree inserts, 8-byte keys. No distributed writer, so UUIDs buy nothing. |
| Money | `NUMERIC` only | 1M floating-point sums drift; dashboard totals must reconcile to source. |
| Precision | prices `(18,6)`, quantities `(18,4)`, totals `(20,4)`, commission `(12,4)` | Sub-cent pricing, fractional shares, aggregate headroom. |
| Time | `TIMESTAMPTZ` UTC; `DATE` for trading days | Naive `TIMESTAMP` drops the offset Silver is supposed to normalise. |
| Naming | `snake_case`, plural tables, `*_id` FKs | SQL, SQLAlchemy, Parquet and Gold stay congruent. |
| Enums | `VARCHAR` + `CHECK` | Native `ENUM` needs non-transactional `ADD VALUE`, and Spark reads it poorly. |
| Audit | `created_at` / `updated_at`, trigger-maintained | Bulk loads and manual fixes cannot skip the trigger. `trades` and `price_history` are append-only and deliberately have no `updated_at`. |
| Deletes | `ON DELETE RESTRICT` written on **every** FK | A parent delete must not erase the audit trail Bronze depends on. No `CASCADE` anywhere (v1.2) — it never fired anyway, because `orders` blocks the parent delete first. |

---

## 3. ERD

```
traders 1───< portfolios 1───< orders 1───< trades
                   │              │
                   │              └── stocks 1───< price_history
                   └──< positions >──┘   (positions: portfolio × stock, unique pair)
```

Full cardinalities: trader → many portfolios; portfolio → many positions (one per stock); portfolio → many orders; order → **many trades** (partial fills); stock → many orders, positions, daily bars (one per date).

---

## 4. Tables

Types shown as `name type null/default` unless noted. Constraint shorthand: `NN` not null, `UK` unique, `FK→` foreign key.

### `traders` (≈1,000 rows)

| Column | Type / constraint | Reason |
|---|---|---|
| `trader_id` | `BIGINT` identity PK | surrogate key, external-account agnostic |
| `name` | `VARCHAR(120) NN`, non-blank | display only; not split |
| `email` | `CITEXT NN UK` | natural key; case-insensitive uniqueness (10.4) |
| `risk_tier` | `VARCHAR(16) NN 'MODERATE'`, in CONSERVATIVE/MODERATE/AGGRESSIVE | feeds `dim_trader.risk_tier` and the risk chart |
| `country` | `CHAR(2) NN 'PK'`, `^[A-Z]{2}$` | feeds `dim_trader.country`. `CHAR` is correct for fixed-width ISO codes — no padding risk given the shape CHECK |
| `created_at` | `TIMESTAMPTZ NN now()` | feeds `dim_trader.account_created_date`, cohort analysis |
| `updated_at` | `TIMESTAMPTZ NN now()` | trigger-maintained |

Index: `email` unique only.

### `stocks` (≈50 rows)

| Column | Type / constraint | Reason |
|---|---|---|
| `stock_id` | `BIGINT` identity PK | warehouse gets its own `stock_key` |
| `ticker` | `VARCHAR(10) NN UK`, `^[A-Z][A-Z0-9.-]{0,9}$` | natural key for `GET /stocks/{ticker}` |
| `company_name` | `VARCHAR(160) NN` | `dim_stock` attribute |
| `sector` | `VARCHAR(40) NN` | grouping for sector-share chart |
| `market_cap_category` | `VARCHAR(16) NN`, LARGE/MID/SMALL | dimension + constrains synthetic price ranges |
| `exchange` | `VARCHAR(16) NN 'NASDAQ'`, NASDAQ/NYSE/AMEX | dimension |
| `current_price` | `NUMERIC(18,6) NN > 0` | prices market orders; values equity |
| `created_at`/`updated_at` | `TIMESTAMPTZ NN now()` | audit |

**`current_price` ↔ `price_history` (v1.2):** `current_price` is *by definition* the `close` of the latest `price_history` row for that stock — no other meaning. The generator sets it after loading bars; in operation one nightly job appends the new bar and updates `current_price` in the same transaction. Historical accuracy never depends on it, because a fill records `execution_price` at the moment of execution.

### `portfolios` (≈5,000 rows)

| Column | Type / constraint | Reason |
|---|---|---|
| `portfolio_id` | `BIGINT` identity PK | |
| `trader_id` | `BIGINT NN FK→traders` RESTRICT | owner; history blocks deletion |
| `name` | `VARCHAR(80) NN 'Main'` | a trader may hold several |
| `cash_balance` | `NUMERIC(20,4) NN 0 >= 0` | the only stored financial state |
| `created_at`/`updated_at` | `TIMESTAMPTZ NN now()` | |

Index `(trader_id)`. **`total_equity` is deliberately not stored** — it is `cash + Σ qty × price` and goes stale on every price move (10.3).

**Opening cash (v1.2):** `DEFAULT 0` alone would make every BUY impossible. Seeding rule (§9): every portfolio is created with an opening `cash_balance` drawn from a fixed-seed distribution in `[10,000, 250,000]`. No `initial_cash_balance` column and no cash ledger — the opening figure is a documented seeding assumption, and every later movement is reconstructible from `trades` (see 10.14).

### `orders` (≈400,000 rows)

| Column | Type / constraint | Reason |
|---|---|---|
| `order_id` | `BIGINT` identity PK | parent of the trade rows |
| `portfolio_id` | `BIGINT NN FK→portfolios` RESTRICT | who bears the order |
| `stock_id` | `BIGINT NN FK→stocks` RESTRICT | instrument |
| `side` | `VARCHAR(4) NN`, BUY/SELL | cash direction, sell-side holdings check |
| `order_type` | `VARCHAR(8) NN 'MARKET'`, MARKET/LIMIT | limit orders carry a bound; market orders must not |
| `quantity` | `NUMERIC(18,4) NN > 0` | denominator for fill completeness |
| `limit_price` | `NUMERIC(18,6) NULL > 0` | `LIMIT` ⇒ required, `MARKET` ⇒ must be `NULL` (both directions CHECKed) |
| `status` | `VARCHAR(20) NN 'PENDING'`, 5-value CHECK | lifecycle + cheap open-order filter |
| `filled_quantity` | `NUMERIC(18,4) NN 0`, `0 ≤ x ≤ quantity` | cached fill total; must agree with `status` (v1.2) |
| `created_at`/`updated_at` | `TIMESTAMPTZ NN now()` | |

**Status ⇔ fill agreement (v1.2):** `PENDING` ⇒ 0 · `PARTIALLY_FILLED` ⇒ `0 < x < quantity` · `FILLED` ⇒ `= quantity` · `CANCELLED` ⇒ `< quantity` (a cancelled order may keep its partial fills) · `REJECTED` ⇒ `0`. The `CHECK` constrains values, not transitions — the state machine stays in the service layer.

### `trades` (1,000,000 rows)

| Column | Type / constraint | Reason |
|---|---|---|
| `trade_id` | `BIGINT` identity PK | stable dedupe key exported to Bronze (8.1) |
| `order_id` | `BIGINT NN FK→orders` RESTRICT | a trade never outlives its order |
| `fill_seq` | `SMALLINT NN > 0`, `UK (order_id, fill_seq)` | distinguishes fills; **idempotency key** |
| `execution_price` | `NUMERIC(18,6) NN > 0` | basis of all value measures |
| `executed_quantity` | `NUMERIC(18,4) NN > 0` | basis of all volume measures |
| `commission` | `NUMERIC(12,4) NN 0 >= 0` | additive brokerage cost; capitalised on BUY (7.1) |
| `realized_pnl` | `NUMERIC(20,4) NULL` | net of commission on SELL; `NULL` on BUY (7.1) |
| `executed_at` | `TIMESTAMPTZ NN` | business time: Silver `trade_date`, heatmap axis |
| `created_at` | `TIMESTAMPTZ NN now()` | recording time; **Bronze watermark** (8.1) |

### `price_history` (≈25,000 rows — 50 tickers × ~502 trading sessions)

| Column | Type / constraint | Reason |
|---|---|---|
| `price_id` | `BIGINT` identity PK | |
| `stock_id` | `BIGINT NN FK→stocks` RESTRICT | reference data does not outlive its instrument |
| `trade_date` | `DATE NN`, `UK (stock_id, trade_date)` | one **daily OHLC bar** per stock **per trading session** (not per calendar day, not ticks); **idempotency key** |
| `open/high/low/close` | `NUMERIC(18,6) NN > 0`, OHLC-ordering CHECK | prices synthetic fills; catches a broken generator |
| `volume` | `BIGINT NN >= 0` | share counts exceed int4 on busy days |

**Row count derivation (measured, not assumed):** `generate_series` across the 730-day range yields **522 weekdays**; subtracting ~20 exchange holidays leaves **~502 trading sessions per ticker**, so 50 × ~502 ≈ **25,000 bars**. Weekends generate no bar — 50 × 730 = 36,500 would imply bars on Saturdays and Sundays. This matches the PID's original ~25,000 estimate.

### `positions` — proposed 7th table (derived, rebuildable)

| Column | Type / constraint | Reason |
|---|---|---|
| `portfolio_id` | `BIGINT FK→portfolios` RESTRICT, PK part 1 | composite PK ⇒ one row per stock |
| `stock_id` | `BIGINT FK→stocks` RESTRICT, PK part 2 | |
| `quantity` | `NUMERIC(18,4) NN 0 >= 0` | makes oversell impossible by construction |
| `avg_cost` | `NUMERIC(18,6) NN 0 >= 0` | cost basis; without it `realized_pnl` is undefined (7.1) |
| `updated_at` | `TIMESTAMPTZ NN now()` | |

**Zero-quantity rule (v1.2):** a fully exited position **keeps its row** with `quantity = 0 AND avg_cost = 0`, enforced by CHECK. The row is retained so the holding is explicit and the PK is stable; the cost basis is *not* retained after exit, because a later re-entry must not inherit stale basis. `realized_pnl` on the closing fill already captured the gain, so nothing is lost.

**Why it exists:** the PID requires rejecting a sell beyond holdings and valuing a portfolio. Deriving either from `trades` is an aggregate over up to 1M rows inside a write transaction, and it still cannot produce a cost basis without a FIFO pass.

---

## 5. DDL

Executed successfully against `postgres:15` (see 11).

```sql
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE traders (
    trader_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name       VARCHAR(120) NOT NULL,
    email      CITEXT       NOT NULL,
    risk_tier  VARCHAR(16)  NOT NULL DEFAULT 'MODERATE',
    country    CHAR(2)      NOT NULL DEFAULT 'PK',
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT traders_email_key       UNIQUE (email),
    CONSTRAINT traders_name_not_blank  CHECK (length(btrim(name)) > 0),
    CONSTRAINT traders_email_shape     CHECK (email LIKE '%_@_%._%'),
    CONSTRAINT traders_risk_tier_valid CHECK (risk_tier IN ('CONSERVATIVE','MODERATE','AGGRESSIVE')),
    CONSTRAINT traders_country_shape   CHECK (country ~ '^[A-Z]{2}$')
);

CREATE TABLE stocks (
    stock_id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ticker              VARCHAR(10)    NOT NULL,
    company_name        VARCHAR(160)   NOT NULL,
    sector              VARCHAR(40)    NOT NULL,
    market_cap_category VARCHAR(16)    NOT NULL,
    exchange            VARCHAR(16)    NOT NULL DEFAULT 'NASDAQ',
    current_price       NUMERIC(18,6)  NOT NULL,
    created_at          TIMESTAMPTZ    NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ    NOT NULL DEFAULT now(),
    CONSTRAINT stocks_ticker_key             UNIQUE (ticker),
    CONSTRAINT stocks_ticker_shape           CHECK (ticker ~ '^[A-Z][A-Z0-9.-]{0,9}$'),
    CONSTRAINT stocks_market_cap_valid       CHECK (market_cap_category IN ('LARGE','MID','SMALL')),
    CONSTRAINT stocks_exchange_valid         CHECK (exchange IN ('NASDAQ','NYSE','AMEX')),
    CONSTRAINT stocks_current_price_positive CHECK (current_price > 0),
    CONSTRAINT stocks_sector_not_blank       CHECK (length(btrim(sector)) > 0)
);

CREATE TABLE portfolios (
    portfolio_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trader_id    BIGINT         NOT NULL,
    name         VARCHAR(80)    NOT NULL DEFAULT 'Main',
    cash_balance NUMERIC(20,4)  NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ    NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ    NOT NULL DEFAULT now(),
    CONSTRAINT portfolios_trader_fk FOREIGN KEY (trader_id) REFERENCES traders (trader_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT portfolios_cash_non_negative CHECK (cash_balance >= 0),
    CONSTRAINT portfolios_name_not_blank    CHECK (length(btrim(name)) > 0)
);
CREATE INDEX idx_portfolios_trader_id ON portfolios (trader_id);

CREATE TABLE orders (
    order_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    portfolio_id    BIGINT         NOT NULL,
    stock_id        BIGINT         NOT NULL,
    side            VARCHAR(4)     NOT NULL,
    order_type      VARCHAR(8)     NOT NULL DEFAULT 'MARKET',
    quantity        NUMERIC(18,4)  NOT NULL,
    limit_price     NUMERIC(18,6),
    status          VARCHAR(20)    NOT NULL DEFAULT 'PENDING',
    filled_quantity NUMERIC(18,4)  NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ    NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ    NOT NULL DEFAULT now(),
    CONSTRAINT orders_portfolio_fk FOREIGN KEY (portfolio_id) REFERENCES portfolios (portfolio_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT orders_stock_fk FOREIGN KEY (stock_id) REFERENCES stocks (stock_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT orders_side_valid   CHECK (side IN ('BUY','SELL')),
    CONSTRAINT orders_type_valid   CHECK (order_type IN ('MARKET','LIMIT')),
    CONSTRAINT orders_status_valid CHECK (status IN ('PENDING','PARTIALLY_FILLED','FILLED','CANCELLED','REJECTED')),
    CONSTRAINT orders_quantity_positive      CHECK (quantity > 0),
    CONSTRAINT orders_limit_price_positive   CHECK (limit_price IS NULL OR limit_price > 0),
    CONSTRAINT orders_limit_price_present    CHECK (order_type <> 'LIMIT'  OR limit_price IS NOT NULL),
    CONSTRAINT orders_market_has_no_limit    CHECK (order_type <> 'MARKET' OR limit_price IS NULL),
    CONSTRAINT orders_filled_within_quantity CHECK (filled_quantity >= 0 AND filled_quantity <= quantity),
    CONSTRAINT orders_status_matches_fills CHECK (
           (status = 'PENDING'          AND filled_quantity = 0)
        OR (status = 'PARTIALLY_FILLED' AND filled_quantity > 0 AND filled_quantity < quantity)
        OR (status = 'FILLED'           AND filled_quantity = quantity)
        OR (status = 'CANCELLED'        AND filled_quantity < quantity)
        OR (status = 'REJECTED'         AND filled_quantity = 0)
    )
);
CREATE INDEX idx_orders_portfolio_created ON orders (portfolio_id, created_at DESC);
CREATE INDEX idx_orders_stock_id          ON orders (stock_id);
CREATE INDEX idx_orders_open              ON orders (portfolio_id)
    WHERE status IN ('PENDING','PARTIALLY_FILLED');

CREATE TABLE trades (
    trade_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id          BIGINT         NOT NULL,
    fill_seq          SMALLINT       NOT NULL,
    execution_price   NUMERIC(18,6)  NOT NULL,
    executed_quantity NUMERIC(18,4)  NOT NULL,
    commission        NUMERIC(12,4)  NOT NULL DEFAULT 0,
    realized_pnl      NUMERIC(20,4),
    executed_at       TIMESTAMPTZ    NOT NULL,
    created_at        TIMESTAMPTZ    NOT NULL DEFAULT now(),
    CONSTRAINT trades_order_fk FOREIGN KEY (order_id) REFERENCES orders (order_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT trades_order_fill_key      UNIQUE (order_id, fill_seq),
    CONSTRAINT trades_fill_seq_positive   CHECK (fill_seq > 0),
    CONSTRAINT trades_price_positive      CHECK (execution_price > 0),
    CONSTRAINT trades_quantity_positive   CHECK (executed_quantity > 0),
    CONSTRAINT trades_commission_non_negative CHECK (commission >= 0)
);
CREATE INDEX idx_trades_executed_at   ON trades (executed_at);
CREATE INDEX idx_trades_created_at_id ON trades (created_at, trade_id);

CREATE TABLE price_history (
    price_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    stock_id   BIGINT        NOT NULL,
    trade_date DATE          NOT NULL,
    open       NUMERIC(18,6) NOT NULL,
    high       NUMERIC(18,6) NOT NULL,
    low        NUMERIC(18,6) NOT NULL,
    close      NUMERIC(18,6) NOT NULL,
    volume     BIGINT        NOT NULL,
    created_at TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT price_history_stock_fk FOREIGN KEY (stock_id) REFERENCES stocks (stock_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT price_history_stock_date_key UNIQUE (stock_id, trade_date),
    CONSTRAINT price_history_prices_positive CHECK (open > 0 AND high > 0 AND low > 0 AND close > 0),
    CONSTRAINT price_history_ohlc_ordered CHECK (
        high >= low AND high >= least(open, close) AND low <= least(open, close)
        AND low <= greatest(open, close) AND high >= greatest(open, close)
    ),
    CONSTRAINT price_history_volume_non_negative CHECK (volume >= 0)
);
CREATE INDEX idx_price_history_trade_date ON price_history (trade_date DESC);

CREATE TABLE positions (
    portfolio_id BIGINT        NOT NULL,
    stock_id     BIGINT        NOT NULL,
    quantity     NUMERIC(18,4) NOT NULL DEFAULT 0,
    avg_cost     NUMERIC(18,6) NOT NULL DEFAULT 0,
    updated_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT positions_pk PRIMARY KEY (portfolio_id, stock_id),
    CONSTRAINT positions_portfolio_fk FOREIGN KEY (portfolio_id) REFERENCES portfolios (portfolio_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT positions_stock_fk FOREIGN KEY (stock_id) REFERENCES stocks (stock_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT positions_quantity_non_negative CHECK (quantity >= 0),
    CONSTRAINT positions_avg_cost_non_negative CHECK (avg_cost >= 0),
    CONSTRAINT positions_flat_zero_cost CHECK (
        (quantity = 0 AND avg_cost = 0) OR (quantity > 0 AND avg_cost > 0)
    )
);
CREATE INDEX idx_positions_stock_id ON positions (stock_id);

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER traders_set_updated_at    BEFORE UPDATE ON traders    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER stocks_set_updated_at     BEFORE UPDATE ON stocks     FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER portfolios_set_updated_at BEFORE UPDATE ON portfolios FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER orders_set_updated_at     BEFORE UPDATE ON orders     FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER positions_set_updated_at  BEFORE UPDATE ON positions  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

---

## 6. Index Strategy

| Query | Index |
|---|---|
| Q1 place order: read cash + holding | PK `portfolios`, PK `positions (portfolio_id, stock_id)` |
| Q2 list portfolio orders newest-first | `idx_orders_portfolio_created` |
| Q3 Bronze extraction (watermark, 8.1) | `idx_trades_created_at_id` |
| Q3b trades for a business date window | `idx_trades_executed_at` |
| Q4 ticker lookup | `stocks_ticker_key` |
| Q5 holdings check / sell validation | `positions_pk` prefix |

Also: `idx_orders_stock_id`, partial `idx_orders_open` (excludes ~1M closed rows), `idx_price_history_trade_date`, `idx_positions_stock_id`.

**Deliberate non-indexes:** no `trades(stock_id)` (column doesn't exist — reached via `order_id`); nothing on `traders(created_at)` or `stocks(sector)` (1,000 and 50 rows — seq scan wins); no standalone `orders(status)`; no index on `commission`/`realized_pnl` (analytical filters belong in Gold). Verify the extraction plan with `EXPLAIN (ANALYZE, BUFFERS)` after loading and `ANALYZE trades`.

---

## 7. Rules & Invariants

**Lifecycle:** `PENDING → PARTIALLY_FILLED → FILLED`, plus `PENDING → CANCELLED|REJECTED` and `PARTIALLY_FILLED → CANCELLED`. `FILLED`, `CANCELLED`, `REJECTED` are terminal. `CHECK` constrains values, not transitions — transitions live in the service layer (10.10). **Partial fills:** one order → 1..n trades, `fill_seq` per order, so no code may assume 1:1.

| Invariant | Where enforced |
|---|---|
| side ∈ BUY/SELL; qty, price, executed qty > 0 | `CHECK` |
| `filled_quantity ≤ quantity`; `positions.quantity ≥ 0`; `cash_balance ≥ 0` | `CHECK` |
| `status` agrees with `filled_quantity`; `MARKET` has no `limit_price` | `CHECK` (v1.2) |
| one bar per stock per day; one fill per `(order, seq)` | `UNIQUE` |
| flat position ⇒ `avg_cost = 0` | `CHECK` (v1.2) |
| **Σ child `executed_quantity` ≤ `orders.quantity`** | **not a `CHECK`** (spans rows) — app validates while holding the order lock (7.2); nightly aggregate as backstop |
| **`filled_quantity` = Σ children** | convention — nightly reconciliation |
| sell requires sufficient position | app, `SELECT … FOR UPDATE` on `positions` (7.2) |
| `executed_at` inside a trading session | generator + Silver validation (not the schema) |

Multi-row invariants are the honest gap: the database guarantees each row is valid, not that a set of rows is collectively consistent.

### 7.1 Accounting policy — weighted-average cost (v1.2)

This defines `avg_cost` and `realized_pnl` so OLTP, Silver and Gold cannot disagree. **Weighted-average cost; buy commission is capitalised; realized P&L is net of commission.**

| Event | Rule |
|---|---|
| **BUY fill** | `basis_added = (execution_price × executed_quantity) + commission`; `avg_cost = (quantity × avg_cost + basis_added) / (quantity + executed_quantity)`; `quantity += executed_quantity`; `realized_pnl = NULL` |
| **SELL fill** | `cost_basis = avg_cost × executed_quantity`; `realized_pnl = (execution_price × executed_quantity) − cost_basis − commission`; `quantity −= executed_quantity`; **`avg_cost` unchanged** (a partial sale does not move the average) |
| **Full exit** | `quantity = 0` **and** `avg_cost = 0`, row retained (see §4) |
| **Rounding** | `avg_cost` rounded to 6 dp (banker's rounding, `ROUND(x, 6)`) on each write; `realized_pnl` rounded to 4 dp at the fill. Cost basis of a sale uses the *stored* `avg_cost`, so a replay reproduces the same number |
| **Gold** | `net_profit_loss = SUM(realized_pnl)` — already net; Gold must **not** subtract commission again. `total_commission` stays a separate reporting measure |

Consequence to state in the report: partial fills of one BUY order apply commission **per fill**, so an order filled in three pieces capitalises three commissions. That is realistic (brokers charge per execution) and it is why `commission` is not stored on `orders`.

**Worked example — the reference numbers both implementers must reproduce** (asserted by the SQL test in 11):

| Step | Fill | `quantity` | `avg_cost` | `realized_pnl` |
|---|---|---|---|---|
| BUY | 10 @ 100, comm 5 | 10 | `(0 + 1000 + 5)/10` = **100.5** | `NULL` |
| BUY | 5 @ 120, comm 3 | 15 | `(10·100.5 + 600 + 3)/15` = **107.2** | `NULL` |
| SELL | 6 @ 130, comm 4 | 9 | **107.2** (unchanged) | `780 − 643.2 − 4` = **132.8** |
| SELL | 9 @ 110, comm 2 | 0 | **0** (reset on exit) | `990 − 964.8 − 2` = **23.2** |
| **Total** | | | | **156.0** |

Cross-check: total sell proceeds net of commission are `1770 − 6 = 1764`, total cost basis is `1608`, so `1764 − 1608 = 156.0` — the sum of the two `realized_pnl` values. If an implementation disagrees with either column, the policy is being applied differently.

### 7.2 Fill / order transaction protocol (v1.2)

Every path that writes cash, holdings or fills follows this sequence exactly:

1. `BEGIN`.
2. `SELECT … FROM orders WHERE order_id = $1 FOR UPDATE` — **the order row first** (v1.2). Locking a position alone does not protect the order's remaining quantity: two concurrent fills would each pass validation and jointly overfill.
3. `SELECT … FROM portfolios WHERE portfolio_id = $1 FOR UPDATE`.
4. `SELECT … FROM positions WHERE portfolio_id = $1 AND stock_id = $2 FOR UPDATE` (insert the row first if it does not exist).
5. Validate, now that all three rows are held: status is open, `filled_quantity + qty ≤ quantity`, `LIMIT` bound respected, sufficient `cash_balance` (BUY: gross + commission) or `quantity` (SELL).
6. `INSERT` the trade (`fill_seq` = next value under the order lock, so no gap race).
7. `UPDATE` order (`filled_quantity`, `status`), portfolio (`cash_balance`), position (`quantity`, `avg_cost`), and set `realized_pnl`.
8. `COMMIT`; any failure rolls back the whole set.

**Lock order is fixed — order → portfolio → position — in every code path.** Two transactions on *different* orders but the same portfolio acquire different order locks, then queue on the portfolio lock in the same sequence, so no cycle can form. Never lock in a different order "because it is convenient".

---

## 8. OLTP → Medallion Contract

### 8.1 Bronze extraction watermark (v1.2)

**`trade_id` is the dedupe key, not the watermark.** A PostgreSQL identity column comes from a sequence, and sequence allocation order is not commit order:

1. Transaction A takes `trade_id = 100` and stays open.
2. Transaction B takes `101` and commits.
3. The extractor reads `max(trade_id) = 101` and records that as its watermark.
4. A commits.
5. `WHERE trade_id > 101` never sees 100 again.

So Bronze extracts on `created_at` with an overlap window:

```sql
SELECT * FROM trades
 WHERE created_at >= :last_extract_time - INTERVAL '1 hour'
   AND created_at <  now() - INTERVAL '1 minute';
```

Three properties make this safe:

- `created_at` defaults to `now()`, which is **transaction start time**, not commit time. A transaction can therefore never have a `created_at` later than the moment it began, so a record can only appear *behind* a watermark, never ahead of it — an overlap window catches it.
- The trailing `now() - 1 minute` keeps the newest, still-committing edge out of the batch.
- Bronze rewrites are idempotent: land the batch, then dedupe on `trade_id` (and `(order_id, fill_seq)`) before appending, so an overlapping batch cannot double-count.

**The assumption behind the 1-hour overlap, stated explicitly.** The overlap is a guarantee only if no write transaction stays open longer than the overlap. A transaction open for 75 minutes *would* escape a 1-hour window — its `created_at` is far behind the watermark by the time it commits. That is why the bound is enforced rather than assumed:

| Bound | Value |
|---|---|
| Target fill transaction (7.2) | < 50 ms — three row locks, arithmetic, commit; no external calls, no user waits, no batch work inside |
| `lock_timeout` on the API role | 2 s |
| `statement_timeout` on the API role | 5 s |
| Overlap | 1 hour ≈ 720× the timeout budget |

The consequence: a transaction that would exceed the window is **aborted by timeout**, not left running to escape it. If a future long-running job (bulk load, migration) must write `trades`, it either runs against a table excluded from Bronze or the overlap is raised for that run — never left implicit.

**Reconciliation is the backstop, not the hope.** Daily `COUNT(*)`, `SUM(executed_quantity)` and `SUM(gross_amount)` per `trade_date`, recomputed from RDS and compared with Silver, catch any row that escaped the window for any reason (timeout, clock skew, a manual `executed_at` backfill). On a mismatch, re-extract a full snapshot for the affected days — Bronze is append-only and deduped, so re-extraction is safe.

**What Bronze does not rely on:** `trade_id > last_max` as an exact watermark. That is only safe with no concurrent writes, which is not this system. If a strict guarantee were required, the answer is logical decoding (CDC), not an identity sequence — out of scope here.

**Business time stays separate:** `executed_at` remains the time trades *happened*, and is what `trade_date` in Silver and the heatmap axis are derived from. Recording time (`created_at`) is never used for financial reporting.

**Reconciliation:** a periodic `full snapshot` count/`SUM` per day compared against Gold catches anything outside the overlap assumption.

### 8.2 Silver and Gold

**Silver** (one row per trade, denormalised). Pass-through: `trade_id`, `order_id`, `fill_seq`, `executed_at`, `execution_price`, `executed_quantity`, `commission`, `realized_pnl`. Joined: `portfolio_id`/`side`/`order_type` from `orders`; `stock_id`/`ticker`/`company_name`/`sector`/`market_cap_category`/`exchange` from `stocks` (via `orders.stock_id`); `trader_id`/`risk_tier`/`country` from `traders`. Derived: `gross_amount = execution_price × executed_quantity`; `commission_rate = commission / nullif(gross_amount, 0)`; `net_amount = gross + commission` (BUY) / `gross − commission` (SELL); `trade_date = (executed_at AT TIME ZONE 'UTC')::date`.

**Silver's actual job (v1.2):** RDS already rejects negative prices, zero quantities, negative commission, bad statuses and duplicate keys — so Silver is *not* where dirty financial rows are expected. Silver performs schema/type validation, referential-integrity validation, duplicate detection (overlapping batches), cross-table financial reconciliation (`filled_quantity` = Σ fills, cash movements), late-record handling inside the overlap window, and quarantine of genuinely bad source or historical records. "Drop invalid rows" is defence in depth, not the primary mechanism.

**Gold** (one row per date × stock × trader): `trade_count = COUNT(*)` (count of **fills**, not orders); `buy_volume`/`sell_volume = SUM(executed_quantity) FILTER (WHERE side = …)`; `total_traded_value = SUM(gross_amount)`; `total_traded_quantity = SUM(executed_quantity)`; `avg_execution_price = SUM(gross_amount) / SUM(executed_quantity)` (**not** `AVG(price)`, and **not** a stored average); `total_commission = SUM(commission)`; `net_profit_loss = SUM(realized_pnl)`.

| Measure | Additive? |
|---|---|
| trade_count, buy_volume, sell_volume, total_traded_value, total_traded_quantity, total_commission, net_profit_loss | additive — `SUM` |
| avg_execution_price | **non-additive** — recompute as `SUM(total_traded_value) / NULLIF(SUM(total_traded_quantity), 0)` |

`dim_stock` from `stocks`; `dim_trader` from `traders` (`trader_code = 'T' || lpad(trader_id::text,6,'0')`); `dim_date` generated over the **full dataset range, 2025-01-01 … 2026-12-31 inclusive = 730 calendar days** (365 + 365; both years are common years), with `is_trading_day` from the weekday/holiday rule — **not** from OLTP, and not a 500-day window (v1.2: 500 days does not cover the PID's 24 months). Generate with `generate_series('2025-01-01'::date, '2026-12-31'::date, '1 day')` and assert `count(*) = 730`.

---

## 9. Migration & Seeding

- **Alembic is the source of truth**; models in `api/app/models/`, engine/session in `api/app/db/`. `alembic revision --autogenerate` must produce an **empty** diff against this design — a non-empty diff is drift.
- **Seed order:** `stocks` → `price_history` → `traders` → `portfolios` → `orders` → `trades` → `positions`. Set `stocks.current_price` from the latest bar; give each portfolio its opening cash (§4); rebuild `positions` from `trades` at the end and assert it matches.
- **Load:** generate in 50,000-row chunks → `COPY` into an `UNLOGGED` staging table → set-based `INSERT … SELECT`. `COPY` is ~10× faster than row inserts, and staging pays constraint/index cost once per batch. Commit per batch; never disable triggers (`session_replication_role` is restricted on RDS). `ANALYZE trades` afterwards or the extract plans from stale stats.
- **Reset:** `TRUNCATE TABLE trades, orders, positions, price_history, portfolios, traders, stocks RESTART IDENTITY;` — children listed explicitly, so no `CASCADE` and nothing unexpected vanishes. `RESTART IDENTITY` reproduces identical keys on re-seed.
- **Regeneration is a reset, not a merge (v1.2):** a fixed seed plus `RESTART IDENTITY` reproduces the same `order_id`/`trade_id` values, so re-running the generator means truncating and reloading — never `INSERT`-ing a second generated dataset alongside the first. No `source_trade_id` column exists, because a second identity would be a second source of truth for the same row (10.13).
- **Idempotency:** the two `UNIQUE` keys turn a duplicate re-run of the *loader* into a conflict, not a double count. Re-runs use `ON CONFLICT DO NOTHING` and fail loudly if conflicts exceed a tolerance.

---

## 10. Decisions to Review

| # | Decision | Options | Cost if changed late | Challenge |
|---|---|---|---|---|
| 10.1 | **7th table `positions`** | table / aggregate / JSON on portfolio | moderate — touches API, generator, seed order | Does the PID's "5+ tables" allow 7, and must the ERD in the report change? |
| 10.2 | **`trades.realized_pnl` stored** | store at fill / FIFO in Silver / drop `net_profit_loss` | **high** — removing it makes Gold's P&L unfillable | Is simulator-computed P&L acceptable as source truth? If not, drop the column **now**. |
| 10.3 | **`total_equity` not stored** | omit / maintain on fill / materialised view | low (DB), but API must compute it | PID's table lists it — the report must record the deviation or contradict the schema. |
| 10.4 | **`citext` email** | citext / unique `lower(email)` / plain | medium — duplicates block index creation | Does the RDS extension list allow `citext`? |
| 10.5 | **cached `filled_quantity`** | cache / always `SUM` | low, but a wrong value is invisible | Accept a second writer + nightly check, or drop the cache? |
| 10.6 | **no `trades` partitioning** | heap / monthly RANGE / BRIN | low | If marks reward partitioning, that's a reporting choice — say so explicitly. |
| 10.7 | **no `stock_id` on `trades`** | normalised / denormalised | low | Is the 1M-row Silver join worth avoiding? |
| 10.8 | **`RESTRICT` on every FK** | RESTRICT / CASCADE | low | Any demo script that deletes traders/portfolios must delete leaves first. |
| 10.9 | **`VARCHAR` + `CHECK` enums** | CHECK / native ENUM | low | — |
| 10.10 | **session rule in generator, not DB** | generator / CHECK / lookup table | low | Puts the rule in two places if also in Silver. |
| 10.11 | **what Silver can actually clean** | — | — | With these constraints RDS cannot hold dirty rows, so Silver's "drop invalid" is defence-in-depth. **State this in the report**, or produce a controlled bad batch in Bronze. |
| 10.12 | **`trade_id` is a dedupe key, not a watermark** | created_at+overlap / trade_id / CDC | low now, high later | Commit order ≠ sequence order. If the overlap assumption is unacceptable, CDC is the only strict answer. |
| 10.13 | **no `source_trade_id`** | add / rely on reset+reseed | medium — a column on 1M rows | Regeneration is documented as reset, not merge. Does the marker expect provenance columns? |
| 10.14 | **no cash ledger table** | ledger / opening-balance assumption | medium — 8th table, second source of truth | Opening cash is a seeded constant; cash movements are reconstructible from `trades`. Acceptable for the PID scope? |
| 10.15 | **no aggregate-fill trigger** | trigger / app validation under order lock | low | A `SUM()` per insert over 1M trades loses the staging-load design (9). Nightly recon instead. |
| 10.16 | **`avg_cost` reset to 0 on full exit** | reset / retain last basis | low | A re-entry cannot inherit stale basis; the P&L was already realised on the closing fill. |

---

## 11. Validation Status

Executed against a throwaway `postgres:15` container — v1.1 on 2026-11-14, re-run for v1.2 on 2026-11-15.

- [x] `citext` extension creates; `AYESHA@Example.COM` rejected after `ayesha@example.com`.
- [x] Full DDL runs in dependency order — 7 tables, 19 indexes, 30 `CHECK` constraints, exit 0.
- [x] `TRUNCATE … RESTART IDENTITY` without `CASCADE` succeeds and resets identity.
- [x] Rejected: duplicate `(order_id, fill_seq)`; duplicate `(stock_id, trade_date)`; `filled_quantity > quantity`; negative cash; negative position; inverted OHLC; zero-quantity trade; `LIMIT` without `limit_price`; **`MARKET` with `limit_price`**; **`FILLED` with `filled_quantity = 0`**; **`PARTIALLY_FILLED` with `filled_quantity = quantity`**; **flat position with non-zero `avg_cost`**; bad `status`; bad `risk_tier`; lowercase ticker.
- [x] `updated_at` trigger fires on UPDATE, `created_at` unchanged.
- [x] Full order-status matrix (quantity 10): **rejected** `PENDING`/3, `PARTIALLY_FILLED`/0, `REJECTED`/1, `FILLED`/9; **accepted** `CANCELLED`/0, `CANCELLED`/4, `MARKET` with `limit_price = NULL`, `LIMIT` with 190.00.
- [x] The legal transition still works: 15 of 15 filled ⇒ `FILLED` accepted, then `PARTIALLY_FILLED` rejected by `orders_status_matches_fills`.
- [x] Accounting policy (7.1) reproduced by a reference implementation: `avg_cost` 100.5 → 107.2 → 107.2 (unchanged on partial sale) → 0 on exit; `realized_pnl` 132.8 + 23.2 = **156.0**, equal to `(gross − commissions) − total cost basis = 1764 − 1608`.
- [x] `generate_series('2025-01-01','2026-12-31','1 day')` = **730 rows, 522 weekdays** — the date-dimension claim (8.2) and the price-history estimate both check out.
- [x] Deleting a `stocks` parent is refused by `price_history_stock_fk`, and a `portfolios` parent by `positions_portfolio_fk` — `RESTRICT`, no `CASCADE` remains. Delete succeeds once children are gone.
- [ ] RDS behaviour unverified — `citext` not yet created there (fallback in 10.4).
- [ ] Bulk-load timing at 1M rows unmeasured; section 9 is a design, not a benchmark.
- [ ] Concurrency behaviour (7.2) is reasoned from Postgres lock semantics, not stress-tested with two concurrent sessions; needs an integration test once the API exists.
- [ ] The accounting test above validates the *policy*, not the API — no application code applies it yet.

---

## 12. Rejected Alternatives

UUID keys (no distributed writer, wider indexes) · partitioned `trades` (no gain at 1M rows) · native `ENUM` (migration + Spark friction) · stored `total_equity` (stale financial figure) · `FLOAT` money (unreconcilable sums) · naive `TIMESTAMP` (lost offset) · `CASCADE` on any FK (destroys audit trail; also never fired) · trigger-based state machine (most complex object in a schema meant to be read; app + nightly validator is proportionate) · ORM-only constraints (the 1M loader bypasses the ORM) · `stock_id` on `trades` (duplicates an order fact for a query that doesn't exist) · one trade per order (fails the partial-fill requirement) · **`source_trade_id`** (second identity on 1M rows for a regeneration flow already handled by reset+reseed) · **`cash_transactions` ledger** (8th table, second source of truth, out of PID scope) · **aggregate-fill trigger** (per-insert `SUM()` defeats bulk loading) · **`CHAR(2)` → `VARCHAR(2)`** (no benefit for fixed-width ISO codes) · **`trade_id` as extraction watermark** (sequence allocation ≠ commit order).

---

## 13. Change Log — v1.1 → v1.2

Accepted from review:

1. Bronze extraction moved off `executed_at` and off `trade_id > last_max`: `created_at` + overlap window, `trade_id` as dedupe key, concurrency assumption documented (8.1, 10.12).
2. Order-row lock added to the fill protocol, with a fixed lock ordering to avoid deadlocks (7.2).
3. Weighted-average cost and realized P&L policy specified, including commission capitalisation and rounding (7.1).
4. `MARKET ⇒ limit_price IS NULL` and `status` ⇔ `filled_quantity` consistency enforced by `CHECK` (§4, §5).
5. `dim_date` covers the full 24-month range, 731 rows, with a trading-day flag (8.2).
6. `ON DELETE CASCADE` removed from `price_history` and `positions`; `ON DELETE RESTRICT` written explicitly on all eight FKs (§2, §5). The old cascades were dead code — the `orders` FK blocked the parent delete first.
7. Opening portfolio cash and `current_price` ↔ `price_history` synchronisation documented (§4, §9).
8. PID corrected: the additive-measures claim and the Silver cleaning description.

Rejected, with reasons in §10 and §12: `source_trade_id`, `cash_transactions`, aggregate-fill trigger, `CHAR(2)` → `VARCHAR(2)`, `trade_id` as an exact watermark.
