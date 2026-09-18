# AI PRO MAX — REBUILT FROM ZERO
# Original scanner design for Railway.
# Markets:
#   🇸🇦 TASI  -> SAHMK universe + Twelve Data technical history
#   🇺🇸 US    -> Twelve Data US stock universe, price floor $0.15, no symbol cap
#   🪙 Crypto -> Twelve Data full crypto universe, no symbol cap
#
# Secrets are read ONLY from Railway environment variables.

import os
import time
import json
import queue
import random
import threading
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, local

import requests

# ============================================================
# CONFIG
# ============================================================

CHAT_ID = os.getenv("CHAT_ID", "").strip()
TASI_TOKEN = os.getenv("TASI_TOKEN", "").strip()
US_TOKEN = os.getenv("US_TOKEN", "").strip()
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN", "").strip()
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "").strip()
SAHMK_API_KEY = os.getenv("SAHMK_API_KEY", "").strip()

TD_BASE = "https://api.twelvedata.com"
SAHMK_BASE = "https://api.sahmk.sa/api/v1"

# No numeric cap on any universe.
MIN_US_PRICE = 0.15
TASI_EXPECTED = 374
US_EXPECTED = 13414

WORKERS = 4
SCAN_SECONDS = 120
REQUEST_TIMEOUT = (8, 25)
RETRIES = 3

# Fast scan first. Deeper timeframes are only requested for candidates.
SIGNAL_TF = "15min"
CONFIRM_TFS = ("30min", "1h", "4h")
BARS = 180

# Telegram queue
TG_QUEUE = queue.Queue(maxsize=5000)

# Locks / sessions
td_local = local()
sa_local = local()
td_lock = Lock()
sa_lock = Lock()
td_last = [0.0]
sa_last = [0.0]

# State
state_lock = Lock()
last_alert = {}
trend_state = {}
catalog_cache = {
    "TASI": {"symbols": [], "at": 0},
    "US": {"symbols": [], "at": 0},
    "CRYPTO": {"symbols": [], "at": 0},
}

# ============================================================
# HTTP
# ============================================================

