
import os
import io
import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from html import escape

import aiohttp
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display


# ============================================================
# 💀🚀 AI PRO MAX — MARKET HUNTER V5
# 🇺🇸 US | 🪙 CRYPTO | 🇸🇦 TASI
# ============================================================

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

US_SYMBOLS = os.getenv(
    "US_SYMBOLS", "AAPL,TSLA,NVDA,AMD,PLTR"
).split(",")

CRYPTO_SYMBOLS = os.getenv(
    "CRYPTO_SYMBOLS",
    "BTC/USD,ETH/USD,SOL/USD,XRP/USD"
).split(",")

SCAN_SECONDS = int(os.getenv("SCAN_SECONDS", "300"))
TASI_SCAN_SECONDS = int(os.getenv("TASI_SCAN_SECONDS", "1800"))

MIN_SCORE = int(os.getenv("MIN_SCORE", "65"))
MIN_VOLUME_RATIO = float(os.getenv("MIN_VOLUME_RATIO", "1.5"))
MIN_US_PRICE = float(os.getenv("MIN_US_PRICE", "0.15"))

TD_INTERVAL = os.getenv("TD_INTERVAL", "5min")
TD_CANDLES = int(os.getenv("TD_CANDLES", "100"))

TD_BASE = "https://api.twelvedata.com"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

log = logging.getLogger("AI_PRO_MAX")

sent_signals = {}


# ============================================================
# HELPERS
# ============================================================

def clean_symbols(items):
    return list(dict.fromkeys(
        x.strip().upper()
        for x in items if x.strip()
    ))


US_SYMBOLS = clean_symbols(US_SYMBOLS)
CRYPTO_SYMBOLS = clean_symbols(CRYPTO_SYMBOLS)


def num(value, default=0.0):
    try:
        x = float(value)
        return x if x == x else default
    except (ValueError, TypeError):
        return default


def fmt(value, digits=4):
    if value is None:
        return "غير متاح"
    return f"{value:,.{digits}f}"


def price_fmt(value):
    if value is None:
        return "—"
    return f"{value:,.4f}" if abs(value) < 1 else f"{value:,.2f}"


def rtl(value):
    try:
        return get_display(
            arabic_reshaper.reshape(str(value))
        )
    except Exception:
        return str(value)


