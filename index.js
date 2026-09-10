
// ============================================================
// 🚀 ALL-IN-ONE TRADING BOTS (US, TASI, & CRYPTO)
// 🇸🇦 TASI + 🇺🇸 US + 🪙 CRYPTO (Binance)
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// 🔐 RAILWAY VARIABLES
// ============================================================

const TASI_TOKEN = process.env.TASI_TOKEN || "";
const US_TOKEN = process.env.US_TOKEN || "";
const CRYPTO_TOKEN = process.env.CRYPTO_TOKEN || "";
const EODHD_API_KEY = process.env.EODHD_API_KEY || "";

// ============================================================
// ⚙️ CONFIGURATIONS
// ============================================================

const TASI_CONFIG = {
  enabled: true,
  exchange: "SR",
  name: "🇸🇦 السوق السعودي AI PRO MAX",
  maxAlertsPerScan: 20,
};

const US_CONFIG = {
  enabled: true,
  exchange: "US",
  name: "🇺🇸 السوق الأمريكي AI PRO MAX",
  minPrice: 0.20,
  maxAlertsPerScan: 20,
};

const CRYPTO_CONFIG = {
  enabled: true,
  name: "🪙 بوت العملات الرقمية AI PRO MAX",
  maxAlertsPerScan: 20,
};

const EODHD_CONFIG = {
  historyLimit: 120,
  atrPeriod: 14,
  supportResistanceLookback: 60,
  scanConcurrency: 16,
  requestTimeoutMs: 25000,
  atrTargets: [0.75, 1.25, 1.75, 2.50, 3.25, 4.00, 5.00, 6.00],
};

// ============================================================
// ⚙️ SERVER (يتوافق مع بورت Railway والشبكة العامة)
// ============================================================

const PORT = Number(process.env.PORT || 8080);
const app = express();
app.use(express.json());

app.get("/", (req, res) => {
  res.status(200).send("AI PRO MAX LIVE 24/7 (US, TASI & CRYPTO)");
});

app.get("/health", (req, res) => {
  res.json({
    status: "ok",
    tasi: TASI_CONFIG.enabled,
    us: US_CONFIG.enabled,
    crypto: CRYPTO_CONFIG.enabled,
    time: new Date().toISOString(),
  });
});

app.listen(PORT, () => {
  console.log(`🌐 Server running on port ${PORT}`);
});

// ============================================================
// 🧠 TELEGRAM BOTS INIT
// ============================================================

let tasiBot = TASI_TOKEN ? new TelegramBot(TASI_TOKEN, { polling: true }) : null;
let usBot = US_TOKEN ? new TelegramBot(US_TOKEN, { polling: true }) : null;
let cryptoBot = CRYPTO_TOKEN ? new TelegramBot(CRYPTO_TOKEN, { polling: true }) : null;

if (tasiBot) {
  tasiBot.on("polling_error", (err) => console.error("🇸🇦 TASI Polling error:", err.message));
}
if (usBot) {
  usBot.on("polling_error", (err) => console.error("🇺🇸 US Polling error:", err.message));
}
if (cryptoBot) {
  cryptoBot.on("polling_error", (err) => console.error("🪙 Crypto Polling error:", err.message));
}

let tasiChatIds = new Set();
let usChatIds = new Set();
let cryptoChatIds = new Set();

// ============================================================
// 🧰 HTTP HELPERS
// ============================================================

async function fetchJson(url, timeout = EODHD_CONFIG.requestTimeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(url, { signal: controller.signal });
    const text = await response.text();
    if (!response.ok) throw new Error(`HTTP ${response.status}: ${text.slice(0, 300)}`);
    if (!text) throw new Error("Empty response");
    return JSON.parse(text);
  } finally {
    clearTimeout(timer);
  }
}

// ============================================================
// 📊 STOCKS LOGIC (TASI & US)
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
  return atr;
}

function calculateTrend(rows) {
  if (rows.length < 10) return { direction: "neutral", score: 50 };
  const current = Number(rows[0].close), old10 = Number(rows[9].close);
  const momentum10 = ((current - old10) / old10) * 100;
  let direction = momentum10 >= 0 ? "up" : "down";
  return { direction, score: 85 };
}

function buildTargets(price, atr, direction) {
  const targets = [];
  for (let i = 0; i < EODHD_CONFIG.atrTargets.length; i++) {
    const multiplier = EODHD_CONFIG.atrTargets[i];
    let target = direction === "up" ? price + atr * multiplier : price - atr * multiplier;
    targets.push({ number: i + 1, multiplier, price: Number(target.toFixed(4)) });
  }
  return targets;
}

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
    const targets = buildTargets(price, atr, trend.direction);

    return { symbol, exchange, price, atr, trend, score: 85, targets };
  } catch (error) {
    return null;
  }
}

// ============================================================
// 🪙 CRYPTO LOGIC (Binance API مباشرة)
// ============================================================

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
    .sort((a, b) => b.volume - a.volume)
    .slice(0, 30);
}

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

function analyzeCryptoData(item, history) {
  const price = item.price;
  const change = item.priceChangePercent;
  const direction = change >= 0 ? "up" : "down";
  const tr = [];
  for (let i = 1; i < history.length; i++) {
    tr.push(Math.max(history[i].high - history[i].low, Math.abs(history[i].high - history[i - 1].close)));
  }
  const atr = tr.reduce((a, b) => a + b, 0) / tr.length || price * 0.03;
  const targets = [
    { number: 1, price: direction === "up" ? price + atr * 1 : price - atr * 1 },
    { number: 2, price: direction === "up" ? price + atr * 2 : price - atr * 2 },
    { number: 3, price: direction === "up" ? price + atr * 3 : price - atr * 3 },
  ];
  return { symbol: item.symbol, price, change, direction, atr, targets, score: 90 };
}

