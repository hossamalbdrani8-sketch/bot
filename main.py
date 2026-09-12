
# ============================================================
# 💀🚀 AI PRO MAX
# PYTHON - BUILD FROM ZERO
# ============================================================

import os
import asyncio
import time
import json
from datetime import datetime, timezone

import aiohttp
from aiohttp import web


# ============================================================
# ⚙️ RAILWAY VARIABLES
# ============================================================

EODHD_API_KEY = os.getenv("API", "").strip()

TASI_TOKEN = os.getenv("TASI_TOKEN", "").strip()
US_TOKEN = os.getenv("US_TOKEN", "").strip()
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN", "").strip()

PORT = int(os.getenv("PORT", "8080"))

SCAN_SECONDS = 120

MIN_US_PRICE = 0.20

REQUEST_TIMEOUT = 30

MAX_CONNECTIONS = 50

SYMBOL_CACHE_SECONDS = 3600

HISTORY_CACHE_SECONDS = 21600

SIGNAL_COOLDOWN = 1800


# ============================================================
# 🧠 MEMORY
# ============================================================

symbols_cache = {
    "TASI": {"symbols": [], "updated": 0},
    "US": {"symbols": [], "updated": 0},
    "CRYPTO": {"symbols": [], "updated": 0},
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

    now = datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    print(
        f"{now} UTC | {message}",
        flush=True
    )


# ============================================================
# 🌐 HTTP SESSION
# ============================================================

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
# 🔐 TOKEN
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
# 🌐 EODHD
# ============================================================

async def eodhd(path, params=None):

    if not EODHD_API_KEY:

        raise RuntimeError(
            "متغير API غير موجود في Railway"
        )

    s = await get_session()

    query = dict(params or {})

    query["api_token"] = EODHD_API_KEY
    query["fmt"] = "json"

    url = (
        "https://eodhd.com/api/"
        + path.lstrip("/")
    )

    async with s.get(
        url,
        params=query
    ) as response:

        body = await response.text()

        if response.status != 200:

            raise RuntimeError(
                f"EODHD HTTP {response.status}: "
                f"{body[:500]}"
            )

        try:

            return json.loads(body)

        except Exception:

            raise RuntimeError(
                "EODHD أرسل استجابة غير صالحة"
            )


# ============================================================
# 📋 EXCHANGE SYMBOLS
# ============================================================

async def get_exchange_symbols(exchange):

    now = time.time()

    cache = symbols_cache.get(exchange)

    if cache:

        if (
            cache["symbols"]
            and
            now - cache["updated"]
            < SYMBOL_CACHE_SECONDS
        ):

            return cache["symbols"]

    log(
        f"📋 تحميل قائمة الرموز: {exchange}"
    )

    try:

        data = await eodhd(
            f"exchange-symbol-list/{exchange}"
        )

    except Exception as exc:

        log(
            f"ℹ️ EODHD {exchange}: {exc}"
        )

        raise

    symbols = []

    if isinstance(data, list):

        for item in data:

            if not isinstance(item, dict):
                continue

            code = str(
                item.get("Code", "")
            ).strip()

            if not code:
                continue

            symbols.append(code)

    symbols = list(
        dict.fromkeys(symbols)
    )

    symbols_cache[exchange] = {
        "symbols": symbols,
        "updated": now
    }

    log(
        f"✅ {exchange}: "
        f"{len(symbols)} رمز"
    )

    return symbols


# ============================================================
# 🇸🇦 TASI
# ============================================================

async def get_tasi_symbols():

    candidates = [
        "SR"
    ]

    try:

        exchanges = await eodhd(
            "exchanges-list"
        )

        if isinstance(
            exchanges,
            list
        ):

            for item in exchanges:

                if not isinstance(
                    item,
                    dict
                ):
                    continue

                code = str(
                    item.get(
                        "Code",
                        ""
                    )
                ).upper()

                name = str(
                    item.get(
                        "Name",
                        ""
                    )
                ).lower()

                country = str(
                    item.get(
                        "Country",
                        ""
                    )
                ).lower()

                if (
                    code == "SR"
                    or
                    "saudi" in name
                    or
                    "saudi" in country
                    or
                    "arabia" in country
                ):

                    if code:
                        candidates.append(
                            code
                        )

    except Exception as exc:

        log(
            f"ℹ️ تعذر اكتشاف سوق السعودية: {exc}"
        )

    candidates = list(
        dict.fromkeys(candidates)
    )

    last_error = None

    for exchange in candidates:

        try:

            symbols = (
                await get_exchange_symbols(
                    exchange
                )
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
# 📦 LOAD ALL SYMBOLS
# ============================================================

async def load_all_symbols():

    results = await asyncio.gather(

        get_tasi_symbols(),

        get_us_symbols(),

        get_crypto_symbols(),

        return_exceptions=True
    )

    names = [
        "TASI",
        "US",
        "CRYPTO"
    ]

    for market, result in zip(
        names,
        results
    ):

        if isinstance(
            result,
            Exception
        ):

            log(
                f"ℹ️ {market}: "
                f"{result}"
            )

            continue

        symbols_cache[market] = {
            "symbols": result,
            "updated": time.time()
        }

        log(
            f"✅ {market}: "
            f"{len(result)} رمز جاهز"
        )


# ============================================================
# 📦 BATCH
# ============================================================

def batches(items, size):

    for index in range(
        0,
        len(items),
        size
    ):

        yield items[
            index:index + size
        ]


# ============================================================
# 💰 LIVE QUOTES
# ============================================================

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

            symbol += suffix

        normalized.append(
            symbol
        )

    quotes = []

    # 100 رمز في كل طلب
    for batch in batches(
        normalized,
        100
    ):

        if not batch:
            continue

        first = batch[0]

        params = {}

        if len(batch) > 1:

            params["s"] = ",".join(
                batch[1:]
            )

        try:

            data = await eodhd(
                f"real-time/{first}",
                params
            )

            if isinstance(
                data,
                list
            ):

                quotes.extend(data)

            elif isinstance(
                data,
                dict
            ):

                quotes.append(data)

        except Exception as exc:

            log(
                f"ℹ️ {market}: "
                f"دفعة الأسعار: {exc}"
            )

    return quotes


# ============================================================
# 📈 HISTORY
# ============================================================

async def get_history(symbol):

    now = time.time()

    cached = history_cache.get(
        symbol
    )

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

        if isinstance(
            data,
            list
        ):

            history_cache[symbol] = {
                "data": data,
                "time": now
            }

            return data

    except Exception as exc:

        log(
            f"ℹ️ تاريخ {symbol}: {exc}"
        )

    return []


# ============================================================
# 📊 EMA
# ============================================================

def ema(values, period):

    if len(values) < period:
        return None

    result = (
        sum(values[:period])
        / period
    )

    multiplier = (
        2 / (period + 1)
    )

    for value in values[period:]:

        result = (
            (
                value - result
            )
            * multiplier
            + result
        )

    return result


# ============================================================
# 📊 RSI
# ============================================================

def rsi(
    values,
    period=14
):

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

        gains.append(
            max(change, 0)
        )

        losses.append(
            max(-change, 0)
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

def atr(
    data,
    period=14
):

    if len(data) < period + 1:
        return None

    trs = []

    previous_close = None

    for row in data:

        try:

            high = float(
                row.get(
                    "high",
                    0
                )
            )

            low = float(
                row.get(
                    "low",
                    0
                )
            )

            close = float(
                row.get(
                    "close",
                    0
                )
            )

        except Exception:

            continue

        if (
            high <= 0
            or low <= 0
            or close <= 0
        ):
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
        sum(trs[:period])
        / period
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

            high = float(
                row.get(
                    "high",
                    0
                )
            )

            low = float(
                row.get(
                    "low",
                    0
                )
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
# 📊 VOLUME
# ============================================================

def volume_strength(data):

    if len(data) < 21:
        return 1.0

    values = []

    for row in data[-21:-1]:

        try:

            volume = float(
                row.get(
                    "volume",
                    0
                )
            )

            if volume > 0:
                values.append(volume)

        except Exception:

            continue

    if not values:
        return 1.0

    average = (
        sum(values)
        / len(values)
    )

    try:

        current = float(
            data[-1].get(
                "volume",
                0
            )
        )

    except Exception:

        return 1.0

    if average <= 0:
        return 1.0

    return (
        current
        / average
    )


# ============================================================
# 🧠 ANALYZE
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
        ).strip()

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
                quote.get(
                    "change",
                    0
                )
            )
        )

    except Exception:

        return None

    if not symbol:
        return None

    if price <= 0:
        return None

    if (
        market == "US"
        and
        price < MIN_US_PRICE
    ):

        return None

    clean = []

    closes = []

    for row in history:

        try:

            close = float(
                row.get(
                    "close",
                    0
                )
            )

            if close <= 0:
                continue

            clean.append(row)
            closes.append(close)

        except Exception:

            continue

    if len(closes) < 60:
        return None

    closes.append(price)

    ema8 = ema(
        closes,
        8
    )

    ema21 = ema(
        closes,
        21
    )

    ema50 = ema(
        closes,
        50
    )

    rsi14 = rsi(
        closes,
        14
    )

    atr_data = clean + [
        {
            "high": price,
            "low": price,
            "close": price,
            "volume": quote.get(
                "volume",
                0
            )
        }
    ]

    atr14 = atr(
        atr_data,
        14
    )

    support, resistance = (
        support_resistance(
            clean
        )
    )

    volume = (
        volume_strength(
            clean
        )
    )

    if (
        ema8 is None
        or ema21 is None
        or ema50 is None
        or rsi14 is None
        or atr14 is None
    ):

        return None

    # ========================================================
    # 🧠 SIGNAL SCORE
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

    if resistance is not None:

        if price < resistance:
            sell += 1

    if volume >= 1.5:

        if buy >= sell:
            buy += 1
        else:
            sell += 1

    total = max(
        buy + sell,
        1
    )

    buy_power = round(
        buy / total * 100
    )

    sell_power = round(
        sell / total * 100
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

    multipliers = [
        1.0,
        1.5,
        2.0,
        2.5,
        3.0,
        3.5,
        4.0,
        4.5
    ]

    targets = []

    for multiplier in multipliers:

        if signal == "BUY":

            target = (
                price
                + atr14 * multiplier
            )

        else:

            target = (
                price
                - atr14 * multiplier
            )

        targets.append(
            target
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
        "volume": volume,
        "ema8": ema8,
        "ema21": ema21,
        "ema50": ema50,
        "rsi": rsi14,
        "atr": atr14,
        "support": support,
        "resistance": resistance,
        "targets": targets
    }


# ============================================================
# 🔢 NUMBER
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
# 📩 TELEGRAM SEND
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
        "https://api.telegram.org/"
        f"bot{token}/sendMessage"
    )

    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True
    }

    try:

        async with s.post(
            url,
            json=payload
        ) as response:

            return response.status == 200

    except Exception as exc:

        log(
            f"ℹ️ Telegram: {exc}"
        )

        return False


