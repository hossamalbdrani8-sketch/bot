import os, time, json, queue, threading, requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
# ============================================================
# AI PRO MAX — FAST FULL-MARKET MODE
# No US/crypto catalog download. Uses SiftingIO full-market snapshots.
# TASI uses SAHMK company symbols internally, then bulk quotes when entitled.
# No price floor, score threshold, A-Z ordering, or numeric symbol cap.
# ============================================================

CHAT_ID=os.getenv('CHAT_ID','').strip()
TASI_TOKEN=os.getenv('TASI_TOKEN','').strip()
US_TOKEN=os.getenv('US_TOKEN','').strip()
CRYPTO_TOKEN=os.getenv('CRYPTO_TOKEN','').strip()
SAHMK_API_KEY=os.getenv('SAHMK_API_KEY','').strip()
SIFTING_API_KEY=os.getenv('SIFTING_API_KEY','').strip()

SAHMK='https://api.sahmk.sa/api/v1'
SIFTING='https://api.sifting.io/v1'
TIMEOUT=(5,15)
WORKERS=16
CYCLE_SECONDS=30
TG=queue.Queue(maxsize=5000)
prev={}
lock=threading.Lock()


def tg(token, text):
    if not token or not CHAT_ID: return
    try:
        requests.post(f'https://api.telegram.org/bot{token}/sendMessage',json={
            'chat_id':CHAT_ID,'text':text,'parse_mode':'HTML','disable_web_page_preview':True
        },timeout=(5,15))
    except Exception: pass


def tg_worker():
    while True:
        market,text=TG.get()
        try: tg({'TASI':TASI_TOKEN,'US':US_TOKEN,'CRYPTO':CRYPTO_TOKEN}[market],text)
        finally: TG.task_done()
threading.Thread(target=tg_worker,daemon=True).start()


def sifting_snapshot(venue):
    try:
        r=requests.get(f'{SIFTING}/snapshot/{venue}',headers={
            'X-API-Key':SIFTING_API_KEY,'Accept-Encoding':'gzip'
        },timeout=TIMEOUT)
        if r.status_code!=200:
            print(f'[FAST {venue}] HTTP {r.status_code}: {r.text[:250]}')
            return []
        return r.json().get('data',[]) or []
    except Exception as e:
        print(f'[FAST {venue}] error: {e}')
        return []


def tasi_symbols():
    try:
        r=requests.get(f'{SAHMK}/companies/',headers={'X-API-Key':SAHMK_API_KEY},params={
            'market':'TASI','limit':1000,'offset':0
        },timeout=TIMEOUT)
        if r.status_code!=200:
            print(f'[TASI] symbols HTTP {r.status_code}: {r.text[:250]}')
            return []
        d=r.json(); rows=d.get('results') or d.get('data') or d.get('companies') or []
        out=[]; seen=set()
        for x in rows:
            if not isinstance(x,dict): continue
            s=str(x.get('symbol') or x.get('ticker') or x.get('code') or '').strip().upper()
            if s and s not in seen: seen.add(s); out.append(s)
        return out
    except Exception as e:
        print('[TASI] symbols error:',e); return []


def tasi_quotes(symbols):
    if not symbols: return []
    # SAHMK Starter+ bulk endpoint. If unavailable, fall back to parallel single quotes.
    out=[]
    for i in range(0,len(symbols),40):
        chunk=symbols[i:i+40]
        try:
            r=requests.get(f'{SAHMK}/quotes/',headers={'X-API-Key':SAHMK_API_KEY},params={
                'symbols':','.join(chunk),'data_mode':'realtime'
            },timeout=TIMEOUT)
            if r.status_code==200:
                out.extend(r.json().get('quotes',[]) or [])
            else:
                print(f'[TASI] bulk quotes HTTP {r.status_code}; falling back to single quotes')
                break
        except Exception:
            break
    if out: return out

    def one(s):
        try:
            r=requests.get(f'{SAHMK}/quote/{s}/',headers={'X-API-Key':SAHMK_API_KEY},params={'data_mode':'realtime'},timeout=TIMEOUT)
            if r.status_code==200: return r.json()
        except Exception: pass
        return None
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        return [x for x in ex.map(one,symbols) if x]


def price(x):
    for k in ('p','price','close','last'):
        try:
            v=float(x.get(k));
            if v>0:return v
        except Exception: pass
    return None


def scan_snapshot(market, rows):
    now=datetime.now(timezone.utc).strftime('%H:%M:%S')
    changed=0
    sent=0
    current={}
    for x in rows:
        if not isinstance(x,dict): continue
        s=str(x.get('s') or x.get('symbol') or '').strip().upper()
        p=price(x)
        if not s or p is None: continue
        current[s]=p
        old=prev.get((market,s))
        if old is None: continue
        if p != old:
            changed += 1
            # No price floor, score, RSI, EMA, A-Z or other filter.
            direction='🟢 ↑' if p>old else '🔴 ↓'
            pct=((p-old)/old*100) if old else 0
            text=(
                f'💀🚀 <b>AI PRO MAX — FAST</b>\n'
                f'{market} | <b>{s}</b>\n'
                f'{direction} <b>{p:g}</b> ({pct:+.3f}%)\n'
                f'🕒 {now} UTC'
            )
            try: TG.put_nowait((market,text)); sent+=1
            except queue.Full: pass
    for s,p in current.items(): prev[(market,s)]=p
    print(f'[{market}] FAST {len(current)} symbols | changed={changed} | sent={sent}')


def scan_tasi():
    syms=tasi_symbols()
    print(f'[TASI] FAST universe ready: {len(syms)}')
    rows=tasi_quotes(syms)
    scan_snapshot('TASI',rows)


def scan_us():
    rows=sifting_snapshot('stocks')
    print(f'[US] FAST FULL MARKET snapshot: {len(rows)} symbols | no catalog | no cap')
    scan_snapshot('US',rows)


def scan_crypto():
    rows=sifting_snapshot('crypto')
    print(f'[CRYPTO] FAST FULL MARKET snapshot: {len(rows)} symbols | no catalog | no cap')
    scan_snapshot('CRYPTO',rows)


def main():
    required={'CHAT_ID':CHAT_ID,'TASI_TOKEN':TASI_TOKEN,'US_TOKEN':US_TOKEN,'CRYPTO_TOKEN':CRYPTO_TOKEN,'SAHMK_API_KEY':SAHMK_API_KEY,'SIFTING_API_KEY':SIFTING_API_KEY}
    missing=[k for k,v in required.items() if not v]
    if missing:
        print('[ENV] Missing:',', '.join(missing)); raise SystemExit(1)
    print('='*70)
    print('💀🚀 AI PRO MAX — FAST FULL-MARKET')
    print('🇸🇦 TASI | 🇺🇸 US | 🪙 CRYPTO')
    print('⚡ NO CATALOG STAGE | NO NUMERIC CAP | NO PRICE FLOOR')
    print('📲 Telegram immediate change alerts | 24/7')
    print('='*70)
    while True:
        started=time.time()
        with ThreadPoolExecutor(max_workers=3) as ex:
            fs=[ex.submit(scan_tasi),ex.submit(scan_us),ex.submit(scan_crypto)]
            for f in as_completed(fs):
                try:f.result()
                except Exception as e:print('[MARKET] safe error:',e)
        elapsed=time.time()-started
        time.sleep(max(1,CYCLE_SECONDS-elapsed))

if __name__=='__main__': main()
