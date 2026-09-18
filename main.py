# AI PRO MAX — FINAL HYBRID
# TASI -> Twelve Data | US + Crypto -> SiftingIO
# Railway: use environment variables, never hard-code secrets.

import os, time, json, queue, threading, random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, local
import requests

CHAT_ID = os.getenv("CHAT_ID", "").strip()
TASI_TOKEN = os.getenv("TASI_TOKEN", "").strip()
US_TOKEN = os.getenv("US_TOKEN", "").strip()
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN", "").strip()
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "").strip()
SIFTING_API_KEY = os.getenv("SIFTING_API_KEY", "").strip()
SAHMK_API_KEY = os.getenv("SAHMK_API_KEY", "").strip()

TD_BASE = "https://api.twelvedata.com"
SF_BASE = "https://api.sifting.io/v1"
SAHMK_BASE = "https://api.sahmk.sa/api/v1"

MAX_WORKERS = 4
TD_GAP = 0.35
SF_GAP = 0.05
MAX_RETRIES = 3
SCAN_INTERVAL = 120
CACHE_TTL = 21600
MIN_US_PRICE = 0.15
US_MAX_SYMBOLS = None  # no numeric cap
TASI_MAX_SYMBOLS = None  # no numeric cap
OUTPUTSIZE = 220
TIMEFRAMES = ("5min", "15min", "30min", "1h", "4h")
SF_TF = {"5min":"5m", "15min":"15m", "30min":"30m", "1h":"1h", "4h":"1h"}
ATR_MULT = [1, 1.5, 2, 2.5, 3, 3.5, 4, 5]
MIN_SCORE = 60

POSITIVE = ("beat","beats","growth","profit","profits","upgrade","upgraded","buy",
            "strong","positive","partnership","contract","approval","revenue","surge","record")
NEGATIVE = ("loss","losses","downgrade","downgraded","sell","weak","negative","lawsuit",
            "decline","drop","warning","debt","offering","investigation","risk")

td_local, sf_local, sahmk_local = local(), local(), local()
td_lock, sf_lock, sahmk_lock = Lock(), Lock(), Lock()
td_last = [0.0]
sf_last = [0.0]
sahmk_last = [0.0]
state_lock = Lock()
last_signal = {}
trend_state = {}
cache_lock = Lock()
symbol_cache = {
    "TASI":{"symbols":[],"updated":0},
    "US":{"symbols":[],"updated":0},
    "CRYPTO":{"symbols":[],"updated":0},
}
TG_QUEUE = queue.Queue(maxsize=5000)

def session_for(obj):
    s = getattr(obj, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent":"AI-PRO-MAX/Final","Accept-Encoding":"gzip"})
        a = requests.adapters.HTTPAdapter(pool_connections=6, pool_maxsize=6, max_retries=0)
        s.mount("https://", a)
        s.mount("http://", a)
        obj.session = s
    return s

def wait_rate(lock, holder, gap):
    with lock:
        now = time.monotonic()
        wait = gap - (now - holder[0])
        if wait > 0: time.sleep(wait)
        holder[0] = time.monotonic()

def api_get(base, path, key, params, local_obj, lock, holder, gap):
    if not key: return None
    s = session_for(local_obj)
    headers = {"X-API-Key":key,"Accept-Encoding":"gzip"} if base == SF_BASE else {}
    p = dict(params or {})
    if base == TD_BASE: p["apikey"] = key
    for attempt in range(MAX_RETRIES):
        try:
            wait_rate(lock, holder, gap)
            r = s.get(base + path, params=p, headers=headers, timeout=(10,30))
            if r.status_code == 429:
                ra = r.headers.get("Retry-After")
                try: delay = float(ra)
                except Exception: delay = min(10,2**attempt)
                time.sleep(delay); continue
            if r.status_code in (500,502,503,504):
                time.sleep(min(10,2**attempt)); continue
            if r.status_code != 200:
                return None
            data = r.json()
            if isinstance(data,dict) and str(data.get("status","")).lower()=="error": return None
            return data
        except (requests.Timeout,requests.ConnectionError):
            if attempt < MAX_RETRIES-1: time.sleep(min(10,2**attempt))
            else: return None
        except Exception:
            return None
    return None

def td(path, params=None):
    return api_get(TD_BASE,path,TWELVEDATA_API_KEY,params,td_local,td_lock,td_last,TD_GAP)

def sf(path, params=None):
    return api_get(SF_BASE,path,SIFTING_API_KEY,params,sf_local,sf_lock,sf_last,SF_GAP)

def sahmk(path, params=None):
    if not SAHMK_API_KEY: return None
    s=session_for(sahmk_local)
    p=dict(params or {})
    for attempt in range(MAX_RETRIES):
        try:
            wait_rate(sahmk_lock,sahmk_last,0.75)
            r=s.get(SAHMK_BASE+path,params=p,headers={"X-API-Key":SAHMK_API_KEY},timeout=(10,30))
            if r.status_code==429:
                time.sleep(min(30,2**attempt)); continue
            if r.status_code in (500,502,503,504):
                time.sleep(min(10,2**attempt)); continue
            if r.status_code!=200: return None
            d=r.json()
            if isinstance(d,dict) and d.get("error"): return None
            return d
        except (requests.Timeout,requests.ConnectionError):
            if attempt<MAX_RETRIES-1: time.sleep(min(10,2**attempt))
            else: return None
        except Exception: return None
    return None

# ---------- indicators ----------

def ema(v,n):
    if len(v)<n:return None
    x=sum(v[:n])/n; a=2/(n+1)
    for z in v[n:]: x=(z-x)*a+x
    return x

def rsi(v,n=14):
    if len(v)<n+1:return None
    g=[];l=[]
    for i in range(1,len(v)):
        d=v[i]-v[i-1];g.append(max(d,0));l.append(max(-d,0))
    ag=sum(g[:n])/n; al=sum(l[:n])/n
    for i in range(n,len(g)):
        ag=((ag*(n-1))+g[i])/n; al=((al*(n-1))+l[i])/n
    return 100 if al==0 else 100-(100/(1+ag/al))

def atr(h,l,c,n=14):
    if len(c)<n+1:return None
    tr=[max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1])) for i in range(1,len(c))]
    x=sum(tr[:n])/n
    for z in tr[n:]:x=((x*(n-1))+z)/n
    return x

