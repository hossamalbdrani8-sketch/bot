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
    bot.sendMessage(chatId, "💀 AI PRO MAX FULL MARKET ACTIVATED");
    run();
  }

  if (msg.text === "/scan") {
    bot.sendMessage(chatId, "🚀 جاري فحص السوق كامل...");
    run();
  }
});

// =======================
// 🧠 تحليل (كما طلبت)
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
// 🎯 تنسيق (كما طلبت)
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
// 📊 APIs
// =======================
async function getUS(symbol) {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/quote?symbol=${symbol}&token=${API_KEY}`);
    const data = await res.json();
    return data?.c || null;
  } catch { return null; }
}

async function getSA(symbol) {
  try {
    const res = await fetch(`https://query1.finance.yahoo.com/v7/finance/quote?symbols=${symbol}`);
    const data = await res.json();
    return data?.quoteResponse?.result?.[0]?.regularMarketPrice || null;
  } catch { return null; }
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
    "GOOGL": "google.com",
    "META": "meta.com",

    "2222.SR": "aramco.com",
    "1120.SR": "alrajhibank.com.sa",
    "2010.SR": "sabic.com",
    "7010.SR": "stc.com.sa"
  };

  return `https://logo.clearbit.com/${map[symbol] || "google.com"}`;
}

// =======================
// 📦 قوائم
// =======================
const saudi = [
  ["أرامكو","2222.SR"],["الراجحي","1120.SR"],["سابك","2010.SR"],
  ["STC","7010.SR"],["معادن","1211.SR"],["الإنماء","1150.SR"],
  ["الأهلي","1180.SR"],["سافكو","2020.SR"],["بنك الرياض","1010.SR"],
  ["المراعي","2280.SR"],["جرير","4190.SR"],["صافولا","2050.SR"]
];

const us = [
  ["Tesla","TSLA"],["Apple","AAPL"],["NVIDIA","NVDA"],
  ["Amazon","AMZN"],["Microsoft","MSFT"],["Google","GOOGL"],
  ["Meta","META"],["AMD","AMD"],["Netflix","NFLX"],
  ["Palantir","PLTR"],["Intel","INTC"],["Uber","UBER"],
  ["Disney","DIS"],["Nike","NKE"]
];

// =======================
// 💀 فلتر مفتوح بالكامل
// =======================
function filterPro(data) {
  return data; // عرض الكل 💀
}

// =======================
// 🚀 التشغيل
// =======================
let running = false;

async function run() {
  if (!chatId || running) return;
  running = true;

  try {

    let all = [];

    // 🇸🇦 سعودي
    for (let s of saudi) {
      let price = await getSA(s[1]);
      if (!price) continue;

      let a = analyze(price);
      if (!a) continue;

      all.push({ name:s[0], symbol:s[1], price, ...a });
    }

    // 🇺🇸 أمريكي
    for (let s of us) {
      let price = await getUS(s[1]);
      if (!price) continue;

      let a = analyze(price);
      if (!a) continue;

      all.push({ name:s[0], symbol:s[1], price, ...a });
    }

    // 💀 السوق كامل بدون فلترة وبدون قص
    let fullMarket = filterPro(all);

    for (let s of fullMarket) {
      await bot.sendPhoto(chatId, getLogo(s.symbol), {
        caption: "💀 السوق كامل\n" + format(s)
      });

      await new Promise(r => setTimeout(r, 800));
    }

  } catch (e) {
    console.log("ERROR:", e.message);
  }

  running = false;
}

// =======================
// ⏱️ تحديث
// =======================
setInterval(run, 60000);

app.get("/", (req, res) => {
  res.send("💀 AI PRO MAX RUNNING");
});

app.listen(3000, () => {
  console.log("🔥 SERVER STARTED");
});
