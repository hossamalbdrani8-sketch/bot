
// ============================================================
// 📊 DUAL AUTONOMOUS STOCK SCANNER BOTS - TASI & US
// EODHD API | FULL TASI + FULL US
// Node.js 18+
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// ⚙️ الإعدادات والمفاتيح الرسمية
// ============================================================

// ضع نفس التوكنات والمفتاح الموجودين لديك
const TASI_TOKEN = "7772382813:AAECFDY04AXNEf-Q98_65UheUEz7u2HymJw";
const US_TOKEN = "8652994768:AAHg_ABByrZdvlljJ1dQfs6LSmBl37XMPXk";
const EODHD_API_KEY = "6a9ef3fd5c9378.52846267";

if (
  !TASI_TOKEN ||
  !US_TOKEN ||
  !EODHD_API_KEY ||
  TASI_TOKEN.startsWith("<") ||
  US_TOKEN.startsWith("<") ||
  EODHD_API_KEY.startsWith("<")
) {
  throw new Error("❌ يرجى التأكد من توفر توكنات البوتين ومفتاح EODHD.");
}

const PORT = Number(process.env.PORT || 3000);

const MIN_PRICE_US = 0.20;
const REQUEST_DELAY_MS = 250;
const UPDATE_INTERVAL_MIN = 2;

// ============================================================
// 🤖 إنشاء البوتين بشكل منفصل
// ============================================================

const tasiBot = new TelegramBot(TASI_TOKEN, {
  polling: true
});

const usBot = new TelegramBot(US_TOKEN, {
  polling: true
});

const tasiSubscribers = new Set();
const usSubscribers = new Set();

// ============================================================
// 🔒 منع تداخل عمليات الفحص
// ============================================================

let tasiScanRunning = false;
let usScanRunning = false;

// ============================================================
// 🌐 خادم Express للحفاظ على التشغيل
// ============================================================

const app = express();

