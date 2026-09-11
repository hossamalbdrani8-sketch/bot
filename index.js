
// ============================================================
// AI PRO MAX 💀🚀
// TASI 🇸🇦 + US 🇺🇸 + CRYPTO 🪙
// Autonomous Telegram Market Scanner
// Node.js 18+
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// CONFIG
// ============================================================

const CONFIG = {
  TELEGRAM_TOKEN: process.env.TELEGRAM_TOKEN || "",
  EODHD_API_KEY: process.env.EODHD_API_KEY || "",

  PORT: Number(process.env.PORT || 3000),

  // السعر الأمريكي الأدنى
  US_MIN_PRICE: 0.20,

  // فاصل الفحص
  SCAN_INTERVAL_MS: 5 * 60 * 1000,

  // عدد المرشحين الذين نحلل لهم OHLCV بعمق
  DEEP_ANALYSIS_LIMIT: 120,

  // أقل عدد شموع مطلوب
  MIN_BARS: 30,

  // عدد الأخبار
  NEWS_LIMIT: 3,

  // ATR
  ATR_PERIOD: 14,

  // أهداف ATR الديناميكية
  ATR_MULTIPLIERS: [
    0.50,
    0.90,
    1.30,
    1.80,
    2.40,
    3.10,
    4.00,
    5.00
  ],

  // منع تكرار الإشارة لنفس السهم
  SIGNAL_COOLDOWN_MS: 30 * 60 * 1000,

  // حد القوة لإرسال الإشارة
  SIGNAL_SCORE_MIN: 60
};

// ============================================================
// TELEGRAM
// ============================================================

if (!CONFIG.TELEGRAM_TOKEN) {
  console.error("❌ TELEGRAM_TOKEN غير موجود");
  process.exit(1);
}

if (!CONFIG.EODHD_API_KEY) {
  console.error("❌ EODHD_API_KEY غير موجود");
  process.exit(1);
}

const bot = new TelegramBot(CONFIG.TELEGRAM_TOKEN, {
  polling: true
});

// ============================================================
// EXPRESS
// ============================================================

const app = express();

app.get("/", (req, res) => {
  res.status(200).send("AI PRO MAX 💀🚀 يعمل");
});

app.get("/health", (req, res) => {
  res.json({
    ok: true,
    bot: "AI PRO MAX",
    running: true,
    time: new Date().toISOString()
  });
});

app.listen(CONFIG.PORT, () => {
  console.log(`🌐 Server running on port ${CONFIG.PORT}`);
});

// ============================================================
// STATE
// ============================================================

const state = {
  chats: new Set(),

  exchanges: {
    us: "US",
    crypto: "CC",
    tasi: null
  },

  universes: {
    us: [],
    tasi: [],
    crypto: []
  },

  lastSignals: new Map(),

  running: false,

  lastScan: {
    us: null,
    tasi: null,
    crypto: null
  }
};

// ============================================================
// HELPERS
// ============================================================

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function number(v, fallback = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function clamp(v, min, max) {
  return Math.max(min, Math.min(max, v));
}

function fmtPrice(v) {
  const n = number(v);

  if (n >= 1000) return n.toFixed(2);
  if (n >= 1) return n.toFixed(3);
  return n.toFixed(4);
}

function fmtPct(v) {
  return `${number(v).toFixed(2)}%`;
}

function now() {
  return Date.now();
}

function isRecentSignal(key) {
  const last = state.lastSignals.get(key);

  if (!last) return false;

  return now() - last < CONFIG.SIGNAL_COOLDOWN_MS;
}

function markSignal(key) {
  state.lastSignals.set(key, now());
}

// ============================================================
// EODHD REQUEST
// ============================================================

async function eodhd(path, params = {}) {
  const url = new URL(`https://eodhd.com${path}`);

  url.searchParams.set("api_token", CONFIG.EODHD_API_KEY);
  url.searchParams.set("fmt", "json");

  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) {
      url.searchParams.set(key, String(value));
    }
  }

  const response = await fetch(url, {
    method: "GET",
    headers: {
      "Accept": "application/json",
      "User-Agent": "AI-PRO-MAX/1.0"
    }
  });

  const text = await response.text();

  if (!response.ok) {
    throw new Error(
      `EODHD ${response.status}: ${text.slice(0, 300)}`
    );
  }

  try {
    return JSON.parse(text);
  } catch {
    throw new Error("EODHD أعاد بيانات غير JSON");
  }
}

