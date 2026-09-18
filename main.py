import os
import requests

key = os.getenv("SIFTING_API_KEY")

if not key:
    print("❌ SIFTING_API_KEY غير موجود")
    raise SystemExit

r = requests.get(
    "https://api.sifting.io/v1/fnd/stocks/search",
    headers={"X-API-Key": key},
    params={"q": "apple", "limit": 5},
    timeout=20
)

print("HTTP:", r.status_code)
print(r.text[:3000])