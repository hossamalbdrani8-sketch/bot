
# ============================================================
# 💀🚀 AI PRO MAX
# Autonomous Market Scanner
# Built from zero
# Data: Twelve Data
# Runtime: Railway / Python 3
# ============================================================

import os
import time
import math
import requests
from datetime import datetime, timezone


# ============================================================
# ⚙️ الإعدادات
# ============================================================

APP_NAME = "💀🚀 AI PRO MAX"

SCAN_INTERVAL = 120          # فحص كل دقيقتين
API_TIMEOUT = 20
MIN_US_PRICE = 0.20

EMA_FAST = 8
EMA_MID = 21
EMA_SLOW = 50

RSI_LENGTH = 14
ATR_LENGTH = 14

ATR_TARGETS = [1, 2, 3, 4, 5, 6, 7, 8]

# عدد الرموز المبدئي في الدورة
US_SYMBOLS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META",
    "TSLA", "GOOGL", "GOOG", "AMD", "INTC",
    "NFLX", "AVGO", "QCOM", "MU", "PLTR",
    "MSTR", "COIN", "SOFI", "NIO", "RIVN",
    "LCID", "PYPL", "UBER", "SNOW", "SHOP",
    "ARM", "SMCI", "CRWD", "MARA", "RIOT",
    "TQQQ", "SQQQ", "SPY", "QQQ", "IWM",
    "XLF", "XLE", "GLD", "SLV", "BA"
]

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
# 🔐 قراءة المتغيرات
# ============================================================

def get_env(*names):
    for name in names:
        value = os.environ.get(name)
        if value:
            return value.strip()
    return ""


# Twelve Data
TWELVE_DATA_API_KEY = get_env(
    "TWELVE_DATA_API_KEY",
    "API",
    "TWELVE_API_KEY"
)

# السوق الأمريكي
US_API_TOKEN = get_env(
    "US_TOKEN",
    "US_API_KEY",
    "US_TWELVE_TOKEN",
    "TWELVE_DATA_API_KEY",
    "API"
)

# العملات الرقمية
CRYPTO_API_TOKEN = get_env(
    "CRYPTO_TOKEN",
    "CRYPTO_API_KEY",
    "CRYPTO_TWELVE_TOKEN",
    "TWELVE_DATA_API_KEY",
    "API"
)

# تاسي
TASI_API_TOKEN = get_env(
    "TASI_TOKEN",
    "TASI_API_KEY",
    "TASI_TWELVE_TOKEN",
    "TWELVE_DATA_API_KEY",
    "API"
)


# ============================================================
# 🤖 Telegram
# ============================================================
#
# الكود يبحث عن عدة أسماء شائعة للمتغيرات.
# لا نضع أي Token داخل الكود.
#

US_BOT_TOKEN = get_env(
    "US_BOT_TOKEN",
    "US_TELEGRAM_TOKEN",
    "TELEGRAM_US_TOKEN",
    "BOT_TOKEN_US"
)

CRYPTO_BOT_TOKEN = get_env(
    "CRYPTO_BOT_TOKEN",
    "CRYPTO_TELEGRAM_TOKEN",
    "TELEGRAM_CRYPTO_TOKEN",
    "BOT_TOKEN_CRYPTO"
)

TASI_BOT_TOKEN = get_env(
    "TASI_BOT_TOKEN",
    "TASI_TELEGRAM_TOKEN",
    "TELEGRAM_TASI_TOKEN",
    "BOT_TOKEN_TASI"
)

# إذا كان هناك بوت عام
GENERAL_BOT_TOKEN = get_env(
    "TELEGRAM_BOT_TOKEN",
    "BOT_TOKEN"
)

TELEGRAM_CHAT_ID = get_env(
    "TELEGRAM_CHAT_ID",
    "CHAT_ID"
)


# ============================================================
# 📊 مدير Twelve Data Credits
# ============================================================

