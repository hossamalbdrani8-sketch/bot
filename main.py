
import os
import json
import asyncio
import aiohttp
import time
from aiohttp import web
from datetime import datetime, timezone

# ============================================================
# 💀🚀 AI PRO MAX
# US + CRYPTO AUTONOMOUS TELEGRAM SCANNER
# ============================================================

API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()

TASI_TOKEN = os.getenv("TASI_TOKEN", "").strip()
US_TOKEN = os.getenv("US_TOKEN", "").strip()
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN", "").strip()

PORT = int(os.getenv("PORT", "8080"))

TD_URL = "https://api.twelvedata.com"
TG_URL = "https://api.telegram.org"

SCAN_SECONDS = 120

# الخطة المجانية = 8 API credits / minute
# لذلك لا نتجاوز 8 رموز في دورة واحدة.
BATCH_SIZE = 8

# تحديث قائمة الرموز مرة واحدة يومياً
CATALOG_REFRESH = 86400

# منع تكرار نفس الإشارة
ALERT_COOLDOWN = 3600

# ============================================================
# التخزين
# ============================================================

US_SYMBOLS = []
CRYPTO_SYMBOLS = []

US_INDEX = 0
CRYPTO_INDEX = 0

US_LAST_LOAD = 0
CRYPTO_LAST_LOAD = 0

US_CHAT_IDS = set()
CRYPTO_CHAT_IDS = set()
TASI_CHAT_IDS = set()

ALERT_CACHE = {}

CATALOG_LOCK = asyncio.Lock()

# ============================================================
# أدوات
# ============================================================

def number(value, default=0.0):
    try:
        return float(value)
    except:
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

        diff = values[i] - values[i - 1]

        if diff > 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def atr(rows, period=14):

    if len(rows) < period + 1:
        return 0.0

    true_ranges = []

    for i in range(1, len(rows)):

        high = number(rows[i].get("high"))
        low = number(rows[i].get("low"))
        previous_close = number(rows[i - 1].get("close"))

        tr = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close)
        )

        true_ranges.append(tr)

    return sum(true_ranges[-period:]) / period


def volume_format(value):

    value = number(value)

    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"

    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"

    if value >= 1_000:
        return f"{value / 1_000:.2f}K"

    return f"{value:.0f}"


# ============================================================
# Twelve Data
# ============================================================

async def td_request(session, endpoint, params):

    if not API_KEY:
        print("ℹ️ TWELVE_DATA_API_KEY غير موجود")
        return None

    query = dict(params)
    query["apikey"] = API_KEY

    try:

        async with session.get(
            TD_URL + endpoint,
            params=query,
            timeout=aiohttp.ClientTimeout(total=25)
        ) as response:

            text = await response.text()

            if response.status == 429:

                print("ℹ️ Twelve Data: حد الدقيقة ممتلئ، الانتظار للدقيقة التالية")
                return None

            if response.status != 200:

                print(
                    f"ℹ️ Twelve Data HTTP {response.status}: "
                    f"{text[:200]}"
                )

                return None

            try:
                data = json.loads(text)
            except:
                return None

            if isinstance(data, dict) and data.get("status") == "error":

                print(
                    "ℹ️ Twelve Data: "
                    + str(data.get("message", "خطأ غير معروف"))
                )

                return None

            return data

    except asyncio.TimeoutError:

        print("ℹ️ Twelve Data: انتهت مهلة الطلب")
        return None

    except Exception as error:

        print(f"ℹ️ Twelve Data: {error}")
        return None


# ============================================================
# تحميل الأسهم الأمريكية
# ============================================================

async def load_us_symbols(session):

    global US_SYMBOLS
    global US_LAST_LOAD

    if US_SYMBOLS and time.time() - US_LAST_LOAD < CATALOG_REFRESH:
        return True

    async with CATALOG_LOCK:

        if US_SYMBOLS and time.time() - US_LAST_LOAD < CATALOG_REFRESH:
            return True

        print("📚 تحميل قائمة الأسهم الأمريكية...")

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
            return False

        rows = data.get("data", [])

        symbols = []

        for item in rows:

            symbol = str(item.get("symbol", "")).strip()
            exchange = str(item.get("exchange", "")).strip()

            if symbol and exchange:
                symbols.append(symbol)

        # إزالة التكرار
        symbols = list(dict.fromkeys(symbols))

        if symbols:

            US_SYMBOLS = symbols
            US_LAST_LOAD = time.time()

            print(
                f"🇺🇸 تم تحميل {len(US_SYMBOLS)} رمز أمريكي"
            )

            return True

        return False


# ============================================================
# تحميل العملات الرقمية
# ============================================================

