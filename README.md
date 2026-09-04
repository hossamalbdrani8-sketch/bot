// ============================================================
// 🇺🇸 US STOCK SCANNER BOT - PRO MAX
// Node.js 18+
// Yahoo Finance public endpoints
// Telegram Bot
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// ⚙️ الإعدادات
// ============================================================

const TOKEN = process.env.TELEGRAM_TOKEN;

if (!TOKEN) {
  throw new Error("❌ TELEGRAM_TOKEN غير موجود في Environment Variables");
}

const PORT = Number(process.env.PORT || 3000);

const MAX_SYMBOLS = Number(process.env.MAX_SYMBOLS || 150);

const MIN_PRICE = Number(process.env.MIN_PRICE || 0.10);

const MIN_CHANGE = Number(process.env.MIN_CHANGE || 0.30);

const SCAN_INTERVAL_MIN = Number(
  process.env.SCAN_INTERVAL_MIN || 5
);

const UPDATE_INTERVAL_SEC = Number(
  process.env.UPDATE_INTERVAL_SEC || 30
);

const REQUEST_DELAY_MS = Number(
  process.env.REQUEST_DELAY_MS || 300
);

const PROFILE_CACHE_MS =
  Number(process.env.PROFILE_CACHE_MS || 30 * 60 * 1000);

const NEWS_CACHE_MS =
  Number(process.env.NEWS_CACHE_MS || 5 * 60 * 1000);

// ============================================================
// 🤖 Telegram
// ============================================================

const bot = new TelegramBot(TOKEN, {
  polling: true
});

// ============================================================
// 🌐 Express
// ============================================================

const app = express();

app.get("/", (req, res) => {
  res.status(200).send("🇺🇸 US Stock Bot is running");
});

app.get("/health", (req, res) => {
  res.json({
    ok: true,
    bot: "US Stock Scanner PRO MAX",
    time: new Date().toISOString()
  });
});

app.listen(PORT, () => {
  console.log(`🌐 Server running on port ${PORT}`);
});

// ============================================================
// 🧠 التخزين
// ============================================================

const sentSignals = new Map();

const profileCache = new Map();

const newsCache = new Map();

let scanRunning = false;

let lastScanTime = null;

let lastScanStats = {
  candidates: 0,
  checked: 0,
  accepted: 0,
  blockedOTC: 0,
  errors: 0
};

// ============================================================
// 🛡️ حماية الطلبات
// ============================================================

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ============================================================
// 🌐 Yahoo Fetch
// ============================================================

async function yahooFetch(url, options = {}) {

  const response = await fetch(url, {
    ...options,
    headers: {
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
      "Accept": "application/json,text/plain,*/*",
      ...(options.headers || {})
    }
  });

  const text = await response.text();

  if (!response.ok) {
    throw new Error(
      `Yahoo HTTP ${response.status}: ${text.slice(0, 150)}`
    );
  }

  try {
    return JSON.parse(text);
  } catch {
    throw new Error(
      `Yahoo returned invalid JSON: ${text.slice(0, 150)}`
    );
  }
}

// ============================================================
// 🚫 فلتر البورصات
// ============================================================

// هذه هي الأكواد المسموح بها فقط
const ALLOWED_EXCHANGES = new Set([
  "NMS", // NASDAQ Global Select
  "NGM", // NASDAQ Global Market
  "NCM", // NASDAQ Capital Market
  "NYQ", // NYSE
  "ASE"  // NYSE American / AMEX
]);

// أكواد OTC الممنوعة صراحة
const BLOCKED_EXCHANGES = new Set([
  "OTC",
  "OTCM",
  "PNK",
  "OQB",
  "OQX",
  "PK",
  "OB",
  "OTCBB"
]);

function normalizeExchange(value) {

  return String(value || "")
    .trim()
    .toUpperCase();
}

// ============================================================
// 🔐 التحقق الأول من البورصة
// ============================================================

function isAllowedExchangeCode(exchange) {

  const ex = normalizeExchange(exchange);

  if (!ex) {
    return false;
  }

  if (BLOCKED_EXCHANGES.has(ex)) {
    return false;
  }

  return ALLOWED_EXCHANGES.has(ex);
}

// ============================================================
// 🔐 التحقق الثاني من اسم البورصة
// ============================================================

function isAllowedExchangeName(exchangeName) {

  const name = String(exchangeName || "")
    .trim()
    .toUpperCase();

  if (!name) {
    return false;
  }

  // OTC
  if (
    name.includes("OTC") ||
    name.includes("PINK") ||
    name.includes("OTCM")
  ) {
    return false;
  }

  return (
    name.includes("NASDAQ") ||
    name.includes("NYSE") ||
    name.includes("AMERICAN STOCK EXCHANGE") ||
    name.includes("NYSE AMERICAN") ||
    name.includes("AMEX")
  );
}

// ============================================================
// 🛡️ التحقق النهائي من سهم أمريكي غير OTC
// ============================================================

function validateUSListing(meta) {

  if (!meta) {
    return {
      allowed: false,
      reason: "لا توجد بيانات البورصة"
    };
  }

  const instrumentType =
    String(meta.instrumentType || "").toUpperCase();

  const exchangeName =
    String(meta.exchangeName || "");

  const fullExchangeName =
    String(meta.fullExchangeName || "");

  const exchange =
    String(meta.exchange || "");

  // يجب أن يكون سهمًا
  if (
    instrumentType &&
    instrumentType !== "EQUITY"
  ) {
    return {
      allowed: false,
      reason: `ليس سهمًا: ${instrumentType}`
    };
  }

  // منع OTC بالاسم
  const combined =
    `${exchangeName} ${fullExchangeName} ${exchange}`.toUpperCase();

  if (
    combined.includes("OTC") ||
    combined.includes("PINK") ||
    combined.includes("OTCMARKETS")
  ) {
    return {
      allowed: false,
      reason: "OTC"
    };
  }

  // يجب أن تكون البورصة معروفة ومسموحة
  if (
    !isAllowedExchangeName(exchangeName) &&
    !isAllowedExchangeName(fullExchangeName) &&
    !isAllowedExchangeCode(exchange)
  ) {
    return {
      allowed: false,
      reason: `بورصة غير مسموحة: ${exchangeName || fullExchangeName || exchange}`
    };
  }

  return {
    allowed: true,
    exchange:
      fullExchangeName ||
      exchangeName ||
      exchange ||
      "US Exchange"
  };
}

