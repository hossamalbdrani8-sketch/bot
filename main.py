import os, json, time, asyncio, logging, sqlite3, io
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

# =========================================================
# AI PRO MAX V12 — LIVE IMAGE DASHBOARD / 24-7
# US + TASI/NOMU + BINANCE SPOT
# Keeps existing environment-variable names.
# =========================================================
APP = "AI PRO MAX 💀🚀"
SCAN_SECONDS = max(30, int(os.getenv("SCAN_SECONDS", "300")))
BATCH_SIZE = max(1, int(os.getenv("BATCH_SIZE", "20")))
WORKERS = max(1, int(os.getenv("WORKERS", "4")))
DB_PATH = os.getenv("DB_PATH", "/data/ai_pro_max.db")
US_MIN_PRICE = float(os.getenv("US_MIN_PRICE", "0.12"))
TIMEFRAMES = [x.strip() for x in os.getenv("TIMEFRAMES", "5m,15m,1h,1d").split(",") if x.strip()]

US_TOKEN = os.getenv("US_TOKEN", "")
SIFTING_KEY = os.getenv("SIFTING_API_KEY", "")
SAHMK_KEY = os.getenv("SAHMK_API_KEY", "") or os.getenv("TASI_TOKEN", "")
TWELVE_KEY = os.getenv("TWELVEDATA_API_KEY", "") or os.getenv("TWELVE_DATA_API_KEY", "")
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("AIPROMAX")

