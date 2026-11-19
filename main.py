
import os
import io
import json
import time
import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta, timezone

import aiohttp
from PIL import Image, ImageDraw, ImageFont

try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    def rtl(text):
        return get_display(arabic_reshaper.reshape(str(text)))
except ImportError:
    def rtl(text):
        return str(text)


# =========================================================
# AI PRO MAX V12 — ULTRA HD TRADING TERMINAL
# US + TASI/NOMU + BINANCE SPOT
# IMAGE ALERTS | 20 TARGETS | 24/7
# =========================================================

APP = "AI PRO MAX"
VERSION = "V12 ULTRA HD"

SCAN_SECONDS = int(os.getenv("SCAN_SECONDS", "300"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "20"))
WORKERS = int(os.getenv("WORKERS", "4"))
DB_PATH = os.getenv("DB_PATH", "/data/ai_pro_max.db")

US_MIN_PRICE = 0.12
TIMEFRAMES = ["5m", "15m", "1h", "1d"]

SIFTING_KEY = os.getenv("SIFTING_API_KEY", "")
SAHMK_KEY = os.getenv("SAHMK_API_KEY", "") or os.getenv("TASI_TOKEN", "")
TWELVE_KEY = (
    os.getenv("TWELVE_DATA_API_KEY", "")
    or os.getenv("TWELVEDATA_API_KEY", "")
)

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

WIDTH = 1600
HEIGHT = 1900

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("AIPROMAX")


