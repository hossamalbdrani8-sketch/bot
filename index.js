
"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");
const fs = require("fs");
const path = require("path");

// ============================================================
// 💀🚀 AI PRO MAX
// EODHD ONLY
// TASI + US + CRYPTO
// Webhook + Railway
// فحص تلقائي كل دقيقتين
// ============================================================

const PORT = Number(process.env.PORT || 3000);

const EODHD_API_KEY =
  String(process.env.EODHD_API_KEY || "").trim();

const TASI_TOKEN =
  String(process.env.TASI_CONFIG || "").trim();

const US_TOKEN =
  String(process.env.US_CONFIG || "").trim();

const CRYPTO_TOKEN =
  String(process.env.CRYPTO_CONFIG || "").trim();

const SCAN_INTERVAL = 2 * 60 * 1000;
const UNIVERSE_REFRESH = 60 * 60 * 1000;

const MIN_US_PRICE = 0.20;
const MAX_ALERTS_PER_MARKET = 3;

const app = express();

app.use(
  express.json({
    limit: "512kb",
  })
);

// ============================================================
// الحالة
// ============================================================

const markets = {
  TASI: {
    symbols: [],
    loadedAt: 0,
    bot: null,
    chats: new Set(),
    lastSignals: new Map(),
  },

  US: {
    symbols: [],
    loadedAt: 0,
    bot: null,
    chats: new Set(),
    lastSignals: new Map(),
  },

  CRYPTO: {
    symbols: [],
    loadedAt: 0,
    bot: null,
    chats: new Set(),
    lastSignals: new Map(),
  },
};

// ============================================================
// أدوات
// ============================================================

