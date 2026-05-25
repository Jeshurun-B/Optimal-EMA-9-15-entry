# analytics_db.py
# ═════════════════════════════════════════════════════════════════════════════
# PURPOSE: Database operations for the analytics dataset.
#          Talks ONLY to the analytics Supabase project.
#
# PHILOSOPHY:
#   - Separate client from main pipeline's db.py
#   - Never raises exceptions (returns bool/None on errors)
#   - Graceful error handling with logging
# ═════════════════════════════════════════════════════════════════════════════

import pandas as pd
from supabase import create_client, Client
from analytics_config import (
    ANALYTICS_SUPABASE_URL,
    ANALYTICS_SUPABASE_KEY,
    ANALYTICS_TABLE,
    ANALYTICS_LOG_FILE
)
from datetime import datetime, timezone


# ══════════════════════════════════════════════════════════════════════════════
#                              ERROR LOGGING
# ══════════════════════════════════════════════════════════════════════════════

def log_analytics_error(msg: str) -> None:
    """
    Write timestamped error message to analytics log file and console.
    Separate from main pipeline's error logging.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    log_line = f"[{timestamp}] {msg}\n"
    
    # Print to console
    print(f"[ANALYTICS ERROR] {msg}")
    
    # Write to log file
    try:
        with open(ANALYTICS_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception:
        pass  # Silent failure on logging


# ══════════════════════════════════════════════════════════════════════════════
#                              CLIENT SETUP
# ══════════════════════════════════════════════════════════════════════════════

try:
    analytics_client: Client = create_client(
        ANALYTICS_SUPABASE_URL,
        ANALYTICS_SUPABASE_KEY
    )
except Exception as e:
    print(f"Failed to create analytics Supabase client: {e}")
    raise


# ══════════════════════════════════════════════════════════════════════════════
#                              INSERT ANALYTICS RECORD
# ══════════════════════════════════════════════════════════════════════════════

def insert_analytics(record: dict) -> bool:
    """
    Insert one crossover analytics record into the analytics table.
    
    Args:
        record: Dictionary with keys matching table columns:
            - crossover_utc: UTC timestamp of crossover
            - symbol: Trading pair (e.g., "BTCUSDT")
            - signal: "LONG" or "SHORT"
            - entry_price: Price at crossover
            - optimal_entry: Best entry price in trade window
            - mfe_percent: Maximum Favorable Excursion (%)
            - mae_percent: Maximum Adverse Excursion (%)
            - trade_duration: Number of candles in trade window
            - next_crossover_utc: UTC timestamp of next crossover
    
    Returns:
        True if insert succeeded, False otherwise
    
    Note:
        Duplicate records (same symbol + crossover_utc) are silently ignored.
        The table should have a UNIQUE constraint on (symbol, crossover_utc).
    """
    try:
        analytics_client.table(ANALYTICS_TABLE).insert(record).execute()
        return True
    
    except Exception as e:
        error_msg = str(e)
        
        # Duplicates are expected and okay (not a real error)
        if "duplicate" in error_msg.lower() or "unique" in error_msg.lower():
            return False  # Already exists, skip quietly
        
        # Real errors get logged
        log_analytics_error(f"insert_analytics failed for {record.get('symbol')}: {repr(e)}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
#                              GET LAST PROCESSED CROSSOVER
# ══════════════════════════════════════════════════════════════════════════════

def get_last_crossover_utc(symbol: str) -> datetime:
    """
    Query the most recent crossover UTC for this symbol.
    Used to implement incremental updates.
    
    Args:
        symbol: Trading pair (e.g., "BTCUSDT")
    
    Returns:
        datetime: Most recent crossover UTC for this symbol
        OR None if no data exists for this symbol
    
    Example:
        last_utc = get_last_crossover_utc("BTCUSDT")
        if last_utc:
            print(f"Resume from {last_utc}")
            # Fetch only new data after this timestamp
        else:
            print("No existing data - do full backfill")
    """
    try:
        response = (
            analytics_client.table(ANALYTICS_TABLE)
            .select("crossover_utc")
            .eq("symbol", symbol)
            .order("crossover_utc", desc=True)
            .limit(1)
            .execute()
        )
        
        if response.data:
            last_utc_str = response.data[0]["crossover_utc"]
            return pd.to_datetime(last_utc_str, utc=True).to_pydatetime()
        
        return None
    
    except Exception as e:
        log_analytics_error(f"get_last_crossover_utc error for {symbol}: {repr(e)}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
#                              COUNT RECORDS
# ══════════════════════════════════════════════════════════════════════════════

def count_analytics_records(symbol: str = None) -> int:
    """
    Count total analytics records in database.
    
    Args:
        symbol: Optional - count records for specific symbol only
    
    Returns:
        Number of records, or 0 on error
    """
    try:
        query = analytics_client.table(ANALYTICS_TABLE).select("*", count="exact")
        
        if symbol:
            query = query.eq("symbol", symbol)
        
        response = query.execute()
        return response.count if response.count else 0
    
    except Exception as e:
        log_analytics_error(f"count_analytics_records error: {repr(e)}")
        return 0


# ══════════════════════════════════════════════════════════════════════════════
#                              BULK INSERT (OPTIMIZATION)
# ══════════════════════════════════════════════════════════════════════════════

def bulk_insert_analytics(records: list) -> int:
    """
    Insert multiple analytics records in a single database transaction.
    More efficient than individual inserts for large batches.
    
    Args:
        records: List of record dictionaries
    
    Returns:
        Number of records successfully inserted
    
    Note:
        If any record fails (e.g., duplicate), the entire batch is rolled back.
        For this reason, we fall back to individual inserts on batch failure.
    """
    if not records:
        return 0

    # ── PRE-FLIGHT: drop any record that has a None in a required column ──────
    # A single None in a NOT NULL column aborts the entire batch transaction.
    # Required columns that must never be None:
    REQUIRED_COLS = [
        "crossover_utc", "symbol", "signal", "entry_price",
        "optimal_entry", "optimal_entry_utc",
        "mfe_percent", "mae_percent", "trade_duration",
        "next_crossover_utc", "exit_price", "pnl_percent",
    ]
    clean_records = []
    skipped = 0
    for rec in records:
        if any(rec.get(col) is None for col in REQUIRED_COLS):
            missing = [c for c in REQUIRED_COLS if rec.get(c) is None]
            log_analytics_error(
                f"bulk_insert_analytics: skipping incomplete record "
                f"symbol={rec.get('symbol')} crossover_utc={rec.get('crossover_utc')} "
                f"missing={missing}"
            )
            skipped += 1
        else:
            clean_records.append(rec)

    if skipped:
        print(f"  ⚠️  Skipped {skipped} incomplete record(s) before insert (see error log)")

    if not clean_records:
        return 0

    try:
        # Try batch insert first (fastest)
        analytics_client.table(ANALYTICS_TABLE).insert(clean_records).execute()
        return len(clean_records)

    except Exception as e:
        log_analytics_error(f"bulk_insert_analytics failed: {repr(e)}")

        # Fall back to individual inserts
        # This handles mixed cases (some duplicates, some new)
        success_count = 0
        for record in clean_records:
            if insert_analytics(record):
                success_count += 1

        return success_count