def font(size, bold=False):
    root = os.path.dirname(os.path.abspath(__file__))

    candidates = [
        os.path.join(
            root, "fonts",
            "NotoKufiArabic-Bold.ttf" if bold
            else "NotoKufiArabic-Regular.ttf"
        ),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass

    return ImageFont.load_default()


# ============================================================
# CANDLE DATA
# ============================================================

def normalize_rows(rows):
    result = []

    if not isinstance(rows, list):
        return result

    for row in rows:
        if not isinstance(row, dict):
            continue

        lower = {str(k).lower(): v for k, v in row.items()}

        item = {
            "open": num(lower.get("open", lower.get("o"))),
            "high": num(lower.get("high", lower.get("h"))),
            "low": num(lower.get("low", lower.get("l"))),
            "close": num(
                lower.get("close", lower.get("c",
                lower.get("price", lower.get("last"))))
            ),
            "volume": num(
                lower.get("volume", lower.get("vol",
                lower.get("v", lower.get("total_volume"))))
            )
        }

        if item["close"] <= 0:
            continue

        if item["high"] <= 0:
            item["high"] = max(item["open"], item["close"])

        if item["low"] <= 0:
            item["low"] = min(
                item["open"] or item["close"],
                item["close"]
            )

        result.append(item)

    return result


def ema(values, period):
    if len(values) < period:
        return None

    result = sum(values[:period]) / period
    alpha = 2 / (period + 1)

    for value in values[period:]:
        result = (
            value * alpha
            + result * (1 - alpha)
        )

    return result


def calculate_rsi(values, period=14):
    if len(values) <= period:
        return 50.0

    changes = [
        values[i] - values[i-1]
        for i in range(1, len(values))
    ]

    gains = [max(x, 0) for x in changes]
    losses = [max(-x, 0) for x in changes]

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def calculate_atr(rows, period=14):
    if len(rows) < period + 1:
        return None

    values = []

    for i in range(1, len(rows)):
        high = rows[i]["high"]
        low = rows[i]["low"]
        previous = rows[i-1]["close"]

        values.append(max(
            high - low,
            abs(high - previous),
            abs(low - previous)
        ))

    return sum(values[-period:]) / period


def calculate_vwap(rows):
    total_value = 0
    total_volume = 0

    for row in rows:
        volume = row["volume"]

        if volume <= 0:
            continue

        typical = (
            row["high"] +
            row["low"] +
            row["close"]
        ) / 3

        total_value += typical * volume
        total_volume += volume

    if total_volume == 0:
        return None

    return total_value / total_volume


def calculate_volume_ratio(rows):
    if len(rows) < 21:
        return 0

    previous = [
        x["volume"] for x in rows[-21:-1]
    ]

    average = sum(previous) / len(previous)

    if average <= 0:
        return 0

    return rows[-1]["volume"] / average


# ============================================================
# SUPPORT / RESISTANCE
# ============================================================

def calculate_levels(rows):
    if len(rows) < 25:
        return None

    highs = [x["high"] for x in rows]
    lows = [x["low"] for x in rows]

    price = rows[-1]["close"]

    ph = []
    pl = []

    start = max(2, len(rows) - 80)

    for i in range(start, len(rows)-2):

        if (
            highs[i] >= highs[i-1]
            and highs[i] >= highs[i-2]
            and highs[i] > highs[i+1]
            and highs[i] > highs[i+2]
        ):
            ph.append(highs[i])

        if (
            lows[i] <= lows[i-1]
            and lows[i] <= lows[i-2]
            and lows[i] < lows[i+1]
            and lows[i] < lows[i+2]
        ):
            pl.append(lows[i])

    supports = sorted(
        {x for x in pl if x < price},
        reverse=True
    )

    resistances = sorted(
        {x for x in ph if x > price}
    )

    if not supports:
        supports = sorted(
            {x for x in lows[-20:] if x < price},
            reverse=True
        )

    if not resistances:
        resistances = sorted(
            {x for x in highs[-20:] if x > price}
        )

    return {
        "supports": supports[:3],
        "resistances": resistances[:3]
    }


def calculate_targets(price, atr, supports):
    if not atr or atr <= 0:
        return None

    stop = price - 1.5 * atr

    if supports:
        stop = min(stop, supports[0] - 0.15 * atr)

    return {
        "stop": stop,
        "targets": [
            price + atr * n
            for n in range(1, 9)
        ]
    }


# ============================================================
# V5 PROFESSIONAL DASHBOARD
# جميع المعلومات داخل صورة واحدة
# ============================================================

def build_dashboard_image(
    market, symbol, price, score, rsi, vol_ratio,
    vwap, atr, levels, targets_data, reasons,
    currency, current_volume=0, liquidity=0
):

    W, H = 1600, 2200

    image = Image.new(
        "RGB", (W, H), (5, 10, 17)
    )

    draw = ImageDraw.Draw(image)

    GREEN = (0, 240, 145)
    DARK_GREEN = (0, 105, 75)
    RED = (255, 65, 85)
    WHITE = (245, 249, 252)
    GOLD = (255, 195, 55)
    CYAN = (65, 205, 255)
    MUTED = (150, 170, 185)
    PANEL = (15, 25, 36)
    PANEL2 = (9, 19, 29)

    title = font(58, True)
    heading = font(43, True)
    large = font(65, True)
    number = font(37, True)
    body = font(34, True)
    small = font(27)

    def box(coords, fill=PANEL, outline=(35, 90, 80), radius=25):
        draw.rounded_rectangle(
            coords,
            radius=radius,
            fill=fill,
            outline=outline,
            width=3
        )

    def left(x, y, value, f=body, color=WHITE):
        draw.text(
            (x, y), str(value),
            font=f, fill=color
        )

    def right(x, y, value, f=body, color=WHITE):
        draw.text(
            (x, y), rtl(value),
            font=f, fill=color,
            anchor="ra"
        )

    # HEADER
    box(
        (25, 25, 1575, 185),
        (8, 25, 33), GREEN
    )

    left(65, 55, "AI PRO MAX", title, GREEN)
    right(1530, 65, "MARKET HUNTER V5", heading)

    left(
        70, 125,
        "LIVE MARKET INTELLIGENCE",
        small, MUTED
    )

    # PRICE
    box(
        (25, 210, 1575, 525),
        (13, 29, 40), GREEN
    )

    right(
        1515, 235,
        f"{market} | {symbol}",
        heading, CYAN
    )

    left(
        75, 315,
        price_fmt(price),
        large, GREEN
    )

    left(80, 410, currency, body, MUTED)

    right(1510, 330, "قوة الإشارة", heading, GOLD)
    right(1510, 395, f"{score}/100", large, GREEN)

    # SIGNAL BAR
    x1, y1, x2 = 750, 465, 1510

    draw.rounded_rectangle(
        (x1, y1, x2, y1+27),
        radius=14,
        fill=(45, 60, 70)
    )

    draw.rounded_rectangle(
        (
            x1, y1,
            x1 + int(
                (x2-x1) *
                max(0, min(score, 100))/100
            ),
            y1+27
        ),
        radius=14,
        fill=GREEN
    )

    # METRICS
    box((25, 555, 1575, 1030))

    right(
        1515, 580,
        "الحجم والسيولة والنشاط",
        heading, GOLD
    )

    metrics = [
        ("VOLUME", f"{current_volume:,.0f}", CYAN),
        ("LIQUIDITY", f"{liquidity:,.2f} {currency}", GREEN),
        ("ACTIVITY", f"x{vol_ratio:.2f}", GOLD),
        ("RSI", f"{rsi:.1f}", CYAN),
        ("VWAP", price_fmt(vwap) if vwap else "—", WHITE),
        ("ATR", price_fmt(atr) if atr else "—", GOLD)
    ]

    positions = [
        (65, 670), (575, 670), (1085, 670),
        (65, 845), (575, 845), (1085, 845)
    ]

    for (label, value, color), (x, y) in zip(
        metrics, positions
    ):

        box(
            (x, y, x+450, y+140),
            PANEL2, (30, 65, 75), 20
        )

        left(x+22, y+15, label, small, MUTED)
        left(x+22, y+65, value, number, color)

    # SUPPORT / RESISTANCE
    box((25, 1060, 1575, 1390))

    right(
        1515, 1085,
        "الدعم والمقاومة",
        heading, GOLD
    )

    supports = levels.get("supports", [])
    resistances = levels.get("resistances", [])

    for i in range(3):

        y = 1170 + i*65

        support = (
            price_fmt(supports[i])
            if i < len(supports) else "—"
        )

        resistance = (
            price_fmt(resistances[i])
            if i < len(resistances) else "—"
        )

        left(
            75, y,
            f"S{i+1}  {support}",
            body, GREEN
        )

        right(
            1510, y,
            f"R{i+1}  {resistance}",
            body, RED
        )

    # TARGETS TP1-TP8
    box((25, 1420, 1575, 1970))

    right(
        1515, 1445,
        "الأهداف السعرية TP1 — TP8",
        heading, GOLD
    )

    targets = targets_data.get("targets", [])

    for i, target in enumerate(targets[:8]):

        col = i % 2
        row = i // 2

        x = 65 if col == 0 else 825
        y = 1520 + row*105

        box(
            (x, y, x+710, y+82),
            (9, 28, 28),
            DARK_GREEN,
            20
        )

        left(
            x+25, y+20,
            f"TP{i+1}",
            body, GREEN
        )

        right(
            x+680, y+12,
            price_fmt(target),
            body, WHITE
        )

        change = (
            (target-price)/price*100
            if price > 0 else 0
        )

        right(
            x+680, y+50,
            f"{change:+.2f}%",
            small, GREEN
        )

    # STOP LOSS
    stop = targets_data.get("stop")

    box(
        (25, 1995, 1575, 2110),
        (42, 13, 22), RED
    )

    right(
        1510, 2025,
        f"وقف الخسارة الفني: {price_fmt(stop)} {currency}",
        heading, RED
    )

    # FOOTER
    footer = datetime.now(
        ZoneInfo("Asia/Riyadh")
    ).strftime("%Y-%m-%d %H:%M:%S")

    right(
        1510, 2140,
        f"AI PRO MAX | {footer} | توقيت الرياض",
        small, MUTED
    )

    output = io.BytesIO()

    image.save(
        output,
        format="PNG",
        optimize=True
    )

    output.seek(0)

    return output


# ============================================================
# TELEGRAM
# ============================================================

async def telegram_send_photo(
    session, token, photo, caption
):

    if not token or not CHAT_ID:
        log.error("Telegram token or CHAT_ID missing")
        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{token}/sendPhoto"
    )

    form = aiohttp.FormData()

    form.add_field("chat_id", str(CHAT_ID))
    form.add_field("caption", caption[:900])

    form.add_field(
        "photo",
        photo.getvalue(),
        filename="AI_PRO_MAX_V5.png",
        content_type="image/png"
    )

    try:

        async with session.post(
            url,
            data=form,
            timeout=aiohttp.ClientTimeout(total=40)
        ) as response:

            result = await response.json(
                content_type=None
            )

            if response.status == 200 and result.get("ok"):
                return True

            log.error(
                "Telegram photo error: %s",
                str(result)[:400]
            )

    except Exception:
        log.exception("Telegram photo failed")

    return False