app.get("/", (req, res) => {
  res.status(200).send(
    "🌍 TASI & US EODHD Autonomous Bots are running"
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
// ⏱️ أدوات عامة
// ============================================================

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ============================================================
// 🌐 جلب EODHD
// ============================================================

async function fetchEodhd(url) {
  const response = await fetch(url, {
    headers: {
      "User-Agent": "Mozilla/5.0"
    }
  });

  const text = await response.text();

  if (!response.ok) {
    throw new Error(
      `EODHD HTTP ${response.status}: ${text.slice(0, 150)}`
    );
  }

  try {
    return JSON.parse(text);
  } catch {
    throw new Error("EODHD returned invalid JSON");
  }
}

// ============================================================
// 📋 جلب قائمة الأسهم من EODHD
// ============================================================

async function getExchangeSymbols(exchange) {
  const url =
    `https://eodhd.com/api/exchange-symbol-list/${exchange}` +
    `?api_token=${EODHD_API_KEY}&fmt=json`;

  const data = await fetchEodhd(url);

  if (!Array.isArray(data)) {
    throw new Error(
      `لم يتم استلام قائمة صحيحة للسوق ${exchange}`
    );
  }

  return data;
}

// ============================================================
// 🇸🇦 قائمة تاسي الكاملة
// ============================================================

async function getFullTasiSymbols() {
  const rows = await getExchangeSymbols("SR");

  const symbols = rows
    .filter(item => {
      const type = String(item.Type || "").toLowerCase();

      return (
        type.includes("stock") ||
        type.includes("common")
      );
    })
    .map(item => String(item.Code || "").trim())
    .filter(Boolean);

  return [...new Set(symbols)];
}

// ============================================================
// 🇺🇸 قائمة السوق الأمريكي الكاملة
// ============================================================

async function getFullUsSymbols() {
  const rows = await getExchangeSymbols("US");

  const symbols = rows
    .filter(item => {
      const type = String(item.Type || "").toLowerCase();

      return (
        type.includes("stock") ||
        type.includes("common") ||
        type.includes("preferred")
      );
    })
    .map(item => String(item.Code || "").trim())
    .filter(Boolean);

  return [...new Set(symbols)];
}

// ============================================================
// 🔧 تجهيز رمز السهم لـ EODHD
// ============================================================

function normalizeTickerForEodhd(symbol) {
  return String(symbol || "")
    .trim()
    .replace(/\./g, "-");
}

// ============================================================
// 📊 حساب EMA
// ============================================================

function calculateEMA(values, period) {
  if (!Array.isArray(values) || values.length < period) {
    return null;
  }

  const multiplier = 2 / (period + 1);

  let ema = 0;

  for (let i = 0; i < period; i++) {
    ema += Number(values[i]) || 0;
  }

  ema /= period;

  for (let i = period; i < values.length; i++) {
    const val = Number(values[i]);

    if (Number.isFinite(val)) {
      ema = (val - ema) * multiplier + ema;
    }
  }

  return ema;
}

// ============================================================
// 📐 VWAP
// ============================================================

function calculateVWAP(high, low, close, volume) {
  let pv = 0;
  let totalVolume = 0;

  const len = Math.min(
    high.length,
    low.length,
    close.length,
    volume.length
  );

  const start = Math.max(0, len - 30);

  for (let i = start; i < len; i++) {
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

    pv += ((h + l + c) / 3) * v;
    totalVolume += v;
  }

  return totalVolume > 0
    ? pv / totalVolume
    : null;
}

// ============================================================
// 💧 تحليل السيولة
// ============================================================

function analyzeLiquidity(close, volume) {
  const len = Math.min(
    close.length,
    volume.length
  );

  const start = Math.max(1, len - 10);

  let buyVol = 0;
  let sellVol = 0;
  let neutVol = 0;

  for (let i = start; i < len; i++) {
    const prev = Number(close[i - 1]);
    const curr = Number(close[i]);
    const vol = Number(volume[i]) || 0;

    if (
      !Number.isFinite(prev) ||
      !Number.isFinite(curr)
    ) {
      continue;
    }

    if (curr > prev) {
      buyVol += vol;
    } else if (curr < prev) {
      sellVol += vol;
    } else {
      neutVol += vol;
    }
  }

  const total =
    buyVol +
    sellVol +
    neutVol;

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

  let label = "⚪ سيولة متوازنة";

  if (buyRatio >= 65) {
    label = "🟢 دخول سيولة قوية";
  } else if (sellRatio >= 65) {
    label = "🔴 خروج سيولة قوية";
  } else if (buyRatio >= 53) {
    label = "🟢 دخول سيولة";
  } else if (sellRatio >= 53) {
    label = "🔴 خروج سيولة";
  }

  return {
    buyRatio,
    sellRatio,
    label
  };
}

// ============================================================
// 🧭 الاتجاه العام
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
      return "🟢 الاتجاه العام صاعد";
    }

    if (
      ema50 < ema180 &&
      price < ema50
    ) {
      return "🔴 الاتجاه العام هابط";
    }
  }

  return "⚪ الاتجاه العام متوازن";
}

// ============================================================
// 📉 الدعوم والمقاومات
// ============================================================

