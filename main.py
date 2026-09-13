
# ============================================================
# 💀🚀 AI PRO MAX
# TWELVE DATA - CREDIT SAFE EDITION
# PYTHON - CLEAN BUILD
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

TWELVE_DATA_API_KEY = os.getenv(
    "TWELVE_DATA_API_KEY",
    ""
).strip()

TASI_TOKEN = os.getenv(
    "TASI_TOKEN",
    ""
).strip()

US_TOKEN = os.getenv(
    "US_TOKEN",
    ""
).strip()

CRYPTO_TOKEN = os.getenv(
    "CRYPTO_TOKEN",
    ""
).strip()

PORT = int(
    os.getenv("PORT", "8080")
)

SCAN_SECONDS = int(
    os.getenv("SCAN_SECONDS", "120")
)

MIN_US_PRICE = float(
    os.getenv("MIN_US_PRICE", "0.20")
)

SIGNAL_COOLDOWN = int(
    os.getenv("SIGNAL_COOLDOWN", "1800")
)

REQUEST_TIMEOUT = int(
    os.getenv("REQUEST_TIMEOUT", "30")
)

# تحديث قائمة الرموز مرة واحدة يومياً
CATALOG_REFRESH_SECONDS = int(
    os.getenv(
        "SYMBOL_REFRESH_SECONDS",
        "86400"
    )
)

# حجم صفحة الكتالوج
CATALOG_PAGE_SIZE = 5000


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

telegram_chats = {
    "TASI": set(),
    "US": set(),
    "CRYPTO": set(),
}

last_signal = {}

scan_pointer = {
    "US": 0,
    "CRYPTO": 0,
}

market_turn = 0

session = None

api_credits_left = None

daily_requests = 0

daily_date = None


# ============================================================
# 📝 LOG
# ============================================================

def log(message):

    now = datetime.now(
        timezone.utc
    ).strftime(
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
            limit=10,
            ttl_dns_cache=300
        )

        session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector
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
    }.get(
        market,
        ""
    )


# ============================================================
# 🌐 TWELVE DATA
# ============================================================

async def twelve(
    endpoint,
    params=None
):

    global api_credits_left
    global daily_requests
    global daily_date

    if not TWELVE_DATA_API_KEY:

        raise RuntimeError(
            "TWELVE_DATA_API_KEY غير موجود"
        )

    today = datetime.now(
        timezone.utc
    ).date()

    if daily_date != today:

        daily_date = today
        daily_requests = 0

    # --------------------------------------------------------
    # حماية حد Basic اليومي
    # نترك هامشاً ولا نصل إلى 800
    # --------------------------------------------------------

    if daily_requests >= 790:

        raise RuntimeError(
            "تم إيقاف طلبات البيانات لحماية حد 800 اليومي"
        )

    s = await get_session()

    query = dict(
        params or {}
    )

    query["apikey"] = (
        TWELVE_DATA_API_KEY
    )

    url = (
        "https://api.twelvedata.com/"
        + endpoint.lstrip("/")
    )

    async with s.get(
        url,
        params=query
    ) as response:

        used = response.headers.get(
            "api-credits-used"
        )

        left = response.headers.get(
            "api-credits-left"
        )

        try:

            if left is not None:

                api_credits_left = int(
                    float(left)
                )

        except Exception:

            pass

        # ----------------------------------------------------
        # 429
        # ----------------------------------------------------

        if response.status == 429:

            raise RuntimeError(
                "429: تم بلوغ حد API في الدقيقة"
            )

        body = await response.text()

        try:

            data = await response.json(
                content_type=None
            )

        except Exception:

            raise RuntimeError(
                "Twelve Data HTTP "
                f"{response.status}: "
                f"{body[:250]}"
            )

        daily_requests += 1

        if response.status != 200:

            if isinstance(
                data,
                dict
            ):

                message = data.get(
                    "message",
                    body[:400]
                )

            else:

                message = body[:400]

            raise RuntimeError(
                "Twelve Data HTTP "
                f"{response.status}: "
                f"{message}"
            )

        if (
            isinstance(data, dict)
            and data.get("status") == "error"
        ):

            raise RuntimeError(
                str(
                    data.get(
                        "message",
                        "خطأ Twelve Data"
                    )
                )
            )

        return data


