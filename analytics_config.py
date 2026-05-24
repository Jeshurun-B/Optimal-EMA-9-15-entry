# analytics_config.py
# ═════════════════════════════════════════════════════════════════════════════
# PURPOSE: Configuration for the EMA Crossover Analytics Dataset Pipeline
#
# This is a SEPARATE analytics system that:
#   - Builds crossover trade analytics (entry, MFE, MAE)
#   - Stores in a DIFFERENT Supabase project
#   - Runs independently from the main signal detection pipeline
#   - Preserves exact UTC alignment for future dataset merging
# ═════════════════════════════════════════════════════════════════════════════

import os

# Load environment variables (same pattern as main config)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ══════════════════════════════════════════════════════════════════════════════
#                              ANALYTICS SUPABASE PROJECT
# ══════════════════════════════════════════════════════════════════════════════
# 
# CRITICAL: This is a DIFFERENT Supabase project than the main pipeline.
# 
# WHY SEPARATE:
#   - Main project: Signal detection features (35+ columns)
#   - Analytics project: Trade outcome metrics (MFE, MAE, optimal entry)
#   - Keeps schemas clean and focused
#   - Later: merge via UTC column during ML preprocessing
# 
# REQUIREMENT:
#   Both projects must use IDENTICAL UTC formats for reliable merging.
# ══════════════════════════════════════════════════════════════════════════════

# Analytics Supabase URL
# Set this to your ANALYTICS project URL
# Example: "https://yyyyyyyyyyyy.supabase.co" (different from main project)
ANALYTICS_SUPABASE_URL = os.getenv("ANALYTICS_SUPABASE_URL")

# Analytics Supabase API Key
# Set this to your ANALYTICS project anon/publishable key
ANALYTICS_SUPABASE_KEY = os.getenv("ANALYTICS_SUPABASE_KEY")

# Analytics table name
ANALYTICS_TABLE = "crossover_analytics"


# ══════════════════════════════════════════════════════════════════════════════
#                              BINANCE API SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

# Reuse Binance base URL from main config
BINANCE_BASE_URL = os.getenv("BINANCE_BASE_URL", "https://data-api.binance.vision")

# HTTP timeout for API requests
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT") or 20)

# API call tracking (prevent rate limits)
API_CALL_LIMIT = int(os.getenv("ANALYTICS_API_CALL_LIMIT") or 500)


# ══════════════════════════════════════════════════════════════════════════════
#                              TIMEFRAME & EMA SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

# Primary timeframe for crossover detection
INTERVAL = "15m"  # Fixed at 15-minute candles

# EMA periods (must match main pipeline for consistency)
EMA_FAST = 9
EMA_SLOW = 15


# ══════════════════════════════════════════════════════════════════════════════
#                              HISTORICAL LOOKBACK
# ══════════════════════════════════════════════════════════════════════════════

# Initial backfill: How many days of history to fetch
# 
# PREFERRED: 250 days (~8 months)
# FALLBACK: 200 days (~6.5 months)
# 
# Why 250 days?
#   - Captures multiple market cycles
#   - Enough data for robust analytics
#   - Binance typically has this much history for major pairs
# 
# Note: If a coin doesn't have 250 days of data (newly listed),
#       the pipeline will fetch whatever is available.
HISTORICAL_DAYS = int(os.getenv("ANALYTICS_HISTORICAL_DAYS") or 250)

# Incremental update: How many days to look back when resuming
# 
# CRITICAL: This should be SMALL (3-7 days)
# 
# Why?
#   - After initial backfill, we only need to process NEW crossovers
#   - Looking back 3 days ensures we catch any missed data
#   - Prevents re-processing months of existing data
# 
# The pipeline automatically detects the last processed UTC and fetches
# from there forward, so this is just a safety buffer.
INCREMENTAL_LOOKBACK_DAYS = int(os.getenv("ANALYTICS_INCREMENTAL_DAYS") or 3)


# ══════════════════════════════════════════════════════════════════════════════
#                              COIN SELECTION
# ══════════════════════════════════════════════════════════════════════════════

# Trading pairs to analyze
# 
# IMPORTANT: Should match the main pipeline's COINS for consistency
# The analytics dataset should cover the same symbols as the main dataset
# so they can be merged later.
COINS = [
    coin.strip().strip('"')
    for coin in os.getenv("ANALYTICS_COINS", "BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT").split(",")
]


# ══════════════════════════════════════════════════════════════════════════════
#                              TRADE WINDOW ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

# Maximum candles to fetch after a crossover when analyzing trade outcomes
# 
# Why 500 candles?
#   500 × 15min = 7,500 minutes = 125 hours = 5.2 days
#   Most crossover trades resolve within 5 days
#   If not resolved by then, we mark as "incomplete"
# 
# This is used when:
#   1. A crossover is detected
#   2. We need to look forward to find the NEXT crossover
#   3. We analyze price action between the two crossovers
LOOKFORWARD_CANDLES = 500

# Minimum candles required between crossovers for valid analysis
# 
# If two crossovers happen within 5 candles (75 minutes):
#   - Too fast, likely noise/whipsaw
#   - Not enough data for meaningful MFE/MAE calculation
#   - Skip this interval
MIN_TRADE_CANDLES = 1


# ══════════════════════════════════════════════════════════════════════════════
#                              ERROR LOGGING
# ══════════════════════════════════════════════════════════════════════════════

# Error log file for analytics pipeline
# Separate from main pipeline's error.log
ANALYTICS_LOG_FILE = os.getenv("ANALYTICS_LOG_FILE") or "analytics_error.log"


# ══════════════════════════════════════════════════════════════════════════════
#                              RESUME STATE TRACKING
# ══════════════════════════════════════════════════════════════════════════════

# File to track which symbols have been processed and when
# Enables incremental updates without re-processing everything
ANALYTICS_STATE_FILE = "analytics_state.json"


# ══════════════════════════════════════════════════════════════════════════════
#                              VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

# Validate required environment variables
if not ANALYTICS_SUPABASE_URL or not ANALYTICS_SUPABASE_KEY:
    raise ValueError(
        "ANALYTICS_SUPABASE_URL and ANALYTICS_SUPABASE_KEY must be set in environment variables.\n"
        "These should point to your SEPARATE analytics Supabase project."
    )
