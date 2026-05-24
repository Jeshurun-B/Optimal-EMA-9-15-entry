# GitHub Actions Setup for Analytics Pipeline

## Overview

This guide shows how to automate the analytics pipeline using GitHub Actions, running every ~30 hours to collect new crossover data.

---

## 📁 Workflow Files

You have **two workflow options**:

### Option 1: Simple Daily Schedule (Recommended for Most Users)
**File:** `.github/workflows/analytics_pipeline.yml`

- Runs daily at 3 AM UTC
- Simple and reliable
- Easy to understand and debug
- ~24 hour interval (good enough for most use cases)

### Option 2: Smart 30-Hour Schedule (Advanced)
**File:** `.github/workflows/analytics_smart_schedule.yml`

- Checks every 12 hours
- Only runs if 30+ hours since last execution
- More complex logic
- True ~30 hour interval
- Requires state file persistence

**Pick one based on your needs. For simplicity, use Option 1.**

---

## 🔧 Setup Instructions

### Step 1: Copy Workflow Files

Copy the workflow files to your repository:

```bash
# Create workflows directory
mkdir -p .github/workflows

# Copy the workflow file (choose one)
# Option 1: Daily schedule
cp analytics_pipeline.yml .github/workflows/

# OR Option 2: 30-hour smart schedule
cp analytics_smart_schedule.yml .github/workflows/
```

### Step 2: Copy Analytics Pipeline Files

Ensure all analytics files are in your repository root:

```
your-repo/
├── .github/
│   └── workflows/
│       └── analytics_pipeline.yml (or analytics_smart_schedule.yml)
├── analytics_config.py
├── analytics_db.py
├── analytics_fetcher.py
├── analytics_crossovers.py
├── analytics_metrics.py
├── analytics_pipeline.py
├── analytics_schema.sql
├── validate_analytics.py
├── merge_datasets.py
└── requirements.txt
```

### Step 3: Add GitHub Secrets

Go to your GitHub repository → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add these secrets:

| Secret Name                    | Value                                      | Required |
|--------------------------------|--------------------------------------------|----------|
| `ANALYTICS_SUPABASE_URL`       | `https://xxxxx.supabase.co`                | ✅ Yes   |
| `ANALYTICS_SUPABASE_KEY`       | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`  | ✅ Yes   |
| `ANALYTICS_COINS`              | `BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT` | Optional |
| `ANALYTICS_HISTORICAL_DAYS`    | `250`                                      | Optional |
| `ANALYTICS_INCREMENTAL_DAYS`   | `3`                                        | Optional |
| `ANALYTICS_API_CALL_LIMIT`     | `500`                                      | Optional |

**Note:** If `ANALYTICS_COINS` is not set, it will try to use your existing `COINS` secret from the main pipeline.

### Step 4: Commit and Push

```bash
git add .github/workflows/analytics_pipeline.yml
git add analytics_*.py validate_analytics.py merge_datasets.py
git commit -m "Add analytics pipeline automation"
git push origin main
```

---

## 🚀 Running the Pipeline

### First Run: Initial Backfill

**This MUST be done manually the first time** to fetch 250 days of historical data.

1. Go to GitHub → **Actions** tab
2. Click **"EMA Analytics Pipeline"** (or your workflow name)
3. Click **"Run workflow"** button
4. Select:
   - **Task:** `initial-backfill`
5. Click **"Run workflow"**

**Expected duration:** 15-30 minutes

**What it does:**
- Fetches ~24,000 candles per coin (250 days × 15-minute intervals)
- Detects all crossovers
- Calculates trade metrics
- Inserts to analytics database

### Automatic Runs: Daily Updates

After the initial backfill, the workflow runs automatically:

**Option 1 (Daily):** Every day at 3 AM UTC
**Option 2 (30-hour):** Every ~30 hours

**Expected duration:** 1-5 minutes

**What it does:**
- Checks last processed crossover
- Fetches only NEW candles
- Processes new crossovers
- Much faster than initial run

### Manual Trigger Anytime

You can manually trigger the workflow anytime:

1. Go to **Actions** → Your workflow
2. Click **"Run workflow"**
3. Select:
   - **Task:** `incremental` (for updates) or `initial-backfill` (to re-fetch everything)
4. Click **"Run workflow"**

---

## 📊 Monitoring Runs

### View Workflow Runs

**GitHub → Actions tab**

You'll see all runs with:
- ✅ Success (green checkmark)
- ❌ Failure (red X)
- 🟡 In progress (yellow circle)

Click any run to see detailed logs.

### Successful Run Output

```
🟢 Running INCREMENTAL UPDATE
⏱️  Expected duration: 1-5 minutes
📊 Fetching only new data since last run

======================================================================
Processing BTCUSDT
======================================================================
Mode: Incremental update (last crossover: 2026-05-24, fetching 3 days)
  ✓ Fetched 288 candles
  ✓ Detected 2 crossovers
  ✓ Calculated metrics for 1 trade window
  ✓ Inserted 1 new record

[... other coins ...]