// ============================================================
// 📊 جلب بيانات الشارت
// ============================================================

async function getChart(symbol, range = "5d", interval = "5m") {

  const url =
    `https://query1.finance.yahoo.com/v8/finance/chart/` +
    `${encodeURIComponent(symbol)}` +
    `?range=${range}` +
    `&interval=${interval}` +
    `&includePrePost=false` +
    `&events=div%2Csplits`;

  const data = await yahooFetch(url);

  if (
    !data ||
    !data.chart ||
    !data.chart.result ||
    !data.chart.result[0]
  ) {
    throw new Error("لا توجد بيانات للشارت");
  }

  return data.chart.result[0];
}

// ============================================================
// 🛡️ فحص OTC من بيانات Yahoo Chart
// ============================================================

async function validateSymbolExchange(symbol) {

  const chart = await getChart(
    symbol,
    "1d",
    "5m"
  );

  const meta = chart.meta;

  const validation =
    validateUSListing(meta);

  if (!validation.allowed) {

    const error = new Error(
      `OTC/BLOCKED: ${validation.reason}`
    );

    error.code = "BLOCKED_EXCHANGE";

    throw error;
  }

  return {
    meta,
    exchange: validation.exchange
  };
}

// ============================================================
// 📈 EMA
// ============================================================

function calculateEMA(values, period) {

  if (!Array.isArray(values) || values.length < period) {
    return null;
  }

  const multiplier =
    2 / (period + 1);

  let ema = 0;

  for (let i = 0; i < period; i++) {
    ema += Number(values[i]) || 0;
  }

  ema /= period;

  for (
    let i = period;
    i < values.length;
    i++
  ) {

    const value =
      Number(values[i]);

    if (!Number.isFinite(value)) {
      continue;
    }

    ema =
      (value - ema) * multiplier + ema;
  }

  return ema;
}

// ============================================================
// 📊 VWAP
// ============================================================

function calculateVWAP(high, low, close, volume) {

  let pv = 0;
  let totalVolume = 0;

  const length =
    Math.min(
      high.length,
      low.length,
      close.length,
      volume.length
    );

  const start =
    Math.max(0, length - 78);

  for (let i = start; i < length; i++) {

    const h = Number(high[i]);
    const l = Number(low[i]);
    const c = Number(close[i]);
    const v = Number(volume[i]);

    if (
      !Number.isFinite(h) ||
      !Number.isFinite(l) ||
      !Number.isFinite(c) ||
      !Number.isFinite(v) ||
      v <= 0
    ) {
      continue;
    }

    const typical =
      (h + l + c) / 3;

    pv += typical * v;
    totalVolume += v;
  }

  if (totalVolume <= 0) {
    return null;
  }

  return pv / totalVolume;
}

// ============================================================
// 💧 قوة الحجم
// ============================================================

function calculateVolumeStrength(volumes) {

  const clean =
    volumes
      .map(Number)
      .filter(v => Number.isFinite(v) && v >= 0);

  if (clean.length < 5) {
    return 0;
  }

  const current =
    clean[clean.length - 1];

  const previous =
    clean.slice(
      Math.max(0, clean.length - 25),
      clean.length - 1
    );

  if (!previous.length) {
    return 0;
  }

  const avg =
    previous.reduce(
      (a, b) => a + b,
      0
    ) / previous.length;

  if (avg <= 0) {
    return 0;
  }

  return Math.max(
    0,
    Math.min(
      100,
      (current / avg) * 50
    )
  );
}

// ============================================================
// 💧 تحليل السيولة
// ============================================================

function analyzeLiquidity(close, volume) {

  const len =
    Math.min(
      close.length,
      volume.length
    );

  const start =
    Math.max(1, len - 24);

  let buyVolume = 0;
  let sellVolume = 0;
  let neutralVolume = 0;

  for (let i = start; i < len; i++) {

    const prev =
      Number(close[i - 1]);

    const curr =
      Number(close[i]);

    const vol =
      Number(volume[i]) || 0;

    if (
      !Number.isFinite(prev) ||
      !Number.isFinite(curr)
    ) {
      continue;
    }

    if (curr > prev) {
      buyVolume += vol;
    } else if (curr < prev) {
      sellVolume += vol;
    } else {
      neutralVolume += vol;
    }
  }

  const total =
    buyVolume +
    sellVolume +
    neutralVolume;

  if (total <= 0) {
    return {
      buyRatio: 50,
      sellRatio: 50,
      label: "⚪ سيولة متوازنة"
    };
  }

  const buyRatio =
    (buyVolume / total) * 100;

  const sellRatio =
    (sellVolume / total) * 100;

  let label = "⚪ سيولة متوازنة";

  if (buyRatio >= 70) {
    label = "🟢 دخول سيولة قوية";
  } else if (sellRatio >= 70) {
    label = "🔴 خروج سيولة قوية";
  } else if (buyRatio >= 55) {
    label = "🟢 دخول سيولة";
  } else if (sellRatio >= 55) {
    label = "🔴 خروج سيولة";
  }

  return {
    buyRatio,
    sellRatio,
    label
  };
}

// ============================================================
// 📦 التجميع والتصريف
// ============================================================

function analyzeAccumulation(
  buyRatio,
  sellRatio,
  price,
  vwap,
  volumeStrength
) {

  if (
    buyRatio >= 65 &&
    price >= vwap &&
    volumeStrength >= 55
  ) {
    return "🟢 تجميع قوي";
  }

  if (
    buyRatio >= 55 &&
    price >= vwap
  ) {
    return "🟢 تجميع";
  }

  if (
    sellRatio >= 65 &&
    price < vwap &&
    volumeStrength >= 55
  ) {
    return "🔴 تصريف قوي";
  }

  if (
    sellRatio >= 55 &&
    price < vwap
  ) {
    return "🔴 تصريف";
  }

  return "⚪ لا يوجد تجميع واضح";
}

// ============================================================
// 📈 نشاط السهم
// ============================================================

