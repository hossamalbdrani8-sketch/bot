
# ============================================================
# 💀🚀 AI PRO MAX — FINAL MARKET HUNTER V3
# 🇸🇦 TASI | 🇺🇸 US | 🪙 CRYPTO
# Twelve Data + SAHMK
# SUPPORT / RESISTANCE / TP1-TP8 / STOP LOSS
# ============================================================

import os
import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from html import escape

import aiohttp

# ============================================================
# 1. SETTINGS
# ============================================================

TWELVE_API_KEY = (
    os.getenv("TWELVE_DATA_API_KEY")
    or os.getenv("TWELVEDATA_API_KEY")
)

SAHMK_API_KEY = os.getenv("SAHMK_API_KEY")

CHAT_ID = os.getenv("CHAT_ID")

US_TOKEN = os.getenv("US_TOKEN")
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN")
TASI_TOKEN = os.getenv("TASI_TOKEN") or US_TOKEN

US_SYMBOLS = os.getenv(
    "US_SYMBOLS",
    "AAPL,TSLA,NVDA,AMD,PLTR"
).split(",")

CRYPTO_SYMBOLS = os.getenv(
    "CRYPTO_SYMBOLS",
    "BTC/USD,ETH/USD,SOL/USD,XRP/USD"
).split(",")

SCAN_SECONDS = int(os.getenv("SCAN_SECONDS", "300"))
TASI_SCAN_SECONDS = int(os.getenv("TASI_SCAN_SECONDS", "1800"))

MIN_SCORE = int(os.getenv("MIN_SCORE", "65"))
MIN_VOLUME_RATIO = float(
    os.getenv("MIN_VOLUME_RATIO", "1.5")
)

TD_BASE = "https://api.twelvedata.com"
SAHMK_BASE = "https://api.sahmk.sa/api/v1"

TD_CANDLES = 100
TASI_CANDLES = 100

# ============================================================
# 2. LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

sent_signals = {}


# ============================================================
# 3. GENERAL FUNCTIONS
# ============================================================

def clean_symbols(items):
    return list(dict.fromkeys(
        item.strip().upper()
        for item in items
        if item.strip()
    ))


US_SYMBOLS = clean_symbols(US_SYMBOLS)
CRYPTO_SYMBOLS = clean_symbols(CRYPTO_SYMBOLS)


def num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def fmt(value, digits=3):
    if value is None:
        return "غير متاح"

    return f"{value:,.{digits}f}"


def ema(values, period):
    if len(values) < period:
        return None

    result = sum(values[:period]) / period
    multiplier = 2 / (period + 1)

    for value in values[period:]:
        result = (
            value * multiplier
            + result * (1 - multiplier)
        )

    return result


def calculate_rsi(values, period=14):
    if len(values) <= period:
        return 50.0

    gains = []
    losses = []

    for i in range(1, len(values)):
        change = values[i] - values[i - 1]

        gains.append(max(change, 0))
        losses.append(max(-change, 0))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def calculate_atr(rows, period=14):
    if len(rows) < period + 1:
        return None

    ranges = []

    for i in range(1, len(rows)):
        high = num(rows[i].get("high"))
        low = num(rows[i].get("low"))
        previous_close = num(rows[i - 1].get("close"))

        tr = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close)
        )

        ranges.append(tr)

    return sum(ranges[-period:]) / period


def calculate_vwap(rows):
    total_value = 0.0
    total_volume = 0.0

    for row in rows:
        typical = (
            num(row.get("high"))
            + num(row.get("low"))
            + num(row.get("close"))
        ) / 3

        volume = num(row.get("volume"))

        total_value += typical * volume
        total_volume += volume

    if total_volume <= 0:
        return None

    return total_value / total_volume


def calculate_volume_ratio(rows):
    if len(rows) < 21:
        return 0.0

    previous_volumes = [
        num(row.get("volume"))
        for row in rows[-21:-1]
    ]

    average = sum(previous_volumes) / len(previous_volumes)

    if average <= 0:
        return 0.0

    return num(rows[-1].get("volume")) / average


# ============================================================
# 4. SUPPORT & RESISTANCE
# ============================================================

