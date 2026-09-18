import os
import requests

KEY = os.getenv("SIFTING_API_KEY")

if not KEY:
    print("❌ SIFTING_API_KEY غير موجود")
    raise SystemExit(1)

url = "https://api.sifting.io/v1/fnd/stocks/search"

r = requests.get(
    url,
    headers={"X-API-Key": KEY},
    params={"q": "AAPL", "limit": 5},
    timeout=20
)

print("HTTP:", r.status_code)
print(r.text[:3000])