# ============================================================
# 📦 CATALOG
# ============================================================

def rows_from_catalog(data):

    if isinstance(
        data,
        dict
    ):

        rows = data.get(
            "data"
        )

        if isinstance(
            rows,
            list
        ):

            return rows

        rows = data.get(
            "values"
        )

        if isinstance(
            rows,
            list
        ):

            return rows

    if isinstance(
        data,
        list
    ):

        return data

    return []


# ============================================================
# 🇺🇸 US STOCKS
# ============================================================

async def get_stock_symbols():

    result = []

    page = 1

    while True:

        data = await twelve(
            "stocks",
            {
                "country":
                    "United States",

                "type":
                    "Common Stock",

                "page":
                    page,

                "outputsize":
                    CATALOG_PAGE_SIZE,
            }
        )

        rows = rows_from_catalog(
            data
        )

        if not rows:

            break

        for item in rows:

            if not isinstance(
                item,
                dict
            ):

                continue

            symbol = str(
                item.get(
                    "symbol",
                    ""
                )
            ).strip()

            if not symbol:

                continue

            result.append({

                "symbol":
                    symbol,

                "name":
                    str(
                        item.get(
                            "name",
                            symbol
                        )
                    ).strip(),

                "exchange":
                    str(
                        item.get(
                            "exchange",
                            ""
                        )
                    ).strip(),

                "mic_code":
                    str(
                        item.get(
                            "mic_code",
                            ""
                        )
                    ).strip(),

            })

        if (
            len(rows)
            < CATALOG_PAGE_SIZE
        ):

            break

        page += 1

        # حماية إضافية
        if page > 20:

            break

    unique = {}

    for item in result:

        key = (
            item["symbol"],
            item["exchange"]
        )

        unique[key] = item

    return list(
        unique.values()
    )


# ============================================================
# 🪙 CRYPTO
# ============================================================

async def get_crypto_symbols():

    result = []

    page = 1

    while True:

        data = await twelve(
            "cryptocurrencies",
            {
                "page":
                    page,

                "outputsize":
                    CATALOG_PAGE_SIZE,
            }
        )

        rows = rows_from_catalog(
            data
        )

        if not rows:

            break

        for item in rows:

            if not isinstance(
                item,
                dict
            ):

                continue

            symbol = str(
                item.get(
                    "symbol",
                    ""
                )
            ).strip()

            if not symbol:

                continue

            result.append({

                "symbol":
                    symbol,

                "name":
                    str(
                        item.get(
                            "currency_base",
                            symbol
                        )
                    ).strip(),

                "exchange":
                    "",

                "mic_code":
                    "",

            })

        if (
            len(rows)
            < CATALOG_PAGE_SIZE
        ):

            break

        page += 1

        if page > 20:

            break

    unique = {}

    for item in result:

        unique[
            item["symbol"]
        ] = item

    return list(
        unique.values()
    )


# ============================================================
# 📚 LOAD SYMBOLS
# ============================================================

async def load_symbols(
    force=False
):

    now = time.time()

    if (
        not force
        and symbols_cache["US"]
        and symbols_cache["CRYPTO"]
        and (
            now
            - symbols_cache_time["US"]
            < CATALOG_REFRESH_SECONDS
        )
        and (
            now
            - symbols_cache_time["CRYPTO"]
            < CATALOG_REFRESH_SECONDS
        )
    ):

        return

    try:

        us, crypto = await asyncio.gather(

            get_stock_symbols(),

            get_crypto_symbols()

        )

        symbols_cache[
            "US"
        ] = us

        symbols_cache[
            "CRYPTO"
        ] = crypto

        symbols_cache_time[
            "US"
        ] = now

        symbols_cache_time[
            "CRYPTO"
        ] = now

        log(
            f"🇺🇸 US: "
            f"{len(us)} رمز جاهز"
        )

        log(
            f"🪙 CRYPTO: "
            f"{len(crypto)} رمز جاهز"
        )

    except Exception as exc:

        log(
            "ℹ️ تحديث قائمة الرموز: "
            f"{exc}"
        )


