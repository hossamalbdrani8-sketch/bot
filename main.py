
# ============================================================
# 💀🚀 AI PRO MAX
# نظام فحص تلقائي للأسهم والعملات الرقمية
# المصدر: Twelve Data فقط
# الفحص: كل دقيقتين
# ============================================================

import os
import time
import requests

# ============================================================
# ⚙️ الإعدادات
# ============================================================

APP_NAME = "💀🚀 AI PRO MAX"

SCAN_INTERVAL = 120
API_TIMEOUT = 20

EMA_FAST = 8
EMA_MID = 21
EMA_SLOW = 50

RSI_LENGTH = 14
ATR_LENGTH = 14

# ============================================================
# 🔑 Twelve Data
# المتغير المطلوب في Railway:
# API
# ============================================================

TWELVE_API_KEY = os.getenv("API", "").strip()

# ============================================================
# 🤖 Telegram
# ============================================================

US_BOT_TOKEN = os.getenv("US_BOT_TOKEN", "").strip()
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN", "").strip()
GENERAL_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# ============================================================
# 🇺🇸 الأسهم الأمريكية
# ============================================================

US_SYMBOLS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "TSLA",
    "GOOGL",
    "GOOG",
    "AMD",
    "INTC",
    "NFLX",
    "AVGO",
    "QCOM",
    "MU",
    "PLTR",
    "MSTR",
    "COIN",
    "SOFI",
    "NIO",
    "RIVN",
    "LCID",
    "PYPL",
    "UBER",
    "SNOW",
    "SHOP",
    "ARM",
    "SMCI",
    "CRWD",
    "MARA",
    "RIOT",
    "TQQQ",
    "SQQQ",
    "SPY",
    "QQQ",
    "IWM",
    "XLF",
    "XLE",
    "GLD",
    "SLV",
    "BA"
]

# ============================================================
# 🪙 العملات الرقمية
# ============================================================

CRYPTO_SYMBOLS = [
    "BTC/USD",
    "ETH/USD",
    "BNB/USD",
    "SOL/USD",
    "XRP/USD",
    "ADA/USD",
    "DOGE/USD",
    "AVAX/USD",
    "DOT/USD",
    "LINK/USD",
    "TRX/USD",
    "LTC/USD",
    "BCH/USD",
    "UNI/USD",
    "ATOM/USD",
    "ETC/USD",
    "FIL/USD",
    "NEAR/USD",
    "APT/USD",
    "ARB/USD"
]

# ============================================================
# 🛡️ مدير Credits
# ============================================================

class CreditManager:

    def __init__(self):

        self.window_start = time.monotonic()

        self.used = 0

        self.limit = 8

    def wait(self):

        now = time.monotonic()

        elapsed = now - self.window_start

        if elapsed >= 60:

            self.window_start = now

            self.used = 0

        if self.used >= self.limit:

            wait_time = max(
                1,
                int(60 - elapsed) + 1
            )

            print(
                f"ℹ️ مدير Credits: انتظار {wait_time} ثانية"
            )

            time.sleep(wait_time)

            self.window_start = time.monotonic()

            self.used = 0

    def consume(self):

        self.used += 1


credits = CreditManager()

# ============================================================
# 📡 Twelve Data
# ============================================================

def get_market_data(symbol):

    if not TWELVE_API_KEY:

        print(
            "ℹ️ Twelve Data: متغير API غير موجود"
        )

        return None, "AUTH"

    credits.wait()

    try:

        response = requests.get(

            "https://api.twelvedata.com/time_series",

            params={

                "symbol": symbol,

                "interval": "1min",

                "outputsize": 100,

                "apikey": TWELVE_API_KEY

            },

            timeout=API_TIMEOUT

        )

        credits.consume()

    except requests.RequestException:

        print(
            "ℹ️ Twelve Data: مشكلة اتصال"
        )

        return None, "NETWORK"

    try:

        data = response.json()

    except ValueError:

        print(
            "ℹ️ Twelve Data: استجابة غير صالحة"
        )

        return None, "ERROR"

    message = str(
        data.get("message", "")
    ).lower()

    # ========================================================
    # 🔐 فحص المفتاح
    # ========================================================

    if response.status_code in (401, 403):

        print(
            "ℹ️ Twelve Data: مفتاح API غير صالح"
        )

        return None, "AUTH"

    if (
        "apikey" in message
        and (
            "incorrect" in message
            or "invalid" in message
            or "not specified" in message
        )
    ):

        print(
            "ℹ️ Twelve Data: مفتاح API غير صالح"
        )

        return None, "AUTH"

    # ========================================================
    # ⏱️ Rate Limit
    # ========================================================

    if response.status_code == 429:

        print(
            "ℹ️ Twelve Data: تم الوصول إلى حد الطلبات"
        )

        return None, "RATE"

    # ========================================================
    # أخطاء API
    # ========================================================

    if data.get("status") == "error":

        print(
            "ℹ️ Twelve Data:",
            data.get("message", "خطأ")
        )

        return None, "ERROR"

    values = data.get("values")

    if not isinstance(values, list):

        print(
            "ℹ️ Twelve Data: لا توجد بيانات"
        )

        return None, "NO_DATA"

    return values, "OK"