// ============================================================
// 📝 تنسيق الرسائل والإرسال
// ============================================================

function formatNumber(value) {
  if (!Number.isFinite(Number(value))) return "—";
  return Number(value).toFixed(Number(value) < 10 ? 4 : 2);
}

function buildStockMessage(result) {
  const up = result.trend.direction === "up";
  const targets = result.targets.map((t) => `🎯 الهدف ${t.number}: ${formatNumber(t.price)}`).join("\n");
  return (
    `🧠 <b>AI PRO MAX STOCK</b>\n\n` +
    `${up ? "🇸🇦" : "🇺🇸"} <b>${result.symbol}</b>\n` +
    `💰 السعر: <b>${formatNumber(result.price)}</b>\n` +
    `🚨 الاتجاه: <b>${up ? "🟢 صعود" : "🔴 هبوط"}</b>\n\n` +
    `🎯 <b>الأهداف</b>\n${targets}`
  );
}

function buildCryptoMessage(result) {
  const up = result.direction === "up";
  const targets = result.targets.map((t) => `🎯 الهدف ${t.number}: ${formatNumber(t.price)}`).join("\n");
  return (
    `🪙 <b>CRYPTO AI PRO MAX</b>\n\n` +
    `🚀 العملة: <b>${result.symbol}</b>\n` +
    `💰 السعر: <b>${formatNumber(result.price)}</b>\n` +
    `📊 التغير: <b>${result.change >= 0 ? "+" : ""}${result.change.toFixed(2)}%</b>\n` +
    `🚨 الاتجاه: <b>${up ? "🟢 صعود" : "🔴 هبوط"}</b>\n\n` +
    `🎯 <b>الأهداف</b>\n${targets}`
  );
}

async function broadcast(bot, chatIds, message) {
  if (!bot) return;
  for (const chatId of chatIds) {
    try {
      await bot.sendMessage(chatId, message, { parse_mode: "HTML", disable_web_page_preview: true });
    } catch (e) {}
  }
}

async function runWorkers(items, worker, concurrency) {
  let index = 0;
  async function runner() {
    while (true) {
      const currentIndex = index++;
      if (currentIndex >= items.length) return;
      try { await worker(items[currentIndex]); } catch (e) {}
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, () => runner()));
}

// ============================================================
// 🔍 عمليات الفحص
// ============================================================

async function scanTASI() {
  try {
    const symbols = await getTasiSymbols();
    let bulk = [];
    try { bulk = await getBulkLastDay("SR"); } catch (e) {}
    const bulkMap = new Map();
    bulk.forEach((row) => bulkMap.set(String(row.code || row.Code || "").trim().toUpperCase(), row));

    let signals = [];
    await runWorkers(symbols.map((item) => ({ ...item, bulk: bulkMap.get(item.code.toUpperCase()) || null })), async (item) => {
      const res = await analyzeStock(item.code, "SR", item.bulk);
      if (res && signals.length < TASI_CONFIG.maxAlertsPerScan) {
        signals.push(res);
        await broadcast(tasiBot, tasiChatIds, buildStockMessage(res));
      }
    }, EODHD_CONFIG.scanConcurrency);
  } catch (e) {}
}

async function scanUS() {
  try {
    const bulk = await getBulkLastDay("US");
    const candidates = filterMarketByPrice(bulk, US_CONFIG.minPrice);
    let signals = [];
    await runWorkers(candidates, async (row) => {
      const symbol = String(row.code || row.Code || "").trim();
      if (!symbol) return;
      const res = await analyzeStock(symbol, "US", row);
      if (res && signals.length < US_CONFIG.maxAlertsPerScan) {
        signals.push(res);
        await broadcast(usBot, usChatIds, buildStockMessage(res));
      }
    }, EODHD_CONFIG.scanConcurrency);
  } catch (e) {}
}

async function scanCrypto() {
  try {
    const symbols = await getCryptoSymbols();
    let signals = [];
    for (const item of symbols) {
      const history = await getCryptoHistory(item.symbol);
      if (!history) continue;
      const res = analyzeCryptoData(item, history);
      signals.push(res);
      if (signals.length <= CRYPTO_CONFIG.maxAlertsPerScan) {
        await broadcast(cryptoBot, cryptoChatIds, buildCryptoMessage(res));
      }
    }
  } catch (e) {}
}

// ============================================================
// 🤖 أوامر تيليجرام
// ============================================================

if (tasiBot) {
  tasiBot.onText(/\/start|\/scan/, async (msg) => {
    tasiChatIds.add(msg.chat.id);
    await tasiBot.sendMessage(msg.chat.id, "🇸🇦 جاري فحص أسهم تاسي...");
    scanTASI();
  });
}

if (usBot) {
  usBot.onText(/\/start|\/scan/, async (msg) => {
    usChatIds.add(msg.chat.id);
    await usBot.sendMessage(msg.chat.id, "🇺🇸 جاري فحص الأسهم الأمريكية...");
    scanUS();
  });
}

if (cryptoBot) {
  cryptoBot.onText(/\/start|\/scan/, async (msg) => {
    cryptoChatIds.add(msg.chat.id);
    await cryptoBot.sendMessage(msg.chat.id, "🪙 جاري فحص العملات الرقمية...");
    scanCrypto();
  });
}

// ============================================================
// 🚀 التشغيل التلقائي
// ============================================================

setTimeout(() => {
  if (TASI_TOKEN) scanTASI();
  if (US_TOKEN) scanUS();
  if (CRYPTO_TOKEN) scanCrypto();
}, 3000);
