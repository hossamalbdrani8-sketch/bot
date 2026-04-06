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

// 🔑 API (تم التحديث فقط)
const API_KEY = "d7a0311r01qspme6c44gd7a0311r01qspme6c450";

let chatId = null;
let memory = {};
let running = false;

// 💀 حماية من الكراش
process.on("uncaughtException", (err) => {
  console.log("💀 CRASH:", err.message);
});

process.on("unhandledRejection", (err) => {
  console.log("💀 PROMISE ERROR:", err);
});

// =======================
bot.on("message", (msg) => {
  chatId = msg.chat.id;

  if (msg.text === "/start") {
    bot.sendMessage(chatId, "💀 AI PRO MAX ELITE MODE (ULTIMATE)");
    run();
  }

  if (msg.text === "/scan") {
    bot.sendMessage(chatId, "🚀 فحص السوق...");
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

  if (!memory[symbol]) {
    memory[symbol] = {
      price: price,
      low: price,
      high: price,
      lastBreak: false
    };
  }

  let prevData = memory[symbol];

  if (price < prevData.low) prevData.low = price;
  if (price > prevData.high) prevData.high = price;

  let fromLow = ((price - prevData.low) / prevData.low) * 100;
  let breakHigh = price > prevData.high * 0.995;

  let flow = price > prevData.price ? "💹 سيولة مستمرة" : "⚠️ ضعف السيولة";

  if (change > 3) {
    signal = "💰 دخول مؤسسات فعلي";
    emoji = "⚡️";
    smart = "🔥 Smart Money";
    type = "🦈 هوامير";
  } 
  else if (change > 1.5) {
    signal = "🧠 تجميع صامت";
    smart = "📈 Accumulation";
  } 
  else if (change < -3) {
    signal = "🚨 تصريف ذكي";
    emoji = "⚡️";
    smart = "📉 Distribution";
    type = "🦈 هوامير";
  }

  if (fromLow > 2 && fromLow < 6 && change > 0.5) {
    entry = "💀 دخول من القاع";
  }

  if (fromLow >= 6 && change > 2 && flow.includes("💹")) {
    entry = "🚀 انطلاق موجة قوية";
  }

  if (fromLow > 3 && breakHigh && flow.includes("💹") && change > 2) {
    entry = "💀🔥 دخول احترافي مؤكد";
  }

  function fix(n) {
    return Number(n).toFixed(price < 1 ? 6 : 2);
  }

  let tpRaw = [
    price * 1.02,
    price * 1.04,
    price * 1.06,
    price * 1.08,
    price * 1.10,
    price * 1.12,
    price * 1.15,
    price * 1.18,
  ];

  let tp = tpRaw.map(v => fix(v));
  let tpStatus = tpRaw.map(v => price >= v);
  let sl = fix(price * 0.95);

  memory[symbol] = {
    price,
    low: prevData.low,
    high: price > prevData.high ? price : prevData.high
  };

  return {
    signal, tp, sl, emoji, change, smart,
    type, entry, flow, tpStatus, fromLow
  };
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

━━━━━━━━━━━━`;
}

// =======================
async function getQuote(symbol) {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/quote?symbol=${symbol}&token=${API_KEY}`);
    const data = await res.json();
    if (!data || !data.c || !data.pc) return null;
    return { price: data.c, prev: data.pc };
  } catch {
    return null;
  }
}

async function getSA(symbol) {
  try {
    const res = await fetch(`https://query1.finance.yahoo.com/v7/finance/quote?symbols=${symbol}`);
    const data = await res.json();
    let p = data?.quoteResponse?.result?.[0];
    if (!p) return null;
    return { price: p.regularMarketPrice, prev: p.regularMarketPreviousClose };
  } catch {
    return null;
  }
}

async function getCryptoSymbols() {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/crypto/symbol?exchange=BINANCE&token=${API_KEY}`);
    return await res.json();
  } catch {
    return [];
  }
}

// =======================
function getLogo(symbol) {
  return `https://logo.clearbit.com/${symbol.replace(".SR","").toLowerCase()}.com`;
}

async function safeSend(chatId, symbol, text) {
  try {
    await bot.sendPhoto(chatId, getLogo(symbol), { caption: text });
  } catch {
    await bot.sendMessage(chatId, text);
  }
}

// =======================
const saudi = ["2222.SR","1120.SR","2010.SR","7010.SR"];

async function getUSSymbols() {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/stock/symbol?exchange=US&token=${API_KEY}`);
    return await res.json();
  } catch {
    return [];
  }
}

// =======================
async function run() {
  if (!chatId || running) return;
  running = true;

  try {
    let all = [];

    for (let s of saudi) {
      let q = await getSA(s);
      if (!q) continue;
      let a = analyze(q.price, q.prev, s);
      if (!a) continue;
      all.push({ name:s, symbol:s, market:"🇸🇦 السوق السعودي", price:q.price, ...a });
    }

    let us = await getUSSymbols();
    for (let s of us.slice(0,50)) {
      if (!s.symbol) continue;
      let q = await getQuote(s.symbol);
      if (!q) continue;
      let a = analyze(q.price, q.prev, s.symbol);
      if (!a) continue;
      all.push({ name:s.symbol, symbol:s.symbol, market:"🇺🇸 السوق الأمريكي", price:q.price, ...a });
    }

    let crypto = await getCryptoSymbols();
    for (let c of crypto.slice(0,40)) {
      if (!c.symbol) continue;
      let q = await getQuote(c.symbol);
      if (!q) continue;
      let a = analyze(q.price, q.prev, c.symbol);
      if (!a) continue;
      all.push({ name:c.displaySymbol || c.symbol, symbol:c.symbol, market:"💰 العملات الرقمية", price:q.price, ...a });
    }

    for (let s of all) {
      await safeSend(chatId, s.symbol, format(s));
      await new Promise(r => setTimeout(r, 200));
    }

  } catch (e) {
    console.log("ERROR:", e.message);
  }

  running = false;
}

// 💀 تشغيل دائم
setInterval(run, 60000);

app.listen(3000, () => {
  console.log("🔥 AI PRO MAX ELITE ULTIMATE RUNNING");
});
