# ============================================================
# AI PRO MAX — QUOTA SAFE / STANDARD LIBRARY EDITION
# ============================================================
# Designed from scratch for the user's Railway project.
# No third-party Python package is required.
#
# Existing Railway variables used:
# TWELVE_DATA_API_KEY
# TASI_TOKEN
# US_TOKEN
# CRYPTO_TOKEN
# PORT
#
# Optional existing variables are accepted if already present:
# MIN_US_PRICE, SIGNAL_COOLDOWN, SCAN_SECONDS
#
# Main goals:
# - Never hammer an exhausted API with repeated 429 requests.
# - Cache symbol catalog locally.
# - Cache historical data for long periods.
# - Request current quotes only when a symbol is due.
# - Never start overlapping scan cycles.
# - Send Telegram signals only when a new signal appears.
# - Keep running 24/7 without crashing when a provider is unavailable.
#
# Important provider reality:
# No program can bypass a provider's quota. "Full market" scanning
# means scanning every symbol available from the provider, but the
# frequency is automatically paced so the API quota is protected.
# ============================================================

import os
import json
import time
import math
import random
import threading
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

# -----------------------------
# Configuration
# -----------------------------
TWELVE_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()

TASI_TOKEN = os.getenv("TASI_TOKEN", "").strip()
US_TOKEN = os.getenv("US_TOKEN", "").strip()
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN", "").strip()

PORT = int(os.getenv("PORT", "8080"))
MIN_US_PRICE = float(os.getenv("MIN_US_PRICE", "0.15"))
SIGNAL_COOLDOWN = int(os.getenv("SIGNAL_COOLDOWN", "1800"))

# These are safety defaults, not market-size caps.
# The scanner calculates its own pacing from the provider budget.
SCAN_SECONDS = int(os.getenv("SCAN_SECONDS", "300"))

