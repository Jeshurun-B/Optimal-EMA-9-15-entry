# merge_datasets.py
# ═════════════════════════════════════════════════════════════════════════════
# PURPOSE: Example script showing how to merge main dataset with analytics
#          dataset for ML training.
#
# USAGE:
#   python merge_datasets.py
#
# OUTPUT:
#   combined_dataset.csv - Ready for ML model training
# ═════════════════════════════════════════════════════════════════════════════

import pandas as pd
from supabase import create_client
from analytics_config import ANALYTICS_SUPABASE_URL, ANALYTICS_SUPABASE_KEY
import os


def fetch_main_dataset():
    """
    Fetch signal features from main Supabase project.
    
    Returns:
        DataFrame with columns:
            - checked_at_utc (merge key)
            - symbol (merge key)
            - signal, price, adx_ltf, ema_fast_ltf, ... (35 features)
    """
    
    # Get credentials from environment
    main_url = os.getenv("SUPABASE_URL")
    main_key = os.getenv("SUPABASE_KEY")
    
    if not main_url or not main_key:
        print("❌ Main dataset credentials not found in environment")
        print("   Set SUPABASE_URL and SUPABASE_KEY")
        return None
    
    print("Fetching main dataset (signal features)...")
    
    try:
        client = create_client(main_url, main_key)
        response = client.table("signals").select("*").execute()
        
        df = pd.DataFrame(response.data)
        print(f"✅ Fetched {len(df)} signals from main dataset")
        
        return df
    
    except Exception as e:
        print(f"❌ Failed to fetch main dataset: {e}")
        return None


def fetch_analytics_dataset():
    """
    Fetch trade analytics from analytics Supabase project.
    
    Returns:
        DataFrame with columns:
            - crossover_utc (merge key)
            - symbol (merge key)
            - optimal_entry, mfe_percent, mae_percent, trade_duration, pnl_percent
    """
    
    print("Fetching analytics dataset (trade metrics)...")
    
    try:
        client = create_client(ANALYTICS_SUPABASE_URL, ANALYTICS_SUPABASE_KEY)
        response = client.table("crossover_analytics").select("*").execute()
        
        df = pd.DataFrame(response.data)
        print(f"✅ Fetched {len(df)} crossovers from analytics dataset")
        
        return df
    
    except Exception as e:
        print(f"❌ Failed to fetch analytics dataset: {e}")
        return None


def merge_datasets(df_main, df_analytics):
    """
    Merge main dataset with analytics dataset on UTC timestamp + symbol.
    
    Args:
        df_main: Main dataset (signal features)
        df_analytics: Analytics dataset (trade metrics)
    
    Returns:
        Combined DataFrame with both features and metrics
    
    Merge Strategy:
        INNER JOIN - Keep only records that exist in BOTH datasets
        
        Why?
            - Main dataset: Has signals that are still "pending" (not labeled yet)
            - Analytics: Only has CLOSED trades (crossover to next crossover)
            - For ML training, we only want COMPLETE data
    """
    
    print("\nMerging datasets...")
    
    # Convert UTC columns to datetime for reliable matching
    df_main["checked_at_utc"] = pd.to_datetime(df_main["checked_at_utc"], utc=True)
    df_analytics["crossover_utc"] = pd.to_datetime(df_analytics["crossover_utc"], utc=True)
    
    # Merge on UTC + symbol
    df_combined = df_main.merge(
        df_analytics,
        left_on=["checked_at_utc", "symbol"],
        right_on=["crossover_utc", "symbol"],
        how="inner",  # Only keep matches
        suffixes=("_main", "_analytics")
    )
    
    print(f"✅ Merged dataset: {len(df_combined)} complete records")
    print(f"   (Dropped {len(df_main) - len(df_combined)} pending signals from main dataset)")
    print(f"   (Dropped {len(df_analytics) - len(df_combined)} orphan analytics records)")
    
    return df_combined


def clean_and_select_features(df):
    """
    Clean the merged dataset and select relevant columns for ML.
    
    Args:
        df: Merged DataFrame
    
    Returns:
        Cleaned DataFrame ready for ML model training
    """
    
    print("\nCleaning and selecting features...")
    
    # Drop duplicate columns created during merge
    df = df.drop(columns=[col for col in df.columns if col.endswith("_analytics")], errors="ignore")
    
    # Rename to clean names
    df = df.rename(columns={
        "checked_at_utc": "utc",
        "signal_main": "signal"
    })
    
    # Keep UTC as the primary timestamp
    if "crossover_utc" in df.columns:
        df = df.drop(columns=["crossover_utc"])
    
    # Select feature columns (adjust based on your main dataset schema)
    feature_cols = [
        "utc", "symbol", "signal",
        # Technical indicators from main dataset
        "price", "adx_ltf", "adx_4h", "adx_1d",
        "ema_fast_ltf", "ema_slow_ltf",
        "rsi_ltf", "rsi_4h", "rsi_1d",
        "bb_width_ltf", "bb_position_ltf",
        "volume_ratio", "volume_spike",
        # HTF alignment
        "htf_4h_aligned", "htf_1d_aligned",
        # Market context
        "fear_greed_index", "btc_4h_bullish",
        # Trade analytics
        "optimal_entry", "mfe_percent", "mae_percent",
        "trade_duration", "pnl_percent"
    ]
    
    # Keep only columns that exist
    available_cols = [col for col in feature_cols if col in df.columns]
    df = df[available_cols]
    
    print(f"✅ Selected {len(available_cols)} feature columns")
    
    return df


