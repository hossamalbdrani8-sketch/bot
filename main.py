# ============================================================
# AI PRO MAX — TASI + US + CRYPTO
# TECHNICAL + VOLUME + PERSISTENT TREND + US NEWS
# ============================================================

import os
import time
import threading
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque

import requests
from flask import Flask, jsonify


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

CHAT_ID = os.getenv("CHAT_ID", "").strip()

CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN", "").strip()
TASI_TOKEN = os.getenv("TASI_TOKEN", "").strip()
US_TOKEN = os.getenv("US_TOKEN", "").strip()

SAHMK_API_KEY = os.getenv("SAHMK_API_KEY", "").strip()

TWELVEDATA_API_KEY = (
    os.getenv("TWELVEDATA_API_KEY", "").strip()
    or os.getenv("TWELVE_DATA_API_KEY", "").strip()
)

TELEGRAM_BOT_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    or os.getenv("BOT_TOKEN", "").strip()
)


# ============================================================
# APP
# ============================================================

app = Flask(__name__)

TD_BASE = "https://api.twelvedata.com"
SAHMK_BASE = "https://api.sahmk.sa/api/v1"
TELEGRAM_BASE = "https://api.telegram.org"


# ============================================================
# SETTINGS
# ============================================================

TIMEFRAME = "5min"

OUTPUTSIZE = 220

MIN_US_PRICE = 0.15

BATCH_SYMBOLS = 8

MAX_WORKERS = 4

SCAN_INTERVAL = 900

SYMBOL_REFRESH = 21600

NEWS_CACHE_TIME = 21600

NEWS_LIMIT = 5

EMA_LENGTHS = (
    10,
    14,
    15,
    25,
    50,
    200
)

RSI_LENGTH = 14

ATR_LENGTH = 14

VOLUME_LENGTH = 20

STOP_ATR = 1.5

ATR_TARGETS = [
    1.0,
    1.5,
    2.0,
    3.0,
    4.0,
    5.0,
    6.5,
    8.0
]


# ============================================================
# TWELVE DATA QUOTA
# ============================================================

TD_DAILY_LIMIT = 760

TD_MINUTE_LIMIT = 8

TD_USED_TODAY = 0

TD_DAY = None

TD_REQUEST_TIMES = deque(maxlen=16)

td_lock = threading.Lock()


# ============================================================
# STATE
# ============================================================

state_lock = threading.Lock()

session = requests.Session()

session.headers.update({
    "User-Agent": "AI-PRO-MAX/1.0"
})


SYMBOL_CACHE = {

    "US": {
        "symbols": [],
        "updated": 0
    },

    "CRYPTO": {
        "symbols": [],
        "updated": 0
    },

    "TASI": {
        "symbols": [],
        "updated": 0
    }

}


TREND_STATE = {}

LAST_SIGNAL = {}

NEWS_CACHE = {}

ROTATION = {

    "US": 0,

    "CRYPTO": 0,

    "TASI": 0

}


# ============================================================
# BASIC FUNCTIONS
# ============================================================

def now_utc():

    return datetime.now(timezone.utc)


def fmt_price(value):

    try:

        value = float(value)

        if value >= 100:

            return f"{value:.2f}"

        if value >= 1:

            return f"{value:.4f}"

        return f"{value:.6f}"

    except:

        return "—"


def fmt_volume(value):

    try:

        value = float(value)

        if value >= 1_000_000_000:

            return f"{value / 1_000_000_000:.2f}B"

        if value >= 1_000_000:

            return f"{value / 1_000_000:.2f}M"

        if value >= 1_000:

            return f"{value / 1_000:.2f}K"

        return f"{value:.0f}"

    except:

        return "—"


def clamp(value, low, high):

    return max(low, min(high, value))


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN:

        print(
            "Telegram token missing. "
            "Create TELEGRAM_BOT_TOKEN or BOT_TOKEN."
        )

        return False

    if not CHAT_ID:

        print("CHAT_ID missing.")

        return False

    url = (
        f"{TELEGRAM_BASE}/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {

        "chat_id": CHAT_ID,

        "text": message,

        "disable_web_page_preview": True

    }

    try:

        response = session.post(
            url,
            json=payload,
            timeout=20
        )

        if response.ok:

            return True

        print(
            "Telegram error:",
            response.status_code,
            response.text[:300]
        )

    except Exception as e:

        print("Telegram exception:", e)

    return False


