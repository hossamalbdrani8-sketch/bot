 ============================================================
# 💀🚀 AI PRO MAX
# TWELVE DATA EDITION
# PYTHON - CLEAN BUILD v2
# ============================================================

import os
import asyncio
import time
from datetime import datetime, timezone

import aiohttp
from aiohttp import web


# ============================================================
# ⚙️ RAILWAY VARIABLES
# ============================================================

TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()

TASI_TOKEN = os.getenv("TASI_TOKEN", "").strip()
US_TOKEN = os.getenv("US_TOKEN", "").strip()
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN", "").strip()

PORT = int(os.getenv("PORT", "8080"))

SCAN_SECONDS = int(os.getenv("SCAN_SECONDS", "600"))
MIN_US_PRICE = float(os.getenv("MIN_US_PRICE", "0.20"))

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
MAX_CONNECTIONS = int(os.getenv("MAX_CONNECTIONS", "10"))
SIGNAL_COOLDOWN = int(os.getenv("SIGNAL_COOLDOWN", "1800"))

# حماية من استنزاف الحصة: لا نسمح بدورات متداخلة ولا نعيد طلب التاريخ إلا عند انتهاء الكاش.
SCAN_LOCK = asyncio.Lock()

# عدد الرموز في الفحص.
# الخطة المجانية لا تسمح بفحص السوق الكامل كل دقيقتين.
MAX_SYMBOLS_PER_MARKET = int(
    os.getenv("MAX_SYMBOLS_PER_MARKET", "100")
)

CATALOG_PAGE_SIZE = 100
SYMBOL_REFRESH_SECONDS = int(
    os.getenv("SYMBOL_REFRESH_SECONDS", "21600")
)


# ============================================================
# 🧠 MEMORY
# ============================================================

symbols_cache = {
    "TASI": [],
    "US": [],
    "CRYPTO": [],
}

symbols_cache_time = {
    "TASI": 0.0,
    "US": 0.0,
    "CRYPTO": 0.0,
}

history_cache = {}
last_signal = {}

telegram_chats = {
    "TASI": set(),
    "US": set(),
    "CRYPTO": set(),
}

scan_number = 0
session = None


# ============================================================
# 📝 LOG
# ============================================================

def log(message):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"{now} UTC | {message}", flush=True)


# ============================================================
# 🌐 HTTP SESSION
# ============================================================

async def get_session():
    global session

    if session is None or session.closed:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

        connector = aiohttp.TCPConnector(
            limit=MAX_CONNECTIONS,
            ttl_dns_cache=300,
        )

        session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
        )

    return session


# ============================================================
# 🔐 TELEGRAM TOKEN
# ============================================================

def token_for_market(market):
    return {
        "TASI": TASI_TOKEN,
        "US": US_TOKEN,
        "CRYPTO": CRYPTO_TOKEN,
    }.get(market, "")


# ============================================================
# 🌐 TWELVE DATA
# ============================================================

async def twelve(endpoint, params=None):
    if not TWELVE_DATA_API_KEY:
        raise RuntimeError(
            "متغير TWELVE_DATA_API_KEY غير موجود"
        )

    s = await get_session()

    query = dict(params or {})
    query["apikey"] = TWELVE_DATA_API_KEY

    url = "https://api.twelvedata.com/" + endpoint.lstrip("/")

    async with s.get(url, params=query) as response:
        body = await response.text()

        try:
            data = await response.json(content_type=None)
        except Exception:
            raise RuntimeError(
                f"Twelve Data استجابة غير صالحة HTTP {response.status}: "
                f"{body[:300]}"
            )

        if response.status != 200:
            message = (
                data.get("message", body[:500])
                if isinstance(data, dict)
                else body[:500]
            )
            raise RuntimeError(
                f"Twelve Data HTTP {response.status}: {message}"
            )

        if isinstance(data, dict) and data.get("status") == "error":
            raise RuntimeError(
                str(data.get("message", "خطأ غير معروف"))
            )

        return data


# ============================================================
# 📦 EXTRACT CATALOG DATA
# ============================================================

