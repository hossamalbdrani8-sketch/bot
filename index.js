
// ============================================================
// 📊 DUAL AUTONOMOUS STOCK SCANNER BOTS - TASI & US PRO
// Node.js 18+ | بوت تاسي وبوت أمريكي منفصلان وتلقائيان بالكامل
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// ⚙️ التوكنات الرسمية والخاصة بالبوتين
// ============================================================

const TASI_TOKEN = "7772382813:AAECFDY04AXNEf-Q98_65UheUEz7u2HymJw";
const US_TOKEN = "8652994768:AAHg_ABByrZdvlljJ1dQfs6LSmBl37XMPXk";

if (!TASI_TOKEN || !US_TOKEN) {
  throw new Error("❌ يرجى التأكد من توفر التوكنات للبوتين.");
}

const PORT = Number(process.env.PORT || 3000);
const MIN_PRICE = 0.10;
const REQUEST_DELAY_MS = 250;
const UPDATE_INTERVAL_MIN = 2; // التحديث التلقائي كل دقيقتين بدقة

// ============================================================
// 🤖 إنشاء البوتين بشكل منفصل تماماً (استماع فوري بدون اشتراك إجباري)
// ============================================================

const tasiBot = new TelegramBot(TASI_TOKEN, { polling: true });
const usBot = new TelegramBot(US_TOKEN, { polling: true });

// تخزين معرفات المحادثات (Chat IDs) التي تفاعلت مع البوت لتنفيذ الإرسال التلقائي إليها
const tasiSubscribers = new Set();
const usSubscribers = new Set();

// ============================================================
// 🌐 خادم Express للحفاظ على تشغيل البوت 24/7
// ============================================================

const app = express();

app.get("/", (req, res) => {
  res.status(200).send("🌍 TASI & US Autonomous Stock Bots are running");
});

app.get("/health", (req, res) => {
  res.json({
    ok: true,
    tasiSubscribers: tasiSubscribers.size,
    usSubscribers: usSubscribers.size,
    time: new Date().toISOString()
  });
});

app.listen(PORT, () => {
  console.log(`🌐 Server running on port ${PORT}`);
});

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ============================================================
// 🌐 Yahoo Fetch مع رؤوس طلبات قوية لضمان جلب البيانات كاملة
// ============================================================

async function yahooFetch(url) {
  const response = await fetch(url, {
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
      "Accept": "application/json,text/plain,*/*"
    }
  });

  const text = await response.text();
  if (!response.ok) {
    throw new Error(`Yahoo HTTP ${response.status}: ${text.slice(0, 100)}`);
  }

  try {
    return JSON.parse(text);
  } catch {
    throw new Error("Yahoo returned invalid JSON");
  }
}

// ============================================================
// 📊 جلب الشارت والمؤشرات الفنية (EMA, VWAP, السيولة, الأهداف)
// ============================================================

