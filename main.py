
# ============================================================
# 💀🚀 AI PRO MAX
# PYTHON - FULL MARKET AUTONOMOUS SCANNER
# ============================================================
# الأسواق:
# 🇸🇦 TASI
# 🇺🇸 US
# 🪙 CRYPTO
#
# الفحص:
# ⏱️ كل دقيقتين
#
# مصدر البيانات:
# EODHD فقط
#
# Telegram:
# Webhook - بدون Polling
#
# التكوينات المطلوبة في Railway:
# TASI_CONFIG
# US_CONFIG
# CRYPTO_CONFIG
# EODHD_API_KEY
# ============================================================

import os
import asyncio
import time
import math
import json
from collections import deque
from datetime import datetime, timezone

import aiohttp
from aiohttp import web


# ============================================================
# ⚙️ CONFIG
# ============================================================

EODHD_API_KEY = os.getenv("EODHD_API_KEY", "").strip()

TASI_TOKEN = os.getenv("TASI_CONFIG", "").strip()
US_TOKEN = os.getenv("US_CONFIG", "").strip()
CRYPTO_TOKEN = os.getenv("CRYPTO_CONFIG", "").strip()

PORT = int(os.getenv("PORT", "8080"))

SCAN_SECONDS = 120

MIN_US_PRICE = 0.20

REQUEST_TIMEOUT = 25

MAX_CONNECTIONS = 50

SYMBOL_CACHE_SECONDS = 3600

HISTORY_CACHE_SECONDS = 21600

SIGNAL_COOLDOWN = 1800


# ============================================================
# 🧠 MEMORY
# ============================================================

symbols_cache = {
    "TASI": {
        "symbols": [],
        "updated": 0
    },
    "US": {
        "symbols": [],
        "updated": 0
    },
    "CRYPTO": {
        "symbols": [],
        "updated": 0
    }
}

history_cache = {}

last_signal = {}

telegram_chats = {
    "TASI": set(),
    "US": set(),
    "CRYPTO": set()
}

scan_number = 0


# ============================================================
# 🌐 HTTP SESSION
# ============================================================

session = None


async def get_session():
    global session

    if session is None or session.closed:

        timeout = aiohttp.ClientTimeout(
            total=REQUEST_TIMEOUT
        )

        connector = aiohttp.TCPConnector(
            limit=MAX_CONNECTIONS,
            ttl_dns_cache=300
        )

        session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector
        )

    return session


# ============================================================
# 📝 LOG
# ============================================================

def log(message):
    now = datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    print(f"{now} UTC | {message}", flush=True)


# ============================================================
# 🔐 TOKEN CHECK
# ============================================================

def token_for_market(market):

    if market == "TASI":
        return TASI_TOKEN

    if market == "US":
        return US_TOKEN

    if market == "CRYPTO":
        return CRYPTO_TOKEN

    return ""


# ============================================================
# 🌐 EODHD REQUEST
# ============================================================

async def eodhd(path, params=None):

    if not EODHD_API_KEY:
        raise RuntimeError(
            "EODHD_API_KEY غير موجود"
        )

    s = await get_session()

    query = dict(params or {})
    query["api_token"] = EODHD_API_KEY
    query["fmt"] = "json"

    url = (
        "https://eodhd.com/api/"
        + path.lstrip("/")
    )

    async with s.get(url, params=query) as response:

        text = await response.text()

        if response.status != 200:

            raise RuntimeError(
                f"EODHD HTTP {response.status}"
            )

        try:
            return json.loads(text)

        except Exception:

            raise RuntimeError(
                "EODHD returned invalid JSON"
            )


# ============================================================
# 📋 GET EXCHANGE SYMBOLS
# ============================================================

