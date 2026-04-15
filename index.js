import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();
app.use(express.json());

// 🔑 TOKEN
const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";

// 💀 اتصال قوي ثابت
const bot = new TelegramBot(TOKEN, {
  polling: {
    interval: 300,
    autoStart: true,
    params: { timeout: 10 }
  }
});

// 🔑 API
const API_KEY = "d7a0311r01qspme6c44gd7a0311r01qspme6c450";

let chatIds = new Set();
let memory = {};
let running = false;
let lastData = {};

// =======================
// 🔥 EMA DATA
async function getCandles(symbol) {
  try {
    let to = Math.floor(Date.now()/1000);
    let from = to - (60*60*24*30);

    const res = await fetch(`https://finnhub.io/api/v1/stock/candle?symbol=${symbol}&resolution=5&from=${from}&to=${to}&token=${API_KEY}`);
    const data = await res.json();

    if (data.s !== "ok") return null;

    return data.c;
  } catch {
    return null;
  }
}

function calculateEMA(data, period) {
  let k = 2 / (period + 1);
  let ema = data[0];

  for (let i = 1; i < data.length; i++) {
    ema = data[i] * k + ema * (1 - k);
  }

  return ema;
}

// 💀💀💀 EMA ELITE FIX 💀💀💀
async function getEMA(symbol) {
  let data = await getCandles(symbol);

  if (!data || data.length < 50) {
    let last = lastData[symbol]?.price;
    let prev = lastData[symbol]?.prev;

    if (last && prev) {
      return {
        emaText: "⚡ EMA سريع",
        cross: last > prev ? "📈 صعود لحظي" : "📉 هبوط لحظي"
      };
    }

    return {
      emaText: "⏳ تحميل EMA",
      cross: "..."
    };
  }

  let slice = data.slice(-400);

  let ema7 = calculateEMA(slice, 7);
  let ema25 = calculateEMA(slice, 25);
  let ema50 = calculateEMA(slice, 50);
  let ema320 = slice.length >= 320 ? calculateEMA(slice, 320) : ema50;
  let ema380 = slice.length >= 380 ? calculateEMA(slice, 380) : ema50;

  let trend = "⚪ تذبذب";

  if (ema7 > ema25 && ema25 > ema50) trend = "📈 صعود";
  if (ema7 > ema25 && ema25 > ema50 && ema50 > ema320) trend = "💀 ترند قوي";
  if (ema7 > ema25 && ema25 > ema50 && ema50 > ema320 && ema320 > ema380) trend = "💀🔥 ELITE";
  if (ema7 < ema25 && ema25 < ema50) trend = "📉 هابط";

  let cross = "⚪";

  if (ema7 > ema25 && ema7 > ema50) cross = "🔥 شراء";
  if (ema7 < ema25 && ema7 < ema50) cross = "🚨 بيع";
  if (ema7 > ema25 && ema25 < ema50) cross = "⚡ انعكاس";
  if (ema7 > ema25 && ema25 > ema50 && ema50 > ema320 && ema320 > ema380) cross = "💀🔥 ELITE";

  return { emaText: trend, cross };
}

// =======================
// 🔥 Yahoo (Float + Volume)
async function getExtra(symbol) {
  try {
    const res = await fetch(`https://query1.finance.yahoo.com/v10/finance/quoteSummary/${symbol}?modules=defaultKeyStatistics,price`);
    const data = await res.json();

    let r = data?.quoteSummary?.result?.[0];

    let float = r?.defaultKeyStatistics?.floatShares?.raw;
    let volume = r?.price?.regularMarketVolume?.raw;

    let floatText = "N/A";
    if (float) {
      let m = float / 1e6;
      if (m < 20) floatText = `💀 خفيف ${m.toFixed(2)}M`;
      else if (m < 100) floatText = `🔥 متوسط ${m.toFixed(2)}M`;
      else floatText = `🐘 ثقيل ${m.toFixed(2)}M`;
    }

    let activity = "⚠️ ضعيف";
    if (volume > 5_000_000) activity = "🔥 نشط";
    if (volume > 20_000_000) activity = "💀 انفجار";

    let liquidityText = volume ? (volume / 1e6).toFixed(2) + "M Vol" : "N/A";

    return { floatText, activity, liquidityText };

  } catch {
    return {
      floatText: "N/A",
      activity: "❌",
      liquidityText: "N/A"
    };
  }
}

// =======================
// 🔥 الأسواق الإضافية
async function getSASymbols() {
  return [
    { symbol: "2222.SR" },
    { symbol: "1120.SR" },
    { symbol: "2010.SR" },
    { symbol: "7010.SR" }
  ];
}

async function getCryptoSymbols() {
  return [
    { symbol: "BINANCE:BTCUSDT" },
    { symbol: "BINANCE:ETHUSDT" },
    { symbol: "BINANCE:SOLUSDT" }
  ];
}