======================================================================
PIPELINE COMPLETE
======================================================================
Duration: 43.2 seconds
New records inserted: 4
API calls made: 8
Total records in database: 1,527
======================================================================
```

### Failed Run

If a run fails:
1. Click the failed run
2. Expand the **"Run Analytics Pipeline"** step
3. Look for error messages (usually at the bottom)

**Common errors:**

| Error Message                          | Solution                                    |
|----------------------------------------|---------------------------------------------|
| `Failed to create analytics client`    | Check `ANALYTICS_SUPABASE_URL/KEY` secrets  |
| `Table 'crossover_analytics' not found`| Run `analytics_schema.sql` in Supabase      |
| `Timeout`                              | Increase `timeout-minutes` in workflow      |

Error logs are automatically uploaded as artifacts for failed runs.

---

## 🔍 Verifying Data

After runs, verify data in your analytics Supabase:

1. Go to your analytics Supabase project
2. Click **Table Editor** → `crossover_analytics`
3. You should see new records being added

**SQL queries to run:**

```sql
-- Count per symbol
SELECT symbol, COUNT(*) as crossovers
FROM crossover_analytics
GROUP BY symbol;

-- Latest crossovers
SELECT *
FROM crossover_analytics
ORDER BY crossover_utc DESC
LIMIT 10;

-- Date coverage
SELECT 
  symbol,
  MIN(crossover_utc) as earliest,
  MAX(crossover_utc) as latest
FROM crossover_analytics
GROUP BY symbol;
```

---

## ⚙️ Advanced Configuration

### Adjust Schedule

Edit `.github/workflows/analytics_pipeline.yml`:

```yaml
on:
  schedule:
    # Change the cron expression
    - cron: "0 3 * * *"  # Daily at 3 AM UTC
    # Examples:
    # - cron: "0 */6 * * *"   # Every 6 hours
    # - cron: "0 0 * * *"     # Daily at midnight
    # - cron: "0 0 * * 0"     # Weekly on Sunday
```

**Cron syntax:** `minute hour day month dayOfWeek`

**Test your cron:** https://crontab.guru/

### Increase Timeout

If initial backfill times out (>90 minutes), increase:

```yaml
jobs:
  run-analytics:
    timeout-minutes: 120  # Increase from 90 to 120
```

### Run Multiple Times Daily

```yaml
on:
  schedule:
    - cron: "0 3 * * *"   # 3 AM UTC
    - cron: "0 15 * * *"  # 3 PM UTC
```

### Conditional Execution

Only run on specific days:

```yaml
- name: Check if should run
  id: check-day
  run: |
    if [ $(date +%u) -eq 1 ]; then  # Monday only
      echo "should_run=true" >> $GITHUB_OUTPUT
    else
      echo "should_run=false" >> $GITHUB_OUTPUT
    fi

- name: Run Analytics
  if: steps.check-day.outputs.should_run == 'true'
  # ... rest of the step
```

---

## 🐛 Troubleshooting

### Workflow Not Running

**Check:**
1. Workflow file is in `.github/workflows/` directory
2. File has `.yml` extension
3. Workflow is enabled (Actions tab → select workflow → Enable if needed)
4. Cron schedule is valid

### "Resource not accessible by integration"

**Solution:** Enable workflow permissions
1. Settings → Actions → General
2. Scroll to "Workflow permissions"
3. Select "Read and write permissions"
4. Save

### API Rate Limits

If you hit Binance rate limits during initial backfill:

**Option 1:** Reduce coin count temporarily
```yaml
env:
  ANALYTICS_COINS: "BTCUSDT,ETHUSDT"  # Start with just 2 coins
```

**Option 2:** Increase timeout and let retries work
```yaml
timeout-minutes: 120
```

### State File Not Persisting (Option 2 only)

The smart schedule workflow uploads `analytics_state.json` as an artifact, but doesn't restore it automatically.

**Workaround:** Use Option 1 (daily schedule) instead, which doesn't rely on state file persistence.

---

## 📈 Monitoring & Alerts

### Enable Email Notifications

GitHub automatically sends emails on workflow failures to the repository owner.

**To customize:**
1. GitHub profile → Settings → Notifications
2. Configure Actions notifications

### Slack/Discord Notifications

Add a notification step to your workflow:

```yaml
- name: Notify on failure
  if: failure()
  run: |
    curl -X POST -H 'Content-type: application/json' \
    --data '{"text":"Analytics pipeline failed! Check GitHub Actions."}' \
    ${{ secrets.SLACK_WEBHOOK_URL }}
```

(Add `SLACK_WEBHOOK_URL` to secrets)

---

## 🔄 Integration with Main Pipeline

Both pipelines can run independently:

**Main pipeline:** Every 23 hours (signal detection)
**Analytics pipeline:** Every 24-30 hours (trade metrics)

They write to **different Supabase projects**, so no conflicts.

**Merge them later:**
```bash
python merge_datasets.py
```

---

## ✅ Checklist

Before going live:

- [ ] Analytics Supabase project created
- [ ] `analytics_schema.sql` executed in Supabase
- [ ] Workflow file copied to `.github/workflows/`
- [ ] All analytics Python files committed
- [ ] GitHub secrets configured
- [ ] Initial backfill completed manually
- [ ] Verified data in Supabase
- [ ] Scheduled runs enabled
- [ ] Email notifications configured

---

## 📚 Summary

**Initial Setup:**
1. Create analytics Supabase project
2. Add GitHub secrets
3. Copy workflow file
4. Run initial backfill manually

**Ongoing:**
- Workflow runs automatically every 24-30 hours
- Fetches only new data (fast, 1-5 minutes)
- No manual intervention needed
- Check Supabase occasionally to verify data

**Result:**
- Automated analytics dataset collection
- Ready to merge with main dataset anytime
- Hands-off data pipeline 🎉
