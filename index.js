import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();

// 🔑 التوكن
const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";

const bot = new TelegramBot(TOKEN, { polling: true });

// =======================
// 🎯 التقاط chatId
// =======================
let msgChatId = null;

bot.on("message", (msg) => {
  msgChatId = msg.chat.id;

  if (msg.text === "/start") {
    bot.sendMessage(msgChatId, "🔥 AI PRO MAX شغال وجاهز");
  }
});

// =======================
// 🎯 TP + السعر
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
// 🧠 تحليل RSI متطور
// =======================
function analyzeMarket(asset) {
  const rsi = asset.rsi;

  if (rsi <= 20) return "💀 تشبع بيع قوي جداً (انفجار محتمل)";
  if (rsi <= 30) return "🟢 دخول مبكر + تأكيد";
  if (rsi <= 40) return "🚀 بداية صعود";
  if (rsi <= 50) return "📈 تأكيد اتجاه";
  if (rsi <= 60) return "🔥 استمرارية صعود";
  if (rsi <= 70) return "⚠️ قرب تشبع";
  if (rsi <= 80) return "🔴 تشبع شراء";
  return "💥 قمة خطر";
}

// =======================
// ⚠️ وقف متحرك مع السعر
// =======================
let lastPrice = 0;

function trailingStop(price) {
  if (price > lastPrice) {
    lastPrice = price;
  }

  if (price < lastPrice * 0.97) {
    sendSignal(`⚠️ وقف متحرك تفعل عند ${price}`);
  }
}

// =======================
// 📩 إرسال رسالة
// =======================
function sendSignal(msg) {
  if (!msgChatId) return;
  bot.sendMessage(msgChatId, msg);
}

// =======================
// 📊 إرسال إشارة كاملة
// =======================
function sendFullSignal(title, asset) {
  if (!msgChatId) return;

  const analysis = analyzeMarket(asset);
  const tps = generateTP(asset.price);

  let msg = `${title}

🟢 ${asset.name}
💰 السعر: ${asset.price}
RSI: ${asset.rsi}
${analysis}

`;

  tps.forEach((tp, i) => {
    msg += `🎯 TP${i + 1}: ${tp.toFixed(2)}\n`;
  });

  msg += "\n⚠️ وقف متحرك مفعل";

  bot.sendMessage(msgChatId, msg);

  trailingStop(asset.price);
}

// =======================
// 📊 الأسواق
// =======================

function saudiMarket() {
  return [
    { name: "أرامكو", price: 30, rsi: 28, volume: 2000000 },
    { name: "سابك", price: 90, rsi: 35, volume: 1500000 }
  ];
}

function usMarket() {
  return [
    { name: "Tesla", price: 250, rsi: 27, volume: 5000000 },
    { name: "Apple", price: 180, rsi: 45, volume: 3000000 }
  ];
}

function cryptoMarket() {
  return [
    { name: "BTC", price: 67000, rsi: 29, volume: 9000000 },
    { name: "ETH", price: 3500, rsi: 31, volume: 7000000 }
  ];
}

// =======================
// 🔥 تشغيل AI
// =======================
async function runAI() {

  for (const s of saudiMarket()) {
    sendFullSignal("🇸🇦 السوق السعودي", s);
  }

  for (const s of usMarket()) {
    sendFullSignal("🇺🇸 السوق الأمريكي", s);
  }

  for (const c of cryptoMarket()) {
    sendFullSignal("🪙 العملات الرقمية", c);
  }
}

// ⏱️ كل دقيقة
setInterval(runAI, 60000);

// =======================
// 🌐 السيرفر
// =======================
app.get("/", (req, res) => {
  res.send("🚀 AI PRO MAX RUNNING");
});

const port = process.env.PORT || 3000;
app.listen(port, () => {
  console.log("Server running on port " + port);
});
