#!/usr/bin/env python3
import akshare as ak

print("=== stock_gdfx_free_holding_detail_em ===")
try:
    df = ak.stock_gdfx_free_holding_detail_em()
    print("columns:", list(df.columns))
    print(df.head(2))
except Exception as e:
    print(f"error: {e}")

print("\n=== stock_zh_a_spot_em ===")
try:
    df2 = ak.stock_zh_a_spot_em()
    print("columns sample:", [c for c in df2.columns if "市值" in c or "代码" in c or "名称" in c])
    print(df2[["代码", "名称", "总市值"]].head(2) if "总市值" in df2.columns else "no 总市值")
except Exception as e:
    print(f"error: {e}")

print("\n=== stock_gdfx_top_10_em (retry) ===")
try:
    df3 = ak.stock_gdfx_top_10_em(symbol="000001")
    print("columns:", list(df3.columns))
except Exception as e:
    print(f"error: {e}")
