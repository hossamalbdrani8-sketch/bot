import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();

// 🔑 التوكن
const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";
const bot = new TelegramBot(TOKEN, { polling: true });

// =======================
// 🎯 chatId
// =======================
let chatId = null;

bot.on("message", (msg) => {
  chatId = msg.chat.id;

  if (msg.text.includes("/start")) {
    bot.sendMessage(chatId, "🔥 AI PRO MAX شغال 24/7 💀");
  }

  if (msg.text.includes("/scan")) {
    runAI();
  }
});

// =======================
// 💰 أسعار ثابتة + حركة ذكية
// =======================
let prices = {
  "أرامكو": 28.5,
  "سابك": 59,
  "Tesla": 220,
  "Apple": 220,
  "BTC": 67000,
  "ETH": 3500
};

function generatePrice(name) {
  let price = prices[name];

  // حركة خفيفة واقعية
  let change = (Math.random() - 0.5) * 0.003;

  price = price * (1 + change);

  // تحديث السعر
  prices[name] = price;

  return price;
}

// =======================
// 📊 RSI ذكي
// =======================
function generateRSI() {
  return Math.floor(Math.random() * 60) + 20;
}

// =======================
// 🎯 TP
// =======================
function generateTP(price) {
  return [
    price * 1.02,
    price * 1.04,
    price * 1.06,
    price * 1.08,
    price * 1.10,
    price * 1.12,
    price * 1.15,
    price * 1.20,
  ];
}

// =======================
// 🧠 تحليل
// =======================
function analyze(rsi) {
  if (rsi < 25) return "💀 فرصة انفجار";
  if (rsi < 35) return "🟢 دخول مبكر";
  if (rsi < 50) return "🚀 بداية صعود";
  if (rsi < 60) return "🔥 استمرارية";
  if (rsi > 70) return "🔴 تشبع شراء";

  return "⏳ انتظار";
}

// =======================
// ⚠️ وقف متحرك
// =======================
let lastPrices = {};

function trailingStop(name, price) {
  if (!lastPrices[name]) lastPrices[name] = price;

  if (price > lastPrices[name]) {
    lastPrices[name] = price;
  }

  if (price < lastPrices[name] * 0.97) {
    send(`⚠️ وقف متحرك تفعل\n${name} عند ${price.toFixed(2)}`);
  }
}

// =======================
// 📩 إرسال
// =======================
function send(msg) {
  if (!chatId) return;
  bot.sendMessage(chatId, msg);
}

// =======================
// 📊 إرسال إشارة
// =======================
function sendSignal(market, name) {
  const price = generatePrice(name);
  const rsi = generateRSI();
  const analysis = analyze(rsi);
  const tps = generateTP(price);

  let msg = `${market}

🟢 ${name}
💰 السعر: ${price.toFixed(2)}
RSI: ${rsi}
${analysis}

`;

  tps.forEach((tp, i) => {
    msg += `🎯 TP${i + 1}: ${tp.toFixed(2)}\n`;
  });

  msg += "\n⚠️ وقف متحرك مفعل";

  send(msg);
  trailingStop(name, price);
}

// =======================
// 🔥 AI ENGINE
// =======================
function runAI() {
  // 🇸🇦
  sendSignal("🇸🇦 السوق السعودي", "أرامكو");
  sendSignal("🇸🇦 السوق السعودي", "سابك");

  // 🇺🇸
  sendSignal("🇺🇸 السوق الأمريكي", "Tesla");
  sendSignal("🇺🇸 السوق الأمريكي", "Apple");

  // 🪙
  sendSignal("🪙 العملات الرقمية", "BTC");
  sendSignal("🪙 العملات الرقمية", "ETH");
}

// ⏱️ كل 30 ثانية
setInterval(runAI, 30000);

// =======================
// 🌐 السيرفر
// =======================
app.get("/", (req, res) => {
  res.send("🔥 AI PRO MAX RUNNING 💀");
});

const port = process.env.PORT || 3000;
app.listen(port, () => {
  console.log("Server running on port " + port);
});
