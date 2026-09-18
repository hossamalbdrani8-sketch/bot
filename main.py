import os
import json
import time
import requests
import websocket

# =========================================================
# SIFTINGIO CONNECTION TEST
# =========================================================

API_KEY = os.getenv("SIFTING_API_KEY")

if not API_KEY:
    print("❌ SIFTING_API_KEY غير موجود في Railway")
    raise SystemExit(1)

print("=" * 60)
print("🚀 SIFTINGIO TEST")
print("=" * 60)

print("🔑 SIFTING_API_KEY: موجود ✅")
print()


# =========================================================
# REST TEST
# =========================================================

def rest_test(name, url):

    print(f"📡 REST → {name}")

    try:
        response = requests.get(
            url,
            headers={
                "X-API-Key": API_KEY
            },
            timeout=20
        )

        print("HTTP:", response.status_code)

        if response.status_code == 200:
            data = response.json()
            print("✅ REST يعمل")
            print(json.dumps(data, indent=2)[:2000])
            print()
            return True

        print("❌ REST فشل")
        print(response.text[:2000])
        print()

    except Exception as e:
        print("❌ REST ERROR:", e)
        print()

    return False


# الأسهم الأمريكية
rest_test(
    "AAPL",
    "https://api.sifting.io/v1/last/trade/stocks/AAPL"
)

# Bitcoin
rest_test(
    "BTCUSD",
    "https://api.sifting.io/v1/last/trade/crypto/BTCUSD"
)


# =========================================================
# WEBSOCKET TEST
# =========================================================

WS_URL = f"wss://stream.sifting.io/ws/v1?key={API_KEY}"

print("=" * 60)
print("🔴 WEBSOCKET TEST")
print("=" * 60)


def on_open(ws):

    print("✅ WebSocket CONNECTED")

    # US Stocks
    ws.send(json.dumps({
        "op": "subscribe",
        "product": "us",
        "symbols": [
            "AAPL"
        ]
    }))

    # Crypto
    ws.send(json.dumps({
        "op": "subscribe",
        "product": "cex",
        "symbols": [
            "BTCUSD"
        ]
    }))

    print("📡 اشتركنا في:")
    print("   🇺🇸 AAPL")
    print("   🪙 BTCUSD")
    print()


def on_message(ws, message):

    try:

        data = json.loads(message)

        event = data.get("f")

        if event == "ack":

            print(
                "✅ ACK:",
                json.dumps(data, ensure_ascii=False)
            )

        elif event == "tick":

            symbol = data.get("s")
            price = data.get("p")
            bid = data.get("b")
            ask = data.get("a")
            timestamp = data.get("t")

            print(
                f"📈 TICK | {symbol} | "
                f"PRICE={price} | "
                f"BID={bid} | "
                f"ASK={ask} | "
                f"T={timestamp}"
            )

        elif event == "pong":

            print("💓 PONG")

        elif event == "error":

            print(
                "❌ SIFTING ERROR:",
                json.dumps(data, ensure_ascii=False)
            )

        else:

            print(
                "📨 MESSAGE:",
                json.dumps(data, ensure_ascii=False)
            )

    except Exception as e:

        print("❌ MESSAGE ERROR:", e)


def on_error(ws, error):

    print("❌ WEBSOCKET ERROR:")
    print(error)


def on_close(ws, close_status_code, close_msg):

    print()
    print("🔴 WebSocket CLOSED")
    print("Code:", close_status_code)
    print("Message:", close_msg)


# =========================================================
# RUN
# =========================================================

while True:

    try:

        print("🔌 Connecting WebSocket...")

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

    except Exception as e:

        print("❌ CONNECTION ERROR:", e)

    print("🔄 إعادة الاتصال بعد 10 ثواني...")
    time.sleep(10)