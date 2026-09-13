
# ============================================================
# 💀🚀 AI PRO MAX
# نظام فحص تلقائي للأسواق
# US + CRYPTO + TASI BOT
# مصدر البيانات: Twelve Data فقط
# ============================================================

import os
import json
import time
import asyncio
from datetime import datetime, timezone

import aiohttp
from aiohttp import web


# ============================================================
# ⚙️ الإعدادات
# ============================================================

TWELVE_DATA_API_KEY = os.getenv(
    "TWELVE_DATA_API_KEY", ""
).strip()

TASI_TOKEN = os.getenv(
    "TASI_TOKEN", ""
).strip()

US_TOKEN = os.getenv(
    "US_TOKEN", ""
).strip()

CRYPTO_TOKEN = os.getenv(
    "CRYPTO_TOKEN", ""
).strip()

PORT = int(
    os.getenv("PORT", "8080")
)

# دورة الفحص
SCAN_SECONDS = 120

# ملف حفظ حالة البوت
STATE_FILE = "scanner_state.json"


# ============================================================
# 📊 الأسهم الأمريكية
# ============================================================

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


# ============================================================
# 🪙 العملات الرقمية
# ============================================================

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
# 💾 الحالة
# ============================================================

DEFAULT_STATE = {
    "us_index": 0,
    "crypto_index": 0,
    "last_market": "CRYPTO",
    "daily_date": "",
    "daily_requests": 0,
    "telegram_chats": {
        "us": [],
        "crypto": [],
        "tasi": []
    },
    "last_alerts": {}
}


def load_state():

    state = dict(DEFAULT_STATE)

    try:

        if os.path.exists(STATE_FILE):

            with open(
                STATE_FILE,
                "r",
                encoding="utf-8"
            ) as f:

                saved = json.load(f)

            if isinstance(saved, dict):
                state.update(saved)

    except Exception as e:

        print(
            f"ℹ️ تعذر قراءة الحالة: {e}"
        )

    if not isinstance(
        state.get("telegram_chats"),
        dict
    ):
        state["telegram_chats"] = {
            "us": [],
            "crypto": [],
            "tasi": []
        }

    return state


state = load_state()


def save_state():

    try:

        temp_file = STATE_FILE + ".tmp"

        with open(
            temp_file,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                state,
                f,
                ensure_ascii=False,
                indent=2
            )

        os.replace(
            temp_file,
            STATE_FILE
        )

    except Exception as e:

        print(
            f"ℹ️ تعذر حفظ الحالة: {e}"
        )


# ============================================================
# 🧠 مدير Credits
# ============================================================

class CreditManager:

    def __init__(self):

        self.lock = asyncio.Lock()

        self.last_request = 0.0

        today = datetime.now(
            timezone.utc
        ).strftime("%Y-%m-%d")

        if state.get(
            "daily_date"
        ) == today:

            self.daily_requests = int(
                state.get(
                    "daily_requests",
                    0
                )
            )

        else:

            self.daily_requests = 0

            state["daily_date"] = today
            state["daily_requests"] = 0

            save_state()

    async def before_request(self):

        async with self.lock:

            now = time.monotonic()

            # طلب واحد فقط في كل دورة
            elapsed = now - self.last_request

            if elapsed < 60:

                wait = 60 - elapsed

                print(
                    f"⏳ مدير Credits: انتظار "
                    f"{int(wait) + 1} ثانية"
                )

                await asyncio.sleep(
                    wait + 1
                )

            # تحديث اليوم
            today = datetime.now(
                timezone.utc
            ).strftime("%Y-%m-%d")

            if today != state.get(
                "daily_date"
            ):

                state["daily_date"] = today
                state["daily_requests"] = 0

                self.daily_requests = 0

                save_state()

            # هامش أمان
            if self.daily_requests >= 790:

                print(
                    "ℹ️ تم الوصول إلى حد الأمان اليومي"
                )

                return False

            self.last_request = (
                time.monotonic()
            )

            return True

    def success(self):

        self.daily_requests += 1

        state["daily_date"] = (
            datetime.now(
                timezone.utc
            ).strftime("%Y-%m-%d")
        )

        state["daily_requests"] = (
            self.daily_requests
        )

        save_state()


credits = CreditManager()


# ============================================================
# 🌐 جلب البيانات
# ============================================================

