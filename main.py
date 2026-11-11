# ============================================================
# 💀🚀 AI PRO MAX — MARKET HUNTER V5
# 🇺🇸 US STOCKS | 🪙 ALL CRYPTO | 🇸🇦 TASI
# ONE IMAGE DASHBOARD — TELEGRAM
# ============================================================

import os
import io
import re
import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from html import escape

import aiohttp
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

# ======================== SETTINGS ==========================

TWELVE_API_KEY = (
    os.getenv("TWELVE_DATA_API_KEY")
    or os.getenv("TWELVEDATA_API_KEY")
)

SAHMK_API_KEY = os.getenv("SAHMK_API_KEY")
SAHMK_BASE = os.getenv(
    "SAHMK_BASE", "https://api.sahmk.sa/api/v1"
).rstrip("/")

CHAT_ID = os.getenv("CHAT_ID")
US_TOKEN = os.getenv("US_TOKEN")
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN")
TASI_TOKEN = os.getenv("TASI_TOKEN") or US_TOKEN

TD_BASE = "https://api.twelvedata.com"

SCAN_SECONDS = int(os.getenv("SCAN_SECONDS", "300"))
TASI_SCAN_SECONDS = int(os.getenv("TASI_SCAN_SECONDS", "1800"))

MIN_SCORE = int(os.getenv("MIN_SCORE", "65"))
MIN_US_PRICE = 0.15
MIN_VOLUME_RATIO = float(os.getenv("MIN_VOLUME_RATIO", "1.5"))

TD_INTERVAL = os.getenv("TD_INTERVAL", "5min")
TD_CANDLES = int(os.getenv("TD_CANDLES", "100"))

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "80"))
WORKERS = int(os.getenv("WORKERS", "4"))
SIGNAL_COOLDOWN = int(os.getenv("SIGNAL_COOLDOWN", "1800"))

