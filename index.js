
// ============================================================
// 🧠 AI PRO MAX — DUAL AUTONOMOUS STOCK SCANNER
// 🇸🇦 TASI + 🇺🇸 US STOCKS
// EODHD API | Node.js 18+ | Telegram
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// 🔐 CONFIGURATION — RAILWAY VARIABLES
// ============================================================

const TASI_TOKEN = process.env.TASI_TOKEN || "";
const US_TOKEN = process.env.US_TOKEN || "";
const EODHD_API_KEY = process.env.EODHD_API_KEY || "";

if (!TASI_TOKEN || !US_TOKEN || !EODHD_API_KEY) {
  throw new Error(
    "❌ Missing TASI_TOKEN / US_TOKEN / EODHD_API_KEY in Railway Variables."
  );
}

// ============================================================
// ⚙️ GENERAL CONFIGURATION
// ============================================================

const PORT = Number(process.env.PORT || 3000);

const MIN_PRICE_US = 0.20;

// الفحص التلقائي كل دقيقتين
const UPDATE_INTERVAL_MIN = 2;

// عدد الطلبات المتوازية
// لا ترفعها كثيرًا حتى لا تضغط API
const SCAN_CONCURRENCY = 12;

// تأخير بسيط بين دفعات الفحص
const REQUEST_DELAY_MS = 150;

// البيانات التاريخية
const HISTORY_LIMIT = 200;

// ATR
const ATR_PERIOD = 14;

// دعم / مقاومة
const SR_LOOKBACK = 60;
const PIVOT_LEFT = 2;
const PIVOT_RIGHT = 2;

// الأهداف
const TARGET_MULTIPLIERS = [
  0.75,
  1.25,
  1.75,
  2.50,
  3.25,
  4.00,
  5.00,
  6.00
];

// الأخبار
const NEWS_ENABLED = true;
const NEWS_GENERAL_LIMIT = 100;
const NEWS_PER_STOCK = false;

// ترجمة الأخبار للعربية
const NEWS_TRANSLATION_ENABLED = true;

// الحد الذي عنده نعتبر السهم مهمًا للأخبار الخاصة
const NEWS_SIGNAL_CHANGE = 3.0;

// ============================================================
// 🤖 CREATE BOTS
// ============================================================

const tasiBot = new TelegramBot(TASI_TOKEN, {
  polling: true
});

const usBot = new TelegramBot(US_TOKEN, {
  polling: true
});

// ============================================================
// 👥 SUBSCRIBERS
// ============================================================

const tasiSubscribers = new Set();
const usSubscribers = new Set();

// ============================================================
// 🔒 SCAN LOCKS
// ============================================================

let tasiScanRunning = false;
let usScanRunning = false;

// ============================================================
// 🌐 EXPRESS SERVER
// ============================================================

const app = express();

app.get("/", (req, res) => {
  res.status(200).send(
    "🧠 AI PRO MAX TASI & US Stock Scanner is running"
  );
});

app.get("/health", (req, res) => {
  res.json({
    ok: true,
    tasiSubscribers: tasiSubscribers.size,
    usSubscribers: usSubscribers.size,
    tasiScanRunning,
    usScanRunning,
    time: new Date().toISOString()
  });
});

app.listen(PORT, () => {
  console.log(`🌐 Server running on port ${PORT}`);
});

// ============================================================
// 🧰 UTILITIES
// ============================================================

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function safeNumber(value, fallback = null) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function roundPrice(value) {
  if (!Number.isFinite(value)) return 0;

  if (value >= 100) return Number(value.toFixed(2));
  if (value >= 10) return Number(value.toFixed(2));
  if (value >= 1) return Number(value.toFixed(3));

  return Number(value.toFixed(4));
}

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function normalizeUSSymbol(symbol) {
  return String(symbol || "")
    .trim()
    .replace(/\./g, "-")
    .toUpperCase();
}

function normalizeTicker(symbol, exchange) {
  const clean = String(symbol || "").trim();

  if (exchange === "US") {
    return `${normalizeUSSymbol(clean)}.US`;
  }

  return `${clean}.SR`;
}

// ============================================================
// 🌐 EODHD FETCH
// ============================================================

async function fetchEodhd(url) {
  const response = await fetch(url, {
    headers: {
      "User-Agent": "AI-Promax-Stock-Scanner/1.0"
    }
  });

  const text = await response.text();

  if (!response.ok) {
    throw new Error(
      `EODHD HTTP ${response.status}: ${text.slice(0, 200)}`
    );
  }

  let data;

  try {
    data = JSON.parse(text);
  } catch {
    throw new Error("EODHD returned invalid JSON");
  }

  if (
    data &&
    typeof data === "object" &&
    !Array.isArray(data) &&
    data.error
  ) {
    throw new Error(String(data.error));
  }

  return data;
}

// ============================================================
// 📋 LOAD EXCHANGE SYMBOLS
// ============================================================

