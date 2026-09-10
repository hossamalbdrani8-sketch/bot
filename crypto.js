
// ============================================================
// 🪙 CRYPTO AI PRO MAX — AUTONOMOUS SCANNER
// 🚀 Binance API | Node.js 18+ | Telegram
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// 🔐 RAILWAY VARIABLES
// ============================================================

const CRYPTO_TOKEN = process.env.CRYPTO_TOKEN || "";

// ============================================================
// ⚙️ CRYPTO CONFIGURATION
// ============================================================

const CRYPTO_CONFIG = {
  enabled: true,
  name: "🪙 بوت العملات الرقمية AI PRO MAX",
  minSignalScore: 0,
  maxAlertsPerScan: 20,
  updateIntervalMinutes: 5,
};

// ============================================================
// ⚙️ SERVER
// ============================================================

const PORT = Number(process.env.PORT || 3000);
const app = express();
app.use(express.json());

app.get("/", (req, res) => {
  res.status(200).send("CRYPTO AI PRO MAX LIVE 24/7");
});

app.get("/health", (req, res) => {
  res.json({
    status: "ok",
    crypto: CRYPTO_CONFIG.enabled,
    time: new Date().toISOString(),
  });
});

app.listen(PORT, () => {
  console.log(`🌐 Server running on port ${PORT}`);
});

// ============================================================
// 🧠 TELEGRAM
// ============================================================

let cryptoBot = null;

if (CRYPTO_TOKEN) {
  cryptoBot = new TelegramBot(CRYPTO_TOKEN, { polling: true });
  cryptoBot.on("polling_error", (err) => console.error("🪙 Telegram polling error:", err.message));
  cryptoBot.on("error", (err) => console.error("🪙 Telegram error:", err.message));
}

let cryptoChatIds = new Set();

// ============================================================
// 🧰 HTTP & BINANCE API
// ============================================================

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return await response.json();
}

// جلب قائمة أهم العملات الرقمية من بانانس مقابل USDT
async function getCryptoSymbols() {
  const data = await fetchJson("https://api.binance.com/api/v3/ticker/24hr");
  if (!Array.isArray(data)) return [];

  return data
    .filter((item) => item.symbol.endsWith("USDT"))
    .map((item) => ({
      symbol: item.symbol,
      price: Number(item.lastPrice),
      volume: Number(item.quoteVolume),
      priceChangePercent: Number(item.priceChangePercent),
    }))
    .sort((a, b) => b.volume - a.volume) // ترتيب حسب الأعلى سيولة وحجماً
    .slice(0, 30); // أخذ أقوى 30 عملة رئيسية
}

// جلب الشموع التاريخية (Klines) لحساب المؤشرات
async function getCryptoHistory(symbol) {
  const url = `https://api.binance.com/api/v3/klines?symbol=${symbol}&interval=1d&limit=50`;
  const data = await fetchJson(url);
  if (!Array.isArray(data) || data.length < 20) return null;

  return data.map((row) => ({
    open: Number(row[1]),
    high: Number(row[2]),
    low: Number(row[3]),
    close: Number(row[4]),
    volume: Number(row[5]),
  }));
}

// ============================================================
// 📐 المؤشرات الفنية (ATR & Trend)
// ============================================================

function calculateATR(rows, period = 14) {
  if (rows.length < period + 1) return null;
  const tr = [];
  for (let i = 1; i < rows.length; i++) {
    const high = rows[i].high;
    const low = rows[i].low;
    const prevClose = rows[i - 1].close;
    tr.push(Math.max(high - low, Math.abs(high - prevClose), Math.abs(low - prevClose)));
  }
  let atr = tr.slice(0, period).reduce((a, b) => a + b, 0) / period;
  return atr;
}

function analyzeCryptoData(item, history) {
  const price = item.price;
  const change = item.priceChangePercent;
  const direction = change >= 0 ? "up" : "down";
  const atr = calculateATR(history) || price * 0.03;

  const targets = [
    { number: 1, price: direction === "up" ? price + atr * 1 : price - atr * 1 },
    { number: 2, price: direction === "up" ? price + atr * 2 : price - atr * 2 },
    { number: 3, price: direction === "up" ? price + atr * 3 : price - atr * 3 },
  ];

  return {
    symbol: item.symbol,
    price,
    change,
    direction,
    atr,
    targets,
    score: Math.min(100, Math.max(30, Math.round(50 + Math.abs(change) * 5))),
  };
}

