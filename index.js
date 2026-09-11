
"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// 🚀 AI PRO MAX
// 🇸🇦 TASI + 🇺🇸 NASDAQ + 🪙 CRYPTO
// بوت واحد = 3 بوتات مستقلة
// ============================================================

const PORT = Number(process.env.PORT || 8080);

const EODHD_API_KEY =
  process.env.EODHD_API_KEY ||
  process.env.EODHD_TOKEN ||
  process.env.EODHD_API_TOKEN ||
  "";

const SCAN_MINUTES = Math.max(
  1,
  Number(process.env.SCAN_MINUTES || 5)
);

const REQUEST_DELAY_MS = Math.max(
  250,
  Number(process.env.REQUEST_DELAY_MS || 350)
);

const SYMBOLS_PER_CYCLE = Math.max(
  1,
  Number(process.env.SYMBOLS_PER_CYCLE || 20)
);

const MIN_US_PRICE = Number(
  process.env.MIN_US_PRICE || 0.20
);

const MAX_ALERTS_PER_CYCLE = Math.max(
  1,
  Number(process.env.MAX_ALERTS_PER_CYCLE || 20)
);


// ============================================================
// 🔐 قراءة المتغيرات الموجودة عندك
// ============================================================

function getEnv(names) {
  for (const name of names) {
    const value = process.env[name];

    if (
      value !== undefined &&
      value !== null &&
      String(value).trim() !== ""
    ) {
      return String(value).trim();
    }
  }

  return "";
}


// ============================================================
// 🔑 استخراج Token من القيمة
// يقبل Token مباشر أو JSON
// ============================================================

function extractToken(value) {

  if (!value) return "";

  const text = String(value).trim();

  // Token مباشر
  if (!text.startsWith("{")) {
    return text;
  }

  // JSON
  try {

    const obj = JSON.parse(text);

    return String(
      obj.token ||
      obj.telegramToken ||
      obj.TELEGRAM_TOKEN ||
      obj.botToken ||
      ""
    ).trim();

  } catch {

    return "";
  }
}


// ============================================================
// 🤖 Tokens البوتات الثلاثة
// ============================================================

const TOKENS = {

  tasi: extractToken(
    getEnv([
      "TELEGRAM_TASI_TOKEN",
      "TASI_TELEGRAM_TOKEN",
      "TASI_BOT_TOKEN",
      "TASI_CONFIG"
    ])
  ),

  us: extractToken(
    getEnv([
      "TELEGRAM_US_TOKEN",
      "US_TELEGRAM_TOKEN",
      "US_BOT_TOKEN",
      "US_CONFIG"
    ])
  ),

  crypto: extractToken(
    getEnv([
      "TELEGRAM_CRYPTO_TOKEN",
      "CRYPTO_TELEGRAM_TOKEN",
      "CRYPTO_BOT_TOKEN",
      "CRYPTO_CONFIG"
    ])
  )
};


// ============================================================
// 💬 Chat IDs
// يمكن للبوت أخذ Chat ID تلقائياً بعد /start
// ============================================================

const CHAT_IDS = {

  tasi: getEnv([
    "TASI_CHAT_ID",
    "TELEGRAM_TASI_CHAT_ID"
  ]),

  us: getEnv([
    "US_CHAT_ID",
    "TELEGRAM_US_CHAT_ID"
  ]),

  crypto: getEnv([
    "CRYPTO_CHAT_ID",
    "TELEGRAM_CRYPTO_CHAT_ID"
  ])

};


// ============================================================
// 🧠 حالة كل سوق
// ============================================================

const state = {

  tasi: {
    symbols: [],
    cursor: 0,
    sent: new Set()
  },

  us: {
    symbols: [],
    cursor: 0,
    sent: new Set()
  },

  crypto: {
    symbols: [],
    cursor: 0,
    sent: new Set()
  }

};


const bots = {};


// ============================================================
// ⏱️ أدوات
// ============================================================

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}


function number(value) {

  const n = Number(value);

  return Number.isFinite(n) ? n : 0;
}