def calculate_levels(rows):

    if len(rows) < 25:
        return None

    highs = [num(x.get("high")) for x in rows]
    lows = [num(x.get("low")) for x in rows]
    closes = [num(x.get("close")) for x in rows]

    price = closes[-1]

    pivot_highs = []
    pivot_lows = []

    start = max(2, len(rows) - 80)
    end = len(rows) - 2

    for i in range(start, end):

        if (
            highs[i] >= highs[i - 1]
            and highs[i] >= highs[i - 2]
            and highs[i] > highs[i + 1]
            and highs[i] > highs[i + 2]
        ):
            pivot_highs.append(highs[i])

        if (
            lows[i] <= lows[i - 1]
            and lows[i] <= lows[i - 2]
            and lows[i] < lows[i + 1]
            and lows[i] < lows[i + 2]
        ):
            pivot_lows.append(lows[i])

    supports = sorted(
        set(x for x in pivot_lows if x < price),
        reverse=True
    )

    resistances = sorted(
        set(x for x in pivot_highs if x > price)
    )

    if not supports:
        supports = sorted(
            set(x for x in lows[-20:] if x < price),
            reverse=True
        )

    if not resistances:
        resistances = sorted(
            set(x for x in highs[-20:] if x > price)
        )

    return {
        "supports": supports[:3],
        "resistances": resistances[:3]
    }


# ============================================================
# 5. TARGETS TP1 - TP8
# ============================================================

def calculate_targets(price, atr, supports):

    if not atr or atr <= 0:
        return None

    stop = price - (1.5 * atr)

    if supports:
        nearest_support = supports[0]

        if nearest_support < price:
            stop = min(
                stop,
                nearest_support - (0.15 * atr)
            )

    targets = []

    for multiplier in range(1, 9):
        targets.append(
            price + (atr * multiplier)
        )

    return {
        "stop": stop,
        "targets": targets
    }


# ============================================================
# 6. SIGNAL COOLDOWN
# ============================================================

def allow_signal(symbol, signal, seconds=1800):

    key = f"{symbol}:{signal}"
    now = datetime.now().timestamp()

    last = sent_signals.get(key, 0)

    return now - last >= seconds


def mark_signal(symbol, signal):

    sent_signals[f"{symbol}:{signal}"] = (
        datetime.now().timestamp()
    )


# ============================================================
# 7. HTTP
# ============================================================

async def get_json(
    session,
    url,
    params=None,
    headers=None
):

    try:

        async with session.get(
            url,
            params=params,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=25)
        ) as response:

            data = await response.json(
                content_type=None
            )

            if response.status != 200:

                logging.warning(
                    "HTTP %s: %s",
                    response.status,
                    str(data)[:300]
                )

                return None

            if isinstance(data, dict):

                if data.get("status") == "error":
                    logging.warning("API error: %s", data)
                    return None

                if data.get("error"):
                    logging.warning("API error: %s", data)
                    return None

                if (
                    data.get("code")
                    and not data.get("data")
                ):
                    logging.warning("API error: %s", data)
                    return None

            return data

    except Exception as error:

        logging.warning(
            "Request failed: %s",
            error
        )

        return None


# ============================================================
# 8. TELEGRAM
# ============================================================

async def telegram_send(
    session,
    token,
    message
):

    if not token or not CHAT_ID:

        logging.warning(
            "Telegram token or CHAT_ID missing"
        )

        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{token}/sendMessage"
    )

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:

        async with session.post(
            url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=20)
        ) as response:

            result = await response.json(
                content_type=None
            )

            if result.get("ok"):
                return True

            logging.warning(
                "Telegram rejected message: %s",
                result
            )

            return False

    except Exception as error:

        logging.error(
            "Telegram send error: %s",
            error
        )

        return False


# ============================================================
# 9. TELEGRAM MESSAGE — IMAGE STYLE
# ============================================================

