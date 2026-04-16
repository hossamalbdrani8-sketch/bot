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

// 💀 EMA
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

  let trend = "⚪";
  if (ema7 > ema25 && ema25 > ema50) trend = "📈 صاعد";
  if (ema7 < ema25 && ema25 < ema50) trend = "📉 هابط";

  let cross = ema7 > ema25 ? "🔥 شراء" : "🚨 بيع";

  return { emaText: trend, cross };
}

// =======================
async function getExtra(symbol) {
  try {
    const res = await fetch(`https://query1.finance.yahoo.com/v10/finance/quoteSummary/${symbol}?modules=price`);
    const data = await res.json();

    let volume = data?.quoteSummary?.result?.[0]?.price?.regularMarketVolume?.raw;

    let activity = "🪫 ضعف سيولة";
    if (volume > 5_000_000) activity = "💹 سيولة";
    if (volume > 20_000_000) activity = "💹🔥 قوية";

    return { activity };

  } catch {
    return { activity: "❌" };
  }
}

// =======================
bot.on("message", (msg) => {
  chatIds.add(msg.chat.id);

  if (msg.text === "/start") {
    bot.sendMessage(msg.chat.id, "💀 RUNNING 24/7");
  }
});

// =======================
function analyze(price, prev) {
  let change = ((price - prev) / prev) * 100;

  let signal = "⚪";
  if (change > 3) signal = "💀🚀 انفجار";
  else if (change > 1) signal = "🔥 صعود";
  else if (change < -3) signal = "🚨 هبوط";

  let tp = [
    price*1.02, price*1.04, price*1.06, price*1.08,
    price*1.10, price*1.12, price*1.15, price*1.18
  ];

  return { change, signal, tp };
}

// =======================
function format(s) {

  function check(tp) {
    return s.price >= tp ? "✅" : "";
  }

  return `
${s.market}

${s.name}

💰 ${s.price.toFixed(2)}

📊 ${s.signal}

📊 EMA: ${s.emaText}
⚡ ${s.cross}

🎯 ${s.tp[0].toFixed(2)} ${check(s.tp[0])}
🎯 ${s.tp[1].toFixed(2)} ${check(s.tp[1])}
🎯 ${s.tp[2].toFixed(2)} ${check(s.tp[2])}
🎯 ${s.tp[3].toFixed(2)} ${check(s.tp[3])}
🎯 ${s.tp[4].toFixed(2)} ${check(s.tp[4])}
🎯 ${s.tp[5].toFixed(2)} ${check(s.tp[5])}
🎯 ${s.tp[6].toFixed(2)} ${check(s.tp[6])}
🎯 ${s.tp[7].toFixed(2)} ${check(s.tp[7])}

${s.activity}
━━━━━━━━━━━━`;
}

// =======================
async function getQuote(symbol) {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/quote?symbol=${symbol}&token=${API_KEY}`);
    const data = await res.json();

    lastData[symbol] = { price: data.c, prev: data.pc };
    return lastData[symbol];

  } catch {
    return null;
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

  let us = await getUSSymbols();

  for (let s of us) {
    let q = await getQuote(s.symbol);
    if (!q) continue;

    let a = analyze(q.price, q.prev);
    let ema = await getEMA(s.symbol);
    let extra = await getExtra(s.symbol);

    let text = format({
      name:s.symbol,
      market:"🇺🇸 السوق الأمريكي",
      price:q.price,
      ...a,
      ...ema,
      ...extra
    });

    for (let id of chatIds) {
      await bot.sendMessage(id, text);
    }

    await new Promise(r => setTimeout(r, 10));
  }

  running = false;
}

// =======================
// 💀 24/7 LOOP
async function startLoop() {
  while (true) {
    try {
      await run();
    } catch (e) {
      console.log(e);
    }
    await new Promise(r => setTimeout(r, 5000));
  }
}

startLoop();

app.listen(3000, () => {
  console.log("💀 RUNNING 24/7");
});
