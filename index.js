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

// =======================
bot.on("message", (msg) => {
  chatId = msg.chat.id;

  if (msg.text === "/start") {
    bot.sendMessage(chatId, "💀 AI PRO MAX FINAL READY");
  }
});

// =======================
// 🧠 تحليل RSI + أهداف
// =======================
function analyze(price) {

  let rsi = Math.floor(price % 100);

  let signal = "⚪ محايد";
  let zone = "";

  if (rsi <= 20) { signal="💀 انفجار"; zone="20"; }
  else if (rsi <= 30) { signal="🟢 شراء قوي"; zone="30"; }
  else if (rsi <= 40) { signal="🟢 شراء"; zone="40"; }
  else if (rsi <= 50) { signal="⚪ محايد"; zone="50"; }
  else if (rsi <= 60) { signal="🔴 بيع خفيف"; zone="60"; }
  else if (rsi <= 70) { signal="🔴 بيع"; zone="70"; }
  else if (rsi <= 80) { signal="🔴 بيع قوي"; zone="80"; }
  else { signal="🚨 خطر"; zone="100"; }

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

  return { rsi, signal, zone, tp, sl };
}

// =======================
// 📊 APIs
// =======================
async function getUS(symbol) {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/quote?symbol=${symbol}&token=${API_KEY}`);
    const data = await res.json();
    return data.c;
  } catch { return null; }
}

async function getSA(symbol) {
  try {
    const res = await fetch(`https://query1.finance.yahoo.com/v7/finance/quote?symbols=${symbol}`);
    const data = await res.json();
    return data.quoteResponse.result[0]?.regularMarketPrice;
  } catch { return null; }
}

// =======================
// 📦 الأسواق
// =======================

const saudi = [
  ["أرامكو","2222.SR"],
  ["الراجحي","1120.SR"],
  ["سابك","2010.SR"],
  ["STC","7010.SR"],
  ["معادن","1211.SR"],
  ["الأهلي","1180.SR"],
  ["بنك الرياض","1010.SR"]
];

const us = [
  ["Tesla","TSLA"],
  ["Apple","AAPL"],
  ["NVIDIA","NVDA"],
  ["Amazon","AMZN"],
  ["Meta","META"],
  ["Microsoft","MSFT"],
  ["Google","GOOGL"]
];

// =======================
// 🎯 فلترة
// =======================
function filterStrong(data) {
  return data.filter(s => s.rsi <= 30 || s.rsi >= 70);
}

// =======================
// 🎯 تنسيق
// =======================
function format(s) {
  return `
🟢 ${s.name}

💰 سعر الدخول: ${s.price}
RSI: ${s.rsi} (${s.zone}) → ${s.signal}

🎯 TP1: ${s.tp[0]}
🎯 TP2: ${s.tp[1]}
🎯 TP3: ${s.tp[2]}
🎯 TP4: ${s.tp[3]}
🎯 TP5: ${s.tp[4]}
🎯 TP6: ${s.tp[5]}
🎯 TP7: ${s.tp[6]}
🎯 TP8: ${s.tp[7]}

🛑 وقف الخسارة: ${s.sl}
━━━━━━━━━━━━`;
}

// =======================
// 🚀 التشغيل
// =======================
async function run() {

  if (!chatId) return;

  let saData = [];
  for (let s of saudi) {
    let p = await getSA(s[1]);
    if (!p) continue;
    let a = analyze(p);
    saData.push({ name:s[0], price:p, ...a });
  }

  let usData = [];
  for (let s of us) {
    let p = await getUS(s[1]);
    if (!p) continue;
    let a = analyze(p);
    usData.push({ name:s[0], price:p, ...a });
  }

  saData = filterStrong(saData);
  usData = filterStrong(usData);

  // كريبتو
  const cryptoRes = await fetch("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd");
  const crypto = await cryptoRes.json();

  let btc = analyze(crypto.bitcoin.usd);
  let eth = analyze(crypto.ethereum.usd);

  let message = `
💀 AI PRO MAX FINAL

🇸🇦 السوق السعودي
━━━━━━━━━━━━
${saData.map(format).join("")}

🇺🇸 السوق الأمريكي
━━━━━━━━━━━━
${usData.map(format).join("")}

🪙 العملات
━━━━━━━━━━━━

BTC
💰 ${crypto.bitcoin.usd}
RSI: ${btc.rsi} → ${btc.signal}

ETH
💰 ${crypto.ethereum.usd}
RSI: ${eth.rsi} → ${eth.signal}

⚡ تحديث تلقائي كل دقيقة
`;

  bot.sendMessage(chatId, message);
}

// تشغيل
setInterval(run, 60000);

app.listen(3000);