def build_signal_message(
    market,
    symbol,
    name,
    price,
    score,
    rsi,
    vol_ratio,
    vwap,
    atr,
    levels,
    targets_data,
    reasons,
    currency
):

    supports = levels["supports"]
    resistances = levels["resistances"]

    targets = targets_data["targets"]
    stop = targets_data["stop"]

    name = escape(str(name))
    symbol = escape(str(symbol))
    market = escape(str(market))

    def price_fmt(value):
        if value is None:
            return "غير متاح"

        return f"{value:,.3f}"

    def percent(value):

        if price <= 0:
            return 0

        return ((value - price) / price) * 100

    if score >= 85:
        signal_title = "🚀 اختراق قوي"

    elif score >= 70:
        signal_title = "🟢 إشارة صاعدة"

    else:
        signal_title = "🟡 مراقبة مبكرة"

    message = (
        "💀🚀 <b>AI PRO MAX — MARKET HUNTER</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🌍 السوق: {market}\n"
        f"📌 السهم: <b>{name}</b>\n"
        f"🔢 الرمز: <b>{symbol}</b>\n"
        f"💰 السعر: <b>{price_fmt(price)} {currency}</b>\n"
        f"⭐ قوة الإشارة: <b>{score}/100</b>\n"
        f"📊 RSI: {rsi:.1f}\n"
        f"💹 حجم التداول: ×{vol_ratio:.2f}\n"
        f"📈 VWAP: {price_fmt(vwap)}\n"
        f"📏 ATR: {price_fmt(atr)}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🟢 <b>مناطق الدعم</b>\n"
    )

    # الدعم S1 - S3

    for i in range(3):

        value = (
            supports[i]
            if i < len(supports)
            else None
        )

        message += (
            f"S{i + 1}: "
            f"{price_fmt(value)}\n"
        )

    message += "\n🔴 <b>مناطق المقاومة</b>\n"

    # المقاومة R1 - R3

    for i in range(3):

        value = (
            resistances[i]
            if i < len(resistances)
            else None
        )

        message += (
            f"R{i + 1}: "
            f"{price_fmt(value)}\n"
        )

    message += (
        "━━━━━━━━━━━━━━━━━━\n"
        "🎯 <b>الأهداف السعرية</b>\n"
    )

    # الأهداف TP1 - TP8

    for i, target in enumerate(targets, 1):

        change = percent(target)

        message += (
            f"🟢 TP{i}: {price_fmt(target)} "
            f"({change:+.2f}%)\n"
        )

    stop_change = percent(stop)

    message += (
        "━━━━━━━━━━━━━━━━━━\n"
        f"🛑 <b>وقف الخسارة الفني:</b>\n"
        f"{price_fmt(stop)} {currency} "
        f"({stop_change:+.2f}%)\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🧠 <b>أسباب الإشارة: {signal_title}</b>\n"
    )

    for reason in reasons:

        message += (
            f"✅ {escape(str(reason))}\n"
        )

    message += (
        "━━━━━━━━━━━━━━━━━━\n"
        "📊 <b>ملخص التحليل</b>\n"
        f"قوة الإشارة: {score}/100\n"
        f"ATR: {price_fmt(atr)}\n"
        f"حجم التداول النسبي: ×{vol_ratio:.2f}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "⚠️ المستويات محسوبة من الشموع المتاحة.\n"
        "⚠️ الأهداف احتمالات متابعة وليست ضماناً للوصول.\n"
        "⚠️ الإشارة تحليل فني وليست توصية شراء."
    )

    return message


# ============================================================
# 10. TECHNICAL ANALYSIS
# ============================================================

