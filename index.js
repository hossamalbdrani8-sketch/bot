
// ============================================================
// 🧠 AI PRO MAX — DUAL AUTONOMOUS STOCK SCANNER
// 🇸🇦 TASI + 🇺🇸 US
// EODHD API | Node.js 18+ | Telegram
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// 🔐 RAILWAY VARIABLES — لا تضع المفاتيح هنا
// ============================================================

const TASI_TOKEN = process.env.TASI_TOKEN || "";
const US_TOKEN = process.env.US_TOKEN || "";
const EODHD_API_KEY = process.env.EODHD_API_KEY || "";

// ============================================================
// ⚙️ TASI CONFIGURATION
// ============================================================

const TASI_CONFIG = {
  enabled: true,
  exchange: "SR",
  name: "🇸🇦 السوق السعودي AI PRO MAX",
  minSignalScore: 0,
  maxAlertsPerScan: 0,
};

// ============================================================
// ⚙️ US CONFIGURATION
// ============================================================

const US_CONFIG = {
  enabled: true,
  exchange: "US",
  name: "🇺🇸 السوق الأمريكي AI PRO MAX",
  minPrice: 0.20,
  minSignalScore: 0,
  maxAlertsPerScan: 0,
};

// ============================================================
// ⚙️ EODHD CONFIGURATION
// ============================================================

const EODHD_CONFIG = {
  historyLimit: 120,
  atrPeriod: 14,
  supportResistanceLookback: 60,

  scanConcurrency: 16,

  updateIntervalMinutes: 2,

  requestTimeoutMs: 25000,

  // الأهداف ATR
  atrTargets: [
    0.75,
    1.25,
    1.75,
    2.50,
    3.25,
    4.00,
    5.00,
    6.00,
  ],

  // الأخبار
  newsEnabled: true,
  newsPerStock: false,
  generalNewsLimit: 50,
};

// ============================================================
// ⚙️ SERVER
// ============================================================

const PORT = Number(process.env.PORT || 3000);

const app = express();
app.use(express.json());

app.get("/", (req, res) => {
  res.status(200).send("AI PRO MAX LIVE 24/7");
});

app.get("/health", (req, res) => {
  res.json({
    status: "ok",
    tasi: TASI_CONFIG.enabled,
    us: US_CONFIG.enabled,
    time: new Date().toISOString(),
  });
});

app.listen(PORT, () => {
  console.log(`🌐 Server running on port ${PORT}`);
});

// ============================================================
// 🧠 TELEGRAM
// ============================================================

let tasiBot = null;
let usBot = null;

if (TASI_TOKEN) {
  tasiBot = new TelegramBot(TASI_TOKEN, {
    polling: true,
  });

  tasiBot.on("polling_error", (err) => {
    console.error("🇸🇦 Telegram polling error:", err.message);
  });

  tasiBot.on("error", (err) => {
    console.error("🇸🇦 Telegram error:", err.message);
  });
}

if (US_TOKEN) {
  usBot = new TelegramBot(US_TOKEN, {
    polling: true,
  });

  usBot.on("polling_error", (err) => {
    console.error("🇺🇸 Telegram polling error:", err.message);
  });

  usBot.on("error", (err) => {
    console.error("🇺🇸 Telegram error:", err.message);
  });
}

// ============================================================
// 🧾 CHAT IDS
// ============================================================

let tasiChatIds = new Set();
let usChatIds = new Set();

// ============================================================
// 🧰 HTTP
// ============================================================

async function fetchJson(url, timeout = EODHD_CONFIG.requestTimeoutMs) {
  const controller = new AbortController();

  const timer = setTimeout(() => {
    controller.abort();
  }, timeout);

  try {
    const response = await fetch(url, {
      signal: controller.signal,
    });

    const text = await response.text();

    if (!response.ok) {
      throw new Error(
        `HTTP ${response.status}: ${text.slice(0, 300)}`
      );
    }

    if (!text) {
      throw new Error("Empty response");
    }

    return JSON.parse(text);
  } finally {
    clearTimeout(timer);
  }
}