function analyzeActivity(
  changePercent,
  volumeStrength,
  buyRatio,
  sellRatio
) {

  const absChange =
    Math.abs(changePercent);

  if (
    volumeStrength >= 80 ||
    absChange >= 5 ||
    buyRatio >= 75 ||
    sellRatio >= 75
  ) {
    return "🔥 نشاط مرتفع جدًا";
  }

  if (
    volumeStrength >= 60 ||
    absChange >= 2 ||
    buyRatio >= 65 ||
    sellRatio >= 65
  ) {
    return "🟠 نشاط مرتفع";
  }

  if (
    volumeStrength >= 40 ||
    absChange >= 0.5
  ) {
    return "🟡 نشاط متوسط";
  }

  return "⚪ نشاط منخفض";
}

// ============================================================
// 📈 الحركة اللحظية
// ============================================================

function analyzeMovement(
  close,
  ema7,
  ema14,
  vwap
) {

  const price =
    Number(close[close.length - 1]);

  if (
    !Number.isFinite(price) ||
    !Number.isFinite(ema7) ||
    !Number.isFinite(ema14) ||
    !Number.isFinite(vwap)
  ) {
    return {
      bullish: false,
      bearish: false,
      label: "⚪ حركة غير واضحة"
    };
  }

  if (
    price > ema7 &&
    ema7 > ema14 &&
    price > vwap
  ) {
    return {
      bullish: true,
      bearish: false,
      label: "⚡ 📈 صعود لحظي"
    };
  }

  if (
    price < ema7 &&
    ema7 < ema14 &&
    price < vwap
  ) {
    return {
      bullish: false,
      bearish: true,
      label: "⚡ 📉 هبوط لحظي"
    };
  }

  return {
    bullish: false,
    bearish: false,
    label: "⚪ حركة لحظية متوازنة"
  };
}

// ============================================================
// 📊 الاتجاه العام
// ============================================================

function analyzeGeneralTrend(
  price,
  ema50,
  ema180
) {

  if (
    Number.isFinite(ema50) &&
    Number.isFinite(ema180)
  ) {

    if (
      ema50 > ema180 &&
      price > ema50
    ) {
      return {
        bullish: true,
        bearish: false,
        label: "🟢 الاتجاه العام صاعد"
      };
    }

    if (
      ema50 < ema180 &&
      price < ema50
    ) {
      return {
        bullish: false,
        bearish: true,
        label: "🔴 الاتجاه العام هابط"
      };
    }
  }

  return {
    bullish: false,
    bearish: false,
    label: "⚪ الاتجاه العام متوازن"
  };
}

// ============================================================
// 📊 EMA Signal
// ============================================================

function analyzeEMA(
  ema7,
  ema14,
  ema25,
  ema50
) {

  if (
    ema7 > ema14 &&
    ema14 > ema25 &&
    ema25 > ema50
  ) {
    return "⚡ EMA سريع";
  }

  if (
    ema7 < ema14 &&
    ema14 < ema25 &&
    ema25 < ema50
  ) {
    return "🔻 EMA هابط";
  }

  return "⚪ EMA متوازن";
}

// ============================================================
// 🚀 نسبة الحركة خلال ساعة تقريبًا
// ============================================================

function calculateMovementPercent(close) {

  const len = close.length;

  if (len < 13) {
    return 0;
  }

  const oldPrice =
    Number(close[len - 13]);

  const currentPrice =
    Number(close[len - 1]);

  if (
    !Number.isFinite(oldPrice) ||
    !Number.isFinite(currentPrice) ||
    oldPrice === 0
  ) {
    return 0;
  }

  return (
    (currentPrice - oldPrice) /
    oldPrice
  ) * 100;
}

// ============================================================
// 🕐 الحركة
// ============================================================

function movementLabel(percent) {

  if (percent >= 2) {
    return "🚀 حركة صاعدة قوية";
  }

  if (percent >= 0.5) {
    return "📈 حركة صاعدة";
  }

  if (percent <= -2) {
    return "🔻 حركة هابطة قوية";
  }

  if (percent <= -0.5) {
    return "📉 حركة هابطة";
  }

  return "⚪ حركة مستقرة";
}

// ============================================================
// 🎯 الأهداف
// ============================================================

function calculateTargets(price) {

  const percentages = [
    2,
    4,
    6,
    8,
    10,
    12,
    15,
    18
  ];

  return percentages.map(p => ({
    percent: p,
    price:
      price * (1 + p / 100)
  }));
}

// ============================================================
// 💥 Explosion Score
// ============================================================

function calculateExplosionScore({
  changePercent,
  price,
  ema7,
  ema14,
  ema25,
  vwap,
  volumeStrength,
  buyRatio,
  generalBullish
}) {

  let score = 0;

  if (changePercent >= MIN_CHANGE) {
    score += 15;
  }

  if (price > ema7) {
    score += 10;
  }

  if (ema7 > ema14) {
    score += 10;
  }

  if (ema14 > ema25) {
    score += 10;
  }

  if (price > vwap) {
    score += 10;
  }

  if (volumeStrength >= 60) {
    score += 15;
  }

  if (buyRatio >= 65) {
    score += 15;
  }

  if (generalBullish) {
    score += 15;
  }

  return Math.min(100, score);
}

// ============================================================
// 🎯 الإشارة الرئيسية
// ============================================================

function generateSignal(data) {

  const {
    changePercent,
    price,
    ema7,
    ema14,
    ema25,
    vwap,
    volumeStrength,
    buyRatio,
    sellRatio,
    liquidity,
    movement,
    generalTrend
  } = data;

  const score =
    calculateExplosionScore({
      changePercent,
      price,
      ema7,
      ema14,
      ema25,
      vwap,
      volumeStrength,
      buyRatio,
      generalBullish:
        generalTrend.bullish
    });

  if (
    score >= 85 &&
    liquidity === "🟢 دخول سيولة قوية" &&
    generalTrend.bullish &&
    movement.bullish &&
    volumeStrength >= 60 &&
    price > vwap
  ) {
    return {
      score,
      signal:
        "📊 💀🚀 انفجار مؤكد"
    };
  }

  if (
    changePercent >= MIN_CHANGE &&
    movement.bullish &&
    price > vwap &&
    volumeStrength >= 50 &&
    buyRatio >= 55
  ) {
    return {
      score,
      signal:
        "📊 🔥 صعود مؤكد"
    };
  }

  if (
    movement.bullish &&
    price > vwap
  ) {
    return {
      score,
      signal:
        "📊 🟡 صعود غير مؤكد"
    };
  }

  if (
    movement.bearish ||
    (
      sellRatio >= 65 &&
      price < vwap
    )
  ) {
    return {
      score,
      signal:
        "📊 🔻 هبوط"
    };
  }

  return {
    score,
    signal:
      "📊 ⚪ صعود غير مؤكد"
  };
}

