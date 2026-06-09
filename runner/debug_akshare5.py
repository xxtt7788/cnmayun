#!/usr/bin/env python3
import akshare as ak

print("=== stock_yjbb_em ===")
try:
    df = ak.stock_yjbb_em(date="20241231")
    print("shape:", df.shape)
    cols = [c for c in df.columns if "员工" in c or "注册" in c or "代码" in c]
    print("cols:", cols)
    if cols:
        print(df[cols].head(2))
except Exception as e:
    print(f"error: {e}")

print("\n=== stock_zh_a_daily ===")
try:
    df2 = ak.stock_zh_a_daily(symbol="sh600000", start_date="20240425", end_date="20250425", adjust="qfq")
    print("shape:", df2.shape)
    print("columns:", list(df2.columns))
    print(df2.head(2))
except Exception as e:
    print(f"error: {e}")

print("\n=== stock_zh_a_hist (baidu?) ===")
try:
    df3 = ak.stock_zh_a_hist(symbol="000001", period="daily", start_date="20250401", end_date="20250425", adjust="qfq")
    print("shape:", df3.shape)
except Exception as e:
    print(f"error: {e}")
