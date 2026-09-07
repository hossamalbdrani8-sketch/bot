
// ============================================================
// 🇸🇦 TASI SENTINEL PRO MAX
// السوق السعودي فقط - TASI / Tadawul
// Node.js 18+
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// ⚙️ الإعدادات
// ============================================================

const TOKEN = process.env.TELEGRAM_TOKEN;

if (!TOKEN) {
  throw new Error("❌ TELEGRAM_TOKEN غير موجود في Railway Variables");
}

const PORT = Number(process.env.PORT || 3000);

const REQUEST_DELAY_MS =
  Number(process.env.REQUEST_DELAY_MS || 350);

const UPDATE_INTERVAL_MIN =
  Number(process.env.UPDATE_INTERVAL_MIN || 2);

const MIN_PRICE =
  Number(process.env.MIN_PRICE || 0.10);

// ============================================================
// 🔐 بوت TASI فقط
// ============================================================

const bot = new TelegramBot(TOKEN, {
  polling: true
});

// ============================================================
// 🌐 Express
// ============================================================

const app = express();

app.get("/", (req, res) => {
  res.status(200).send(
    "🇸🇦 TASI SENTINEL PRO MAX is running"
  );
});

app.get("/health", (req, res) => {
  res.json({
    ok: true,
    market: "TASI",
    country: "Saudi Arabia",
    onlySaudiStocks: true,
    time: new Date().toISOString()
  });
});

app.listen(PORT, () => {
  console.log(
    `🌐 TASI server running on port ${PORT}`
  );
});

// ============================================================
// 🧠 التخزين
// ============================================================

const tasiSignals = new Map();

const newsCache = new Map();

let scanning = false;

let lastScanTime = null;

let lastScanStats = {
  candidates: 0,
  checked: 0,
  accepted: 0,
  errors: 0
};

// ============================================================
// ⏳ Sleep
// ============================================================

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ============================================================
// 🌐 Yahoo Fetch
// ============================================================

async function yahooFetch(url) {

  const response = await fetch(url, {
    headers: {
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",

      "Accept":
        "application/json,text/plain,*/*"
    }
  });

  const text = await response.text();

  if (!response.ok) {
    throw new Error(
      `Yahoo HTTP ${response.status}`
    );
  }

  try {
    return JSON.parse(text);
  } catch {
    throw new Error(
      "Yahoo returned invalid JSON"
    );
  }
}

// ============================================================
// 🇸🇦 حماية TASI
// ============================================================

function isTasiSymbol(symbol) {

  const value =
    String(symbol || "")
      .trim()
      .toUpperCase();

  // TASI في Yahoo = XXXXX.SR
  return /^\d{4}\.SR$/.test(value);
}

// ============================================================
// 📊 قائمة أسهم TASI
// ============================================================

function getTasiSymbols() {

  return [
    "2222.SR",
    "1120.SR",
    "1010.SR",
    "1180.SR",
    "2010.SR",
    "1210.SR",
    "2350.SR",
    "4200.SR",
    "7010.SR",
    "4300.SR",
    "3030.SR",
    "2380.SR",
    "1301.SR",
    "4030.SR",
    "2280.SR",
    "1810.SR",
    "2020.SR",
    "2290.SR",
    "2310.SR",
    "4190.SR",
    "8210.SR",
    "1111.SR",
    "1150.SR",
    "1202.SR",
    "1304.SR",
    "2001.SR",
    "2021.SR",
    "2060.SR",
    "2150.SR",
    "2170.SR",
    "2223.SR",
    "2240.SR",
    "2270.SR",
    "2330.SR",
    "3001.SR",
    "3002.SR",
    "3003.SR",
    "3004.SR",
    "3005.SR",
    "3007.SR",
    "3008.SR",
    "3010.SR"
  ];
}

// ============================================================
// 📊 جلب الشارت
// ============================================================

async function getChart(symbol) {

  // 🔐 حماية نهائية
  if (!isTasiSymbol(symbol)) {
    throw new Error(
      `🚫 ${symbol} ليس سهم TASI`
    );
  }

  const url =
    `https://query1.finance.yahoo.com/v8/finance/chart/` +
    `${encodeURIComponent(symbol)}` +
    `?range=5d` +
    `&interval=5m` +
    `&includePrePost=false` +
    `&events=div%2Csplits`;

  const data =
    await yahooFetch(url);

  const result =
    data?.chart?.result?.[0];

  if (!result) {
    throw new Error(
      "لا توجد بيانات للسهم"
    );
  }

  return result;
}

