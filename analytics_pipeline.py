# analytics_pipeline.py
# ═════════════════════════════════════════════════════════════════════════════
# PURPOSE: Main orchestrator for the EMA Crossover Analytics Dataset Pipeline.
#
# WORKFLOW:
#   1. Fetch historical candle data (250 days initial, 3 days incremental)
#   2. Detect all EMA crossovers
#   3. Isolate trade windows between consecutive crossovers
#   4. Calculate metrics: optimal entry, MFE, MAE
#   5. Store in separate analytics Supabase project
#   6. Track progress for incremental updates
#
# CRITICAL FEATURES:
#   - Smart resume: only fetches NEW data after initial backfill
#   - UTC preservation: exact alignment with main dataset
#   - Incremental updates: no redundant API calls
#   - Graceful error handling: one symbol failure doesn't stop others
# ═════════════════════════════════════════════════════════════════════════════

import json
from datetime import datetime, timezone, timedelta
from analytics_config import (
    COINS,
    INTERVAL,
    HISTORICAL_DAYS,
    INCREMENTAL_LOOKBACK_DAYS,
    ANALYTICS_STATE_FILE
)
from analytics_fetcher import (
    fetch_historical_klines,
    fetch_from_timestamp,
    get_analytics_api_calls,
    log_analytics_error
)
from analytics_crossovers import detect_crossovers, get_next_crossover
from analytics_metrics import calculate_trade_metrics, calculate_pnl_percent
from analytics_db import (
    get_last_crossover_utc,
    insert_analytics,
    bulk_insert_analytics,
    count_analytics_records
)


# ══════════════════════════════════════════════════════════════════════════════
#                              STATE MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