function calculateSupportResistance(
  highs,
  lows,
  price
) {
  const pivotHighs = [];
  const pivotLows = [];

  const leftRight = 3;

  for (
    let i = leftRight;
    i < highs.length - leftRight;
    i++
  ) {
    const currentHigh =
      Number(highs[i]);

    const currentLow =
      Number(lows[i]);

    if (
      !Number.isFinite(currentHigh) ||
      !Number.isFinite(currentLow)
    ) {
      continue;
    }

    let isHigh = true;
    let isLow = true;

    for (
      let j = 1;
      j <= leftRight;
      j++
    ) {
      if (
        currentHigh <= Number(highs[i - j]) ||
        currentHigh <= Number(highs[i + j])
      ) {
        isHigh = false;
      }

      if (
        currentLow >= Number(lows[i - j]) ||
        currentLow >= Number(lows[i + j])
      ) {
        isLow = false;
      }
    }

    if (isHigh) {
      pivotHighs.push(currentHigh);
    }

    if (isLow) {
      pivotLows.push(currentLow);
    }
  }

  const tolerance =
    Math.max(
      price * 0.003,
      0.01
    );

  function clusterLevels(levels) {
    const sorted =
      [...levels].sort((a, b) => a - b);

    const clusters = [];

    for (const level of sorted) {
      const last =
        clusters[clusters.length - 1];

      if (
        !last ||
        Math.abs(
          level - last.price
        ) > tolerance
      ) {
        clusters.push({
          price: level,
          count: 1
        });
      } else {
        last.price =
          (
            last.price * last.count +
            level
          ) /
          (last.count + 1);

        last.count++;
      }
    }

    return clusters;
  }

  const supportClusters =
    clusterLevels(
      pivotLows.filter(
        level => level < price
      )
    );

  const resistanceClusters =
    clusterLevels(
      pivotHighs.filter(
        level => level > price
      )
    );

  const supports =
    supportClusters
      .sort(
        (a, b) =>
          b.price - a.price
      )
      .slice(0, 3)
      .map(x => x.price);

  const resistances =
    resistanceClusters
      .sort(
        (a, b) =>
          a.price - b.price
      )
      .slice(0, 3)
      .map(x => x.price);

  return {
    supports,
    resistances
  };
}

// ============================================================
// 🎯 الأهداف السعرية
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

  return percentages.map(p => {
    const targetPrice =
      price * (1 + p / 100);

    const achieved =
      price >= targetPrice;

    return {
      percent: p,
      price: targetPrice,
      achieved
    };
  });
}

// ============================================================
// 📰 قاموس مصادر الأخبار بالعربي
// ============================================================

const sourceArabicMap = {
  "Reuters": "رويترز",
  "Bloomberg": "بلومبرغ",
  "Yahoo Finance": "ياهو المالية",
  "MarketWatch": "ماركت ووتش",
  "CNBC": "سي إن بي سي",
  "Business Wire": "بيزنس واير",
  "GlobeNewswire": "غلوب نيوز واير",
  "PR Newswire": "بي آر نيوزواير",
  "Seeking Alpha": "سيكنغ ألفا",
  "Benzinga": "بنزينغا",
  "The Motley Fool": "ذا موتلي فول",
  "Investing.com": "إنفستنج",
  "Barron's": "بارونز",
  "Forbes": "فوربس",
  "Associated Press": "أسوشيتد برس"
};

// ============================================================
// 🌐 تعريب اسم المصدر
// ============================================================

function translateSourceToArabic(source) {
  if (!source) {
    return "مصدر مالي";
  }

  const clean =
    String(source).trim();

  if (sourceArabicMap[clean]) {
    return sourceArabicMap[clean];
  }

  return clean;
}

// ============================================================
// 🌐 ترجمة الخبر إلى العربية
//
// تستخدم خدمة ترجمة عامة لترجمة العنوان فقط.
// إذا تعذر الاتصال، يعاد النص الأصلي حتى لا يتوقف البوت.
// ============================================================

async function translateToArabic(text) {
  if (!text) {
    return "";
  }

  const original =
    String(text).trim();

  if (!original) {
    return "";
  }

  // إذا كان النص عربيًا بالفعل
  if (
    /[\u0600-\u06FF]/.test(original)
  ) {
    return original;
  }

  try {
    const url =
      "https://translate.googleapis.com/translate_a/single" +
      "?client=gtx" +
      "&sl=auto" +
      "&tl=ar" +
      "&dt=t" +
      "&q=" +
      encodeURIComponent(original);

    const response =
      await fetch(url);

    if (!response.ok) {
      return original;
    }

    const data =
      await response.json();

    if (
      Array.isArray(data) &&
      Array.isArray(data[0])
    ) {
      return data[0]
        .map(part =>
          Array.isArray(part)
            ? part[0]
            : ""
        )
        .join("")
        .trim() || original;
    }

    return original;
  } catch {
    return original;
  }
}

