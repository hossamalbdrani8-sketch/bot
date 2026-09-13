
import os
import json
import asyncio
import aiohttp
import time
from aiohttp import web
from datetime import datetime, timezone

# ============================================================
# 💀🚀 AI PRO MAX
# CLEAN AUTONOMOUS ENGINE
# US + CRYPTO + TELEGRAM
# ============================================================

API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()

TASI_TOKEN = os.getenv("TASI_TOKEN", "").strip()
US_TOKEN = os.getenv("US_TOKEN", "").strip()
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN", "").strip()

PORT = int(os.getenv("PORT", "8080"))

TD_URL = "https://api.twelvedata.com"
TG_URL = "https://api.telegram.org"

# ============================================================
# ⚙️ الإعدادات
# ============================================================

SCAN_SECONDS = 120

# رمز واحد في كل طلب
# حتى لا نستنزف 8 credits دفعة واحدة
SYMBOLS_PER_SCAN = 1

ALERT_COOLDOWN = 3600

MIN_US_PRICE = 0.20

# لا نحاول تحديث قوائم الرموز باستمرار
CATALOG_REFRESH = 86400

# ============================================================
# 📦 التخزين
# ============================================================

US_SYMBOLS = []
CRYPTO_SYMBOLS = []

US_INDEX = 0
CRYPTO_INDEX = 0

US_CHAT_IDS = set()
CRYPTO_CHAT_IDS = set()
TASI_CHAT_IDS = set()

ALERT_CACHE = {}

LAST_CREDITS_LEFT = None

NEXT_US_CATALOG = 0
NEXT_CRYPTO_CATALOG = 0

# ============================================================
# 🇺🇸 قائمة تشغيل أولية
# ============================================================
# هذه ليست القائمة الكاملة.
# هدفها أن يبدأ البوت فورًا بدل انتظار /stocks.

START_US = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL",
    "GOOG",
    "TSLA",
    "AVGO",
    "AMD",
    "NFLX",
    "INTC",
    "MU",
    "QCOM",
    "PLTR",
    "SMCI",
    "ARM",
    "MSTR",
    "COIN",
    "HOOD",
    "SOFI",
    "NIO",
    "RIVN",
    "LCID",
    "AAL",
    "MARA",
    "RIOT",
    "IONQ",
    "SOUN",
    "BBAI",
    "ACHR",
    "JOBY",
    "RKLB",
    "GME",
    "AMC",
    "TQQQ",
    "SQQQ",
    "SPY",
    "QQQ",
    "IWM"
]

# ============================================================
# 🪙 قائمة تشغيل أولية للعملات
# ============================================================

START_CRYPTO = [
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
    "SHIB/USD",
    "UNI/USD",
    "ATOM/USD",
    "XLM/USD",
    "ETC/USD",
    "FIL/USD",
    "NEAR/USD"
]

# ============================================================
# 🔢 أدوات
# ============================================================

def n(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def ema(values, period):
    if not values:
        return 0.0

    alpha = 2 / (period + 1)
    result = values[0]

    for value in values[1:]:
        result = alpha * value + (1 - alpha) * result

    return result


def rsi(values, period=14):
    if len(values) < period + 1:
        return 50.0

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

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def atr(rows, period=14):
    if len(rows) < period + 1:
        return 0.0

    ranges = []

    for i in range(1, len(rows)):
        high = n(rows[i].get("high"))
        low = n(rows[i].get("low"))
        previous_close = n(rows[i - 1].get("close"))

        true_range = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close)
        )

        ranges.append(true_range)

    return sum(ranges[-period:]) / period


def volume_text(value):
    value = n(value)

    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"

    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"

    if value >= 1_000:
        return f"{value / 1_000:.2f}K"

    return f"{value:.0f}"


# ============================================================
# 💾 حفظ / تحميل القائمة
# ============================================================

def load_file(filename, fallback):
    try:
        with open(filename, "r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, list) and data:
            return data

    except Exception:
        pass

    return list(fallback)


def save_file(filename, data):
    try:
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                ensure_ascii=False
            )
    except Exception:
        pass


# ============================================================
# 📡 Twelve Data
# ============================================================