def load_analytics_state() -> dict:
    """
    Load pipeline state from JSON file.
    Tracks which symbols have been processed and when.
    """
    try:
        with open(ANALYTICS_STATE_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        log_analytics_error(f"Failed to load state: {repr(e)}")
        return {}


def save_analytics_state(state: dict) -> None:
    """
    Save pipeline state to JSON file.
    """
    try:
        with open(ANALYTICS_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2, default=str)
    except Exception as e:
        log_analytics_error(f"Failed to save state: {repr(e)}")


# ══════════════════════════════════════════════════════════════════════════════
#                              PROCESS ONE SYMBOL
# ══════════════════════════════════════════════════════════════════════════════

def process_symbol(symbol: str, is_initial_run: bool = False) -> int:
    """
    Process one trading pair: detect crossovers and calculate metrics.
    
    Args:
        symbol: Trading pair (e.g., "BTCUSDT")
        is_initial_run: True for first backfill (250 days), False for updates (3 days)
    
    Returns:
        Number of analytics records inserted
    
    Workflow:
        1. Determine date range (initial backfill vs incremental update)
        2. Fetch candle data from Binance
        3. Detect all EMA crossovers in the data
        4. For each crossover:
           a. Find next crossover (defines trade window)
           b. Calculate metrics (optimal entry, MFE, MAE)
           c. Build analytics record
        5. Insert records to analytics database
    """
    
    print(f"\n{'=' * 70}")
    print(f"Processing {symbol}")
    print(f"{'=' * 70}")
    
    # ── STEP 1: DETERMINE DATE RANGE ──────────────────────────────────────────
    
    if is_initial_run:
        # Initial backfill: fetch ~250 days
        days_to_fetch = HISTORICAL_DAYS
        print(f"Mode: Initial backfill ({days_to_fetch} days)")
    
    else:
        # Incremental update: check last processed crossover
        last_utc = get_last_crossover_utc(symbol)
        
        if last_utc:
            # We have existing data - fetch from last crossover forward
            days_since = (datetime.now(timezone.utc) - last_utc).days
            days_to_fetch = HISTORICAL_DAYS#max(INCREMENTAL_LOOKBACK_DAYS, days_since + 1)
            print(f"Mode: Incremental update (last crossover: {last_utc.date()}, fetching {days_to_fetch} days)")
        
        else:
            # No existing data - do full backfill
            days_to_fetch = HISTORICAL_DAYS
            print(f"Mode: Full backfill ({days_to_fetch} days) - no existing data")
    
    # ── STEP 2: FETCH CANDLE DATA ─────────────────────────────────────────────
    
    df = fetch_historical_klines(symbol, INTERVAL, days_to_fetch)
    
    if df.empty:
        print(f"  ❌ Failed to fetch data for {symbol}")
        return 0
    
    print(f"  ✓ Fetched {len(df)} candles")
    print(f"  ✓ Date range: {df['timestamp'].min().date()} to {df['timestamp'].max().date()}")
    
    # ── STEP 3: DETECT CROSSOVERS ─────────────────────────────────────────────
    
    crossovers = detect_crossovers(df)
    
    if not crossovers:
        print(f"  ℹ️  No crossovers detected in {symbol}")
        return 0
    
    print(f"  ✓ Detected {len(crossovers)} crossovers")
    
    # ── STEP 4: CALCULATE METRICS FOR EACH CROSSOVER ──────────────────────────
    
    analytics_records = []
    
    for i, xo in enumerate(crossovers):
        # Get next crossover (defines end of trade window)
        next_xo = get_next_crossover(df, i, crossovers)
        
        if not next_xo:
            # This is the last crossover - trade still open
            # Skip it (we need a closed window for metrics)
            continue
        
        # Extract window indices
        start_idx = xo["index"]
        end_idx = next_xo["index"]
        
        # Calculate trade metrics
        metrics = calculate_trade_metrics(
            df=df,
            signal_type=xo["signal"],
            entry_price=xo["price"],
            start_idx=start_idx,
            end_idx=end_idx
        )
        
        if not metrics:
            # Window too short or invalid
            continue
        
        # Calculate actual PnL (entry to exit)
        pnl = calculate_pnl_percent(
            signal_type=xo["signal"],
            entry_price=xo["price"],
            exit_price=metrics["exit_price"]
        )
        
        # Build analytics record
        record = {
            "crossover_utc": xo["timestamp"].isoformat(),
            "symbol": symbol,
            "signal": xo["signal"],
            "entry_price": xo["price"],
            "optimal_entry": metrics["optimal_entry"],
            "optimal_entry_utc": metrics["optimal_entry_utc"],  # FIX: was missing
            "mfe_percent": metrics["mfe_percent"],
            "mae_percent": metrics["mae_percent"],
            "trade_duration": metrics["trade_duration"],
            "next_crossover_utc": next_xo["timestamp"].isoformat(),
            "exit_price": metrics["exit_price"],
            "pnl_percent": round(pnl, 2)
        }
        
        analytics_records.append(record)
    
    # ── STEP 5: INSERT TO DATABASE ────────────────────────────────────────────
    
    if not analytics_records:
        print(f"  ℹ️  No complete trade windows for {symbol}")
        return 0
    
    print(f"  ✓ Calculated metrics for {len(analytics_records)} trade windows")
    
    # Use bulk insert for efficiency
    inserted_count = bulk_insert_analytics(analytics_records)
    
    print(f"  ✓ Inserted {inserted_count} new records to analytics database")
    
    return inserted_count


# ══════════════════════════════════════════════════════════════════════════════
#                              MAIN PIPELINE RUNNER
# ══════════════════════════════════════════════════════════════════════════════

def run_analytics_pipeline(initial_backfill: bool = False):
    """
    Main entry point for the analytics pipeline.
    
    Args:
        initial_backfill: If True, processes all coins with full historical data.
                         If False, does incremental updates only.
    
    Workflow:
        1. Load state (track progress)
        2. For each coin:
           a. Process symbol (fetch, detect, calculate, insert)
           b. Update state
           c. Track API calls
        3. Print summary statistics
    """
    
    start_time = datetime.now(timezone.utc)
    
    print("\n" + "=" * 70)
    print("EMA CROSSOVER ANALYTICS PIPELINE")
    print("=" * 70)
    print(f"Started: {start_time.isoformat()}")
    print(f"Mode: {'INITIAL BACKFILL' if initial_backfill else 'INCREMENTAL UPDATE'}")
    print(f"Coins: {len(COINS)}")
    print(f"Interval: {INTERVAL}")
    print("=" * 70)
    
    state = load_analytics_state()
    total_inserted = 0
    
    for symbol in COINS:
        try:
            # Process this symbol
            inserted = process_symbol(symbol, is_initial_run=initial_backfill)
            total_inserted += inserted
            
            # Update state
            state[symbol] = {
                "last_processed": datetime.now(timezone.utc).isoformat(),
                "records_inserted": inserted
            }
            save_analytics_state(state)
        
        except Exception as e:
            log_analytics_error(f"Failed to process {symbol}: {repr(e)}")
            print(f"  ❌ Error processing {symbol} (see analytics_error.log)")
    
    # ── FINAL SUMMARY ─────────────────────────────────────────────────────────
    
    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()
    
    print("\n" + "=" * 70)
    print("PIPELINE COMPLETE")
    print("=" * 70)
    print(f"Duration: {duration:.1f} seconds")
    print(f"Coins processed: {len(COINS)}")
    print(f"New records inserted: {total_inserted}")
    print(f"API calls made: {get_analytics_api_calls()}")
    
    # Database statistics
    total_records = count_analytics_records()
    print(f"Total records in database: {total_records}")
    
    for symbol in COINS:
        symbol_records = count_analytics_records(symbol)
        print(f"  {symbol}: {symbol_records} records")
    
    print("=" * 70)


# ══════════════════════════════════════════════════════════════════════════════
#                              COMMAND LINE INTERFACE
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    
    # Usage: python analytics_pipeline.py [--initial]
    
    if "--initial" in sys.argv or "--backfill" in sys.argv:
        print("\n🔵 Running INITIAL BACKFILL mode (250 days)")
        run_analytics_pipeline(initial_backfill=True)
    
    else:
        print("\n🟢 Running INCREMENTAL UPDATE mode")
        run_analytics_pipeline(initial_backfill=False)