async def load_crypto_symbols(session):

    global CRYPTO_SYMBOLS
    global CRYPTO_LAST_LOAD

    if CRYPTO_SYMBOLS and time.time() - CRYPTO_LAST_LOAD < CATALOG_REFRESH:
        return True

    async with CATALOG_LOCK:

        if CRYPTO_SYMBOLS and time.time() - CRYPTO_LAST_LOAD < CATALOG_REFRESH:
            return True

        print("📚 تحميل قائمة العملات الرقمية...")

        data = await td_request(
            session,
            "/cryptocurrencies",
            {
                "currency": "USD",
                "outputsize": 5000
            }
        )

        if not data:
            return False

        rows = data.get("data", [])

        symbols = []

        for item in rows:

            symbol = str(item.get("symbol", "")).strip()

            if symbol:
                symbols.append(symbol)

        symbols = list(dict.fromkeys(symbols))

        if symbols:

            CRYPTO_SYMBOLS = symbols
            CRYPTO_LAST_LOAD = time.time()

            print(
                f"🪙 تم تحميل {len(CRYPTO_SYMBOLS)} عملة"
            )

            return True

        return False


# ============================================================
# طلب بيانات مجموعة
# ============================================================

async def get_batch_history(session, symbols):

    if not symbols:
        return {}

    symbol_string = ",".join(symbols)

    data = await td_request(
        session,
        "/time_series",
        {
            "symbol": symbol_string,
            "interval": "1min",
            "outputsize": 60
        }
    )

    if not data:
        return {}

    # إذا رمز واحد
    if len(symbols) == 1:

        if "values" in data:
            return {
                symbols[0]: data
            }

        return {}

    result = {}

    for symbol, packet in data.items():

        if isinstance(packet, dict) and "values" in packet:
            result[symbol] = packet

    return result


# ============================================================
# التحليل الذكي
# ============================================================