def vwap(h,l,c,v):
    pv=vv=0
    for a,b,x,z in zip(h,l,c,v):
        if z>0: pv+=((a+b+x)/3)*z;vv+=z
    return pv/vv if vv else None

def vol_ratio(v):
    if len(v)<21:return 1
    a=sum(v[-21:-1])/20
    return v[-1]/a if a>0 else 1

def trend(c):
    x=[z["close"] for z in c]
    e10,e14,e15,e25,e50=[ema(x,n) for n in (10,14,15,25,50)]
    if None in (e10,e14,e15,e25,e50):return "NEUTRAL"
    bull=sum((e10>e14,e14>e15,e15>e25,e25>e50,x[-1]>e50))
    bear=sum((e10<e14,e14<e15,e15<e25,e25<e50,x[-1]<e50))
    return "UP" if bull>=3 else "DOWN" if bear>=3 else "NEUTRAL"

def ars(c):
    x=[z["close"] for z in c]
    e10,e14,e25,e50=[ema(x,n) for n in (10,14,25,50)]
    if None in (e10,e14,e25,e50):return 50
    s=50+(15 if e10>e14 else -15)+(15 if e14>e25 else -15)+(10 if x[-1]>e50 else -10)
    return max(20,min(100,s))

def golden(c):
    if len(c)<30:return False
    x=[z["close"] for z in c];v=[z["volume"] for z in c]
    z=c[-1];p=c[-2];e10,e25=ema(x,10),ema(x,25);rv=rsi(x)
    av=sum(v[-21:-1])/20 if len(v)>=21 else 0
    rng=z["high"]-z["low"];body=abs(z["close"]-z["open"])
    return (z["close"]>z["open"] and rng>0 and body/rng>=.45 and e10 and e25 and
            e10>e25 and z["close"]>e10 and rv is not None and rv>=50 and
            (av<=0 or z["volume"]>=av*1.10) and z["close"]>p["high"])

def hidden_div(c):
    if len(c)<60:return False,False
    x=[z["close"] for z in c];rr=[rsi(x[:i+1]) for i in range(len(x))]
    lo=[];hi=[]
    for i in range(5,len(c)-5):
        if c[i]["low"]==min(z["low"] for z in c[i-5:i+6]):lo.append(i)
        if c[i]["high"]==max(z["high"] for z in c[i-5:i+6]):hi.append(i)
    hb=hs=False
    if len(lo)>=2 and rr[lo[-1]] is not None and rr[lo[-2]] is not None:
        a,b=lo[-2],lo[-1];hb=c[b]["low"]>c[a]["low"] and rr[b]<rr[a]
    if len(hi)>=2 and rr[hi[-1]] is not None and rr[hi[-2]] is not None:
        a,b=hi[-2],hi[-1];hs=c[b]["high"]<c[a]["high"] and rr[b]>rr[a]
    return hb,hs