class CreditManager:

    def __init__(self):
        self.used = 0
        self.window_start = time.time()
        self.minute_limit = 8

    def reset_if_needed(self):
        elapsed = time.time() - self.window_start

        if elapsed >= 60:
            self.used = 0
            self.window_start = time.time()

    def can_request(self):
        self.reset_if_needed()

        return self.used < self.minute_limit

    def wait_for_slot(self):
        self.reset_if_needed()

        if self.used >= self.minute_limit:
            remaining = 60 - (time.time() - self.window_start)

            if remaining > 0:
                print(
                    f"ℹ️ مدير Credits: انتظار {int(remaining)} ثانية"
                )
                time.sleep(remaining + 1)

            self.reset_if_needed()

    def register(self):
        self.used += 1

    def status(self):
        self.reset_if_needed()

        return (
            f"Credits داخل الدقيقة: "
            f"{self.used}/{self.minute_limit}"
        )


credits = CreditManager()


# ============================================================
# 🌐 Twelve Data Client
# ============================================================

class TwelveData:

    BASE_URL = "https://api.twelvedata.com"

    def __init__(self, api_key):
        self.api_key = api_key

    def request(self, endpoint, params=None):

        if not self.api_key:
            return None

        credits.wait_for_slot()

        params = params or {}
        params["apikey"] = self.api_key

        try:

            response = requests.get(
                self.BASE_URL + endpoint,
                params=params,
                timeout=API_TIMEOUT
            )

            credits.register()

            status_code = response.status_code

            try:
                data = response.json()
            except Exception:
                data = {}

            # ------------------------------------------------
            # التعامل الصحيح مع Rate Limit
            # ------------------------------------------------

            if status_code == 429:

                print(
                    "ℹ️ Twelve Data: تم الوصول إلى حد الطلبات المؤقت"
                )

                return None

            message = str(
                data.get("message", "")
            ).lower()

            # لا نعتبر كلمة credits وحدها Rate Limit
            rate_words = [
                "rate limit",
                "too many requests",
                "per minute",
                "limit per minute",
                "maximum requests",
                "request limit"
            ]

            if any(word in message for word in rate_words):

                print(
                    "ℹ️ Twelve Data: حد الطلبات"
                )

                return None

            if data.get("status") == "error":

                print(
                    "ℹ️ Twelve Data: "
                    + str(data.get("message", "خطأ غير معروف"))
                )

                return None

            print(
                f"📊 {credits.status()}"
            )

            return data

        except requests.RequestException as exc:

            print(
                f"ℹ️ اتصال Twelve Data: {type(exc).__name__}"
            )

            return None


# ============================================================
# 📈 الحسابات الفنية
# ============================================================

def ema(values, period):

    if len(values) < period:
        return None

    multiplier = 2 / (period + 1)

    current = sum(
        values[:period]
    ) / period

    for price in values[period:]:
        current = (
            (price - current) * multiplier
        ) + current

    return current


def rsi(values, period=14):

    if len(values) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(1, len(values)):
        change = values[i] - values[i - 1]

        if change >= 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    avg_gain = sum(
        gains[:period]
    ) / period

    avg_loss = sum(
        losses[:period]
    ) / period

    for i in range(period, len(gains)):

        avg_gain = (
            (avg_gain * (period - 1))
            + gains[i]
        ) / period

        avg_loss = (
            (avg_loss * (period - 1))
            + losses[i]
        ) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def atr(candles, period=14):

    if len(candles) < period + 1:
        return None

    true_ranges = []

    for i in range(1, len(candles)):

        high = candles[i]["high"]
        low = candles[i]["low"]
        previous_close = candles[i - 1]["close"]

        tr = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close)
        )

        true_ranges.append(tr)

    if len(true_ranges) < period:
        return None

    value = sum(
        true_ranges[:period]
    ) / period

    for tr in true_ranges[period:]:

        value = (
            (value * (period - 1))
            + tr
        ) / period

    return value


# ============================================================
# 📉 تحليل الدعم والمقاومة
# ============================================================

def support_resistance(candles, lookback=30):

    if not candles:
        return None, None

    recent = candles[-lookback:]

    lows = [
        x["low"]
        for x in recent
    ]

    highs = [
        x["high"]
        for x in recent
    ]

    support = min(lows)
    resistance = max(highs)

    return support, resistance


# ============================================================
# 📊 قوة الحجم
# ============================================================