async def analyze_rows(
    session,
    symbol,
    name,
    market,
    rows,
    token,
    currency
):

    if not rows or len(rows) < 25:

        logging.info(
            "%s: insufficient candles",
            symbol
        )

        return

    closes = [
        num(x.get("close"))
        for x in rows
    ]

    if any(x <= 0 for x in closes[-25:]):
        return

    price = closes[-1]
    previous_price = closes[-2]

    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)

    rsi = calculate_rsi(closes)
    atr = calculate_atr(rows)
    vwap = calculate_vwap(rows)
    vol_ratio = calculate_volume_ratio(rows)

    if atr is None or atr <= 0:
        return

    levels = calculate_levels(rows)

    if not levels:
        return

    targets_data = calculate_targets(
        price,
        atr,
        levels["supports"]
    )

    if not targets_data:
        return

    score = 0
    reasons = []

    # المتوسطات

    if ema9 and ema21 and ema9 > ema21:

        score += 15
        reasons.append(
            "الاتجاه قصير الأجل صاعد"
        )

    # VWAP

    if vwap and price > vwap:

        score += 15
        reasons.append(
            "السعر أعلى VWAP"
        )

    # حجم التداول

    if vol_ratio >= MIN_VOLUME_RATIO:

        score += 20
        reasons.append(
            f"نشاط تداول أعلى من المتوسط ×{vol_ratio:.2f}"
        )

    # RSI

    if 50 <= rsi <= 75:

        score += 10
        reasons.append(
            f"RSI إيجابي {rsi:.1f}"
        )

    # الاختراق

    nearest_resistance = (
        levels["resistances"][0]
        if levels["resistances"]
        else None
    )

    breakout = (
        nearest_resistance is not None
        and price > nearest_resistance
    )

    if breakout:

        score += 25
        reasons.append(
            "اختراق مقاومة تاريخية"
        )

    # بداية الصعود

    early = (
        ema9 is not None
        and ema21 is not None
        and price > ema9
        and previous_price <= ema9
    )

    if early:

        score += 10
        reasons.append(
            "بداية تحرك صاعد"
        )

    # قوة الشمعة

    last_high = num(rows[-1].get("high"))
    last_low = num(rows[-1].get("low"))

    candle_range = last_high - last_low

    if candle_range > 0:

        close_position = (
            (price - last_low) / candle_range
        )

        if close_position >= 0.75:

            score += 5
            reasons.append(
                "إغلاق قريب من قمة الشمعة"
            )

    if score < MIN_SCORE:
        return

    signal = (
        "BREAKOUT"
        if breakout
        else "EARLY"
    )

    if not allow_signal(symbol, signal):
        return

    message = build_signal_message(
        market=market,
        symbol=symbol,
        name=name,
        price=price,
        score=score,
        rsi=rsi,
        vol_ratio=vol_ratio,
        vwap=vwap,
        atr=atr,
        levels=levels,
        targets_data=targets_data,
        reasons=reasons,
        currency=currency
    )

    success = await telegram_send(
        session,
        token,
        message
    )

    if success:

        mark_signal(symbol, signal)

        logging.info(
            "Signal sent: %s | %s | score=%s",
            market,
            symbol,
            score
        )


# ============================================================
# 11. TWELVE DATA
# ============================================================

async def get_td_candles(
    session,
    symbol,
    market
):

    if not TWELVE_API_KEY:
        return None

    params = {
        "symbol": symbol,
        "interval": "5min",
        "outputsize": TD_CANDLES,
        "apikey": TWELVE_API_KEY
    }

    if market == "US":
        params["prepost"] = "true"

    data = await get_json(
        session,
        f"{TD_BASE}/time_series",
        params=params
    )

    if not data or not isinstance(data, dict):
        return None

    values = data.get("values")

    if not isinstance(values, list):
        return None

    return list(reversed(values))


async def scan_td_market(
    session,
    symbols,
    market
):

    token = (
        US_TOKEN
        if market == "US"
        else CRYPTO_TOKEN
    )

    currency = "USD"

    semaphore = asyncio.Semaphore(3)

    async def worker(symbol):

        async with semaphore:

            rows = await get_td_candles(
                session,
                symbol,
                market
            )

            if not rows:
                return

            await analyze_rows(
                session=session,
                symbol=symbol,
                name=symbol,
                market=market,
                rows=rows,
                token=token,
                currency=currency
            )

    await asyncio.gather(
        *(
            worker(symbol)
            for symbol in symbols
        ),
        return_exceptions=True
    )


# ============================================================
# 12. SAHMK HISTORICAL DATA
# ============================================================

async def get_sahmk_history(
    session,
    symbol
):

    if not SAHMK_API_KEY:
        return None

    headers = {
        "X-API-Key": SAHMK_API_KEY
    }

    today = datetime.now(
        ZoneInfo("Asia/Riyadh")
    ).date()

    start = today - timedelta(days=180)

    params = {
        "interval": "1d",
        "from": start.isoformat(),
        "to": today.isoformat(),
        "limit": TASI_CANDLES,
        "offset": 0
    }

    data = await get_json(
        session,
        f"{SAHMK_BASE}/historical/{symbol}/",
        params=params,
        headers=headers
    )

    if not isinstance(data, dict):
        return None

    rows = data.get("data")

    if not isinstance(rows, list):
        return None

    return rows