DATA_DIR = Path(os.getenv("DATA_DIR", "/tmp/ai_pro_max"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

CATALOG_FILE = DATA_DIR / "symbols.json"
STATE_FILE = DATA_DIR / "state.json"

# Refresh catalog rarely. Repeated catalog calls are wasteful.
CATALOG_TTL = 24 * 60 * 60

# History is expensive, so keep it for 12 hours.
HISTORY_TTL = 12 * 60 * 60

# Do not hammer the provider after 429/limit responses.
BACKOFF_MIN = 60
BACKOFF_MAX = 6 * 60 * 60

# In-memory caches
symbols = {"TASI": [], "US": [], "CRYPTO": []}
symbol_index = {"TASI": 0, "US": 0, "CRYPTO": 0}

history_cache = {}
quote_cache = {}
last_signal = {}
telegram_chats = {"TASI": set(), "US": set(), "CRYPTO": set()}

provider_block_until = 0.0
provider_backoff = BACKOFF_MIN
state_lock = threading.Lock()


# ============================================================
# Logging
# ============================================================

def log(msg):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"{stamp} UTC | {msg}", flush=True)


# ============================================================
# Persistent state
# ============================================================

def load_json(path, default):
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as exc:
        log(f"state read warning: {exc}")
    return default


def save_json(path, value):
    tmp = path.with_suffix(".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False)
        tmp.replace(path)
    except Exception as exc:
        log(f"state write warning: {exc}")


def load_state():
    global symbols
    data = load_json(STATE_FILE, {})
    saved_symbols = data.get("symbols", {})
    if isinstance(saved_symbols, dict):
        for market in symbols:
            rows = saved_symbols.get(market, [])
            if isinstance(rows, list):
                symbols[market] = rows

    saved_last = data.get("last_signal", {})
    if isinstance(saved_last, dict):
        last_signal.update(saved_last)


def save_state():
    with state_lock:
        save_json(
            STATE_FILE,
            {
                "symbols": symbols,
                "last_signal": last_signal,
            },
        )


# ============================================================
# HTTP — standard library only
# ============================================================

def api_get(endpoint, params=None, timeout=20):
    """
    Single HTTP function.
    It deliberately stops making requests when a provider quota/rate
    limit is detected, preventing a tight 429 loop.
    """
    global provider_block_until, provider_backoff

    if not TWELVE_KEY:
        raise RuntimeError("TWELVE_DATA_API_KEY غير موجود")

    now = time.time()
    if now < provider_block_until:
        return None

    query = dict(params or {})
    query["apikey"] = TWELVE_KEY

    url = "https://api.twelvedata.com/" + endpoint.lstrip("/")
    full_url = url + "?" + urllib.parse.urlencode(query)

    request = urllib.request.Request(
        full_url,
        headers={"User-Agent": "AI-PRO-MAX/1.0"},
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            data = json.loads(raw)

        if isinstance(data, dict) and data.get("status") == "error":
            message = str(data.get("message", "unknown error"))
            lower = message.lower()

            if (
                "429" in lower
                or "rate" in lower
                or "limit" in lower
                or "quota" in lower
                or "credits" in lower
            ):
                provider_block_until = time.time() + provider_backoff
                provider_backoff = min(
                    BACKOFF_MAX,
                    max(BACKOFF_MIN, provider_backoff * 2),
                )
                log(
                    f"⛔ API limit detected — pause "
                    f"{int(provider_block_until-time.time())}s"
                )
                return None

            raise RuntimeError(message)

        provider_backoff = BACKOFF_MIN
        return data

    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass

        text = f"HTTP {exc.code} {body[:300]}"
        if exc.code in (429, 402, 403):
            provider_block_until = time.time() + provider_backoff
            provider_backoff = min(
                BACKOFF_MAX,
                max(BACKOFF_MIN, provider_backoff * 2),
            )
            log(
                f"⛔ {text} | API paused "
                f"{int(provider_block_until-time.time())}s"
            )
            return None

        raise RuntimeError(text)

    except Exception as exc:
        raise RuntimeError(str(exc))


# ============================================================
# Catalog
# ============================================================

def rows_from(data):
    if not isinstance(data, dict):
        return []
    for key in ("data", "values"):
        rows = data.get(key)
        if isinstance(rows, list):
            return rows
    return []


def catalog_is_fresh():
    try:
        return (
            CATALOG_FILE.exists()
            and time.time() - CATALOG_FILE.stat().st_mtime < CATALOG_TTL
        )
    except Exception:
        return False


def load_catalog_file():
    data = load_json(CATALOG_FILE, {})
    if not isinstance(data, dict):
        return
    for market in symbols:
        rows = data.get(market)
        if isinstance(rows, list):
            symbols[market] = rows


def save_catalog_file():
    save_json(CATALOG_FILE, symbols)


def fetch_catalog(market):
    if market == "CRYPTO":
        data = api_get(
            "cryptocurrencies",
            {"page": 1},
        )
    elif market == "US":
        data = api_get(
            "stocks",
            {
                "country": "United States",
                "type": "Common Stock",
                "page": 1,
            },
        )
    else:
        data = api_get(
            "stocks",
            {
                "exchange": "Saudi Exchange",
                "page": 1,
            },
        )

    if data is None:
        return []

    rows = rows_from(data)
    out = []
    seen = set()

    for item in rows:
        if not isinstance(item, dict):
            continue

        sym = str(item.get("symbol", "")).strip()
        if not sym or sym in seen:
            continue

        seen.add(sym)

        exchange = str(item.get("exchange", "")).strip()
        name = str(
            item.get("name")
            or item.get("currency_base")
            or sym
        ).strip()

        out.append(
            {
                "symbol": sym,
                "name": name,
                "exchange": exchange,
            }
        )

    return out


def ensure_catalog():
    load_catalog_file()

    if catalog_is_fresh() and all(symbols[m] for m in symbols):
        log(
            "📚 catalog cache loaded: "
            + ", ".join(f"{m}={len(symbols[m])}" for m in symbols)
        )
        return

    for market in ("TASI", "US", "CRYPTO"):
        if time.time() < provider_block_until:
            break

        try:
            fresh = fetch_catalog(market)
            if fresh:
                symbols[market] = fresh
                log(f"📚 {market}: {len(fresh)} symbols")
                save_catalog_file()
        except Exception as exc:
            log(f"catalog {market}: {exc}")

    save_state()


# ============================================================
# Technical calculations
# ============================================================

def closes(data):
    out = []
    for r in data:
        try:
            v = float(r["close"])
            if v > 0:
                out.append(v)
        except Exception:
            pass
    return out


def ema(values, period):
    if len(values) < period:
        return None
    value = sum(values[:period]) / period
    k = 2.0 / (period + 1)
    for x in values[period:]:
        value = value + k * (x - value)
    return value


def rsi(values, period=14):
    if len(values) <= period:
        return None

    gains = []
    losses = []

    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))

    gain = sum(gains[:period]) / period
    loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        gain = ((gain * (period - 1)) + gains[i]) / period
        loss = ((loss * (period - 1)) + losses[i]) / period

    if loss == 0:
        return 100.0

    return 100.0 - 100.0 / (1.0 + gain / loss)


def atr(data, period=14):
    if len(data) < period + 1:
        return None

    trs = []
    previous = None

    for row in data:
        try:
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])
        except Exception:
            continue

        if previous is None:
            tr = high - low
        else:
            tr = max(
                high - low,
                abs(high - previous),
                abs(low - previous),
            )

        trs.append(tr)
        previous = close

    if len(trs) < period:
        return None

    value = sum(trs[:period]) / period
    for tr in trs[period:]:
        value = ((value * (period - 1)) + tr) / period
    return value