function average(values) {

  if (!values.length) return 0;

  return values.reduce(
    (a, b) => a + b,
    0
  ) / values.length;
}


function formatPrice(value) {

  const n = number(value);

  if (n >= 100) {
    return n.toFixed(2);
  }

  if (n >= 1) {
    return n.toFixed(3);
  }

  return n.toFixed(5);
}


function clean(value) {

  return String(value || "")
    .replace(/[<>]/g, "");
}


// ============================================================
// 🌐 EODHD
// ============================================================

async function eodhd(path, params = {}) {

  if (!EODHD_API_KEY) {
    throw new Error("EODHD_API_KEY غير موجود");
  }

  const query = new URLSearchParams({

    ...params,

    api_token: EODHD_API_KEY,

    fmt: "json"

  });

  const url =
    `https://eodhd.com/api/${path}?${query}`;

  const response = await fetch(url);

  const text = await response.text();

  if (!response.ok) {

    throw new Error(
      `EODHD HTTP ${response.status}`
    );

  }

  try {

    return JSON.parse(text);

  } catch {

    return [];

  }

}


// ============================================================
// 📈 EMA
// ============================================================

function EMA(values, length) {

  if (!values.length) return 0;

  const multiplier =
    2 / (length + 1);

  let ema = values[0];

  for (let i = 1; i < values.length; i++) {

    ema =
      values[i] * multiplier +
      ema * (1 - multiplier);

  }

  return ema;
}


// ============================================================
// 📏 ATR(14)
// ============================================================

function ATR(bars, length = 14) {

  if (bars.length < 2) {
    return 0;
  }

  const trueRanges = [];

  for (
    let i = 1;
    i < bars.length;
    i++
  ) {

    const high =
      number(bars[i].high);

    const low =
      number(bars[i].low);

    const previousClose =
      number(bars[i - 1].close);

    const tr =
      Math.max(
        high - low,
        Math.abs(high - previousClose),
        Math.abs(low - previousClose)
      );

    trueRanges.push(tr);

  }

  return average(
    trueRanges.slice(-length)
  );

}


// ============================================================
// 📊 RSI
// ============================================================

function RSI(closes, length = 14) {

  if (closes.length <= length) {
    return 50;
  }

  let gain = 0;
  let loss = 0;

  for (
    let i = closes.length - length;
    i < closes.length;
    i++
  ) {

    const change =
      closes[i] - closes[i - 1];

    if (change >= 0) {
      gain += change;
    } else {
      loss -= change;
    }

  }

  if (loss === 0) {
    return 100;
  }

  const rs =
    (gain / length) /
    (loss / length);

  return 100 - (100 / (1 + rs));

}


// ============================================================
// 📍 الدعم والمقاومة
// ============================================================

function supportResistance(bars) {

  const lows =
    bars
      .map(b => number(b.low))
      .filter(v => v > 0)
      .slice(-30);

  const highs =
    bars
      .map(b => number(b.high))
      .filter(v => v > 0)
      .slice(-30);

  return {

    support:
      lows.length
        ? Math.min(...lows)
        : 0,

    resistance:
      highs.length
        ? Math.max(...highs)
        : 0

  };

}


// ============================================================
// 💧 السيولة / قوة الحجم
// ============================================================

function volumeStrength(bars) {

  const volumes =
    bars
      .map(b => number(b.volume))
      .filter(v => v > 0)
      .slice(-21);

  if (volumes.length < 2) {
    return 1;
  }

  const current =
    volumes[volumes.length - 1];

  const previous =
    average(
      volumes.slice(0, -1)
    );

  if (!previous) {
    return 1;
  }

  return current / previous;

}


// ============================================================
// 🧠 تحليل AI PRO MAX
// ============================================================

