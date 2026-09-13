
# ============================================================
# 💀🚀 AI PRO MAX
# Autonomous Telegram Market Scanner
# US + CRYPTO
# Twelve Data
# ============================================================

import os
import json
import time
import asyncio
from datetime import datetime, timezone

import aiohttp
from aiohttp import web


# ============================================================
# ⚙️ CONFIGURATION
# ============================================================

TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()

TASI_TOKEN = os.getenv("TASI_TOKEN", "").strip()
US_TOKEN = os.getenv("US_TOKEN", "").strip()
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN", "").strip()

PORT = int(os.getenv("PORT", "8080"))

SCAN_SECONDS = 120

# Twelve Data Basic:
# 8 credits / minute
# 800 credits / day
#
# نحن نستخدم طلب بيانات واحد فقط لكل عملية فحص.
MAX_CREDITS_PER_MINUTE = 8

# لا نستهلك أكثر من طلب واحد في الدورة.
REQUESTS_PER_CYCLE = 1


# ============================================================
# 📊 SYMBOL LISTS
# ============================================================

# البداية تكون برموز معروفة.
# المدير يواصل من مكانه ولا يعيد الفحص من البداية.

US_SYMBOLS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "AVGO",
    "AMD",
    "INTC",
    "NFLX",
    "PLTR",
    "MU",
    "QCOM",
    "COST",
    "PEP",
    "KO",
    "JPM",
    "BAC",
    "WMT",
    "XOM",
    "CVX",
    "DIS",
    "NKE",
    "PYPL",
    "SOFI",
    "COIN",
    "MARA",
    "RIOT",
    "RIVN",
    "LCID",
    "F",
    "GM",
    "UBER",
    "ABNB",
    "SHOP",
    "SNOW",
    "ORCL",
    "CRM",
    "ADBE",
]

CRYPTO_SYMBOLS = [
    "BTC/USD",
    "ETH/USD",
    "SOL/USD",
    "XRP/USD",
    "DOGE/USD",
    "ADA/USD",
    "AVAX/USD",
    "LINK/USD",
    "DOT/USD",
    "LTC/USD",
    "BCH/USD",
    "UNI/USD",
    "ATOM/USD",
    "XLM/USD",
    "TRX/USD",
    "NEAR/USD",
    "FIL/USD",
    "ETC/USD",
    "AAVE/USD",
    "ALGO/USD",
]


# ============================================================
# 💾 STATE
# ============================================================

STATE_FILE = "scanner_state.json"

state = {
    "us_index": 0,
    "crypto_index": 0,
    "last_market": "CRYPTO",
    "telegram_chats": {
        "us": [],
        "crypto": [],
        "tasi": []
    },
    "last_alerts": {},
    "daily_date": "",
    "daily_requests": 0
}


def load_state():
    global state

    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)

            if isinstance(saved, dict):
                state.update(saved)

    except Exception as e:
        print(f"ℹ️ تعذر قراءة الحالة: {e}")


def save_state():
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(
                state,
                f,
                ensure_ascii=False,
                indent=2
            )
    except Exception as e:
        print(f"ℹ️ تعذر حفظ الحالة: {e}")


load_state()


# ============================================================
# 🧠 CREDIT MANAGER
# ============================================================

class CreditManager:

    def __init__(self):
        self.lock = asyncio.Lock()

        self.minute_start = time.monotonic()
        self.minute_requests = 0

        self.daily_date = datetime.now(
            timezone.utc
        ).strftime("%Y-%m-%d")

        self.daily_requests = int(
            state.get("daily_requests", 0)
        )

    async def wait_for_slot(self):

        async with self.lock:

            now = time.monotonic()

            # إعادة ضبط عداد الدقيقة
            if now - self.minute_start >= 60:
                self.minute_start = now
                self.minute_requests = 0

            # إذا وصلنا الحد، ننتظر حتى الدقيقة التالية
            if self.minute_requests >= MAX_CREDITS_PER_MINUTE:

                wait_time = 60 - (
                    now - self.minute_start
                )

                if wait_time > 0:
                    print(
                        f"ℹ️ Credits: انتظار {int(wait_time)} ثانية"
                    )

                    await asyncio.sleep(
                        wait_time + 1
                    )

                self.minute_start = time.monotonic()
                self.minute_requests = 0

            # اليوم الجديد UTC
            today = datetime.now(
                timezone.utc
            ).strftime("%Y-%m-%d")

            if today != self.daily_date:
                self.daily_date = today
                self.daily_requests = 0

            # حد Basic اليومي
            if self.daily_requests >= 790:
                print(
                    "ℹ️ Credits اليومية اقتربت من الحد"
                )
                return False

            self.minute_requests += 1
            self.daily_requests += 1

            state["daily_requests"] = self.daily_requests
            save_state()

            return True


