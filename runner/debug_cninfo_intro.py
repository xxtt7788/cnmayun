#!/usr/bin/env python3
"""
Debug CNINFO getCompanyIntroduction API.

Author: Kimi Code CLI Agent
Date: 2026-04-27
"""
import json
from urllib.request import Request, urlopen

CNINFO_INTRO_API = "https://webapi.cninfo.com.cn/api/data20/companyOverview/getCompanyIntroduction"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

for code in ["SH600000", "SZ000001", "BJ430047"]:
    url = f"{CNINFO_INTRO_API}?scode={code}"
    print(f"\n=== {code} ===")
    print(f"URL: {url}")
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"Status: {data.get('status')}")
            print(f"Message: {data.get('msg')}")
            records = data.get("records") or data.get("data") or []
            print(f"Records count: {len(records)}")
            if records:
                print(f"First record keys: {list(records[0].keys())[:20]}")
                print(f"Sample: {json.dumps(records[0], ensure_ascii=False, indent=2)[:1000]}")
    except Exception as e:
        print(f"Error: {e}")
