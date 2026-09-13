# ============================================================
# 💀🚀 AI PRO MAX — TASI + US + CRYPTO
# ============================================================
# ملف واحد
# 3 بوتات Telegram
# TASI 375
# US Market
# Crypto Market
# 8 أهداف ATR
# VWAP + ATR + RSI + EMA
# Support / Resistance
# ARS Market Direction
# استمرار اتجاه صاعد 🟢 / هابط 🔴
# News Sentiment
# فحص تلقائي
# منع تكرار الإشارات
# ============================================================

import os
import time
import math
import requests
import threading
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================================
# 🔐 VARIABLES
# ============================================================

TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()

TASI_TOKEN = os.getenv("TASI_TOKEN", "").strip()
US_TOKEN = os.getenv("US_TOKEN", "").strip()
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN", "").strip()

# ============================================================
# ⚙️ SETTINGS
# ============================================================

SCAN_INTERVAL = 120

TIMEFRAMES = [
    "5min",
    "15min",
    "30min",
    "1h",
    "4h",
    "1day"
]

PRIMARY_TIMEFRAME = "15min"

EMA_FAST = 8
EMA_MID = 21
EMA_SLOW = 50
EMA_LONG = 200

RSI_LENGTH = 14
ATR_LENGTH = 14

RSI_BUY = 30
RSI_SELL = 70

VOLUME_LENGTH = 20

ATR_TARGET_1 = 1.0
ATR_TARGET_2 = 1.5
ATR_TARGET_3 = 2.0
ATR_TARGET_4 = 2.5
ATR_TARGET_5 = 3.0
ATR_TARGET_6 = 3.5
ATR_TARGET_7 = 4.0
ATR_TARGET_8 = 5.0

MAX_WORKERS = 8

MIN_SIGNAL_SCORE = 70

# ============================================================
# 🧠 STATE
# ============================================================

LAST_SIGNAL = {}
TREND_STATE = {}

LOCK = threading.Lock()

# ============================================================
# 📡 TWELVE DATA
# ============================================================

BASE_URL = "https://api.twelvedata.com"


def td_request(endpoint, params=None):
    if not TWELVEDATA_API_KEY:
        return None

    params = params or {}
    params["apikey"] = TWELVEDATA_API_KEY

    try:
        response = requests.get(
            BASE_URL + endpoint,
            params=params,
            timeout=20
        )

        if response.status_code != 200:
            return None

        data = response.json()

        if isinstance(data, dict) and data.get("status") == "error":
            return None

        return data

    except Exception:
        return None


# ============================================================
# 📊 INDICATORS
# ============================================================

def ema(values, length):
    if len(values) < length:
        return None

    multiplier = 2 / (length + 1)

    result = sum(values[:length]) / length

    for value in values[length:]:
        result = ((value - result) * multiplier) + result

    return result


def rsi(values, length=14):
    if len(values) < length + 1:
        return None

    gains = []
    losses = []

    for i in range(1, len(values)):
        change = values[i] - values[i - 1]

        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    avg_gain = sum(gains[:length]) / length
    avg_loss = sum(losses[:length]) / length

    for i in range(length, len(gains)):
        avg_gain = ((avg_gain * (length - 1)) + gains[i]) / length
        avg_loss = ((avg_loss * (length - 1)) + losses[i]) / length

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def atr(highs, lows, closes, length=14):
    if len(closes) < length + 1:
        return None

    trs = []

    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )

        trs.append(tr)

    if len(trs) < length:
        return None

    value = sum(trs[:length]) / length

    for tr in trs[length:]:
        value = ((value * (length - 1)) + tr) / length

    return value


def vwap(highs, lows, closes, volumes):

    cumulative_price_volume = 0
    cumulative_volume = 0

    for high, low, close, volume in zip(
        highs,
        lows,
        closes,
        volumes
    ):
        typical = (high + low + close) / 3

        cumulative_price_volume += typical * volume
        cumulative_volume += volume

    if cumulative_volume == 0:
        return None

    return cumulative_price_volume / cumulative_volume


def sma(values, length):

    if len(values) < length:
        return None

    return sum(values[-length:]) / length


# ============================================================
# 📥 PRICE DATA
# ============================================================