def surge_info(c, a, up):
    """Detect an unusually fast move and adapt the 8 ATR targets.
    This is a technical proxy only; it does not identify a market maker/fund.
    """
    if not c or len(c)<30 or not a or a<=0:
        return {"active":False,"score":0,"factor":1.0,"volume_ratio":1.0,"atr_ratio":1.0,"body_pct":0.0,"breakout":False}
    z=c[-1]; prev=c[-2]; rng=max(z["high"]-z["low"],0.0)
    body=abs(z["close"]-z["open"])
    body_pct=(body/z["open"]*100) if z["open"] else 0.0
    vr=vol_ratio([x["volume"] for x in c])
    # Compare current ATR with recent ATR values.
    atrs=[]
    h=[x["high"] for x in c]; l=[x["low"] for x in c]; cl=[x["close"] for x in c]
    for i in range(max(15,len(c)-30),len(c)+1):
        if i<=len(c) and i>=15:
            aa=atr(h[:i],l[:i],cl[:i],14)
            if aa and aa>0: atrs.append(aa)
    avg_atr=sum(atrs[:-1])/len(atrs[:-1]) if len(atrs)>1 else a
    atr_ratio=a/avg_atr if avg_atr>0 else 1.0
    recent_high=max(x["high"] for x in c[-21:-1])
    recent_low=min(x["low"] for x in c[-21:-1])
    breakout=(z["close"]>recent_high) if up else (z["close"]<recent_low)
    score=0
    score += min(35, max(0,(vr-1.0)*14))
    score += min(30, max(0,(atr_ratio-1.0)*30))
    score += min(25, max(0,(body_pct-0.75)*12))
    score += 10 if breakout else 0
    score=int(max(0,min(100,round(score))))
    active=bool(score>=65 and vr>=1.8 and atr_ratio>=1.10 and body_pct>=0.75 and breakout)
    # Expand target spacing progressively, capped to avoid absurd targets.
    factor=1.0
    if active:
        factor=min(2.50,1.0+(score-65)/35*1.50)
    return {"active":active,"score":score,"factor":factor,"volume_ratio":vr,
            "atr_ratio":atr_ratio,"body_pct":body_pct,"breakout":breakout}

def targets(price,a,up,surge_factor=1.0):
    if not a or a<=0:return []
    return [price+(a*m*surge_factor if up else -a*m*surge_factor) for m in ATR_MULT]

# ---------- data ----------

def td_candles(data):
    if not isinstance(data,dict) or not data.get("values"):return None,""
    out=[]
    for x in reversed(data["values"]):
        try:out.append({"datetime":x.get("datetime"),"open":float(x["open"]),"high":float(x["high"]),
                        "low":float(x["low"]),"close":float(x["close"]),
                        "volume":float(x.get("volume",0) or 0)})
        except Exception:pass
    return (out if len(out)>=60 else None),str((data.get("meta") or {}).get("name") or "")

def sf_candles(data):
    if not isinstance(data,dict):
        return None,""
    rows=data.get("data",[])
    if isinstance(rows,dict):
        rows=rows.get("data",[]) if isinstance(rows.get("data",[]),list) else list(rows.values())
    if not isinstance(rows,list):
        return None,""
    meta=data.get("meta") if isinstance(data.get("meta"),dict) else {}
    name=str(meta.get("symbol") or "")
    out=[]
    for x in rows:
        if not isinstance(x,dict):
            continue
        try:
            ts=x.get("t")
            if ts is None:
                continue
            out.append({"datetime":int(float(ts)),"open":float(x["o"]),"high":float(x["h"]),
                        "low":float(x["l"]),"close":float(x["c"]),
                        "volume":float(x.get("v",0) or 0)})
        except (TypeError,ValueError,KeyError):
            continue
    out.sort(key=lambda z:z["datetime"])
    return (out[-OUTPUTSIZE:] if len(out)>=60 else None),name

def get_tasi(symbol,tf):
    return td_candles(td("/time_series",{"symbol":symbol,"interval":tf,"outputsize":OUTPUTSIZE,"format":"JSON"}))

def get_sf(asset,symbol,tf):
    native=SF_TF[tf]
    # SiftingIO historical bars require gzip and currently allow up to 2000 rows/page.
    # Keep the requested window below that ceiling while still providing enough bars
    # for RSI/ATR/hidden-divergence calculations.
    from datetime import timedelta
    days_by_tf = {"5m": 6, "15m": 15, "30m": 30, "1h": 60}
    days = days_by_tf.get(native, 120)
    start_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    params={"interval":native,"start":start_date,"limit":2000}
    raw=sf(f"/hist/{asset}/{symbol}/bars",params)
    if not raw:
        # Provider fallback: keep the universe open and use Twelve Data if
        # SiftingIO does not carry this particular ETF/ADR/security.
        td_interval = {"5m":"5min","15m":"15min","30m":"30min","1h":"1h"}.get(native,native)
        td_data=td("/time_series",{"symbol":symbol,"interval":td_interval,"outputsize":OUTPUTSIZE,"format":"JSON"})
        return td_candles(td_data)
    c,n=sf_candles(raw)
    if not c:
        return None,n
    if tf=="4h":
        out=[];bucket=None;cur=None
        for z in c:
            b=int(z["datetime"])//3600000//4
            if b!=bucket:
                if cur:out.append(cur)
                bucket=b;cur=dict(z)
            else:
                cur["high"]=max(cur["high"],z["high"]);cur["low"]=min(cur["low"],z["low"])
                cur["close"]=z["close"];cur["volume"]+=z["volume"]
        if cur:out.append(cur)
        c=out
    return c[-OUTPUTSIZE:],n

TASI_QUOTE_CACHE={}
TASI_QUOTE_TTL=900

def current_price_tasi(symbol):
    now=time.time()
    old=TASI_QUOTE_CACHE.get(symbol)
    if old and now-old[0]<TASI_QUOTE_TTL:
        return old[1]
    d=sahmk(f"/quote/{symbol}/",{"data_mode":"delayed"})
    try:
        price=float(d["price"]) if isinstance(d,dict) and d.get("price") is not None else None
    except Exception:
        price=None
    if price is not None:
        TASI_QUOTE_CACHE[symbol]=(now,price)
    return price