# ============================================================
# TWELVE DATA QUOTA CONTROL
# ============================================================

def reset_td_day():

    global TD_DAY
    global TD_USED_TODAY

    today = now_utc().date().isoformat()

    with td_lock:

        if TD_DAY != today:

            TD_DAY = today

            TD_USED_TODAY = 0

            TD_REQUEST_TIMES.clear()


def td_can_spend(cost):

    global TD_USED_TODAY

    reset_td_day()

    with td_lock:

        if TD_USED_TODAY + cost > TD_DAILY_LIMIT:

            return False

        current = time.time()

        while TD_REQUEST_TIMES:

            if current - TD_REQUEST_TIMES[0] < 60:

                break

            TD_REQUEST_TIMES.popleft()

        if (
            len(TD_REQUEST_TIMES) + cost
            > TD_MINUTE_LIMIT
        ):

            return False

        TD_USED_TODAY += cost

        for _ in range(cost):

            TD_REQUEST_TIMES.append(current)

        return True


def td_request(
    endpoint,
    params=None,
    cost=1,
    retries=2
):

    params = dict(params or {})

    params["apikey"] = TWELVEDATA_API_KEY

    if not TWELVEDATA_API_KEY:

        return None

    if not td_can_spend(cost):

        print(
            "Twelve Data quota protected:",
            endpoint
        )

        return None

    url = TD_BASE + endpoint

    for attempt in range(retries + 1):

        try:

            response = session.get(
                url,
                params=params,
                timeout=30
            )

            if response.status_code == 200:

                data = response.json()

                if (
                    isinstance(data, dict)
                    and data.get("status") == "error"
                ):

                    print(
                        "Twelve Data error:",
                        data
                    )

                    return None

                return data

            if response.status_code in (
                429,
                500,
                502,
                503,
                504
            ):

                time.sleep(
                    2 + attempt * 2
                )

                continue

            print(
                "Twelve Data HTTP:",
                response.status_code
            )

            return None

        except Exception as e:

            if attempt < retries:

                time.sleep(
                    2 + attempt * 2
                )

            else:

                print(
                    "Twelve Data exception:",
                    e
                )

    return None


# ============================================================
# INDICATORS
# ============================================================

def EMA(values, length):

    if len(values) < length:

        return None

    alpha = 2 / (length + 1)

    result = float(values[0])

    for value in values[1:]:

        result = (
            alpha * float(value)
            +
            (1 - alpha) * result
        )

    return result


def SMA(values, length):

    if len(values) < length:

        return None

    return (
        sum(
            float(x)
            for x in values[-length:]
        )
        /
        length
    )


def RSI(values, length=14):

    if len(values) < length + 1:

        return None

    gains = []

    losses = []

    for i in range(-length, 0):

        change = (
            float(values[i])
            -
            float(values[i - 1])
        )

        gains.append(
            max(change, 0)
        )

        losses.append(
            max(-change, 0)
        )

    average_gain = sum(gains) / length

    average_loss = sum(losses) / length

    if average_loss == 0:

        return 100

    rs = average_gain / average_loss

    return 100 - (
        100 /
        (1 + rs)
    )


def ATR(rows, length=14):

    if len(rows) < length + 1:

        return None

    tr = []

    for i in range(1, len(rows)):

        high = float(rows[i]["high"])

        low = float(rows[i]["low"])

        previous_close = float(
            rows[i - 1]["close"]
        )

        value = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close)
        )

        tr.append(value)

    return sum(
        tr[-length:]
    ) / length


def VWAP(rows, length=20):

    rows = rows[-length:]

    total_pv = 0

    total_volume = 0

    for row in rows:

        high = float(row["high"])

        low = float(row["low"])

        close = float(row["close"])

        volume = float(
            row.get("volume", 0)
            or 0
        )

        typical_price = (
            high + low + close
        ) / 3

        total_pv += (
            typical_price * volume
        )

        total_volume += volume

    if total_volume == 0:

        return float(rows[-1]["close"])

    return (
        total_pv /
        total_volume
    )


# ============================================================
# TWELVE DATA SERIES
# ============================================================

def parse_series(data):

    if not data:

        return []

    values = data.get(
        "values",
        []
    )

    result = []

    for item in reversed(values):

        try:

            result.append({

                "datetime":
                    item.get("datetime"),

                "open":
                    float(item["open"]),

                "high":
                    float(item["high"]),

                "low":
                    float(item["low"]),

                "close":
                    float(item["close"]),

                "volume":
                    float(
                        item.get(
                            "volume",
                            0
                        )
                        or 0
                    )

            })

        except:

            continue

    return result


