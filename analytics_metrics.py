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
        1. Optimal Entry: Best possible entry price in the window
        2. MFE (Maximum Favorable Excursion): Peak profit potential
        3. MAE (Maximum Adverse Excursion): Worst drawdown
        4. Trade Duration: Number of candles in window
    
    Args:
        df: DataFrame with [timestamp, open, high, low, close, volume]
        signal_type: "LONG" or "SHORT"
        entry_price: Price at crossover (actual entry)
        start_idx: Starting index in df (crossover candle)
        end_idx: Ending index in df (next crossover candle)
    
    Returns:
        Dictionary with metrics:
            {
                "optimal_entry": Best entry price,
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
        # LONG signal: entered at $100, looking for best entry and max profit/loss
        metrics = calculate_trade_metrics(
            df=candles,
            signal_type="LONG",
            entry_price=100.0,
            start_idx=50,  # Crossover at candle 50
            end_idx=150    # Next crossover at candle 150
        )
        
        if metrics:
            print(f"Optimal entry: ${metrics['optimal_entry']:.2f}")
            print(f"Max profit potential: {metrics['mfe_percent']:.2f}%")
            print(f"Worst drawdown: {metrics['mae_percent']:.2f}%")
            print(f"Trade lasted {metrics['trade_duration']} candles")
    
    LOGIC FOR LONG SIGNALS:
        - Optimal Entry: Lowest low in the window (best buy price)
        - MFE: Highest high in the window (peak profit)
        - MAE: Lowest low before reaching MFE (worst drawdown)
    
    LOGIC FOR SHORT SIGNALS:
        - Optimal Entry: Highest high in the window (best sell price)
        - MFE: Lowest low in the window (peak profit)
        - MAE: Highest high before reaching MFE (worst drawdown)
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
        # Optimal entry: lowest low in window (best buy price)
        optimal_entry = float(window["low"].min())
        
        # MFE: highest high in window (peak profit potential)
        peak_price = float(window["high"].max())
        mfe_percent = ((peak_price - entry_price) / entry_price) * 100
        
        # MAE: worst drawdown before reaching peak
        # Find index of peak
        peak_idx_in_window = window["high"].idxmax()
        
        # Get candles before peak
        before_peak = window.loc[:peak_idx_in_window]
        
        if not before_peak.empty:
            # Worst price before peak = lowest low
            worst_price = float(before_peak["low"].min())
            mae_percent = ((worst_price - entry_price) / entry_price) * 100
        else:
            mae_percent = 0.0  # No drawdown
        
        return {
            "optimal_entry": round(optimal_entry, 8),
            "mfe_percent": round(mfe_percent, 2),
            "mae_percent": round(mae_percent, 2),
            "trade_duration": trade_duration,
            "exit_price": round(exit_price, 8)
        }
    
    # ══════════════════════════════════════════════════════════════════════════
    #                              SHORT SIGNAL METRICS
    # ══════════════════════════════════════════════════════════════════════════
    
    elif signal_type == "SHORT":
        # Optimal entry: highest high in window (best sell price)
        optimal_entry = float(window["high"].max())
        
        # MFE: lowest low in window (peak profit potential)
        bottom_price = float(window["low"].min())
        mfe_percent = ((entry_price - bottom_price) / entry_price) * 100
        
        # MAE: worst drawdown before reaching peak
        # Find index of bottom
        bottom_idx_in_window = window["low"].idxmin()
        
        # Get candles before bottom
        before_bottom = window.loc[:bottom_idx_in_window]
        
        if not before_bottom.empty:
            # Worst price before bottom = highest high
            worst_price = float(before_bottom["high"].max())
            mae_percent = ((entry_price - worst_price) / entry_price) * 100
        else:
            mae_percent = 0.0  # No drawdown
        
        return {
            "optimal_entry": round(optimal_entry, 8),
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
