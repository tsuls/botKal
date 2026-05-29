"""
Run this first to confirm which markets the bot will watch.
    python check_markets.py

It prints every open BTC market from Kalshi so you can verify
the series ticker and 15-min detection logic are correct.
"""

from client import KalshiClient
import json

client = KalshiClient()

# 1. Show all open markets that mention BTC
print("=== All open BTC markets ===")
data = client._get("/markets", params={"status": "open", "series_ticker": "KXBTC", "limit": 100})
markets = data.get("markets", [])
if not markets:
    # Try alternate series tickers if KXBTC returns nothing
    for series in ["BTCX", "BTC", "KXBTCD"]:
        data = client._get("/markets", params={"status": "open", "series_ticker": series, "limit": 20})
        markets = data.get("markets", [])
        if markets:
            print(f"Found markets under series: {series}")
            break

for m in markets:
    print(json.dumps({
        "ticker":     m.get("ticker"),
        "title":      m.get("title"),
        "subtitle":   m.get("subtitle"),
        "close_time": m.get("close_time"),
        "status":     m.get("status"),
    }, indent=2))

# 2. Show what the bot would actually watch
print("\n=== Markets bot will subscribe to ===")
fifteen = client.get_active_btc_markets()
for m in fifteen:
    print(f"  {m.get('ticker')} — closes {m.get('close_time')}")

client.close()