# ============================================================
# 📈 HISTORY
# ============================================================

async def get_history(
    item,
    market
):

    params = {

        "symbol":
            item["symbol"],

        "interval":
            "1day",

        "outputsize":
            100,
    }

    # الأسهم الأمريكية
    if (
        market == "US"
        and item.get("exchange")
    ):

        params[
            "exchange"
        ] = item["exchange"]

    data = await twelve(
        "time_series",
        params
    )

    values = []

    meta = {}

    if isinstance(
        data,
        dict
    ):

        values = data.get(
            "values",
            []
        )

        meta = data.get(
            "meta",
            {}
        )

    if not values:

        return [], {}

    values = list(
        reversed(values)
    )

    return values, meta


# ============================================================
# 📊 EMA
# ============================================================

def ema(
    values,
    period
):

    if len(values) < period:

        return None

    result = sum(
        values[:period]
    ) / period

    multiplier = (
        2 / (period + 1)
    )

    for value in values[period:]:

        result = (
            (value - result)
            * multiplier
        ) + result

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
        sum(
            gains[:period]
        )
        / period
    )

    avg_loss = (
        sum(
            losses[:period]
        )
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

    if len(data) < (
        period + 1
    ):

        return None

    trs = []

    previous_close = None

    for row in data:

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

        except Exception:

            continue

        if min(
            high,
            low,
            close
        ) <= 0:

            continue

        if previous_close is None:

            tr = (
                high - low
            )

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
        )
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

def support_resistance(
    data
):

    recent = data[-30:]

    highs = []

    lows = []

    for row in recent:

        try:

            highs.append(
                float(
                    row["high"]
                )
            )

            lows.append(
                float(
                    row["low"]
                )
            )

        except Exception:

            pass

    if (
        not highs
        or not lows
    ):

        return None, None

    return (
        min(lows),
        max(highs)
    )


# ============================================================
# 📊 VOLUME
# ============================================================

def volume_strength(
    data
):

    if len(data) < 21:

        return 1.0

    values = []

    for row in data[-21:-1]:

        try:

            value = float(
                row.get(
                    "volume",
                    0
                )
            )

            if value > 0:

                values.append(
                    value
                )

        except Exception:

            pass

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
# 🧠 AI ANALYZE
# ============================================================

def analyze(
    market,
    item,
    history,
    meta
):

    if len(history) < 60:

        return None

    try:

        closes = []

        for row in history:

            close = float(
                row["close"]
            )

            if close > 0:

                closes.append(
                    close
                )

        if len(closes) < 60:

            return None

        price = closes[-1]

        previous = closes[-2]

        if previous > 0:

            change = (
                (
                    price
                    / previous
                ) - 1
            ) * 100

        else:

            change = 0.0

        if (
            market == "US"
            and price < MIN_US_PRICE
        ):

            return None

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

        atr14 = atr(
            history,
            14
        )

        support, resistance = (
            support_resistance(
                history
            )
        )

        volume = volume_strength(
            history
        )

        if any(
            value is None
            for value in [
                ema8,
                ema21,
                ema50,
                rsi14,
                atr14
            ]
        ):

            return None

        # ----------------------------------------------------
        # POWER ENGINE
        # ----------------------------------------------------

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

        total = max(
            buy + sell,
            1
        )

        buy_power = round(
            buy
            / total
            * 100
        )

        sell_power = round(
            sell
            / total
            * 100
        )

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

        # ----------------------------------------------------
        # 8 ATR TARGETS
        # ----------------------------------------------------

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

                target = (
                    price
                    + (
                        atr14
                        * multiplier
                    )
                )

            else:

                target = (
                    price
                    - (
                        atr14
                        * multiplier
                    )
                )

            targets.append(
                target
            )

        name = str(
            meta.get(
                "name",
                ""
            )
        ).strip()

        if not name:

            name = item.get(
                "name",
                item["symbol"]
            )

        return {

            "market":
                market,

            "symbol":
                item["symbol"],

            "name":
                name,

            "price":
                price,

            "change":
                change,

            "signal":
                signal,

            "strength":
                strength,

            "buy_power":
                buy_power,

            "sell_power":
                sell_power,

            "volume":
                volume,

            "ema8":
                ema8,

            "ema21":
                ema21,

            "ema50":
                ema50,

            "rsi":
                rsi14,

            "atr":
                atr14,

            "support":
                support,

            "resistance":
                resistance,

            "trend":
                trend,

            "targets":
                targets,

        }

    except Exception:

        return None