def current_price_sf(asset,symbol):
    d=sf(f"/last/trade/{asset}/{symbol}")
    try:return float(d["p"]) if isinstance(d,dict) and d.get("p") is not None else None
    except Exception:return None

def current_price_td(symbol):
    d=td("/quote",{"symbol":symbol})
    try:
        return float(d["close"]) if isinstance(d,dict) and d.get("close") is not None else None
    except Exception:
        return None


def symbols_td(data):
    rows=data.get("data",[]) if isinstance(data,dict) else data if isinstance(data,list) else []
    return [str(x["symbol"]).strip() for x in rows
            if isinstance(x,dict) and x.get("symbol")]

def _paged_td_catalog(path, base_params=None, page_size=5000):
    """Return the complete catalog available from Twelve Data, without sorting or slicing."""
    base_params=dict(base_params or {})
    out=[]; seen=set(); page=1
    while True:
        params=dict(base_params)
        params["page"]=page
        params["outputsize"]=page_size
        data=td(path,params)
        rows=data.get("data",[]) if isinstance(data,dict) else []
        if not isinstance(rows,list) or not rows:
            break
        added=0
        for row in rows:
            if not isinstance(row,dict):
                continue
            sym=str(row.get("symbol","")).strip().upper()
            if not sym or sym in seen:
                continue
            seen.add(sym); out.append(sym); added += 1
        print(f"[CATALOG {path}] page={page} +{added} total={len(out)}")
        if len(rows) < page_size:
            break
        page += 1
        if page > 10000:
            break
    return out

def load_tasi():
    data=sahmk("/companies/",{"market":"TASI","limit":2000,"offset":0})
    rows=data.get("results",[]) if isinstance(data,dict) else []
    syms=[]; seen=set()
    for x in rows:
        if not isinstance(x,dict): continue
        sym=str(x.get("symbol","")).strip().upper()
        if not sym or sym in seen: continue
        if str(x.get("market","" )).upper()=="TASI" and str(x.get("status","active")).lower()=="active":
            seen.add(sym); syms.append(sym)
    if not syms:
        data=td("/stocks",{"country":"Saudi Arabia"})
        rows=data.get("data",[]) if isinstance(data,dict) else []
        for x in rows:
            if isinstance(x,dict) and x.get("symbol"):
                sym=str(x["symbol"]).strip().upper()
                if sym not in seen: seen.add(sym); syms.append(sym)
    random.shuffle(syms)
    print(f"[TASI] FULL OPEN catalog total={len(syms)} | randomized scan order")
    return syms

def load_us():
    # FULL US UNIVERSE: ask the provider for ALL US instruments in its catalog.
    # Do not restrict by type and do not take the first N symbols.
    # The dedicated ETF catalog is merged as a second safety net.
    all_symbols=[]; seen=set(); page=1
    while True:
        data=td("/stocks",{"country":"United States","page":page,"outputsize":5000})
        part=data.get("data",[]) if isinstance(data,dict) else []
        if not isinstance(part,list) or not part:
            break
        added=0
        for row in part:
            if not isinstance(row,dict):
                continue
            sym=str(row.get("symbol","")).strip().upper()
            if sym and sym not in seen:
                seen.add(sym); all_symbols.append(sym); added += 1
        print(f"[US] stocks page={page} +{added} total={len(all_symbols)}")
        if len(part)<5000:
            break
        page += 1
        if page>10000:
            break

    # Dedicated ETF catalog.
    page=1
    while True:
        data=td("/etfs",{"country":"United States","page":page,"outputsize":5000})
        part=data.get("data",[]) if isinstance(data,dict) else []
        if not isinstance(part,list) or not part:
            break
        added=0
        for row in part:
            if isinstance(row,dict) and row.get("symbol"):
                sym=str(row["symbol"]).strip().upper()
                if sym and sym not in seen:
                    seen.add(sym); all_symbols.append(sym); added += 1
        print(f"[US] ETFs page={page} +{added} total={len(all_symbols)}")
        if len(part)<5000:
            break
        page += 1
        if page>10000:
            break

    # IMPORTANT: do not scan A-Z in every cycle. Shuffle the complete universe
    # so expensive/large-cap symbols cannot monopolize the beginning of every cycle.
    random.shuffle(all_symbols)
    print(f"[US] FULL OPEN catalog total={len(all_symbols)} | price floor >= ${MIN_US_PRICE:.2f} | randomized scan order")
    return all_symbols

def load_crypto():
    # OPEN CRYPTO UNIVERSE: paginate the entire provider catalog and do not
    # restrict to USD pairs. Symbols are normalized only for the analysis API.
    out=[]; seen=set(); page=1
    while True:
        data=td("/cryptocurrencies",{"page":page,"outputsize":5000})
        rows=data.get("data",[]) if isinstance(data,dict) else []
        if not isinstance(rows,list) or not rows: break
        for row in rows:
            if not isinstance(row,dict) or not row.get("symbol"): continue
            sym=str(row["symbol"]).strip().upper().replace("/","")
            if sym and sym not in seen:
                seen.add(sym); out.append(sym)
        print(f"[CRYPTO] page={page} total={len(out)}")
        if len(rows)<5000: break
        page += 1
        if page>10000: break
    random.shuffle(out)
    print(f"[CRYPTO] FULL OPEN catalog total={len(out)} | randomized scan order")
    return out

