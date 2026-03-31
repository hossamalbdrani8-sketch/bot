import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();
app.use(express.json());

const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";
const bot = new TelegramBot(TOKEN, { polling: true });

const API_KEY = "d75o0l1r01qk56kdfon0d75o0l1r01qk56kdfong";

let chatId = null;
let sentSignals = new Set(); // 🔥 بدون تكرار

// =======================
bot.on("message", (msg) => {
  chatId = msg.chat.id;

  if (msg.text === "/start") {
    bot.sendMessage(chatId, "💀 AI PRO MAX HEDGE MODE");
  }
});

// =======================
// 🧠 حساب RSI الحقيقي
// =======================
function calculateRSI(closes) {
  let gains = 0, losses = 0;

  for (let i = 1; i < closes.length; i++) {
    let diff = closes[i] - closes[i - 1];
    if (diff > 0) gains += diff;
    else losses -= diff;
  }

  let avgGain = gains / closes.length;
  let avgLoss = losses / closes.length;

  if (avgLoss === 0) return 100;

  let rs = avgGain / avgLoss;
  return Math.floor(100 - (100 / (1 + rs)));
}

// =======================
// 📊 RSI API
// =======================
async function getRSI(symbol) {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/stock/candle?symbol=${symbol}&resolution=5&count=50&token=${API_KEY}`);
    const data = await res.json();

    if (!data.c) return null;

    return calculateRSI(data.c);
  } catch {
    return null;
  }
}

// =======================
// 📊 السعر
// =======================
async function getPrice(symbol) {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/quote?symbol=${symbol}&token=${API_KEY}`);
    const data = await res.json();
    return data.c;
  } catch {
    return null;
  }
}

// =======================
// 🎯 تحليل احترافي
// =======================
function analyze(price, rsi) {

  let signal = null;
  let tp = [];
  let sl = null;

  if (rsi <= 30) {
    signal = "🟢 BUY 💀";
    for (let i = 1; i <= 8; i++) {
      tp.push((price * (1 + i * 0.02)).toFixed(2));
    }
    sl = (price * 0.95).toFixed(2);
  }

  if (rsi >= 70) {
    signal = "🔴 SELL 💀";
    for (let i = 1; i <= 8; i++) {
      tp.push((price * (1 - i * 0.02)).toFixed(2));
    }
    sl = (price * 1.05).toFixed(2);
  }

  return { signal, tp, sl };
}

// =======================
// 📦 قائمة كبيرة (تقدر تزودها)
// =======================
const symbols = [
  "AAPL","TSLA","NVDA","MSFT","AMZN","META","GOOGL",
  "AMD","NFLX","INTC",
  "2222.SR","1120.SR","2010.SR","1211.SR","7010.SR"
];

// =======================
// 🚀 الفلتر
// =======================
async function run() {

  if (!chatId) return;

  let message = "💀 AI PRO MAX HEDGE SCANNER\n\n";

  for (let sym of symbols) {

    const price = await getPrice(sym);
    const rsi = await getRSI(sym);

    if (!price || !rsi) continue;

    const a = analyze(price, rsi);

    if (!a.signal) continue;

    // 💀 منع التكرار
    let key = sym + a.signal;
    if (sentSignals.has(key)) continue;
    sentSignals.add(key);

    message += `
📊 ${sym}
💰 ${price}
RSI: ${rsi}
${a.signal}

🎯 ${a.tp.join(" | ")}

🛑 ${a.sl}
━━━━━━━━━━━━
`;
  }

  if (message.length < 50) return;

  bot.sendMessage(chatId, message);
}

// =======================
setInterval(run, 60000);

app.listen(3000, () => {
  console.log("💀 HEDGE MODE RUNNING");
});