# ============================================================
# 13. SAHMK MARKET LISTS
# ============================================================

async def get_sahmk_market_list(
    session,
    endpoint
):

    headers = {
        "X-API-Key": SAHMK_API_KEY
    }

    data = await get_json(
        session,
        f"{SAHMK_BASE}/market/{endpoint}/",
        params={
            "limit": 30,
            "market": "TASI"
        },
        headers=headers
    )

    if not isinstance(data, dict):
        return []

    for key in (
        "data",
        "results",
        "gainers",
        "leaders",
        "stocks",
        "items"
    ):

        value = data.get(key)

        if isinstance(value, list):
            return value

    return []


async def scan_tasi(session):

    if not SAHMK_API_KEY:

        logging.warning(
            "SAHMK_API_KEY missing"
        )

        return

    gainers = await get_sahmk_market_list(
        session,
        "gainers"
    )

    volume_leaders = await get_sahmk_market_list(
        session,
        "volume"
    )

    selected = {}

    for item in gainers + volume_leaders:

        if not isinstance(item, dict):
            continue

        symbol = str(
            item.get("symbol")
            or item.get("ticker")
            or ""
        ).strip()

        if symbol:
            selected[symbol] = item

    logging.info(
        "TASI selected symbols: %s",
        len(selected)
    )

    semaphore = asyncio.Semaphore(2)

    async def worker(symbol, item):

        async with semaphore:

            rows = await get_sahmk_history(
                session,
                symbol
            )

            if not rows:

                logging.info(
                    "No historical candles for TASI %s",
                    symbol
                )

                return

            name = (
                item.get("name")
                or item.get("name_ar")
                or item.get("name_en")
                or symbol
            )

            await analyze_rows(
                session=session,
                symbol=symbol,
                name=name,
                market="السوق السعودي",
                rows=rows,
                token=TASI_TOKEN,
                currency="SAR"
            )

    await asyncio.gather(
        *(
            worker(symbol, item)
            for symbol, item in selected.items()
        ),
        return_exceptions=True
    )


# ============================================================
# 14. MAIN LOOP — 24/7
# ============================================================

async def main():

    if not CHAT_ID:
        raise RuntimeError(
            "CHAT_ID is missing"
        )

    if not TWELVE_API_KEY:
        raise RuntimeError(
            "TWELVE_DATA_API_KEY is missing"
        )

    logging.info(
        "AI PRO MAX V3 STARTED | US=%s | CRYPTO=%s",
        len(US_SYMBOLS),
        len(CRYPTO_SYMBOLS)
    )

    connector = aiohttp.TCPConnector(
        limit=10,
        ttl_dns_cache=300
    )

    last_tasi_scan = 0

    async with aiohttp.ClientSession(
        connector=connector
    ) as session:

        while True:

            cycle_start = (
                datetime.now().timestamp()
            )

            try:

                # 🇺🇸 الأمريكي

                if US_SYMBOLS:

                    await scan_td_market(
                        session,
                        US_SYMBOLS,
                        "US"
                    )

                # 🪙 الكريبتو

                if CRYPTO_SYMBOLS:

                    await scan_td_market(
                        session,
                        CRYPTO_SYMBOLS,
                        "CRYPTO"
                    )

                # 🇸🇦 السعودي

                now = datetime.now().timestamp()

                if (
                    now - last_tasi_scan
                    >= TASI_SCAN_SECONDS
                ):

                    await scan_tasi(session)

                    last_tasi_scan = now

            except Exception:

                logging.exception(
                    "Main loop error"
                )

            elapsed = (
                datetime.now().timestamp()
                - cycle_start
            )

            sleep_time = max(
                10,
                SCAN_SECONDS - elapsed
            )

            logging.info(
                "Cycle complete. Next scan in %.0f seconds",
                sleep_time
            )

            await asyncio.sleep(
                sleep_time
            )


# ============================================================
# 15. START
# ============================================================

if __name__ == "__main__":

    asyncio.run(main())
