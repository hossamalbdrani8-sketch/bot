
// ============================================================
// 🚀 ALL-IN-ONE TRADING BOTS (US, TASI, & CRYPTO)
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// 🔐 المتغيرات من Railway
const US_TOKEN = process.env.US_TOKEN || "";
const TASI_TOKEN = process.env.TASI_TOKEN || "";
const CRYPTO_TOKEN = process.env.CRYPTO_TOKEN || "";

// 🌐 خادم الويب الأساسي لضمان استمرار عمل المنصة على Railway
const PORT = Number(process.env.PORT || 3000);
const app = express();
app.use(express.json());

app.get("/", (req, res) => {
  res.status(200).send("ALL TRADING BOTS ARE LIVE 24/7 🚀");
});

app.get("/health", (req, res) => {
  res.json({
    status: "ok",
    usStock: Boolean(US_TOKEN),
    tasiStock: Boolean(TASI_TOKEN),
    crypto: Boolean(CRYPTO_TOKEN),
    time: new Date().toISOString(),
  });
});

app.listen(PORT, () => {
  console.log(`🌐 Server running on port ${PORT}`);
});

// ============================================================
// 🇺🇸 بوت الأسهم الأمريكية (US Stocks)
// ============================================================
if (US_TOKEN) {
  const usBot = new TelegramBot(US_TOKEN, { polling: true });
  usBot.onText(/\/start|\/scan/, async (msg) => {
    await usBot.sendMessage(msg.chat.id, "🇺🇸 تم تفعيل بوت الأسهم الأمريكية بنجاح!\n\n🔍 جاري استقبال الأوامر وفحص السوق...");
  });
  usBot.on("polling_error", (err) => console.error("🇺🇸 US Bot Error:", err.message));
  console.log("🇺🇸 US Stock Bot initialized.");
}

// ============================================================
// 🇸🇦 بوت الأسهم السعودية (TASI)
// ============================================================
if (TASI_TOKEN) {
  const tasiBot = new TelegramBot(TASI_TOKEN, { polling: true });
  tasiBot.onText(/\/start|\/scan/, async (msg) => {
    await tasiBot.sendMessage(msg.chat.id, "🇸🇦 تم تفعيل بوت السوق السعودي (تاسي) بنجاح!\n\n🔍 جاري استقبال الأوامر وفحص الأسهم...");
  });
  tasiBot.on("polling_error", (err) => console.error("🇸🇦 TASI Bot Error:", err.message));
  console.log("🇸🇦 TASI Stock Bot initialized.");
}

// ============================================================
// 🪙 بوت العملات الرقمية (Crypto - Binance API)
// ============================================================
if (CRYPTO_TOKEN) {
  const cryptoBot = new TelegramBot(CRYPTO_TOKEN, { polling: true });
  
  async function fetchJson(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  }

  async function scanCryptoForUser(chatId) {
    try {
      await cryptoBot.sendMessage(chatId, "🪙 جاري فحص سوق العملات الرقمية عبر Binance...");
      const data = await fetchJson("https://api.binance.com/api/v3/ticker/24hr");
      const topCoins = data
        .filter((item) => item.symbol.endsWith("USDT"))
        .sort((a, b) => Number(b.quoteVolume) - Number(a.quoteVolume))
        .slice(0, 5);

      let report = "🪙 <b>أبرز العملات الرقمية الحالية:</b>\n\n";
      for (const coin of topCoins) {
        const price = Number(coin.lastPrice).toFixed(4);
        const change = Number(coin.priceChangePercent).toFixed(2);
        const emoji = change >= 0 ? "🟢" : "🔴";
        report += `${emoji} <b>${coin.symbol}</b>\n💰 السعر: ${price} | التغير: ${change}%\n\n`;
      }
      await cryptoBot.sendMessage(chatId, report, { parse_mode: "HTML" });
    } catch (err) {
      await cryptoBot.sendMessage(chatId, "❌ حدث خطأ أثناء جلب بيانات الكريبتو.");
    }
  }

  cryptoBot.onText(/\/start|\/scan/, async (msg) => {
    await cryptoBot.sendMessage(msg.chat.id, "🪙 تم تفعيل بوت العملات الرقمية بنجاح!");
    await scanCryptoForUser(msg.chat.id);
  });

  cryptoBot.on("polling_error", (err) => console.error("🪙 Crypto Bot Error:", err.message));
  console.log("🪙 Crypto Bot initialized.");
}
