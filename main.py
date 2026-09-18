import os
import json
import time
import websocket

API_KEY = os.getenv("SIFTING_API_KEY")

if not API_KEY:
    print("❌ SIFTING_API_KEY غير موجود")
    raise SystemExit(1)

print("========================================")
print("🚀 SIFTINGIO WEBSOCKET TEST")
print("========================================")
print("🔑 API KEY: موجود ✅")

WS_URL = f"wss://stream.sifting.io/ws/v1?key={API_KEY}"


def on_open(ws):
    print("🟢 WebSocket CONNECTED")

    # 🇺🇸 US
    ws.send(json.dumps({
        "op": "subscribe",
        "product": "us",
        "symbols": ["AAPL", "MSFT", "NVDA"]
    }))

    # 🪙 Crypto
    ws.send(json.dumps({
        "op": "subscribe",
        "product": "cex",
        "symbols": ["BTCUSD", "ETHUSD"]
    }))

    print("📡 اشتركنا في الأسهم والكريبتو")


def on_message(ws, message):
    try:
        data = json.loads(message)

        if data.get("f") == "ack":
            print("✅ ACK:")
            print(data)

        elif data.get("f") == "tick":
            symbol = data.get("s")
            price = data.get("p")
            bid = data.get("b")
            ask = data.get("a")

            print(
                f"📈 {symbol} | "
                f"PRICE={price} | "
                f"BID={bid} | "
                f"ASK={ask}"
            )

        elif data.get("f") == "error":
            print("❌ ERROR:")
            print(data)

        elif data.get("f") == "pong":
            print("💓 PONG")

    except Exception as e:
        print("❌ MESSAGE ERROR:", e)


def on_error(ws, error):
    print("❌ WebSocket ERROR:")
    print(error)


def on_close(ws, code, message):
    print("🔴 WebSocket CLOSED")
    print("Code:", code)
    print("Message:", message)


while True:

    try:
        print("🔌 Connecting...")

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