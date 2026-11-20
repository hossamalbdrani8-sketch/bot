# AI PRO MAX V2040 — MARKET HUNTER
# US + TASI/NOMU + BINANCE SPOT
# 24/7 | ULTRA-HD TELEGRAM DASHBOARDS | 20 TARGETS
# Ticker-change tracking is conservative: it only migrates history when a
# verified old->new mapping is supplied by an authoritative change feed.
#
# Required packages:
# aiohttp
# Pillow
# arabic-reshaper
# python-bidi
#
# Environment variables retained from the original project:
# SIFTING_API_KEY, SAHMK_API_KEY (or TASI_TOKEN),
# TWELVE_DATA_API_KEY (or TWELVEDATA_API_KEY),
# US_TOKEN, TASI_TOKEN, CRYPTO_TOKEN,
# CHAT_ID, US_CHAT_ID, TASI_CHAT_ID, CRYPTO_CHAT_ID
#
# Optional:
# NASDAQ_DAILY_LIST_URL = URL to a licensed/authorized Nasdaq Daily List feed
# NASDAQ_DAILY_LIST_TOKEN = feed token, if required by your provider
# TICKER_MAP_JSON = path to a JSON file containing verified mappings:
#   [{"old_symbol":"ABC","new_symbol":"XYZ","company_id":"CIK0000000001",
#     "effective_date":"2026-11-20","source":"Nasdaq Daily List"}]
# TICKER_REFRESH_SECONDS=21600
# SYMBOL_REFRESH_SECONDS=21600
# ALERT_COOLDOWN_SECONDS=1800
# MAX_ALERTS_PER_CYCLE=100
#
# IMPORTANT:
# The public Nasdaq symbol-directory files list current symbols, but do not
# themselves reliably provide a complete old-symbol -> new-symbol mapping.
# Do not infer a ticker change from a missing symbol or similar company name.
# Supply verified mappings from Nasdaq Daily List / a licensed corporate
# actions feed. The bot archives old symbols and migrates history only after
# validating the mapping and (when present) company identifier.

import os
import io
import json
import time
import math
import asyncio
import logging
import sqlite3
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiohttp
from PIL import Image, ImageDraw, ImageFont

try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    def rtl(value):
        return get_display(arabic_reshaper.reshape(str(value)))
except ImportError:
    def rtl(value):
        return str(value)

APP = "AI PRO MAX"
VERSION = "V2040 MARKET HUNTER"

SCAN_SECONDS = max(30, int(os.getenv("SCAN_SECONDS", "300")))
BATCH_SIZE = max(1, int(os.getenv("BATCH_SIZE", "20")))
WORKERS = max(1, int(os.getenv("WORKERS", "4")))
SYMBOL_REFRESH_SECONDS = max(300, int(os.getenv("SYMBOL_REFRESH_SECONDS", "21600")))
TICKER_REFRESH_SECONDS = max(300, int(os.getenv("TICKER_REFRESH_SECONDS", "3600")))
ALERT_COOLDOWN_SECONDS = max(60, int(os.getenv("ALERT_COOLDOWN_SECONDS", "1800")))
MAX_ALERTS_PER_CYCLE = max(1, int(os.getenv("MAX_ALERTS_PER_CYCLE", "100")))
DB_PATH = os.getenv("DB_PATH", "/data/ai_pro_max.db")
TICKER_MAP_JSON = os.getenv("TICKER_MAP_JSON", "ticker_changes.json")
NASDAQ_DAILY_LIST_URL = os.getenv("NASDAQ_DAILY_LIST_URL", "").strip()
NASDAQ_DAILY_LIST_TOKEN = os.getenv("NASDAQ_DAILY_LIST_TOKEN", "").strip()

US_MIN_PRICE = float(os.getenv("US_MIN_PRICE", "0.12"))
TIMEFRAMES = ["5m", "15m", "1h", "1d"]

SIFTING_KEY = os.getenv("SIFTING_API_KEY", "")
SAHMK_KEY = os.getenv("SAHMK_API_KEY", "") or os.getenv("TASI_TOKEN", "")
TWELVE_KEY = os.getenv("TWELVE_DATA_API_KEY", "") or os.getenv("TWELVEDATA_API_KEY", "")

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

WIDTH, HEIGHT = 2400, 3000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("AIPROMAX")


# ----------------------------- DATABASE -----------------------------

def db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=30000")
    con.executescript("""
    CREATE TABLE IF NOT EXISTS states (
        market TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
        data TEXT, updated REAL,
        PRIMARY KEY (market,symbol,timeframe)
    );
    CREATE TABLE IF NOT EXISTS targets (
        market TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
        target_no INTEGER NOT NULL, target_price REAL NOT NULL,
        hit INTEGER DEFAULT 0, created REAL,
        PRIMARY KEY (market,symbol,timeframe,target_no)
    );
    CREATE TABLE IF NOT EXISTS cursors (
        market TEXT PRIMARY KEY, position INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS symbol_aliases (
        market TEXT NOT NULL, old_symbol TEXT NOT NULL, new_symbol TEXT NOT NULL,
        company_id TEXT, effective_date TEXT, source TEXT, changed_at REAL,
        PRIMARY KEY (market,old_symbol,new_symbol)
    );
    CREATE TABLE IF NOT EXISTS symbol_archive (
        market TEXT NOT NULL, symbol TEXT NOT NULL, company_name TEXT,
        status TEXT NOT NULL, replacement_symbol TEXT, company_id TEXT,
        archived_at REAL, source TEXT,
        PRIMARY KEY (market,symbol)
    );
    CREATE TABLE IF NOT EXISTS alert_log (
        market TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
        alert_key TEXT NOT NULL, sent_at REAL NOT NULL,
        PRIMARY KEY (market,symbol,timeframe,alert_key)
    );
    CREATE TABLE IF NOT EXISTS historical_levels (
        market TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
        level_type TEXT NOT NULL, level_price REAL NOT NULL,
        level_time TEXT, source TEXT,
        UNIQUE(market,symbol,timeframe,level_type,level_price,level_time)
    );
    """)
    con.commit()
    return con