async def td_request(session, endpoint, params):
    global LAST_CREDITS_LEFT

    if not API_KEY:
        print("ℹ️ مفتاح Twelve Data غير موجود")
        return None

    query = dict(params)
    query["apikey"] = API_KEY

    try:

        async with session.get(
            TD_URL + endpoint,
            params=query,
            timeout=aiohttp.ClientTimeout(total=20)
        ) as response:

            text = await response.text()

            credits_left = response.headers.get(
                "api-credits-left"
            )

            credits_used = response.headers.get(
                "api-credits-used"
            )

            if credits_left is not None:
                LAST_CREDITS_LEFT = n(
                    credits_left,
                    None
                )

            if credits_left is not None:
                print(
                    f"📊 Credits "
                    f"used={credits_used or '?'} "
                    f"left={credits_left}"
                )

            # --------------------------------------------
            # حد الدقيقة
            # --------------------------------------------

            if response.status == 429:

                print(
                    "ℹ️ Twelve Data: "
                    "انتظار تجدد رصيد الدقيقة"
                )

                return None

            # --------------------------------------------
            # أي HTTP آخر
            # --------------------------------------------

            if response.status != 200:

                print(
                    f"ℹ️ Twelve Data HTTP "
                    f"{response.status}: "
                    f"{text[:180]}"
                )

                return None

            try:
                data = json.loads(text)
            except Exception:
                return None

            # --------------------------------------------
            # خطأ API داخل JSON
            # --------------------------------------------

            if (
                isinstance(data, dict)
                and data.get("status") == "error"
            ):

                print(
                    "ℹ️ Twelve Data: "
                    + str(
                        data.get(
                            "message",
                            "خطأ غير معروف"
                        )
                    )
                )

                return None

            return data

    except asyncio.TimeoutError:

        print("ℹ️ انتهت مهلة Twelve Data")
        return None

    except Exception as error:

        print(
            f"ℹ️ Twelve Data: {error}"
        )

        return None


# ============================================================
# 📊 بيانات رمز واحد
# ============================================================

async def get_history(session, symbol):

    return await td_request(
        session,
        "/time_series",
        {
            "symbol": symbol,
            "interval": "1min",
            "outputsize": 60
        }
    )


# ============================================================
# 🧠 تحليل AI PRO MAX
# ============================================================

def analyze(symbol, packet, market):

    if not packet:
        return None

    values = packet.get("values", [])

    if len(values) < 30:
        return None

    rows = list(reversed(values))

    closes = [
        n(row.get("close"))
        for row in rows
    ]

    if not closes:
        return None

    price = closes[-1]

    # --------------------------------------------
    # السعر الأدنى للأمريكي
    # --------------------------------------------

    if market == "US" and price < MIN_US_PRICE:
        return None

    ema8 = ema(closes, 8)
    ema21 = ema(closes, 21)
    ema50 = ema(closes, 50)

    rsi14 = rsi(closes, 14)

    atr14 = atr(rows, 14)

    previous = (
        closes[-2]
        if len(closes) > 1
        else price
    )

    change = (
        ((price - previous) / previous) * 100
        if previous
        else 0
    )

    # --------------------------------------------
    # الحجم
    # --------------------------------------------

    volumes = [
        n(row.get("volume"))
        for row in rows[-20:]
    ]

    average_volume = (
        sum(volumes) / len(volumes)
        if volumes
        else 0
    )

    current_volume = n(
        rows[-1].get("volume")
    )

    volume_strength = (
        current_volume / average_volume
        if average_volume
        else 1
    )

    # --------------------------------------------
    # قوة الاتجاه
    # --------------------------------------------

    score = 50

    if ema8 > ema21:
        score += 15
    else:
        score -= 15

    if ema21 > ema50:
        score += 15
    else:
        score -= 15

    if rsi14 >= 55:
        score += 10

    elif rsi14 <= 45:
        score -= 10

    if volume_strength >= 1.5:
        score += 10

    score = max(
        0,
        min(100, score)
    )

    # --------------------------------------------
    # الإشارة
    # --------------------------------------------

    if score >= 80:

        side = "BUY"
        signal = "🟢⬆️ شراء قوي"

    elif score <= 20:

        side = "SELL"
        signal = "🔴⬇️ بيع قوي"

    else:

        return None

    # --------------------------------------------
    # دعم ومقاومة
    # --------------------------------------------

    highs = [
        n(row.get("high"))
        for row in rows[-20:]
    ]

    lows = [
        n(row.get("low"))
        for row in rows[-20:]
    ]

    support = (
        min(lows)
        if lows
        else price
    )

    resistance = (
        max(highs)
        if highs
        else price
    )

    return {
        "symbol": symbol,
        "price": price,
        "change": change,
        "score": score,
        "side": side,
        "signal": signal,
        "buy": round(score),
        "sell": 100 - round(score),
        "volume": current_volume,
        "volume_strength": volume_strength,
        "ema8": ema8,
        "ema21": ema21,
        "ema50": ema50,
        "rsi": rsi14,
        "atr": atr14,
        "support": support,
        "resistance": resistance
    }