// ============================================================
// FIND TADAWUL EXCHANGE AUTOMATICALLY
// ============================================================

async function resolveTadawul() {
  try {
    const exchanges = await eodhd("/api/exchanges-list/");

    if (!Array.isArray(exchanges)) {
      throw new Error("قائمة البورصات غير صالحة");
    }

    const found = exchanges.find(x => {
      const name = String(x.Name || "").toLowerCase();
      const country = String(x.Country || "").toLowerCase();
      const code = String(x.Code || "").toLowerCase();

      return (
        name.includes("saudi") ||
        name.includes("tadawul") ||
        country.includes("saudi") ||
        code.includes("tadawul")
      );
    });

    if (found && found.Code) {
      console.log(
        `🇸🇦 TASI exchange resolved: ${found.Code}`
      );

      state.exchanges.tasi = found.Code;

      return found.Code;
    }

    // fallback
    state.exchanges.tasi = "TADAWUL";

    return "TADAWUL";

  } catch (error) {
    console.error(
      "⚠️ تعذر اكتشاف رمز تداول تلقائيًا:",
      error.message
    );

    state.exchanges.tasi = "TADAWUL";

    return "TADAWUL";
  }
}

// ============================================================
// LOAD FULL UNIVERSE
// ============================================================

async function loadUniverse(exchange, type = null) {
  const params = {};

  if (type) {
    params.type = type;
  }

  const data = await eodhd(
    `/api/exchange-symbol-list/${encodeURIComponent(exchange)}/`,
    params
  );

  if (!Array.isArray(data)) {
    throw new Error(
      `قائمة ${exchange} غير صالحة`
    );
  }

  return data.filter(x => x && x.Code);
}

// ============================================================
// BUILD UNIVERSES
// ============================================================

async function loadAllUniverses() {
  console.log("📥 تحميل قوائم الأسواق...");

  const tasiCode = await resolveTadawul();

  const [us, tasi, crypto] = await Promise.all([
    loadUniverse("US", "common_stock"),
    loadUniverse(tasiCode, "common_stock"),
    loadUniverse("CC")
  ]);

  state.universes.us = us.filter(x => {
    const price = number(
      x.previousClose ||
      x.PreviousClose ||
      x.close
    );

    return price === 0 || price >= CONFIG.US_MIN_PRICE;
  });

  state.universes.tasi = tasi;

  state.universes.crypto = crypto;

  console.log(
    `🇺🇸 US: ${state.universes.us.length}`
  );

  console.log(
    `🇸🇦 TASI: ${state.universes.tasi.length}`
  );

  console.log(
    `🪙 Crypto: ${state.universes.crypto.length}`
  );
}

// ============================================================
// BULK US LIVE
// ============================================================

async function getUSBulk() {
  try {
    const data = await eodhd(
      "/api/real-time/AAPL.US",
      {
        ex: "US"
      }
    );

    return Array.isArray(data) ? data : [];

  } catch (error) {
    console.error(
      "❌ US bulk:",
      error.message
    );

    return [];
  }
}

// ============================================================
// GET QUOTE
// ============================================================

async function getQuote(symbol) {
  try {
    const data = await eodhd(
      `/api/real-time/${encodeURIComponent(symbol)}`
    );

    if (Array.isArray(data)) {
      return data[0] || null;
    }

    return data || null;

  } catch (error) {
    return null;
  }
}

