#!/usr/bin/env python3
import akshare as ak

print("=== stock_zh_a_daily ===")
try:
    df = ak.stock_zh_a_daily(symbol="sh600000", start_date="20240425", end_date="20250425", adjust="qfq")
    print("shape:", df.shape)
    print("columns:", list(df.columns))
    print(df.head(2))
except Exception as e:
    print(f"error: {e}")

print("\n=== stock_yjbb_em quick ===")
try:
    df2 = ak.stock_yjbb_em(date="20241231")
    print("shape:", df2.shape)
    print("head:", df2.head(1))
except Exception as e:
    print(f"error: {e}")