def extract_catalog_rows(data):
    # Twelve Data يرجع الكتالوج داخل data.
    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    rows = data.get("data")

    if isinstance(rows, list):
        return rows

    rows = data.get("values")

    if isinstance(rows, list):
        return rows

    return []


# ============================================================
# 📋 STOCK CATALOG
# ============================================================

async def get_stock_symbols(market):
    log(f"📋 تحميل قائمة الرموز: {market}")

    if market == "US":
        params = {
            "country": "United States",
            "type": "Common Stock",
            "page": 1,
        }

    elif market == "TASI":
        params = {
            "exchange": "Saudi Exchange",
            "page": 1,
        }

    else:
        return []

    data = await twelve("stocks", params)
    rows = extract_catalog_rows(data)

    symbols = []

    for item in rows:
        if not isinstance(item, dict):
            continue

        symbol = str(item.get("symbol", "")).strip()

        if not symbol:
            continue

        symbols.append({
            "symbol": symbol,
            "name": str(item.get("name", symbol)).strip(),
            "exchange": str(item.get("exchange", "")).strip(),
            "mic_code": str(item.get("mic_code", "")).strip(),
            "country": str(item.get("country", "")).strip(),
        })

    unique = {}

    for item in symbols:
        key = (
            item["symbol"],
            item["exchange"],
        )
        unique[key] = item

    return list(unique.values())


# ============================================================
# 🪙 CRYPTO CATALOG
# ============================================================

async def get_crypto_symbols():
    log("📋 تحميل قائمة الرموز: CRYPTO")

    data = await twelve(
        "cryptocurrencies",
        {
            "page": 1,
        },
    )

    rows = extract_catalog_rows(data)

    symbols = []

    for item in rows:
        if not isinstance(item, dict):
            continue

        symbol = str(item.get("symbol", "")).strip()

        if not symbol:
            continue

        available = item.get("available_exchanges", [])

        if not isinstance(available, list):
            available = []

        symbols.append({
            "symbol": symbol,
            "name": str(
                item.get("currency_base", symbol)
            ).strip(),
            "exchange": (
                str(available[0]).strip()
                if available
                else ""
            ),
            "mic_code": "",
            "country": "",
        })

    unique = {}

    for item in symbols:
        unique[item["symbol"]] = item

    return list(unique.values())


# ============================================================
# 📦 LOAD SYMBOLS
# ============================================================

async def load_market_symbols(market, force=False):
    now = time.time()

    if (
        not force
        and symbols_cache[market]
        and now - symbols_cache_time[market]
        < SYMBOL_REFRESH_SECONDS
    ):
        return

    try:
        if market == "CRYPTO":
            symbols = await get_crypto_symbols()
        else:
            symbols = await get_stock_symbols(market)

        symbols_cache[market] = symbols[:MAX_SYMBOLS_PER_MARKET]
        symbols_cache_time[market] = now

        log(
            f"✅ {market}: "
            f"{len(symbols_cache[market])} رمز جاهز"
        )

        if symbols_cache[market]:
            preview = ", ".join(
                item["symbol"]
                for item in symbols_cache[market][:10]
            )
            log(
                f"🔎 {market} أول الرموز: "
                f"{preview}"
            )

    except Exception as exc:
        log(
            f"ℹ️ {market}: "
            f"تعذر تحميل القائمة: {exc}"
        )

        if not symbols_cache[market]:
            log(
                f"ℹ️ {market}: "
                "لا توجد قائمة سابقة للاستخدام"
            )


async def load_symbols(force=False):
    await asyncio.gather(
        load_market_symbols("TASI", force),
        load_market_symbols("US", force),
        load_market_symbols("CRYPTO", force),
        return_exceptions=True,
    )


# ============================================================
# 💰 QUOTE
# ============================================================