// ============================================================
// INTRADAY
// ============================================================

async function getIntraday(symbol) {
  const end = Math.floor(Date.now() / 1000);

  const start =
    end -
    7 * 24 * 60 * 60;

  try {
    const data = await eodhd(
      `/api/intraday/${encodeURIComponent(symbol)}`,
      {
        interval: "5m",
        from: start,
        to: end
      }
    );

    return Array.isArray(data) ? data : [];

  } catch {
    return [];
  }
}

// ============================================================
// TECHNICAL FUNCTIONS
// ============================================================

function calculateATR(bars, period = 14) {
  if (bars.length < period + 1) {
    return 0;
  }

  const trs = [];

  for (let i = 1; i < bars.length; i++) {
    const high = number(bars[i].high);
    const low = number(bars[i].low);
    const prevClose = number(bars[i - 1].close);

    const tr = Math.max(
      high - low,
      Math.abs(high - prevClose),
      Math.abs(low - prevClose)
    );

    trs.push(tr);
  }

  const recent = trs.slice(-period);

  if (!recent.length) {
    return 0;
  }

  return (
    recent.reduce((a, b) => a + b, 0) /
    recent.length
  );
}

function calculateEMA(values, period) {
  if (!values.length) return 0;

  const k = 2 / (period + 1);

  let ema = values[0];

  for (let i = 1; i < values.length; i++) {
    ema =
      values[i] * k +
      ema * (1 - k);
  }

  return ema;
}

function calculateRSI(values, period = 14) {
  if (values.length <= period) {
    return 50;
  }

  let gains = 0;
  let losses = 0;

  for (let i = 1; i <= period; i++) {
    const change =
      values[i] - values[i - 1];

    if (change >= 0) {
      gains += change;
    } else {
      losses += Math.abs(change);
    }
  }

  let avgGain = gains / period;
  let avgLoss = losses / period;

  for (let i = period + 1; i < values.length; i++) {
    const change =
      values[i] - values[i - 1];

    const gain =
      change > 0 ? change : 0;

    const loss =
      change < 0 ? Math.abs(change) : 0;

    avgGain =
      (avgGain * (period - 1) + gain) /
      period;

    avgLoss =
      (avgLoss * (period - 1) + loss) /
      period;
  }

  if (avgLoss === 0) return 100;

  const rs = avgGain / avgLoss;

  return 100 - 100 / (1 + rs);
}

// ============================================================
// VOLUME / LIQUIDITY
// ============================================================

function liquidityAnalysis(bars) {
  if (bars.length < 10) {
    return {
      ratio: 1,
      strength: "عادية"
    };
  }

  const recent = bars.slice(-5);
  const previous = bars.slice(-20, -5);

  const recentVolume =
    recent.reduce(
      (sum, x) => sum + number(x.volume),
      0
    ) / Math.max(1, recent.length);

  const previousVolume =
    previous.reduce(
      (sum, x) => sum + number(x.volume),
      0
    ) / Math.max(1, previous.length);

  const ratio =
    previousVolume > 0
      ? recentVolume / previousVolume
      : 1;

  let strength = "عادية";

  if (ratio >= 2.5) {
    strength = "قوية جدًا 🟢";
  } else if (ratio >= 1.5) {
    strength = "قوية 🟢";
  } else if (ratio <= 0.65) {
    strength = "ضعيفة 🔴";
  }

  return {
    ratio,
    strength
  };
}

// ============================================================
// SUPPORT / RESISTANCE
// ============================================================

function supportResistance(bars) {
  const recent = bars.slice(-20);

  if (!recent.length) {
    return {
      support: 0,
      resistance: 0
    };
  }

  const lows = recent.map(x =>
    number(x.low)
  );

  const highs = recent.map(x =>
    number(x.high)
  );

  return {
    support: Math.min(...lows),
    resistance: Math.max(...highs)
  };
}

// ============================================================
// AI PRO MAX TREND ENGINE
// ============================================================