def get_td_series(symbol):

    data = td_request(
        "/time_series",
        {
            "symbol": symbol,
            "interval": TIMEFRAME,
            "outputsize": OUTPUTSIZE,
            "format": "JSON"
        },
        cost=1
    )

    return parse_series(data)


# ============================================================
# US STOCKS
# ============================================================

def get_us_symbols():

    cache = SYMBOL_CACHE["US"]

    if (
        cache["symbols"]
        and
        time.time() - cache["updated"]
        < SYMBOL_REFRESH
    ):

        return cache["symbols"]

    data = td_request(
        "/stocks",
        {
            "country":
                "United States"
        },
        cost=1
    )

    if not data:

        return []

    rows = data.get(
        "data",
        []
    )

    symbols = []

    for row in rows:

        symbol = str(
            row.get("symbol", "")
        ).strip()

        country = str(
            row.get("country", "")
        )

        if not symbol:

            continue

        if (
            "United States"
            not in country
            and
            country.upper() != "US"
        ):

            continue

        symbols.append(symbol)

    symbols = sorted(
        set(symbols),
        key=lambda x: x.upper()
    )

    SYMBOL_CACHE["US"] = {

        "symbols": symbols,

        "updated": time.time()

    }

    return symbols


# ============================================================
# CRYPTO
# ============================================================

def get_crypto_symbols():

    cache = SYMBOL_CACHE["CRYPTO"]

    if (
        cache["symbols"]
        and
        time.time() - cache["updated"]
        < SYMBOL_REFRESH
    ):

        return cache["symbols"]

    data = td_request(
        "/cryptocurrencies",
        {},
        cost=1
    )

    if not data:

        return []

    rows = data.get(
        "data",
        []
    )

    symbols = []

    for row in rows:

        symbol = str(
            row.get("symbol", "")
        ).strip()

        if symbol:

            symbols.append(symbol)

    symbols = sorted(
        set(symbols),
        key=lambda x: x.upper()
    )

    SYMBOL_CACHE["CRYPTO"] = {

        "symbols": symbols,

        "updated": time.time()

    }

    return symbols


# ============================================================
# SAHMK — TASI
# ============================================================

def sahmk_request(
    endpoint,
    params=None
):

    key = (
        SAHMK_API_KEY
        or
        TASI_TOKEN
    )

    if not key:

        return None

    try:

        response = session.get(

            SAHMK_BASE + endpoint,

            headers={
                "X-API-Key": key
            },

            params=params or {},

            timeout=30

        )

        if response.ok:

            return response.json()

        print(
            "SAHMK error:",
            response.status_code,
            response.text[:300]
        )

    except Exception as e:

        print(
            "SAHMK exception:",
            e
        )

    return None


def get_tasi_symbols():

    cache = SYMBOL_CACHE["TASI"]

    if (
        cache["symbols"]
        and
        time.time() - cache["updated"]
        < SYMBOL_REFRESH
    ):

        return cache["symbols"]

    symbols = []

    offset = 0

    while True:

        data = sahmk_request(
            "/companies/",
            {
                "market": "TASI",
                "limit": 100,
                "offset": offset
            }
        )

        if not data:

            break

        rows = data.get(
            "results",
            []
        )

        if not rows:

            break

        for row in rows:

            if (
                row.get("status")
                == "active"
                and
                row.get("security_type")
                == "Equity"
            ):

                symbol = str(
                    row.get(
                        "symbol",
                        ""
                    )
                ).strip()

                if symbol:

                    symbols.append(
                        symbol
                    )

        if len(rows) < 100:

            break

        offset += 100

        if offset > 1000:

            break

    symbols = sorted(
        set(symbols)
    )

    SYMBOL_CACHE["TASI"] = {

        "symbols": symbols,

        "updated": time.time()

    }

    return symbols


def get_tasi_series(symbol):

    data = sahmk_request(

        f"/historical/{symbol}/",

        {
            "interval": "1d",
            "limit": OUTPUTSIZE,
            "offset": 0
        }

    )

    if not data:

        return []

    values = (
        data.get("data")
        or
        data.get("results")
        or
        []
    )

    rows = []

    for item in reversed(values):

        try:

            rows.append({

                "datetime":
                    item.get(
                        "date"
                    )
                    or
                    item.get(
                        "datetime"
                    ),

                "open":
                    float(
                        item["open"]
                    ),

                "high":
                    float(
                        item["high"]
                    ),

                "low":
                    float(
                        item["low"]
                    ),

                "close":
                    float(
                        item["close"]
                    ),

                "volume":
                    float(
                        item.get(
                            "volume",
                            0
                        )
                        or 0
                    )

            })

        except:

            continue

    return rows


