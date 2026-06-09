#!/usr/bin/env python3
import json
from urllib.request import Request, urlopen

# Test PageSDGD (shareholder top10)
url1 = "https://emweb.securities.eastmoney.com/PC_HSF10/ShareholderResearch/PageSDGD?code=SZ000001&date=2024-12-31"
req1 = Request(url1, headers={
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Referer": "https://emweb.securities.eastmoney.com/"
})

try:
    with urlopen(req1, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        print("PageSDGD keys:", data.keys())
        if "sdgd" in data:
            print("sdgd count:", len(data["sdgd"]))
            if data["sdgd"]:
                print("sample:", data["sdgd"][0])
except Exception as e:
    print(f"PageSDGD error: {e}")

# Test CompanySurveyAjax (company overview)
url2 = "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/CompanySurveyAjax?code=SZ000001"
req2 = Request(url2, headers={
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Referer": "https://emweb.securities.eastmoney.com/"
})

try:
    with urlopen(req2, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        print("\nCompanySurvey keys:", data.keys())
        if "data" in data and data["data"]:
            d = data["data"]
            print("sample fields:", list(d.keys())[:20])
            # Look for market cap, employee count, registered capital
            for k in d:
                if any(x in k for x in ["\u5e02\u503c", "\u5458\u5de5", "\u6ce8\u518c", "\u8d44\u672c", "\u603b\u80a1\u672c"]):
                    print(f"  {k}: {d[k]}")
except Exception as e:
    print(f"CompanySurvey error: {e}")