# ============================================================
# 📊 EMA
# ============================================================

def calculate_ema(values, period):

    if len(values) < period:

        return None

    multiplier = 2 / (period + 1)

    result = sum(
        values[:period]
    ) / period

    for value in values[period:]:

        result = (
            value * multiplier
            + result * (1 - multiplier)
        )

    return result

# ============================================================
# 📈 RSI
# ============================================================

def calculate_rsi(values, period=14):

    if len(values) <= period:

        return None

    gains = []

    losses = []

    for i in range(1, len(values)):

        change = (
            values[i]
            - values[i - 1]
        )

        gains.append(
            max(change, 0)
        )

        losses.append(
            max(-change, 0)
        )

    average_gain = (
        sum(gains[:period])
        / period
    )

    average_loss = (
        sum(losses[:period])
        / period
    )

    for i in range(
        period,
        len(gains)
    ):

        average_gain = (
            (
                average_gain
                * (period - 1)
            )
            + gains[i]
        ) / period

        average_loss = (
            (
                average_loss
                * (period - 1)
            )
            + losses[i]
        ) / period

    if average_loss == 0:

        return 100.0

    rs = (
        average_gain
        / average_loss
    )

    return (
        100
        - (100 / (1 + rs))
    )

# ============================================================
# 📐 ATR
# ============================================================

def calculate_atr(candles, period=14):

    if len(candles) <= period:

        return None

    true_ranges = []

    for i in range(
        1,
        len(candles)
    ):

        high = candles[i]["high"]

        low = candles[i]["low"]

        previous_close = (
            candles[i - 1]["close"]
        )

        tr = max(

            high - low,

            abs(
                high
                - previous_close
            ),

            abs(
                low
                - previous_close
            )

        )

        true_ranges.append(tr)

    if len(true_ranges) < period:

        return None

    result = (
        sum(true_ranges[:period])
        / period
    )

    for tr in true_ranges[period:]:

        result = (
            (
                result
                * (period - 1)
            )
            + tr
        ) / period

    return result

# ============================================================
# 🕯️ تحويل الشموع
# ============================================================

def convert_candles(values):

    candles = []

    for item in reversed(values):

        try:

            candles.append({

                "open":
                    float(item["open"]),

                "high":
                    float(item["high"]),

                "low":
                    float(item["low"]),

                "close":
                    float(item["close"]),

                "volume":
                    float(
                        item.get(
                            "volume",
                            0
                        ) or 0
                    )

            })

        except Exception:

            continue

    return candles

# ============================================================
# 🧠 المحرك الذكي
# ============================================================