// ============================================================
// 🏭 معلومات الشركة: القطاع / الصناعة / الدولة
// ============================================================

async function getCompanyProfile(symbol) {

  const cached =
    profileCache.get(symbol);

  if (
    cached &&
    Date.now() - cached.time <
      PROFILE_CACHE_MS
  ) {
    return cached.data;
  }

  let result = {
    sector: "غير متوفر",
    industry: "غير متوفر",
    country: "غير متوفر",
    employees: null
  };

  try {

    const url =
      `https://query2.finance.yahoo.com/v10/finance/quoteSummary/` +
      `${encodeURIComponent(symbol)}` +
      `?modules=assetProfile`;

    const data =
      await yahooFetch(url);

    const profile =
      data?.quoteSummary?.result?.[0]?.assetProfile;

    if (profile) {

      result = {
        sector:
          profile.sector ||
          "غير متوفر",

        industry:
          profile.industry ||
          "غير متوفر",

        country:
          profile.country ||
          "غير متوفر",

        employees:
          profile.fullTimeEmployees ||
          null
      };
    }

  } catch (error) {

    console.log(
      `⚠️ Profile ${symbol}: ${error.message}`
    );
  }

  profileCache.set(symbol, {
    time: Date.now(),
    data: result
  });

  return result;
}

// ============================================================
// 📰 الأخبار
// ============================================================

function classifyNewsSentiment(title) {

  const text =
    String(title || "").toLowerCase();

  const positiveWords = [
    "surge",
    "soar",
    "rally",
    "gain",
    "gains",
    "rise",
    "rises",
    "up",
    "growth",
    "profit",
    "profits",
    "beat",
    "beats",
    "strong",
    "bullish",
    "upgrade",
    "upgraded",
    "approval",
    "approved",
    "partnership",
    "contract",
    "deal",
    "record",
    "positive",
    "breakthrough",
    "acquire",
    "acquisition"
  ];

  const negativeWords = [
    "fall",
    "falls",
    "drop",
    "drops",
    "down",
    "decline",
    "loss",
    "losses",
    "weak",
    "bearish",
    "downgrade",
    "downgraded",
    "warning",
    "lawsuit",
    "investigation",
    "fraud",
    "bankruptcy",
    "offering",
    "dilution",
    "layoff",
    "layoffs",
    "debt",
    "miss",
    "misses",
    "negative",
    "recall",
    "risk"
  ];

  let positive = 0;
  let negative = 0;

  for (const word of positiveWords) {

    if (text.includes(word)) {
      positive++;
    }
  }

  for (const word of negativeWords) {

    if (text.includes(word)) {
      negative++;
    }
  }

  if (positive > negative) {
    return "🟢 إيجابي";
  }

  if (negative > positive) {
    return "🔴 سلبي";
  }

  return "⚪ محايد";
}

// ============================================================
// 📰 جلب الأخبار
// ============================================================

async function getNews(symbol) {

  const cached =
    newsCache.get(symbol);

  if (
    cached &&
    Date.now() - cached.time <
      NEWS_CACHE_MS
  ) {
    return cached.data;
  }

  let news = [];

  try {

    const url =
      `https://query1.finance.yahoo.com/v1/finance/search` +
      `?q=${encodeURIComponent(symbol)}` +
      `&quotesCount=1` +
      `&newsCount=5` +
      `&enableFuzzyQuery=false`;

    const data =
      await yahooFetch(url);

    const rawNews =
      Array.isArray(data?.news)
        ? data.news
        : [];

    news =
      rawNews
        .slice(0, 5)
        .map(item => {

          const title =
            item.title ||
            "خبر بدون عنوان";

          return {
            title,
            publisher:
              item.publisher ||
              "Yahoo Finance",

            link:
              item.link ||
              null,

            time:
              item.providerPublishTime
                ? new Date(
                    item.providerPublishTime * 1000
                  )
                : null,

            sentiment:
              classifyNewsSentiment(title)
          };
        });

  } catch (error) {

    console.log(
      `⚠️ News ${symbol}: ${error.message}`
    );
  }

  newsCache.set(symbol, {
    time: Date.now(),
    data: news
  });

  return news;
}

// ============================================================
// 💰 تنسيق الأرقام
// ============================================================

function formatNumber(value) {

  if (
    value === null ||
    value === undefined ||
    !Number.isFinite(Number(value))
  ) {
    return "غير متوفر";
  }

  const n = Number(value);

  if (Math.abs(n) >= 1e12) {
    return `${(n / 1e12).toFixed(2)}T`;
  }

  if (Math.abs(n) >= 1e9) {
    return `${(n / 1e9).toFixed(2)}B`;
  }

  if (Math.abs(n) >= 1e6) {
    return `${(n / 1e6).toFixed(2)}M`;
  }

  if (Math.abs(n) >= 1e3) {
    return `${(n / 1e3).toFixed(2)}K`;
  }

  return n.toFixed(2);
}

function formatPrice(value) {

  if (!Number.isFinite(Number(value))) {
    return "0.00";
  }

  return Number(value).toFixed(
    Number(value) < 1 ? 4 : 2
  );
}

// ============================================================
// 📊 بيانات السهم كاملة
// ============================================================