def volume_strength(candles):

    if len(candles) < 20:
        return 50.0

    volumes = [
        x["volume"]
        for x in candles[-20:]
    ]

    current = volumes[-1]

    average = sum(
        volumes[:-1]
    ) / max(len(volumes[:-1]), 1)

    if average <= 0:
        return 50.0

    ratio = current / average

    strength = 50 + ((ratio - 1) * 25)

    return max(
        0,
        min(100, strength)
    )


# ============================================================
# 🧠 محرك الإشارة
# ============================================================

def analyze(candles):

    if len(candles) < 60:
        return None

    closes = [
        x["close"]
        for x in candles
    ]

    current_price = closes[-1]

    ema8 = ema(
        closes,
        EMA_FAST
    )

    ema21 = ema(
        closes,
        EMA_MID
    )

    ema50 = ema(
        closes,
        EMA_SLOW
    )

    rsi14 = rsi(
        closes,
        RSI_LENGTH
    )

    atr14 = atr(
        candles,
        ATR_LENGTH
    )

    support, resistance = support_resistance(
        candles
    )

    vol_strength = volume_strength(
        candles
    )

    if any(
        x is None
        for x in [
            ema8,
            ema21,
            ema50,
            rsi14,
            atr14
        ]
    ):
        return None

    # --------------------------------------------------------
    # قوة الشراء والبيع
    # --------------------------------------------------------

    buy_score = 0
    sell_score = 0

    if ema8 > ema21:
        buy_score += 20
    else:
        sell_score += 20

    if ema21 > ema50:
        buy_score += 20
    else:
        sell_score += 20

    if current_price > ema8:
        buy_score += 15
    else:
        sell_score += 15

    if current_price > ema50:
        buy_score += 15
    else:
        sell_score += 15

    if rsi14 >= 50:
        buy_score += 15
    else:
        sell_score += 15

    if vol_strength >= 55:
        buy_score += 15

    elif vol_strength <= 45:
        sell_score += 15

    buy_score = max(
        0,
        min(100, buy_score)
    )

    sell_score = max(
        0,
        min(100, sell_score)
    )

    # --------------------------------------------------------
    # الاتجاه
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # القرار
    # --------------------------------------------------------

    if (
        buy_score >= 70
        and trend == "صاعد"
        and rsi14 < 80
    ):

        signal = "🟢⬆️ شراء قوي"

    elif (
        sell_score >= 70
        and trend == "هابط"
        and rsi14 > 20
    ):

        signal = "🔴⬇️ بيع قوي"

    else:

        signal = "محايد"

    # --------------------------------------------------------
    # أهداف ATR
    # --------------------------------------------------------

    targets = []

    if signal.startswith("🟢"):

        for multiplier in ATR_TARGETS:

            targets.append(
                current_price
                + (atr14 * multiplier)
            )

    elif signal.startswith("🔴"):

        for multiplier in ATR_TARGETS:

            targets.append(
                current_price
                - (atr14 * multiplier)
            )

    else:

        targets = [
            None
            for _ in ATR_TARGETS
        ]

    return {
        "price": current_price,
        "ema8": ema8,
        "ema21": ema21,
        "ema50": ema50,
        "rsi": rsi14,
        "atr": atr14,
        "support": support,
        "resistance": resistance,
        "volume_strength": vol_strength,
        "buy_power": buy_score,
        "sell_power": sell_score,
        "trend": trend,
        "signal": signal,
        "targets": targets
    }


# ============================================================
# 🕯️ تحويل بيانات Twelve Data
# ============================================================

def parse_candles(data):

    if not data:
        return []

    values = data.get("values")

    if not values:
        return []

    candles = []

    for item in reversed(values):

        try:

            candles.append({
                "open": float(item["open"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "close": float(item["close"]),
                "volume": float(
                    item.get("volume", 0) or 0
                )
            })

        except Exception:
            continue

    return candles


# ============================================================
# 📡 جلب الشموع
# ============================================================

def get_history(client, symbol):

    data = client.request(
        "/time_series",
        {
            "symbol": symbol,
            "interval": "1min",
            "outputsize": 100
        }
    )

    return parse_candles(data)


# ============================================================
# 💬 Telegram
# ============================================================

def telegram_send(token, chat_id, text):

    if not token or not chat_id:
        return False

    url = (
        "https://api.telegram.org/bot"
        + token
        + "/sendMessage"
    )

    try:

        response = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": True
            },
            timeout=API_TIMEOUT
        )

        if response.ok:
            return True

        print(
            "ℹ️ Telegram: تعذر إرسال الرسالة"
        )

        return False

    except requests.RequestException:

        print(
            "ℹ️ Telegram: مشكلة اتصال"
        )

        return False