// ============================================================
// 📝 تنسيق الرسائل
// ============================================================

function formatNumber(value) {
  if (!Number.isFinite(Number(value))) return "—";
  return Number(value).toFixed(Number(value) < 1 ? 4 : 2);
}

function buildMessage(result) {
  const up = result.direction === "up";
  const targetsText = result.targets
    .map((t) => `🎯 الهدف ${t.number}: <b>${formatNumber(t.price)}</b>`)
    .join("\n");

  return (
    `🪙 <b>CRYPTO AI PRO MAX</b>\n\n` +
    `🚀 العملة: <b>${escapeHtml(result.symbol)}</b>\n` +
    `💰 السعر: <b>${formatNumber(result.price)}</b>\n` +
    `📊 التغير (24 ساعة): <b>${result.change >= 0 ? "+" : ""}${result.change.toFixed(2)}%</b>\n` +
    `🚨 الاتجاه: <b>${up ? "🟢 صعود قوي" : "🔴 هبوط قوي"}</b>\n` +
    `💥 التقييم: <b>${result.score}/100</b>\n\n` +
    `📐 ATR: ${formatNumber(result.atr)}\n\n` +
    `🎯 <b>الأهداف الفنية</b>\n${targetsText}\n\n` +
    `🕒 ${new Date().toLocaleString("ar-SA", { timeZone: "Asia/Riyadh" })}`
  );
}

function escapeHtml(text) {
  return String(text ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

async function sendMessage(bot, chatId, message) {
  try {
    await bot.sendMessage(chatId, message, { parse_mode: "HTML", disable_web_page_preview: true });
  } catch (error) {
    console.error("❌ Telegram send:", error.message);
  }
}

async function broadcast(bot, chatIds, message) {
  if (!bot) return;
  for (const chatId of chatIds) {
    await sendMessage(bot, chatId, message);
  }
}

// ============================================================
// 🔍 الفحص التلقائي للعملات
// ============================================================

let cryptoScanRunning = false;

async function scanCrypto() {
  if (cryptoScanRunning) return;
  cryptoScanRunning = true;

  try {
    console.log("\n🔍 بدء فحص سوق العملات الرقمية...");
    const symbols = await getCryptoSymbols();
    let signals = [];

    for (const item of symbols) {
      try {
        const history = await getCryptoHistory(item.symbol);
        if (!history) continue;

        const result = analyzeCryptoData(item, history);
        signals.push(result);

        if (signals.length <= CRYPTO_CONFIG.maxAlertsPerScan) {
          await broadcast(cryptoBot, cryptoChatIds, buildMessage(result));
        }
      } catch (err) {
        // تجاهل الأخطاء الفردية للعملات المستمرة
      }
    }

    console.log(`✅ انتهى فحص العملات الرقمية — الإشارات المرسلة: ${signals.length}`);
  } catch (error) {
    console.error("❌ Crypto scan error:", error.message);
  } finally {
    cryptoScanRunning = false;
  }
}

// ============================================================
// 🤖 الأوامر
// ============================================================

if (cryptoBot) {
  cryptoBot.onText(/\/start|\/scan/, async (msg) => {
    cryptoChatIds.add(msg.chat.id);
    await cryptoBot.sendMessage(msg.chat.id, "🪙 تم تفعيل بوت العملات الرقمية\n\n🔍 جاري جلب وتحليل أقوى العملات...");
    scanCrypto();
  });
}

// ============================================================
// 🚀 التشغيل والدورة التلقائية
// ============================================================

setTimeout(() => {
  if (CRYPTO_CONFIG.enabled) {
    scanCrypto();
  }
}, 3000);

setInterval(() => {
  if (CRYPTO_CONFIG.enabled) {
    scanCrypto();
  }
}, CRYPTO_CONFIG.updateIntervalMinutes * 60 * 1000);
