import os, time, json, random, hashlib, threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

CHAT_ID = os.getenv("CHAT_ID","").strip()
US_TOKEN = os.getenv("US_TOKEN","").strip()
TASI_TOKEN = os.getenv("TASI_TOKEN","").strip()
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN","").strip()
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET","").strip()
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY","").strip()
SAHMK_API_KEY = os.getenv("SAHMK_API_KEY","").strip()

TD_BASE = "https://api.twelvedata.com"
SAHMK_BASE = "https://api.sahmk.sa/api/v1"
TD_DAY_LIMIT = 700
TD_MIN_LIMIT = 8
BATCH = 8
SCAN_SECONDS = 60
US_MIN_PRICE = 0.15
seen = {}
td_lock = threading.Lock()
td_minute = ""
td_min_used = 0
td_day = ""
td_day_used = 0
us_symbols, crypto_symbols = [], []
us_i = crypto_i = 0
turn = 0
catalog_time = 0
scanner_started = False

def now_utc(): return datetime.now(timezone.utc)
def num(v):
    try: return f"{float(v):,.8f}".rstrip("0").rstrip(".")
    except: return str(v or "").strip()
def esc(v): return str(v or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def market_name(v):
    v=str(v or "").strip().upper()
    if v in {"US","USA","NASDAQ","NYSE","AMEX"}: return "US"
    if v in {"TASI","SAUDI","KSA","TADAWUL","SA"}: return "TASI"
    if v in {"CRYPTO","CRYPTOS","DIGITAL"}: return "CRYPTO"
    return v

def signal_name(v):
    v=str(v or "").strip().upper()
    if v in {"BUY","LONG","BULL","BULLISH"}: return "BUY"
    if v in {"SELL","SHORT","BEAR","BEARISH"}: return "SELL"
    return ""

def telegram(token,text):
    if not token or not CHAT_ID: return False,"Telegram token/CHAT_ID missing"
    try:
        r=requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id":CHAT_ID,"text":text,"parse_mode":"HTML","disable_web_page_preview":True},timeout=15)
        return r.ok,r.text[:500]
    except Exception as e: return False,str(e)[:500]

def token_for(m): return {"US":US_TOKEN,"TASI":TASI_TOKEN,"CRYPTO":CRYPTO_TOKEN}.get(m,"")

def cleanup():
    n=time.time()
    for k,t in list(seen.items()):
        if n-t>180: seen.pop(k,None)

def td_reserve(cost):
    global td_minute,td_min_used,td_day,td_day_used
    while True:
        n=now_utc(); mi=n.strftime("%Y%m%d%H%M"); dy=n.strftime("%Y%m%d")
        with td_lock:
            if mi!=td_minute: td_minute,td_min_used=mi,0
            if dy!=td_day: td_day,td_day_used=dy,0
            if td_day_used+cost>TD_DAY_LIMIT: return False
            if td_min_used+cost<=TD_MIN_LIMIT:
                td_min_used+=cost; td_day_used+=cost; return True
            wait=60-n.second+0.2
        time.sleep(max(1,wait))

def td_get(path,params,cost):
    if not TWELVE_DATA_API_KEY or not td_reserve(cost): return None
    p=dict(params); p["apikey"]=TWELVE_DATA_API_KEY
    try: r=requests.get(TD_BASE+path,params=p,timeout=20)
    except Exception as e:
        print("[TD]",e,flush=True); return None
    try: d=r.json()
    except: return None
    if r.status_code>=400 or (isinstance(d,dict) and d.get("status")=="error"):
        print("[TD] error",d,flush=True); return None
    return d

def load_catalogs():
    global us_symbols,crypto_symbols,catalog_time
    a=td_get("/stocks",{"country":"United States"},1)
    b=td_get("/cryptocurrencies",{},1)
    us=[]; cr=[]
    for row in (a or {}).get("data",[]):
        if isinstance(row,dict) and row.get("symbol"):
            us.append(str(row["symbol"]).strip())
    for row in (b or {}).get("data",[]):
        if isinstance(row,dict) and row.get("symbol"):
            cr.append(str(row["symbol"]).strip())
    us_symbols=list(set(us)); crypto_symbols=list(set(cr))
    random.shuffle(us_symbols); random.shuffle(crypto_symbols)
    catalog_time=time.time()
    print(f"[CATALOG] US={len(us_symbols)} CRYPTO={len(crypto_symbols)}",flush=True)

def batch_series(symbols):
    if not symbols: return {}
    d=td_get("/time_series",{"symbol":",".join(symbols),"interval":"5min","outputsize":120},len(symbols))
    if not d: return {}
    out={}
    for s in symbols:
        x=d.get(s) if isinstance(d,dict) else None
        if isinstance(x,dict) and isinstance(x.get("values"),list): out[s]=x["values"]
    if len(symbols)==1 and isinstance(d,dict) and isinstance(d.get("values"),list): out[symbols[0]]=d["values"]
    return out

def ema(a,n):
    if len(a)<n:return None
    x=a[0]; k=2/(n+1)
    for v in a[1:]: x=k*v+(1-k)*x
    return x

def rsi(a,n=14):
    if len(a)<n+1:return None
    g=[];l=[]
    for i in range(1,len(a)):
        z=a[i]-a[i-1];g.append(max(z,0));l.append(max(-z,0))
    ag=sum(g[:n])/n; al=sum(l[:n])/n
    for i in range(n,len(g)):
        ag=((n-1)*ag+g[i])/n; al=((n-1)*al+l[i])/n
    return 100 if al==0 else 100-100/(1+ag/al)

def analyze(symbol,rows):
    if len(rows)<30:return None
    x=list(reversed(rows)); c=[float(v.get("close",0)) for v in x]
    h=[float(v.get("high",0)) for v in x]; l=[float(v.get("low",0)) for v in x]
    o=[float(v.get("open",0)) for v in x]; vol=[float(v.get("volume",0)) for v in x]
    p=c[-1]
    if p<=0:return None
    tv=sum(((h[i]+l[i]+c[i])/3)*vol[i] for i in range(len(x)))
    vv=sum(vol)
    vwap=tv/vv if vv else None
    R=rsi(c); e20=ema(c,20); e50=ema(c,50)
    av=sum(vol[-20:])/20
    strongvol=vol[-1]>=av*1.3 if av else False
    rng=h[-1]-l[-1]; body=abs(c[-1]-o[-1])
    golden=o[-1]<c[-1] and rng>0 and body/rng>=.60 and vwap and p>vwap and strongvol
    buy=sell=0
    if vwap:
        if p>vwap: buy+=40
        elif p<vwap: sell+=40
    if R is not None:
        if R>=55: buy+=20
        elif R<=45: sell+=20
    if strongvol:
        if p>c[-2]: buy+=15
        elif p<c[-2]: sell+=15
    if e20 and e50:
        if e20>e50: buy+=15
        elif e20<e50: sell+=15
    if golden: buy+=10
    sig="BUY" if buy>=70 and buy>sell else "SELL" if sell>=70 and sell>buy else None
    return {"symbol":symbol,"price":p,"vwap":vwap,"rsi":R,"volume":vol[-1],"buy":buy,"sell":sell,
            "score":max(buy,sell),"signal":sig,"golden":golden}

def send_signal(m,res,source="AI PRO MAX Scanner"):
    if res["signal"] not in {"BUY","SELL"}: return
    cleanup()
    key=hashlib.sha256(f"{m}|{res['symbol']}|{res['signal']}|{round(res['price'],8)}".encode()).hexdigest()
    if key in seen:return
    seen[key]=time.time()
    icon="ð¢" if res["signal"]=="BUY" else "ð´"
    ml={"US":"ðºð¸ Ø§ÙØ³ÙÙ Ø§ÙØ£ÙØ±ÙÙÙ","TASI":"ð¸ð¦ ØªØ¯Ø§ÙÙ","CRYPTO":"â¿ Ø§ÙØ¹ÙÙØ§Øª Ø§ÙØ±ÙÙÙØ©"}[m]
    lines=[f"{icon} <b>{res['signal']} â AI PRO MAX</b>","",
           f"ð <b>Ø§ÙØ±ÙØ²:</b> {esc(res['symbol'])}",f"ð <b>Ø§ÙØ³ÙÙ:</b> {ml}",
           f"ð° <b>Ø§ÙØ³Ø¹Ø±:</b> {num(res['price'])}",f"â­ <b>Ø§ÙÙÙØ©:</b> {res['score']}/100"]
    if res.get("vwap") is not None: lines.append(f"ð <b>VWAP:</b> {num(res['vwap'])}")
    if res.get("rsi") is not None: lines.append(f"ð <b>RSI:</b> {num(res['rsi'])}")
    lines.append(f"ð¦ <b>Volume:</b> {num(res['volume'])}")
    if res.get("golden"): lines.append("ð¡ <b>Ø´ÙØ¹Ø© Ø°ÙØ¨ÙØ©:</b> ÙØ¹Ù")
    lines += ["ð <b>Ø­Ø±ÙØ© ØµÙÙØ§Ø¹ Ø§ÙØ³ÙÙ:</b> Ø±ØµØ¯ Ø¢ÙÙ","â¡ <b>Ø­Ø±ÙØ© ÙØ¶Ø§Ø±Ø¨ÙÙ ÙÙÙØ©:</b> Ø±ØµØ¯ Ø¢ÙÙ",
              "ð <b>Ø­Ø±ÙØ© ØºÙØ± Ø§Ø¹ØªÙØ§Ø¯ÙØ©:</b> Ø±ØµØ¯ Ø¢ÙÙ","",f"â±ï¸ <b>Ø§ÙÙØ§ØµÙ:</b> 5min",
              f"ð¤ <b>Ø§ÙÙØµØ¯Ø±:</b> {esc(source)}"]
    ok,reply=telegram(token_for(m),"\n".join(lines))
    print(f"[{m}] {res['symbol']} {res['signal']} sent={ok}",flush=True)

def scan_us():
    global us_i
    if not us_symbols:return
    batch=[us_symbols[(us_i+j)%len(us_symbols)] for j in range(min(BATCH,len(us_symbols)))]
    us_i=(us_i+len(batch))%len(us_symbols)
    for s,rows in batch_series(batch).items():
        r=analyze(s,rows)
        if r and r["price"]>=US_MIN_PRICE:send_signal("US",r)

def scan_crypto():
    global crypto_i
    if not crypto_symbols:return
    batch=[crypto_symbols[(crypto_i+j)%len(crypto_symbols)] for j in range(min(BATCH,len(crypto_symbols)))]
    crypto_i=(crypto_i+len(batch))%len(crypto_symbols)
    for s,rows in batch_series(batch).items(): 
        r=analyze(s,rows)
        if r:send_signal("CRYPTO",r)

def tasi_open():
    n=datetime.now(ZoneInfo("Asia/Riyadh"))
    return n.weekday() in (6,0,1,2,3) and (9*60+30)<=n.hour*60+n.minute<=(15*60)

def tasi_scan():
    if not SAHMK_API_KEY or not tasi_open():return
    def get(path):
        try:
            r=requests.get(SAHMK_BASE+path,headers={"Authorization":f"Bearer {SAHMK_API_KEY}","Accept":"application/json"},timeout=20)
            return r.json() if r.ok else None
        except:return None
    rows=[]
    for path in ("/market/gainers/","/market/losers/"):
        d=get(path)
        if isinstance(d,list):rows+=d
        elif isinstance(d,dict):
            for k in ("data","results","values","items"):
                if isinstance(d.get(k),list):rows+=d[k];break
    if not rows:return
    def ch(x):
        try:return float(x.get("change") or x.get("change_percent") or x.get("percent_change") or 0)
        except:return 0
    z=max(rows,key=lambda x:abs(ch(x)))
    change=ch(z)
    s=str(z.get("symbol") or z.get("ticker") or z.get("code") or z.get("name") or "").strip()
    if not s or not change:return
    r={"symbol":s,"price":z.get("price") or z.get("last") or z.get("close") or 0,
       "vwap":None,"rsi":None,"volume":z.get("volume") or 0,
       "buy":80 if change>0 else 0,"sell":80 if change<0 else 0,
       "score":80,"signal":"BUY" if change>0 else "SELL","golden":change>3}
    send_signal("TASI",r,"SAHMK")

def scanner_loop():
    global turn
    print("[SYSTEM] scanner started",flush=True)
    load_catalogs()
    last_tasi=0
    while True:
        try:
            if time.time()-catalog_time>86400: load_catalogs()
            if time.time()-last_tasi>=900: tasi_scan(); last_tasi=time.time()
            turn=(turn+1)%8
            scan_crypto() if turn==0 else scan_us()
        except Exception as e: print("[SYSTEM]",e,flush=True)
        time.sleep(SCAN_SECONDS)

@app.get("/")
def home():
    with td_lock: u,d,m,ml=td_day_used,TD_DAY_LIMIT,td_min_used,TD_MIN_LIMIT
    return jsonify(status="ok",service="AI PRO MAX Scanner + TradingView Webhook",
        scanners={"US":bool(TWELVE_DATA_API_KEY and US_TOKEN),
                  "TASI":bool(SAHMK_API_KEY and TASI_TOKEN),
                  "CRYPTO":bool(TWELVE_DATA_API_KEY and CRYPTO_TOKEN)},
        twelve_data_daily_used=u,twelve_data_daily_limit=d,
        twelve_data_minute_used=m,twelve_data_minute_limit=ml,
        signals=["BUY","SELL"],doji_used=False)

@app.get("/health")
def health(): return jsonify(status="healthy")

@app.post("/webhook")
def webhook():
    if WEBHOOK_SECRET:
        supplied=(request.headers.get("X-Webhook-Secret","") or request.args.get("secret","")).strip()
        if supplied!=WEBHOOK_SECRET:return jsonify(ok=False,error="Unauthorized"),401
    data=request.get_json(silent=True)
    if not isinstance(data,dict):
        try:data=json.loads(request.get_data(as_text=True))
        except:data={"message":request.get_data(as_text=True)}
    sig=signal_name(data.get("signal") or data.get("action") or data.get("side") or data.get("type"))
    if sig not in {"BUY","SELL"}:return jsonify(ok=True,ignored=True,reason="Only BUY and SELL are accepted")
    source=str(data.get("source") or data.get("pattern") or data.get("setup") or "").upper()
    if "DOJI" in source:return jsonify(ok=True,ignored=True,reason="Doji signals are disabled")
    m=market_name(data.get("market") or data.get("exchange") or data.get("market_type"))
    token=token_for(m)
    if not token or not CHAT_ID:return jsonify(ok=False,error="Telegram token/CHAT_ID missing"),500
    ticker=str(data.get("ticker") or data.get("symbol") or data.get("tickerid") or "").strip()
    price=num(data.get("price") or data.get("close") or data.get("last") or "")
    tf=str(data.get("timeframe") or data.get("interval") or "").strip()
    cleanup()
    key=hashlib.sha256(f"WEBHOOK|{m}|{ticker}|{sig}|{price}|{tf}".encode()).hexdigest()
    if key in seen:return jsonify(ok=True,ignored=True,reason="Duplicate alert")
    seen[key]=time.time()
    ml={"US":"ðºð¸ Ø§ÙØ³ÙÙ Ø§ÙØ£ÙØ±ÙÙÙ","TASI":"ð¸ð¦ ØªØ¯Ø§ÙÙ","CRYPTO":"â¿ Ø§ÙØ¹ÙÙØ§Øª Ø§ÙØ±ÙÙÙØ©"}.get(m,esc(m))
    lines=[f"{'ð¢' if sig=='BUY' else 'ð´'} <b>{sig} â AI PRO MAX</b>","",
           f"ð <b>Ø§ÙØ±ÙØ²:</b> {esc(ticker)}",f"ð <b>Ø§ÙØ³ÙÙ:</b> {ml}"]
    if price:lines.append(f"ð° <b>Ø§ÙØ³Ø¹Ø±:</b> {price}")
    if tf:lines.append(f"â±ï¸ <b>Ø§ÙÙØ§ØµÙ:</b> {esc(tf)}")
    for k,label in (("vwap","VWAP"),("rsi","RSI"),("volume","Volume"),("strength","Ø§ÙÙÙØ©")):
        if str(data.get(k,"")).strip():lines.append(f"ð <b>{label}:</b> {num(data[k])}")
    lines += ["","ð¤ <b>AI PRO MAX</b>","ð¡ TradingView Webhook"]
    ok,reply=telegram(token,"\n".join(lines))
    if not ok:return jsonify(ok=False,error=reply),502
    return jsonify(ok=True,sent=True,market=m,signal=sig,ticker=ticker)

def start():
    global scanner_started
    if scanner_started:return
    scanner_started=True
    threading.Thread(target=scanner_loop,name="AI-PRO-MAX",daemon=True).start()

start()

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","8080")))