# ============================================================
# NEWS — US STOCKS
# ============================================================

POSITIVE_WORDS = [

    "beat",
    "beats",
    "strong",
    "surge",
    "surges",
    "growth",
    "grows",
    "profit",
    "profits",
    "record",
    "raises",
    "raised",
    "upgrade",
    "approved",
    "approval",
    "contract",
    "partnership",
    "deal",
    "acquisition",
    "buyback",
    "dividend",
    "positive",
    "expands",
    "expansion",
    "launch",
    "launches",
    "award",
    "awarded",
    "milestone",
    "secures",
    "bullish"

]


NEGATIVE_WORDS = [

    "miss",
    "misses",
    "weak",
    "drop",
    "drops",
    "fall",
    "falls",
    "loss",
    "losses",
    "cuts",
    "cut",
    "downgrade",
    "rejected",
    "rejection",
    "lawsuit",
    "investigation",
    "fraud",
    "recall",
    "warning",
    "warns",
    "bankruptcy",
    "layoffs",
    "dilution",
    "offering",
    "default",
    "negative",
    "delay",
    "delayed",
    "fine",
    "penalty",
    "bearish",
    "resigns",
    "resignation"

]


def classify_news(
    title,
    summary=""
):

    text = (
        f"{title} {summary}"
        .lower()
    )

    positive = sum(

        1
        for word
        in POSITIVE_WORDS
        if word in text

    )

    negative = sum(

        1
        for word
        in NEGATIVE_WORDS
        if word in text

    )

    if (
        positive >= 2
        and
        positive >= negative + 2
    ):

        return "🟢 إيجابي قوي"

    if (
        negative >= 2
        and
        negative >= positive + 2
    ):

        return "🔴 سلبي قوي"

    if positive > negative:

        return "🟢 إيجابي"

    if negative > positive:

        return "🔴 سلبي"

    return "🟡 محايد"


def get_us_news(symbol):

    cached = NEWS_CACHE.get(
        symbol
    )

    if cached:

        if (
            time.time()
            -
            cached["time"]
            <
            NEWS_CACHE_TIME
        ):

            return cached["news"]

    data = td_request(

        "/press_releases",

        {
            "symbol":
                symbol,

            "limit":
                NEWS_LIMIT,

            "language":
                "en"
        },

        cost=1

    )

    if not data:

        return []

    rows = (

        data.get(
            "press_releases"
        )

        or

        data.get(
            "data"
        )

        or

        data.get(
            "results"
        )

        or

        []

    )

    news = []

    for row in rows[:NEWS_LIMIT]:

        title = str(

            row.get(
                "title"
            )

            or

            row.get(
                "headline"
            )

            or

            ""

        ).strip()

        summary = str(

            row.get(
                "summary"
            )

            or

            row.get(
                "description"
            )

            or

            ""

        ).strip()

        if not title:

            continue

        news.append({

            "title":
                title,

            "summary":
                summary,

            "sentiment":
                classify_news(
                    title,
                    summary
                ),

            "url":
                str(
                    row.get(
                        "url"
                    )
                    or
                    row.get(
                        "link"
                    )
                    or
                    ""
                )

        })

    NEWS_CACHE[symbol] = {

        "time":
            time.time(),

        "news":
            news

    }

    return news


# ============================================================
# VOLUME
# ============================================================

def volume_analysis(rows):

    volumes = [

        float(
            x.get(
                "volume",
                0
            )
            or
            0
        )

        for x in rows

    ]

    current = volumes[-1]

    average = SMA(
        volumes,
        VOLUME_LENGTH
    )

    if not average:

        average = current or 1

    ratio = (
        current / average
        if average
        else 0
    )

    candle = rows[-1]

    high = float(
        candle["high"]
    )

    low = float(
        candle["low"]
    )

    close = float(
        candle["close"]
    )

    spread = high - low

    if spread > 0:

        buy_power = (
            (close - low)
            /
            spread
            *
            100
        )

    else:

        buy_power = 50

    sell_power = (
        100 - buy_power
    )

    return {

        "volume":
            current,

        "average":
            average,

        "ratio":
            ratio,

        "buy":
            buy_power,

        "sell":
            sell_power

    }