// ============================================================
// 📰 جلب أخبار السهم
// ============================================================

const newsCache = new Map();

const NEWS_CACHE_MS =
  5 * 60 * 1000;

async function getStockNews(symbol, exchange) {
  const cleanSymbol =
    normalizeTickerForEodhd(symbol);

  const ticker =
    `${cleanSymbol}.${exchange}`;

  const cached =
    newsCache.get(ticker);

  if (
    cached &&
    Date.now() - cached.time <
      NEWS_CACHE_MS
  ) {
    return cached.news;
  }

  const url =
    "https://eodhd.com/api/news" +
    `?s=${encodeURIComponent(ticker)}` +
    `&offset=0` +
    `&limit=3` +
    `&api_token=${EODHD_API_KEY}` +
    `&fmt=json`;

  try {
    const data =
      await fetchEodhd(url);

    if (!Array.isArray(data)) {
      return [];
    }

    const news = [];

    for (
      const item of data.slice(0, 3)
    ) {
      const originalTitle =
        item.title ||
        item.content ||
        "";

      const title =
        await translateToArabic(
          originalTitle
        );

      const source =
        translateSourceToArabic(
          item.source ||
          item.site ||
          item.domain ||
          ""
        );

      news.push({
        title,
        source,
        date:
          item.date ||
          item.publishedAt ||
          ""
      });
    }

    newsCache.set(
      ticker,
      {
        time: Date.now(),
        news
      }
    );

    return news;
  } catch {
    return [];
  }
}

// ============================================================
// 📊 جلب بيانات السهم
// ============================================================

async function getStockDataFromEodhd(
  symbol,
  exchangeSuffix,
  minPriceAllowed
) {
  const cleanSymbol =
    normalizeTickerForEodhd(symbol);

  const ticker =
    `${cleanSymbol}.${exchangeSuffix}`;

  const url =
    `https://eodhistoricaldata.com/api/eod/${ticker}` +
    `?api_token=${EODHD_API_KEY}` +
    `&fmt=json` +
    `&period=d` +
    `&limit=200`;

  const data =
    await fetchEodhd(url);

  if (
    !Array.isArray(data) ||
    data.length < 50
  ) {
    throw new Error(
      "بيانات غير كافية من EODHD"
    );
  }

  const closes =
    data
      .map(item =>
        Number(item.close)
      )
      .filter(Number.isFinite);

  const highs =
    data
      .map(item =>
        Number(item.high)
      )
      .filter(Number.isFinite);

  const lows =
    data
      .map(item =>
        Number(item.low)
      )
      .filter(Number.isFinite);

  const volumes =
    data
      .map(item =>
        Number(item.volume)
      )
      .filter(Number.isFinite);

  const price =
    closes[closes.length - 1];

  if (
    !Number.isFinite(price) ||
    price < minPriceAllowed
  ) {
    throw new Error(
      "السعر أقل من الحد الأدنى"
    );
  }

  const prevClose =
    closes[closes.length - 2] ||
    price;

  const changePercent =
    prevClose > 0
      ? ((price - prevClose) /
          prevClose) *
        100
      : 0;

  // ========================================================
  // EMA
  // ========================================================

  const ema7 =
    calculateEMA(closes, 7);

  const ema14 =
    calculateEMA(closes, 14);

  const ema25 =
    calculateEMA(closes, 25);

  const ema50 =
    calculateEMA(closes, 50);

  const ema180 =
    calculateEMA(closes, 180) ||
    ema50;

  // ========================================================
  // VWAP
  // ========================================================

  const vwap =
    calculateVWAP(
      highs,
      lows,
      closes,
      volumes
    ) || price;

  // ========================================================
  // السيولة
  // ========================================================

  const liquidity =
    analyzeLiquidity(
      closes,
      volumes
    );

  // ========================================================
  // الاتجاه
  // ========================================================

  const generalTrend =
    analyzeGeneralTrend(
      price,
      ema50,
      ema180
    );

  // ========================================================
  // الدعوم والمقاومات
  // ========================================================

  const levels =
    calculateSupportResistance(
      highs,
      lows,
      price
    );

  // ========================================================
  // الأهداف
  // ========================================================

  const targets =
    calculateTargets(price);

  // ========================================================
  // الأخبار
  // ========================================================

  const news =
    await getStockNews(
      symbol,
      exchangeSuffix
    );

  return {
    symbol,
    price,
    changePercent,

    companyName: symbol,

    exchange:
      exchangeSuffix === "SR"
        ? "تداول (تاسي)"
        : "السوق الأمريكي",

    vwap,

    ema7,
    ema14,
    ema25,
    ema50,
    ema180,

    buyRatio:
      liquidity.buyRatio,

    sellRatio:
      liquidity.sellRatio,

    liquidityLabel:
      liquidity.label,

    generalTrend,

    supports:
      levels.supports,

    resistances:
      levels.resistances,

    targets,

    news,

    updatedAt:
      new Date()
  };
}