async function getStockData(symbol) {

  // ----------------------------------------------------------
  // أول شيء: تحقق البورصة
  // ----------------------------------------------------------

  const exchangeData =
    await validateSymbolExchange(symbol);

  const meta =
    exchangeData.meta;

  // ----------------------------------------------------------
  // الشارت
  // ----------------------------------------------------------

  const chart =
    await getChart(
      symbol,
      "5d",
      "5m"
    );

  const timestamps =
    chart.timestamp || [];

  const quote =
    chart.indicators?.quote?.[0];

  if (!quote) {
    throw new Error("لا توجد بيانات الأسعار");
  }

  const open =
    quote.open || [];

  const high =
    quote.high || [];

  const low =
    quote.low || [];

  const close =
    quote.close || [];

  const volume =
    quote.volume || [];

  const cleanClose = [];
  const cleanHigh = [];
  const cleanLow = [];
  const cleanVolume = [];

  for (let i = 0; i < close.length; i++) {

    const c = Number(close[i]);

    if (!Number.isFinite(c)) {
      continue;
    }

    cleanClose.push(c);
    cleanHigh.push(
      Number.isFinite(Number(high[i]))
        ? Number(high[i])
        : c
    );

    cleanLow.push(
      Number.isFinite(Number(low[i]))
        ? Number(low[i])
        : c
    );

    cleanVolume.push(
      Number.isFinite(Number(volume[i]))
        ? Number(volume[i])
        : 0
    );
  }

  if (cleanClose.length < 20) {
    throw new Error("بيانات الشارت غير كافية");
  }

  const price =
    cleanClose[cleanClose.length - 1];

  if (
    !Number.isFinite(price) ||
    price < MIN_PRICE
  ) {
    throw new Error("السعر أقل من الحد المسموح");
  }

  // ----------------------------------------------------------
  // السعر السابق
  // ----------------------------------------------------------

  const previousClose =
    Number(meta.previousClose) ||
    Number(meta.chartPreviousClose) ||
    cleanClose[
      Math.max(0, cleanClose.length - 2)
    ];

  const changePercent =
    previousClose > 0
      ? ((price - previousClose) / previousClose) * 100
      : 0;

  // ----------------------------------------------------------
  // EMA
  // ----------------------------------------------------------

  const ema7 =
    calculateEMA(cleanClose, 7);

  const ema14 =
    calculateEMA(cleanClose, 14);

  const ema25 =
    calculateEMA(cleanClose, 25);

  const ema50 =
    calculateEMA(cleanClose, 50);

  const ema180 =
    calculateEMA(cleanClose, 180);

  // إذا البيانات أقل من 180 شمعة
  // نستخدم EMA50 بدل EMA180 فقط للتحليل
  const effectiveEMA180 =
    ema180 !== null
      ? ema180
      : ema50;

  // ----------------------------------------------------------
  // VWAP
  // ----------------------------------------------------------

  const vwap =
    calculateVWAP(
      cleanHigh,
      cleanLow,
      cleanClose,
      cleanVolume
    );

  if (!Number.isFinite(vwap)) {
    throw new Error("VWAP غير متوفر");
  }

  // ----------------------------------------------------------
  // الحجم
  // ----------------------------------------------------------

  const volumeStrength =
    calculateVolumeStrength(
      cleanVolume
    );

  // ----------------------------------------------------------
  // السيولة
  // ----------------------------------------------------------

  const liquidityData =
    analyzeLiquidity(
      cleanClose,
      cleanVolume
    );

  // ----------------------------------------------------------
  // التجميع
  // ----------------------------------------------------------

  const accumulation =
    analyzeAccumulation(
      liquidityData.buyRatio,
      liquidityData.sellRatio,
      price,
      vwap,
      volumeStrength
    );

  // ----------------------------------------------------------
  // الحركة
  // ----------------------------------------------------------

  const movementPercent =
    calculateMovementPercent(
      cleanClose
    );

  const movement =
    analyzeMovement(
      cleanClose,
      ema7,
      ema14,
      vwap
    );

  // ----------------------------------------------------------
  // الاتجاه العام
  // ----------------------------------------------------------

  const generalTrend =
    analyzeGeneralTrend(
      price,
      ema50,
      effectiveEMA180
    );

  // ----------------------------------------------------------
  // EMA
  // ----------------------------------------------------------

  const emaSignal =
    analyzeEMA(
      ema7,
      ema14,
      ema25,
      ema50
    );

  // ----------------------------------------------------------
  // النشاط
  // ----------------------------------------------------------

  const activity =
    analyzeActivity(
      changePercent,
      volumeStrength,
      liquidityData.buyRatio,
      liquidityData.sellRatio
    );

  // ----------------------------------------------------------
  // أقل سعر 4 ساعات تقريبًا
  // ----------------------------------------------------------

  const last48 =
    cleanLow.slice(
      Math.max(0, cleanLow.length - 48)
    );

  const low4H =
    last48.length
      ? Math.min(...last48)
      : null;

  const distanceFrom4HLow =
    low4H && low4H > 0
      ? ((price - low4H) / low4H) * 100
      : 0;

  // ----------------------------------------------------------
  // Score + Signal
  // ----------------------------------------------------------

  const signalData =
    generateSignal({
      changePercent,
      price,
      ema7,
      ema14,
      ema25,
      vwap,
      volumeStrength,
      buyRatio:
        liquidityData.buyRatio,
      sellRatio:
        liquidityData.sellRatio,
      liquidity:
        liquidityData.label,
      movement,
      generalTrend
    });

  // ----------------------------------------------------------
  // الأهداف
  // ----------------------------------------------------------

  const targets =
    calculateTargets(price);

  // ----------------------------------------------------------
  // الشركة
  // ----------------------------------------------------------

  const profile =
    await getCompanyProfile(symbol);

  // ----------------------------------------------------------
  // الأخبار
  // ----------------------------------------------------------

  const news =
    await getNews(symbol);

  return {

    symbol,

    price,

    previousClose,

    changePercent,

    exchange:
      exchangeData.exchange,

    exchangeName:
      meta.exchangeName || "",

    fullExchangeName:
      meta.fullExchangeName || "",

    instrumentType:
      meta.instrumentType || "",

    isUSListed: true,

    // الشركة
    companyName:
      meta.longName ||
      meta.shortName ||
      symbol,

    sector:
      profile.sector,

    industry:
      profile.industry,

    country:
      profile.country,

    employees:
      profile.employees,

    // المؤشرات
    ema7,
    ema14,
    ema25,
    ema50,
    ema180:
      effectiveEMA180,

    vwap,

    // السيولة
    volumeStrength,

    buyRatio:
      liquidityData.buyRatio,

    sellRatio:
      liquidityData.sellRatio,

    liquidity:
      liquidityData.label,

    accumulation,

    // النشاط
    activity,

    movementPercent,

    movementLabel:
      movementLabel(movementPercent),

    movement,

    // الاتجاه
    generalTrend,

    emaSignal,

    // 4H
    low4H,

    distanceFrom4HLow,

    // الإشارة
    score:
      signalData.score,

    signal:
      signalData.signal,

    // الأهداف
    targets,

    // الأخبار
    news,

    updatedAt:
      new Date()
  };
}

