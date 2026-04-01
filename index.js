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
    bot.sendMessage(chatId, "💀 AI PRO MAX FULL MARKET (TASI + US + CRYPTO)");
    run();
  }

  if (msg.text === "/scan") {
    bot.sendMessage(chatId, "🚀 فحص السوق كامل...");
    run();
  }
});

// =======================
// 🧠 تحليل + زخم ⚡️
// =======================
function analyze(price, prev) {
  if (!price || !prev) return null;

  let change = ((price - prev) / prev) * 100;

  let signal = "⚪ محايد";
  let emoji = "";

  if (change > 2) {
    signal = "💀 دخول قوي";
    emoji = "⚡️";
  } else if (change > 1) {
    signal = "🟢 فرصة";
  } else if (change < -2) {
    signal = "🔴 تصريف";
    emoji = "⚡️";
  }

  let tp = [
    (price * 1.02).toFixed(2),
    (price * 1.04).toFixed(2),
    (price * 1.06).toFixed(2),
    (price * 1.08).toFixed(2),
    (price * 1.10).toFixed(2),
    (price * 1.12).toFixed(2),
    (price * 1.15).toFixed(2),
    (price * 1.18).toFixed(2),
  ];

  let sl = (price * 0.95).toFixed(2);

  return { signal, tp, sl, emoji, change };
}

// =======================
function format(s) {
  return `
${s.emoji} ${s.name}

💰 ${s.price}
📊 ${s.signal} (${s.change.toFixed(2)}%)

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
// 📊 APIs
// =======================
async function getQuote(symbol) {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/quote?symbol=${symbol}&token=${API_KEY}`);
    const data = await res.json();
    return { price: data.c, prev: data.pc };
  } catch { return null; }
}

async function getSA(symbol) {
  try {
    const res = await fetch(`https://query1.finance.yahoo.com/v7/finance/quote?symbols=${symbol}`);
    const data = await res.json();
    let p = data?.quoteResponse?.result?.[0];
    if (!p) return null;
    return { price: p.regularMarketPrice, prev: p.regularMarketPreviousClose };
  } catch { return null; }
}

// =======================
const saudi = [
"2222.SR","1120.SR","2010.SR","7010.SR","1211.SR","1150.SR",
"1180.SR","2020.SR","1010.SR","2280.SR","4190.SR","2050.SR"
];

async function getUSSymbols() {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/stock/symbol?exchange=US&token=${API_KEY}`);
    return await res.json();
  } catch { return []; }
}

async function getCryptoSymbols() {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/crypto/symbol?exchange=BINANCE&token=${API_KEY}`);
    return await res.json();
  } catch { return []; }
}

// =======================
let running = false;

async function run() {
  if (!chatId || running) return;
  running = true;

  try {

    let all = [];

    for (let s of saudi) {
      let q = await getSA(s);
      if (!q) continue;

      let a = analyze(q.price, q.prev);
      if (!a) continue;

      all.push({ name:s, price:q.price, ...a });
    }

    let us = await getUSSymbols();
    for (let s of us.slice(0,150)) {
      let q = await getQuote(s.symbol);
      if (!q) continue;

      let a = analyze(q.price, q.prev);
      if (!a) continue;

      all.push({ name:s.description || s.symbol, price:q.price, ...a });
    }

    let crypto = await getCryptoSymbols();
    for (let c of crypto.slice(0,80)) {
      let q = await getQuote(c.symbol);
      if (!q) continue;

      let a = analyze(q.price, q.prev);
      if (!a) continue;

      all.push({ name:c.displaySymbol, price:q.price, ...a });
    }

    for (let s of all) {
      await bot.sendMessage(chatId, "💀 MARKET FLOW\n" + format(s));
      await new Promise(r => setTimeout(r, 300));
    }

  } catch (e) {
    console.log("ERROR:", e.message);
  }

  running = false;
}

// =======================
setInterval(run, 60000);

const PORT = process.env.PORT || 3000;

app.listen(PORT, () => {
  console.log("🔥 FULL MARKET RUNNING ON " + PORT);
});