# قوائم إضافية اختيارية، تدمج مع القوائم المكتشفة
US_EXTRA = os.getenv("US_SYMBOLS", "")
CRYPTO_EXTRA = os.getenv("CRYPTO_SYMBOLS", "")
TASI_EXTRA = os.getenv("TASI_SYMBOLS", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("AI_PRO_MAX_V5")

sent_signals = {}
universe = {"US": [], "CRYPTO": [], "TASI": []}
offsets = {"US": 0, "CRYPTO": 0, "TASI": 0}


# ======================== HELPERS ===========================

def unique(items):
    return list(dict.fromkeys(
        str(x).strip().upper()
        for x in items
        if x and str(x).strip()
    ))


def extra_symbols(value):
    return unique(value.split(","))


def number(value, default=0.0):
    try:
        result = float(value)
        return result if result == result else default
    except (TypeError, ValueError):
        return default


def fmt(value, digits=4):
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def arabic(value):
    try:
        return get_display(arabic_reshaper.reshape(str(value)))
    except Exception:
        return str(value)


def font(size, bold=False):
    root = os.path.dirname(os.path.abspath(__file__))
    names = [
        os.path.join(
            root, "fonts",
            "NotoKufiArabic-Bold.ttf" if bold
            else "NotoKufiArabic-Regular.ttf"
        ),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    ]

    for path in names:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass

    return ImageFont.load_default()


def normalize(rows):
    result = []

    if not isinstance(rows, list):
        return result

    for row in rows:
        if not isinstance(row, dict):
            continue

        r = {str(k).lower(): v for k, v in row.items()}

        item = {
            "open": number(r.get("open", r.get("o"))),
            "high": number(r.get("high", r.get("h"))),
            "low": number(r.get("low", r.get("l"))),
            "close": number(
                r.get("close", r.get("c", r.get("price")))
            ),
            "volume": number(
                r.get("volume", r.get("vol", r.get("v")))
            )
        }

        if item["close"] <= 0:
            continue

        item["high"] = max(
            item["high"], item["open"], item["close"]
        )
        item["low"] = min(
            x for x in (
                item["low"], item["open"], item["close"]
            ) if x > 0
        )

        result.append(item)

    return result


def ema(values, period):
    if len(values) < period:
        return None

    result = sum(values[:period]) / period
    alpha = 2 / (period + 1)

    for value in values[period:]:
        result = value * alpha + result * (1 - alpha)

    return result


def rsi(values, period=14):
    if len(values) <= period:
        return 50.0

    changes = [
        values[i] - values[i - 1]
        for i in range(1, len(values))
    ]

    gains = [max(x, 0) for x in changes]
    losses = [max(-x, 0) for x in changes]

    gain = sum(gains[-period:]) / period
    loss = sum(losses[-period:]) / period

    if loss == 0:
        return 100.0

    return 100 - (100 / (1 + gain / loss))


def atr(rows, period=14):
    if len(rows) < period + 1:
        return None

    values = []

    for i in range(1, len(rows)):
        h = rows[i]["high"]
        l = rows[i]["low"]
        p = rows[i - 1]["close"]

        values.append(max(h - l, abs(h - p), abs(l - p)))

    return sum(values[-period:]) / period


def vwap(rows):
    total = 0
    volume = 0

    for x in rows:
        if x["volume"] <= 0:
            continue

        typical = (x["high"] + x["low"] + x["close"]) / 3
        total += typical * x["volume"]
        volume += x["volume"]

    return total / volume if volume else None


def volume_ratio(rows):
    if len(rows) < 21:
        return 0

    old = [x["volume"] for x in rows[-21:-1]]
    average = sum(old) / len(old)

    return rows[-1]["volume"] / average if average else 0


def levels(rows):
    if len(rows) < 25:
        return {"supports": [], "resistances": []}

    price = rows[-1]["close"]
    highs = [x["high"] for x in rows]
    lows = [x["low"] for x in rows]

    supports = []
    resistances = []

    for i in range(max(2, len(rows) - 80), len(rows) - 2):
        if (
            highs[i] >= highs[i-1]
            and highs[i] >= highs[i-2]
            and highs[i] > highs[i+1]
            and highs[i] > highs[i+2]
            and highs[i] > price
        ):
            resistances.append(highs[i])

        if (
            lows[i] <= lows[i-1]
            and lows[i] <= lows[i-2]
            and lows[i] < lows[i+1]
            and lows[i] < lows[i+2]
            and lows[i] < price
        ):
            supports.append(lows[i])

    if not supports:
        supports = [x for x in lows[-20:] if x < price]

    if not resistances:
        resistances = [x for x in highs[-20:] if x > price]

    return {
        "supports": sorted(set(supports), reverse=True)[:3],
        "resistances": sorted(set(resistances))[:3]
    }


def targets(price, volatility, support):
    stop = price - 1.5 * volatility

    if support:
        stop = min(stop, support[0] - 0.15 * volatility)

    return {
        "stop": stop,
        "targets": [
            price + volatility * i for i in range(1, 9)
        ]
    }


# ===================== IMAGE DASHBOARD =====================

def build_dashboard(
    market, symbol, price, score, strength,
    rsi_value, vol, vwap_value, atr_value,
    market_levels, target_data, currency
):
    W, H = 1100, 1450

    img = Image.new("RGB", (W, H), (7, 12, 19))
    d = ImageDraw.Draw(img)

    BG = (7, 12, 19)
    PANEL = (15, 25, 35)
    PANEL2 = (18, 32, 43)
    GREEN = (0, 230, 145)
    RED = (255, 75, 90)
    GOLD = (255, 194, 65)
    WHITE = (239, 245, 249)
    MUTED = (140, 163, 178)
    CYAN = (65, 205, 255)

    title = font(43, True)
    heading = font(29, True)
    body = font(24)
    small = font(19)
    large = font(57, True)

    def panel(box, color=PANEL, outline=(38, 64, 78)):
        d.rounded_rectangle(
            box, radius=22, fill=color,
            outline=outline, width=2
        )

    def right(x, y, value, f=body, color=WHITE):
        d.text(
            (x, y), arabic(value),
            font=f, fill=color, anchor="ra"
        )

    def left(x, y, value, f=body, color=WHITE):
        d.text((x, y), str(value), font=f, fill=color)

    # الإطار الرئيسي
    d.rounded_rectangle(
        (15, 15, W-15, H-15),
        radius=30, fill=BG, outline=GREEN, width=3
    )

    # الرأس
    panel((32, 32, W-32, 145), PANEL2, GREEN)
    left(60, 53, "AI PRO MAX", title, GREEN)
    right(W-60, 65, "صائد الفرص — MARKET HUNTER V5", heading)
    left(60, 108, "LIVE MARKET INTELLIGENCE", small, MUTED)

    # السعر والإشارة
    panel((32, 165, W-32, 390), PANEL2, GREEN)

    right(W-65, 185, f"{market} | {symbol}", heading, CYAN)

    left(
        65, 235,
        f"{price:,.4f}" if price < 1 else f"{price:,.2f}",
        large, GREEN
    )

    left(70, 315, currency, body, MUTED)
    right(W-65, 260, "قوة الإشارة", heading, GOLD)
    right(W-65, 310, f"{score}/100", title, GREEN)

    # شريط القوة
    x1, x2 = 610, W-65
    y1, y2 = 355, 375

    d.rounded_rectangle(
        (x1, y1, x2, y2), radius=10, fill=(45, 58, 67)
    )

    d.rounded_rectangle(
        (x1, y1, x1 + (x2-x1)*score/100, y2),
        radius=10, fill=GREEN
    )

    # المؤشرات
    panel((32, 410, W-32, 620))
    right(W-65, 430, "مؤشرات التداول والسيولة", heading, GOLD)

    metrics = [
        ("RSI", f"{rsi_value:.1f}", CYAN),
        ("VOLUME", f"×{vol:.2f}", GREEN),
        ("VWAP", fmt(vwap_value), WHITE),
        ("ATR", fmt(atr_value), GOLD)
    ]

    cell = (W-150)//4

    for i, (name, value, color) in enumerate(metrics):
        x = 65 + i*cell

        d.rounded_rectangle(
            (x, 490, x+cell-15, 585),
            radius=15, fill=(9, 18, 27)
        )

        left(x+13, 503, name, small, MUTED)
        left(x+13, 540, value, body, color)

    # الدعم والمقاومة
    panel((32, 640, W-32, 865))
    right(W-65, 658, "الدعم والمقاومة", heading, GOLD)

    supports = market_levels["supports"]
    resistances = market_levels["resistances"]

    for i in range(3):
        y = 720 + i*43

        s = supports[i] if i < len(supports) else None
        r = resistances[i] if i < len(resistances) else None

        left(
            65, y,
            f"S{i+1}  {fmt(s)}", body, GREEN
        )

        right(
            W-65, y,
            f"R{i+1}  {fmt(r)}", body, RED
        )

    # الأهداف
    panel((32, 885, W-32, 1300))
    right(W-65, 903, "الأهداف السعرية TP1 — TP8", heading, GOLD)

    for i, value in enumerate(target_data["targets"]):
        col = i % 2
        row = i // 2

        x = 65 if col == 0 else 565
        y = 965 + row*75

        panel(
            (x, y, x+470, y+58),
            (10, 26, 28), (0, 100, 73)
        )

        left(x+15, y+13, f"TP{i+1}", body, GREEN)

        right(
            x+450, y+13,
            fmt(value), body, WHITE
        )

    # وقف الخسارة
    panel((32, 1320, W-32, 1390), (38, 15, 23), RED)

    right(
        W-60, 1337,
        f"وقف الخسارة الفني: {fmt(target_data['stop'])} {currency}",
        body, RED
    )

    return img


# ======================== TELEGRAM ==========================

async def send_dashboard(session, token, image):
    if not token or not CHAT_ID:
        return False

    url = f"https://api.telegram.org/bot{token}/sendPhoto"

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)

    form = aiohttp.FormData()
    form.add_field("chat_id", str(CHAT_ID))
    form.add_field(
        "photo", buffer.getvalue(),
        filename="AI_PRO_MAX_V5.png",
        content_type="image/png"
    )

    try:
        async with session.post(
            url, data=form,
            timeout=aiohttp.ClientTimeout(total=40)
        ) as response:
            result = await response.json(content_type=None)

            if response.status == 200 and result.get("ok"):
                return True

            log.error("Telegram error: %s", result)

    except Exception:
        log.exception("Telegram photo error")

    return False