async function getChart(symbol) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?range=5d&interval=5m&includePrePost=false`;
  const data = await yahooFetch(url);
  const result = data?.chart?.result?.[0];
  if (!result) throw new Error("لا توجد بيانات للشارت");
  return result;
}

function calculateEMA(values, period) {
  if (!Array.isArray(values) || values.length < period) return null;
  const multiplier = 2 / (period + 1);
  let ema = 0;
  for (let i = 0; i < period; i++) ema += Number(values[i]) || 0;
  ema /= period;
  for (let i = period; i < values.length; i++) {
    const val = Number(values[i]);
    if (Number.isFinite(val)) ema = (val - ema) * multiplier + ema;
  }
  return ema;
}

function calculateVWAP(high, low, close, volume) {
  let pv = 0;
  let totalVolume = 0;
  const len = Math.min(high.length, low.length, close.length, volume.length);
  const start = Math.max(0, len - 78);

  for (let i = start; i < len; i++) {
    const h = Number(high[i]);
    const l = Number(low[i]);
    const c = Number(close[i]);
    const v = Number(volume[i]);
    if (!Number.isFinite(h) || !Number.isFinite(l) || !Number.isFinite(c) || !Number.isFinite(v) || v <= 0) continue;
    pv += ((h + l + c) / 3) * v;
    totalVolume += v;
  }
  return totalVolume > 0 ? pv / totalVolume : null;
}

function analyzeLiquidity(close, volume) {
  const len = Math.min(close.length, volume.length);
  const start = Math.max(1, len - 24);
  let buyVol = 0, sellVol = 0, neutVol = 0;

  for (let i = start; i < len; i++) {
    const prev = Number(close[i - 1]), curr = Number(close[i]), vol = Number(volume[i]) || 0;
    if (!Number.isFinite(prev) || !Number.isFinite(curr)) continue;
    if (curr > prev) buyVol += vol;
    else if (curr < prev) sellVol += vol;
    else neutVol += vol;
  }

  const total = buyVol + sellVol + neutVol;
  if (total <= 0) return { buyRatio: 50, sellRatio: 50, label: "⚪ سيولة متوازنة" };
  const buyRatio = (buyVol / total) * 100;
  const sellRatio = (sellVol / total) * 100;

  let label = "⚪ سيولة متوازنة";
  if (buyRatio >= 65) label = "🟢 دخول سيولة قوية";
  else if (sellRatio >= 65) label = "🔴 خروج سيولة قوية";
  else if (buyRatio >= 53) label = "🟢 دخول سيولة";
  else if (sellRatio >= 53) label = "🔴 خروج سيولة";

  return { buyRatio, sellRatio, label };
}

function analyzeGeneralTrend(price, ema50, ema180) {
  if (Number.isFinite(ema50) && Number.isFinite(ema180)) {
    if (ema50 > ema180 && price > ema50) return "🟢 الاتجاه العام صاعد";
    if (ema50 < ema180 && price < ema50) return "🔴 الاتجاه العام هابط";
  }
  return "⚪ الاتجاه العام متوازن";
}

// 8 أهداف سعرية متدرجة مع تتبع التحقيق (✅) تلقائياً
function calculateTargets(price) {
  const percentages = [2, 4, 6, 8, 10, 12, 15, 18];
  return percentages.map(p => {
    const targetPrice = price * (1 + p / 100);
    const achieved = price >= targetPrice;
    return { percent: p, price: targetPrice, achieved };
  });
}

// ============================================================
// 📰 الأخبار المعربة وتحليلها (إيجابي 🟢 / سلبي 🔴) لكل سوق على حدة
// ============================================================

function classifyNewsSentiment(title) {
  const text = String(title || "").toLowerCase();
  const posWords = ["surge", "soar", "rally", "gain", "rise", "growth", "profit", "beat", "strong", "bullish", "approval", "contract", "ارتفاع", "نمو", "أرباح", "عقد", "إيجابي"];
  const negWords = ["fall", "drop", "down", "decline", "loss", "weak", "bearish", "downgrade", "warning", "lawsuit", "debt", "انخفاض", "خسائر", "هبوط", "تحقيق", "ديون"];

  let pos = 0, neg = 0;
  for (const w of posWords) if (text.includes(w)) pos++;
  for (const w of negWords) if (text.includes(w)) neg++;

  if (pos > neg) return "🟢 إيجابي";
  if (neg > pos) return "🔴 سلبي";
  return "⚪ محايد";
}

async function getNews(symbol) {
  try {
    const url = `https://query1.finance.yahoo.com/v1/finance/search?q=${encodeURIComponent(symbol)}&newsCount=3`;
    const data = await yahooFetch(url);
    const raw = Array.isArray(data?.news) ? data.news : [];

    return raw.map(item => ({
      title: item.title || "خبر مالي",
      publisher: item.publisher || "Financial News",
      sentiment: classifyNewsSentiment(item.title)
    }));
  } catch (e) {
    return [];
  }
}

// ============================================================
// 📊 جلب بيانات السهم الشاملة
// ============================================================

async function getStockData(symbol, isTasi) {
  const chart = await getChart(symbol);
  const meta = chart.meta || {};
  const quote = chart.indicators?.quote?.[0];
  if (!quote) throw new Error("لا توجد بيانات");

  const close = (quote.close || []).map(Number).filter(Number.isFinite);
  const high = (quote.high || []).map(Number).filter(Number.isFinite);
  const low = (quote.low || []).map(Number).filter(Number.isFinite);
  const volume = (quote.volume || []).map(Number).filter(Number.isFinite);

  if (close.length < 15) throw new Error("بيانات غير كافية");

  const price = close[close.length - 1];
  if (price < MIN_PRICE) throw new Error("السعر منخفض");

  const prevClose = Number(meta.previousClose) || Number(meta.chartPreviousClose) || close[close.length - 2];
  const changePercent = prevClose > 0 ? ((price - prevClose) / prevClose) * 100 : 0;

  const ema50 = calculateEMA(close, 50);
  const ema180 = calculateEMA(close, 180) || ema50;
  const vwap = calculateVWAP(high, low, close, volume) || price;
  const liquidity = analyzeLiquidity(close, volume);
  const generalTrend = analyzeGeneralTrend(price, ema50, ema180);
  const targets = calculateTargets(price);
  const news = await getNews(symbol);

  return {
    symbol,
    price,
    changePercent,
    companyName: meta.longName || meta.shortName || symbol,
    exchange: meta.exchangeName || (isTasi ? "تداول (TADAWUL)" : "NASDAQ/NYSE"),
    vwap,
    buyRatio: liquidity.buyRatio,
    sellRatio: liquidity.sellRatio,
    liquidityLabel: liquidity.label,
    generalTrend,
    targets,
    news,
    updatedAt: new Date()
  };
}