# ============================================================
# HTTP
# ============================================================

async def get_json(
    session, url, params=None, headers=None
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
                log.error(
                    "HTTP %s: %s",
                    response.status,
                    str(data)[:300]
                )
                return None

            if isinstance(data, dict):

                if (
                    data.get("status") == "error"
                    or data.get("code") == 400
                    or (
                        data.get("message")
                        and not data.get("values")
                    )
                ):
                    log.error(
                        "API error: %s",
                        str(data)[:300]
                    )
                    return None

            return data

    except Exception:
        log.exception("HTTP request failed")
        return None


# ============================================================
# TWELVE DATA
# ============================================================

async def get_td_candles(session, symbol, market):

    if not TWELVE_API_KEY:
        return None

    params = {
        "symbol": symbol,
        "interval": TD_INTERVAL,
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

    if not isinstance(data, dict):
        return None

    values = data.get("values")

    if not isinstance(values, list):
        return None

    return list(reversed(values))


# ============================================================
# ANALYSIS
# ============================================================

def allow_signal(key, cooldown=1800):

    last = sent_signals.get(key, 0)

    return (
        datetime.now().timestamp() - last
        >= cooldown
    )


async def analyze_rows(
    session, symbol, market, rows, token, currency
):

    rows = normalize_rows(rows)

    if len(rows) < 25:
        return

    closes = [x["close"] for x in rows]

    if any(x <= 0 for x in closes[-25:]):
        return

    price = closes[-1]
    previous_price = closes[-2]

    if market == "US" and price < MIN_US_PRICE:
        return

    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)

    rsi = calculate_rsi(closes)
    atr = calculate_atr(rows)
    vwap = calculate_vwap(rows)
    vol_ratio = calculate_volume_ratio(rows)

    if not atr or atr <= 0:
        return

    prior_levels = calculate_levels(rows[:-1])
    display_levels = calculate_levels(rows)

    if not prior_levels or not display_levels:
        return

    targets_data = calculate_targets(
        price,
        atr,
        display_levels["supports"]
    )

    if not targets_data:
        return

    score = 0
    reasons = []

    if ema9 and ema21 and ema9 > ema21:
        score += 15
        reasons.append("EMA9 أعلى من EMA21")

    if vwap and price > vwap:
        score += 15
        reasons.append("السعر أعلى VWAP")

    if vol_ratio >= MIN_VOLUME_RATIO:
        score += 20
        reasons.append(
            f"ارتفاع الحجم ×{vol_ratio:.2f}"
        )

    if 50 <= rsi <= 75:
        score += 10
        reasons.append("RSI إيجابي")

    prior_resistance = (
        prior_levels["resistances"][0]
        if prior_levels["resistances"]
        else None
    )

    breakout = (
        prior_resistance is not None
        and price > prior_resistance
        and previous_price <= prior_resistance
    )

    if breakout:
        score += 25
        reasons.append("اختراق مقاومة سابقة")

    early = (
        ema9 is not None
        and price > ema9
        and previous_price <= ema9
    )

    if early:
        score += 10
        reasons.append("بداية تحرك فوق EMA9")

    candle_range = rows[-1]["high"] - rows[-1]["low"]

    if candle_range > 0:

        close_position = (
            price - rows[-1]["low"]
        ) / candle_range

        if close_position >= 0.75:
            score += 5
            reasons.append("إغلاق قرب قمة الشمعة")

    if score < MIN_SCORE:
        return

    signal = "BREAKOUT" if breakout else "EARLY"

    key = f"{market}:{symbol}:{signal}"

    if not allow_signal(key):
        return

    # حجم آخر شمعة
    current_volume = rows[-1]["volume"]

    # قيمة التداول للشمعة الأخيرة
    liquidity = price * current_volume

    dashboard = build_dashboard_image(
        market=market,
        symbol=symbol,
        price=price,
        score=score,
        rsi=rsi,
        vol_ratio=vol_ratio,
        vwap=vwap,
        atr=atr,
        levels=display_levels,
        targets_data=targets_data,
        reasons=reasons,
        currency=currency,
        current_volume=current_volume,
        liquidity=liquidity
    )

    caption = (
        f"💀🚀 AI PRO MAX V5 — {symbol}\n"
        f"⭐ قوة الإشارة: {score}/100\n"
        "📊 التفاصيل والمستويات داخل اللوحة."
    )

    photo_ok = await telegram_send_photo(
        session,
        token,
        dashboard,
        caption
    )

    if photo_ok:

        sent_signals[key] = (
            datetime.now().timestamp()
        )

        log.info(
            "V5 SENT %s %s SCORE=%s",
            market, symbol, score
        )


# ============================================================
# MARKET SCANNERS
# ============================================================

async def scan_td_market(
    session, symbols, market
):

    token = (
        US_TOKEN if market == "US"
        else CRYPTO_TOKEN
    )

    semaphore = asyncio.Semaphore(3)

    async def worker(symbol):

        async with semaphore:

            try:

                rows = await get_td_candles(
                    session, symbol, market
                )

                if rows:

                    await analyze_rows(
                        session,
                        symbol,
                        market,
                        rows,
                        token,
                        "USD"
                    )

            except Exception:
                log.exception(
                    "Worker failed %s %s",
                    market, symbol
                )

    await asyncio.gather(
        *(worker(s) for s in symbols)
    )


# ============================================================
# SAHMK — TASI
# ============================================================

async def get_sahmk_history(session, symbol):

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
        "limit": 100,
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

    if isinstance(rows, dict):
        rows = (
            rows.get("results")
            or rows.get("items")
            or rows.get("candles")
        )

    return rows if isinstance(rows, list) else None


async def get_sahmk_market_list(session, endpoint):

    if not SAHMK_API_KEY:
        return []

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
        "data", "results", "gainers",
        "leaders", "stocks", "items"
    ):

        value = data.get(key)

        if isinstance(value, list):
            return value

    return []


