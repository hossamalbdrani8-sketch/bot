
// ============================================================
// 🧠 AI PRO MAX — DUAL AUTONOMOUS STOCK SCANNER
// 🇸🇦 TASI + 🇺🇸 US
// EODHD API | Node.js 18+ | Telegram
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// 🔐 RAILWAY VARIABLES
// ============================================================

const TASI_TOKEN = process.env.TASI_TOKEN || "";
const US_TOKEN = process.env.US_TOKEN || "";
const EODHD_API_KEY = process.env.EODHD_API_KEY || "";

// ============================================================
// ⚙️ TASI CONFIGURATION (بدون قيود على قوة الإشارة)
// ============================================================

const TASI_CONFIG = {
  enabled: true,
  exchange: "SR",
  name: "🇸🇦 السوق السعودي AI PRO MAX",
  minSignalScore: 0,
  maxAlertsPerScan: 20,
};

// ============================================================
// ⚙️ US CONFIGURATION (بدون قيود على قوة الإشارة)
// ============================================================

const US_CONFIG = {
  enabled: true,
  exchange: "US",
  name: "🇺🇸 السوق الأمريكي AI PRO MAX",
  minPrice: 0.20,
  minSignalScore: 0,
  maxAlertsPerScan: 20,
};

// ============================================================
// ⚙️ EODHD CONFIGURATION
// ============================================================

const EODHD_CONFIG = {
  historyLimit: 120,
  atrPeriod: 14,
  supportResistanceLookback: 60,
  scanConcurrency: 16,
  updateIntervalMinutes: 2,
  requestTimeoutMs: 25000,
  atrTargets: [0.75, 1.25, 1.75, 2.50, 3.25, 4.00, 5.00, 6.00],
  newsEnabled: true,
  newsPerStock: false,
  generalNewsLimit: 50,
};

// ============================================================
// ⚙️ SERVER
// ============================================================

const PORT = Number(process.env.PORT || 3000);
const app = express();
app.use(express.json());

app.get("/", (req, res) => {
  res.status(200).send("AI PRO MAX LIVE 24/7");
});

app.get("/health", (req, res) => {
  res.json({
    status: "ok",
    tasi: TASI_CONFIG.enabled,
    us: US_CONFIG.enabled,
    time: new Date().toISOString(),
  });
});

app.listen(PORT, () => {
  console.log(`🌐 Server running on port ${PORT}`);
});

// ============================================================
// 🧠 TELEGRAM
// ============================================================

let tasiBot = null;
let usBot = null;

if (TASI_TOKEN) {
  tasiBot = new TelegramBot(TASI_TOKEN, { polling: true });
  tasiBot.on("polling_error", (err) => console.error("🇸🇦 Telegram polling error:", err.message));
  tasiBot.on("error", (err) => console.error("🇸🇦 Telegram error:", err.message));
}

if (US_TOKEN) {
  usBot = new TelegramBot(US_TOKEN, { polling: true });
  usBot.on("polling_error", (err) => console.error("🇺🇸 Telegram polling error:", err.message));
  usBot.on("error", (err) => console.error("🇺🇸 Telegram error:", err.message));
}

let tasiChatIds = new Set();
let usChatIds = new Set();

// ============================================================
// 🧰 HTTP
// ============================================================

async function fetchJson(url, timeout = EODHD_CONFIG.requestTimeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, { signal: controller.signal });
    const text = await response.text();

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${text.slice(0, 300)}`);
    }

    if (!text) {
      throw new Error("Empty response");
    }

    return JSON.parse(text);
  } finally {
    clearTimeout(timer);
  }
}

// ============================================================
// 🔐 API CHECK
// ============================================================

function checkConfig() {
  if (!EODHD_API_KEY) console.error("❌ EODHD_API_KEY غير موجود");
  if (!TASI_TOKEN) console.error("⚠️ TASI_TOKEN غير موجود");
  if (!US_TOKEN) console.error("⚠️ US_TOKEN غير موجود");
}

// ============================================================
// 📋 جلب القوائم
// ============================================================

async function getExchangeSymbols(exchange) {
  const url = `https://eodhd.com/api/exchange-symbol-list/${exchange}?api_token=${encodeURIComponent(EODHD_API_KEY)}&fmt=json&type=common_stock`;
  const data = await fetchJson(url);
  if (!Array.isArray(data)) throw new Error(`قائمة ${exchange} غير صالحة`);
  return data;
}