credits = CreditManager()


# ============================================================
# 🌐 TWELVE DATA REQUEST
# ============================================================

async def twelve_time_series(
    session,
    symbol,
    interval="5min",
    outputsize=80
):

    allowed = await credits.wait_for_slot()

    if not allowed:
        return None

    url = "https://api.twelvedata.com/time_series"

    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": TWELVE_DATA_API_KEY,
    }

    try:

        async with session.get(
            url,
            params=params,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:

            data = await response.json(
                content_type=None
            )

            used = response.headers.get(
                "api-credits-used"
            )

            left = response.headers.get(
                "api-credits-left"
            )

            if used or left:
                print(
                    f"📊 Credits used={used or '?'} "
                    f"left={left or '?'}"
                )

            if response.status == 429:

                print(
                    "ℹ️ Twelve Data: الرصيد في الدقيقة ممتلئ"
                )

                # نعيد الطلب إلى المدير في الدورة القادمة
                credits.minute_requests = (
                    MAX_CREDITS_PER_MINUTE
                )

                return None

            if response.status != 200:

                print(
                    f"ℹ️ Twelve Data HTTP {response.status}"
                )

                return None

            if not isinstance(data, dict):
                return None

            if "status" in data:
                if data.get("status") == "error":

                    msg = data.get(
                        "message",
                        "خطأ غير معروف"
                    )

                    print(
                        f"ℹ️ Twelve Data: {msg}"
                    )

                    return None

            values = data.get("values")

            if not values:
                print(
                    f"ℹ️ لا توجد بيانات: {symbol}"
                )
                return None

            return values

    except asyncio.TimeoutError:

        print(
            f"ℹ️ انتهت مهلة البيانات: {symbol}"
        )

        return None

    except Exception as e:

        print(
            f"ℹ️ خطأ بيانات {symbol}: {e}"
        )

        return None


# ============================================================
# 📐 MATH FUNCTIONS
# ============================================================

def closes(values):

    result = []

    for x in reversed(values):

        try:
            result.append(
                float(x["close"])
            )
        except:
            pass

    return result


def highs(values):

    result = []

    for x in reversed(values):

        try:
            result.append(
                float(x["high"])
            )
        except:
            pass

    return result


def lows(values):

    result = []

    for x in reversed(values):

        try:
            result.append(
                float(x["low"])
            )
        except:
            pass

    return result


def volumes(values):

    result = []

    for x in reversed(values):

        try:
            result.append(
                float(x.get("volume", 0))
            )
        except:
            result.append(0)

    return result


def ema(data, period):

    if not data:
        return 0.0

    if len(data) < period:
        return sum(data) / len(data)

    multiplier = 2 / (period + 1)

    value = sum(
        data[:period]
    ) / period

    for price in data[period:]:

        value = (
            (price - value) * multiplier
        ) + value

    return value


def rsi(data, period=14):

    if len(data) < period + 1:
        return 50.0

    gains = []
    losses = []

    for i in range(1, len(data)):

        change = data[i] - data[i - 1]

        if change >= 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    avg_gain = (
        sum(gains[:period]) / period
    )

    avg_loss = (
        sum(losses[:period]) / period
    )

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

    return 100 - (
        100 / (1 + rs)
    )


def atr(values, period=14):

    if len(values) < period + 1:
        return 0.0

    trs = []

    previous_close = None

    for row in reversed(values):

        try:

            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])

            if previous_close is None:

                tr = high - low

            else:

                tr = max(
                    high - low,
                    abs(high - previous_close),
                    abs(low - previous_close)
                )

            trs.append(tr)

            previous_close = close

        except:
            continue

    if not trs:
        return 0.0

    return sum(
        trs[-period:]
    ) / min(
        period,
        len(trs)
    )


def average_volume(values, period=20):

    vols = volumes(values)

    valid = [
        x for x in vols
        if x > 0
    ]

    if not valid:
        return 0.0

    sample = valid[-period:]

    return sum(sample) / len(sample)


# ============================================================
# 🧠 MARKET ANALYZER
# ============================================================