// ============================================================
// 📝 رسالة Telegram
// ============================================================

function buildStockMessage(data) {

  let message = "";

  message +=
    `🇺🇸 *السوق الأمريكي*\n\n`;

  message +=
    `📌 *${data.symbol}*\n`;

  message +=
    `🏢 ${data.companyName}\n\n`;

  // ----------------------------------------------------------
  // السعر
  // ----------------------------------------------------------

  message +=
    `💰 السعر: *${formatPrice(data.price)}*\n`;

  message +=
    `📈 التغير: *${data.changePercent.toFixed(2)}%*\n`;

  message +=
    `🏦 البورصة: *${data.exchange}*\n`;

  message +=
    `🏛️ ${data.fullExchangeName || data.exchangeName}\n\n`;

  // ----------------------------------------------------------
  // الشركة
  // ----------------------------------------------------------

  message +=
    `🏭 القطاع: *${data.sector}*\n`;

  message +=
    `🔧 الصناعة: *${data.industry}*\n`;

  message +=
    `🌎 الدولة: *${data.country}*\n\n`;

  // ----------------------------------------------------------
  // النشاط
  // ----------------------------------------------------------

  message +=
    `🔥 نشاط السهم: *${data.activity}*\n`;

  message +=
    `📊 حركة السهم: *${data.movementLabel}*\n`;

  message +=
    `⏱️ الحركة: *${data.movementPercent.toFixed(2)}%*\n\n`;

  // ----------------------------------------------------------
  // EMA
  // ----------------------------------------------------------

  message +=
    `📊 EMA: *${data.emaSignal}*\n`;

  message +=
    `EMA7: ${formatPrice(data.ema7)}\n`;

  message +=
    `EMA14: ${formatPrice(data.ema14)}\n`;

  message +=
    `EMA25: ${formatPrice(data.ema25)}\n`;

  message +=
    `EMA50: ${formatPrice(data.ema50)}\n`;

  message +=
    `EMA180: ${formatPrice(data.ema180)}\n\n`;

  // ----------------------------------------------------------
  // VWAP
  // ----------------------------------------------------------

  message +=
    `📐 VWAP: *${formatPrice(data.vwap)}*\n`;

  // ----------------------------------------------------------
  // السيولة
  // ----------------------------------------------------------

  message +=
    `💧 السيولة: *${data.liquidity}*\n`;

  message +=
    `🟢 شراء: ${data.buyRatio.toFixed(1)}%\n`;

  message +=
    `🔴 بيع: ${data.sellRatio.toFixed(1)}%\n`;

  message +=
    `📦 قوة الحجم: ${data.volumeStrength.toFixed(1)}%\n`;

  message +=
    `🧲 التجميع: *${data.accumulation}*\n\n`;

  // ----------------------------------------------------------
  // الاتجاه
  // ----------------------------------------------------------

  message +=
    `🧭 الاتجاه العام: *${data.generalTrend.label}*\n`;

  message +=
    `${data.movement.label}\n\n`;

  // ----------------------------------------------------------
  // 4H
  // ----------------------------------------------------------

  if (Number.isFinite(data.low4H)) {

    message +=
      `📉 قاع 4H: *${formatPrice(data.low4H)}*\n`;

    message +=
      `📍 البعد عن قاع 4H: *${data.distanceFrom4HLow.toFixed(2)}%*\n\n`;
  }

  // ----------------------------------------------------------
  // الإشارة
  // ----------------------------------------------------------

  message +=
    `🚨 *الإشارة: ${data.signal}*\n`;

  message +=
    `💥 قوة الإشارة: *${data.score}/100*\n\n`;

  // ----------------------------------------------------------
  // الأهداف
  // ----------------------------------------------------------

  message +=
    `🎯 *الأهداف:*\n`;

  for (const target of data.targets) {

    message +=
      `🎯 +${target.percent}% → *${formatPrice(target.price)}*\n`;
  }

  // ----------------------------------------------------------
  // الأخبار
  // ----------------------------------------------------------

  message +=
    `\n📰 *آخر الأخبار:*\n`;

  if (!data.news || data.news.length === 0) {

    message +=
      `⚪ لا توجد أخبار حديثة.\n`;

  } else {

    for (
      const news of data.news.slice(0, 3)
    ) {

      message +=
        `\n${news.sentiment}\n`;

      message +=
        `• ${news.title}\n`;

      if (news.publisher) {

        message +=
          `  🗞️ ${news.publisher}\n`;
      }
    }
  }

  // ----------------------------------------------------------
  // تحديث
  // ----------------------------------------------------------

  message +=
    `\n🕒 تحديث: ${data.updatedAt.toLocaleString("ar-SA")}`;

  return message;
}

// ============================================================
// 📡 جلب قائمة الأسهم
// ============================================================

async function getSymbols() {

  const screeners = [
    "day_gainers",
    "most_actives",
    "growth_technology_stocks"
  ];

  const symbolsMap = new Map();

  for (const screener of screeners) {

    try {

      const url =
        `https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved` +
        `?scrIds=${encodeURIComponent(screener)}` +
        `&count=${MAX_SYMBOLS}`;

      const data =
        await yahooFetch(url);

      const quotes =
        data?.finance?.result?.[0]?.quotes ||
        [];

      for (const item of quotes) {

        const symbol =
          String(item.symbol || "")
            .trim()
            .toUpperCase();

        const exchange =
          normalizeExchange(
            item.exchange
          );

        const quoteType =
          String(
            item.quoteType || ""
          ).toUpperCase();

        // ------------------------------------------------------
        // 🚫 أول فلتر OTC
        // ------------------------------------------------------

        if (!symbol) {
          continue;
        }

        if (
          !isAllowedExchangeCode(exchange)
        ) {
          continue;
        }

        if (
          quoteType &&
          quoteType !== "EQUITY"
        ) {
          continue;
        }

        // منع رموز غير أمريكية الواضحة
        if (
          symbol.includes(".") ||
          symbol.includes("=") ||
          symbol.includes("^")
        ) {
          continue;
        }

        // السعر
        const price =
          Number(
            item.regularMarketPrice
          );

        if (
          Number.isFinite(price) &&
          price < MIN_PRICE
        ) {
          continue;
        }

        symbolsMap.set(
          symbol,
          {
            symbol,
            exchange,
            quoteType
          }
        );
      }

    } catch (error) {

      console.log(
        `⚠️ Screener ${screener}: ${error.message}`
      );
    }

    await sleep(REQUEST_DELAY_MS);
  }

  return Array.from(
    symbolsMap.values()
  );
}

