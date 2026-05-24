# QUICK START GUIDE
# EMA Crossover Analytics Dataset Pipeline

## 🚀 Setup (10 minutes)

### Step 1: Create Analytics Supabase Project

1. Go to https://supabase.com/dashboard
2. Click "New Project"
3. Name: `ema-analytics` (or any name you prefer)
4. Set a strong password
5. Choose region closest to you
6. Wait for project creation (~2 minutes)

### Step 2: Create Database Table

1. In your new project, click **SQL Editor**
2. Copy the entire contents of `analytics_schema.sql`
3. Paste into SQL Editor
4. Click **Run**
5. Verify in **Table Editor** → you should see `crossover_analytics` table

### Step 3: Get API Credentials

1. In your project, click **Settings** → **API**
2. Copy these two values:
   - **Project URL** (looks like: `https://xxxxx.supabase.co`)
   - **anon/public key** (starts with `eyJ...`)

### Step 4: Configure Environment

Create a `.env` file (or add to your existing one):

```bash
# Analytics Supabase credentials (NEW project)
ANALYTICS_SUPABASE_URL=https://your-project.supabase.co
ANALYTICS_SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Coins to analyze (match your main pipeline)
ANALYTICS_COINS=BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT

# Historical lookback
ANALYTICS_HISTORICAL_DAYS=250
```

### Step 5: Validate Setup

```bash
python validate_analytics.py
```

Expected output:
```
✅ PASS - Environment
✅ PASS - Database Connection
✅ PASS - Data Quality
✅ PASS - UTC Alignment

🎉 All checks passed! Analytics pipeline is ready to use.
```

---

## 📊 First Run (Initial Backfill)

Fetch 250 days of historical data:

```bash
python analytics_pipeline.py --initial
```

**What happens:**
- Fetches ~24,000 candles per coin (250 days × 15-minute intervals)
- Detects all EMA crossovers
- Calculates MFE/MAE/optimal entry for each trade
- Inserts to analytics database

**Expected time:** 5-15 minutes (depending on number of coins)

**Expected output:**
```
Processing BTCUSDT
  ✓ Fetched 24,000 candles
  ✓ Detected 347 crossovers
  ✓ Calculated metrics for 346 trade windows
  ✓ Inserted 346 new records

[... similar for other coins ...]

PIPELINE COMPLETE
Duration: 412.3 seconds
New records inserted: 1,523
```

---

## 🔄 Daily Updates

After initial backfill, run daily to catch new crossovers:

```bash
python analytics_pipeline.py
```

**What happens:**
- Checks last processed crossover
- Fetches only NEW candles since then
- Processes new crossovers
- Much faster (30 seconds - 2 minutes)

**Schedule with cron:**
```bash
0 2 * * * cd /path/to/project && python analytics_pipeline.py >> analytics.log 2>&1
```

**Or GitHub Actions:**
See `README_ANALYTICS.md` for workflow file

---

## 🔍 Verify Data Quality

Run these SQL queries in Supabase SQL Editor:

**1. Count per symbol:**
```sql
SELECT symbol, COUNT(*) as crossovers
FROM crossover_analytics
GROUP BY symbol;
```

**2. Average metrics:**
```sql
SELECT 
  signal,
  COUNT(*) as trades,
  ROUND(AVG(mfe_percent), 2) as avg_mfe,
  ROUND(AVG(mae_percent), 2) as avg_mae,
  ROUND(AVG(pnl_percent), 2) as avg_pnl
FROM crossover_analytics
GROUP BY signal;
```

**3. Date coverage:**
```sql
SELECT 
  symbol,
  MIN(crossover_utc) as earliest,
  MAX(crossover_utc) as latest,
  COUNT(*) as total
FROM crossover_analytics
GROUP BY symbol;
```

---

## 🤝 Merge with Main Dataset

When ready for ML training:

```bash
python merge_datasets.py
```

**What happens:**
- Fetches from BOTH Supabase projects
- Merges on UTC timestamp + symbol
- Saves to `combined_dataset.csv`

**Output:**
```
✅ Fetched 2,341 signals from main dataset
✅ Fetched 1,523 crossovers from analytics dataset
✅ Merged dataset: 1,458 complete records
✅ Saved to combined_dataset.csv
```

**Then in your ML notebook:**
```python
import pandas as pd

df = pd.read_csv('combined_dataset.csv')

# Features: 35 technical indicators from main dataset
X = df.drop(columns=['utc', 'symbol', 'signal', 
                     'mfe_percent', 'mae_percent', 
                     'pnl_percent', 'optimal_entry'])

# Target: Trade metrics from analytics dataset
y_mfe = df['mfe_percent']      # Predict max profit potential
y_mae = df['mae_percent']      # Predict max drawdown
y_optimal = df['optimal_entry']  # Predict best entry price

# Train your model
from sklearn.model_selection import train_test_split
X_train, X_test, y_train, y_test = train_test_split(X, y_mfe, test_size=0.2)
```

---

## 📁 Files Overview

**Core Pipeline:**
- `analytics_config.py` - Configuration
- `analytics_db.py` - Database operations
- `analytics_fetcher.py` - Binance API calls
- `analytics_crossovers.py` - EMA crossover detection
- `analytics_metrics.py` - MFE/MAE calculations
- `analytics_pipeline.py` - **Main entry point**

**Setup & Validation:**
- `analytics_schema.sql` - Database table schema
- `validate_analytics.py` - Setup validation
- `.env.analytics.example` - Environment template

**Usage:**
- `merge_datasets.py` - Merge main + analytics for ML
- `README_ANALYTICS.md` - Full documentation
- `QUICKSTART.md` - This file

---

## 🆘 Troubleshooting

### "Failed to create analytics Supabase client"
→ Check `.env` file has correct `ANALYTICS_SUPABASE_URL` and `ANALYTICS_SUPABASE_KEY`

### "Table 'crossover_analytics' doesn't exist"
→ Run `analytics_schema.sql` in Supabase SQL Editor

### "No crossovers detected"
→ Check if coin has sufficient history (try BTCUSDT first)

### "Duplicate key violation"
→ Expected and harmless (records already exist)

### Merge returns 0 records
→ Main and analytics datasets have no matching UTC timestamps
→ Both pipelines must process the same coins

---

## ✅ Checklist

- [ ] Created analytics Supabase project
- [ ] Ran `analytics_schema.sql` to create table
- [ ] Set environment variables in `.env`
- [ ] Ran `validate_analytics.py` (all checks pass)
- [ ] Ran initial backfill: `python analytics_pipeline.py --initial`
- [ ] Verified data in Supabase Table Editor
- [ ] Scheduled daily updates (cron or GitHub Actions)
- [ ] Merged datasets: `python merge_datasets.py`
- [ ] Ready for ML training! 🎉

---

## 📚 Next Steps

1. **Explore the data** - Run SQL queries to understand patterns
2. **Schedule automation** - Set up daily cron job or GitHub Actions
3. **Train ML models** - Use combined dataset to predict MFE/MAE
4. **Iterate** - Add more coins, adjust lookback period, experiment

**Full documentation:** See `README_ANALYTICS.md`

**Questions?** All files are heavily commented with explanations.