async def get_quote(item, market):
    symbol = item["symbol"]

    params = {
        "symbol": symbol,
    }

    exchange = item.get("exchange", "")

    # لا نفرض NASDAQ على جميع الأسهم الأمريكية.
    if exchange:
        params["exchange"] = exchange

    try:
        data = await twelve("quote", params)

        if not isinstance(data, dict):
            return None

        return data

    except Exception as exc:
        log(
            f"ℹ️ Quote {market} "
            f"{symbol}: {exc}"
        )
        return None


# ============================================================
# 📈 HISTORY
# ============================================================

async def get_history(item, market):
    symbol = item["symbol"]
    exchange = item.get("exchange", "")

    key = (
        market,
        symbol,
        exchange,
    )

    now = time.time()

    cached = history_cache.get(key)

    if cached:
        if now - cached["time"] < 21600:
            return cached["data"]

    params = {
        "symbol": symbol,
        "interval": "1day",
        "outputsize": 100,
    }

    if exchange:
        params["exchange"] = exchange

    try:
        data = await twelve(
            "time_series",
            params,
        )

        values = []

        if isinstance(data, dict):
            values = data.get("values", [])

        if not values:
            return []

        values = list(reversed(values))

        history_cache[key] = {
            "data": values,
            "time": now,
        }

        return values

    except Exception as exc:
        log(
            f"ℹ️ تاريخ {market} "
            f"{symbol}: {exc}"
        )
        return []


# ============================================================
# 📊 EMA
# ============================================================

def ema(values, period):
    if len(values) < period:
        return None

    result = sum(values[:period]) / period
    multiplier = 2 / (period + 1)

    for value in values[period:]:
        result = (
            (value - result) * multiplier
            + result
        )

    return result


# ============================================================
# 📊 RSI
# ============================================================

def rsi(values, period=14):
    if len(values) <= period:
        return None

    gains = []
    losses = []

    for i in range(1, len(values)):
        change = values[i] - values[i - 1]

        gains.append(max(change, 0))
        losses.append(max(-change, 0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (
            (avg_gain * (period - 1)) + gains[i]
        ) / period

        avg_loss = (
            (avg_loss * (period - 1)) + losses[i]
        ) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


# ============================================================
# 📐 ATR
# ============================================================

def atr(data, period=14):
    if len(data) < period + 1:
        return None

    trs = []
    previous_close = None

    for row in data:
        try:
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])
        except Exception:
            continue

        if high <= 0 or low <= 0 or close <= 0:
            continue

        if previous_close is None:
            tr = high - low
        else:
            tr = max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )

        trs.append(tr)
        previous_close = close

    if len(trs) < period:
        return None

    value = sum(trs[:period]) / period

    for tr in trs[period:]:
        value = (
            (value * (period - 1)) + tr
        ) / period

    return value


# ============================================================
# 🛡️ SUPPORT / RESISTANCE
# ============================================================

def support_resistance(data):
    if not data:
        return None, None

    recent = data[-30:]

    highs = []
    lows = []

    for row in recent:
        try:
            highs.append(float(row["high"]))
            lows.append(float(row["low"]))
        except Exception:
            continue

    if not highs or not lows:
        return None, None

    return min(lows), max(highs)


# ============================================================
# 📊 VOLUME
# ============================================================

def volume_strength(data):
    if len(data) < 21:
        return 1.0

    values = []

    for row in data[-21:-1]:
        try:
            value = float(row.get("volume", 0))

            if value > 0:
                values.append(value)

        except Exception:
            pass

    if not values:
        return 1.0

    average = sum(values) / len(values)

    try:
        current = float(data[-1].get("volume", 0))
    except Exception:
        return 1.0

    if average <= 0:
        return 1.0

    return current / average


# ============================================================
# 🧠 ANALYZE
# ============================================================