// ============================================================
// 🔐 API CHECK
// ============================================================

function checkConfig() {
  if (!EODHD_API_KEY) {
    console.error("❌ EODHD_API_KEY غير موجود في Railway Variables");
  }

  if (!TASI_TOKEN) {
    console.error("⚠️ TASI_TOKEN غير موجود");
  }

  if (!US_TOKEN) {
    console.error("⚠️ US_TOKEN غير موجود");
  }
}

// ============================================================
// 📋 جلب قائمة الأسهم كاملة
// ============================================================

async function getExchangeSymbols(exchange) {
  const url =
    `https://eodhd.com/api/exchange-symbol-list/${exchange}` +
    `?api_token=${encodeURIComponent(EODHD_API_KEY)}` +
    `&fmt=json` +
    `&type=common_stock`;

  const data = await fetchJson(url);

  if (!Array.isArray(data)) {
    throw new Error(`قائمة ${exchange} غير صالحة`);
  }

  return data;
}

// ============================================================
// 🇸🇦 جميع أسهم تاسي
// ============================================================

async function getTasiSymbols() {
  const rows = await getExchangeSymbols(TASI_CONFIG.exchange);

  const symbols = rows
    .filter((x) => {
      const code = String(x.Code || x.code || "").trim();
      return code.length > 0;
    })
    .map((x) => ({
      code: String(x.Code || x.code).trim(),
      name: x.Name || x.name || "",
    }));

  console.log(`🇸🇦 TASI symbols: ${symbols.length}`);

  return symbols;
}

// ============================================================
// 🇺🇸 جميع الأسهم الأمريكية
// ============================================================

async function getUSSymbols() {
  const rows = await getExchangeSymbols(US_CONFIG.exchange);

  const symbols = rows
    .filter((x) => {
      const code = String(x.Code || x.code || "").trim();

      if (!code) return false;

      const type = String(
        x.Type || x.type || ""
      ).toLowerCase();

      if (
        type &&
        !type.includes("common") &&
        !type.includes("stock")
      ) {
        return false;
      }

      return true;
    })
    .map((x) => ({
      code: String(x.Code || x.code).trim(),
      name: x.Name || x.name || "",
    }));

  console.log(`🇺🇸 US symbols: ${symbols.length}`);

  return symbols;
}

// ============================================================
// 🚀 BULK EOD — أهم تعديل لمنع فحص 24 ساعة
// ============================================================

async function getBulkLastDay(exchange) {
  const url =
    `https://eodhd.com/api/eod-bulk-last-day/${exchange}` +
    `?api_token=${encodeURIComponent(EODHD_API_KEY)}` +
    `&fmt=json`;

  const data = await fetchJson(url, 60000);

  if (!Array.isArray(data)) {
    throw new Error(`Bulk ${exchange} response غير صالح`);
  }

  return data;
}

// ============================================================
// 💰 فلترة السوق حسب السعر
// ============================================================

function filterMarketByPrice(rows, minPrice = 0) {
  return rows.filter((row) => {
    const price = Number(
      row.adjusted_close ??
      row.close ??
      0
    );

    return Number.isFinite(price) && price >= minPrice;
  });
}

// ============================================================
// 📊 جلب تاريخ سهم واحد للتحليل الفني
// ============================================================

async function getHistory(symbol, exchange) {
  const ticker =
    `${symbol}.${exchange}`;

  const url =
    `https://eodhd.com/api/eod/${encodeURIComponent(ticker)}` +
    `?api_token=${encodeURIComponent(EODHD_API_KEY)}` +
    `&fmt=json` +
    `&period=d` +
    `&order=d` +
    `&limit=${EODHD_CONFIG.historyLimit}`;

  const data = await fetchJson(url);

  if (!Array.isArray(data) || data.length < 20) {
    return null;
  }

  return data;
}

// ============================================================
// 📐 ATR
// ============================================================

