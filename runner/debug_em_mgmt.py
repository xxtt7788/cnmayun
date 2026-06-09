#!/usr/bin/env python3
import json
from urllib.request import Request, urlopen

url = "https://emweb.securities.eastmoney.com/PC_HSF10/CompanyManagement/CompanyManagementAjax?code=SZ000001"
req = Request(url, headers={
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Referer": "https://emweb.securities.eastmoney.com/"
})

try:
    with urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        print("success, keys:", data.keys())
        if "RptManagerList" in data:
            print("managers count:", len(data["RptManagerList"]))
except Exception as e:
    print(f"error: {e}")
