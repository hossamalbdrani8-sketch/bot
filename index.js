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
// 🎲 مولد سعر وهمي (واقعي)
// =======================
function generatePrice(base) {
  const change = (Math.random() - 0.5) * 0.02; // ±2%
  return base * (1 + change);
}

// =======================
// 📊 RSI وهمي ذكي
// =======================
function generateRSI() {
  return Math.floor(Math.random() * 60) + 20; // 20 - 80
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
// 🧠 تحليل ذكي 💀
// =======================
function analyze(rsi) {
  if (rsi < 25) return "💀 دخول قوي جداً (انفجار)";
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
// 📊 إرسال إشارة كاملة
// =======================
function sendSignal(market, name, basePrice) {
  const price = generatePrice(basePrice);
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
// 🔥 AI ENGINE (ما يسكت 💀)
// =======================
function runAI() {
  // 🇸🇦
  sendSignal("🇸🇦 السوق السعودي", "أرامكو", 30);
  sendSignal("🇸🇦 السوق السعودي", "سابك", 90);

  // 🇺🇸
  sendSignal("🇺🇸 السوق الأمريكي", "Tesla", 250);
  sendSignal("🇺🇸 السوق الأمريكي", "Apple", 180);

  // 🪙
  sendSignal("🪙 العملات الرقمية", "BTC", 67000);
  sendSignal("🪙 العملات الرقمية", "ETH", 3500);
}

// ⏱️ كل 30 ثانية (💀 هجومي)
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
