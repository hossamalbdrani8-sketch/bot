
import os
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import aiohttp

# =====================================================
# AI PRO MAX V10 — SMART MONEY
# US + TASI + CRYPTO | PUBLIC DATA
# TELEGRAM DIAGNOSTICS FIX
# =====================================================

BOT_NAME = "AI PRO MAX 💀🚀"
TZ = ZoneInfo("Asia/Riyadh")

US_TOKEN = os.getenv("US_TOKEN", "")
TASI_TOKEN = os.getenv("TASI_TOKEN", "")
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN", "")

MAIN_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")

US_CHAT = os.getenv("US_CHAT_ID", CHAT_ID)
TASI_CHAT = os.getenv("TASI_CHAT_ID", CHAT_ID)
CRYPTO_CHAT = os.getenv("CRYPTO_CHAT_ID", CHAT_ID)

SCAN_SECONDS = int(os.getenv("SCAN_SECONDS", "300"))
MAX_US = int(os.getenv("MAX_US", "150"))
MAX_CRYPTO = int(os.getenv("MAX_CRYPTO", "80"))
MAX_RESULTS = int(os.getenv("MAX_RESULTS", "10"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

log = logging.getLogger("AIPROMAX")

BASE_YAHOO = "https://query1.finance.yahoo.com"
BASE_BINANCE = "https://api.binance.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

last_signals = {}
semaphore = asyncio.Semaphore(12)


def now():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def fmt(value):
    return f"{value:,.4f}" if value < 10 else f"{value:,.2f}"


def ema(values, period):
    if not values:
        return 0

    k = 2 / (period + 1)
    result = values[0]

    for x in values[1:]:
        result = x * k + result * (1 - k)

    return result


def rsi(values, period=14):
    if len(values) < period + 1:
        return 50

    gains = []
    losses = []

    for i in range(-period, 0):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100

    return 100 - (100 / (1 + avg_gain / avg_loss))


def analyze(rows):
    if len(rows) < 25:
        return None

    closes = [float(x["close"]) for x in rows]
    highs = [float(x["high"]) for x in rows]
    lows = [float(x["low"]) for x in rows]
    volumes = [float(x["volume"]) for x in rows]

    price = closes[-1]
    volume = volumes[-1]

    avg_volume = sum(volumes[-21:-1]) / 20
    volume_ratio = volume / max(avg_volume, 1)

    e10 = ema(closes[-80:], 10)
    e14 = ema(closes[-80:], 14)
    e25 = ema(closes[-80:], 25)
    e50 = ema(closes[-100:], 50)

    vwap_num = sum(
        ((highs[i] + lows[i] + closes[i]) / 3) * volumes[i]
        for i in range(len(rows))
    )

    vwap_den = sum(volumes)
    vwap = vwap_num / max(vwap_den, 1)

    demand = min(lows[-30:])
    supply = max(highs[-30:])

    strength = 0

    if price > e10:
        strength += 10
    if price > e14:
        strength += 10
    if price > e25:
        strength += 10
    if price > e50:
        strength += 10
    if price > vwap:
        strength += 15
    if volume_ratio >= 1.5:
        strength += 20
    if volume_ratio >= 2:
        strength += 10
    if rsi(closes) >= 50:
        strength += 10
    if closes[-1] > closes[-2]:
        strength += 5

    strength = min(strength, 100)

    return {
        "price": price,
        "volume": volume,
        "volume_ratio": volume_ratio,
        "vwap": vwap,
        "ema10": e10,
        "ema14": e14,
        "ema25": e25,
        "ema50": e50,
        "rsi": rsi(closes),
        "demand": demand,
        "supply": supply,
        "score": strength,
        "change": (
            (closes[-1] - closes[-2]) /
            max(closes[-2], 0.000001) * 100
        )
    }


async def get_json(session, url, params=None):
    try:
        async with semaphore:
            async with session.get(
                url,
                params=params,
                headers=HEADERS,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:

                if response.status != 200:
                    log.warning(
                        "DATA HTTP ERROR | %s | %s",
                        response.status, url
                    )
                    return None

                return await response.json(content_type=None)

    except Exception as e:
        log.warning("DATA ERROR: %s", e)
        return None


# =====================================================
# TELEGRAM — FIXED WITH ERROR DIAGNOSTICS
# =====================================================

async def telegram(session, token, chat, message):

    if not token or not chat:
        log.error(
            "TELEGRAM CONFIG ERROR | token=%s | chat=%s",
            bool(token), bool(chat)
        )
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    try:
        async with session.post(
            url,
            json={
                "chat_id": chat,
                "text": message,
                "disable_web_page_preview": True
            },
            timeout=aiohttp.ClientTimeout(total=20)
        ) as response:

            body = await response.text()

            try:
                result = await response.json(content_type=None)
            except Exception:
                result = {}

            if response.status == 200 and result.get("ok"):
                log.info("TELEGRAM SEND SUCCESS")
                return True

            log.error(
                "TELEGRAM SEND FAILED | HTTP=%s | RESPONSE=%s",
                response.status,
                body[:1000]
            )

            return False

    except Exception:
        log.exception("TELEGRAM CONNECTION ERROR")
        return False


# =====================================================
# US STOCK UNIVERSE
# =====================================================

async def get_us_symbols(session):
    symbols = []

    for exchange in ("nasdaq", "nyse", "amex"):

        data = await get_json(
            session,
            "https://api.nasdaq.com/api/screener/stocks",
            {
                "tableonly": "true",
                "limit": "5000",
                "exchange": exchange
            }
        )

        if not data:
            continue

        try:
            rows = data["data"]["table"]["rows"]

            for row in rows:
                symbol = row.get("symbol", "").strip()

                if (
                    symbol
                    and symbol.isascii()
                    and symbol.replace(".", "").replace("-", "").isalnum()
                    and len(symbol) <= 6
                    and "^" not in symbol
                ):
                    symbols.append(symbol)

        except Exception:
            log.exception("US SYMBOL PARSE ERROR")

    result = list(dict.fromkeys(symbols))

    log.info("US SYMBOLS FOUND: %s", len(result))

    return result


async def yahoo_chart(session, symbol):
    url = f"{BASE_YAHOO}/v8/finance/chart/{symbol}"

    data = await get_json(
        session,
        url,
        {"range": "5d", "interval": "5m"}
    )

    try:
        result = data["chart"]["result"][0]
        quote = result["indicators"]["quote"][0]

        rows = []

        for i in range(len(result["timestamp"])):

            close = quote["close"][i]
            high = quote["high"][i]
            low = quote["low"][i]
            volume = quote["volume"][i]

            if None in (close, high, low, volume):
                continue

            rows.append({
                "close": close,
                "high": high,
                "low": low,
                "volume": volume
            })

        return rows

    except Exception:
        return None


# =====================================================
# SAUDI MARKET
# =====================================================

async def get_tasi_symbols(session):

    data = await get_json(
        session,
        f"{BASE_YAHOO}/v1/finance/screener/predefined/saved",
        {
            "scrIds": "most_actives",
            "count": "250",
            "region": "SA",
            "formatted": "false"
        }
    )

    try:
        quotes = data["finance"]["result"][0]["quotes"]

        symbols = list(dict.fromkeys(
            q["symbol"]
            for q in quotes
            if q.get("symbol", "").endswith(".SR")
        ))

        log.info("TASI SYMBOLS FOUND: %s", len(symbols))

        return symbols

    except Exception:
        log.exception("TASI SYMBOL ERROR")
        return []


# =====================================================
# CRYPTO MARKET
# =====================================================

async def get_crypto_symbols(session):

    data = await get_json(
        session,
        f"{BASE_BINANCE}/api/v3/ticker/24hr"
    )

    if not isinstance(data, list):
        return []

    coins = [
        x for x in data
        if x.get("symbol", "").endswith("USDT")
        and not any(
            tag in x["symbol"]
            for tag in (
                "UPUSDT",
                "DOWNUSDT",
                "BULLUSDT",
                "BEARUSDT"
            )
        )
    ]

    coins.sort(
        key=lambda x: float(x.get("quoteVolume", 0)),
        reverse=True
    )

    symbols = [x["symbol"] for x in coins[:MAX_CRYPTO]]

    log.info("CRYPTO SYMBOLS FOUND: %s", len(symbols))

    return symbols


async def crypto_chart(session, symbol):

    data = await get_json(
        session,
        f"{BASE_BINANCE}/api/v3/klines",
        {
            "symbol": symbol,
            "interval": "5m",
            "limit": "100"
        }
    )

    if not isinstance(data, list):
        return None

    return [
        {
            "close": float(x[4]),
            "high": float(x[2]),
            "low": float(x[3]),
            "volume": float(x[5])
        }
        for x in data
    ]


async def crypto_depth(session, symbol):

    data = await get_json(
        session,
        f"{BASE_BINANCE}/api/v3/depth",
        {
            "symbol": symbol,
            "limit": "20"
        }
    )

    if not data:
        return None

    bids = sum(
        float(x[0]) * float(x[1])
        for x in data["bids"]
    )

    asks = sum(
        float(x[0]) * float(x[1])
        for x in data["asks"]
    )

    return {
        "bids": bids,
        "asks": asks,
        "imbalance": bids / max(asks, 0.000001)
    }


# =====================================================
# SIGNAL ENGINE
# =====================================================

def make_signal(market, symbol, a, depth=None):

    score = a["score"]
    price = a["price"]

    if score < 55:
        return None

    if a["volume_ratio"] < 1.2:
        return None

    if depth and depth["imbalance"] > 1.3:
        score = min(score + 5, 100)

    if price > a["supply"]:
        state = "🚀 اختراق مقاومة"

    elif price >= a["demand"] * 1.01:
        state = "🟢 قريب من منطقة الطلب"

    else:
        state = "⏳ مراقبة"

    stop = a["demand"] * 0.985

    target1 = price + (price - stop) * 1.5
    target2 = price + (price - stop) * 2.5
    target3 = price + (price - stop) * 4

    return {
        "market": market,
        "symbol": symbol,
        "score": score,
        "state": state,
        "price": price,
        "demand": a["demand"],
        "supply": a["supply"],
        "vwap": a["vwap"],
        "volume": a["volume"],
        "ratio": a["volume_ratio"],
        "rsi": a["rsi"],
        "change": a["change"],
        "stop": stop,
        "tp1": target1,
        "tp2": target2,
        "tp3": target3,
        "depth": depth
    }


def render_signal(s):

    depth_text = ""

    if s["depth"]:
        d = s["depth"]

        depth_text = (
            f"\n🟢 طلبات دفتر الأوامر: ${d['bids']:,.0f}"
            f"\n🔴 عروض دفتر الأوامر: ${d['asks']:,.0f}"
            f"\n⚖️ نسبة الطلب/العرض: {d['imbalance']:.2f}"
        )

    return (
        f"💀 AI PRO MAX — SMART MONEY\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🏦 السوق: {s['market']}\n"
        f"📌 الرمز: {s['symbol']}\n"
        f"💵 السعر: {fmt(s['price'])}\n"
        f"📈 التغير: {s['change']:+.2f}%\n"
        f"⭐ قوة الإشارة: {s['score']}/100\n"
        f"📊 الحالة: {s['state']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 حجم التداول: {s['volume']:,.0f}\n"
        f"🔥 الفوليوم مقارنة بالمتوسط: {s['ratio']:.2f}x\n"
        f"📍 VWAP: {fmt(s['vwap'])}\n"
        f"📉 RSI: {s['rsi']:.1f}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🟢 الطلب: {fmt(s['demand'])}\n"
        f"🔴 العرض: {fmt(s['supply'])}\n"
        f"🛑 وقف الخسارة: {fmt(s['stop'])}\n"
        f"🎯 الهدف 1: {fmt(s['tp1'])}\n"
        f"🎯 الهدف 2: {fmt(s['tp2'])}\n"
        f"🎯 الهدف 3: {fmt(s['tp3'])}\n"
        f"{depth_text}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🕒 {now()}\n"
        f"⚠️ تحليل آلي وليس توصية شراء أو بيع"
    )


# =====================================================
# SCAN ONE SYMBOL
# =====================================================

async def scan_one(session, market, symbol):

    if market == "CRYPTO":
        rows = await crypto_chart(session, symbol)
        depth = await crypto_depth(session, symbol)

    else:
        rows = await yahoo_chart(session, symbol)
        depth = None

    if not rows:
        return None

    analysis = analyze(rows)

    if not analysis:
        return None

    return make_signal(market, symbol, analysis, depth)


# =====================================================
# SCAN MARKET
# =====================================================

async def scan_market(session, market, symbols, token, chat):

    results = []

    async def worker(symbol):
        try:
            result = await scan_one(session, market, symbol)

            if result:
                results.append(result)

        except Exception:
            log.exception(
                "%s SCAN ERROR: %s",
                market, symbol
            )

    await asyncio.gather(
        *(worker(s) for s in symbols)
    )

    results.sort(
        key=lambda x: (x["score"], x["ratio"]),
        reverse=True
    )

    sent = 0

    for item in results:

        key = f"{market}:{item['symbol']}"
        old = last_signals.get(key)

        if old is not None and old >= item["score"]:
            continue

        if item["score"] < 65:
            continue

        ok = await telegram(
            session,
            token,
            chat,
            render_signal(item)
        )

        if ok:
            last_signals[key] = item["score"]
            sent += 1

        if sent >= MAX_RESULTS:
            break

    log.info(
        "%s: scanned=%s results=%s sent=%s",
        market,
        len(symbols),
        len(results),
        sent
    )


# =====================================================
# MAIN ENGINE — 24/7
# =====================================================

async def run():

    connector = aiohttp.TCPConnector(
        limit=30,
        ttl_dns_cache=300
    )

    async with aiohttp.ClientSession(
        connector=connector,
        headers=HEADERS
    ) as session:

        log.info("AI PRO MAX STARTING")

        # Independent welcome messages
        welcome_bots = [
            ("US", US_TOKEN or MAIN_TOKEN, US_CHAT),
            ("TASI", TASI_TOKEN or MAIN_TOKEN, TASI_CHAT),
            ("CRYPTO", CRYPTO_TOKEN or MAIN_TOKEN, CRYPTO_CHAT)
        ]

        for market, token, chat in welcome_bots:

            message = (
                f"💀 {BOT_NAME}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"✅ تم تشغيل محرك {market}\n"
                f"📡 جاري تجهيز بيانات السوق\n"
                f"🕒 {now()}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🚀 AI PRO MAX SMART MONEY"
            )

            success = await telegram(
                session,
                token,
                chat,
                message
            )

            log.info(
                "%s WELCOME: %s",
                market,
                "SUCCESS" if success else "FAILED"
            )

        # Continuous scanning
        while True:

            try:

                log.info("STARTING MARKET SCAN")

                us_symbols, tasi_symbols, crypto_symbols = (
                    await asyncio.gather(
                        get_us_symbols(session),
                        get_tasi_symbols(session),
                        get_crypto_symbols(session)
                    )
                )

                us_symbols = us_symbols[:MAX_US]

                log.info(
                    "MARKET STATUS | US=%s | TASI=%s | CRYPTO=%s",
                    len(us_symbols),
                    len(tasi_symbols),
                    len(crypto_symbols)
                )

                await asyncio.gather(

                    scan_market(
                        session,
                        "US",
                        us_symbols,
                        US_TOKEN or MAIN_TOKEN,
                        US_CHAT
                    ),

                    scan_market(
                        session,
                        "TASI",
                        tasi_symbols,
                        TASI_TOKEN or MAIN_TOKEN,
                        TASI_CHAT
                    ),

                    scan_market(
                        session,
                        "CRYPTO",
                        crypto_symbols,
                        CRYPTO_TOKEN or MAIN_TOKEN,
                        CRYPTO_CHAT
                    )
                )

            except Exception:
                log.exception("MAIN SCANNER ERROR")

            log.info(
                "NEXT SCAN IN %s SECONDS",
                SCAN_SECONDS
            )

            await asyncio.sleep(SCAN_SECONDS)


if __name__ == "__main__":
    asyncio.run(run())