def vwap(data):
    total_pv = 0.0
    total_volume = 0.0

    for row in data:
        try:
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])
            volume = float(row.get("volume", 0))
        except Exception:
            continue

        if volume <= 0:
            continue

        typical = (high + low + close) / 3.0
        total_pv += typical * volume
        total_volume += volume

    if total_volume <= 0:
        return None

    return total_pv / total_volume


def support_resistance(data, length=30):
    recent = data[-length:]
    highs, lows = [], []

    for row in recent:
        try:
            highs.append(float(row["high"]))
            lows.append(float(row["low"]))
        except Exception:
            pass

    if not highs or not lows:
        return None, None

    return min(lows), max(highs)


def volume_ratio(data):
    if len(data) < 21:
        return 1.0

    vals = []
    for row in data[-21:-1]:
        try:
            v = float(row.get("volume", 0))
            if v > 0:
                vals.append(v)
        except Exception:
            pass

    if not vals:
        return 1.0

    avg = sum(vals) / len(vals)

    try:
        current = float(data[-1].get("volume", 0))
    except Exception:
        return 1.0

    return current / avg if avg else 1.0


def format_price(x):
    if x is None:
        return "—"
    x = float(x)
    if abs(x) >= 1000:
        return f"{x:,.2f}"
    if abs(x) >= 1:
        return f"{x:.2f}"
    return f"{x:.6f}"


# ============================================================
# Data cache
# ============================================================

def history_key(market, item):
    return (
        market,
        item.get("symbol", ""),
        item.get("exchange", ""),
    )


def get_history(market, item):
    key = history_key(market, item)
    now = time.time()

    cached = history_cache.get(key)
    if cached and now - cached["time"] < HISTORY_TTL:
        return cached["data"]

    if now < provider_block_until:
        return cached["data"] if cached else []

    params = {
        "symbol": item["symbol"],
        "interval": "1day",
        "outputsize": 100,
    }

    if item.get("exchange"):
        params["exchange"] = item["exchange"]

    data = api_get("time_series", params)
    if data is None:
        return cached["data"] if cached else []

    values = data.get("values", []) if isinstance(data, dict) else []
    if not isinstance(values, list) or len(values) < 60:
        return cached["data"] if cached else []

    values = list(reversed(values))
    history_cache[key] = {"time": now, "data": values}
    return values


def get_quote(market, item):
    key = history_key(market, item)
    now = time.time()

    # Quote cache prevents accidental duplicate requests inside a cycle.
    cached = quote_cache.get(key)
    if cached and now - cached["time"] < 60:
        return cached["data"]

    if now < provider_block_until:
        return cached["data"] if cached else None

    params = {"symbol": item["symbol"]}
    if item.get("exchange"):
        params["exchange"] = item["exchange"]

    data = api_get("quote", params)
    if data is None:
        return cached["data"] if cached else None

    quote_cache[key] = {"time": now, "data": data}
    return data


# ============================================================
# Analysis
# ============================================================