// ============================================================
// 🧹 حذف الإشارات غير المسموحة
// ============================================================

function purgeInvalidSignals() {

  for (
    const [symbol, data]
    of sentSignals.entries()
  ) {

    if (
      !data ||
      data.isUSListed !== true
    ) {
      sentSignals.delete(symbol);
      continue;
    }

    const exchangeText =
      `${data.exchange || ""} ` +
      `${data.exchangeName || ""} ` +
      `${data.fullExchangeName || ""}`;

    if (
      exchangeText
        .toUpperCase()
        .includes("OTC")
    ) {
      sentSignals.delete(symbol);
    }
  }
}

// ============================================================
// 🔎 فحص سهم
// ============================================================

async function safelyGetStock(symbol) {

  try {

    const data =
      await getStockData(symbol);

    if (
      !data.isUSListed
    ) {
      throw new Error(
        "غير مدرج في بورصة أمريكية مسموحة"
      );
    }

    return data;

  } catch (error) {

    if (
      error.code ===
      "BLOCKED_EXCHANGE" ||
      error.message.includes("OTC") ||
      error.message.includes("BLOCKED")
    ) {

      lastScanStats.blockedOTC++;

      console.log(
        `🚫 ${symbol} تم حظره: ${error.message}`
      );

    } else {

      lastScanStats.errors++;

      console.log(
        `⚠️ ${symbol}: ${error.message}`
      );
    }

    return null;
  }
}

// ============================================================
// 🔍 SCAN
// ============================================================

async function runScan(chatId = null) {

  if (scanRunning) {

    if (chatId) {

      await bot.sendMessage(
        chatId,
        "⏳ الفحص يعمل حاليًا، انتظر قليلًا."
      );
    }

    return;
  }

  scanRunning = true;

  lastScanStats = {
    candidates: 0,
    checked: 0,
    accepted: 0,
    blockedOTC: 0,
    errors: 0
  };

  try {

    purgeInvalidSignals();

    const symbols =
      await getSymbols();

    lastScanStats.candidates =
      symbols.length;

    const found = [];

    console.log(
      `🔎 Candidates: ${symbols.length}`
    );

    for (const item of symbols) {

      lastScanStats.checked++;

      const data =
        await safelyGetStock(
          item.symbol
        );

      if (!data) {
        await sleep(REQUEST_DELAY_MS);
        continue;
      }

      // --------------------------------------------------------
      // 🚫 الحماية النهائية
      // --------------------------------------------------------

      if (
        data.isUSListed !== true
      ) {
        continue;
      }

      // --------------------------------------------------------
      // لا نرسل الهبوط الضعيف
      // --------------------------------------------------------

      const interesting =
        data.score >= 60 ||
        data.signal.includes("انفجار") ||
        data.signal.includes("صعود مؤكد") ||
        (
          data.movement.bullish &&
          data.volumeStrength >= 40
        );

      if (!interesting) {
        await sleep(REQUEST_DELAY_MS);
        continue;
      }

      found.push(data);

      lastScanStats.accepted++;

      await sleep(REQUEST_DELAY_MS);
    }

    // ----------------------------------------------------------
    // ترتيب حسب قوة الإشارة
    // ----------------------------------------------------------

    found.sort(
      (a, b) =>
        b.score - a.score
    );

    // ----------------------------------------------------------
    // حفظ الإشارات
    // ----------------------------------------------------------

    for (const data of found) {

      sentSignals.set(
        data.symbol,
        data
      );
    }

    purgeInvalidSignals();

    lastScanTime =
      new Date();

    console.log(
      "━━━━━━━━━━━━━━━━━━━━━━"
    );

    console.log(
      "📊 SCAN FINISHED"
    );

    console.log(
      lastScanStats
    );

    // ----------------------------------------------------------
    // إرسال النتائج
    // ----------------------------------------------------------

    if (chatId) {

      if (found.length === 0) {

        await bot.sendMessage(
          chatId,
          `🇺🇸 *انتهى الفحص*\n\n` +
          `⚪ لا توجد إشارة قوية حاليًا.\n\n` +
          `🔎 تم فحص: ${lastScanStats.checked}\n` +
          `🚫 تم حظر OTC: ${lastScanStats.blockedOTC}\n` +
          `❌ أخطاء: ${lastScanStats.errors}`,
          {
            parse_mode: "Markdown"
          }
        );

      } else {

        const top =
          found.slice(0, 10);

        await bot.sendMessage(
          chatId,
          `🇺🇸 *نتائج الفحص*\n\n` +
          `🔎 تم فحص: ${lastScanStats.checked}\n` +
          `🚫 OTC محظور: ${lastScanStats.blockedOTC}\n` +
          `📈 إشارات: ${found.length}\n\n` +
          top
            .map(
              (x, i) =>
                `${i + 1}. *${x.symbol}* ` +
                `${x.signal}\n` +
                `💰 ${formatPrice(x.price)} | ` +
                `📊 ${x.changePercent.toFixed(2)}% | ` +
                `💥 ${x.score}/100`
            )
            .join("\n\n"),
          {
            parse_mode: "Markdown"
          }
        );
      }
    }

  } catch (error) {

    console.log(
      `❌ Scan error: ${error.message}`
    );

    if (chatId) {

      await bot.sendMessage(
        chatId,
        `❌ حدث خطأ أثناء الفحص:\n${error.message}`
      );
    }

  } finally {

    scanRunning = false;
  }
}

// ============================================================
// 🔄 تحديث الإشارات
// ============================================================

async function updateSignals() {

  if (sentSignals.size === 0) {
    return;
  }

  console.log(
    `🔄 Updating ${sentSignals.size} signals`
  );

  const symbols =
    Array.from(
      sentSignals.keys()
    );

  for (const symbol of symbols) {

    try {

      const data =
        await safelyGetStock(symbol);

      if (!data) {

        sentSignals.delete(symbol);

        continue;
      }

      // حماية OTC
      if (
        data.isUSListed !== true
      ) {

        sentSignals.delete(symbol);

        continue;
      }

      sentSignals.set(
        symbol,
        data
      );

    } catch (error) {

      console.log(
        `⚠️ Update ${symbol}: ${error.message}`
      );
    }

    await sleep(REQUEST_DELAY_MS);
  }

  purgeInvalidSignals();
}