async function getExchangeSymbols(exchange) {
  let url =
    `https://eodhistoricaldata.com/api/exchange-symbol-list/` +
    `${exchange}?api_token=${EODHD_API_KEY}&fmt=json`;

  const data = await fetchEodhd(url);

  if (!Array.isArray(data)) {
    throw new Error(
      `Invalid symbol list returned for ${exchange}`
    );
  }

  const symbols = [];

  for (const item of data) {
    const code =
      item.Code ||
      item.code ||
      item.Symbol ||
      item.symbol;

    if (!code) continue;

    const type = String(
      item.Type ||
      item.type ||
      ""
    ).toLowerCase();

    // الأمريكي:
    // نركز على الأسهم العادية ونستبعد الأدوات غير المطلوبة
    if (
      exchange === "US" &&
      type &&
      ![
        "common_stock",
        "stock",
        "common stock"
      ].includes(type)
    ) {
      continue;
    }

    symbols.push({
      symbol: String(code).trim(),
      name:
        item.Name ||
        item.name ||
        String(code).trim(),
      exchange:
        item.Exchange ||
        item.exchange ||
        exchange,
      type
    });
  }

  const unique = new Map();

  for (const item of symbols) {
    const key =
      exchange === "US"
        ? normalizeUSSymbol(item.symbol)
        : item.symbol;

    if (!unique.has(key)) {
      unique.set(key, item);
    }
  }

  return Array.from(unique.values());
}

// ============================================================
// 📊 FALLBACK SYMBOLS
// تستخدم فقط إذا تعذر جلب قائمة EODHD
// ============================================================

const TASI_FALLBACK_SYMBOLS = [
  "1010","1020","1030","1040","1050","1060","1080","1090",
  "1111","1120","1140","1150","1180","1201","1202","1210",
  "1211","1212","1301","1302","1303","1304","1320","1810",
  "1820","1830","2001","2002","2010","2020","2021","2030",
  "2040","2050","2060","2070","2080","2090","2100","2110",
  "2120","2130","2140","2150","2160","2170","2180","2190",
  "2200","2210","2220","2222","2230","2240","2250","2270",
  "2280","2282","2290","2300","2310","2320","2330","2340",
  "2350","2360","2370","2380","2381","2382","3001","3002",
  "3003","3004","3005","3007","3008","3010","3020","3030",
  "3040","3050","4001","4002","4003","4004","4005","4006",
  "4007","4008","4009","4010","4020","4030","4031","4040",
  "4050","4051","4061","4071","4081","4082","4090","4100",
  "4110","4130","4140","4150","4160","4161","4162","4163",
  "4164","4180","4190","4191","4192","4193","4200","4210",
  "4220","4230","4240","4250","4260","4270","4280","4290",
  "4300","4310","4320","4321","4322","4323","4330","4331",
  "4332","4333","4334","4335","4336","4337","4338","4339",
  "4340","6001","6002","6004","6010","6020","6040","6060",
  "7010","7020","7030","7040","7200","8010","8012","8020",
  "8030","8040","8050","8060","8070","8080","8090","8100",
  "8110","8120","8130","8140","8150","8160","8170","8180",
  "8190","8200","8210","8230","8240","8250","8260","8270",
  "8280","8300","8310","8311","9510","9520","9530","9540",
  "9550","9560","9570","9580","9590"
];

const US_FALLBACK_SYMBOLS = [
  "AAPL","MSFT","GOOGL","AMZN","NVDA",
  "TSLA","META","NFLX","AMD","INTC",
  "PLTR","SNDK","RIVN","NIO","PLUG",
  "SOFI","BAC","F","VALE","T"
];

// ============================================================
// 📐 ATR CALCULATION
// ============================================================

function calculateATR(highs, lows, closes, period = 14) {
  const len = Math.min(
    highs.length,
    lows.length,
    closes.length
  );

  if (len < period + 1) return null;

  const trs = [];

  for (let i = 1; i < len; i++) {
    const high = safeNumber(highs[i]);
    const low = safeNumber(lows[i]);
    const previousClose = safeNumber(closes[i - 1]);

    if (
      high === null ||
      low === null ||
      previousClose === null
    ) {
      continue;
    }

    const tr = Math.max(
      high - low,
      Math.abs(high - previousClose),
      Math.abs(low - previousClose)
    );

    if (Number.isFinite(tr)) {
      trs.push(tr);
    }
  }

  if (trs.length < period) return null;

  // Wilder-style ATR
  let atr =
    trs
      .slice(0, period)
      .reduce((sum, value) => sum + value, 0) /
    period;

  for (let i = period; i < trs.length; i++) {
    atr =
      ((atr * (period - 1)) + trs[i]) /
      period;
  }

  return atr > 0 ? atr : null;
}

// ============================================================
// 🧠 AI PRO MAX TREND ENGINE
// بدون EMA
// ============================================================

