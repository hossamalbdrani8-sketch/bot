// ============================================================
// 🇺🇸 US STOCK TELEGRAM BOT
// EMA + LIQUIDITY + VOLUME + VWAP + TARGETS
// Node.js 18+
// ============================================================

import express from "express";
import TelegramBot from "node-telegram-bot-api";

// ============================================================
// الإعدادات
// ============================================================

const TOKEN = process.env.TELEGRAM_TOKEN;

const PORT = Number(process.env.PORT || 3000);

const MAX_SYMBOLS = Number(process.env.MAX_SYMBOLS || 250);

const MIN_CHANGE = Number(process.env.MIN_CHANGE || 0.30);

const SCAN_INTERVAL_MIN = Number(
  process.env.SCAN_INTERVAL_MIN || 5
);

const UPDATE_INTERVAL_SEC = Number(
  process.env.UPDATE_INTERVAL_SEC || 30
);

const REQUEST_DELAY_MS = Number(
  process.env.REQUEST_DELAY_MS || 350
);

if (!TOKEN) {
  console.error("❌ TELEGRAM_TOKEN غير موجود");
  process.exit(1);
}

// ============================================================
// Telegram
// ============================================================

const bot = new TelegramBot(TOKEN, {
  polling: true
});

const app = express();

app.use(express.json());

// ============================================================
// التخزين
// ============================================================

const sentSignals = new Map();

let scanning = false;

let lastScanTime = null;

let lastScanCount = 0;

let cachedSymbols = [];

let symbolsCacheTime = 0;

// ============================================================
// أدوات عامة
// ============================================================

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function roundPrice(price) {
  if (!Number.isFinite(price)) return "0.00";

  if (price < 1) {
    return price.toFixed(2);
  }

  if (price < 10) {
    return price.toFixed(2);
  }

  return price.toFixed(2);
}

function formatNumber(value) {
  if (!Number.isFinite(value)) return "0";

  if (value >= 1_000_000_000) {
    return `${(value / 1_000_000_000).toFixed(2)}B`;
  }

  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(2)}M`;
  }

  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(2)}K`;
  }

  return Math.round(value).toLocaleString("en-US");
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

// ============================================================
// Yahoo Finance
// ============================================================

async function yahooFetch(url) {
  const response = await fetch(url, {
    headers: {
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
      "Accept": "application/json"
    }
  });

  if (!response.ok) {
    throw new Error(`Yahoo HTTP ${response.status}`);
  }

  return response.json();
}

// ============================================================
// قائمة الأسهم
// ============================================================

async function getSymbols() {

  const now = Date.now();

  // كاش 15 دقيقة
  if (
    cachedSymbols.length > 0 &&
    now - symbolsCacheTime < 15 * 60 * 1000
  ) {
    return cachedSymbols;
  }

  const lists = [
    "day_gainers",
    "most_actives",
    "growth_technology_stocks"
  ];

  const symbols = new Set();

  for (const list of lists) {

    try {

      const url =
        `https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=${encodeURIComponent(list)}&count=250`;

      const data = await yahooFetch(url);

      const quotes =
        data?.finance?.result?.[0]?.quotes || [];

      for (const item of quotes) {

        const symbol = item?.symbol;

        if (
          symbol &&
          /^[A-Z0-9.\-]+$/.test(symbol) &&
          !symbol.includes("=") &&
          !symbol.includes("^")
        ) {
          symbols.add(symbol);
        }

        if (symbols.size >= MAX_SYMBOLS) {
          break;
        }
      }

    } catch (error) {

      console.log(
        `⚠️ تعذر تحميل القائمة ${list}:`,
        error.message
      );
    }

    if (symbols.size >= MAX_SYMBOLS) {
      break;
    }
  }

  cachedSymbols = [...symbols].slice(0, MAX_SYMBOLS);

  symbolsCacheTime = now;

  console.log(
    `📋 تم تحميل ${cachedSymbols.length} سهم`
  );

  return cachedSymbols;
}

// ============================================================
// جلب بيانات السهم
// ============================================================

