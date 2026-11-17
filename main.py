
import io
from PIL import Image, ImageDraw, ImageFont
import os
import asyncio
import logging
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

import aiohttp

# =========================================================
# AI PRO MAX — MARKET HUNTER V8.0
# US | TASI | CRYPTO — SEPARATE TELEGRAM BOTS
# =========================================================

TD_KEY = os.getenv("TWELVE_DATA_API_KEY") or os.getenv("TWELVEDATA_API_KEY")
SAHMK_KEY = os.getenv("SAHMK_API_KEY")

US_TOKEN = os.getenv("US_TOKEN")
TASI_TOKEN = os.getenv("TASI_TOKEN")
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN")

CHAT_ID = os.getenv("CHAT_ID")
US_CHAT_ID = os.getenv("US_CHAT_ID") or CHAT_ID
TASI_CHAT_ID = os.getenv("TASI_CHAT_ID") or CHAT_ID
CRYPTO_CHAT_ID = os.getenv("CRYPTO_CHAT_ID") or CHAT_ID

TD_BASE = "https://api.twelvedata.com"
SAHMK_BASE = "https://api.sahmk.sa/api/v1"

SCAN_SECONDS = int(os.getenv("SCAN_SECONDS", "300"))
US_BATCH_SIZE = int(os.getenv("US_BATCH_SIZE", "20"))
CRYPTO_BATCH_SIZE = int(os.getenv("CRYPTO_BATCH_SIZE", "20"))
MIN_US_PRICE = 0.15
MAX_RESULTS = int(os.getenv("MAX_RESULTS", "15"))
TIMEZONE = ZoneInfo("Asia/Riyadh")