async def get_exchange_symbols(exchange):

    now = time.time()

    cached = symbols_cache.get(exchange)

    if cached:

        if (
            cached["symbols"]
            and now - cached["updated"]
            < SYMBOL_CACHE_SECONDS
        ):

            return cached["symbols"]

    log(
        f"📋 تحميل قائمة الرموز: {exchange}"
    )

    data = await eodhd(
        f"exchange-symbol-list/{exchange}"
    )

    symbols = []

    if isinstance(data, list):

        for item in data:

            if not isinstance(item, dict):
                continue

            code = str(
                item.get("Code", "")
            ).strip()

            typ = str(
                item.get("Type", "")
            ).strip().lower()

            if not code:
                continue

            # الأسهم فقط للأسواق
            if exchange != "CC":

                if typ and typ not in {
                    "common stock",
                    "stock",
                    "etf",
                    "preferred stock"
                }:

                    continue

            symbols.append(
                code
            )

    symbols = list(
        dict.fromkeys(symbols)
    )

    symbols_cache[exchange] = {
        "symbols": symbols,
        "updated": now
    }

    log(
        f"📊 {exchange}: {len(symbols)} رمز"
    )

    return symbols


# ============================================================
# 🇸🇦 TASI
# ============================================================

async def get_tasi_symbols():

    # نحاول اكتشاف سوق السعودية تلقائياً
    exchanges = await eodhd(
        "exchanges-list"
    )

    candidates = []

    if isinstance(exchanges, list):

        for ex in exchanges:

            if not isinstance(ex, dict):
                continue

            code = str(
                ex.get("Code", "")
            ).upper()

            name = str(
                ex.get("Name", "")
            ).lower()

            country = str(
                ex.get("Country", "")
            ).lower()

            if (
                code == "SR"
                or "saudi" in name
                or "saudi" in country
                or "arabia" in country
            ):

                candidates.append(code)

    # SR هو رمز السوق السعودي المعتاد
    candidates = list(
        dict.fromkeys(
            ["SR"] + candidates
        )
    )

    last_error = None

    for exchange in candidates:

        try:

            symbols = await get_exchange_symbols(
                exchange
            )

            if symbols:
                return symbols

        except Exception as exc:

            last_error = exc

    if last_error:
        raise last_error

    return []


# ============================================================
# 🇺🇸 US
# ============================================================

async def get_us_symbols():

    return await get_exchange_symbols(
        "US"
    )


# ============================================================
# 🪙 CRYPTO
# ============================================================

async def get_crypto_symbols():

    return await get_exchange_symbols(
        "CC"
    )


# ============================================================
# 📦 SYMBOLS
# ============================================================

async def load_all_symbols():

    tasi_task = asyncio.create_task(
        get_tasi_symbols()
    )

    us_task = asyncio.create_task(
        get_us_symbols()
    )

    crypto_task = asyncio.create_task(
        get_crypto_symbols()
    )

    tasi_result, us_result, crypto_result = (
        await asyncio.gather(
            tasi_task,
            us_task,
            crypto_task,
            return_exceptions=True
        )
    )

    results = {
        "TASI": tasi_result,
        "US": us_result,
        "CRYPTO": crypto_result
    }

    for market, result in results.items():

        if isinstance(result, Exception):

            log(
                f"ℹ️ {market}: تعذر تحميل قائمة الرموز"
            )

            continue

        symbols_cache[market] = {
            "symbols": result,
            "updated": time.time()
        }

        log(
            f"✅ {market}: {len(result)} رمز جاهز"
        )


# ============================================================
# 💰 LIVE QUOTES
# ============================================================

def split_batches(items, size):

    for i in range(
        0,
        len(items),
        size
    ):

        yield items[
            i:i + size
        ]


async def get_quotes(
    market,
    symbols
):

    if not symbols:
        return []

    suffix = {
        "TASI": ".SR",
        "US": ".US",
        "CRYPTO": ".CC"
    }[market]

    normalized = []

    for symbol in symbols:

        symbol = str(
            symbol
        ).strip()

        if not symbol:
            continue

        if "." not in symbol:

            symbol = symbol + suffix

        normalized.append(
            symbol
        )

    all_quotes = []

    # دفعات كبيرة لتقليل زمن الفحص
    for batch in split_batches(
        normalized,
        100
    ):

        if not batch:
            continue

        first = batch[0]

        others = ",".join(
            batch[1:]
        )

        params = {}

        if others:
            params["s"] = others

        try:

            data = await eodhd(
                f"real-time/{first}",
                params
            )

            if isinstance(data, list):

                all_quotes.extend(
                    data
                )

            elif isinstance(data, dict):

                all_quotes.append(
                    data
                )

        except Exception as exc:

            log(
                f"ℹ️ {market}: تعذر تحديث دفعة أسعار"
            )

            continue

    return all_quotes