def get_series(symbol, interval, outputsize=220):

    data = td_request(
        "/time_series",
        {
            "symbol": symbol,
            "interval": interval,
            "outputsize": outputsize,
            "format": "JSON"
        }
    )

    if not data:
        return None

    values = data.get("values")

    if not values:
        return None

    values = list(reversed(values))

    candles = []

    for item in values:

        try:

            candles.append({
                "datetime": item.get("datetime"),
                "open": float(item["open"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "close": float(item["close"]),
                "volume": float(item.get("volume", 0))
            })

        except Exception:
            continue

    return candles


# ============================================================
# 🧱 SUPPORT / RESISTANCE
# ============================================================

def support_resistance(candles):

    if len(candles) < 30:
        return None, None

    recent = candles[-50:]

    highs = [x["high"] for x in recent]
    lows = [x["low"] for x in recent]

    resistance = max(highs)
    support = min(lows)

    return support, resistance


# ============================================================
# 📈 MARKET TREND
# ============================================================

def calculate_trend(candles):

    closes = [x["close"] for x in candles]

    e8 = ema(closes, EMA_FAST)
    e21 = ema(closes, EMA_MID)
    e50 = ema(closes, EMA_SLOW)
    e200 = ema(closes, EMA_LONG)

    current = closes[-1]

    bullish = 0
    bearish = 0

    if e8 and e21:

        if e8 > e21:
            bullish += 1
        else:
            bearish += 1

    if e21 and e50:

        if e21 > e50:
            bullish += 1
        else:
            bearish += 1

    if e50 and e200:

        if e50 > e200:
            bullish += 1
        else:
            bearish += 1

    if e200:

        if current > e200:
            bullish += 1
        else:
            bearish += 1

    if bullish >= 3:
        return "UP"

    if bearish >= 3:
        return "DOWN"

    return "NEUTRAL"


# ============================================================
# 🧠 ARS — AUTOMATIC MARKET DIRECTION SCORE
# ============================================================

def calculate_ars(candles):

    closes = [x["close"] for x in candles]

    if len(closes) < 50:
        return 50

    score = 50

    e8 = ema(closes, 8)
    e21 = ema(closes, 21)
    e50 = ema(closes, 50)

    current = closes[-1]

    if e8 > e21:
        score += 15
    else:
        score -= 15

    if e21 > e50:
        score += 15
    else:
        score -= 15

    if current > e50:
        score += 10
    else:
        score -= 10

    return max(0, min(100, score))


# ============================================================
# 🐋 BUY / SELL POWER
# ============================================================

def calculate_power(candles):

    recent = candles[-20:]

    buy_volume = 0
    sell_volume = 0

    for candle in recent:

        volume = candle["volume"]

        if candle["close"] > candle["open"]:
            buy_volume += volume

        elif candle["close"] < candle["open"]:
            sell_volume += volume

        else:
            buy_volume += volume * 0.5
            sell_volume += volume * 0.5

    total = buy_volume + sell_volume

    if total <= 0:
        return 50, 50

    buy = (buy_volume / total) * 100
    sell = (sell_volume / total) * 100

    return buy, sell


# ============================================================
# 📊 VOLUME STRENGTH
# ============================================================

def volume_strength(candles):

    volumes = [x["volume"] for x in candles]

    if len(volumes) < VOLUME_LENGTH + 1:
        return 1.0

    average = sma(volumes[:-1], VOLUME_LENGTH)

    if not average or average <= 0:
        return 1.0

    return volumes[-1] / average


# ============================================================
# 🎯 8 ATR TARGETS
# ============================================================

def targets(price, atr_value, direction):

    multipliers = [
        ATR_TARGET_1,
        ATR_TARGET_2,
        ATR_TARGET_3,
        ATR_TARGET_4,
        ATR_TARGET_5,
        ATR_TARGET_6,
        ATR_TARGET_7,
        ATR_TARGET_8
    ]

    result = []

    for multiplier in multipliers:

        if direction == "UP":
            target = price + (atr_value * multiplier)
        else:
            target = price - (atr_value * multiplier)

        result.append(target)

    return result


# ============================================================
# 🟢🔴 PERSISTENT TREND
# ============================================================

def persistent_trend(symbol, current_trend):

    with LOCK:

        previous = TREND_STATE.get(symbol)

        if current_trend == "NEUTRAL":

            if previous:
                return previous

            return "NEUTRAL"

        TREND_STATE[symbol] = current_trend

        return current_trend


# ============================================================
# 📰 NEWS SENTIMENT
# ============================================================

POSITIVE_WORDS = [
    "beat",
    "beats",
    "growth",
    "profit",
    "profits",
    "upgrade",
    "upgraded",
    "buy",
    "strong",
    "positive",
    "partnership",
    "contract",
    "approval",
    "revenue",
    "surge",
    "record"
]

NEGATIVE_WORDS = [
    "loss",
    "losses",
    "downgrade",
    "downgraded",
    "sell",
    "weak",
    "negative",
    "lawsuit",
    "decline",
    "drop",
    "warning",
    "debt",
    "offering",
    "investigation",
    "risk"
]


def news_sentiment(symbol):

    data = td_request(
        "/news",
        {
            "symbol": symbol,
            "limit": 10
        }
    )

    if not data:
        return "⚪ محايد"

    if isinstance(data, dict):
        articles = data.get("news", [])
    else:
        articles = data

    if not articles:
        return "⚪ محايد"

    positive = 0
    negative = 0

    for article in articles:

        text = (
            str(article.get("title", "")) +
            " " +
            str(article.get("description", ""))
        ).lower()

        for word in POSITIVE_WORDS:
            if word in text:
                positive += 1

        for word in NEGATIVE_WORDS:
            if word in text:
                negative += 1

    if positive > negative:
        return "🟢 إيجابي"

    if negative > positive:
        return "🔴 سلبي"

    return "⚪ محايد"


# ============================================================
# 🧠 SIGNAL ENGINE
# ============================================================

def analyze_symbol(symbol, market):

    candles = get_series(
        symbol,
        PRIMARY_TIMEFRAME,
        220
    )

    if not candles or len(candles) < 100:
        return None

    closes = [x["close"] for x in candles]
    highs = [x["high"] for x in candles]
    lows = [x["low"] for x in candles]
    volumes = [x["volume"] for x in candles]

    price = closes[-1]

    ema8 = ema(closes, EMA_FAST)
    ema21 = ema(closes, EMA_MID)
    ema50 = ema(closes, EMA_SLOW)
    ema200 = ema(closes, EMA_LONG)

    rsi_value = rsi(
        closes,
        RSI_LENGTH
    )

    atr_value = atr(
        highs,
        lows,
        closes,
        ATR_LENGTH
    )

    vwap_value = vwap(
        highs,
        lows,
        closes,
        volumes
    )

    support, resistance = support_resistance(candles)

    ars = calculate_ars(candles)

    buy_power, sell_power = calculate_power(candles)

    volume_ratio = volume_strength(candles)

    raw_trend = calculate_trend(candles)

    trend = persistent_trend(
        symbol,
        raw_trend
    )

    score = 50

    # EMA
    if price > ema8:
        score += 5
    else:
        score -= 5

    if ema8 > ema21:
        score += 7
    else:
        score -= 7

    if ema21 > ema50:
        score += 7
    else:
        score -= 7

    if ema50 > ema200:
        score += 7
    else:
        score -= 7

    # VWAP
    if vwap_value:

        if price > vwap_value:
            score += 7
        else:
            score -= 7

    # RSI
    if rsi_value:

        if 50 <= rsi_value <= 70:
            score += 8

        elif 30 <= rsi_value < 50:
            score += 2

        elif rsi_value < 30:
            score += 5

        elif rsi_value > 70:
            score -= 3

    # Buy / Sell power
    if buy_power > sell_power:
        score += 8
    else:
        score -= 8

    # Volume
    if volume_ratio >= 1.5:
        score += 5

    score = max(0, min(100, score))

    # ========================================================
    # SIGNAL
    # ========================================================

    if (
        trend == "UP"
        and score >= MIN_SIGNAL_SCORE
        and buy_power >= sell_power
    ):

        signal = "BUY"
        signal_text = "🟢 شراء قوي"

    elif (
        trend == "DOWN"
        and score <= 45
        and sell_power >= buy_power
    ):

        signal = "SELL"
        signal_text = "🔴 بيع قوي"

    else:

        signal = "WAIT"
        signal_text = "⚪ انتظار"

    # ========================================================
    # TARGETS
    # ========================================================

    direction = "UP" if signal == "BUY" else "DOWN"

    target_values = []

    if atr_value and signal != "WAIT":

        target_values = targets(
            price,
            atr_value,
            direction
        )

    # ========================================================
    # NEWS
    # ========================================================

    if market == "US":

        news = news_sentiment(symbol)

    else:

        news = "⚪ غير متاح"

    return {
        "symbol": symbol,
        "market": market,
        "price": price,
        "ema8": ema8,
        "ema21": ema21,
        "ema50": ema50,
        "ema200": ema200,
        "rsi": rsi_value,
        "atr": atr_value,
        "vwap": vwap_value,
        "support": support,
        "resistance": resistance,
        "ars": ars,
        "buy_power": buy_power,
        "sell_power": sell_power,
        "volume_ratio": volume_ratio,
        "trend": trend,
        "score": score,
        "signal": signal,
        "signal_text": signal_text,
        "news": news,
        "targets": target_values
    }


# ============================================================
# 🔢 FORMAT
# ============================================================

def fmt(value):

    if value is None:
        return "-"

    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"

    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"

    if abs(value) >= 1_000:
        return f"{value / 1_000:.2f}K"

    return f"{value:.2f}"


def pct(value):

    if value is None:
        return "-"

    return f"{value:.1f}%"


# ============================================================
# 📱 TELEGRAM
# ============================================================

def telegram_send(token, message):

    if not token or not CHAT_ID:
        return False

    url = (
        "https://api.telegram.org/bot"
        + token
        + "/sendMessage"
    )

    try:

        response = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=20
        )

        return response.ok

    except Exception:
        return False


# ============================================================
# 📨 MESSAGE
# ============================================================

def build_message(result):

    market = result["market"]

    if market == "TASI":
        market_name = "🇸🇦 السوق السعودي TASI"

    elif market == "US":
        market_name = "🇺🇸 السوق الأمريكي US"

    else:
        market_name = "🪙 العملات الرقمية CRYPTO"

    if result["trend"] == "UP":

        trend_text = "🟢 اتجاه صاعد"

    elif result["trend"] == "DOWN":

        trend_text = "🔴 اتجاه هابط"

    else:

        trend_text = "⚪ اتجاه محايد"

    if result["vwap"]:

        if result["price"] > result["vwap"]:
            vwap_text = "🟢 فوق VWAP"

        else:
            vwap_text = "🔴 تحت VWAP"

    else:

        vwap_text = "-"

    text = []

    text.append("💀🚀 <b>AI PRO MAX SIGNAL</b>")
    text.append("")
    text.append(market_name)
    text.append("")
    text.append(
        f"<b>{result['symbol']}</b>"
    )

    text.append("")
    text.append(
        f"{result['signal_text']}   |   قوة الإشارة: "
        f"<b>{result['score']}/100</b>"
    )

    text.append("")
    text.append(
        f"💰 السعر: <b>{fmt(result['price'])}</b>"
    )

    text.append(
        f"📈 EMA 8: {fmt(result['ema8'])}"
    )

    text.append(
        f"EMA 21: {fmt(result['ema21'])}"
    )

    text.append(
        f"EMA 50: {fmt(result['ema50'])}"
    )

    text.append(
        f"EMA 200: {fmt(result['ema200'])}"
    )

    text.append("")
    text.append(
        f"🧠 RSI: {fmt(result['rsi'])}"
    )

    text.append(
        f"📐 ATR: {fmt(result['atr'])}"
    )

    text.append(
        f"📊 VWAP: {fmt(result['vwap'])} "
        f"{vwap_text}"
    )

    text.append("")
    text.append(
        f"🟢 قوة الشراء: {pct(result['buy_power'])}"
    )

    text.append(
        f"🔴 قوة البيع: {pct(result['sell_power'])}"
    )

    text.append(
        f"📦 قوة الحجم: {result['volume_ratio']:.2f}x"
    )

    text.append("")
    text.append(
        f"🛡️ الدعم: <b>{fmt(result['support'])}</b>"
    )

    text.append(
        f"🚧 المقاومة: <b>{fmt(result['resistance'])}</b>"
    )

    text.append("")
    text.append(
        f"🧭 ARS: <b>{result['ars']}/100</b>"
    )

    text.append(
        f"📈 اتجاه السوق: <b>{trend_text}</b>"
    )

    if market == "US":

        text.append(
            f"📰 أخبار السهم: <b>{result['news']}</b>"
        )

    if result["targets"]:

        text.append("")
        text.append("🎯 <b>أهداف ATR — 8 أهداف</b>")

        for i, target in enumerate(
            result["targets"],
            start=1
        ):

            change = (
                (target - result["price"])
                / result["price"]
            ) * 100

            text.append(
                f"TP{i}: {fmt(target)} "
                f"({change:+.2f}%)"
            )

    text.append("")
    text.append(
        "🤖 الفحص تلقائي"
    )

    text.append(
        "🔄 الاتجاه يستمر حتى ظهور انعكاس مؤكد"
    )

    text.append(
        f"⏱️ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    return "\n".join(text)


# ============================================================
# 🚫 DUPLICATE CONTROL
# ============================================================

def should_send(result):

    if result["signal"] == "WAIT":
        return False

    key = result["symbol"]

    current_state = (
        result["signal"],
        result["trend"]
    )

    with LOCK:

        previous = LAST_SIGNAL.get(key)

        if previous == current_state:
            return False

        LAST_SIGNAL[key] = current_state

    return True


# ============================================================
# 📋 SYMBOL DISCOVERY
# ============================================================

def get_tasi_symbols():

    data = td_request(
        "/stocks",
        {
            "exchange": "TADAWUL"
        }
    )

    symbols = []

    if isinstance(data, dict):

        values = data.get("data", [])

    else:

        values = data or []

    for item in values:

        symbol = item.get("symbol")

        if symbol:
            symbols.append(symbol)

    return symbols[:375]


def get_us_symbols():

    symbols = []

    exchanges = [
        "NASDAQ",
        "NYSE",
        "AMEX"
    ]

    for exchange in exchanges:

        data = td_request(
            "/stocks",
            {
                "exchange": exchange
            }
        )

        if not data:
            continue

        values = data.get("data", [])

        for item in values:

            symbol = item.get("symbol")

            if symbol:
                symbols.append(symbol)

    return list(dict.fromkeys(symbols))


def get_crypto_symbols():

    data = td_request(
        "/cryptocurrencies",
        {}
    )

    symbols = []

    if isinstance(data, dict):

        values = data.get("data", [])

    else:

        values = data or []

    for item in values:

        symbol = item.get("symbol")

        if symbol:
            symbols.append(symbol)

    return symbols


# ============================================================
# 🔎 SCAN MARKET
# ============================================================

def scan_market(
    symbols,
    market,
    token
):

    if not symbols:
        return

    print(
        f"[{market}] "
        f"Scanning {len(symbols)} symbols..."
    )

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        jobs = {
            executor.submit(
                analyze_symbol,
                symbol,
                market
            ): symbol

            for symbol in symbols
        }

        for job in as_completed(jobs):

            try:

                result = job.result()

                if not result:
                    continue

                if should_send(result):

                    message = build_message(result)

                    telegram_send(
                        token,
                        message
                    )

                    print(
                        f"[{market}] "
                        f"{result['symbol']} "
                        f"{result['signal']} "
                        f"{result['score']}"
                    )

            except Exception as error:

                print(
                    f"[{market}] error:",
                    error
                )


# ============================================================
# 🔄 MARKET LOOP
# ============================================================

def market_loop(
    market,
    token,
    symbol_function
):

    symbols = []

    while True:

        try:

            # تحديث قائمة الأسهم
            new_symbols = symbol_function()

            if new_symbols:

                symbols = new_symbols

            print(
                f"💀 {market}: "
                f"{len(symbols)} symbols loaded"
            )

            scan_market(
                symbols,
                market,
                token
            )

        except Exception as error:

            print(
                f"{market} loop error:",
                error
            )

        time.sleep(SCAN_INTERVAL)


# ============================================================
# ❤️ HEARTBEAT
# ============================================================

def heartbeat():

    while True:

        print(
            "💀🚀 AI PRO MAX يعمل "
            "24/7 | "
            + datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

        time.sleep(300)


# ============================================================
# 🚀 START
# ============================================================

def main():

    print("=" * 60)
    print("💀🚀 AI PRO MAX")
    print("🇸🇦 TASI 375")
    print("🇺🇸 US MARKET")
    print("🪙 CRYPTO MARKET")
    print("=" * 60)

    if not TWELVEDATA_API_KEY:

        print(
            "❌ TWELVEDATA_API_KEY غير موجود"
        )

        return

    if not CHAT_ID:

        print(
            "❌ CHAT_ID غير موجود"
        )

        return

    print(
        "🟢 TWELVEDATA_API_KEY: OK"
    )

    print(
        "🟢 CHAT_ID: OK"
    )

    print(
        "🇸🇦 TASI TOKEN:",
        "OK" if TASI_TOKEN else "MISSING"
    )

    print(
        "🇺🇸 US TOKEN:",
        "OK" if US_TOKEN else "MISSING"
    )

    print(
        "🪙 CRYPTO TOKEN:",
        "OK" if CRYPTO_TOKEN else "MISSING"
    )

    threading.Thread(
        target=heartbeat,
        daemon=True
    ).start()

    # ========================================================
    # 🇸🇦 TASI
    # ========================================================

    threading.Thread(
        target=market_loop,
        args=(
            "TASI",
            TASI_TOKEN,
            get_tasi_symbols
        ),
        daemon=True
    ).start()

    # ========================================================
    # 🇺🇸 US
    # ========================================================

    threading.Thread(
        target=market_loop,
        args=(
            "US",
            US_TOKEN,
            get_us_symbols
        ),
        daemon=True
    ).start()

    # ========================================================
    # 🪙 CRYPTO
    # ========================================================

    threading.Thread(
        target=market_loop,
        args=(
            "CRYPTO",
            CRYPTO_TOKEN,
            get_crypto_symbols
        ),
        daemon=True
    ).start()

    while True:

        time.sleep(60)


if __name__ == "__main__":
    main()