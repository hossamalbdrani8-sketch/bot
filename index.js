
// ============================================================
// 💀🚀 AI PRO MAX
// 🇸🇦 TASI + 🇺🇸 US/NASDAQ + 🪙 CRYPTO
// 🤖 3 TELEGRAM BOTS / 1 INDEX.JS
// 📡 EODHD = مصدر بيانات السوق الوحيد
// ⏱️ فحص تلقائي كل دقيقتين
// Node.js 18+
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");
const fs = require("fs");
const path = require("path");

// ============================================================
// 🔐 RAILWAY VARIABLES
// ============================================================

const TASI_CONFIG =
  String(process.env.TASI_CONFIG || "").trim();

const US_CONFIG =
  String(process.env.US_CONFIG || "").trim();

const CRYPTO_CONFIG =
  String(process.env.CRYPTO_CONFIG || "").trim();

const EODHD_API_KEY =
  String(process.env.EODHD_API_KEY || "").trim();

// ============================================================
// ⚙️ SETTINGS
// ============================================================

const PORT =
  Number(process.env.PORT || 8080);

const SCAN_MINUTES = 2;

const REQUEST_TIMEOUT =
  25000;

const QUOTE_BATCH =
  20;

const DEEP_CANDIDATES =
  12;

const US_MIN_PRICE =
  0.20;

const ALERT_COOLDOWN =
  30 * 60 * 1000;

const UNIVERSE_REFRESH =
  60 * 60 * 1000;

const MAX_SYMBOLS =
  5000;

// ============================================================
// 🌐 EXPRESS
// ============================================================

const app = express();

let scanRunning = false;

let lastScanAt = null;

let universeLoadedAt = null;

app.get("/", (_req, res) => {

  res.json({

    status: "online",

    bot: "AI PRO MAX 💀🚀",

    markets: [
      "TASI 🇸🇦",
      "US 🇺🇸",
      "CRYPTO 🪙"
    ],

    dataSource: "EODHD",

    scanMinutes:
      SCAN_MINUTES,

    scanRunning,

    lastScanAt,

    universeLoadedAt

  });

});

app.get("/health", (_req, res) => {

  res.json({

    status: "healthy",

    TASI_CONFIG:
      !!TASI_CONFIG,

    US_CONFIG:
      !!US_CONFIG,

    CRYPTO_CONFIG:
      !!CRYPTO_CONFIG,

    EODHD_API_KEY:
      !!EODHD_API_KEY,

    scanRunning,

    lastScanAt

  });

});

app.listen(
  PORT,
  "0.0.0.0",
  () => {

    console.log(
      `🌐 Server running on port ${PORT}`
    );

  }
);

// ============================================================
// 🔐 TOKEN READER
// ============================================================