def get_state(market, symbol, tf):
    with db() as con:
        row = con.execute(
            "SELECT data FROM states WHERE market=? AND symbol=? AND timeframe=?",
            (market, symbol, tf)
        ).fetchone()
    if not row:
        return {}
    try:
        return json.loads(row[0] or "{}")
    except Exception:
        return {}


def save_state(market, symbol, tf, data):
    with db() as con:
        con.execute("""
        INSERT INTO states VALUES(?,?,?,?,?)
        ON CONFLICT(market,symbol,timeframe)
        DO UPDATE SET data=excluded.data,updated=excluded.updated
        """, (market, symbol, tf, json.dumps(data), time.time()))
        con.commit()


def get_cursor(market):
    with db() as con:
        row = con.execute("SELECT position FROM cursors WHERE market=?", (market,)).fetchone()
    return row[0] if row else 0


def set_cursor(market, position):
    with db() as con:
        con.execute("""
        INSERT INTO cursors VALUES(?,?)
        ON CONFLICT(market) DO UPDATE SET position=excluded.position
        """, (market, position))
        con.commit()


def get_targets(market, symbol, tf):
    with db() as con:
        return con.execute("""
        SELECT target_no,target_price,hit FROM targets
        WHERE market=? AND symbol=? AND timeframe=? ORDER BY target_no
        """, (market, symbol, tf)).fetchall()


def archive_symbol(market, symbol, name="", replacement="", company_id="", source=""):
    with db() as con:
        con.execute("""
        INSERT INTO symbol_archive
        (market,symbol,company_name,status,replacement_symbol,company_id,archived_at,source)
        VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(market,symbol) DO UPDATE SET
          status=excluded.status,
          replacement_symbol=excluded.replacement_symbol,
          company_id=COALESCE(NULLIF(excluded.company_id,''),symbol_archive.company_id),
          archived_at=excluded.archived_at,
          source=excluded.source
        """, (market, symbol, name, "REPLACED" if replacement else "ARCHIVED",
              replacement or None, company_id or None, time.time(), source))
        con.commit()


def migrate_symbol_history(market, old_symbol, new_symbol, company_id="", effective_date="", source=""):
    """Move current state/targets to the new ticker, retaining the old archive."""
    if old_symbol == new_symbol:
        return False
    with db() as con:
        # Do not overwrite an existing new-symbol target history.
        old_rows = con.execute("""
          SELECT timeframe,target_no,target_price,hit,created FROM targets
          WHERE market=? AND symbol=?
        """, (market, old_symbol)).fetchall()
        for tf, no, price, hit, created in old_rows:
            con.execute("""
              INSERT OR IGNORE INTO targets
              VALUES(?,?,?,?,?,?,?)
            """, (market, new_symbol, tf, no, price, hit, created))

        state_rows = con.execute("""
          SELECT timeframe,data,updated FROM states
          WHERE market=? AND symbol=?
        """, (market, old_symbol)).fetchall()
        for tf, data, updated in state_rows:
            # Preserve provenance in the migrated state.
            try:
                payload = json.loads(data or "{}")
            except Exception:
                payload = {}
            payload["previous_symbol"] = old_symbol
            payload["ticker_change"] = {
                "effective_date": effective_date,
                "source": source,
                "company_id": company_id
            }
            con.execute("""
              INSERT INTO states VALUES(?,?,?,?,?)
              ON CONFLICT(market,symbol,timeframe)
              DO UPDATE SET data=excluded.data,updated=excluded.updated
            """, (market, new_symbol, tf, json.dumps(payload), updated))

        con.execute("""
          INSERT OR IGNORE INTO symbol_aliases
          VALUES(?,?,?,?,?,?,?)
        """, (market, old_symbol, new_symbol, company_id or None,
              effective_date or None, source or "verified mapping", time.time()))
        con.execute("""
          UPDATE cursors SET position=0 WHERE market=?
        """, (market,))
        con.commit()

    archive_symbol(market, old_symbol, replacement=new_symbol,
                   company_id=company_id, source=source)
    return True


# -------------------------- FONT / DASHBOARD -------------------------

def load_font(size):
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "NotoNaskhArabic-Bold.ttf"),
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf",
        "/usr/share/fonts/opentype/noto/NotoNaskhArabic-Bold.ttf",
        "/usr/local/share/fonts/NotoNaskhArabic-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def draw_rtl(draw, xy, text, font, fill, anchor="ra"):
    draw.text(xy, rtl(text), font=font, fill=fill, anchor=anchor)


def money(value, market):
    currency = "SAR" if market == "TASI" else ("USDT" if market == "CRYPTO" else "USD")
    decimals = 2 if value >= 100 else (4 if value >= 1 else 6)
    return f"{value:,.{decimals}f} {currency}"