# ============================================================
# 🎯 رسالة الإشارة
# ============================================================

def make_signal(data, market):

    price = data["price"]
    atr14 = data["atr"]

    if data["side"] == "BUY":

        targets = [
            price + (atr14 * i)
            for i in range(1, 9)
        ]

    else:

        targets = [
            price - (atr14 * i)
            for i in range(1, 9)
        ]

    target_text = "\n".join(
        f"{i}️⃣ {targets[i - 1]:.4f}"
        for i in range(1, 9)
    )

    return f"""💀🚀 AI PRO MAX SIGNAL

{market}

<b>{data["symbol"]}</b>

{data["signal"]}

💰 السعر: {price:.4f}
📈 التغير: {data["change"]:+.2f}%

🎯 قوة الإشارة: {data["score"]}/100

🟢 قوة الشراء: {data["buy"]}%
🔴 قوة البيع: {data["sell"]}%

📊 قوة الحجم: {data["volume_strength"]:.2f}x
📦 الحجم: {volume_text(data["volume"])}

EMA 8: {data["ema8"]:.4f}
EMA 21: {data["ema21"]:.4f}
EMA 50: {data["ema50"]:.4f}

RSI 14: {data["rsi"]:.1f}
ATR 14: {data["atr"]:.4f}

🟦 الدعم: {data["support"]:.4f}
🟥 المقاومة: {data["resistance"]:.4f}

🎯 أهداف ATR:

{target_text}

⏱️ الفحص تلقائي
🤖 AI PRO MAX"""


# ============================================================
# 📲 Telegram
# ============================================================

async def telegram_send(
    session,
    token,
    chat_id,
    message
):

    if not token or not chat_id:
        return False

    try:

        async with session.post(
            f"{TG_URL}/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=15
        ) as response:

            return response.status == 200

    except Exception:

        return False


async def broadcast(
    session,
    token,
    chat_ids,
    message
):

    for chat_id in list(chat_ids):

        await telegram_send(
            session,
            token,
            chat_id,
            message
        )


# ============================================================
# 🚫 منع التكرار
# ============================================================

def allow_alert(symbol, side):

    key = (
        f"{symbol}:{side}"
    )

    now = time.time()

    last = ALERT_CACHE.get(
        key,
        0
    )

    if (
        now - last
        < ALERT_COOLDOWN
    ):
        return False

    ALERT_CACHE[key] = now

    return True


# ============================================================
# 🔎 فحص رمز
# ============================================================

async def scan_symbol(
    session,
    symbol,
    market
):

    print(
        f"🔎 فحص {market}: {symbol}"
    )

    packet = await get_history(
        session,
        symbol
    )

    if not packet:
        return

    result = analyze(
        symbol,
        packet,
        market
    )

    if not result:
        return

    if not allow_alert(
        symbol,
        result["side"]
    ):
        return

    if market == "US":

        message = make_signal(
            result,
            "🇺🇸 السوق الأمريكي"
        )

        await broadcast(
            session,
            US_TOKEN,
            US_CHAT_IDS,
            message
        )

    else:

        message = make_signal(
            result,
            "🪙 العملات الرقمية"
        )

        await broadcast(
            session,
            CRYPTO_TOKEN,
            CRYPTO_CHAT_IDS,
            message
        )

    print(
        f"🚨 إشارة {market}: "
        f"{symbol} "
        f"{result['side']} "
        f"{result['score']}/100"
    )


# ============================================================
# 📚 تحديث قائمة الرموز في الخلفية
# ============================================================

