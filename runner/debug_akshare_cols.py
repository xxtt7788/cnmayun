#!/usr/bin/env python3
import akshare as ak

# Test stock_gdfx_top_10_em
print("=== stock_gdfx_top_10_em ===")
try:
    df = ak.stock_gdfx_top_10_em(symbol="000001")
    print("columns:", list(df.columns))
    print(df.head(2))
except Exception as e:
    print(f"error: {e}")

print("\n=== stock_individual_info_em ===")
try:
    df2 = ak.stock_individual_info_em(symbol="000001")
    print("columns:", list(df2.columns))
    print(df2)
except Exception as e:
    print(f"error: {e}")

print("\n=== stock_zh_a_hist ===")
try:
    df3 = ak.stock_zh_a_hist(symbol="000001", period="daily", start_date="20250401", end_date="20250425", adjust="qfq")
    print("columns:", list(df3.columns))
    print(df3.head(2))
except Exception as e:
    print(f"error: {e}")