function getToken(value) {

  const text =
    String(value || "").trim();

  if (!text) {
    return "";
  }

  // إذا كان المتغير توكن مباشر
  if (!text.startsWith("{")) {
    return text;
  }

  // إذا كان JSON
  try {

    const obj =
      JSON.parse(text);

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
// 🔎 CONFIG CHECK
// ============================================================

function checkConfig() {

  const missing = [];

  if (!getToken(TASI_CONFIG)) {
    missing.push("TASI_CONFIG");
  }

  if (!getToken(US_CONFIG)) {
    missing.push("US_CONFIG");
  }

  if (!getToken(CRYPTO_CONFIG)) {
    missing.push("CRYPTO_CONFIG");
  }

  if (!EODHD_API_KEY) {
    missing.push("EODHD_API_KEY");
  }

  if (missing.length) {

    throw new Error(
      "المتغيرات الناقصة: " +
      missing.join(", ")
    );

  }

}

// ============================================================
// 🤖 TELEGRAM BOTS
// ============================================================

const bots = {

  tasi: null,

  us: null,

  crypto: null

};

// ============================================================
// 💬 CHAT IDS
// ============================================================

const chatFile =
  path.join(
    process.cwd(),
    "chat_ids.json"
  );

let chats = {

  tasi: null,

  us: null,

  crypto: null

};

try {

  if (fs.existsSync(chatFile)) {

    const saved =
      JSON.parse(
        fs.readFileSync(
          chatFile,
          "utf8"
        )
      );

    chats = {

      ...chats,

      ...saved

    };

  }

} catch (error) {

  console.log(
    "⚠️ تعذر قراءة chat_ids.json"
  );

}

function saveChats() {

  try {

    fs.writeFileSync(
      chatFile,
      JSON.stringify(
        chats,
        null,
        2
      )
    );

  } catch (error) {

    console.log(
      "⚠️ تعذر حفظ chat_ids.json"
    );

  }

}

// ============================================================
// 🤖 CREATE BOT
// ============================================================

function createBot(
  key,
  market,
  config
) {

  const token =
    getToken(config);

  if (!token) {

    console.error(
      `❌ ${market}: التوكن غير موجود`
    );

    return null;

  }

  const bot =
    new TelegramBot(
      token,
      {
        polling: true
      }
    );

  // ==========================================================
  // START
  // ==========================================================

  bot.onText(
    /^\/start$/i,
    async (msg) => {

      chats[key] =
        msg.chat.id;

      saveChats();

      const text =

        `💀🚀 أهلاً بك في AI PRO MAX\n\n` +

        `✅ البوت يعمل الآن\n` +

        `🔄 الفحص تلقائي وكامل\n` +

        `⏱️ الفحص كل ${SCAN_MINUTES} دقيقة\n` +

        `📊 السوق: ${market}\n` +

        `📡 مصدر البيانات: EODHD\n\n` +

        `🤖 لن تحتاج إلى تشغيل الفحص يدويًا.`;

      await bot
        .sendMessage(
          msg.chat.id,
          text
        )
        .catch(() => {});

    }
  );

  // ==========================================================
  // STATUS
  // ==========================================================

  bot.onText(
    /^\/status$/i,
    async (msg) => {

      const text =

        `💀🚀 AI PRO MAX\n\n` +

        `✅ البوت متصل\n` +

        `🔄 الفحص تلقائي\n` +

        `⏱️ كل ${SCAN_MINUTES} دقيقة\n` +

        `📡 EODHD متصل`;

      await bot
        .sendMessage(
          msg.chat.id,
          text
        )
        .catch(() => {});

    }
  );

  bot.on(
    "polling_error",
    (error) => {

      console.error(
        `❌ Telegram ${market}: ${error.message}`
      );

    }
  );

  console.log(
    `🤖 ${market}: تم تشغيل البوت`
  );

  return bot;

}

// ============================================================
// 🚀 START THREE BOTS
// ============================================================

bots.tasi =
  createBot(
    "tasi",
    "TASI 🇸🇦",
    TASI_CONFIG
  );

bots.us =
  createBot(
    "us",
    "US / NASDAQ 🇺🇸",
    US_CONFIG
  );

bots.crypto =
  createBot(
    "crypto",
    "CRYPTO 🪙",
    CRYPTO_CONFIG
  );

// ============================================================
// 📡 EODHD
// ============================================================

const EODHD_BASE =
  "https://eodhd.com/api";

async function eodhd(
  endpoint,
  params = {}
) {

  if (!EODHD_API_KEY) {

    throw new Error(
      "EODHD_API_KEY غير موجود"
    );

  }

  const cleanEndpoint =
    String(endpoint)
      .replace(/^\/+/, "");

  const url =
    new URL(
      `${EODHD_BASE}/${cleanEndpoint}`
    );

  url.searchParams.set(
    "api_token",
    EODHD_API_KEY
  );

  url.searchParams.set(
    "fmt",
    "json"
  );

  for (
    const [key, value]
    of Object.entries(params)
  ) {

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

  const controller =
    new AbortController();

  const timeout =
    setTimeout(
      () =>
        controller.abort(),
      REQUEST_TIMEOUT
    );

  try {

    const response =
      await fetch(
        url,
        {
          method: "GET",

          headers: {
            "Accept":
              "application/json",

            "User-Agent":
              "AI-PRO-MAX"
          },

          signal:
            controller.signal
        }
      );

    const text =
      await response.text();

    let data;

    try {

      data =
        JSON.parse(text);

    } catch {

      data =
        text;

    }

    if (!response.ok) {

      let detail =
        typeof data === "string"
          ? data
          : JSON.stringify(data);

      detail =
        detail.slice(0, 400);

      throw new Error(
        `EODHD HTTP ${response.status}: ${detail}`
      );

    }

    if (
      data &&
      typeof data === "object" &&
      !Array.isArray(data)
    ) {

      if (data.error) {

        throw new Error(
          `EODHD: ${data.error}`
        );

      }

      if (data.message) {

        const message =
          String(data.message);

        if (
          /error|forbidden|unauthorized|limit/i
            .test(message)
        ) {

          throw new Error(
            `EODHD: ${message}`
          );

        }

      }

    }

    return data;

  } finally {

    clearTimeout(timeout);

  }

}

// ============================================================
// 🧰 HELPERS
// ============================================================

function sleep(ms) {

  return new Promise(
    resolve =>
      setTimeout(
        resolve,
        ms
      )
  );

}

function num(value) {

  const x =
    Number(value);

  return Number.isFinite(x)
    ? x
    : 0;

}

function money(value) {

  const x =
    num(value);

  if (x >= 1000) {

    return x.toLocaleString(
      "en-US",
      {
        maximumFractionDigits: 2
      }
    );

  }

  return x
    .toFixed(4)
    .replace(/0+$/, "")
    .replace(/\.$/, "");

}

function percent(value) {

  return (
    num(value).toFixed(2) +
    "%"
  );

}

function volumeText(value) {

  const x =
    num(value);

  if (x >= 1e9) {

    return (
      (x / 1e9).toFixed(2) +
      "B"
    );

  }

  if (x >= 1e6) {

    return (
      (x / 1e6).toFixed(2) +
      "M"
    );

  }

  if (x >= 1e3) {

    return (
      (x / 1e3).toFixed(2) +
      "K"
    );

  }

  return x.toFixed(0);

}

function chunks(
  array,
  size
) {

  const output = [];

  for (
    let i = 0;
    i < array.length;
    i += size
  ) {

    output.push(
      array.slice(
        i,
        i + size
      )
    );

  }

  return output;

}

function dateYMD(
  daysAgo = 0
) {

  const date =
    new Date(
      Date.now() -
      daysAgo *
      24 *
      60 *
      60 *
      1000
    );

  return date
    .toISOString()
    .slice(0, 10);

}

// ============================================================
// 📋 UNIVERSES
// ============================================================

let universes = {

  tasi: [],

  us: [],

  crypto: []

};

// ============================================================
// 🧾 SYMBOL NORMALIZATION
// ============================================================

function symbolOf(row) {

  return String(
    row.Code ||
    row.code ||
    row.Symbol ||
    row.symbol ||
    ""
  ).trim();

}

function nameOf(
  row,
  fallback
) {

  return String(
    row.Name ||
    row.name ||
    row.Description ||
    row.description ||
    fallback ||
    ""
  ).trim();

}

// ============================================================
// 🇸🇦 TASI SYMBOLS
// ============================================================

async function loadTasi() {

  const rows =
    await eodhd(
      "exchange-symbol-list/SR"
    );

  if (!Array.isArray(rows)) {

    throw new Error(
      "قائمة TASI غير صالحة"
    );

  }

  return rows

    .map(row => {

      const symbol =
        symbolOf(row);

      return {

        symbol,

        fullSymbol:
          `${symbol}.SR`,

        name:
          nameOf(
            row,
            symbol
          )

      };

    })

    .filter(
      x => x.symbol
    )

    .slice(
      0,
      MAX_SYMBOLS
    );

}

// ============================================================
// 🇺🇸 US SYMBOLS
// ============================================================

async function loadUS() {

  const rows =
    await eodhd(
      "exchange-symbol-list/US"
    );

  if (!Array.isArray(rows)) {

    throw new Error(
      "قائمة US غير صالحة"
    );

  }

  return rows

    .map(row => {

      const symbol =
        symbolOf(row);

      const type =
        String(
          row.Type ||
          row.type ||
          ""
        );

      return {

        symbol,

        fullSymbol:
          `${symbol}.US`,

        name:
          nameOf(
            row,
            symbol
          ),

        type

      };

    })

    .filter(
      x => x.symbol
    )

    .filter(
      x =>
        !x.type ||
        /common|stock|etf|adr|fund|preferred/i
          .test(x.type)
    )

    .slice(
      0,
      MAX_SYMBOLS
    );

}

// ============================================================
// 🪙 CRYPTO SYMBOLS
// ============================================================

async function loadCrypto() {

  const rows =
    await eodhd(
      "exchange-symbol-list/CC"
    );

  if (!Array.isArray(rows)) {

    throw new Error(
      "قائمة العملات غير صالحة"
    );

  }

  return rows

    .map(row => {

      const symbol =
        symbolOf(row);

      return {

        symbol,

        fullSymbol:
          `${symbol}.CC`,

        name:
          nameOf(
            row,
            symbol
          )

      };

    })

    .filter(
      x => x.symbol
    )

    .slice(
      0,
      MAX_SYMBOLS
    );

}

// ============================================================
// 🔄 LOAD ALL MARKETS
// ============================================================

async function loadUniverses() {

  console.log(
    "🔄 تحديث قوائم الأسواق من EODHD..."
  );

  const results =
    await Promise.allSettled([

      loadTasi(),

      loadUS(),

      loadCrypto()

    ]);

  if (
    results[0].status ===
    "fulfilled"
  ) {

    universes.tasi =
      results[0].value;

    console.log(
      `🇸🇦 TASI: ${universes.tasi.length} رمز`
    );

  } else {

    console.error(
      `❌ TASI: ${results[0].reason.message}`
    );

  }

  if (
    results[1].status ===
    "fulfilled"
  ) {

    universes.us =
      results[1].value;

    console.log(
      `🇺🇸 US: ${universes.us.length} رمز`
    );

  } else {

    console.error(
      `❌ US: ${results[1].reason.message}`
    );

  }

  if (
    results[2].status ===
    "fulfilled"
  ) {

    universes.crypto =
      results[2].value;

    console.log(
      `🪙 CRYPTO: ${universes.crypto.length} رمز`
    );

  } else {

    console.error(
      `❌ CRYPTO: ${results[2].reason.message}`
    );

  }

  universeLoadedAt =
    new Date().toISOString();

}

// ============================================================
// 💹 QUOTES
// ============================================================

async function getQuotes(
  symbols
) {

  const unique =
    [
      ...new Set(
        symbols.filter(Boolean)
      )
    ];

  const map =
    new Map();

  for (
    const group
    of chunks(
      unique,
      QUOTE_BATCH
    )
  ) {

    try {

      const data =
        await eodhd(
          "real-time/",
          {
            s:
              group.join(",")
          }
        );

      if (
        Array.isArray(data)
      ) {

        for (
          const row
          of data
        ) {

          const code =
            String(
              row.code ||
              row.Code ||
              ""
            ).trim();

          if (code) {

            map.set(
              code,
              row
            );

          }

        }

      } else if (
        data &&
        typeof data === "object"
      ) {

        const code =
          String(
            data.code ||
            data.Code ||
            ""
          ).trim();

        if (code) {

          map.set(
            code,
            data
          );

        }

      }

    } catch (error) {

      console.error(
        `⚠️ أسعار EODHD: ${error.message}`
      );

    }

    await sleep(100);

  }

  return map;

}

// ============================================================
// 🔎 FIND QUOTE
// ============================================================

function findQuote(
  item,
  map
) {

  return (
    map.get(
      item.fullSymbol
    ) ||
    map.get(
      item.symbol
    ) ||
    null
  );

}

// ============================================================
// 📈 INTRADAY
// ============================================================

async function getIntraday(
  fullSymbol
) {

  return eodhd(
    `intraday/${encodeURIComponent(fullSymbol)}`,
    {
      interval:
        "5m",

      from:
        dateYMD(5),

      to:
        dateYMD(0)
    }
  );

}

// ============================================================
// 🧾 NORMALIZE BARS
// ============================================================

function normalizeBars(
  data
) {

  if (!Array.isArray(data)) {

    return [];

  }

  return data

    .map(row => ({

      time:
        row.datetime ||
        row.timestamp ||
        row.date ||
        "",

      open:
        num(row.open),

      high:
        num(row.high),

      low:
        num(row.low),

      close:
        num(row.close),

      volume:
        num(row.volume)

    }))

    .filter(
      row =>
        row.close > 0 &&
        row.high > 0 &&
        row.low > 0
    );

}

// ============================================================
// 📐 EMA
// ============================================================

function EMA(
  values,
  length
) {

  if (!values.length) {

    return 0;

  }

  const k =
    2 /
    (length + 1);

  let result =
    values[0];

  for (
    let i = 1;
    i < values.length;
    i++
  ) {

    result =
      values[i] * k +
      result * (1 - k);

  }

  return result;

}

// ============================================================
// 📉 RSI
// ============================================================

function RSI(
  values,
  length = 14
) {

  if (
    values.length <= length
  ) {

    return 50;

  }

  let gain = 0;

  let loss = 0;

  for (
    let i = 1;
    i <= length;
    i++
  ) {

    const difference =
      values[i] -
      values[i - 1];

    if (
      difference >= 0
    ) {

      gain +=
        difference;

    } else {

      loss -=
        difference;

    }

  }

  gain /=
    length;

  loss /=
    length;

  for (
    let i =
      length + 1;
    i < values.length;
    i++
  ) {

    const difference =
      values[i] -
      values[i - 1];

    gain =
      (
        gain *
        (length - 1) +
        Math.max(
          difference,
          0
        )
      ) / length;

    loss =
      (
        loss *
        (length - 1) +
        Math.max(
          -difference,
          0
        )
      ) / length;

  }

  if (loss === 0) {

    return 100;

  }

  return (
    100 -
    100 /
    (
      1 +
      gain / loss
    )
  );

}

// ============================================================
// 📐 ATR
// ============================================================

function ATR(
  rows,
  length = 14
) {

  if (
    rows.length <
    length + 1
  ) {

    return 0;

  }

  const trueRanges = [];

  for (
    let i = 1;
    i < rows.length;
    i++
  ) {

    const current =
      rows[i];

    const previous =
      rows[i - 1];

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

    trueRanges.push(tr);

  }

  const last =
    trueRanges.slice(
      -length
    );

  if (!last.length) {

    return 0;

  }

  return (
    last.reduce(
      (a, b) =>
        a + b,
      0
    ) /
    last.length
  );

}

// ============================================================
// 📍 SUPPORT / RESISTANCE
// ============================================================

function supportResistance(
  rows
) {

  const recent =
    rows.slice(-80);

  if (!recent.length) {

    return {

      support: 0,

      resistance: 0

    };

  }

  return {

    support:
      Math.min(
        ...recent.map(
          x => x.low
        )
      ),

    resistance:
      Math.max(
        ...recent.map(
          x => x.high
        )
      )

  };

}

// ============================================================
// 💧 LIQUIDITY
// ============================================================

function liquidity(
  rows
) {

  const volumes =
    rows
      .map(
        x => x.volume
      )
      .filter(
        x => x > 0
      );

  if (!volumes.length) {

    return {

      current: 0,

      average: 0,

      ratio: 0,

      label:
        "غير متوفرة"

    };

  }

  const current =
    volumes.at(-1);

  const base =
    volumes.slice(
      -21,
      -1
    );

  const average =
    base.length

      ? base.reduce(
          (a, b) =>
            a + b,
          0
        ) /
        base.length

      : current;

  const ratio =
    average > 0
      ? current / average
      : 0;

  let label =
    "سيولة طبيعية";

  if (
    ratio >= 2
  ) {

    label =
      "سيولة قوية جدًا 💧🔥";

  } else if (
    ratio >= 1.3
  ) {

    label =
      "سيولة قوية 💧";

  } else if (
    ratio < 0.8
  ) {

    label =
      "سيولة ضعيفة";

  }

  return {

    current,

    average,

    ratio,

    label

  };

}

// ============================================================
// 🧠 AI ANALYSIS
// ============================================================

function analyze(
  rows,
  quote
) {

  if (
    rows.length < 30
  ) {

    return null;

  }

  const closes =
    rows.map(
      x => x.close
    );

  const price =
    num(
      quote?.close
    ) ||
    closes.at(-1);

  const previous =
    num(
      quote?.previousClose
    ) ||
    closes.at(-2) ||
    price;

  const change =
    previous > 0

      ? (
          (price - previous) /
          previous
        ) * 100

      : 0;

  const ema8 =
    EMA(
      closes,
      8
    );

  const ema21 =
    EMA(
      closes,
      21
    );

  const ema50 =
    EMA(
      closes,
      50
    );

  const rsi =
    RSI(
      closes,
      14
    );

  const atr =
    ATR(
      rows,
      14
    );

  const sr =
    supportResistance(
      rows
    );

  const liq =
    liquidity(
      rows
    );

  let score =
    50;

  if (
    price >= ema8
  ) {

    score += 8;

  } else {

    score -= 8;

  }

  if (
    ema8 >= ema21
  ) {

    score += 10;

  } else {

    score -= 10;

  }

  if (
    ema21 >= ema50
  ) {

    score += 12;

  } else {

    score -= 12;

  }

  if (
    rsi >= 50 &&
    rsi < 80
  ) {

    score += 8;

  } else if (
    rsi < 50
  ) {

    score -= 8;

  }

  if (
    liq.ratio >= 1.5
  ) {

    score += 7;

  } else if (
    liq.ratio < 0.7
  ) {

    score -= 4;

  }

  if (
    change >= 2
  ) {

    score += 5;

  } else if (
    change <= -2
  ) {

    score -= 5;

  }

  score =
    Math.max(
      0,
      Math.min(
        100,
        score
      )
    );

  let signal =
    "مراقبة";

  if (
    score >= 78
  ) {

    signal =
      "شراء قوي 🟢";

  } else if (
    score <= 25
  ) {

    signal =
      "بيع قوي 🔴";

  } else if (
    score >= 65
  ) {

    signal =
      "شراء 🟢";

  } else if (
    score <= 40
  ) {

    signal =
      "بيع 🔴";

  }

  const bullish =
    score >= 50;

  const multipliers = [

    0.5,

    1,

    1.5,

    2,

    2.5,

    3,

    4,

    5

  ];

  const targets =
    multipliers.map(
      (multiplier, index) => ({

        name:
          `TP${index + 1}`,

        price:
          bullish

            ? price +
              atr *
              multiplier

            : price -
              atr *
              multiplier

      })
    );

  return {

    price,

    change,

    ema8,

    ema21,

    ema50,

    rsi,

    atr,

    score,

    bullish,

    signal,

    sr,

    liq,

    targets

  };

}

// ============================================================
// 📰 NEWS
// ============================================================

async function getNews(
  fullSymbol
) {

  try {

    const data =
      await eodhd(
        "news",
        {
          s:
            fullSymbol,

          limit:
            1,

          offset:
            0
        }
      );

    if (
      !Array.isArray(data) ||
      !data.length
    ) {

      return null;

    }

    const row =
      data[0];

    return {

      title:
        String(
          row.titleAr ||
          row.title_ar ||
          row.titleArabic ||
          row.title ||
          "خبر"
        ),

      link:
        String(
          row.link ||
          row.url ||
          ""
        ),

      date:
        String(
          row.date ||
          row.datetime ||
          ""
        )

    };

  } catch (error) {

    console.log(
      `⚠️ الأخبار ${fullSymbol}: ${error.message}`
    );

    return null;

  }

}

// ============================================================
// 📲 MESSAGE
// ============================================================

function buildMessage(
  market,
  item,
  analysis,
  news
) {

  const flag =
    market === "TASI"

      ? "🇸🇦"

      : market === "US"

        ? "🇺🇸"

        : "🪙";

  const targetIcon =
    analysis.bullish
      ? "🟢"
      : "🔴✓";

  let text =

    `💀🚀 AI PRO MAX\n` +

    `━━━━━━━━━━━━━━━━━━\n` +

    `${flag} ${market}\n` +

    `📌 ${item.symbol}\n` +

    `🏢 ${item.name}\n\n` +

    `💰 السعر: ${money(analysis.price)}\n` +

    `📊 الإشارة: ${analysis.signal}\n` +

    `🧠 قوة الإشارة: ${analysis.score}/100\n` +

    `📈 التغير: ${percent(analysis.change)}\n` +

    `📉 RSI14: ${analysis.rsi.toFixed(2)}\n` +

    `📐 ATR14: ${money(analysis.atr)}\n\n` +

    `📊 EMA8: ${money(analysis.ema8)}\n` +

    `📊 EMA21: ${money(analysis.ema21)}\n` +

    `📊 EMA50: ${money(analysis.ema50)}\n\n` +

    `💧 السيولة: ${analysis.liq.label}\n` +

    `💧 الحجم: ${volumeText(analysis.liq.current)}\n` +

    `💧 متوسط الحجم: ${volumeText(analysis.liq.average)}\n` +

    `💧 قوة الحجم: ${analysis.liq.ratio.toFixed(2)}x\n\n` +

    `📍 الدعم: ${money(analysis.sr.support)}\n` +

    `📍 المقاومة: ${money(analysis.sr.resistance)}\n\n` +

    `🎯 أهداف ATR\n`;

  for (
    const target
    of analysis.targets
  ) {

    text +=
      `${targetIcon} ` +
      `${target.name}: ` +
      `${money(target.price)}\n`;

  }

  if (news) {

    text +=
      `\n📰 ${news.title}\n`;

    if (news.link) {

      text +=
        `🔗 ${news.link}\n`;

    }

  }

  text +=

    `\n━━━━━━━━━━━━━━━━━━\n` +

    `📡 EODHD\n` +

    `🤖 فحص تلقائي كل ${SCAN_MINUTES} دقيقة`;

  return text;

}

// ============================================================
// 📤 TELEGRAM SEND
// ============================================================

async function sendTelegram(
  botKey,
  text
) {

  const bot =
    bots[botKey];

  const chatId =
    chats[botKey];

  if (
    !bot ||
    !chatId
  ) {

    return false;

  }

  await bot.sendMessage(
    chatId,
    text,
    {
      disable_web_page_preview:
        true
    }
  );

  return true;

}

// ============================================================
// 🔔 ALERT CONTROL
// ============================================================

const lastAlerts =
  new Map();

function canAlert(
  market,
  symbol,
  signal
) {

  const key =
    `${market}:${symbol}`;

  const now =
    Date.now();

  const previous =
    lastAlerts.get(
      key
    );

  if (
    previous &&
    previous.signal === signal &&
    now -
      previous.time <
      ALERT_COOLDOWN
  ) {

    return false;

  }

  lastAlerts.set(
    key,
    {
      signal,
      time: now
    }
  );

  return true;

}

// ============================================================
// 🔎 MARKET SCAN
// ============================================================

async function scanMarket(
  market,
  items,
  botKey
) {

  if (!items.length) {

    console.log(
      `⚠️ ${market}: لا توجد رموز`
    );

    return;

  }

  console.log(
    `🔎 ${market}: فحص ${items.length} رمز`
  );

  const quoteMap =
    await getQuotes(
      items.map(
        item =>
          item.fullSymbol
      )
    );

  const candidates =
    [];

  for (
    const item
    of items
  ) {

    const quote =
      findQuote(
        item,
        quoteMap
      );

    if (!quote) {

      continue;

    }

    const price =
      num(
        quote.close ||
        quote.price ||
        quote.previousClose
      );

    if (
      price <= 0
    ) {

      continue;

    }

    if (
      market === "US" &&
      price <
        US_MIN_PRICE
    ) {

      continue;

    }

    const change =
      num(
        quote.change_p ||
        quote.change_percent ||
        0
      );

    let quickScore =
      50;

    quickScore +=
      Math.max(
        -20,
        Math.min(
          20,
          change * 2
        )
      );

    if (
      num(
        quote.volume
      ) > 0
    ) {

      quickScore +=
        5;

    }

    candidates.push({

      item,

      quote,

      quickScore

    });

  }

  candidates.sort(
    (a, b) =>
      b.quickScore -
      a.quickScore
  );

  const selected =
    candidates.slice(
      0,
      DEEP_CANDIDATES
    );

  console.log(
    `📊 ${market}: ${quoteMap.size} أسعار | ${candidates.length} مرشح | ${selected.length} تحليل`
  );

  for (
    const candidate
    of selected
  ) {

    try {

      const raw =
        await getIntraday(
          candidate.item.fullSymbol
        );

      const bars =
        normalizeBars(
          raw
        );

      const analysis =
        analyze(
          bars,
          candidate.quote
        );

      if (!analysis) {

        continue;

      }

      if (
        analysis.signal !==
          "شراء قوي 🟢" &&
        analysis.signal !==
          "بيع قوي 🔴"
      ) {

        continue;

      }

      if (
        !canAlert(
          market,
          candidate.item.symbol,
          analysis.signal
        )
      ) {

        continue;

      }

      const news =
        await getNews(
          candidate.item.fullSymbol
        );

      const message =
        buildMessage(
          market,
          candidate.item,
          analysis,
          news
        );

      await sendTelegram(
        botKey,
        message
      );

      console.log(
        `🚨 ${market} ${candidate.item.symbol} → ${analysis.signal}`
      );

    } catch (error) {

      console.error(
        `⚠️ ${market} ${candidate.item.symbol}: ${error.message}`
      );

    }

    await sleep(150);

  }

}

// ============================================================
// 🚀 FULL SCAN
// ============================================================

async function fullScan() {

  if (scanRunning) {

    console.log(
      "⏭️ دورة فحص سابقة ما زالت تعمل"
    );

    return;

  }

  scanRunning =
    true;

  const startTime =
    Date.now();

  try {

    if (
      !universeLoadedAt ||
      Date.now() -
        new Date(
          universeLoadedAt
        ).getTime() >
        UNIVERSE_REFRESH
    ) {

      await loadUniverses();

    }

    await scanMarket(
      "TASI",
      universes.tasi,
      "tasi"
    );

    await scanMarket(
      "US",
      universes.us,
      "us"
    );

    await scanMarket(
      "CRYPTO",
      universes.crypto,
      "crypto"
    );

    lastScanAt =
      new Date().toISOString();

    const seconds =
      (
        Date.now() -
        startTime
      ) / 1000;

    console.log(
      `✅ اكتملت الدورة خلال ${seconds.toFixed(1)} ثانية`
    );

  } catch (error) {

    console.error(
      `❌ خطأ دورة الفحص: ${error.message}`
    );

  } finally {

    scanRunning =
      false;

  }

}

// ============================================================
// ▶️ START
// ============================================================

async function start() {

  console.log(
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  );

  console.log(
    "💀🚀 AI PRO MAX"
  );

  console.log(
    "🇸🇦 TASI"
  );

  console.log(
    "🇺🇸 US / NASDAQ"
  );

  console.log(
    "🪙 CRYPTO"
  );

  console.log(
    "📡 EODHD"
  );

  console.log(
    `⏱️ فحص كل ${SCAN_MINUTES} دقيقة`
  );

  console.log(
    "🤖 3 BOTS / 1 CODE"
  );

  console.log(
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  );

  checkConfig();

  await loadUniverses();

  // أول فحص
  setTimeout(
    () => {

      fullScan()
        .catch(
          error =>
            console.error(
              error.message
            )
        );

    },
    5000
  );

  // فحص كل دقيقتين
  setInterval(
    () => {

      fullScan()
        .catch(
          error =>
            console.error(
              error.message
            )
        );

    },
    SCAN_MINUTES *
    60 *
    1000
  );

  console.log(
    "✅ النظام بدأ العمل تلقائيًا"
  );

}

// ============================================================
// 💀 RUN
// ============================================================

start()
  .catch(
    error => {

      console.error(
        `❌ فشل تشغيل AI PRO MAX: ${error.message}`
      );

      process.exitCode =
        1;

    }
  );