function analyzeAITrend(closes, highs, lows, volumes, atr) {
  const len = Math.min(
    closes.length,
    highs.length,
    lows.length
  );

  if (len < 30) {
    return {
      direction: "neutral",
      label: "⚪ الاتجاه غير مؤكد",
      score: 50
    };
  }

  const close = closes.map(Number);
  const high = highs.map(Number);
  const low = lows.map(Number);

  const current = close[len - 1];
  const previous5 = close[len - 6];
  const previous20 = close[len - 21];

  if (
    !Number.isFinite(current) ||
    !Number.isFinite(previous5) ||
    !Number.isFinite(previous20)
  ) {
    return {
      direction: "neutral",
      label: "⚪ الاتجاه غير مؤكد",
      score: 50
    };
  }

  let bullish = 0;
  let bearish = 0;

  // 1 — زخم 5 أيام
  const momentum5 =
    ((current - previous5) / previous5) * 100;

  if (momentum5 > 1) bullish += 2;
  if (momentum5 > 3) bullish += 2;

  if (momentum5 < -1) bearish += 2;
  if (momentum5 < -3) bearish += 2;

  // 2 — زخم 20 يوم
  const momentum20 =
    ((current - previous20) / previous20) * 100;

  if (momentum20 > 2) bullish += 3;
  if (momentum20 > 5) bullish += 2;

  if (momentum20 < -2) bearish += 3;
  if (momentum20 < -5) bearish += 2;

  // 3 — هيكل القمم والقيعان
  const firstHalfHigh =
    Math.max(...high.slice(-30, -15));

  const secondHalfHigh =
    Math.max(...high.slice(-15));

  const firstHalfLow =
    Math.min(...low.slice(-30, -15));

  const secondHalfLow =
    Math.min(...low.slice(-15));

  if (secondHalfHigh > firstHalfHigh) bullish += 2;
  if (secondHalfLow > firstHalfLow) bullish += 2;

  if (secondHalfHigh < firstHalfHigh) bearish += 2;
  if (secondHalfLow < firstHalfLow) bearish += 2;

  // 4 — آخر 5 شموع
  const last5 = close.slice(-5);

  let rising = 0;
  let falling = 0;

  for (let i = 1; i < last5.length; i++) {
    if (last5[i] > last5[i - 1]) rising++;
    if (last5[i] < last5[i - 1]) falling++;
  }

  if (rising >= 3) bullish += 2;
  if (falling >= 3) bearish += 2;

  // 5 — ATR momentum
  if (Number.isFinite(atr) && atr > 0) {
    const move = Math.abs(current - previous20);

    if (move >= atr * 2) {
      if (current > previous20) bullish += 2;
      if (current < previous20) bearish += 2;
    }
  }

  // 6 — حجم التداول
  if (Array.isArray(volumes) && volumes.length >= 20) {
    const v = volumes.map(Number);

    const recentVolume =
      v.slice(-5)
        .filter(Number.isFinite)
        .reduce((a, b) => a + b, 0) / 5;

    const averageVolume =
      v.slice(-20)
        .filter(Number.isFinite)
        .reduce((a, b) => a + b, 0) /
      Math.max(
        1,
        v.slice(-20).filter(Number.isFinite).length
      );

    if (
      Number.isFinite(recentVolume) &&
      Number.isFinite(averageVolume) &&
      averageVolume > 0
    ) {
      if (recentVolume > averageVolume * 1.5) {
        if (current > previous5) bullish += 2;
        if (current < previous5) bearish += 2;
      }
    }
  }

  const total = bullish + bearish;

  if (total <= 0) {
    return {
      direction: "neutral",
      label: "⚪ الاتجاه متوازن",
      score: 50
    };
  }

  const bullScore =
    (bullish / total) * 100;

  const bearScore =
    (bearish / total) * 100;

  if (
    bullish >= bearish + 2 &&
    bullScore >= 60
  ) {
    return {
      direction: "up",
      label: "🟢 الاتجاه صاعد",
      score: Math.round(bullScore)
    };
  }

  if (
    bearish >= bullish + 2 &&
    bearScore >= 60
  ) {
    return {
      direction: "down",
      label: "🔴 الاتجاه هابط",
      score: Math.round(bearScore)
    };
  }

  return {
    direction: "neutral",
    label: "⚪ الاتجاه متوازن",
    score: 50
  };
}

// ============================================================
// 📍 SUPPORT / RESISTANCE ENGINE
// ============================================================

function calculateSupportResistance(
  highs,
  lows,
  closes
) {
  const len = Math.min(
    highs.length,
    lows.length,
    closes.length
  );

  if (len < 30) {
    return {
      support: null,
      resistance: null
    };
  }

  const start =
    Math.max(0, len - SR_LOOKBACK);

  const H = highs.slice(start).map(Number);
  const L = lows.slice(start).map(Number);
  const C = closes.slice(start).map(Number);

  const price = C[C.length - 1];

  const pivotHighs = [];
  const pivotLows = [];

  for (
    let i = PIVOT_LEFT;
    i < H.length - PIVOT_RIGHT;
    i++
  ) {
    let isHigh = true;

    for (
      let j = 1;
      j <= PIVOT_LEFT;
      j++
    ) {
      if (H[i] <= H[i - j]) {
        isHigh = false;
        break;
      }
    }

    if (isHigh) {
      for (
        let j = 1;
        j <= PIVOT_RIGHT;
        j++
      ) {
        if (H[i] <= H[i + j]) {
          isHigh = false;
          break;
        }
      }
    }

    if (isHigh) {
      pivotHighs.push(H[i]);
    }
  }

  for (
    let i = PIVOT_LEFT;
    i < L.length - PIVOT_RIGHT;
    i++
  ) {
    let isLow = true;

    for (
      let j = 1;
      j <= PIVOT_LEFT;
      j++
    ) {
      if (L[i] >= L[i - j]) {
        isLow = false;
        break;
      }
    }

    if (isLow) {
      for (
        let j = 1;
        j <= PIVOT_RIGHT;
        j++
      ) {
        if (L[i] >= L[i + j]) {
          isLow = false;
          break;
        }
      }
    }

    if (isLow) {
      pivotLows.push(L[i]);
    }
  }

  const supports = pivotLows
    .filter(v => Number.isFinite(v) && v < price)
    .sort((a, b) => b - a);

  const resistances = pivotHighs
    .filter(v => Number.isFinite(v) && v > price)
    .sort((a, b) => a - b);

  const support =
    supports.length
      ? supports[0]
      : Math.min(...L.filter(Number.isFinite));

  const resistance =
    resistances.length
      ? resistances[0]
      : Math.max(...H.filter(Number.isFinite));

  return {
    support:
      Number.isFinite(support)
        ? support
        : null,

    resistance:
      Number.isFinite(resistance)
        ? resistance
        : null
  };
}