function analyze(bars) {

  const closes =
    bars
      .map(b => number(b.close))
      .filter(v => v > 0);

  if (closes.length < 20) {
    return null;
  }

  const price =
    closes[closes.length - 1];

  const ema8 =
    EMA(closes, 8);

  const ema21 =
    EMA(closes, 21);

  const ema50 =
    EMA(closes, 50);

  const ema200 =
    EMA(closes, 200);

  const atr =
    ATR(bars, 14) ||
    price * 0.01;

  const rsi =
    RSI(closes, 14);

  const sr =
    supportResistance(bars);

  const liquidity =
    volumeStrength(bars);


  // ==========================================================
  // 🧠 الاتجاه
  // ==========================================================

  const bullish =
    ema8 > ema21 &&
    ema21 >= ema50 &&
    price >= ema21;

  const bearish =
    ema8 < ema21 &&
    ema21 <= ema50 &&
    price <= ema21;


  let trend = "محايد";

  if (bullish) {
    trend = "صاعد";
  }

  if (bearish) {
    trend = "هابط";
  }


  // ==========================================================
  // 💪 قوة الاتجاه
  // ==========================================================

  let power =
    50 +
    ((rsi - 50) * 0.7);

  if (ema8 > ema21) {
    power += 10;
  } else {
    power -= 10;
  }

  power =
    Math.max(
      0,
      Math.min(
        100,
        power
      )
    );


  // ==========================================================
  // 🎯 8 أهداف ATR
  // ==========================================================

  const targets = [];

  for (
    let i = 1;
    i <= 8;
    i++
  ) {

    if (trend === "صاعد") {

      targets.push(
        price + atr * i
      );

    } else if (trend === "هابط") {

      targets.push(
        price - atr * i
      );

    } else {

      targets.push(
        price + atr * i
      );

    }

  }


  return {

    price,

    ema8,

    ema21,

    ema50,

    ema200,

    atr,

    rsi,

    support: sr.support,

    resistance: sr.resistance,

    liquidity,

    power,

    trend,

    targets

  };

}


// ============================================================
// 📩 رسالة الإشارة
// ============================================================

function createAlert(
  analysis,
  market,
  symbol
) {

  const bearish =
    analysis.trend === "هابط";

  const mark =
    bearish
      ? "🔴✓"
      : "🟢";


  const targets =
    analysis.targets
      .map(
        (target, index) =>
          `${mark} الهدف ${index + 1}: ${formatPrice(target)}`
      )
      .join("\n");


  return [

    "🚨 AI PRO MAX",

    `━━━━━━━━━━━━━━`,

    `${market}`,

    `📌 الرمز: ${clean(symbol)}`,

    `💰 السعر: ${formatPrice(analysis.price)}`,

    `${mark} الاتجاه: ${analysis.trend}`,

    `🧠 قوة الاتجاه: ${analysis.power.toFixed(0)}%`,

    `📏 ATR(14): ${formatPrice(analysis.atr)}`,

    `📊 RSI(14): ${analysis.rsi.toFixed(1)}`,

    `💧 قوة السيولة: ${analysis.liquidity.toFixed(2)}x`,

    `📍 الدعم: ${formatPrice(analysis.support)}`,

    `📍 المقاومة: ${formatPrice(analysis.resistance)}`,

    "",

    "🎯 أهداف ATR",

    targets,

    "",

    "⚡ AI PRO MAX — تلقائي"

  ].join("\n");

}


// ============================================================
// 📋 قائمة الرموز
// ============================================================

async function loadSymbols(
  exchange,
  market
) {

  const current =
    state[market].symbols;

  if (current.length) {
    return current;
  }


  const rows =
    await eodhd(
      `exchange-symbol-list/${exchange}`
    );


  let items =
    (Array.isArray(rows)
      ? rows
      : []
    )
      .map(row => ({

        code:
          String(
            row.Code ||
            row.code ||
            ""
          ).trim(),

        venue:
          String(
            row.Exchange ||
            row.exchange ||
            exchange
          ).trim(),

        type:
          String(
            row.Type ||
            row.type ||
            ""
          ).trim(),

        name:
          String(
            row.Name ||
            row.name ||
            ""
          ).trim()

      }))
      .filter(
        item =>
          item.code
      );


  // ==========================================================
  // 🇺🇸 NASDAQ فقط
  // ==========================================================

  if (market === "us") {

    items =
      items.filter(
        item =>
          item.venue
            .toUpperCase()
            .startsWith("NASDAQ")
      );

  }


  // ==========================================================
  // 🪙 العملات
  // ==========================================================

  if (market === "crypto") {

    items =
      items.filter(
        item =>
          item.code.includes("-")
      );

  }


  const unique =
    new Set();


  state[market].symbols =
    items.filter(item => {

      const key =
        `${item.code}|${item.venue}`;

      if (unique.has(key)) {
        return false;
      }

      unique.add(key);

      return true;

    });


  return state[market].symbols;

}