# ============================================================
# 📈 HISTORY
# ============================================================

async def get_history(symbol):

    cached = history_cache.get(
        symbol
    )

    now = time.time()

    if cached:

        if (
            now - cached["time"]
            < HISTORY_CACHE_SECONDS
        ):

            return cached["data"]

    try:

        data = await eodhd(
            f"eod/{symbol}",
            {
                "period": "d",
                "from": "2025-01-01"
            }
        )

        if isinstance(data, list):

            history_cache[symbol] = {
                "data": data,
                "time": now
            }

            return data

    except Exception:
        pass

    return []


# ============================================================
# 🧮 EMA
# ============================================================

def ema(values, period):

    if len(values) < period:
        return None

    multiplier = (
        2 / (period + 1)
    )

    result = sum(
        values[:period]
    ) / period

    for price in values[period:]:

        result = (
            price - result
        ) * multiplier + result

    return result


# ============================================================
# 📊 RSI
# ============================================================

def rsi(values, period=14):

    if len(values) <= period:
        return None

    gains = []
    losses = []

    for i in range(
        1,
        len(values)
    ):

        change = (
            values[i]
            - values[i - 1]
        )

        if change > 0:

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

    rs = (
        avg_gain
        / avg_loss
    )

    return (
        100
        - (
            100
            / (1 + rs)
        )
    )


# ============================================================
# 📐 ATR
# ============================================================

def atr(data, period=14):

    if len(data) < period + 1:
        return None

    trs = []

    previous_close = None

    for row in data:

        high = float(
            row.get("high", 0)
        )

        low = float(
            row.get("low", 0)
        )

        close = float(
            row.get("close", 0)
        )

        if high <= 0 or low <= 0:
            continue

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

    if len(trs) < period:
        return None

    value = (
        sum(
            trs[:period]
        ) / period
    )

    for tr in trs[period:]:

        value = (
            (
                value
                * (period - 1)
            )
            + tr
        ) / period

    return value


# ============================================================
# 📊 SUPPORT / RESISTANCE
# ============================================================

def support_resistance(data):

    if not data:
        return None, None

    recent = data[-30:]

    highs = []

    lows = []

    for row in recent:

        try:

            high = float(
                row.get("high", 0)
            )

            low = float(
                row.get("low", 0)
            )

            if high > 0:
                highs.append(high)

            if low > 0:
                lows.append(low)

        except Exception:
            continue

    if not highs or not lows:
        return None, None

    return (
        min(lows),
        max(highs)
    )


# ============================================================
# 📦 VOLUME STRENGTH
# ============================================================

def volume_strength(data):

    if len(data) < 21:
        return 1.0

    volumes = []

    for row in data[-21:-1]:

        try:

            v = float(
                row.get(
                    "volume",
                    0
                )
            )

            if v > 0:
                volumes.append(v)

        except Exception:
            continue

    if not volumes:
        return 1.0

    average = (
        sum(volumes)
        / len(volumes)
    )

    current = float(
        data[-1].get(
            "volume",
            0
        )
    )

    if average <= 0:
        return 1.0

    return current / average


# ============================================================
# 🧠 ANALYSIS
# ============================================================