// ============================================================
// 🎯 AI PRO MAX TARGET ENGINE
// ============================================================

function calculateAIPromaxTargets(
  price,
  atr,
  directionData,
  levels,
  latestHigh,
  latestLow
) {
  if (
    !Number.isFinite(price) ||
    price <= 0
  ) {
    return [];
  }

  const safeATR =
    Number.isFinite(atr) && atr > 0
      ? atr
      : price * 0.02;

  const direction =
    directionData?.direction || "neutral";

  const targets = [];

  for (
    let i = 0;
    i < TARGET_MULTIPLIERS.length;
    i++
  ) {
    const multiplier =
      TARGET_MULTIPLIERS[i];

    let targetPrice;

    // ========================================================
    // 🟢 UP
    // ========================================================

    if (direction === "up") {
      targetPrice =
        price + safeATR * multiplier;

      // المقاومة القريبة تحسن الهدف الأول
      if (
        i === 0 &&
        Number.isFinite(levels?.resistance) &&
        levels.resistance > price
      ) {
        const distance =
          levels.resistance - price;

        if (
          distance >= safeATR * 0.50 &&
          distance <= safeATR * 1.50
        ) {
          targetPrice =
            levels.resistance;
        }
      }
    }

    // ========================================================
    // 🔴 DOWN
    // ========================================================

    else if (direction === "down") {
      targetPrice =
        price - safeATR * multiplier;

      // الدعم القريب يحسن الهدف الأول
      if (
        i === 0 &&
        Number.isFinite(levels?.support) &&
        levels.support < price
      ) {
        const distance =
          price - levels.support;

        if (
          distance >= safeATR * 0.50 &&
          distance <= safeATR * 1.50
        ) {
          targetPrice =
            levels.support;
        }
      }
    }

    // ========================================================
    // ⚪ NEUTRAL
    // ========================================================

    else {
      targetPrice =
        i % 2 === 0
          ? price + safeATR * multiplier
          : price - safeATR * multiplier;
    }

    if (
      !Number.isFinite(targetPrice) ||
      targetPrice <= 0
    ) {
      continue;
    }

    // ========================================================
    // ✅ TARGET ACHIEVEMENT
    // ========================================================

    let achieved = false;

    if (direction === "up") {
      achieved =
        Number.isFinite(latestHigh) &&
        latestHigh >= targetPrice;
    }

    if (direction === "down") {
      achieved =
        Number.isFinite(latestLow) &&
        latestLow <= targetPrice;
    }

    const distancePercent =
      price > 0
        ? Math.abs(
            ((targetPrice - price) / price) * 100
          )
        : 0;

    targets.push({
      number: i + 1,
      price: roundPrice(targetPrice),
      atrMultiplier: multiplier,
      direction,
      achieved,
      distancePercent
    });
  }

  return targets;
}

// ============================================================
// 💧 LIQUIDITY ENGINE
// ============================================================

function analyzeLiquidity(closes, volumes) {
  const len = Math.min(
    closes.length,
    volumes.length
  );

  const start =
    Math.max(1, len - 10);

  let buyVol = 0;
  let sellVol = 0;
  let neutralVol = 0;

  for (let i = start; i < len; i++) {
    const prev =
      safeNumber(closes[i - 1]);

    const current =
      safeNumber(closes[i]);

    const volume =
      safeNumber(volumes[i], 0);

    if (
      prev === null ||
      current === null
    ) {
      continue;
    }

    if (current > prev) {
      buyVol += volume;
    } else if (current < prev) {
      sellVol += volume;
    } else {
      neutralVol += volume;
    }
  }

  const total =
    buyVol +
    sellVol +
    neutralVol;

  if (total <= 0) {
    return {
      buyRatio: 50,
      sellRatio: 50,
      label: "⚪ سيولة متوازنة"
    };
  }

  const buyRatio =
    (buyVol / total) * 100;

  const sellRatio =
    (sellVol / total) * 100;

  let label =
    "⚪ سيولة متوازنة";

  if (buyRatio >= 65) {
    label =
      "🟢 دخول سيولة قوية";
  } else if (sellRatio >= 65) {
    label =
      "🔴 خروج سيولة قوية";
  } else if (buyRatio >= 53) {
    label =
      "🟢 دخول سيولة";
  } else if (sellRatio >= 53) {
    label =
      "🔴 خروج سيولة";
  }

  return {
    buyRatio,
    sellRatio,
    label
  };
}

// ============================================================
// 📐 VWAP
// ============================================================

function calculateVWAP(
  high,
  low,
  close,
  volume
) {
  const len = Math.min(
    high.length,
    low.length,
    close.length,
    volume.length
  );

  const start =
    Math.max(0, len - 30);

  let pv = 0;
  let totalVolume = 0;

  for (let i = start; i < len; i++) {
    const h = safeNumber(high[i]);
    const l = safeNumber(low[i]);
    const c = safeNumber(close[i]);
    const v = safeNumber(volume[i], 0);

    if (
      h === null ||
      l === null ||
      c === null ||
      v <= 0
    ) {
      continue;
    }

    pv +=
      ((h + l + c) / 3) * v;

    totalVolume += v;
  }

  return totalVolume > 0
    ? pv / totalVolume
    : null;
}