# ============================================================
# SUPPORT / RESISTANCE
# ============================================================

def support_resistance(rows):

    sample = rows[-30:]

    support = min(

        float(x["low"])
        for x in sample

    )

    resistance = max(

        float(x["high"])
        for x in sample

    )

    return support, resistance


# ============================================================
# GOLDEN CANDLE
# ============================================================

def golden_candle(
    rows,
    volume_ratio
):

    candle = rows[-1]

    open_price = float(
        candle["open"]
    )

    high = float(
        candle["high"]
    )

    low = float(
        candle["low"]
    )

    close = float(
        candle["close"]
    )

    candle_range = (
        high - low
    )

    body = abs(
        close - open_price
    )

    if candle_range <= 0:

        return False

    body_ratio = (
        body /
        candle_range
    )

    close_position = (
        close - low
    ) / candle_range

    return (

        close > open_price

        and

        body_ratio >= 0.65

        and

        close_position >= 0.75

        and

        volume_ratio >= 1.5

    )


# ============================================================
# HIDDEN DIVERGENCE
# ============================================================

def hidden_divergence(
    rows,
    rsi_values
):

    if len(rows) < 30:

        return "—"

    if len(rsi_values) < 30:

        return "—"

    recent = rows[-15]

    old = rows[-30]

    recent_rsi = rsi_values[-15]

    old_rsi = rsi_values[-30]

    if (

        float(recent["low"])
        >
        float(old["low"])

        and

        recent_rsi
        <
        old_rsi

    ):

        return "🟢 Hidden Bullish"

    if (

        float(recent["high"])
        <
        float(old["high"])

        and

        recent_rsi
        >
        old_rsi

    ):

        return "🔴 Hidden Bearish"

    return "—"


# ============================================================
# SMART MOVEMENT
# ============================================================

def smart_movement(
    volume_ratio,
    buy_power,
    sell_power
):

    if (
        volume_ratio >= 2.5
        and
        max(
            buy_power,
            sell_power
        ) >= 70
    ):

        return "🐋 حركة صنّاع السهم"

    if (
        volume_ratio >= 2.0
    ):

        return "⚡️ حركة مضاربين قوية"

    if (
        volume_ratio >= 1.5
    ):

        return "🔎 رصد حركة غير اعتيادية"

    if (
        buy_power >= 65
        and
        volume_ratio >= 1.1
    ):

        return "💰💰 عمليات التجميع"

    return "🔎 حركة طبيعية"


# ============================================================
# FULL ANALYSIS
# ============================================================

def analyze(rows):

    if len(rows) < 60:

        return None

    closes = [

        float(x["close"])

        for x in rows

    ]

    ema10 = EMA(
        closes,
        10
    )

    ema14 = EMA(
        closes,
        14
    )

    ema15 = EMA(
        closes,
        15
    )

    ema25 = EMA(
        closes,
        25
    )

    ema50 = EMA(
        closes,
        50
    )

    ema200 = EMA(
        closes,
        200
    )

    rsi14 = RSI(
        closes,
        14
    )

    atr14 = ATR(
        rows,
        14
    )

    vwap = VWAP(
        rows,
        20
    )

    if None in (
        ema10,
        ema14,
        ema15,
        ema25,
        ema50,
        ema200,
        rsi14,
        atr14
    ):

        return None

    price = closes[-1]

    volume = volume_analysis(
        rows
    )

    support, resistance = (
        support_resistance(
            rows
        )
    )

    long_up = (

        price > ema200

        and

        ema50 > ema200

    )

    long_down = (

        price < ema200

        and

        ema50 < ema200

    )

    short_up = (

        ema10
        >
        ema14
        >
        ema15
        >
        ema25

        and

        price > vwap

    )

    short_down = (

        ema10
        <
        ema14
        <
        ema15
        <
        ema25

        and

        price < vwap

    )

    score = 50

    if long_up:

        score += 15

    if short_up:

        score += 15

    if long_down:

        score -= 15

    if short_down:

        score -= 15

    if volume["buy"] > volume["sell"]:

        score += 5

    else:

        score -= 5

    if volume["ratio"] >= 1.5:

        if volume["buy"] > volume["sell"]:

            score += 5

        else:

            score -= 5

    score = int(
        clamp(
            score,
            0,
            100
        )
    )

    if score >= 60:

        direction = "UP"

        signal = "🟢 SMART BUY"

    elif score <= 40:

        direction = "DOWN"

        signal = "🔴 SMART SELL"

    else:

        direction = "WAIT"

        signal = "🟡 WAIT"

    rsi_history = []

    for i in range(
        max(
            0,
            len(closes) - 60
        ),
        len(closes)
    ):

        value = RSI(
            closes[:i + 1],
            14
        )

        if value is not None:

            rsi_history.append(
                value
            )

    divergence = hidden_divergence(
        rows,
        rsi_history
    )

    return {

        "price":
            price,

        "ema10":
            ema10,

        "ema14":
            ema14,

        "ema15":
            ema15,

        "ema25":
            ema25,

        "ema50":
            ema50,

        "ema200":
            ema200,

        "rsi":
            rsi14,

        "atr":
            atr14,

        "vwap":
            vwap,

        "volume":
            volume,

        "support":
            support,

        "resistance":
            resistance,

        "long_up":
            long_up,

        "long_down":
            long_down,

        "short_up":
            short_up,

        "short_down":
            short_down,

        "direction":
            direction,

        "signal":
            signal,

        "score":
            score,

        "golden":
            golden_candle(
                rows,
                volume["ratio"]
            ),

        "divergence":
            divergence,

        "movement":
            smart_movement(
                volume["ratio"],
                volume["buy"],
                volume["sell"]
            )

    }