// ============================================================
// /start
// ============================================================

bot.onText(
  /^\/start$/,
  async msg => {

    const chatId =
      msg.chat.id;

    await bot.sendMessage(
      chatId,
      `🇺🇸 *US STOCK SCANNER PRO MAX*\n\n` +
      `📊 مراقبة الأسهم الأمريكية\n` +
      `🚫 OTC محظور\n` +
      `🏦 NASDAQ / NYSE / NYSE American\n\n` +
      `الأوامر:\n\n` +
      `/scan - بدء فحص جديد\n` +
      `/stop - مسح الإشارات الحالية\n` +
      `/signals - عرض الإشارات الحالية\n` +
      `/status - حالة البوت\n` +
      `/help - المساعدة`,
      {
        parse_mode: "Markdown"
      }
    );
  }
);

// ============================================================
// /scan
// ============================================================

bot.onText(
  /^\/scan$/,
  async msg => {

    await runScan(
      msg.chat.id
    );
  }
);

// ============================================================
// /stop
// ============================================================

bot.onText(
  /^\/stop$/,
  async msg => {

    const chatId =
      msg.chat.id;

    sentSignals.clear();

    await bot.sendMessage(
      chatId,
      `🛑 *تم إيقاف الإشارات الحالية.*\n\n` +
      `🧹 تم مسح قائمة الأسهم المراقبة.\n\n` +
      `لتشغيل فحص جديد أرسل:\n` +
      `/scan`,
      {
        parse_mode: "Markdown"
      }
    );
  }
);

// ============================================================
// /signals
// ============================================================

bot.onText(
  /^\/signals$/,
  async msg => {

    const chatId =
      msg.chat.id;

    purgeInvalidSignals();

    if (sentSignals.size === 0) {

      await bot.sendMessage(
        chatId,
        "📭 لا توجد إشارات محفوظة حاليًا.\n\nأرسل /scan"
      );

      return;
    }

    const list =
      Array.from(
        sentSignals.values()
      )
      .sort(
        (a, b) =>
          b.score - a.score
      )
      .slice(0, 20);

    let text =
      "🇺🇸 *الإشارات الحالية*\n\n";

    for (const data of list) {

      text +=
        `*${data.symbol}* ` +
        `${data.signal}\n`;

      text +=
        `💰 ${formatPrice(data.price)}\n`;

      text +=
        `🏦 ${data.fullExchangeName || data.exchange}\n`;

      text +=
        `🔥 ${data.activity}\n`;

      text +=
        `💥 ${data.score}/100\n\n`;
    }

    await bot.sendMessage(
      chatId,
      text,
      {
        parse_mode: "Markdown"
      }
    );
  }
);

// ============================================================
// /status
// ============================================================

bot.onText(
  /^\/status$/,
  async msg => {

    const chatId =
      msg.chat.id;

    purgeInvalidSignals();

    await bot.sendMessage(
      chatId,
      `🤖 *حالة البوت*\n\n` +
      `🟢 البوت يعمل\n` +
      `🔎 آخر فحص: ${
        lastScanTime
          ? lastScanTime.toLocaleString("ar-SA")
          : "لم يبدأ بعد"
      }\n` +
      `📊 إشارات محفوظة: ${sentSignals.size}\n` +
      `🚫 OTC محظور\n` +
      `🏦 NASDAQ / NYSE / NYSE American\n\n` +
      `آخر فحص:\n` +
      `🔎 مرشحون: ${lastScanStats.candidates}\n` +
      `📊 تم فحصهم: ${lastScanStats.checked}\n` +
      `🟢 مقبول: ${lastScanStats.accepted}\n` +
      `🚫 OTC محظور: ${lastScanStats.blockedOTC}\n` +
      `❌ أخطاء: ${lastScanStats.errors}`,
      {
        parse_mode: "Markdown"
      }
    );
  }
);

// ============================================================
// /help
// ============================================================

bot.onText(
  /^\/help$/,
  async msg => {

    await bot.sendMessage(
      msg.chat.id,
      `🇺🇸 *مساعدة البوت*\n\n` +
      `/scan\n` +
      `🔎 فحص الأسهم الأمريكية\n\n` +
      `/stop\n` +
      `🛑 مسح الإشارات الحالية\n\n` +
      `/signals\n` +
      `📊 عرض الإشارات الحالية\n\n` +
      `/status\n` +
      `🤖 حالة البوت\n\n` +
      `🚫 OTC يتم رفضه قبل إرسال السهم.\n` +
      `🏦 المسموح: NASDAQ / NYSE / NYSE American\n` +
      `🏭 القطاع والصناعة والدولة\n` +
      `📰 الأخبار + إيجابي/سلبي/محايد`,
      {
        parse_mode: "Markdown"
      }
    );
  }
);

// ============================================================
// 🔄 تحديث تلقائي للإشارات
// ============================================================

setInterval(
  async () => {

    try {
      await updateSignals();
    } catch (error) {

      console.log(
        `❌ Update loop: ${error.message}`
      );
    }

  },
  UPDATE_INTERVAL_SEC * 1000
);

// ============================================================
// 🔎 فحص تلقائي
// ============================================================

setInterval(
  async () => {

    try {

      await runScan();

    } catch (error) {

      console.log(
        `❌ Auto scan: ${error.message}`
      );
    }

  },
  SCAN_INTERVAL_MIN * 60 * 1000
);

// ============================================================
// 🟢 بدء التشغيل
// ============================================================

console.log(
  "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
);

console.log(
  "🇺🇸 US STOCK SCANNER PRO MAX"
);

console.log(
  "🟢 Bot started"
);

console.log(
  "🚫 OTC BLOCK ENABLED"
);

console.log(
  "🏦 NASDAQ / NYSE / NYSE AMERICAN ONLY"
);

console.log(
  "🏭 Industry + Country + Activity"
);

console.log(
  "📰 News Sentiment Enabled"
);

console.log(
  "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
);