US_EXCHANGES = {
    "NASDAQ",
    "NYSE",
    "NYSE AMERICAN",
    "NYSEAMERICAN",
    "AMEX"
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("AI_PRO_MAX")

sent = {}
universe = {"US": [], "CRYPTO": []}
positions = {"US": 0, "CRYPTO": 0}


# =========================================================
# BASIC FUNCTIONS
# =========================================================

def number(value, default=0.0):
    try:
        result = float(value)
        return result if result == result else default
    except (ValueError, TypeError):
        return default


def fmt(value):
    return f"{value:,.4f}" if abs(value) < 1 else f"{value:,.2f}"


def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


async def get_json(session, url, params=None, headers=None):
    try:
        async with session.get(
            url,
            params=params,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            data = await response.json(content_type=None)

            if response.status != 200:
                log.warning("API HTTP %s: %s", response.status, str(data)[:250])
                return None

            if isinstance(data, dict) and (
                data.get("status") == "error"
                or data.get("code") == 429
                or data.get("message") and not data.get("values")
            ):
                log.warning("API response: %s", str(data)[:250])
                return None

            return data

    except Exception:
        log.exception("API connection error")
        return None


# =========================================================
# TELEGRAM — THREE SEPARATE CHANNELS
# =========================================================

async def telegram_send(session, token, chat_id, message):
    if not token or not chat_id:
        log.error("Telegram token or chat ID missing")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    try:
        async with session.post(
            url,
            json={
                "chat_id": chat_id,
                "text": message,
                "disable_web_page_preview": True
            },
            timeout=aiohttp.ClientTimeout(total=25)
        ) as response:

            result = await response.json(content_type=None)

            if response.status == 200 and result.get("ok"):
                return True

            log.error("Telegram error: %s", str(result)[:300])

    except Exception:
        log.exception("Telegram delivery error")

    return False


async def startup(session):
    bots = [
        (US_TOKEN, US_CHAT_ID, "🇺🇸 الماسح الأمريكي"),
        (TASI_TOKEN, TASI_CHAT_ID, "🇸🇦 الماسح السعودي"),
        (CRYPTO_TOKEN, CRYPTO_CHAT_ID, "🪙 ماسح العملات الرقمية")
    ]

    for token, chat, name in bots:
        if token and chat:
            await telegram_send(
                session, token, chat,
                f"💀🚀 AI PRO MAX V8.0\n"
                f"🟢 {name}\n"
                f"تم تشغيل الماسح بنجاح\n"
                f"📡 البيانات والمؤشرات قيد الفحص\n"
                f"🕒 {datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}"
            )


# =========================================================
# TECHNICAL INDICATORS
# =========================================================

def ema(values, period):
    if len(values) < period:
        return None

    result = sum(values[:period]) / period
    alpha = 2 / (period + 1)

    for value in values[period:]:
        result = value * alpha + result * (1 - alpha)

    return result


def calculate_vwap(rows):
    total_value = 0.0
    total_volume = 0.0

    for row in rows:
        volume = number(row.get("volume"))
        high = number(row.get("high"))
        low = number(row.get("low"))
        close = number(row.get("close"))

        if volume <= 0:
            continue

        typical = (high + low + close) / 3
        total_value += typical * volume
        total_volume += volume

    if total_volume <= 0:
        return None

    return total_value / total_volume


def normalize_candles(data):
    if not isinstance(data, dict):
        return []

    values = data.get("values")

    if not isinstance(values, list):
        return []

    rows = []

    for item in reversed(values):
        close = number(item.get("close"))

        if close <= 0:
            continue

        rows.append({
            "open": number(item.get("open")),
            "high": number(item.get("high")),
            "low": number(item.get("low")),
            "close": close,
            "volume": number(item.get("volume"))
        })

    return rows


def analyze(rows):
    if len(rows) < 50:
        return None

    closes = [r["close"] for r in rows]
    price = closes[-1]
    previous = closes[-2]

    if price <= 0:
        return None

    averages = {
        10: ema(closes, 10),
        14: ema(closes, 14),
        25: ema(closes, 25),
        50: ema(closes, 50)
    }

    vwap = calculate_vwap(rows)

    volumes = [r["volume"] for r in rows]
    avg_volume = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else 0
    current_volume = volumes[-1]

    activity = (
        current_volume / avg_volume if avg_volume > 0 else 0
    )

    liquidity = price * current_volume

    change = (
        (price - previous) / previous * 100
        if previous > 0 else 0
    )

    rising = (
        averages[10] is not None
        and averages[14] is not None
        and averages[25] is not None
        and averages[50] is not None
        and averages[10] > averages[14] > averages[25] > averages[50]
    )

    return {
        "price": price,
        "change": change,
        "volume": current_volume,
        "liquidity": liquidity,
        "activity": activity,
        "vwap": vwap,
        "ema": averages,
        "rising": rising,
        "high": max(r["high"] for r in rows[-20:]),
        "low": min(r["low"] for r in rows[-20:])
    }


# =========================================================
# MESSAGE BUILDER
# =========================================================

def build_message(market, symbol, name, result, currency):
    e = result["ema"]

    direction = (
        "🟢 اتجاه صاعد"
        if result["rising"]
        else "🟡 اتجاه غير مكتمل"
    )

    vwap_state = (
        "🟢 أعلى VWAP"
        if result["vwap"] is not None
        and result["price"] > result["vwap"]
        else "🔴 أسفل VWAP"
        if result["vwap"] is not None
        else "غير متاح"
    )

    return (
        f"💀🚀 AI PRO MAX V8.0\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🌍 {market}\n"
        f"📌 {symbol} | {name}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 السعر: {fmt(result['price'])} {currency}\n"
        f"📈 نسبة التغير: {result['change']:+.2f}%\n"
        f"📊 الحجم الفعلي: {result['volume']:,.0f}\n"
        f"💵 قيمة التداول: {result['liquidity']:,.2f} {currency}\n"
        f"⚡ النشاط: x{result['activity']:.2f}\n"
        f"📍 VWAP: {fmt(result['vwap']) if result['vwap'] is not None else 'غير متاح'}\n"
        f"{vwap_state}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"EMA10: {fmt(e[10])}\n"
        f"EMA14: {fmt(e[14])}\n"
        f"EMA25: {fmt(e[25])}\n"
        f"EMA50: {fmt(e[50])}\n"
        f"{direction}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔺 مقاومة تقريبية: {fmt(result['high'])}\n"
        f"🟢 دعم تقريبي: {fmt(result['low'])}\n"
        f"🕒 {datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"⚠️ بيانات تحليلية وليست توصية استثمارية."
    )


# =========================================================
# US MARKET — FULL SYMBOL DISCOVERY
# =========================================================

async def load_us_universe(session):
    if not TD_KEY:
        log.error("Twelve Data key missing")
        return

    data = await get_json(
        session,
        f"{TD_BASE}/stocks",
        params={
            "country": "United States",
            "format": "JSON",
            "apikey": TD_KEY
        }
    )

    items = data.get("data", []) if isinstance(data, dict) else data

    if not isinstance(items, list):
        log.error("US stock directory unavailable")
        return

    selected = {}

    for item in items:
        if not isinstance(item, dict):
            continue

        symbol = str(item.get("symbol", "")).strip().upper()
        exchange = str(item.get("exchange", "")).strip().upper()
        name = str(item.get("name", symbol))

        if not symbol:
            continue

        if exchange not in US_EXCHANGES:
            continue

        if item.get("country") not in (None, "", "United States"):
            continue

        if item.get("type") and item["type"] not in (
            "Common Stock", "American Depositary Receipt"
        ):
            continue

        selected[symbol] = {
            "symbol": symbol,
            "name": name,
            "exchange": exchange
        }

    universe["US"] = list(selected.values())

    log.info("US universe loaded: %s symbols", len(universe["US"]))


async def scan_us_symbol(session, item):
    symbol = item["symbol"]

    data = await get_json(
        session,
        f"{TD_BASE}/time_series",
        params={
            "symbol": symbol,
            "interval": "5min",
            "outputsize": 100,
            "prepost": "true",
            "apikey": TD_KEY
        }
    )

    rows = normalize_candles(data)

    if len(rows) < 50:
        return None

    result = analyze(rows)

    if not result or result["price"] < MIN_US_PRICE:
        return None

    return {
        "symbol": symbol,
        "name": item["name"],
        "result": result
    }


async def us_loop(session):
    if not US_TOKEN or not US_CHAT_ID or not TD_KEY:
        log.error("US bot settings incomplete")
        return

    await load_us_universe(session)

    while not universe["US"]:
        await asyncio.sleep(60)
        await load_us_universe(session)

    while True:
        try:
            items = universe["US"]
            start = positions["US"]
            batch = items[start:start + US_BATCH_SIZE]

            if len(batch) < US_BATCH_SIZE:
                batch += items[:US_BATCH_SIZE - len(batch)]

            positions["US"] = (start + US_BATCH_SIZE) % len(items)

            semaphore = asyncio.Semaphore(3)

            async def worker(item):
                async with semaphore:
                    try:
                        return await scan_us_symbol(session, item)
                    except Exception:
                        log.exception("US scan failed: %s", item["symbol"])
                        return None

            results = await asyncio.gather(
                *(worker(item) for item in batch)
            )

            results = [x for x in results if x]

            results.sort(
                key=lambda x: x["result"]["change"],
                reverse=True
            )

            for item in results[:MAX_RESULTS]:
                key = "US:" + item["symbol"]
                now = datetime.now().timestamp()

                if now - sent.get(key, 0) < 1800:
                    continue

                message = build_message(
                    "🇺🇸 السوق الأمريكي",
                    item["symbol"],
                    item["name"],
                    item["result"],
                    "USD"
                )

                if await telegram_send(
                    session, US_TOKEN, US_CHAT_ID, message
                ):
                    sent[key] = now

            log.info(
                "US scanned %s | results %s",
                len(batch), len(results)
            )

            await asyncio.sleep(SCAN_SECONDS)

        except Exception:
            log.exception("US loop error")
            await asyncio.sleep(60)


# =========================================================
# CRYPTO — 24/7
# =========================================================

async def load_crypto_universe(session):
    data = await get_json(
        session,
        f"{TD_BASE}/cryptocurrencies",
        params={"apikey": TD_KEY}
    )

    items = data.get("data", []) if isinstance(data, dict) else data

    if not isinstance(items, list):
        return

    selected = {}

    for item in items:
        if not isinstance(item, dict):
            continue

        symbol = str(item.get("symbol", "")).strip().upper()

        if "/" not in symbol:
            continue

        base, quote = symbol.split("/", 1)

        if quote not in ("USD", "USDT"):
            continue

        if not base:
            continue

        selected[symbol] = {
            "symbol": symbol,
            "name": item.get("currency_base", base)
        }

    universe["CRYPTO"] = list(selected.values())

    log.info("Crypto pairs loaded: %s", len(universe["CRYPTO"]))


async def scan_crypto_symbol(session, item):
    data = await get_json(
        session,
        f"{TD_BASE}/time_series",
        params={
            "symbol": item["symbol"],
            "interval": "5min",
            "outputsize": 100,
            "apikey": TD_KEY
        }
    )

    rows = normalize_candles(data)

    if len(rows) < 50:
        return None

    result = analyze(rows)

    if not result:
        return None

    return {
        "symbol": item["symbol"],
        "name": item["name"],
        "result": result
    }


async def crypto_loop(session):
    if not CRYPTO_TOKEN or not CRYPTO_CHAT_ID or not TD_KEY:
        log.error("Crypto bot settings incomplete")
        return

    await load_crypto_universe(session)

    while not universe["CRYPTO"]:
        await asyncio.sleep(60)
        await load_crypto_universe(session)

    while True:
        try:
            items = universe["CRYPTO"]
            start = positions["CRYPTO"]

            batch = items[start:start + CRYPTO_BATCH_SIZE]

            if len(batch) < CRYPTO_BATCH_SIZE:
                batch += items[:CRYPTO_BATCH_SIZE - len(batch)]

            positions["CRYPTO"] = (
                start + CRYPTO_BATCH_SIZE
            ) % len(items)

            semaphore = asyncio.Semaphore(3)

            async def worker(item):
                async with semaphore:
                    try:
                        return await scan_crypto_symbol(session, item)
                    except Exception:
                        log.exception(
                            "Crypto scan failed: %s", item["symbol"]
                        )
                        return None

            results = await asyncio.gather(
                *(worker(item) for item in batch)
            )

            results = [x for x in results if x]

            results.sort(
                key=lambda x: x["result"]["change"],
                reverse=True
            )

            for item in results[:MAX_RESULTS]:
                key = "CRYPTO:" + item["symbol"]
                now = datetime.now().timestamp()

                if now - sent.get(key, 0) < 1800:
                    continue

                message = build_message(
                    "🪙 العملات الرقمية",
                    item["symbol"],
                    item["name"],
                    item["result"],
                    "USD"
                )

                if await telegram_send(
                    session, CRYPTO_TOKEN,
                    CRYPTO_CHAT_ID, message
                ):
                    sent[key] = now

            log.info(
                "CRYPTO scanned %s | results %s",
                len(batch), len(results)
            )

            await asyncio.sleep(SCAN_SECONDS)

        except Exception:
            log.exception("Crypto loop error")
            await asyncio.sleep(60)


# =========================================================
# SAUDI MARKET — SAHMK
# =========================================================

def saudi_market_active():
    now = datetime.now(TIMEZONE)

    # Sunday to Thursday
    if now.weekday() not in (6, 0, 1, 2, 3):
        return False

    # Pre-open starts 09:30, regular session ends 15:00
    current = now.time()

    return dtime(9, 30) <= current <= dtime(15, 0)


async def sahmk_get(session, endpoint, params=None):
    return await get_json(
        session,
        f"{SAHMK_BASE}/{endpoint}/",
        params=params or {},
        headers={"X-API-Key": SAHMK_KEY}
    )


async def scan_saudi_symbol(session, item):
    symbol = str(item.get("symbol", "")).strip()

    if not symbol:
        return None

    today = datetime.now(TIMEZONE).date()
    start = today - timedelta(days=180)

    data = await sahmk_get(
        session,
        f"historical/{symbol}",
        {
            "interval": "5min",
            "from": start.isoformat(),
            "to": today.isoformat(),
            "limit": 500,
            "offset": 0
        }
    )

    if not isinstance(data, dict):
        return None

    values = data.get("data", [])

    if isinstance(values, dict):
        values = (
            values.get("results")
            or values.get("items")
            or values.get("candles")
            or []
        )

    if not isinstance(values, list):
        return None

    rows = []

    for x in values:
        rows.append({
            "open": number(x.get("open")),
            "high": number(x.get("high")),
            "low": number(x.get("low")),
            "close": number(x.get("close")),
            "volume": number(x.get("volume"))
        })

    result = analyze(rows)

    if not result:
        return None

    return {
        "symbol": symbol,
        "name": item.get("name", symbol),
        "result": result
    }


async def saudi_loop(session):
    if not TASI_TOKEN or not TASI_CHAT_ID or not SAHMK_KEY:
        log.error("TASI bot settings incomplete")
        return

    while True:
        try:
            if not saudi_market_active():
                await asyncio.sleep(60)
                continue

            gainers, volume, value = await asyncio.gather(
                sahmk_get(session, "market/gainers", {"limit": 50, "index": "TASI"}),
                sahmk_get(session, "market/volume", {"limit": 50, "index": "TASI"}),
                sahmk_get(session, "market/value", {"limit": 50, "index": "TASI"})
            )

            selected = {}

            for data, key_name in (
                (gainers, "gainers"),
                (volume, "volume"),
                (value, "value")
            ):
                if not isinstance(data, dict):
                    continue

                values = data.get(key_name, data.get("data", []))

                if isinstance(values, dict):
                    values = values.get("results", [])

                if not isinstance(values, list):
                    continue

                for item in values:
                    if isinstance(item, dict):
                        symbol = str(item.get("symbol", "")).strip()
                        if symbol:
                            selected[symbol] = item

            semaphore = asyncio.Semaphore(3)

            async def worker(item):
                async with semaphore:
                    try:
                        return await scan_saudi_symbol(session, item)
                    except Exception:
                        log.exception(
                            "TASI scan failed: %s",
                            item.get("symbol")
                        )
                        return None

            results = await asyncio.gather(
                *(worker(item) for item in selected.values())
            )

            results = [x for x in results if x]

            results.sort(
                key=lambda x: x["result"]["change"],
                reverse=True
            )

            for item in results[:MAX_RESULTS]:
                key = "TASI:" + item["symbol"]
                now = datetime.now().timestamp()

                if now - sent.get(key, 0) < 1800:
                    continue

                message = build_message(
                    "🇸🇦 السوق السعودي",
                    item["symbol"],
                    item["name"],
                    item["result"],
                    "SAR"
                )

                if await telegram_send(
                    session, TASI_TOKEN, TASI_CHAT_ID, message
                ):
                    sent[key] = now

            log.info(
                "TASI scanned %s | results %s",
                len(selected), len(results)
            )

            await asyncio.sleep(SCAN_SECONDS)

        except Exception:
            log.exception("TASI loop error")
            await asyncio.sleep(60)


# =========================================================
# MAIN — THREE INDEPENDENT WORKERS
# =========================================================

async def main():
    connector = aiohttp.TCPConnector(
        limit=20,
        ttl_dns_cache=300
    )

    timeout = aiohttp.ClientTimeout(total=40)

    async with aiohttp.ClientSession(
        connector=connector,
        timeout=timeout
    ) as session:

        await startup(session)

        tasks = [
            asyncio.create_task(us_loop(session)),
            asyncio.create_task(saudi_loop(session)),
            asyncio.create_task(crypto_loop(session))
        ]

        log.info("AI PRO MAX V8.0 — ALL WORKERS STARTED")

        await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.warning("Bot stopped manually")