def create_dashboard(market, item, tf, result, events, hits):
    image = Image.new("RGB", (WIDTH, HEIGHT), "#06101E")
    draw = ImageDraw.Draw(image)

    price_font = load_font(125)
    symbol_font = load_font(85)
    section_font = load_font(70)
    data_font = load_font(58)
    target_font = load_font(52)
    title_font = load_font(82)
    badge_font = load_font(46)
    footer_font = load_font(44)

    is_up = result["change"] > 0
    is_down = result["change"] < 0
    white, green, red = "#F5F8FF", "#16DB7E", "#FF475E"
    green_soft, red_soft = "#0E2E24", "#33111B"
    green_border, red_border = "#1FC977", "#F2465D"
    navy_header, navy_panel, navy_card = "#0E223D", "#0C1A2E", "#11233D"
    navy_border, muted, gold = "#233F63", "#9BB2CE", "#F7C948"

    accent = green if is_up else (red if is_down else gold)
    accent_bg = green_soft if is_up else (red_soft if is_down else "#2A2411")
    accent_border = green_border if is_up else (red_border if is_down else gold)

    market_name = {"US": "السوق الأمريكي", "TASI": "السوق السعودي",
                   "CRYPTO": "العملات الرقمية"}.get(market, market)
    currency = "SAR" if market == "TASI" else ("USDT" if market == "CRYPTO" else "USD")
    direction = "صاعد" if is_up else ("هابط" if is_down else "مستقر")

    def panel(x1, y1, x2, y2, fill=navy_panel, outline=navy_border, width=3):
        draw.rounded_rectangle((x1, y1, x2, y2), radius=32, fill=fill,
                               outline=outline, width=width)

    panel(55, 40, WIDTH-55, 220, navy_header, accent_border, 4)
    draw.text((WIDTH-105, 130), "AI PRO MAX", font=title_font, fill=white, anchor="rm")
    draw_rtl(draw, (105, 130), f"{VERSION} | {market_name} | {tf}",
             badge_font, accent, anchor="lm")

    panel(55, 250, WIDTH-55, 820, navy_panel, accent_border, 4)
    symbol = str(item["symbol"])
    name = str(item.get("name", symbol))
    draw_rtl(draw, (WIDTH-105, 330), f"{name} ({symbol})", symbol_font, white)
    draw.rounded_rectangle((105,315,435,425), radius=22, fill=accent_bg,
                           outline=accent_border, width=3)
    draw_rtl(draw, (270,370), f"{direction} {result['change']:+.2f}%",
             data_font, accent, anchor="mm")
    price_text = f"{result['price']:,.4f} {currency}" if result["price"] >= 1 else f"{result['price']:,.6f} {currency}"
    draw.text((WIDTH//2,560), price_text, font=price_font, fill=accent, anchor="mm")
    draw_rtl(draw, (WIDTH-105,705), f"السوق: {market_name} • الفاصل: {tf}",
             data_font, muted)
    draw_rtl(draw, (105,705), f"التغير: {result['change']:+.2f}% • الحالة: {direction}",
             data_font, accent, anchor="la")

    panel(55,850,WIDTH-55,1475)
    draw_rtl(draw,(WIDTH-105,880),"بيانات السيولة والمؤشرات الفنية",section_font,gold)
    metrics = [
        ("الفوليوم",f"{result['volume']:,.0f}",white),
        ("نشاط الفوليوم",f"{result['volume_ratio']:.2f}x",green if result["volume_ratio"]>=1.5 else white),
        ("RSI (14)",f"{result['rsi']:.2f}" if result["rsi"] is not None else "--",white),
        ("VWAP",f"{result['vwap']:.4f}" if result["vwap"] is not None else "--",white),
        ("قوة إغلاق الشمعة",f"{result['buyer_proxy']:.1f}%",green if result["buyer_proxy"]>=50 else red),
        ("التجميع", "احتمال" if result["accumulation"] else "غير ظاهر",
         green if result["accumulation"] else muted)
    ]
    col_width, gap, right = 720, 35, WIDTH-105
    for idx,(label,value,color) in enumerate(metrics):
        row,col=idx//3,idx%3
        x2=right-col*(col_width+gap); x1=x2-col_width
        y1=980+row*235; y2=y1+205
        draw.rounded_rectangle((x1,y1,x2,y2),radius=22,fill=navy_card,outline=navy_border,width=2)
        draw_rtl(draw,(x2-26,y1+22),label,data_font,muted)
        draw.text(((x1+x2)//2,y1+148),str(value),font=data_font,fill=color,anchor="mm")

    panel(55,1505,WIDTH-55,1855)
    draw_rtl(draw,(WIDTH-105,1532),"الدعم والمقاومة والمتوسطات EMA",section_font,gold)
    draw.rounded_rectangle((1240,1625,WIDTH-105,1730),radius=20,fill=red_soft,outline=red_border,width=2)
    draw_rtl(draw,(WIDTH-135,1677),f"المقاومة: {result['resistance']:.4f}",data_font,red,anchor="rm")
    draw.rounded_rectangle((105,1625,1200,1730),radius=20,fill=green_soft,outline=green_border,width=2)
    draw_rtl(draw,(1170,1677),f"الدعم: {result['support']:.4f}",data_font,green,anchor="rm")
    ema_items=[f"EMA{p}: {v:.4f}" for p,v in result["ema"].items() if v is not None]
    draw.text((WIDTH//2,1795),"   |   ".join(ema_items) if ema_items else "EMA: --",
              font=data_font,fill=white,anchor="mm")

    panel(55,1885,WIDTH-55,2845)
    draw_rtl(draw,(WIDTH-105,1912),"الأهداف السعرية (1 - 20)",section_font,gold)
    targets=get_targets(market,symbol,tf)
    if targets:
        col_w,col_gap,row_h=1110,70,78
        for idx,(number,target_price,hit) in enumerate(targets[:20]):
            col,row=idx//10,idx%10
            x2=(WIDTH-105)-col*(col_w+col_gap); x1=x2-col_w
            y1=2015+row*row_h; y2=y1+66
            fill=green_soft if hit else navy_card
            outline=green_border if hit else navy_border
            color=green if hit else white
            mark="✓" if hit else "○"
            draw.rounded_rectangle((x1,y1,x2,y2),radius=16,fill=fill,outline=outline,width=2)
            draw_rtl(draw,(x2-24,y1+33),f"[{mark}] هدف {number:02d}: {money(target_price,market)}",
                     target_font,color,anchor="rm")
    else:
        draw_rtl(draw,(WIDTH-105,2120),"بانتظار بيانات كافية لحساب الأهداف",data_font,muted)

    panel(55, 2860, WIDTH-55, 2960, navy_header, navy_border, 2)
    draw.text((WIDTH-105,2910),"AI PRO MAX | 24/7 MARKET HUNTER",
              font=footer_font,fill=accent,anchor="rm")
    draw.text((105,2910),datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
              font=footer_font,fill=muted,anchor="lm")

    output=io.BytesIO()
    image.save(output,format="PNG",optimize=True)
    output.seek(0)
    output.name=f"{symbol}_{tf}.png"
    return output


# ------------------------------- HTTP -------------------------------

async def get_json(session,url,headers=None,params=None,retries=3):
    for attempt in range(retries):
        try:
            async with session.get(url,headers=headers,params=params,
                                   timeout=aiohttp.ClientTimeout(total=25)) as response:
                if response.status==429:
                    await asyncio.sleep(3*(attempt+1)); continue
                if response.status>=500:
                    await asyncio.sleep(2*(attempt+1)); continue
                if response.status>=400:
                    log.warning("HTTP %s %s: %s",response.status,url,(await response.text())[:200])
                    return None
                return await response.json(content_type=None)
        except Exception as exc:
            log.warning("HTTP error %s: %s",url,exc)
            await asyncio.sleep(2*(attempt+1))
    return None


async def get_text(session,url,headers=None):
    try:
        async with session.get(url,headers=headers,timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status != 200:
                log.warning("Text feed HTTP %s: %s",response.status,url)
                return None
            return await response.text()
    except Exception as exc:
        log.warning("Text feed error: %s",exc)
        return None


async def telegram_text(session,token,chat,message):
    if not token or not chat:
        log.error("Telegram token/chat missing")
        return False
    url=f"{TELEGRAM_API}/bot{token}/sendMessage"
    for start in range(0,len(message),3900):
        try:
            async with session.post(url,json={"chat_id":chat,"text":message[start:start+3900],
                                              "disable_web_page_preview":True},
                                    timeout=aiohttp.ClientTimeout(total=25)) as response:
                data=await response.json(content_type=None)
                if response.status!=200 or not data.get("ok"):
                    log.error("Telegram text error: %s",data); return False
        except Exception as exc:
            log.exception("Telegram error: %s",exc); return False
    return True


async def telegram_photo(session,token,chat,photo,caption):
    if not token or not chat:
        log.error("Telegram photo credentials missing"); return False
    form=aiohttp.FormData()
    form.add_field("chat_id",str(chat))
    form.add_field("caption",caption[:1000])
    form.add_field("photo",photo,filename="AI_PRO_MAX.png",content_type="image/png")
    try:
        async with session.post(f"{TELEGRAM_API}/bot{token}/sendPhoto",data=form,
                                timeout=aiohttp.ClientTimeout(total=60)) as response:
            data=await response.json(content_type=None)
            if response.status!=200 or not data.get("ok"):
                log.error("Telegram photo error: %s",data); return False
            return True
    except Exception as exc:
        log.exception("Photo send error: %s",exc); return False


def bot_details(market):
    if market=="US": return US_BOT,US_CHAT
    if market=="TASI": return TASI_BOT,TASI_CHAT
    return CRYPTO_BOT,CRYPTO_CHAT


# -------------------------- SYMBOL UNIVERSES -------------------------

async def get_us_symbols(session):
    if not TWELVE_KEY:
        log.error("TWELVEDATA_API_KEY missing"); return []
    data=await get_json(session,f"{TWELVE_API}/stocks",
                        params={"apikey":TWELVE_KEY,"format":"JSON"})
    if not data: return []
    rows=data if isinstance(data,list) else data.get("data",[])
    allowed={"NASDAQ","NYSE","NYSE AMERICAN","NYSE ARCA"}
    symbols=[]; seen=set()
    for item in rows:
        symbol=str(item.get("symbol","")).strip().upper()
        exchange=str(item.get("exchange","")).strip().upper()
        country=str(item.get("country","")).strip().lower()
        currency=str(item.get("currency","")).strip().upper()
        if not symbol or symbol in seen: continue
        if country not in ("united states","usa","us"): continue
        if currency!="USD" or exchange not in allowed: continue
        seen.add(symbol)
        symbols.append({"symbol":symbol,"name":item.get("name") or symbol,
                        "exchange":exchange,"company_id":str(item.get("cik") or item.get("figi") or "")})
    log.info("US symbols loaded: %s",len(symbols))
    return symbols


async def get_sa_symbols(session):
    if not SAHMK_KEY:
        log.error("SAHMK_API_KEY missing"); return []
    headers={"X-API-Key":SAHMK_KEY}; symbols=[]; seen=set()
    for market in ("TASI","NOMU"):
        offset=0
        while True:
            data=await get_json(session,f"{SAHMK_API}/companies/",headers=headers,
                                params={"market":market,"limit":500,"offset":offset})
            if not data: break
            rows=data.get("results",[])
            if not rows: break
            for item in rows:
                symbol=str(item.get("symbol","")).strip()
                status=str(item.get("status","")).lower()
                sec_type=str(item.get("security_type","")).lower()
                if not symbol or symbol in seen: continue
                if status and status!="active": continue
                if sec_type!="equity": continue
                seen.add(symbol)
                symbols.append({"symbol":symbol,"name":item.get("name_ar") or item.get("name_en") or symbol})
            offset+=len(rows)
            total=int(data.get("total",0) or 0)
            if len(rows)<500 or (total and offset>=total): break
    log.info("Saudi symbols loaded: %s",len(symbols))
    return symbols


async def get_crypto_symbols(session):
    data=await get_json(session,f"{BINANCE_API}/api/v3/exchangeInfo")
    if not data: return []
    result=[]
    for item in data.get("symbols",[]):
        if item.get("status")!="TRADING": continue
        if item.get("quoteAsset") not in ("USDT","USD"): continue
        permissions=item.get("permissions",[])
        if permissions and "SPOT" not in permissions: continue
        result.append({"symbol":item.get("symbol"),"name":item.get("baseAsset",item.get("symbol"))})
    return result


# ---------------------- TICKER CHANGE DETECTOR -----------------------

def load_verified_ticker_mappings():
    """Read only explicit verified mappings; never guess from symbol disappearance."""
    path=Path(TICKER_MAP_JSON)
    if not path.exists():
        return []
    try:
        raw=json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw,list): return []
        valid=[]
        for row in raw:
            if not isinstance(row,dict): continue
            old=str(row.get("old_symbol","")).strip().upper()
            new=str(row.get("new_symbol","")).strip().upper()
            if not old or not new or old==new: continue
            valid.append({
                "old_symbol":old,"new_symbol":new,
                "company_id":str(row.get("company_id","")).strip(),
                "effective_date":str(row.get("effective_date","")).strip(),
                "source":str(row.get("source","Verified corporate-action feed")).strip()
            })
        return valid
    except Exception:
        log.exception("Could not read ticker mapping file")
        return []


async def fetch_daily_list_mappings(session):
    """
    Optional authorized provider adapter.
    Expected JSON response:
      [{"old_symbol":"ABC","new_symbol":"XYZ","company_id":"...","effective_date":"..."}]
    Or CSV with the same column names.
    A raw Nasdaq symbol-directory file is NOT an old/new mapping feed.
    """
    if not NASDAQ_DAILY_LIST_URL:
        return []
    headers={}
    if NASDAQ_DAILY_LIST_TOKEN:
        headers["Authorization"]=f"Bearer {NASDAQ_DAILY_LIST_TOKEN}"
    body=await get_text(session,NASDAQ_DAILY_LIST_URL,headers=headers)
    if not body: return []
    rows=[]
    try:
        parsed=json.loads(body)
        rows=parsed if isinstance(parsed,list) else parsed.get("changes",[])
    except Exception:
        try:
            # Nasdaq Daily List files may be comma- or tab-delimited.
            sample="\\n".join(body.splitlines()[:8])
            dialect=csv.Sniffer().sniff(sample, delimiters=",\\t;|")
            rows=list(csv.DictReader(body.splitlines(), dialect=dialect))
        except Exception:
            log.exception("Could not parse Daily List mapping feed")
            return []
    mappings=[]
    for row in rows:
        if not isinstance(row,dict): continue
        normalized={str(k).strip().lower().replace(" ","_"):v for k,v in row.items() if k is not None}
        event=str(normalized.get("issue_event") or normalized.get("event") or "").strip().lower()
        # Accept only explicit symbol-change rows, not additions/deletions.
        if event and "symbol" not in event:
            continue
        old=str(normalized.get("old_symbol") or normalized.get("oldticker") or
                normalized.get("symbol") or "").strip().upper()
        new=str(normalized.get("new_symbol") or normalized.get("newticker") or "").strip().upper()
        if old and new and old!=new:
            mappings.append({
                "old_symbol":old,"new_symbol":new,
                "company_id":str(normalized.get("company_id") or normalized.get("cik") or "").strip(),
                "effective_date":str(normalized.get("effective_date") or normalized.get("date") or "").strip(),
                "source":str(normalized.get("source") or "Nasdaq Daily List").strip()
            })
    return mappings


async def process_ticker_changes(session, current_us_symbols):
    mappings=load_verified_ticker_mappings()
    feed_mappings=await fetch_daily_list_mappings(session)
    mappings.extend(feed_mappings)
    current={x["symbol"]:x for x in current_us_symbols}
    token,chat=bot_details("US")
    processed=set()

    for mapping in mappings:
        old=mapping["old_symbol"]; new=mapping["new_symbol"]
        key=(old,new)
        if key in processed: continue
        processed.add(key)

        # New ticker should be present in the current US universe. This avoids
        # migrating to a typo or a ticker not recognized by the current provider.
        if new not in current:
            log.warning("Ticker change awaiting new symbol in universe: %s -> %s",old,new)
            continue

        company_id=mapping.get("company_id","")
        old_item=None
        # If company IDs are supplied by both sides, require equality.
        new_id=str(current[new].get("company_id","") or "")
        if company_id and new_id and company_id not in (new_id, f"CIK{new_id}"):
            log.error("Ticker mapping identity mismatch: %s -> %s",old,new)
            continue

        changed=migrate_symbol_history(
            "US",old,new,company_id,
            mapping.get("effective_date",""),mapping.get("source","")
        )
        if changed:
            message=(
                "🔔 AI PRO MAX V2040\n"
                "تم تغيير رمز السهم\n\n"
                f"الرمز السابق: {old}\n"
                f"الرمز الجديد: {new}\n"
                f"اسم الشركة: {current[new].get('name',new)}\n"
                f"تاريخ النفاذ: {mapping.get('effective_date') or 'غير محدد'}\n"
                f"المصدر: {mapping.get('source')}\n\n"
                "تم أرشفة الرمز السابق وربط سجل الأهداف والمؤشرات المتاح بالرمز الجديد."
            )
            await telegram_text(session,token,chat,message)
            log.info("Verified ticker change migrated: %s -> %s",old,new)


# ----------------------------- MARKET DATA --------------------------

async def us_bars(session,symbol,interval):
    if not SIFTING_KEY: return []
    end=datetime.now(timezone.utc)
    days=5 if interval in ("5m","15m") else (40 if interval=="1h" else 500)
    data=await get_json(
        session,f"{SIFTING_API}/v1/hist/stocks/{symbol}/bars",
        headers={"X-API-Key":SIFTING_KEY,"Accept-Encoding":"gzip"},
        params={"start":(end-timedelta(days=days)).strftime("%Y-%m-%d"),
                "end":end.strftime("%Y-%m-%d"),"interval":interval,"limit":500}
    )
    if not data: return []
    bars=[]
    for x in data.get("data",[]):
        try:
            bars.append({"open":float(x["o"]),"high":float(x["h"]),
                         "low":float(x["l"]),"close":float(x["c"]),
                         "volume":float(x["v"]),"time":x.get("t")})
        except (KeyError,TypeError,ValueError):
            continue
    return bars


async def sa_bars(session,symbol,interval):
    if not SAHMK_KEY: return []
    interval_map={"5m":"5min","15m":"15min","1h":"60min","1d":"1d"}
    days=30 if interval!="1d" else 500
    data=await get_json(
        session,f"{SAHMK_API}/historical/{symbol}/",
        headers={"X-API-Key":SAHMK_KEY},
        params={"interval":interval_map[interval],
                "from":(datetime.now()-timedelta(days=days)).strftime("%Y-%m-%d"),
                "to":datetime.now().strftime("%Y-%m-%d"),"limit":500}
    )
    if not data: return []
    bars=[]
    for x in data.get("data",[]):
        try:
            bars.append({"open":float(x["open"]),"high":float(x["high"]),
                         "low":float(x["low"]),"close":float(x["close"]),
                         "volume":float(x["volume"]),"time":x.get("date")})
        except (KeyError,TypeError,ValueError):
            continue
    return bars


async def crypto_bars(session,symbol,interval):
    data=await get_json(session,f"{BINANCE_API}/api/v3/klines",
                        params={"symbol":symbol,"interval":interval,"limit":500})
    if not isinstance(data,list): return []
    return [{"open":float(x[1]),"high":float(x[2]),"low":float(x[3]),
             "close":float(x[4]),"volume":float(x[5]),"time":x[0]} for x in data]


# -------------------------- TECHNICAL ANALYSIS -----------------------

def ema(values,period):
    if len(values)<period: return None
    alpha=2/(period+1)
    value=sum(values[:period])/period
    for x in values[period:]:
        value=alpha*x+(1-alpha)*value
    return value


def rsi(values,period=14):
    if len(values)<period+1: return None
    changes=[values[i]-values[i-1] for i in range(1,len(values))]
    gains=[max(x,0) for x in changes]
    losses=[max(-x,0) for x in changes]
    avg_gain=sum(gains[:period])/period
    avg_loss=sum(losses[:period])/period
    for i in range(period,len(gains)):
        avg_gain=(avg_gain*(period-1)+gains[i])/period
        avg_loss=(avg_loss*(period-1)+losses[i])/period
    if avg_loss==0: return 100.0
    rs=avg_gain/avg_loss
    return 100-(100/(1+rs))


def atr(bars,period=14):
    if len(bars)<period+1: return None
    trs=[]
    for i in range(1,len(bars)):
        cur,prev=bars[i],bars[i-1]
        trs.append(max(cur["high"]-cur["low"],
                       abs(cur["high"]-prev["close"]),
                       abs(cur["low"]-prev["close"])))
    return sum(trs[-period:])/min(period,len(trs))


def vwap(bars):
    recent=bars[-30:]
    volume=sum(x["volume"] for x in recent)
    if volume<=0: return None
    return sum(((x["high"]+x["low"]+x["close"])/3)*x["volume"] for x in recent)/volume


def historical_swings(bars, left=3, right=3):
    highs=[]; lows=[]
    for i in range(left,len(bars)-right):
        hi=bars[i]["high"]; lo=bars[i]["low"]
        if all(hi>=bars[j]["high"] for j in range(i-left,i+right+1) if j!=i):
            highs.append((hi,bars[i].get("time")))
        if all(lo<=bars[j]["low"] for j in range(i-left,i+right+1) if j!=i):
            lows.append((lo,bars[i].get("time")))
    return highs,lows


def analyze(bars):
    if len(bars)<30: return None
    closes=[x["close"] for x in bars]
    volumes=[x["volume"] for x in bars]
    price=closes[-1]; previous=closes[-2]
    current_rsi=rsi(closes); current_atr=atr(bars); current_vwap=vwap(bars)
    emas={p:ema(closes,p) for p in (10,14,25,50)}
    avg_volume=sum(volumes[-21:-1])/20 if len(volumes)>=21 else 0
    volume_ratio=volumes[-1]/avg_volume if avg_volume>0 else 0
    # Keep the recent 30-bar range for near-term S/R.
    support=min(x["low"] for x in bars[-30:])
    resistance=max(x["high"] for x in bars[-30:])
    previous_resistance=max(x["high"] for x in bars[-31:-1]) if len(bars)>=31 else resistance
    recent_range=max(x["high"] for x in bars[-8:])-min(x["low"] for x in bars[-8:])
    accumulation=bool(current_atr and recent_range<=current_atr*2.5 and volume_ratio>=1.15)
    candle_range=max(bars[-1]["high"]-bars[-1]["low"],1e-9)
    buyer_proxy=((bars[-1]["close"]-bars[-1]["low"])/candle_range)*100
    swing_highs,swing_lows=historical_swings(bars)
    # Potential previous recovery levels above current price.
    old_highs=sorted({round(p,8) for p,_ in swing_highs if p>price})
    old_lows=sorted({round(p,8) for p,_ in swing_lows if p<price},reverse=True)
    return {
        "price":price,"previous":previous,
        "change":((price/previous)-1)*100 if previous else 0,
        "rsi":current_rsi,"atr":current_atr,"vwap":current_vwap,"ema":emas,
        "volume":volumes[-1],"volume_ratio":volume_ratio,
        "support":support,"resistance":resistance,
        "previous_resistance":previous_resistance,
        "accumulation":accumulation,"buyer_proxy":buyer_proxy,
        "historical_highs":old_highs[-20:],
        "historical_lows":old_lows[:20],
        "bar_high":bars[-1]["high"],"bar_low":bars[-1]["low"]
    }


# ------------------------- HISTORICAL MEMORY -------------------------

def save_historical_levels(market,symbol,tf,result):
    with db() as con:
        for price in result.get("historical_highs",[]):
            con.execute("""
              INSERT OR IGNORE INTO historical_levels
              VALUES(?,?,?,?,?,?,?)
            """,(market,symbol,tf,"PREVIOUS_SWING_HIGH",price,None,"OHLC swing scan"))
        for price in result.get("historical_lows",[]):
            con.execute("""
              INSERT OR IGNORE INTO historical_levels
              VALUES(?,?,?,?,?,?,?)
            """,(market,symbol,tf,"PREVIOUS_SWING_LOW",price,None,"OHLC swing scan"))
        con.commit()


def historical_targets(market,symbol,tf,current_price):
    with db() as con:
        rows=con.execute("""
          SELECT level_price FROM historical_levels
          WHERE market=? AND symbol=? AND timeframe=?
            AND level_type='PREVIOUS_SWING_HIGH' AND level_price>?
          ORDER BY level_price LIMIT 20
        """,(market,symbol,tf,current_price)).fetchall()
    return [r[0] for r in rows]


# ------------------------------- TARGETS -----------------------------

def create_targets(market,symbol,tf,price,current_atr,old_highs=None):
    if not current_atr or current_atr<=0: return
    with db() as con:
        existing=con.execute("""
          SELECT COUNT(*) FROM targets WHERE market=? AND symbol=? AND timeframe=?
        """,(market,symbol,tf)).fetchone()[0]
        if existing: return
        # First 20 targets use ATR ladder. Historical levels are stored separately
        # and displayed as recovery levels; they are not silently mixed into ATR targets.
        for number in range(1,21):
            target_price=price+current_atr*0.5*number
            con.execute("INSERT OR IGNORE INTO targets VALUES(?,?,?,?,?,?,?)",
                        (market,symbol,tf,number,target_price,0,time.time()))
        con.commit()


def update_targets(market,symbol,tf,high):
    hits=[]
    with db() as con:
        rows=con.execute("""
          SELECT target_no,target_price FROM targets
          WHERE market=? AND symbol=? AND timeframe=? AND hit=0
          ORDER BY target_no
        """,(market,symbol,tf)).fetchall()
        for number,target_price in rows:
            if high>=target_price:
                con.execute("""
                  UPDATE targets SET hit=1
                  WHERE market=? AND symbol=? AND timeframe=? AND target_no=?
                """,(market,symbol,tf,number))
                hits.append((number,target_price))
        con.commit()
    return hits


# --------------------------- SIGNAL ENGINE ---------------------------

def signal_events(market,symbol,tf,result):
    old=get_state(market,symbol,tf)
    price=result["price"]; current_rsi=result["rsi"]; events=[]
    if not old:
        old={"price":price,"rsi":current_rsi,"ema":{},"volume_ratio":0,"accumulation":False}
    old_ema=old.get("ema",{})
    for period,value in result["ema"].items():
        if value is None: continue
        was_above=old_ema.get(str(period))
        is_above=price>=value
        if was_above is not None and was_above!=is_above:
            events.append(f"اختراق EMA{period} للأعلى" if is_above else f"كسر EMA{period} للأسفل")
    if current_rsi is not None:
        old_rsi=old.get("rsi")
        if old_rsi is not None:
            for zone in (20,30,40,50,60,70,80):
                if old_rsi<zone<=current_rsi: events.append(f"RSI اخترق {zone} للأعلى")
                elif old_rsi>zone>=current_rsi: events.append(f"RSI كسر {zone} للأسفل")
    if result["volume_ratio"]>=1.5 and old.get("volume_ratio",0)<1.5:
        events.append("ارتفاع نشاط الفوليوم")
    if result["accumulation"] and not old.get("accumulation",False):
        events.append("احتمال تجميع سعري")
    if result["vwap"] and old.get("price",price)<result["vwap"]<=price:
        events.append("اختراق VWAP للأعلى")
    elif result["vwap"] and old.get("price",price)>result["vwap"]>=price:
        events.append("كسر VWAP للأسفل")

    # Breakout: compare against previous candles excluding current candle.
    prior_high=result.get("previous_resistance")
    if prior_high is not None and price>prior_high and result["volume_ratio"]>=1.5:
        if "اختراق سعري مع نشاط فوليوم" not in events:
            events.append("اختراق سعري مع نشاط فوليوم")

    save_state(market,symbol,tf,{
        "price":price,"rsi":current_rsi,
        "ema":{str(k):(price>=v if v is not None else None) for k,v in result["ema"].items()},
        "volume_ratio":result["volume_ratio"],"accumulation":result["accumulation"]
    })
    return events


def should_send_alert(market,symbol,tf,events,hits):
    keys=[]
    keys.extend("EVENT:"+e for e in events)
    keys.extend(f"HIT:{n}" for n,_ in hits)
    if not keys: return False
    now=time.time()
    fresh=[]
    with db() as con:
        for key in keys:
            row=con.execute("""
              SELECT sent_at FROM alert_log
              WHERE market=? AND symbol=? AND timeframe=? AND alert_key=?
            """,(market,symbol,tf,key)).fetchone()
            if not row or now-row[0]>=ALERT_COOLDOWN_SECONDS:
                fresh.append(key)
        for key in fresh:
            con.execute("INSERT OR REPLACE INTO alert_log VALUES(?,?,?,?,?)",
                        (market,symbol,tf,key,now))
        con.commit()
    return bool(fresh)


# ----------------------------- SEND REPORT ---------------------------

async def send_dashboard(session,market,item,tf,result,events,hits):
    token,chat=bot_details(market)
    if not token or not chat:
        log.error("%s: Telegram credentials missing",market); return False
    try:
        photo=create_dashboard(market,item,tf,result,events,hits)
        lines=[f"AI PRO MAX V2040 | {market}",f"{item['symbol']} | {tf}",
               f"السعر: {result['price']:.6f}",f"التغير: {result['change']:+.2f}%"]
        if events: lines.append("الإشارات: "+"، ".join(events))
        if hits: lines.append("الأهداف المحققة: "+"، ".join(f"هدف {n:02d} ✅" for n,_ in hits))
        old_levels=historical_targets(market,item["symbol"],tf,result["price"])
        if old_levels:
            lines.append("قمم سابقة أعلى من السعر: "+", ".join(f"{x:.4f}" for x in old_levels[:8]))
        return await telegram_photo(session,token,chat,photo,"\n".join(lines))
    except Exception as exc:
        log.exception("Dashboard error: %s",exc)
        return await telegram_text(session,token,chat,
            f"AI PRO MAX V2040 | {market}\n{item['symbol']} | {tf}\n"
            f"السعر: {result['price']:.6f}\nالتغير: {result['change']:+.2f}%")


# ---------------------------- SCAN WORKERS ---------------------------

async def scan_one(session,market,item):
    symbol=item["symbol"]; reports=[]
    for tf in TIMEFRAMES:
        try:
            if market=="US": bars=await us_bars(session,symbol,tf)
            elif market=="TASI": bars=await sa_bars(session,symbol,tf)
            else: bars=await crypto_bars(session,symbol,tf)
            if len(bars)<30: continue
            result=analyze(bars)
            if not result: continue
            if market=="US" and result["price"]<US_MIN_PRICE: continue
            save_historical_levels(market,symbol,tf,result)
            create_targets(market,symbol,tf,result["price"],result["atr"],result.get("historical_highs"))
            hits=update_targets(market,symbol,tf,result["bar_high"])
            events=signal_events(market,symbol,tf,result)
            if should_send_alert(market,symbol,tf,events,hits):
                reports.append((item,tf,result,events,hits))
        except Exception as exc:
            log.exception("Scan error %s %s %s: %s",market,symbol,tf,exc)
    return reports


async def process_market(session,market,symbols):
    if not symbols:
        log.warning("%s universe empty",market); return
    start=get_cursor(market)
    end=min(start+BATCH_SIZE,len(symbols))
    batch=symbols[start:end]
    if not batch:
        start=0; end=min(BATCH_SIZE,len(symbols)); batch=symbols[start:end]
    semaphore=asyncio.Semaphore(WORKERS)
    async def limited(item):
        async with semaphore: return await scan_one(session,market,item)
    results=await asyncio.gather(*(limited(x) for x in batch),return_exceptions=True)
    reports=[]
    for result in results:
        if isinstance(result,list): reports.extend(result)
        elif isinstance(result,Exception): log.error("Batch error: %s",result)
    set_cursor(market,0 if end>=len(symbols) else end)
    sent=0
    for item,tf,result,events,hits in reports[:MAX_ALERTS_PER_CYCLE]:
        if await send_dashboard(session,market,item,tf,result,events,hits): sent+=1
        await asyncio.sleep(0.4)
    log.info("%s scanned %s/%s | reports=%s | sent=%s",market,end,len(symbols),len(reports),sent)


# ------------------------------- MAIN --------------------------------

async def main():
    db()
    connector=aiohttp.TCPConnector(limit=WORKERS*4+20,ttl_dns_cache=300)
    timeout=aiohttp.ClientTimeout(total=45)
    async with aiohttp.ClientSession(connector=connector,timeout=timeout) as session:
        for market in ("US","TASI","CRYPTO"):
            token,chat=bot_details(market)
            await telegram_text(session,token,chat,
                f"AI PRO MAX V2040 — MARKET HUNTER\n"
                f"تم تشغيل بوت {market}\n"
                f"الفحص 24/7 مفعل\nالدورة: {SCAN_SECONDS} ثانية\n"
                f"لوحات الصور: 2400 × 3000\nالأهداف: 1 إلى 20\n"
                f"ذاكرة الرموز والأهداف: مفعلة\n"
                f"تغيير الرمز: يتحقق من خرائط موثقة فقط")

        universes={"US":[],"TASI":[],"CRYPTO":[]}
        last_symbol_refresh=0
        last_ticker_refresh=0

        while True:
            cycle_start=time.time()
            try:
                now=time.time()
                if now-last_symbol_refresh>=SYMBOL_REFRESH_SECONDS:
                    log.info("Refreshing market symbol universes")
                    us,sa,crypto=await asyncio.gather(
                        get_us_symbols(session),get_sa_symbols(session),get_crypto_symbols(session)
                    )
                    # Never replace a previously valid universe with an empty response.
                    if us: universes["US"]=us
                    if sa: universes["TASI"]=sa
                    if crypto: universes["CRYPTO"]=crypto
                    last_symbol_refresh=now
                    for market,symbols in universes.items():
                        token,chat=bot_details(market)
                        await telegram_text(session,token,chat,
                            f"تحديث قائمة {market}\nعدد الرموز: {len(symbols):,}\nالفحص المستمر فعال")

                if time.time()-last_ticker_refresh>=TICKER_REFRESH_SECONDS:
                    await process_ticker_changes(session,universes["US"])
                    last_ticker_refresh=time.time()

                # Separate processing queues for each market.
                for market in ("US","TASI","CRYPTO"):
                    await process_market(session,market,universes[market])

                elapsed=time.time()-cycle_start
                await asyncio.sleep(max(1,SCAN_SECONDS-elapsed))
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("MAIN LOOP ERROR")
                await asyncio.sleep(15)


if __name__=="__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Bot stopped manually")