def analyze_market(candles):

    if len(candles) < 60:

        return None

    closes = [
        candle["close"]
        for candle in candles
    ]

    ema8 = calculate_ema(
        closes,
        EMA_FAST
    )

    ema21 = calculate_ema(
        closes,
        EMA_MID
    )

    ema50 = calculate_ema(
        closes,
        EMA_SLOW
    )

    rsi = calculate_rsi(
        closes,
        RSI_LENGTH
    )

    atr = calculate_atr(
        candles,
        ATR_LENGTH
    )

    if any(
        value is None
        for value in (
            ema8,
            ema21,
            ema50,
            rsi,
            atr
        )
    ):

        return None

    current_price = closes[-1]

    previous_price = closes[-2]

    change = (

        (
            current_price
            - previous_price
        )
        / previous_price
        * 100

    ) if previous_price else 0

    # ========================================================
    # الدعم والمقاومة
    # ========================================================

    recent = candles[-30:]

    support = min(
        candle["low"]
        for candle in recent
    )

    resistance = max(
        candle["high"]
        for candle in recent
    )

    # ========================================================
    # قوة الحجم
    # ========================================================

    volumes = [

        candle["volume"]

        for candle
        in candles[-21:]

    ]

    average_volume = (

        sum(volumes[:-1])
        / max(
            1,
            len(volumes) - 1
        )

    )

    current_volume = volumes[-1]

    if average_volume > 0:

        volume_strength = max(

            0,

            min(

                100,

                50
                + (
                    (
                        current_volume
                        / average_volume
                    )
                    - 1
                )
                * 25

            )

        )

    else:

        volume_strength = 50

    # ========================================================
    # قوة الشراء والبيع
    # ========================================================

    buy_power = 0

    sell_power = 0

    if ema8 > ema21:

        buy_power += 20

    else:

        sell_power += 20

    if ema21 > ema50:

        buy_power += 20

    else:

        sell_power += 20

    if current_price > ema8:

        buy_power += 15

    else:

        sell_power += 15

    if current_price > ema50:

        buy_power += 15

    else:

        sell_power += 15

    if rsi >= 50:

        buy_power += 15

    else:

        sell_power += 15

    if volume_strength >= 55:

        buy_power += 15

    elif volume_strength <= 45:

        sell_power += 15

    # ========================================================
    # الاتجاه
    # ========================================================

    if (

        ema8 > ema21
        and ema21 > ema50
        and current_price > ema50

    ):

        trend = "صاعد"

    elif (

        ema8 < ema21
        and ema21 < ema50
        and current_price < ema50

    ):

        trend = "هابط"

    else:

        trend = "محايد"

    # ========================================================
    # الإشارة
    # ========================================================

    if (

        buy_power >= 70
        and trend == "صاعد"
        and rsi < 80

    ):

        signal = "🟢⬆️ شراء قوي"

        targets = [

            current_price
            + (
                atr * multiplier
            )

            for multiplier
            in range(1, 9)

        ]

    elif (

        sell_power >= 70
        and trend == "هابط"
        and rsi > 20

    ):

        signal = "🔴⬇️ بيع قوي"

        targets = [

            current_price
            - (
                atr * multiplier
            )

            for multiplier
            in range(1, 9)

        ]

    else:

        signal = "محايد"

        targets = []

    return {

        "price":
            current_price,

        "change":
            change,

        "ema8":
            ema8,

        "ema21":
            ema21,

        "ema50":
            ema50,

        "rsi":
            rsi,

        "atr":
            atr,

        "support":
            support,

        "resistance":
            resistance,

        "volume_strength":
            volume_strength,

        "buy_power":
            buy_power,

        "sell_power":
            sell_power,

        "trend":
            trend,

        "signal":
            signal,

        "targets":
            targets

    }

# ============================================================
# 🔢 تنسيق الأرقام
# ============================================================

def fmt(value):

    if value is None:

        return "--"

    if abs(value) >= 100:

        return f"{value:.2f}"

    if abs(value) >= 1:

        return f"{value:.3f}"

    return f"{value:.6f}"

# ============================================================
# 📱 رسالة Telegram
# ============================================================

def build_signal_message(
    market,
    symbol,
    analysis
):

    text = (

        "💀🚀 AI PRO MAX SIGNAL\n"
        "━━━━━━━━━━━━━━━━━━\n"

        f"🌐 السوق: {market}\n"

        f"📌 الرمز: {symbol}\n"

        f"{analysis['signal']}\n"

        f"💰 السعر: "
        f"{fmt(analysis['price'])}\n"

        f"📈 التغير: "
        f"{analysis['change']:+.2f}%\n"

        f"💪 قوة الشراء: "
        f"{analysis['buy_power']}%\n"

        f"💪 قوة البيع: "
        f"{analysis['sell_power']}%\n"

        f"📊 قوة الحجم: "
        f"{analysis['volume_strength']:.1f}%\n"

        "\n"

        f"EMA 8: "
        f"{fmt(analysis['ema8'])}\n"

        f"EMA 21: "
        f"{fmt(analysis['ema21'])}\n"

        f"EMA 50: "
        f"{fmt(analysis['ema50'])}\n"

        f"RSI 14: "
        f"{analysis['rsi']:.2f}\n"

        f"ATR 14: "
        f"{fmt(analysis['atr'])}\n"

        f"🟦 الدعم: "
        f"{fmt(analysis['support'])}\n"

        f"🟥 المقاومة: "
        f"{fmt(analysis['resistance'])}\n"

        f"📈 الاتجاه: "
        f"{analysis['trend']}\n"

    )

    if analysis["targets"]:

        text += "\n🎯 أهداف ATR\n"

        for i, target in enumerate(
            analysis["targets"],
            1
        ):

            text += (
                f"TP{i}: "
                f"{fmt(target)}\n"
            )

    text += (

        "━━━━━━━━━━━━━━━━━━\n"

        "🤖 الفحص تلقائي 24/7\n"

        "📡 مصدر البيانات: Twelve Data"

    )

    return text