async def get_data(
    session,
    symbol
):

    url = (
        "https://api.twelvedata.com/"
        "time_series"
    )

    params = {
        "symbol": symbol,
        "interval": "5min",
        "outputsize": 80,
        "apikey": TWELVE_DATA_API_KEY
    }

    # إعادة المحاولة على نفس السهم
    for attempt in range(4):

        allowed = await credits.before_request()

        if not allowed:
            return None

        try:

            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(
                    total=30
                )
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

                print(
                    f"📊 Credits "
                    f"used={used or '?'} "
                    f"left={left or '?'}"
                )

                # ------------------------------------------------
                # نجاح
                # ------------------------------------------------

                values = None

                if isinstance(
                    data,
                    dict
                ):
                    values = data.get(
                        "values"
                    )

                if (
                    response.status == 200
                    and values
                ):

                    credits.success()

                    return values

                # ------------------------------------------------
                # 429
                # ------------------------------------------------

                message = ""

                if isinstance(
                    data,
                    dict
                ):

                    message = str(
                        data.get(
                            "message",
                            ""
                        )
                    )

                lower = message.lower()

                rate_limit = (
                    response.status == 429
                    or "rate limit" in lower
                    or "per minute" in lower
                    or "credits" in lower
                    or "too many" in lower
                )

                if rate_limit:

                    print(
                        f"ℹ️ Twelve Data: "
                        f"الحد المؤقت للطلبات"
                    )

                    if attempt < 3:

                        wait = 65

                        print(
                            f"⏳ إعادة نفس السهم "
                            f"{symbol} بعد {wait} ثانية"
                        )

                        await asyncio.sleep(
                            wait
                        )

                        continue

                    print(
                        f"ℹ️ لم تنجح إعادة "
                        f"فحص {symbol}"
                    )

                    return None

                # ------------------------------------------------
                # خطأ عادي
                # ------------------------------------------------

                if message:

                    print(
                        f"ℹ️ Twelve Data: "
                        f"{message}"
                    )

                else:

                    print(
                        f"ℹ️ Twelve Data HTTP "
                        f"{response.status}"
                    )

                return None

        except asyncio.TimeoutError:

            print(
                f"ℹ️ انتهت مهلة البيانات: "
                f"{symbol}"
            )

            if attempt < 3:

                await asyncio.sleep(5)
                continue

            return None

        except Exception as e:

            print(
                f"ℹ️ خطأ الاتصال: {e}"
            )

            if attempt < 3:

                await asyncio.sleep(5)
                continue

            return None

    return None


# ============================================================
# 📐 المؤشرات
# ============================================================

def closes(values):

    result = []

    for row in reversed(values):

        try:
            result.append(
                float(row["close"])
            )
        except:
            pass

    return result


def highs(values):

    result = []

    for row in reversed(values):

        try:
            result.append(
                float(row["high"])
            )
        except:
            pass

    return result


def lows(values):

    result = []

    for row in reversed(values):

        try:
            result.append(
                float(row["low"])
            )
        except:
            pass

    return result


def volumes(values):

    result = []

    for row in reversed(values):

        try:

            result.append(
                float(
                    row.get(
                        "volume",
                        0
                    )
                )
            )

        except:

            result.append(0)

    return result


def ema(data, period):

    if not data:
        return 0.0

    if len(data) < period:

        return (
            sum(data) / len(data)
        )

    multiplier = 2 / (
        period + 1
    )

    value = (
        sum(data[:period])
        / period
    )

    for price in data[period:]:

        value = (
            (price - value)
            * multiplier
        ) + value

    return value


def rsi(
    data,
    period=14
):

    if len(data) < period + 1:
        return 50.0

    gains = []
    losses = []

    for i in range(
        1,
        len(data)
    ):

        change = (
            data[i]
            - data[i - 1]
        )

        if change >= 0:

            gains.append(change)
            losses.append(0)

        else:

            gains.append(0)
            losses.append(
                abs(change)
            )

    avg_gain = (
        sum(gains[:period])
        / period
    )

    avg_loss = (
        sum(losses[:period])
        / period
    )

    for i in range(
        period,
        len(gains)
    ):

        avg_gain = (
            (
                avg_gain
                * (period - 1)
            )
            + gains[i]
        ) / period

        avg_loss = (
            (
                avg_loss
                * (period - 1)
            )
            + losses[i]
        ) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss

    return 100 - (
        100 / (1 + rs)
    )


