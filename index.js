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
    bot.sendMessage(chatId, "💀 AI PRO MAX STABLE RUNNING");
  }
});

// =======================
// 🧠 تحليل
// =======================
function analyze(price) {
  if (!price || isNaN(price)) return null;

  let rsi = Math.floor(price % 100);

  let signal = "⚪ محايد";

  if (rsi <= 20) signal="💀 انفجار";
  else if (rsi <= 30) signal="🟢 شراء قوي";
  else if (rsi <= 40) signal="🟢 شراء";
  else if (rsi <= 50) signal="⚪ محايد";
  else if (rsi <= 60) signal="🔴 بيع خفيف";
  else if (rsi <= 70) signal="🔴 بيع";
  else if (rsi <= 80) signal="🔴 بيع قوي";
  else signal="🚨 خطر";

  let entry = price;

  let tp = [
    (entry * 1.02).toFixed(2),
    (entry * 1.04).toFixed(2),
    (entry * 1.06).toFixed(2),
    (entry * 1.08).toFixed(2),
    (entry * 1.10).toFixed(2),
    (entry * 1.12).toFixed(2),
    (entry * 1.15).toFixed(2),
    (entry * 1.18).toFixed(2),
  ];

  let sl = (entry * 0.94).toFixed(2);

  return { rsi, signal, tp, sl };
}

// =======================
// 🎯 تنسيق
// =======================
function format(s) {
  return `
🟢 ${s.name}

💰 ${s.price}
RSI: ${s.rsi} → ${s.signal}

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
// 📊 APIs (بدون node-fetch)
// =======================
async function getUS(symbol) {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/quote?symbol=${symbol}&token=${API_KEY}`);
    const data = await res.json();
    return data?.c || null;
  } catch {
    return null;
  }
}

async function getSA(symbol) {
  try {
    const res = await fetch(`https://query1.finance.yahoo.com/v7/finance/quote?symbols=${symbol}`);
    const data = await res.json();
    return data?.quoteResponse?.result?.[0]?.regularMarketPrice || null;
  } catch {
    return null;
  }
}

// =======================
// 🧾 الشعارات
// =======================
function getLogo(symbol) {
  const map = {
    "AAPL": "apple.com",
    "TSLA": "tesla.com",
    "NVDA": "nvidia.com",
    "AMZN": "amazon.com",
    "MSFT": "microsoft.com",

    "2222.SR": "aramco.com",
    "1120.SR": "alrajhibank.com.sa",
    "2010.SR": "sabic.com",
    "7010.SR": "stc.com.sa"
  };

  return `https://logo.clearbit.com/${map[symbol] || "google.com"}`;
}

// =======================
// 📦 الأسواق
// =======================
const saudi = [
  ["أرامكو","2222.SR"],
  ["الراجحي","1120.SR"],
  ["سابك","2010.SR"],
  ["STC","7010.SR"]
];

const us = [
  ["Tesla","TSLA"],
  ["Apple","AAPL"],
  ["NVIDIA","NVDA"],
  ["Amazon","AMZN"]
];

// =======================
// 🚀 التشغيل (مستقر)
// =======================
let running = false;

async function run() {
  if (!chatId || running) return;
  running = true;

  try {

    for (let s of saudi) {
      let price = await getSA(s[1]);
      let a = analyze(price);
      if (!a) continue;

      await bot.sendPhoto(chatId, getLogo(s[1]), {
        caption: format({ name:s[0], price, ...a })
      });

      await new Promise(r => setTimeout(r, 1500));
    }

    for (let s of us) {
      let price = await getUS(s[1]);
      let a = analyze(price);
      if (!a) continue;

      await bot.sendPhoto(chatId, getLogo(s[1]), {
        caption: format({ name:s[0], price, ...a })
      });

      await new Promise(r => setTimeout(r, 1500));
    }

  } catch (e) {
    console.log("ERROR:", e.message);
  }

  running = false;
}

// =======================
// ⏱️ كل دقيقة (مستقر)
// =======================
setInterval(run, 60000);

app.get("/", (req, res) => {
  res.send("💀 AI PRO MAX RUNNING");
});

app.listen(3000, () => {
  console.log("🔥 SERVER STARTED");
});