// ============================================================
// 📰 بناء قسم الأخبار
// ============================================================

function buildNewsSection(news) {
  if (
    !Array.isArray(news) ||
    news.length === 0
  ) {
    return (
      "📰 *الأخبار:*\n" +
      "• لا توجد أخبار متاحة حاليًا\n\n"
    );
  }

  let msg =
    "📰 *آخر الأخبار:*\n";

  for (
    const item of news
  ) {
    msg +=
      `• ${item.title}\n` +
      `  🏷️ المصدر: ${item.source}\n`;

    if (item.date) {
      msg +=
        `  🕒 ${item.date}\n`;
    }

    msg += "\n";
  }

  return msg;
}

// ============================================================
// 📉 بناء قسم الدعوم والمقاومات
// ============================================================

function buildSupportResistanceSection(
  stock
) {
  let msg =
    "📉 *الدعوم والمقاومات:*\n\n";

  if (
    stock.supports &&
    stock.supports.length
  ) {
    msg += "🟢 *الدعوم:*\n";

    stock.supports.forEach(
      (level, index) => {
        msg +=
          `• دعم ${index + 1}: *${level.toFixed(2)}*\n`;
      }
    );
  } else {
    msg +=
      "🟢 *الدعوم:* لا يوجد مستوى واضح\n";
  }

  msg += "\n";

  if (
    stock.resistances &&
    stock.resistances.length
  ) {
    msg += "🔴 *المقاومات:*\n";

    stock.resistances.forEach(
      (level, index) => {
        msg +=
          `• مقاومة ${index + 1}: *${level.toFixed(2)}*\n`;
      }
    );
  } else {
    msg +=
      "🔴 *المقاومات:* لا يوجد مستوى واضح\n";
  }

  msg += "\n";

  return msg;
}

// ============================================================
// 📊 رسالة السهم
// ============================================================