def session_for(holder):
    s = getattr(holder, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update({
            "User-Agent": "AI-PRO-MAX/1.0",
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
        })
        holder.session = s
    return s


def rate_limit(lock, last, gap):
    with lock:
        now = time.monotonic()
        wait = gap - (now - last[0])
        if wait > 0:
            time.sleep(wait)
        last[0] = time.monotonic()


def get_json(base, path, params, key, holder, lock, last, gap):
    if not key:
        return None

    s = session_for(holder)
    p = dict(params or {})
    headers = {}

    if base == TD_BASE:
        p["apikey"] = key
    else:
        headers["X-API-Key"] = key

    for attempt in range(RETRIES):
        try:
            rate_limit(lock, last, gap)
            r = s.get(
                base + path,
                params=p,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )

            if r.status_code == 429:
                retry_after = r.headers.get("Retry-After")
                try:
                    delay = float(retry_after)
                except Exception:
                    delay = min(20, 2 ** attempt)
                time.sleep(delay)
                continue

            if r.status_code in (500, 502, 503, 504):
                time.sleep(min(15, 2 ** attempt))
                continue

            if r.status_code != 200:
                return None

            data = r.json()

            if isinstance(data, dict):
                status = str(data.get("status", "")).lower()
                if status == "error":
                    return None
                if data.get("error"):
                    return None

            return data

        except (requests.Timeout, requests.ConnectionError):
            if attempt < RETRIES - 1:
                time.sleep(min(10, 2 ** attempt))
            else:
                return None
        except Exception:
            return None

    return None


def td(path, params=None):
    return get_json(
        TD_BASE, path, params, TWELVEDATA_API_KEY,
        td_local, td_lock, td_last, 0.35
    )


def sahmk(path, params=None):
    return get_json(
        SAHMK_BASE, path, params, SAHMK_API_KEY,
        sa_local, sa_lock, sa_last, 0.60
    )


# ============================================================
# DATA NORMALIZATION
# ============================================================

def rows_from_catalog(data):
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []

    for key in ("data", "stocks", "companies", "result", "results"):
        value = data.get(key)
        if isinstance(value, list):
            return value

    return []


def candles(data):
    if not isinstance(data, dict):
        return None

    values = data.get("values")
    if not isinstance(values, list) or len(values) < 40:
        return None

    out = []
    for row in reversed(values):
        try:
            o = float(row["open"])
            h = float(row["high"])
            l = float(row["low"])
            c = float(row["close"])
            v = float(row.get("volume", 0) or 0)
            out.append((o, h, l, c, v))
        except Exception:
            continue

    return out if len(out) >= 40 else None


def last_price(data):
    if not isinstance(data, dict):
        return None

    for key in ("price", "close", "last", "value"):
        try:
            x = float(data.get(key))
            if x > 0:
                return x
        except Exception:
            pass

    values = data.get("values")
    if isinstance(values, list) and values:
        try:
            return float(values[0]["close"])
        except Exception:
            pass

    return None


# ============================================================
# CATALOGS
# ============================================================

def load_tasi():
    # Never let the Saudi directory block the whole bot.
    # SAHMK is primary; Twelve Data XSAU is an independent fallback.
    print("[TASI] loading catalog...")
    data = sahmk("/companies/", {"market": "TASI", "limit": 2000, "offset": 0})
    rows = rows_from_catalog(data)

    found = []
    seen = set()

    for row in rows:
        if not isinstance(row, dict):
            continue

        symbol = str(
            row.get("symbol")
            or row.get("ticker")
            or row.get("code")
            or ""
        ).strip().upper()

        if not symbol:
            continue

        # Keep Saudi listed symbols; do not impose a numeric cap.
        if symbol not in seen:
            seen.add(symbol)
            found.append(symbol)

    random.shuffle(found)

    catalog_cache["TASI"] = {"symbols": found, "at": time.time()}

    print(f"[TASI] catalog={len(found)} | expected current universe≈{TASI_EXPECTED} | no numeric cap")
    if not found:
        print("[TASI] SAHMK catalog unavailable -> trying Twelve Data XSAU fallback...")
        fallback = td("/stocks", {"exchange": "XSAU"})
        frows = rows_from_catalog(fallback)
        for row in frows:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").strip().upper()
            if symbol and symbol not in seen:
                seen.add(symbol)
                found.append(symbol)
        random.shuffle(found)
        catalog_cache["TASI"] = {"symbols": found, "at": time.time()}

    if len(found) != TASI_EXPECTED:
        print(f"[TASI] WARNING: provider returned {len(found)} symbols; code did NOT truncate or invent symbols.")

    return found


def load_us():
    # US universe: stocks endpoint only. No ETF merge and no numeric cap.
    print("[US] loading full stock catalog...")
    all_rows = []

    # Primary: provider's US country catalog, paged.
    for page in range(1, 101):
        data = td("/stocks", {"country": "United States", "page": page, "outputsize": 5000})
        rows = rows_from_catalog(data)
        if not rows:
            break
        all_rows.extend(rows)
        print(f"[US] page {page}: +{len(rows)}")
        if len(rows) < 5000:
            break

    # Fallback: exchange-level stock catalog if country filtering failed.
    if not all_rows:
        print("[US] country catalog unavailable -> trying exchange fallbacks...")
        for exchange in ("NASDAQ", "NYSE", "AMEX", "ARCA", "OTC"):
            data = td("/stocks", {"exchange": exchange, "outputsize": 5000})
            rows = rows_from_catalog(data)
            if rows:
                all_rows.extend(rows)
                print(f"[US] {exchange}: +{len(rows)}")

    symbols = []
    seen = set()
    for row in all_rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        country = str(row.get("country") or "").strip().lower()
        exchange = str(row.get("exchange") or "").strip().upper()
        if country and country not in ("united states", "us", "usa", "united states of america"):
            if exchange not in {"NASDAQ", "NYSE", "AMEX", "ARCA", "OTC", "BATS", "CBOE"}:
                continue
        seen.add(symbol)
        symbols.append(symbol)

    random.shuffle(symbols)
    catalog_cache["US"] = {"symbols": symbols, "at": time.time()}
    print(f"[US] catalog={len(symbols)} | price >= ${MIN_US_PRICE:.2f} | NO NUMERIC CAP")
    if len(symbols) != US_EXPECTED:
        print(f"[US] NOTE: provider returned {len(symbols)} symbols; nothing was truncated.")
    return symbols

def load_crypto():
    data = td("/cryptocurrencies", {})
    rows = rows_from_catalog(data)

    symbols = []
    seen = set()

    for row in rows:
        if not isinstance(row, dict):
            continue

        # Preserve the provider's native pair. Do NOT force USD.
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol or symbol in seen:
            continue

        seen.add(symbol)
        symbols.append(symbol)

    random.shuffle(symbols)

    catalog_cache["CRYPTO"] = {"symbols": symbols, "at": time.time()}

    print(f"[CRYPTO] catalog={len(symbols)} | FULL OPEN | no USD-only filter | no numeric cap")
    return symbols


# ============================================================
# TECHNICAL INDICATORS
# ============================================================

def ema(values, n):
    if len(values) < n:
        return None
    x = sum(values[:n]) / n
    a = 2.0 / (n + 1)
    for v in values[n:]:
        x = x + a * (v - x)
    return x


def rsi(values, n=14):
    if len(values) < n + 1:
        return None

    gains = []
    losses = []

    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))

    ag = sum(gains[:n]) / n
    al = sum(losses[:n]) / n

    for i in range(n, len(gains)):
        ag = ((ag * (n - 1)) + gains[i]) / n
        al = ((al * (n - 1)) + losses[i]) / n

    if al == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + ag / al))