# ============================================================
# 🧾 تنسيق الرقم
# ============================================================

def price(value):

    if value is None:
        return "--"

    if value >= 100:
        return f"{value:.2f}"

    if value >= 1:
        return f"{value:.3f}"

    return f"{value:.5f}"


def pct(value):

    return f"{value:.1f}%"


# ============================================================
# 📩 بناء رسالة الإشارة
# ============================================================

def build_signal_message(
    market,
    symbol,
    analysis
):

    p = analysis["price"]

    message = (
        "💀🚀 AI PRO MAX SIGNAL\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🌐 السوق: {market}\n"
        f"📌 الرمز: {symbol}\n"
        "\n"
        f"{analysis['signal']}\n"
        f"💰 السعر: {price(p)}\n"
        f"📊 قوة الإشارة: "
        f"{max(analysis['buy_power'], analysis['sell_power'])}%\n"
        "\n"
        "📈 قوة الشراء: "
        f"{analysis['buy_power']}%\n"
        "📉 قوة البيع: "
        f"{analysis['sell_power']}%\n"
        "📊 قوة الحجم: "
        f"{pct(analysis['volume_strength'])}\n"
        "\n"
        "📐 EMA 8: "
        f"{price(analysis['ema8'])}\n"
        "📐 EMA 21: "
        f"{price(analysis['ema21'])}\n"
        "📐 EMA 50: "
        f"{price(analysis['ema50'])}\n"
        "\n"
        "📊 RSI 14: "
        f"{analysis['rsi']:.2f}\n"
        "📏 ATR 14: "
        f"{price(analysis['atr'])}\n"
        "\n"
        "🟦 الدعم: "
        f"{price(analysis['support'])}\n"
        "🟥 المقاومة: "
        f"{price(analysis['resistance'])}\n"
        "📈 الاتجاه: "
        f"{analysis['trend']}\n"
        "\n"
        "🎯 أهداف ATR\n"
    )

    for i, target in enumerate(
        analysis["targets"],
        start=1
    ):

        if target is not None:

            message += (
                f"TP{i}: {price(target)}\n"
            )

    message += (
        "━━━━━━━━━━━━━━━━━━\n"
        "🤖 AI PRO MAX يعمل تلقائيًا 24/7\n"
        "📡 مصدر البيانات: Twelve Data"
    )

    return message


# ============================================================
# 🛡️ منع تكرار التنبيهات
# ============================================================

last_signals = {}


def should_send(
    market,
    symbol,
    signal
):

    if signal == "محايد":
        return False

    key = (
        market,
        symbol
    )

    previous = last_signals.get(key)

    if previous == signal:
        return False

    last_signals[key] = signal

    return True


# ============================================================
# 🇺🇸 فحص السوق الأمريكي
# ============================================================

def scan_us():

    if not US_API_TOKEN:
        print(
            "ℹ️ لم يتم العثور على مفتاح US"
        )
        return

    client = TwelveData(
        US_API_TOKEN
    )

    for symbol in US_SYMBOLS:

        print(
            f"🔎 فحص US: {symbol}"
        )

        candles = get_history(
            client,
            symbol
        )

        if not candles:
            continue

        analysis = analyze(
            candles
        )

        if not analysis:
            continue

        # السعر الأدنى
        if analysis["price"] < MIN_US_PRICE:
            continue

        signal = analysis["signal"]

        if not should_send(
            "US",
            symbol,
            signal
        ):
            continue

        text = build_signal_message(
            "🇺🇸 السوق الأمريكي",
            symbol,
            analysis
        )

        token = (
            US_BOT_TOKEN
            or GENERAL_BOT_TOKEN
        )

        if token and TELEGRAM_CHAT_ID:

            telegram_send(
                token,
                TELEGRAM_CHAT_ID,
                text
            )