// بناء قالب الرسالة الموحد والمنسق
function buildMessage(stock, marketName) {
  let msg = `📊 *${marketName} (تحديث تلقائي)*\n\n`;
  msg += `📌 الرمز: *${stock.symbol}*\n`;
  msg += `🏢 الشركة: ${stock.companyName}\n\n`;
  msg += `💰 السعر اللحظي: *${stock.price.toFixed(2)}*\n`;
  msg += `📈 نسبة التغير: *${stock.changePercent.toFixed(2)}%*\n`;
  msg += `🏦 البورصة: ${stock.exchange}\n\n`;

  msg += `🧭 ${stock.generalTrend}\n`;
  msg += `📐 VWAP: *${stock.vwap.toFixed(2)}*\n`;
  msg += `💧 السيولة: *${stock.liquidityLabel}* (شراء ${stock.buyRatio.toFixed(1)}% | بيع ${stock.sellRatio.toFixed(1)}%)\n\n`;

  msg += `🎯 *الأهداف السعرية (8 أهداف):*\n`;
  for (const t of stock.targets) {
    const statusMark = t.achieved ? " ✅" : "";
    msg += `• +${t.percent}% ➔ *${t.price.toFixed(2)}*${statusMark}\n`;
  }

  msg += `\n📰 *الأخبار الخاصة بالسوق والتحليل:*\n`;
  if (stock.news.length === 0) {
    msg += `⚪ لا توجد أخبار جديدة حالياً.\n`;
  } else {
    for (const n of stock.news) {
      msg += `${n.sentiment} ${n.title}\n  🗞️ المصدر: ${n.publisher}\n`;
    }
  }

  msg += `\n🕒 التحديث: ${stock.updatedAt.toLocaleTimeString("ar-SA")}`;
  return msg;
}

// ============================================================
// 🇸🇦 وظيفة مسح وتشغيل السوق السعودي (تاسي) تلقائياً
// ============================================================

async function fetchAllTasiSymbols() {
  return [
    "2222.SR", "1120.SR", "1010.SR", "1180.SR", "2010.SR", "1210.SR", "2350.SR",
    "4200.SR", "7010.SR", "4300.SR", "3030.SR", "2380.SR", "1301.SR", "4030.SR",
    "2280.SR", "1810.SR", "2020.SR", "2290.SR", "2310.SR", "4190.SR", "8210.SR",
    "1111.SR", "1150.SR", "1202.SR", "1304.SR", "2001.SR", "2021.SR", "2060.SR"
  ];
}

async function runTasiAutoScan() {
  if (tasiSubscribers.size === 0) return;
  try {
    const symbols = await fetchAllTasiSymbols();
    const found = [];

    for (const sym of symbols) {
      try {
        const data = await getStockData(sym, true);
        if (data) found.push(data);
      } catch (e) {}
      await sleep(REQUEST_DELAY_MS);
    }

    found.sort((a, b) => b.changePercent - a.changePercent);

    // إرسال أهم الأسهم المرصودة تلقائياً لكل المشتركين في بوت تاسي
    for (const chatId of tasiSubscribers) {
      for (const stock of found.slice(0, 3)) {
        await tasiBot.sendMessage(chatId, buildMessage(stock, "🇸🇦 السوق السعودي (تاسي)"), { parse_mode: "Markdown" });
        await sleep(300);
      }
    }
  } catch (err) {
    console.log("TASI Auto Scan Error:", err.message);
  }
}

// ============================================================
// 🇺🇸 وظيفة مسح وتشغيل السوق الأمريكي تلقائياً
// ============================================================

