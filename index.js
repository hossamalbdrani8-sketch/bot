import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();

const TOKEN = "حط_التوكن_حقك_هنا";
const bot = new TelegramBot(TOKEN, { polling: true });

let chatId = null;

// =======================
// 🎯 استقبال
// =======================
bot.on("message", (msg) => {
  chatId = msg.chat.id;

  if (msg.text && msg.text.includes("/start")) {
    bot.sendMessage(chatId, "💀 AI PRO MAX ACTIVE");
  }

  if (msg.text && msg.text.includes("/scan")) {
    runAI();
  }
});

// =======================
// 📊 السوق السعودي
// =======================
async function getSaudi() {
  try {
    const res = await fetch("https://www.tadawulgroup.sa/wps/portal/tadawul/market-participants/issuers-list?locale=en");
    const data = await res.json();
    return data?.issuers?.map(x => x.symbol) || [];
  } catch (e) {
    console.log("Saudi API Error");
    return [];
  }
}

// =======================
// 📊 السوق الأمريكي
// =======================
async function getUS() {
  try {
    const res = await fetch("https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=4000");
    const data = await res.json();
    return data?.data?.rows?.map(x => x.symbol) || [];
  } catch (e) {
    console.log("US API Error");
    return [];
  }
}

// =======================
// 🪙 العملات
// =======================
async function getCrypto() {
  try {
    const res = await fetch("https://api.binance.com/api/v3/ticker/price");
    const data = await res.json();
    return data.map(x => x.symbol);
  } catch (e) {
    console.log("Crypto API Error");
    return [];
  }
}

// =======================
// 💰 السعر
// =======================
async function getPrice(symbol) {
  try {
    const res = await fetch(`https://query1.finance.yahoo.com/v7/finance/quote?symbols=${symbol}`);
    const data = await res.json();
    return data?.quoteResponse?.result?.[0]?.regularMarketPrice || null;
  } catch {
    return null;
  }
}

// =======================
// 📊 تحليل بسيط
// =======================
function analyze(price) {
  if (!price) return null;

  if (price % 5 < 1) return "💀 فرصة قوية";
  if (price % 3 < 1) return "🚀 بداية حركة";

  return null; // فلترة
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
async function analyzeAsset(market, symbol, suffix = "") {
  const price = await getPrice(symbol + suffix);

  if (!price) return;

  const signal = analyze(price);

  if (!signal) return;

  send(`${market}
🟢 ${symbol}
💰 ${price.toFixed(2)}
${signal}
`);
}

// =======================
// 🔥 تشغيل
// =======================
async function runAI() {
  try {

    const saudi = await getSaudi();
    const us = await getUS();
    const crypto = await getCrypto();

    // ⚠️ تحديد عدد عشان ما ينهار
    const saudiList = saudi.slice(0, 100);
    const usList = us.slice(0, 100);
    const cryptoList = crypto.slice(0, 100);

    for (const s of saudiList) {
      await analyzeAsset("🇸🇦 السوق السعودي", s, ".SR");
    }

    for (const s of usList) {
      await analyzeAsset("🇺🇸 السوق الأمريكي", s);
    }

    for (const c of cryptoList) {
      send(`🪙 ${c}`);
    }

  } catch (e) {
    console.log("RUN ERROR:", e.message);
  }
}

// كل دقيقة
setInterval(runAI, 60000);

// =======================
// 🌐 السيرفر
// =======================
app.get("/", (req, res) => {
  res.send("💀 AI PRO MAX RUNNING");
});

const port = process.env.PORT || 3000;
app.listen(port, () => {
  console.log("Server running on port " + port);
});