// ============================================================
// 📊 بيانات 5 دقائق
// ============================================================

async function getBars(
  item,
  exchange,
  market
) {

  let ticker;


  if (market === "crypto") {

    ticker =
      `${item.code}.CC`;

  } else if (market === "us") {

    ticker =
      `${item.code}.US`;

  } else {

    ticker =
      `${item.code}.${item.venue || exchange}`;

  }


  const now =
    Math.floor(
      Date.now() / 1000
    );


  const from =
    now -
    60 * 60 * 24 * 30;


  const data =
    await eodhd(
      `intraday/${ticker}`,
      {

        interval: "5m",

        from,

        to: now

      }
    );


  if (!Array.isArray(data)) {
    return [];
  }


  return data.map(
    row => ({

      open: row.open,

      high: row.high,

      low: row.low,

      close: row.close,

      volume: row.volume

    })
  );

}


// ============================================================
// 🔍 فحص سوق
// ============================================================

async function scanMarket(
  market,
  label,
  exchange
) {

  if (!bots[market]) {

    console.log(
      `⏸️ ${label}: البوت غير متصل`
    );

    return;

  }


  const symbols =
    await loadSymbols(
      exchange,
      market
    );


  if (!symbols.length) {

    throw new Error(
      `${label}: لا توجد رموز`
    );

  }


  const currentState =
    state[market];


  let checked = 0;

  let alerts = 0;


  const batch =
    Math.min(
      symbols.length,
      SYMBOLS_PER_CYCLE
    );


  while (
    checked < batch
  ) {

    const item =
      symbols[
        currentState.cursor %
        symbols.length
      ];


    currentState.cursor =
      (
        currentState.cursor + 1
      ) %
      symbols.length;


    checked++;


    const symbol =
      item.code;


    try {

      const bars =
        await getBars(
          item,
          exchange,
          market
        );


      const analysis =
        analyze(bars);


      if (!analysis) {
        await sleep(
          REQUEST_DELAY_MS
        );
        continue;
      }


      // 🇺🇸 السعر الأدنى
      if (
        market === "us" &&
        analysis.price < MIN_US_PRICE
      ) {

        await sleep(
          REQUEST_DELAY_MS
        );

        continue;

      }


      // ======================================================
      // 🚨 شروط الإشارة
      // ======================================================

      const strongSignal =

        analysis.trend !== "محايد" &&

        (
          analysis.rsi >= 60 ||
          analysis.rsi <= 40
        ) &&

        analysis.liquidity >= 1.15;


      if (!strongSignal) {

        await sleep(
          REQUEST_DELAY_MS
        );

        continue;

      }


      const signalKey =
        `${symbol}:${analysis.trend}`;


      if (
        currentState.sent.has(
          signalKey
        )
      ) {

        await sleep(
          REQUEST_DELAY_MS
        );

        continue;

      }


      currentState.sent.add(
        signalKey
      );


      // منع تضخم الذاكرة
      if (
        currentState.sent.size >
        5000
      ) {

        currentState.sent =
          new Set(
            [
              ...currentState.sent
            ].slice(-2500)
          );

      }


      const chatId =
        CHAT_IDS[market];


      if (!chatId) {

        console.log(
          `⚠️ ${label}: لم يتم تحديد Chat ID`
        );

        await sleep(
          REQUEST_DELAY_MS
        );

        continue;

      }


      await bots[market].sendMessage(

        chatId,

        createAlert(
          analysis,
          label,
          symbol
        )

      );


      alerts++;


      console.log(
        `🚨 ${label} ${symbol} → تم إرسال إشارة`
      );


      if (
        alerts >=
        MAX_ALERTS_PER_CYCLE
      ) {

        break;

      }


    } catch (error) {

      console.error(
        `❌ ${label} ${symbol}:`,
        error.message
      );

    }


    await sleep(
      REQUEST_DELAY_MS
    );

  }


  console.log(
    `✅ ${label}: فحص ${checked} من ${symbols.length} | إشارات ${alerts}`
  );

}