# ============================================================
# 📣 SIGNAL MESSAGE
# ============================================================

async def send_signal(signal):

    market = signal["market"]

    token = token_for_market(
        market
    )

    if not token:
        return

    if signal["signal"] == "BUY":

        arrow = "🟢⬆️"
        title = "شراء قوي"
        trend = "صاعد قوي"

    else:

        arrow = "🔴⬇️"
        title = "بيع قوي"
        trend = "هابط قوي"

    market_name = {
        "TASI":
            "🇸🇦 السوق السعودي (TASI)",

        "US":
            "🇺🇸 السوق الأمريكي (US)",

        "CRYPTO":
            "🪙 العملات الرقمية (CRYPTO)"
    }[market]

    target_lines = []

    for index, target in enumerate(
        signal["targets"],
        1
    ):

        if signal["signal"] == "BUY":

            percentage = (
                target
                / signal["price"]
                - 1
            ) * 100

        else:

            percentage = (
                1
                - target
                / signal["price"]
            ) * 100

        sign = (
            "+"
            if percentage >= 0
            else ""
        )

        target_lines.append(
            f"TP{index}: "
            f"{number(target)} "
            f"({sign}{percentage:.1f}%)"
        )

    text = (
        "💀🚀 AI PRO MAX SIGNAL\n\n"

        f"{market_name}\n\n"

        f"{signal['symbol']}\n\n"

        f"{arrow} {title}\n\n"

        f"💰 السعر: "
        f"{number(signal['price'])}\n"

        f"📈 التغير: "
        f"{signal['change']:+.2f}%\n"

        f"🎯 قوة الإشارة: "
        f"{signal['strength']}/100\n"

        f"🟢 قوة الشراء: "
        f"{signal['buy_power']}%\n"

        f"🔴 قوة البيع: "
        f"{signal['sell_power']}%\n"

        f"📊 قوة الحجم: "
        f"{signal['volume']:.1f}x\n\n"

        f"EMA 8: "
        f"{number(signal['ema8'])}\n"

        f"EMA 21: "
        f"{number(signal['ema21'])}\n"

        f"EMA 50: "
        f"{number(signal['ema50'])}\n"

        f"RSI 14: "
        f"{number(signal['rsi'])}\n"

        f"ATR 14: "
        f"{number(signal['atr'])}\n\n"

        f"🛡️ الدعم: "
        f"{number(signal['support'])}\n"

        f"🔺 المقاومة: "
        f"{number(signal['resistance'])}\n"

        f"📊 الاتجاه: "
        f"{trend}\n\n"

        "🎯 أهداف ATR الثمانية:\n"

        + "\n".join(
            target_lines
        )
    )

    chats = list(
        telegram_chats[
            market
        ]
    )

    if not chats:
        return

    # إرسال بالتوازي
    await asyncio.gather(
        *[
            telegram_send(
                token,
                chat_id,
                text
            )
            for chat_id in chats
        ],
        return_exceptions=True
    )