def atr(high, low, close, n=14):
    if len(close) < n + 1:
        return None

    tr = []
    for i in range(1, len(close)):
        tr.append(max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        ))

    x = sum(tr[:n]) / n
    for v in tr[n:]:
        x = ((x * (n - 1)) + v) / n
    return x


def vwap(high, low, close, volume):
    pv = 0.0
    vv = 0.0

    for h, l, c, v in zip(high, low, close, volume):
        if v > 0:
            pv += ((h + l + c) / 3.0) * v
            vv += v

    return pv / vv if vv else None


def volume_ratio(volume):
    if len(volume) < 21:
        return 1.0
    base = sum(volume[-21:-1]) / 20.0
    return volume[-1] / base if base > 0 else 1.0


def support_resistance(close, window=30):
    w = close[-window:] if len(close) >= window else close
    if not w:
        return None, None
    return min(w), max(w)


def golden_candle(o, h, l, c, v, vr):
    rng = h - l
    if rng <= 0:
        return False
    body = abs(c - o)
    return c > o and body / rng >= 0.65 and vr >= 1.5


def hidden_divergence(close, rsi_values):
    # Bullish hidden divergence:
    # price makes a higher low while RSI makes a lower low.
    if len(close) < 8 or len(rsi_values) < 8:
        return None

    p1 = min(close[-8:-4])
    p2 = min(close[-4:])
    r1 = min(rsi_values[-8:-4])
    r2 = min(rsi_values[-4:])

    if p2 > p1 and r2 < r1:
        return "BULLISH"

    # Bearish hidden divergence:
    # price makes a lower high while RSI makes a higher high.
    p1 = max(close[-8:-4])
    p2 = max(close[-4:])
    r1 = max(rsi_values[-8:-4])
    r2 = max(rsi_values[-4:])

    if p2 < p1 and r2 > r1:
        return "BEARISH"

    return None