def analyze(
    market,
    quote,
    history
):

    try:

        symbol = str(
            quote.get(
                "code",
                ""
            )
        )

        price = float(
            quote.get(
                "close",
                quote.get(
                    "price",
                    0
                )
            )
        )

        change = float(
            quote.get(
                "change_p",
                0
            )
        )

        if price <= 0:
            return None

    except Exception:
        return None

    if market == "US":

        if price < MIN_US_PRICE:
            return None

    closes = []

    clean_history = []

    for row in history:

        try:

            close = float(
                row.get(
                    "close",
                    0
                )
            )

            if close > 0:

                closes.append(
                    close
                )

                clean_history.append(
                    row
                )

        except Exception:
            continue

    if len(closes) < 60:
        return None

    # نضع السعر الحالي في آخر السلسلة
    calc_closes = (
        closes
        + [price]
    )

    ema8 = ema(
        calc_closes,
        8
    )

    ema21 = ema(
        calc_closes,
        21
    )

    ema50 = ema(
        calc_closes,
        50
    )

    rsi14 = rsi(
        calc_closes,
        14
    )

    atr14 = atr(
        clean_history
        + [{
            "high": price,
            "low": price,
            "close": price,
            "volume": quote.get(
                "volume",
                0
            )
        }],
        14
    )

    support, resistance = (
        support_resistance(
            clean_history
        )
    )

    vol_strength = (
        volume_strength(
            clean_history
        )
    )

    if None in {
        ema8,
        ema21,
        ema50,
        rsi14,
        atr14
    }:

        return None

    # ========================================================
    # 🧠 SIGNAL ENGINE
    # ========================================================

    bullish_points = 0
    bearish_points = 0

    if price > ema8:
        bullish_points += 1
    else:
        bearish_points += 1

    if ema8 > ema21:
        bullish_points += 1
    else:
        bearish_points += 1

    if ema21 > ema50:
        bullish_points += 1
    else:
        bearish_points += 1

    if rsi14 >= 55:
        bullish_points += 1

    if rsi14 <= 45:
        bearish_points += 1

    if support and price > support:
        bullish_points += 1

    if resistance and price < resistance:
        bearish_points += 1

    if vol_strength >= 1.5:

        if bullish_points >= bearish_points:
            bullish_points += 1
        else:
            bearish_points += 1

    total = max(
        bullish_points
        + bearish_points,
        1
    )

    buy_power = round(
        bullish_points
        / total
        * 100
    )

    sell_power = round(
        bearish_points
        / total
        * 100
    )

    if buy_power >= 75:

        signal = "BUY"

        strength = buy_power

    elif sell_power >= 75:

        signal = "SELL"

        strength = sell_power

    else:

        return None

    # ========================================================
    # 🎯 8 ATR TARGETS
    # ========================================================

    targets = []

    if signal == "BUY":

        for multiplier in [
            1,
            1.5,
            2,
            2.5,
            3,
            3.5,
            4,
            4.5
        ]:

            targets.append(
                price
                + (
                    atr14
                    * multiplier
                )
            )

    else:

        for multiplier in [
            1,
            1.5,
            2,
            2.5,
            3,
            3.5,
            4,
            4.5
        ]:

            targets.append(
                price
                - (
                    atr14
                    * multiplier
                )
            )

    return {
        "market": market,
        "symbol": symbol,
        "price": price,
        "change": change,
        "signal": signal,
        "strength": strength,
        "buy_power": buy_power,
        "sell_power": sell_power,
        "ema8": ema8,
        "ema21": ema21,
        "ema50": ema50,
        "rsi": rsi14,
        "atr": atr14,
        "support": support,
        "resistance": resistance,
        "volume": vol_strength,
        "targets": targets
    }


# ============================================================
# 🧾 FORMAT NUMBER
# ============================================================

def number(value):

    if value is None:
        return "—"

    if abs(value) >= 1000:
        return f"{value:,.2f}"

    if abs(value) >= 1:
        return f"{value:.2f}"

    return f"{value:.4f}"


# ============================================================
# 📩 TELEGRAM
# ============================================================

async def telegram_send(
    token,
    chat_id,
    text
):

    if not token:
        return False

    s = await get_session()

    url = (
        f"https://api.telegram.org/"
        f"bot{token}/sendMessage"
    )

    payload = {
        "chat_id": chat_id,
        "text": text
    }

    try:

        async with s.post(
            url,
            json=payload
        ) as response:

            return response.status == 200

    except Exception:

        return False


# ============================================================
# 📣 SEND SIGNAL
# ============================================================