// ============================================================
// 📊 GET STOCK DATA
// ============================================================

async function getStockDataFromEodhd(
  symbolInfo,
  exchange,
  minPriceAllowed
) {
  const symbol =
    typeof symbolInfo === "string"
      ? symbolInfo
      : symbolInfo.symbol;

  const companyName =
    typeof symbolInfo === "string"
      ? symbolInfo
      : symbolInfo.name || symbol;

  const ticker =
    normalizeTicker(symbol, exchange);

  const url =
    `https://eodhistoricaldata.com/api/eod/` +
    `${ticker}` +
    `?api_token=${EODHD_API_KEY}` +
    `&fmt=json` +
    `&period=d` +
    `&order=a` +
    `&limit=${HISTORY_LIMIT}`;

  const data =
    await fetchEodhd(url);

  if (
    !Array.isArray(data) ||
    data.length < 30
  ) {
    throw new Error(
      `${ticker}: insufficient historical data`
    );
  }

  const rows = data.filter(row =>
    Number.isFinite(Number(row.close))
  );

  if (rows.length < 30) {
    throw new Error(
      `${ticker}: insufficient valid rows`
    );
  }

  const closes =
    rows.map(row => Number(row.close));

  const highs =
    rows.map(row => Number(row.high));

  const lows =
    rows.map(row => Number(row.low));

  const volumes =
    rows.map(row =>
      Number(row.volume) || 0
    );

  const price =
    closes[closes.length - 1];

  if (
    !Number.isFinite(price) ||
    price < minPriceAllowed
  ) {
    throw new Error(
      `${ticker}: below minimum price`
    );
  }

  const previousClose =
    closes[closes.length - 2] || price;

  const changePercent =
    previousClose > 0
      ? ((price - previousClose) /
          previousClose) * 100
      : 0;

  const atr =
    calculateATR(
      highs,
      lows,
      closes,
      ATR_PERIOD
    );

  const direction =
    analyzeAITrend(
      closes,
      highs,
      lows,
      volumes,
      atr
    );

  const supportResistance =
    calculateSupportResistance(
      highs,
      lows,
      closes
    );

  const latestHigh =
    highs[highs.length - 1];

  const latestLow =
    lows[lows.length - 1];

  const targets =
    calculateAIPromaxTargets(
      price,
      atr,
      direction,
      supportResistance,
      latestHigh,
      latestLow
    );

  const vwap =
    calculateVWAP(
      highs,
      lows,
      closes,
      volumes
    ) || price;

  const liquidity =
    analyzeLiquidity(
      closes,
      volumes
    );

  return {
    symbol,
    ticker,
    companyName,

    price,
    previousClose,
    changePercent,

    exchange:
      exchange === "SR"
        ? "تداول (TADAWUL)"
        : "NASDAQ / NYSE / US",

    atr,

    marketDirection:
      direction,

    supportResistance,

    latestHigh,
    latestLow,

    vwap,

    buyRatio:
      liquidity.buyRatio,

    sellRatio:
      liquidity.sellRatio,

    liquidityLabel:
      liquidity.label,

    targets,

    updatedAt:
      new Date()
  };
}

// ============================================================
// 📰 NEWS CACHE
// ============================================================

let generalNewsCache = [];
let generalNewsCacheTime = 0;

const NEWS_CACHE_MS =
  5 * 60 * 1000;

// ============================================================
// 📰 GET GENERAL NEWS
// ============================================================

async function getGeneralNews() {
  if (!NEWS_ENABLED) {
    return [];
  }

  const now =
    Date.now();

  if (
    generalNewsCache.length > 0 &&
    now - generalNewsCacheTime <
      NEWS_CACHE_MS
  ) {
    return generalNewsCache;
  }

  try {
    const url =
      `https://eodhistoricaldata.com/api/news` +
      `?api_token=${EODHD_API_KEY}` +
      `&limit=${NEWS_GENERAL_LIMIT}`;

    const data =
      await fetchEodhd(url);

    if (!Array.isArray(data)) {
      return [];
    }

    generalNewsCache =
      data.filter(item =>
        item &&
        item.title
      );

    generalNewsCacheTime =
      now;

    return generalNewsCache;
  } catch (error) {
    console.error(
      "❌ News error:",
      error.message
    );

    return [];
  }
}

// ============================================================
// 📰 FIND NEWS FOR STOCK
// ============================================================

function findNewsForStock(
  stock,
  news
) {
  if (
    !NEWS_ENABLED ||
    !Array.isArray(news)
  ) {
    return null;
  }

  const target =
    stock.ticker.toUpperCase();

  const symbol =
    stock.symbol.toUpperCase();

  const matches =
    news.filter(article => {
      if (
        !Array.isArray(article.symbols)
      ) {
        return false;
      }

      return article.symbols.some(s => {
        const value =
          String(s).toUpperCase();

        return (
          value === target ||
          value === symbol ||
          value.includes(symbol)
        );
      });
    });

  if (!matches.length) {
    return null;
  }

  matches.sort(
    (a, b) =>
      new Date(b.date) -
      new Date(a.date)
  );

  return matches[0];
}

// ============================================================
// 🌐 SOURCE NAME
// ============================================================

