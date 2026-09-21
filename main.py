
import os, time, hashlib
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)
CHAT_ID=os.getenv('CHAT_ID','').strip(); US_TOKEN=os.getenv('US_TOKEN','').strip(); TASI_TOKEN=os.getenv('TASI_TOKEN','').strip(); CRYPTO_TOKEN=os.getenv('CRYPTO_TOKEN','').strip(); WEBHOOK_SECRET=os.getenv('WEBHOOK_SECRET','').strip(); DEDUP_SECONDS=int(os.getenv('DEDUP_SECONDS','120'))
seen={}

def market_name(v):
    v=str(v or '').strip().upper()
    if v in {'US','USA','NASDAQ','NYSE','AMEX'}: return 'US'
    if v in {'TASI','SAUDI','KSA','TADAWUL','SA'}: return 'TASI'
    if v in {'CRYPTO','CRYPTOS','DIGITAL'}: return 'CRYPTO'
    return v

def signal_name(v):
    v=str(v or '').strip().upper()
    if v in {'BUY','LONG','BULL','BULLISH'}: return 'BUY'
    if v in {'SELL','SHORT','BEAR','BEARISH'}: return 'SELL'
    return ''

def token_for(m): return {'US':US_TOKEN,'TASI':TASI_TOKEN,'CRYPTO':CRYPTO_TOKEN}.get(m,'')
def num(v):
    try: return f'{float(v):,.8f}'.rstrip('0').rstrip('.')
    except: return str(v or '').strip()
def esc(v): return str(v or '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
def cleanup():
    now=time.time()
    for k,t in list(seen.items()):
        if now-t>DEDUP_SECONDS: seen.pop(k,None)
def telegram(token,text):
    r=requests.post(f'https://api.telegram.org/bot{token}/sendMessage',json={'chat_id':CHAT_ID,'text':text,'parse_mode':'HTML','disable_web_page_preview':True},timeout=15)
    return r.ok,r.text[:500]

@app.get('/')
def home(): return jsonify(status='ok',service='AI PRO MAX TradingView Webhook',twelve_data=False,sahmk=False,signals=['BUY','SELL'],doji_used=False)
@app.get('/health')
def health(): return jsonify(status='healthy')

@app.post('/webhook')
def webhook():
    if WEBHOOK_SECRET:
        supplied=(request.headers.get('X-Webhook-Secret','') or request.args.get('secret','')).strip()
        if supplied!=WEBHOOK_SECRET: return jsonify(ok=False,error='Unauthorized'),401
    data=request.get_json(silent=True)
    if not isinstance(data,dict): data={'message':request.get_data(as_text=True)}
    sig=signal_name(data.get('signal') or data.get('action') or data.get('side') or data.get('type'))
    if sig not in {'BUY','SELL'}: return jsonify(ok=True,ignored=True,reason='Only BUY and SELL are accepted')
    source=str(data.get('source') or data.get('pattern') or data.get('setup') or '').upper()
    if 'DOJI' in source: return jsonify(ok=True,ignored=True,reason='Doji signals are disabled')
    market=market_name(data.get('market') or data.get('exchange') or data.get('market_type'))
    token=token_for(market)
    if not token or not CHAT_ID: return jsonify(ok=False,error='Telegram token/CHAT_ID missing'),500
    ticker=str(data.get('ticker') or data.get('symbol') or data.get('tickerid') or '').strip()
    price=num(data.get('price') or data.get('close') or data.get('last') or '')
    tf=str(data.get('timeframe') or data.get('interval') or '').strip()
    key=hashlib.sha256(f'{market}|{ticker}|{sig}|{price}|{tf}|{data.get("time","")}'.encode()).hexdigest()
    cleanup()
    if key in seen: return jsonify(ok=True,ignored=True,reason='Duplicate alert')
    seen[key]=time.time()
    icon='ð¢' if sig=='BUY' else 'ð´'
    mt={'US':'ðºð¸ Ø§ÙØ³ÙÙ Ø§ÙØ£ÙØ±ÙÙÙ','TASI':'ð¸ð¦ ØªØ¯Ø§ÙÙ','CRYPTO':'â¿ Ø§ÙØ¹ÙÙØ§Øª Ø§ÙØ±ÙÙÙØ©'}.get(market,esc(market))
    lines=[f'{icon} <b>{sig}</b>','','ð <b>Ø§ÙØ³ÙÙ:</b> '+esc(ticker),'ð <b>Ø§ÙØ³ÙÙ:</b> '+mt]
    if price: lines.append('ð° <b>Ø§ÙØ³Ø¹Ø±:</b> '+price)
    if tf: lines.append('â±ï¸ <b>Ø§ÙÙØ§ØµÙ:</b> '+esc(tf))
    for k,label in [('vwap','VWAP'),('rsi','RSI'),('volume','Volume'),('strength','Ø§ÙÙÙØ©')]:
        if str(data.get(k,'')).strip(): lines.append(f'ð <b>{label}:</b> {num(data[k])}')
    lines += ['','ð¤ <b>AI PRO MAX</b>','ð¡ TradingView Webhook']
    ok,result=telegram(token,'\n'.join(lines))
    if not ok: return jsonify(ok=False,error=result),502
    return jsonify(ok=True,sent=True,market=market,signal=sig,ticker=ticker)

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.getenv('PORT','8080')))
