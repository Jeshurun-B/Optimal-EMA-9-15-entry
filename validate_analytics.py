# validate_analytics.py
# ═════════════════════════════════════════════════════════════════════════════
# PURPOSE: Validate analytics pipeline setup and data quality.
#          Run this after initial backfill to verify everything works.
#
# USAGE:
#   python validate_analytics.py
# ═════════════════════════════════════════════════════════════════════════════

import sys
from datetime import datetime, timezone, timedelta
from analytics_config import (
    ANALYTICS_SUPABASE_URL,
    ANALYTICS_SUPABASE_KEY,
    COINS,
    HISTORICAL_DAYS
)
from analytics_db import analytics_client, ANALYTICS_TABLE, count_analytics_records


def print_header(text):
    """Print formatted section header."""
    print("\n" + "=" * 70)
    print(text)
    print("=" * 70)


def check_environment():
    """Verify environment variables are set."""
    print_header("ENVIRONMENT VALIDATION")
    
    issues = []
    
    # Check Supabase URL
    if not ANALYTICS_SUPABASE_URL:
        issues.append("❌ ANALYTICS_SUPABASE_URL is not set")
    elif not ANALYTICS_SUPABASE_URL.startswith("https://"):
        issues.append("❌ ANALYTICS_SUPABASE_URL should start with https://")
    else:
        print(f"✅ ANALYTICS_SUPABASE_URL: {ANALYTICS_SUPABASE_URL}")
    
    # Check Supabase Key
    if not ANALYTICS_SUPABASE_KEY:
        issues.append("❌ ANALYTICS_SUPABASE_KEY is not set")
    elif not ANALYTICS_SUPABASE_KEY.startswith("eyJ"):
        issues.append("⚠️  ANALYTICS_SUPABASE_KEY doesn't look like a JWT token")
    else:
        print(f"✅ ANALYTICS_SUPABASE_KEY: {ANALYTICS_SUPABASE_KEY[:20]}...")
    
    # Check coins
    if not COINS:
        issues.append("❌ COINS list is empty")
    else:
        print(f"✅ COINS: {len(COINS)} configured ({', '.join(COINS[:3])}...)")
    
    print(f"✅ HISTORICAL_DAYS: {HISTORICAL_DAYS}")
    
    if issues:
        print("\n⚠️  ISSUES FOUND:")
        for issue in issues:
            print(f"   {issue}")
        return False
    
    print("\n✅ Environment configuration looks good!")
    return True


def check_database_connection():
    """Test Supabase connection."""
    print_header("DATABASE CONNECTION TEST")
    
    try:
        # Try to query the table
        response = analytics_client.table(ANALYTICS_TABLE).select("id").limit(1).execute()
        print("✅ Successfully connected to analytics Supabase")
        print(f"✅ Table '{ANALYTICS_TABLE}' exists and is accessible")
        return True
    
    except Exception as e:
        print(f"❌ Failed to connect to analytics database")
        print(f"   Error: {str(e)}")
        
        if "relation" in str(e).lower() and "does not exist" in str(e).lower():
            print("\n💡 SOLUTION:")
            print("   1. Go to your analytics Supabase project")
            print("   2. Open SQL Editor")
            print("   3. Run the contents of analytics_schema.sql")
        
        return False