def analyze(values):

    if len(values) < 30:
        return None

    c = closes(values)
    h = highs(values)
    l = lows(values)

    if not c:
        return None

    price = c[-1]

    ema8 = ema(c, 8)
    ema21 = ema(c, 21)
    ema50 = ema(c, 50)

    rsi14 = rsi(c, 14)

    atr14 = atr(values, 14)

    support = min(
        l[-20:]
    )

    resistance = max(
        h[-20:]
    )

    vols = volumes(values)

    current_volume = (
        vols[-1]
        if vols
        else 0
    )

    avg_vol = average_volume(
        values,
        20
    )

    if avg_vol > 0:
        volume_strength = (
            current_volume / avg_vol
        )
    else:
        volume_strength = 1.0

    # --------------------------------------------------------
    # Trend
    # --------------------------------------------------------

    bullish = (
        ema8 > ema21 > ema50
    )

    bearish = (
        ema8 < ema21 < ema50
    )

    if bullish:
        trend = "صاعد قوي"
    elif bearish:
        trend = "هابط قوي"
    elif ema8 > ema21:
        trend = "صاعد"
    elif ema8 < ema21:
        trend = "هابط"
    else:
        trend = "محايد"

    # --------------------------------------------------------
    # Buy / Sell Power
    # --------------------------------------------------------

    buy_power = 50.0

    if price > ema8:
        buy_power += 10

    if ema8 > ema21:
        buy_power += 10

    if ema21 > ema50:
        buy_power += 10

    if rsi14 > 50:
        buy_power += 10

    if volume_strength >= 1.5:
        buy_power += 10

    buy_power = min(
        100,
        max(0, buy_power)
    )

    sell_power = 100 - buy_power

    # --------------------------------------------------------
    # Signal strength
    # --------------------------------------------------------

    signal_strength = 50.0

    if bullish:
        signal_strength += 20

    if bearish:
        signal_strength += 20

    if rsi14 >= 55:
        signal_strength += 10

    if rsi14 <= 45:
        signal_strength += 10

    if volume_strength >= 1.5:
        signal_strength += 10

    signal_strength = min(
        100,
        max(0, signal_strength)
    )

    # --------------------------------------------------------
    # Signal
    # --------------------------------------------------------

    if (
        bullish
        and rsi14 >= 55
        and price >= ema8
    ):

        signal = "🟢⬆️ شراء قوي"

    elif (
        bearish
        and rsi14 <= 45
        and price <= ema8
    ):

        signal = "🔴⬇️ بيع قوي"

    else:

        signal = "محايد"

    # --------------------------------------------------------
    # ATR TARGETS
    # --------------------------------------------------------

    targets = []

    if atr14 > 0:

        if "شراء" in signal:

            for i in range(1, 9):

                targets.append(
                    price + (
                        atr14 * i
                    )
                )

        elif "بيع" in signal:

            for i in range(1, 9):

                targets.append(
                    price - (
                        atr14 * i
                    )
                )

    return {
        "price": price,
        "ema8": ema8,
        "ema21": ema21,
        "ema50": ema50,
        "rsi": rsi14,
        "atr": atr14,
        "support": support,
        "resistance": resistance,
        "volume_strength": volume_strength,
        "buy_power": buy_power,
        "sell_power": sell_power,
        "signal_strength": signal_strength,
        "signal": signal,
        "trend": trend,
        "targets": targets
    }


# ============================================================
# 💰 NUMBER FORMAT
# ============================================================

def fmt(value, digits=2):

    try:

        return f"{float(value):,.{digits}f}"

    except:
        return "-"


def fmt_volume(value):

    try:

        value = float(value)

        if value >= 1_000_000_000:
            return f"{value / 1_000_000_000:.2f}B"

        if value >= 1_000_000:
            return f"{value / 1_000_000:.2f}M"

        if value >= 1_000:
            return f"{value / 1_000:.2f}K"

        return f"{value:.0f}"

    except:
        return "-"


# ============================================================
# 📱 TELEGRAM
# ============================================================

async def telegram_send(
    session,
    token,
    chat_id,
    text
):

    if not token:
        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{token}/sendMessage"
    )

    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True
    }

    try:

        async with session.post(
            url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=20)
        ) as response:

            return response.status == 200

    except:

        return False


