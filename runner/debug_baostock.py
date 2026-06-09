#!/usr/bin/env python3
import baostock as bs
import pandas as pd

print("=== baostock login ===")
lg = bs.login()
print("login msg:", lg.error_msg)

print("\n=== query_history_k_data_plus ===")
rs = bs.query_history_k_data_plus("sh.600000",
    "date,code,open,high,low,close,volume,amount,turn,pctChg",
    start_date='2025-04-01', end_date='2025-04-25', frequency="d")
print("query msg:", rs.error_msg)
data = []
while (rs.error_code == '0') & rs.next():
    data.append(rs.get_row_data())
df = pd.DataFrame(data, columns=rs.fields)
print("shape:", df.shape)
print(df.head(2))

print("\n=== query_stock_basic ===")
rs2 = bs.query_stock_basic(code="sh.600000")
print("query msg:", rs2.error_msg)
data2 = []
while (rs2.error_code == '0') & rs2.next():
    data2.append(rs2.get_row_data())
df2 = pd.DataFrame(data2, columns=rs2.fields)
print(df2)

bs.logout()