def check_data_quality():
    """Analyze existing data in the database."""
    print_header("DATA QUALITY CHECK")
    
    try:
        # Count total records
        total = count_analytics_records()
        
        if total == 0:
            print("ℹ️  No records found in database")
            print("   This is expected if you haven't run initial backfill yet")
            print("\n💡 NEXT STEP:")
            print("   Run: python analytics_pipeline.py --initial")
            return True
        
        print(f"✅ Total records: {total:,}")
        
        # Count per symbol
        print("\n📊 Records per symbol:")
        for symbol in COINS:
            count = count_analytics_records(symbol)
            print(f"   {symbol}: {count:,} crossovers")
        
        # Get date range
        response = analytics_client.table(ANALYTICS_TABLE).select("crossover_utc").order("crossover_utc").limit(1).execute()
        earliest = response.data[0]["crossover_utc"] if response.data else None
        
        response = analytics_client.table(ANALYTICS_TABLE).select("crossover_utc").order("crossover_utc", desc=True).limit(1).execute()
        latest = response.data[0]["crossover_utc"] if response.data else None
        
        if earliest and latest:
            print(f"\n📅 Date coverage:")
            print(f"   Earliest crossover: {earliest}")
            print(f"   Latest crossover:   {latest}")
        
        # Sample metrics
        print("\n📈 Average metrics:")
        
        query = """
            SELECT 
                signal,
                COUNT(*) as trades,
                ROUND(AVG(mfe_percent), 2) as avg_mfe,
                ROUND(AVG(mae_percent), 2) as avg_mae,
                ROUND(AVG(pnl_percent), 2) as avg_pnl,
                ROUND(AVG(trade_duration), 0) as avg_duration
            FROM crossover_analytics
            GROUP BY signal
        """
        
        response = analytics_client.rpc("exec_sql", {"query": query}).execute()
        
        # Fallback if RPC not available
        response = analytics_client.table(ANALYTICS_TABLE).select("signal,mfe_percent,mae_percent,pnl_percent,trade_duration").execute()
        
        if response.data:
            # Calculate manually
            longs = [r for r in response.data if r["signal"] == "LONG"]
            shorts = [r for r in response.data if r["signal"] == "SHORT"]
            
            if longs:
                print(f"   LONG signals:")
                print(f"      Count: {len(longs)}")
                print(f"      Avg MFE: {sum(r['mfe_percent'] for r in longs)/len(longs):.2f}%")
                print(f"      Avg MAE: {sum(r['mae_percent'] for r in longs)/len(longs):.2f}%")
                print(f"      Avg PnL: {sum(r['pnl_percent'] for r in longs)/len(longs):.2f}%")
            
            if shorts:
                print(f"   SHORT signals:")
                print(f"      Count: {len(shorts)}")
                print(f"      Avg MFE: {sum(r['mfe_percent'] for r in shorts)/len(shorts):.2f}%")
                print(f"      Avg MAE: {sum(r['mae_percent'] for r in shorts)/len(shorts):.2f}%")
                print(f"      Avg PnL: {sum(r['pnl_percent'] for r in shorts)/len(shorts):.2f}%")
        
        print("\n✅ Data quality check complete")
        return True
    
    except Exception as e:
        print(f"❌ Error during data quality check: {str(e)}")
        return False


def check_utc_alignment():
    """Verify UTC format matches main dataset requirements."""
    print_header("UTC ALIGNMENT CHECK")
    
    try:
        response = analytics_client.table(ANALYTICS_TABLE).select("crossover_utc").limit(1).execute()
        
        if not response.data:
            print("ℹ️  No records to check (run initial backfill first)")
            return True
        
        utc_str = response.data[0]["crossover_utc"]
        print(f"✅ Sample UTC timestamp: {utc_str}")
        
        # Verify format
        if "T" in utc_str and ("+" in utc_str or "Z" in utc_str):
            print("✅ Format looks correct (ISO 8601 with timezone)")
        else:
            print("⚠️  UTC format might not be timezone-aware")
        
        # Check if parseable
        from datetime import datetime
        import pandas as pd
        
        parsed = pd.to_datetime(utc_str, utc=True)
        print(f"✅ Successfully parsed as: {parsed}")
        
        print("\n💡 This format will merge correctly with main dataset")
        print("   as long as both use pd.to_datetime(..., utc=True)")
        
        return True
    
    except Exception as e:
        print(f"❌ Error checking UTC alignment: {str(e)}")
        return False


def main():
    """Run all validation checks."""
    print("\n" + "🔍" * 35)
    print("   ANALYTICS PIPELINE VALIDATION")
    print("🔍" * 35)
    
    checks = [
        ("Environment", check_environment),
        ("Database Connection", check_database_connection),
        ("Data Quality", check_data_quality),
        ("UTC Alignment", check_utc_alignment)
    ]
    
    results = {}
    
    for name, check_func in checks:
        try:
            results[name] = check_func()
        except Exception as e:
            print(f"\n❌ {name} check crashed: {str(e)}")
            results[name] = False
    
    # Summary
    print_header("VALIDATION SUMMARY")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")
    
    print(f"\nOverall: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n🎉 All checks passed! Analytics pipeline is ready to use.")
        print("\n💡 NEXT STEPS:")
        print("   1. Run initial backfill: python analytics_pipeline.py --initial")
        print("   2. Schedule daily updates: python analytics_pipeline.py")
        print("   3. See README_ANALYTICS.md for more details")
    else:
        print("\n⚠️  Some checks failed. Please fix issues above before proceeding.")
        sys.exit(1)


if __name__ == "__main__":
    main()