async def telegram_broadcast(
    session,
    market,
    text
):

    token = {
        "us": US_TOKEN,
        "crypto": CRYPTO_TOKEN,
        "tasi": TASI_TOKEN
    }.get(market, "")

    chats = state[
        "telegram_chats"
    ].get(market, [])

    if not token or not chats:
        return

    for chat_id in list(chats):

        ok = await telegram_send(
            session,
            token,
            chat_id,
            text
        )

        if not ok:

            print(
                f"ℹ️ تعذر إرسال Telegram: {chat_id}"
            )

        await asyncio.sleep(0.2)


# ============================================================
# 📨 SIGNAL MESSAGE
# ============================================================

def build_signal_message(
    market,
    symbol,
    analysis
):

    if market == "us":
        market_name = "🇺🇸 السوق الأمريكي"
    elif market == "crypto":
        market_name = "🪙 العملات الرقمية"
    else:
        market_name = "🇸🇦 السوق السعودي (TASI)"

    a = analysis

    lines = [
        "💀🚀 AI PRO MAX SIGNAL",
        "",
        market_name,
        f"📌 {symbol}",
        "",
        f"📈 السعر: {fmt(a['price'])}",
        f"🎯 الإشارة: {a['signal']}",
        f"💪 قوة الإشارة: {fmt(a['signal_strength'], 0)}/100",
        "",
        f"🟢 قوة الشراء: {fmt(a['buy_power'], 0)}%",
        f"🔴 قوة البيع: {fmt(a['sell_power'], 0)}%",
        f"📊 قوة الحجم: {fmt(a['volume_strength'], 2)}x",
        "",
        "🧠 المؤشرات",
        f"EMA 8: {fmt(a['ema8'])}",
        f"EMA 21: {fmt(a['ema21'])}",
        f"EMA 50: {fmt(a['ema50'])}",
        f"RSI 14: {fmt(a['rsi'], 1)}",
        f"ATR 14: {fmt(a['atr'])}",
        "",
        f"🟩 الدعم: {fmt(a['support'])}",
        f"🟥 المقاومة: {fmt(a['resistance'])}",
        f"📈 الاتجاه: {a['trend']}",
        "",
        "🎯 أهداف ATR"
    ]

    for i, target in enumerate(
        a["targets"],
        start=1
    ):

        lines.append(
            f"TP{i}: {fmt(target)}"
        )

    lines.extend([
        "",
        "📡 Twelve Data",
        "🤖 الفحص تلقائي"
    ])

    return "\n".join(lines)


# ============================================================
# 🔔 ALERT FILTER
# ============================================================

def should_alert(
    market,
    symbol,
    analysis
):

    signal = analysis["signal"]

    if signal == "محايد":
        return False

    key = f"{market}:{symbol}"

    now = time.time()

    previous = state[
        "last_alerts"
    ].get(key)

    # منع تكرار الإشارة لمدة 30 دقيقة
    if previous:

        if (
            now - previous < 1800
        ):
            return False

    state[
        "last_alerts"
    ][key] = now

    save_state()

    return True


# ============================================================
# 🔎 SCAN ONE SYMBOL
# ============================================================

async def scan_symbol(
    session,
    market,
    symbol
):

    print(
        f"🔎 فحص {market.upper()}: {symbol}"
    )

    values = await twelve_time_series(
        session,
        symbol
    )

    if not values:
        return

    result = analyze(values)

    if not result:
        print(
            f"ℹ️ بيانات غير كافية: {symbol}"
        )
        return

    signal = result["signal"]

    print(
        f"📊 {symbol} | "
        f"{signal} | "
        f"RSI={result['rsi']:.1f} | "
        f"ATR={result['atr']:.4f}"
    )

    if should_alert(
        market,
        symbol,
        result
    ):

        message = build_signal_message(
            market,
            symbol,
            result
        )

        await telegram_broadcast(
            session,
            market,
            message
        )

        print(
            f"📨 تم إرسال إشارة: {symbol}"
        )


# ============================================================
# 🔄 ROTATION ENGINE
# ============================================================

def next_symbol(market):

    if market == "us":

        if not US_SYMBOLS:
            return None

        index = int(
            state.get("us_index", 0)
        )

        symbol = US_SYMBOLS[
            index % len(US_SYMBOLS)
        ]

        state["us_index"] = (
            index + 1
        )

        return symbol

    if market == "crypto":

        if not CRYPTO_SYMBOLS:
            return None

        index = int(
            state.get("crypto_index", 0)
        )

        symbol = CRYPTO_SYMBOLS[
            index % len(CRYPTO_SYMBOLS)
        ]

        state["crypto_index"] = (
            index + 1
        )

        return symbol

    return None