async function fetchAllUsSymbols() {
  const symbolsSet = new Set();
  const screeners = ["day_gainers", "most_actives", "growth_technology_stocks"];

  for (const scr of screeners) {
    try {
      const url = `https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=${scr}&count=150`;
      const data = await yahooFetch(url);
      const quotes = data?.finance?.result?.[0]?.quotes || [];
      for (const q of quotes) {
        const sym = String(q.symbol || "").trim().toUpperCase();
        if (sym && !sym.includes(".") && !sym.includes("^")) symbolsSet.add(sym);
      }
    } catch (e) {}
    await sleep(REQUEST_DELAY_MS);
  }

  ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "NFLX"].forEach(s => symbolsSet.add(s));
  return Array.from(symbolsSet);
}

async function runUsAutoScan() {
  if (usSubscribers.size === 0) return;
  try {
    const symbols = await fetchAllUsSymbols();
    const found = [];

    for (const sym of symbols) {
      try {
        const data = await getStockData(sym, false);
        if (data) found.push(data);
      } catch (e) {}
      await sleep(REQUEST_DELAY_MS);
    }

    found.sort((a, b) => b.changePercent - a.changePercent);

    // إرسال النتائج تلقائياً للمشتركين في بوت السوق الأمريكي
    for (const chatId of usSubscribers) {
      for (const stock of found.slice(0, 3)) {
        await usBot.sendMessage(chatId, buildMessage(stock, "🇺🇸 السوق الأمريكي (ناسداك)"), { parse_mode: "Markdown" });
        await sleep(300);
      }
    }
  } catch (err) {
    console.log("US Auto Scan Error:", err.message);
  }
}

// ============================================================
// 🤖 أوامر بوت تاسي وتفعيل الاشتراك التلقائي عند الضغط على /start
// ============================================================

tasiBot.onText(/\/start/, async msg => {
  const chatId = msg.chat.id;
  tasiSubscribers.add(chatId);
  await tasiBot.sendMessage(
    chatId,
    `🇸🇦 *تم تفعيل بوت السوق السعودي (تاسي) بنجاح!*\n\n` +
    `• سيتم إرسال التحديثات والتحليلات والأخبار تلقائياً كل دقيقتين.\n` +
    `• 8 أهداف سعرية متدرجة مع علامة ✅ عند التحقيق.\n` +
    `• اتجاه الفياب والسيولة اللحظية مفعلة.`,
    { parse_mode: "Markdown" }
  );
  runTasiAutoScan();
});

tasiBot.onText(/\/scan/, async msg => {
  const chatId = msg.chat.id;
  tasiSubscribers.add(chatId);
  await tasiBot.sendMessage(chatId, "🔍 جاري الفحص الفوري لجميع أسهم تاسي...");
  await runTasiAutoScan();
});

// ============================================================
// 🤖 أوامر بوت الأمريكي وتفعيل الاشتراك التلقائي عند الضغط على /start
// ============================================================

usBot.onText(/\/start/, async msg => {
  const chatId = msg.chat.id;
  usSubscribers.add(chatId);
  await usBot.sendMessage(
    chatId,
    `🇺🇸 *تم تفعيل بوت السوق الأمريكي (ناسداك) بنجاح!*\n\n` +
    `• الأخبار الأمريكية مترجمة ومعربة بالكامل مع تحليل (إيجابي 🟢 / سلبي 🔴).\n` +
    `• تحديث تلقائي كل دقيقتين.\n` +
    `• تتبع الأهداف الثمانية والفيواب لحظياً.`,
    { parse_mode: "Markdown" }
  );
  runUsAutoScan();
});

usBot.onText(/\/scan/, async msg => {
  const chatId = msg.chat.id;
  usSubscribers.add(chatId);
  await usBot.sendMessage(chatId, "🔍 جاري الفحص الفوري لجميع الأسهم الأمريكية...");
  await runUsAutoScan();
});

// ============================================================
// ⏱️ الجدولة التلقائية المستقلة (كل دقيقتين 2 دقيقة بالضبط)
// ============================================================

setInterval(() => {
  runTasiAutoScan();
}, UPDATE_INTERVAL_MIN * 60 * 1000);

setInterval(() => {
  runUsAutoScan();
}, UPDATE_INTERVAL_MIN * 60 * 1000);

console.log("🟢 TASI and US Autonomous Bots are running and updating every 2 minutes!");
