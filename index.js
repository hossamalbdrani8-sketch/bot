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
    bot.sendMessage(msgChatId, "🔥 AI PRO MAX شغال 24/7");
  }
});

// =======================
// 📊 جلب الأسعار (بدون node-fetch)
// =======================

async function getCryptoPrice(symbol) {
  try {
    const res = await fetch(`https://api.binance.com/api/v3/ticker/price?symbol=${symbol}`);
    const data = await res.json();
    return parseFloat(data.price);
  } catch (e) {
    console.log("Crypto API Error:", e.message);
    return null;
  }
}

async function getStockPrice(symbol) {
  try {
    const res = await fetch(`https://query1.finance.yahoo.com/v7/finance/quote?symbols=${symbol}`);
    const data = await res.json();

    const result = data?.quoteResponse?.result?.[0];
    return result?.regularMarketPrice || null;

  } catch (e) {
    console.log("Stock API Error:", e.message);
    return null;
  }
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
// 🧠 AI تحليل
// =======================
function analyzeMarket(asset) {
  const rsi = asset.rsi;
  const vol = asset.volume;

  if (rsi <= 30 && vol > 1000000) return "💀 دخول مؤسساتي قوي";
  if (rsi <= 40) return "🚀 بداية انفجار";
  if (rsi <= 50) return "📈 تأكيد اتجاه";
  if (rsi <= 60) return "🔥 استمرارية";
  if (rsi >= 70) return "🔴 خروج تدريجي";

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
    sendSignal(`⚠️ وقف متحرك تفعل\n${asset.name} عند ${asset.price}`);
  }
}

// =======================
// 📩 إرسال
// =======================
function sendSignal(msg) {
  if (!msgChatId) return;
  bot.sendMessage(msgChatId, msg);
}

// =======================
// 📊 إرسال إشارة
// =======================
function sendFullSignal(title, asset) {
  if (!msgChatId) return;
  if (!asset.price) return; // حماية

  const analysis = analyzeMarket(asset);

  // فلترة قوية 💀
  if (!analysis.includes("💀") && !analysis.includes("🚀")) return;

  const tps = generateTP(asset.price);

  let msg = `${title}

🟢 ${asset.name}
💰 السعر: ${asset.price.toFixed(2)}
RSI: ${asset.rsi}
${analysis}

`;

  tps.forEach((tp, i) => {
    msg += `🎯 TP${i + 1}: ${tp.toFixed(2)}\n`;
  });

  msg += "\n⚠️ وقف متحرك مفعل";

  bot.sendMessage(msgChatId, msg);

  trailingStop(asset);
}

// =======================
// 📊 الأسواق
// =======================

async function saudiMarket() {
  return [
    {
      name: "أرامكو",
      price: await getStockPrice("2222.SR"),
      rsi: 28,
      volume: 2000000
    },
    {
      name: "سابك",
      price: await getStockPrice("2010.SR"),
      rsi: 35,
      volume: 1500000
    }
  ];
}

async function usMarket() {
  return [
    {
      name: "Tesla",
      price: await getStockPrice("TSLA"),
      rsi: 27,
      volume: 5000000
    },
    {
      name: "Apple",
      price: await getStockPrice("AAPL"),
      rsi: 45,
      volume: 3000000
    }
  ];
}

async function cryptoMarket() {
  return [
    {
      name: "BTC",
      price: await getCryptoPrice("BTCUSDT"),
      rsi: 29,
      volume: 9000000
    },
    {
      name: "ETH",
      price: await getCryptoPrice("ETHUSDT"),
      rsi: 31,
      volume: 7000000
    }
  ];
}

// =======================
// 🔥 تشغيل AI
// =======================
async function runAI() {
  try {
    const saudi = await saudiMarket();
    const us = await usMarket();
    const crypto = await cryptoMarket();

    for (const s of saudi) sendFullSignal("🇸🇦 السوق السعودي", s);
    for (const s of us) sendFullSignal("🇺🇸 السوق الأمريكي", s);
    for (const c of crypto) sendFullSignal("🪙 العملات الرقمية", c);

  } catch (e) {
    console.log("AI ERROR:", e.message);
  }
}

// ⏱️ كل 5 دقائق (أفضل)
setInterval(runAI, 300000);

// =======================
// 🌐 السيرفر
// =======================
app.get("/", (req, res) => {
  res.send("🚀 AI PRO MAX LIVE");
});

const port = process.env.PORT || 3000;
app.listen(port, () => {
  console.log("Server running on port " + port);
});
