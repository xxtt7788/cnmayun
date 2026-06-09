#!/usr/bin/env python3
import json
from urllib.request import Request, urlopen

url = "https://push2.eastmoney.com/api/qt/stock/get"
params = "?fltt=2&invt=2&fields=f120,f121,f122,f174,f175,f59,f163,f43,f57,f58,f169,f170,f46,f44,f51,f168,f47,f164,f116,f60,f45,f52,f50,f48,f167,f117,f71,f161,f49,f530,f135,f136,f137,f138,f139,f141,f142,f144,f145,f147,f148,f140,f143,f146,f149,f55,f62,f162,f92,f173,f104,f105,f84,f85,f183,f184,f185,f186,f187,f188,f189,f190,f191,f192,f107,f111,f86,f177,f78,f110,f262,f263,f264,f267,f268,f255,f256,f257,f258,f127,f199,f128,f198,f259,f260,f261,f171,f277,f278,f279,f288,f152,f250,f251,f252,f253,f254,f269,f270,f271,f272,f273,f274,f275,f276,f265,f266,f289,f290,f286,f285,f292,f293,f294,f295,f43&secid=0.000001"

req = Request(url + params, headers={
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/"
})

try:
    with urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        print("keys:", data.keys())
        if "data" in data and data["data"]:
            d = data["data"]
            print("f116(total shares):", d.get("f116"))
            print("f117(circ shares):", d.get("f117"))
            print("f84(listing date):", d.get("f84"))
            print("f85(total shares?):", d.get("f85"))
        else:
            print("no data")
except Exception as e:
    print(f"error: {e}")
