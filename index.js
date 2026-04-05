import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();
app.use(express.json());

// 🔑 TOKEN
const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";
const bot = new TelegramBot(TOKEN, { polling: true });

// 🔑 API
const API_KEY = "d75o0l1r01qk56kdfon0d75o0l1r01qk56kdfong";

let chatId = null;

bot.on("message", (msg) => {
  chatId = msg.chat.id;

  if (msg.text === "/start") {
    bot.sendMessage(chatId, "💀 AI PRO MAX FULL MARKET (SMART MONEY)");
    run();
  }

  if (msg.text === "/scan") {
    bot.sendMessage(chatId, "🚀 فحص السوق كامل...");
    run();
  }
});

// =======================
function analyze(price, prev) {
  if (!price || !prev || prev === 0 || price <= 0) return null;

  let change = ((price - prev) / prev) * 100;

  let signal = "⚪ محايد";
  let emoji = "";
  let smart = "";
  let type = "🐠 مضاربين"; // افتراضي

  if (change > 3) {
    signal = "💰 دخول مؤسسات فعلي";
    emoji = "⚡️";
    smart = "🔥 Smart Money";
    type = "🦈 هوامير"; // قوي
  } 
  else if (change > 1.5) {
    signal = "🧠 تجميع صامت";
    smart = "📈 Accumulation";
    type = "🐠 مضاربين";
  } 
  else if (change < -3) {
    signal = "🚨 تصريف ذكي";
    emoji = "⚡️";
    smart = "📉 Distribution";
    type = "🦈 هوامير";
  }

  function fix(n) {
    return Number(n).toFixed(price < 1 ? 6 : 2);
  }

  let tp = [
    fix(price * 1.02),
    fix(price * 1.04),
    fix(price * 1.06),
    fix(price * 1.08),
    fix(price * 1.10),
    fix(price * 1.12),
    fix(price * 1.15),
    fix(price * 1.18),
  ];

  let sl = fix(price * 0.95);

  return { signal, tp, sl, emoji, change, smart, type };
}

// =======================
function format(s) {
  return `
${s.market}
${s.type}

${s.emoji} ${s.name}

💰 ${Number(s.price).toFixed(s.price < 1 ? 6 : 2)}
📊 ${s.signal} (${s.change.toFixed(2)}%)
${s.smart ? "🧠 " + s.smart : ""}

🎯 TP1: ${s.tp[0]}
🎯 TP2: ${s.tp[1]}
🎯 TP3: ${s.tp[2]}
🎯 TP4: ${s.tp[3]}
🎯 TP5: ${s.tp[4]}
🎯 TP6: ${s.tp[5]}
🎯 TP7: ${s.tp[6]}
🎯 TP8: ${s.tp[7]}

🛑 SL: ${s.sl}
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

    return {
      price: p.regularMarketPrice,
      prev: p.regularMarketPreviousClose
    };
  } catch {
    return null;
  }
}

// =======================
// 💰 العملات (الإضافة المهمة)
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
const saudi = [
"2222.SR","1120.SR","2010.SR","7010.SR"
];

async function getUSSymbols() {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/stock/symbol?exchange=US&token=${API_KEY}`);
    return await res.json();
  } catch {
    return [];
  }
}

// =======================
let running = false;

async function run() {
  if (!chatId || running) return;
  running = true;

  try {

    let all = [];

    // 🇸🇦
    for (let s of saudi) {
      let q = await getSA(s);
      if (!q) continue;

      let a = analyze(q.price, q.prev);
      if (!a) continue;

      all.push({ 
        name:s,
        symbol:s,
        market:"🇸🇦 السوق السعودي",
        price:q.price,
        ...a
      });
    }

    // 🇺🇸
    let us = await getUSSymbols();
    for (let s of us.slice(0,50)) {
      if (!s.symbol) continue;

      let q = await getQuote(s.symbol);
      if (!q) continue;

      let a = analyze(q.price, q.prev);
      if (!a) continue;

      all.push({ 
        name:s.symbol,
        symbol:s.symbol,
        market:"🇺🇸 السوق الأمريكي",
        price:q.price,
        ...a
      });
    }

    // 💰 كريبتو
    let crypto = await getCryptoSymbols();
    for (let c of crypto.slice(0,40)) {
      if (!c.symbol) continue;

      let q = await getQuote(c.symbol);
      if (!q) continue;

      let a = analyze(q.price, q.prev);
      if (!a) continue;

      all.push({
        name:c.displaySymbol || c.symbol,
        symbol:c.symbol,
        market:"💰 العملات الرقمية",
        price:q.price,
        ...a
      });
    }

    // 🚀 إرسال
    for (let s of all) {
      await safeSend(chatId, s.symbol, format(s));
      await new Promise(r => setTimeout(r, 200));
    }

  } catch (e) {
    console.log("ERROR:", e.message);
  }

  running = false;
}

setInterval(run, 60000);

app.listen(3000, () => {
  console.log("🔥 RUNNING");
});