async def send_signal(signal):

    market = signal["market"]

    token = token_for_market(
        market
    )

    if not token:
        return

    direction = signal[
        "signal"
    ]

    if direction == "BUY":

        arrow = "🟢⬆️"
        title = "شراء قوي"
        market_arrow = "صاعد قوي"

    else:

        arrow = "🔴⬇️"
        title = "بيع قوي"
        market_arrow = "هابط قوي"

    market_name = {
        "TASI": "🇸🇦 السوق السعودي (TASI)",
        "US": "🇺🇸 السوق الأمريكي (US)",
        "CRYPTO": "🪙 العملات الرقمية (CRYPTO)"
    }[market]

    targets_text = []

    for index, target in enumerate(
        signal["targets"],
        start=1
    ):

        if direction == "BUY":

            percent = (
                target
                / signal["price"]
                - 1
            ) * 100

        else:

            percent = (
                1
                - target
                / signal["price"]
            ) * 100

        sign = "+" if percent >= 0 else ""

        targets_text.append(
            f"TP{index}: {number(target)} "
            f"({sign}{percent:.1f}%)"
        )

    text = (
        "💀🚀 AI PRO MAX SIGNAL\n\n"
        f"{market_name}\n\n"
        f"{signal['symbol']}\n\n"
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
        f"📊 الاتجاه: {market_arrow}\n\n"
        "🎯 أهداف ATR الثمانية:\n"
        + "\n".join(targets_text)
    )

    chats = list(
        telegram_chats[
            market
        ]
    )

    for chat_id in chats:

        await telegram_send(
            token,
            chat_id,
            text
        )


# ============================================================
# 🚫 DUPLICATE PROTECTION
# ============================================================

def can_send(signal):

    key = (
        signal["market"],
        signal["symbol"],
        signal["signal"]
    )

    now = time.time()

    previous = last_signal.get(
        key,
        0
    )

    if (
        now - previous
        < SIGNAL_COOLDOWN
    ):

        return False

    last_signal[key] = now

    return True


# ============================================================
# 🔍 PROCESS ONE QUOTE
# ============================================================

async def process_quote(
    market,
    quote
):

    symbol = str(
        quote.get(
            "code",
            ""
        )
    ).strip()

    if not symbol:
        return

    history = await get_history(
        symbol
    )

    if not history:
        return

    signal = analyze(
        market,
        quote,
        history
    )

    if not signal:
        return

    if not can_send(signal):
        return

    await send_signal(
        signal
    )


# ============================================================
# 🔎 SCAN MARKET
# ============================================================

async def scan_market(
    market
):

    symbols = (
        symbols_cache
        .get(market, {})
        .get("symbols", [])
    )

    if not symbols:

        return

    log(
        f"🔎 {market}: فحص {len(symbols)} رمز"
    )

    quotes = await get_quotes(
        market,
        symbols
    )

    if not quotes:

        log(
            f"ℹ️ {market}: لم تصل أسعار"
        )

        return

    # الأسعار تصل دفعة واحدة
    # ثم التحليل بالتوازي
    semaphore = asyncio.Semaphore(
        30
    )

    async def worker(quote):

        async with semaphore:

            try:

                await process_quote(
                    market,
                    quote
                )

            except Exception:

                return

    await asyncio.gather(
        *[
            worker(q)
            for q in quotes
        ],
        return_exceptions=True
    )

    log(
        f"✅ {market}: اكتمل فحص الأسعار"
    )


# ============================================================
# 🔄 FULL SCAN
# ============================================================

async def full_scan():

    global scan_number

    scan_number += 1

    started = time.monotonic()

    log(
        ""
    )

    log(
        "============================================================"
    )

    log(
        f"💀🚀 AI PRO MAX SCAN #{scan_number}"
    )

    log(
        "============================================================"
    )

    # تحديث القوائم عند الحاجة
    try:

        await load_all_symbols()

    except Exception:

        log(
            "ℹ️ استخدام القوائم المحفوظة"
        )

    # الأسواق الثلاثة بالتوازي
    await asyncio.gather(
        scan_market("TASI"),
        scan_market("US"),
        scan_market("CRYPTO"),
        return_exceptions=True
    )

    elapsed = (
        time.monotonic()
        - started
    )

    log(
        f"✅ انتهت الدورة خلال {elapsed:.2f} ثانية"
    )


# ============================================================
# 🤖 START MESSAGE
# ============================================================

