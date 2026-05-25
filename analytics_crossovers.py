# analytics_crossovers.py
# ═════════════════════════════════════════════════════════════════════════════
# PURPOSE: Detect EMA crossovers in historical data.
#          Uses same EMA logic as main pipeline for consistency.
#
# PHILOSOPHY:
#   - Pure calculation (no API calls, no DB calls)
#   - Returns list of crossover events with timestamps
#   - Handles edge cases (insufficient data, NaN values)
# ═════════════════════════════════════════════════════════════════════════════

import pandas as pd
from analytics_config import EMA_FAST, EMA_SLOW


def detect_crossovers(df: pd.DataFrame) -> list:
    """
    Detect all EMA crossovers in a DataFrame of candles.
    
    CROSSOVER DEFINITION:
        LONG:  Fast EMA crosses from BELOW to ABOVE slow EMA
        SHORT: Fast EMA crosses from ABOVE to BELOW slow EMA
    
    Args:
        df: DataFrame with columns [timestamp, open, high, low, close, volume]
            Must be sorted chronologically (oldest first)
    
    Returns:
        List of crossover dictionaries, each containing:
            {
                "timestamp": UTC datetime of crossover,
                "signal": "LONG" or "SHORT",
                "price": Close price at crossover,
                "ema_fast": Fast EMA value at crossover,
                "ema_slow": Slow EMA value at crossover
            }
        
        Empty list if no crossovers detected or insufficient data
    
    Example:
        df = fetch_historical_klines("BTCUSDT", "15m", 250)
        crossovers = detect_crossovers(df)
        
        print(f"Found {len(crossovers)} crossovers")
        for xo in crossovers[:5]:
            print(f"{xo['timestamp']}: {xo['signal']} at ${xo['price']:.2f}")
    
    Algorithm:
        1. Calculate fast EMA (9-period) and slow EMA (15-period)
        2. For each candle, check if EMA relationship changed from previous
        3. Record crossover timestamp, direction, and price
        4. Skip NaN values (warmup period)
    """
    
    if df.empty or len(df) < EMA_SLOW:
        return []
    
    # Calculate EMAs
    df = df.copy()
    df.loc[:, "ema_fast"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    df.loc[:, "ema_slow"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()
    
    # Drop NaN rows (warmup period)
    df = df.dropna(subset=["ema_fast", "ema_slow"]).reset_index(drop=True)
    
    if len(df) < 2:
        return []
    
    crossovers = []
    
    # Iterate through candles starting from index 1 (need previous candle)
    for i in range(1, len(df)):
        current = df.iloc[i]
        previous = df.iloc[i - 1]
        
        # Extract values
        ema_fast_curr = current["ema_fast"]
        ema_slow_curr = current["ema_slow"]
        ema_fast_prev = previous["ema_fast"]
        ema_slow_prev = previous["ema_slow"]
        
        # Detect crossovers
        # LONG: fast was below slow, now at or above
        cross_up = (ema_fast_prev < ema_slow_prev) and (ema_fast_curr >= ema_slow_curr)
        
        # SHORT: fast was above slow, now at or below
        cross_down = (ema_fast_prev > ema_slow_prev) and (ema_fast_curr <= ema_slow_curr)
        
        if cross_up or cross_down:
            crossovers.append({
                "timestamp": current["timestamp"],
                "signal": "LONG" if cross_up else "SHORT",
                "price": float(current["close"]),
                "ema_fast": float(ema_fast_curr),
                "ema_slow": float(ema_slow_curr),
                "index": i  # Internal use: position in DataFrame
            })
    
    return crossovers


def get_next_crossover(df: pd.DataFrame, current_idx: int, crossovers: list) -> dict:
    """
    Find the next crossover after a given index in the crossover list.
    
    Args:
        df: DataFrame of candles
        current_idx: Current crossover's index in the crossovers list
        crossovers: List of all detected crossovers
    
    Returns:
        Next crossover dict, or None if this is the last one
    
    Example:
        crossovers = detect_crossovers(df)
        
        for i, xo in enumerate(crossovers):
            next_xo = get_next_crossover(df, i, crossovers)
            
            if next_xo:
                print(f"Crossover at {xo['timestamp']}")
                print(f"Next crossover at {next_xo['timestamp']}")
                print(f"Trade window: {next_xo['timestamp'] - xo['timestamp']}")
            else:
                print(f"Last crossover at {xo['timestamp']} - still open")
    """
    
    if current_idx >= len(crossovers) - 1:
        return None  # This is the last crossover
    
    return crossovers[current_idx + 1]