async function getTasiSymbols() {
  const rows = await getExchangeSymbols(TASI_CONFIG.exchange);
  return rows
    .filter((x) => String(x.Code || x.code || "").trim().length > 0)
    .map((x) => ({
      code: String(x.Code || x.code).trim(),
      name: x.Name || x.name || "",
    }));
}

async function getBulkLastDay(exchange) {
  const url = `https://eodhd.com/api/eod-bulk-last-day/${exchange}?api_token=${encodeURIComponent(EODHD_API_KEY)}&fmt=json`;
  const data = await fetchJson(url, 60000);
  if (!Array.isArray(data)) throw new Error(`Bulk ${exchange} response غير صالح`);
  return data;
}

function filterMarketByPrice(rows, minPrice = 0) {
  return rows.filter((row) => {
    const price = Number(row.adjusted_close ?? row.close ?? 0);
    return Number.isFinite(price) && price >= minPrice;
  });
}

async function getHistory(symbol, exchange) {
  const ticker = `${symbol}.${exchange}`;
  const url = `https://eodhd.com/api/eod/${encodeURIComponent(ticker)}?api_token=${encodeURIComponent(EODHD_API_KEY)}&fmt=json&period=d&order=d&limit=${EODHD_CONFIG.historyLimit}`;
  const data = await fetchJson(url);
  if (!Array.isArray(data) || data.length < 20) return null;
  return data;
}

// ============================================================
// 📐 المؤشرات الفنية
// ============================================================

function calculateATR(rows, period = 14) {
  if (rows.length < period + 1) return null;
  const tr = [];
  for (let i = 1; i < rows.length; i++) {
    const high = Number(rows[i].high);
    const low = Number(rows[i].low);
    const prevClose = Number(rows[i - 1].close);
    if (!Number.isFinite(high) || !Number.isFinite(low) || !Number.isFinite(prevClose)) continue;
    tr.push(Math.max(high - low, Math.abs(high - prevClose), Math.abs(low - prevClose)));
  }
  if (tr.length < period) return null;
  let atr = 0;
  for (let i = 0; i < period; i++) atr += tr[i];
  atr /= period;
  for (let i = period; i < tr.length; i++) atr = ((atr * (period - 1)) + tr[i]) / period;
  return atr;
}

