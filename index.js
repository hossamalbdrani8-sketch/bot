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

async function getEMA(symbol) {
  let data = await getCandles(symbol);
  if (!data || data.length < 400) {
    return {
      emaText: "❌ EMA غير متوفر",
      cross: "❌"
    };
  }

  let ema7 = calculateEMA(data, 7);
  let ema25 = calculateEMA(data, 25);
  let ema50 = calculateEMA(data, 50);
  let ema320 = calculateEMA(data, 320);
  let ema380 = calculateEMA(data, 380);

  let trend = "⚪ تذبذب";

  if (ema7 > ema25 && ema25 > ema50 && ema50 > ema320) {
    trend = "💀 ترند صاعد قوي";
  }

  if (ema7 < ema25 && ema25 < ema50) {
    trend = "📉 ترند هابط";
  }

  let cross = "❌";

  if (ema7 > ema25 && ema7 > ema50) {
    cross = "🔥 تقاطع صاعد (دخول)";
  }

  if (ema7 < ema25 && ema7 < ema50) {
    cross = "🚨 تقاطع هابط (خروج)";
  }

  if (ema7 > ema25 && ema25 > ema50 && ema50 > ema320 && ema320 > ema380) {
    cross = "💀🔥 ELITE TREND";
  }

  return {
    emaText: trend,
    cross
  };
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
      if (m < 20) floatText = `💀 خفيف (انفجاري) ${m.toFixed(2)}M`;
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
bot.on("message", (msg) => {
  chatIds.add(msg.chat.id);

  if (msg.text === "/start") {
    bot.sendMessage(msg.chat.id, "💀 AI PRO MAX ELITE MODE (ULTIMATE)");
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
  let emoji = "";
  let smart = "";
  let type = "🐠 مضاربين";
  let entry = "⏳ انتظر";
  let alert = "";

  if (!memory[symbol]) {
    memory[symbol] = { price, low: price, high: price, momentum: 0 };
  }

  let prevData = memory[symbol];

  if (price < prevData.low) prevData.low = price;
  if (price > prevData.high) prevData.high = price;

  let fromLow = ((price - prevData.low) / prevData.low) * 100;
  let momentum = price - prevData.price;

  let flow = "⚠️ ضعف السيولة";
  if (momentum > 0 && change > 0.5) flow = "💹 سيولة مستمرة";
  if (momentum > 0.5 && change > 1.5) flow = "🔥💹 سيولة قوية";
  if (momentum > 1 && change > 2.5) flow = "💀🚀 سيولة انفجار";

  if (momentum > 0.4 && change > 1 && fromLow > 2) {
    alert = "⚠️💀 تنبيه قبل الانفجار";
  }
  if (momentum > 1 && change > 2.5 && fromLow > 3) {
    alert = "💀🚀 تأكيد انفجار";
  }

  if (change > 4) {
    signal = "💀🚀 دخول مؤسسات ضخم";
    emoji = "🔥";
    smart = "💀 Smart Money ELITE";
    type = "🦈 هوامير";
  } 
  else if (change > 2) {
    signal = "🔥 تجميع قوي";
    smart = "📈 Accumulation PRO";
  } 
  else if (change < -4) {
    signal = "🚨 تصريف عنيف";
    emoji = "⚡️";
    smart = "📉 Distribution";
    type = "🦈 هوامير";
  }

  if (fromLow > 1.5 && change > 0.3 && momentum > 0) entry = "⚡️ دخول مبكر";
  if (fromLow > 2 && change > 1) entry = "💀 دخول ذكي";
  if (fromLow > 3 && change > 2 && flow.includes("💹")) entry = "💀🔥 دخول احترافي";
  if (fromLow > 4 && change > 3 && flow.includes("💀")) entry = "💀🚀 ELITE";

  function fix(n) {
    return Number(n).toFixed(price < 1 ? 6 : 2);
  }

  let tpRaw = [
    price*1.02, price*1.04, price*1.06, price*1.08,
    price*1.10, price*1.12, price*1.15, price*1.18
  ];

  let tp = tpRaw.map(fix);
  let tpStatus = tpRaw.map(v => price >= v * 0.995);
  let sl = fix(price * 0.95);

  memory[symbol] = {
    price,
    low: prevData.low,
    high: prevData.high,
    momentum
  };

  return { signal,tp,sl,emoji,change,smart,type,entry,flow,tpStatus,fromLow,alert };
}

// =======================
function format(s) {
  return `
${s.market}
${s.type}

${s.emoji} ${s.name}

💰 ${Number(s.price).toFixed(s.price < 1 ? 6 : 2)}
📉 من القاع: ${s.fromLow.toFixed(2)}%

📊 ${s.signal} (${s.change.toFixed(2)}%)
${s.smart ? "🧠 " + s.smart : ""}

📦 ${s.floatText}
⚡ ${s.activity}
💵 ${s.liquidityText}

📊 EMA: ${s.emaText}
⚡ ${s.cross}

🎯 TP1: ${s.tp[0]} ${s.tpStatus[0] ? "✅" : ""}
🎯 TP2: ${s.tp[1]} ${s.tpStatus[1] ? "✅" : ""}
🎯 TP3: ${s.tp[2]} ${s.tpStatus[2] ? "✅" : ""}
🎯 TP4: ${s.tp[3]} ${s.tpStatus[3] ? "✅" : ""}
🎯 TP5: ${s.tp[4]} ${s.tpStatus[4] ? "✅" : ""}
🎯 TP6: ${s.tp[5]} ${s.tpStatus[5] ? "✅" : ""}
🎯 TP7: ${s.tp[6]} ${s.tpStatus[6] ? "✅" : ""}
🎯 TP8: ${s.tp[7]} ${s.tpStatus[7] ? "✅" : ""}

🛑 SL: ${s.sl}

${s.entry}
${s.flow}
${s.alert ? "🚨 " + s.alert : ""}

━━━━━━━━━━━━`;
}

// =======================
async function sendAll(symbol, text) {
  for (let id of chatIds) {
    try {
      await bot.sendPhoto(id, `https://logo.clearbit.com/${symbol.toLowerCase()}.com`, { caption: text });
    } catch {
      await bot.sendMessage(id, text);
    }
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

    for (let s of us) {
      if (!s.symbol) continue;

      let q = await getQuote(s.symbol);
      if (!q) continue;

      let a = analyze(q.price, q.prev, s.symbol);
      if (!a) continue;

      let extra = await getExtra(s.symbol);
      let ema = await getEMA(s.symbol);

      await sendAll(s.symbol, format({
        name:s.symbol,
        symbol:s.symbol,
        market:"🇺🇸 السوق الأمريكي",
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
  console.log("🔥 AI PRO MAX ELITE ULTIMATE RUNNING");
});