// ============================================================
// 📈 EMA
// ============================================================

function calculateEMA(values, period) {

  if (
    !Array.isArray(values) ||
    values.length < period
  ) {
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
      (value - ema) *
      multiplier +
      ema;
  }

  return ema;
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

  const len =
    Math.min(
      high.length,
      low.length,
      close.length,
      volume.length
    );

  const start =
    Math.max(0, len - 78);

  let pv = 0;
  let totalVolume = 0;

  for (
    let i = start;
    i < len;
    i++
  ) {

    const h =
      Number(high[i]);

    const l =
      Number(low[i]);

    const c =
      Number(close[i]);

    const v =
      Number(volume[i]);

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
// 💧 السيولة
// ============================================================

function analyzeLiquidity(
  close,
  volume
) {

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

  for (
    let i = start;
    i < len;
    i++
  ) {

    const previous =
      Number(close[i - 1]);

    const current =
      Number(close[i]);

    const vol =
      Number(volume[i]) || 0;

    if (
      !Number.isFinite(previous) ||
      !Number.isFinite(current)
    ) {
      continue;
    }

    if (current > previous) {
      buyVolume += vol;
    } else if (current < previous) {
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
// 📈 الاتجاه العام
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
        label:
          "🟢 الاتجاه العام صاعد"
      };
    }

    if (
      ema50 < ema180 &&
      price < ema50
    ) {

      return {
        bullish: false,
        bearish: true,
        label:
          "🔴 الاتجاه العام هابط"
      };
    }
  }

  return {
    bullish: false,
    bearish: false,
    label:
      "⚪ الاتجاه العام متوازن"
  };
}

// ============================================================
// ⚡ الحركة اللحظية
// ============================================================

function analyzeMovement(
  price,
  ema7,
  ema14,
  vwap
) {

  if (
    !Number.isFinite(price) ||
    !Number.isFinite(ema7) ||
    !Number.isFinite(ema14) ||
    !Number.isFinite(vwap)
  ) {

    return {
      bullish: false,
      bearish: false,
      label:
        "⚪ حركة غير واضحة"
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
      label:
        "⚡ 📈 صعود لحظي"
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
      label:
        "⚡ 📉 هبوط لحظي"
    };
  }

  return {
    bullish: false,
    bearish: false,
    label:
      "⚪ حركة لحظية متوازنة"
  };
}

// ============================================================
// 📊 قوة الحجم
// ============================================================

function calculateVolumeStrength(
  volumes
) {

  const clean =
    volumes
      .map(Number)
      .filter(
        v =>
          Number.isFinite(v) &&
          v >= 0
      );

  if (clean.length < 5) {
    return 0;
  }

  const current =
    clean[clean.length - 1];

  const previous =
    clean.slice(
      Math.max(
        0,
        clean.length - 25
      ),
      clean.length - 1
    );

  if (!previous.length) {
    return 0;
  }

  const average =
    previous.reduce(
      (a, b) => a + b,
      0
    ) / previous.length;

  if (average <= 0) {
    return 0;
  }

  return Math.max(
    0,
    Math.min(
      100,
      (current / average) * 50
    )
  );
}

// ============================================================
// 🧲 التجميع والتصريف
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
// 🔥 النشاط
// ============================================================

function analyzeActivity(
  changePercent,
  volumeStrength,
  buyRatio,
  sellRatio
) {

  const abs =
    Math.abs(changePercent);

  if (
    volumeStrength >= 80 ||
    abs >= 5 ||
    buyRatio >= 75 ||
    sellRatio >= 75
  ) {

    return "🔥 نشاط مرتفع جدًا";
  }

  if (
    volumeStrength >= 60 ||
    abs >= 2 ||
    buyRatio >= 65 ||
    sellRatio >= 65
  ) {

    return "🟠 نشاط مرتفع";
  }

  if (
    volumeStrength >= 40 ||
    abs >= 0.5
  ) {

    return "🟡 نشاط متوسط";
  }

  return "⚪ نشاط منخفض";
}

// ============================================================
// 💥 قوة الإشارة
// ============================================================

function calculateScore({
  price,
  changePercent,
  ema7,
  ema14,
  ema25,
  ema50,
  ema180,
  vwap,
  volumeStrength,
  buyRatio,
  generalTrend,
  movement
}) {

  let score = 0;

  if (
    changePercent >= 0.30
  ) {
    score += 10;
  }

  if (
    price > ema7
  ) {
    score += 10;
  }

  if (
    ema7 > ema14
  ) {
    score += 10;
  }

  if (
    ema14 > ema25
  ) {
    score += 10;
  }

  if (
    ema25 > ema50
  ) {
    score += 10;
  }

  if (
    price > vwap
  ) {
    score += 10;
  }

  if (
    volumeStrength >= 60
  ) {
    score += 15;
  }

  if (
    buyRatio >= 65
  ) {
    score += 15;
  }

  if (
    generalTrend.bullish
  ) {
    score += 5;
  }

  if (
    movement.bullish
  ) {
    score += 5;
  }

  return Math.min(
    100,
    score
  );
}

// ============================================================
// 🚨 الإشارة
// ============================================================

function generateSignal(
  score,
  movement,
  price,
  vwap,
  buyRatio,
  generalTrend
) {

  if (
    score >= 85 &&
    movement.bullish &&
    price > vwap &&
    buyRatio >= 65 &&
    generalTrend.bullish
  ) {

    return "💀🚀 انفجار صعود قوي";
  }

  if (
    score >= 70 &&
    movement.bullish &&
    price > vwap
  ) {

    return "🔥 صعود مؤكد";
  }

  if (
    score >= 55 &&
    movement.bullish &&
    price > vwap
  ) {

    return "🟡 صعود غير مؤكد";
  }

  if (
    movement.bearish &&
    price < vwap
  ) {

    return "🔻 هبوط";
  }

  return "⚪ محايد";
}

// ============================================================
// 🎯 الأهداف
// ============================================================

function calculateTargets(
  price
) {

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

  return percentages.map(
    percent => ({
      percent,
      price:
        price *
        (1 + percent / 100)
    })
  );
}

// ============================================================
// 🌐 ترجمة الخبر للعربية
// ============================================================

async function translateToArabic(
  text
) {

  if (!text) {
    return "لا يوجد عنوان";
  }

  try {

    const url =
      "https://translate.googleapis.com/translate_a/single" +
      "?client=gtx" +
      "&sl=auto" +
      "&tl=ar" +
      "&dt=t" +
      "&q=" +
      encodeURIComponent(text);

    const response =
      await fetch(url);

    if (!response.ok) {
      return text;
    }

    const data =
      await response.json();

    if (
      Array.isArray(data) &&
      Array.isArray(data[0])
    ) {

      return data[0]
        .map(x => x[0])
        .join("");
    }

  } catch (error) {

    console.log(
      `⚠️ Translation error: ${error.message}`
    );
  }

  return text;
}

// ============================================================
// 🧠 تحليل الخبر بالعربي
// ============================================================

function analyzeNewsArabic(
  title
) {

  const text =
    String(title || "")
      .toLowerCase();

  const positive = [
    "ارتفاع",
    "نمو",
    "أرباح",
    "ربح",
    "إيرادات",
    "عقد",
    "اتفاقية",
    "مشروع",
    "توسع",
    "استحواذ",
    "موافقة",
    "ترقية",
    "توزيعات",
    "صفقة",
    "زيادة",
    "تحسن",
    "قوي",
    "إيجابي",
    "growth",
    "profit",
    "revenue",
    "contract",
    "agreement",
    "approval",
    "upgrade",
    "acquisition",
    "partnership",
    "record",
    "strong"
  ];

  const negative = [
    "انخفاض",
    "خسائر",
    "خسارة",
    "هبوط",
    "تراجع",
    "ديون",
    "تحقيق",
    "دعوى",
    "قضية",
    "تحذير",
    "تخفيض",
    "طرح",
    "تخفيف",
    "إفلاس",
    "مشكلة",
    "سلبي",
    "ضعف",
    "decline",
    "loss",
    "lawsuit",
    "investigation",
    "warning",
    "downgrade",
    "debt",
    "offering",
    "dilution",
    "bankruptcy",
    "weak"
  ];

  let positiveScore = 0;
  let negativeScore = 0;

  for (
    const word of positive
  ) {

    if (text.includes(word)) {
      positiveScore++;
    }
  }

  for (
    const word of negative
  ) {

    if (text.includes(word)) {
      negativeScore++;
    }
  }

  if (
    positiveScore > negativeScore
  ) {

    return {
      sentiment: "🟢 إيجابي",
      analysis:
        "الخبر يحمل مؤشرات إيجابية وقد يدعم اهتمام المستثمرين بالسهم، لكن يجب تأكيد أثر الخبر من خلال حركة السعر والسيولة."
    };
  }

  if (
    negativeScore > positiveScore
  ) {

    return {
      sentiment: "🔴 سلبي",
      analysis:
        "الخبر يحمل مؤشرات سلبية وقد يضغط على السهم، ويُفضّل مراقبة السعر والسيولة قبل اتخاذ أي قرار."
    };
  }

  return {
    sentiment: "⚪ محايد",
    analysis:
      "الخبر لا يحتوي على إشارة واضحة للاتجاه، لذلك يعتمد تقييم أثره على حركة السعر والسيولة."
  };
}

// ============================================================
// 📰 التحقق من ارتباط الخبر بالسهم
// ============================================================

function isRelevantNews(
  item,
  symbol,
  companyName
) {

  const title =
    String(
      item?.title || ""
    ).toLowerCase();

  const cleanCompany =
    String(
      companyName || ""
    )
      .toLowerCase()
      .replace(
        /[^a-z0-9\u0600-\u06ff ]/gi,
        " "
      );

  const companyWords =
    cleanCompany
      .split(/\s+/)
      .filter(
        word =>
          word.length >= 4
      );

  const symbolClean =
    String(symbol || "")
      .replace(".SR", "")
      .toLowerCase();

  // الرمز
  if (
    title.includes(symbolClean)
  ) {
    return true;
  }

  // اسم الشركة
  let matches = 0;

  for (
    const word of companyWords
  ) {

    if (
      title.includes(word)
    ) {
      matches++;
    }
  }

  // نحتاج كلمتين من اسم الشركة
  // أو كلمة واحدة قوية
  return matches >= 2;
}

// ============================================================
// 📰 جلب الأخبار المرتبطة بالشركة فقط
// ============================================================

async function getNews(
  symbol,
  companyName
) {

  const cacheKey =
    symbol;

  const cached =
    newsCache.get(cacheKey);

  if (
    cached &&
    Date.now() - cached.time <
      5 * 60 * 1000
  ) {

    return cached.data;
  }

  let news = [];

  try {

    const query =
      `${companyName} ${symbol}`;

    const url =
      `https://query1.finance.yahoo.com/v1/finance/search` +
      `?q=${encodeURIComponent(query)}` +
      `&quotesCount=1` +
      `&newsCount=10` +
      `&enableFuzzyQuery=false`;

    const data =
      await yahooFetch(url);

    const raw =
      Array.isArray(data?.news)
        ? data.news
        : [];

    // 🚫 إزالة الأخبار غير المرتبطة
    const relevant =
      raw.filter(
        item =>
          isRelevantNews(
            item,
            symbol,
            companyName
          )
      );

    for (
      const item of relevant.slice(0, 3)
    ) {

      const originalTitle =
        item.title ||
        "";

      const arabicTitle =
        await translateToArabic(
          originalTitle
        );

      const analysis =
        analyzeNewsArabic(
          arabicTitle
        );

      news.push({

        originalTitle,

        title:
          arabicTitle,

        publisher:
          item.publisher ||
          "Yahoo Finance",

        link:
          item.link ||
          null,

        sentiment:
          analysis.sentiment,

        analysis:
          analysis.analysis
      });

      await sleep(150);
    }

  } catch (error) {

    console.log(
      `⚠️ News ${symbol}: ${error.message}`
    );
  }

  newsCache.set(
    cacheKey,
    {
      time: Date.now(),
      data: news
    }
  );

  return news;
}

// ============================================================
// 📊 بيانات السهم
// ============================================================

async function getStockData(
  symbol
) {

  // 🔐 قفل TASI
  if (!isTasiSymbol(symbol)) {

    throw new Error(
      `🚫 تم رفض ${symbol}: ليس TASI`
    );
  }

  const chart =
    await getChart(symbol);

  const meta =
    chart.meta || {};

  const quote =
    chart.indicators?.quote?.[0];

  if (!quote) {
    throw new Error(
      "لا توجد بيانات الأسعار"
    );
  }

  const close =
    (quote.close || [])
      .map(Number)
      .filter(
        Number.isFinite
      );

  const high =
    (quote.high || [])
      .map(Number)
      .filter(
        Number.isFinite
      );

  const low =
    (quote.low || [])
      .map(Number)
      .filter(
        Number.isFinite
      );

  const volume =
    (quote.volume || [])
      .map(Number)
      .filter(
        Number.isFinite
      );

  if (close.length < 20) {

    throw new Error(
      "بيانات غير كافية"
    );
  }

  const price =
    close[close.length - 1];

  if (
    !Number.isFinite(price) ||
    price < MIN_PRICE
  ) {

    throw new Error(
      "السعر غير صالح"
    );
  }

  const previousClose =
    Number(meta.previousClose) ||
    Number(meta.chartPreviousClose) ||
    close[close.length - 2];

  const changePercent =
    previousClose > 0
      ? (
          (price - previousClose) /
          previousClose
        ) * 100
      : 0;

  // ==========================================================
  // EMA
  // ==========================================================

  const ema7 =
    calculateEMA(close, 7);

  const ema14 =
    calculateEMA(close, 14);

  const ema25 =
    calculateEMA(close, 25);

  const ema50 =
    calculateEMA(close, 50);

  const ema180Raw =
    calculateEMA(close, 180);

  const ema180 =
    ema180Raw !== null
      ? ema180Raw
      : ema50;

  // ==========================================================
  // VWAP
  // ==========================================================

  const vwap =
    calculateVWAP(
      high,
      low,
      close,
      volume
    );

  const effectiveVWAP =
    Number.isFinite(vwap)
      ? vwap
      : price;

  // ==========================================================
  // السيولة
  // ==========================================================

  const liquidity =
    analyzeLiquidity(
      close,
      volume
    );

  // ==========================================================
  // الحجم
  // ==========================================================

  const volumeStrength =
    calculateVolumeStrength(
      volume
    );

  // ==========================================================
  // الاتجاه
  // ==========================================================

  const generalTrend =
    analyzeGeneralTrend(
      price,
      ema50,
      ema180
    );

  // ==========================================================
  // الحركة
  // ==========================================================

  const movement =
    analyzeMovement(
      price,
      ema7,
      ema14,
      effectiveVWAP
    );

  // ==========================================================
  // النشاط
  // ==========================================================

  const activity =
    analyzeActivity(
      changePercent,
      volumeStrength,
      liquidity.buyRatio,
      liquidity.sellRatio
    );

  // ==========================================================
  // التجميع
  // ==========================================================

  const accumulation =
    analyzeAccumulation(
      liquidity.buyRatio,
      liquidity.sellRatio,
      price,
      effectiveVWAP,
      volumeStrength
    );

  // ==========================================================
  // Score
  // ==========================================================

  const score =
    calculateScore({
      price,
      changePercent,
      ema7,
      ema14,
      ema25,
      ema50,
      ema180,
      vwap: effectiveVWAP,
      volumeStrength,
      buyRatio:
        liquidity.buyRatio,
      generalTrend,
      movement
    });

  const signal =
    generateSignal(
      score,
      movement,
      price,
      effectiveVWAP,
      liquidity.buyRatio,
      generalTrend
    );

  // ==========================================================
  // أهداف
  // ==========================================================

  const targets =
    calculateTargets(
      price
    );

  // ==========================================================
  // اسم الشركة
  // ==========================================================

  const companyName =
    meta.longName ||
    meta.shortName ||
    symbol;

  // ==========================================================
  // الأخبار
  // ==========================================================

  const news =
    await getNews(
      symbol,
      companyName
    );

  return {

    symbol,

    price,

    previousClose,

    changePercent,

    companyName,

    exchange:
      "🇸🇦 تداول السعودية",

    country:
      "🇸🇦 المملكة العربية السعودية",

    ema7,
    ema14,
    ema25,
    ema50,
    ema180,

    vwap:
      effectiveVWAP,

    buyRatio:
      liquidity.buyRatio,

    sellRatio:
      liquidity.sellRatio,

    liquidity:
      liquidity.label,

    volumeStrength,

    accumulation,

    activity,

    movement,

    generalTrend,

    score,

    signal,

    targets,

    news,

    updatedAt:
      new Date()
  };
}

// ============================================================
// 💰 تنسيق السعر
// ============================================================

function formatPrice(
  value
) {

  if (
    !Number.isFinite(
      Number(value)
    )
  ) {
    return "0.00";
  }

  const number =
    Number(value);

  return number < 1
    ? number.toFixed(4)
    : number.toFixed(2);
}

// ============================================================
// 📝 رسالة السهم
// ============================================================

function buildMessage(
  stock
) {

  let msg = "";

  msg +=
    `🇸🇦 *TASI SENTINEL PRO MAX*\n\n`;

  msg +=
    `📊 *السوق: السوق السعودي (تاسي)*\n\n`;

  msg +=
    `📌 الرمز: *${stock.symbol.replace(".SR", "")}*\n`;

  msg +=
    `🏢 الشركة: *${stock.companyName}*\n`;

  msg +=
    `🏦 البورصة: *تداول السعودية*\n`;

  msg +=
    `🌎 الدولة: *المملكة العربية السعودية*\n\n`;

  // ==========================================================
  // السعر
  // ==========================================================

  msg +=
    `💰 السعر اللحظي: *${formatPrice(stock.price)}*\n`;

  msg +=
    `📈 التغير: *${stock.changePercent.toFixed(2)}%*\n\n`;

  // ==========================================================
  // الاتجاه
  // ==========================================================

  msg +=
    `🧭 الاتجاه العام: *${stock.generalTrend.label}*\n`;

  msg +=
    `${stock.movement.label}\n`;

  msg +=
    `🔥 نشاط السهم: *${stock.activity}*\n\n`;

  // ==========================================================
  // EMA
  // ==========================================================

  msg +=
    `📊 *المتوسطات EMA*\n`;

  msg +=
    `EMA7: ${formatPrice(stock.ema7)}\n`;

  msg +=
    `EMA14: ${formatPrice(stock.ema14)}\n`;

  msg +=
    `EMA25: ${formatPrice(stock.ema25)}\n`;

  msg +=
    `EMA50: ${formatPrice(stock.ema50)}\n`;

  msg +=
    `EMA180: ${formatPrice(stock.ema180)}\n\n`;

  // ==========================================================
  // VWAP
  // ==========================================================

  msg +=
    `📐 VWAP: *${formatPrice(stock.vwap)}*\n\n`;

  // ==========================================================
  // السيولة
  // ==========================================================

  msg +=
    `💧 *السيولة:* ${stock.liquidity}\n`;

  msg +=
    `🟢 شراء: *${stock.buyRatio.toFixed(1)}%*\n`;

  msg +=
    `🔴 بيع: *${stock.sellRatio.toFixed(1)}%*\n`;

  msg +=
    `📦 قوة الحجم: *${stock.volumeStrength.toFixed(1)}%*\n`;

  msg +=
    `🧲 التجميع/التصريف: *${stock.accumulation}*\n\n`;

  // ==========================================================
  // الإشارة
  // ==========================================================

  msg +=
    `🚨 *الإشارة: ${stock.signal}*\n`;

  msg +=
    `💥 *قوة الإشارة: ${stock.score}/100*\n\n`;

  // ==========================================================
  // الأهداف
  // ==========================================================

  msg +=
    `🎯 *الأهداف السعرية:*\n`;

  for (
    const target of stock.targets
  ) {

    msg +=
      `• +${target.percent}% ➜ *${formatPrice(target.price)}*\n`;
  }

  // ==========================================================
  // الأخبار
  // ==========================================================

  msg +=
    `\n📰 *الأخبار المرتبطة بالسهم:*\n`;

  if (
    !stock.news ||
    stock.news.length === 0
  ) {

    msg +=
      `⚪ لا توجد أخبار موثوقة مرتبطة بالسهم حاليًا.\n`;

  } else {

    for (
      const news of stock.news
    ) {

      msg +=
        `\n${news.sentiment}\n`;

      msg +=
        `📰 *${news.title}*\n`;

      msg +=
        `🧠 *التحليل:* ${news.analysis}\n`;

      msg +=
        `🗞️ المصدر: ${news.publisher}\n`;
    }
  }

  // ==========================================================
  // تحديث
  // ==========================================================

  msg +=
    `\n🕒 التحديث: ${
      stock.updatedAt.toLocaleString(
        "ar-SA"
      )
    }`;

  return msg;
}

// ============================================================
// 🔎 فحص TASI
// ============================================================

async function runTasiScan(
  chatId = null
) {

  if (scanning) {

    if (chatId) {

      await bot.sendMessage(
        chatId,
        "⏳ الفحص يعمل حاليًا، انتظر حتى ينتهي."
      );
    }

    return;
  }

  scanning = true;

  lastScanStats = {
    candidates: 0,
    checked: 0,
    accepted: 0,
    errors: 0
  };

  try {

    const symbols =
      getTasiSymbols()
        .filter(
          isTasiSymbol
        );

    lastScanStats.candidates =
      symbols.length;

    const found = [];

    console.log(
      `🇸🇦 TASI Candidates: ${symbols.length}`
    );

    for (
      const symbol of symbols
    ) {

      lastScanStats.checked++;

      try {

        // 🔐 حماية إضافية
        if (
          !isTasiSymbol(symbol)
        ) {
          continue;
        }

        const data =
          await getStockData(
            symbol
          );

        if (
          data &&
          isTasiSymbol(
            data.symbol
          )
        ) {

          found.push(data);

          lastScanStats.accepted++;
        }

      } catch (error) {

        lastScanStats.errors++;

        console.log(
          `⚠️ ${symbol}: ${error.message}`
        );
      }

      await sleep(
        REQUEST_DELAY_MS
      );
    }

    // ========================================================
    // ترتيب قوة الإشارة
    // ========================================================

    found.sort(
      (a, b) =>
        b.score - a.score
    );

    tasiSignals.clear();

    for (
      const stock of found
    ) {

      // 🔐 لا نحفظ إلا TASI
      if (
        isTasiSymbol(
          stock.symbol
        )
      ) {

        tasiSignals.set(
          stock.symbol,
          stock
        );
      }
    }

    lastScanTime =
      new Date();

    console.log(
      "━━━━━━━━━━━━━━━━━━━━━━━━"
    );

    console.log(
      "🇸🇦 TASI SCAN FINISHED"
    );

    console.log(
      lastScanStats
    );

    // ========================================================
    // إرسال أفضل النتائج
    // ========================================================

    if (chatId) {

      if (!found.length) {

        await bot.sendMessage(
          chatId,
          `🇸🇦 *انتهى فحص تاسي*\n\n` +
          `⚪ لا توجد نتائج قوية حاليًا.\n\n` +
          `🔎 تم فحص: ${lastScanStats.checked}\n` +
          `❌ أخطاء: ${lastScanStats.errors}`,
          {
            parse_mode:
              "Markdown"
          }
        );

      } else {

        const top =
          found.slice(0, 5);

        await bot.sendMessage(
          chatId,
          `🇸🇦 *نتائج فحص تاسي*\n\n` +
          top.map(
            (x, i) =>
              `${i + 1}. *${x.symbol.replace(".SR", "")}*\n` +
              `${x.signal}\n` +
              `💰 ${formatPrice(x.price)} | ` +
              `📈 ${x.changePercent.toFixed(2)}% | ` +
              `💥 ${x.score}/100`
          ).join("\n\n"),
          {
            parse_mode:
              "Markdown"
          }
        );

        // إرسال التفاصيل
        for (
          const stock of top
        ) {

          await sleep(500);

          await bot.sendMessage(
            chatId,
            buildMessage(stock),
            {
              parse_mode:
                "Markdown"
            }
          );
        }
      }
    }

  } catch (error) {

    console.log(
      `❌ TASI Scan Error: ${error.message}`
    );

    if (chatId) {

      await bot.sendMessage(
        chatId,
        `❌ حدث خطأ أثناء فحص تاسي:\n${error.message}`
      );
    }

  } finally {

    scanning = false;
  }
}

// ============================================================
// 🟢 /start
// ============================================================

bot.onText(
  /^\/start$/,
  async msg => {

    await bot.sendMessage(
      msg.chat.id,

      `🇸🇦 *TASI SENTINEL PRO MAX*\n\n` +

      `📊 بوت متخصص في السوق السعودي فقط.\n\n` +

      `🔐 الحماية:\n` +
      `• يسمح فقط بأسهم TASI\n` +
      `• يمنع الأسهم الأمريكية\n` +
      `• يمنع أي رمز غير .SR\n\n` +

      `📈 التحليل:\n` +
      `• EMA 7 / 14 / 25 / 50 / 180\n` +
      `• VWAP\n` +
      `• السيولة\n` +
      `• التجميع والتصريف\n` +
      `• قوة الحجم\n` +
      `• الاتجاه اللحظي والعام\n` +
      `• قوة الإشارة /100\n` +
      `• 8 أهداف سعرية\n\n` +

      `📰 الأخبار:\n` +
      `🟢 إيجابي\n` +
      `🔴 سلبي\n` +
      `⚪ محايد\n` +
      `🇸🇦 ترجمة وتحليل الخبر بالعربي\n\n` +

      `الأوامر:\n` +
      `/scan - فحص تاسي\n` +
      `/signals - الإشارات الحالية\n` +
      `/status - حالة البوت\n` +
      `/stop - مسح الإشارات\n` +
      `/help - المساعدة`,

      {
        parse_mode:
          "Markdown"
      }
    );
  }
);

// ============================================================
// 🔎 /scan
// ============================================================

bot.onText(
  /^\/scan$/,
  async msg => {

    await bot.sendMessage(
      msg.chat.id,
      "🇸🇦 🔎 جاري فحص أسهم السوق السعودي فقط..."
    );

    await runTasiScan(
      msg.chat.id
    );
  }
);

// ============================================================
// 📊 /signals
// ============================================================

bot.onText(
  /^\/signals$/,
  async msg => {

    const chatId =
      msg.chat.id;

    const list =
      Array.from(
        tasiSignals.values()
      )
      .filter(
        stock =>
          isTasiSymbol(
            stock.symbol
          )
      )
      .sort(
        (a, b) =>
          b.score - a.score
      )
      .slice(0, 10);

    if (!list.length) {

      await bot.sendMessage(
        chatId,
        "📭 لا توجد إشارات محفوظة حاليًا.\n\nأرسل /scan"
      );

      return;
    }

    for (
      const stock of list
    ) {

      await bot.sendMessage(
        chatId,
        buildMessage(stock),
        {
          parse_mode:
            "Markdown"
        }
      );

      await sleep(400);
    }
  }
);

// ============================================================
// 🛑 /stop
// ============================================================

bot.onText(
  /^\/stop$/,
  async msg => {

    tasiSignals.clear();

    await bot.sendMessage(
      msg.chat.id,

      `🛑 *تم مسح إشارات تاسي الحالية.*\n\n` +
      `🔎 لإجراء فحص جديد:\n` +
      `/scan`,

      {
        parse_mode:
          "Markdown"
      }
    );
  }
);

// ============================================================
// 📊 /status
// ============================================================

bot.onText(
  /^\/status$/,
  async msg => {

    await bot.sendMessage(
      msg.chat.id,

      `🇸🇦 *حالة TASI SENTINEL*\n\n` +

      `🟢 البوت يعمل\n` +
      `🔐 السوق: TASI فقط\n` +
      `🚫 الأسهم الأمريكية: محظورة\n` +
      `🚫 OTC: محظور\n\n` +

      `🕒 آخر فحص: ${
        lastScanTime
          ? lastScanTime.toLocaleString("ar-SA")
          : "لم يبدأ"
      }\n` +

      `📊 مرشحون: ${lastScanStats.candidates}\n` +
      `🔎 تم فحصهم: ${lastScanStats.checked}\n` +
      `🟢 مقبول: ${lastScanStats.accepted}\n` +
      `❌ أخطاء: ${lastScanStats.errors}\n` +

      `\n📌 إشارات محفوظة: ${tasiSignals.size}`,

      {
        parse_mode:
          "Markdown"
      }
    );
  }
);

// ============================================================
// ℹ️ /help
// ============================================================

bot.onText(
  /^\/help$/,
  async msg => {

    await bot.sendMessage(
      msg.chat.id,

      `🇸🇦 *TASI SENTINEL PRO MAX*\n\n` +

      `/scan\n` +
      `🔎 فحص السوق السعودي\n\n` +

      `/signals\n` +
      `📊 عرض أفضل الإشارات\n\n` +

      `/status\n` +
      `🤖 حالة البوت\n\n` +

      `/stop\n` +
      `🛑 مسح الإشارات\n\n` +

      `📰 الأخبار:\n` +
      `🟢 إيجابي\n` +
      `🔴 سلبي\n` +
      `⚪ محايد\n` +
      `🇸🇦 ترجمة الخبر وتحليله بالعربي\n\n` +

      `🔐 لا يسمح البوت بأي رمز لا ينتهي بـ .SR`,

      {
        parse_mode:
          "Markdown"
      }
    );
  }
);

// ============================================================
// 🔄 فحص تلقائي كل دقيقتين
// ============================================================

setInterval(
  async () => {

    try {

      await runTasiScan();

    } catch (error) {

      console.log(
        `❌ Auto TASI Scan: ${error.message}`
      );
    }

  },
  UPDATE_INTERVAL_MIN * 60 * 1000
);

// ============================================================
// 🟢 التشغيل
// ============================================================

console.log(
  "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
);

console.log(
  "🇸🇦 TASI SENTINEL PRO MAX"
);

console.log(
  "🟢 TASI BOT STARTED"
);

console.log(
  "🔐 TASI ONLY"
);

console.log(
  "🚫 US STOCKS BLOCKED"
);

console.log(
  "📰 ARABIC NEWS ANALYSIS ENABLED"
);

console.log(
  "🟢 POSITIVE / 🔴 NEGATIVE / ⚪ NEUTRAL"
);

console.log(
  "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
);