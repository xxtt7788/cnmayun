#!/usr/bin/env python3
"""
Test EastMoney executive data API for historical tenure dates.

Author: Kimi Code CLI Agent
Date: 2026-04-27
"""
import json
import urllib.request

# EastMoney executive holding change API
# https://data.eastmoney.com/executive/

def test_executive_api(ticker):
    em_code = f"SH{ticker}" if ticker.startswith("6") or ticker.startswith("5") else f"SZ{ticker}"
    
    # Try executive holding detail API
    url = f"https://datacenter-web.eastmoney.com/api/data/v1/get?sortColumns=SECUCODE&sortTypes=-1&pageSize=50&pageNumber=1&reportName=RPTA_WEB_RESPREPORT&columns=ALL&filter=(SECUCODE=%22{em_code}%22)"
    
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("result") and data["result"].get("data"):
                items = data["result"]["data"]
                print(f"  {ticker}: {len(items)} items")
                if items:
                    print(f"    sample keys: {list(items[0].keys())[:15]}")
                    print(f"    sample: {items[0]}")
                return True
    except Exception as e:
        print(f"  {ticker}: {e}")
    return False


if __name__ == "__main__":
    # Test with a few tickers
    for t in ["000001", "600000", "430047", "920751"]:
        print(f"Testing {t}...")
        test_executive_api(t)
        print()