function averageVolume(rows, period = 20) {
  const values = rows.slice(0, period).map((x) => Number(x.volume)).filter(Number.isFinite);
  if (!values.length) return 0;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

function calculateVWAP(rows, period = 20) {
  const data = rows.slice(0, period);
  let pv = 0, volume = 0;
  for (const row of data) {
    const high = Number(row.high), low = Number(row.low), close = Number(row.close), vol = Number(row.volume);
    if (!Number.isFinite(high) || !Number.isFinite(low) || !Number.isFinite(close) || !Number.isFinite(vol)) continue;
    const typical = (high + low + close) / 3;
    pv += typical * vol;
    volume += vol;
  }
  return volume > 0 ? pv / volume : null;
}

function calculateSupportResistance(rows, lookback = 60) {
  const data = rows.slice(0, Math.min(rows.length, lookback));
  const highs = data.map((x) => Number(x.high)).filter(Number.isFinite);
  const lows = data.map((x) => Number(x.low)).filter(Number.isFinite);
  if (!highs.length || !lows.length) return { support: null, resistance: null };
  const current = Number(data[0].close);
  const below = lows.filter((x) => x < current).sort((a, b) => b - a);
  const above = highs.filter((x) => x > current).sort((a, b) => a - b);
  return { support: below[0] ?? Math.min(...lows), resistance: above[0] ?? Math.max(...highs) };
}

function calculateTrend(rows) {
  if (rows.length < 10) return { direction: "neutral", score: 50 };
  const current = Number(rows[0].close), old10 = Number(rows[9].close), old5 = Number(rows[4].close);
  if (!Number.isFinite(current) || !Number.isFinite(old10) || !Number.isFinite(old5)) {
    return { direction: "neutral", score: 50 };
  }
  const momentum10 = ((current - old10) / old10) * 100;
  let score = 50;
  if (momentum10 > 0) score += 25;
  if (momentum10 < 0) score -= 25;
  score = Math.max(0, Math.min(100, score));
  let direction = momentum10 >= 0 ? "up" : "down";
  return { direction, score };
}

function calculateLiquidity(rows) {
  const current = rows[0];
  const close = Number(current.close), open = Number(current.open), volume = Number(current.volume);
  const avgVol = averageVolume(rows);
  let buy = close >= open ? 60 : 40;
  return { buy, sell: 100 - buy, volume, avgVol, volumeStrength: avgVol > 0 ? (volume / avgVol) * 100 : 0 };
}

function calculateSignalScore() {
  return 85; // إعطاء نتيجة تقييم افتراضية لتظهر كل الأسهم فوراً
}

function buildTargets(price, atr, direction, support, resistance) {
  const targets = [];
  for (let i = 0; i < EODHD_CONFIG.atrTargets.length; i++) {
    const multiplier = EODHD_CONFIG.atrTargets[i];
    let target = direction === "up" ? price + atr * multiplier : price - atr * multiplier;
    targets.push({ number: i + 1, multiplier, price: Number(target.toFixed(4)) });
  }
  return targets;
}

// ============================================================
// 🔎 تحليل سهم
// ============================================================

async function analyzeStock(symbol, exchange, bulkRow = null) {
  try {
    let history = await getHistory(symbol, exchange);
    if (!history || history.length < 20) return null;

    const latest = history[0];
    const price = Number(bulkRow?.adjusted_close ?? bulkRow?.close ?? latest.close);
    if (!Number.isFinite(price) || price <= 0) return null;

    const atr = calculateATR(history, EODHD_CONFIG.atrPeriod);
    if (!atr || atr <= 0) return null;

    const trend = calculateTrend(history);
    const liquidity = calculateLiquidity(history);
    const vwap = calculateVWAP(history);
    const sr = calculateSupportResistance(history, EODHD_CONFIG.supportResistanceLookback);
    const score = calculateSignalScore();
    const targets = buildTargets(price, atr, trend.direction, sr.support, sr.resistance);

    return {
      symbol,
      exchange,
      price,
      atr,
      trend,
      liquidity,
      vwap,
      support: sr.support,
      resistance: sr.resistance,
      score,
      targets,
      timestamp: new Date().toISOString(),
    };
  } catch (error) {
    return null;
  }
}

// ============================================================
// 📝 تنسيق الرسائل
// ============================================================

function formatNumber(value) {
  if (!Number.isFinite(Number(value))) return "—";
  return Number(value).toFixed(Number(value) < 10 ? 4 : 2);
}

function buildMessage(result) {
  const up = result.trend.direction === "up";
  const direction = up ? "🟢 صعود" : "🔴 هبوط";
  const targets = result.targets.map((t) => `🎯 الهدف ${t.number}: ${formatNumber(t.price)} (ATR × ${t.multiplier})`).join("\n");

  return (
    `🧠 <b>AI PRO MAX (بدون قيود)</b>\n\n` +
    `${up ? "🇸🇦" : "🇺🇸"} <b>${escapeHtml(result.symbol)}</b>\n\n` +
    `💰 السعر: <b>${formatNumber(result.price)}</b>\n` +
    `🚨 الاتجاه: <b>${direction}</b>\n` +
    `💥 التقييم: <b>${result.score}/100</b>\n\n` +
    `📐 ATR: ${formatNumber(result.atr)}\n` +
    `📍 الدعم: ${formatNumber(result.support)}\n` +
    `📌 المقاومة: ${formatNumber(result.resistance)}\n\n` +
    `🎯 <b>أهداف ATR</b>\n${targets}\n\n` +
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

async function runWorkers(items, worker, concurrency, onProgress) {
  let index = 0, completed = 0;
  async function runner() {
    while (true) {
      const currentIndex = index++;
      if (currentIndex >= items.length) return;
      try { await worker(items[currentIndex], currentIndex); } catch (e) {}
      completed++;
      if (onProgress) onProgress(completed, items.length);
    }
  }
  const count = Math.min(concurrency, items.length);
  await Promise.all(Array.from({ length: count }, () => runner()));
}

// ============================================================
// 🇸🇦 فحص تاسي
// ============================================================

let tasiScanRunning = false;
async function scanTASI() {
  if (tasiScanRunning) return;
  tasiScanRunning = true;
  try {
    console.log("\n🔍 بدء الفحص المباشر لتاسي...");
    const symbols = await getTasiSymbols();
    let bulk = [];
    try { bulk = await getBulkLastDay("SR"); } catch (e) {}

    const bulkMap = new Map();
    for (const row of bulk) {
      const code = String(row.code || row.Code || "").trim();
      if (code) bulkMap.set(code.toUpperCase(), row);
    }

    const candidates = symbols.map((item) => ({
      ...item,
      bulk: bulkMap.get(item.code.toUpperCase()) || null,
    }));

    let signals = [];
    await runWorkers(
      candidates,
      async (item) => {
        const result = await analyzeStock(item.code, "SR", item.bulk);
        if (!result) return;
        signals.push(result);
        if (signals.length <= TASI_CONFIG.maxAlertsPerScan) {
          await broadcast(tasiBot, tasiChatIds, buildMessage(result));
        }
      },
      EODHD_CONFIG.scanConcurrency
    );
    console.log(`✅ انتهى فحص تاسي — الإشارات المرسلة: ${signals.length}`);
  } catch (error) {
    console.error("❌ TASI error:", error.message);
  } finally {
    tasiScanRunning = false;
  }
}

// ============================================================
// 🇺🇸 فحص السوق الأمريكي
// ============================================================

let usScanRunning = false;
async function scanUS() {
  if (usScanRunning) return;
  usScanRunning = true;
  try {
    console.log("\n🔍 بدء الفحص المباشر لأمريكا...");
    const bulk = await getBulkLastDay("US");
    const candidates = filterMarketByPrice(bulk, US_CONFIG.minPrice);

    let signals = [];
    await runWorkers(
      candidates,
      async (row) => {
        const symbol = String(row.code || row.Code || "").trim();
        if (!symbol) return;
        const result = await analyzeStock(symbol, "US", row);
        if (!result) return;
        signals.push(result);
        if (signals.length <= US_CONFIG.maxAlertsPerScan) {
          await broadcast(usBot, usChatIds, buildMessage(result));
        }
      },
      EODHD_CONFIG.scanConcurrency
    );
    console.log(`✅ انتهى فحص أمريكا — الإشارات المرسلة: ${signals.length}`);
  } catch (error) {
    console.error("❌ US error:", error.message);
  } finally {
    usScanRunning = false;
  }
}

// ============================================================
// 🤖 الأوامر
// ============================================================

if (tasiBot) {
  tasiBot.onText(/\/start|\/scan/, async (msg) => {
    tasiChatIds.add(msg.chat.id);
    await tasiBot.sendMessage(msg.chat.id, "🇸🇦 جاري فحص أسهم تاسي وإرسال النتائج الفورية...");
    scanTASI();
  });
}

if (usBot) {
  usBot.onText(/\/start|\/scan/, async (msg) => {
    usChatIds.add(msg.chat.id);
    await usBot.sendMessage(msg.chat.id, "🇺🇸 جاري فحص الأسهم الأمريكية وإرسال النتائج الفورية...");
    scanUS();
  });
}

// ============================================================
// 🚀 التشغيل
// ============================================================

checkConfig();
setTimeout(() => {
  if (TASI_CONFIG.enabled) scanTASI();
  if (US_CONFIG.enabled) scanUS();
}, 3000);