// ============================================================
// 🔄 دورة كاملة
// ============================================================

async function runCycle() {

  console.log(
    "\n🚀 AI PRO MAX — بدء دورة فحص جديدة"
  );


  try {

    await scanMarket(
      "tasi",
      "🇸🇦 تاسي",
      "TADAWUL"
    );

  } catch (error) {

    console.error(
      "❌ تاسي:",
      error.message
    );

  }


  try {

    await scanMarket(
      "us",
      "🇺🇸 NASDAQ",
      "US"
    );

  } catch (error) {

    console.error(
      "❌ الأمريكي:",
      error.message
    );

  }


  try {

    await scanMarket(
      "crypto",
      "🪙 العملات الرقمية",
      "CC"
    );

  } catch (error) {

    console.error(
      "❌ العملات:",
      error.message
    );

  }


  console.log(
    "🏁 نهاية دورة الفحص"
  );

}


// ============================================================
// 🤖 إنشاء بوت
// ============================================================

async function createBot(
  market,
  name
) {

  const token =
    TOKENS[market];


  if (!token) {

    console.error(
      `❌ ${name}: Token غير موجود`
    );

    return null;

  }


  try {

    const bot =
      new TelegramBot(
        token,
        {
          polling: true
        }
      );


    bots[market] =
      bot;


    // ========================================================
    // /start
    // ========================================================

    bot.onText(
      /^\/start$/,
      async message => {

        const chatId =
          message.chat.id;


        CHAT_IDS[market] =
          String(chatId);


        const text =

          `🚀 AI PRO MAX\n\n` +

          `${name}\n\n` +

          `✅ البوت متصل ويعمل\n` +

          `🤖 الوضع: تلقائي\n` +

          `🔄 الفحص: كل ${SCAN_MINUTES} دقائق\n` +

          `📡 البيانات: EODHD\n\n` +

          `🎯 ATR(14)\n` +

          `🎯 8 أهداف ديناميكية\n` +

          `📍 دعم ومقاومة\n` +

          `💧 تحليل السيولة`;


        try {

          await bot.sendMessage(
            chatId,
            text
          );

          console.log(
            `✅ ${name}: /start تم بنجاح`
          );

        } catch (error) {

          console.error(
            `❌ Telegram ${name}:`,
            error.message
          );

        }

      }
    );


    bot.on(
      "polling_error",
      error => {

        console.error(
          `❌ Telegram ${name}:`,
          error.message
        );

      }
    );


    console.log(
      `✅ ${name}: Telegram متصل`
    );


    return bot;


  } catch (error) {

    console.error(
      `❌ ${name}: فشل تشغيل البوت`,
      error.message
    );

    return null;

  }

}


// ============================================================
// 🌐 Railway Server
// ============================================================

const app =
  express();


app.get(
  "/",
  (req, res) => {

    res.json({

      ok: true,

      name: "AI PRO MAX",

      status: "running",

      bots: {

        tasi:
          !!bots.tasi,

        us:
          !!bots.us,

        crypto:
          !!bots.crypto

      },

      eodhd:
        !!EODHD_API_KEY

    });

  }
);


app.get(
  "/health",
  (req, res) => {

    res.status(200).send(
      "AI PRO MAX OK"
    );

  }
);


app.listen(
  PORT,
  () => {

    console.log(
      `🌐 الخادم يعمل على المنفذ ${PORT}`
    );

  }
);


// ============================================================
// 🚀 تشغيل