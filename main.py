# AI PRO MAX — FINAL HYBRID
# TASI -> Twelve Data | US + Crypto -> SiftingIO
# Railway: use environment variables, never hard-code secrets.

import os, time, json, queue, threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, local
import requests

CHAT_ID = os.getenv("CHAT_ID", "").strip()
TASI_TOKEN = os.getenv("TASI_TOKEN", "").strip()
US_TOKEN = os.getenv("US_TOKEN", "").strip()
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN", "").strip()
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "").strip()
SIFTING_API_KEY = os.getenv("SIFTING_API_KEY", "").strip()

TD_BASE = "https://api.twelvedata.com"
SF_BASE = "https://api.sifting.io/v1"

MAX_WORKERS = 4
TD_GAP = 0.35
SF_GAP = 0.05
MAX_RETRIES = 3
SCAN_INTERVAL = 120
CACHE_TTL = 21600
MIN_US_PRICE = 0.20
US_MAX_SYMBOLS = 13402
OUTPUTSIZE = 220
TIMEFRAMES = ("3min", "5min", "15min", "30min", "1h", "4h")
SF_TF = {"3min":"5m", "5min":"5m", "15min":"15m", "30min":"30m", "1h":"1h", "4h":"1h"}
ATR_MULT = [1, 1.5, 2, 2.5, 3, 3.5, 4, 5]
MIN_SCORE = 70

POSITIVE = ("beat","beats","growth","profit","profits","upgrade","upgraded","buy",
            "strong","positive","partnership","contract","approval","revenue","surge","record")
NEGATIVE = ("loss","losses","downgrade","downgraded","sell","weak","negative","lawsuit",
            "decline","drop","warning","debt","offering","investigation","risk")

td_local, sf_local = local(), local()
td_lock, sf_lock = Lock(), Lock()
td_last = [0.0]
sf_last = [0.0]
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
        s.headers.update({"User-Agent":"AI-PRO-MAX/Final"})
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
            if r.status_code != 200: return None
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

def targets(price,a,up):
    if not a or a<=0:return []
    return [price+(a*m if up else -a*m) for m in ATR_MULT]

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
    if not isinstance(data,dict):return None,""
    out=[]
    for x in data.get("data",[]):
        try:out.append({"datetime":x["t"],"open":float(x["o"]),"high":float(x["h"]),
                        "low":float(x["l"]),"close":float(x["c"]),
                        "volume":float(x.get("v",0) or 0)})
        except Exception:pass
    out.sort(key=lambda z:z["datetime"])
    return (out[-OUTPUTSIZE:] if len(out)>=60 else None),""

def get_tasi(symbol,tf):
    return td_candles(td("/time_series",{"symbol":symbol,"interval":tf,"outputsize":OUTPUTSIZE,"format":"JSON"}))

def get_sf(asset,symbol,tf):
    native=SF_TF[tf]
    c,n=sf_candles(sf(f"/hist/{asset}/{symbol}/bars",{"interval":native,"limit":2000}))
    if not c:return None,n
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

def symbols_td(data):
    rows=data.get("data",[]) if isinstance(data,dict) else data if isinstance(data,list) else []
    return sorted({str(x["symbol"]).strip() for x in rows if isinstance(x,dict) and x.get("symbol")},key=str.upper)

def load_tasi(): return symbols_td(td("/stocks",{"exchange":"TADAWUL"}))[:375]
def load_us():
    x=symbols_td(td("/stocks",{"country":"United States"}))
    return x[:US_MAX_SYMBOLS] if x else ["AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","AVGO","AMD","NFLX"]
def load_crypto():
    x=symbols_td(td("/cryptocurrencies",{}))
    return x if x else ["BTCUSD","ETHUSD","SOLUSD","XRPUSD","DOGEUSD"]

def get_symbols(market,loader):
    now=time.time()
    with cache_lock:
        c=symbol_cache[market]
        if c["symbols"] and now-c["updated"]<CACHE_TTL:return list(c["symbols"])
    x=loader()
    if x:
        with cache_lock:symbol_cache[market]={"symbols":list(x),"updated":now}
    return x

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

def analyze_candles(symbol,market,c,name,tf):
    if not c:return None
    x=[z["close"] for z in c];h=[z["high"] for z in c];l=[z["low"] for z in c];v=[z["volume"] for z in c]
    price=x[-1]
    if market=="US" and price<MIN_US_PRICE:return None
    e10,e14,e15,e25,e50=[ema(x,n) for n in (10,14,15,25,50)]
    rv=rsi(x);a=atr(h,l,x);vw=vwap(h,l,x,v);hb,hs=hidden_div(c);g=golden(c)
    score=0
    score+=20 if e50 and price>e50 else 0
    score+=15 if e10 and e14 and e10>e14 else 0
    score+=15 if e14 and e25 and e14>e25 else 0
    score+=20 if rv and rv>50 else 0
    score+=15 if vw and price>vw else 0
    score+=15 if vol_ratio(v)>=1.10 else 0
    buy=g or hb or (e10 and e25 and rv and vw and e10>e25 and rv>50 and price>vw)
    sell=hs or (e10 and e25 and rv and vw and e10<e25 and rv<50 and price<vw)
    if buy and score>=MIN_SCORE: sig="BUY";txt="🟢 شراء قوي";strength=score
    elif sell and 100-score>=MIN_SCORE: sig="SELL";txt="🔴 بيع قوي";strength=100-score
    else:return None
    tr=trend(c)
    with state_lock:
        if tr!="NEUTRAL":trend_state[f"{market}:{symbol}"]=tr
        tr=trend_state.get(f"{market}:{symbol}",tr)
    return {"market":market,"symbol":symbol,"name":name or symbol,"price":price,"signal":sig,
            "signal_text":txt,"score":strength,"timeframe":tf,"trend":tr,"ema10":e10,
            "ema14":e14,"ema15":e15,"ema25":e25,"ema50":e50,"rsi":rv,"atr":a,"vwap":vw,
            "support":min(z["low"] for z in c[-50:]),"resistance":max(z["high"] for z in c[-50:]),
            "volume_ratio":vol_ratio(v),"ars":ars(c),"golden":g,"targets":targets(price,a,sig=="BUY"),
            "news":"⚪ غير متاح"}

