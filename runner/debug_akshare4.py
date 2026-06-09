#!/usr/bin/env python3
import akshare as ak

print("=== stock_zh_a_spot_sina ===")
try:
    df = ak.stock_zh_a_spot()
    print("shape:", df.shape)
    print("columns:", list(df.columns))
    print(df.head(2))
except Exception as e:
    print(f"error: {e}")

print("\n=== stock_zh_a_hist_tx ===")
try:
    df2 = ak.stock_zh_a_hist_tx(symbol="000001")
    print("shape:", df2.shape)
    print("columns:", list(df2.columns))
    print(df2.head(2))
except Exception as e:
    print(f"error: {e}")

print("\n=== stock_zh_a_hist_sina ===")
try:
    df3 = ak.stock_zh_a_hist(symbol="sh600000", period="daily", start_date="20250401", end_date="20250425", adjust="")
    print("shape:", df3.shape)
    print("columns:", list(df3.columns))
    print(df3.head(2))
except Exception as e:
    print(f"error: {e}")