# ----------------------------- DATABASE -----------------------------
def db():
    folder = os.path.dirname(DB_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""CREATE TABLE IF NOT EXISTS states (
        market TEXT, symbol TEXT, timeframe TEXT, data TEXT, updated REAL,
        PRIMARY KEY(market,symbol,timeframe))""")
    con.execute("""CREATE TABLE IF NOT EXISTS targets (
        market TEXT, symbol TEXT, timeframe TEXT, target_no INTEGER,
        target_price REAL, hit INTEGER DEFAULT 0, created REAL,
        entry_price REAL DEFAULT 0, created_bar_time TEXT DEFAULT '',
        stop_price REAL DEFAULT 0, status TEXT DEFAULT 'ACTIVE',
        PRIMARY KEY(market,symbol,timeframe,target_no))""")
    con.execute("""CREATE TABLE IF NOT EXISTS cursors (
        market TEXT PRIMARY KEY, position INTEGER DEFAULT 0, batch_no INTEGER DEFAULT 0)""")
    # Safe migrations for an existing V11 database.
    cols = {r[1] for r in con.execute("PRAGMA table_info(targets)").fetchall()}
    for name, decl in (("entry_price", "REAL DEFAULT 0"),
                       ("created_bar_time", "TEXT DEFAULT ''"),
                       ("stop_price", "REAL DEFAULT 0"),
                       ("status", "TEXT DEFAULT 'ACTIVE'")):
        if name not in cols:
            con.execute(f"ALTER TABLE targets ADD COLUMN {name} {decl}")
    ccols = {r[1] for r in con.execute("PRAGMA table_info(cursors)").fetchall()}
    if "batch_no" not in ccols:
        con.execute("ALTER TABLE cursors ADD COLUMN batch_no INTEGER DEFAULT 0")
    # Old V11 target ladders had no signal-bar timestamp; never treat them as fresh active signals.
    con.execute("UPDATE targets SET status='LEGACY' WHERE created_bar_time='' OR created_bar_time IS NULL")
    con.commit()
    return con


def get_state(market, symbol, tf):
    con = db()
    row = con.execute("SELECT data FROM states WHERE market=? AND symbol=? AND timeframe=?", (market, symbol, tf)).fetchone()
    con.close()
    try:
        return json.loads(row[0]) if row else {}
    except Exception:
        return {}


def save_state(market, symbol, tf, data):
    con = db()
    con.execute("""INSERT INTO states VALUES(?,?,?,?,?)
        ON CONFLICT(market,symbol,timeframe) DO UPDATE SET data=excluded.data,updated=excluded.updated""",
        (market, symbol, tf, json.dumps(data), time.time()))
    con.commit(); con.close()


def get_cursor(market):
    con = db(); row = con.execute("SELECT position FROM cursors WHERE market=?", (market,)).fetchone(); con.close()
    return row[0] if row else 0


def set_cursor(market, position):
    con = db()
    con.execute("INSERT INTO cursors(market,position,batch_no) VALUES(?,?,0) ON CONFLICT(market) DO UPDATE SET position=excluded.position", (market, position))
    con.commit(); con.close()


def next_batch(market):
    con = db()
    con.execute("INSERT OR IGNORE INTO cursors(market,position,batch_no) VALUES(?,0,0)", (market,))
    con.execute("UPDATE cursors SET batch_no=batch_no+1 WHERE market=?", (market,))
    n = con.execute("SELECT batch_no FROM cursors WHERE market=?", (market,)).fetchone()[0]
    con.commit(); con.close(); return n

# ----------------------------- HTTP / TELEGRAM -----------------------------
async def get_json(session, url, headers=None, params=None, retries=3):
    for attempt in range(retries):
        try:
            async with session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=25)) as r:
                body = await r.text()
                if r.status == 429:
                    await asyncio.sleep(3 * (attempt + 1)); continue
                if r.status >= 500:
                    await asyncio.sleep(2 * (attempt + 1)); continue
                if r.status >= 400:
                    log.warning("HTTP %s | %s | %s", r.status, url, body[:200]); return None
                try: return json.loads(body)
                except Exception: log.warning("Invalid JSON: %s", url); return None
        except Exception as exc:
            log.warning("HTTP error: %s", exc); await asyncio.sleep(2 * (attempt + 1))
    return None


async def telegram(session, token, chat, message):
    if not token or not chat:
        log.error("Telegram credentials missing: token/chat"); return False
    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    ok = True
    for start in range(0, len(message), 3900):
        try:
            async with session.post(url, json={"chat_id": chat, "text": message[start:start+3900], "disable_web_page_preview": True}, timeout=aiohttp.ClientTimeout(total=25)) as r:
                data = await r.json(content_type=None)
                if r.status != 200 or not data.get("ok"):
                    log.error("Telegram text failed: %s", data); ok = False
        except Exception as exc:
            log.exception("Telegram text exception: %s", exc); ok = False
    return ok


async def telegram_photo(session, token, chat, image_bytes, caption):
    if not token or not chat:
        log.error("Telegram photo credentials missing: token/chat"); return False
    form = aiohttp.FormData()
    form.add_field("chat_id", str(chat))
    form.add_field("caption", caption[:900])
    form.add_field("photo", image_bytes, filename="AI_PRO_MAX.png", content_type="image/png")
    try:
        async with session.post(f"{TELEGRAM_API}/bot{token}/sendPhoto", data=form, timeout=aiohttp.ClientTimeout(total=60)) as r:
            data = await r.json(content_type=None)
            if r.status != 200 or not data.get("ok"):
                log.error("Telegram photo failed: %s", data); return False
            return True
    except Exception as exc:
        log.exception("Telegram photo exception: %s", exc); return False


def market_credentials(market):
    if market == "US": return US_BOT, US_CHAT
    if market == "TASI": return TASI_BOT, TASI_CHAT
    return CRYPTO_BOT, CRYPTO_CHAT


async def send_market(session, market, message):
    token, chat = market_credentials(market)
    return await telegram(session, token, chat, message)

# ----------------------------- SYMBOL LISTS -----------------------------
async def get_us_symbols(session):
    if not TWELVE_KEY:
        log.error("TWELVEDATA_API_KEY is missing"); return []
    data = await get_json(session, f"{TWELVE_API}/stocks", params={"apikey": TWELVE_KEY, "format": "JSON"})
    if not data: return []
    rows = data if isinstance(data, list) else data.get("data", [])
    allowed = {"NASDAQ", "NYSE", "NYSE AMERICAN", "NYSE ARCA"}
    out, seen = [], set()
    for x in rows:
        s = str(x.get("symbol", "")).strip().upper(); ex = str(x.get("exchange", "")).strip().upper()
        country = str(x.get("country", "")).strip().lower(); currency = str(x.get("currency", "")).strip().upper()
        if not s or s in seen or country not in ("united states", "usa", "us") or currency != "USD" or ex not in allowed: continue
        seen.add(s); out.append({"symbol": s, "name": x.get("name", s), "exchange": ex})
    log.info("US universe loaded: %s", len(out)); return out


async def get_sa_symbols(session):
    if not SAHMK_KEY:
        log.error("SAHMK_API_KEY / TASI_TOKEN missing"); return []
    headers = {"X-API-Key": SAHMK_KEY}; out=[]; seen=set()
    for market in ("TASI", "NOMU"):
        offset=0
        while True:
            data = await get_json(session, f"{SAHMK_API}/companies/", headers=headers, params={"market": market, "limit": 500, "offset": offset})
            if not data: break
            rows=data.get("results", [])
            if not rows: break
            for x in rows:
                s=str(x.get("symbol", "")).strip(); status=str(x.get("status", "")).lower(); typ=str(x.get("security_type", "")).lower()
                if not s or s in seen or (status and status != "active") or typ != "equity": continue
                seen.add(s); out.append({"symbol":s,"name":x.get("name_ar") or x.get("name_en") or s,"market":market})
            offset += len(rows); total=int(data.get("total",0) or 0)
            if len(rows)<500 or (total and offset>=total): break
    log.info("Saudi universe loaded: %s",len(out)); return out


async def get_crypto_symbols(session):
    data=await get_json(session,f"{BINANCE_API}/api/v3/exchangeInfo")
    if not data: return []
    out=[]
    for x in data.get("symbols",[]):
        if x.get("status")!="TRADING" or x.get("quoteAsset") not in ("USDT","USD"): continue
        perms=x.get("permissions",[])
        if perms and "SPOT" not in perms: continue
        out.append({"symbol":x.get("symbol"),"base":x.get("baseAsset"),"quote":x.get("quoteAsset")})
    log.info("Crypto SPOT universe loaded: %s",len(out)); return out

# ----------------------------- MARKET BARS -----------------------------
def normalize_bars(rows, keys):
    out=[]
    for x in rows:
        try:
            out.append({"open":float(x[keys[0]]),"high":float(x[keys[1]]),"low":float(x[keys[2]]),"close":float(x[keys[3]]),"volume":float(x[keys[4]]),"time":str(x.get(keys[5], ""))})
        except (KeyError,TypeError,ValueError): continue
    # APIs can return newest-first; normalize to oldest-first when timestamps are comparable.
    if len(out)>1 and out[0]["time"] and out[-1]["time"] and out[0]["time"] > out[-1]["time"]: out.reverse()
    return out


async def us_bars(session,symbol,interval):
    if not SIFTING_KEY: return []
    end=datetime.now(timezone.utc); days=5 if interval in ("5m","15m") else 40
    params={"start":(end-timedelta(days=days)).strftime("%Y-%m-%d"),"end":end.strftime("%Y-%m-%d"),"interval":interval,"limit":500}
    data=await get_json(session,f"{SIFTING_API}/v1/hist/stocks/{symbol}/bars",headers={"X-API-Key":SIFTING_KEY,"Accept-Encoding":"gzip"},params=params)
    return normalize_bars(data.get("data",[]),("o","h","l","c","v","t")) if data else []


async def sa_bars(session,symbol,interval):
    if not SAHMK_KEY: return []
    imap={"5m":"5min","15m":"15min","1h":"60min","1d":"1d"}; days=30 if interval!="1d" else 180
    params={"interval":imap[interval],"from":(datetime.now()-timedelta(days=days)).strftime("%Y-%m-%d"),"to":datetime.now().strftime("%Y-%m-%d"),"limit":500}
    data=await get_json(session,f"{SAHMK_API}/historical/{symbol}/",headers={"X-API-Key":SAHMK_KEY},params=params)
    return normalize_bars(data.get("data",[]),("open","high","low","close","volume","date")) if data else []


async def crypto_bars(session,symbol,interval):
    data=await get_json(session,f"{BINANCE_API}/api/v3/klines",params={"symbol":symbol,"interval":interval,"limit":200})
    if not isinstance(data,list): return []
    out=[]
    for x in data:
        try: out.append({"open":float(x[1]),"high":float(x[2]),"low":float(x[3]),"close":float(x[4]),"volume":float(x[5]),"time":str(x[0])})
        except (ValueError,TypeError,IndexError): continue
    return out

# ----------------------------- INDICATORS -----------------------------
def ema(values,period):
    if len(values)<period:return None
    alpha=2/(period+1); value=sum(values[:period])/period
    for x in values[period:]: value=alpha*x+(1-alpha)*value
    return value


def rsi(values,period=14):
    if len(values)<period+1:return None
    changes=[values[i]-values[i-1] for i in range(1,len(values))]
    gains=[max(x,0) for x in changes]; losses=[max(-x,0) for x in changes]
    ag=sum(gains[:period])/period; al=sum(losses[:period])/period
    for i in range(period,len(gains)):
        ag=(ag*(period-1)+gains[i])/period; al=(al*(period-1)+losses[i])/period
    if al==0:return 100.0
    return 100-(100/(1+ag/al))


def atr(bars,period=14):
    if len(bars)<period+1:return None
    trs=[]
    for i in range(1,len(bars)):
        c,p=bars[i],bars[i-1]
        trs.append(max(c["high"]-c["low"],abs(c["high"]-p["close"]),abs(c["low"]-p["close"])))
    return sum(trs[-period:])/period


def vwap(bars):
    recent=bars[-30:]; vol=sum(x["volume"] for x in recent)
    if vol<=0:return None
    return sum(((x["high"]+x["low"]+x["close"])/3)*x["volume"] for x in recent)/vol


def analyze(bars):
    if len(bars)<30:return None
    closes=[x["close"] for x in bars]; vols=[x["volume"] for x in bars]
    price=closes[-1]; prev=closes[-2]; a=atr(bars)
    emas={p:ema(closes,p) for p in (10,14,25,50)}
    avg=sum(vols[-21:-1])/20 if len(vols)>=21 else 0
    ratio=vols[-1]/avg if avg>0 else 0
    support=min(x["low"] for x in bars[-30:]); resistance=max(x["high"] for x in bars[-30:])
    recent_range=max(x["high"] for x in bars[-8:])-min(x["low"] for x in bars[-8:])
    accumulation=bool(a and recent_range<=a*2.5 and ratio>=1.15)
    candle_range=max(bars[-1]["high"]-bars[-1]["low"],1e-9)
    buyer=max(0,min(100,(bars[-1]["close"]-bars[-1]["low"])/candle_range*100))
    return {"price":price,"previous":prev,"change":((price/prev)-1)*100 if prev else 0,"rsi":rsi(closes),"atr":a,"vwap":vwap(bars),"ema":emas,"volume":vols[-1],"volume_ratio":ratio,"support":support,"resistance":resistance,"accumulation":accumulation,"buyer_proxy":buyer}


def score_result(r):
    """Technical score 0-100; not a prediction or order-book reading."""
    score=0; p=r["price"]
    if r["vwap"] is not None and p>r["vwap"]: score+=20
    valid=[v for v in r["ema"].values() if v is not None]
    if valid: score+=25*sum(p>v for v in valid)/len(valid)
    if r["rsi"] is not None:
        if 50<=r["rsi"]<=70: score+=20
        elif 40<=r["rsi"]<50: score+=10
    if r["volume_ratio"]>=2: score+=20
    elif r["volume_ratio"]>=1.2: score+=12
    if r["change"]>0: score+=10
    if r["accumulation"]: score+=5
    return round(min(100,score))

# ----------------------------- SIGNALS AND TARGETS -----------------------------
def active_targets(market,symbol,tf):
    con=db(); rows=con.execute("SELECT target_no,target_price,hit,entry_price,created_bar_time,stop_price,status FROM targets WHERE market=? AND symbol=? AND timeframe=? ORDER BY target_no",(market,symbol,tf)).fetchall(); con.close()
    return rows


def create_signal_targets(market,symbol,tf,price,current_atr,bar_time):
    if not current_atr or current_atr<=0:return False
    con=db()
    active=con.execute("SELECT COUNT(*) FROM targets WHERE market=? AND symbol=? AND timeframe=? AND status='ACTIVE'",(market,symbol,tf)).fetchone()[0]
    if active:
        con.close(); return False
    # Start a fresh signal cycle only after the previous one is closed.
    con.execute("DELETE FROM targets WHERE market=? AND symbol=? AND timeframe=?",(market,symbol,tf))
    stop=price-current_atr*1.5
    now=time.time()
    for n in range(1,21):
        target=price+current_atr*0.5*n
        con.execute("INSERT INTO targets(market,symbol,timeframe,target_no,target_price,hit,created,entry_price,created_bar_time,stop_price,status) VALUES(?,?,?,?,?,0,?,?,?,?, 'ACTIVE')",
                    (market,symbol,tf,n,target,now,price,str(bar_time or ""),stop))
    con.commit();con.close();return True


def update_signal_targets(market,symbol,tf,bar):
    """Only bars strictly later than the signal bar can confirm target/stop."""
    con=db()
    rows=con.execute("SELECT target_no,target_price,created_bar_time,stop_price,status FROM targets WHERE market=? AND symbol=? AND timeframe=? AND hit=0 AND status='ACTIVE' ORDER BY target_no",(market,symbol,tf)).fetchall()
    if not rows:con.close();return [],False
    bar_time=str(bar.get("time", "")); hits=[]; stopped=False
    # If no reliable bar timestamp exists, do not confirm targets from that bar.
    for n,target,created_time,stop,status in rows:
        if not bar_time or not created_time or bar_time<=created_time: continue
        if bar["low"]<=stop:
            con.execute("UPDATE targets SET status='STOPPED' WHERE market=? AND symbol=? AND timeframe=? AND status='ACTIVE'",(market,symbol,tf))
            stopped=True;break
        if bar["high"]>=target:
            con.execute("UPDATE targets SET hit=1 WHERE market=? AND symbol=? AND timeframe=? AND target_no=?",(market,symbol,tf,n))
            hits.append((n,target))
    remaining=con.execute("SELECT COUNT(*) FROM targets WHERE market=? AND symbol=? AND timeframe=? AND status='ACTIVE' AND hit=0",(market,symbol,tf)).fetchone()[0]
    if remaining==0 and not stopped:
        con.execute("UPDATE targets SET status='COMPLETED' WHERE market=? AND symbol=? AND timeframe=?",(market,symbol,tf))
    con.commit();con.close();return hits,stopped


def signal_events(market,symbol,tf,r):
    old=get_state(market,symbol,tf); events=[]; p=r["price"]
    if old:
        old_ema=old.get("ema",{})
        for period,value in r["ema"].items():
            was=old_ema.get(str(period)); now=(p>=value) if value is not None else None
            if was is not None and now is not None and was!=now:
                events.append(f"{'🟢 اختراق' if now else '🔴 كسر'} EMA{period}")
        old_rsi=old.get("rsi"); cur=r["rsi"]
        if old_rsi is not None and cur is not None:
            for z in (20,40,50,60,70,80):
                if old_rsi<z<=cur:events.append(f"🟢 RSI اخترق {z}")
                elif old_rsi>z>=cur:events.append(f"🔴 RSI كسر {z}")
        if r["volume_ratio"]>=1.5>old.get("volume_ratio",0):events.append("💹 نشاط فوليوم مرتفع")
        if r["accumulation"] and not old.get("accumulation",False):events.append("🟡 نطاق تجميع محتمل — ليس دليلاً مؤسسياً")
        ov=old.get("vwap")
        if r["vwap"] and ov:
            if old.get("price",p)<ov and p>=r["vwap"]:events.append("🟢 استعادة VWAP")
            elif old.get("price",p)>ov and p<=r["vwap"]:events.append("🔴 فقد VWAP")
    save_state(market,symbol,tf,{"price":p,"rsi":r["rsi"],"vwap":r["vwap"],"ema":{str(k):(p>=v if v is not None else None) for k,v in r["ema"].items()},"volume_ratio":r["volume_ratio"],"accumulation":r["accumulation"]})
    return events

# ----------------------------- IMAGE DASHBOARD -----------------------------
W,H=1200,1800
BG="#080B13"; PANEL="#111725"; GREEN="#20F477"; RED="#FF465A"; YELLOW="#FFD43B"; WHITE="#F4F6FF"; GRAY="#AAB4C8"; BLUE="#27B9FF"

def ar(text):
    try:return get_display(arabic_reshaper.reshape(str(text)))
    except Exception:return str(text)


def get_font(size,bold=False):
    candidates=(
        ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf","/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"] if bold else
        ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf","/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"])
    for path in candidates:
        try:return ImageFont.truetype(path,size)
        except Exception:pass
    return ImageFont.load_default()


def dashboard_image(market,item,tf,r,score,signal_created=False):
    img=Image.new("RGB",(W,H),BG);d=ImageDraw.Draw(img)
    ft=get_font(48,True);fb=get_font(112,True);fl=get_font(43,True);fn=get_font(32);fs=get_font(26);fsmall=get_font(22)
    symbol=item["symbol"];name=str(item.get("name",symbol))[:38]
    currency="$" if market in ("US","CRYPTO") else "⃁"
    col=GREEN if r["change"]>0 else RED if r["change"]<0 else YELLOW
    direction="صاعد" if r["change"]>0 else "هابط" if r["change"]<0 else "مستقر"
    def center(y,text,font=fn,fill=WHITE):d.text((W//2,y),text,font=font,fill=fill,anchor="mm")
    d.rounded_rectangle((12,12,W-12,H-12),radius=38,outline="#536078",width=3)
    d.rounded_rectangle((30,28,W-30,155),radius=28,fill=PANEL,outline="#344158",width=2)
    center(78,"💀 AI PRO MAX 💀 🚀",ft,WHITE)
    market_name={"US":"🇺🇸 السوق الأمريكي","TASI":"🇸🇦 السوق السعودي","CRYPTO":"₿ العملات الرقمية"}.get(market,market)
    center(128,ar(market_name),fn,WHITE)
    d.rounded_rectangle((930,42,1135,112),radius=30,fill="#07552A",outline=GREEN,width=3)
    d.text((1032,77),"● LIVE",font=fl,fill=WHITE,anchor="mm")
    center(205,ar(name),fn,WHITE);center(255,f"({symbol})",fl,GREEN)
    center(385,f"{score}/100",fb,GREEN)
    center(470,ar("قوة الإشارة الفنية التقديرية"),fn,WHITE)
    d.rounded_rectangle((65,510,1135,535),radius=12,fill="#293342")
    d.rounded_rectangle((65,510,65+int(1070*score/100),535),radius=12,fill=GREEN)
    # Main stats: four rows, two columns.
    d.rounded_rectangle((40,565,1160,890),radius=25,fill=PANEL,outline="#39465C",width=2)
    stats=[("السعر الحالي",f"{currency}{r['price']:.4f}",GREEN),("التغير",f"{r['change']:+.2f}%",col),("حجم التداول",f"{r['volume']:,.0f}",WHITE),("نشاط الفوليوم",f"{r['volume_ratio']:.2f}x",BLUE),("الحالة",direction,col),("الفاصل",tf,YELLOW),("VWAP",f"{currency}{r['vwap']:.4f}" if r['vwap'] is not None else "غير متاح",BLUE),("RSI",f"{r['rsi']:.1f}" if r['rsi'] is not None else "غير متاح",WHITE)]
    for i,(label,value,color) in enumerate(stats):
        c=i%2;row=i//2;x=320 if c==0 else 880;y=600+row*70
        d.text((x,y),ar(label),font=fs,fill=GRAY,anchor="mm")
        d.text((x,y+34),value,font=fn,fill=color,anchor="mm")
    d.line((55,920,1145,920),fill="#586078",width=2)
    center(965,"EMA 10 / 14 / 25 / 50",fl,WHITE)
    for i,p in enumerate((10,14,25,50)):
        v=r["ema"].get(p);ok=v is not None and r["price"]>=v;x=155+i*295
        d.rounded_rectangle((x-115,1000,x+115,1100),radius=20,fill="#10251C" if ok else "#32151C",outline=GREEN if ok else RED,width=3)
        d.text((x,1035),f"EMA{p}",font=fs,fill=WHITE,anchor="mm")
        d.text((x,1075),"✓" if ok else "✕",font=fl,fill=GREEN if ok else RED,anchor="mm")
    d.line((55,1130,1145,1130),fill="#586078",width=2)
    d.text((310,1175),ar("الدعم"),font=fn,fill=GREEN,anchor="mm")
    d.text((310,1225),f"{currency}{r['support']:.4f}",font=fl,fill=GREEN,anchor="mm")
    d.text((890,1175),ar("المقاومة"),font=fn,fill=RED,anchor="mm")
    d.text((890,1225),f"{currency}{r['resistance']:.4f}",font=fl,fill=RED,anchor="mm")
    d.line((55,1270,1145,1270),fill="#586078",width=2)
    center(1310,ar("الأهداف — 20 مستوى"),fl,YELLOW)
    targets=active_targets(market,symbol,tf);tmap={n:(price,hit,status) for n,price,hit,entry,ct,stop,status in targets}
    for n in range(1,21):
        c=(n-1)%5;row=(n-1)//5;x=55+c*222;y=1355+row*75
        tp,hit,status=tmap.get(n,(0,0,"PENDING"))
        is_hit=bool(hit);stopped=status=="STOPPED"
        outline=GREEN if is_hit else RED if stopped else "#586078"
        label=f"{n}  {'✓' if is_hit else '×' if stopped else '○'}"
        d.rounded_rectangle((x,y,x+195,y+58),radius=15,fill="#17202D",outline=outline,width=3)
        d.text((x+97,y+29),label,font=fn,fill=GREEN if is_hit else RED if stopped else WHITE,anchor="mm")
    center(1685,ar("التجميع المحتمل: "+("ظاهر فنياً" if r["accumulation"] else "غير ظاهر")),fs,YELLOW if r["accumulation"] else GRAY)
    center(1730,ar(f"قوة المشترين التقديرية: {r['buyer_proxy']:.1f}% — ليست دفتر أوامر"),fsmall,BLUE)
    stamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    center(1770,ar("وقت الفحص: "+stamp),fsmall,GRAY)
    out=io.BytesIO();img.save(out,format="PNG",optimize=True);return out.getvalue()

# ----------------------------- SCANNING -----------------------------
async def scan_one(session,market,item):
    symbol=item["symbol"];reports=[]
    for tf in TIMEFRAMES:
        try:
            if market=="US":bars=await us_bars(session,symbol,tf)
            elif market=="TASI":bars=await sa_bars(session,symbol,tf)
            else:bars=await crypto_bars(session,symbol,tf)
            if len(bars)<30:continue
            r=analyze(bars)
            if not r or (market=="US" and r["price"]<US_MIN_PRICE):continue
            score=score_result(r)
            events=signal_events(market,symbol,tf,r)
            hits,stopped=update_signal_targets(market,symbol,tf,bars[-1])
            active=active_targets(market,symbol,tf)
            active_exists=any(x[6]=="ACTIVE" for x in active)
            created=False
            # Open a new target ladder only on a strong technical setup, and only if no active ladder exists.
            if score>=70 and not active_exists:
                created=create_signal_targets(market,symbol,tf,r["price"],r["atr"],bars[-1].get("time",""))
            # Send first qualified signal, a new technical event, target hit, or stop event.
            if created or events or hits or stopped:
                reports.append({"item":item,"tf":tf,"result":r,"score":score,"events":events,"hits":hits,"stopped":stopped,"created":created})
        except Exception as exc:
            log.exception("Scan error %s %s %s: %s",market,symbol,tf,exc)
    return reports


async def process_market(session,market,symbols):
    if not symbols:log.warning("%s universe empty",market);return
    start=get_cursor(market);end=min(start+BATCH_SIZE,len(symbols));batch=symbols[start:end]
    if not batch:start=0;end=min(BATCH_SIZE,len(symbols));batch=symbols[start:end]
    sem=asyncio.Semaphore(WORKERS)
    async def limited(item):
        async with sem:return await scan_one(session,market,item)
    results=await asyncio.gather(*(limited(x) for x in batch),return_exceptions=True)
    reports=[]
    for x in results:
        if isinstance(x,list):reports.extend(x)
        elif isinstance(x,Exception):log.error("%s batch error: %s",market,x)
    set_cursor(market,0 if end>=len(symbols) else end)
    batch_no=next_batch(market)
    if reports:
        token,chat=market_credentials(market)
        for report in reports:
            r=report["result"];item=report["item"];tf=report["tf"]
            image=dashboard_image(market,item,tf,r,report["score"])
            caption=(f"💀🚀 AI PRO MAX — {market}\n📡 الدفعة: {batch_no} | {item['symbol']} | {tf}\n"
                     f"السعر: {r['price']:.6f} | التقييم الفني: {report['score']}/100\n"
                     f"{('✅ أهداف جديدة: '+str(len(report['hits']))) if report['hits'] else ''}"
                     f"{' | 🛑 وقف الخسارة' if report['stopped'] else ''}\n"
                     "القوة تقديرية وليست قراءة دفتر أوامر. التحليل آلي وليس توصية.")
            await telegram_photo(session,token,chat,image,caption)
            await asyncio.sleep(1)
    log.info("%s scanned %s/%s | image_reports=%s | batch=%s",market,end,len(symbols),len(reports),batch_no)

# ----------------------------- MAIN LOOP -----------------------------
async def main():
    connector=aiohttp.TCPConnector(limit=WORKERS+8,ttl_dns_cache=300)
    timeout=aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(connector=connector,timeout=timeout) as session:
        for market in ("US","TASI","CRYPTO"):
            await send_market(session,market,
                f"💀🚀 {APP}\n✅ تم تشغيل لوحة الصور للسوق {market}\n🟢 فحص مستمر 24/7\n"
                f"⏱️ دورة الفحص: {SCAN_SECONDS} ثانية\n📡 الدفعات: {BATCH_SIZE} رمز\n"
                "🖼️ التقارير الفنية ترسل كصور واضحة")
        universes={"US":[],"TASI":[],"CRYPTO":[]};last_refresh=0
        while True:
            try:
                if time.time()-last_refresh>=21600:
                    log.info("Refreshing symbol universes")
                    us,sa,crypto=await asyncio.gather(get_us_symbols(session),get_sa_symbols(session),get_crypto_symbols(session))
                    if us:universes["US"]=us
                    if sa:universes["TASI"]=sa
                    if crypto:universes["CRYPTO"]=crypto
                    last_refresh=time.time()
                    for market,items in universes.items():
                        await send_market(session,market,f"📡 تحديث قائمة {market}\nالرموز المتاحة: {len(items):,}\n🟢 نظام الفحص مستمر")
                await process_market(session,"US",universes["US"])
                await process_market(session,"TASI",universes["TASI"])
                await process_market(session,"CRYPTO",universes["CRYPTO"])
                log.info("NEXT SCAN IN %s SECONDS",SCAN_SECONDS)
                await asyncio.sleep(SCAN_SECONDS)
            except asyncio.CancelledError:raise
            except Exception:log.exception("MAIN LOOP ERROR");await asyncio.sleep(15)

if __name__=="__main__":
    try:asyncio.run(main())
    except KeyboardInterrupt:log.info("Bot stopped manually")