async function getStockData(symbol) {

  const url =
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}` +
    `?range=5d&interval=5m&includePrePost=false`;

  const data = await yahooFetch(url);

  const result =
    data?.chart?.result?.[0];

  if (!result) {
    throw new Error("لا توجد بيانات");
  }

  const meta = result.meta || {};

  const quote =
    result.indicators?.quote?.[0];

  if (!quote) {
    throw new Error("بيانات التداول غير موجودة");
  }

  const closes = (quote.close || [])
    .map(Number)
    .filter(Number.isFinite);

  const highs = (quote.high || [])
    .map(Number)
    .filter(Number.isFinite);

  const lows = (quote.low || [])
    .map(Number)
    .filter(Number.isFinite);

  const volumes = (quote.volume || [])
    .map(Number)
    .filter(Number.isFinite);

  if (closes.length < 20) {
    throw new Error("بيانات غير كافية");
  }

  const price =
    Number(meta.regularMarketPrice) ||
    closes[closes.length - 1];

  const previousClose =
    Number(meta.previousClose) ||
    Number(meta.chartPreviousClose) ||
    closes[Math.max(0, closes.length - 2)];

  if (
    !Number.isFinite(price) ||
    !Number.isFinite(previousClose) ||
    previousClose <= 0
  ) {
    throw new Error("السعر غير صالح");
  }

  // ==========================================================
  // التغير
  // ==========================================================

  const change =
    ((price - previousClose) / previousClose) * 100;

  // ==========================================================
  // EMA
  // ==========================================================

  const ema7 = calculateEMA(closes, 7);

  const ema14 = calculateEMA(closes, 14);

  const ema25 = calculateEMA(closes, 25);

  const ema50 = calculateEMA(closes, 50);

  // ==========================================================
  // VWAP
  // ==========================================================

  const vwap =
    calculateVWAP(
      highs,
      lows,
      closes,
      volumes
    );

  // ==========================================================
  // حجم التداول
  // ==========================================================

  const currentVolume =
    volumes.length
      ? volumes[volumes.length - 1]
      : 0;

  const averageVolume =
    average(
      volumes.slice(
        Math.max(0, volumes.length - 50),
        volumes.length
      )
    );

  // ==========================================================
  // قوة الفوليوم
  // ==========================================================

  let volumeStrength = 0;

  if (averageVolume > 0) {

    volumeStrength =
      (currentVolume / averageVolume) * 50;

    volumeStrength =
      clamp(volumeStrength, 0, 100);
  }

  // ==========================================================
  // قوة VWAP
  // ==========================================================

  let vwapStrength = 50;

  if (vwap > 0) {

    const distance =
      ((price - vwap) / vwap) * 100;

    vwapStrength =
      50 + distance * 20;

    vwapStrength =
      clamp(vwapStrength, 0, 100);
  }

  // ==========================================================
  // ضغط السيولة
  // ==========================================================

  let buyPressure = 0;

  let sellPressure = 0;

  const lookback = Math.min(
    20,
    closes.length
  );

  for (
    let i = closes.length - lookback;
    i < closes.length;
    i++
  ) {

    const close = closes[i];

    const open =
      i > 0
        ? closes[i - 1]
        : close;

    const volume =
      volumes[i] || 0;

    if (close > open) {

      buyPressure += volume;

    } else if (close < open) {

      sellPressure += volume;

    }
  }

  const totalPressure =
    buyPressure + sellPressure;

  let liquidityState =
    "⚪ سيولة متوازنة";

  if (totalPressure > 0) {

    const buyRatio =
      (buyPressure / totalPressure) * 100;

    const sellRatio =
      (sellPressure / totalPressure) * 100;

    if (
      buyRatio >= 65 &&
      volumeStrength >= 60 &&
      price >= vwap
    ) {

      liquidityState =
        "🟢 دخول سيولة قوية";

    } else if (
      sellRatio >= 65 &&
      volumeStrength >= 60 &&
      price < vwap
    ) {

      liquidityState =
        "🔴 خروج سيولة";

    } else if (buyRatio >= 55) {

      liquidityState =
        "🟢 دخول سيولة";

    } else if (sellRatio >= 55) {

      liquidityState =
        "🔴 خروج سيولة";
    }
  }

  // ==========================================================
  // EMA Signal
  // ==========================================================

  let emaSignal =
    "⚪ EMA متوازن";

  if (
    ema7 > ema14 &&
    ema14 > ema25 &&
    ema25 > ema50
  ) {

    emaSignal =
      "⚡ EMA سريع";

  } else if (
    ema7 < ema14 &&
    ema14 < ema25 &&
    ema25 < ema50
  ) {

    emaSignal =
      "🔻 EMA هابط";
  }

  // ==========================================================
  // الاتجاه اللحظي
  // ==========================================================

  let intradaySignal =
    "⚪ مستقر";

  if (
    price > ema7 &&
    ema7 > ema14 &&
    price > vwap
  ) {

    intradaySignal =
      "⚡ 📈 صعود لحظي";

  } else if (
    price < ema7 &&
    ema7 < ema14 &&
    price < vwap
  ) {

    intradaySignal =
      "⚡ 📉 هبوط لحظي";
  }

  // ==========================================================
  // إشارة رئيسية
  // ==========================================================

  let signal =
    "📊 محايد";

  if (
    change >= MIN_CHANGE &&
    price > ema7 &&
    ema7 > ema14 &&
    price > vwap &&
    volumeStrength >= 50
  ) {

    signal =
      "📊 🔥 صعود";

  } else if (
    change <= -MIN_CHANGE &&
    price < ema7 &&
    ema7 < ema14 &&
    price < vwap &&
    volumeStrength >= 50
  ) {

    signal =
      "📊 🔻 هبوط";
  }

  return {
    symbol,
    price,
    previousClose,
    change,
    ema7,
    ema14,
    ema25,
    ema50,
    vwap,
    currentVolume,
    averageVolume,
    volumeStrength,
    vwapStrength,
    liquidityState,
    emaSignal,
    intradaySignal,
    signal
  };
}

// ============================================================
// EMA
// ============================================================

function calculateEMA(values, period) {

  if (!values.length) {
    return 0;
  }

  const multiplier =
    2 / (period + 1);

  let ema =
    values[0];

  for (let i = 1; i < values.length; i++) {

    ema =
      (values[i] - ema) *
      multiplier +
      ema;
  }

  return ema;
}

// ============================================================
// VWAP
// ============================================================

function calculateVWAP(
  highs,
  lows,
  closes,
  volumes
) {

  let totalPV = 0;

  let totalVolume = 0;

  const length = Math.min(
    highs.length,
    lows.length,
    closes.length,
    volumes.length
  );

  const start =
    Math.max(0, length - 78);

  for (let i = start; i < length; i++) {

    const high = highs[i];

    const low = lows[i];

    const close = closes[i];

    const volume = volumes[i];

    if (
      !Number.isFinite(high) ||
      !Number.isFinite(low) ||
      !Number.isFinite(close) ||
      !Number.isFinite(volume) ||
      volume <= 0
    ) {
      continue;
    }

    const typical =
      (high + low + close) / 3;

    totalPV +=
      typical * volume;

    totalVolume +=
      volume;
  }

  if (totalVolume <= 0) {
    return closes[closes.length - 1];
  }

  return totalPV / totalVolume;
}

// ============================================================
// Average
// ============================================================

function average(values) {

  if (!values.length) {
    return 0;
  }

  const sum =
    values.reduce(
      (a, b) => a + b,
      0
    );

  return sum / values.length;
}

// ============================================================
// الأهداف
// ============================================================

function calculateTargets(entry) {

  const percentages = [
    0.02,
    0.04,
    0.06,
    0.08,
    0.10,
    0.12,
    0.15,
    0.18
  ];

  return percentages.map(
    percent =>
      entry * (1 + percent)
  );
}

// ============================================================
// تنسيق الرسالة
// ============================================================

function formatSignal(data) {

  const targets =
    calculateTargets(data.price);

  const targetText =
    targets
      .map(
        target =>
          `🎯 ${roundPrice(target)}`
      )
      .join("\n");

  return `