def get_symbols(market,loader):
    now=time.time()
    with cache_lock:
        c=symbol_cache[market]
        if c["symbols"] and now-c["updated"]<CACHE_TTL:return list(c["symbols"])
    x=loader()
    if x:
        with cache_lock:symbol_cache[market]={"symbols":list(x),"updated":now}
    return x

# ---------- corporate actions / ownership ----------
SPLIT_CACHE={"rows":[],"updated":0}
OWNERSHIP_CACHE={}
SPLIT_SENT=set()
SPLIT_TTL=21600
OWNERSHIP_TTL=86400

def refresh_split_calendar():
    now=time.time()
    if now-SPLIT_CACHE["updated"]<SPLIT_TTL:
        return SPLIT_CACHE["rows"]
    today=datetime.utcnow().strftime("%Y-%m-%d")
    end=(datetime.utcnow()+__import__('datetime').timedelta(days=7)).strftime("%Y-%m-%d")
    d=td("/splits_calendar",{"start_date":today,"end_date":end,"outputsize":500})
    rows=d if isinstance(d,list) else d.get("data",[]) if isinstance(d,dict) else []
    SPLIT_CACHE.update({"rows":rows,"updated":now})
    return rows

def split_for_symbol(symbol):
    for row in refresh_split_calendar():
        if str(row.get("symbol","")).upper()==symbol.upper():
            return row
    return None

def institutional_activity(symbol):
    now=time.time(); old=OWNERSHIP_CACHE.get(symbol)
    if old and now-old[0]<OWNERSHIP_TTL:
        return old[1]
    d=sf(f"/fnd/stocks/{symbol}/ownership",{"limit":25})
    rows=d.get("data",[]) if isinstance(d,dict) else []
    # 13D/13G is beneficial ownership, not live trading.
    info="⚪ لا توجد حركة مؤسسية جديدة موثقة"
    if rows:
        latest=rows[0]
        form=str(latest.get("form","")).upper()
        filed=latest.get("filed_at") or latest.get("filing_date") or ""
        info=f"🏦 آخر إفصاح ملكية: {form} {filed}".strip()
    OWNERSHIP_CACHE[symbol]=(now,info)
    return info

def send_split_alerts(symbols,market,token):
    if market not in ("TASI","US"): return 0
    symbol_set={x.upper() for x in symbols}
    sent=0
    for row in refresh_split_calendar():
        sym=str(row.get("symbol","")).upper()
        if not sym or sym not in symbol_set: continue
        date=str(row.get("date","") or "")
        key=f"{market}:{sym}:{date}:{row.get('description','')}"
        if key in SPLIT_SENT: continue
        text=("⚠️ <b>تنبيه تقسيم السهم</b>\n\n"
              f"🌐 {market}\n📌 <b>{sym}</b>\n"
              f"🔄 {row.get('description','Split')}\n"
              f"📅 التاريخ: {date}\n"
              "ℹ️ تم فصل حدث التقسيم عن الإشارة الفنية حتى لا يختلط أثره السعري بالمؤشرات.")
        if tg(token,text):
            SPLIT_SENT.add(key); sent+=1
    return sent

# ---------- news ----------

def news(symbol):
    data=td("/news",{"symbol":symbol,"limit":10})
    rows=data.get("news",[]) if isinstance(data,dict) else data if isinstance(data,list) else []
    p=n=0
    for a in rows:
        if isinstance(a,dict):
            t=(str(a.get("title",""))+" "+str(a.get("description",""))).lower()
            p+=sum(w in t for w in POSITIVE);n+=sum(w in t for w in NEGATIVE)
    return "🟢 إيجابي" if p>n else "🔴 سلبي" if n>p else "⚪ محايد"

# ---------- analysis ----------

def flow_events(c):
    if len(c)<25:
        return {"breakout":False,"funds":False,"makers":False,"speculators":False,"accumulation":False,"unusual":False}
    last=c[-1]; prev=c[-21:-1]
    resistance=max(z["high"] for z in prev); support=min(z["low"] for z in prev)
    avg_vol=sum(z["volume"] for z in prev)/20 if prev else 0
    vr=(last["volume"]/avg_vol) if avg_vol>0 else 1.0
    rng=max(last["high"]-last["low"],0); body=abs(last["close"]-last["open"])
    breakout=last["close"]>resistance or last["close"]<support
    unusual=vr>=2.0 or (avg_vol>0 and rng>0 and body/rng>=0.75 and vr>=1.5)
    accumulation=vr>=1.5 and last["close"]>=last["open"] and last["close"]>sum(z["close"] for z in prev[-5:])/5
    speculators=vr>=2.5 and abs(last["close"]-last["open"])/(last["open"] or 1)>=0.01
    makers=vr>=3.0 and body/rng>=0.65 if rng>0 else False
    funds=vr>=2.0 and last["close"]>=last["open"] and last["close"]>=sum(z["close"] for z in prev[-10:])/10
    return {"breakout":breakout,"funds":funds,"makers":makers,"speculators":speculators,"accumulation":accumulation,"unusual":unusual}