function aiProMax(bars) {
  const closes = bars
    .map(x => number(x.close))
    .filter(x => x > 0);

  if (closes.length < 30) {
    return null;
  }

  const price =
    closes[closes.length - 1];

  const ema7 =
    calculateEMA(closes, 7);

  const ema14 =
    calculateEMA(closes, 14);

  const ema25 =
    calculateEMA(closes, 25);

  const ema50 =
    calculateEMA(closes, 50);

  const rsi =
    calculateRSI(closes, 14);

  const atr =
    calculateATR(
      bars,
      CONFIG.ATR_PERIOD
    );

  let score = 50;

  if (price > ema7) score += 8;
  else score -= 8;

  if (ema7 > ema14) score += 8;
  else score -= 8;

  if (ema14 > ema25) score += 8;
  else score -= 8;

  if (ema25 > ema50) score += 8;
  else score -= 8;

  if (rsi >= 55) score += 8;
  else if (rsi <= 45) score -= 8;

  score = clamp(score, 0, 100);

  let trend = "محايد";
  let direction = "NEUTRAL";

  if (score >= 60) {
    trend = "صاعد 🟢";
    direction = "UP";
  }

  if (score <= 40) {
    trend = "هابط 🔴";
    direction = "DOWN";
  }

  return {
    price,
    ema7,
    ema14,
    ema25,
    ema50,
    rsi,
    atr,
    score,
    trend,
    direction
  };
}

// ============================================================
// DYNAMIC TARGETS
// ============================================================

function targets(price, atr, direction) {
  const result = [];

  for (
    let i = 0;
    i < CONFIG.ATR_MULTIPLIERS.length;
    i++
  ) {
    const multiplier =
      CONFIG.ATR_MULTIPLIERS[i];

    let target;

    if (direction === "UP") {
      target =
        price +
        atr * multiplier;
    } else {
      target =
        price -
        atr * multiplier;
    }

    result.push({
      number: i + 1,
      multiplier,
      price: Math.max(0, target)
    });
  }

  return result;
}

// ============================================================
// NEWS
// ============================================================

function arabicTitle(title) {
  if (!title) return "لا يوجد عنوان";

  // EODHD قد يعيد عنوانًا عربيًا في بعض البيانات المستقبلية.
  // بدون خدمة ترجمة خارجية لا يتم إرسال النص إلى طرف ثالث.
  return title;
}

async function getNews(symbol) {
  try {
    const data = await eodhd(
      "/api/news",
      {
        s: symbol,
        offset: 0,
        limit: CONFIG.NEWS_LIMIT
      }
    );

    if (!Array.isArray(data)) {
      return [];
    }

    return data.map(item => ({
      title: arabicTitle(
        item.titleAr ||
        item.title_ar ||
        item.title
      ),
      date:
        item.date ||
        item.datetime ||
        "",
      source:
        item.source ||
        item.site ||
        "EODHD",
      link:
        item.link ||
        item.url ||
        ""
    }));

  } catch {
    return [];
  }
}

// ============================================================
// ANALYZE SYMBOL
// ============================================================