def analyze(market, quote, history):
    try:
        symbol = str(
            quote.get("symbol", "")
        ).strip()

        price = float(
            quote.get("close", 0)
        )

        change = float(
            quote.get("percent_change", 0)
        )

    except Exception:
        return None

    if not symbol or price <= 0:
        return None

    if market == "US" and price < MIN_US_PRICE:
        return None

    if len(history) < 60:
        return None

    clean = []
    closes = []

    for row in history:
        try:
            close = float(row["close"])
            float(row["high"])
            float(row["low"])

            if close <= 0:
                continue

            clean.append(row)
            closes.append(close)

        except Exception:
            continue

    if len(closes) < 60:
        return None

    closes_with_current = closes + [price]

    ema8 = ema(closes_with_current, 8)
    ema21 = ema(closes_with_current, 21)
    ema50 = ema(closes_with_current, 50)

    rsi14 = rsi(closes_with_current, 14)
    atr14 = atr(clean, 14)

    support, resistance = support_resistance(clean)
    volume = volume_strength(clean)

    if any(
        x is None
        for x in [
            ema8,
            ema21,
            ema50,
            rsi14,
            atr14,
        ]
    ):
        return None

    # ========================================================
    # 🧠 POWER ENGINE
    # ========================================================

    buy = 0
    sell = 0

    if price > ema8:
        buy += 1
    else:
        sell += 1

    if ema8 > ema21:
        buy += 1
    else:
        sell += 1

    if ema21 > ema50:
        buy += 1
    else:
        sell += 1

    if rsi14 >= 55:
        buy += 1
    elif rsi14 <= 45:
        sell += 1

    if support is not None:
        if price > support:
            buy += 1
        else:
            sell += 1

    if resistance is not None:
        if price < resistance:
            sell += 1
        else:
            buy += 1

    if volume >= 1.5:
        if buy >= sell:
            buy += 1
        else:
            sell += 1

    total = max(buy + sell, 1)

    buy_power = round(buy / total * 100)
    sell_power = round(sell / total * 100)

    if buy_power >= 75:
        signal = "BUY"
        strength = buy_power
        trend = "صاعد قوي"

    elif sell_power >= 75:
        signal = "SELL"
        strength = sell_power
        trend = "هابط قوي"

    else:
        return None

    # ========================================================
    # 🎯 8 ATR TARGETS
    # ========================================================

    multipliers = [
        1.0,
        1.5,
        2.0,
        2.5,
        3.0,
        3.5,
        4.0,
        4.5,
    ]

    targets = []

    for multiplier in multipliers:
        if signal == "BUY":
            target = price + (atr14 * multiplier)
        else:
            target = price - (atr14 * multiplier)

        targets.append(target)

    return {
        "market": market,
        "symbol": symbol,
        "name": quote.get("name", symbol),
        "price": price,
        "change": change,
        "signal": signal,
        "strength": strength,
        "buy_power": buy_power,
        "sell_power": sell_power,
        "volume": volume,
        "ema8": ema8,
        "ema21": ema21,
        "ema50": ema50,
        "rsi": rsi14,
        "atr": atr14,
        "support": support,
        "resistance": resistance,
        "trend": trend,
        "targets": targets,
    }


# ============================================================
# 🔢 NUMBER
# ============================================================

def number(value):
    if value is None:
        return "—"

    value = float(value)

    if abs(value) >= 1000:
        return f"{value:,.2f}"

    if abs(value) >= 1:
        return f"{value:.2f}"

    return f"{value:.4f}"


# ============================================================
# 📩 TELEGRAM
# ============================================================

async def telegram_send(token, chat_id, text):
    if not token:
        return False

    s = await get_session()

    url = (
        "https://api.telegram.org/"
        f"bot{token}/sendMessage"
    )

    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }

    try:
        async with s.post(url, json=payload) as response:
            return response.status == 200

    except Exception as exc:
        log(f"ℹ️ Telegram: {exc}")
        return False


# ============================================================
# 📣 SIGNAL
# ============================================================