def analyze_candles(symbol,market,c,name,tf,current_price=None):
    if not c:return None
    x=[z["close"] for z in c];h=[z["high"] for z in c];l=[z["low"] for z in c];v=[z["volume"] for z in c]
    bar_price=x[-1]
    price=current_price if current_price is not None and current_price>0 else bar_price
    if market=="US" and price < MIN_US_PRICE:
        return None
    e10,e14,e15,e25,e50=[ema(x,n) for n in (10,14,15,25,50)]
    rv=rsi(x);a=atr(h,l,x);vw=vwap(h,l,x,v);hb,hs=hidden_div(c);g=golden(c)
    score=0
    score+=20 if e50 and price>e50 else 0
    score+=15 if e10 and e14 and e10>e14 else 0
    score+=15 if e14 and e25 and e14>e25 else 0
    score+=20 if rv and rv>50 else 0
    score+=15 if vw and price>vw else 0
    score+=15 if vol_ratio(v)>=1.10 else 0
    # Signal logic is intentionally more tolerant so TASI and crypto can emit alerts
    # even when VWAP/volume is missing or a market has thinner intraday history.
    above_vwap = (vw is not None and price > vw)
    below_vwap = (vw is not None and price < vw)
    buy_core = bool(e10 and e25 and rv and e10>e25 and rv>50 and (vw is None or above_vwap))
    sell_core = bool(e10 and e25 and rv and e10<e25 and rv<50 and (vw is None or below_vwap))
    buy_confirm = bool(e50 and rv and price>e50 and rv>=55 and (vw is None or above_vwap))
    sell_confirm = bool(e50 and rv and price<e50 and rv<=45 and (vw is None or below_vwap))
    buy=g or hb or buy_core or buy_confirm
    sell=hs or sell_core or sell_confirm
    if buy and score>=MIN_SCORE: sig="BUY";txt="🟢 شراء قوي";strength=score
    elif sell and 100-score>=MIN_SCORE: sig="SELL";txt="🔴 بيع قوي";strength=100-score
    else:return None
    surge=surge_info(c,a,sig=="BUY")
    tr=trend(c)
    with state_lock:
        if tr!="NEUTRAL":trend_state[f"{market}:{symbol}"]=tr
        tr=trend_state.get(f"{market}:{symbol}",tr)
    return {"market":market,"symbol":symbol,"name":name or symbol,"price":price,"signal":sig,
            "signal_text":txt,"score":strength,"timeframe":tf,"trend":tr,"ema10":e10,
            "ema14":e14,"ema15":e15,"ema25":e25,"ema50":e50,"rsi":rv,"atr":a,"vwap":vw,
            "support":min(z["low"] for z in c[-50:]),"resistance":max(z["high"] for z in c[-50:]),
            "volume_ratio":vol_ratio(v),"ars":ars(c),"golden":g,"flow":flow_events(c),
            "surge":surge,"targets":targets(price,a,sig=="BUY",surge["factor"]),
            "news":"⚪ غير متاح"}

def analyze(symbol,market):
    if market=="TASI":
        live=current_price_tasi(symbol)
        asset=None
    else:
        asset="stocks" if market=="US" else "crypto"
        live=current_price_sf(asset,symbol)
        if live is None:
            live=current_price_td(symbol)
    split=split_for_symbol(symbol) if market in ("TASI","US") else None
    tf_list=("15min",) if market=="TASI" else TIMEFRAMES
    for tf in tf_list:
        c,n=get_tasi(symbol,tf) if market=="TASI" else get_sf(asset,symbol,tf)
        # TASI uses Twelve Data for the technical candle series and SAHMK for the
        # current/most recent quoted price. If SAHMK is delayed or temporarily
        # unavailable, analyze the candle price instead of dropping the symbol.
        r=analyze_candles(symbol,market,c,n,tf,live)
        if r:
            r["split"]=split
            r["institutional"] = ""
            r["news"] = "⚪ محايد"
            return r
    return None

# ---------- Telegram ----------

def tg(token,text):
    if not token or not CHAT_ID:return False
    try:
        r=requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                        data={"chat_id":CHAT_ID,"text":text,"parse_mode":"HTML"},timeout=30)
        return r.ok
    except Exception:return False

def fmt(x):
    if x is None:return "-"
    try:x=float(x)
    except Exception:return "-"
    if abs(x)>=1e9:return f"{x/1e9:.2f}B"
    if abs(x)>=1e6:return f"{x/1e6:.2f}M"
    if abs(x)>=1e3:return f"{x/1e3:.2f}K"
    ax=abs(x)
    if ax>=100:return f"{x:.2f}"
    if ax>=1:return f"{x:.4f}"
    if ax>=0.01:return f"{x:.6f}"
    if ax>=0.0001:return f"{x:.8f}"
    if ax>=0.000001:return f"{x:.10f}"
    return f"{x:.12f}"

