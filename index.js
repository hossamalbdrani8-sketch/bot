import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();

// 🔑 التوكن
const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";
const bot = new TelegramBot(TOKEN, { polling: true });

// 🔑 API المدفوع (حطه هنا)
const API_KEY = "PUT_YOUR_API_KEY_HERE";

let chatId = null;

// =======================
// 🎯 استقبال
// =======================
bot.on("message", (msg) => {
  chatId = msg.chat.id;

  if (msg.text?.includes("/start")) {
    bot.sendMessage(chatId, "💀 AI PRO MAX ELITE ACTIVE");
  }

  if (msg.text?.includes("/scan")) {
    runAI();
  }
});

// =======================
// 📊 جلب السوق (API)
// =======================

// 🇸🇦
async function getSaudiMarket() {
  const res = await fetch(`https://YOUR_API/saudi?apikey=${API_KEY}`);
  const data = await res.json();
  return data; // [{symbol,name,price,state}]
}

// 🇺🇸
async function getUSMarket() {
  const res = await fetch(`https://YOUR_API/us?apikey=${API_KEY}`);
  const data = await res.json();
  return data;
}

// 🪙
async function getCryptoMarket() {
  const res = await fetch(`https://YOUR_API/crypto?apikey=${API_KEY}`);
  const data = await res.json();
  return data;
}

// =======================
// 📊 RSI
// =======================
let history = {};

function calcRSI(symbol, price) {

  if (!history[symbol]) history[symbol] = [];
  history[symbol].push(price);

  if (history[symbol].length > 20) history[symbol].shift();
  if (history[symbol].length < 14) return 50;

  let gain = 0, loss = 0;

  for (let i = 1; i < history[symbol].length; i++) {
    let diff = history[symbol][i] - history[symbol][i - 1];
    if (diff > 0) gain += diff;
    else loss -= diff;
  }

  let rs = gain / (loss || 1);
  return 100 - (100 / (1 + rs));
}

// =======================
// 💀 تحليل AI
// =======================
function analyze(rsi) {

  if (rsi < 25) return "💀 انفجار قريب";
  if (rsi < 40) return "🟢 دخول مبكر";
  if (rsi < 60) return "⚖️ ترند";
  if (rsi < 75) return "🔥 قوة";

  return "🔴 تصريف";
}

// =======================
// 🎯 أهداف
// =======================
function targets(price) {
  return [
    price*1.02, price*1.04, price*1.06, price*1.08,
    price*1.10, price*1.12, price*1.15, price*1.20
  ];
}

// =======================
// 📩 إرسال
// =======================
function send(msg) {
  if (!chatId) return;
  bot.sendMessage(chatId, msg);
}

// =======================
// 🧠 فلترة قوية
// =======================
function strong(rsi) {
  return rsi < 35 || rsi > 70;
}

// =======================
// 🔥 تحليل أصل
// =======================
function process(asset, flag) {

  const price = asset.price;
  const rsi = calcRSI(asset.symbol, price);

  if (!strong(rsi)) return;

  const signal = analyze(rsi);

  let session = asset.state || "MARKET";

  let msg = `${flag} ${asset.name}

💰 ${price}
RSI: ${rsi.toFixed(1)}

${signal}
📊 الحالة: ${session}
`;

  targets(price).forEach((t,i)=>{
    msg += `🎯 TP${i+1}: ${t.toFixed(2)}\n`;
  });

  send(msg);
}

// =======================
// 🔥 تشغيل كامل
// =======================
async function runAI() {

  try {

    console.log("AI RUNNING...");

    const saudi = await getSaudiMarket();
    const us = await getUSMarket();
    const crypto = await getCryptoMarket();

    saudi.forEach(s => process(s, "🇸🇦"));
    us.forEach(s => process(s, "🇺🇸"));
    crypto.forEach(s => process(s, "🪙"));

  } catch (e) {
    console.log("ERROR:", e.message);
  }
}

// ⏱️ كل دقيقتين
setInterval(runAI, 120000);

// =======================
app.get("/", (req, res) => {
  res.send("💀 AI PRO MAX ELITE RUNNING");
});

app.listen(3000);
