
"use strict";

/*
============================================================
💀🚀 AI PRO MAX
AUTONOMOUS TASI + US + CRYPTO TELEGRAM SCANNER
============================================================

المصدر الوحيد للبيانات:
EODHD API

المزايا:
- TASI 🇸🇦
- US 🇺🇸
- CRYPTO 🪙
- EMA 8 / 21 / 50
- RSI 14
- ATR 14
- دعم
- مقاومة
- قوة الحجم
- قوة الشراء
- قوة البيع
- قوة الإشارة
- 8 أهداف ATR
- سهم صعود 🟢
- سهم هبوط 🔴
- منع تكرار التنبيهات
- فحص تلقائي كل دقيقتين
- لا يحتاج أمر فحص يدوي
- Telegram Webhook على Railway لتجنب 409
============================================================
*/

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");
const fs = require("fs");
const path = require("path");

// ============================================================
// ⚙️ CONFIG
// ============================================================

const PORT = Number(process.env.PORT || 3000);

const TASI_TOKEN = String(process.env.TASI_CONFIG || "").trim();
const US_TOKEN = String(process.env.US_CONFIG || "").trim();
const CRYPTO_TOKEN = String(process.env.CRYPTO_CONFIG || "").trim();

const EODHD_API_KEY = String(
  process.env.EODHD_API_KEY || ""
).trim();

const SCAN_INTERVAL_MS = 2 * 60 * 1000;

// عدد الأسهم التي يتم تحليلها بعمق بعد مرحلة الفرز
const DEEP_SCAN_LIMIT = 30;

// أقل سعر للأسهم الأمريكية
const US_MIN_PRICE = 0.20;

// منع تكرار نفس الإشارة
const SIGNAL_COOLDOWN_MS = 30 * 60 * 1000;

// ذاكرة الرموز
const CACHE_TTL_MS = 6 * 60 * 60 * 1000;

// عدد الشموع المطلوبة للتحليل
const REQUIRED_CANDLES = 120;

// ============================================================
// 📁 STORAGE
// ============================================================

const DATA_DIR = path.join(process.cwd(), "data");

if (!fs.existsSync(DATA_DIR)) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

const CHAT_FILE = path.join(DATA_DIR, "chat_ids.json");