function buildMessage(
  stock,
  marketName
) {
  let msg =
    `📊 *${marketName}*\n\n`;

  msg +=
    `📌 الرمز: *${stock.symbol}*\n`;

  msg +=
    `🏢 الشركة: ${stock.companyName}\n\n`;

  msg +=
    `💰 السعر: *${stock.price.toFixed(2)}*\n`;

  msg +=
    `📈 نسبة التغير: *${stock.changePercent.toFixed(2)}%*\n`;

  msg +=
    `🏦 السوق: ${stock.exchange}\n\n`;

  msg +=
    `🧭 ${stock.generalTrend}\n`;

  msg +=
    `📐 VWAP: *${stock.vwap.toFixed(2)}*\n`;

  msg +=
    `💧 السيولة: *${stock.liquidityLabel}* ` +
    `(شراء ${stock.buyRatio.toFixed(1)}% | ` +
    `بيع ${stock.sellRatio.toFixed(1)}%)\n\n`;

  // ========================================================
  // الدعوم والمقاومات
  // ========================================================

  msg +=
    buildSupportResistanceSection(
      stock
    );

  // ========================================================
  // EMA
  // ========================================================

  msg +=
    `📊 *المتوسطات الأسية EMA:*\n`;

  msg +=
    `• EMA 7: ${
      stock.ema7
        ? stock.ema7.toFixed(2)
        : "N/A"
    }\n`;

  msg +=
    `• EMA 14: ${
      stock.ema14
        ? stock.ema14.toFixed(2)
        : "N/A"
    }\n`;

  msg +=
    `• EMA 25: ${
      stock.ema25
        ? stock.ema25.toFixed(2)
        : "N/A"
    }\n`;

  msg +=
    `• EMA 50: ${
      stock.ema50
        ? stock.ema50.toFixed(2)
        : "N/A"
    }\n`;

  msg +=
    `• EMA 180: ${
      stock.ema180
        ? stock.ema180.toFixed(2)
        : "N/A"
    }\n\n`;

  // ========================================================
  // الأهداف
  // ========================================================

  msg +=
    `🎯 *الأهداف السعرية:*\n`;

  for (
    const t of stock.targets
  ) {
    const statusMark =
      t.achieved
        ? " ✅"
        : "";

    msg +=
      `• +${t.percent}% ➔ *${t.price.toFixed(2)}*${statusMark}\n`;
  }

  msg += "\n";

  // ========================================================
  // الأخبار
  // ========================================================

  msg +=
    buildNewsSection(
      stock.news
    );

  msg +=
    `🕒 التحديث: ${stock.updatedAt.toLocaleTimeString("ar-SA")}`;

  return msg;
}

// ============================================================
// 🇸🇦 الفحص الكامل للسوق السعودي
// ============================================================

async function runTasiAutoScan() {
  if (
    tasiScanRunning ||
    tasiSubscribers.size === 0
  ) {
    return;
  }

  tasiScanRunning = true;

  try {
    console.log(
      "🇸🇦 بدء الفحص الكامل لتاسي..."
    );

    const symbols =
      await getFullTasiSymbols();

    console.log(
      `🇸🇦 عدد أسهم تاسي المستلمة: ${symbols.length}`
    );

    for (
      const sym of symbols
    ) {
      try {
        const stock =
          await getStockDataFromEodhd(
            sym,
            "SR",
            0.01
          );

        if (stock) {
          for (
            const chatId of tasiSubscribers
          ) {
            await tasiBot.sendMessage(
              chatId,
              buildMessage(
                stock,
                "🇸🇦 السوق السعودي (تاسي)"
              ),
              {
                parse_mode: "Markdown"
              }
            );

            await sleep(200);
          }
        }
      } catch (e) {
        console.log(
          `⚠️ TASI ${sym}: ${e.message}`
        );
      }

      await sleep(
        REQUEST_DELAY_MS
      );
    }

    console.log(
      "✅ انتهى فحص تاسي الكامل."
    );

  } finally {
    tasiScanRunning = false;
  }
}

// ============================================================
// 🇺🇸 الفحص الكامل للسوق الأمريكي
// ============================================================