// =======================
bot.on("message", (msg) => {
  chatIds.add(msg.chat.id);

  if (msg.text === "/start") {
    bot.sendMessage(msg.chat.id, "💀 AI PRO MAX ELITE MODE");
    run();
  }

  if (msg.text === "/scan") {
    bot.sendMessage(msg.chat.id, "🚀 فحص السوق...");
    run();
  }
});

// =======================
function analyze(price, prev, symbol) {
  if (!price || !prev || prev === 0 || price <= 0) return null;

  let change = ((price - prev) / prev) * 100;

  let signal = "⚪ محايد";
  let type = "🐠 مضاربين";
  let entry = "⏳ انتظر";

  if (change > 4) signal = "💀🚀 انفجار";
  else if (change > 2) signal = "🔥 تجميع";
  else if (change < -4) signal = "🚨 تصريف";

  if (change > 1) entry = "⚡️ دخول";

  let tp = [
    (price*1.02).toFixed(2),
    (price*1.04).toFixed(2),
    (price*1.06).toFixed(2),
    (price*1.08).toFixed(2),
    (price*1.10).toFixed(2),
    (price*1.12).toFixed(2),
    (price*1.15).toFixed(2),
    (price*1.18).toFixed(2)
  ];

  let sl = (price * 0.95).toFixed(2);

  return { signal,tp,sl,type,entry,change,fromLow:0 };
}

// =======================
// 💀💀💀 FORMAT ELITE SMART 💀💀💀
function format(s) {

  let liquidity = "🪫 ضعف سيولة";
  if (s.change > 1) liquidity = "💹 سيولة مستمرة";
  if (s.change > 3) liquidity = "💹🔥 سيولة قوية";

  function check(tp) {
    return Number(s.price) >= Number(tp) ? "✅" : "";
  }

  return `
${s.market}
${s.type}

${s.name}

💰 ${Number(s.price).toFixed(2)}

📊 ${s.signal}

📊 EMA: ${s.emaText}
⚡ ${s.cross}

🎯 TP1: ${s.tp[0]} ${check(s.tp[0])}
🎯 TP2: ${s.tp[1]} ${check(s.tp[1])}
🎯 TP3: ${s.tp[2]} ${check(s.tp[2])}
🎯 TP4: ${s.tp[3]} ${check(s.tp[3])}
🎯 TP5: ${s.tp[4]} ${check(s.tp[4])}
🎯 TP6: ${s.tp[5]} ${check(s.tp[5])}
🎯 TP7: ${s.tp[6]} ${check(s.tp[6])}
🎯 TP8: ${s.tp[7]} ${check(s.tp[7])}

🛑 SL: ${s.sl}

${s.entry}
${liquidity}
━━━━━━━━━━━━`;
}

// =======================
async function sendAll(symbol, text) {
  for (let id of chatIds) {
    try {
      await bot.sendMessage(id, text);
    } catch {}
  }
}

// =======================
async function getQuote(symbol) {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/quote?symbol=${symbol}&token=${API_KEY}`);
    const data = await res.json();

    if (!data?.c || !data?.pc) throw "no data";

    lastData[symbol] = { price: data.c, prev: data.pc };
    return lastData[symbol];

  } catch {
    return lastData[symbol] || null;
  }
}

// =======================
async function getUSSymbols() {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/stock/symbol?exchange=US&token=${API_KEY}`);
    return await res.json();
  } catch { return []; }
}

// =======================
async function run() {
  if (running) return;
  running = true;

  try {
    let us = await getUSSymbols();
    let sa = await getSASymbols();
    let crypto = await getCryptoSymbols();

    let all = [
      ...us.map(s => ({...s, market:"🇺🇸 السوق الأمريكي"})),
      ...sa.map(s => ({...s, market:"🇸🇦 السوق السعودي"})),
      ...crypto.map(s => ({...s, market:"💰 العملات الرقمية"}))
    ];

    for (let s of all) {
      let q = await getQuote(s.symbol);
      if (!q) continue;

      let a = analyze(q.price, q.prev, s.symbol);
      if (!a) continue;

      let extra = await getExtra(s.symbol);
      let ema = await getEMA(s.symbol);

      await sendAll(s.symbol, format({
        name:s.symbol,
        market:s.market,
        price:q.price,
        ...a,
        ...extra,
        ...ema
      }));

      await new Promise(r => setTimeout(r, 10));
    }

  } catch (e) {
    console.log("ERROR:", e.message);
  }

  running = false;
}

// 🔥 تشغيل دائم
setInterval(() => {
  if (!running) run();
}, 60000);

app.listen(3000, () => {
  console.log("🔥 RUNNING");
});
