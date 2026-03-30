import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();

// 🔑 التوكن
const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";
const bot = new TelegramBot(TOKEN, { polling: true });

// =======================
// 🎯 chatId
// =======================
let msgChatId = null;

bot.on("message", (msg) => {
  msgChatId = msg.chat.id;

  if (msg.text === "/start") {
    bot.sendMessage(msgChatId, "🔥 AI PRO MAX LIVE 24/7");
    runAI(); // تشغيل مباشر
  }

  if (msg.text === "/scan") {
    runAI();
  }
});

// =======================
// 📊 جلب بيانات (Binance)
// =======================
async function getKlines(symbol) {
  try {
    const res = await fetch(
      `https://api.binance.com/api/v3/klines?symbol=${symbol}&interval=1m&limit=100`
    );
    const data = await res.json();

    return data.map(c => parseFloat(c[4])); // سعر الإغلاق
  } catch {
    return [];
  }
}

// =======================
// 🧠 حساب RSI حقيقي
// =======================
function calculateRSI(prices, period = 14) {
  if (prices.length < period) return 50;

  let gains = 0;
  let losses = 0;

  for (let i = 1; i <= period; i++) {
    const diff = prices[i] - prices[i - 1];
    if (diff >= 0) gains += diff;
    else losses -= diff;
  }

  let avgGain = gains / period;
  let avgLoss = losses / period;

  for (let i = period + 1; i < prices.length; i++) {
    const diff = prices[i] - prices[i - 1];

    if (diff >= 0) {
      avgGain = (avgGain * (period - 1) + diff) / period;
      avgLoss = (avgLoss * (period - 1)) / period;
    } else {
      avgGain = (avgGain * (period - 1)) / period;
      avgLoss = (avgLoss * (period - 1) - diff) / period;
    }
  }

  const rs = avgGain / avgLoss;
  return 100 - 100 / (1 + rs);
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
// 💀 تحليل ذكي (صانع سوق)
// =======================
function analyze(asset) {
  const rsi = asset.rsi;

  if (rsi < 25) return "💀 تجميع قوي (انفجار قريب)";
  if (rsi < 35) return "🟢 دخول مبكر";
  if (rsi < 45) return "🚀 بداية صعود";
  if (rsi < 60) return "🔥 استمرارية";
  if (rsi > 70) return "🔴 تصريف";

  return "⏳ انتظار";
}

// =======================
// ⚠️ وقف متحرك
// =======================
let lastPrices = {};

function trailingStop(asset) {
  const name = asset.name;

  if (!lastPrices[name]) {
    lastPrices[name] = asset.price;
  }

  if (asset.price > lastPrices[name]) {
    lastPrices[name] = asset.price;
  }

  if (asset.price < lastPrices[name] * 0.97) {
    send(`⚠️ وقف متحرك\n${asset.name} عند ${asset.price.toFixed(2)}`);
  }
}

// =======================
// 📩 إرسال
// =======================
function send(msg) {
  if (!msgChatId) return;
  bot.sendMessage(msgChatId, msg);
}

// =======================
// 📊 إرسال إشارة
// =======================
function sendSignal(title, asset) {
  const analysis = analyze(asset);
  const tps = generateTP(asset.price);

  let msg = `${title}

🟢 ${asset.name}
💰 السعر: ${asset.price.toFixed(2)}
RSI: ${asset.rsi.toFixed(2)}
${analysis}

`;

  tps.forEach((tp, i) => {
    msg += `🎯 TP${i + 1}: ${tp.toFixed(2)}\n`;
  });

  msg += "\n⚠️ وقف متحرك مفعل";

  send(msg);
  trailingStop(asset);
}

// =======================
// 🪙 العملات (حقيقي)
// =======================
async function cryptoMarket() {
  const coins = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];

  let result = [];

  for (const symbol of coins) {
    const prices = await getKlines(symbol);
    if (prices.length === 0) continue;

    const price = prices[prices.length - 1];
    const rsi = calculateRSI(prices);

    result.push({
      name: symbol.replace("USDT", ""),
      price,
      rsi
    });
  }

  return result;
}

// =======================
// 🔥 تشغيل AI
// =======================
async function runAI() {
  try {
    const crypto = await cryptoMarket();

    for (const c of crypto) {
      sendSignal("🪙 العملات الرقمية", c);
    }

  } catch (e) {
    console.log("AI ERROR:", e.message);
  }
}

// كل دقيقة
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