# =========================================================
# DATABASE
# =========================================================

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
            PRIMARY KEY (market,symbol,timeframe)
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
            PRIMARY KEY (market,symbol,timeframe,target_no)
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
        DO UPDATE SET data=excluded.data,updated=excluded.updated
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
        ON CONFLICT(market)
        DO UPDATE SET position=excluded.position
    """, (market, position))
    con.commit()
    con.close()


# =========================================================
# FONT AND IMAGE DESIGN
# =========================================================

def load_font(size):
    paths = [
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"
    ]

    for path in paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass

    return ImageFont.load_default()


def draw_rtl(draw, xy, text, font, fill, anchor="ra"):
    draw.text(
        xy,
        rtl(text),
        font=font,
        fill=fill,
        anchor=anchor
    )


def money(value, market):
    currency = "SAR" if market == "TASI" else (
        "USDT" if market == "CRYPTO" else "USD"
    )

    if value >= 100:
        decimals = 2
    elif value >= 1:
        decimals = 4
    else:
        decimals = 6

    return f"{value:,.{decimals}f} {currency}"


def get_targets(market, symbol, tf):
    con = db()
    rows = con.execute("""
        SELECT target_no,target_price,hit
        FROM targets
        WHERE market=? AND symbol=? AND timeframe=?
        ORDER BY target_no
    """, (market, symbol, tf)).fetchall()
    con.close()
    return rows


def create_dashboard(market, item, tf, result, events, hits):
    image = Image.new("RGB", (WIDTH, HEIGHT), "#07111f")
    draw = ImageDraw.Draw(image)

    title_font = load_font(64)
    big_font = load_font(80)
    price_font = load_font(68)
    section_font = load_font(43)
    normal_font = load_font(36)
    small_font = load_font(30)
    target_font = load_font(31)

    white = "#F3F7FF"
    green = "#21D483"
    red = "#FF5268"
    yellow = "#FFD166"
    muted = "#9CAFC5"
    panel = "#101F33"
    line = "#263C55"

    market_name = {
        "US": "السوق الأمريكي",
        "TASI": "السوق السعودي",
        "CRYPTO": "العملات الرقمية"
    }.get(market, market)

    currency = "SAR" if market == "TASI" else (
        "USDT" if market == "CRYPTO" else "USD"
    )

    price = result["price"]
    direction = (
        "صاعد" if result["change"] > 0
        else "هابط" if result["change"] < 0
        else "مستقر"
    )
    direction_color = green if result["change"] > 0 else (
        red if result["change"] < 0 else yellow
    )

    def panel_box(x1, y1, x2, y2):
        draw.rounded_rectangle(
            (x1, y1, x2, y2),
            radius=25,
            fill=panel,
            outline=line,
            width=2
        )

    # HEADER
    draw.rounded_rectangle(
        (35, 30, WIDTH - 35, 165),
        radius=28,
        fill="#142943",
        outline="#315475",
        width=3
    )

    draw.text(
        (WIDTH // 2, 83),
        "AI PRO MAX",
        font=title_font,
        fill=white,
        anchor="mm"
    )

    draw.text(
        (WIDTH // 2, 135),
        VERSION,
        font=small_font,
        fill=green,
        anchor="mm"
    )

    # SYMBOL AND MARKET
    panel_box(35, 190, WIDTH - 35, 480)

    symbol = item["symbol"]
    name = item.get("name", symbol)

    draw_rtl(
        draw, (WIDTH - 75, 245),
        f"{name}  |  {symbol}",
        section_font, white
    )

    draw_rtl(
        draw, (WIDTH - 75, 310),
        market_name + "  |  الفاصل " + tf,
        normal_font, muted
    )

    draw.text(
        (WIDTH // 2, 405),
        f"{price:,.6f} {currency}",
        font=price_font,
        fill=green if result["change"] >= 0 else red,
        anchor="mm"
    )

    draw_rtl(
        draw, (WIDTH - 75, 455),
        f"التغير: {result['change']:+.2f}%  |  الحالة: {direction}",
        normal_font, direction_color
    )

    # MARKET DATA
    panel_box(35, 505, WIDTH - 35, 890)

    draw_rtl(
        draw, (WIDTH - 75, 565),
        "مؤشرات السوق والسيولة",
        section_font, yellow
    )

    left_x = 760
    right_x = WIDTH - 75

    metrics = [
        ("الفوليوم", f"{result['volume']:,.0f}"),
        ("نشاط الفوليوم", f"{result['volume_ratio']:.2f}x"),
        ("RSI", f"{result['rsi']:.2f}" if result["rsi"] is not None else "--"),
        ("VWAP", f"{result['vwap']:.6f}" if result["vwap"] else "--"),
        ("قوة المشترين التقديرية", f"{result['buyer_proxy']:.1f}%"),
        ("التجميع المحتمل", "موجود" if result["accumulation"] else "غير ظاهر")
    ]

    for i, (label, value) in enumerate(metrics):
        y = 640 + i * 39
        draw_rtl(draw, (right_x, y), label, small_font, muted)
        draw.text(
            (left_x, y),
            str(value),
            font=small_font,
            fill=white,
            anchor="la"
        )

    # SUPPORT / RESISTANCE
    panel_box(35, 915, WIDTH - 35, 1095)

    draw_rtl(
        draw, (WIDTH - 75, 970),
        "مناطق السعر المهمة",
        section_font, yellow
    )

    draw_rtl(
        draw, (WIDTH - 75, 1040),
        f"المقاومة: {result['resistance']:.6f}",
        normal_font, red
    )

    draw_rtl(
        draw, (760, 1040),
        f"الدعم: {result['support']:.6f}",
        normal_font, green
    )

    # EMA
    panel_box(35, 1120, WIDTH - 35, 1320)

    draw_rtl(
        draw, (WIDTH - 75, 1170),
        "المتوسطات المتحركة EMA",
        section_font, yellow
    )

    ema_values = result["ema"]
    ema_line = "   |   ".join(
        f"{p}: {v:.4f}" for p, v in ema_values.items()
        if v is not None
    )

    draw.text(
        (WIDTH // 2, 1260),
        ema_line if ema_line else "--",
        font=normal_font,
        fill=white,
        anchor="mm"
    )

    # TARGETS
    panel_box(35, 1345, WIDTH - 35, 1770)

    draw_rtl(
        draw, (WIDTH - 75, 1400),
        "الأهداف السعرية 1 - 20",
        section_font, yellow
    )

    targets = get_targets(market, symbol, tf)

    if targets:
        for i, (number, target_price, hit) in enumerate(targets):
            col = i // 10
            row = i % 10

            x = WIDTH - 90 - col * 760
            y = 1470 + row * 29

            color = green if hit else muted
            status = "✓" if hit else "○"

            draw_rtl(
                draw,
                (x, y),
                f"{status} هدف {number}: {money(target_price, market)}",
                target_font,
                color
            )
    else:
        draw_rtl(
            draw, (WIDTH - 75, 1510),
            "تنتظر اكتمال بيانات ATR",
            normal_font, muted
        )

    # FOOTER
    draw.line((50, 1790, WIDTH - 50, 1790), fill=line, width=3)

    draw.text(
        (WIDTH // 2, 1830),
        "AI PRO MAX  |  LIVE MARKET SCANNER  |  24/7",
        font=small_font,
        fill=green,
        anchor="mm"
    )

    draw.text(
        (WIDTH // 2, 1870),
        datetime.now().strftime("%Y-%m-%d  %H:%M:%S"),
        font=small_font,
        fill=muted,
        anchor="mm"
    )

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    output.seek(0)
    output.name = f"{symbol}_{tf}.png"

    return output


# =========================================================
# HTTP
# =========================================================

async def get_json(session, url, headers=None, params=None, retries=3):
    for attempt in range(retries):
        try:
            async with session.get(
                url,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=25)
            ) as response:

                if response.status == 429:
                    await asyncio.sleep(3 * (attempt + 1))
                    continue

                if response.status >= 500:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue

                if response.status >= 400:
                    log.warning("HTTP %s: %s",
                                response.status, (await response.text())[:200])
                    return None

                return await response.json(content_type=None)

        except Exception as exc:
            log.warning("HTTP error: %s", exc)
            await asyncio.sleep(2 * (attempt + 1))

    return None


async def telegram_text(session, token, chat, message):
    if not token or not chat:
        log.error("Telegram token/chat missing")
        return False

    url = f"{TELEGRAM_API}/bot{token}/sendMessage"

    for start in range(0, len(message), 3900):
        try:
            async with session.post(
                url,
                json={
                    "chat_id": chat,
                    "text": message[start:start + 3900],
                    "disable_web_page_preview": True
                },
                timeout=aiohttp.ClientTimeout(total=25)
            ) as response:

                data = await response.json(content_type=None)

                if response.status != 200 or not data.get("ok"):
                    log.error("Telegram text error: %s", data)
                    return False

        except Exception as exc:
            log.exception("Telegram error: %s", exc)
            return False

    return True


async def telegram_photo(session, token, chat, photo, caption):
    if not token or not chat:
        log.error("Telegram photo credentials missing")
        return False

    url = f"{TELEGRAM_API}/bot{token}/sendPhoto"

    form = aiohttp.FormData()
    form.add_field("chat_id", str(chat))
    form.add_field("caption", caption[:1000])
    form.add_field(
        "photo",
        photo,
        filename="AI_PRO_MAX.png",
        content_type="image/png"
    )

    try:
        async with session.post(
            url,
            data=form,
            timeout=aiohttp.ClientTimeout(total=45)
        ) as response:

            data = await response.json(content_type=None)

            if response.status != 200 or not data.get("ok"):
                log.error("Telegram photo error: %s", data)
                return False

            log.info("IMAGE SENT SUCCESS")
            return True

    except Exception as exc:
        log.exception("Photo send error: %s", exc)
        return False


def bot_details(market):
    if market == "US":
        return US_BOT, US_CHAT
    if market == "TASI":
        return TASI_BOT, TASI_CHAT
    return CRYPTO_BOT, CRYPTO_CHAT


# =========================================================
# SYMBOL UNIVERSES
# =========================================================

async def get_us_symbols(session):
    if not TWELVE_KEY:
        log.error("TWELVEDATA_API_KEY missing")
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
        if currency != "USD" or exchange not in allowed:
            continue

        seen.add(symbol)
        symbols.append({
            "symbol": symbol,
            "name": item.get("name", symbol)
        })

    log.info("US symbols: %s", len(symbols))
    return symbols


async def get_sa_symbols(session):
    if not SAHMK_KEY:
        log.error("SAHMK_API_KEY missing")
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
                    "name": item.get("name_ar") or item.get("name_en") or symbol
                })

            offset += len(rows)

            total = int(data.get("total", 0) or 0)
            if len(rows) < 500 or (total and offset >= total):
                break

    log.info("Saudi symbols: %s", len(symbols))
    return symbols


async def get_crypto_symbols(session):
    data = await get_json(
        session,
        f"{BINANCE_API}/api/v3/exchangeInfo"
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
            "name": item.get("baseAsset", item.get("symbol"))
        })

    log.info("Crypto symbols: %s", len(symbols))
    return symbols


# =========================================================
# MARKET DATA
# =========================================================

async def us_bars(session, symbol, interval):
    if not SIFTING_KEY:
        return []

    end = datetime.now(timezone.utc)
    days = 5 if interval in ("5m", "15m") else 40

    data = await get_json(
        session,
        f"{SIFTING_API}/v1/hist/stocks/{symbol}/bars",
        headers={
            "X-API-Key": SIFTING_KEY,
            "Accept-Encoding": "gzip"
        },
        params={
            "start": (end - timedelta(days=days)).strftime("%Y-%m-%d"),
            "end": end.strftime("%Y-%m-%d"),
            "interval": interval,
            "limit": 500
        }
    )

    if not data:
        return []

    return [{
        "open": float(x["o"]),
        "high": float(x["h"]),
        "low": float(x["l"]),
        "close": float(x["c"]),
        "volume": float(x["v"]),
        "time": x.get("t")
    } for x in data.get("data", [])
        if all(k in x for k in ("o", "h", "l", "c", "v"))]


async def sa_bars(session, symbol, interval):
    if not SAHMK_KEY:
        return []

    interval_map = {
        "5m": "5min",
        "15m": "15min",
        "1h": "60min",
        "1d": "1d"
    }

    days = 30 if interval != "1d" else 180

    data = await get_json(
        session,
        f"{SAHMK_API}/historical/{symbol}/",
        headers={"X-API-Key": SAHMK_KEY},
        params={
            "interval": interval_map[interval],
            "from": (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d"),
            "to": datetime.now().strftime("%Y-%m-%d"),
            "limit": 500
        }
    )

    if not data:
        return []

    return [{
        "open": float(x["open"]),
        "high": float(x["high"]),
        "low": float(x["low"]),
        "close": float(x["close"]),
        "volume": float(x["volume"]),
        "time": x.get("date")
    } for x in data.get("data", [])
        if all(k in x for k in ("open", "high", "low", "close", "volume"))]


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

    if not isinstance(data, list):
        return []

    return [{
        "open": float(x[1]),
        "high": float(x[2]),
        "low": float(x[3]),
        "close": float(x[4]),
        "volume": float(x[5]),
        "time": x[0]
    } for x in data]


# =========================================================
# TECHNICAL ANALYSIS
# =========================================================

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

    gains = []
    losses = []

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

        trs.append(max(
            current["high"] - current["low"],
            abs(current["high"] - previous["close"]),
            abs(current["low"] - previous["close"])
        ))

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

    emas = {p: ema(closes, p) for p in (10, 14, 25, 50)}

    avg_volume = sum(volumes[-21:-1]) / 20
    volume_ratio = volumes[-1] / avg_volume if avg_volume > 0 else 0

    support = min(x["low"] for x in bars[-30:])
    resistance = max(x["high"] for x in bars[-30:])

    recent_range = (
        max(x["high"] for x in bars[-8:])
        - min(x["low"] for x in bars[-8:])
    )

    accumulation = (
        current_atr is not None
        and recent_range <= current_atr * 2.5
        and volume_ratio >= 1.15
    )

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


# =========================================================
# TARGETS 1-20
# =========================================================

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
        target_price = price + current_atr * 0.5 * number

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
        SELECT target_no,target_price FROM targets
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


# =========================================================
# SIGNAL ENGINE
# =========================================================

def signal_events(market, symbol, tf, result):
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

    for period, value in result["ema"].items():
        if value is None:
            continue

        was_above = old_ema.get(str(period))
        is_above = price >= value

        if was_above is not None and was_above != is_above:
            if is_above:
                events.append(f"اختراق EMA{period} للأعلى")
            else:
                events.append(f"كسر EMA{period} للأسفل")

    if current_rsi is not None:
        old_rsi = old.get("rsi")

        if old_rsi is not None:
            for zone in (20, 40, 50, 60, 70, 80, 100):
                if old_rsi < zone <= current_rsi:
                    events.append(f"RSI اخترق {zone} للأعلى")
                elif old_rsi > zone >= current_rsi:
                    events.append(f"RSI كسر {zone} للأسفل")

    if (
        result["volume_ratio"] >= 1.5
        and old.get("volume_ratio", 0) < 1.5
    ):
        events.append("ارتفاع نشاط الفوليوم")

    if result["accumulation"] and not old.get("accumulation", False):
        events.append("احتمال تجميع سعري")

    if (
        result["vwap"]
        and old.get("price", price) < result["vwap"] <= price
    ):
        events.append("اختراق VWAP للأعلى")

    elif (
        result["vwap"]
        and old.get("price", price) > result["vwap"] >= price
    ):
        events.append("كسر VWAP للأسفل")

    # Breakout confirmation against the previous candles only.
    # This avoids comparing the price to a resistance containing itself.
    # The current candle is excluded from the previous-range calculation.

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


# =========================================================
# SEND DASHBOARD
# =========================================================

async def send_dashboard(session, market, item, tf, result, events, hits):
    token, chat = bot_details(market)

    if not token or not chat:
        log.error("%s: Telegram credentials missing", market)
        return False

    try:
        photo = create_dashboard(
            market, item, tf, result, events, hits
        )

        caption = (
            f"AI PRO MAX V12 | {market}\n"
            f"{item['symbol']} | {tf}\n"
            f"السعر: {result['price']:.6f}\n"
            f"التغير: {result['change']:+.2f}%"
        )

        return await telegram_photo(
            session, token, chat, photo, caption
        )

    except Exception as exc:
        log.exception("Dashboard error: %s", exc)

        # Fallback text notification if image creation fails.
        return await telegram_text(
            session, token, chat,
            f"AI PRO MAX | {market}\n"
            f"{item['symbol']} | {tf}\n"
            f"السعر: {result['price']:.6f}\n"
            f"التغير: {result['change']:+.2f}%"
        )


# =========================================================
# SCAN ONE SYMBOL
# =========================================================

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
                market, symbol, tf, result
            )

            if events or hits:
                messages.append((
                    item, tf, result, events, hits
                ))

        except Exception as exc:
            log.exception(
                "Scan error %s %s %s: %s",
                market, symbol, tf, exc
            )

    return messages


# =========================================================
# MARKET PROCESSING
# =========================================================

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
            log.error("Batch error: %s", result)

    set_cursor(
        market,
        0 if end >= len(symbols) else end
    )

    sent = 0

    for item, tf, result, events, hits in reports:
        success = await send_dashboard(
            session, market, item, tf, result, events, hits
        )

        if success:
            sent += 1

        # Avoid Telegram flood.
        await asyncio.sleep(0.4)

    log.info(
        "%s scanned %s/%s | reports=%s | sent=%s",
        market, end, len(symbols), len(reports), sent
    )


# =========================================================
# MAIN LOOP 24/7
# =========================================================

async def main():
    db()

    connector = aiohttp.TCPConnector(
        limit=WORKERS + 10,
        ttl_dns_cache=300
    )

    timeout = aiohttp.ClientTimeout(total=45)

    async with aiohttp.ClientSession(
        connector=connector,
        timeout=timeout
    ) as session:

        # Welcome messages
        for market in ("US", "TASI", "CRYPTO"):
            token, chat = bot_details(market)

            await telegram_text(
                session,
                token,
                chat,
                f"AI PRO MAX V12 ULTRA HD\n"
                f"تم تشغيل بوت {market}\n"
                f"نظام الفحص 24/7 يعمل\n"
                f"دورة الفحص: {SCAN_SECONDS} ثانية\n"
                f"لوحات التداول: صور عالية الدقة\n"
                f"الأهداف: 1 إلى 20\n"
                f"قاعدة البيانات: مفعلة"
            )

        universes = {
            "US": [],
            "TASI": [],
            "CRYPTO": []
        }

        last_refresh = 0

        while True:
            try:
                if time.time() - last_refresh >= 21600:
                    log.info("Refreshing market symbols")

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
                        token, chat = bot_details(market)

                        await telegram_text(
                            session,
                            token,
                            chat,
                            f"تحديث قائمة {market}\n"
                            f"عدد الرموز: {len(symbols):,}\n"
                            f"الفحص المستمر فعال"
                        )

                # Independent market scans
                for market in ("US", "TASI", "CRYPTO"):
                    await process_market(
                        session,
                        market,
                        universes[market]
                    )

                log.info(
                    "Next scan in %s seconds",
                    SCAN_SECONDS
                )

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
