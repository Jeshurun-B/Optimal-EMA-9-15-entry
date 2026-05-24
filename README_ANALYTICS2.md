# EMA Crossover Analytics Dataset Pipeline

## Overview

This is a **standalone analytics pipeline** that builds a comprehensive dataset of EMA crossover trade outcomes. It works independently from your main signal detection pipeline but is designed to merge seamlessly with it during ML training.

### What It Does

1. **Fetches Historical Data**: Pulls ~250 days of 15-minute candle data from Binance
2. **Detects Crossovers**: Identifies every 9/15 EMA crossover in the historical data
3. **Isolates Trade Windows**: Segments data between consecutive crossovers
4. **Calculates Metrics**: Computes optimal entry, MFE (Maximum Favorable Excursion), and MAE (Maximum Adverse Excursion)
5. **Stores Results**: Saves to a **separate Supabase project** with exact UTC alignment
6. **Incremental Updates**: Continues from the last processed crossover (no redundant fetches)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    ANALYTICS PIPELINE                        │
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │   Binance    │───>│  Crossover   │───>│   Metrics    │ │
│  │   Fetcher    │    │   Detector   │    │  Calculator  │ │
│  └──────────────┘    └──────────────┘    └──────────────┘ │
│         │                    │                    │         │
│         └────────────────────┴────────────────────┘         │
│                              │                              │
│                              ▼                              │
│                   ┌──────────────────┐                      │
│                   │  Analytics DB    │                      │
│                   │  (Supabase #2)   │                      │
│                   └──────────────────┘                      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    MAIN PIPELINE                             │
│                   (Your Existing System)                     │
│                                                              │
│                   ┌──────────────────┐                      │
│                   │   Signals DB     │                      │
│                   │  (Supabase #1)   │                      │
│                   └──────────────────┘                      │
└─────────────────────────────────────────────────────────────┘

                              │
                              │ MERGE DURING ML TRAINING
                              ▼
                   ┌──────────────────┐
                   │  Combined Dataset│
                   │  (35 features +  │
                   │   trade metrics) │
                   └──────────────────┘
```

---

## File Structure

```
analytics-pipeline/
├── analytics_config.py         # Configuration (Supabase URLs, coins, lookback)
├── analytics_db.py              # Database operations (Supabase client)
├── analytics_fetcher.py         # Binance API calls (paginated historical fetch)
├── analytics_crossovers.py      # EMA crossover detection logic
├── analytics_metrics.py         # MFE/MAE/optimal entry calculations
├── analytics_pipeline.py        # Main orchestrator (entry point)
├── analytics_schema.sql         # Supabase table schema
├── analytics_state.json         # Progress tracking (auto-generated)
├── analytics_error.log          # Error log (auto-generated)
└── README_ANALYTICS.md          # This file
```

---

## Setup Instructions

### 1. Create Analytics Supabase Project

This pipeline requires a **separate Supabase project** (different from your main signals database).

1. Go to [Supabase Dashboard](https://supabase.com/dashboard)
2. Create a new project (name it something like "ema-analytics")
3. Note the **Project URL** and **anon/public API Key**

### 2. Run Database Schema

In your new Supabase project:

1. Go to **SQL Editor**
2. Copy the contents of `analytics_schema.sql`
3. Run the SQL to create the `crossover_analytics` table
4. Verify table creation in **Table Editor**

### 3. Set Environment Variables

Create a `.env` file or set environment variables:

```bash
# Analytics Supabase (NEW project)
ANALYTICS_SUPABASE_URL=https://yyyyyyyyyyyy.supabase.co
ANALYTICS_SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Coins to analyze (should match main pipeline)
ANALYTICS_COINS=BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT

# Historical lookback (250 days recommended)
ANALYTICS_HISTORICAL_DAYS=250

# Incremental updates (3-7 days)
ANALYTICS_INCREMENTAL_DAYS=3

# API rate limit (500 calls per run)
ANALYTICS_API_CALL_LIMIT=500
```

### 4. Install Dependencies

```bash
pip install requests pandas python-dotenv supabase
```

All dependencies are already in your `requirements.txt` from the main pipeline.

---

## Usage

### Initial Backfill (First Run)

Fetch 250 days of historical data for all coins:

```bash
python analytics_pipeline.py --initial
```

**Expected behavior:**
- Fetches ~250 days of 15-minute candles per coin
- Detects all crossovers in historical data
- Calculates metrics for each trade window
- Inserts thousands of records to analytics database
- Takes 5-15 minutes depending on number of coins

**Example output:**
```
======================================================================
EMA CROSSOVER ANALYTICS PIPELINE
======================================================================
Started: 2026-05-24T18:30:00+00:00
Mode: INITIAL BACKFILL
Coins: 5
Interval: 15m
======================================================================

======================================================================
Processing BTCUSDT
======================================================================
Mode: Initial backfill (250 days)
  Fetching 15m history for BTCUSDT (250 days)...
    Reached target date - fetched 25 batches
    ✓ Got 24000 candles from 2025-09-07 to 2026-05-24
  ✓ Fetched 24000 candles
  ✓ Date range: 2025-09-07 to 2026-05-24
  ✓ Detected 347 crossovers
  ✓ Calculated metrics for 346 trade windows
  ✓ Inserted 346 new records to analytics database

[... similar for ETHUSDT, SOLUSDT, etc ...]

======================================================================
PIPELINE COMPLETE
======================================================================
Duration: 412.3 seconds
Coins processed: 5
New records inserted: 1,523
API calls made: 127
Total records in database: 1,523
  BTCUSDT: 346 records
  ETHUSDT: 298 records
  SOLUSDT: 312 records
  XRPUSDT: 289 records
  DOGEUSDT: 278 records
======================================================================
```

### Incremental Updates (Subsequent Runs)

Only fetch new data since last run:

```bash
python analytics_pipeline.py
```

**Expected behavior:**
- Checks last processed crossover per coin
- Fetches only NEW candles since then
- Processes new crossovers
- Much faster (30 seconds - 2 minutes)

**Example output:**
```
======================================================================
Processing BTCUSDT
======================================================================
Mode: Incremental update (last crossover: 2026-05-23, fetching 3 days)
  Fetching 15m history for BTCUSDT (3 days)...
    ✓ Got 288 candles from 2026-05-21 to 2026-05-24
  ✓ Detected 2 crossovers
  ✓ Calculated metrics for 1 trade window
  ✓ Inserted 1 new record to analytics database

[... similar for other coins ...]

======================================================================
PIPELINE COMPLETE
======================================================================
Duration: 28.7 seconds
Coins processed: 5
New records inserted: 4
API calls made: 8
Total records in database: 1,527
======================================================================
```

---

## Database Schema

### Table: `crossover_analytics`

| Column               | Type         | Description                                      |
|----------------------|--------------|--------------------------------------------------|
| `id`                 | BIGSERIAL    | Auto-increment primary key                       |
| `crossover_utc`      | TIMESTAMPTZ  | **UTC timestamp of crossover** (merge key)       |
| `symbol`             | TEXT         | Trading pair (e.g., "BTCUSDT")                   |
| `signal`             | TEXT         | "LONG" or "SHORT"                                |
| `entry_price`        | NUMERIC      | Price at crossover                               |
| `optimal_entry`      | NUMERIC      | Best entry price in window                       |
| `mfe_percent`        | NUMERIC      | Maximum Favorable Excursion (%)                  |
| `mae_percent`        | NUMERIC      | Maximum Adverse Excursion (%)                    |
| `trade_duration`     | INTEGER      | Number of candles in trade window                |
| `next_crossover_utc` | TIMESTAMPTZ  | UTC timestamp of next crossover                  |
| `exit_price`         | NUMERIC      | Price at next crossover                          |
| `pnl_percent`        | NUMERIC      | Actual PnL from entry to exit (%)                |
| `created_at`         | TIMESTAMPTZ  | Record insertion timestamp                       |

**Unique Constraint:** `(symbol, crossover_utc)` - prevents duplicates

---

## Metrics Explained

### 1. Optimal Entry

**Definition:** Best possible entry price that existed **before** the MFE peak was reached.

**CRITICAL CONSTRAINT:** Temporal ordering matters!
- The optimal entry MUST occur chronologically **before** the MFE peak
- If the best price occurs **after** the peak, it's invalid (too late to capture max profit)

**Calculation:**
- **LONG signals:** Lowest low in the time window **before** reaching highest high
- **SHORT signals:** Highest high in the time window **before** reaching lowest low

**Example (LONG):**
```
Window prices (chronological):
  t0: $100 (entry)
  t1: $95  ← Optimal entry candidate
  t2: $110 ← MFE peak
  t3: $90  ← Lower, but INVALID (after peak)

Optimal entry: $95 ✅
Why not $90? It occurred AFTER the peak at $110
The constraint: t(optimal_entry) < t(MFE)
```

**Example (SHORT):**
```
Window prices (chronological):
  t0: $100 (entry)
  t1: $105 ← Optimal entry candidate
  t2: $90  ← MFE bottom
  t3: $108 ← Higher, but INVALID (after bottom)

Optimal entry: $105 ✅
Why not $108? It occurred AFTER the bottom at $90
```

**Why this matters:**
- Represents a **realistic** opportunity that existed before max profit
- You can't enter at the "best price" if it happens after the move is over
- Critical for ML models learning entry timing

### 2. MFE (Maximum Favorable Excursion)

**Definition:** Peak profit potential from entry point.

- **LONG signals:** (highest high - entry) / entry × 100
- **SHORT signals:** (entry - lowest low) / entry × 100

**Example:**
```
LONG entry at $100
Highest high in window: $108
MFE = (108 - 100) / 100 × 100 = 8.0%
(Trade had potential for 8% profit)
```

### 3. MAE (Maximum Adverse Excursion)

**Definition:** Worst drawdown before reaching peak profit.

- **LONG signals:** (lowest low - entry) / entry × 100 (negative = drawdown)
- **SHORT signals:** (entry - highest high) / entry × 100 (negative = drawdown)

**Example:**
```
LONG entry at $100
Lowest low before peak: $95
MAE = (95 - 100) / 100 × 100 = -5.0%
(Trade went 5% against you before recovering)
```

---

## Trade Window Isolation Logic

The core innovation of this pipeline is **crossover-to-crossover segmentation**:

```
Timeline:
─────┬──────────────────────────────┬──────────────────┬─────
     │                              │                  │
  Crossover 1                   Crossover 2       Crossover 3
  (LONG)                        (SHORT)           (LONG)
  Entry: $100                   Entry: $105       Entry: $102

Trade Window 1:
  Start: Crossover 1 UTC
  End:   Crossover 2 UTC
  Duration: 63 candles (15.75 hours)
  Metrics: Analyze price action in this window only

Trade Window 2:
  Start: Crossover 2 UTC
  End:   Crossover 3 UTC
  Duration: 48 candles (12 hours)
  Metrics: Analyze this window independently
```

**Key points:**
- Each crossover starts a new trade
- Previous trade closes when next crossover occurs
- No overlap between trades
- Last crossover is excluded (still open)

---

## Incremental Update Logic

### How It Works

1. **Check database:** "What was the last crossover UTC for BTCUSDT?"
2. **Fetch forward:** Pull candles from that UTC to now
3. **Process new crossovers only:** Skip already-analyzed data
4. **Insert new records:** Duplicates are silently ignored (UNIQUE constraint)

### Example Flow

**Initial run (Day 1):**
```
Fetch 250 days → Detect 346 crossovers → Insert 346 records
Last crossover: 2026-05-24 10:30 UTC
```

**Incremental run (Day 2):**
```
Query DB: "Last crossover = 2026-05-24 10:30"
Fetch from: 2026-05-24 10:30 to now (1 day of data)
Detect: 2 new crossovers
Insert: 1 new record (last crossover still open)
```

**Incremental run (Day 3):**
```
Query DB: "Last crossover = 2026-05-25 08:15"
Fetch from: 2026-05-25 08:15 to now
Detect: 3 new crossovers
Insert: 2 new records
```

**No redundant API calls. No duplicate processing.**

---

## UTC Alignment with Main Dataset

### Critical Requirement

The analytics dataset **MUST use identical UTC formatting** to the main dataset for reliable merging.

**Guaranteed by design:**
- Both systems use `pd.to_datetime(..., utc=True)`
- Both use `.isoformat()` for string conversion
- Both store as TIMESTAMPTZ in Supabase
- Both preserve millisecond precision

**Example matching records:**

**Main dataset (signals table):**
```
checked_at_utc: 2026-05-01T10:30:00+00:00
symbol: BTCUSDT
signal: LONG
adx_ltf: 32.5
ema_fast_ltf: 108250.0
... (35 features)
```

**Analytics dataset (crossover_analytics table):**
```
crossover_utc: 2026-05-01T10:30:00+00:00
symbol: BTCUSDT
signal: LONG
optimal_entry: 107900.0
mfe_percent: 4.8
mae_percent: -1.2
```

**Merge in Python/Pandas:**
```python
import pandas as pd
from supabase import create_client

# Fetch from main database
main_client = create_client(MAIN_URL, MAIN_KEY)
signals = main_client.table("signals").select("*").execute()
df_main = pd.DataFrame(signals.data)

# Fetch from analytics database
analytics_client = create_client(ANALYTICS_URL, ANALYTICS_KEY)
analytics = analytics_client.table("crossover_analytics").select("*").execute()
df_analytics = pd.DataFrame(analytics.data)

# Merge on UTC + symbol
df_combined = df_main.merge(
    df_analytics,
    left_on=["checked_at_utc", "symbol"],
    right_on=["crossover_utc", "symbol"],
    how="inner"
)

# Now you have 35 features + trade metrics in one DataFrame
print(df_combined.columns)
# Output: ['checked_at_utc', 'symbol', 'signal', 'adx_ltf', 'ema_fast_ltf', ...,
#          'optimal_entry', 'mfe_percent', 'mae_percent', 'trade_duration']
```

---

## Error Handling

### Graceful Degradation

- **One symbol fails:** Pipeline continues to next symbol
- **Network timeout:** Retries internally, logs error, moves on
- **Duplicate record:** Silently ignored (UNIQUE constraint)
- **Invalid data:** Skips that window, continues processing

### Error Logging

All errors are written to `analytics_error.log`:

```
[2026-05-24T18:45:23.123456+00:00] fetch_historical_klines error for LINKUSDT: HTTPError(429)
[2026-05-24T18:46:01.987654+00:00] insert_analytics failed for ETHUSDT: UniqueViolation
```

**No exceptions are raised to the caller.** The pipeline never crashes.

---

## Performance & Rate Limits

### API Call Budget

- **Initial backfill (5 coins):** ~125-150 calls
- **Incremental update (5 coins):** ~5-10 calls

Binance rate limit: ~1200 requests/minute (weight-based)

**We're well under the limit.**

### Runtime

- **Initial backfill:** 5-15 minutes (depending on number of coins)
- **Incremental update:** 30 seconds - 2 minutes

### Database Operations

- **Bulk inserts:** Used when possible (faster than individual inserts)
- **Duplicate handling:** UNIQUE constraint at database level (no manual checks needed)
- **Indexes:** Created on `symbol`, `crossover_utc`, and `signal` for fast queries

---

## Scheduling Recommendations

### Option 1: GitHub Actions (Automated)

Create `.github/workflows/analytics.yml`:

```yaml
name: Analytics Pipeline

on:
  schedule:
    # Run daily at 2:00 AM UTC
    - cron: '0 2 * * *'
  workflow_dispatch:  # Manual trigger

jobs:
  update-analytics:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: pip install -r requirements.txt
      
      - name: Run analytics pipeline
        env:
          ANALYTICS_SUPABASE_URL: ${{ secrets.ANALYTICS_SUPABASE_URL }}
          ANALYTICS_SUPABASE_KEY: ${{ secrets.ANALYTICS_SUPABASE_KEY }}
        run: python analytics_pipeline.py
```

**First run:** Trigger manually with `--initial` flag for backfill  
**Daily runs:** Automatic incremental updates

### Option 2: Cron Job (Local/Server)

```bash
# Daily at 2 AM
0 2 * * * cd /path/to/project && python analytics_pipeline.py >> analytics.log 2>&1
```

### Option 3: Manual Runs

```bash
# Initial backfill (once)
python analytics_pipeline.py --initial

# Daily updates (cron or manual)
python analytics_pipeline.py
```

---

## Data Quality Checks

### Validation Queries

Run these in Supabase SQL Editor to verify data quality:

**1. Count records per symbol:**
```sql
SELECT symbol, COUNT(*) as crossovers
FROM crossover_analytics
GROUP BY symbol
ORDER BY crossovers DESC;
```

**2. Check date coverage:**
```sql
SELECT 
  symbol,
  MIN(crossover_utc) as earliest,
  MAX(crossover_utc) as latest,
  COUNT(*) as total
FROM crossover_analytics
GROUP BY symbol;
```

**3. Average metrics per signal type:**
```sql
SELECT 
  signal,
  COUNT(*) as trades,
  ROUND(AVG(mfe_percent), 2) as avg_mfe,
  ROUND(AVG(mae_percent), 2) as avg_mae,
  ROUND(AVG(pnl_percent), 2) as avg_pnl,
  ROUND(AVG(trade_duration), 0) as avg_duration
FROM crossover_analytics
GROUP BY signal;
```

**4. Find best trades (highest MFE):**
```sql
SELECT 
  crossover_utc,
  symbol,
  signal,
  mfe_percent,
  pnl_percent,
  trade_duration
FROM crossover_analytics
ORDER BY mfe_percent DESC
LIMIT 20;
```

---

## Troubleshooting

### "Failed to create analytics Supabase client"

**Cause:** Missing or invalid `ANALYTICS_SUPABASE_URL` / `ANALYTICS_SUPABASE_KEY`

**Fix:**
1. Check `.env` file has correct values
2. Verify URL format: `https://xxxxx.supabase.co`
3. Verify key starts with `eyJ...`

### "Table 'crossover_analytics' doesn't exist"

**Cause:** Schema not created in Supabase

**Fix:**
1. Go to Supabase SQL Editor
2. Run `analytics_schema.sql`
3. Verify in Table Editor

### "No crossovers detected"

**Cause:** Coin might not have 250 days of history, or insufficient price movement

**Fix:**
- Check if coin is newly listed (reduce `ANALYTICS_HISTORICAL_DAYS`)
- Verify data fetched: look for "Got X candles" in output
- Try different coin (BTCUSDT always has data)

### "Duplicate key violation"

**Cause:** Re-running initial backfill with existing data

**Fix:**
- This is expected and harmless (records already exist)
- Pipeline silently skips duplicates
- Use incremental mode (`python analytics_pipeline.py` without `--initial`)

---

## Next Steps

### After Initial Backfill

1. **Verify data:** Run validation queries in Supabase
2. **Check coverage:** Ensure all coins have ~250 days of crossovers
3. **Schedule updates:** Set up GitHub Actions or cron for daily runs

### During ML Training

Merge analytics with main dataset:

```python
# Fetch both datasets
df_signals = fetch_from_supabase(MAIN_PROJECT, "signals")
df_analytics = fetch_from_supabase(ANALYTICS_PROJECT, "crossover_analytics")

# Merge on UTC + symbol
df_combined = df_signals.merge(
    df_analytics,
    left_on=["checked_at_utc", "symbol"],
    right_on=["crossover_utc", "symbol"],
    how="inner"  # Keep only crossovers with both signal features AND trade outcomes
)

# Now train your model
X = df_combined[FEATURE_COLUMNS]  # 35 features from main dataset
y_mfe = df_combined["mfe_percent"]  # Target from analytics dataset
y_mae = df_combined["mae_percent"]
y_optimal = df_combined["optimal_entry"]
```

---

## Summary

This analytics pipeline:

✅ **Fetches 250 days** of historical data (adjustable)  
✅ **Detects all crossovers** using your existing EMA logic  
✅ **Isolates trade windows** between consecutive crossovers  
✅ **Calculates metrics** (optimal entry, MFE, MAE)  
✅ **Stores in separate DB** with exact UTC alignment  
✅ **Incremental updates** (no redundant processing)  
✅ **Never crashes** (graceful error handling)  
✅ **Ready to merge** with main dataset during ML training  

**You now have a complete trade analytics system that complements your signal detection pipeline.**
