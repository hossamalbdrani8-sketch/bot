import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();

// 🔑 التوكن (تم تثبيته)
const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";
const bot = new TelegramBot(TOKEN, { polling: true });

// =======================
// 🎯 chatId
// =======================
let chatId = null;

// =======================
// 🎯 استقبال
// =======================
bot.on("message", (msg) => {
  chatId = msg.chat.id;

  if (msg.text && msg.text.includes("/start")) {
    bot.sendMessage(chatId, "💀 AI PRO MAX CORE ACTIVE");
  }

  if (msg.text && msg.text.includes("/scan")) {
    runAI();
  }
});

// =======================
// 💰 محرك سعر ذكي
// =======================
let market = {};

function getPrice(symbol) {
  if (!market[symbol]) {
    market[symbol] = {
      price: 50 + Math.random() * 200,
      trend: Math.random() > 0.5 ? 1 : -1,
      momentum: 0.001 + Math.random() * 0.002
    };
  }

  let m = market[symbol];

  if (Math.random() < 0.05) {
    m.trend *= -1;
  }

  let move = m.trend * m.momentum;
  m.price *= (1 + move);

  return m.price;
}

// =======================
// 📊 RSI
// =======================
let history = {};

function calculateRSI(symbol, price) {
  if (!history[symbol]) history[symbol] = [];

  history[symbol].push(price);

  if (history[symbol].length < 14) return 50;

  let gains = 0;
  let losses = 0;

  for (let i = 1; i < history[symbol].length; i++) {
    let diff = history[symbol][i] - history[symbol][i - 1];
    if (diff > 0) gains += diff;
    else losses -= diff;
  }

  let rs = gains / (losses || 1);
  let rsi = 100 - (100 / (1 + rs));

  return Math.max(10, Math.min(90, rsi));
}

// =======================
// 💀 تحليل
// =======================
function analyze(price, rsi) {
  if (rsi < 25) return "💀 دخول مبكر قوي";
  if (rsi < 40) return "🟢 بداية صعود";
  if (rsi < 60) return "⚖️ ترند";
  if (rsi < 75) return "🔥 قوة";
  return "🔴 تصريف";
}

// =======================
// 🎯 أهداف
// =======================
function tp(price) {
  return [
    price * 1.02,
    price * 1.04,
    price * 1.06
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
// 🔥 تحليل سهم
// =======================
function analyzeAsset(marketName, symbol) {
  const price = getPrice(symbol);
  const rsi = calculateRSI(symbol, price);
  const signal = analyze(price, rsi);

  // فلترة (يمنع الإزعاج)
  if (rsi > 40 && rsi < 60) return;

  let msg = `${marketName}

🟢 ${symbol}
💰 ${price.toFixed(2)}
RSI: ${rsi.toFixed(1)}

${signal}

`;

  tp(price).forEach((t, i) => {
    msg += `🎯 TP${i + 1}: ${t.toFixed(2)}\n`;
  });

  send(msg);
}

// =======================
// 🔥 قوائم
// =======================
const saudi = Array.from({ length: 200 }, (_, i) => "TASI_" + (2000 + i));
const us = Array.from({ length: 500 }, (_, i) => "US_" + i);
const crypto = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE"];

// =======================
// 🔥 تشغيل
// =======================
function runAI() {
  saudi.forEach(s => analyzeAsset("🇸🇦 السوق السعودي", s));
  us.forEach(s => analyzeAsset("🇺🇸 السوق الأمريكي", s));
  crypto.forEach(s => analyzeAsset("🪙 العملات الرقمية", s));
}

// كل دقيقة
setInterval(runAI, 60000);

// =======================
// 🌐 السيرفر
// =======================
app.get("/", (req, res) => {
  res.send("💀 AI CORE RUNNING");
});

const port = process.env.PORT || 3000;
app.listen(port, () => {
  console.log("Server running on port " + port);
});