async function analyzeSymbol(symbol, market) {
  const bars =
    await getIntraday(symbol);

  if (
    !bars ||
    bars.length < CONFIG.MIN_BARS
  ) {
    return null;
  }

  const cleanBars = bars
    .filter(x =>
      number(x.close) > 0 &&
      number(x.high) > 0 &&
      number(x.low) > 0
    );

  const ai =
    aiProMax(cleanBars);

  if (!ai) return null;

  const liquidity =
    liquidityAnalysis(cleanBars);

  const levels =
    supportResistance(cleanBars);

  const targetsList =
    targets(
      ai.price,
      ai.atr,
      ai.direction === "DOWN"
        ? "DOWN"
        : "UP"
    );

  const latest =
    cleanBars[cleanBars.length - 1];

  const signalKey =
    `${market}:${symbol}`;

  let signal = "مراقبة 🟡";

  if (
    ai.direction === "UP" &&
    ai.score >= CONFIG.SIGNAL_SCORE_MIN &&
    liquidity.ratio >= 1.15
  ) {
    signal = "🔥 صعود قوي 🟢";
  }

  if (
    ai.direction === "DOWN" &&
    ai.score <= 40 &&
    liquidity.ratio >= 1.15
  ) {
    signal = "🔴✓ هبوط قوي";
  }

  // لا نرسل الإشارة المحايدة
  if (
    signal === "مراقبة 🟡"
  ) {
    return null;
  }

  return {
    market,
    symbol,
    price: ai.price,
    signal,
    direction: ai.direction,
    trend: ai.trend,
    score: ai.score,
    atr: ai.atr,
    rsi: ai.rsi,
    volume: number(latest.volume),
    liquidity,
    support: levels.support,
    resistance: levels.resistance,
    targets: targetsList
  };
}

// ============================================================
// MESSAGE
// ============================================================

function buildSignalMessage(result, news = []) {
  const marketName =
    result.market === "US"
      ? "🇺🇸 الأسهم الأمريكية"
      : result.market === "TASI"
        ? "🇸🇦 تاسي"
        : "🪙 العملات الرقمية";

  const targetTitle =
    result.direction === "UP"
      ? "🎯 الأهداف الصاعدة"
      : "🔴✓ الأهداف الهابطة";

  let message = "";

  message +=
    `💀🚀 *AI PRO MAX*\n`;

  message +=
    `━━━━━━━━━━━━━━━━━━\n`;

  message +=
    `${marketName}\n\n`;

  message +=
    `📌 *الرمز:* \`${result.symbol}\`\n`;

  message +=
    `💰 *السعر:* ${fmtPrice(result.price)}\n`;

  message +=
    `🚦 *الإشارة:* ${result.signal}\n`;

  message +=
    `🧠 *الاتجاه العام:* ${result.trend}\n`;

  message +=
    `📊 *قوة AI:* ${result.score}/100\n`;

  message +=
    `📏 *ATR(14):* ${fmtPrice(result.atr)}\n`;

  message +=
    `📈 *RSI(14):* ${result.rsi.toFixed(2)}\n`;

  message +=
    `💧 *السيولة:* ${result.liquidity.strength}\n`;

  message +=
    `💧 *نسبة السيولة:* ${result.liquidity.ratio.toFixed(2)}x\n`;

  message +=
    `📦 *حجم التداول:* ${result.volume.toLocaleString()}\n\n`;

  message +=
    `📍 *الدعم:* ${fmtPrice(result.support)}\n`;

  message +=
    `📍 *المقاومة:* ${fmtPrice(result.resistance)}\n\n`;

  message +=
    `${targetTitle}\n`;

  for (const target of result.targets) {
    message +=
      `${target.number}. ${fmtPrice(target.price)}  ` +
      `ATR × ${target.multiplier}\n`;
  }

  if (news.length) {
    message +=
      `\n📰 *الأخبار*\n`;

    for (const item of news) {
      message +=
        `• ${item.title}\n`;

      if (item.source) {
        message +=
          `  المصدر: ${item.source}\n`;
      }
    }
  }

  message +=
    `\n━━━━━━━━━━━━━━━━━━\n`;

  message +=
    `🤖 فحص تلقائي — AI PRO MAX`;

  return message;
}

// ============================================================
// SEND
// ============================================================

async function sendToAllChats(message) {
  for (const chatId of state.chats) {
    try {
      await bot.sendMessage(
        chatId,
        message,
        {
          parse_mode: "Markdown",
          disable_web_page_preview: true
        }
      );
    } catch (error) {
      console.error(
        `Telegram ${chatId}:`,
        error.message
      );
    }
  }
}

// ============================================================
// REGISTER CHAT
// ============================================================

