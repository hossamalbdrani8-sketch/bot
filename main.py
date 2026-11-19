
import os
import json
import time
import math
import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

# =========================================================
# AI PRO MAX V11 — 24/7 FULL MARKET SCANNER
# US + TASI/NOMU + BINANCE SPOT
# =========================================================

APP = "AI PRO MAX 💀🚀"
SCAN_SECONDS = int(os.getenv("SCAN_SECONDS", "300"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "20"))
WORKERS = int(os.getenv("WORKERS", "4"))
DB_PATH = os.getenv("DB_PATH", "/data/ai_pro_max.db")

US_MIN_PRICE = 0.12
TIMEFRAMES = ["5m", "15m", "1h", "1d"]

US_TOKEN = os.getenv("US_TOKEN", "")
SIFTING_KEY = os.getenv("SIFTING_API_KEY", "")
SAHMK_KEY = os.getenv("SAHMK_API_KEY", "") or os.getenv("TASI_TOKEN", "")
TWELVE_KEY = os.getenv("TWELVEDATA_API_KEY", "")

US_BOT = os.getenv("US_TOKEN", "")
TASI_BOT = os.getenv("TASI_TOKEN", "")
CRYPTO_BOT = os.getenv("CRYPTO_TOKEN", "")

GENERAL_CHAT = os.getenv("CHAT_ID", "")
US_CHAT = os.getenv("US_CHAT_ID", "") or GENERAL_CHAT
TASI_CHAT = os.getenv("TASI_CHAT_ID", "") or GENERAL_CHAT
CRYPTO_CHAT = os.getenv("CRYPTO_CHAT_ID", "") or GENERAL_CHAT

TELEGRAM_API = "https://api.telegram.org"
SAHMK_API = "https://api.sahmk.sa/api/v1"
SIFTING_API = "https://api.sifting.io"
TWELVE_API = "https://api.twelvedata.com"
BINANCE_API = "https://api.binance.com"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("AIPROMAX")

# ---------------------------------------------------------
# DATABASE — persistent signals and target confirmations
# ---------------------------------------------------------