def analyze(market, item, quote, history):
    try:
        price = float(quote.get("close", 0))
        change = float(quote.get("percent_change", 0))
    except Exception:
        return None

    if price <= 0:
        return None

    if market == "US" and price < MIN_US_PRICE:
        return None

    c = closes(history)
    if len(c) < 60:
        return None

    e10 = ema(c, 10)
    e14 = ema(c, 14)
    e15 = ema(c, 15)
    e25 = ema(c, 25)
    e50 = ema(c, 50)
    r = rsi(c, 14)
    a = atr(history, 14)
    w = vwap(history)
    support, resistance = support_resistance(history)
    vr = volume_ratio(history)

    if any(x is None for x in (e10, e14, e15, e25, e50, r, a)):
        return None

    buy = 0
    sell = 0

    if price > e10:
        buy += 1
    else:
        sell += 1

    if e10 > e14:
        buy += 1
    else:
        sell += 1

    if e14 > e15:
        buy += 1
    else:
        sell += 1

    if e15 > e25:
        buy += 1
    else:
        sell += 1

    if e25 > e50:
        buy += 1
    else:
        sell += 1

    if r >= 55:
        buy += 2
    elif r <= 45:
        sell += 2

    if w is not None:
        if price > w:
            buy += 1
        else:
            sell += 1

    if vr >= 1.5:
        if price >= c[-1]:
            buy += 1
        else:
            sell += 1

    total = max(buy + sell, 1)
    buy_power = round(100 * buy / total)
    sell_power = round(100 * sell / total)

    if buy_power >= 70 and buy > sell:
        signal = "BUY"
        strength = buy_power
        trend = "🟢 UP"
    elif sell_power >= 70 and sell > buy:
        signal = "SELL"
        strength = sell_power
        trend = "🔴 DOWN"
    else:
        return None

    targets = []
    for mult in (1, 1.5, 2, 2.5, 3, 3.5, 4, 5):
        targets.append(
            price + a * mult
            if signal == "BUY"
            else price - a * mult
        )

    # Golden candle / unusual activity are technical proxies.
    golden = False
    try:
        last = history[-1]
        op = float(last.get("open", last["close"]))
        hi = float(last["high"])
        lo = float(last["low"])
        cl = float(last["close"])
        rng = hi - lo
        body = abs(cl - op)
        golden = (
            rng > 0
            and cl > op
            and body / rng >= 0.65
            and vr >= 1.5
        )
    except Exception:
        pass

    return {
        "market": market,
        "symbol": item["symbol"],
        "price": price,
        "change": change,
        "signal": signal,
        "strength": strength,
        "buy_power": buy_power,
        "sell_power": sell_power,
        "trend": trend,
        "rsi": r,
        "atr": a,
        "vwap": w,
        "volume_ratio": vr,
        "ema10": e10,
        "ema14": e14,
        "ema15": e15,
        "ema25": e25,
        "ema50": e50,
        "support": support,
        "resistance": resistance,
        "golden": golden,
        "targets": targets,
    }


# ============================================================
# Telegram — standard library only
# ============================================================

def token_for(market):
    return {
        "TASI": TASI_TOKEN,
        "US": US_TOKEN,
        "CRYPTO": CRYPTO_TOKEN,
    }.get(market, "")