def score_signal(o, h, l, c, v):
    closes = c
    r = rsi(closes, 14)
    a = atr(h, l, closes, 14)
    vw = vwap(h, l, closes, v)
    vr = volume_ratio(v)

    e10 = ema(closes, 10)
    e14 = ema(closes, 14)
    e15 = ema(closes, 15)
    e25 = ema(closes, 25)
    e50 = ema(closes, 50)

    if None in (r, a, vw, e10, e14, e15, e25, e50):
        return None

    # Build an RSI history for divergence.
    rsih = []
    for i in range(max(0, len(closes) - 40), len(closes)):
        x = rsi(closes[:i + 1], 14)
        if x is not None:
            rsih.append(x)

    div = hidden_divergence(closes, rsih)
    golden = golden_candle(o[-1], h[-1], l[-1], c[-1], v[-1], vr)

    points = 0
    reasons = []

    if c[-1] > vw:
        points += 15
        reasons.append("فوق VWAP")

    if e10 > e14 > e15 > e25 > e50:
        points += 20
        reasons.append("ترتيب EMA صاعد")
    elif e10 < e14 < e15 < e25 < e50:
        points += 20
        reasons.append("ترتيب EMA هابط")

    if 50 <= r < 70:
        points += 15
        reasons.append("RSI إيجابي")
    elif r >= 70:
        points += 10
        reasons.append("RSI قوي")
    elif r <= 30:
        points += 10
        reasons.append("RSI منخفض")

    if vr >= 2:
        points += 20
        reasons.append("حجم غير اعتيادي")
    elif vr >= 1.5:
        points += 10
        reasons.append("ارتفاع الحجم")

    if golden:
        points += 15
        reasons.append("Golden Candle")

    if div == "BULLISH":
        points += 10
        reasons.append("Hidden Bullish Divergence")
    elif div == "BEARISH":
        points += 10
        reasons.append("Hidden Bearish Divergence")

    trend = "UP" if c[-1] >= e50 else "DOWN"

    # Persist direction until the technical state reverses.
    key = None
    return {
        "price": c[-1],
        "rsi": r,
        "atr": a,
        "vwap": vw,
        "vr": vr,
        "ema10": e10,
        "ema14": e14,
        "ema15": e15,
        "ema25": e25,
        "ema50": e50,
        "support": support_resistance(c)[0],
        "resistance": support_resistance(c)[1],
        "golden": golden,
        "divergence": div,
        "score": min(100, int(points)),
        "trend": trend,
        "reasons": reasons,
    }


def targets(price, atr_value, direction):
    if not atr_value or atr_value <= 0:
        return []

    multipliers = (1, 1.5, 2, 2.5, 3, 3.5, 4, 5)

    if direction == "BUY":
        return [price + atr_value * x for x in multipliers]
    return [price - atr_value * x for x in multipliers]


# ============================================================
# DATA FETCH
# ============================================================

def history(symbol, interval):
    data = td("/time_series", {
        "symbol": symbol,
        "interval": interval,
        "outputsize": BARS,
        "format": "JSON",
    })
    return candles(data)


def current_price(symbol):
    data = td("/price", {"symbol": symbol})
    p = last_price(data)
    if p is not None:
        return p

    # Fallback to one recent bar.
    data = td("/time_series", {
        "symbol": symbol,
        "interval": SIGNAL_TF,
        "outputsize": 2,
        "format": "JSON",
    })
    return last_price(data)


# ============================================================
# NEWS — lightweight, only when a US signal is generated
# ============================================================

POSITIVE = {
    "beat", "growth", "profit", "profits", "upgrade", "upgraded",
    "buy", "strong", "positive", "partnership", "contract",
    "approval", "revenue", "surge", "record", "raises"
}

NEGATIVE = {
    "loss", "losses", "downgrade", "downgraded", "sell", "weak",
    "negative", "lawsuit", "decline", "drop", "warning", "debt",
    "offering", "investigation", "risk", "cuts", "cut"
}