function calculateATR(rows, period = 14) {
  if (rows.length < period + 1) {
    return null;
  }

  const tr = [];

  for (let i = 1; i < rows.length; i++) {
    const high = Number(rows[i].high);
    const low = Number(rows[i].low);
    const prevClose = Number(rows[i - 1].close);

    if (
      !Number.isFinite(high) ||
      !Number.isFinite(low) ||
      !Number.isFinite(prevClose)
    ) {
      continue;
    }

    const trueRange = Math.max(
      high - low,
      Math.abs(high - prevClose),
      Math.abs(low - prevClose)
    );

    tr.push(trueRange);
  }

  if (tr.length < period) {
    return null;
  }

  let atr = 0;

  for (let i = 0; i < period; i++) {
    atr += tr[i];
  }

  atr /= period;

  for (let i = period; i < tr.length; i++) {
    atr =
      ((atr * (period - 1)) + tr[i]) /
      period;
  }

  return atr;
}

// ============================================================
// 📊 متوسط الحجم
// ============================================================

function averageVolume(rows, period = 20) {
  const values = rows
    .slice(0, period)
    .map((x) => Number(x.volume))
    .filter(Number.isFinite);

  if (!values.length) return 0;

  return (
    values.reduce((a, b) => a + b, 0) /
    values.length
  );
}

// ============================================================
// 💧 VWAP تقريبي تاريخي
// ============================================================

function calculateVWAP(rows, period = 20) {
  const data = rows.slice(0, period);

  let pv = 0;
  let volume = 0;

  for (const row of data) {
    const high = Number(row.high);
    const low = Number(row.low);
    const close = Number(row.close);
    const vol = Number(row.volume);

    if (
      !Number.isFinite(high) ||
      !Number.isFinite(low) ||
      !Number.isFinite(close) ||
      !Number.isFinite(vol)
    ) {
      continue;
    }

    const typical =
      (high + low + close) / 3;

    pv += typical * vol;
    volume += vol;
  }

  return volume > 0
    ? pv / volume
    : null;
}

// ============================================================
// 🧱 دعم ومقاومة
// ============================================================

function calculateSupportResistance(
  rows,
  lookback = 60
) {
  const data = rows.slice(
    0,
    Math.min(rows.length, lookback)
  );

  const highs = data
    .map((x) => Number(x.high))
    .filter(Number.isFinite);

  const lows = data
    .map((x) => Number(x.low))
    .filter(Number.isFinite);

  if (!highs.length || !lows.length) {
    return {
      support: null,
      resistance: null,
    };
  }

  const current =
    Number(data[0].close);

  const below = lows
    .filter((x) => x < current)
    .sort((a, b) => b - a);

  const above = highs
    .filter((x) => x > current)
    .sort((a, b) => a - b);

  return {
    support: below[0] ?? Math.min(...lows),
    resistance: above[0] ?? Math.max(...highs),
  };
}

// ============================================================
// 🧠 تحليل الاتجاه — بدون EMA
// ============================================================

function calculateTrend(rows) {
  if (rows.length < 10) {
    return {
      direction: "neutral",
      score: 0,
    };
  }

  const current = Number(rows[0].close);
  const old10 = Number(rows[9].close);
  const old5 = Number(rows[4].close);

  if (
    !Number.isFinite(current) ||
    !Number.isFinite(old10) ||
    !Number.isFinite(old5)
  ) {
    return {
      direction: "neutral",
      score: 0,
    };
  }

  const momentum10 =
    ((current - old10) / old10) * 100;

  const momentum5 =
    ((current - old5) / old5) * 100;

  let score = 50;

  if (momentum10 > 0) score += 20;
  if (momentum10 > 3) score += 10;
  if (momentum5 > 0) score += 10;
  if (momentum5 > 2) score += 10;

  if (momentum10 < 0) score -= 20;
  if (momentum10 < -3) score -= 10;
  if (momentum5 < 0) score -= 10;
  if (momentum5 < -2) score -= 10;

  score = Math.max(
    0,
    Math.min(100, score)
  );

  let direction = "neutral";

  if (score >= 65) {
    direction = "up";
  } else if (score <= 35) {
    direction = "down";
  }

  return {
    direction,
    score,
    momentum5,
    momentum10,
  };
}