🇺🇸 السوق الأمريكي

${data.symbol}

💰 ${roundPrice(data.price)}

${data.signal}

📊 EMA: ${data.emaSignal}
${data.intradaySignal}

${data.liquidityState}
💪 قوة الفوليوم: ${data.volumeStrength.toFixed(0)}%
📦 حجم التداول: ${formatNumber(data.currentVolume)}
🔥 قوة الفيواب: ${data.vwapStrength.toFixed(0)}%

${targetText}

━━━━━━━━━━━━
`.trim();
}

// ============================================================
// إرسال إشارة
// ============================================================

async function sendSignal(chatId, data) {

  const old =
    sentSignals.get(data.symbol);

  // لا نكرر نفس الإشارة
  if (
    old &&
    old.signal === data.signal &&
    old.liquidityState === data.liquidityState
  ) {
    return false;
  }

  sentSignals.set(
    data.symbol,
    {
      ...data,
      entryPrice: data.price,
      targetsHit: []
    }
  );

  await bot.sendMessage(
    chatId,
    formatSignal(data)
  );

  return true;
}

// ============================================================
// فحص الأسهم
// ============================================================

async function scan(chatId) {

  if (scanning) {
    return;
  }

  scanning = true;

  console.log("🔎 بدء الفحص...");

  try {

    const symbols =
      await getSymbols();

    let found = 0;

    for (
      const symbol of symbols
    ) {

      try {

        const data =
          await getStockData(symbol);

        // نركز على الأسهم الصاعدة
        if (
          data.change >= MIN_CHANGE &&
          data.price > 0
        ) {

          const sent =
            await sendSignal(
              chatId,
              data
            );

          if (sent) {
            found++;
          }
        }

      } catch (error) {

        console.log(
          `⚠️ ${symbol}: ${error.message}`
        );
      }

      await sleep(
        REQUEST_DELAY_MS
      );
    }

    lastScanCount = found;

    lastScanTime =
      new Date();

    console.log(
      `✅ انتهى الفحص — إشارات جديدة: ${found}`
    );

  } finally {

    scanning = false;
  }
}

// ============================================================
// تحديث الإشارات
// ============================================================

async function updateSignals() {

  if (
    sentSignals.size === 0
  ) {
    return;
  }

  for (
    const [
      symbol,
      old
    ] of sentSignals
  ) {

    try {

      const data =
        await getStockData(symbol);

      // تحديث البيانات الداخلية
      old.price =
        data.price;

      old.change =
        data.change;

      old.volumeStrength =
        data.volumeStrength;

      old.currentVolume =
        data.currentVolume;

      old.vwapStrength =
        data.vwapStrength;

      old.liquidityState =
        data.liquidityState;

      old.emaSignal =
        data.emaSignal;

      old.intradaySignal =
        data.intradaySignal;

      old.signal =
        data.signal;

      const targets =
        calculateTargets(
          old.entryPrice
        );

      for (
        let i = 0;
        i < targets.length;
        i++
      ) {

        const target =
          targets[i];

        if (
          data.price >= target &&
          !old.targetsHit.includes(i)
        ) {

          old.targetsHit.push(i);

          console.log(
            `🎯 ${symbol} وصل الهدف ${i + 1}`
          );

          // نرسل تحديث الهدف فقط
          for (
            const chatId of old.chatIds || []
          ) {

            await bot.sendMessage(
              chatId,
              `