async def send_signal(signal):
    market = signal["market"]
    token = token_for_market(market)

    if not token:
        return

    if signal["signal"] == "BUY":
        arrow = "🟢⬆️"
        title = "شراء قوي"
    else:
        arrow = "🔴⬇️"
        title = "بيع قوي"

    market_name = {
        "TASI": "🇸🇦 السوق السعودي (TASI)",
        "US": "🇺🇸 السوق الأمريكي (US)",
        "CRYPTO": "🪙 العملات الرقمية (CRYPTO)",
    }[market]

    target_lines = []

    for index, target in enumerate(
        signal["targets"],
        1,
    ):
        if signal["signal"] == "BUY":
            percentage = (
                target / signal["price"] - 1
            ) * 100
        else:
            percentage = (
                1 - target / signal["price"]
            ) * 100

        sign = "+" if percentage >= 0 else ""

        target_lines.append(
            f"TP{index}: {number(target)} "
            f"({sign}{percentage:.1f}%)"
        )

    text = (
        "💀🚀 AI PRO MAX SIGNAL\n\n"
        f"{market_name}\n\n"
        f"{signal['symbol']}\n"
        f"{signal['name']}\n\n"
        f"{arrow} {title}\n\n"
        f"💰 السعر: {number(signal['price'])}\n"
        f"📈 التغير: {signal['change']:+.2f}%\n"
        f"🎯 قوة الإشارة: {signal['strength']}/100\n"
        f"🟢 قوة الشراء: {signal['buy_power']}%\n"
        f"🔴 قوة البيع: {signal['sell_power']}%\n"
        f"📊 قوة الحجم: {signal['volume']:.1f}x\n\n"
        f"EMA 8: {number(signal['ema8'])}\n"
        f"EMA 21: {number(signal['ema21'])}\n"
        f"EMA 50: {number(signal['ema50'])}\n"
        f"RSI 14: {number(signal['rsi'])}\n"
        f"ATR 14: {number(signal['atr'])}\n\n"
        f"🛡️ الدعم: {number(signal['support'])}\n"
        f"🔺 المقاومة: {number(signal['resistance'])}\n"
        f"📊 الاتجاه: {signal['trend']}\n\n"
        "🎯 أهداف ATR الثمانية:\n"
        + "\n".join(target_lines)
    )

    chats = list(telegram_chats[market])

    if not chats:
        return

    await asyncio.gather(
        *[
            telegram_send(token, chat_id, text)
            for chat_id in chats
        ],
        return_exceptions=True,
    )


# ============================================================
# 🚫 DUPLICATE
# ============================================================

def can_send(signal):
    key = (
        signal["market"],
        signal["symbol"],
        signal["signal"],
    )

    now = time.time()
    previous = last_signal.get(key, 0)

    if now - previous < SIGNAL_COOLDOWN:
        return False

    last_signal[key] = now
    return True


# ============================================================
# 🔍 PROCESS
# ============================================================

async def process_symbol(market, item):
    quote = await get_quote(item, market)

    if not quote:
        return

    try:
        price = float(
            quote.get("close", 0)
        )
    except Exception:
        return

    if price <= 0:
        return

    if market == "US" and price < MIN_US_PRICE:
        return

    history = await get_history(item, market)

    if not history:
        return

    signal = analyze(
        market,
        quote,
        history,
    )

    if not signal:
        return

    if not can_send(signal):
        return

    await send_signal(signal)


# ============================================================
# 🔎 MARKET SCAN
# ============================================================

async def scan_market(market):
    symbols = symbols_cache.get(market, [])

    if not symbols:
        log(
            f"ℹ️ {market}: "
            "لا توجد رموز محملة"
        )
        return

    log(
        f"🔎 {market}: "
        f"فحص {len(symbols)} رمز"
    )

    semaphore = asyncio.Semaphore(2)

    async def worker(item):
        async with semaphore:
            try:
                await process_symbol(
                    market,
                    item,
                )
            except Exception as exc:
                log(
                    f"ℹ️ {market} "
                    f"{item.get('symbol', '')}: "
                    f"{exc}"
                )

    await asyncio.gather(
        *[
            worker(item)
            for item in symbols
        ],
        return_exceptions=True,
    )

    log(
        f"✅ {market}: "
        "اكتمل الفحص"
    )


# ============================================================
# 🔄 FULL SCAN
# ============================================================

async def full_scan():
    global scan_number

    if SCAN_LOCK.locked():
        log("⏭️ تم تخطي الدورة: الدورة السابقة ما زالت تعمل")
        return

    async with SCAN_LOCK:
        await _full_scan_locked()


