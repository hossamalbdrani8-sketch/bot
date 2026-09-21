import os
import hmac
import hashlib
import requests
from flask import Flask, request, jsonify

# ============================================================
# AI PRO MAX — TRADINGVIEW DIRECT WEBHOOK
# One file: TASI + US + CRYPTO
#
# DATA SOURCE:
#   TradingView -> Webhook -> Railway -> Telegram
#
# NO market-data API is used here.
# NO Twelve Data.
# NO SAHMK.
#
# Railway Variables:
#   CHAT_ID
#   TASI_TOKEN
#   US_TOKEN
#   CRYPTO_TOKEN
#   WEBHOOK_SECRET   (optional but recommended)
#
# Accepted signals:
#   BUY
#   SELL
#
# Doji is ignored.
# ============================================================

app = Flask(__name__)

CHAT_ID = os.getenv("CHAT_ID", "").strip()
TASI_TOKEN = os.getenv("TASI_TOKEN", "").strip()
US_TOKEN = os.getenv("US_TOKEN", "").strip()
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN", "").strip()
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()

MARKET_TOKENS = {
    "TASI": TASI_TOKEN,
    "SAUDI": TASI_TOKEN,
    "TADAWUL": TASI_TOKEN,
    "SA": TASI_TOKEN,
    "US": US_TOKEN,
    "USA": US_TOKEN,
    "NASDAQ": US_TOKEN,
    "NYSE": US_TOKEN,
    "CRYPTO": CRYPTO_TOKEN,
    "CRYPTOCURRENCY": CRYPTO_TOKEN,
    "COIN": CRYPTO_TOKEN,
}

session = requests.Session()
session.headers.update({
    "User-Agent": "AI-PRO-MAX-TradingView-Webhook/1.0"
})


def clean(value):
    if value is None:
        return ""
    return str(value).strip()


def normalize_signal(value):
    signal = clean(value).upper()

    # Only BUY / SELL are accepted.
    if signal == "BUY":
        return "BUY"

    if signal == "SELL":
        return "SELL"

    return ""


def normalize_market(value, ticker=""):
    market = clean(value).upper()

    if market in MARKET_TOKENS:
        if market in ("SA", "SAUDI", "TADAWUL"):
            return "TASI"
        if market in ("USA", "NASDAQ", "NYSE"):
            return "US"
        if market in ("CRYPTOCURRENCY", "COIN"):
            return "CRYPTO"
        return market

    # Helpful fallbacks when TradingView sends exchange instead of market.
    exchange = market
    ticker_upper = clean(ticker).upper()

    if exchange in ("TADAWUL", "TASI", "SAUDI"):
        return "TASI"

    if exchange in ("NASDAQ", "NYSE", "AMEX", "CBOE"):
        return "US"

    # Common TradingView crypto exchanges.
    if exchange in (
        "BINANCE", "COINBASE", "BYBIT", "OKX",
        "KRAKEN", "BITSTAMP", "CRYPTO",
    ):
        return "CRYPTO"

    # Fallback for common crypto pair formats.
    if "/" in ticker_upper or ticker_upper.endswith("USDT"):
        return "CRYPTO"

    return ""


def valid_secret(req):
    if not WEBHOOK_SECRET:
        return True

    supplied = clean(req.headers.get("X-Webhook-Secret"))

    # Also accept ?secret=... for TradingView configurations where
    # custom headers are not convenient.
    if not supplied:
        supplied = clean(req.args.get("secret"))

    return hmac.compare_digest(supplied, WEBHOOK_SECRET)


def token_for_market(market):
    return MARKET_TOKENS.get(market, "")


def telegram_send(token, text):
    if not token or not CHAT_ID:
        print("Telegram configuration missing")
        return False, "telegram_configuration_missing"

    try:
        response = session.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=(10, 30),
        )

        if response.ok:
            return True, "sent"

        print(
            "Telegram HTTP",
            response.status_code,
            response.text[:500],
        )
        return False, f"telegram_http_{response.status_code}"

    except requests.RequestException as exc:
        print("Telegram connection error:", exc)
        return False, "telegram_connection_error"


def tradingview_chart_url(ticker):
    ticker = clean(ticker)

    if not ticker:
        return ""

    # TradingView accepts the ticker as supplied by the alert.
    # This is only a convenience button; it does not fetch data.
    return f"https://www.tradingview.com/chart/?symbol={ticker}"