# ============================================================
# 🪙 فحص العملات الرقمية
# ============================================================

def scan_crypto():

    if not CRYPTO_API_TOKEN:
        print(
            "ℹ️ لم يتم العثور على مفتاح Crypto"
        )
        return

    client = TwelveData(
        CRYPTO_API_TOKEN
    )

    for symbol in CRYPTO_SYMBOLS:

        print(
            f"🔎 فحص Crypto: {symbol}"
        )

        candles = get_history(
            client,
            symbol
        )

        if not candles:
            continue

        analysis = analyze(
            candles
        )

        if not analysis:
            continue

        signal = analysis["signal"]

        if not should_send(
            "CRYPTO",
            symbol,
            signal
        ):
            continue

        text = build_signal_message(
            "🪙 العملات الرقمية",
            symbol,
            analysis
        )

        token = (
            CRYPTO_BOT_TOKEN
            or GENERAL_BOT_TOKEN
        )

        if token and TELEGRAM_CHAT_ID:

            telegram_send(
                token,
                TELEGRAM_CHAT_ID,
                text
            )


# ============================================================
# 🇸🇦 حالة تاسي
# ============================================================

def tasi_status():

    print(
        "ℹ️ TASI: وحدة السوق السعودي موجودة "
        "لكن لا يتم اختلاق بيانات من مصدر غير متاح."
    )


# ============================================================
# 🚀 رسالة التشغيل
# ============================================================

def startup_message():

    return (
        "💀🚀 AI PRO MAX\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✅ البوت يعمل الآن\n"
        "🔄 الفحص تلقائي\n"
        "⏱️ دورة الفحص: كل دقيقتين\n"
        "\n"
        "🌐 الأسواق:\n"
        "🇸🇦 TASI\n"
        "🇺🇸 US\n"
        "🪙 CRYPTO\n"
        "\n"
        "🧠 المحرك الذكي:\n"
        "EMA 8\n"
        "EMA 21\n"
        "EMA 50\n"
        "RSI 14\n"
        "ATR 14\n"
        "دعم\n"
        "مقاومة\n"
        "قوة الحجم\n"
        "قوة الشراء\n"
        "قوة البيع\n"
        "8 أهداف ATR\n"
        "منع تكرار التنبيهات\n"
        "\n"
        "🤖 لا تحتاج إلى تشغيل الفحص يدويًا.\n"
        "📡 مصدر البيانات: Twelve Data"
    )


# ============================================================
# 🔁 الحلقة الرئيسية
# ============================================================

def main():

    print(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    print(
        APP_NAME
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
        f"🇺🇸 US: {len(US_SYMBOLS)}"
    )

    print(
        f"🪙 CRYPTO: {len(CRYPTO_SYMBOLS)}"
    )

    print(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    # رسالة تشغيل Telegram
    if GENERAL_BOT_TOKEN and TELEGRAM_CHAT_ID:

        telegram_send(
            GENERAL_BOT_TOKEN,
            TELEGRAM_CHAT_ID,
            startup_message()
        )

    # --------------------------------------------------------
    # التشغيل المستمر
    # --------------------------------------------------------

    market_turn = 0

    while True:

        cycle_start = time.time()

        try:

            # دورة واحدة فقط في كل دقيقتين
            #
            # نبدل بين US و Crypto
            # حتى لا يتم استهلاك Credits بسرعة.
            #

            if market_turn == 0:

                scan_us()

                market_turn = 1

            else:

                scan_crypto()

                market_turn = 0

            tasi_status()

        except Exception as exc:

            print(
                "ℹ️ خطأ داخلي تمت معالجته: "
                f"{type(exc).__name__}"
            )

        elapsed = time.time() - cycle_start

        sleep_time = max(
            1,
            SCAN_INTERVAL - elapsed
        )

        print(
            f"⏳ الدورة التالية بعد "
            f"{int(sleep_time)} ثانية"
        )

        time.sleep(
            sleep_time
        )


# ============================================================
# ▶️ START
# ============================================================

if __name__ == "__main__":

    main()