function log(text) {
  console.log(
    `${new Date().toISOString()} | ${text}`
  );
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function num(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function fmt(value, decimals = 2) {
  const n = num(value);

  if (n === null) {
    return "-";
  }

  return n.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function percent(value, decimals = 2) {
  const n = num(value);

  if (n === null) {
    return "-";
  }

  return `${n >= 0 ? "+" : ""}${n.toFixed(decimals)}%`;
}

function clamp(value, min, max) {
  return Math.max(
    min,
    Math.min(max, value)
  );
}

// ============================================================
// EODHD
// ============================================================

async function eodhd(endpoint, params = {}) {

  if (!EODHD_API_KEY) {
    throw new Error(
      "EODHD_API_KEY غير موجود"
    );
  }

  const url = new URL(
    `https://eodhd.com/api/${endpoint.replace(/^\/+/, "")}`
  );

  url.searchParams.set(
    "api_token",
    EODHD_API_KEY
  );

  url.searchParams.set(
    "fmt",
    "json"
  );

  for (const [key, value] of Object.entries(params)) {

    if (
      value !== undefined &&
      value !== null &&
      value !== ""
    ) {
      url.searchParams.set(
        key,
        String(value)
      );
    }
  }

  const response = await fetch(
    url,
    {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
    }
  );

  const text = await response.text();

  let data;

  try {
    data = JSON.parse(text);
  } catch {
    data = text;
  }

  if (!response.ok) {

    let message = "";

    if (typeof data === "string") {
      message = data;
    } else {
      message =
        data?.message ||
        data?.error ||
        JSON.stringify(data);
    }

    throw new Error(
      `EODHD HTTP ${response.status}: ${message}`
    );
  }

  return data;
}

// ============================================================
// اكتشاف مشكلة الحد
// ============================================================

function quotaError(error) {

  const text =
    String(error?.message || error || "");

  return (
    /HTTP 402/i.test(text) ||
    /daily API requests limit/i.test(text) ||
    /daily requests limit/i.test(text) ||
    /exceeded your daily/i.test(text)
  );
}

// ============================================================
// السوق السعودي
// لا نستخدم SR بشكل ثابت
// نبحث عن رمز السوق من EODHD
// ============================================================

async function getSaudiExchange() {

  const exchanges =
    await eodhd("exchanges-list/");

  if (!Array.isArray(exchanges)) {
    throw new Error(
      "قائمة البورصات غير صالحة"
    );
  }

  const found =
    exchanges.find(exchange => {

      const name =
        String(exchange?.Name || "")
          .toLowerCase();

      const country =
        String(exchange?.Country || "")
          .toLowerCase();

      return (
        name.includes("saudi") ||
        name.includes("tadawul") ||
        country.includes("saudi")
      );
    });

  if (!found?.Code) {
    throw new Error(
      "لم يتم العثور على السوق السعودي"
    );
  }

  return String(found.Code);
}

// ============================================================
// الرموز
// ============================================================

function fullSymbol(code, exchange) {

  if (!code) {
    return null;
  }

  const value =
    String(code).trim();

  if (!value) {
    return null;
  }

  if (value.includes(".")) {
    return value;
  }

  return `${value}.${exchange}`;
}

// ============================================================
// تحميل رموز TASI
// ============================================================

async function loadTASI() {

  const state = markets.TASI;

  if (
    state.symbols.length &&
    Date.now() - state.loadedAt <
      UNIVERSE_REFRESH
  ) {
    return state.symbols;
  }

  try {

    const exchange =
      await getSaudiExchange();

    const rows =
      await eodhd(
        `exchange-symbol-list/${encodeURIComponent(exchange)}`,
        {}
      );

    if (!Array.isArray(rows)) {
      throw new Error(
        "قائمة السوق السعودي غير صالحة"
      );
    }

    const symbols =
      rows
        .filter(row => {

          const type =
            String(row?.Type || "")
              .toLowerCase();

          return (
            type.includes("common stock") ||
            type === "stock"
          );
        })
        .map(row =>
          fullSymbol(
            row?.Code,
            exchange
          )
        )
        .filter(Boolean);

    if (!symbols.length) {
      throw new Error(
        "لم يتم العثور على أسهم سعودية"
      );
    }

    state.symbols =
      [...new Set(symbols)];

    state.loadedAt =
      Date.now();

    log(
      `🇸🇦 TASI: ${state.symbols.length} رمز`
    );

    return state.symbols;

  } catch (error) {

    if (quotaError(error)) {

      log(
        "ℹ️ TASI: تم إيقاف طلبات EODHD لهذه الدورة."
      );

    } else {

      log(
        `ℹ️ TASI: ${error.message}`
      );
    }

    return state.symbols;
  }
}

// ============================================================
// تحميل رموز US
// ============================================================

async function loadUS() {

  const state = markets.US;

  if (
    state.symbols.length &&
    Date.now() - state.loadedAt <
      UNIVERSE_REFRESH
  ) {
    return state.symbols;
  }

  try {

    const rows =
      await eodhd(
        "exchange-symbol-list/US",
        {}
      );

    if (!Array.isArray(rows)) {
      throw new Error(
        "قائمة US غير صالحة"
      );
    }

    const symbols =
      rows
        .filter(row => {

          const type =
            String(row?.Type || "")
              .toLowerCase();

          return (
            type.includes("common stock") ||
            type === "stock"
          );
        })
        .map(row =>
          fullSymbol(
            row?.Code,
            "US"
          )
        )
        .filter(Boolean);

    if (!symbols.length) {
      throw new Error(
        "لم يتم العثور على أسهم أمريكية"
      );
    }

    state.symbols =
      [...new Set(symbols)];

    state.loadedAt =
      Date.now();

    log(
      `🇺🇸 US: ${state.symbols.length} رمز`
    );

    return state.symbols;

  } catch (error) {

    if (quotaError(error)) {

      log(
        "ℹ️ US: تم إيقاف طلبات EODHD لهذه الدورة."
      );

    } else {

      log(
        `ℹ️ US: ${error.message}`
      );
    }

    return state.symbols;
  }
}

// ============================================================
// تحميل العملات الرقمية
// ============================================================

async function loadCrypto() {

  const state = markets.CRYPTO;

  if (
    state.symbols.length &&
    Date.now() - state.loadedAt <
      UNIVERSE_REFRESH
  ) {
    return state.symbols;
  }

  try {

    const rows =
      await eodhd(
        "exchange-symbol-list/CC",
        {}
      );

    if (!Array.isArray(rows)) {
      throw new Error(
        "قائمة العملات غير صالحة"
      );
    }

    const symbols =
      rows
        .filter(row =>
          String(row?.Code || "")
            .includes("-")
        )
        .map(row =>
          fullSymbol(
            row?.Code,
            "CC"
          )
        )
        .filter(Boolean);

    if (!symbols.length) {
      throw new Error(
        "لم يتم العثور على عملات"
      );
    }

    state.symbols =
      [...new Set(symbols)];

    state.loadedAt =
      Date.now();

    log(
      `🪙 CRYPTO: ${state.symbols.length} رمز`
    );

    return state.symbols;

  } catch (error) {

    if (quotaError(error)) {

      log(
        "ℹ️ CRYPTO: تم إيقاف طلبات EODHD لهذه الدورة."
      );

    } else {

      log(
        `ℹ️ CRYPTO: ${error.message}`
      );
    }

    return state.symbols;
  }
}

// ============================================================
// الأسعار
// ============================================================

async function getLivePrices(symbols) {

  if (!symbols.length) {
    return [];
  }

  const result = [];

  const BATCH_SIZE = 80;

  for (
    let i = 0;
    i < symbols.length;
    i += BATCH_SIZE
  ) {

    const batch =
      symbols.slice(
        i,
        i + BATCH_SIZE
      );

    const first =
      batch[0];

    const rest =
      batch
        .slice(1)
        .join(",");

    try {

      const data =
        await eodhd(
          `real-time/${encodeURIComponent(first)}`,
          rest
            ? { s: rest }
            : {}
        );

      if (Array.isArray(data)) {

        result.push(...data);

      } else if (
        data &&
        typeof data === "object"
      ) {

        result.push(data);
      }

    } catch (error) {

      if (quotaError(error)) {
        throw error;
      }

      log(
        `ℹ️ تعذر جلب الأسعار: ${error.message}`
      );
    }

    if (
      i + BATCH_SIZE <
      symbols.length
    ) {
      await sleep(100);
    }
  }

  return result;
}

// ============================================================
// قراءة السعر
// ============================================================

function getSymbol(q) {

  return (
    q?.code ||
    q?.symbol ||
    q?.ticker ||
    ""
  );
}

function getPrice(q) {

  return num(
    q?.close ??
    q?.price ??
    q?.last ??
    q?.previousClose
  );
}

function getVolume(q) {

  return num(
    q?.volume ??
    q?.Volume
  );
}

function getChange(q) {

  const direct =
    num(
      q?.change_p ??
      q?.changePercent ??
      q?.change_pct
    );

  if (direct !== null) {
    return direct;
  }

  const price =
    getPrice(q);

  const previous =
    num(
      q?.previousClose ??
      q?.previous_close
    );

  if (
    price !== null &&
    previous
  ) {

    return (
      (price - previous) /
      previous
    ) * 100;
  }

  return 0;
}

// ============================================================
// اختيار الأسهم الأقوى
// ============================================================

function candidates(quotes, market) {

  return quotes

    .map(q => ({
      raw: q,

      symbol:
        getSymbol(q),

      price:
        getPrice(q),

      volume:
        getVolume(q),

      change:
        getChange(q),
    }))

    .filter(x =>
      x.symbol &&
      x.price !== null &&
      x.price > 0
    )

    .filter(x =>
      market !== "US" ||
      x.price >= MIN_US_PRICE
    )

    .sort((a, b) => {

      const scoreA =
        Math.abs(a.change) * 2 +
        Math.log10(
          (a.volume || 1) + 1
        );

      const scoreB =
        Math.abs(b.change) * 2 +
        Math.log10(
          (b.volume || 1) + 1
        );

      return scoreB - scoreA;
    });
}

// ============================================================
// التاريخ
// ============================================================

async function getHistory(symbol) {

  const now =
    new Date();

  const old =
    new Date(
      Date.now() -
      260 *
      24 *
      60 *
      60 *
      1000
    );

  const date =
    d =>
      d.toISOString()
        .slice(0, 10);

  const rows =
    await eodhd(
      `eod/${encodeURIComponent(symbol)}`,
      {
        from: date(old),
        to: date(now),
        order: "a",
      }
    );

  if (!Array.isArray(rows)) {
    throw new Error(
      "بيانات EOD غير صالحة"
    );
  }

  return rows.filter(row =>

    num(row?.open) !== null &&
    num(row?.high) !== null &&
    num(row?.low) !== null &&
    num(row?.close) !== null
  );
}

// ============================================================
// EMA
// ============================================================

function EMA(values, period) {

  if (
    values.length <
    period
  ) {
    return null;
  }

  const multiplier =
    2 /
    (period + 1);

  let result =
    values
      .slice(0, period)
      .reduce(
        (a, b) => a + b,
        0
      ) /
    period;

  for (
    let i = period;
    i < values.length;
    i++
  ) {

    result =
      values[i] *
        multiplier +
      result *
        (1 - multiplier);
  }

  return result;
}

// ============================================================
// RSI
// ============================================================

function RSI(values, period = 14) {

  if (
    values.length <=
    period
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

  let avgGain =
    gain / period;

  let avgLoss =
    loss / period;

  for (
    let i = period + 1;
    i < values.length;
    i++
  ) {

    const diff =
      values[i] -
      values[i - 1];

    const g =
      Math.max(
        diff,
        0
      );

    const l =
      Math.max(
        -diff,
        0
      );

    avgGain =
      (
        avgGain *
          (period - 1) +
        g
      ) /
      period;

    avgLoss =
      (
        avgLoss *
          (period - 1) +
        l
      ) /
      period;
  }

  if (
    avgLoss === 0
  ) {
    return 100;
  }

  const rs =
    avgGain /
    avgLoss;

  return (
    100 -
    100 /
      (1 + rs)
  );
}

// ============================================================
// ATR
// ============================================================

function ATR(rows, period = 14) {

  if (
    rows.length <=
    period
  ) {
    return null;
  }

  const TR = [];

  for (
    let i = 0;
    i < rows.length;
    i++
  ) {

    const high =
      Number(rows[i].high);

    const low =
      Number(rows[i].low);

    if (i === 0) {

      TR.push(
        high - low
      );

      continue;
    }

    const previousClose =
      Number(
        rows[i - 1].close
      );

    TR.push(
      Math.max(
        high - low,
        Math.abs(
          high -
          previousClose
        ),
        Math.abs(
          low -
          previousClose
        )
      )
    );
  }

  let result =
    TR
      .slice(
        1,
        period + 1
      )
      .reduce(
        (a, b) => a + b,
        0
      ) /
    period;

  for (
    let i =
      period + 1;
    i < TR.length;
    i++
  ) {

    result =
      (
        result *
          (period - 1) +
        TR[i]
      ) /
      period;
  }

  return result;
}

// ============================================================
// الدعم والمقاومة
// ============================================================

function supportResistance(
  rows
) {

  const recent =
    rows.slice(-20);

  const lows =
    recent
      .map(x => num(x.low))
      .filter(x => x !== null);

  const highs =
    recent
      .map(x => num(x.high))
      .filter(x => x !== null);

  return {

    support:
      lows.length
        ? Math.min(...lows)
        : null,

    resistance:
      highs.length
        ? Math.max(...highs)
        : null,
  };
}

// ============================================================
// قوة الحجم
// ============================================================

function volumePower(rows) {

  const volumes =
    rows
      .map(x =>
        num(x.volume)
      )
      .filter(
        x =>
          x !== null &&
          x > 0
      );

  if (
    volumes.length <
    21
  ) {
    return 1;
  }

  const current =
    volumes[
      volumes.length - 1
    ];

  const previous =
    volumes.slice(
      -21,
      -1
    );

  const average =
    previous.reduce(
      (a, b) => a + b,
      0
    ) /
    previous.length;

  if (!average) {
    return 1;
  }

  return (
    current /
    average
  );
}

// ============================================================
// قوة الشراء والبيع
// ============================================================

function buySellPower(rows) {

  const recent =
    rows.slice(-20);

  let buy = 0;
  let sell = 0;

  for (const row of recent) {

    const open =
      num(row.open);

    const high =
      num(row.high);

    const low =
      num(row.low);

    const close =
      num(row.close);

    const volume =
      num(row.volume) || 1;

    if (
      open === null ||
      high === null ||
      low === null ||
      close === null
    ) {
      continue;
    }

    const range =
      Math.max(
        high - low,
        0.00000001
      );

    const position =
      (close - low) /
      range;

    buy +=
      volume *
      position;

    sell +=
      volume *
      (1 - position);
  }

  const total =
    buy + sell || 1;

  return {

    buy:
      (buy / total) *
      100,

    sell:
      (sell / total) *
      100,
  };
}

// ============================================================
// المحرك الذكي
// ============================================================

function analyze(
  rows,
  price,
  change
) {

  const closes =
    rows.map(
      x => Number(x.close)
    );

  const ema8 =
    EMA(closes, 8);

  const ema21 =
    EMA(closes, 21);

  const ema50 =
    EMA(closes, 50);

  const rsi =
    RSI(closes, 14);

  const atr =
    ATR(rows, 14);

  const sr =
    supportResistance(rows);

  const volume =
    volumePower(rows);

  const power =
    buySellPower(rows);

  if (
    ema8 === null ||
    ema21 === null ||
    ema50 === null ||
    rsi === null ||
    atr === null
  ) {
    return null;
  }

  let score = 50;

  // EMA
  if (ema8 > ema21) {
    score += 10;
  } else {
    score -= 10;
  }

  if (ema21 > ema50) {
    score += 10;
  } else {
    score -= 10;
  }

  if (price > ema50) {
    score += 8;
  } else {
    score -= 8;
  }

  // RSI
  if (
    rsi >= 55 &&
    rsi <= 75
  ) {
    score += 7;
  }

  if (rsi < 45) {
    score -= 7;
  }

  if (rsi > 80) {
    score -= 4;
  }

  // القوة
  if (
    power.buy >
    power.sell
  ) {
    score += 7;
  } else {
    score -= 7;
  }

  // الحجم
  if (volume >= 1.5) {
    score += 5;
  }

  // التغير
  if (change > 0) {
    score += 3;
  }

  if (change < 0) {
    score -= 3;
  }

  score =
    Math.round(
      clamp(
        score,
        0,
        100
      )
    );

  let direction =
    "NEUTRAL";

  if (
    score >= 72 &&
    ema8 > ema21 &&
    ema21 > ema50 &&
    power.buy >= power.sell
  ) {

    direction =
      "BUY";

  } else if (
    score <= 28 &&
    ema8 < ema21 &&
    ema21 < ema50 &&
    power.sell >= power.buy
  ) {

    direction =
      "SELL";
  }

  return {

    direction,

    score,

    price,

    change,

    ema8,
    ema21,
    ema50,

    rsi,
    atr,

    support:
      sr.support,

    resistance:
      sr.resistance,

    volume,

    buyPower:
      power.buy,

    sellPower:
      power.sell,
  };
}

// ============================================================
// أهداف ATR الثمانية
// ============================================================

function targets(signal) {

  const result = [];

  const multipliers =
    [1, 2, 3, 4, 5, 6, 7, 8];

  for (
    let i = 0;
    i < multipliers.length;
    i++
  ) {

    const m =
      multipliers[i];

    let target;

    if (
      signal.direction ===
      "SELL"
    ) {

      target =
        signal.price -
        signal.atr * m;

    } else {

      target =
        signal.price +
        signal.atr * m;
    }

    const change =
      (
        (target -
          signal.price) /
        signal.price
      ) *
      100;

    result.push({

      number:
        i + 1,

      price:
        target,

      change,
    });
  }

  return result;
}

// ============================================================
// اسم السوق
// ============================================================

function marketName(
  market
) {

  if (
    market === "TASI"
  ) {

    return (
      "🇸🇦 السوق السعودي (TASI)"
    );
  }

  if (
    market === "US"
  ) {

    return (
      "🇺🇸 السوق الأمريكي (US)"
    );
  }

  return (
    "🪙 العملات الرقمية (CRYPTO)"
  );
}

// ============================================================
// رسالة الإشارة
// ============================================================

function signalMessage(
  market,
  symbol,
  company,
  signal
) {

  const buy =
    signal.direction ===
    "BUY";

  const title =
    buy
      ? "🟢⬆️ شراء قوي"
      : "🔴⬇️ بيع قوي";

  const trend =
    buy
      ? "🟢 صاعد قوي"
      : "🔴 هابط قوي";

  const tp =
    targets(signal);

  let text = "";

  text +=
    "💀🚀 AI PRO MAX SIGNAL\n\n";

  text +=
    `${marketName(market)}\n\n`;

  text +=
    `${symbol}\n`;

  if (company) {

    text +=
      `${company}\n`;
  }

  text += "\n";

  text +=
    `${title}\n\n`;

  text +=
    `السعر: ${fmt(signal.price)}\n`;

  text +=
    `التغير: ${percent(signal.change)}\n`;

  text +=
    `قوة الإشارة: ${signal.score}/100\n`;

  text +=
    `قوة الشراء: ${fmt(signal.buyPower, 0)}%\n`;

  text +=
    `قوة البيع: ${fmt(signal.sellPower, 0)}%\n`;

  text +=
    `قوة الحجم: ${fmt(signal.volume, 1)}x\n\n`;

  text +=
    `EMA 8: ${fmt(signal.ema8)}\n`;

  text +=
    `EMA 21: ${fmt(signal.ema21)}\n`;

  text +=
    `EMA 50: ${fmt(signal.ema50)}\n`;

  text +=
    `RSI 14: ${fmt(signal.rsi, 1)}\n`;

  text +=
    `ATR 14: ${fmt(signal.atr)}\n\n`;

  text +=
    `الدعم: ${fmt(signal.support)}\n`;

  text +=
    `المقاومة: ${fmt(signal.resistance)}\n`;

  text +=
    `${trend}\n\n`;

  text +=
    "🎯 أهداف ATR الثمانية:\n";

  for (const item of tp) {

    text +=
      `TP${item.number}  ` +
      `${fmt(item.price)}  ` +
      `(${percent(item.change, 1)})\n`;
  }

  return text;
}

// ============================================================
// رسالة /start
// ============================================================

function startMessage(
  market
) {

  let marketText;

  if (
    market === "TASI"
  ) {

    marketText =
      "🇸🇦 السوق السعودي";

  } else if (
    market === "US"
  ) {

    marketText =
      "🇺🇸 السوق الأمريكي";

  } else {

    marketText =
      "🪙 العملات الرقمية";
  }

  return [
    "💀🚀 AI PRO MAX",
    "",
    "✅ البوت يعمل الآن",
    "",
    "🔄 الفحص تلقائي وكامل",
    "⏱️ الفحص كل دقيقتين",
    "",
    "📊 السوق:",
    marketText,
    "",
    "🧠 المحرك الذكي:",
    "",
    "• EMA 8",
    "• EMA 21",
    "• EMA 50",
    "• RSI 14",
    "• ATR 14",
    "• دعم",
    "• مقاومة",
    "• قوة الحجم",
    "• قوة الشراء",
    "• قوة البيع",
    "• 8 أهداف ATR",
    "• منع تكرار التنبيهات",
    "",
    "🟢⬆️ سهم أخضر متحرك = صعود قوي",
    "🔴⬇️ سهم أحمر متحرك = هبوط قوي",
    "",
    "🤖 لا تحتاج إلى تشغيل الفحص يدويًا.",
    "",
    "📡 مصدر البيانات:",
    "EODHD فقط",
  ].join("\n");
}

// ============================================================
// Telegram
// ============================================================

function chatFile(
  market
) {

  return path.join(
    __dirname,
    `chat_ids_${market.toLowerCase()}.json`
  );
}

function loadChats(
  market
) {

  const state =
    markets[market];

  try {

    const file =
      chatFile(market);

    if (
      !fs.existsSync(file)
    ) {
      return;
    }

    const data =
      JSON.parse(
        fs.readFileSync(
          file,
          "utf8"
        )
      );

    if (
      Array.isArray(data)
    ) {

      for (
        const id of data
      ) {

        state.chats.add(
          String(id)
        );
      }
    }

  } catch (error) {

    log(
      `ℹ️ ${market}: تعذر قراءة المحادثات`
    );
  }
}

function saveChats(
  market
) {

  const state =
    markets[market];

  try {

    fs.writeFileSync(
      chatFile(market),
      JSON.stringify(
        [...state.chats],
        null,
        2
      ),
      "utf8"
    );

  } catch (error) {

    log(
      `ℹ️ ${market}: تعذر حفظ المحادثات`
    );
  }
}

// ============================================================
// Railway Webhook
// ============================================================

async function setupWebhook(
  market,
  bot
) {

  const domain =
    process.env.RAILWAY_PUBLIC_DOMAIN ||
    process.env.RAILWAY_STATIC_URL ||
    "";

  if (!domain) {

    throw new Error(
      "لم يتم العثور على نطاق Railway"
    );
  }

  const base =
    domain.startsWith("http")
      ? domain
      : `https://${domain}`;

  const url =
    `${base.replace(/\/+$/, "")}` +
    `/telegram/${market.toLowerCase()}`;

  await bot.setWebHook(
    url,
    {
      max_connections: 40,
      drop_pending_updates: true,
    }
  );
}

// ============================================================
// تشغيل بوت
// ============================================================

function startBot(
  market,
  token
) {

  const state =
    markets[market];

  if (!token) {

    log(
      `ℹ️ ${market} BOT: لا يوجد token`
    );

    return;
  }

  loadChats(market);

  const bot =
    new TelegramBot(
      token,
      {
        polling: false,
      }
    );

  state.bot =
    bot;

  bot.on(
    "message",
    async message => {

      if (
        !message?.chat?.id
      ) {
        return;
      }

      const chatId =
        String(
          message.chat.id
        );

      state.chats.add(
        chatId
      );

      saveChats(market);

      const command =
        String(
          message.text || ""
        )
        .trim()
        .toLowerCase();

      if (
        command === "/start"
      ) {

        try {

          await bot.sendMessage(
            chatId,
            startMessage(
              market
            )
          );

        } catch (error) {

          log(
            `ℹ️ ${market}: Telegram ${error.message}`
          );
        }
      }
    }
  );

  app.post(
    `/telegram/${market.toLowerCase()}`,
    async (req, res) => {

      try {

        await bot.processUpdate(
          req.body
        );

      } catch (error) {

        log(
          `ℹ️ ${market}: webhook ${error.message}`
        );
      }

      res.sendStatus(200);
    }
  );

  setupWebhook(
    market,
    bot
  )
    .then(() => {

      log(
        `Telegram Webhook: ${market.toLowerCase()} ON`
      );

    })
    .catch(error => {

      log(
        `ℹ️ ${market}: webhook ${error.message}`
      );
    });

  log(
    `🤖 ${market} BOT: ON`
  );
}

// ============================================================
// إرسال الإشارة
// ============================================================

async function sendSignal(
  market,
  message
) {

  const state =
    markets[market];

  if (!state.bot) {
    return;
  }

  const chats =
    [...state.chats];

  for (
    const chatId of chats
  ) {

    try {

      await state.bot.sendMessage(
        chatId,
        message
      );

    } catch (error) {

      log(
        `ℹ️ ${market}: تعذر إرسال Telegram`
      );
    }
  }
}

// ============================================================
// تحليل سهم
// ============================================================

async function analyzeSymbol(
  candidate
) {

  try {

    const rows =
      await getHistory(
        candidate.symbol
      );

    if (
      rows.length < 60
    ) {
      return null;
    }

    return analyze(
      rows,
      candidate.price,
      candidate.change
    );

  } catch (error) {

    if (!quotaError(error)) {

      log(
        `ℹ️ ${candidate.symbol}: ${error.message}`
      );
    }

    return null;
  }
}

// ============================================================
// فحص سوق
// ============================================================

async function scanMarket(
  market
) {

  let symbols;

  if (
    market === "TASI"
  ) {

    symbols =
      await loadTASI();

  } else if (
    market === "US"
  ) {

    symbols =
      await loadUS();

  } else {

    symbols =
      await loadCrypto();
  }

  if (
    !symbols.length
  ) {

    log(
      `ℹ️ ${market}: لا توجد قائمة رموز جاهزة.`
    );

    return;
  }

  let quotes;

  try {

    quotes =
      await getLivePrices(
        symbols
      );

  } catch (error) {

    if (
      quotaError(error)
    ) {

      log(
        `ℹ️ ${market}: EODHD وصل إلى حد الطلبات.`
      );

      return;
    }

    log(
      `ℹ️ ${market}: ${error.message}`
    );

    return;
  }

  const list =
    candidates(
      quotes,
      market
    )
    .slice(
      0,
      8
    );

  if (
    !list.length
  ) {

    log(
      `ℹ️ ${market}: لا توجد أسعار قابلة للتحليل.`
    );

    return;
  }

  let sent =
    0;

  for (
    const candidate of list
  ) {

    const signal =
      await analyzeSymbol(
        candidate
      );

    if (!signal) {
      continue;
    }

    if (
      signal.direction ===
      "NEUTRAL"
    ) {
      continue;
    }

    if (
      signal.direction ===
        "BUY" &&
      signal.score < 72
    ) {
      continue;
    }

    if (
      signal.direction ===
        "SELL" &&
      signal.score > 28
    ) {
      continue;
    }

    // منع التكرار
    const state =
      markets[market];

    const old =
      state.lastSignals.get(
        candidate.symbol
      );

    const signalKey =
      `${candidate.symbol}_${signal.direction}`;

    const now =
      Date.now();

    if (
      old &&
      old.key === signalKey &&
      now - old.time <
        60 * 60 * 1000
    ) {

      continue;
    }

    state.lastSignals.set(
      candidate.symbol,
      {
        key:
          signalKey,

        time:
          now,
      }
    );

    const company =
      candidate.raw?.name ||
      candidate.raw?.Name ||
      "";

    const message =
      signalMessage(
        market,
        candidate.symbol,
        company,
        signal
      );

    log(
      `📡 ${market}: ${signal.direction} ${candidate.symbol}`
    );

    await sendSignal(
      market,
      message
    );

    sent++;

    if (
      sent >=
      MAX_ALERTS_PER_MARKET
    ) {
      break;
    }
  }
}

// ============================================================
// الفحص الكامل
// ============================================================

let scanNumber = 0;
let running = false;

async function fullScan() {

  if (running) {
    return;
  }

  running = true;

  scanNumber++;

  const start =
    Date.now();

  log(
    "============================================================"
  );

  log(
    `🚀 AI PRO MAX SCAN #${scanNumber}`
  );

  try {

    await scanMarket(
      "TASI"
    );

    await scanMarket(
      "US"
    );

    await scanMarket(
      "CRYPTO"
    );

  } catch (error) {

    log(
      `ℹ️ خطأ في دورة الفحص: ${error.message}`
    );

  } finally {

    log(
      `✅ انتهت الدورة | ${Date.now() - start} ms`
    );

    log(
      "============================================================"
    );

    running = false;
  }
}

// ============================================================
// Railway Health
// ============================================================

app.get(
  "/",
  (req, res) => {

    res.json({
      ok: true,
      bot: "AI PRO MAX",
      mode: "24/7",
      scan: "2 minutes",
      data: "EODHD ONLY",
      markets: [
        "TASI",
        "US",
        "CRYPTO",
      ],
    });
  }
);

app.get(
  "/health",
  (req, res) => {

    res
      .status(200)
      .send(
        "AI PRO MAX OK"
      );
  }
);

// ============================================================
// فحص المتغيرات
// ============================================================

function checkConfig() {

  const missing = [];

  if (!TASI_TOKEN) {
    missing.push(
      "TASI_CONFIG"
    );
  }

  if (!US_TOKEN) {
    missing.push(
      "US_CONFIG"
    );
  }

  if (!CRYPTO_TOKEN) {
    missing.push(
      "CRYPTO_CONFIG"
    );
  }

  if (!EODHD_API_KEY) {
    missing.push(
      "EODHD_API_KEY"
    );
  }

  if (
    missing.length
  ) {

    throw new Error(
      `متغيرات ناقصة: ${missing.join(", ")}`
    );
  }
}

// ============================================================
// التشغيل
// ============================================================

async function main() {

  checkConfig();

  app.listen(
    PORT,
    () => {

      log(
        `🚀 AI PRO MAX يعمل على PORT ${PORT}`
      );
    }
  );

  startBot(
    "TASI",
    TASI_TOKEN
  );

  startBot(
    "US",
    US_TOKEN
  );

  startBot(
    "CRYPTO",
    CRYPTO_TOKEN
  );

  log(
    "🟢 النظام يعمل 24/7"
  );

  log(
    "⏱️ الفحص كل دقيقتين"
  );

  log(
    "📡 مصدر البيانات: EODHD فقط"
  );

  await sleep(5000);

  await fullScan();

  setInterval(
    fullScan,
    SCAN_INTERVAL
  );
}

main().catch(
  error => {

    log(
      `ℹ️ تعذر تشغيل النظام: ${error.message}`
    );

    process.exit(1);
  }
);