function getArabicSource(link) {
  try {
    const host =
      new URL(link).hostname
        .replace(/^www\./, "")
        .toLowerCase();

    const sources = {
      "finance.yahoo.com": "ياهو فاينانس",
      "yahoo.com": "ياهو فاينانس",
      "investing.com": "إنفستنج",
      "reuters.com": "رويترز",
      "benzinga.com": "بنزينجا",
      "marketwatch.com": "ماركت ووتش",
      "seekingalpha.com": "سيكينج ألفا",
      "nasdaq.com": "ناسداك",
      "prnewswire.com": "PR Newswire",
      "globenewswire.com": "GlobeNewswire",
      "businesswire.com": "Business Wire",
      "fool.com": "Motley Fool"
    };

    return (
      sources[host] ||
      host
    );
  } catch {
    return "مصدر الخبر";
  }
}

// ============================================================
// 🇸🇦 TRANSLATE NEWS TITLE
// ============================================================

const translationCache =
  new Map();

async function translateToArabic(text) {
  const clean =
    String(text || "").trim();

  if (!clean) {
    return "";
  }

  if (!NEWS_TRANSLATION_ENABLED) {
    return clean;
  }

  if (
    translationCache.has(clean)
  ) {
    return translationCache.get(clean);
  }

  try {
    const url =
      "https://translate.googleapis.com/" +
      "translate_a/single" +
      "?client=gtx" +
      "&sl=auto" +
      "&tl=ar" +
      "&dt=t" +
      `&q=${encodeURIComponent(clean)}`;

    const response =
      await fetch(url);

    if (!response.ok) {
      return clean;
    }

    const data =
      await response.json();

    let translated = "";

    if (
      Array.isArray(data) &&
      Array.isArray(data[0])
    ) {
      translated =
        data[0]
          .map(part => part[0])
          .filter(Boolean)
          .join("");
    }

    translated =
      translated.trim() || clean;

    translationCache.set(
      clean,
      translated
    );

    return translated;
  } catch {
    return clean;
  }
}

// ============================================================
// 📰 PREPARE NEWS
// ============================================================

async function prepareNews(
  stock,
  generalNews
) {
  if (!NEWS_ENABLED) {
    return null;
  }

  let article =
    findNewsForStock(
      stock,
      generalNews
    );

  // لا نطلب أخبار خاصة لكل سهم
  // إلا إذا فعّل المستخدم NEWS_PER_STOCK
  if (
    !article &&
    NEWS_PER_STOCK &&
    Math.abs(stock.changePercent) >=
      NEWS_SIGNAL_CHANGE
  ) {
    try {
      const url =
        `https://eodhistoricaldata.com/api/news` +
        `?s=${encodeURIComponent(stock.ticker)}` +
        `&limit=1` +
        `&api_token=${EODHD_API_KEY}`;

      const data =
        await fetchEodhd(url);

      if (
        Array.isArray(data) &&
        data.length > 0
      ) {
        article = data[0];
      }
    } catch (error) {
      console.error(
        `⚠️ News ${stock.symbol}:`,
        error.message
      );
    }
  }

  if (!article) {
    return null;
  }

  const arabicTitle =
    await translateToArabic(
      article.title
    );

  return {
    title:
      arabicTitle,

    source:
      getArabicSource(
        article.link
      ),

    link:
      article.link || "",

    date:
      article.date || ""
  };
}

// ============================================================
// 📊 BUILD TELEGRAM MESSAGE
// ============================================================