🎯 تحقق الهدف ${i + 1}

${symbol}

💰 السعر الحالي:
${roundPrice(data.price)}

🎯 الهدف:
${roundPrice(target)}

${data.liquidityState}

💪 قوة الفوليوم:
${data.volumeStrength.toFixed(0)}%

🔥 قوة الفيواب:
${data.vwapStrength.toFixed(0)}%

━━━━━━━━━━━━
`.trim()
            );
          }
        }
      }

    } catch (error) {

      console.log(
        `⚠️ تحديث ${symbol}:`,
        error.message
      );
    }

    await sleep(
      REQUEST_DELAY_MS
    );
  }
}

// ============================================================
// حفظ Chat ID للإشارة
// ============================================================

function attachChatId(
  symbol,
  chatId
) {

  const item =
    sentSignals.get(symbol);

  if (!item) {
    return;
  }

  if (!item.chatIds) {
    item.chatIds = [];
  }

  if (
    !item.chatIds.includes(chatId)
  ) {
    item.chatIds.push(chatId);
  }
}

// ============================================================
// /start
// ============================================================

bot.onText(
  /\/start/,
  async msg => {

    const chatId =
      msg.chat.id;

    await bot.sendMessage(
      chatId,
      `
🇺🇸 بوت مراقبة الأسهم الأمريكية

✅ EMA
✅ الاتجاه اللحظي
🟢 دخول السيولة
🔴 خروج السيولة
💪 قوة الفوليوم
📦 حجم التداول
🔥 قوة VWAP
🎯 8 أهداف

الأوامر:

/scan — فحص الأسهم
/signals — الإشارات الحالية
/status — حالة البوت
/refresh — تحديث قائمة الأسهم
/stop — إيقاف الإشارات