# ============================================================
# PERSISTENT TREND + TP1 → TP8 → TP9...
# ============================================================

def get_persistent_state(
    key,
    direction,
    price,
    atr
):

    with state_lock:

        old = TREND_STATE.get(
            key
        )

        reversed_now = False

        if old is None:

            old = {

                "direction":
                    direction,

                "entry":
                    price,

                "targets":
                    [],

                "last_price":
                    price,

                "hit":
                    set()

            }

            TREND_STATE[key] = old

        elif (
            old["direction"]
            != direction
            and
            direction
            in
            ("UP", "DOWN")
        ):

            old["direction"] = (
                direction
            )

            old["entry"] = price

            old["targets"] = []

            old["hit"] = set()

            reversed_now = True

        old["last_price"] = price

        if not old["targets"]:

            sign = (
                1
                if direction == "UP"
                else -1
            )

            old["targets"] = [

                price
                +
                sign
                *
                atr
                *
                multiplier

                for multiplier
                in ATR_TARGETS

            ]

        return old, reversed_now


def extend_targets(
    state,
    atr,
    price
):

    sign = (
        1
        if state["direction"]
        == "UP"
        else -1
    )

    while len(
        state["targets"]
    ) < 8:

        state["targets"].append(

            state["entry"]
            +
            sign
            *
            atr
            *
            ATR_TARGETS[
                len(state["targets"])
            ]

        )

    # بعد TP8
    # TP9 / TP10 / TP11...
    while True:

        last = state[
            "targets"
        ][-1]

        next_target = (
            last
            +
            sign
            *
            atr
            *
            1.5
        )

        if sign > 0:

            if next_target <= price:

                state[
                    "targets"
                ].append(
                    next_target
                )

            else:

                break

        else:

            if next_target >= price:

                state[
                    "targets"
                ].append(
                    next_target
                )

            else:

                break


# ============================================================
# NEWS TEXT
# ============================================================

def format_news(news):

    if not news:

        return [
            "📰 لا يوجد خبر أمريكي متاح حالياً."
        ]

    result = []

    for item in news:

        result.append(

            f'{item["sentiment"]} — '
            f'{item["title"]}'

        )

    return result


# ============================================================
# TELEGRAM MESSAGE
# ============================================================

