import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();
const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";
const bot = new TelegramBot(TOKEN, { polling: true });

let chatId = null;

bot.on("message", (msg) => {
  chatId = msg.chat.id;

  if (msg.text.includes("/start")) {
    bot.sendMessage(chatId, "💀 AI PRO MAX ELITE ACTIVE");
  }

  if (msg.text.includes("/scan")) {
    runAI();
  }
});

// =======================
// 💰 السعر
// =======================
let prices = {
  "أرامكو": 28.5,
  "سابك": 59,
  "Tesla": 220,
  "Apple": 220,
  "BTC": 67000,
  "ETH": 3500
};

function priceMove(name) {
  let p = prices[name];
  let move = (Math.random() - 0.5) * 0.004;
  p = p * (1 + move);
  prices[name] = p;
  return p;
}

// =======================
// 📊 RSI ذكي
// =======================
let rsiMem = {};

function getRSI(name, price) {
  if (!rsiMem[name]) {
    rsiMem[name] = { last: price, rsi: 50 };
  }

  let diff = price - rsiMem[name].last;
  let rsi = rsiMem[name].rsi;

  rsi += diff > 0 ? 1.5 : -1.5;
  rsi = Math.max(10, Math.min(90, rsi));

  rsiMem[name] = { last: price, rsi };
  return rsi;
}

// =======================
// 🕯 تحليل شموع
// =======================
function candleSignal(price, prev) {
  if (!prev) return "⏳";

  if (price > prev * 1.002) return "🟢 شمعة صاعدة قوية";
  if (price < prev * 0.998) return "🔴 شمعة هابطة قوية";

  return "⚖️ تذبذب";
}

// =======================
// 💀 دايفرجنس
// =======================
let history = {};

function divergence(name, price, rsi) {
  if (!history[name]) {
    history[name] = [];
  }

  history[name].push({ price, rsi });

  if (history[name].length < 5) return "";

  let h = history[name];

  let p1 = h[h.length - 1].price;
  let p2 = h[h.length - 3].price;

  let r1 = h[h.length - 1].rsi;
  let r2 = h[h.length - 3].rsi;

  // Bullish
  if (p1 < p2 && r1 > r2) return "💀 دايفرجنس صاعد";

  // Bearish
  if (p1 > p2 && r1 < r2) return "💀 دايفرجنس هابط";

  return "";
}

// =======================
// 🚀 انفجار
// =======================
function explosion(rsi, div) {
  if (rsi < 30 && div.includes("صاعد")) {
    return "🚀 دخول قبل الانفجار";
  }

  if (rsi > 70 && div.includes("هابط")) {
    return "💀 تصريف قوي";
  }

  return "";
}

// =======================
// 🎯 TP
// =======================
function tp(price) {
  return [
    price * 1.02,
    price * 1.04,
    price * 1.06,
    price * 1.08
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
// 📊 تحليل كامل
// =======================
let prevPrice = {};

function analyzeAsset(market, name) {

  let price = priceMove(name);
  let rsi = getRSI(name, price);

  let prev = prevPrice[name];
  prevPrice[name] = price;

  let candle = candleSignal(price, prev);
  let div = divergence(name, price, rsi);
  let boom = explosion(rsi, div);

  let targets = tp(price);

  let msg = `${market}

🟢 ${name}
💰 ${price.toFixed(2)}
RSI: ${rsi.toFixed(1)}

${candle}
${div}
${boom}

`;

  targets.forEach((t, i) => {
    msg += `🎯 TP${i+1}: ${t.toFixed(2)}\n`;
  });

  send(msg);
}

// =======================
// 🔥 تشغيل
// =======================
function runAI() {

  analyzeAsset("🇸🇦 السوق السعودي", ");
  analyzeAsset("🇸🇦 السوق السعودي", "");

  analyzeAsset("🇺🇸 السوق الأمريكي",");
  analyzeAsset("🇺🇸 السوق الأمريكي",");

  analyzeAsset("🪙 العملات الرقمية",");
  analyzeAsset("🪙 العملات الرقمية",");
}

// كل 30 ثانية
setInterval(runAI, 30000);

// =======================
app.get("/", (req, res) => {
  res.send("💀 AI ELITE RUNNING");
});

app.listen(3000);
