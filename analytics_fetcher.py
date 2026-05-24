# analytics_fetcher.py
# ═════════════════════════════════════════════════════════════════════════════
# PURPOSE: Fetch historical market data from Binance for analytics pipeline.
#          Handles pagination for multi-month lookbacks.
#
# PHILOSOPHY:
#   - Reuses patterns from main fetcher.py
#   - Supports both initial backfill (250 days) and incremental updates
#   - Never raises exceptions (returns empty DataFrame on error)
# ═════════════════════════════════════════════════════════════════════════════

import time
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
from analytics_config import BINANCE_BASE_URL, REQUEST_TIMEOUT, ANALYTICS_LOG_FILE


# ══════════════════════════════════════════════════════════════════════════════
#                              API CALL TRACKING
# ══════════════════════════════════════════════════════════════════════════════

# Global counter for this analytics pipeline run
ANALYTICS_API_CALLS = 0


def _inc_analytics_api_call() -> int:
    """Increment analytics API call counter."""
    global ANALYTICS_API_CALLS
    ANALYTICS_API_CALLS += 1
    return ANALYTICS_API_CALLS


def get_analytics_api_calls() -> int:
    """Get current API call count for this run."""
    return ANALYTICS_API_CALLS


# ══════════════════════════════════════════════════════════════════════════════
#                              ERROR LOGGING
# ══════════════════════════════════════════════════════════════════════════════

def log_analytics_error(msg: str) -> None:
    """Log error to analytics error file and console."""
    timestamp = datetime.now(timezone.utc).isoformat()
    log_line = f"[{timestamp}] {msg}\n"
    
    print(f"[ANALYTICS ERROR] {msg}")
    
    try:
        with open(ANALYTICS_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#                              FETCH HISTORICAL KLINES (PAGINATED)
# ══════════════════════════════════════════════════════════════════════════════

def fetch_historical_klines(
    symbol: str,
    interval: str,
    days_back: int
) -> pd.DataFrame:
    """
    Fetch months of historical candles by paginating backwards from today.
    
    WHY PAGINATION:
        Binance limits each request to 1000 candles max.
        To get 250 days of 15m data = 24,000 candles.
        We need multiple requests, fetching 1000 at a time.
    
    HOW IT WORKS:
        1. Calculate target start time (now - days_back)
        2. Fetch 1000 candles ending at 'now'
        3. Find oldest candle in batch
        4. Next request: fetch 1000 candles ending just before oldest
        5. Repeat until oldest candle <= target start
        6. Combine all batches, sort chronologically
    
    Args:
        symbol:     Trading pair (e.g., "BTCUSDT")
        interval:   Timeframe (e.g., "15m")
        days_back:  How many days of history to fetch
    
    Returns:
        DataFrame sorted oldest-first with columns:
            [timestamp, open, high, low, close, volume]
        
        Empty DataFrame on failure (never raises exception)
    
    Example:
        # Fetch 250 days of BTC 15-minute data
        df = fetch_historical_klines("BTCUSDT", "15m", 250)
        
        if not df.empty:
            print(f"Fetched {len(df)} candles")
            print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
        else:
            print("Failed to fetch data")
    """
    
    # Calculate target start timestamp
    start_time_ms = int(
        (datetime.now(timezone.utc) - timedelta(days=days_back)).timestamp() * 1000
    )
    
    all_dfs = []
    end_time_ms = None
    
    print(f"  Fetching {interval} history for {symbol} ({days_back} days)...")
    
    # Pagination loop
    while True:
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": 1000  # Binance max per request
        }
        
        # For pagination: set endTime to get candles BEFORE the previous batch
        if end_time_ms:
            params["endTime"] = end_time_ms
        
        try:
            _inc_analytics_api_call()
            
            resp = requests.get(
                f"{BINANCE_BASE_URL}/api/v3/klines",
                params=params,
                timeout=REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            raw = resp.json()
            
            # Empty response = no more historical data available
            if not raw:
                break
            
            # Parse batch
            df = pd.DataFrame(raw, columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_asset_volume", "num_trades",
                "taker_base_vol", "taker_quote_vol", "ignore"
            ])
            
            # Convert timestamp
            df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
            
            # Convert OHLCV to numeric
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            
            # Keep only needed columns
            df = df[["timestamp", "open", "high", "low", "close", "volume"]]
            
            all_dfs.append(df)
            
            # Check if we've reached target start time
            oldest_time_ms = int(df["timestamp"].min().timestamp() * 1000)
            
            if oldest_time_ms <= start_time_ms:
                print(f"    Reached target date - fetched {len(all_dfs)} batches")
                break
            
            # Set endTime for next iteration (1ms before oldest candle)
            end_time_ms = oldest_time_ms - 1
            
            # Rate limiting: brief pause between requests
            time.sleep(0.1)
        
        except Exception as e:
            log_analytics_error(f"fetch_historical_klines error for {symbol}: {repr(e)}")
            break
    
    # Combine all batches
    if not all_dfs:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    
    combined = pd.concat(all_dfs, ignore_index=True)
    combined = combined.sort_values("timestamp").reset_index(drop=True)
    
    # Filter to exact date range requested
    cutoff_time = datetime.now(timezone.utc) - timedelta(days=days_back)
    combined = combined[combined["timestamp"] >= cutoff_time].reset_index(drop=True)
    
    print(f"    ✓ Got {len(combined)} candles from {combined['timestamp'].min().date()} to {combined['timestamp'].max().date()}")
    
    return combined


# ══════════════════════════════════════════════════════════════════════════════
#                              FETCH FROM SPECIFIC TIMESTAMP
# ══════════════════════════════════════════════════════════════════════════════

def fetch_from_timestamp(
    symbol: str,
    interval: str,
    start_time: datetime,
    limit: int = 1000
) -> pd.DataFrame:
    """
    Fetch candles starting from a specific timestamp going FORWARD in time.
    Used for incremental updates.
    
    Args:
        symbol:     Trading pair (e.g., "BTCUSDT")
        interval:   Timeframe (e.g., "15m")
        start_time: Start fetching from this UTC datetime
        limit:      Max candles to fetch (default 1000)
    
    Returns:
        DataFrame with columns: [timestamp, open, high, low, close, volume]
        Empty DataFrame on failure
    
    Example:
        # Last processed crossover was 2026-05-01 10:00
        last_time = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
        
        # Fetch all candles since then
        df = fetch_from_timestamp("BTCUSDT", "15m", last_time)
        
        if not df.empty:
            print(f"Got {len(df)} new candles since {last_time}")
    """
    
    start_time_ms = int(start_time.timestamp() * 1000)
    
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_time_ms,
        "limit": limit
    }
    
    try:
        _inc_analytics_api_call()
        
        resp = requests.get(
            f"{BINANCE_BASE_URL}/api/v3/klines",
            params=params,
            timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        raw = resp.json()
        
        if not raw:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        
        df = pd.DataFrame(raw, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "num_trades",
            "taker_base_vol", "taker_quote_vol", "ignore"
        ])
        
        df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        
        return df[["timestamp", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
    
    except Exception as e:
        log_analytics_error(f"fetch_from_timestamp error for {symbol}: {repr(e)}")
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