def startup_message(market):

    market_name = {
        "TASI":
            "🇸🇦 السوق السعودي TASI",
        "US":
            "🇺🇸 السوق الأمريكي",
        "CRYPTO":
            "🪙 العملات الرقمية"
    }[market]

    return (
        "💀🚀 AI PRO MAX\n"
        "✅ البوت يعمل الآن\n"
        "🔄 الفحص تلقائي وكامل\n"
        "⏱️ الفحص كل دقيقتين\n\n"
        f"📊 السوق:\n"
        f"{market_name}\n\n"
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
        "EODHD فقط"
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

    token = token_for_market(
        market
    )

    if not token:

        return web.Response(
            status=200
        )

    try:

        update = await request.json()

    except Exception:

        return web.Response(
            status=200
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

    if chat_id is not None:

        telegram_chats[
            market
        ].add(
            int(chat_id)
        )

        text = message.get(
            "text",
            ""
        )

        if text.startswith(
            "/start"
        ):

            await telegram_send(
                token,
                chat_id,
                startup_message(
                    market
                )
            )

    return web.Response(
        status=200
    )


# ============================================================
# 🌐 HEALTH
# ============================================================

async def health(request):

    return web.json_response({
        "status": "ok",
        "system": "AI PRO MAX",
        "scan_seconds": SCAN_SECONDS,
        "markets": [
            "TASI",
            "US",
            "CRYPTO"
        ]
    })


# ============================================================
# 🔗 SET WEBHOOK
# ============================================================

async def set_webhook(
    market,
    token,
    base_url
):

    if not token:
        return

    webhook_url = (
        f"{base_url}/telegram/{market.lower()}"
    )

    s = await get_session()

    url = (
        f"https://api.telegram.org/"
        f"bot{token}/setWebhook"
    )

    try:

        async with s.post(
            url,
            json={
                "url": webhook_url,
                "drop_pending_updates": True
            }
        ) as response:

            if response.status == 200:

                log(
                    f"Telegram Webhook: "
                    f"{market.lower()} ON"
                )

            else:

                log(
                    f"Telegram Webhook: "
                    f"{market.lower()}"
                )

    except Exception:

        log(
            f"Telegram Webhook: "
            f"{market.lower()}"
        )


# ============================================================
# 🌐 START WEB SERVER
# ============================================================

async def start_server():

    app = web.Application()

    app.router.add_get(
        "/",
        health
    )

    app.router.add_get(
        "/health",
        health
    )

    app.router.add_post(
        "/telegram/tasi",
        telegram_webhook
    )

    app.router.add_post(
        "/telegram/us",
        telegram_webhook
    )

    app.router.add_post(
        "/telegram/crypto",
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

    log(
        f"🚀 AI PRO MAX يعمل على PORT {PORT}"
    )

    return runner


# ============================================================
# 🔁 SCAN LOOP
# ============================================================

async def scanner_loop():

    # أول فحص فور التشغيل
    await asyncio.sleep(3)

    while True:

        started = time.monotonic()

        try:

            await full_scan()

        except Exception as exc:

            log(
                "ℹ️ حدث خطأ أثناء دورة الفحص"
            )

        elapsed = (
            time.monotonic()
            - started
        )

        wait = max(
            1,
            SCAN_SECONDS
            - elapsed
        )

        log(
            f"⏱️ الدورة القادمة خلال "
            f"{int(wait)} ثانية"
        )

        await asyncio.sleep(
            wait
        )


# ============================================================
# 🚀 MAIN
# ============================================================

async def main():

    log(
        "============================================================"
    )

    log(
        "💀🚀 AI PRO MAX"
    )

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

    log(
        "🟢 النظام يعمل 24/7"
    )

    log(
        "⏱️ الفحص كل دقيقتين"
    )

    log(
        "📡 مصدر البيانات: EODHD فقط"
    )

    log(
        "============================================================"
    )

    runner = await start_server()

    # Railway public URL
    domain = (
        os.getenv(
            "RAILWAY_PUBLIC_DOMAIN",
            ""
        ).strip()
    )

    if domain:

        if not domain.startswith(
            "http"
        ):

            domain = (
                "https://"
                + domain
            )

        await asyncio.gather(

            set_webhook(
                "TASI",
                TASI_TOKEN,
                domain
            ),

            set_webhook(
                "US",
                US_TOKEN,
                domain
            ),

            set_webhook(
                "CRYPTO",
                CRYPTO_TOKEN,
                domain
            )
        )

    else:

        log(
            "ℹ️ Railway Public Domain غير متوفر"
        )

    # التشغيل المستمر
    try:

        await scanner_loop()

    finally:

        await runner.cleanup()

        if session:
            await session.close()


# ============================================================
# ▶️ RUN
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        pass