def news_for(symbol):
    data = td("/news", {"symbol": symbol, "limit": 5})
    rows = rows_from_catalog(data)

    if not rows:
        return "لا توجد أخبار متاحة"

    pos = neg = 0
    title = ""

    for row in rows:
        if not isinstance(row, dict):
            continue
        t = str(row.get("title") or row.get("headline") or "")
        low = t.lower()
        pos += sum(1 for x in POSITIVE if x in low)
        neg += sum(1 for x in NEGATIVE if x in low)
        if not title and t:
            title = t

    if pos > neg:
        sentiment = "🟢 إيجابي"
    elif neg > pos:
        sentiment = "🔴 سلبي"
    else:
        sentiment = "⚪ محايد"

    return f"{sentiment} | {title[:160]}" if title else sentiment


# ============================================================
# FLOW PROXIES
# ============================================================

def flow_flags(o, h, l, c, v):
    vr = volume_ratio(v)
    rng = h[-1] - l[-1]
    body = abs(c[-1] - o[-1])
    body_ratio = body / rng if rng > 0 else 0

    out = []

    if len(c) >= 21:
        prev_high = max(c[-21:-1])
        prev_low = min(c[-21:-1])

        if c[-1] > prev_high:
            out.append("📈 اختراق")
        elif c[-1] < prev_low:
            out.append("📉 كسر")

    if vr >= 2:
        out.append("🔎 حركة غير اعتيادية")

    if vr >= 1.5 and c[-1] > o[-1]:
        out.append("💰 تجميع محتمل")

    if vr >= 2.5 and abs(c[-1] / c[-2] - 1) >= 0.01:
        out.append("⚡ حركة مضاربين محتملة")

    if vr >= 3 and body_ratio >= 0.65:
        out.append("🐋 حركة كبيرة — مؤشر فني")

    if vr >= 2 and c[-1] > ema(c, 20):
        out.append("🏦 تدفق مؤسسي محتمل — مؤشر فني")

    return out


# ============================================================
# ANALYSIS
# ============================================================

def analyze(symbol, market):
    # TASI uses SAHMK for the latest quote when available.
    # Technical history remains Twelve Data.
    bars = history(symbol, SIGNAL_TF)
    if not bars:
        return None

    o, h, l, c, v = map(list, zip(*bars))

    if market == "US":
        if c[-1] < MIN_US_PRICE:
            return None

    metrics = score_signal(o, h, l, c, v)
    if not metrics:
        return None

    # Direction is based on the current technical state.
    if metrics["trend"] == "UP" and metrics["rsi"] >= 50:
        signal = "BUY"
    elif metrics["trend"] == "DOWN" and metrics["rsi"] <= 50:
        signal = "SELL"
    else:
        signal = "WATCH"

    # Only send actionable signals.
    if metrics["score"] < 60 or signal == "WATCH":
        return None

    # Confirm the direction on deeper timeframes for stronger signals.
    confirmations = []
    for tf in CONFIRM_TFS:
        b = history(symbol, tf)
        if not b:
            continue
        cc = [x[3] for x in b]
        e = ema(cc, 50)
        if e is None:
            continue
        confirmations.append(
            "UP" if cc[-1] >= e else "DOWN"
        )

    if confirmations:
        same = sum(1 for x in confirmations if x == metrics["trend"])
        if same == 0:
            return None
        metrics["score"] = min(100, metrics["score"] + min(15, same * 5))

    flow = flow_flags(o, h, l, c, v)
    t = targets(metrics["price"], metrics["atr"], signal)

    news = news_for(symbol) if market == "US" else None

    return {
        "symbol": symbol,
        "market": market,
        "signal": signal,
        "score": metrics["score"],
        "trend": metrics["trend"],
        "price": metrics["price"],
        "rsi": metrics["rsi"],
        "vwap": metrics["vwap"],
        "atr": metrics["atr"],
        "ema10": metrics["ema10"],
        "ema14": metrics["ema14"],
        "ema15": metrics["ema15"],
        "ema25": metrics["ema25"],
        "ema50": metrics["ema50"],
        "support": metrics["support"],
        "resistance": metrics["resistance"],
        "golden": metrics["golden"],
        "divergence": metrics["divergence"],
        "reasons": metrics["reasons"],
        "flow": flow,
        "targets": t,
        "news": news,
    }