def save_combined_dataset(df, filename="combined_dataset.csv"):
    """
    Save the combined dataset to CSV.
    
    Args:
        df: Combined DataFrame
        filename: Output filename
    """
    
    print(f"\nSaving to {filename}...")
    
    df.to_csv(filename, index=False)
    
    print(f"✅ Saved {len(df)} records to {filename}")
    print(f"   File size: {os.path.getsize(filename) / 1024 / 1024:.2f} MB")


def print_dataset_summary(df):
    """Print summary statistics of the combined dataset."""
    
    print("\n" + "=" * 70)
    print("DATASET SUMMARY")
    print("=" * 70)
    
    print(f"\nTotal records: {len(df):,}")
    
    # Signals breakdown
    if "signal" in df.columns:
        print("\nSignal distribution:")
        print(df["signal"].value_counts())
    
    # Symbols breakdown
    if "symbol" in df.columns:
        print("\nRecords per symbol:")
        print(df["symbol"].value_counts().sort_values(ascending=False))
    
    # Date range
    if "utc" in df.columns:
        df["utc"] = pd.to_datetime(df["utc"], utc=True)
        print(f"\nDate range:")
        print(f"  Earliest: {df['utc'].min()}")
        print(f"  Latest:   {df['utc'].max()}")
        print(f"  Span:     {(df['utc'].max() - df['utc'].min()).days} days")
    
    # Trade metrics summary
    if "mfe_percent" in df.columns:
        print("\nTrade metrics:")
        print(f"  Avg MFE: {df['mfe_percent'].mean():.2f}%")
        print(f"  Avg MAE: {df['mae_percent'].mean():.2f}%")
        print(f"  Avg PnL: {df['pnl_percent'].mean():.2f}%")
        print(f"  Avg Duration: {df['trade_duration'].mean():.0f} candles")
    
    # Win rate
    if "pnl_percent" in df.columns:
        wins = (df["pnl_percent"] > 0).sum()
        total = len(df)
        win_rate = (wins / total) * 100
        print(f"\nWin rate: {win_rate:.1f}% ({wins:,}/{total:,})")
    
    print("=" * 70)


def main():
    """Main execution flow."""
    
    print("\n" + "=" * 70)
    print("DATASET MERGE FOR ML TRAINING")
    print("=" * 70)
    
    # Step 1: Fetch main dataset
    df_main = fetch_main_dataset()
    if df_main is None or df_main.empty:
        print("❌ Cannot proceed without main dataset")
        return
    
    # Step 2: Fetch analytics dataset
    df_analytics = fetch_analytics_dataset()
    if df_analytics is None or df_analytics.empty:
        print("❌ Cannot proceed without analytics dataset")
        return
    
    # Step 3: Merge datasets
    df_combined = merge_datasets(df_main, df_analytics)
    if df_combined.empty:
        print("❌ Merge resulted in empty dataset")
        print("   This means no matching UTC timestamps between datasets")
        print("   Check that both pipelines are processing the same coins")
        return
    
    # Step 4: Clean and select features
    df_final = clean_and_select_features(df_combined)
    
    # Step 5: Save to CSV
    save_combined_dataset(df_final)
    
    # Step 6: Print summary
    print_dataset_summary(df_final)
    
    print("\n✅ Dataset merge complete!")
    print("\n💡 NEXT STEPS:")
    print("   1. Load combined_dataset.csv in your ML notebook")
    print("   2. Split into train/test sets")
    print("   3. Train your model using the 35 features")
    print("   4. Predict MFE, MAE, or optimal entry")
    print("\nExample:")
    print("   import pandas as pd")
    print("   df = pd.read_csv('combined_dataset.csv')")
    print("   X = df.drop(columns=['utc', 'symbol', 'signal', 'mfe_percent', 'mae_percent', 'pnl_percent'])")
    print("   y = df['mfe_percent']  # or 'mae_percent', 'pnl_percent'")
    print("   # Now train your model...")


if __name__ == "__main__":
    main()