def db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS states (
            market TEXT,
            symbol TEXT,
            timeframe TEXT,
            data TEXT,
            updated REAL,
            PRIMARY KEY (market, symbol, timeframe)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS targets (
            market TEXT,
            symbol TEXT,
            timeframe TEXT,
            target_no INTEGER,
            target_price REAL,
            hit INTEGER DEFAULT 0,
            created REAL,
            PRIMARY KEY (market, symbol, timeframe, target_no)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS cursors (
            market TEXT PRIMARY KEY,
            position INTEGER DEFAULT 0
        )
    """)
    con.commit()
    return con


def get_state(market, symbol, tf):
    con = db()
    row = con.execute(
        "SELECT data FROM states WHERE market=? AND symbol=? AND timeframe=?",
        (market, symbol, tf)
    ).fetchone()
    con.close()
    if not row:
        return {}
    try:
        return json.loads(row[0])
    except Exception:
        return {}


def save_state(market, symbol, tf, data):
    con = db()
    con.execute("""
        INSERT INTO states VALUES(?,?,?,?,?)
        ON CONFLICT(market,symbol,timeframe)
        DO UPDATE SET data=excluded.data, updated=excluded.updated
    """, (market, symbol, tf, json.dumps(data), time.time()))
    con.commit()
    con.close()


def get_cursor(market):
    con = db()
    row = con.execute(
        "SELECT position FROM cursors WHERE market=?", (market,)
    ).fetchone()
    con.close()
    return row[0] if row else 0


def set_cursor(market, position):
    con = db()
    con.execute("""
        INSERT INTO cursors VALUES(?,?)
        ON CONFLICT(market) DO UPDATE SET position=excluded.position
    """, (market, position))
    con.commit()
    con.close()


# ---------------------------------------------------------
# HTTP
# ---------------------------------------------------------

async def get_json(session, url, headers=None, params=None, retries=3):
    for attempt in range(retries):
        try:
            async with session.get(
                url, headers=headers, params=params,
                timeout=aiohttp.ClientTimeout(total=25)
            ) as response:
                body = await response.text()

                if response.status == 429:
                    await asyncio.sleep(3 * (attempt + 1))
                    continue

                if response.status >= 500:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue

                if response.status >= 400:
                    log.warning("HTTP %s | %s | %s",
                                response.status, url, body[:250])
                    return None

                try:
                    return json.loads(body)
                except Exception:
                    log.warning("Invalid JSON from %s", url)
                    return None

        except Exception as exc:
            log.warning("HTTP error: %s", exc)
            await asyncio.sleep(2 * (attempt + 1))

    return None


async def telegram(session, token, chat, message):
    if not token or not chat:
        log.error("Telegram credentials missing: token/chat")
        return False

    url = f"{TELEGRAM_API}/bot{token}/sendMessage"

    # Telegram message maximum is 4096 characters.
    chunks = []
    while message:
        chunks.append(message[:3900])
        message = message[3900:]

    ok = True
    for chunk in chunks:
        try:
            async with session.post(
                url,
                json={
                    "chat_id": chat,
                    "text": chunk,
                    "disable_web_page_preview": True
                },
                timeout=aiohttp.ClientTimeout(total=20)
            ) as response:
                result = await response.json(content_type=None)
                if response.status != 200 or not result.get("ok"):
                    log.error("Telegram failed: %s", result)
                    ok = False
                else:
                    log.info("Telegram SEND SUCCESS")
        except Exception as exc:
            log.exception("Telegram exception: %s", exc)
            ok = False

    return ok


async def send_market(session, market, message):
    if market == "US":
        return await telegram(session, US_BOT, US_CHAT, message)
    if market == "TASI":
        return await telegram(session, TASI_BOT, TASI_CHAT, message)
    return await telegram(session, CRYPTO_BOT, CRYPTO_CHAT, message)


# ---------------------------------------------------------
# SYMBOL UNIVERSES
# ---------------------------------------------------------

async def get_us_symbols(session):
    """
    Twelve Data symbol directory.
    Only US exchanges; OTC and other venues excluded.
    """
    if not TWELVE_KEY:
        log.error("TWELVEDATA_API_KEY is missing")
        return []

    data = await get_json(
        session,
        f"{TWELVE_API}/stocks",
        params={"apikey": TWELVE_KEY, "format": "JSON"}
    )

    if not data:
        return []

    rows = data if isinstance(data, list) else data.get("data", [])
    allowed = {"NASDAQ", "NYSE", "NYSE AMERICAN", "NYSE ARCA"}

    symbols = []
    seen = set()

    for item in rows:
        symbol = str(item.get("symbol", "")).strip().upper()
        exchange = str(item.get("exchange", "")).strip().upper()
        country = str(item.get("country", "")).strip().lower()
        currency = str(item.get("currency", "")).strip().upper()

        if not symbol or symbol in seen:
            continue
        if country not in ("united states", "usa", "us"):
            continue
        if currency != "USD":
            continue
        if exchange not in allowed:
            continue

        seen.add(symbol)
        symbols.append({
            "symbol": symbol,
            "name": item.get("name", symbol),
            "exchange": exchange
        })

    log.info("US universe loaded: %s symbols", len(symbols))
    return symbols


async def get_sa_symbols(session):
    """
    Complete Saudi listed company directory:
    TASI + NOMU, equities only.
    """
    if not SAHMK_KEY:
        log.error("SAHMK_API_KEY / TASI_TOKEN missing")
        return []

    headers = {"X-API-Key": SAHMK_KEY}
    symbols = []
    seen = set()

    for market in ("TASI", "NOMU"):
        offset = 0
        while True:
            data = await get_json(
                session,
                f"{SAHMK_API}/companies/",
                headers=headers,
                params={
                    "market": market,
                    "limit": 500,
                    "offset": offset
                }
            )

            if not data:
                break

            rows = data.get("results", [])
            if not rows:
                break

            for item in rows:
                symbol = str(item.get("symbol", "")).strip()
                status = str(item.get("status", "")).lower()
                security_type = str(
                    item.get("security_type", "")
                ).lower()

                if not symbol or symbol in seen:
                    continue
                if status and status != "active":
                    continue
                if security_type != "equity":
                    continue

                seen.add(symbol)
                symbols.append({
                    "symbol": symbol,
                    "name": item.get("name_ar") or item.get("name_en") or symbol,
                    "market": market
                })

            offset += len(rows)
            total = int(data.get("total", 0) or 0)
            if len(rows) < 500 or (total and offset >= total):
                break

    log.info("Saudi universe loaded: %s symbols", len(symbols))
    return symbols


async def get_crypto_symbols(session):
    """
    All Binance SPOT trading pairs quoted in USDT or USD.
    """
    data = await get_json(
        session, f"{BINANCE_API}/api/v3/exchangeInfo"
    )
    if not data:
        return []

    symbols = []
    for item in data.get("symbols", []):
        if item.get("status") != "TRADING":
            continue
        if item.get("quoteAsset") not in ("USDT", "USD"):
            continue

        permissions = item.get("permissions", [])
        if permissions and "SPOT" not in permissions:
            continue

        symbols.append({
            "symbol": item.get("symbol"),
            "base": item.get("baseAsset"),
            "quote": item.get("quoteAsset")
        })

    log.info("Crypto SPOT universe loaded: %s pairs", len(symbols))
    return symbols


# ---------------------------------------------------------
# MARKET DATA
# ---------------------------------------------------------

async def us_bars(session, symbol, interval):
    if not SIFTING_KEY:
        return []

    end = datetime.now(timezone.utc)
    days = 5 if interval in ("5m", "15m") else 40

    params = {
        "start": (end - timedelta(days=days)).strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
        "interval": interval,
        "limit": 500
    }
    headers = {
        "X-API-Key": SIFTING_KEY,
        "Accept-Encoding": "gzip"
    }

    data = await get_json(
        session,
        f"{SIFTING_API}/v1/hist/stocks/{symbol}/bars",
        headers=headers,
        params=params
    )

    if not data:
        return []

    bars = data.get("data", [])
    return [{
        "open": float(x["o"]),
        "high": float(x["h"]),
        "low": float(x["l"]),
        "close": float(x["c"]),
        "volume": float(x["v"]),
        "time": x.get("t")
    } for x in bars if all(k in x for k in ("o", "h", "l", "c", "v"))]


async def sa_bars(session, symbol, interval):
    if not SAHMK_KEY:
        return []

    headers = {"X-API-Key": SAHMK_KEY}
    interval_map = {
        "5m": "5min",
        "15m": "15min",
        "1h": "60min",
        "1d": "1d"
    }

    # Saudi API plan determines which intervals are available.
    api_interval = interval_map[interval]
    days = 30 if interval != "1d" else 180

    params = {
        "interval": api_interval,
        "from": (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d"),
        "to": datetime.now().strftime("%Y-%m-%d"),
        "limit": 500
    }

    data = await get_json(
        session,
        f"{SAHMK_API}/historical/{symbol}/",
        headers=headers,
        params=params
    )

    if not data:
        return []

    rows = data.get("data", [])
    return [{
        "open": float(x["open"]),
        "high": float(x["high"]),
        "low": float(x["low"]),
        "close": float(x["close"]),
        "volume": float(x["volume"]),
        "time": x.get("date")
    } for x in rows if all(k in x for k in
                           ("open", "high", "low", "close", "volume"))]


async def crypto_bars(session, symbol, interval):
    data = await get_json(
        session,
        f"{BINANCE_API}/api/v3/klines",
        params={
            "symbol": symbol,
            "interval": interval,
            "limit": 200
        }
    )

    if not data or not isinstance(data, list):
        return []

    return [{
        "open": float(x[1]),
        "high": float(x[2]),
        "low": float(x[3]),
        "close": float(x[4]),
        "volume": float(x[5]),
        "time": x[0]
    } for x in data]


# ---------------------------------------------------------
# TECHNICAL ANALYSIS
# ---------------------------------------------------------

def ema(values, period):
    if len(values) < period:
        return None
    alpha = 2 / (period + 1)
    result = sum(values[:period]) / period
    for value in values[period:]:
        result = alpha * value + (1 - alpha) * result
    return result


def rsi(values, period=14):
    if len(values) < period + 1:
        return None

    gains, losses = [], []
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(bars, period=14):
    if len(bars) < period + 1:
        return None

    trs = []
    for i in range(1, len(bars)):
        current = bars[i]
        previous = bars[i - 1]
        tr = max(
            current["high"] - current["low"],
            abs(current["high"] - previous["close"]),
            abs(current["low"] - previous["close"])
        )
        trs.append(tr)

    return sum(trs[-period:]) / min(period, len(trs))


def vwap(bars):
    recent = bars[-30:]
    total_volume = sum(x["volume"] for x in recent)
    if total_volume <= 0:
        return None

    total = sum(
        ((x["high"] + x["low"] + x["close"]) / 3) * x["volume"]
        for x in recent
    )
    return total / total_volume


def analyze(bars):
    if len(bars) < 30:
        return None

    closes = [x["close"] for x in bars]
    volumes = [x["volume"] for x in bars]

    price = closes[-1]
    previous = closes[-2]
    current_rsi = rsi(closes)
    current_atr = atr(bars)
    current_vwap = vwap(bars)

    emas = {
        p: ema(closes, p) for p in (10, 14, 25, 50)
    }

    avg_volume = sum(volumes[-21:-1]) / 20
    volume_ratio = volumes[-1] / avg_volume if avg_volume > 0 else 0

    support = min(x["low"] for x in bars[-30:])
    resistance = max(x["high"] for x in bars[-30:])

    # Approximate accumulation: tight range + above-average volume.
    recent_range = max(x["high"] for x in bars[-8:]) - min(
        x["low"] for x in bars[-8:]
    )
    accumulation = (
        current_atr is not None
        and recent_range <= current_atr * 2.5
        and volume_ratio >= 1.15
    )

    # Buyer pressure proxy, not exchange order-flow.
    candle_range = max(bars[-1]["high"] - bars[-1]["low"], 1e-9)
    buyer_proxy = (
        (bars[-1]["close"] - bars[-1]["low"]) / candle_range
    ) * 100

    return {
        "price": price,
        "previous": previous,
        "change": ((price / previous) - 1) * 100 if previous else 0,
        "rsi": current_rsi,
        "atr": current_atr,
        "vwap": current_vwap,
        "ema": emas,
        "volume": volumes[-1],
        "volume_ratio": volume_ratio,
        "support": support,
        "resistance": resistance,
        "accumulation": accumulation,
        "buyer_proxy": buyer_proxy
    }


# ---------------------------------------------------------
# TARGETS 1–20 + PERSISTENT HIT CHECKS
# ---------------------------------------------------------

def create_targets(market, symbol, tf, price, current_atr):
    if not current_atr or current_atr <= 0:
        return

    con = db()
    existing = con.execute("""
        SELECT COUNT(*) FROM targets
        WHERE market=? AND symbol=? AND timeframe=?
    """, (market, symbol, tf)).fetchone()[0]

    if existing:
        con.close()
        return

    for number in range(1, 21):
        # ATR-based projections; not guaranteed price predictions.
        target_price = price + (current_atr * 0.5 * number)
        con.execute("""
            INSERT OR IGNORE INTO targets
            VALUES(?,?,?,?,?,?,?)
        """, (
            market, symbol, tf, number,
            target_price, 0, time.time()
        ))

    con.commit()
    con.close()


def update_targets(market, symbol, tf, high):
    con = db()
    rows = con.execute("""
        SELECT target_no, target_price FROM targets
        WHERE market=? AND symbol=? AND timeframe=? AND hit=0
        ORDER BY target_no
    """, (market, symbol, tf)).fetchall()

    hits = []
    for number, target_price in rows:
        if high >= target_price:
            con.execute("""
                UPDATE targets SET hit=1
                WHERE market=? AND symbol=? AND timeframe=? AND target_no=?
            """, (market, symbol, tf, number))
            hits.append((number, target_price))

    con.commit()
    con.close()
    return hits


def target_text(market, symbol, tf):
    con = db()
    rows = con.execute("""
        SELECT target_no, target_price, hit FROM targets
        WHERE market=? AND symbol=? AND timeframe=?
        ORDER BY target_no
    """, (market, symbol, tf)).fetchall()
    con.close()

    if not rows:
        return "الأهداف: تنتظر اكتمال بيانات ATR"

    return "🎯 الأهداف:\n" + "\n".join(
        f"{'✅' if hit else '⬜'} هدف {n}: {price:.6f}"
        for n, price, hit in rows
    )


# ---------------------------------------------------------
# SIGNAL ENGINE
# ---------------------------------------------------------

def signal_events(market, symbol, tf, result, bars):
    if not result:
        return []

    old = get_state(market, symbol, tf)
    price = result["price"]
    current_rsi = result["rsi"]
    events = []

    if not old:
        old = {
            "price": price,
            "rsi": current_rsi,
            "ema": {},
            "volume_ratio": 0,
            "accumulation": False
        }

    old_ema = old.get("ema", {})

    # EMA crossing alerts.
    for period, value in result["ema"].items():
        if value is None:
            continue
        was_above = old_ema.get(str(period))
        is_above = price >= value

        if was_above is not None and was_above != is_above:
            if is_above:
                events.append(f"🟢 اختراق EMA{period} للأعلى: {value:.6f}")
            else:
                events.append(f"🔴 كسر EMA{period} للأسفل: {value:.6f}")

    # RSI zones.
    if current_rsi is not None:
        old_rsi = old.get("rsi")
        if old_rsi is not None:
            zones = (20, 40, 50, 60, 70, 80, 100)
            for zone in zones:
                if old_rsi < zone <= current_rsi:
                    events.append(f"🟢 RSI صاعد واخترق منطقة {zone}")
                elif old_rsi > zone >= current_rsi:
                    events.append(f"🔴 RSI هابط وكسر منطقة {zone}")

            if old_rsi >= 95 and current_rsi < old_rsi:
                events.append("🔴 RSI بدأ يتراجع من منطقة التشبع الشرائي")

    # Volume increase.
    if result["volume_ratio"] >= 1.5 and old.get("volume_ratio", 0) < 1.5:
        events.append(
            f"💹 ارتفاع نشاط الفوليوم: {result['volume_ratio']:.2f}x"
        )

    # Accumulation / breakout.
    if result["accumulation"] and not old.get("accumulation", False):
        events.append(
            f"🟡 احتمال تجميع سعري حول {price:.6f} — ليس تأكيدًا مؤسسيًا"
        )

    if price > result["resistance"]:
        events.append("🚀 اختراق قمة النطاق السعري")

    if result["vwap"] and old.get("price", price) < result["vwap"] <= price:
        events.append("🟢 السعر اخترق VWAP للأعلى")
    elif result["vwap"] and old.get("price", price) > result["vwap"] >= price:
        events.append("🔴 السعر كسر VWAP للأسفل")

    # Store state.
    save_state(market, symbol, tf, {
        "price": price,
        "rsi": current_rsi,
        "ema": {
            str(k): (price >= v if v is not None else None)
            for k, v in result["ema"].items()
        },
        "volume_ratio": result["volume_ratio"],
        "accumulation": result["accumulation"]
    })

    return events


def format_report(market, item, tf, result, events, target_hits):
    symbol = item["symbol"]
    name = item.get("name", symbol)
    price = result["price"]
    rsi_value = result["rsi"]
    vwap_value = result["vwap"]

    currency = "$" if market in ("US", "CRYPTO") else "⃁"

    if result["change"] > 0:
        direction = "🟢 صاعد"
    elif result["change"] < 0:
        direction = "🔴 هابط"
    else:
        direction = "🟡 مستقر"

    if price < result["support"]:
        warning = f"🔴 السلبية بالإغلاق تحت: {result['support']:.6f}"
    elif price < result["resistance"]:
        warning = "🟡 داخل النطاق السعري"
    else:
        warning = "🟢 فوق مقاومة النطاق"

    lines = [
        f"💀🚀 {APP}",
        f"📊 السوق: {market}",
        f"🏷️ {name} ({symbol})",
        f"⏱️ الفاصل: {tf}",
        f"💰 السعر: {currency}{price:.6f}",
        f"📈 التغير: {result['change']:+.2f}%",
        f"📊 الحالة: {direction}",
        f"📦 الفوليوم: {result['volume']:,.0f}",
        f"💹 نشاط الفوليوم: {result['volume_ratio']:.2f}x",
        f"📍 VWAP: {vwap_value:.6f}" if vwap_value else "📍 VWAP: غير متاح",
        f"🧭 RSI: {rsi_value:.2f}" if rsi_value is not None else "🧭 RSI: غير متاح",
        f"🟢 قوة المشترين التقديرية: {result['buyer_proxy']:.1f}%",
        "⚠️ قوة المشترين هنا تقدير من الشمعة وليست قراءة دفتر أوامر",
        f"🟩 الدعم: {result['support']:.6f}",
        f"🟥 المقاومة: {result['resistance']:.6f}",
        warning,
        f"🟡 التجميع المحتمل: {'موجود' if result['accumulation'] else 'غير ظاهر'}",
        "",
        "📐 المتوسطات:"
    ]

    for period, value in result["ema"].items():
        if value is not None:
            state = "فوقه 🟢" if price >= value else "تحته 🔴"
            lines.append(f"EMA{period}: {value:.6f} — السعر {state}")

    if events:
        lines += ["", "🚨 التنبيهات الجديدة:"]
        lines.extend(events)

    if target_hits:
        lines += ["", "🎯 تم تحقيق أهداف جديدة:"]
        lines.extend(
            f"✅ الهدف {n} تحقق عند {p:.6f}"
            for n, p in target_hits
        )

    lines += ["", target_text(market, symbol, tf)]
    lines += [
        "",
        "ℹ️ الأهداف مستويات حسابية مبنية على ATR وليست ضمانًا للوصول.",
        "ℹ️ البيانات الفنية لا تمثل توصية شراء أو بيع."
    ]

    return "\n".join(lines)


# ---------------------------------------------------------
# SYMBOL SCANNING
# ---------------------------------------------------------

async def scan_one(session, market, item):
    symbol = item["symbol"]
    messages = []

    for tf in TIMEFRAMES:
        try:
            if market == "US":
                bars = await us_bars(session, symbol, tf)
            elif market == "TASI":
                bars = await sa_bars(session, symbol, tf)
            else:
                bars = await crypto_bars(session, symbol, tf)

            if len(bars) < 30:
                continue

            result = analyze(bars)
            if not result:
                continue

            # US minimum price filter.
            if market == "US" and result["price"] < US_MIN_PRICE:
                continue

            create_targets(
                market, symbol, tf,
                result["price"], result["atr"]
            )

            hits = update_targets(
                market, symbol, tf, bars[-1]["high"]
            )

            events = signal_events(
                market, symbol, tf, result, bars
            )

            # First valid report, new event, or target hit.
            old = get_state(market, symbol, tf)
            if events or hits:
                messages.append(
                    format_report(market, item, tf, result, events, hits)
                )

        except Exception as exc:
            log.exception("Scan error %s %s %s: %s",
                          market, symbol, tf, exc)

    return messages


async def process_market(session, market, symbols):
    if not symbols:
        log.warning("%s universe empty", market)
        return

    start = get_cursor(market)
    end = min(start + BATCH_SIZE, len(symbols))
    batch = symbols[start:end]

    if not batch:
        start = 0
        end = min(BATCH_SIZE, len(symbols))
        batch = symbols[start:end]

    semaphore = asyncio.Semaphore(WORKERS)

    async def limited(item):
        async with semaphore:
            return await scan_one(session, market, item)

    results = await asyncio.gather(
        *(limited(item) for item in batch),
        return_exceptions=True
    )

    reports = []
    for result in results:
        if isinstance(result, list):
            reports.extend(result)
        elif isinstance(result, Exception):
            log.error("%s batch error: %s", market, result)

    set_cursor(market, 0 if end >= len(symbols) else end)

    # Batch messages to avoid Telegram flood.
    if reports:
        await send_market(
            session, market,
            f"💀🚀 AI PRO MAX — {market}\n"
            f"📡 نتائج الدفعة: {len(reports)}\n\n" +
            "\n\n━━━━━━━━━━━━━━━━\n\n".join(reports)
        )

    log.info(
        "%s scanned %s/%s | reports=%s",
        market, end, len(symbols), len(reports)
    )


# ---------------------------------------------------------
# MAIN LOOP — 24/7
# ---------------------------------------------------------

async def main():
    connector = aiohttp.TCPConnector(
        limit=WORKERS + 5,
        ttl_dns_cache=300
    )

    async with aiohttp.ClientSession(connector=connector) as session:

        # Welcome / health message.
        for market in ("US", "TASI", "CRYPTO"):
            await send_market(
                session,
                market,
                f"💀🚀 {APP}\n"
                f"✅ تم تشغيل بوت {market}\n"
                f"🟢 نظام الفحص المستمر يعمل\n"
                f"⏱️ دورة الفحص: {SCAN_SECONDS} ثانية\n"
                f"📡 الفحص على دفعات مع حفظ موضع التقدم\n"
                f"🗃️ حفظ الأهداف والتنبيهات في قاعدة البيانات"
            )

        universes = {
            "US": [],
            "TASI": [],
            "CRYPTO": []
        }

        last_refresh = 0

        while True:
            try:
                # Refresh symbol directories every 6 hours.
                if time.time() - last_refresh >= 21600:
                    log.info("Refreshing all symbol universes")

                    us, sa, crypto = await asyncio.gather(
                        get_us_symbols(session),
                        get_sa_symbols(session),
                        get_crypto_symbols(session)
                    )

                    if us:
                        universes["US"] = us
                    if sa:
                        universes["TASI"] = sa
                    if crypto:
                        universes["CRYPTO"] = crypto

                    last_refresh = time.time()

                    for market, symbols in universes.items():
                        await send_market(
                            session,
                            market,
                            f"📡 تحديث قائمة {market}\n"
                            f"عدد الرموز المتاحة: {len(symbols):,}\n"
                            f"🟢 نظام الفحص مستمر"
                        )

                # Each market is independent.
                await process_market(
                    session, "US", universes["US"]
                )
                await process_market(
                    session, "TASI", universes["TASI"]
                )
                await process_market(
                    session, "CRYPTO", universes["CRYPTO"]
                )

                log.info("NEXT SCAN IN %s SECONDS", SCAN_SECONDS)
                await asyncio.sleep(SCAN_SECONDS)

            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("MAIN LOOP ERROR")
                await asyncio.sleep(15)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Bot stopped manually")