// ============================================================
// 💧 تحليل السيولة
// ============================================================

function calculateLiquidity(rows) {
  const current = rows[0];

  const close = Number(current.close);
  const open = Number(current.open);
  const volume = Number(current.volume);

  const avgVol = averageVolume(rows);

  let buy = 50;

  if (close > open) {
    buy = 65;
  } else if (close < open) {
    buy = 35;
  }

  if (
    avgVol > 0 &&
    volume > avgVol * 2
  ) {
    if (close > open) buy += 10;
    if (close < open) buy -= 10;
  }

  buy = Math.max(
    0,
    Math.min(100, buy)
  );

  return {
    buy,
    sell: 100 - buy,
    volume,
    avgVol,
    volumeStrength:
      avgVol > 0
        ? (volume / avgVol) * 100
        : 0,
  };
}

// ============================================================
// 🧠 AI PRO MAX SCORE
// ============================================================

function calculateSignalScore({
  trend,
  liquidity,
  price,
  vwap,
  support,
  resistance,
  atr,
}) {
  let score = 50;

  if (trend.direction === "up") {
    score += 20;
  }

  if (trend.direction === "down") {
    score -= 20;
  }

  if (liquidity.buy >= 60) {
    score += 15;
  }

  if (liquidity.sell >= 60) {
    score -= 15;
  }

  if (vwap && price > vwap) {
    score += 10;
  }

  if (vwap && price < vwap) {
    score -= 10;
  }

  if (
    support &&
    atr &&
    price - support <= atr * 1.5
  ) {
    score += 5;
  }

  if (
    resistance &&
    atr &&
    resistance - price <= atr * 1.5
  ) {
    score -= 5;
  }

  return Math.max(
    0,
    Math.min(100, Math.round(score))
  );
}

// ============================================================
// 🎯 أهداف ATR
// ============================================================

function buildTargets(
  price,
  atr,
  direction,
  support,
  resistance
) {
  const targets = [];

  for (
    let i = 0;
    i < EODHD_CONFIG.atrTargets.length;
    i++
  ) {
    const multiplier =
      EODHD_CONFIG.atrTargets[i];

    let target;

    if (direction === "up") {
      target =
        price + atr * multiplier;

      if (
        i === 0 &&
        resistance &&
        resistance > price &&
        resistance < target
      ) {
        target = resistance;
      }
    } else if (direction === "down") {
      target =
        price - atr * multiplier;

      if (
        i === 0 &&
        support &&
        support < price &&
        support > target
      ) {
        target = support;
      }
    } else {
      target = price;
    }

    targets.push({
      number: i + 1,
      multiplier,
      price: Number(target.toFixed(4)),
    });
  }

  return targets;
}

// ============================================================
// 🔎 تحليل سهم
// ============================================================

async function analyzeStock(
  symbol,
  exchange,
  bulkRow = null
) {
  try {
    let history = await getHistory(
      symbol,
      exchange
    );

    if (!history || history.length < 20) {
      return null;
    }

    const latest = history[0];

    const price = Number(
      bulkRow?.adjusted_close ??
      bulkRow?.close ??
      latest.close
    );

    if (!Number.isFinite(price) || price <= 0) {
      return null;
    }

    const atr = calculateATR(
      history,
      EODHD_CONFIG.atrPeriod
    );

    if (!atr || atr <= 0) {
      return null;
    }

    const trend =
      calculateTrend(history);

    const liquidity =
      calculateLiquidity(history);

    const vwap =
      calculateVWAP(history);

    const sr =
      calculateSupportResistance(
        history,
        EODHD_CONFIG.supportResistanceLookback
      );

    const score =
      calculateSignalScore({
        trend,
        liquidity,
        price,
        vwap,
        support: sr.support,
        resistance: sr.resistance,
        atr,
      });

    if (
      score <
      (exchange === "SR"
        ? TASI_CONFIG.minSignalScore
        : US_CONFIG.minSignalScore)
    ) {
      return null;
    }

    if (trend.direction === "neutral") {
      return null;
    }

    const targets =
      buildTargets(
        price,
        atr,
        trend.direction,
        sr.support,
        sr.resistance
      );

    return {
      symbol,
      exchange,
      price,
      atr,
      trend,
      liquidity,
      vwap,
      support: sr.support,
      resistance: sr.resistance,
      score,
      targets,
      timestamp: new Date().toISOString(),
    };

  } catch (error) {
    console.error(
      `❌ ${exchange} ${symbol}:`,
      error.message
    );

    return null;
  }
}

