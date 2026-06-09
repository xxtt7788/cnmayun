#!/usr/bin/env python3
import akshare as ak

print("=== stock_gdfx_top_10_em with date ===")
try:
    df = ak.stock_gdfx_top_10_em(symbol="000001", date="20241231")
    print("columns:", list(df.columns))
    print(df.head(2))
except Exception as e:
    print(f"error: {e}")

print("\n=== stock_zh_a_spot_em ===")
try:
    df2 = ak.stock_zh_a_spot_em()
    print("shape:", df2.shape)
    cols = [c for c in df2.columns if "市值" in c or "代码" in c or "名称" in c]
    print("cols:", cols)
    if "代码" in df2.columns and "总市值" in df2.columns:
        print(df2[["代码", "名称", "总市值"]].head(2))
except Exception as e:
    print(f"error: {e}")

print("\n=== stock_zh_a_hist ===")
try:
    df3 = ak.stock_zh_a_hist(symbol="000001", period="daily", start_date="20250401", end_date="20250425", adjust="qfq")
    print("columns:", list(df3.columns))
    print(df3.head(2))
except Exception as e:
    print(f"error: {e}")