def build_message(
    market,
    symbol,
    analysis,
    state,
    news
):

    a = analysis

    long_icon = (

        "🟢"
        if a["long_up"]
        else
        "🔴"
        if a["long_down"]
        else
        "🟡"

    )

    short_icon = (

        "🟢"
        if a["short_up"]
        else
        "🔴"
        if a["short_down"]
        else
        "🟡"

    )

    if state["direction"] == "UP":

        stop = (
            a["price"]
            -
            a["atr"]
            *
            STOP_ATR
        )

    else:

        stop = (
            a["price"]
            +
            a["atr"]
            *
            STOP_ATR
        )

    lines = [

        "🐊🚀 AI PRO MAX SIGNAL",

        "",

        f"🌐 السوق: {market}",

        f"🔖 السهم: {symbol}",

        "",

        f"{long_icon} طويل المدى - "
        f"{short_icon} قصير المدى",

        "",

        f"{a['signal']} "
        f"🎯 قوة الإشارة: "
        f"{a['score']}/100",

        "",

        f"📈 الاتجاه المستمر: "
        f"{'🟢 صعود' if state['direction'] == 'UP' else '🔴 هبوط'}",

        "",

        a["movement"],

        (
            "🐋 حركة صنّاع السهم"
            if a["volume"]["ratio"] >= 2.5
            else ""
        ),

        (
            "⚡️ حركة مضاربين قوية"
            if a["volume"]["ratio"] >= 2
            else ""
        ),

        (
            "🔎 رصد حركة غير اعتيادية"
            if a["volume"]["ratio"] >= 1.5
            else ""
        ),

        (
            "💰💰 عمليات التجميع"
            if (
                a["volume"]["buy"] >= 65
                and
                a["volume"]["ratio"] >= 1.1
            )
            else ""
        ),

        "",

        "📰 الأخبار الأمريكية للسهم:",

        *format_news(news),

        "",

        f"💰 السعر: "
        f"{fmt_price(a['price'])}",

        f"🛑 وقف الخسارة: "
        f"{fmt_price(stop)}",

        f"📊 VWAP: "
        f"{fmt_price(a['vwap'])}",

        f"🧠 RSI 14: "
        f"{a['rsi']:.2f}",

        f"📐 ATR 14: "
        f"{fmt_price(a['atr'])}",

        f"🧩 Hidden Divergence: "
        f"{a['divergence']}",

        "",

        f"📦 Volume: "
        f"{fmt_volume(a['volume']['volume'])}",

        f"📊 Volume Ratio: "
        f"{a['volume']['ratio']:.2f}x",

        f"🟢 قوة الشراء: "
        f"{a['volume']['buy']:.1f}%",

        f"🔴 قوة البيع: "
        f"{a['volume']['sell']:.1f}%",

        "",

        f"📈 EMA 10: "
        f"{fmt_price(a['ema10'])}",

        f"📈 EMA 14: "
        f"{fmt_price(a['ema14'])}",

        f"📈 EMA 15: "
        f"{fmt_price(a['ema15'])}",

        f"📈 EMA 25: "
        f"{fmt_price(a['ema25'])}",

        f"📈 EMA 50: "
        f"{fmt_price(a['ema50'])}",

        f"📈 EMA 200: "
        f"{fmt_price(a['ema200'])}",

        "",

        f"🛡️ الدعم: "
        f"{fmt_price(a['support'])}",

        f"🚧 المقاومة: "
        f"{fmt_price(a['resistance'])}",

        "",

        "🎯 الأهداف ATR",

    ]

    for i, target in enumerate(
        state["targets"],
        1
    ):

        if state["direction"] == "UP":

            hit = (
                a["price"]
                >= target
            )

        else:

            hit = (
                a["price"]
                <= target
            )

        mark = (
            "✅"
            if hit
            else
            "🎯"
        )

        lines.append(

            f"{mark} TP{i}: "
            f"{fmt_price(target)}"

        )

    lines += [

        "",

        "♾️ بعد TP8 تستمر "
        "الأهداف تلقائياً مع "
        "استمرار الاتجاه.",

        "",

        f"🕒 "
        f"{now_utc().strftime('%Y-%m-%d %H:%M:%S UTC')}"

    ]

    return "\n".join(
        x
        for x in lines
        if x != ""
    )


# ============================================================
# SCAN ONE SYMBOL
# ============================================================