def analyze_symbol(symbol, packet):

    values = packet.get("values", [])

    if len(values) < 30:
        return None

    rows = list(reversed(values))

    closes = [
        number(row.get("close"))
        for row in rows
    ]

    if not closes:
        return None

    price = closes[-1]

    ema8 = ema(closes, 8)
    ema21 = ema(closes, 21)
    ema50 = ema(closes, 50)

    rsi14 = rsi(closes, 14)

    atr14 = atr(rows, 14)

    previous = closes[-2] if len(closes) >= 2 else price

    change = 0

    if previous:
        change = ((price - previous) / previous) * 100

    volumes = [
        number(row.get("volume"))
        for row in rows[-20:]
    ]

    average_volume = (
        sum(volumes) / len(volumes)
        if volumes
        else 0
    )

    current_volume = number(
        rows[-1].get("volume")
    )

    volume_strength = 1

    if average_volume > 0:
        volume_strength = current_volume / average_volume

    # ========================================================
    # قوة الإشارة
    # ========================================================

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

    score = max(0, min(100, score))

    # ========================================================
    # إشارة شراء / بيع قوية
    # ========================================================

    if score >= 80:

        signal = "🟢⬆️ شراء قوي"
        side = "BUY"

    elif score <= 20:

        signal = "🔴⬇️ بيع قوي"
        side = "SELL"

    else:

        return None

    highs = [
        number(row.get("high"))
        for row in rows[-20:]
    ]

    lows = [
        number(row.get("low"))
        for row in rows[-20:]
    ]

    support = min(lows) if lows else price
    resistance = max(highs) if highs else price

    buy_power = round(score)

    sell_power = 100 - buy_power

    return {
        "symbol": symbol,
        "price": price,
        "change": change,
        "score": score,
        "signal": signal,
        "side": side,
        "buy": buy_power,
        "sell": sell_power,
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
# رسالة الإشارة
# ============================================================

def build_signal_message(data, market):

    price = data["price"]
    atr14 = data["atr"]

    if data["side"] == "BUY":

        targets = [
            price + atr14 * i
            for i in range(1, 9)
        ]

    else:

        targets = [
            price - atr14 * i
            for i in range(1, 9)
        ]

    targets_text = "\n".join(
        f"{i}️⃣ {targets[i-1]:.4f}"
        for i in range(1, 9)
    )

    return f"""💀🚀 AI PRO MAX SIGNAL

{market}

<b>{data["symbol"]}</b>

{data["signal"]}

💰 السعر: {price:.4f}
📈 التغير: {data["change"]:+.2f}%

🎯 قوة الإشارة: {data["score"]:.0f}/100

🟢 قوة الشراء: {data["buy"]}%
🔴 قوة البيع: {data["sell"]}%

📊 قوة الحجم: {data["volume_strength"]:.2f}x
📦 الحجم: {volume_format(data["volume"])}

EMA 8: {data["ema8"]:.4f}
EMA 21: {data["ema21"]:.4f}
EMA 50: {data["ema50"]:.4f}

RSI 14: {data["rsi"]:.1f}
ATR 14: {atr14:.4f}

🟦 الدعم: {data["support"]:.4f}
🟥 المقاومة: {data["resistance"]:.4f}

🎯 أهداف ATR:

{targets_text}

⏱️ الفحص تلقائي كل دقيقتين
🤖 AI PRO MAX"""


# ============================================================
# Telegram
# ============================================================

async def telegram_send(
    session,
    token,
    chat_id,
    message
):

    if not token or not chat_id:
        return False

    url = f"{TG_URL}/bot{token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:

        async with session.post(
            url,
            json=payload,
            timeout=15
        ) as response:

            return response.status == 200

    except:
        return False


async def broadcast(
    session,
    token,
    chat_ids,
    message
):

    if not token:
        return

    if not chat_ids:
        return

    for chat_id in list(chat_ids):

        await telegram_send(
            session,
            token,
            chat_id,
            message
        )

        await asyncio.sleep(0.15)


# ============================================================
# منع تكرار التنبيه
# ============================================================

def can_alert(symbol, side):

    key = f"{symbol}:{side}"

    now = time.time()

    previous = ALERT_CACHE.get(key, 0)

    if now - previous < ALERT_COOLDOWN:
        return False

    ALERT_CACHE[key] = now

    return True


# ============================================================
# فحص السوق الأمريكي
# ============================================================

async def scan_us(session):

    global US_INDEX

    if not US_SYMBOLS:

        loaded = await load_us_symbols(session)

        if not loaded:
            print("ℹ️ الولايات المتحدة: القائمة غير جاهزة")
            return

    batch = []

    for _ in range(BATCH_SIZE):

        if not US_SYMBOLS:
            break

        symbol = US_SYMBOLS[
            US_INDEX % len(US_SYMBOLS)
        ]

        US_INDEX += 1

        batch.append(symbol)

    if not batch:
        return

    print(
        "🇺🇸 فحص:",
        ", ".join(batch)
    )

    packets = await get_batch_history(
        session,
        batch
    )

    for symbol in batch:

        packet = packets.get(symbol)

        if not packet:
            continue

        result = analyze_symbol(
            symbol,
            packet
        )

        if not result:
            continue

        if not can_alert(
            symbol,
            result["side"]
        ):
            continue

        message = build_signal_message(
            result,
            "🇺🇸 السوق الأمريكي"
        )

        await broadcast(
            session,
            US_TOKEN,
            US_CHAT_IDS,
            message
        )

        print(
            f"🚨 US SIGNAL {symbol} "
            f"{result['side']} "
            f"{result['score']:.0f}/100"
        )


# ============================================================
# فحص العملات
# ============================================================

async def scan_crypto(session):

    global CRYPTO_INDEX

    if not CRYPTO_SYMBOLS:

        loaded = await load_crypto_symbols(session)

        if not loaded:
            print("ℹ️ CRYPTO: القائمة غير جاهزة")
            return

    batch = []

    for _ in range(BATCH_SIZE):

        if not CRYPTO_SYMBOLS:
            break

        symbol = CRYPTO_SYMBOLS[
            CRYPTO_INDEX % len(CRYPTO_SYMBOLS)
        ]

        CRYPTO_INDEX += 1

        batch.append(symbol)

    if not batch:
        return

    print(
        "🪙 فحص:",
        ", ".join(batch)
    )

    packets = await get_batch_history(
        session,
        batch
    )

    for symbol in batch:

        packet = packets.get(symbol)

        if not packet:
            continue

        result = analyze_symbol(
            symbol,
            packet
        )

        if not result:
            continue

        if not can_alert(
            symbol,
            result["side"]
        ):
            continue

        message = build_signal_message(
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
            f"🚨 CRYPTO SIGNAL {symbol} "
            f"{result['side']} "
            f"{result['score']:.0f}/100"
        )


# ============================================================
# رسالة التشغيل
# ============================================================

def startup_message(market):

    return f"""💀🚀 AI PRO MAX

✅ البوت يعمل الآن
🔄 الفحص تلقائي وكامل
⏱️ الفحص كل دقيقتين

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
# Telegram Webhook
# ============================================================

async def telegram_webhook(request):

    market = request.match_info.get("market", "")

    try:
        update = await request.json()
    except:
        return web.json_response({"ok": True})

    message = update.get("message", {})

    chat = message.get("chat", {})

    chat_id = chat.get("id")

    text = str(
        message.get("text", "")
    ).strip()

    if not chat_id:
        return web.json_response({"ok": True})

    if text.startswith("/start"):

        if market == "us":

            US_CHAT_IDS.add(chat_id)

            await telegram_send(
                request.app["session"],
                US_TOKEN,
                chat_id,
                startup_message("🇺🇸 US")
            )

        elif market == "crypto":

            CRYPTO_CHAT_IDS.add(chat_id)

            await telegram_send(
                request.app["session"],
                CRYPTO_TOKEN,
                chat_id,
                startup_message("🪙 CRYPTO")
            )

        elif market == "tasi":

            TASI_CHAT_IDS.add(chat_id)

            await telegram_send(
                request.app["session"],
                TASI_TOKEN,
                chat_id,
                startup_message("🇸🇦 TASI")
            )

    return web.json_response({"ok": True})


# ============================================================
# Health
# ============================================================

async def health(request):

    return web.json_response({
        "status": "online",
        "engine": "AI PRO MAX",
        "scan_seconds": SCAN_SECONDS,
        "us_symbols": len(US_SYMBOLS),
        "crypto_symbols": len(CRYPTO_SYMBOLS),
        "time": datetime.now(
            timezone.utc
        ).isoformat()
    })


# ============================================================
# إعداد Webhook
# ============================================================

async def setup_webhook(
    session,
    token,
    path
):

    if not token:
        return

    domain = (
        os.getenv("RAILWAY_PUBLIC_DOMAIN")
        or os.getenv("RAILWAY_STATIC_URL")
        or ""
    )

    domain = domain.replace(
        "https://",
        ""
    ).replace(
        "http://",
        ""
    ).rstrip("/")

    if not domain:
        print(
            "ℹ️ لم يتم العثور على RAILWAY_PUBLIC_DOMAIN"
        )
        return

    webhook_url = (
        f"https://{domain}"
        f"/telegram/{path}"
    )

    url = f"{TG_URL}/bot{token}/setWebhook"

    try:

        async with session.post(
            url,
            json={
                "url": webhook_url,
                "drop_pending_updates": True
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
            f"ℹ️ Telegram Webhook {path}: "
            f"{error}"
        )


# ============================================================
# محرك الفحص
# ============================================================

async def scanner():

    global US_LAST_LOAD
    global CRYPTO_LAST_LOAD

    connector = aiohttp.TCPConnector(
        limit=20
    )

    async with aiohttp.ClientSession(
        connector=connector
    ) as session:

        # --------------------------------------------
        # تحميل القوائم بشكل متسلسل
        # --------------------------------------------

        print("📚 بدء تجهيز القوائم...")

        await load_us_symbols(
            session
        )

        # لا نطلب طلبين بنفس الدقيقة
        print(
            "⏳ تجهيز CRYPTO بعد فترة حماية API..."
        )

        await asyncio.sleep(65)

        await load_crypto_symbols(
            session
        )

        print("")
        print("💀🚀 AI PRO MAX")
        print("🟢 النظام يعمل 24/7")
        print("⏱️ الفحص كل 120 ثانية")
        print(
            f"🇺🇸 US: {len(US_SYMBOLS)}"
        )
        print(
            f"🪙 CRYPTO: {len(CRYPTO_SYMBOLS)}"
        )
        print("")

        # --------------------------------------------
        # التشغيل المستمر
        # --------------------------------------------

        market_turn = 0

        while True:

            cycle_start = time.time()

            try:

                # تبديل السوق كل دورة
                if market_turn == 0:

                    await scan_us(
                        session
                    )

                    market_turn = 1

                else:

                    await scan_crypto(
                        session
                    )

                    market_turn = 0

            except Exception as error:

                print(
                    f"ℹ️ خطأ في دورة الفحص: {error}"
                )

            elapsed = time.time() - cycle_start

            wait_time = max(
                1,
                SCAN_SECONDS - elapsed
            )

            print(
                f"⏱️ الدورة القادمة بعد "
                f"{wait_time:.0f} ثانية"
            )

            await asyncio.sleep(
                wait_time
            )


# ============================================================
# تشغيل التطبيق
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


async def main():

    app = await create_app()

    session = app["session"]

    # Webhooks
    await setup_webhook(
        session,
        US_TOKEN,
        "us"
    )

    await setup_webhook(
        session,
        CRYPTO_TOKEN,
        "crypto"
    )

    await setup_webhook(
        session,
        TASI_TOKEN,
        "tasi"
    )

    # الفحص بالخلفية
    asyncio.create_task(
        scanner()
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

    try:

        while True:
            await asyncio.sleep(3600)

    finally:

        await session.close()
        await runner.cleanup()


if __name__ == "__main__":

    try:
        asyncio.run(main())

    except KeyboardInterrupt:

        print(
            "AI PRO MAX stopped"
        )