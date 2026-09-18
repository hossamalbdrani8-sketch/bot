import os
import json
import time
import requests
import websocket

API_KEY = os.getenv("SIFTING_API_KEY")

if not API_KEY:
    print("❌ SIFTING_API_KEY غير موجود")
    raise SystemExit(1)

HEADERS = {
    "X-API-Key": API_KEY,
    "Accept-Encoding": "gzip",
}

print("=" * 70)
print("🔎 SIFTINGIO ACCOUNT + MARKET TEST")
print("=" * 70)


# =========================================================
# 1) حسابك وحدود WebSocket
# =========================================================

WS_URL = f"wss://stream.sifting.io/ws/v1?key={API_KEY}"


def on_open(ws):
    print("\n🟢 WebSocket متصل")
    print("⏳ ننتظر معلومات الحساب من SiftingIO...")


def on_message(ws, message):
    try:
        data = json.loads(message)

        print("\n📨 SERVER:")
        print(json.dumps(data, ensure_ascii=False, indent=2))

        # معلومات الحساب
        if data.get("f") == "ack" and data.get("op") == "auth":

            print("\n" + "=" * 70)
            print("💳 حدود حساب SiftingIO")
            print("=" * 70)

            print("Tier:", data.get("tier"))
            print("Max Connections:", data.get("max_conn"))
            print("Max Subscriptions:", data.get("max_subs"))
            print("Active Connections:", data.get("active_conn"))

            print("=" * 70)

            # اختبار 5 أسهم + 5 كريبتو
            ws.send(json.dumps({
                "op": "subscribe",
                "product": "us",
                "symbols": [
                    "AAPL",
                    "MSFT",
                    "NVDA",
                    "AMZN",
                    "TSLA"
                ]
            }))

            ws.send(json.dumps({
                "op": "subscribe",
                "product": "cex",
                "symbols": [
                    "BTCUSD",
                    "ETHUSD",
                    "SOLUSD",
                    "XRPUSD",
                    "DOGEUSD"
                ]
            }))

            print("\n📡 تم طلب:")
            print("🇺🇸 5 أسهم أمريكية")
            print("🪙 5 عملات رقمية")

        elif data.get("f") == "tick":

            symbol = data.get("s")
            price = data.get("p")
            bid = data.get("b")
            ask = data.get("a")

            print(
                f"📈 LIVE | {symbol} | "
                f"PRICE={price} | "
                f"BID={bid} | "
                f"ASK={ask}"
            )

        elif data.get("f") == "error":

            print("\n❌ SIFTING ERROR")
            print("Code:", data.get("code"))
            print("Message:", data.get("message"))
            print("Limit:", data.get("limit"))

    except Exception as e:
        print("❌ Parse error:", e)


def on_error(ws, error):
    print("\n❌ WebSocket ERROR:")
    print(error)


def on_close(ws, code, message):
    print("\n🔴 WebSocket CLOSED")
    print("Code:", code)
    print("Message:", message)


# =========================================================
# 2) REST — اختبار الأسهم
# =========================================================

print("\n🇺🇸 اختبار الأسهم الأمريكية...")

try:

    r = requests.get(
        "https://api.sifting.io/v1/fnd/stocks/search",
        headers=HEADERS,
        params={
            "q": "a",
            "limit": 200
        },
        timeout=30
    )

    print("HTTP:", r.status_code)

    if r.status_code == 200:

        data = r.json()

        rows = data.get("data", [])

        print("✅ عدد النتائج في هذه الصفحة:", len(rows))

        meta = data.get("meta", {})

        print("📊 META:")
        print(json.dumps(meta, ensure_ascii=False, indent=2))

        print("\nأمثلة:")

        for x in rows[:20]:

            print(
                x.get("ticker"),
                "|",
                x.get("name"),
                "| CIK:",
                x.get("cik")
            )

    else:

        print("❌ REST ERROR")
        print(r.text[:2000])

except Exception as e:

    print("❌ REST EXCEPTION:", e)


# =========================================================
# 3) REST — اختبار Crypto
# =========================================================

print("\n🪙 اختبار Crypto...")

crypto_tests = [
    "BTCUSD",
    "ETHUSD",
    "SOLUSD",
    "XRPUSD",
    "DOGEUSD"
]

for symbol in crypto_tests:

    try:

        r = requests.get(
            f"https://api.sifting.io/v1/last/trade/crypto/{symbol}",
            headers=HEADERS,
            timeout=20
        )

        if r.status_code == 200:

            data = r.json()

            print(
                f"✅ {symbol} | "
                f"PRICE={data.get('p')}"
            )

        else:

            print(
                f"❌ {symbol} | "
                f"HTTP={r.status_code}"
            )

    except Exception as e:

        print(
            f"❌ {symbol} | ERROR={e}"
        )


# =========================================================
# 4) WebSocket
# =========================================================

print("\n" + "=" * 70)
print("🔴 بدء WebSocket")
print("=" * 70)

ws = websocket.WebSocketApp(
    WS_URL,
    on_open=on_open,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close
)

ws.run_forever(
    ping_interval=30,
    ping_timeout=10
)