def message(r):
    """Telegram alert layout — organized to match the approved visual mockup."""
    market_labels = {
        "TASI": "🇸🇦 <b>تاسي</b>",
        "US": "🇺🇸 <b>السوق الأمريكي US</b>",
        "CRYPTO": "🪙 <b>العملات الرقمية</b>",
    }
    market = market_labels.get(r["market"], f"🌐 <b>{r['market']}</b>")

    if r["signal"] == "BUY":
        signal_badge = "🟢 <b>شراء قوي</b>"
    elif r["signal"] == "SELL":
        signal_badge = "🔴 <b>بيع قوي</b>"
    else:
        signal_badge = "⚪ <b>انتظار</b>"

    if r["trend"] == "UP":
        trend_text = "🟢 اتجاه صاعد ↗️"
    elif r["trend"] == "DOWN":
        trend_text = "🔴 اتجاه هابط ↘️"
    else:
        trend_text = "⚪ اتجاه محايد"

    # Momentum is descriptive only; it is derived from the existing score/volume/RSI data.
    if r["score"] >= 80:
        momentum = "قوي"
    elif r["score"] >= 60:
        momentum = "جيد"
    else:
        momentum = "ضعيف"

    vwap_state = "🟢 فوق VWAP" if r.get("vwap") is not None and r["price"] > r["vwap"] else \
                 "🔴 تحت VWAP" if r.get("vwap") is not None else "⚪ غير متاح"

    s = [
        "💀🚀 <b>AI PRO MAX</b>",
        f"🌐 {market}",
        "",
        f"📌 <b>{r['symbol']}</b>",
        f"{signal_badge}    <b>{r['score']}/100</b>",
        f"⏱️ الإطار: <b>{r['timeframe']}</b>",
        "",
        f"💰 السعر الحالي: <b>{fmt(r['price'])}</b>",
        f"📊 الزخم: <b>{momentum}</b>",
        f"📈 الاتجاه: <b>{trend_text}</b>",
        f"🧠 RSI 14: <b>{fmt(r['rsi'])}</b>",
        f"📊 VWAP: <b>{fmt(r['vwap'])}</b>  {vwap_state}",
        f"📐 ATR 14: <b>{fmt(r['atr'])}</b>",
        f"📦 الحجم: <b>{r['volume_ratio']:.2f}x</b>",
        "",
        "📐 <b>المتوسطات EMA</b>",
        f"EMA10: <b>{fmt(r['ema10'])}</b>   |   EMA14: <b>{fmt(r['ema14'])}</b>",
        f"EMA15: <b>{fmt(r['ema15'])}</b>   |   EMA25: <b>{fmt(r['ema25'])}</b>",
        f"EMA50: <b>{fmt(r['ema50'])}</b>",
        "",
        "🛡️ <b>الدعم والمقاومة</b>",
        f"🛡️ الدعم: <b>{fmt(r['support'])}</b>",
        f"🚧 المقاومة: <b>{fmt(r['resistance'])}</b>",
        "",
        f"🧮 <b>ARS: {r['ars']}</b>",
        f"🟡 Golden Candle: <b>{'نعم' if r['golden'] else 'لا'}</b>",
    ]

    f = r.get("flow", {})
    flow_lines = []
    if f.get("breakout"):
        flow_lines.append("📈 الاختراقات: <b>تم رصد اختراق</b>")
    if f.get("funds"):
        flow_lines.append("🏦 تحركات الصناديق: <b>نشاط محتمل من الحجم</b>")
    if f.get("makers"):
        flow_lines.append("🐋 صنّاع السهم: <b>حركة كبيرة محتملة</b> <i>(Proxy)</i>")
    if f.get("speculators"):
        flow_lines.append("⚡ حركة المضاربين: <b>قوية</b>")
    if f.get("accumulation"):
        flow_lines.append("💰 عمليات التجميع: <b>محتملة</b>")
    if f.get("unusual"):
        flow_lines.append("🔎 تحركات غير اعتيادية: <b>تم رصدها</b>")

    if flow_lines:
        s += ["", "🐋 <b>تحليل الحركة</b>"] + flow_lines

    if r.get("institutional"):
        s += ["", r["institutional"]]

    if r["market"] == "US":
        s += ["", f"📰 <b>آخر الأخبار:</b> {r['news']}"]

    if r.get("split"):
        sp = r["split"]
        s += [
            "",
            "⚠️ <b>تنبيه تقسيم السهم</b>",
            f"🔄 {sp.get('description', 'Split')}",
            f"📅 {sp.get('date', '-')}",
        ]

    surge=r.get("surge") or {}
    if surge.get("active"):
        s += [
            "",
            "🚀 <b>حركة انفجارية — SURGE MODE</b>",
            f"🔥 قوة القفزة: <b>{surge.get('score',0)}/100</b>",
            f"📊 الحجم: <b>{surge.get('volume_ratio',1):.1f}x</b>",
            f"📐 توسع ATR: <b>{surge.get('atr_ratio',1):.2f}x</b>",
            f"⚡ اتساع الأهداف: <b>{surge.get('factor',1):.2f}x</b>",
        ]

    if r.get("targets"):
        s += ["", "🎯 <b>أهداف ATR (8)</b>" + (" 🚀" if surge.get("active") else "")]
        for i, t in enumerate(r["targets"], 1):
            ch = (t - r["price"]) / r["price"] * 100 if r["price"] else 0
            s.append(f"TP{i}: <b>{fmt(t)}</b>   ({ch:+.2f}%)")

    s += [
        "",
        "🔄 <b>استمرار الاتجاه</b>: حتى ظهور انعكاس مؤكد",
        f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "⚠️ <i>إشارة تحليلية آلية وليست توصية استثمارية.</i>",
    ]
    return "\n".join(s)