# ============================================================
# 📲 إرسال Telegram
# ============================================================

def send_telegram(
    token,
    text
):

    if not token:

        return

    if not CHAT_ID:

        print(
            "ℹ️ Telegram: TELEGRAM_CHAT_ID غير موجود"
        )

        return

    try:

        response = requests.post(

            f"https://api.telegram.org/bot{token}/sendMessage",

            json={

                "chat_id": CHAT_ID,

                "text": text,

                "disable_web_page_preview": True

            },

            timeout=API_TIMEOUT

        )

        if not response.ok:

            print(
                "ℹ️ Telegram: تعذر إرسال الرسالة"
            )

    except requests.RequestException:

        print(
            "ℹ️ Telegram: مشكلة اتصال"
        )

# ============================================================
# 🧠 منع تكرار الإشارة
# ============================================================

last_signals = {}

# ============================================================
# 🔎 فحص سهم واحد فقط
# ============================================================

def scan_symbol(
    symbol,
    market,
    bot_token
):

    print(
        f"🔎 فحص {market}: {symbol}"
    )

    values, status = get_market_data(
        symbol
    )

    if status == "AUTH":

        return "STOP"

    if status != "OK":

        return status

    candles = convert_candles(
        values
    )

    analysis = analyze_market(
        candles
    )

    if not analysis:

        return "NO_ANALYSIS"

    if analysis["signal"] == "محايد":

        return "NEUTRAL"

    key = (
        f"{market}:{symbol}"
    )

    previous = last_signals.get(
        key
    )

    if previous == analysis["signal"]:

        return "DUPLICATE"

    last_signals[key] = (
        analysis["signal"]
    )

    send_telegram(

        bot_token
        or GENERAL_BOT_TOKEN,

        build_signal_message(
            market,
            symbol,
            analysis
        )

    )

    return "SIGNAL"

# ============================================================
# 🚀 التشغيل الرئيسي
# ============================================================

def main():

    print(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    print(
        "💀🚀 AI PRO MAX"
    )

    print(
        "🟢 النظام يعمل 24/7"
    )

    print(
        "📡 Twelve Data"
    )

    print(
        "🛡️ مدير Credits مفعل"
    )

    print(
        f"🇺🇸 US: "
        f"{len(US_SYMBOLS)}"
    )

    print(
        f"🪙 CRYPTO: "
        f"{len(CRYPTO_SYMBOLS)}"
    )

    print(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    if not TWELVE_API_KEY:

        print(
            "ℹ️ متغير API غير موجود في Railway"
        )

        return

    us_index = 0

    crypto_index = 0

    market = "US"

    while True:

        cycle_start = time.monotonic()

        try:

            if market == "US":

                symbol = (
                    US_SYMBOLS[
                        us_index
                    ]
                )

                us_index = (
                    us_index + 1
                ) % len(US_SYMBOLS)

                result = scan_symbol(

                    symbol,

                    "🇺🇸 السوق الأمريكي",

                    US_BOT_TOKEN

                )

                market = "CRYPTO"

            else:

                symbol = (
                    CRYPTO_SYMBOLS[
                        crypto_index
                    ]
                )

                crypto_index = (
                    crypto_index + 1
                ) % len(
                    CRYPTO_SYMBOLS
                )

                result = scan_symbol(

                    symbol,

                    "🪙 العملات الرقمية",

                    CRYPTO_BOT_TOKEN

                )

                market = "US"

            if result == "STOP":

                print(
                    "ℹ️ تم إيقاف النظام لحماية Credits بسبب مشكلة مفتاح API."
                )

                return

        except Exception as error:

            print(
                "ℹ️ خطأ داخلي تمت معالجته:",
                type(error).__name__
            )

        elapsed = (
            time.monotonic()
            - cycle_start
        )

        wait_time = max(
            1,
            SCAN_INTERVAL - elapsed
        )

        time.sleep(
            wait_time
        )

# ============================================================
# ▶️ START
# ============================================================

if __name__ == "__main__":

    main()