async def scan_tasi(session):

    if not SAHMK_API_KEY:
        log.warning("SAHMK_API_KEY missing")
        return

    gainers, volume = await asyncio.gather(
        get_sahmk_market_list(session, "gainers"),
        get_sahmk_market_list(session, "volume")
    )

    selected = {}

    for item in gainers + volume:

        if not isinstance(item, dict):
            continue

        symbol = str(
            item.get("symbol")
            or item.get("ticker")
            or ""
        ).strip()

        if symbol:
            selected[symbol] = item

    log.info(
        "TASI selected symbols: %s",
        len(selected)
    )

    semaphore = asyncio.Semaphore(2)

    async def worker(symbol):

        async with semaphore:

            try:

                rows = await get_sahmk_history(
                    session, symbol
                )

                if rows:

                    await analyze_rows(
                        session,
                        symbol,
                        "السوق السعودي",
                        rows,
                        TASI_TOKEN,
                        "SAR"
                    )

            except Exception:
                log.exception(
                    "TASI worker failed %s",
                    symbol
                )

    await asyncio.gather(
        *(worker(s) for s in selected)
    )


# ============================================================
# MAIN — 24/7
# ============================================================

async def main():

    if not CHAT_ID:
        raise RuntimeError(
            "CHAT_ID غير موجود في Railway Variables"
        )

    if not TWELVE_API_KEY:
        raise RuntimeError(
            "TWELVE_DATA_API_KEY غير موجود"
        )

    if not US_TOKEN:
        log.warning("US_TOKEN missing")

    if not CRYPTO_TOKEN:
        log.warning("CRYPTO_TOKEN missing")

    if not SAHMK_API_KEY:
        log.warning("SAHMK_API_KEY missing")

    log.info(
        "AI PRO MAX V5 STARTED | US=%s | CRYPTO=%s",
        len(US_SYMBOLS),
        len(CRYPTO_SYMBOLS)
    )

    connector = aiohttp.TCPConnector(
        limit=15,
        ttl_dns_cache=300
    )

    async with aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=40)
    ) as session:

        last_tasi_scan = 0

        while True:

            started = datetime.now().timestamp()

            try:

                if US_SYMBOLS:
                    await scan_td_market(
                        session,
                        US_SYMBOLS,
                        "US"
                    )

                if CRYPTO_SYMBOLS:
                    await scan_td_market(
                        session,
                        CRYPTO_SYMBOLS,
                        "CRYPTO"
                    )

                now = datetime.now().timestamp()

                if (
                    now - last_tasi_scan
                    >= TASI_SCAN_SECONDS
                ):

                    await scan_tasi(session)

                    last_tasi_scan = now

            except Exception:
                log.exception(
                    "Main scan cycle failed"
                )

            elapsed = (
                datetime.now().timestamp() - started
            )

            wait = max(
                15,
                SCAN_SECONDS - elapsed
            )

            log.info(
                "Next scan in %.0f seconds",
                wait
            )

            await asyncio.sleep(wait)


if __name__ == "__main__":
    asyncio.run(main())
 