def atr(
    values,
    period=14
):

    if len(values) < period + 1:
        return 0.0

    trs = []

    previous_close = None

    for row in reversed(values):

        try:

            high = float(
                row["high"]
            )

            low = float(
                row["low"]
            )

            close = float(
                row["close"]
            )

            if previous_close is None:

                tr = high - low

            else:

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

            trs.append(tr)

            previous_close = close

        except:
            pass

    if not trs:
        return 0.0

    sample = trs[-period:]

    return (
        sum(sample)
        / len(sample)
    )


# ============================================================
# 🧠 محرك AI PRO MAX
# ============================================================

def analyze(values):

    if len(values) < 30:
        return None

    c = closes(values)
    h = highs(values)
    l = lows(values)

    if len(c) < 30:
        return None

    price = c[-1]

    ema8 = ema(c, 8)
    ema21 = ema(c, 21)
    ema50 = ema(c, 50)

    rsi14 = rsi(c, 14)

    atr14 = atr(
        values,
        14
    )

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

    valid_volumes = [
        x for x in vols[-20:]
        if x > 0
    ]

    if valid_volumes:

        avg_volume = (
            sum(valid_volumes)
            / len(valid_volumes)
        )

    else:

        avg_volume = 0

    if avg_volume > 0:

        volume_strength = (
            current_volume
            / avg_volume
        )

    else:

        volume_strength = 1.0

    # ========================================================
    # الاتجاه
    # ========================================================

    bullish = (
        ema8 > ema21
        and ema21 > ema50
    )

    bearish = (
        ema8 < ema21
        and ema21 < ema50
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

    # ========================================================
    # قوة الشراء
    # ========================================================

    buy_power = 50

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

    buy_power = max(
        0,
        min(
            100,
            buy_power
        )
    )

    sell_power = (
        100 - buy_power
    )

    # ========================================================
    # قوة الإشارة
    # ========================================================

    strength = 50

    if bullish:
        strength += 20

    if bearish:
        strength += 20

    if rsi14 >= 55:
        strength += 10

    if rsi14 <= 45:
        strength += 10

    if volume_strength >= 1.5:
        strength += 10

    strength = max(
        0,
        min(
            100,
            strength
        )
    )

    # ========================================================
    # الإشارة
    # ========================================================

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

    # ========================================================
    # أهداف ATR
    # ========================================================

    targets = []

    if atr14 > 0:

        if "شراء" in signal:

            for i in range(1, 9):

                targets.append(
                    price
                    + (
                        atr14 * i
                    )
                )

        elif "بيع" in signal:

            for i in range(1, 9):

                targets.append(
                    price
                    - (
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
        "strength": strength,
        "signal": signal,
        "trend": trend,
        "targets": targets,
    }


# ============================================================
# 💰 تنسيق الأرقام
# ============================================================

def fmt(
    value,
    digits=2
):

    try:

        return f"{float(value):,.{digits}f}"

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
        "https://api.telegram.org/"
        f"bot{token}/sendMessage"
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
            timeout=aiohttp.ClientTimeout(
                total=20
            )
        ) as response:

            return response.status == 200

    except:

        return False


async def broadcast(
    session,
    market,
    text
):

    token = {
        "us": US_TOKEN,
        "crypto": CRYPTO_TOKEN,
        "tasi": TASI_TOKEN
    }.get(
        market,
        ""
    )

    chats = state[
        "telegram_chats"
    ].get(
        market,
        []
    )

    if not token or not chats:
        return

    for chat_id in list(chats):

        await telegram_send(
            session,
            token,
            chat_id,
            text
        )

        await asyncio.sleep(
            0.2
        )


# ============================================================
# 📨 رسالة الإشارة
# ============================================================

def signal_message(
    market,
    symbol,
    result
):

    if market == "us":

        market_name = (
            "🇺🇸 السوق الأمريكي (US)"
        )

    elif market == "crypto":

        market_name = (
            "🪙 العملات الرقمية (CRYPTO)"
        )

    else:

        market_name = (
            "🇸🇦 السوق السعودي (TASI)"
        )

    lines = [

        "💀🚀 AI PRO MAX SIGNAL",
        "",
        market_name,
        "",
        f"📌 {symbol}",
        "",
        f"💰 السعر: "
        f"{fmt(result['price'])}",

        f"🎯 الإشارة: "
        f"{result['signal']}",

        f"💪 قوة الإشارة: "
        f"{fmt(result['strength'], 0)}/100",

        f"🟢 قوة الشراء: "
        f"{fmt(result['buy_power'], 0)}%",

        f"🔴 قوة البيع: "
        f"{fmt(result['sell_power'], 0)}%",

        f"📊 قوة الحجم: "
        f"{fmt(result['volume_strength'], 2)}x",

        "",
        "🧠 المؤشرات",

        f"EMA 8: "
        f"{fmt(result['ema8'])}",

        f"EMA 21: "
        f"{fmt(result['ema21'])}",

        f"EMA 50: "
        f"{fmt(result['ema50'])}",

        f"RSI 14: "
        f"{fmt(result['rsi'], 1)}",

        f"ATR 14: "
        f"{fmt(result['atr'])}",

        "",
        f"🟩 الدعم: "
        f"{fmt(result['support'])}",

        f"🟥 المقاومة: "
        f"{fmt(result['resistance'])}",

        f"📈 الاتجاه: "
        f"{result['trend']}",

        "",
        "🎯 أهداف ATR الثمانية:"
    ]

    for i, target in enumerate(
        result["targets"],
        1
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
# 🔔 منع تكرار التنبيه
# ============================================================

def can_alert(
    market,
    symbol
):

    key = (
        f"{market}:{symbol}"
    )

    now = time.time()

    previous = state[
        "last_alerts"
    ].get(
        key,
        0
    )

    # 30 دقيقة
    if (
        now - float(previous)
        < 1800
    ):
        return False

    state[
        "last_alerts"
    ][key] = now

    save_state()

    return True


# ============================================================
# 🔎 فحص سهم
# ============================================================

async def scan(
    session,
    market,
    symbol
):

    print(
        f"🔎 فحص {market.upper()}: "
        f"{symbol}"
    )

    values = await get_data(
        session,
        symbol
    )

    if not values:

        print(
            f"ℹ️ لم تصل بيانات "
            f"{symbol}"
        )

        return

    result = analyze(
        values
    )

    if not result:

        print(
            f"ℹ️ بيانات غير كافية: "
            f"{symbol}"
        )

        return

    print(
        f"📈 {symbol} | "
        f"{result['signal']} | "
        f"RSI={result['rsi']:.1f} | "
        f"ATR={result['atr']:.4f}"
    )

    # لا ترسل المحايد
    if result["signal"] == "محايد":
        return

    if not can_alert(
        market,
        symbol
    ):
        return

    message = signal_message(
        market,
        symbol,
        result
    )

    await broadcast(
        session,
        market,
        message
    )

    print(
        f"📨 تم إرسال الإشارة: "
        f"{symbol}"
    )


# ============================================================
# 🔄 نظام التدوير
# ============================================================

def next_market():

    last = state.get(
        "last_market",
        "CRYPTO"
    )

    if last == "CRYPTO":

        market = "us"

    else:

        market = "crypto"

    state["last_market"] = (
        market.upper()
    )

    save_state()

    return market


def next_symbol(
    market
):

    if market == "us":

        index = int(
            state.get(
                "us_index",
                0
            )
        )

        symbol = US_SYMBOLS[
            index
            % len(US_SYMBOLS)
        ]

        state["us_index"] = (
            index + 1
        )

    else:

        index = int(
            state.get(
                "crypto_index",
                0
            )
        )

        symbol = CRYPTO_SYMBOLS[
            index
            % len(CRYPTO_SYMBOLS)
        ]

        state["crypto_index"] = (
            index + 1
        )

    save_state()

    return symbol


# ============================================================
# 🤖 رسائل التشغيل
# ============================================================

async def startup_messages(
    session
):

    us = """💀🚀 AI PRO MAX

✅ البوت يعمل الآن
🔄 الفحص تلقائي وكامل
⏱️ الفحص كل دقيقتين

📊 السوق: 🇺🇸 الأمريكي

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

    crypto = """💀🚀 AI PRO MAX

✅ البوت يعمل الآن
🔄 الفحص تلقائي وكامل
⏱️ الفحص كل دقيقتين

📊 السوق: 🪙 العملات الرقمية

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

    tasi = """💀🚀 AI PRO MAX

✅ بوت السوق السعودي جاهز
🔄 النظام تلقائي
⏱️ الفحص كل دقيقتين

📊 السوق: 🇸🇦 TASI

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

    await broadcast(
        session,
        "us",
        us
    )

    await broadcast(
        session,
        "crypto",
        crypto
    )

    await broadcast(
        session,
        "tasi",
        tasi
    )


# ============================================================
# 📲 Telegram Webhook
# ============================================================

async def webhook(
    request
):

    market = request.match_info[
        "market"
    ]

    if market not in (
        "us",
        "crypto",
        "tasi"
    ):
        return web.json_response({
            "ok": True
        })

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

        replies = {

            "us":
                """💀🚀 AI PRO MAX

✅ تم تفعيل بوت السوق الأمريكي

🔄 الفحص تلقائي
⏱️ كل دقيقتين

📡 Twelve Data""",

            "crypto":
                """💀🚀 AI PRO MAX

✅ تم تفعيل بوت العملات الرقمية

🔄 الفحص تلقائي
⏱️ كل دقيقتين

📡 Twelve Data""",

            "tasi":
                """💀🚀 AI PRO MAX

✅ تم تفعيل بوت السوق السعودي

🔄 النظام تلقائي
⏱️ كل دقيقتين

📡 Twelve Data"""
        }

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
            replies[market]
        )

    return web.json_response({
        "ok": True
    })


# ============================================================
# ❤️ HEALTH
# ============================================================

async def health(
    request
):

    return web.json_response({

        "status": "online",

        "name":
            "AI PRO MAX",

        "data":
            "Twelve Data",

        "scan_seconds":
            SCAN_SECONDS,

        "us_symbols":
            len(US_SYMBOLS),

        "crypto_symbols":
            len(CRYPTO_SYMBOLS),

        "us_index":
            state["us_index"],

        "crypto_index":
            state["crypto_index"],

        "daily_requests":
            credits.daily_requests
    })


# ============================================================
# 🔗 ضبط Webhook
# ============================================================

async def set_webhook(
    session,
    market,
    token,
    base_url
):

    if not token:

        print(
            f"ℹ️ Telegram {market}: "
            f"لا يوجد TOKEN"
        )

        return

    url = (
        "https://api.telegram.org/"
        f"bot{token}/setWebhook"
    )

    webhook_url = (
        f"{base_url}/telegram/{market}"
    )

    try:

        async with session.post(
            url,
            json={
                "url": webhook_url,
                "drop_pending_updates": True
            },
            timeout=aiohttp.ClientTimeout(
                total=20
            )
        ) as response:

            data = await response.json(
                content_type=None
            )

            print(
                f"Telegram Webhook "
                f"{market}: {data}"
            )

    except Exception as e:

        print(
            f"ℹ️ Webhook {market}: {e}"
        )


# ============================================================
# 🚀 المحرك الرئيسي
# ============================================================

async def scanner(
    session
):

    first = True

    while True:

        try:

            if not first:

                print(
                    f"⏱️ الدورة التالية بعد "
                    f"{SCAN_SECONDS} ثانية"
                )

                await asyncio.sleep(
                    SCAN_SECONDS
                )

            first = False

            market = next_market()

            symbol = next_symbol(
                market
            )

            await scan(
                session,
                market,
                symbol
            )

        except asyncio.CancelledError:

            raise

        except Exception as e:

            print(
                f"ℹ️ خطأ في المحرك: {e}"
            )

            await asyncio.sleep(
                10
            )


# ============================================================
# 🏁 MAIN
# ============================================================

async def main():

    print("")
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
        f"🇺🇸 US: {len(US_SYMBOLS)}"
    )

    print(
        f"🪙 CRYPTO: "
        f"{len(CRYPTO_SYMBOLS)}"
    )

    if not TWELVE_DATA_API_KEY:

        print(
            "ℹ️ TWELVE_DATA_API_KEY "
            "غير موجود"
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
            webhook
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

        domain = os.getenv(
            "RAILWAY_PUBLIC_DOMAIN"
        )

        if domain:

            domain = domain.rstrip("/")

            if not domain.startswith(
                "http"
            ):

                domain = (
                    "https://"
                    + domain
                )

            await set_webhook(
                session,
                "us",
                US_TOKEN,
                domain
            )

            await set_webhook(
                session,
                "crypto",
                CRYPTO_TOKEN,
                domain
            )

            await set_webhook(
                session,
                "tasi",
                TASI_TOKEN,
                domain
            )

        else:

            print(
                "ℹ️ RAILWAY_PUBLIC_DOMAIN "
                "غير موجود"
            )

        await startup_messages(
            session
        )

        await scanner(
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