async function buildMessage(
  stock,
  marketName,
  generalNews
) {
  let msg = "";

  msg += `📊 <b>${escapeHtml(marketName)}</b>\n\n`;

  msg += `📌 الرمز: <b>${escapeHtml(stock.symbol)}</b>\n`;

  msg += `🏢 الشركة: ${escapeHtml(stock.companyName)}\n\n`;

  msg += `💰 السعر: <b>${stock.price.toFixed(4)}</b>\n`;

  const changeEmoji =
    stock.changePercent > 0
      ? "🟢"
      : stock.changePercent < 0
        ? "🔴"
        : "⚪";

  msg +=
    `${changeEmoji} التغير: ` +
    `<b>${stock.changePercent.toFixed(2)}%</b>\n`;

  msg +=
    `🏦 السوق: ${escapeHtml(stock.exchange)}\n\n`;

  // ==========================================================
  // 🧠 AI TREND
  // ==========================================================

  if (stock.marketDirection) {
    msg +=
      `🧠 <b>AI PRO MAX</b>\n`;

    msg +=
      `🧭 الاتجاه: ` +
      `<b>${escapeHtml(
        stock.marketDirection.label
      )}</b>\n`;

    msg +=
      `🎯 قوة الاتجاه: ` +
      `<b>${stock.marketDirection.score}/100</b>\n`;
  }

  // ==========================================================
  // ATR
  // ==========================================================

  if (Number.isFinite(stock.atr)) {
    msg +=
      `📏 ATR(14): ` +
      `<b>${stock.atr.toFixed(4)}</b>\n`;
  }

  // ==========================================================
  // SUPPORT / RESISTANCE
  // ==========================================================

  if (stock.supportResistance) {
    if (
      Number.isFinite(
        stock.supportResistance.support
      )
    ) {
      msg +=
        `🟢 الدعم: ` +
        `<b>${roundPrice(
          stock.supportResistance.support
        )}</b>\n`;
    }

    if (
      Number.isFinite(
        stock.supportResistance.resistance
      )
    ) {
      msg +=
        `🔴 المقاومة: ` +
        `<b>${roundPrice(
          stock.supportResistance.resistance
        )}</b>\n`;
    }
  }

  msg += "\n";

  // ==========================================================
  // 💧 LIQUIDITY
  // ==========================================================

  msg +=
    `💧 السيولة: ` +
    `<b>${escapeHtml(
      stock.liquidityLabel
    )}</b>\n`;

  msg +=
    `شراء ${stock.buyRatio.toFixed(1)}% | ` +
    `بيع ${stock.sellRatio.toFixed(1)}%\n`;

  msg +=
    `📐 VWAP: <b>${stock.vwap.toFixed(4)}</b>\n\n`;

  // ==========================================================
  // 🎯 AI PRO MAX TARGETS
  // ==========================================================

  const direction =
    stock.marketDirection?.direction;

  const targetTitle =
    direction === "up"
      ? "🟢 أهداف صعود ATR"
      : direction === "down"
        ? "🔴 أهداف هبوط ATR"
        : "⚪ أهداف ATR";

  msg +=
    `🎯 <b>${targetTitle}</b>\n`;

  if (
    Array.isArray(stock.targets) &&
    stock.targets.length
  ) {
    for (const target of stock.targets) {
      const sign =
        target.direction === "down"
          ? "−"
          : "+";

      // علامة تحقق حمراء
      const achievedMark =
        target.achieved
          ? " 🔴✓"
          : "";

      msg +=
        `• الهدف ${target.number}: ` +
        `<b>${target.price.toFixed(4)}</b> ` +
        `(${sign}${target.atrMultiplier} ATR)` +
        `${achievedMark}\n`;
    }
  } else {
    msg +=
      `• ⚪ لا توجد بيانات ATR كافية\n`;
  }

  // ==========================================================
  // 📰 NEWS
  // ==========================================================

  const news =
    await prepareNews(
      stock,
      generalNews
    );

  if (news) {
    msg += "\n";
    msg += `📰 <b>آخر خبر</b>\n`;
    msg +=
      `🔹 ${escapeHtml(news.title)}\n`;
    msg +=
      `📡 المصدر: <b>${escapeHtml(
        news.source
      )}</b>\n`;

    if (news.link) {
      msg +=
        `🔗 <a href="${escapeHtml(
          news.link
        )}">فتح الخبر</a>\n`;
    }
  }

  msg += "\n";

  msg +=
    `🕒 التحديث: ` +
    `${new Date(stock.updatedAt).toLocaleTimeString(
      "ar-SA"
    )}`;

  return msg;
}

// ============================================================
// ⚡ PARALLEL WORKER ENGINE
// ============================================================

async function processInParallel(
  items,
  worker,
  concurrency = SCAN_CONCURRENCY
) {
  const results = [];

  let index = 0;

  async function runner() {
    while (true) {
      const currentIndex =
        index++;

      if (
        currentIndex >= items.length
      ) {
        return;
      }

      const item =
        items[currentIndex];

      try {
        const result =
          await worker(item);

        if (result !== undefined) {
          results.push(result);
        }
      } catch (error) {
        console.error(
          "Worker error:",
          error.message
        );
      }

      await sleep(REQUEST_DELAY_MS);
    }
  }

  const workers = [];

  const count =
    Math.min(
      concurrency,
      items.length
    );

  for (let i = 0; i < count; i++) {
    workers.push(
      runner()
    );
  }

  await Promise.all(workers);

  return results;
}

// ============================================================
// 📤 SEND TO SUBSCRIBERS
// ============================================================

async function sendToSubscribers(
  bot,
  subscribers,
  message
) {
  for (const chatId of subscribers) {
    try {
      await bot.sendMessage(
        chatId,
        message,
        {
          parse_mode: "HTML",
          disable_web_page_preview: true
        }
      );

      await sleep(150);
    } catch (error) {
      console.error(
        `❌ Telegram send error ${chatId}:`,
        error.message
      );
    }
  }
}

// ============================================================
// 🇸🇦 TASI FULL SCAN
// ============================================================

async function runTasiAutoScan() {
  if (tasiScanRunning) {
    console.log(
      "⏳ TASI scan already running."
    );
    return;
  }

  if (tasiSubscribers.size === 0) {
    return;
  }

  tasiScanRunning = true;

  console.log(
    "🇸🇦 Starting full TASI scan..."
  );

  try {
    let symbols;

    try {
      symbols =
        await getExchangeSymbols("SR");

      console.log(
        `🇸🇦 EODHD TASI symbols: ${symbols.length}`
      );
    } catch (error) {
      console.error(
        "❌ TASI symbol list error:",
        error.message
      );

      symbols =
        TASI_FALLBACK_SYMBOLS.map(
          symbol => ({
            symbol,
            name: symbol
          })
        );
    }

    const news =
      await getGeneralNews();

    await processInParallel(
      symbols,
      async symbolInfo => {
        try {
          const stock =
            await getStockDataFromEodhd(
              symbolInfo,
              "SR",
              0.01
            );

          const message =
            await buildMessage(
              stock,
              "🇸🇦 السوق السعودي — TASI",
              news
            );

          await sendToSubscribers(
            tasiBot,
            tasiSubscribers,
            message
          );
        } catch (error) {
          console.error(
            `⚠️ TASI ${symbolInfo.symbol}:`,
            error.message
          );
        }
      }
    );

    console.log(
      "✅ TASI full scan completed."
    );
  } catch (error) {
    console.error(
      "❌ TASI scan fatal error:",
      error
    );
  } finally {
    tasiScanRunning = false;
  }
}