━━━━━━━━━━━━
`.trim()
    );
  }
);

// ============================================================
// /scan
// ============================================================

bot.onText(
  /\/scan/,
  async msg => {

    const chatId =
      msg.chat.id;

    await bot.sendMessage(
      chatId,
      "🔎 بدأ فحص الأسهم الأمريكية..."
    );

    await scan(chatId);

    // ربط chatId بالإشارات
    for (
      const [
        symbol
      ] of sentSignals
    ) {
      attachChatId(
        symbol,
        chatId
      );
    }

    await bot.sendMessage(
      chatId,
      `
✅ انتهى الفحص

📊 إشارات جديدة:
${lastScanCount}

⏱ آخر فحص:
${lastScanTime
  ? lastScanTime.toLocaleString("ar-SA")
  : "—"}
`.trim()
    );
  }
);

// ============================================================
// /signals
// ============================================================

bot.onText(
  /\/signals/,
  async msg => {

    const chatId =
      msg.chat.id;

    if (
      sentSignals.size === 0
    ) {

      await bot.sendMessage(
        chatId,
        "📭 لا توجد إشارات حالياً."
      );

      return;
    }

    let text =
      "📊 الإشارات الحالية\n\n";

    let count = 0;

    for (
      const [
        symbol,
        data
      ] of sentSignals
    ) {

      text +=
        `${symbol} — ${roundPrice(data.price)} — ${data.signal}\n`;

      count++;

      if (count >= 30) {
        break;
      }
    }

    await bot.sendMessage(
      chatId,
      text.trim()
    );
  }
);

// ============================================================
// /status
// ============================================================

bot.onText(
  /\/status/,
  async msg => {

    const chatId =
      msg.chat.id;

    await bot.sendMessage(
      chatId,
      `
🟢 حالة البوت

📡 Telegram: يعمل
📊 الإشارات: ${sentSignals.size}
📋 الأسهم: ${cachedSymbols.length}
🔎 الفحص: ${scanning ? "جارٍ" : "متوقف"}
⏱ آخر فحص:
${lastScanTime
  ? lastScanTime.toLocaleString("ar-SA")
  : "لم يبدأ"}

━━━━━━━━━━━━
`.trim()
    );
  }
);

// ============================================================
// /refresh
// ============================================================

bot.onText(
  /\/refresh/,
  async msg => {

    const chatId =
      msg.chat.id;

    cachedSymbols = [];

    symbolsCacheTime = 0;

    await bot.sendMessage(
      chatId,
      "🔄 تم مسح قائمة الأسهم وسيتم تحميلها من جديد."
    );
  }
);

// ============================================================
// /stop
// ============================================================

bot.onText(
  /\/stop/,
  async msg => {

    const chatId =
      msg.chat.id;

    sentSignals.clear();

    await bot.sendMessage(
      chatId,
      "🛑 تم مسح الإشارات الحالية."
    );
  }
);

// ============================================================
// تحديث كل X ثانية
// ============================================================

setInterval(
  async () => {

    try {

      await updateSignals();

    } catch (error) {

      console.log(
        "⚠️ خطأ في التحديث:",
        error.message
      );
    }

  },
  UPDATE_INTERVAL_SEC * 1000
);

// ============================================================
// فحص تلقائي
// ============================================================

setInterval(
  async () => {

    console.log(
      "⏰ الفحص التلقائي..."
    );

    // الفحص التلقائي يحتاج Chat IDs
    const chats =
      new Set();

    for (
      const data of sentSignals.values()
    ) {

      for (
        const chatId of data.chatIds || []
      ) {
        chats.add(chatId);
      }
    }

    for (
      const chatId of chats
    ) {

      try {

        await scan(chatId);

      } catch (error) {

        console.log(
          "⚠️ خطأ في الفحص:",
          error.message
        );
      }
    }

  },
  SCAN_INTERVAL_MIN * 60 * 1000
);

// ============================================================
// Express
// ============================================================

app.get(
  "/",
  (req, res) => {

    res.send(
      "🇺🇸 US Stock Telegram Bot — Running"
    );
  }
);

app.get(
  "/health",
  (req, res) => {

    res.json({
      status: "ok",
      signals: sentSignals.size,
      scanning,
      lastScanTime
    });
  }
);

// ============================================================
// تشغيل السيرفر
// ============================================================

app.listen(
  PORT,
  () => {

    console.log(
      `🚀 Server running on port ${PORT}`
    );

    console.log(
      "🤖 Telegram bot is running"
    );

    console.log(
      "📊 EMA + Liquidity + Volume + VWAP enabled"
    );
  }
);