// ============================================================
// 📝 تنسيق الرسالة
// ============================================================

function formatNumber(value) {
  if (!Number.isFinite(Number(value))) {
    return "—";
  }

  return Number(value).toFixed(
    Number(value) < 10 ? 4 : 2
  );
}

function buildMessage(result) {
  const up =
    result.trend.direction === "up";

  const direction = up
    ? "🟢 صعود قوي"
    : "🔴 هبوط قوي";

  const targets = result.targets
    .map((t) => {
      return (
        `🎯 الهدف ${t.number}: ` +
        `${formatNumber(t.price)} ` +
        `(ATR × ${t.multiplier})`
      );
    })
    .join("\n");

  return (
    `🧠 <b>AI PRO MAX</b>\n\n` +

    `${up ? "🇺🇸" : "🇸🇦"} ` +
    `<b>${escapeHtml(result.symbol)}</b>\n\n` +

    `💰 السعر: <b>${formatNumber(result.price)}</b>\n` +

    `🚨 الإشارة: <b>${direction}</b>\n` +

    `💥 قوة الإشارة: <b>${result.score}/100</b>\n\n` +

    `🧭 الاتجاه: ${
      up
        ? "🟢 صاعد"
        : "🔴 هابط"
    }\n` +

    `📐 ATR: ${formatNumber(result.atr)}\n` +

    `📍 الدعم: ${formatNumber(result.support)}\n` +

    `📌 المقاومة: ${formatNumber(result.resistance)}\n` +

    `📊 VWAP: ${formatNumber(result.vwap)}\n\n` +

    `💧 دخول السيولة: ${
      result.liquidity.buy.toFixed(1)
    }%\n` +

    `🔴 ضغط البيع: ${
      result.liquidity.sell.toFixed(1)
    }%\n` +

    `📦 قوة الحجم: ${
      result.liquidity.volumeStrength.toFixed(1)
    }%\n\n` +

    `🎯 <b>أهداف ATR</b>\n` +

    `${targets}\n\n` +

    `🕒 ${new Date().toLocaleString(
      "ar-SA",
      { timeZone: "Asia/Riyadh" }
    )}`
  );
}

// ============================================================
// 🛡️ HTML ESCAPE
// ============================================================

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// ============================================================
// 📤 إرسال رسالة
// ============================================================

async function sendMessage(
  bot,
  chatId,
  message
) {
  try {
    await bot.sendMessage(
      chatId,
      message,
      {
        parse_mode: "HTML",
        disable_web_page_preview: true,
      }
    );
  } catch (error) {
    console.error(
      "❌ Telegram send:",
      error.message
    );
  }
}

// ============================================================
// 📢 إرسال الإشارة لجميع المشتركين
// ============================================================

async function broadcast(
  bot,
  chatIds,
  message
) {
  if (!bot) return;

  for (const chatId of chatIds) {
    await sendMessage(
      bot,
      chatId,
      message
    );
  }
}

// ============================================================
// ⚡ WORKER POOL
// ============================================================

async function runWorkers(
  items,
  worker,
  concurrency,
  onProgress
) {
  let index = 0;
  let completed = 0;

  async function runner() {
    while (true) {
      const currentIndex =
        index++;

      if (currentIndex >= items.length) {
        return;
      }

      const item =
        items[currentIndex];

      try {
        await worker(
          item,
          currentIndex
        );
      } catch (error) {
        console.error(
          "Worker error:",
          error.message
        );
      }

      completed++;

      if (onProgress) {
        onProgress(
          completed,
          items.length
        );
      }
    }
  }

  const count = Math.min(
    concurrency,
    items.length
  );

  await Promise.all(
    Array.from(
      { length: count },
      () => runner()
    )
  );
}