# ============================================================
# 🚫 DUPLICATE
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
# 🔍 PROCESS QUOTE
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

    if not can_send(
        signal
    ):
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

        log(
            f"ℹ️ {market}: "
            "لا توجد رموز محملة"
        )

        return

    log(
        f"🔎 {market}: "
        f"فحص {len(symbols)} رمز"
    )

    quotes = await get_quotes(
        market,
        symbols
    )

    if not quotes:

        log(
            f"ℹ️ {market}: "
            "لم تصل أسعار"
        )

        return

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

            except Exception as exc:

                log(
                    f"ℹ️ {market}: "
                    f"تحليل رمز: {exc}"
                )

    await asyncio.gather(
        *[
            worker(quote)
            for quote in quotes
        ],
        return_exceptions=True
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

    # تحميل القوائم بالتوازي
    await load_all_symbols()

    # فحص الأسواق الثلاثة بالتوازي
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
        f"✅ انتهت الدورة خلال "
        f"{elapsed:.2f} ثانية"
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
        "💀🚀 AI PRO MAX\n\n"

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

    # لا نستخدم match_info نهائيًا
    path = request.path.lower()

    if path.endswith(
        "/telegram/tasi"
    ):

        market = "TASI"

    elif path.endswith(
        "/telegram/us"
    ):

        market = "US"

    elif path.endswith(
        "/telegram/crypto"
    ):

        market = "CRYPTO"

    else:

        return web.Response(
            status=200
        )

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

    if chat_id is None:

        return web.Response(
            status=200
        )

    telegram_chats[
        market
    ].add(
        int(chat_id)
    )

    text = str(
        message.get(
            "text",
            ""
        )
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
# ❤️ HEALTH
# ============================================================

async def health(request):

    return web.json_response({
        "status": "ok",
        "system": "AI PRO MAX",
        "markets": [
            "TASI",
            "US",
            "CRYPTO"
        ],
        "scan_seconds": SCAN_SECONDS
    })


# ============================================================
# 🔗 WEBHOOK
# ============================================================

async def set_webhook(
    market,
    token,
    base_url
):

    if not token:
        return

    url = (
        f"https://api.telegram.org/"
        f"bot{token}/setWebhook"
    )

    webhook_url = (
        f"{base_url}/telegram/"
        f"{market.lower()}"
    )

    try:

        s = await get_session()

        async with s.post(
            url,
            json={
                "url": webhook_url,
                "drop_pending_updates": True
            }
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
                    f"{body[:300]}"
                )

    except Exception as exc:

        log(
            f"ℹ️ Webhook {market}: "
            f"{exc}"
        )


# ============================================================
# 🌐 WEB SERVER
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

        elapsed = (
            time.monotonic()
            - started
        )

        wait = max(
            1,
            SCAN_SECONDS
            - int(elapsed)
        )

        log(
            f"⏱️ الدورة القادمة خلال "
            f"{wait} ثانية"
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
        "============================================================"
    )

    log(
        "🤖 TASI BOT: "
        + (
            "ON"
            if TASI_TOKEN
            else "OFF"
        )
    )

    log(
        "🤖 US BOT: "
        + (
            "ON"
            if US_TOKEN
            else "OFF"
        )
    )

    log(
        "🤖 CRYPTO BOT: "
        + (
            "ON"
            if CRYPTO_TOKEN
            else "OFF"
        )
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

    # Railway public domain
    domain = (
        os.getenv(
            "RAILWAY_PUBLIC_DOMAIN",
            ""
        ).strip()
    )

    if not domain:

        domain = (
            os.getenv(
                "RAILWAY_STATIC_URL",
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
            "ℹ️ لم يتم العثور على Railway Public Domain"
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

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        pass