# ============================================================
# 🔢 NUMBER
# ============================================================

def number(value):

    if value is None:

        return "—"

    value = float(
        value
    )

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

        "chat_id":
            chat_id,

        "text":
            text,

        "disable_web_page_preview":
            True,

    }

    try:

        async with s.post(
            url,
            json=payload
        ) as response:

            return (
                response.status
                == 200
            )

    except Exception as exc:

        log(
            f"ℹ️ Telegram: {exc}"
        )

        return False


# ============================================================
# 📣 SIGNAL MESSAGE
# ============================================================

async def send_signal(
    signal
):

    market = signal[
        "market"
    ]

    token = token_for_market(
        market
    )

    if not token:

        return

    if signal[
        "signal"
    ] == "BUY":

        arrow = "🟢⬆️"

        title = "شراء قوي"

    else:

        arrow = "🔴⬇️"

        title = "بيع قوي"

    market_name = {

        "TASI":
            "🇸🇦 السوق السعودي (TASI)",

        "US":
            "🇺🇸 السوق الأمريكي (US)",

        "CRYPTO":
            "🪙 العملات الرقمية (CRYPTO)",

    }[market]

    target_lines = []

    for index, target in enumerate(
        signal["targets"],
        1
    ):

        if signal[
            "signal"
        ] == "BUY":

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

        target_lines.append(

            f"TP{index}: "
            f"{number(target)} "
            f"({percentage:+.1f}%)"

        )

    text = (

        "💀🚀 AI PRO MAX SIGNAL\n\n"

        f"{market_name}\n\n"

        f"{signal['symbol']}\n"

        f"{signal['name']}\n\n"

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
        f"{signal['trend']}\n\n"

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

def can_send(
    signal
):

    key = (

        signal["market"],

        signal["symbol"],

        signal["signal"],

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
# 🔎 SCAN ONE SYMBOL
# ============================================================

async def scan_one(
    market
):

    symbols = symbols_cache.get(
        market,
        []
    )

    if not symbols:

        log(
            f"ℹ️ {market}: "
            "لا توجد رموز محملة"
        )

        return

    index = (
        scan_pointer[market]
        % len(symbols)
    )

    item = symbols[
        index
    ]

    scan_pointer[market] = (
        index + 1
    ) % len(symbols)

    log(

        f"🔎 {market}: "
        f"فحص {item['symbol']} "
        f"({index + 1}/"
        f"{len(symbols)})"

    )

    try:

        history, meta = (
            await get_history(
                item,
                market
            )
        )

        signal = analyze(
            market,
            item,
            history,
            meta
        )

        if signal:

            if can_send(
                signal
            ):

                await send_signal(
                    signal
                )

                log(

                    f"📣 {market}: "
                    f"إشارة "
                    f"{signal['signal']} "
                    f"- "
                    f"{signal['symbol']}"

                )

    except Exception as exc:

        log(

            f"ℹ️ {market} "
            f"{item['symbol']}: "
            f"{exc}"

        )


# ============================================================
# 🔄 FULL SCAN
# ============================================================

async def full_scan():

    global market_turn

    await load_symbols()

    # --------------------------------------------------------
    # طلب بيانات واحد فقط في كل دورة
    # --------------------------------------------------------

    if market_turn % 2 == 0:

        market = "US"

    else:

        market = "CRYPTO"

    market_turn += 1

    await scan_one(
        market
    )


# ============================================================
# 🤖 START MESSAGE
# ============================================================

def startup_message(
    market
):

    market_name = {

        "TASI":
            "🇸🇦 السوق السعودي",

        "US":
            "🇺🇸 السوق الأمريكي",

        "CRYPTO":
            "🪙 العملات الرقمية",

    }[market]

    return (

        "💀🚀 AI PRO MAX\n\n"

        "✅ البوت يعمل الآن\n"

        "🔄 الفحص تلقائي وكامل\n"

        "⏱️ الفحص كل دقيقتين\n\n"

        f"📊 السوق: "
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

        "🤖 لا تحتاج إلى تشغيل "
        "الفحص يدويًا.\n\n"

        "📡 مصدر البيانات:\n"

        "Twelve Data فقط"

    )


# ============================================================
# 📲 TELEGRAM WEBHOOK
# ============================================================

async def telegram_webhook(
    request
):

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

async def health(
    request
):

    return web.json_response({

        "status":
            "ok",

        "system":
            "AI PRO MAX",

        "data":
            "Twelve Data",

        "scan_seconds":
            SCAN_SECONDS,

        "mode":
            "credit-safe rotating scan",

        "tasi_data":
            "غير متاح على Basic",

        "symbols": {

            "TASI":
                0,

            "US":
                len(
                    symbols_cache["US"]
                ),

            "CRYPTO":
                len(
                    symbols_cache["CRYPTO"]
                ),

        },

        "api_credits_left":
            api_credits_left,

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

        "https://api.telegram.org/"
        f"bot{token}/setWebhook"

    )

    webhook_url = (

        f"{base_url.rstrip('/')}"
        f"/telegram/"
        f"{market.lower()}"

    )

    try:

        s = await get_session()

        async with s.post(

            url,

            json={

                "url":
                    webhook_url,

                "drop_pending_updates":
                    True,

            }

        ) as response:

            if response.status == 200:

                log(

                    "Telegram Webhook: "
                    f"{market.lower()} ON"

                )

            else:

                body = await response.text()

                log(

                    f"ℹ️ Webhook "
                    f"{market}: "
                    f"HTTP "
                    f"{response.status} "
                    f"{body[:200]}"

                )

    except Exception as exc:

        log(

            f"ℹ️ Webhook "
            f"{market}: "
            f"{exc}"

        )


# ============================================================
# 🌐 SERVER
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

        f"🚀 AI PRO MAX يعمل "
        f"على PORT {PORT}"

    )

    return runner


# ============================================================
# 🔁 SCANNER LOOP
# ============================================================

async def scanner_loop():

    await asyncio.sleep(
        3
    )

    while True:

        started = time.monotonic()

        try:

            await full_scan()

        except Exception as exc:

            log(

                f"ℹ️ خطأ في دورة "
                f"الفحص: {exc}"

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

            f"⏱️ الدورة القادمة "
            f"خلال {wait} ثانية"

        )

        await asyncio.sleep(
            wait
        )


# ============================================================
# 🚀 MAIN
# ============================================================

async def main():

    log("=" * 60)

    log(
        "💀🚀 AI PRO MAX"
    )

    log("=" * 60)

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

        f"⏱️ الفحص كل "
        f"{SCAN_SECONDS} ثانية"

    )

    log(
        "📡 مصدر البيانات: "
        "Twelve Data"
    )

    log(
        "🛡️ حماية API: "
        "طلب بيانات واحد كل دورة"
    )

    log(
        "ℹ️ تاسي: بيانات "
        "السوق السعودي غير "
        "متاحة على Basic"
    )

    log("=" * 60)

    if not TWELVE_DATA_API_KEY:

        log(
            "ℹ️ مفتاح Twelve Data "
            "غير موجود"
        )

    runner = await start_server()

    domain = (
        os.getenv(
            "RAILWAY_PUBLIC_DOMAIN",
            ""
        ).strip()
        or
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
            ),

        )

    else:

        log(
            "ℹ️ لا يوجد Railway "
            "Public Domain"
        )

    try:

        await scanner_loop()

    finally:

        await runner.cleanup()

        if (
            session
            and not session.closed
        ):

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