def build_message(payload, market, signal):
    ticker = clean(
        payload.get("ticker")
        or payload.get("symbol")
        or payload.get("syminfo")
        or "UNKNOWN"
    )

    price = clean(
        payload.get("price")
        or payload.get("close")
        or payload.get("last")
    )

    timeframe = clean(
        payload.get("timeframe")
        or payload.get("interval")
        or payload.get("tf")
    )

    exchange = clean(
        payload.get("exchange")
        or payload.get("venue")
    )

    source = clean(payload.get("source")) or "AI PRO MAX / TradingView"
    alert_time = clean(
        payload.get("time")
        or payload.get("timestamp")
    )

    market_name = {
        "TASI": "🇸🇦 السوق السعودي",
        "US": "🇺🇸 السوق الأمريكي",
        "CRYPTO": "🪙 العملات الرقمية",
    }.get(market, market)

    if signal == "BUY":
        badge = "🟢 <b>BUY — شراء</b>"
    else:
        badge = "🔴 <b>SELL — بيع</b>"

    lines = [
        "💀🚀 <b>AI PRO MAX</b>",
        "",
        market_name,
        f"📌 <b>{ticker}</b>",
        "",
        badge,
    ]

    if price:
        lines.append(f"💰 السعر: <b>{price}</b>")

    if timeframe:
        lines.append(f"⏱️ الفاصل: <b>{timeframe}</b>")

    if exchange:
        lines.append(f"🏦 المنصة: <b>{exchange}</b>")

    lines.extend([
        "",
        "📡 المصدر: <b>TradingView</b>",
        f"🧠 النظام: <b>{source}</b>",
    ])

    if alert_time:
        lines.append(f"🕒 الوقت: <b>{alert_time}</b>")

    chart_url = tradingview_chart_url(ticker)
    if chart_url:
        lines.extend([
            "",
            f"📈 {chart_url}",
        ])

    lines.extend([
        "",
        "⚠️ <i>تم اعتماد BUY / SELL فقط. إشارات Doji يتم تجاهلها.</i>",
    ])

    return "\n".join(lines)


@app.get("/")
def home():
    return jsonify({
        "status": "ok",
        "service": "AI PRO MAX TradingView Webhook",
        "source": "TradingView",
        "markets": ["TASI", "US", "CRYPTO"],
        "accepted_signals": ["BUY", "SELL"],
        "doji": "ignored",
    })


@app.get("/health")
def health():
    return jsonify({
        "status": "healthy",
        "telegram_chat_id": bool(CHAT_ID),
        "tasi_bot": bool(TASI_TOKEN),
        "us_bot": bool(US_TOKEN),
        "crypto_bot": bool(CRYPTO_TOKEN),
        "webhook_secret": bool(WEBHOOK_SECRET),
    })


@app.post("/webhook")
def webhook():
    if not valid_secret(request):
        return jsonify({
            "ok": False,
            "error": "unauthorized",
        }), 401

    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify({
            "ok": False,
            "error": "JSON body required",
        }), 400

    # Ignore Doji explicitly.
    source_text = " ".join(
        clean(payload.get(key))
        for key in ("signal", "source", "type", "pattern", "message")
    ).upper()

    if "DOJI" in source_text:
        return jsonify({
            "ok": True,
            "ignored": "DOJI",
        }), 200

    signal = normalize_signal(
        payload.get("signal")
        or payload.get("action")
        or payload.get("side")
    )

    if not signal:
        return jsonify({
            "ok": True,
            "ignored": "signal_not_buy_or_sell",
        }), 200

    ticker = (
        payload.get("ticker")
        or payload.get("symbol")
        or payload.get("syminfo")
        or ""
    )

    market = normalize_market(
        payload.get("market")
        or payload.get("exchange")
        or payload.get("venue"),
        ticker=ticker,
    )

    if not market:
        return jsonify({
            "ok": False,
            "error": "market_required",
            "accepted_markets": ["TASI", "US", "CRYPTO"],
        }), 400

    token = token_for_market(market)

    if not token:
        return jsonify({
            "ok": False,
            "error": f"{market}_TOKEN_missing",
        }), 500

    message = build_message(payload, market, signal)

    sent, result = telegram_send(token, message)

    return jsonify({
        "ok": sent,
        "market": market,
        "signal": signal,
        "result": result,
    }), (200 if sent else 502)


if __name__ == "__main__":
    # Local development only. Railway uses Gunicorn.
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
    )