def next_market():

    last = state.get(
        "last_market",
        "CRYPTO"
    )

    if last == "CRYPTO":
        market = "US"
    else:
        market = "CRYPTO"

    state["last_market"] = market

    save_state()

    return market.lower()


# ============================================================
# 🤖 STARTUP MESSAGE
# ============================================================

async def send_startup_messages(
    session
):

    us_text = """💀🚀 AI PRO MAX

✅ البوت يعمل الآن
🔄 الفحص تلقائي
⏱️ الفحص كل دقيقتين

📊 السوق: الولايات المتحدة

🧠 المحرك الذكي:
• EMA 8
• EMA 21
• EMA 50
• RSI 14
• ATR 14
• دعم
• مقاومة
• قوة الحجم
• قوة الشراء
• قوة البيع
• 8 أهداف ATR
• منع تكرار التنبيهات

🟢⬆️ شراء قوي
🔴⬇️ بيع قوي

🤖 لا تحتاج إلى تشغيل الفحص يدويًا.

📡 مصدر البيانات:
Twelve Data فقط"""

    crypto_text = """💀🚀 AI PRO MAX

✅ البوت يعمل الآن
🔄 الفحص تلقائي
⏱️ الفحص كل دقيقتين

📊 السوق: العملات الرقمية

🧠 المحرك الذكي:
• EMA 8
• EMA 21
• EMA 50
• RSI 14
• ATR 14
• دعم
• مقاومة
• قوة الحجم
• قوة الشراء
• قوة البيع
• 8 أهداف ATR
• منع تكرار التنبيهات

🟢⬆️ شراء قوي
🔴⬇️ بيع قوي

🤖 لا تحتاج إلى تشغيل الفحص يدويًا.

📡 مصدر البيانات:
Twelve Data فقط"""

    tasi_text = """💀🚀 AI PRO MAX

✅ بوت TASI جاهز
🔄 الفحص تلقائي
⏱️ الفحص كل دقيقتين

📊 السوق: TASI

🧠 المحرك الذكي:
• EMA 8
• EMA 21
• EMA 50
• RSI 14
• ATR 14
• دعم
• مقاومة
• قوة الحجم
• قوة الشراء
• قوة البيع
• 8 أهداف ATR
• منع تكرار التنبيهات

📡 مصدر البيانات:
Twelve Data"""

    await telegram_broadcast(
        session,
        "us",
        us_text
    )

    await telegram_broadcast(
        session,
        "crypto",
        crypto_text
    )

    await telegram_broadcast(
        session,
        "tasi",
        tasi_text
    )


# ============================================================
# 📲 TELEGRAM WEBHOOK
# ============================================================

async def telegram_webhook(
    request
):

    market = request.match_info[
        "market"
    ]

    try:

        body = await request.json()

    except:

        return web.json_response({
            "ok": True
        })

    message = body.get(
        "message",
        {}
    )

    chat = message.get(
        "chat",
        {}
    )

    chat_id = chat.get(
        "id"
    )

    text = str(
        message.get(
            "text",
            ""
        )
    ).strip()

    if chat_id is None:
        return web.json_response({
            "ok": True
        })

    chats = state[
        "telegram_chats"
    ].setdefault(
        market,
        []
    )

    if chat_id not in chats:

        chats.append(
            chat_id
        )

        save_state()

    if text == "/start":

        if market == "us":

            reply = """💀🚀 AI PRO MAX

✅ تم تفعيل بوت السوق الأمريكي

🔄 الفحص تلقائي
⏱️ كل دقيقتين

📡 Twelve Data"""

        elif market == "crypto":

            reply = """💀🚀 AI PRO MAX

✅ تم تفعيل بوت العملات الرقمية

🔄 الفحص تلقائي
⏱️ كل دقيقتين

📡 Twelve Data"""

        else:

            reply = """💀🚀 AI PRO MAX

✅ تم تفعيل بوت TASI

🔄 الفحص تلقائي
⏱️ كل دقيقتين

📡 Twelve Data"""

        token = {
            "us": US_TOKEN,
            "crypto": CRYPTO_TOKEN,
            "tasi": TASI_TOKEN
        }.get(
            market,
            ""
        )

        await telegram_send(
            request.app["session"],
            token,
            chat_id,
            reply
        )

    return web.json_response({
        "ok": True
    })


# ============================================================
# ❤️ HEALTH
# ============================================================