def analyze(symbol,market):
    for tf in TIMEFRAMES:
        c,n=get_tasi(symbol,tf) if market=="TASI" else get_sf("stocks" if market=="US" else "crypto",symbol,tf)
        r=analyze_candles(symbol,market,c,n,tf)
        if r:
            if market=="US":r["news"]=news(symbol)
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
    return f"{x:.4f}"

def message(r):
    tr="🟢 استمرار صاعد" if r["trend"]=="UP" else "🔴 استمرار هابط" if r["trend"]=="DOWN" else "⚪ محايد"
    s=["💀🚀 <b>AI PRO MAX</b>","",f"🌐 <b>{r['market']}</b>",
       f"📌 <b>{r['symbol']}</b> — {r['name']}",
       f"🎯 <b>{r['signal_text']}</b> | القوة: <b>{r['score']}/100</b>",
       f"⏱️ الإطار: <b>{r['timeframe']}</b>","",
       f"💰 السعر: <b>{fmt(r['price'])}</b>",f"🧠 RSI 14: <b>{fmt(r['rsi'])}</b>",
       f"📊 VWAP: <b>{fmt(r['vwap'])}</b>",f"📐 ATR 14: <b>{fmt(r['atr'])}</b>",
       f"📦 الحجم: <b>{r['volume_ratio']:.2f}x</b>","",
       f"EMA10: <b>{fmt(r['ema10'])}</b> | EMA14: <b>{fmt(r['ema14'])}</b>",
       f"EMA15: <b>{fmt(r['ema15'])}</b> | EMA25: <b>{fmt(r['ema25'])}</b>",
       f"EMA50: <b>{fmt(r['ema50'])}</b>","",
       f"🛡️ الدعم: <b>{fmt(r['support'])}</b>",f"🚧 المقاومة: <b>{fmt(r['resistance'])}</b>",
       f"📈 الاتجاه: <b>{tr}</b>",f"🧮 ARS: <b>{r['ars']}</b>",
       f"🟡 Golden Candle: <b>{'نعم' if r['golden'] else 'لا'}</b>"]
    if r["market"]=="US":s.append(f"📰 الأخبار: <b>{r['news']}</b>")
    if r["targets"]:
        s+=["","🎯 <b>8 أهداف ATR</b>"]
        for i,t in enumerate(r["targets"],1):
            ch=(t-r["price"])/r["price"]*100 if r["price"] else 0
            s.append(f"TP{i}: <b>{fmt(t)}</b> ({ch:+.2f}%)")
    s+=["", "🔄 الاتجاه يستمر حتى ظهور انعكاس مؤكد",
        f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"]
    return "\n".join(s)

def should_send(r):
    k=f"{r['market']}:{r['symbol']}";st=(r["signal"],r["trend"])
    with state_lock:
        if last_signal.get(k)==st:return False
        last_signal[k]=st
    return True

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
    print(f"[{market}] 🧠 بدء الفحص: {total} رمز | Workers={MAX_WORKERS}")
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
                        TG_QUEUE.put_nowait((token,r));signals+=1
                except queue.Full:pass
                except Exception as e:print(f"[{market}] analysis error: {e}")
        if done%100==0 or done==total:print(f"[{market}] {done}/{total} | signals={signals}")
    print(f"[{market}] انتهى | {total} | signals={signals}")

def market_loop(market,token,loader):
    while True:
        try:
            symbols=get_symbols(market,loader)
            print(f"💀 {market}: {len(symbols)} رمز")
            if symbols:scan(symbols,market,token)
        except Exception as e:print(f"[{market}] loop error: {e}")
        time.sleep(SCAN_INTERVAL)

def heartbeat():
    while True:
        print("💀🚀 AI PRO MAX يعمل 24/7 | "+datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        time.sleep(300)

def main():
    print("="*70)
    print("💀🚀 AI PRO MAX — FINAL HYBRID")
    print("🇸🇦 TASI -> Twelve Data | 🇺🇸 US -> SiftingIO | 🪙 Crypto -> SiftingIO")
    print("="*70)
    required=("CHAT_ID","TASI_TOKEN","US_TOKEN","CRYPTO_TOKEN","TWELVEDATA_API_KEY","SIFTING_API_KEY")
    missing=[x for x in required if not os.getenv(x)]
    if missing:
        print("❌ متغيرات ناقصة: "+", ".join(missing));return
    print("🟢 Environment: OK")
    threading.Thread(target=tg_worker,daemon=True).start()
    threading.Thread(target=heartbeat,daemon=True).start()
    threading.Thread(target=market_loop,args=("TASI",TASI_TOKEN,load_tasi),daemon=True).start()
    threading.Thread(target=market_loop,args=("US",US_TOKEN,load_us),daemon=True).start()
    threading.Thread(target=market_loop,args=("CRYPTO",CRYPTO_TOKEN,load_crypto),daemon=True).start()
    while True:time.sleep(60)

if __name__=="__main__":main()