async def _full_scan_locked():
    global scan_number

    scan_number += 1
    started = time.monotonic()

    log("=" * 60)
    log(
        f"💀🚀 AI PRO MAX SCAN "
        f"#{scan_number}"
    )
    log("=" * 60)

    await load_symbols(force=False)

    await asyncio.gather(
        scan_market("TASI"),
        scan_market("US"),
        scan_market("CRYPTO"),
        return_exceptions=True,
    )

    elapsed = time.monotonic() - started

    log(
        f"✅ انتهت الدورة خلال "
        f"{elapsed:.2f} ثانية"
    )


# ============================================================
# 🤖 START MESSAGE
# ============================================================

def startup_message(market):
    market_name = {
        "TASI": "🇸🇦 السوق السعودي",
        "US": "🇺🇸 السوق الأمريكي",
        "CRYPTO": "🪙 العملات الرقمية",
    }[market]

    return (
        "💀🚀 AI PRO MAX\n\n"
        "✅ البوت يعمل الآن\n"
        "🔄 الفحص تلقائي وكامل\n"
        f"⏱️ الفحص كل {SCAN_SECONDS // 60 if SCAN_SECONDS >= 60 else SCAN_SECONDS} {"دقيقة" if SCAN_SECONDS >= 60 else "ثانية"}\n\n"
        f"📊 السوق: {market_name}\n\n"
        "🧠 المحرك الذكي:\n"
        "• EMA 8\n"
        "• EMA 21\n"
        "• EMA 50\n"
        "• RSI 14\n"
        "• ATR 14\n"
        "• دعم\n"
        "• مقاومة\n"
        "• قوة الحجم\n"
        "• قوة الشراء\n"
        "• قوة البيع\n"
        "• 8 أهداف ATR\n"
        "• منع تكرار التنبيهات\n\n"
        "🟢⬆️ سهم أخضر = صعود قوي\n"
        "🔴⬇️ سهم أحمر = هبوط قوي\n\n"
        "🤖 لا تحتاج إلى تشغيل الفحص يدويًا.\n\n"
        "📡 مصدر البيانات:\n"
        "Twelve Data فقط"
    )


# ============================================================
# 📲 TELEGRAM WEBHOOK
# ============================================================

async def telegram_webhook(request):
    path = request.path.lower()

    if path.endswith("/telegram/tasi"):
        market = "TASI"
    elif path.endswith("/telegram/us"):
        market = "US"
    elif path.endswith("/telegram/crypto"):
        market = "CRYPTO"
    else:
        return web.Response(status=200)

    token = token_for_market(market)

    if not token:
        return web.Response(status=200)

    try:
        update = await request.json()
    except Exception:
        return web.Response(status=200)

    message = update.get("message", {})
    chat = message.get("chat", {})
    chat_id = chat.get("id")

    if chat_id is None:
        return web.Response(status=200)

    telegram_chats[market].add(int(chat_id))

    text = str(
        message.get("text", "")
    )

    if text.startswith("/start"):
        await telegram_send(
            token,
            chat_id,
            startup_message(market),
        )

    return web.Response(status=200)


# ============================================================
# ❤️ HEALTH
# ============================================================

async def health(request):
    return web.json_response({
        "status": "ok",
        "system": "AI PRO MAX",
        "data": "Twelve Data",
        "markets": [
            "TASI",
            "US",
            "CRYPTO",
        ],
        "scan_seconds": SCAN_SECONDS,
        "symbols": {
            "TASI": len(symbols_cache["TASI"]),
            "US": len(symbols_cache["US"]),
            "CRYPTO": len(symbols_cache["CRYPTO"]),
        },
    })


# ============================================================
# 🔗 WEBHOOK
# ============================================================