async def update_us_catalog(session):

    global US_SYMBOLS

    data = await td_request(
        session,
        "/stocks",
        {
            "country": "United States",
            "type": "Common Stock",
            "outputsize": 5000
        }
    )

    if not data:
        return

    rows = data.get(
        "data",
        []
    )

    symbols = []

    for row in rows:

        symbol = str(
            row.get("symbol", "")
        ).strip()

        if symbol:
            symbols.append(symbol)

    symbols = list(
        dict.fromkeys(symbols)
    )

    if symbols:

        # نضيف القائمة الجديدة
        # بعد القائمة الحالية
        US_SYMBOLS = list(
            dict.fromkeys(
                US_SYMBOLS + symbols
            )
        )

        save_file(
            "us_symbols.json",
            US_SYMBOLS
        )

        print(
            f"📚 US أصبح لديه "
            f"{len(US_SYMBOLS)} رمز"
        )


async def update_crypto_catalog(session):

    global CRYPTO_SYMBOLS

    data = await td_request(
        session,
        "/cryptocurrencies",
        {
            "currency": "USD",
            "outputsize": 5000
        }
    )

    if not data:
        return

    rows = data.get(
        "data",
        []
    )

    symbols = []

    for row in rows:

        symbol = str(
            row.get("symbol", "")
        ).strip()

        if symbol:
            symbols.append(symbol)

    symbols = list(
        dict.fromkeys(symbols)
    )

    if symbols:

        CRYPTO_SYMBOLS = list(
            dict.fromkeys(
                CRYPTO_SYMBOLS + symbols
            )
        )

        save_file(
            "crypto_symbols.json",
            CRYPTO_SYMBOLS
        )

        print(
            f"📚 CRYPTO أصبح لديه "
            f"{len(CRYPTO_SYMBOLS)} رمز"
        )


# ============================================================
# 💬 رسالة بدء البوت
# ============================================================

def startup_message(market):

    return f"""💀🚀 AI PRO MAX

✅ البوت يعمل الآن
🔄 الفحص تلقائي
⏱️ الفحص مستمر

📊 السوق: {market}

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
Twelve Data"""


# ============================================================
# 🤖 Telegram Webhook
# ============================================================

