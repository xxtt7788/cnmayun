#!/usr/bin/env python3
import json
from urllib.request import Request, urlopen
import time

url = "https://emweb.securities.eastmoney.com/PC_HSF10/ShareholderResearch/PageSDGD?code=SZ000001&date=2024-12-31"
req = Request(url, headers={
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Referer": "https://emweb.securities.eastmoney.com/"
})

print(f"Fetching {url}")
start = time.time()
try:
    with urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        print(f"Done in {time.time()-start:.2f}s, keys: {data.keys()}")
        if "sdgd" in data:
            print(f"sdgd count: {len(data['sdgd'])}")
except Exception as e:
    print(f"Error in {time.time()-start:.2f}s: {e}")
