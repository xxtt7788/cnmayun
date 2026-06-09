#!/usr/bin/env python3
"""
Debug CNINFO getCompanyIntroduction API with correct scode format.

Author: Kimi Code CLI Agent
Date: 2026-04-27
"""
import json
from urllib.request import Request, urlopen

CNINFO_INTRO_API = "https://webapi.cninfo.com.cn/api/data20/companyOverview/getCompanyIntroduction"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

for code in ["600000", "000001", "430047"]:
    url = f"{CNINFO_INTRO_API}?scode={code}"
    print(f"\n=== {code} ===")
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"Status: {data.get('status')}")
            print(f"Message: {data.get('msg')}")
            records = data.get("records") or data.get("data") or []
            print(f"Records count: {len(records)}")
            if records:
                print(f"Keys: {list(records[0].keys())[:20]}")
                for k, v in list(records[0].items())[:10]:
                    print(f"  {k}: {v}")
    except Exception as e:
        print(f"Error: {e}")