async def telegram_webhook(request):

    market = request.match_info.get(
        "market",
        ""
    )

    try:

        update = await request.json()

    except Exception:

        return web.json_response(
            {"ok": True}
        )

    message = update.get(
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

    if not chat_id:

        return web.json_response(
            {"ok": True}
        )

    session = request.app[
        "session"
    ]

    if text.startswith("/start"):

        if market == "us":

            US_CHAT_IDS.add(
                chat_id
            )

            await telegram_send(
                session,
                US_TOKEN,
                chat_id,
                startup_message(
                    "🇺🇸 US"
                )
            )

        elif market == "crypto":

            CRYPTO_CHAT_IDS.add(
                chat_id
            )

            await telegram_send(
                session,
                CRYPTO_TOKEN,
                chat_id,
                startup_message(
                    "🪙 CRYPTO"
                )
            )

        elif market == "tasi":

            TASI_CHAT_IDS.add(
                chat_id
            )

            await telegram_send(
                session,
                TASI_TOKEN,
                chat_id,
                startup_message(
                    "🇸🇦 TASI"
                )
            )

    return web.json_response(
        {"ok": True}
    )


# ============================================================
# ❤️ Health
# ============================================================

async def health(request):

    return web.json_response({

        "status": "online",

        "engine":
            "AI PRO MAX",

        "US":
            len(US_SYMBOLS),

        "CRYPTO":
            len(CRYPTO_SYMBOLS),

        "credits_left":
            LAST_CREDITS_LEFT,

        "time":
            datetime.now(
                timezone.utc
            ).isoformat()
    })


# ============================================================
# 🔗 Telegram Webhooks
# ============================================================

async def set_webhook(
    session,
    token,
    path
):

    if not token:
        return

    domain = (
        os.getenv(
            "RAILWAY_PUBLIC_DOMAIN"
        )
        or
        os.getenv(
            "RAILWAY_STATIC_URL"
        )
        or ""
    )

    domain = (
        domain
        .replace(
            "https://",
            ""
        )
        .replace(
            "http://",
            ""
        )
        .rstrip("/")
    )

    if not domain:

        print(
            f"ℹ️ لا يوجد عنوان Railway لـ {path}"
        )

        return

    try:

        async with session.post(

            f"{TG_URL}/bot{token}/setWebhook",

            json={
                "url":
                    f"https://{domain}/telegram/{path}",

                "drop_pending_updates":
                    True
            },

            timeout=20

        ) as response:

            result = await response.json(
                content_type=None
            )

            print(
                f"Telegram Webhook {path}: "
                f"{result}"
            )

    except Exception as error:

        print(
            f"ℹ️ Webhook {path}: "
            f"{error}"
        )


# ============================================================
# 🚀 محرك الفحص
# ============================================================

async def scanner():

    global US_SYMBOLS
    global CRYPTO_SYMBOLS
    global US_INDEX
    global CRYPTO_INDEX

    # --------------------------------------------
    # تحميل القوائم المحلية أو قوائم البداية
    # --------------------------------------------

    US_SYMBOLS = load_file(
        "us_symbols.json",
        START_US
    )

    CRYPTO_SYMBOLS = load_file(
        "crypto_symbols.json",
        START_CRYPTO
    )

    connector = aiohttp.TCPConnector(
        limit=2
    )

    async with aiohttp.ClientSession(
        connector=connector
    ) as session:

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
        print("")

        # --------------------------------------------
        # نبدأ فورًا
        # --------------------------------------------

        market_turn = 0

        while True:

            started = time.time()

            try:

                # ------------------------------------
                # الأمريكي
                # ------------------------------------

                if market_turn == 0:

                    if US_SYMBOLS:

                        symbol = US_SYMBOLS[
                            US_INDEX %
                            len(US_SYMBOLS)
                        ]

                        US_INDEX += 1

                        await scan_symbol(
                            session,
                            symbol,
                            "US"
                        )

                    market_turn = 1

                # ------------------------------------
                # العملات
                # ------------------------------------

                else:

                    if CRYPTO_SYMBOLS:

                        symbol = CRYPTO_SYMBOLS[
                            CRYPTO_INDEX %
                            len(CRYPTO_SYMBOLS)
                        ]

                        CRYPTO_INDEX += 1

                        await scan_symbol(
                            session,
                            symbol,
                            "CRYPTO"
                        )

                    market_turn = 0

                # ------------------------------------
                # تحديث القائمة بشكل متباعد
                # ------------------------------------

                # لا نطلب catalog كل دقيقتين.
                # بعد وجود القوائم المحلية،
                # يتم التحديث لاحقًا فقط.

                now = time.time()

                if (
                    now % CATALOG_REFRESH
                    < 2
                ):

                    if market_turn == 0:

                        await update_us_catalog(
                            session
                        )

                    else:

                        await update_crypto_catalog(
                            session
                        )

            except Exception as error:

                print(
                    f"ℹ️ خطأ في الفحص: "
                    f"{error}"
                )

            elapsed = (
                time.time() - started
            )

            wait = max(
                1,
                SCAN_SECONDS - elapsed
            )

            print(
                f"⏱️ الدورة التالية بعد "
                f"{wait:.0f} ثانية"
            )

            await asyncio.sleep(
                wait
            )


# ============================================================
# 🌐 التطبيق
# ============================================================

async def create_app():

    app = web.Application()

    session = aiohttp.ClientSession()

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

    return app


# ============================================================
# ▶️ MAIN
# ============================================================

async def main():

    app = await create_app()

    session = app["session"]

    # --------------------------------------------
    # Telegram
    # --------------------------------------------

    await set_webhook(
        session,
        US_TOKEN,
        "us"
    )

    await set_webhook(
        session,
        CRYPTO_TOKEN,
        "crypto"
    )

    await set_webhook(
        session,
        TASI_TOKEN,
        "tasi"
    )

    # --------------------------------------------
    # Scanner
    # --------------------------------------------

    asyncio.create_task(
        scanner()
    )

    # --------------------------------------------
    # Web Server
    # --------------------------------------------

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

    try:

        while True:

            await asyncio.sleep(
                3600
            )

    finally:

        await session.close()

        await runner.cleanup()


# ============================================================
# تشغيل
# ============================================================

if __name__ == "__main__":

    asyncio.run(main())