async function runUsAutoScan() {
  if (
    usScanRunning ||
    usSubscribers.size === 0
  ) {
    return;
  }

  usScanRunning = true;

  try {
    console.log(
      "🇺🇸 بدء الفحص الكامل للسوق الأمريكي..."
    );

    const symbols =
      await getFullUsSymbols();

    console.log(
      `🇺🇸 عدد الرموز الأمريكية المستلمة: ${symbols.length}`
    );

    for (
      const sym of symbols
    ) {
      try {
        const stock =
          await getStockDataFromEodhd(
            sym,
            "US",
            MIN_PRICE_US
          );

        if (stock) {
          for (
            const chatId of usSubscribers
          ) {
            await usBot.sendMessage(
              chatId,
              buildMessage(
                stock,
                "🇺🇸 السوق الأمريكي"
              ),
              {
                parse_mode: "Markdown"
              }
            );

            await sleep(200);
          }
        }

      } catch (e) {
        // الأسهم تحت $0.20 أو التي لا توجد لها بيانات
        // يتم تجاوزها بدون إيقاف الفحص الكامل.
      }

      await sleep(
        REQUEST_DELAY_MS
      );
    }

    console.log(
      "✅ انتهى فحص السوق الأمريكي الكامل."
    );

  } finally {
    usScanRunning = false;
  }
}

// ============================================================
// 🤖 أوامر بوت تاسي
// ============================================================

tasiBot.onText(
  /\/start/,
  async msg => {
    const chatId =
      msg.chat.id;

    tasiSubscribers.add(
      chatId
    );

    await tasiBot.sendMessage(
      chatId,
      "🇸🇦 *تم تفعيل بوت السوق السعودي عبر EODHD بنجاح!*\n\n" +
      "📊 سيتم فحص السوق السعودي بالكامل.\n" +
      "📉 الدعوم والمقاومات مفعلة.\n" +
      "📰 الأخبار والمصدر بالعربي.",
      {
        parse_mode: "Markdown"
      }
    );

    runTasiAutoScan();
  }
);

// ============================================================
// 🔍 فحص تاسي يدوي
// ============================================================

tasiBot.onText(
  /\/scan/,
  async msg => {
    const chatId =
      msg.chat.id;

    tasiSubscribers.add(
      chatId
    );

    await tasiBot.sendMessage(
      chatId,
      "🔍 جاري الفحص الكامل لأسهم تاسي..."
    );

    await runTasiAutoScan();
  }
);

// ============================================================
// 🤖 أوامر بوت US
// ============================================================

usBot.onText(
  /\/start/,
  async msg => {
    const chatId =
      msg.chat.id;

    usSubscribers.add(
      chatId
    );

    await usBot.sendMessage(
      chatId,
      "🇺🇸 *تم تفعيل بوت السوق الأمريكي عبر EODHD بنجاح!*\n\n" +
      "📊 سيتم فحص السوق الأمريكي بالكامل.\n" +
      "💵 الحد الأدنى للسعر: $0.20\n" +
      "📉 الدعوم والمقاومات مفعلة.\n" +
      "📰 الأخبار والمصدر بالعربي.",
      {
        parse_mode: "Markdown"
      }
    );

    runUsAutoScan();
  }
);

// ============================================================
// 🔍 فحص US يدوي
// ============================================================

usBot.onText(
  /\/scan/,
  async msg => {
    const chatId =
      msg.chat.id;

    usSubscribers.add(
      chatId
    );

    await usBot.sendMessage(
      chatId,
      "🔍 جاري الفحص الكامل للأسهم الأمريكية من $0.20 فأعلى..."
    );

    await runUsAutoScan();
  }
);

// ============================================================
// 🔄 الجدولة التلقائية
// ============================================================

setInterval(
  runTasiAutoScan,
  UPDATE_INTERVAL_MIN * 60 * 1000
);

setInterval(
  runUsAutoScan,
  UPDATE_INTERVAL_MIN * 60 * 1000
);

// ============================================================
// 🟢 تشغيل
// ============================================================

console.log(
  "🟢 EODHD Stock Scanners are running successfully!"
);

console.log(
  "🇸🇦 TASI: FULL SCAN"
);

console.log(
  "🇺🇸 US: FULL SCAN >= $0.20"
);

console.log(
  "📉 Support / Resistance: ON"
);

console.log(
  "📰 Arabic News / Arabic Source: ON"
);