function loadJson(file, fallback) {
  try {
    if (!fs.existsSync(file)) return fallback;

    const raw = fs.readFileSync(file, "utf8");
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

function saveJson(file, data) {
  try {
    fs.writeFileSync(
      file,
      JSON.stringify(data, null, 2),
      "utf8"
    );
  } catch (err) {
    log("⚠️ حفظ البيانات فشل:", err.message);
  }
}

const chatIds = loadJson(CHAT_FILE, {
  TASI: [],
  US: [],
  CRYPTO: []
});

// ============================================================
// 🧠 STATE
// ============================================================

const state = {
  running: false,

  universes: {
    TASI: [],
    US: [],
    CRYPTO: []
  },

  universeLoadedAt: {
    TASI: 0,
    US: 0,
    CRYPTO: 0
  },

  lastSignals: new Map(),

  stats: {
    scans: 0,
    alerts: 0,
    apiErrors: 0
  }
};

// ============================================================
// 📝 LOGGER
// ============================================================

function log(...args) {
  console.log(
    new Date().toISOString(),
    "|",
    ...args
  );
}

// ============================================================
// 🔐 CHECK CONFIG
// ============================================================

function checkConfig() {
  const missing = [];

  if (!TASI_TOKEN) missing.push("TASI_CONFIG");
  if (!US_TOKEN) missing.push("US_CONFIG");
  if (!CRYPTO_TOKEN) missing.push("CRYPTO_CONFIG");
  if (!EODHD_API_KEY) missing.push("EODHD_API_KEY");

  if (missing.length) {
    throw new Error(
      "متغيرات ناقصة: " + missing.join(" , ")
    );
  }
}

// ============================================================
// 🤖 TELEGRAM BOTS
// ============================================================

let tasiBot = null;
let usBot = null;
let cryptoBot = null;

function createBots() {
  tasiBot = new TelegramBot(TASI_TOKEN, {
    polling: false
  });

  usBot = new TelegramBot(US_TOKEN, {
    polling: false
  });

  cryptoBot = new TelegramBot(CRYPTO_TOKEN, {
    polling: false
  });

  setupBot(tasiBot, "TASI", "السوق السعودي 🇸🇦");
  setupBot(usBot, "US", "السوق الأمريكي 🇺🇸");
  setupBot(
    cryptoBot,
    "CRYPTO",
    "العملات الرقمية 🪙"
  );

  log("🤖 TASI BOT: ON");
  log("🤖 US BOT: ON");
  log("🤖 CRYPTO BOT: ON");
}

// ============================================================
// 🤖 BOT SETUP
// ============================================================

function setupBot(bot, market, marketName) {

  bot.on("polling_error", err => {
    log("Telegram:", market, err.message);
  });

  bot.on("webhook_error", err => {
    log("Telegram:", market, err.message);
  });

  bot.on("message", async msg => {

    if (!msg || !msg.chat) return;

    const chatId = String(msg.chat.id);

    if (!chatIds[market].includes(chatId)) {
      chatIds[market].push(chatId);
      saveJson(CHAT_FILE, chatIds);
    }

    if (
      typeof msg.text === "string" &&
      msg.text.trim().toLowerCase() === "/start"
    ) {
      await sendStartupMessage(
        bot,
        chatId,
        marketName
      );
    }
  });
}

// ============================================================
// 📡 TELEGRAM WEBHOOK
// ============================================================

function getRailwayDomain() {

  const domain =
    process.env.RAILWAY_PUBLIC_DOMAIN ||
    process.env.RAILWAY_STATIC_URL ||
    "";

  if (!domain) return "";

  return String(domain)
    .replace(/^https?:\/\//, "")
    .replace(/\/+$/, "");
}

async function setupWebhooks() {

  const domain = getRailwayDomain();

  if (!domain) {
    log(
      "⚠️ لم يتم العثور على نطاق Railway؛",
      "سيبقى الفحص التلقائي فعالًا."
    );
    return;
  }

  const bots = [
    [tasiBot, "tasi"],
    [usBot, "us"],
    [cryptoBot, "crypto"]
  ];

  for (const [bot, name] of bots) {

    try {

      const url =
        `https://${domain}/telegram/${name}`;

      await bot.setWebHook(url);

      log(
        "Telegram Webhook:",
        name,
        "ON"
      );

    } catch (err) {

      log(
        "Telegram Webhook:",
        name,
        "FAILED",
        err.message
      );
    }
  }
}

// ============================================================
// 🚀 STARTUP MESSAGE
// ============================================================

async function sendStartupMessage(
  bot,
  chatId,
  marketName
) {

  const text =
`💀🚀 AI PRO MAX

✅ البوت يعمل الآن

🔄 الفحص تلقائي وكامل
⏱️ الفحص كل دقيقتين

📊 السوق:
${marketName}

🧠 المحرك الذكي:

• EMA 8
• EMA 21
• EMA 50
• RSI 14
• ATR 14
• دعم
• مقاومة
• قوة الحجم
• قوة الشراء
• قوة البيع
• 8 أهداف ATR
• منع تكرار التنبيهات

🟢 سهم أخضر متحرك = صعود قوي
🔴 سهم أحمر متحرك = هبوط قوي

🤖 لا تحتاج إلى تشغيل الفحص يدويًا.

📡 مصدر البيانات:
EODHD فقط`;

  try {
    await bot.sendMessage(
      chatId,
      text
    );
  } catch (err) {
    log(
      "Telegram send:",
      err.message
    );
  }
}

// ============================================================
// 🌐 EXPRESS
// ============================================================

const app = express();

app.use(express.json({
  limit: "2mb"
}));

app.get("/", (req, res) => {

  res.status(200).json({
    bot: "AI PRO MAX",
    status: "online",
    automatic_scan: true,
    interval: "2 minutes",
    markets: [
      "TASI",
      "US",
      "CRYPTO"
    ],
    data_source: "EODHD"
  });
});

// ============================================================
// TELEGRAM WEBHOOK ROUTES
// ============================================================

app.post(
  "/telegram/tasi",
  (req, res) => {

    try {
      tasiBot.processUpdate(req.body);
    } catch (err) {
      log(
        "Webhook TASI:",
        err.message
      );
    }

    res.sendStatus(200);
  }
);

app.post(
  "/telegram/us",
  (req, res) => {

    try {
      usBot.processUpdate(req.body);
    } catch (err) {
      log(
        "Webhook US:",
        err.message
      );
    }

    res.sendStatus(200);
  }
);

app.post(
  "/telegram/crypto",
  (req, res) => {

    try {
      cryptoBot.processUpdate(req.body);
    } catch (err) {
      log(
        "Webhook CRYPTO:",
        err.message
      );
    }

    res.sendStatus(200);
  }
);

// ============================================================
// 🚨 EODHD REQUEST ENGINE
// ============================================================

async function eodhd(endpoint, params = {}) {

  if (!EODHD_API_KEY) {
    throw new Error(
      "EODHD_API_KEY غير موجود"
    );
  }

  const query = new URLSearchParams();

  query.set(
    "api_token",
    EODHD_API_KEY
  );

  query.set(
    "fmt",
    "json"
  );

  for (const [key, value] of Object.entries(params)) {

    if (
      value !== undefined &&
      value !== null &&
      value !== ""
    ) {
      query.set(
        key,
        String(value)
      );
    }
  }

  const url =
    `https://eodhd.com/api/${endpoint}?${query.toString()}`;

  let response;

  try {

    response = await fetch(
      url,
      {
        method: "GET",
        headers: {
          "Accept": "application/json",
          "User-Agent":
            "AI-PRO-MAX/2.0"
        }
      }
    );

  } catch (err) {

    state.stats.apiErrors++;

    throw new Error(
      "تعذر الاتصال بـ EODHD: " +
      err.message
    );
  }

  const text =
    await response.text();

  let data;

  try {
    data = JSON.parse(text);
  } catch {
    data = text;
  }

  if (!response.ok) {

    state.stats.apiErrors++;

    let message =
      typeof data === "string"
        ? data
        : JSON.stringify(data);

    throw new Error(
      `EODHD HTTP ${response.status}: ${message}`
    );
  }

  return data;
}

// ============================================================
// 🧾 EXCHANGE DISCOVERY
// ============================================================

async function findSaudiExchange() {

  const exchanges =
    await eodhd(
      "exchanges-list/"
    );

  if (!Array.isArray(exchanges)) {
    throw new Error(
      "قائمة البورصات من EODHD غير صالحة"
    );
  }

  const candidates =
    exchanges.filter(x => {

      const text = [
        x.Code,
        x.Name,
        x.Country,
        x.Description
      ]
        .filter(Boolean)
        .join(" ");

      return /saudi|tadawul|saudi stock/i
        .test(text);
    });

  if (!candidates.length) {
    throw new Error(
      "EODHD لم يرجع بورصة السعودية"
    );
  }

  const preferred =
    candidates.find(x =>
      /tadawul|saudi stock exchange/i
        .test(
          `${x.Name || ""} ${x.Description || ""}`
        )
    ) ||
    candidates[0];

  return preferred.Code;
}

// ============================================================
// 📊 LOAD TASI
// ============================================================

async function loadTasi() {

  const exchange =
    await findSaudiExchange();

  log(
    "🇸🇦 EODHD Saudi Exchange:",
    exchange
  );

  const rows =
    await eodhd(
      `exchange-symbol-list/${encodeURIComponent(exchange)}`
    );

  if (!Array.isArray(rows)) {
    throw new Error(
      "EODHD لم يرجع قائمة أسهم TASI"
    );
  }

  const symbols =
    rows
      .map(row => {

        const code =
          row.Code ||
          row.code ||
          row.Symbol ||
          row.symbol;

        if (!code) return null;

        return {
          symbol:
            String(code).trim(),
          name:
            String(
              row.Name ||
              row.name ||
              row.Description ||
              ""
            ).trim(),
          exchange
        };
      })
      .filter(Boolean);

  if (!symbols.length) {
    throw new Error(
      "EODHD أعاد قائمة TASI فارغة"
    );
  }

  state.universes.TASI =
    symbols;

  state.universeLoadedAt.TASI =
    Date.now();

  log(
    "🇸🇦 TASI symbols:",
    symbols.length
  );
}

// ============================================================
// 🇺🇸 LOAD US
// ============================================================

async function loadUS() {

  const rows =
    await eodhd(
      "exchange-symbol-list/US"
    );

  if (!Array.isArray(rows)) {
    throw new Error(
      "EODHD لم يرجع قائمة US"
    );
  }

  const symbols =
    rows
      .map(row => {

        const code =
          row.Code ||
          row.code ||
          row.Symbol ||
          row.symbol;

        if (!code) return null;

        const type =
          String(
            row.Type ||
            row.type ||
            ""
          ).toUpperCase();

        if (
          type &&
          !/COMMON|ETF|STOCK|FUND/.test(type)
        ) {
          return null;
        }

        return {
          symbol:
            String(code).trim(),
          name:
            String(
              row.Name ||
              row.name ||
              ""
            ).trim(),
          exchange: "US"
        };
      })
      .filter(Boolean);

  if (!symbols.length) {
    throw new Error(
      "EODHD أعاد قائمة US فارغة"
    );
  }

  state.universes.US =
    symbols;

  state.universeLoadedAt.US =
    Date.now();

  log(
    "🇺🇸 US symbols:",
    symbols.length
  );
}

// ============================================================
// 🪙 LOAD CRYPTO
// ============================================================

async function loadCrypto() {

  const rows =
    await eodhd(
      "exchange-symbol-list/CC"
    );

  if (!Array.isArray(rows)) {
    throw new Error(
      "EODHD لم يرجع قائمة العملات الرقمية"
    );
  }

  const symbols =
    rows
      .map(row => {

        const code =
          row.Code ||
          row.code ||
          row.Symbol ||
          row.symbol;

        if (!code) return null;

        return {
          symbol:
            String(code).trim(),
          name:
            String(
              row.Name ||
              row.name ||
              ""
            ).trim(),
          exchange: "CC"
        };
      })
      .filter(Boolean);

  if (!symbols.length) {
    throw new Error(
      "EODHD أعاد قائمة العملات فارغة"
    );
  }

  state.universes.CRYPTO =
    symbols;

  state.universeLoadedAt.CRYPTO =
    Date.now();

  log(
    "🪙 CRYPTO symbols:",
    symbols.length
  );
}

// ============================================================
// 🌍 LOAD ALL MARKETS
// ============================================================

async function loadUniverse(
  market
) {

  const loadedAt =
    state.universeLoadedAt[market];

  if (
    loadedAt &&
    Date.now() - loadedAt <
      CACHE_TTL_MS &&
    state.universes[market].length
  ) {
    return;
  }

  try {

    if (market === "TASI") {
      await loadTasi();
    }

    if (market === "US") {
      await loadUS();
    }

    if (market === "CRYPTO") {
      await loadCrypto();
    }

  } catch (err) {

    log(
      "🚨",
      market,
      "EODHD:",
      err.message
    );

    /*
    لا نمسح القائمة القديمة.
    إذا كانت لدينا قائمة سابقة نستمر بها.
    */

    if (
      !state.universes[market].length
    ) {
      log(
        "ℹ️",
        market,
        "لا توجد قائمة محفوظة؛",
        "سيتم إعادة المحاولة لاحقًا."
      );
    }
  }
}

// ============================================================
// 📈 QUOTES
// ============================================================

async function getQuotes(
  market,
  symbols
) {

  if (!symbols.length) {
    return [];
  }

  let exchange;

  if (market === "TASI") {
    exchange =
      symbols[0].exchange;
  }

  if (market === "US") {
    exchange = "US";
  }

  if (market === "CRYPTO") {
    exchange = "CC";
  }

  const result = [];

  /*
  نرسل دفعات صغيرة حتى لا يصبح رابط API ضخمًا.
  */

  const BATCH = 50;

  for (
    let i = 0;
    i < symbols.length;
    i += BATCH
  ) {

    const batch =
      symbols.slice(
        i,
        i + BATCH
      );

    const codes =
      batch
        .map(x =>
          x.symbol
        )
        .join(",");

    try {

      const rows =
        await eodhd(
          `real-time/${encodeURIComponent(exchange)}`,
          {
            s: codes
          }
        );

      if (Array.isArray(rows)) {

        for (const row of rows) {

          const symbol =
            row.code ||
            row.Code ||
            row.symbol ||
            row.Symbol;

          const price =
            Number(
              row.close ??
              row.Close ??
              row.price ??
              row.Price
            );

          if (
            symbol &&
            Number.isFinite(price) &&
            price > 0
          ) {

            result.push({
              symbol:
                String(symbol),
              price,
              open:
                Number(row.open || 0),
              high:
                Number(row.high || 0),
              low:
                Number(row.low || 0),
              volume:
                Number(
                  row.volume || 0
                ),
              previousClose:
                Number(
                  row.previousClose ||
                  row.prevClose ||
                  0
                )
            });
          }
        }
      }

    } catch (err) {

      log(
        "⚠️",
        market,
        "quotes:",
        err.message
      );

      /*
      لا نكمل ضرب API إذا كان الحساب
      يرفض الطلبات.
      */

      if (
        /HTTP 401|HTTP 402|HTTP 403|HTTP 429/i
          .test(err.message)
      ) {
        break;
      }
    }
  }

  return result;
}

// ============================================================
// 🕯️ INTRADAY
// ============================================================

async function getIntraday(
  symbol,
  exchange
) {

  try {

    const rows =
      await eodhd(
        `intraday/${encodeURIComponent(
          `${symbol}.${exchange}`
        )}`,
        {
          interval: "5m"
        }
      );

    if (!Array.isArray(rows)) {
      return [];
    }

    return rows
      .map(x => ({
        date:
          x.datetime ||
          x.date ||
          "",
        open:
          Number(x.open || 0),
        high:
          Number(x.high || 0),
        low:
          Number(x.low || 0),
        close:
          Number(x.close || 0),
        volume:
          Number(x.volume || 0)
      }))
      .filter(x =>
        x.close > 0
      );

  } catch (err) {

    log(
      "⚠️ Intraday:",
      symbol,
      err.message
    );

    return [];
  }
}

// ============================================================
// 🧮 EMA
// ============================================================

function ema(values, period) {

  if (
    !Array.isArray(values) ||
    values.length < period
  ) {
    return null;
  }

  const multiplier =
    2 / (period + 1);

  let value = 0;

  for (
    let i = 0;
    i < period;
    i++
  ) {
    value += values[i];
  }

  value /= period;

  for (
    let i = period;
    i < values.length;
    i++
  ) {

    value =
      (
        values[i] - value
      ) *
      multiplier +
      value;
  }

  return value;
}

// ============================================================
// 📊 RSI
// ============================================================

function rsi(
  values,
  period = 14
) {

  if (
    values.length <= period
  ) {
    return null;
  }

  let gain = 0;
  let loss = 0;

  for (
    let i = 1;
    i <= period;
    i++
  ) {

    const diff =
      values[i] -
      values[i - 1];

    if (diff >= 0) {
      gain += diff;
    } else {
      loss -= diff;
    }
  }

  gain /= period;
  loss /= period;

  for (
    let i = period + 1;
    i < values.length;
    i++
  ) {

    const diff =
      values[i] -
      values[i - 1];

    const g =
      diff > 0
        ? diff
        : 0;

    const l =
      diff < 0
        ? -diff
        : 0;

    gain =
      ((gain * (period - 1)) + g)
      / period;

    loss =
      ((loss * (period - 1)) + l)
      / period;
  }

  if (loss === 0) {
    return 100;
  }

  const rs =
    gain / loss;

  return 100 -
    (100 / (1 + rs));
}

// ============================================================
// 📐 ATR
// ============================================================

function atr(
  candles,
  period = 14
) {

  if (
    candles.length <
    period + 1
  ) {
    return null;
  }

  const trs = [];

  for (
    let i = 1;
    i < candles.length;
    i++
  ) {

    const current =
      candles[i];

    const previous =
      candles[i - 1];

    const tr =
      Math.max(
        current.high -
          current.low,

        Math.abs(
          current.high -
          previous.close
        ),

        Math.abs(
          current.low -
          previous.close
        )
      );

    trs.push(tr);
  }

  if (
    trs.length < period
  ) {
    return null;
  }

  let value = 0;

  for (
    let i = 0;
    i < period;
    i++
  ) {
    value += trs[i];
  }

  value /= period;

  for (
    let i = period;
    i < trs.length;
    i++
  ) {

    value =
      (
        value * (period - 1) +
        trs[i]
      ) / period;
  }

  return value;
}

// ============================================================
// 📏 SUPPORT / RESISTANCE
// ============================================================

function supportResistance(
  candles
) {

  if (
    candles.length < 20
  ) {
    return {
      support: null,
      resistance: null
    };
  }

  const recent =
    candles.slice(-30);

  const lows =
    recent.map(x => x.low);

  const highs =
    recent.map(x => x.high);

  return {
    support:
      Math.min(...lows),

    resistance:
      Math.max(...highs)
  };
}

// ============================================================
// 🔊 VOLUME STRENGTH
// ============================================================

function volumeStrength(
  candles
) {

  if (
    candles.length < 20
  ) {
    return 1;
  }

  const volumes =
    candles
      .slice(-20)
      .map(x =>
        Number(x.volume || 0)
      );

  const current =
    volumes[
      volumes.length - 1
    ];

  const average =
    volumes
      .slice(0, -1)
      .reduce(
        (a, b) => a + b,
        0
      ) /
    Math.max(
      1,
      volumes.length - 1
    );

  if (!average) {
    return 1;
  }

  return current / average;
}

// ============================================================
// 🟢 BUY / 🔴 SELL POWER
// ============================================================

function powerScore(
  candles
) {

  if (
    candles.length < 20
  ) {

    return {
      buy: 50,
      sell: 50
    };
  }

  const recent =
    candles.slice(-20);

  let buy = 0;
  let sell = 0;

  for (const c of recent) {

    const range =
      c.high - c.low;

    if (range <= 0) continue;

    const position =
      (
        c.close - c.low
      ) / range;

    const weight =
      Math.max(
        1,
        Number(c.volume || 1)
      );

    buy +=
      position * weight;

    sell +=
      (1 - position) *
      weight;
  }

  const total =
    buy + sell;

  if (!total) {
    return {
      buy: 50,
      sell: 50
    };
  }

  return {
    buy:
      Math.round(
        (buy / total) * 100
      ),

    sell:
      Math.round(
        (sell / total) * 100
      )
  };
}

// ============================================================
// 🧠 SIGNAL ENGINE
// ============================================================

function analyze(
  quote,
  candles
) {

  if (
    !quote ||
    !Array.isArray(candles) ||
    candles.length <
      REQUIRED_CANDLES
  ) {
    return null;
  }

  const closes =
    candles.map(
      x => x.close
    );

  const ema8 =
    ema(closes, 8);

  const ema21 =
    ema(closes, 21);

  const ema50 =
    ema(closes, 50);

  const rsi14 =
    rsi(closes, 14);

  const atr14 =
    atr(candles, 14);

  if (
    !ema8 ||
    !ema21 ||
    !ema50 ||
    rsi14 === null ||
    !atr14
  ) {
    return null;
  }

  const sr =
    supportResistance(
      candles
    );

  const volume =
    volumeStrength(
      candles
    );

  const power =
    powerScore(
      candles
    );

  const price =
    quote.price;

  let score = 50;

  // EMA
  if (price > ema8)
    score += 7;
  else
    score -= 7;

  if (ema8 > ema21)
    score += 8;
  else
    score -= 8;

  if (ema21 > ema50)
    score += 8;
  else
    score -= 8;

  // RSI
  if (
    rsi14 >= 55 &&
    rsi14 <= 78
  ) {
    score += 10;
  }

  if (
    rsi14 <= 45 &&
    rsi14 >= 22
  ) {
    score -= 10;
  }

  // Volume
  if (volume >= 2) {
    score += 8;
  } else if (volume >= 1.3) {
    score += 4;
  }

  // Buy/Sell
  score +=
    (power.buy -
      power.sell) *
    0.12;

  score =
    Math.max(
      0,
      Math.min(
        100,
        Math.round(score)
      )
    );

  let signal =
    "محايد";

  let direction =
    "neutral";

  /*
  🟢 شراء قوي
  */

  if (
    score >= 75 &&
    power.buy >= 60 &&
    price > ema8 &&
    ema8 > ema21
  ) {

    signal =
      "شراء قوي";

    direction =
      "up";
  }

  /*
  🔴 بيع قوي
  */

  else if (
    score <= 25 &&
    power.sell >= 60 &&
    price < ema8 &&
    ema8 < ema21
  ) {

    signal =
      "بيع قوي";

    direction =
      "down";
  }

  else {
    return null;
  }

  return {
    signal,
    direction,

    price,

    change:
      quote.previousClose > 0
        ? (
            (
              price -
              quote.previousClose
            ) /
            quote.previousClose
          ) * 100
        : 0,

    ema8,
    ema21,
    ema50,

    rsi14,
    atr14,

    support:
      sr.support,

    resistance:
      sr.resistance,

    volumeStrength:
      volume,

    buyPower:
      power.buy,

    sellPower:
      power.sell,

    score
  };
}

// ============================================================
// 🎯 ATR TARGETS
// ============================================================

function atrTargets(
  price,
  atrValue,
  direction
) {

  const multipliers = [
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8
  ];

  return multipliers.map(
    (m, index) => {

      const target =
        direction === "up"
          ? price +
            atrValue * m
          : price -
            atrValue * m;

      const percent =
        (
          (target - price) /
          price
        ) * 100;

      return {
        number:
          index + 1,

        price:
          target,

        percent
      };
    }
  );
}

// ============================================================
// 🔢 FORMAT PRICE
// ============================================================

function formatPrice(
  value
) {

  if (
    value === null ||
    value === undefined ||
    !Number.isFinite(
      Number(value)
    )
  ) {
    return "-";
  }

  const n =
    Number(value);

  if (Math.abs(n) >= 1000) {
    return n.toLocaleString(
      "en-US",
      {
        minimumFractionDigits: 0,
        maximumFractionDigits: 2
      }
    );
  }

  if (Math.abs(n) >= 1) {
    return n.toFixed(2);
  }

  return n.toFixed(4);
}

// ============================================================
// 🔢 FORMAT VOLUME
// ============================================================

function formatVolume(
  value
) {

  const n =
    Number(value || 0);

  if (n >= 1e9) {
    return (
      (n / 1e9).toFixed(2) +
      "B"
    );
  }

  if (n >= 1e6) {
    return (
      (n / 1e6).toFixed(2) +
      "M"
    );
  }

  if (n >= 1e3) {
    return (
      (n / 1e3).toFixed(2) +
      "K"
    );
  }

  return String(
    Math.round(n)
  );
}

// ============================================================
// 🟢🔴 MOVING ARROW
// ============================================================

function directionArrow(
  direction
) {

  if (direction === "up") {
    return "🟢⬆️";
  }

  if (direction === "down") {
    return "🔴⬇️";
  }

  return "⚪";
}

// ============================================================
// 🎯 SIGNAL MESSAGE
// ============================================================

function buildSignalMessage(
  market,
  quote,
  analysis,
  name
) {

  const marketName = {

    TASI:
      "السوق السعودي (TASI) 🇸🇦",

    US:
      "السوق الأمريكي (US) 🇺🇸",

    CRYPTO:
      "العملات الرقمية (CRYPTO) 🪙"

  }[market];

  const action =
    analysis.direction === "up"
      ? "🟢⬆️ شراء قوي"
      : "🔴⬇️ بيع قوي";

  const targets =
    atrTargets(
      analysis.price,
      analysis.atr14,
      analysis.direction
    );

  let targetText =
    "";

  for (const target of targets) {

    const sign =
      target.percent >= 0
        ? "+"
        : "";

    targetText +=
`TP${target.number}   ${formatPrice(target.price)}   (${sign}${target.percent.toFixed(1)}%)
`;
  }

  const changeSign =
    analysis.change >= 0
      ? "+"
      : "";

  return (
`💀🚀 AI PRO MAX SIGNAL

${marketName}

${quote.symbol}
${name || "—"}

━━━━━━━━━━━━━━━━━━━━

${action}

السعر: ${formatPrice(analysis.price)}
التغير: ${changeSign}${analysis.change.toFixed(2)}%

قوة الإشارة: ${analysis.score}/100
قوة الشراء: ${analysis.buyPower}%
قوة البيع: ${analysis.sellPower}%
قوة الحجم: ${analysis.volumeStrength.toFixed(1)}x
الحجم: ${formatVolume(quote.volume)}

━━━━━━━━━━━━━━━━━━━━

EMA 8: ${formatPrice(analysis.ema8)}
EMA 21: ${formatPrice(analysis.ema21)}
EMA 50: ${formatPrice(analysis.ema50)}

RSI 14: ${analysis.rsi14.toFixed(1)}
ATR 14: ${formatPrice(analysis.atr14)}

━━━━━━━━━━━━━━━━━━━━

الدعم: ${formatPrice(analysis.support)}
المقاومة: ${formatPrice(analysis.resistance)}

${directionArrow(analysis.direction)} الاتجاه:
${
  analysis.direction === "up"
    ? "صاعد قوي"
    : "هابط قوي"
}

━━━━━━━━━━━━━━━━━━━━

🎯 أهداف ATR الثمانية:

${targetText}
━━━━━━━━━━━━━━━━━━━━

🤖 AI PRO MAX
🔄 الفحص تلقائي كل دقيقتين
📡 البيانات: EODHD فقط`
  );
}

// ============================================================
// 🚨 DUPLICATE CONTROL
// ============================================================

function signalKey(
  market,
  symbol,
  direction
) {

  return (
    market +
    ":" +
    symbol +
    ":" +
    direction
  );
}

function canSendSignal(
  market,
  symbol,
  direction
) {

  const key =
    signalKey(
      market,
      symbol,
      direction
    );

  const previous =
    state.lastSignals.get(
      key
    );

  if (
    previous &&
    Date.now() - previous <
      SIGNAL_COOLDOWN_MS
  ) {
    return false;
  }

  state.lastSignals.set(
    key,
    Date.now()
  );

  return true;
}

// ============================================================
// 📤 SEND ALERT
// ============================================================

async function sendSignal(
  market,
  quote,
  analysis,
  name
) {

  if (
    !canSendSignal(
      market,
      quote.symbol,
      analysis.direction
    )
  ) {
    return;
  }

  const bot = {

    TASI: tasiBot,
    US: usBot,
    CRYPTO: cryptoBot

  }[market];

  if (!bot) return;

  const message =
    buildSignalMessage(
      market,
      quote,
      analysis,
      name
    );

  const recipients =
    chatIds[market] || [];

  for (
    const chatId of recipients
  ) {

    try {

      await bot.sendMessage(
        chatId,
        message
      );

      state.stats.alerts++;

      log(
        "📨 ALERT",
        market,
        quote.symbol,
        analysis.signal
      );

    } catch (err) {

      log(
        "Telegram:",
        market,
        err.message
      );
    }
  }
}

// ============================================================
// 🔎 DEEP ANALYSIS
// ============================================================

async function deepAnalyze(
  market,
  candidate
) {

  let exchange;

  if (market === "TASI") {
    exchange =
      candidate.exchange;
  }

  if (market === "US") {
    exchange = "US";
  }

  if (market === "CRYPTO") {
    exchange = "CC";
  }

  const candles =
    await getIntraday(
      candidate.symbol,
      exchange
    );

  if (
    candles.length <
    REQUIRED_CANDLES
  ) {
    return null;
  }

  const analysis =
    analyze(
      candidate,
      candles
    );

  if (!analysis) {
    return null;
  }

  return {
    quote: candidate,
    analysis,
    name:
      candidate.name || ""
  };
}

// ============================================================
// 🧠 MARKET SCAN
// ============================================================

async function scanMarket(
  market
) {

  await loadUniverse(
    market
  );

  const universe =
    state.universes[market];

  if (!universe.length) {

    /*
    لا نكتب:
    "لا توجد رموز"

    لأن هذا كان سبب الالتباس السابق.
    */

    log(
      "ℹ️",
      market,
      "لم يتم تحميل القائمة من EODHD في هذه الدورة."
    );

    return;
  }

  log(
    "🔎 فحص",
    market,
    "|",
    universe.length,
    "رمز"
  );

  const quotes =
    await getQuotes(
      market,
      universe
    );

  if (!quotes.length) {

    log(
      "ℹ️",
      market,
      "لم تصل أسعار من EODHD في هذه الدورة."
    );

    return;
  }

  let filtered =
    quotes;

  // US minimum price
  if (market === "US") {

    filtered =
      filtered.filter(
        x =>
          x.price >=
          US_MIN_PRICE
      );
  }

  /*
  فرز مبدئي حسب الحركة والحجم
  */

  filtered.sort(
    (a, b) => {

      const aChange =
        Math.abs(
          a.previousClose
            ? (
                (
                  a.price -
                  a.previousClose
                ) /
                a.previousClose
              ) * 100
            : 0
        );

      const bChange =
        Math.abs(
          b.previousClose
            ? (
                (
                  b.price -
                  b.previousClose
                ) /
                b.previousClose
              ) * 100
            : 0
        );

      const av =
        Number(a.volume || 0);

      const bv =
        Number(b.volume || 0);

      return (
        (bChange + Math.log10(bv + 1)) -
        (aChange + Math.log10(av + 1))
      );
    }
  );

  const candidates =
    filtered.slice(
      0,
      DEEP_SCAN_LIMIT
    );

  log(
    "🧠 تحليل عميق",
    market,
    "|",
    candidates.length
  );

  for (
    const candidate of candidates
  ) {

    try {

      const result =
        await deepAnalyze(
          market,
          candidate
        );

      if (!result) {
        continue;
      }

      await sendSignal(
        market,
        result.quote,
        result.analysis,
        result.name
      );

    } catch (err) {

      log(
        "⚠️ تحليل:",
        market,
        candidate.symbol,
        err.message
      );
    }
  }
}

// ============================================================
// 🔄 FULL SCAN
// ============================================================

async function fullScan() {

  if (state.running) {
    log(
      "⏳ دورة سابقة ما زالت تعمل."
    );
    return;
  }

  state.running = true;
  state.stats.scans++;

  const started =
    Date.now();

  log(
    "================================================"
  );

  log(
    "🚀 AI PRO MAX SCAN",
    "#",
    state.stats.scans
  );

  try {

    /*
    الأسواق الثلاثة
    */

    await scanMarket(
      "TASI"
    );

    await scanMarket(
      "US"
    );

    await scanMarket(
      "CRYPTO"
    );

  } catch (err) {

    log(
      "🚨 SCAN ERROR:",
      err.message
    );

  } finally {

    state.running = false;

    log(
      "✅ انتهت الدورة |",
      `${Date.now() - started}ms`
    );

    log(
      "================================================"
    );
  }
}

// ============================================================
// ❤️ HEALTH
// ============================================================

function healthLog() {

  log(
    "❤️ AI PRO MAX",
    "| scans:",
    state.stats.scans,
    "| alerts:",
    state.stats.alerts,
    "| API errors:",
    state.stats.apiErrors
  );
}

// ============================================================
// 🚀 START
// ============================================================

async function start() {

  try {

    checkConfig();

    log(
      "================================================"
    );

    log(
      "💀🚀 تشغيل AI PRO MAX"
    );

    log(
      "✅ EODHD_API_KEY موجود"
    );

    log(
      "✅ TASI_CONFIG موجود"
    );

    log(
      "✅ US_CONFIG موجود"
    );

    log(
      "✅ CRYPTO_CONFIG موجود"
    );

    log(
      "📡 مصدر البيانات: EODHD فقط"
    );

    log(
      "🔄 الفحص: كل دقيقتين"
    );

    log(
      "================================================"
    );

    createBots();

    await setupWebhooks();

    /*
    أول فحص مباشرة
    */

    setTimeout(
      () => {
        fullScan().catch(
          err =>
            log(
              "SCAN:",
              err.message
            )
        );
      },
      5000
    );

    /*
    فحص تلقائي كل دقيقتين
    */

    setInterval(
      () => {

        fullScan().catch(
          err =>
            log(
              "SCAN:",
              err.message
            )
        );

      },
      SCAN_INTERVAL_MS
    );

    /*
    صحة الخدمة كل 10 دقائق
    */

    setInterval(
      healthLog,
      10 * 60 * 1000
    );

    log(
      "🟢 النظام يعمل 24/7"
    );

  } catch (err) {

    log(
      "🚨 START ERROR:",
      err.message
    );

    /*
    لا نغلق الخدمة بسبب خطأ مؤقت.
    */

    setTimeout(
      start,
      30 * 1000
    );
  }
}

// ============================================================
// 🌐 SERVER
// ============================================================

app.listen(
  PORT,
  "0.0.0.0",
  () => {

    log(
      "🌐 PORT:",
      PORT
    );

    start();
  }
);

// ============================================================
// 🛡️ GLOBAL ERROR PROTECTION
// ============================================================

process.on(
  "unhandledRejection",
  err => {

    log(
      "🚨 unhandledRejection:",
      err?.message ||
      String(err)
    );
  }
);

process.on(
  "uncaughtException",
  err => {

    log(
      "🚨 uncaughtException:",
      err?.message ||
      String(err)
    );
  }
);