// ============================================================
// 🇺🇸 فحص السوق الأمريكي
// ============================================================

let usScanRunning = false;

async function scanUS() {
  if (usScanRunning) {
    console.log(
      "⏳ 🇺🇸 US scan already running"
    );
    return;
  }

  usScanRunning = true;

  try {
    console.log(
      "\n🔍 جاري الفحص الكامل للأسهم الأمريكية..."
    );

    // --------------------------------------------------------
    // 1️⃣ جلب جميع بيانات اليوم دفعة واحدة
    // --------------------------------------------------------

    const bulk =
      await getBulkLastDay("US");

    console.log(
      `🇺🇸 Bulk rows: ${bulk.length}`
    );

    // --------------------------------------------------------
    // 2️⃣ فلترة السعر $0.20+
    // --------------------------------------------------------

    const candidates =
      filterMarketByPrice(
        bulk,
        US_CONFIG.minPrice
      );

    console.log(
      `🇺🇸 بعد فلترة $0.20+: ${candidates.length}`
    );

    let completed = 0;
    let signals = [];

    await runWorkers(
      candidates,
      async (row) => {
        const symbol =
          String(
            row.code ||
            row.Code ||
            ""
          ).trim();

        if (!symbol) return;

        const result =
          await analyzeStock(
            symbol,
            "US",
            row
          );

        if (!result) return;

        signals.push(result);

        // إرسال الإشارة فور اكتشافها
        if (
          signals.length <=
          US_CONFIG.maxAlertsPerScan
        ) {
          await broadcast(
            usBot,
            usChatIds,
            buildMessage(result)
          );
        }
      },
      EODHD_CONFIG.scanConcurrency,
      (done, total) => {
        completed = done;

        if (
          done === 1 ||
          done % 250 === 0 ||
          done === total
        ) {
          console.log(
            `🇺🇸 التقدم: ${done}/${total} | إشارات: ${signals.length}`
          );
        }
      }
    );

    signals.sort(
      (a, b) =>
        b.score - a.score
    );

    console.log(
      `✅ 🇺🇸 انتهى الفحص — ${completed}/${candidates.length} — الإشارات: ${signals.length}`
    );

  } catch (error) {
    console.error(
      "❌ US scan failed:",
      error.message
    );
  } finally {
    usScanRunning = false;
  }
}

// ============================================================
// 🇸🇦 فحص تاسي
// ============================================================

let tasiScanRunning = false;

async function scanTASI() {
  if (tasiScanRunning) {
    console.log(
      "⏳ 🇸🇦 TASI scan already running"
    );
    return;
  }

  tasiScanRunning = true;

  try {
    console.log(
      "\n🔍 جاري الفحص الكامل لأسهم تاسي..."
    );

    // --------------------------------------------------------
    // 1️⃣ جلب قائمة جميع أسهم تاسي
    // --------------------------------------------------------

    const symbols =
      await getTasiSymbols();

    // --------------------------------------------------------
    // 2️⃣ جلب بيانات السوق دفعة واحدة
    // --------------------------------------------------------

    let bulk = [];

    try {
      bulk =
        await getBulkLastDay("SR");

      console.log(
        `🇸🇦 Bulk rows: ${bulk.length}`
      );
    } catch (bulkError) {
      console.warn(
        "⚠️ تعذر Bulk SR، سيتم الاعتماد على قائمة الرموز:",
        bulkError.message
      );
    }

    const bulkMap =
      new Map();

    for (const row of bulk) {
      const code =
        String(
          row.code ||
          row.Code ||
          ""
        ).trim();

      if (code) {
        bulkMap.set(
          code.toUpperCase(),
          row
        );
      }
    }

    let candidates =
      symbols
        .map((item) => ({
          ...item,
          bulk:
            bulkMap.get(
              item.code.toUpperCase()
            ) || null,
        }))
        .filter((item) => {
          if (!item.bulk) return true;

          const price =
            Number(
              item.bulk.adjusted_close ??
              item.bulk.close ??
              0
            );

          return price > 0;
        });

    console.log(
      `🇸🇦 المرشحون للتحليل: ${candidates.length}`
    );

    let signals = [];

    await runWorkers(
      candidates,
      async (item) => {
        const result =
          await analyzeStock(
            item.code,
            "SR",
            item.bulk
          );

        if (!result) return;

        signals.push(result);

        if (
          signals.length <=
          TASI_CONFIG.maxAlertsPerScan
        ) {
          await broadcast(
            tasiBot,
            tasiChatIds,
            buildMessage(result)
          );
        }
      },
      EODHD_CONFIG.scanConcurrency,
      (done, total) => {
        if (
          done === 1 ||
          done % 50 === 0 ||
          done === total
        ) {
          console.log(
            `🇸🇦 التقدم: ${done}/${total} | إشارات: ${signals.length}`
          );
        }
      }
    );

    signals.sort(
      (a, b) =>
        b.score - a.score
    );

    console.log(
      `✅ 🇸🇦 انتهى الفحص — ${candidates.length} سهم — الإشارات: ${signals.length}`
    );

  } catch (error) {
    console.error(
      "❌ TASI scan failed:",
      error.message
    );
  } finally {
    tasiScanRunning = false;
  }
}