bot.on("message", async message => {
  if (!message.chat) return;

  const chatId =
    message.chat.id;

  state.chats.add(chatId);

  if (
    message.text === "/start"
  ) {
    await bot.sendMessage(
      chatId,
      [
        "💀🚀 AI PRO MAX",
        "",
        "تم تفعيل البوت.",
        "",
        "🇸🇦 فحص تاسي الكامل",
        "🇺🇸 فحص الأسهم الأمريكية",
        "🪙 فحص العملات الرقمية",
        "",
        "🧠 محرك AI PRO MAX",
        "📏 ATR(14)",
        "🎯 8 أهداف ديناميكية",
        "📍 دعم ومقاومة",
        "💧 تحليل السيولة",
        "📰 أخبار EODHD",
        "",
        "🤖 الفحص تلقائي ولا يحتاج /scan"
      ].join("\n")
    );
  }
});

// ============================================================
// US CANDIDATES
// ============================================================

function getUSCandidates(rows) {
  return rows
    .filter(x => {
      const price =
        number(x.close);

      return (
        price >= CONFIG.US_MIN_PRICE
      );
    })
    .sort((a, b) => {
      const scoreA =
        Math.abs(number(a.change_p)) *
        Math.log10(
          Math.max(10, number(a.volume))
        );

      const scoreB =
        Math.abs(number(b.change_p)) *
        Math.log10(
          Math.max(10, number(b.volume))
        );

      return scoreB - scoreA;
    })
    .slice(
      0,
      CONFIG.DEEP_ANALYSIS_LIMIT
    );
}

// ============================================================
// GENERIC CANDIDATES
// ============================================================

async function getGenericCandidates(
  universe,
  limit
) {
  const candidates = [];

  // تقسيم الطلبات حتى لا يتم الضغط على API
  const batchSize = 15;

  for (
    let i = 0;
    i < universe.length;
    i += batchSize
  ) {
    const batch =
      universe.slice(i, i + batchSize);

    const results =
      await Promise.all(
        batch.map(async item => {
          const symbol =
            `${item.Code}.${item.Exchange || ""}`
              .replace(/\.$/, "");

          const quote =
            await getQuote(symbol);

          if (!quote) return null;

          return {
            ...item,
            quote,
            symbol
          };
        })
      );

    for (const row of results) {
      if (row) {
        candidates.push(row);
      }
    }

    if (
      candidates.length >= limit * 2
    ) {
      break;
    }

    await sleep(100);
  }

  return candidates
    .sort((a, b) =>
      Math.abs(
        number(b.quote.change_p)
      ) -
      Math.abs(
        number(a.quote.change_p)
      )
    )
    .slice(0, limit);
}

// ============================================================
// SCAN US
// ============================================================

async function scanUS() {
  console.log("🇺🇸 بدء فحص US الكامل...");

  const rows =
    await getUSBulk();

  if (!rows.length) {
    console.log(
      "⚠️ لم تصل بيانات US"
    );
    return;
  }

  const candidates =
    getUSCandidates(rows);

  console.log(
    `🇺🇸 تم فحص الكون الكامل واختيار ${candidates.length} للتحليل العميق`
  );

  for (const row of candidates) {
    const symbol =
      row.code ||
      row.Code;

    if (!symbol) continue;

    try {
      const result =
        await analyzeSymbol(
          symbol,
          "US"
        );

      if (!result) continue;

      const key =
        `US:${symbol}`;

      if (isRecentSignal(key)) {
        continue;
      }

      const news =
        await getNews(symbol);

      const message =
        buildSignalMessage(
          result,
          news
        );

      await sendToAllChats(
        message
      );

      markSignal(key);

      await sleep(150);

    } catch (error) {
      console.error(
        `US ${symbol}:`,
        error.message
      );
    }
  }

  state.lastScan.us =
    new Date().toISOString();
}

// ============================================================
// SCAN TASI
// ============================================================