def telegram_send(market, chat_id, message):
    token = token_for(market)
    if not token:
        return False

    url = (
        "https://api.telegram.org/"
        f"bot{token}/sendMessage"
    )

    payload = urllib.parse.urlencode(
        {
            "chat_id": str(chat_id),
            "text": message,
            "disable_web_page_preview": "true",
        }
    ).encode()

    request = urllib.request.Request(
        url,
        data=payload,
        headers={"User-Agent": "AI-PRO-MAX/1.0"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status == 200
    except Exception as exc:
        log(f"Telegram warning: {exc}")
        return False


def signal_text(s):
    title = "🟢⬆️ شراء قوي" if s["signal"] == "BUY" else "🔴⬇️ بيع قوي"

    tps = []
    for i, target in enumerate(s["targets"], 1):
        if s["signal"] == "BUY":
            pct = (target / s["price"] - 1) * 100
        else:
            pct = (1 - target / s["price"]) * 100
        tps.append(f"TP{i}: {format_price(target)} ({pct:+.1f}%)")

    market_name = {
        "TASI": "🇸🇦 تاسي",
        "US": "🇺🇸 السوق الأمريكي",
        "CRYPTO": "🪙 العملات الرقمية",
    }[s["market"]]

    return (
        "💀🚀 AI PRO MAX\n\n"
        f"{market_name}\n"
        f"#{s['symbol']}\n\n"
        f"{title}\n"
        f"🎯 القوة: {s['strength']}/100\n"
        f"💰 السعر: {format_price(s['price'])}\n"
        f"📈 التغير: {s['change']:+.2f}%\n"
        f"📊 الاتجاه: {s['trend']}\n"
        f"RSI 14: {s['rsi']:.1f}\n"
        f"VWAP: {format_price(s['vwap'])}\n"
        f"ATR 14: {format_price(s['atr'])}\n"
        f"📊 الحجم: {s['volume_ratio']:.2f}x\n\n"
        f"EMA10: {format_price(s['ema10'])}\n"
        f"EMA14: {format_price(s['ema14'])}\n"
        f"EMA15: {format_price(s['ema15'])}\n"
        f"EMA25: {format_price(s['ema25'])}\n"
        f"EMA50: {format_price(s['ema50'])}\n\n"
        f"🛡️ الدعم: {format_price(s['support'])}\n"
        f"🔺 المقاومة: {format_price(s['resistance'])}\n"
        f"✨ Golden Candle: {'نعم' if s['golden'] else 'لا'}\n\n"
        "🎯 أهداف ATR:\n"
        + "\n".join(tps)
        + "\n\n"
        "⚠️ المؤشرات حسابات فنية وليست ضمانًا للنتيجة."
    )


def can_send(s):
    key = f"{s['market']}|{s['symbol']}|{s['signal']}"
    now = time.time()

    previous = float(last_signal.get(key, 0))
    if now - previous < SIGNAL_COOLDOWN:
        return False

    last_signal[key] = now
    save_state()
    return True


def send_signal(s):
    if not can_send(s):
        return

    message = signal_text(s)
    chats = list(telegram_chats[s["market"]])

    for chat_id in chats:
        telegram_send(s["market"], chat_id, message)


# ============================================================
# Telegram webhook / lightweight server
# ============================================================

def http_server():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            return

        def do_GET(self):
            body = json.dumps(
                {
                    "status": "ok",
                    "system": "AI PRO MAX",
                    "markets": {
                        k: len(v) for k, v in symbols.items()
                    },
                    "provider_paused": max(
                        0, int(provider_block_until - time.time())
                    ),
                },
                ensure_ascii=False,
            ).encode()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"

            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                data = {}

            path = self.path.lower()
            market = None

            if path.endswith("/telegram/tasi"):
                market = "TASI"
            elif path.endswith("/telegram/us"):
                market = "US"
            elif path.endswith("/telegram/crypto"):
                market = "CRYPTO"

            if market:
                message = data.get("message", {})
                chat = message.get("chat", {})
                chat_id = chat.get("id")

                if chat_id is not None:
                    telegram_chats[market].add(int(chat_id))

                    text = str(message.get("text", ""))
                    if text.startswith("/start"):
                        telegram_send(
                            market,
                            chat_id,
                            (
                                "💀🚀 AI PRO MAX\n\n"
                                "✅ البوت متصل\n"
                                f"📊 {market}\n"
                                "🔄 الفحص تلقائي\n"
                                "🛡️ حماية الحصة مفعلة"
                            ),
                        )

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    log(f"🌐 health server :{PORT}")
    server.serve_forever()


# ============================================================
# Scan engine
# ============================================================

def process_one(market, item):
    quote = get_quote(market, item)
    if not quote:
        return

    history = get_history(market, item)
    if not history:
        return

    result = analyze(market, item, quote, history)
    if result:
        send_signal(result)


def scan_market_slice(market):
    rows = symbols.get(market, [])
    if not rows:
        return

    total = len(rows)

    # One symbol at a time keeps the provider connection quiet.
    # The index moves forward, so the entire catalog is eventually covered.
    start = symbol_index[market]
    item = rows[start % total]
    symbol_index[market] = (start + 1) % total

    log(
        f"🔎 {market}: "
        f"{item['symbol']} "
        f"({symbol_index[market]}/{total})"
    )

    try:
        process_one(market, item)
    except Exception as exc:
        log(f"scan {market} {item.get('symbol')}: {exc}")


def main_loop():
    ensure_catalog()

    # Stagger markets. No huge burst at startup.
    market_order = ("TASI", "US", "CRYPTO")
    cursor = 0

    while True:
        if time.time() < provider_block_until:
            wait = max(5, int(provider_block_until - time.time()))
            log(f"🛡️ الحصة محمية — انتظار {wait} ثانية")
            time.sleep(min(wait, 300))
            continue

        market = market_order[cursor % len(market_order)]
        cursor += 1

        scan_market_slice(market)

        # Catalog is refreshed only once per day.
        if not catalog_is_fresh():
            ensure_catalog()

        # No overlapping cycles and no burst.
        time.sleep(max(5, SCAN_SECONDS))


# ============================================================
# Startup
# ============================================================

if __name__ == "__main__":
    log("=" * 60)
    log("💀🚀 AI PRO MAX — QUOTA SAFE")
    log("=" * 60)
    log("🧠 Engine: custom Python / standard library")
    log("🛡️ quota protection: ON")
    log("📚 local catalog cache: ON")
    log("💾 local state cache: ON")
    log("🚫 overlapping scans: OFF")
    log(
        "🤖 TASI: "
        + ("ON" if TASI_TOKEN else "OFF")
    )
    log(
        "🤖 US: "
        + ("ON" if US_TOKEN else "OFF")
    )
    log(
        "🤖 CRYPTO: "
        + ("ON" if CRYPTO_TOKEN else "OFF")
    )

    if not TWELVE_KEY:
        log("⛔ TWELVE_DATA_API_KEY غير موجود")

    # Server in background.
    threading.Thread(
        target=http_server,
        daemon=True,
    ).start()
