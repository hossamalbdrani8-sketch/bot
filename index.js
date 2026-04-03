import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();
app.use(express.json());

// 🔑 TOKEN
const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";
const bot = new TelegramBot(TOKEN, { polling: true });


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

  if (change > 3) {
    signal = "💰 دخول مؤسسات فعلي";
    emoji = "⚡️";
    smart = "🔥 Smart Money";
  } 
  else if (change > 1.5) {
    signal = "🧠 تجميع صامت";
    smart = "📈 Accumulation";
  } 
  else if (change < -3) {
    signal = "🚨 تصريف ذكي";
    emoji = "⚡️";
    smart = "📉 Distribution";
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

  return { signal, tp, sl, emoji, change, smart };
}

// =======================
function format(s) {
  return `
${s.market}
${s.emoji} ${s.name}

💰 ${s.price}
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

    // 🇸🇦 تاسي
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

    // 🇺🇸 أمريكي
    let us = await getUSSymbols();
    for (let s of us.slice(0,15)) {
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

    // 🪙 كريبتو (تم تفعيله ✅)
    let crypto = await getCryptoSymbols();
    for (let c of crypto.slice(0,10)) {
      let q = await getQuote(c.symbol);
      if (!q) continue;

      let a = analyze(q.price, q.prev);
      if (!a) continue;

      all.push({
        name:c.symbol,
        symbol:c.symbol,
        market:"🪙 العملات الرقمية",
        price:q.price,
        ...a
      });
    }

    // 💀 فلترة قوية
    for (let s of all) {
      if (s.change > 3 || s.change < -3) {
        await safeSend(chatId, s.symbol, format(s));
      }
    }

  } catch (e) {
    console.log("ERROR:", e.message);
  }

  running = false;
}

setInterval(run, 60000);

app.get("/", (req, res) => {
  res.send("OK");
});

app.listen(3000, () => {
  console.log("🔥 RUNNING");
});