async function scanTASI() {
  console.log(
    "🇸🇦 بدء فحص تاسي الكامل..."
  );

  const candidates =
    await getGenericCandidates(
      state.universes.tasi,
      CONFIG.DEEP_ANALYSIS_LIMIT
    );

  console.log(
    `🇸🇦 تم فحص قائمة تاسي واختيار ${candidates.length}`
  );

  for (const item of candidates) {
    const symbol =
      item.symbol;

    try {
      const result =
        await analyzeSymbol(
          symbol,
          "TASI"
        );

      if (!result) continue;

      const key =
        `TASI:${symbol}`;

      if (isRecentSignal(key)) {
        continue;
      }

      const news =
        await getNews(symbol);

      await sendToAllChats(
        buildSignalMessage(
          result,
          news
        )
      );

      markSignal(key);

      await sleep(150);

    } catch (error) {
      console.error(
        `TASI ${symbol}:`,
        error.message
      );
    }
  }

  state.lastScan.tasi =
    new Date().toISOString();
}

// ============================================================
// SCAN CRYPTO
// ============================================================

async function scanCrypto() {
  console.log(
    "🪙 بدء فحص العملات الرقمية الكامل..."
  );

  const candidates =
    await getGenericCandidates(
      state.universes.crypto,
      CONFIG.DEEP_ANALYSIS_LIMIT
    );

  console.log(
    `🪙 تم فحص قائمة العملات واختيار ${candidates.length}`
  );

  for (const item of candidates) {
    const symbol =
      item.symbol;

    try {
      const result =
        await analyzeSymbol(
          symbol,
          "CRYPTO"
        );

      if (!result) continue;

      const key =
        `CRYPTO:${symbol}`;

      if (isRecentSignal(key)) {
        continue;
      }

      const news =
        await getNews(symbol);

      await sendToAllChats(
        buildSignalMessage(
          result,
          news
        )
      );

      markSignal(key);

      await sleep(150);

    } catch (error) {
      console.error(
        `CRYPTO ${symbol}:`,
        error.message
      );
    }
  }

  state.lastScan.crypto =
    new Date().toISOString();
}

// ============================================================
// MASTER SCAN
// ============================================================

async function fullScan() {
  if (state.running) {
    console.log(
      "⏳ يوجد فحص يعمل حاليًا"
    );
    return;
  }

  state.running = true;

  try {
    console.log(
      "━━━━━━━━━━━━━━━━━━━━━━━━"
    );

    console.log(
      "💀🚀 AI PRO MAX — FULL SCAN"
    );

    console.log(
      new Date().toISOString()
    );

    console.log(
      "━━━━━━━━━━━━━━━━━━━━━━━━"
    );

    await scanUS();

    await scanTASI();

    await scanCrypto();

  } catch (error) {
    console.error(
      "❌ FULL SCAN:",
      error
    );

  } finally {
    state.running = false;
  }
}

// ============================================================
// STARTUP
// ============================================================

async function startup() {
  try {
    console.log(
      "🚀 تشغيل AI PRO MAX..."
    );

    await loadAllUniverses();

    console.log(
      "✅ القوائم جاهزة"
    );

    // الفحص الأول
    await fullScan();

    // فحص تلقائي مستمر
    setInterval(
      fullScan,
      CONFIG.SCAN_INTERVAL_MS
    );

    console.log(
      "♾️ التشغيل التلقائي 24/7 مفعل"
    );

  } catch (error) {
    console.error(
      "❌ Startup:",
      error
    );

    // إعادة المحاولة تلقائيًا
    setTimeout(
      startup,
      60 * 1000
    );
  }
}

// ============================================================
// GLOBAL ERROR PROTECTION
// ============================================================

process.on(
  "unhandledRejection",
  error => {
    console.error(
      "Unhandled rejection:",
      error
    );
  }
);

process.on(
  "uncaughtException",
  error => {
    console.error(
      "Uncaught exception:",
      error
    );
  }
);

// ============================================================
// RUN
// ============================================================

startup();