async def health(request):

    return web.json_response({
        "status": "online",
        "name": "AI PRO MAX",
        "data": "Twelve Data",
        "scan_seconds": SCAN_SECONDS,
        "us_symbols": len(US_SYMBOLS),
        "crypto_symbols": len(CRYPTO_SYMBOLS),
        "us_index": state["us_index"],
        "crypto_index": state["crypto_index"],
        "daily_requests": credits.daily_requests
    })


# ============================================================
# 🔗 SET WEBHOOK
# ============================================================

async def set_webhook(
    session,
    market,
    token,
    base_url
):

    if not token:
        print(
            f"ℹ️ Telegram {market}: لا يوجد TOKEN"
        )
        return

    webhook_url = (
        f"{base_url}/telegram/{market}"
    )

    url = (
        f"https://api.telegram.org/"
        f"bot{token}/setWebhook"
    )

    try:

        async with session.post(
            url,
            json={
                "url": webhook_url,
                "drop_pending_updates": True
            },
            timeout=aiohttp.ClientTimeout(total=20)
        ) as response:

            data = await response.json(
                content_type=None
            )

            print(
                f"Telegram Webhook {market}: "
                f"{data}"
            )

    except Exception as e:

        print(
            f"ℹ️ Telegram webhook {market}: {e}"
        )


# ============================================================
# 🚀 SCANNER LOOP
# ============================================================

async def scanner_loop(
    session
):

    # أول تشغيل بدون انتظار
    first_cycle = True

    while True:

        try:

            if not first_cycle:

                print(
                    f"⏱️ الدورة التالية بعد "
                    f"{SCAN_SECONDS} ثانية"
                )

                await asyncio.sleep(
                    SCAN_SECONDS
                )

            first_cycle = False

            market = next_market()

            symbol = next_symbol(
                market
            )

            if not symbol:

                print(
                    f"ℹ️ لا توجد رموز: {market}"
                )

                continue

            await scan_symbol(
                session,
                market,
                symbol
            )

        except asyncio.CancelledError:

            raise

        except Exception as e:

            print(
                f"ℹ️ خطأ في دورة الفحص: {e}"
            )

            await asyncio.sleep(
                10
            )


# ============================================================
# 🏁 MAIN
# ============================================================

async def main():

    if not TWELVE_DATA_API_KEY:

        print(
            "ℹ️ TWELVE_DATA_API_KEY غير موجود"
        )

    print("")
    print("💀🚀 AI PRO MAX")
    print("🟢 النظام يعمل 24/7")
    print("📡 Twelve Data")
    print("🛡️ مدير Credits مفعل")
    print(
        f"🇺🇸 US: {len(US_SYMBOLS)}"
    )
    print(
        f"🪙 CRYPTO: {len(CRYPTO_SYMBOLS)}"
    )

    connector = aiohttp.TCPConnector(
        limit=10,
        ttl_dns_cache=300
    )

    async with aiohttp.ClientSession(
        connector=connector
    ) as session:

        app = web.Application()

        app["session"] = session

        app.router.add_get(
            "/",
            health
        )

        app.router.add_get(
            "/health",
            health
        )

        app.router.add_post(
            "/telegram/{market}",
            telegram_webhook
        )

        runner = web.AppRunner(
            app
        )

        await runner.setup()

        site = web.TCPSite(
            runner,
            "0.0.0.0",
            PORT
        )

        await site.start()

        print(
            f"🚀 AI PRO MAX {PORT}"
        )

        # Railway يعطينا RAILWAY_PUBLIC_DOMAIN
        domain = os.getenv(
            "RAILWAY_PUBLIC_DOMAIN"
        )

        if domain:

            if not domain.startswith(
                "http"
            ):
                base_url = (
                    "https://" + domain
                )
            else:
                base_url = domain

            await set_webhook(
                session,
                "us",
                US_TOKEN,
                base_url
            )

            await set_webhook(
                session,
                "crypto",
                CRYPTO_TOKEN,
                base_url
            )

            await set_webhook(
                session,
                "tasi",
                TASI_TOKEN,
                base_url
            )

        else:

            print(
                "ℹ️ RAILWAY_PUBLIC_DOMAIN غير موجود"
            )

        # رسالة البداية
        await send_startup_messages(
            session
        )

        # تشغيل المحرك
        await scanner_loop(
            session
        )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        print(
            "ℹ️ تم إيقاف النظام"
        )

    except Exception as e:

        print(
            f"ℹ️ خطأ رئيسي: {e}"
        )