# ============================================================
# TELEGRAM
# ============================================================

def tg_send(token, text_message):
    if not token or not CHAT_ID:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": text_message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=(8, 20),
        )
        return r.status_code == 200
    except Exception:
        return False


def token_for(market):
    return {
        "TASI": TASI_TOKEN,
        "US": US_TOKEN,
        "CRYPTO": CRYPTO_TOKEN,
    }.get(market, "")


def fmt(x):
    if x is None:
        return "-"
    if abs(x) >= 1000:
        return f"{x:,.2f}"
    if abs(x) >= 1:
        return f"{x:.4f}"
    return f"{x:.6f}"


def message(r):
    market_name = {
        "TASI": "🇸🇦 <b>تاسي</b>",
        "US": "🇺🇸 <b>السوق الأمريكي</b>",
        "CRYPTO": "🪙 <b>العملات الرقمية</b>",
    }[r["market"]]

    targets_text = "\n".join(
        f"🎯 TP{i}: {fmt(x)}"
        for i, x in enumerate(r["targets"], 1)
    )

    flow_text = "\n".join(r["flow"]) if r["flow"] else "—"

    return (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💀🚀 <b>AI PRO MAX</b>\n"
        f"{market_name}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔹 <b>{r['symbol']}</b>\n"
        f"📣 الإشارة: <b>{r['signal']}</b> | القوة: <b>{r['score']}/100</b>\n"
        f"💵 السعر: <b>{fmt(r['price'])}</b>\n"
        f"📈 الاتجاه: <b>{r['trend']}</b>\n"
        f"📊 RSI(14): {r['rsi']:.2f}\n"
        f"VWAP: {fmt(r['vwap'])}\n"
        f"ATR(14): {fmt(r['atr'])}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"EMA10: {fmt(r['ema10'])}\n"
        f"EMA14: {fmt(r['ema14'])}\n"
        f"EMA15: {fmt(r['ema15'])}\n"
        f"EMA25: {fmt(r['ema25'])}\n"
        f"EMA50: {fmt(r['ema50'])}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🛡 الدعم: {fmt(r['support'])}\n"
        f"🚧 المقاومة: {fmt(r['resistance'])}\n"
        f"🕯 Golden Candle: {'نعم' if r['golden'] else 'لا'}\n"
        f"🔀 Hidden Divergence: {r['divergence'] or 'لا يوجد'}\n"
        f"🧠 ARS: {r['score']}/100\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔍 <b>رصد الحركة</b>\n"
        f"{flow_text}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{targets_text}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        + (f"📰 الخبر: {r['news']}\n" if r["news"] else "")
        + f"🕒 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
        "⚠️ <i>إشارة فنية آلية وليست توصية مالية.</i>\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )


def enqueue_alert(r):
    market = r["market"]
    symbol = r["symbol"]
    key = (market, symbol)

    with state_lock:
        previous = last_alert.get(key)
        current = (r["signal"], r["trend"])

        # Prevent repeated identical alerts.
        if previous == current:
            return

        last_alert[key] = current

    try:
        TG_QUEUE.put_nowait(r)
    except queue.Full:
        pass


def telegram_worker():
    while True:
        r = TG_QUEUE.get()
        try:
            tg_send(token_for(r["market"]), message(r))
        finally:
            TG_QUEUE.task_done()


# ============================================================
# SCANNING
# ============================================================

def scan_market(market, symbols):
    total = len(symbols)
    signals = 0

    print(
        f"[{market}] START FULL SCAN | {total} symbols | "
        f"Workers={WORKERS} | no numeric cap"
    )

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {
            pool.submit(analyze, symbol, market): symbol
            for symbol in symbols
        }

        done = 0
        for future in as_completed(futures):
            done += 1
            try:
                result = future.result()
            except Exception:
                result = None

            if result:
                signals += 1
                enqueue_alert(result)
                print(
                    f"[{market}] 📲 {result['symbol']} "
                    f"{result['signal']} {result['score']}/100"
                )

            if done % 250 == 0 or done == total:
                print(
                    f"[{market}] {done}/{total} | signals={signals}"
                )

    print(f"[{market}] FINISHED | {total} | signals={signals}")


def ensure_catalogs():
    # Load the three universes in parallel so one slow provider cannot
    # prevent the other markets from starting.
    now = time.time()
    jobs = []

    if not catalog_cache["TASI"]["symbols"] or now - catalog_cache["TASI"]["at"] > 21600:
        jobs.append(("TASI", load_tasi))
    if not catalog_cache["US"]["symbols"] or now - catalog_cache["US"]["at"] > 21600:
        jobs.append(("US", load_us))
    if not catalog_cache["CRYPTO"]["symbols"] or now - catalog_cache["CRYPTO"]["at"] > 21600:
        jobs.append(("CRYPTO", load_crypto))

    if not jobs:
        return

    print(f"[CATALOG] starting {len(jobs)} market catalogs in parallel...")
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {pool.submit(fn): name for name, fn in jobs}
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                print(f"[CATALOG] {name} ready: {len(result or [])} symbols")
            except Exception as exc:
                print(f"[CATALOG] {name} failed safely: {exc}")


def market_loop():
    print("=" * 70)
    print("💀🚀 AI PRO MAX — REBUILT FROM ZERO")
    print("🇸🇦 TASI  | 🇺🇸 US  | 🪙 CRYPTO")
    print("=" * 70)
    print("🟢 Environment:", "OK" if CHAT_ID else "CHECK CHAT_ID")
    print(f"🇸🇦 TASI target reference: {TASI_EXPECTED} | NO CAP")
    print(f"🇺🇸 US target reference: {US_EXPECTED} | price >= ${MIN_US_PRICE:.2f} | NO CAP")
    print("🪙 CRYPTO: FULL OPEN | NO CAP | NO USD-ONLY FILTER")
    print("💀🚀 يعمل 24/7")

    while True:
        started = time.time()

        try:
            ensure_catalogs()

            # Full universes. No slicing / [:N] anywhere.
            markets = (
                ("TASI", list(catalog_cache["TASI"]["symbols"])),
                ("US", list(catalog_cache["US"]["symbols"])),
                ("CRYPTO", list(catalog_cache["CRYPTO"]["symbols"])),
            )
            print(
                f"[CATALOG] READY | TASI={len(markets[0][1])} | "
                f"US={len(markets[1][1])} | CRYPTO={len(markets[2][1])}"
            )

            # Randomize every cycle so the same symbols do not always wait
            # behind the same earlier symbols.
            for market, symbols in markets:
                random.shuffle(symbols)
                scan_market(market, symbols)

        except Exception as exc:
            print(f"[LOOP] error: {exc}")

        elapsed = time.time() - started
        sleep_for = max(5, SCAN_SECONDS - elapsed)
        print(f"[LOOP] cycle={elapsed:.1f}s | next cycle in ~{sleep_for:.1f}s")
        time.sleep(sleep_for)


def validate_environment():
    required = {
        "CHAT_ID": CHAT_ID,
        "TASI_TOKEN": TASI_TOKEN,
        "US_TOKEN": US_TOKEN,
        "CRYPTO_TOKEN": CRYPTO_TOKEN,
        "TWELVEDATA_API_KEY": TWELVEDATA_API_KEY,
        "SAHMK_API_KEY": SAHMK_API_KEY,
    }

    missing = [k for k, v in required.items() if not v]

    if missing:
        print("[ENV] Missing:", ", ".join(missing))
        return False

    print("[ENV] OK — all required variables are present")
    return True


if __name__ == "__main__":
    if not validate_environment():
        raise SystemExit(1)

    threading.Thread(target=telegram_worker, daemon=True).start()
    market_loop()