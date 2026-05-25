# analytics_metrics.py
# ═════════════════════════════════════════════════════════════════════════════
# PURPOSE: Calculate trade metrics between crossover intervals.
#          Computes optimal entry, MFE (Maximum Favorable Excursion),
#          and MAE (Maximum Adverse Excursion).
#
# PHILOSOPHY:
#   - Pure calculation logic (no external dependencies)
#   - Handles both LONG and SHORT signals
#   - Returns None if interval is too small or invalid
# ═════════════════════════════════════════════════════════════════════════════

import pandas as pd
from analytics_config import MIN_TRADE_CANDLES


def calculate_trade_metrics(
    df: pd.DataFrame,
    signal_type: str,
    entry_price: float,
    start_idx: int,
    end_idx: int
) -> dict:
    """
    Calculate comprehensive trade metrics for a crossover interval.
    
    METRICS CALCULATED:
        1. Optimal Entry: Best possible entry price BEFORE MFE peak
        2. MFE (Maximum Favorable Excursion): Peak profit potential
        3. MAE (Maximum Adverse Excursion): Worst drawdown before MFE
        4. Trade Duration: Number of candles in window
    
    CRITICAL TEMPORAL CONSTRAINT:
        Optimal Entry MUST occur chronologically BEFORE the MFE peak.
        If the best price occurs AFTER the peak, it's invalid (too late).
        
        Example (LONG):
            Window: [100, 95, 110, 90]
            MFE peak: 110 (index 2)
            Optimal entry: 95 (index 1) ✅ VALID - occurs before peak
            Invalid: 90 (index 3) ❌ INVALID - occurs after peak
        
        This ensures the optimal entry represents a realistic opportunity
        that existed BEFORE maximum profit was achieved.
    
    Args:
        df: DataFrame with [timestamp, open, high, low, close, volume]
        signal_type: "LONG" or "SHORT"
        entry_price: Price at crossover (actual entry)
        start_idx: Starting index in df (crossover candle)
        end_idx: Ending index in df (next crossover candle)
    
    Returns:
        Dictionary with metrics:
            {
                "optimal_entry": Best entry price (before MFE peak),
                "mfe_percent": Max favorable move (%),
                "mae_percent": Max adverse move (%),
                "trade_duration": Number of candles,
                "exit_price": Price at next crossover
            }
        
        Returns None if:
            - Interval too short (< MIN_TRADE_CANDLES)
            - Invalid indices
            - Missing data
    
    Example:
        # LONG signal: entered at $100
        metrics = calculate_trade_metrics(
            df=candles,
            signal_type="LONG",
            entry_price=100.0,
            start_idx=50,  # Crossover at candle 50
            end_idx=150    # Next crossover at candle 150
        )
        
        if metrics:
            print(f"Optimal entry: ${metrics['optimal_entry']:.2f}")
            # Optimal entry is the lowest price BEFORE the highest peak
            print(f"Max profit potential: {metrics['mfe_percent']:.2f}%")
            print(f"Worst drawdown: {metrics['mae_percent']:.2f}%")
    
    LOGIC FOR LONG SIGNALS:
        1. Find MFE: highest high in entire window (peak profit target)
        2. Extract "before peak" window: all candles from start to MFE
        3. Optimal Entry: lowest low in "before peak" window
        4. MAE: also calculated from "before peak" window
        
        Constraint: t(optimal_entry) < t(MFE) ← temporal ordering enforced
    
    LOGIC FOR SHORT SIGNALS:
        1. Find MFE: lowest low in entire window (peak profit target)
        2. Extract "before bottom" window: all candles from start to MFE
        3. Optimal Entry: highest high in "before bottom" window
        4. MAE: also calculated from "before bottom" window
        
        Constraint: t(optimal_entry) < t(MFE) ← temporal ordering enforced
    """
    
    # Validate inputs
    if start_idx >= end_idx:
        return None
    
    trade_duration = end_idx - start_idx
    
    if trade_duration < MIN_TRADE_CANDLES:
        return None  # Too short, likely whipsaw
    
    if start_idx < 0 or end_idx > len(df):
        return None  # Invalid indices
    
    # Extract trade window
    window = df.iloc[start_idx:end_idx].copy()
    
    if window.empty:
        return None
    
    # Exit price (close at next crossover)
    exit_price = float(df.iloc[end_idx - 1]["close"])
    
    # ══════════════════════════════════════════════════════════════════════════
    #                              LONG SIGNAL METRICS
    # ══════════════════════════════════════════════════════════════════════════
    
    if signal_type == "LONG":
        # MFE: highest high in window (peak profit potential)
        # THIS MUST BE FOUND FIRST - optimal entry depends on it
        peak_price = float(window["high"].max())
        peak_idx_in_window = window["high"].idxmax()
        mfe_percent = ((peak_price - entry_price) / entry_price) * 100
        
        # Optimal entry: lowest low BEFORE the MFE peak
        # CRITICAL CONSTRAINT: Optimal entry must occur chronologically BEFORE MFE
        # If lowest price occurs AFTER the peak, it's invalid (too late to enter)
        before_peak = window.loc[:peak_idx_in_window]
        
        if not before_peak.empty:
            optimal_entry_idx = before_peak["low"].idxmin()
            optimal_entry = float(before_peak.loc[optimal_entry_idx, "low"])
            optimal_entry_utc = df.loc[optimal_entry_idx, "timestamp"].isoformat()
        else:
            # Edge case: peak is at first candle, no "before" window
            optimal_entry = float(window.iloc[0]["low"])
            optimal_entry_utc = df.iloc[start_idx]["timestamp"].isoformat()
        
        # MAE: worst drawdown before reaching peak
        # This is the same window as optimal entry (before peak)
        if not before_peak.empty:
            worst_price = float(before_peak["low"].min())
            mae_percent = ((worst_price - entry_price) / entry_price) * 100
        else:
            mae_percent = 0.0  # No drawdown if peak at start
        
        return {
            "optimal_entry": round(optimal_entry, 8),
            "optimal_entry_utc": optimal_entry_utc,
            "mfe_percent": round(mfe_percent, 2),
            "mae_percent": round(mae_percent, 2),
            "trade_duration": trade_duration,
            "exit_price": round(exit_price, 8)
        }
    
    # ══════════════════════════════════════════════════════════════════════════
    #                              SHORT SIGNAL METRICS
    # ══════════════════════════════════════════════════════════════════════════
    
    elif signal_type == "SHORT":
        # MFE: lowest low in window (peak profit potential for short)
        # THIS MUST BE FOUND FIRST - optimal entry depends on it
        bottom_price = float(window["low"].min())
        bottom_idx_in_window = window["low"].idxmin()
        mfe_percent = ((entry_price - bottom_price) / entry_price) * 100
        
        # Optimal entry: highest high BEFORE the MFE bottom
        # CRITICAL CONSTRAINT: Optimal entry must occur chronologically BEFORE MFE
        # If highest price occurs AFTER the bottom, it's invalid (too late to enter)
        before_bottom = window.loc[:bottom_idx_in_window]
        
        if not before_bottom.empty:
            optimal_entry_idx = before_bottom["high"].idxmax()
            optimal_entry = float(before_bottom.loc[optimal_entry_idx, "high"])
            optimal_entry_utc = df.loc[optimal_entry_idx, "timestamp"].isoformat()
        else:
            # Edge case: bottom is at first candle, no "before" window
            optimal_entry = float(window.iloc[0]["high"])
            optimal_entry_utc = df.iloc[start_idx]["timestamp"].isoformat()
        
        # MAE: worst drawdown before reaching peak
        # This is the same window as optimal entry (before bottom)
        if not before_bottom.empty:
            worst_price = float(before_bottom["high"].max())
            mae_percent = ((entry_price - worst_price) / entry_price) * 100
        else:
            mae_percent = 0.0  # No drawdown if bottom at start
        
        return {
            "optimal_entry": round(optimal_entry, 8),
            "optimal_entry_utc": optimal_entry_utc,
            "mfe_percent": round(mfe_percent, 2),
            "mae_percent": round(mae_percent, 2),
            "trade_duration": trade_duration,
            "exit_price": round(exit_price, 8)
        }
    
    else:
        return None  # Invalid signal type


def calculate_pnl_percent(
    signal_type: str,
    entry_price: float,
    exit_price: float
) -> float:
    """
    Calculate profit/loss percentage for a trade.
    
    Args:
        signal_type: "LONG" or "SHORT"
        entry_price: Entry price
        exit_price: Exit price
    
    Returns:
        PnL as percentage (positive = profit, negative = loss)
    
    Example:
        # LONG: bought at 100, sold at 110 = 10% profit
        pnl = calculate_pnl_percent("LONG", 100, 110)
        # Returns: 10.0
        
        # SHORT: sold at 100, bought back at 90 = 10% profit
        pnl = calculate_pnl_percent("SHORT", 100, 90)
        # Returns: 10.0
    """
    
    if signal_type == "LONG":
        return ((exit_price - entry_price) / entry_price) * 100
    
    elif signal_type == "SHORT":
        return ((entry_price - exit_price) / entry_price) * 100
    
    else:
        return 0.0
