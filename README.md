// ============================================================
// 💀 US STOCK SCANNER TELEGRAM BOT
// نسخة مستقرة بدون Finnhub API
// يعتمد على Yahoo Finance Public Chart/Screener
// ============================================================
// Node.js 18+ مطلوب
// لا تحتاج node-fetch
import express from "express";
import TelegramBot from "node-telegram-bot-api";
const app = express();
app.use(express.json());
// ============================================================
// 🔐 الإعدادات
// ============================================================
// ضعها في Environment Variables
const TOKEN = process.env.TELEGRAM_TOKEN;
// عدد الأسهم التي يتم فحصها في كل دورة
const MAX_SYMBOLS = Number(process.env.MAX_SYMBOLS || 250);
// الحد الأدنى للتغير لإرسال الإشارة
const MIN_CHANGE = Number(process.env.MIN_CHANGE || 0.30);
// كل كم دقيقة يعاد الفحص
const SCAN_INTERVAL_MIN = Number(
  process.env.SCAN_INTERVAL_MIN || 5
);
// تحديث الإشارات الموجودة
const UPDATE_INTERVAL_SEC = Number(
  process.env.UPDATE_INTERVAL_SEC || 30
);
// التأخير بين طلبات الأسعار
const REQUEST_DELAY_MS = Number(
  process.env.REQUEST_DELAY_MS || 350
);
// ============================================================
// 🔐 التأكد من TOKEN
// ============================================================
if (!TOKEN) {
  console.error(
    "❌ TELEGRAM_TOKEN غير موجود في Environment Variables"
  );
  process.exit(1);
}
// ============================================================
// 🤖 Telegram
// ============================================================
const bot = new TelegramBot(TOKEN, {
  polling: true,
});
// ============================================================
// 🌐 Web Server
// ============================================================
const PORT = Number(process.env.PORT || 3000);
app.get("/", (req, res) => {
  res.status(200).send("💀 US STOCK BOT RUNNING");
});
app.get("/health", (req, res) => {
  res.json({
    status: "ok",
    running,
    users: chatIds.size,
    signals: Object.keys(sentSignals).length,
    uptime: Math.floor(process.uptime()),
  });
});
app.listen(PORT, () => {
  console.log(`🌐 Server running on port ${PORT}`);
});
// ============================================================
// 🧠 حالة البوت
// ============================================================
const chatIds = new Set();
let running = false;
let scanStartedAt = null;
let lastScanAt = null;
let lastScanCount = 0;
const sentSignals = new Map();
const lastRequest = new Map();
let cachedSymbols = [];
let symbolsCacheTime = 0;
const SYMBOL_CACHE_MS = 15 * 60 * 1000;
// ============================================================
// ⏳ Delay
// ============================================================
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
// ============================================================
// 🔒 تنظيف الرمز
// ============================================================
function cleanSymbol(symbol) {
  if (!symbol) return "";
  return String(symbol)
    .trim()
    .toUpperCase()
    .replace(/\./g, "-");
}
// ============================================================
// 💰 Yahoo Chart
// ============================================================
async function yahooChart(symbol) {
  try {
    const now = Math.floor(Date.now() / 1000);
    const url =
      "https://query1.finance.yahoo.com/v8/finance/chart/" +
      encodeURIComponent(symbol) +
      "?period1=" +
      (now - 86400 * 5) +
      "&period2=" +
      now +
      "&interval=1d&events=history&includeAdjustedClose=true";
    const response = await fetch(url, {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        Accept: "application/json",
      },
    });
    if (!response.ok) {
      return null;
    }
    const json = await response.json();
    const result = json?.chart?.result?.[0];
    if (!result) {
      return null;
    }
    const meta = result.meta;
    const price =
      Number(meta?.regularMarketPrice) ||
      Number(meta?.previousClose);
    const previousClose =
      Number(meta?.previousClose) ||
      Number(meta?.chartPreviousClose);
    if (
      !Number.isFinite(price) ||
      !Number.isFinite(previousClose) ||
      price <= 0 ||
      previousClose <= 0
    ) {
      return null;
    }
    const change =
      ((price - previousClose) / previousClose) * 100;
    return {
      symbol,
      price,
      previousClose,
      change,
      currency: meta?.currency || "USD",
      exchange: meta?.exchangeName || "US",
      marketState: meta?.marketState || "UNKNOWN",
    };
  } catch (error) {
    console.log(
      `⚠️ Yahoo error ${symbol}:`,
      error.message
    );
    return null;
  }
}
// ============================================================
// 🔥 Yahoo Screener
// ============================================================
async function yahooScreener(scrId, count = 250) {
  try {
    const url =
      "https://query1.finance.yahoo.com/v1/finance/screener/predefined" +
      "?scrIds=" +
      encodeURIComponent(scrId) +
      "&count=" +
      count;
    const response = await fetch(url, {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        Accept: "application/json",
      },
    });
    if (!response.ok) {
      console.log(
        `⚠️ Screener ${scrId}: HTTP ${response.status}`
      );
      return [];
    }
    const json = await response.json();
    const quotes =
      json?.finance?.result?.[0]?.quotes || [];
    return quotes
      .map((q) => cleanSymbol(q.symbol))
      .filter(Boolean);
  } catch (error) {
    console.log(
      `⚠️ Screener error ${scrId}:`,
      error.message
    );
    return [];
  }
}
// ============================================================
// 📋 الحصول على الأسهم
// ============================================================
async function getUSSymbols(force = false) {
  const now = Date.now();
  if (
    !force &&
    cachedSymbols.length > 0 &&
    now - symbolsCacheTime < SYMBOL_CACHE_MS
  ) {
    return cachedSymbols;
  }
  console.log("📋 تحديث قائمة الأسهم...");
  const sets = await Promise.all([
    yahooScreener("day_gainers", 250),
    yahooScreener("most_actives", 250),
    yahooScreener("day_losers", 100),
    yahooScreener("growth_technology_stocks", 250),
  ]);
  const unique = new Set();
  for (const list of sets) {
    for (const symbol of list) {
      if (unique.size >= MAX_SYMBOLS) {
        break;
      }
      unique.add(symbol);
    }
  }
  cachedSymbols = [...unique];
  symbolsCacheTime = now;
  console.log(
    `📊 تم تحميل ${cachedSymbols.length} سهم`
  );
  return cachedSymbols;
}
// ============================================================
// 🛡️ منع الطلبات السريعة لنفس السهم
// ============================================================
function canRequest(symbol) {
  const now = Date.now();
  const previous = lastRequest.get(symbol) || 0;
  if (now - previous < 1000) {
    return false;
  }
  lastRequest.set(symbol, now);
  return true;
}
// ============================================================
// 💰 جلب السعر مع إعادة المحاولة
// ============================================================
async function getQuote(symbol, retries = 2) {
  symbol = cleanSymbol(symbol);
  if (!symbol) {
    return null;
  }
  if (!canRequest(symbol)) {
    return null;
  }
  for (let attempt = 0; attempt <= retries; attempt++) {
    const data = await yahooChart(symbol);
    if (data) {
      return data;
    }
    if (attempt < retries) {
      await sleep(1000 * (attempt + 1));
    }
  }
  return null;
}
// ============================================================
// 🧠 تحليل السهم
// ============================================================
function analyze(data) {
  if (!data) {
    return null;
  }
  const price = data.price;
  const change = data.change;
  let signal = "⚪ مراقبة";
  let strength = 0;
  if (change >= 5) {
    signal = "💀🚀 انفجار قوي";
    strength = 100;
  } else if (change >= 3) {
    signal = "🚀 صعود قوي";
    strength = 90;
  } else if (change >= 2) {
    signal = "🔥 صعود";
    strength = 75;
  } else if (change >= 1) {
    signal = "🟢 إيجابي";
    strength = 60;
  } else if (change >= 0.3) {
    signal = "🟢 بداية صعود";
    strength = 50;
  } else if (change <= -5) {
    signal = "🚨 هبوط قوي";
    strength = 0;
  } else if (change <= -3) {
    signal = "🔻 هبوط";
    strength = 10;
  } else if (change < 0) {
    signal = "🔴 سلبي";
    strength = 25;
  }
  // ========================================================
  // 🎯 الأهداف
  // ========================================================
  const targets = [
    price * 1.02,
    price * 1.04,
    price * 1.06,
    price * 1.08,
    price * 1.10,
    price * 1.12,
    price * 1.15,
    price * 1.18,
  ];
  return {
    symbol: data.symbol,
    price,
    previousClose: data.previousClose,
    change,
    signal,
    strength,
    targets,
    marketState: data.marketState,
    createdAt: Date.now(),
  };
}
// ============================================================
// 🎯 تنسيق السعر
// ============================================================
function priceFormat(value) {
  if (!Number.isFinite(value)) {
    return "0.00";
  }
  if (value < 1) {
    return value.toFixed(4);
  }
  if (value < 10) {
    return value.toFixed(3);
  }
  return value.toFixed(2);
}
// ============================================================
// 🎯 فحص الهدف
// ============================================================
function targetStatus(price, target) {
  return price >= target ? "✅" : "";
}
// ============================================================
// 📩 رسالة السهم
// ============================================================
function formatSignal(s) {
  const targetLines = s.targets
    .map(
      (target, index) =>
        `🎯 الهدف ${index + 1}: ${priceFormat(
          target
        )} ${targetStatus(s.price, target)}`
    )
    .join("\n");
  const direction =
    s.change >= 0 ? "📈" : "📉";
  return `
🇺🇸 <b>السوق الأمريكي</b>
<b>💠 ${s.symbol}</b>
💰 السعر: <b>$${priceFormat(s.price)}</b>
${direction} التغير: <b>${s.change.toFixed(2)}%</b>
📊 الإشارة:
<b>${s.signal}</b>
💪 قوة الإشارة:
<b>${s.strength}%</b>
━━━━━━━━━━━━━━
🎯 <b>الأهداف</b>
━━━━━━━━━━━━━━
${targetLines}
━━━━━━━━━━━━━━
🕐 حالة السوق:
${s.marketState}
⚠️ الإشارة آلية وليست توصية مالية.
`;
}
// ============================================================
// 📤 إرسال للجميع
// ============================================================
async function sendToAll(text) {
  for (const chatId of chatIds) {
    try {
      await bot.sendMessage(chatId, text, {
        parse_mode: "HTML",
        disable_web_page_preview: true,
      });
      await sleep(250);
    } catch (error) {
      console.log(
        `⚠️ Telegram error ${chatId}:`,
        error.message
      );
      // المستخدم حظر البوت
      if (
        error.message?.includes("bot was blocked") ||
        error.message?.includes("chat not found") ||
        error.message?.includes("user is deactivated")
      ) {
        chatIds.delete(chatId);
      }
    }
  }
}
// ============================================================
// 🔥 إرسال إشارة جديدة فقط
// ============================================================
async function processSignal(data) {
  if (!data) {
    return;
  }
  const analysis = analyze(data);
  if (!analysis) {
    return;
  }
  if (analysis.change < MIN_CHANGE) {
    return;
  }
  const old = sentSignals.get(analysis.symbol);
  // ========================================================
  // منع التكرار
  // ========================================================
  if (old) {
    const priceMove =
      Math.abs(
        (analysis.price - old.price) /
          old.price
      ) * 100;
    // إذا لم يتحرك السعر بشكل واضح لا ترسل مرة أخرى
    if (priceMove < 1) {
      return;
    }
  }
  sentSignals.set(
    analysis.symbol,
    analysis
  );
  const text = formatSignal(analysis);
  await sendToAll(text);
}
// ============================================================
// 🚀 الفحص الرئيسي
// ============================================================
async function runScan(force = false) {
  if (running) {
    console.log("⏳ الفحص السابق ما زال يعمل");
    return;
  }
  running = true;
  scanStartedAt = Date.now();
  console.log("=================================");
  console.log("🚀 بدء فحص السوق الأمريكي");
  console.log("=================================");
  try {
    const symbols =
      await getUSSymbols(force);
    let scanned = 0;
    for (const symbol of symbols) {
      try {
        const data =
          await getQuote(symbol);
        if (data) {
          scanned++;
          await processSignal(data);
        }
        await sleep(REQUEST_DELAY_MS);
      } catch (error) {
        console.log(
          `⚠️ ${symbol}:`,
          error.message
        );
      }
    }
    lastScanCount = scanned;
    lastScanAt = Date.now();
    console.log(
      `✅ انتهى الفحص — تم تحليل ${scanned} سهم`
    );
  } catch (error) {
    console.log(
      "❌ Scan ERROR:",
      error.message
    );
  } finally {
    running = false;
  }
}
// ============================================================
// 🔄 تحديث الإشارات الموجودة
// ============================================================
async function updateSignals() {
  if (sentSignals.size === 0) {
    return;
  }
  console.log(
    `🔄 تحديث ${sentSignals.size} إشارة`
  );
  for (const [
    symbol,
    signal,
  ] of sentSignals) {
    try {
      const data =
        await getQuote(symbol);
      if (!data) {
        continue;
      }
      const oldPrice = signal.price;
      signal.price = data.price;
      signal.change = data.change;
      signal.marketState =
        data.marketState;
      // إعادة حساب الأهداف
      signal.targets = [
        signal.price * 1.02,
        signal.price * 1.04,
        signal.price * 1.06,
        signal.price * 1.08,
        signal.price * 1.10,
        signal.price * 1.12,
        signal.price * 1.15,
        signal.price * 1.18,
      ];
      // ======================================================
      // لا نرسل رسالة عند كل تحديث بسيط
      // ======================================================
      const movement =
        Math.abs(
          ((signal.price - oldPrice) /
            oldPrice) *
            100
        );
      if (movement >= 1) {
        await sendToAll(
          formatSignal(signal)
        );
      }
      await sleep(
        REQUEST_DELAY_MS
      );
    } catch (error) {
      console.log(
        `⚠️ Update ${symbol}:`,
        error.message
      );
    }
  }
}
// ============================================================
// 🤖 Telegram Commands
// ============================================================
bot.on("message", async (msg) => {
  const chatId = msg.chat.id;
  chatIds.add(chatId);
  const text =
    (msg.text || "").trim().toLowerCase();
  // ========================================================
  // START
  // ========================================================
  if (text === "/start") {
    await bot.sendMessage(
      chatId,
      `
💀 <b>US STOCK BOT</b>
🟢 البوت يعمل الآن
━━━━━━━━━━━━━━
📊 /scan
بدء فحص السوق
📈 /signals
الإشارات الحالية
📊 /status
حالة البوت
🛑 /stop
إيقاف الفحص الحالي
🔄 /refresh
تحديث قائمة الأسهم
━━━━━━━━━━━━━━
🇺🇸 السوق الأمريكي
`,
      {
        parse_mode: "HTML",
      }
    );
    return;
  }
  // ========================================================
  // SCAN
  // ========================================================
  if (text === "/scan") {
    await bot.sendMessage(
      chatId,
      "🚀 جاري فحص السوق الأمريكي..."
    );
    runScan(true);
    return;
  }
  // ========================================================
  // SIGNALS
  // ========================================================
  if (text === "/signals") {
    if (sentSignals.size === 0) {
      await bot.sendMessage(
        chatId,
        "⚪ لا توجد إشارات محفوظة حاليًا."
      );
      return;
    }
    let message =
      "📊 <b>الإشارات الحالية</b>\n\n";
    let counter = 0;
    for (const [
      symbol,
      signal,
    ] of sentSignals) {
      counter++;
      message +=
        `${counter}. <b>${symbol}</b> ` +
        `$${priceFormat(signal.price)} ` +
        `${signal.change >= 0 ? "📈" : "📉"} ` +
        `${signal.change.toFixed(2)}%\n`;
      if (counter >= 30) {
        break;
      }
    }
    await bot.sendMessage(
      chatId,
      message,
      {
        parse_mode: "HTML",
      }
    );
    return;
  }
  // ========================================================
  // STATUS
  // ========================================================
  if (text === "/status") {
    const uptime =
      Math.floor(
        process.uptime()
      );
    const hours =
      Math.floor(uptime / 3600);
    const minutes =
      Math.floor(
        (uptime % 3600) / 60
      );
    const seconds =
      uptime % 60;
    await bot.sendMessage(
      chatId,
      `
🟢 <b>حالة البوت</b>
الحالة:
${running ? "🔴 فحص يعمل" : "🟢 جاهز"}
👥 المستخدمون:
${chatIds.size}
📊 الأسهم:
${cachedSymbols.length}
🎯 الإشارات:
${sentSignals.size}
📡 آخر فحص:
${
  lastScanAt
    ? new Date(lastScanAt).toLocaleString(
        "en-US"
      )
    : "لم يبدأ"
}
📈 الأسهم التي تم تحليلها:
${lastScanCount}
⏱️ التشغيل:
${hours}h ${minutes}m ${seconds}s
`,
      {
        parse_mode: "HTML",
      }
    );
    return;
  }
  // ========================================================
  // STOP
  // ========================================================
  if (text === "/stop") {
    if (!running) {
      await bot.sendMessage(
        chatId,
        "🟢 لا يوجد فحص يعمل حاليًا."
      );
      return;
    }
    await bot.sendMessage(
      chatId,
      "⚠️ لا يمكن إلغاء طلب الشبكة الجاري، لكنه سيتوقف بعد انتهاء الدورة الحالية."
    );
    return;
  }
  // ========================================================
  // REFRESH
  // ========================================================
  if (text === "/refresh") {
    cachedSymbols = [];
    symbolsCacheTime = 0;
    await bot.sendMessage(
      chatId,
      "🔄 تم حذف القائمة القديمة. سيتم تحميل قائمة جديدة في الفحص القادم."
    );
    return;
  }
});
// ============================================================
// 🚨 أخطاء Telegram
// ============================================================
bot.on("polling_error", (error) => {
  console.log(
    "⚠️ Telegram polling:",
    error.message
  );
});
// ============================================================
// 🚨 أخطاء عامة
// ============================================================
process.on("unhandledRejection", (error) => {
  console.log(
    "❌ Unhandled rejection:",
    error
  );
});
process.on("uncaughtException", (error) => {
  console.log(
    "❌ Uncaught exception:",
    error
  );
});
// ============================================================
// 🔄 الفحص التلقائي
// ============================================================
setInterval(() => {
  runScan(false);
}, SCAN_INTERVAL_MIN * 60 * 1000);
// ============================================================
// 🔄 تحديث الإشارات
// ============================================================
setInterval(() => {
  updateSignals();
}, UPDATE_INTERVAL_SEC * 1000);
// ============================================================
// 🚀 تشغيل أول فحص
// ============================================================
setTimeout(() => {
  runScan(true);
}, 5000);
// ============================================================
// 💀 READY
// ============================================================
console.log("");
console.log("=================================");
console.log("💀 US STOCK BOT");
console.log("🟢 BOT ONLINE");
console.log("📡 Yahoo Finance Data");
console.log("🚫 Finnhub API NOT REQUIRED");
console.log("=================================");
console.log("");