// ============================================================
// 🇺🇸 US FULL SCAN
// ============================================================

async function runUsAutoScan() {
  if (usScanRunning) {
    console.log(
      "⏳ US scan already running."
    );
    return;
  }

  if (usSubscribers.size === 0) {
    return;
  }

  usScanRunning = true;

  console.log(
    "🇺🇸 Starting full US stock scan..."
  );

  try {
    let symbols;

    try {
      symbols =
        await getExchangeSymbols("US");

      console.log(
        `🇺🇸 EODHD US symbols: ${symbols.length}`
      );
    } catch (error) {
      console.error(
        "❌ US symbol list error:",
        error.message
      );

      symbols =
        US_FALLBACK_SYMBOLS.map(
          symbol => ({
            symbol,
            name: symbol
          })
        );
    }

    const news =
      await getGeneralNews();

    await processInParallel(
      symbols,
      async symbolInfo => {
        try {
          const stock =
            await getStockDataFromEodhd(
              symbolInfo,
              "US",
              MIN_PRICE_US
            );

          const message =
            await buildMessage(
              stock,
              "🇺🇸 السوق الأمريكي — US",
              news
            );

          await sendToSubscribers(
            usBot,
            usSubscribers,
            message
          );
        } catch (error) {
          console.error(
            `⚠️ US ${symbolInfo.symbol}:`,
            error.message
          );
        }
      }
    );

    console.log(
      "✅ US full scan completed."
    );
  } catch (error) {
    console.error(
      "❌ US scan fatal error:",
      error
    );
  } finally {
    usScanRunning = false;
  }
}

// ============================================================
// 🤖 TASI COMMANDS
// ============================================================

tasiBot.onText(
  /^\/start$/,
  async msg => {
    const chatId =
      msg.chat.id;

    tasiSubscribers.add(
      chatId
    );

    await tasiBot.sendMessage(
      chatId,
      "🇸🇦 <b>تم تفعيل بوت السوق السعودي AI PRO MAX</b>\n\n" +
      "🔍 جاري الفحص الكامل لأسهم تاسي...",
      {
        parse_mode: "HTML"
      }
    );

    runTasiAutoScan();
  }
);

tasiBot.onText(
  /^\/scan$/,
  async msg => {
    const chatId =
      msg.chat.id;

    tasiSubscribers.add(
      chatId
    );

    await tasiBot.sendMessage(
      chatId,
      "🔍 <b>جاري الفحص الكامل لأسهم تاسي...</b>",
      {
        parse_mode: "HTML"
      }
    );

    await runTasiAutoScan();
  }
);

// ============================================================
// 🤖 US COMMANDS
// ============================================================

usBot.onText(
  /^\/start$/,
  async msg => {
    const chatId =
      msg.chat.id;

    usSubscribers.add(
      chatId
    );

    await usBot.sendMessage(
      chatId,
      "🇺🇸 <b>تم تفعيل بوت السوق الأمريكي AI PRO MAX</b>\n\n" +
      "🔍 جاري الفحص الكامل للأسهم الأمريكية...",
      {
        parse_mode: "HTML"
      }
    );

    runUsAutoScan();
  }
);

usBot.onText(
  /^\/scan$/,
  async msg => {
    const chatId =
      msg.chat.id;

    usSubscribers.add(
      chatId
    );

    await usBot.sendMessage(
      chatId,
      "🔍 <b>جاري الفحص الكامل للأسهم الأمريكية...</b>",
      {
        parse_mode: "HTML"
      }
    );

    await runUsAutoScan();
  }
);

// ============================================================
// 🚨 TELEGRAM POLLING ERROR LOG
// ============================================================

tasiBot.on(
  "polling_error",
  error => {
    console.error(
      "❌ TASI polling_error:",
      error.message
    );
  }
);

usBot.on(
  "polling_error",
  error => {
    console.error(
      "❌ US polling_error:",
      error.message
    );
  }
);

// ============================================================
// ⏱️ AUTO SCAN
// ============================================================

setInterval(
  () => {
    runTasiAutoScan()
      .catch(error => {
        console.error(
          "TASI interval error:",
          error
        );
      });
  },
  UPDATE_INTERVAL_MIN *
    60 *
    1000
);

setInterval(
  () => {
    runUsAutoScan()
      .catch(error => {
        console.error(
          "US interval error:",
          error
        );
      });
  },
  UPDATE_INTERVAL_MIN *
    60 *
    1000
);

// ============================================================
// 🟢 START
// ============================================================

console.log(
  "============================================================"
);

console.log(
  "🧠 AI PRO MAX STOCK SCANNER STARTED"
);

console.log(
  "🇸🇦 TASI Scanner: READY"
);

console.log(
  "🇺🇸 US Scanner: READY"
);

console.log(
  "🎯 ATR Dynamic Targets: ENABLED"
);

console.log(
  "📍 Support / Resistance: ENABLED"
);

console.log(
  "💧 Liquidity Engine: ENABLED"
);

console.log(
  "📰 News Engine: ENABLED"
);

console.log(
  "❌ EMA: REMOVED"
);

console.log(
  `⚡ Scan concurrency: ${SCAN_CONCURRENCY}`
);

console.log(
  `⏱️ Auto scan: every ${UPDATE_INTERVAL_MIN} minutes`
);

console.log(
  "============================================================"
);