# ====================== API CONNECTION ======================

async def get_json(session, url, params=None, headers=None):
    try:
        async with session.get(
            url, params=params, headers=headers,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:

            data = await response.json(content_type=None)

            if response.status != 200:
                log.warning("API HTTP %s: %s", response.status, str(data)[:250])
                return None

            if isinstance(data, dict) and (
                data.get("status") == "error"
                or data.get("code") == 400
                or data.get("message") and not data.get("values")
            ):
                log.warning("API error: %s", str(data)[:250])
                return None

            return data

    except Exception:
        log.exception("API connection failed")
        return None


# ===================== MARKET DISCOVERY =====================

def extract_list(data):
    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    for key in (
        "data", "values", "stocks", "cryptocurrencies",
        "results", "items", "companies"
    ):
        value = data.get(key)

        if isinstance(value, list):
            return value

    return []


async def discover_td(session, endpoint, params):
    data = await get_json(
        session,
        f"{TD_BASE}/{endpoint}",
        params={**params, "apikey": TWELVE_API_KEY}
    )

    found = []

    for item in extract_list(data):
        if isinstance(item, str):
            found.append(item)
            continue

        if not isinstance(item, dict):
            continue

        symbol = (
            item.get("symbol")
            or item.get("ticker")
        )

        if symbol:
            found.append(str(symbol).strip().upper())

    return found


def valid_us_exchange(item):
    if not isinstance(item, dict):
        return False

    exchange = str(
        item.get("exchange") or item.get("mic_code") or ""
    ).upper().replace(" ", "")

    # البورصات الأمريكية الرئيسية فقط
    allowed = {
        "NASDAQ", "NYSE", "NYSEAMERICAN",
        "AMEX", "NYSEARCA", "BATS"
    }

    return exchange in allowed


async def refresh_us(session):
    found = []

    # جلب أسهم الولايات المتحدة من دليل Twelve Data
    data = await get_json(
        session,
        f"{TD_BASE}/stocks",
        params={
            "country": "United States",
            "apikey": TWELVE_API_KEY
        }
    )

    for item in extract_list(data):
        if not isinstance(item, dict):
            continue

        if not valid_us_exchange(item):
            continue

        symbol = item.get("symbol")

        if symbol:
            found.append(str(symbol).upper())

    found += extra_symbols(US_EXTRA)

    universe["US"] = unique(found)

    log.info("US universe discovered: %s", len(universe["US"]))


async def refresh_crypto(session):
    found = await discover_td(
        session,
        "cryptocurrencies",
        {}
    )

    found += extra_symbols(CRYPTO_EXTRA)

    universe["CRYPTO"] = unique(found)

    log.info(
        "Crypto universe discovered: %s",
        len(universe["CRYPTO"])
    )


async def sahmk_list(session, endpoint):
    if not SAHMK_API_KEY:
        return []

    data = await get_json(
        session,
        f"{SAHMK_BASE}/market/{endpoint}/",
        params={
            "limit": 1000,
            "offset": 0,
            "market": "TASI"
        },
        headers={"X-API-Key": SAHMK_API_KEY}
    )

    return extract_list(data)


async def refresh_tasi(session):
    gainers, volume = await asyncio.gather(
        sahmk_list(session, "gainers"),
        sahmk_list(session, "volume")
    )

    found = []

    for item in gainers + volume:
        if isinstance(item, dict):
            symbol = item.get("symbol") or item.get("ticker")
            if symbol:
                found.append(str(symbol).upper())

    found += extra_symbols(TASI_EXTRA)

    universe["TASI"] = unique(found)

    log.info(
        "TASI discovered from provider lists: %s",
        len(universe["TASI"])
    )


# ======================= PRICE DATA =========================

async def get_td_candles(session, symbol):
    data = await get_json(
        session,
        f"{TD_BASE}/time_series",
        params={
            "symbol": symbol,
            "interval": TD_INTERVAL,
            "outputsize": TD_CANDLES,
            "apikey": TWELVE_API_KEY
        }
    )

    if not isinstance(data, dict):
        return []

    return normalize(list(reversed(data.get("values", []))))


async def get_sahmk_history(session, symbol):
    today = datetime.now(
        ZoneInfo("Asia/Riyadh")
    ).date()

    start = today - timedelta(days=180)

    data = await get_json(
        session,
        f"{SAHMK_BASE}/historical/{symbol}/",
        params={
            "interval": "1d",
            "from": start.isoformat(),
            "to": today.isoformat(),
            "limit": 100,
            "offset": 0
        },
        headers={"X-API-Key": SAHMK_API_KEY}
    )

    if not isinstance(data, dict):
        return []

    rows = data.get("data")

    if isinstance(rows, dict):
        rows = (
            rows.get("results")
            or rows.get("items")
            or rows.get("candles")
        )

    return normalize(rows or [])


# ====================== SIGNAL ENGINE =======================

def cooldown_allowed(key):
    last = sent_signals.get(key, 0)

    return (
        datetime.now().timestamp() - last
        >= SIGNAL_COOLDOWN
    )


async def analyze(
    session, symbol, market, token, currency
):
    try:
        if market == "TASI":
            rows = await get_sahmk_history(session, symbol)
        else:
            rows = await get_td_candles(session, symbol)

        if len(rows) < 25:
            return

        price = rows[-1]["close"]

        # فلتر السعر الأمريكي
        if market == "US" and price < MIN_US_PRICE:
            return

        closes = [x["close"] for x in rows]

        e9 = ema(closes, 9)
        e21 = ema(closes, 21)
        rv = rsi(closes)
        av = atr(rows)
        vw = vwap(rows)
        vr = volume_ratio(rows)

        if not av or av <= 0:
            return

        lv = levels(rows)
        td = targets(price, av, lv["supports"])

        score = 0
        reasons = []

        if e9 and e21 and e9 > e21:
            score += 15
            reasons.append("اتجاه المتوسطات إيجابي")

        if vw and price > vw:
            score += 15
            reasons.append("السعر أعلى VWAP")

        if vr >= MIN_VOLUME_RATIO:
            score += 20
            reasons.append("ارتفاع حجم التداول")

        if 50 <= rv <= 75:
            score += 10
            reasons.append("RSI إيجابي")

        previous = rows[-2]["close"]

        prior = levels(rows[:-1])
        resistance = (
            prior["resistances"][0]
            if prior["resistances"] else None
        )

        breakout = (
            resistance is not None
            and price > resistance
            and previous <= resistance
        )

        if breakout:
            score += 25
            reasons.append("اختراق مقاومة")

        if e9 and price > e9 and previous <= e9:
            score += 10
            reasons.append("بداية حركة صاعدة")

        candle_range = rows[-1]["high"] - rows[-1]["low"]

        if candle_range > 0:
            position = (
                price - rows[-1]["low"]
            ) / candle_range

            if position >= 0.75:
                score += 5
                reasons.append("إغلاق قوي")

        score = min(score, 100)

        if score < MIN_SCORE:
            return

        signal_type = "BREAKOUT" if breakout else "EARLY"
        key = f"{market}:{symbol}:{signal_type}"

        if not cooldown_allowed(key):
            return

        image = build_dashboard(
            market,
            symbol,
            price,
            score,
            score,
            rv,
            vr,
            vw,
            av,
            lv,
            td,
            currency
        )

        sent = await send_dashboard(session, token, image)

        if sent:
            sent_signals[key] = datetime.now().timestamp()

            log.info(
                "V5 signal sent | %s | %s | %s/100",
                market, symbol, score
            )

    except Exception:
        log.exception("Analysis error %s %s", market, symbol)


# ======================== BATCH SCAN ========================

def next_batch(market):
    symbols = universe[market]

    if not symbols:
        return []

    start = offsets[market]
    end = start + BATCH_SIZE

    if end <= len(symbols):
        batch = symbols[start:end]
    else:
        batch = symbols[start:] + symbols[:end-len(symbols)]

    offsets[market] = end % len(symbols)

    return batch


async def scan_market(session, market):
    symbols = next_batch(market)

    if not symbols:
        log.warning("%s: no symbols available", market)
        return

    token = {
        "US": US_TOKEN,
        "CRYPTO": CRYPTO_TOKEN,
        "TASI": TASI_TOKEN
    }[market]

    currency = "SAR" if market == "TASI" else "USD"

    semaphore = asyncio.Semaphore(WORKERS)

    async def worker(symbol):
        async with semaphore:
            await analyze(
                session,
                symbol,
                market,
                token,
                currency
            )

    await asyncio.gather(
        *(worker(symbol) for symbol in symbols)
    )

    log.info(
        "%s batch scanned: %s / %s",
        market, len(symbols), len(universe[market])
    )


# ============================ MAIN ==========================

async def main():
    if not CHAT_ID:
        raise RuntimeError("CHAT_ID missing")

    if not TWELVE_API_KEY:
        raise RuntimeError("Twelve Data API key missing")

    if not US_TOKEN:
        log.warning("US_TOKEN missing")

    if not CRYPTO_TOKEN:
        log.warning("CRYPTO_TOKEN missing")

    if not SAHMK_API_KEY:
        log.warning("SAHMK_API_KEY missing")

    connector = aiohttp.TCPConnector(
        limit=WORKERS + 4,
        ttl_dns_cache=300
    )

    async with aiohttp.ClientSession(
        connector=connector
    ) as session:

        last_discovery = 0
        last_tasi = 0

        log.info("AI PRO MAX MARKET HUNTER V5 STARTED")

        while True:
            started = datetime.now().timestamp()

            try:
                now = datetime.now().timestamp()

                # تحديث قوائم الأسواق
                if now - last_discovery >= 21600:
                    await refresh_us(session)
                    await refresh_crypto(session)
                    last_discovery = now

                if now - last_tasi >= 21600:
                    await refresh_tasi(session)
                    last_tasi = now

                # المسح الدوري
                await scan_market(session, "US")
                await scan_market(session, "CRYPTO")

                if now - last_tasi < TASI_SCAN_SECONDS:
                    await scan_market(session, "TASI")

                else:
                    await refresh_tasi(session)
                    last_tasi = now
                    await scan_market(session, "TASI")

            except Exception:
                log.exception("Main cycle failed")

            elapsed = datetime.now().timestamp() - started

            wait = max(30, SCAN_SECONDS - elapsed)

            log.info("Next scan in %s seconds", int(wait))

            await asyncio.sleep(wait)


if __name__ == "__main__":
    asyncio.run(main())