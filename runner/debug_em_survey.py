#!/usr/bin/env python3
import json
from urllib.request import Request, urlopen

url = "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/CompanySurveyAjax?code=SZ000001"
req = Request(url, headers={
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Referer": "https://emweb.securities.eastmoney.com/"
})

try:
    with urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        print("top keys:", data.keys())
        if "jbzl" in data:
            jbzl = data["jbzl"]
            print("jbzl type:", type(jbzl))
            if isinstance(jbzl, dict):
                print("jbzl keys:", list(jbzl.keys()))
                for k, v in jbzl.items():
                    print(f"  {k}: {v}")
            elif isinstance(jbzl, list) and jbzl:
                print("jbzl[0] keys:", list(jbzl[0].keys()))
                for k, v in jbzl[0].items():
                    print(f"  {k}: {v}")
        if "fxxg" in data:
            fxxg = data["fxxg"]
            print("\nfxxg type:", type(fxxg))
            if isinstance(fxxg, dict):
                print("fxxg keys:", list(fxxg.keys()))
                for k, v in fxxg.items():
                    if any(x in k for x in ["\u5e02\u503c", "\u80a1\u672c", "\u5458\u5de5", "\u6ce8\u518c"]):
                        print(f"  {k}: {v}")
            elif isinstance(fxxg, list) and fxxg:
                print("fxxg[0] keys:", list(fxxg[0].keys()))
                for k, v in fxxg[0].items():
                    if any(x in k for x in ["\u5e02\u503c", "\u80a1\u672c", "\u5458\u5de5", "\u6ce8\u518c"]):
                        print(f"  {k}: {v}")
except Exception as e:
    print(f"error: {e}")