async def set_webhook(market, token, base_url):
    if not token:
        return

    url = (
        "https://api.telegram.org/"
        f"bot{token}/setWebhook"
    )

    webhook_url = (
        f"{base_url.rstrip('/')}/telegram/"
        f"{market.lower()}"
    )

    try:
        s = await get_session()

        async with s.post(
            url,
            json={
                "url": webhook_url,
                "drop_pending_updates": True,
            },
        ) as response:
            body = await response.text()

            if response.status == 200:
                log(
                    f"Telegram Webhook: "
                    f"{market.lower()} ON"
                )
            else:
                log(
                    f"ℹ️ Telegram Webhook "
                    f"{market.lower()}: "
                    f"HTTP {response.status} "
                    f"{body[:200]}"
                )

    except Exception as exc:
        log(
            f"ℹ️ Webhook {market}: "
            f"{exc}"
        )


# ============================================================
# 🌐 SERVER
# ============================================================

async def start_server():
    app = web.Application()

    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    app.router.add_post(
        "/telegram/tasi",
        telegram_webhook,
    )

    app.router.add_post(
        "/telegram/us",
        telegram_webhook,
    )

    app.router.add_post(
        "/telegram/crypto",
        telegram_webhook,
    )

    runner = web.AppRunner(app)

    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        PORT,
    )

    await site.start()

    log(
        f"🚀 AI PRO MAX يعمل "
        f"على PORT {PORT}"
    )

    return runner


# ============================================================
# 🔁 SCANNER LOOP
# ============================================================

async def scanner_loop():
    await asyncio.sleep(3)

    while True:
        started = time.monotonic()

        try:
            await full_scan()

        except Exception as exc:
            log(
                f"ℹ️ خطأ في دورة الفحص: "
                f"{exc}"
            )

        elapsed = time.monotonic() - started

        wait = max(
            1,
            SCAN_SECONDS - int(elapsed),
        )

        log(
            f"⏱️ الدورة القادمة خلال "
            f"{wait} ثانية"
        )

        await asyncio.sleep(wait)


# ============================================================
# 🚀 MAIN
# ============================================================

async def main():
    log("=" * 60)
    log("💀🚀 AI PRO MAX")
    log("=" * 60)

    log(
        "🤖 TASI BOT: "
        + ("ON" if TASI_TOKEN else "OFF")
    )

    log(
        "🤖 US BOT: "
        + ("ON" if US_TOKEN else "OFF")
    )

    log(
        "🤖 CRYPTO BOT: "
        + ("ON" if CRYPTO_TOKEN else "OFF")
    )

    log("🟢 النظام يعمل 24/7")

    log(
        f"⏱️ الفحص كل "
        f"{SCAN_SECONDS} ثانية"
    )

    log("📡 مصدر البيانات: Twelve Data")
    log("🛡️ حماية الحصة: تفعيل الكاش ومنع تداخل دورات الفحص")

    log(
        f"📊 الحد لكل سوق: "
        f"{MAX_SYMBOLS_PER_MARKET} رمز"
    )

    log(
        f"📚 تحديث قائمة الرموز كل "
        f"{SYMBOL_REFRESH_SECONDS} ثانية"
    )

    log("=" * 60)

    if not TWELVE_DATA_API_KEY:
        log(
            "ℹ️ مفتاح Twelve Data غير موجود"
        )

    runner = await start_server()

    domain = os.getenv(
        "RAILWAY_PUBLIC_DOMAIN",
        "",
    ).strip()

    if not domain:
        domain = os.getenv(
            "RAILWAY_STATIC_URL",
            "",
        ).strip()

    if domain:
        if not domain.startswith("http"):
            domain = "https://" + domain

        await asyncio.gather(
            set_webhook(
                "TASI",
                TASI_TOKEN,
                domain,
            ),
            set_webhook(
                "US",
                US_TOKEN,
                domain,
            ),
            set_webhook(
                "CRYPTO",
                CRYPTO_TOKEN,
                domain,
            ),
        )

    else:
        log(
            "ℹ️ لا يوجد Railway Public Domain"
        )

    try:
        await scanner_loop()

    finally:
        await runner.cleanup()

        if session and not session.closed:
            await session.close()


# ============================================================
# ▶️ START
# ============================================================

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass