#!/usr/bin/env python3
"""
Try multiple CNINFO API URL patterns.

Author: Kimi Code CLI Agent
Date: 2026-04-27
"""
import json
from urllib.request import Request, urlopen

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

urls = [
    "https://webapi.cninfo.com.cn/api/data20/companySnapshot/getCompanyIntroduction?scode=600000",
    "https://webapi.cninfo.com.cn/api/stock/p_stock2401?scode=600000",
    "https://webapi.cninfo.com.cn/api/data20/companyOverview/getCompanyIntroduction?scode=SH600000",
    "https://webapi.cninfo.com.cn/api/data20/companyOverview/getCompanyIntroduction?mcode=600000",
]

for url in urls:
    print(f"\n=== {url} ===")
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"Status: {data.get('status')}, Msg: {data.get('msg')}")
            records = data.get("records") or data.get("data") or []
            print(f"Records: {len(records)}")
            if records:
                print(f"Keys: {list(records[0].keys())[:10]}")
    except Exception as e:
        print(f"Error: {e}")