def scan_symbol(
    market,
    symbol
):

    try:

        if market == "TASI":

            rows = get_tasi_series(
                symbol
            )

            news = []

        else:

            rows = get_td_series(
                symbol
            )

            if market == "US":

                if not rows:

                    return None

                if (
                    rows[-1]["close"]
                    <
                    MIN_US_PRICE
                ):

                    return None

                news = get_us_news(
                    symbol
                )

            else:

                news = []

        if not rows:

            return None

        analysis = analyze(
            rows
        )

        if not analysis:

            return None

        if analysis[
            "direction"
        ] == "WAIT":

            return None

        key = (
            f"{market}:{symbol}"
        )

        state, reversed_now = (
            get_persistent_state(

                key,

                analysis[
                    "direction"
                ],

                analysis[
                    "price"
                ],

                analysis[
                    "atr"
                ]

            )
        )

        extend_targets(

            state,

            analysis[
                "atr"
            ],

            analysis[
                "price"
            ]

        )

        old = LAST_SIGNAL.get(
            key
        )

        should_send = False

        if old is None:

            should_send = True

        elif reversed_now:

            should_send = True

        elif (
            time.time()
            -
            old["time"]
            >
            1800
        ):

            if (
                abs(
                    analysis["score"]
                    -
                    old["score"]
                )
                >= 10
            ):

                should_send = True

        if should_send:

            LAST_SIGNAL[key] = {

                "direction":
                    analysis[
                        "direction"
                    ],

                "score":
                    analysis[
                        "score"
                    ],

                "time":
                    time.time()

            }

            return build_message(

                market,

                symbol,

                analysis,

                state,

                news

            )

    except Exception as e:

        print(
            "scan error:",
            market,
            symbol,
            e
        )

    return None


# ============================================================
# ROTATING SCANNER
# ============================================================

def get_next_batch(
    market,
    symbols
):

    if not symbols:

        return []

    index = ROTATION[
        market
    ]

    batch = symbols[
        index:
        index + BATCH_SYMBOLS
    ]

    if len(batch) < BATCH_SYMBOLS:

        batch += symbols[
            :BATCH_SYMBOLS -
            len(batch)
        ]

    ROTATION[
        market
    ] = (
        index +
        BATCH_SYMBOLS
    ) % len(symbols)

    return batch


def scan_market(market):

    if market == "US":

        symbols = get_us_symbols()

    elif market == "CRYPTO":

        symbols = get_crypto_symbols()

    else:

        symbols = get_tasi_symbols()

    if not symbols:

        print(
            "No symbols:",
            market
        )

        return

    batch = get_next_batch(
        market,
        symbols
    )

    print(
        "Scanning:",
        market,
        batch
    )

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = [

            executor.submit(
                scan_symbol,
                market,
                symbol
            )

            for symbol
            in batch

        ]

        for future in as_completed(
            futures
        ):

            message = future.result()

            if message:

                send_telegram(
                    message
                )


# ============================================================
# CONTINUOUS SCANNER
# ============================================================

def scanner_loop():

    markets = [

        "US",
        "CRYPTO",
        "TASI"

    ]

    index = 0

    while True:

        market = markets[
            index %
            len(markets)
        ]

        try:

            scan_market(
                market
            )

        except Exception as e:

            print(
                "Scanner error:",
                e
            )

        index += 1

        time.sleep(
            SCAN_INTERVAL
        )


# ============================================================
# RAILWAY HEALTH
# ============================================================

@app.get("/")
def home():

    return jsonify({

        "status":
            "AI PRO MAX ONLINE",

        "markets":
            [
                "TASI",
                "US",
                "CRYPTO"
            ],

        "features":
            [
                "Persistent Up Trend",
                "Persistent Down Trend",
                "Volume",
                "Volume Ratio",
                "Buy Power",
                "Sell Power",
                "VWAP",
                "RSI",
                "ATR",
                "EMA 10",
                "EMA 14",
                "EMA 15",
                "EMA 25",
                "EMA 50",
                "EMA 200",
                "Golden Candle",
                "Hidden Divergence",
                "Support",
                "Resistance",
                "TP1-TP8",
                "TP9+",
                "US News",
                "Strong Positive News",
                "Strong Negative News"
            ],

        "time":
            now_utc().isoformat()

    })


@app.get("/health")
def health():

    reset_td_day()

    return jsonify({

        "ok":
            True,

        "twelve_data_used_today":
            TD_USED_TODAY,

        "twelve_data_daily_limit":
            TD_DAILY_LIMIT,

        "US_symbols":
            len(
                SYMBOL_CACHE[
                    "US"
                ]["symbols"]
            ),

        "CRYPTO_symbols":
            len(
                SYMBOL_CACHE[
                    "CRYPTO"
                ]["symbols"]
            ),

        "TASI_symbols":
            len(
                SYMBOL_CACHE[
                    "TASI"
                ]["symbols"]
            )

    })


# ============================================================
# START
# ============================================================

def start_scanner():

    thread = threading.Thread(

        target=scanner_loop,

        daemon=True

    )

    thread.start()


start_scanner()


if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "8080"
        )
    )

    app.run(

        host="0.0.0.0",

        port=port

    )