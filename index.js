import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();

const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";

const bot = new TelegramBot(TOKEN, { polling: true });

bot.on("message", (msg) => {
  const chatId = msg.chat.id;
  const text = msg.text;

  if (text === "/start") {
    bot.sendMessage(chatId, "🔥 البوت شغال وجاهز");
  } else {
    bot.sendMessage(chatId, "🤖 قلت: " + text);
  }
});

app.get("/", (req, res) => {
  res.send("🚀 Bot is running!");
});

const port = process.env.PORT || 3000;
app.listen(port, () => {
  console.log("Server running on port " + port);
});
// =======================
// 🔥 AI PRO MAX SCANNER
// =======================

// تشغيل كل دقيقة
setInterval(runScanner, 60000);

// بيانات تجريبية (نستبدلها لاحقاً بسوق حقيقي)
async function runScanner() {
  const fakeData = [
    { name: "BTC", rsi: 32, volume: 2000000, price: 67000 },
    { name: "ETH", rsi: 28, volume: 3000000, price: 3500 },
    { name: "SOL", rsi: 55, volume: 800000, price: 150 }
  ];

  for (const coin of fakeData) {

    // 💀 دخول قوي (RSI + سيولة)
    if (coin.rsi < 30 && coin.volume > 1000000) {
      sendSignal(`💀 دخول مؤسساتي ${coin.name}\nRSI: ${coin.rsi}`);
    }

    // 🔴 خروج
    else if (coin.rsi > 70) {
      sendSignal(`🔴 خروج من ${coin.name}`);
    }

    // ⏳ انتظار
    else {
      console.log("انتظار:", coin.name);
    }

    // ⚠️ وقف متحرك
    trailingStop(coin.price);
  }
}

// =======================
// 📩 إرسال إشارات
// =======================

function sendSignal(msg) {
  const chatId = msgChatId; // نعرفه تحت
  bot.sendMessage(chatId, msg);
}

// =======================
// ⚠️ وقف متحرك
// =======================

let lastPrice = 0;

function trailingStop(price) {
  if (price > lastPrice) {
    lastPrice = price;
  }

  if (price < lastPrice * 0.97) {
    sendSignal("⚠️ وقف متحرك تفعل - خروج");
  }
}

// =======================
// 🎯 التقاط chatId تلقائي
// =======================

let msgChatId = null;

bot.on("message", (msg) => {
  msgChatId = msg.chat.id;
});
import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();

// 🔑 التوكن
const TOKEN = "حط_التوكن_هنا";

const bot = new TelegramBot(TOKEN, { polling: true });

// =======================
// 🎯 التقاط chatId تلقائي
// =======================
let msgChatId = null;

bot.on("message", (msg) => {
  msgChatId = msg.chat.id;
});

// =======================
// 🎯 TP GENERATOR
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
// 🧠 AI RSI ANALYSIS
// =======================
function analyzeMarket(asset) {
  const rsi = asset.rsi;

  if (rsi <= 20) return "💀 تشبع بيع قوي جداً";
  if (rsi <= 30) return "🟢 دخول ذكي مبكر";
  if (rsi <= 40) return "🚀 بداية صعود";
  if (rsi <= 50) return "📈 تأكيد اتجاه صاعد";
  if (rsi <= 60) return "🔥 استمرارية صعود";
  if (rsi <= 70) return "⚠️ قرب التشبع";
  if (rsi <= 80) return "🔴 تشبع شراء";
  return "💥 قمة خطيرة";
}

// =======================
// 🇸🇦 السوق السعودي
// =======================
function saudiMarket() {
  return [
    { name: "أرامكو", price: 30, rsi: 28, volume: 2000000 },
    { name: "سابك", price: 90, rsi: 35, volume: 1500000 }
  ];
}

// =======================
// 🇺🇸 السوق الأمريكي
// =======================
function usMarket() {
  return [
    { name: "Tesla", price: 250, rsi: 27, volume: 5000000 },
    { name: "Apple", price: 180, rsi: 45, volume: 3000000 }
  ];
}

// =======================
// 🪙 العملات
// =======================
function cryptoMarket() {
  return [
    { name: "BTC", price: 67000, rsi: 29, volume: 9000000 },
    { name: "ETH", price: 3500, rsi: 31, volume: 7000000 }
  ];
}

// =======================
// ⚠️ وقف متحرك
// =======================
let lastPrice = 0;

function trailingStop(price) {
  if (price > lastPrice) {
    lastPrice = price;
  }

  if (price < lastPrice * 0.97) {
    sendSignal("⚠️ وقف متحرك تفعل - خروج");
  }
}

// =======================
// 📩 إرسال إشارة كاملة
// =======================
function sendFullSignal(title, asset) {

  if (!msgChatId) return; // لازم ترسل رسالة أول

  const analysis = analyzeMarket(asset);
  const tps = generateTP(asset.price);

  let msg = `${title}

🟢 ${asset.name}
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
// 🔥 تشغيل AI PRO MAX
// =======================
async function runAI() {

  // 🇸🇦
  for (const stock of saudiMarket()) {
    sendFullSignal("🇸🇦 السوق السعودي", stock);
  }

  // 🇺🇸
  for (const stock of usMarket()) {
    sendFullSignal("🇺🇸 السوق الأمريكي", stock);
  }

  // 🪙
  for (const coin of cryptoMarket()) {
    sendFullSignal("🪙 العملات الرقمية", coin);
  }
}

// ⏱️ تشغيل تلقائي كل دقيقة
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