def should_send(r):
    k=f"{r['market']}:{r['symbol']}";st=(r["signal"],r["trend"])
    with state_lock:
        if last_signal.get(k)==st:return False
        last_signal[k]=st
    return True

def enrich_alert(r):
    if r["market"]=="US":
        r["news"]=news(r["symbol"])
        r["institutional"]=institutional_activity(r["symbol"])
    elif r["market"]=="TASI":
        r["institutional"]="⚪ تتبع الصناديق: غير متاح من مزود البيانات الحالي"
    else:
        r["institutional"]="⚪ تتبع الصناديق: غير منطبق على السوق الفوري للعملات الرقمية"
    return r

def tg_worker():
    while True:
        item=TG_QUEUE.get()
        if item is None:TG_QUEUE.task_done();return
        token,r=item
        try:
            if tg(token,message(r)):print(f"[{r['market']}] 📲 {r['symbol']} {r['signal']} {r['score']}/100")
        finally:TG_QUEUE.task_done()

# ---------- scanning ----------

def scan(symbols,market,token):
    total=len(symbols);done=signals=0
    print(f"[{market}] 🌐 OPEN UNIVERSE | لا يوجد حد عددي أو ترتيب A-Z | الأمريكي: ${MIN_US_PRICE:.2f} فأعلى")
    print(f"[{market}] 🧠 بدء الفحص الكامل: {total} رمز | Workers={MAX_WORKERS}")
    if market=="US":
        print(f"[{market}] 💵 شرط السعر الوحيد: >= ${MIN_US_PRICE:.2f} | لا يوجد حد عددي ولا ترتيب A-Z")
    else:
        print(f"[{market}] 🔓 لا يوجد حد عددي | فحص كامل 24/7")
    batch_size=MAX_WORKERS*8
    for start in range(0,total,batch_size):
        batch=symbols[start:start+batch_size]
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            jobs={ex.submit(analyze,s,market):s for s in batch}
            for job in as_completed(jobs):
                done+=1
                try:
                    r=job.result()
                    if r and should_send(r):
                        r=enrich_alert(r)
                        TG_QUEUE.put_nowait((token,r));signals+=1
                except queue.Full:pass
                except Exception as e:print(f"[{market}] analysis error: {e}")
        if done%100==0 or done==total:print(f"[{market}] {done}/{total} | signals={signals}")
    print(f"[{market}] انتهى | {total} | signals={signals}")

RIYADH=ZoneInfo("Asia/Riyadh")

def tasi_market_open():
    # 24/7 mode requested by the user: do not stop the Saudi scanner
    # based on the official TASI session calendar. The provider may return
    # the latest available/delayed data outside market hours.
    return True

def market_loop(market,token,loader):
    while True:
        try:
            # TASI scanner is configured for 24/7 operation.
            symbols=get_symbols(market,loader)
            print(f"💀 {market}: {len(symbols)} رمز")
            if symbols:
                send_split_alerts(symbols,market,token)
                scan(symbols,market,token)
        except Exception as e:print(f"[{market}] loop error: {e}")
        time.sleep(SCAN_INTERVAL)

def heartbeat():
    while True:
        print("💀🚀 AI PRO MAX يعمل 24/7 | "+datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        time.sleep(300)

def main():
    print("="*70)
    print("💀🚀 AI PRO MAX — FINAL HYBRID")
    print("🇸🇦 تاسي -> SAHMK + Twelve Data history | 🇺🇸 US -> SiftingIO | 🪙 Crypto -> SiftingIO")
    print("="*70)
    required=("CHAT_ID","TASI_TOKEN","US_TOKEN","CRYPTO_TOKEN","TWELVEDATA_API_KEY","SIFTING_API_KEY","SAHMK_API_KEY")
    missing=[x for x in required if not os.getenv(x)]
    if missing:
        print("❌ متغيرات ناقصة: "+", ".join(missing));return
    print("🟢 Environment: OK")
    print("🇸🇦 TASI: SAHMK symbol/quote + Twelve Data technical history")
    threading.Thread(target=tg_worker,daemon=True).start()
    threading.Thread(target=heartbeat,daemon=True).start()
    threading.Thread(target=market_loop,args=("TASI",TASI_TOKEN,load_tasi),daemon=True).start()
    threading.Thread(target=market_loop,args=("US",US_TOKEN,load_us),daemon=True).start()
    threading.Thread(target=market_loop,args=("CRYPTO",CRYPTO_TOKEN,load_crypto),daemon=True).start()
    while True:time.sleep(60)

if __name__=="__main__":main()