// ============================================================
// 🤖 TELEGRAM COMMANDS
// ============================================================

if (tasiBot) {

  tasiBot.onText(
    /\/start/,
    async (msg) => {
      tasiChatIds.add(
        msg.chat.id
      );

      await tasiBot.sendMessage(
        msg.chat.id,
        "🇸🇦 تم تفعيل بوت السوق السعودي AI PRO MAX\n\n🔍 جاري الفحص الكامل لأسهم تاسي..."
      );

      scanTASI();
    }
  );

  tasiBot.onText(
    /\/scan/,
    async (msg) => {
      tasiChatIds.add(
        msg.chat.id
      );

      await tasiBot.sendMessage(
        msg.chat.id,
        "🔍 بدء فحص تاسي الآن..."
      );

      scanTASI();
    }
  );
}

// ============================================================
// 🇺🇸 TELEGRAM COMMANDS
// ============================================================

if (usBot) {

  usBot.onText(
    /\/start/,
    async (msg) => {
      usChatIds.add(
        msg.chat.id
      );

      await usBot.sendMessage(
        msg.chat.id,
        "🇺🇸 تم تفعيل بوت السوق الأمريكي AI PRO MAX\n\n🔍 جاري الفحص الكامل للأسهم الأمريكية..."
      );

      scanUS();
    }
  );

  usBot.onText(
    /\/scan/,
    async (msg) => {
      usChatIds.add(
        msg.chat.id
      );

      await usBot.sendMessage(
        msg.chat.id,
        "🔍 بدء فحص السوق الأمريكي الآن..."
      );

      scanUS();
    }
  );
}

// ============================================================
// 🕒 AUTO SCAN
// ============================================================

let autoStarted = false;

async function startAutoScanner() {
  if (autoStarted) return;

  autoStarted = true;

  console.log(
    "\n🚀 AI PRO MAX AUTO SCANNER LIVE 24/7"
  );

  console.log(
    "🇺🇸 US + 🇸🇦 TASI"
  );

  // أول فحص
  setTimeout(() => {
    if (US_CONFIG.enabled) {
      scanUS();
    }

    if (TASI_CONFIG.enabled) {
      scanTASI();
    }
  }, 5000);

  // كل دورة مستقلة
  setInterval(
    () => {
      if (US_CONFIG.enabled) {
        scanUS();
      }
    },
    EODHD_CONFIG.updateIntervalMinutes *
      60 *
      1000
  );

  setInterval(
    () => {
      if (TASI_CONFIG.enabled) {
        scanTASI();
      }
    },
    EODHD_CONFIG.updateIntervalMinutes *
      60 *
      1000
  );
}

// ============================================================
// 🚀 START
// ============================================================

checkConfig();

startAutoScanner();